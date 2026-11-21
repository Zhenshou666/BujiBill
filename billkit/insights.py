# -*- coding: utf-8 -*-
"""把账单读成几句话。

这里没有联网、没有大模型：全部是本地规则 + 真实数字。
账单是很私密的东西，不该为了"看起来像 AI"就往外发；
规则版也不会连不上、不会编数字。

**每句都有多个说法**：长期用下来不会老看到同一句。
用数据本身当随机种子，同一份账单每次打开是同一句（不会刷新一下就换），
换个月份、换了数据组合，读到的就是另一种说法。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

import pandas as pd

from .models import Kind


def _yuan(x: float) -> str:
    return f"¥{x:,.0f}" if abs(x - round(x)) < 0.005 else f"¥{x:,.2f}"


def _md(ts) -> str:
    return f"{ts.month}月{ts.day}日"


def _pick(rng: random.Random, *options: str) -> str:
    return rng.choice(options)


@dataclass
class Note:
    """一份小记：一句总述 + 几条发现 + 一句建议。"""

    lead: str
    findings: list[str] = field(default_factory=list)
    tip: str = ""


def _seed(consume: pd.DataFrame) -> int:
    """用数据本身当种子：同一份账单说法固定，换数据才换说法。"""
    first = consume["ts"].min()
    return (
        int(first.year) * 10000
        + int(first.month) * 100
        + int(first.day)
        + len(consume) * 7
    )


def _month_totals(consume: pd.DataFrame) -> pd.Series:
    return consume.groupby(consume["ts"].dt.to_period("M"))["amount"].sum()


# ============================================================ 小记

def analyse(consume: pd.DataFrame, dropped: pd.DataFrame | None = None) -> Note | None:
    """读一遍消费记录，写一段小记。数据太少就返回 None（不硬凑）。"""
    if consume is None or consume.empty:
        return None

    rng = random.Random(_seed(consume))
    total = float(consume["amount"].sum())
    n = len(consume)
    start, end = consume["ts"].min(), consume["ts"].max()
    days = max(1, (end.normalize() - start.normalize()).days + 1)
    daily = total / days

    # ---------- 总述 ----------
    a, b = _md(start), _md(end)
    if days == 1:
        lead = _pick(
            rng,
            f"{a}这一天，你花了 <b>{_yuan(total)}</b>，{n} 笔。",
            f"就看 {a} 一天，一共 <b>{_yuan(total)}</b>，{n} 笔。",
        )
    else:
        lead = _pick(
            rng,
            f"{a}到{b}，这 {days} 天里你花了 <b>{_yuan(total)}</b>，{n} 笔，"
            f"平均每天 {_yuan(daily)}。",
            f"从 {a} 到 {b} 一共 {days} 天，花了 <b>{_yuan(total)}</b>。"
            f"{n} 笔，摊到每天差不多 {_yuan(daily)}。",
            f"{a}到{b}的这 {days} 天，合计 <b>{_yuan(total)}</b>，{n} 笔，"
            f"日均 {_yuan(daily)}。",
        )

    findings: list[str] = []

    # ---------- 花得最多的一类 ----------
    by_cat = consume.groupby("category")["amount"].sum().sort_values(ascending=False)
    top_cat = by_cat.index[0] if len(by_cat) else None
    if top_cat is not None and total > 0:
        top_amt = float(by_cat.iloc[0])
        share = top_amt / total
        if share >= 0.3:
            findings.append(_pick(
                rng,
                f"钱主要花在<b>{top_cat}</b>上，{_yuan(top_amt)}，占了 {share:.0%}。",
                f"<b>{top_cat}</b>是最大的一块：{_yuan(top_amt)}，占 {share:.0%}。",
                f"支出的大头是<b>{top_cat}</b> —— {_yuan(top_amt)}，{share:.0%}。",
            ))
        else:
            findings.append(_pick(
                rng,
                f"花得最多的是<b>{top_cat}</b>，{_yuan(top_amt)}（{share:.0%}），"
                "分得还算匀。",
                f"没有特别扎眼的一类，最多的<b>{top_cat}</b>也只占 {share:.0%}。",
            ))

    # ---------- 单笔最大 ----------
    if n >= 5:
        row = consume.loc[consume["amount"].idxmax()]
        who = str(row.get("counterparty") or "").strip() or "某家店"
        amt = float(row["amount"])
        if amt >= max(50.0, total * 0.12):
            findings.append(_pick(
                rng,
                f"最贵的一笔是 {_md(row['ts'])} 在<b>{who}</b>，{_yuan(amt)}。",
                f"{_md(row['ts'])} 那笔<b>{who}</b>最贵，{_yuan(amt)}，"
                "一笔就顶上好几天。",
            ))

    # ---------- 周末 vs 工作日 ----------
    if days >= 10:
        wk = consume[consume["ts"].dt.weekday >= 5]
        wd = consume[consume["ts"].dt.weekday < 5]
        if len(wk) and len(wd):
            wk_days = max(1, wk["ts"].dt.date.nunique())
            wd_days = max(1, wd["ts"].dt.date.nunique())
            wk_avg = float(wk["amount"].sum()) / wk_days
            wd_avg = float(wd["amount"].sum()) / wd_days
            if wk_avg > wd_avg * 1.5 and wk_avg - wd_avg > 10:
                findings.append(_pick(
                    rng,
                    f"周末一天平均 {_yuan(wk_avg)}，工作日 {_yuan(wd_avg)} —— "
                    "休息日的钱花得明显快一些。",
                    f"工作日日均 {_yuan(wd_avg)}，一到周末就变成 {_yuan(wk_avg)}。",
                ))

    # ---------- 小额高频 ----------
    if n >= 15:
        small = consume[consume["amount"] <= 20]
        share_small = len(small) / n
        word = None
        if share_small >= 0.7:
            word = "绝大多数都是"
        elif share_small >= 0.45:
            word = "差不多一半是"
        if word:
            findings.append(_pick(
                rng,
                f"这 {n} 笔有 {len(small)} 笔不到 20 元 —— {word}这种小钱，"
                f"加起来 {_yuan(float(small['amount'].sum()))}。",
                f"小额消费不少：{len(small)} 笔都在 20 元以下，"
                f"攒起来 {_yuan(float(small['amount'].sum()))}。",
            ))

    # ---------- 没花钱的日子 ----------
    if days >= 14:
        quiet = days - consume["ts"].dt.date.nunique()
        if quiet >= 3:
            findings.append(_pick(
                rng,
                f"其中 {quiet} 天一分没花，挺好的。",
                f"有 {quiet} 天完全没动钱包，节奏挺稳。",
            ))

    # ---------- 每月固定扣款 ----------
    if n >= 10:
        sub = consume.assign(月=consume["ts"].dt.to_period("M"))
        if sub["月"].nunique() >= 2:
            g = (
                sub.assign(档=sub["amount"].round(0))
                .groupby(["counterparty", "档"])
                .agg(月数=("月", "nunique"), 笔数=("amount", "count"))
            )
            rec = g[(g["月数"] >= 2) & (g["笔数"] <= g["月数"])]
            if len(rec) >= 2:
                findings.append(_pick(
                    rng,
                    f"有 {len(rec)} 处每个月都在扣，看着像订阅，"
                    "不用的话记得去关掉。",
                    f"认出 {len(rec)} 项每月自动扣款 —— 平时不太容易注意到，"
                    "有空翻一眼。",
                ))

    # ---------- 被剔掉的那些 ----------
    if dropped is not None and not dropped.empty:
        ex_amt = float(dropped["amount"].sum())
        if ex_amt > 0:
            findings.append(_pick(
                rng,
                f"另外有 {len(dropped)} 笔共 {_yuan(ex_amt)} 没算进花销"
                "（充值、退款、还钱这类），账面上是干净的。",
                f"还有 {len(dropped)} 笔 {_yuan(ex_amt)} 属于充值、退款、还钱，"
                "这些没有算成花销。",
            ))

    # ---------- 建议：只给一条 ----------
    tip = ""
    if top_cat is not None and total > 0 and by_cat.iloc[0] / total >= 0.45:
        tip = _pick(
            rng,
            f"如果想让下个月轻一点，可以先从<b>{top_cat}</b>看看～"
            "不是要你省，只是这类的弹性通常最大。",
            f"<b>{top_cat}</b>占了这么多，多半是有几处固定要去的地方。"
            "留意一下就好，不用刻意收着。",
        )
    elif days >= 10:
        m = _month_totals(consume)
        if len(m) >= 2 and m.iloc[-1] > m.iloc[-2] * 1.2:
            tip = _pick(
                rng,
                "这个月比上个月多花了 "
                f"{_yuan(float(m.iloc[-1] - m.iloc[-2]))}，"
                "翻一眼明细，看看是不是有哪笔是一次性的。",
                f"比上个月多出 {_yuan(float(m.iloc[-1] - m.iloc[-2]))}，"
                "大概率是某几笔一次性的开销，不一定是习惯变了。",
            )
        else:
            tip = _pick(
                rng,
                "花得挺稳的，没什么要提醒的 —— 保持就好～",
                "节奏很平稳，继续这样就好。",
                "没什么需要提醒的地方，看着挺健康的。",
            )

    return Note(lead=lead, findings=findings, tip=tip)


# ============================================================ 图表旁的小注
# 每张图/表下面配一句：说清"这张图里最值得注意的那件事"。
# 没东西可说就返回 None，页面上就不显示，不硬凑。

_KIND_NAME = {
    Kind.TRANSFER: "账户之间的搬运",
    Kind.REFUND: "退款",
    Kind.REPAYMENT: "还旧账",
    Kind.UNCLEAR: "还没定性的转账",
}


def hint_channel(consume: pd.DataFrame) -> str | None:
    if consume is None or consume.empty:
        return None
    by = consume.groupby("channel")["amount"].sum().sort_values(ascending=False)
    total = float(by.sum())
    if total <= 0:
        return None
    top, amt = by.index[0], float(by.iloc[0])
    share = amt / total
    if share >= 0.85:
        return f"几乎都走<b>{top}</b> —— {_yuan(amt)}，占 {share:.0%}，别的渠道只是零星几笔。"
    if share >= 0.45:
        return f"主要还是<b>{top}</b>，{_yuan(amt)}，{share:.0%}。"
    return f"{len(by)} 个渠道花得挺平均，最多的<b>{top}</b>也只占 {share:.0%}。"


def hint_dropped(dropped: pd.DataFrame) -> str | None:
    if dropped is None or dropped.empty:
        return None
    by = dropped.groupby("kind")["amount"].sum().sort_values(ascending=False)
    if by.empty or float(by.iloc[0]) <= 0:
        return None
    name = _KIND_NAME.get(by.index[0], str(by.index[0]))
    return f"金额最大的是<b>{name}</b>，{_yuan(float(by.iloc[0]))}。"


def hint_weekly(series: pd.DataFrame) -> str | None:
    if series is None or series.empty or len(series) < 2:
        return None
    avg = float(series["支出"].mean())
    if avg <= 0:
        return None
    top = series.loc[series["支出"].idxmax()]
    low = series.loc[series["支出"].idxmin()]
    if float(top["支出"]) >= avg * 1.4:
        return (
            f"<b>{_md(top['时间'])}</b>那一周最凶，{_yuan(float(top['支出']))}，"
            f"比平均多出 {_yuan(float(top['支出']) - avg)}。"
        )
    return (
        f"最松的一周是<b>{_md(low['时间'])}</b>，只有 {_yuan(float(low['支出']))}；"
        f"最紧的一周 {_yuan(float(top['支出']))}，差得不算大。"
    )


def hint_calendar(diag: pd.Series) -> str | None:
    if diag is None or diag.empty:
        return None
    top_day = diag.idxmax()
    parts = [f"<b>{_md(pd.Timestamp(top_day))}</b>花得最多，{_yuan(float(diag.max()))}"]
    quiet = int((diag <= 0).sum())
    if quiet >= 3:
        parts.append(f"另有 {quiet} 天没动钱包")
    # 日历没有坐标轴，颜色深浅这层含义必须说一句
    parts.append("格子越深，那天花得越多")
    return "；".join(parts) + "～"


def hint_recurring(rec: pd.DataFrame) -> str | None:
    if rec is None or rec.empty:
        return None
    if "单笔约" not in rec.columns:
        return None
    total = float(rec["单笔约"].sum())
    if total <= 0:
        return None
    return f"这些加起来每月大约 {_yuan(total)}，一年就是 {_yuan(total * 12)}。"


def hint_category(cat: pd.DataFrame) -> str | None:
    if cat is None or cat.empty or len(cat) < 2:
        return None
    total = float(cat["amount"].sum())
    if total <= 0:
        return None
    top2 = cat.head(2)
    share = float(top2["amount"].sum()) / total
    return (
        f"<b>{top2['category'].iloc[0]}</b>和<b>{top2['category'].iloc[1]}</b>"
        f"两项就占了 {share:.0%}。"
    )


def hint_category_small(cat: pd.DataFrame) -> str | None:
    """和左边那张重复，就说另一头：最少的那一类。"""
    if cat is None or cat.empty or len(cat) < 3:
        return None
    last = cat.iloc[-1]
    total = float(cat["amount"].sum()) or 1.0
    return (
        f"最少的是<b>{last['category']}</b>，"
        f"{_yuan(float(last['amount']))}，只占 {float(last['amount']) / total:.0%}。"
    )


def hint_top(top: pd.DataFrame, total: float) -> str | None:
    if top is None or top.empty or total <= 0:
        return None
    head3 = float(top.head(3)["金额"].sum())
    return (
        f"前三家店合计 {_yuan(head3)}，占全部花销的 {head3 / total:.0%}；"
        f"第一名是<b>{top.iloc[0]['商户']}</b>。"
    )


def hint_unclear(unknown: pd.DataFrame, consume: pd.DataFrame) -> str | None:
    if unknown is None or unknown.empty:
        return None
    amt = float(unknown["amount"].sum())
    total = float(consume["amount"].sum()) or 1.0
    return (
        f"这 {len(unknown)} 笔一共 {_yuan(amt)}，占花销的 {amt / total:.0%} —— "
        "告诉我是哪类，以后就不用再问啦。"
    )
