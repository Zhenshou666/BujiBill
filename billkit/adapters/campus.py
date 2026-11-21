# -*- coding: utf-8 -*-
"""校园一卡通 —— 目前只留接口，等确认平台能否导出后再实现自动抓取。

已知入口（你给的那个地址）：
    http://etcard.hzcu.edu.cn:8088/easytong_webapp/index.html#/bill
它是 Vue 单页应用 + 校园统一身份认证登录，没有登录态拿不到数据，
所以现阶段走「手动导出 -> 丢进来解析」这条路；等确认有导出按钮或公开接口，
只需要在 fetch() 里补 HTTP 请求，其余解析/去重/分类逻辑完全复用。

TODO（等你确认后补）：
    1. 登录后账单页有没有「导出 / 下载」按钮
    2. 能选的时间跨度（一个月？一学期？）
    3. 明细里有没有商户名 —— 没有的话就只能做现金流校准，做不了分类画像
"""
from __future__ import annotations

import pandas as pd

from ..models import Channel, Direction
from ..normalize import map_columns
from .base import BillAdapter

# 一卡通平台入口（界面上「去登录」按钮跳这里）
CAMPUS_LOGIN_URL = "http://etcard.hzcu.edu.cn:8088/easytong_webapp/index.html#/bill"

# 一卡通导出文件常见的表头首列
_HEADER_CELLS = ("交易时间", "记账时间", "交易日期", "发生时间")


class CampusAdapter(BillAdapter):
    channel = Channel.CAMPUS

    # ---------------------------------------------------------- 钩子
    def postprocess(self, txn, row: pd.Series):
        # 一卡通的表往往没有「收/支」列，只能靠业务类型推
        if txn.direction == Direction.NEUTRAL:
            text = f"{txn.raw_category}{txn.product}{txn.counterparty}"
            txn.direction = Direction.INCOME if "充" in text else Direction.EXPENSE
        return txn

    # ---------------------------------------------------------- 预留：自动抓取
    def fetch(self, *_args, **_kwargs):
        """自动抓取的占位。真要实现时在这里补：
        1) requests.Session() 走统一身份认证拿 cookie
        2) 调账单接口（浏览器 F12 -> Network 里能看到）
        3) 把返回的 JSON 转成 DataFrame，交给 self.parse 之后的逻辑
        """
        raise NotImplementedError(
            "一卡通自动抓取尚未实现（需要统一身份认证）。\n"
            f"请先登录 {CAMPUS_LOGIN_URL} 手动导出账单，再上传 CSV/Excel。"
        )

    # ---------------------------------------------------------- 说明文案
    @staticmethod
    def columns_report(raw: bytes) -> dict:
        """调试用：读一份文件，报告实际有哪些列、能映射到哪些字段。"""
        adapter = CampusAdapter()
        df = adapter.read(raw)
        return {
            "实际列名": list(df.columns),
            "字段映射": map_columns(df.columns),
            "行数": len(df),
            "首行样例": df.head(1).to_dict("records"),
        }
