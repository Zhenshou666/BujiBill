# -*- coding: utf-8 -*-
"""手帐风格的明细表格（纯 HTML 渲染）。

为什么不用 st.dataframe：
    它是 canvas 画的，字号、行高、分隔线、悬停效果全都不受 CSS 控制，
    和整站的纸质调子对不上，而且字最小、最难读。

代价：
    失去列排序、列宽拖动、单元格选中。筛选/分页仍在 Python 侧做，
    对"看账单"这个场景来说够用。
"""
from __future__ import annotations

import html as _html

import pandas as pd
import streamlit as st

# 分类小标签的底色：同一套莫奈色，压低透明度当色纸
# 渠道图标：用 Simple Icons 的官方品牌 SVG（CDN），加载失败就自动隐藏，不影响排版
_CH_ICON = {
    "微信": "https://cdn.simpleicons.org/wechat/07C160",
    "支付宝": "https://cdn.simpleicons.org/alipay/1677FF",
}

_CHIP_BG = {
    "餐饮": "rgba(156,184,164,.30)",
    "日用": "rgba(214,166,162,.30)",
    "学习": "rgba(138,166,191,.30)",
    "交通": "rgba(230,210,162,.42)",
    "娱乐": "rgba(167,155,192,.28)",
    "医疗": "rgba(185,203,178,.34)",
    "通讯": "rgba(203,184,198,.30)",
    "住宿": "rgba(156,184,164,.22)",
    "数码": "rgba(138,166,191,.22)",
    "未分类": "rgba(120,118,130,.16)",
}


def _cell(col: str, val, extra: str = "") -> str:
    cls = f"c-{col}"
    if val is None or (isinstance(val, float) and pd.isna(val)) or val == "":
        return f'<td class="{cls}"></td>'
    text = str(val)
    if col == "金额":
        return f'<td class="{cls} num">{float(val):,.2f}</td>'
    if col == "时间":
        return f'<td class="{cls} time">{_html.escape(text)}</td>'
    if col == "分类":
        bg = _CHIP_BG.get(text, "rgba(120,118,130,.16)")
        return f'<td class="{cls}"><span class="chip" style="background:{bg}">{_html.escape(text)}</span></td>'
    if col == "性质":
        warn = "" if text == "消费" else " chip-warn"
        return f'<td class="{cls}"><span class="chip{warn}">{_html.escape(text)}</span></td>'
    if col == "渠道":
        src = _CH_ICON.get(text)
        if src:
            return (f'<td class="{cls}"><span class="ch"><img src="{src}" alt="" '
                    f'onerror="this.remove()">{_html.escape(text)}</span></td>')
        # 校园卡没有公开品牌标，用银行卡 emoji 代替（尺寸和另外两个图标对齐）
        return (f'<td class="{cls}"><span class="ch"><span class="ch-mark">💳</span>'
                f'{_html.escape(text)}</span></td>')
    if col == "对方":
        sub = f'<span class="sub">{_html.escape(extra)}</span>' if extra else ""
        return f'<td class="{cls} who"><span class="main">{_html.escape(text)}</span>{sub}</td>'
    return f'<td class="{cls}">{_html.escape(text)}</td>'


def render_ledger(df: pd.DataFrame) -> None:
    """把一张已经改好中文列名的表渲染成手帐样式。

    「商品」不单独占一列 —— 很多行是空的，白占宽度；
    合并到「对方」下面当副标题，既省地方又更像账本的行文。
    """
    if df.empty:
        st.info("这个条件下没有记录。")
        return
    products = df["商品"].fillna("").astype(str) if "商品" in df.columns else None
    if products is not None:
        df = df.drop(columns=["商品"])
    head = "".join(f'<th class="c-{c}">{_html.escape(str(c))}</th>' for c in df.columns)
    # 注意：<colgroup>/<col> 会被 Streamlit 的 HTML 清洗器剥掉，
    # 所以列宽改用 CSS 的 nth-child 控制（见 ui_theme.py 的 table.ledger 段）
    rows = []
    for i, record in enumerate(df.itertuples(index=False)):
        sub = products.iloc[i] if products is not None else ""
        cells = "".join(_cell(c, v, sub) for c, v in zip(df.columns, record))
        rows.append(f"<tr>{cells}</tr>")

    st.markdown(
        f"""
        <div class="ledger-wrap">
          <table class="ledger">
            <thead><tr>{head}</tr></thead>
            <tbody>{''.join(rows)}</tbody>
          </table>
        </div>
        """,
        unsafe_allow_html=True,
    )
