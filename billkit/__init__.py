# -*- coding: utf-8 -*-
"""billkit —— 微信 / 支付宝 / 校园一卡通 三源账单整合工具包。

对外只暴露这几样东西：
    from billkit import ADAPTERS, Channel, Kind, Transaction, store
"""
from __future__ import annotations

from . import store
from .adapters import ADAPTERS, CHANNELS, CAMPUS_LOGIN_URL, detect_channel
from .classify import classify, load_rules
from .dedupe import TRANSFER_HINT, mark_kind
from .models import Channel, Direction, Kind, Transaction

__all__ = [
    "ADAPTERS", "CHANNELS", "CAMPUS_LOGIN_URL", "detect_channel",
    "Channel", "Direction", "Kind", "Transaction",
    "classify", "load_rules", "mark_kind", "TRANSFER_HINT", "store",
]
__version__ = "0.1.0"
