# -*- coding: utf-8 -*-
"""统一交易模型。

三个渠道（微信 / 支付宝 / 校园卡）的原始表格字段完全不同，
解析后一律变成本文件里的 Transaction，后面所有统计逻辑只写一遍。
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass


class Channel:
    """数据来源渠道。"""
    WECHAT = "微信"
    ALIPAY = "支付宝"
    CAMPUS = "校园卡"


class Direction:
    """资金流向（只看方向，金额本身永远存正数）。"""
    EXPENSE = "支出"
    INCOME = "收入"
    NEUTRAL = "不计收支"


class Kind:
    """交易性质。只有 NORMAL 会被算进消费统计，这是防重复记账的关键。"""
    NORMAL = "消费"
    TRANSFER = "内部转账"      # 一卡通充值 / 零钱提现 / 余额宝转入转出
    REFUND = "退款"            # 已全额退款
    REPAYMENT = "还款"         # 信用卡还款
    UNCLEAR = "待确认"         # 个人转账等，需人工判断


@dataclass
class Transaction:
    channel: str
    time: object                      # datetime
    amount: float                     # 永远为正数
    direction: str
    counterparty: str = ""
    product: str = ""
    raw_category: str = ""
    pay_method: str = ""
    status: str = ""
    order_id: str = ""
    merchant_id: str = ""
    note: str = ""
    category: str = "未分类"
    kind: str = Kind.NORMAL
    source_file: str = ""
    uid_hint: str = ""                # 无交易单号时，由解析层补「同内容第几笔」

    @property
    def uid(self) -> str:
        """全局唯一键：有交易单号就用单号，没有就用 渠道+时间+金额+对方 的摘要。"""
        if self.uid_hint:
            return self.uid_hint
        if self.order_id:
            return f"{self.channel}:{self.order_id}"
        raw = f"{self.channel}|{self.time:%Y-%m-%d %H:%M:%S}|{self.amount:.2f}|{self.counterparty}"
        return f"{self.channel}:#{hashlib.md5(raw.encode('utf-8')).hexdigest()[:16]}"

    @property
    def signed_amount(self) -> float:
        if self.direction == Direction.INCOME:
            return self.amount
        if self.direction == Direction.EXPENSE:
            return -self.amount
        return 0.0

    @property
    def is_consumption(self) -> bool:
        """是否计入消费统计。"""
        return self.kind == Kind.NORMAL and self.direction == Direction.EXPENSE

    def to_row(self) -> dict:
        d = asdict(self)
        d["ts"] = self.time.strftime("%Y-%m-%d %H:%M:%S")
        d.pop("time", None)
        d["uid"] = self.uid
        return d
