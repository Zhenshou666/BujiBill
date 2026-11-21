# -*- coding: utf-8 -*-
"""分类器：关键词规则表 -> 分类名。

为什么先做规则而不是直接上大模型：
  - 账单含真实隐私，本地规则不联网
  - 规则命中率约 80%，且可解释、可当场改（答辩时能讲清每一笔为什么这么分）
  - 剩下的「未分类」再考虑接 LLM 兜底，属于加分项
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .store import DATA_DIR

RULES_PATH = DATA_DIR / "data" / "rules.json"

# 支付宝「记账本」导出自带「分类」列（用户自己填的），比关键词更准，优先采用。
CATEGORY_ALIASES: dict[str, str] = {
    "餐饮": "餐饮", "美食": "餐饮", "吃饭": "餐饮", "外卖": "餐饮",
    "交通": "交通", "出行": "交通", "打车": "交通", "爱车": "交通",
    "购物": "日用", "日用": "日用", "生活": "日用", "超市": "日用",
    "生活日用": "日用", "穿搭美容": "日用", "美容": "日用",
    "学习": "学习", "教育": "学习", "书籍": "学习",
    "娱乐": "娱乐", "休闲": "娱乐", "游戏": "娱乐", "休闲玩乐": "娱乐",
    "通讯": "通讯", "话费": "通讯", "通讯费": "通讯",
    "医疗": "医疗", "健康": "医疗", "医药": "医疗", "医疗保健": "医疗",
    "住宿": "住宿", "住房": "住宿", "房租": "住宿",
    "数码": "数码", "电器": "数码",
    "转账": "转账", "人情": "转账", "红包": "转账", "借还": "转账", "借还款": "转账",
    "内部转账": "内部转账", "理财": "内部转账", "投资": "内部转账", "投资理财": "内部转账",
    "退款": "退款",
    "收入": "收入", "工资": "收入",
}


@lru_cache(maxsize=1)
def load_rules() -> dict[str, tuple[str, ...]]:
    raw = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    # 下划线开头的键是注释，跳过；关键词统一转小写，避免 Steam / STARBUCKS 匹配不上
    return {
        k: tuple(w.lower() for w in v)
        for k, v in raw.items()
        if not k.startswith("_")
    }


def classify(txn) -> str:
    """给一笔交易打分类。

    优先级：账单自带的「分类」列 > 关键词规则表 > 未分类。
    """
    from .models import Direction

    if txn.direction == Direction.INCOME:
        return "收入"

    # 1) 账单里已经有分类（支付宝记账本），直接用
    raw = (txn.raw_category or "").strip()
    if raw in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[raw]

    # 2) 关键词规则
    text = " ".join([txn.counterparty, txn.product, txn.raw_category, txn.note]).lower()
    for category, words in load_rules().items():
        if category == "收入":
            continue
        if any(w and w in text for w in words):
            return category
    return "未分类"


def add_rule(category: str, keyword: str) -> str:
    """把一个关键词写进 rules.json 的某个分类下（已存在则不重复加）。

    给界面上的「教它认一个新商户」用，用户不必打开 json 文件。
    """
    kw = (keyword or "").strip()
    if not kw:
        raise ValueError("关键词不能为空")
    raw = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    words = raw.setdefault(category, [])
    if not isinstance(words, list):
        raise ValueError(f"分类「{category}」的规则格式不对")
    if kw not in words:
        words.append(kw)
        RULES_PATH.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return kw
