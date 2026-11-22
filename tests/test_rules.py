# -*- coding: utf-8 -*-
"""规则误判的回归测试。

这四条都是真实反馈出来的问题，改动规则后必须仍然通过；
用 `python -m unittest tests.test_rules` 或 `pytest tests/` 都能跑。
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from billkit.dedupe import mark_kind, pair_refunds          # noqa: E402
from billkit.models import Direction, Kind, Transaction      # noqa: E402


def make(amount, dt, counterparty="", note="", direction=Direction.EXPENSE,
         product="", raw_category="", status="", channel="微信") -> Transaction:
    return Transaction(
        channel=channel, time=dt, amount=amount, direction=direction,
        counterparty=counterparty, product=product, raw_category=raw_category,
        note=note, status=status,
    )


class CampusRuleTest(unittest.TestCase):
    """校园词必须和充值词同现，否则不判转账。"""

    def test_canteen_is_not_transfer(self):
        t = make(15.0, datetime(2026, 11, 3, 12, 0), "浙大城市学院食堂")
        mark_kind(t)
        self.assertNotEqual(t.kind, Kind.TRANSFER, "食堂吃饭被当成内部转账了")
        self.assertEqual(t.kind, Kind.NORMAL)

    def test_campus_supermarket_is_not_transfer(self):
        t = make(23.5, datetime(2026, 11, 4, 18, 0), "城院校园超市")
        mark_kind(t)
        self.assertNotEqual(t.kind, Kind.TRANSFER)

    def test_real_recharge_is_transfer(self):
        t = make(100.0, datetime(2026, 11, 5, 9, 0), "校园一卡通充值")
        mark_kind(t)
        self.assertEqual(t.kind, Kind.TRANSFER)

    def test_card_account_without_keyword_is_unclear_not_silent(self):
        """对方就是一卡通这张卡、又没写充值：标待确认，不能静默剔除。"""
        t = make(200.0, datetime(2026, 11, 6, 9, 0), "校园一卡通")
        mark_kind(t)
        self.assertEqual(t.kind, Kind.UNCLEAR)


class IncomeTransferWordTest(unittest.TestCase):
    """收入备注里的「转入」是真实收入，不能当内部转账。"""

    def test_income_with_transfer_word_stays_income(self):
        t = make(500.0, datetime(2026, 11, 7, 10, 0), "张三",
                 note="转入", direction=Direction.INCOME)
        mark_kind(t)
        self.assertNotEqual(t.kind, Kind.TRANSFER, "收入被当成内部转账了")
        self.assertEqual(t.kind, Kind.NORMAL)

    def test_qualified_transfer_still_works(self):
        """带限定语的划转仍然要判内部转账。"""
        t = make(300.0, datetime(2026, 11, 9, 8, 0), "余额宝-自动转入",
                 raw_category="投资理财")
        mark_kind(t)
        self.assertEqual(t.kind, Kind.TRANSFER)


class RefundPairTest(unittest.TestCase):
    """退款配对不能只看金额，否则会硬配到不相干的消费上。"""

    def test_same_amount_different_merchant_is_not_paired(self):
        buy = make(399.0, datetime(2026, 9, 1, 20, 0), "京东商城")
        refund = make(399.0, datetime(2026, 11, 2, 15, 0), "退款-某小店",
                      direction=Direction.INCOME, raw_category="退款")
        for t in (buy, refund):
            mark_kind(t)
        self.assertEqual(refund.kind, Kind.REFUND, "退款行本身仍应标成退款")

        pair_refunds([buy, refund])
        self.assertEqual(buy.kind, Kind.NORMAL, "京东那笔被强行配成退款了")

    def test_same_merchant_within_week_is_paired(self):
        buy = make(59.9, datetime(2026, 11, 10, 12, 0), "某小店", channel="支付宝")
        refund = make(59.9, datetime(2026, 11, 12, 9, 0), "退款-某小店",
                      direction=Direction.INCOME, raw_category="退款", channel="支付宝")
        for t in (buy, refund):
            mark_kind(t)
        self.assertEqual(pair_refunds([buy, refund]), 1)
        self.assertEqual(buy.kind, Kind.REFUND)


if __name__ == "__main__":
    unittest.main(verbosity=2)
