# -*- coding: utf-8 -*-
"""微信支付账单解析。

获取：我 -> 服务 -> 钱包 -> 账单 -> 右上角「常见问题」->「下载账单」->「用于个人对账」
      选时间范围 + 填邮箱 + 验证支付密码，24 小时内邮箱收到加密 zip，
      解压密码在「微信支付」公众号消息里。解压出的 .csv 直接丢进来即可。

微信的坑：
  - UTF-8 带 BOM，前十几行是说明文字
  - 「收/支」列里中性交易写的是 "/"
  - 全额退款的行「当前状态」是「已全额退款」，但金额仍然是正数
"""
from __future__ import annotations

import pandas as pd

from ..models import Channel, Direction, Kind
from .base import BillAdapter


class WechatAdapter(BillAdapter):
    channel = Channel.WECHAT

    def postprocess(self, txn, row: pd.Series):
        # 中性交易（提现、零钱通存取等）微信记成 "/"
        if txn.direction == Direction.NEUTRAL and not txn.status:
            txn.direction = Direction.EXPENSE

        # 全额退款 -> 退款（金额仍为正，必须剔除）
        if "已全额退款" in txn.status or txn.status == "已退款":
            txn.kind = Kind.REFUND
            txn.category = "退款"
        return txn
