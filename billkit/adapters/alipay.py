# -*- coding: utf-8 -*-
"""支付宝解析。

真实数据有两种导出，格式差别很大，本适配器都要能吃：

A. 记账本导出（cashbook_record_*.csv，当前最常见）
   特别提示区（8 条）+ 空行 + 表头：
       记录时间, 分类, 收支类型, 金额, 备注, 账户, 来源, 标签
   —— 没有交易对方、没有交易单号、没有交易状态。
   → 备注就是商户/商品描述，拿它当「交易对方」；
   → 没有单号，靠 base.parse 的「同内容第几笔」保证不丢记录。

B. 标准账单明细（老版本）
       交易时间, 交易分类, 交易对方, 对方账号, 商品说明, 收/支, 金额, 收/付款方式, 交易状态, ...
   有「交易状态」，退款行要剔除。

编码是 GBK、说明区在表头之前，这两点由 normalize 统一处理。
"""
from __future__ import annotations

import pandas as pd

from ..models import Channel, Kind
from .base import BillAdapter


class AlipayAdapter(BillAdapter):
    channel = Channel.ALIPAY

    def postprocess(self, txn, row: pd.Series):
        # 退款成功 -> 退款（金额仍为正，必须剔除）
        if "退款" in txn.status:
            txn.kind = Kind.REFUND
            txn.category = "退款"
            return txn

        # 记账本导出没有「交易对方」列，备注就是对方 / 商品描述
        if not txn.counterparty and txn.note:
            txn.counterparty = txn.note.strip()[:24]

        return txn
