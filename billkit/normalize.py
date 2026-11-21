# -*- coding: utf-8 -*-
"""脏数据清洗层。

真实账单长这样，你必须先扛住这些：
  1. 微信是 UTF-8-带BOM，支付宝是 GBK
  2. 前 10~20 行是说明文字，真表头藏在中间
  3. 金额是 "¥16.00" 这种字符串，还可能带千分位
  4. 时间格式五花八门，还有 "2026年11月3日"
  5. 表尾可能跟着 "注：..." 之类的说明行
本模块负责把这些统统捋平。
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime

import pandas as pd

# ---------------------------------------------------------------- 编码探测

def decode_bytes(raw: bytes) -> str:
    """依次尝试常见编码。utf-8-sig 解不了 GBK，gb18030 几乎能解一切，所以放最后兜底。"""
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("gb18030", errors="replace")


# ------------------------------------------------------------ 表头行定位

_HEADER_FIRST_CELLS = ("交易时间", "记录时间", "记账时间", "交易日期", "发生时间", "创建时间")


def find_header_line(text: str, max_scan: int = 150) -> int | None:
    """扫描前若干行，找到首列是「交易时间」的那一行，返回其行号。"""
    for i, line in enumerate(text.splitlines()[:max_scan]):
        if not line.strip():
            continue
        try:
            first = next(csv.reader([line]))[0].strip().lstrip("\ufeff")
        except Exception:
            continue
        if first in _HEADER_FIRST_CELLS:
            return i
    return None


def read_bill_csv(raw: bytes) -> pd.DataFrame:
    """把一份账单 CSV 读成 DataFrame（自动跳过说明头）。"""
    text = decode_bytes(raw)
    idx = find_header_line(text)
    if idx is None:
        head = "\n".join(text.splitlines()[:8])
        raise ValueError(
            "没找到表头行（期望某行首列为「交易时间」）。文件开头是：\n" + head
        )
    body = "\n".join(text.splitlines()[idx:])
    df = pd.read_csv(io.StringIO(body), dtype=str, engine="python", on_bad_lines="skip")
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
    return df.dropna(how="all").reset_index(drop=True)


def is_excel(raw: bytes) -> bool:
    """xlsx/xls 的本质是 zip，前两字节是 PK。"""
    return raw[:2] == b"PK"


def read_bill_excel(raw: bytes) -> pd.DataFrame:
    """读 xlsx 账单：微信新版导出就是 xlsx，说明文字同样在表头之前。"""
    book = pd.read_excel(io.BytesIO(raw), header=None, dtype=str)
    for i in range(min(80, len(book))):
        values = [str(v).strip() for v in book.iloc[i].tolist()]
        if any(v in _HEADER_FIRST_CELLS for v in values):
            df = book.iloc[i + 1:].copy()
            header, seen = [], {}
            for c in values:                       # 处理空列名与重名
                c = "" if c.lower() == "nan" else c
                if not c:
                    header.append("_empty_%d" % len(header))
                elif c in seen:
                    seen[c] += 1
                    header.append(f"{c}_{seen[c]}")
                else:
                    seen[c] = 1
                    header.append(c)
            df.columns = header
            df = df[[c for c in df.columns if not c.startswith("_empty_")]]
            return df.dropna(how="all").reset_index(drop=True)
    raise ValueError("这个 Excel 里没找到「交易时间」表头行，请确认导出的是流水明细。")


def read_bill_bytes(raw: bytes) -> pd.DataFrame:
    """统一入口：自动区分 CSV / Excel。"""
    return read_bill_excel(raw) if is_excel(raw) else read_bill_csv(raw)


# --------------------------------------------------------------- 列名归一

# 字段 -> 可能出现的列名（按优先级）
# 注意这里混了两套真实格式：
#   微信流水：交易时间/交易类型/交易对方/商品/收、支/金额(元)/支付方式/当前状态/交易单号/商户单号/备注
#   支付宝记账本：记录时间/分类/收支类型/金额/备注/账户/来源/标签
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "time":         ("交易时间", "记录时间", "记账时间", "交易日期", "发生时间", "创建时间"),
    "direction":    ("收/支", "收支类型", "收支", "收/付", "借贷标志"),
    "amount":       ("金额(元)", "金额", "交易金额", "消费金额", "发生额", "本次金额"),
    "counterparty": ("交易对方", "对方", "商户名称", "商户", "收款方", "对方户名", "记账对象"),
    "product":      ("商品", "商品说明", "商品名称", "摘要", "用途", "消费项目"),
    "raw_category": ("交易分类", "分类", "交易类型", "业务类型", "交易种类"),
    "pay_method":   ("支付方式", "收/付款方式", "付款方式", "账户"),
    "status":       ("当前状态", "交易状态", "状态"),
    "order_id":     ("交易单号", "交易订单号", "流水号", "交易流水号", "订单号"),
    "merchant_id":  ("商户单号", "商家订单号", "商户号"),
    "note":         ("备注", "说明"),
    "balance":      ("余额", "账户余额", "卡余额"),
}


def _squash(s: str) -> str:
    """去掉空格和括号，方便「金额(元)」和「金额」互相匹配。"""
    return re.sub(r"[\s()（）]", "", s)


def _pick(columns, aliases) -> str | None:
    cols = list(columns)
    for a in aliases:                                  # 1. 完全相等
        if a in cols:
            return a
    norm = {_squash(c): c for c in cols}
    for a in aliases:                                  # 2. 去空格后相等
        if _squash(a) in norm:
            return norm[_squash(a)]
    for a in aliases:                                  # 3. 前缀 / 后缀包含
        key = _squash(a)
        for k, c in norm.items():
            if k.startswith(key) or k.endswith(key):
                return c
    return None


def map_columns(columns) -> dict[str, str | None]:
    """把真实列名映射到统一字段名。"""
    return {field: _pick(columns, aliases) for field, aliases in FIELD_ALIASES.items()}


# ------------------------------------------------------------ 值解析

_AMOUNT_NOISE = re.compile(r"[¥￥,，\s元]")


def parse_amount(value) -> float | None:
    """'¥1,234.50' / '12.00' / '-5' -> 1234.5。恒返回正数。"""
    if value is None:
        return None
    s = _AMOUNT_NOISE.sub("", str(value)).replace("−", "-").replace("—", "-")
    if s in ("", "-", "nan", "None", "nan.0"):
        return None
    try:
        return abs(float(s))
    except ValueError:
        return None


_TIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d",
    "%Y年%m月%d日 %H:%M:%S", "%Y年%m月%d日 %H:%M", "%Y年%m月%d日",
    "%Y%m%d%H%M%S",
)


def parse_time(value) -> datetime | None:
    if value is None:
        return None
    s = str(value).strip().replace("\u3000", " ")
    if not s or s.lower() in ("nan", "nat", "none", "-"):
        return None
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    ts = pd.to_datetime(s, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.to_pydatetime()


def normalize_direction(value, channel: str = "") -> str:
    """把各家的「收/支」栏统一成 收入 / 支出 / 不计收支。"""
    from .models import Direction

    s = str(value or "").strip()
    if s in ("收入", "收", "入", "贷"):
        return Direction.INCOME
    if s in ("支出", "支", "出", "借"):
        return Direction.EXPENSE
    return Direction.NEUTRAL


def cell(row: pd.Series, cols: dict, field: str) -> str:
    """按映射取单元格文本，取不到就返回空串。"""
    name = cols.get(field)
    if not name or name not in row.index:
        return ""
    v = row[name]
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    return "" if s.lower() == "nan" else s
