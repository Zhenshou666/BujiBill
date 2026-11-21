# -*- coding: utf-8 -*-
"""解析器基类。

子类只需要声明 channel，个别差异（状态含义、方向推断）用 postprocess 钩子覆盖，
通用的「找表头 -> 映射列 -> 逐行清洗 -> 分类 -> 判性质」全在这里写一次。
"""
from __future__ import annotations

import pandas as pd

from ..classify import classify
from ..dedupe import mark_kind, pair_refunds
from ..models import Transaction
from ..normalize import (
    cell, map_columns, normalize_direction, parse_amount, parse_time, read_bill_bytes,
)


class BillAdapter:
    channel: str = "未知"

    # ---------------------------------------------------------- 读取
    def read(self, raw: bytes) -> pd.DataFrame:
        """CSV / XLSX 都走这里：微信新版导出是 xlsx，支付宝是 GBK 的 csv。"""
        return read_bill_bytes(raw)

    # ---------------------------------------------------------- 解析
    def parse(self, raw: bytes, source_file: str = "") -> tuple[list[Transaction], list[str]]:
        df = self.read(raw)
        cols = map_columns(df.columns)
        if cols.get("time") is None or cols.get("amount") is None:
            raise ValueError(
                f"[{self.channel}] 缺少「时间」或「金额」列。实际列名：{list(df.columns)}"
            )

        txns: list[Transaction] = []
        warns: list[str] = []
        seen: dict[str, int] = {}          # 处理「没有交易单号」的渠道（如支付宝记账本）
        for i, row in df.iterrows():
            t = parse_time(cell(row, cols, "time"))
            amount = parse_amount(cell(row, cols, "amount"))
            if t is None or amount is None:
                # 表尾说明行、汇总行会走到这里，正常跳过
                if len(warns) < 5:
                    warns.append(
                        f"第 {i + 2} 行时间/金额无法解析，已跳过："
                        f"{cell(row, cols, 'time')!r} / {cell(row, cols, 'amount')!r}"
                    )
                continue

            txn = Transaction(
                channel=self.channel,
                time=t,
                amount=amount,
                direction=normalize_direction(cell(row, cols, "direction"), self.channel),
                counterparty=cell(row, cols, "counterparty"),
                product=cell(row, cols, "product"),
                raw_category=cell(row, cols, "raw_category"),
                pay_method=cell(row, cols, "pay_method"),
                status=cell(row, cols, "status"),
                order_id=cell(row, cols, "order_id"),
                merchant_id=cell(row, cols, "merchant_id"),
                note=cell(row, cols, "note"),
                source_file=source_file,
            )
            txn = self.postprocess(txn, row)
            txn.category = classify(txn)
            txn = mark_kind(txn)

            # 没有交易单号的渠道：内容完全相同的多笔不能被合成一笔，
            # 用「同内容第几笔」做区分；同一份文件重复导入时序号稳定，仍然幂等。
            base_uid = txn.uid
            n = seen.get(base_uid, 0) + 1
            seen[base_uid] = n
            if n > 1:
                txn.uid_hint = f"{base_uid}#{n}"

            txns.append(txn)

        # 全部解析完再配对退款：需要跨行看，单行判定做不到
        pair_refunds(txns)
        return txns, warns

    # ---------------------------------------------------------- 钩子
    def postprocess(self, txn: Transaction, row: pd.Series) -> Transaction:
        """子类可覆盖：修正方向、补充字段。"""
        return txn
