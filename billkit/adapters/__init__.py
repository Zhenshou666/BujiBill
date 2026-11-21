# -*- coding: utf-8 -*-
"""解析器注册表 + 按文件名自动识别渠道。"""
from __future__ import annotations

from ..models import Channel
from .alipay import AlipayAdapter
from .base import BillAdapter
from .campus import CAMPUS_LOGIN_URL, CampusAdapter
from .wechat import WechatAdapter

ADAPTERS: dict[str, type[BillAdapter]] = {
    Channel.WECHAT: WechatAdapter,
    Channel.ALIPAY: AlipayAdapter,
    Channel.CAMPUS: CampusAdapter,
}

CHANNELS = list(ADAPTERS.keys())


def detect_channel(filename: str) -> str | None:
    """靠文件名猜渠道，猜不出来就让用户手选。

    真实导出文件的命名（别只认「微信」「支付宝」这两个词）：
        微信：微信支付账单流水文件(20261017-20261117)_20261117152445.xlsx
        支付宝：cashbook_record_20261117_152639.csv
    """
    name = filename.lower()
    if "微信" in filename or "wechat" in name or "wxpay" in name:
        return Channel.WECHAT
    if "支付宝" in filename or "alipay" in name or "cashbook" in name:
        return Channel.ALIPAY
    if any(k in filename for k in ("校园", "一卡通", "饭卡")) or any(
        k in name for k in ("campus", "etcard", "card")
    ):
        return Channel.CAMPUS
    return None


__all__ = ["ADAPTERS", "CHANNELS", "BillAdapter", "CAMPUS_LOGIN_URL", "detect_channel"]
