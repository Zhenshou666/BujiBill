# -*- coding: utf-8 -*-
"""账单助手 —— 微信 / 支付宝 / 校园一卡通 三源账单整合与分析

启动：
    cd "C:\\Users\\ZhenShou\\Desktop\\本科课程文件\\Python\\账单助手"
    .\\.venv\\Scripts\\streamlit run app.py

设计原则：
    1. 先跑通数据，再做界面。所有图表都建立在 store.load() 出来的同一张宽表上。
    2. 金额永远存正数，方向单独一列，避免正负号混用导致的统计错误。
    3. 内部转账必须剔除，否则一卡通充值会让消费总额翻倍。
"""
from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, time as dtime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pandas.api.types import is_numeric_dtype
import streamlit as st

from billkit import ADAPTERS, CAMPUS_LOGIN_URL, CHANNELS, Kind, detect_channel, store
from billkit import insights
from billkit.adapters.campus import CampusAdapter
from billkit.classify import add_rule, load_rules
from billkit.models import Transaction
from ui.charts import apply_chart_theme, style_bar, style_pie
from ui.table import render_ledger
from ui.theme import apply_theme

st.set_page_config(page_title="不记账本", page_icon="📔", layout="wide")
apply_theme()        # 手帐风主题
apply_chart_theme()  # 图表统一主题（纸底、墨字、抹茶配色）

PROJECT_ROOT = Path(__file__).resolve().parent
CATEGORY_ORDER = ["餐饮", "交通", "日用", "学习", "娱乐", "通讯", "医疗", "住宿", "数码", "转账", "退款", "内部转账", "未分类"]

# 表格对外一律用中文列名，别把内部字段名暴露给用户
# 性质对外显示用更直白的说法
KIND_CN = {
    "消费": "消费",
    "内部转账": "账户互转",
    "退款": "退款",
    "还款": "还款",
    "待确认": "待确认",
}

# 图表统一用这一套颜色，和界面主题一致（别再让 Plotly 用默认蓝）
PALETTE = ["#9CB8A4", "#D6A6A2", "#8AA6BF", "#E6D2A2", "#A79BC0", "#B9CBB2", "#CBB8C6"]

COL_CN = {
    "ts": "时间", "channel": "渠道", "direction": "收支", "amount": "金额",
    "counterparty": "对方", "product": "商品", "category": "分类",
    "kind": "性质", "status": "状态", "note": "备注",
    "date": "日期", "month": "月份", "uid": "编号",
}


# ============================================================ 工具函数

def money(x: float) -> str:
    return f"¥{x:,.2f}"


# ============================================================ 分享模式

# 分享给同学看时设 BILLKIT_SHARE=1：每人拿到一份演示数据的副本，
# 看不到你自己的真实账本，导入的东西也只落在各自的临时库里。
SHARE_MODE = os.environ.get("BILLKIT_SHARE") == "1"


def _guest_name() -> str:
    """按浏览器会话生成一个访客账本名，同一会话始终同一个。"""
    try:
        sid = st.runtime.scriptrunner.get_script_run_ctx().session_id
    except Exception:  # noqa: BLE001
        sid = hashlib.md5(str(id(st)).encode()).hexdigest()
    return f"访客{str(sid)[:6]}"


GUEST = _guest_name() if SHARE_MODE else ""
if SHARE_MODE:
    store.purge_guests()
    # 从零开始：不塞演示数据，访客进来就是「先放一份账单进来吧」
    store.ensure_empty(GUEST)


# ============================================================ 多用户（账本）

def chart(fig) -> None:
    """所有图表统一出口（集中关掉 plotly 自带的工具条）。

    滚动条不在图表本身，而在外层 stElementContainer（它写死了 height:300px + overflow:auto），
    那层由 ui_theme 里的 :has() 规则统一处理。
    """
    # 关掉框选缩放：一旦框选放大就再也回不去，纯属添乱
    fig.update_layout(dragmode=False)
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    st.plotly_chart(
        fig, width="stretch",
        config={
            "displayModeBar": False,
            "scrollZoom": False,
            "doubleClick": False,
            "displaylogo": False,
        },
    )


def copy_button(text: str, label: str = "📄 复制脚本") -> None:
    """一个中文的「复制」按钮。

    为什么不用 st.code 自带的那个：它的提示语写死是英文 Copy to clipboard，
    改不了文案，只能藏掉。这里用 components 里的自包含按钮，
    优先走 clipboard API，被浏览器拦了就退回 textarea + execCommand。
    """
    import json as _json

    payload = _json.dumps(text)
    st.iframe(
        f"""
        <style>
          html,body{{margin:0;padding:0;background:transparent;overflow:hidden}}
          body{{padding:10px 0 12px 2px}}
          #cp{{
            font-family:'LXGW WenKai','Segoe UI Emoji','Apple Color Emoji',serif;
            font-size:15px;line-height:1.2;
            border:2px solid #3B3A45;border-radius:14px 16px 12px 15px;
            background:#FDFBF6;color:#3B3A45;padding:7px 20px;cursor:pointer;
            box-shadow:3px 3px 0 rgba(59,58,69,.14);
            transition:background .18s ease, transform .18s cubic-bezier(.22,.61,.36,1),
                       box-shadow .18s ease;
          }}
          #cp:hover{{
            background:#FFF8E8;
            transform:translateY(-2px);
            box-shadow:5px 5px 0 rgba(59,58,69,.18);
          }}
        </style>
        <button id="cp">{label}</button>
        <script>
          const T = {payload};
          const b = document.getElementById('cp');
          b.onclick = async () => {{
            let ok = false;
            try {{ await navigator.clipboard.writeText(T); ok = true; }} catch (e) {{}}
            if (!ok) {{
              const ta = document.createElement('textarea');
              ta.value = T;
              ta.style.cssText = 'position:fixed;top:0;left:0;opacity:0';
              document.body.appendChild(ta);
              ta.select();
              try {{ ok = document.execCommand('copy'); }} catch (e) {{}}
              ta.remove();
            }}
            b.textContent = ok ? '已复制 ✓' : '复制失败，请手动全选';
            setTimeout(() => {{ b.textContent = '{label}'; }}, 1600);
          }};
        </script>
        """,
        height=74,
    )


def current_user() -> str:
    """当前账本 / 用户。每个用户对应 data/profiles/<名字>.db，数据天然隔离。"""
    if SHARE_MODE:
        return GUEST
    return st.session_state.get("profile") or store.DEFAULT_PROFILE


def current_db():
    return store.profile_db(current_user())


@st.cache_data(show_spinner=False)
def load(user: str) -> pd.DataFrame:
    """读当前用户的库 + 补派生列。

    一次 rerun 里 6 个 tab 各调一次 load()，每次都新开 SQLite 连接、全表重读，
    纯属浪费（数据量一大就明显卡）。这里加缓存，代价是：导入 / 清空 / 切用户之后
    必须手动调用 load.clear()，否则界面会一直显示旧数据。
    """
    df = store.load(store.profile_db(user))
    if not df.empty:
        df["月份"] = df["ts"].dt.to_period("M").astype(str)
        df["日期"] = df["ts"].dt.date
    return df


def split(df: pd.DataFrame):
    """把宽表切成 消费支出 / 真实收入 两半。"""
    consume = df[(df["kind"] == Kind.NORMAL) & (df["direction"] == "支出")]
    income = df[(df["kind"] == Kind.NORMAL) & (df["direction"] == "收入")]
    return consume, income


def ingest(raw: bytes, filename: str, channel: str):
    adapter = ADAPTERS[channel]()
    txns, warns = adapter.parse(raw, source_file=filename)
    added, skipped = store.save(txns, current_db())
    return txns, added, skipped, warns


def render_uploader(widget_key: str, auto_key: str, select_prefix: str):
    """上传框 + 渠道识别，返回 [(文件名, 渠道, 原始字节)]。"""
    uploads = st.file_uploader(
        "把账单文件拖进来就好，一次选好几个也行",
        type=["csv", "xlsx", "xls"],
        accept_multiple_files=True,
        key=widget_key,
    )
    auto = st.checkbox("让我自己认是哪家的账单", value=True, key=auto_key)
    targets = []
    for f in uploads or []:
        raw = f.getvalue()
        # widget key 用「序号 + 内容哈希」：同名文件（比如重复导出的账单）直接用
        # 文件名当 key 会撞车，Streamlit 会直接报错
        file_key = f"{select_prefix}_{len(targets)}_{hashlib.md5(raw).hexdigest()[:10]}"
        guess = detect_channel(f.name) if auto else None
        if guess is None:
            guess = st.selectbox(f"「{f.name}」是哪家的呀？", CHANNELS, key=file_key)
        targets.append((f.name, guess, raw))
        st.caption(f"`{f.name}` → 我认成 **{guess}** 了")
    return targets


def run_import(targets) -> bool:
    """把上传的文件解析入库，返回是否至少成功一个。"""
    ok = False
    for name, ch, raw in targets:
        try:
            txns, added, skipped, warns = ingest(raw, name, ch)
            st.success(
                f"{name}：读出来 {len(txns)} 笔，新存了 {added} 笔，"
                f"还有 {skipped} 笔之前就存过、这次跳过了～"
            )
            for w in warns:
                st.warning(w)
            ok = True
        except Exception as exc:  # noqa: BLE001
            st.error(f"{name} 没能读出来：{exc}")
    if ok:
        load.clear()   # 新数据已落库，不清缓存其他页还是旧数据
    return ok


def page_welcome() -> None:
    """第一次用：没有数据就直接给上传框，不摆一排空页签。"""
    st.markdown("### 🧾 先放一份账单进来吧")
    st.caption("放一次就好，以后每次打开都能直接看～")

    with st.expander("第一次用？三种账单怎么导", expanded=True):
        # 原来三列并排，每列才两百多像素，「下载账单」都会被拆行；改成两列 + 一行提示
        # 三列太窄（「下载账单」会被拆行），改成两列 + 一行提示。
        # 每段之间用空行分隔，单换行在 markdown 里不生效。
        c1, c2 = st.columns(2)
        c1.markdown(
            "**微信**\n\n"
            "我 → 服务 → 钱包 → 账单 → 右上角「…」→ 下载账单\n\n"
            "接收方式选「微信」或「邮箱」，一天内到～"
        )
        c2.markdown(
            "**支付宝**\n\n"
            "① 我的 → 账单 → 右上角「…」→ 开具交易流水证明\n\n"
            "接收方式选「支付宝」或「邮箱」，几分钟就到\n\n"
            "② 或用「记账本」小程序：账单导出 → 申请 → 邮箱收"
        )
        st.caption("🎓 校园一卡通没有导出按钮，要在浏览器里跑一小段脚本，具体到「校园卡」页再看看～")

    targets = render_uploader("welcome_upload", "welcome_auto", "welcome")
    if st.button("看看我的账", type="primary", key="welcome_go"):
        if not targets:
            st.warning("还没选文件呢～ 先把账单拖到上面的框里，我就在这儿等着。")
        elif run_import(targets):
            st.session_state["flash"] = "导入好啦～下面是你的账单全貌"
            st.rerun()


def hint(text: str | None) -> None:
    """图表/表格下面的一行小注。没内容就不占位。"""
    if text:
        st.markdown(f'<div class="hint">{text}</div>', unsafe_allow_html=True)


def render_note(consume: pd.DataFrame, dropped: pd.DataFrame) -> None:
    """总览页的「小记」：把这段时间的账读成几句话。"""
    from billkit.insights import analyse

    note = analyse(consume, dropped)
    if note is None:
        return
    items = "".join(f"<li>{x}</li>" for x in note.findings)
    tip = f'<p class="note-tip">💡 {note.tip}</p>' if note.tip else ""
    st.markdown(
        '<div class="note-card">'
        '<div class="note-title">📝 这段时间的小记</div>'
        f'<p class="note-lead">{note.lead}</p>'
        f'<ul class="note-list">{items}</ul>'
        f"{tip}"
        '<div class="note-foot">就写到这儿啦 —— 说得对不对，你心里最有数～</div>'
        "</div>",
        unsafe_allow_html=True,
    )


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    """导出 CSV（带 BOM，Excel 不乱码）。

    商户名 / 商品名来自用户上传的账单，属于不可信输入；若以 = + - @ 开头，
    在 Excel 里会被当公式执行（CSV 注入）。这里统一加前缀单引号钝化。
    """
    out = df.copy()
    for col in out.columns:
        # 注意：pandas 3 的字符串列 dtype 是 str 而不是 object，
        # 用 dtype == object 判断会漏掉所有文本列，这里按「非数值列」处理
        if not is_numeric_dtype(out[col]):
            out[col] = out[col].map(
                lambda v: f"'{v}"
                if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r")
                else v
            )
    return out.to_csv(index=False).encode("utf-8-sig")


# ============================================================ 侧边栏

with st.sidebar:
    st.markdown("### 📔 不记账本")
    st.caption("微信 · 支付宝 · 校园卡")

    # ------------------------------------------------ 多用户（账本）
    if SHARE_MODE:
        st.caption("你的账本是空的，导一份自己的账单就能用～退出后自动清空")
    else:
        users = store.list_profiles()
        if st.session_state.get("profile") not in users:
            st.session_state["profile"] = users[0]

        st.markdown("**账本**")

        # Streamlit 没有「鼠标悬停」事件，删除叉只能靠 CSS 控显隐。
        # 只依赖官方公开的 .st-key-<key> 类名，不碰私有 data-testid，升级不易坏。
        css = ["<style>"]
        for _i in range(len(users)):
            css.append(
                # 「⋯」菜单按钮：去掉边框和底色，看起来就是个图标
                f".st-key-userrow_{_i} [data-testid='stPopover'] button {{"
                " min-height:1.9rem; min-width:2rem; padding:0 .25rem;"
                " border:none; background:transparent; box-shadow:none;"
                " font-size:14px; color:#6C6875; }"
            )
        css.append(
            '[data-testid="stSidebar"] [data-testid="stPopoverBody"] { min-width:230px; }'
        )
        css.append("</style>")
        st.markdown("".join(css), unsafe_allow_html=True)

        pending = st.session_state.get("pending_delete")

        for idx, u in enumerate(users):
            is_cur = (u == st.session_state["profile"])
            with st.container(key=f"userrow_{idx}"):
                if pending == u:
                    slot = st.empty()
                    with slot.container():
                        st.warning(f"删除「{u}」？里面的账单会一起没掉。", icon="⚠️")
                        c1, c2 = st.columns(2)
                        do_ok = c1.button("确认删除", type="primary", width="stretch",
                                          key=f"delok_{idx}")
                        do_no = c2.button("取消", width="stretch", key=f"delno_{idx}")
                    if do_no:
                        st.session_state.pop("pending_delete", None)
                        slot.empty()
                        st.rerun()
                    if do_ok:
                        try:
                            store.delete_profile(u)
                            st.session_state.pop("profile", None)
                            st.session_state.pop("pending_delete", None)
                            load.clear()
                            slot.empty()
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))
                else:
                    c_pick, c_more = st.columns([9, 1.4], vertical_alignment="center")
                    if c_pick.button(
                        f"{u}" + ("　✓" if is_cur else ""),
                        key=f"pick_{idx}", width="stretch",
                        type="primary" if is_cur else "secondary",
                        disabled=is_cur,
                        help="当前账本" if is_cur else f"切换到「{u}」",
                    ):
                        st.session_state["profile"] = u
                        load.clear()
                        st.rerun()

                    with c_more:
                        with st.popover("", icon=":material/more_horiz:",
                                        key=f"more_{idx}_{u}", width="content"):
                            st.caption("给这个账本换个名字")
                            new_name = st.text_input(
                                "新的名字", value=u, key=f"rn_in_{idx}_{u}",
                                label_visibility="collapsed",
                                placeholder="比如：我的生活账",
                            )
                            if st.button("改好了", type="primary", width="stretch",
                                         key=f"rn_ok_{idx}_{u}"):
                                try:
                                    final = store.rename_profile(u, new_name)
                                except Exception as exc:
                                    st.error(str(exc))
                                else:
                                    if st.session_state.get("profile") == u:
                                        st.session_state["profile"] = final
                                    load.clear()
                                    st.rerun()
                            st.divider()
                            if st.button("删掉这个账本", key=f"del_btn_{idx}_{u}",
                                         width="stretch"):
                                if len(users) <= 1:
                                    st.warning("至少得留一个账本呀")
                                else:
                                    st.session_state["pending_delete"] = u
                                    st.rerun()

        if len(users) > 1:
            with st.expander("⇅ 调整账本顺序"):
                st.caption("按住名字上下拖，松手就记住了～")
                # 组件在折叠状态下挂载时会被量成 0 高，展开后一片空白。
                # 这里按账本条数直接给 iframe 定高（每条约 44px），它就一定能显示出来。
                _sort_h = 8 + 44 * len(users)
                st.markdown(
                    "<style>[data-testid=\"stSidebar\"] "
                    f"iframe[title*='sortables']{{min-height:{_sort_h}px !important;}}"
                    "</style>",
                    unsafe_allow_html=True,
                )
                from streamlit_sortables import sort_items

                # key 只看"有哪些账本"，不看顺序：
                # ① 写死 key → 改名后仍显示旧列表（名字不同步、拖动像坏了）
                # ② key 跟顺序绑定 → 拖完一 rerun 就重挂载，轻则闪，重则顺序来回覆盖
                _order_key = "lo_" + hashlib.md5(
                    "|".join(sorted(users)).encode("utf-8")
                ).hexdigest()[:10]
                ordered = sort_items(
                    users,
                    direction="vertical",
                    key=_order_key,
                    custom_style="""
                      /* 之前条目整块消失，其实是组件状态被缓存卡死（换 key 就好了），
                         跟样式无关。现在放心加圆角。 */
                      .sortable-item{
                        font-family:'LXGW WenKai',serif;
                        font-size:15px;
                        background:#FDFBF6;
                        color:#3B3A45;
                        border-radius:11px 13px 10px 12px;
                        /* 不能用 border：实测一加 border 条目就不渲染了。
                           inset 阴影画在内部，不参与布局，效果一样。 */
                      }
                      /* 外层那两圈方框试过 .sortable-component / .sortable-container,
                         两者都被组件自己的样式盖掉，改不动。条目圆角已经是能做到的了。 */
                    """,
                )
                if ordered and list(ordered) != list(users):
                    # 落盘后 rerun 一次：侧边栏的账本列表要跟着变。
                    # key 不含顺序，所以这次 rerun 不会让组件重挂载，也就不会闪/死循环。
                    store.set_order(list(ordered))
                    st.rerun()

        with st.expander("＋ 新建账本"):
            new_name = st.text_input(
                "名字", placeholder="例如：张三", key="new_profile_name",
            )
            if st.button("创建", key="btn_create_profile"):
                try:
                    store.create_profile(new_name)
                    st.session_state["profile"] = store.safe_name(new_name)
                    load.clear()
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))
            st.caption("每个账本单独存一份，互相看不到～")

    # 记录数两种模式都要显示，所以放在 if/else 之外
    total = store.count(current_db())
    st.metric(f"「{current_user()}」已经记了", f"{total} 笔")
    st.divider()
    st.markdown("**它认得这三家的账单**")
    _icons = {
        "微信": '<img src="https://cdn.simpleicons.org/wechat/07C160" onerror="this.remove()">',
        "支付宝": '<img src="https://cdn.simpleicons.org/alipay/1677FF" onerror="this.remove()">',
        "校园卡": '<span class="mark">💳</span>',
    }
    for ch in CHANNELS:
        st.markdown(
            f'<div class="side-ch">{_icons.get(ch, "")}<span>{ch}</span></div>',
            unsafe_allow_html=True,
        )
    st.divider()
    if st.checkbox("清空这个账本的所有记录", key="chk_clear"):
        if st.button("确认清空", type="secondary", key="btn_clear"):
            store.clear(current_db())
            load.clear()   # 缓存不失效的话，清空后各页仍会显示旧数据
            st.success("清好啦～")
            st.rerun()
    try:
        db_label = current_db().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:  # 自定义路径时可能不在项目目录下
        db_label = str(current_db())
    if not SHARE_MODE:   # 访客不用知道文件在哪
        st.caption(f"数据库：`{db_label}`")


st.title("不记账本")
st.caption("微信、支付宝、校园卡，都记在这一本里～")

df_home = load(current_user())

flash = st.session_state.pop("flash", None)
if flash:
    # 包一层带 key 的容器，配 CSS 让它几秒后自动淡出收起来。
    # 只 pop 状态不够：Streamlit 不会主动移除已渲染的元素，没人 rerun 它就一直在那儿。
    with st.container(key="flash_msg"):
        st.success(flash)

# 没有数据的人一进来该看到「怎么开始」，而不是六个空页签；
# 有数据的人直接落在总览，导入退到后面的页签里
if df_home.empty:
    page_welcome()
    st.stop()

tab_overview, tab_trend, tab_category, tab_detail, tab_import, tab_campus = st.tabs(
    ["📊 总览", "📈 趋势", "🏷️ 分类", "📋 明细", "📥 导入", "🎓 校园卡"]
)

# ============================================================ 导入

with tab_import:
    st.subheader("📥 再放一份账单")
    st.markdown(
        "微信、支付宝导出的账单，还有校园一卡通导出的表格，都能放进来～ "
        "同一份重复放也不会翻倍，存过的我会自己跳过。"
    )

    targets = render_uploader("tab_upload", "tab_auto", "tab")
    # 不再用 disabled：禁用状态下点了完全没反应，会让人以为卡住了。
    # 保持可点，没选文件就明确说一句。
    if st.button("读进来", type="primary", key="tab_go"):
        if not targets:
            st.warning("还没选文件呢～ 先把账单拖到上面的框里，我就在这儿等着。")
        else:
            run_import(targets)

    st.divider()
    st.markdown("#### 🧾 这些数字是怎么算出来的")
    st.caption("不用记这些，只是让你知道账对得上～")
    with st.expander("好奇的话，点开看看我替你处理了什么", expanded=False):
        st.markdown(
            """
- **给校园卡充的钱，不会算两次** —— 充 100、刷卡花 44，真正花掉的只有 44，
  所以「充值」那笔我会先放一边。
- **退了款的那笔，不记账** —— 东西退回去了，钱也回来了，就当没发生～
- **钱在自己账户里搬来搬去，不算花销** —— 零钱提现、余额宝转进转出，都是左手换右手。
- **还花呗、还信用卡，不算花销** —— 那是在还旧账，不是新花的钱。
- **转给朋友的钱，我先标「待确认」** —— 不敢替你决定这算不算花掉，留给你自己看。
- **同一份账单放两次，也不会翻倍**。
            """
        )

    df_now = load(current_user())
    unclear = df_now[df_now["kind"] == Kind.UNCLEAR] if not df_now.empty else df_now
    if len(unclear):
        st.info(
            f"有 {len(unclear)} 笔转给朋友的钱，我拿不准算不算花销～"
            "你先去「明细」页看一眼，再告诉我。"
        )

# ============================================================ 总览

with tab_overview:
    df = load(current_user())
    if df.empty:
        st.info("🫙 这里还空着～去「导入」放一份账单进来就好")
    else:
        consume, income = split(df)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💸 这个月花了", money(consume["amount"].sum()))
        income_sum = income["amount"].sum()
        consume_sum = consume["amount"].sum()
        c2.metric("🧾 收到的", money(income_sum))
        if income_sum > 0:
            c3.metric(
                "🪙 还剩", money(income_sum - consume_sum),
                help="收到的减去真正花掉的（充值、退款这些不算）",
            )
        else:
            # 只导了支出、没有收入时，「还剩」会等于负的支出总额，是个没意义的数。
            # 这种情况下换成「平均每天花」，同样是这一格的位置，但说得通。
            _days = max(1, (df["ts"].max() - df["ts"].min()).days + 1)
            c3.metric(
                "📅 平均每天花", money(consume_sum / _days),
                help="这份账单里没有收入记录，所以不显示「还剩」；这里是真实消费摊到每天的金额",
            )
        # 只看「支出」侧的非消费记录，这样和左边「真实消费支出」口径一致。
        # 原写法右侧表格用 kind != NORMAL（含收入侧）、标题却用支出侧，两处金额对不上。
        dropped = df[(df["kind"] != Kind.NORMAL) & (df["direction"] == "支出")]
        # 「待确认」是性质未定，不是重复记账，单独从「虚增」里摘出来
        double_count = dropped[dropped["kind"] != Kind.UNCLEAR]
        c4.metric(
            "🚫 没算进花销",
            money(dropped["amount"].sum()),
            help="充值、退款、还钱，还有你还没定的转账 —— 这些先都不算花掉～",
        )

        render_note(consume, dropped)

        st.divider()
        left, right = st.columns([3, 2])

        with left:
            st.markdown("##### 💳 钱是从哪儿出去的")
            by_channel = (
                consume.groupby("channel", as_index=False)["amount"].sum()
                .sort_values("amount", ascending=True)
            )
            fig = px.bar(
                by_channel, x="amount", y="channel", orientation="h",
                text=by_channel["amount"].map(lambda v: f"¥{v:,.0f}"),
                height=300,
            )
            # 金额越大颜色越深（浅苔绿 → 水蓝 → 深蓝），一眼看出谁占大头
            fig.update_traces(
                textposition="inside", insidetextanchor="end",
                hovertemplate="渠道：%{y}<br>金额：¥%{x:,.2f}<extra></extra>",
                marker=dict(
                    color=by_channel["amount"],
                    colorscale=[[0, "#C3D1C0"], [0.55, "#8AA6BF"], [1, "#5C7C9B"]],
                    showscale=False, line_width=0,
                ),
            )
            style_bar(fig, horizontal=True)
            fig.update_layout(barcornerradius=10)
            chart(fig)
            hint(insights.hint_channel(consume))

        with right:
            st.markdown("##### 🧮 这些没算进花销")
            if dropped.empty:
                st.caption("这次没有要剔出去的记录，很干净～")
            else:
                stat = dropped.groupby("kind", as_index=False).agg(
                    笔数=("uid", "count"), 金额=("amount", "sum")
                )
                stat["kind"] = stat["kind"].replace(KIND_CN)
                # 和左边的图表卡片保持同一套外观，两个卡片顶边才会齐
                render_ledger(
                    stat.rename(columns={"kind": "性质"})
                )
                hint(insights.hint_dropped(dropped))
                st.caption(
                    "要是把这些也算进去，总额会变成 "
                    f"**{money(consume['amount'].sum() + double_count['amount'].sum())}**，"
                    f"平白多出 {money(double_count['amount'].sum())}。"
                )

        st.divider()
        st.markdown("##### 📅 这份账单的来路")
        # 原来分三列，列太窄会把「时间」折成两行、看着像数据丢了；改成一行自然排布
        st.markdown(
            '<div class="meta-line">'
            f"时间：<b>{df['ts'].min():%Y-%m-%d} ~ {df['ts'].max():%Y-%m-%d}</b>"
            f"　·　记录：<b>{len(df)} 笔</b>（消费 <b>{len(consume)} 笔</b>）"
            f"　·　渠道：<b>{'、'.join(sorted(df['channel'].unique()))}</b>"
            "</div>",
            unsafe_allow_html=True,
        )

# ============================================================ 趋势

with tab_trend:
    df = load(current_user())
    if df.empty:
        st.info("这里还空着～先去「导入」放一份账单吧")
    else:
        consume, _ = split(df)
        if consume.empty:
            st.info("这段时间还没有花钱记录～")
        else:
            # 不提供粒度切换：按天的细节交给下面的日历，这里固定按周看节奏。
            # 原来那个「每一格代表多久」的开关只管柱状图，却和下面的日历对不上，容易误解。
            st.markdown("##### 📈 一周一周地看")

            series = (
                consume.set_index("ts")["amount"].resample("W-MON").sum().reset_index()
            )
            series.columns = ["时间", "支出"]

            fig = px.bar(series, x="时间", y="支出", height=320)
            # 按花费分三档（不是连续渐变）：少=绿、中=黄、多=红，都取莫奈色
            _v = series["支出"]
            _lo, _hi = _v.quantile(0.34), _v.quantile(0.67)
            def _tier(x):
                if x <= _lo:
                    return "#9CB8A4"      # 苔绿
                if x <= _hi:
                    return "#E6D2A2"      # 暖黄
                return "#C97C6A"          # 陶土红
            fig.update_traces(
                marker=dict(color=[_tier(v) for v in _v], line_width=0),
                hovertemplate="时间：%{x|%m月%d日}<br>支出：¥%{y:,.2f}<extra></extra>",
            )
            fig.update_layout(yaxis_title="", barcornerradius=8)
            fig.update_xaxes(tickformat="%m/%d", hoverformat="%m月%d日")
            chart(fig)
            hint(insights.hint_weekly(series))

            # 日历热力图：一个月摊成 5×7 的格子，深浅代表当天花了多少。
            # 比「累计支出」有用得多 —— 累计线永远是往上的，看一整个月没有信息量；
            # 格子能一眼看出哪天花得凶、哪几天完全没花。
            st.markdown("##### 🗓️ 这个月的花钱日历")
            diag = consume.assign(日=consume["ts"].dt.date).groupby("日")["amount"].sum()
            if not diag.empty:
                first = diag.index.min() - timedelta(days=diag.index.min().weekday())
                last = diag.index.max()
                ndays = (last - first).days + 1
                weeks = (ndays + 6) // 7
                z = [[None] * 7 for _ in range(weeks)]
                tips = [[""] * 7 for _ in range(weeks)]
                for i in range(ndays):
                    d = first + timedelta(days=i)
                    v = float(diag.get(d, 0.0))
                    w, wd = divmod(i, 7)
                    z[w][wd] = v
                    tips[w][wd] = (f"{d.month}月{d.day}日 · ¥{v:,.2f}" if v
                                   else f"{d.month}月{d.day}日 · 没花钱")
                heat = go.Figure(go.Heatmap(
                    z=z, x=["一", "二", "三", "四", "五", "六", "日"],
                    y=[f"第 {i + 1} 周" for i in range(weeks)],
                    text=tips, hoverinfo="text", showscale=False,
                    xgap=7, ygap=7,
                    colorscale=[[0, "#EFECE2"], [0.25, "#DCE5DE"],
                                [0.6, "#B4C8BC"], [1, "#8AA6BF"]],
                    zmin=0, zmax=max(1.0, max((v or 0) for row in z for v in row)),
                ))
                heat.update_layout(height=46 * weeks + 60, yaxis_autorange="reversed")
                heat.update_yaxes(showgrid=False, tickfont=dict(size=12))
                heat.update_xaxes(showgrid=False, tickfont=dict(size=12), side="top")
                chart(heat)
                hint(insights.hint_calendar(diag))


            st.markdown("##### 🔁 每个月都会悄悄扣走的")
            st.caption("同一个地方、金额差不多、每个月都来一次。")
            sub = consume.copy()
            # 商户名为空时会把互不相关的消费聚成一组，必须先剔掉
            sub = sub[sub["counterparty"].fillna("").astype(str).str.strip() != ""]
            sub["月"] = sub["ts"].dt.to_period("M").astype(str)
            sub["金额档"] = sub["amount"].round(0)
            recurring = (
                sub.groupby(["counterparty", "金额档"], as_index=False)
                .agg(月份数=("月", "nunique"), 笔数=("uid", "count"))
            )
            # 订阅的特征是「每月一笔」：笔数不能多于月份数，
            # 否则食堂 15 元/次这种高频小额消费也会被误判成月度订阅
            recurring = recurring[
                (recurring["月份数"] >= 2) & (recurring["笔数"] <= recurring["月份数"])
            ]
            if recurring.empty:
                st.caption("数据还不太够～攒满两个月，我就能帮你认出每月固定支出了。")
            else:
                rec_view = recurring.rename(
                    columns={"counterparty": "商户", "金额档": "单笔约"}
                )
                st.dataframe(rec_view, hide_index=True, width="stretch")
                hint(insights.hint_recurring(rec_view))

# ============================================================ 分类

with tab_category:
    df = load(current_user())
    if df.empty:
        st.info("这里还空着～先去「导入」放一份账单吧")
    else:
        consume, _ = split(df)
        if consume.empty:
            st.info("这段时间还没有花钱记录～")
        else:
            left, right = st.columns(2)
            cat = (
                consume.groupby("category", as_index=False)["amount"].sum()
                .sort_values("amount", ascending=False)
            )
            with left:
                st.markdown("##### 🍽️ 钱都花到哪儿了")
                fig = px.pie(
                    cat, names="category", values="amount", hole=0.45,
                    height=340,
                )
                fig.update_traces(
                    hovertemplate="分类：%{label}<br>金额：¥%{value:,.2f}<br>占比：%{percent}<extra></extra>",
                )
                style_pie(fig, hole=0.55)
                fig.update_traces(textposition="inside", textinfo="percent")
                fig.update_layout(showlegend=True)
                chart(fig)
                hint(insights.hint_category(cat))

            with right:
                st.markdown("##### 📊 每一类各花了多少")
                # 颜色和左边的环形图一一对应：同一顺序取同一个色
                cat_color = {
                    row.category: PALETTE[i % len(PALETTE)]
                    for i, row in enumerate(cat.itertuples())
                }
                cat_sorted = cat.sort_values("amount")
                fig = px.bar(
                    cat_sorted, x="amount", y="category", orientation="h",
                    height=340,
                )
                fig.update_traces(
                    marker_color=[cat_color[c] for c in cat_sorted["category"]],
                    marker_line_width=0,
                    hovertemplate="分类：%{y}<br>金额：¥%{x:,.2f}<extra></extra>",
                )
                style_bar(fig, horizontal=True)
                fig.update_layout(barcornerradius=10)
                chart(fig)
                hint(insights.hint_category_small(cat))

            st.divider()
            st.markdown("##### 🏆 最舍得花的地方")
            top = (
                consume.groupby("counterparty", as_index=False)
                .agg(笔数=("uid", "count"), 金额=("amount", "sum"))
                .sort_values("金额", ascending=False)
                .head(10)
            )
            top_view = top.rename(columns={"counterparty": "商户"})
            render_ledger(top_view)
            hint(insights.hint_top(top_view, float(consume["amount"].sum())))

            st.markdown("##### 🤔 这几个我还不太认识")
            unknown = consume[consume["category"] == "未分类"]
            if unknown.empty:
                st.success("🎉 每一笔都认出来了，真好～")
            else:
                st.caption(
                    f"这 **{len(unknown)} 笔** 的商户我之前没见过，就先没归类～"
                    "你挑一个告诉我它算哪类，以后同名的我自动就记住啦。"
                )
                unk_view = (
                    unknown.sort_values("ts", ascending=False)
                    [["ts", "channel", "counterparty", "amount"]]
                    .rename(columns=COL_CN).head(50)
                )
                unk_view["时间"] = unk_view["时间"].dt.strftime("%m-%d %H:%M")
                render_ledger(unk_view)
                hint(insights.hint_unclear(unknown, consume))

                names = sorted({n for n in unknown["counterparty"].dropna() if str(n).strip()})
                if names:
                    pickable = [c for c in CATEGORY_ORDER
                                if c not in ("未分类", "转账", "退款", "内部转账")]
                    # 底部对齐：按钮没有标签，不对齐会浮在两个下拉框上面
                    c1, c2, c3 = st.columns([2, 2, 1], vertical_alignment="bottom")
                    pick = c1.selectbox("这是哪家", names, key="unk_shop")
                    target = c2.selectbox("我觉得算", pickable, key="unk_cat")
                    if c3.button("记下来", key="unk_save", width="stretch"):
                        try:
                            add_rule(target, pick)
                            load_rules.cache_clear()
                            n_fix = store.update_category(pick, target, current_db())
                            load.clear()
                            st.success(
                                f"记好啦～「{pick}」以后都算「{target}」，"
                                f"顺手把现有的 {n_fix} 笔也一起改过来了。"
                            )
                            st.rerun()
                        except Exception as exc:  # noqa: BLE001
                            st.error(f"没能记下来：{exc}")

# ============================================================ 明细

with tab_detail:
    df = load(current_user())
    if df.empty:
        st.info("这里还空着～先去「导入」放一份账单吧")
    else:
        f1, f2, f3 = st.columns([2, 2, 3])
        # 用可点标签代替下拉：渠道只有 3 个、分类 7 个，一屏放得下。
        # 下拉框（react-aria 的 combobox）点第二次不收起，是组件内部行为，CSS 改不动；
        # 换成 pills 之后点一下就是选/取消，没有"展开-收起"这回事。
        ch = f1.pills("渠道", sorted(df["channel"].unique()),
                      selection_mode="multi", key="pick_ch", width="stretch", wrap=True)
        cat = f2.pills("分类", sorted(df["category"].unique()),
                       selection_mode="multi", key="pick_cat", width="stretch", wrap=True)
        f3a, f3b = f3.columns([0.68, 0.32], vertical_alignment="bottom")
        kw = f3a.text_input("想找哪一笔？店名或东西都行", key="kw_box")
        f3b.button("搜索", key="kw_go", width="content")

        first_day, last_day = df["ts"].min().date(), df["ts"].max().date()
        d1, d2 = st.columns(2)
        start = d1.date_input(
            "起始日期", value=first_day, min_value=first_day, max_value=last_day
        )
        end = d2.date_input(
            "结束日期", value=last_day, min_value=first_day, max_value=last_day
        )
        if start > end:  # 否则静默返回空表，用户会以为数据丢了
            st.warning("起始日期比结束日期还晚，我先帮你换过来了～")
            start, end = end, start

        view = df.copy()
        if ch:
            view = view[view["channel"].isin(ch)]
        if cat:
            view = view[view["category"].isin(cat)]
        if kw:
            # 关键词是普通输入，按字面量匹配：用户输入 "(" 之类正则元字符
            # 时，默认 regex=True 会直接抛 re.error 崩掉整个页面
            pattern = re.escape(kw.strip())
            mask = (
                view["counterparty"].fillna("").str.contains(pattern, case=False, na=False)
                | view["product"].fillna("").str.contains(pattern, case=False, na=False)
            )
            view = view[mask]
        view = view[(view["ts"].dt.date >= start) & (view["ts"].dt.date <= end)]

        # 最新的排在最前面（用户打开就想看最近花了什么）
        view = view.sort_values("ts", ascending=False)

        # 合计只算「真实消费」，否则内部转账 / 退款会被算进支出，和总览口径冲突
        real = view[(view["kind"] == Kind.NORMAL) & (view["direction"] == "支出")]
        excluded = int(((view["kind"] != Kind.NORMAL) & (view["direction"] == "支出")).sum())

        total_rows = len(view)
        show = view[["ts", "channel", "direction", "amount", "counterparty", "product",
                     "category", "kind", "status", "note"]].rename(columns=COL_CN)
        show["性质"] = show["性质"].replace(KIND_CN)
        # 明细表只要到分钟，年份同一次导出里都一样，去掉省地方
        show["时间"] = show["时间"].dt.strftime("%m-%d %H:%M")

        # 导出放最上面，不用翻到页底才找得到
        head_l, head_r = st.columns([3, 1])
        head_l.caption(
            f"一共 {total_rows} 笔 ｜ 真花掉 {money(real['amount'].sum())}"
            f" ｜ 另有 {excluded} 笔没算进来"
        )
        head_r.download_button(
            "存成表格",
            data=to_csv_bytes(show),
            file_name="账单明细.csv",
            mime="text/csv",
            width="stretch",
        )

        # -------------------------------------------------- 手动补记
        with st.expander("＋ 补记一笔"):
            st.caption("现金、转账、临时垫付这些导不进账单的，可以在这儿手动记～")
            a1, a2, a3 = st.columns([1.1, 1, 1])
            add_date = a1.date_input(
                "日期", value=df["ts"].max().date(),
                min_value=df["ts"].min().date(), key="add_date",
            )
            add_time = a2.time_input("时间", value=dtime(12, 0), key="add_time")
            add_amt = a3.number_input(
                "金额", min_value=0.01, value=20.0, step=1.0,
                format="%.2f", key="add_amt",
            )
            b1, b2, b3 = st.columns([1, 1.3, 1.5])
            add_dir = b1.selectbox("收支", ["支出", "收入"], key="add_dir")
            add_ch = b2.selectbox("渠道", list(CHANNELS) + ["现金"], key="add_ch")
            add_cat = b3.selectbox(
                "分类", sorted(load_rules().keys()) + ["未分类"], key="add_cat",
            )
            add_who = st.text_input(
                "对方 / 商户", key="add_who", placeholder="比如：楼下水果店",
            )
            add_note = st.text_input("备注（可不填）", key="add_note")

            if st.button("记下来", type="primary", key="add_save"):
                tx = Transaction(
                    channel=add_ch,
                    time=datetime.combine(add_date, add_time),
                    amount=float(add_amt),
                    direction=add_dir,
                    counterparty=add_who.strip(),
                    product=add_note.strip(),
                    note=add_note.strip(),
                    category=add_cat,
                    kind=Kind.NORMAL,
                    source_file="手动添加",
                )
                added, skipped = store.save([tx], current_db())
                if added:
                    load.clear()
                    st.toast("记上了～")
                    st.rerun()
                else:
                    st.warning(
                        "这条好像已经记过了（同一时间、同样金额、同一个对方）～"
                        "要是确实有两笔，把时间改一分钟再存。"
                    )

        # -------------------------------------------------- 改一笔 / 删一笔
        # 表格是自绘的手帐表，没法在格子里放控件，所以单独开一块「编辑区」。
        with st.expander("🔧 有记录记错了？"):
            if view.empty:
                st.caption("现在这个筛选下没有能改的记录～")
            else:
                pool = view.sort_values("ts", ascending=False).copy()

                def _label(uid: str) -> str:
                    r = pool[pool["uid"] == uid].iloc[0]
                    who = str(r["counterparty"] or "").strip() or "（没写店名）"
                    return f"{r['ts'].month}月{r['ts'].day}日 · {who} · ¥{r['amount']:,.2f}"

                c_a, c_b = st.columns([3, 2])
                picked = c_a.selectbox(
                    "哪一笔", pool["uid"].tolist(), format_func=_label, key="edit_pick",
                )
                row = pool[pool["uid"] == picked].iloc[0]
                cur_cat = str(row["category"] or "未分类")
                options = sorted(set(list(load_rules().keys()) + ["未分类", cur_cat]))
                new_cat = c_b.selectbox(
                    "改成哪一类", options,
                    index=options.index(cur_cat) if cur_cat in options else 0,
                    key="edit_cat",
                )
                who_now = str(row["counterparty"] or "").strip()
                r1, r2 = st.columns(2)
                remember = r1.checkbox(
                    "以后导入也自动归到这一类", key="edit_remember",
                    help="把这个商户写进词库，下次导入就不用再改",
                )
                bulk = r2.checkbox(
                    "这个商户的历史记录一起改", key="edit_bulk",
                    help="把这个账本里同一个商户的其它记录也改成这一类",
                    disabled=not who_now,
                )

                pending_txn = st.session_state.get("pending_del_txn")
                c1, c2, _ = st.columns([1.2, 1.2, 2])
                if pending_txn == picked:
                    st.warning("删掉之后就找不回来了，确定吗？", icon="⚠️")
                    d1, d2 = st.columns(2)
                    if d1.button("确认删掉", type="primary", width="stretch", key="del_txn_ok"):
                        store.delete_txn(picked, current_db())
                        st.session_state.pop("pending_del_txn", None)
                        load.clear()
                        st.toast("删掉了～")
                        st.rerun()
                    if d2.button("算了", width="stretch", key="del_txn_no"):
                        st.session_state.pop("pending_del_txn", None)
                        st.rerun()
                else:
                    if c1.button("存下新分类", type="primary", width="stretch", key="edit_save"):
                        store.set_category(picked, new_cat, current_db())
                        note = ""
                        if bulk and who_now:
                            n = store.set_category_by_merchant(
                                who_now, new_cat, direction=row["direction"],
                                db_path=current_db(),
                            )
                            note = f"连同其它 {max(0, n - 1)} 笔一起改好了"
                        if remember and who_now:
                            add_rule(new_cat, who_now)   # 顺序是 (分类, 关键词)
                            load_rules.cache_clear()     # 不清缓存新规则要重启才生效
                            store.update_category(who_now, new_cat, current_db())
                            note = (note + "，" if note else "") + "也记住这个商户了"
                        load.clear()
                        st.toast(note or "改好了～")
                        st.rerun()
                    if c2.button("删掉这笔", width="stretch", key="del_txn"):
                        st.session_state["pending_del_txn"] = picked
                        st.rerun()

        if total_rows == 0:
            st.info("这个条件下什么都没找到～要不要把日期放宽一点，或者清掉筛选再看看？")
        else:
            # 分页：一页多放一些，表格整体展开、由页面滚动，不再在表格里挤着滚
            c_size, c_prev, c_next, c_info = st.columns([1.1, 1, 1, 3],
                                                       vertical_alignment="bottom")
            size = c_size.selectbox("每页显示", [25, 50, 100], index=0, key="detail_page_size")
            pages = max(1, (total_rows - 1) // size + 1)
            # 页码不再用数字输入框（它的 +/- 按钮 focus 后高亮不消失，很别扭），
            # 改成明确的「上一页 / 下一页」，当前页用文字显示
            page = int(st.session_state.get("detail_page", 1))
            page = min(max(1, page), pages)
            if pages > 1:
                if c_prev.button("上一页", key="pg_prev", disabled=page <= 1, width="stretch"):
                    st.session_state["detail_page"] = page - 1
                    st.rerun()
                if c_next.button("下一页", key="pg_next", disabled=page >= pages, width="stretch"):
                    st.session_state["detail_page"] = page + 1
                    st.rerun()
            start_i = (page - 1) * size
            page_df = show.iloc[start_i:start_i + size]
            c_info.caption(f"第 {page}/{pages} 页 · 第 {start_i + 1}–{start_i + len(page_df)} 行，共 {total_rows} 行")

            style = st.radio(
                "表格样式", ["手帐表格", "原生表格"],
                horizontal=True, index=0, key="table_style",
                help="手帐表格字大、有行距；原生表格能点列头排序",
            )
            # 手帐表格不需要「收支/状态/备注」这几列（多数为空），先精简掉
            slim = page_df.drop(columns=[c for c in ("收支", "状态", "备注") if c in page_df.columns])
            if style == "手帐表格":
                render_ledger(slim)
            else:
                st.dataframe(
                    page_df,
                    hide_index=True,
                    width="stretch",
                    height=len(page_df) * 35 + 40,
                    column_config={
                        "时间": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
                        "金额": st.column_config.NumberColumn(format="%.2f"),
                    },
                )

# ============================================================ 校园卡

with tab_campus:
    st.subheader("🎓 校园一卡通")
    st.markdown("一卡通这边没有导出按钮，也下不了流水。不过别急～"
                "我给你准备了一小段脚本，在网页里跑一下就会自动存成表格，"
                "**一个月跑一次就够了**。")

    left, right = st.columns([1, 1])

    with left:
        st.markdown("**第 1 步 · 打开并登录一卡通账单页**")
        st.link_button("打开一卡通账单页", CAMPUS_LOGIN_URL, width="stretch")
        st.caption(CAMPUS_LOGIN_URL)

        st.markdown("**第 2 步 · 在页面里跑抓取脚本**")
        st.markdown(
            """
1. 在这一页按 **F12**，右边（或下面）会冒出一个开发者面板
2. 把脚本粘进 **Console（控制台）** 里，按回车

   - 如果提示不让粘贴：**手打** `allow pasting` 回车解锁，再粘

3. 跑到一半它可能提示「需要你配合一步」——照做：点顶部「钱包」，再点回「全部」
4. 跑完会自动下载一个表格文件，把它拖到右边框里
            """
        )
        with st.expander("📄 点开复制脚本", expanded=False):
            script_path = PROJECT_ROOT / "tools" / "campus_grab.js"
            script_text = (
                script_path.read_text(encoding="utf-8")
                if script_path.exists()
                else "// 找不到 tools/campus_grab.js"
            )
            copy_button(script_text)
            st.code(script_text, language="javascript")
            st.caption("点上面的按钮就能复制，也可以全选后按 Ctrl+C～")
            st.download_button(
                "下载这个脚本",
                data=script_text.encode("utf-8"),
                file_name="campus_grab.js",
                mime="text/javascript",
            )
        st.info("想多导几个月？把页面上的「本月」换成更早的月份，再跑一遍就好～")

    with right:
        st.markdown("**第 3 步 · 把下载的 CSV 拖进来**")
        probe = st.file_uploader(
            "上传脚本导出的 CSV",
            type=["csv", "xlsx", "xls"],
            key="campus_probe",
        )
        if probe is not None:
            try:
                txns, warns = CampusAdapter().parse(probe.getvalue(), probe.name)
                from collections import Counter as _Counter

                stat = _Counter(t.kind for t in txns)
                cat = _Counter(t.category for t in txns)
                c1, c2, c3 = st.columns(3)
                c1.metric("读出多少笔", len(txns))
                c2.metric("其中消费", stat.get(Kind.NORMAL, 0))
                c3.metric("充值（不算花销）", stat.get(Kind.TRANSFER, 0))
                st.write("**都分到哪儿了**：", dict(cat))
                if warns:
                    for w in warns[:3]:
                        st.warning(w)
                if txns:
                    st.dataframe(
                        pd.DataFrame([{
                            "时间": t.time, "类型": t.direction, "商户": t.counterparty,
                            "金额": t.amount, "分类": t.category, "性质": t.kind,
                        } for t in txns]).head(20),
                        hide_index=True, width="stretch", height=280,
                    )
                    if st.button("导入到数据库", type="primary", key="campus_import"):
                        added, skipped = store.save(txns, current_db())
                        st.success(f"新增 {added} 笔，已存在跳过 {skipped} 笔")
                with st.expander("高级：看看字段有没有认错", expanded=False):
                    report = CampusAdapter.columns_report(probe.getvalue())
                    st.write("实际列名：", report["实际列名"])
                    st.json({k: v for k, v in report["字段映射"].items() if v})
            except Exception as exc:  # noqa: BLE001
                st.error(f"读不了：{exc}")


# ============================================================ 页脚

st.markdown('<div class="page-foot">账记到这里</div>', unsafe_allow_html=True)
