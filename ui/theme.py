# -*- coding: utf-8 -*-
"""Streamlit 外观主题：手帐纸质风。

为什么单独一个模块：
    CSS 字符串很长，塞进 app.py 会把主逻辑淹掉；而且主题是纯表现层，
    和「账单解析 / 去重」这些业务逻辑没有任何关系，分开更清楚。

用法（在 app.py 里，set_page_config 之后、任何 st.* 渲染之前调用）：

    from ui_theme import apply_theme
    apply_theme()
"""
from __future__ import annotations

import streamlit as st

# 字体：霞鹜文楷（正文与标题统一），用 @import 而不是 <link>，
# 因为 st.markdown 会把 <link> 过滤掉，<style> 里的 @import 才能生效
_FONT_CSS = """
/* 字体走本地静态目录，不走 CDN：外网不能保证通，exe 里 WebView2 更容易拿不到 */
@import url('/app/static/fonts/lxgw.css');
/* 原来的 Google Fonts（Noto Serif SC）在国内基本连不上，已去掉，交给系统楷体兜底 */
"""

_THEME_CSS = """
:root{
  /* 莫奈色板：取《睡莲》那组的灰调 —— 水蓝、藕粉、雾紫、苔绿、暖黄，
     全部压低饱和度，纸底偏冷一点。变量名沿用旧的（matcha/peach/…），
     这样不必去改几十条规则，只换这里的值。 */
  --paper:#F7F4EC;
  --paper-2:#FDFBF6;
  --paper-3:#F1EDE3;
  --ink:#3B3A45;
  --ink-soft:#6C6875;
  --line:rgba(120,118,130,.10);
  --matcha:#9CB8A4;   /* 苔绿 */
  --peach:#D6A6A2;    /* 藕粉 */
  --sky:#8AA6BF;      /* 水蓝 */
  --sun:#E6D2A2;      /* 暖黄 */
  --clay:#A79BC0;     /* 雾紫 */
  --r-lg:24px 20px 26px 22px;   /* 不规则圆角，模仿手绘框 */
  --r-md:16px 18px 14px 17px;
  --shadow:5px 6px 0 rgba(59,58,69,.12);
}

/* ---------- 纸面 ---------- */
.stApp{
  background-color:var(--paper);
  /* 横线会从字中间穿过去，形成视觉上的"笔画断裂/毛刺"。
     改用点阵：手帐方格本常见，且永远不会干扰文字。 */
  background-image:
    radial-gradient(rgba(120,118,130,.16) 1px, transparent 1.2px),
    radial-gradient(circle at 12% 0%, #FFFBF0 0%, transparent 46%);
  background-size:22px 22px, 100% 100%;
  font-family:'LXGW WenKai','Noto Sans SC',serif;
  color:var(--ink);
  font-size:17px;
  line-height:1.8;
}
[data-testid="stHeader"], [data-testid="stToolbar"], header[data-testid="stHeader"]{
  background:transparent;
}
#MainMenu, footer{visibility:hidden}
/* 注意：顶栏 stHeader 里装着「侧边栏收起后的展开按钮」，
   整条藏掉会导致侧边栏一旦收起就再也打不开。只藏 Deploy 和运行状态 */
[data-testid="stAppDeployButton"], [data-testid="stStatusWidget"],
[data-testid="stToolbarActions"], [data-testid="stDecoration"]{ display:none !important }
/* 表格/图表右上角那排悬浮小图标，提示语全是英文，且功能我们都有替代品 */
[data-testid="stElementToolbar"],
[data-testid="stElementToolbarButton"],
[data-testid="stHeadingWithActionElements"] a,
[data-testid="stHeadingWithActionElements"] button{ display:none !important }
/* 代码块自带「Copy to clipboard」复制键，提示语是英文且改不了；
   功能上「下载脚本」已覆盖，这里直接藏掉，免得中文界面里蹦英文 */
[data-testid="stHeader"]{ background:transparent !important }
/* 这两个键其实是两个完全不同的控件：
     · 展开键 stExpandSidebarButton 在顶栏（侧边栏收起时才出现）
     · 收起键 stSidebarCollapseButton 在侧边栏内部（默认只在鼠标移到侧边栏时才浮现）
   所以「展开后回原处再点一下没反应」不是 bug，是那个位置本来就没有按钮。
   下面把收起键做成常显的小胶囊，位置、形状都明确。 */
[data-testid="stHeaderActionElements"]{ visibility:visible !important; opacity:1 !important }

[data-testid="stSidebarCollapseButton"]{
  opacity:1 !important; visibility:visible !important;
}
/* 不再给这个按钮加内边距/位移/投影：这些会让可点区域和视觉框错位，
   点上去像"点不动"。保持原生尺寸，只让它常显。 */
/* 页签下面那条彩色下划线（1.67 的 tab-highlight）在这儿很跳，去掉 */
[data-baseweb="tab-list"] > div[class*="highlight"],
[data-baseweb="tab-list"] [data-testid*="highlight"]{ display:none !important }

/* 全量强制字体。Streamlit 给很多元素单独设了 font-family，
   不用 !important 盖不住；图标和代码块必须排除，否则变方块 */
.stApp, .stApp *, [data-testid="stSidebar"] *{
  /* 只留一个中文字族：霞鹜文楷缺失的字形往系统楷体退，
     不要退到黑体（Noto Sans SC），否则同一个页面会出现两种性格的字 */
  font-family:'LXGW WenKai','KaiTi','STKaiti','Noto Serif SC',
              'Segoe UI Emoji','Apple Color Emoji','Noto Color Emoji',serif !important;
  /* 允许浏览器合成粗体：霞鹜文楷这一支没有独立粗体字重，
     关掉合成的话整页只能是一个细度，压不住标题。
     坠底字体已从 Noto Sans SC 换成 KaiTi，合成出来仍是楷形，不会突然变黑体。 */
  font-synthesis:weight !important;
}

/* 正文提一档 —— 手帐风要厚一点才压得住纸面。
   注意只对「正文段落」加粗；11~13px 的辅助小字不加，
   因为浏览器合成粗体在这个尺寸上会让笔画边缘起毛（锯齿）。 */
[data-testid="stMarkdownContainer"] p,
.stApp li, .stApp td, .stApp th{
  font-weight:500 !important;
  font-size:17px !important;     /* 整数 px，避免 15.3px 这类值把字形 hinting 搞坏 */
  line-height:1.85 !important;
}

/* 辅助小字：只放大，不加粗 */
/* 辅助文字：字号只比正文小一档（16px），颜色也压深。
   之前用 15px + 浅灰，读起来像"可以忽略的备注"，反而增加阅读负担。 */
[data-testid="stCaptionContainer"] p,
[data-testid="stWidgetLabel"] p,
[data-testid="stMetricLabel"] p{
  font-weight:500 !important;
  font-size:16px !important;
  line-height:1.7 !important;
  letter-spacing:.2px;
  color:#5F5B69 !important;
}

/* 标题：不用加粗，用字号 + 轻微描边撑起份量，保持同一种笔触 */
h1, h2, h3, h4, h5, h6{
  font-weight:700 !important;
}

/* 行内强调：加粗 + 一道淡荧光笔，手帐里就是这么划重点的 */
.stApp strong, .stApp b{
  font-weight:700 !important;
  background:linear-gradient(transparent 62%, rgba(242,212,146,.55) 62%);
  padding:0 1px;
}
[data-testid="stIconMaterial"], .material-symbols-rounded,
span[class*="material-symbols"], [class*="stIcon"], [data-testid="stExpanderToggleIcon"]{
  font-family:'Material Symbols Rounded' !important;
}
code, pre, kbd, samp, [data-testid="stCode"] *{
  font-family:ui-monospace, 'Cascadia Mono', Consolas, monospace !important;
}

/* 窄容器里 Streamlit 会把多列竖着堆叠 —— 账本行的删除叉就是因为这个
   跑到按钮下面去了。这里强制保持横排 */
[class*="st-key-userrow_"] [data-testid="stHorizontalBlock"]{
  flex-wrap:nowrap !important; gap:4px !important; align-items:center !important;
}
[class*="st-key-userrow_"] [data-testid="column"]{
  min-width:0 !important; width:auto !important;
}
[class*="st-key-userrow_"] [data-testid="column"]:first-child{ flex:1 1 auto !important }
[class*="st-key-userrow_"] [data-testid="column"]:last-child{ flex:0 0 32px !important }
[class*="st-key-userrow_"] [data-testid="stButton"],
[class*="st-key-userrow_"] .stButton,
[class*="st-key-userrow_"] .stButton > button{ width:100% !important }

/* ---------- 标题 ---------- */
h1, h2, h3, h4{
  font-family:'LXGW WenKai',serif !important;
  font-weight:700 !important;
  letter-spacing:.5px;
  color:var(--ink);
}
h1{ font-size:44px !important; letter-spacing:2px; line-height:1.28 }
/* 标题的笔记本图标记号：放正文里会跟着 44px 一起变得巨大，
   改用伪元素单独缩小，视觉上像一个标签而不是一个字 */
h1::before{
  content:"📔";
  font-size:.58em;
  margin-right:.22em;
  vertical-align:.08em;
}
h1::after{
  content:"";display:block;width:104px;height:11px;margin-top:4px;
  background:var(--sun);opacity:.55;border-radius:6px;
}
h2{ font-size:27px !important; letter-spacing:1px }
h3{ font-size:23px !important }

/* ---------- 侧边栏 ---------- */
[data-testid="stSidebar"]{
  background:var(--paper-3);
  border-right:2px solid var(--ink);
}
[data-testid="stSidebar"] *{ color:var(--ink) }
/* 侧边栏「能读这三种账单」的小图标行 */
.side-ch{
  display:flex; align-items:center; gap:8px;
  padding:3px 0; font-size:15px;
}
.side-ch img{ width:16px; height:16px; display:block; opacity:.9 }
.side-ch .mark{ font-size:15px; opacity:.5; width:16px; text-align:center }

/* ---------- 指标卡 ---------- */
[data-testid="stMetric"]{
  background:var(--paper-2);
  border:2px solid var(--ink);
  border-radius:var(--r-lg);
  padding:14px 18px;
  box-shadow:var(--shadow);
  transition:transform .28s cubic-bezier(.22,.61,.36,1), box-shadow .28s;
}
[data-testid="stMetric"]:hover{
  transform:translateY(-3px) rotate(-.3deg);
  box-shadow:7px 9px 0 rgba(58,55,51,.16);
}
[data-testid="stMetricLabel"] p{
  color:var(--ink-soft) !important;font-size:13px !important;letter-spacing:.5px;
  font-weight:500 !important;
}
[data-testid="stMetricValue"]{
  font-family:'LXGW WenKai','KaiTi',serif !important;
  font-weight:700;color:var(--ink);
  font-size:28px !important;      /* 默认字号会把 ¥6,290.00 截成 ¥6,29… */
  line-height:1.25 !important;
}
[data-testid="stMetricValue"] *{
  overflow:visible !important;
  text-overflow:clip !important;
  white-space:nowrap;
}

/* ---------- 按钮 ---------- */
.stButton > button, .stDownloadButton > button, .stLinkButton > a{
  font-family:inherit !important;
  border:2px solid var(--ink) !important;
  border-radius:var(--r-md) !important;
  background:var(--paper-2) !important;
  color:var(--ink) !important;
  box-shadow:3px 3px 0 rgba(58,55,51,.14);
  transition:transform .2s cubic-bezier(.22,.61,.36,1), box-shadow .2s, background .2s;
  font-weight:500;
  font-size:16px;
}
.stButton > button:hover, .stDownloadButton > button:hover, .stLinkButton > a:hover{
  transform:translateY(-2px) rotate(-.4deg);
  box-shadow:5px 5px 0 rgba(58,55,51,.18);
  background:#FFF8E8 !important;
}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"]{
  background:var(--matcha) !important;
  color:#FFFDF7 !important;
}
.stButton > button[kind="primary"]:hover{
  background:#6E8B60 !important;
}
/* 当前账本按钮是 primary + disabled，默认会灰成一片，这里给它一点存在感 */
.stButton > button[kind="primary"]:disabled,
.stButton > button:disabled{
  background:#EFE6D2 !important;
  color:var(--ink) !important;
  border-color:var(--ink) !important;
  opacity:1 !important;
  box-shadow:none;
  cursor:default;
}

/* ---------- 页签 ---------- */
[data-testid="stTabs"] [role="tablist"]{ gap:8px !important; border-bottom:none !important }
[data-testid="stTab"]{
  border:2px solid transparent !important;
  border-radius:14px 16px 12px 15px !important;
  padding:9px 22px !important;
  font-size:17px !important;
  background:transparent !important;
  color:var(--ink-soft) !important;
  transition:all .25s cubic-bezier(.22,.61,.36,1);
}
[data-testid="stTab"]:hover{
  background:rgba(242,212,146,.30) !important;
  color:var(--ink) !important;
}
[data-testid="stTab"][aria-selected="true"]{
  background:var(--paper-2) !important;
  border-color:var(--ink) !important;
  color:var(--ink) !important;
  box-shadow:3px 3px 0 rgba(58,55,51,.14);
}
/* 原生那条绿色选中指示条，和描边胶囊重复 */
.react-aria-SelectionIndicator{ display:none !important }

/* ---------- 输入类 ---------- */
[data-testid="stTextInputRootElement"],
[data-testid="stSelectbox"] [role="group"],
[data-testid="stNumberInput"] [data-testid="stNumberInputContainer"],
[data-testid="stDateInput"] [data-testid="stDateInputField"]{
  font-family:inherit !important;
  background:var(--paper-2) !important;
  border:1.5px solid rgba(58,55,51,.55) !important;
  border-radius:12px !important;
  color:var(--ink) !important;
}
/* 内层控件不要再画一遍框，否则会套娃、看起来「框比字大」 */
[data-testid="stTextInput"] input,
[data-testid="stSelectbox"] input,
[data-testid="stDateInput"] input,
[data-testid="stNumberInput"] input{
  border:none !important;
  background:transparent !important;
  box-shadow:none !important;
  color:var(--ink) !important;
}
[data-testid="stTextInputRootElement"]:focus-within,
[data-testid="stSelectbox"] [role="group"]:focus-within,
[data-testid="stNumberInput"] [data-testid="stNumberInputContainer"]:focus-within,
[data-testid="stDateInput"] [data-testid="stDateInputField"]:focus-within{
  border-color:var(--matcha) !important;
  box-shadow:0 0 0 3px rgba(124,154,109,.18) !important;
}
/* 可点标签（渠道 / 分类筛选）：做成手帐里的小色标 */
[data-testid="stPills"] button{
  border:1.5px solid rgba(59,58,69,.26) !important;
  border-radius:10px 12px 9px 11px !important;
  background:var(--paper-2) !important;
  color:#5F5B69 !important;
  font-size:13.5px !important;
  padding:1px 9px !important;
  min-height:26px !important;
  box-shadow:none !important;
  transition:all .18s ease;
}
/* 标签之间排紧一点，十个分类别占掉五行 */
[data-testid="stPills"] [role="group"]{ gap:5px !important }
[data-testid="stPills"] div[data-testid="stWidgetLabel"]{ margin-bottom:2px !important }
[data-testid="stPills"] button:hover{
  background:#FFF8E8 !important;
  transform:translateY(-1px);
}
[data-testid="stPills"] button[aria-checked="true"],
[data-testid="stPills"] button[aria-pressed="true"],
[data-testid="stPills"] button[data-selected="true"]{
  background:var(--matcha) !important;
  border-color:var(--ink) !important;
  color:#FDFBF6 !important;
  box-shadow:2px 2px 0 rgba(59,58,69,.16) !important;
}

[data-testid="stFileUploaderDropzone"]{
  background:var(--paper-2) !important;
  border:2px dashed rgba(58,55,51,.45) !important;
  border-radius:var(--r-md) !important;
}
[data-testid="stFileUploaderDropzone"]:hover{ background:#FFF8E8 !important }
/* 内置文案是英文（Drag and drop / Browse files / Upload / Limit 200MB），
   组件不暴露 i18n，只能把原文藏掉、用伪元素写中文。
   按钮里是「图标 + 一个 markdown 文本块」，只藏文本块，图标留着。 */
[data-testid="stFileUploaderDropzoneInstructions"]{
  display:flex !important; flex-direction:column !important;
  align-items:flex-start !important; gap:2px !important;
}
[data-testid="stFileUploaderDropzoneInstructions"] > *{ display:none !important }
[data-testid="stFileUploaderDropzoneInstructions"]::before{
  content:"把账单文件拖到这里，或者点右边的按钮挑一个";
  font-size:13.5px; color:var(--ink-soft); line-height:1.6;
}
[data-testid="stFileUploaderDropzoneInstructions"]::after{
  content:"支持 CSV / Excel，单份不超过 200MB";
  font-size:12px; color:rgba(138,131,120,.9); line-height:1.6;
}
[data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"]{
  display:none !important;
}
[data-testid="stFileUploaderDropzone"] button::after{
  content:"选择文件"; font-size:14px; margin-left:2px; color:var(--ink);
}
/* 已选文件那一行的英文（Upload / Remove / 文件大小） */
[data-testid="stFileUploaderFile"] [data-testid="stMarkdownContainer"]{
  display:none !important;
}
[data-testid="stFileUploaderFile"] small{ font-size:0 !important }
[data-testid="stFileUploaderFile"] small::after{ content:"已选择"; font-size:12px }

/* ---------- 容器类 ---------- */
[data-testid="stDataFrame"]{
  border:2px solid var(--ink) !important;
  border-radius:18px 16px 20px 17px !important;
  overflow:hidden;
  box-shadow:4px 4px 0 rgba(58,55,51,.10);
}
[data-testid="stExpander"] details{
  border:2px solid var(--ink) !important;
  border-radius:var(--r-md) !important;
  background:var(--paper-2) !important;
  box-shadow:3px 3px 0 rgba(58,55,51,.09);
  /* 关键：不裁的话，展开后内部表头的底色会盖住上面两个圆角
     （鼠标移开就看得到方角，移上去又好了，就是这层在作怪） */
  overflow:hidden !important;
}
[data-testid="stExpander"] summary{
  font-weight:700;
  border-radius:inherit;      /* 表头也跟着圆，避免自己画一个方角底 */
  background:transparent !important;
}
[data-testid="stExpander"] summary:hover{ background:rgba(230,210,162,.22) !important }
[data-testid="stExpander"] [data-testid="stExpanderDetails"]{
  background:transparent !important;
  border-radius:inherit !important;
}
[data-testid="stAlert"],
[data-testid="stAlertContainer"]{
  border-radius:var(--r-md) !important;
  border:1.5px solid rgba(58,55,51,.38) !important;
  background:var(--paper-2) !important;
  overflow:hidden !important;     /* 不裁的话背景是方角，圆角边框只是贴在外面 */
}
[data-testid="stAlert"] > div{ border-radius:inherit !important }
/* ---------- 手帐表格（ui_table.render_ledger） ---------- */
.ledger-wrap{
  border:2px solid var(--ink);
  border-radius:var(--r-lg);
  overflow:hidden;
  box-shadow:var(--shadow);
  background:var(--paper-2);
  margin:6px 8px 14px 0;   /* 与 [data-testid="stPlotlyChart"] 一致，否则并排时顶边不齐 */
}
table.ledger{
  width:100%; border-collapse:collapse; font-size:16px;
  table-layout:fixed;          /* 固定布局，列宽按 colgroup 走，不然长文本会把短列挤成竖排 */
}
table.ledger th{
  background:#F1EDE3; color:#5F5B69; font-weight:500; text-align:left;
  padding:9px 10px; border-bottom:2px solid var(--ink);
  font-size:15px; letter-spacing:.6px; white-space:nowrap;
}
table.ledger td{
  padding:9px 10px; border-bottom:1px dashed rgba(120,118,130,.32);
  vertical-align:middle; color:var(--ink);
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
}
/* 列宽按「列名」而不是位置 —— 明细表是 7 列、未分类表是 4 列、商户榜是 3 列，
   用 nth-child 会让宽度错位（对方拿到最宽、金额反而挤没了）。 */
table.ledger .c-时间{ width:124px }
table.ledger .c-渠道{ width:104px }   /* 要放下图标 + 「校园卡」三个字 */
table.ledger .c-金额{ width:112px }
table.ledger .c-对方{ width:auto }        /* 商户名 / 商品名最长，把剩余空间全给它 */
table.ledger .c-分类{ width:106px }
table.ledger .c-性质{ width:100px }
table.ledger .c-商户{ width:auto }
table.ledger .c-笔数{ width:84px }
table.ledger .c-收支{ width:74px }

table.ledger tbody tr:last-child td{ border-bottom:none }
table.ledger tbody tr{ transition:background .15s ease }
table.ledger tbody tr:hover{ background:rgba(230,210,162,.26) }
table.ledger td.num{
  text-align:right; font-variant-numeric:tabular-nums;
  font-weight:500; white-space:nowrap;
}
table.ledger td.time{ color:#5F5B69; white-space:nowrap; font-size:14px; letter-spacing:.2px }
table.ledger td.who{ white-space:normal; line-height:1.45 }
table.ledger .ch{ display:inline-flex; align-items:center; gap:5px }
table.ledger .ch img{ width:15px; height:15px; display:block }
table.ledger .ch-mark{ font-size:14px; opacity:.55; line-height:1 }
table.ledger td.who .main{
  display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
}
table.ledger td.who .sub{
  display:block; font-size:13.5px; color:#7C7886;
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
}

.chip{
  display:inline-block; padding:1px 8px; border-radius:8px;
  font-size:14px; line-height:1.6; color:var(--ink);
  background:rgba(120,118,130,.16); white-space:nowrap;
}
.chip-warn{ background:rgba(214,166,162,.42) }

/* 输入框右下角那句 "Press Enter to apply" 是英文水印，我们已经有「搜索」按钮了 */
[data-testid="InputInstructions"], .st-emotion-cache-1p1m0v3{ display:none !important }

/* 「数据范围」这类信息行：比正文小一档，一行放得下 */
.meta-line{
  font-size:15px; line-height:1.95; color:var(--ink);
}
.meta-line b{ font-weight:700 }

/* 图表/表格下方的一行小注：说的话比 caption 具体，所以字稍大、颜色深一点 */
.hint{
  font-size:14.5px; line-height:1.75;
  color:var(--ink-soft);
  margin:-6px 0 14px 2px;
  padding-left:14px;
  position:relative;
}
.hint::before{
  content:"·";
  position:absolute; left:3px; top:-2px;
  font-size:18px; color:var(--matcha);
}

/* popover 面板（账本改名）：默认是个白框，跟纸感主题不搭，这里统一成卡片样式 */
[data-testid="stPopoverBody"]{
  background:var(--paper-2);
  border:2px solid var(--ink);
  border-radius:14px 16px 13px 15px;
  box-shadow:4px 5px 0 rgba(59,58,69,.12);
  padding:14px 16px 12px;
  animation:bb-fade .16s ease both;
}

/* ---------- 展开动画 ----------
   这两处浮层都是"点开时挂载、关掉时立刻卸载"，所以只能做"展开"这一下，
   关闭时的淡出做不到——Streamlit 直接把节点移除，没留时间。

   ⚠️ 关键：用独立的 translate / scale 属性，不要用 transform。
   浮层是靠行内 transform: translate(x, y) 定位的，而 CSS 动画的优先级高于行内样式，
   一旦动画里写 transform，定位就被覆盖 —— 下拉列表会跑到屏幕左上角（踩过）。
   translate / scale 是独立的属性，会和 transform 叠加，定位不受影响。 */

@keyframes bb-pop-in{
  from{ opacity:0; translate:0 -6px; scale:.98; }
  to  { opacity:1; translate:0 0;    scale:1; }
}

@keyframes bb-dd-in{
  from{ opacity:0; translate:0 -5px; }
  to  { opacity:1; translate:0 0; }
}

@keyframes bb-page-in{
  from{ opacity:0; translate:0 6px; }
  to  { opacity:1; translate:0 0; }
}

[data-testid="stPopoverBody"]{
  transform-origin:top left;
  animation:bb-pop-in .26s cubic-bezier(.22,.68,.36,1) both;
}

[data-testid="stSelectboxVirtualDropdown"]{
  transform-origin:top center;
  animation:bb-dd-in .26s cubic-bezier(.22,.68,.36,1) both;
}

/* 页签切换：Streamlit 只把当前页签挂进 DOM，切换等于重新挂载，
   所以这条 animation 每次切页都会重播一遍 */
[role="tabpanel"]{
  animation:bb-page-in .26s cubic-bezier(.22,.68,.36,1) both;
}

@media (prefers-reduced-motion: reduce){
  [data-testid="stPopoverBody"],
  [data-testid="stSelectboxVirtualDropdown"],
  [role="tabpanel"]{
    animation:none !important;
  }
}

/* 一次性提示（导入完成之类）：显示 5 秒后自动淡出收紧，不用手动关。
   只 pop session 状态不够——没人触发 rerun 的话，元素会一直留在页面上。 */
.st-key-flash_msg {
  overflow: hidden;
  animation: bb-flash-out .5s ease 5s both;
}

@keyframes bb-flash-out {
  from { opacity: 1; max-height: 160px; margin-bottom: 1rem; }
  to   { opacity: 0; max-height: 0;    margin-bottom: 0;    padding: 0; }
}

/* 「小记」卡片：图表和表格之外的一块批注，左侧一条苔绿色书签带 */
.note-card{
  position:relative;
  background:var(--paper-2);
  border:2px solid var(--ink);
  border-radius:16px 19px 15px 18px;
  box-shadow:4px 5px 0 rgba(59,58,69,.10);
  padding:18px 24px 16px 26px;
  margin:10px 0 18px;
}
.note-card::before{
  content:"";
  position:absolute; left:9px; top:16px; bottom:16px;
  width:4px; border-radius:2px;
  background:var(--matcha);
}
.note-title{
  font-size:17px; font-weight:700; letter-spacing:1px;
  margin:0 0 10px;
}
.note-lead{ font-size:16px; line-height:1.95; margin:0 0 6px; }
.note-list{ margin:0 0 6px; padding-left:1.15em; }
.note-list li{ font-size:15.5px; line-height:1.9; margin:3px 0; }
.note-tip{
  font-size:15px; line-height:1.9; color:var(--ink-soft);
  margin:8px 0 0;
}
.note-foot{
  font-size:12.5px; color:var(--ink-soft); opacity:.72;
  margin-top:12px; letter-spacing:.3px;
}
.note-card b{ font-weight:700; }

/* 页脚：一条细线加一句收尾的话，别让页面断得太生硬 */
.page-foot{
  text-align:center; color:var(--ink-soft);
  font-size:14px; letter-spacing:3px; opacity:.85;
  margin:40px 0 12px;
}
.page-foot::before, .page-foot::after{
  content:""; display:inline-block; width:34px; height:1px;
  background:rgba(120,118,130,.4);
  vertical-align:middle; margin:0 14px;
}

hr{ border-color:var(--line) !important }
[data-testid="stCaptionContainer"] p, .stCaption{ color:#5F5B69 !important }

/* 图表：不再做卡片装饰（无边框、无投影），只保留纸色底和圆角。

   为什么放弃装饰：Streamlit 给图表外层容器写死了高度，画布只要比它高一点点，
   就会冒出滚动条或被裁掉底部；而 border / padding 这些"占布局"的东西
   会进一步扩大这个差值。前面加边框、改阴影、调容器高度，绕了四五圈都没根治。
   现在的版本：容器高度自适应 + 图表自身不裁切 + 不做任何装饰 —— 图表完整、无滚动条。 */
[data-testid="stElementContainer"]:has([data-testid="stPlotlyChart"]){
  height:auto !important;
  max-height:none !important;
  overflow:visible !important;
}
[data-testid="stPlotlyChart"]{
  position:relative;
  background:var(--paper-2);
  border:none !important;
  border-radius:var(--r-lg);
  padding:0 !important;
  overflow:visible !important;
  box-shadow:none !important;
  margin:6px 0 14px 0;
}
/* 边框和投影画在伪元素上：绝对定位 + inset:0，完全不参与父元素尺寸计算，
   所以不会把画布挤出去（这招绕开了 border 占 4px 的老问题），
   而且 z-index 在图表之上，四条边一定都看得见。 */
[data-testid="stPlotlyChart"]::after{
  content:"";
  position:absolute;
  inset:0;
  border:2px solid var(--ink);
  border-radius:var(--r-lg);
  box-shadow:5px 6px 0 rgba(59,58,69,.12);
  pointer-events:none;
}
[data-testid="stPlotlyChart"] *{ scrollbar-width:none }
[data-testid="stPlotlyChart"] ::-webkit-scrollbar{
  width:0 !important; height:0 !important; display:none !important;
}
[data-testid="stPlotlyChart"] .modebar{ display:none !important }
"""


def apply_theme() -> None:
    """注入手帐风主题。必须在页面任何内容渲染之前调用。"""
    st.markdown(f"<style>{_FONT_CSS}{_THEME_CSS}</style>", unsafe_allow_html=True)
