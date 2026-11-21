# -*- coding: utf-8 -*-
"""去重与性质判定 —— 整个项目最值钱的一段。

核心场景（一定要讲给老师听）：
    你在微信/支付宝给校园卡充值 100 元，然后刷卡吃饭花了 44 元。
    真实消费只有 44 元。
    但直接相加会得到 100 + 44 = 144 元，凭空多算 2.3 倍。
所以必须把「一卡通充值」识别成账户内部转账并剔除，只保留一卡通里的真实刷卡消费。
同理还有：零钱提现、余额宝转入转出、信用卡还款、全额退款。
"""
from __future__ import annotations

from .models import Channel, Direction, Kind

# 一卡通充值：出现这些词，说明钱只是从微信/支付宝挪到了校园卡，没有产生消费
# 注意别放「校园」「市民卡」这种宽泛词：
#   「校园网」「校园超市」是真消费；「杭州市民卡」是社保/交通卡，不是校园卡
CAMPUS_WORDS = ("校园卡", "一卡通", "饭卡", "城院", "城市学院")
RECHARGE_WORDS = ("充值", "圈存", "续费")

# 账户之间的搬运（不要放「存入」「转」这类过于宽泛的词，会误伤红包和转账）
TRANSFER_WORDS = (
    "零钱提现", "提现到", "提现",
    "余额宝", "余利宝", "自动转入", "转入到", "转出到",
    "转入", "转出",                     # 余利宝/理财通这类货币基金划转
    "理财通", "零钱通", "自动赎回",
)

# 信用卡还款：钱是还给银行，不是当期消费
REPAYMENT_WORDS = ("信用卡还款", "还款", "花呗还款", "白条还款")

# 个人之间转账：性质不明确，交给用户人工确认
P2P_WORDS = ("转账", "红包")

TRANSFER_HINT = (
    "被标记为「内部转账」的记录不计入消费：它们只是钱在自己账户之间移动，"
    "真实消费由收款方那一侧记录（例如一卡通的刷卡明细）。"
)


def _text_of(txn) -> str:
    """用于匹配的业务文本。

    注意：这里故意 **不包含 status**。
    微信红包/转账的状态统一写「已存入零钱」，一旦把 status 拼进来，
    「存入」就会命中转账关键词，把真实的红包收入误判成内部转账。
    status 只在退款判定时单独看。
    """
    return " ".join([txn.counterparty, txn.product, txn.raw_category, txn.note])


def _add_note(txn, msg: str) -> None:
    txn.note = (txn.note + " | " + msg).strip(" |")


def mark_kind(txn):
    """判定交易性质，必要时修正 category。返回同一个 txn（原地修改）。"""
    text = _text_of(txn)
    raw_cat = (txn.raw_category or "").strip()

    # -1) 理财收益是真实收入，必须最先判定，否则会被下面的「理财划转」规则吃掉
    if txn.direction == Direction.INCOME and "收益" in text:
        txn.kind = Kind.NORMAL
        txn.category = "收入"
        return txn

    # 0) 账单自带的分类先说话（支付宝记账本会把退款/理财单独标类）
    if "退款" in raw_cat or "退款" in txn.status:
        txn.kind = Kind.REFUND
        txn.category = "退款"
        _add_note(txn, "已退款，不计入消费")
        return txn
    if raw_cat in ("投资理财", "理财", "余额宝"):
        txn.kind = Kind.TRANSFER
        txn.category = "内部转账"
        _add_note(txn, "理财账户划转，不计入消费")
        return txn

    # 1) 全额退款：原始行金额仍是正数，若照算会虚增支出
    if "退款" in txn.status or "已退还" in txn.status:
        txn.kind = Kind.REFUND
        txn.category = "退款"
        _add_note(txn, "已退款，不计入消费")
        return txn

    # 2) 一卡通充值（跨渠道重复的关键）
    if txn.channel != Channel.CAMPUS:
        if any(w in text for w in CAMPUS_WORDS) and any(w in text for w in RECHARGE_WORDS):
            txn.kind = Kind.TRANSFER
            txn.category = "内部转账"
            _add_note(txn, "一卡通充值，由校园卡明细记录真实消费")
            return txn
        if any(w in text for w in CAMPUS_WORDS) and txn.direction == Direction.EXPENSE:
            # 只有对方是校园卡、没写"充值"字样，大概率仍是充值
            txn.kind = Kind.TRANSFER
            txn.category = "内部转账"
            _add_note(txn, "疑似一卡通充值，请人工确认")
            return txn

    # 3) 卡内充值（校园卡自己的充值记录）
    #    一卡通平台的类型名是「第三方支付平台转账」，不含「充值」二字，要单独认
    if txn.channel == Channel.CAMPUS and (
        any(w in text for w in RECHARGE_WORDS) or "转账" in txn.raw_category
    ):
        txn.kind = Kind.TRANSFER
        txn.category = "内部转账"
        _add_note(txn, "校园卡充值，真实消费以刷卡记录为准")
        return txn

    # 3.5) 理财收益是真实收入，不能因为带「余额宝」三个字就被当成转账
    if txn.direction == Direction.INCOME and "收益" in text:
        txn.kind = Kind.NORMAL
        txn.category = "收入"
        return txn

    # 4) 信用卡 / 花呗还款
    if any(w in text for w in REPAYMENT_WORDS):
        txn.kind = Kind.REPAYMENT
        txn.category = "还款"
        return txn

    # 5) 零钱提现 / 余额宝 / 账户互转
    if any(w in text for w in TRANSFER_WORDS):
        txn.kind = Kind.TRANSFER
        txn.category = "内部转账"
        return txn

    # 6) 个人转账：性质不明，不擅自计入消费，也不擅自剔除
    if txn.direction == Direction.EXPENSE and any(w in text for w in P2P_WORDS):
        txn.kind = Kind.UNCLEAR
        txn.category = "转账"
        _add_note(txn, "个人转账，请人工确认是否算支出")
        return txn

    # 7) 兜底：「不计收支」本身就是账单在说「这笔不进收支统计」
    #    典型是账户间划转（余额宝↔余额、零钱↔零钱通），按内部转账处理
    if txn.kind == Kind.NORMAL and txn.direction == Direction.NEUTRAL:
        txn.kind = Kind.TRANSFER
        txn.category = "内部转账"
        _add_note(txn, "账单标记为不计收支，按内部转账处理")

    return txn


def find_recharge_pairs(df):
    """找出「充值」与「刷卡消费」的对应关系，仅用于界面上解释，不强耦合。

    返回 (充值总额, 一卡通刷卡总额)，让用户直观看到重复计算有多大。
    """
    if df.empty:
        return 0.0, 0.0
    recharge = df[(df["kind"] == Kind.TRANSFER) & (df["category"] == "内部转账")]
    recharge_total = float(recharge["amount"].sum())
    campus_consume = df[(df["channel"] == Channel.CAMPUS) & (df["kind"] == Kind.NORMAL)]
    campus_total = float(campus_consume["amount"].sum())
    return recharge_total, campus_total


def _refund_target_name(txn) -> str:
    """支付宝的退款行，对方名是「退款-原商户名」，把前缀削掉就是线索。"""
    name = (txn.counterparty or "").strip()
    for prefix in ("退款-", "退款－", "退款 "):
        if name.startswith(prefix):
            return name[len(prefix):].strip()
    return ""


def pair_refunds(txns) -> int:
    """把「退款」和它对应的那笔消费配对，避免退掉的东西还算成花掉。

    微信省事：直接在原笔的「当前状态」写「已全额退款」，标一下就完。
    支付宝「记账本」则把退款单独记一行（收/支=不计收支，分类=退款，对方名带「退款-」前缀），
    原始那笔支出还躺在账单里 —— 不配对的话，买了又退的东西
    依然会出现在「花钱最多的地方」里。

    配对依据：同渠道 + 同金额 + 名字对得上（或时间最近）。
    返回配对成功的笔数。
    """
    from .models import Direction, Kind

    refunds = [t for t in txns if t.kind == Kind.REFUND and t.direction != Direction.EXPENSE]
    if not refunds:
        return 0
    pool = [t for t in txns if t.kind == Kind.NORMAL and t.direction == Direction.EXPENSE]
    used: set[int] = set()
    paired = 0

    for r in refunds:
        target = _refund_target_name(r)
        best, best_score = None, None
        for c in pool:
            if id(c) in used or c.channel != r.channel:
                continue
            if abs(c.amount - r.amount) > 0.01:
                continue
            # 名字对得上优先，其次按时间距离
            name_hit = 1 if target and (target == (c.counterparty or "").strip()
                                       or target in (c.counterparty or "")
                                       or (c.counterparty or "") in target) else 0
            score = (name_hit, -abs((r.time - c.time).total_seconds()))
            if best_score is None or score > best_score:
                best, best_score = c, score
        if best is not None:
            best.kind = Kind.REFUND
            best.category = "退款"
            _add_note(best, "已退款，不计入消费")
            used.add(id(best))
            paired += 1
    return paired
