# -*- coding: utf-8 -*-
"""图表主题：让 Plotly 长成手帐里该有的样子。

之前是逐张图 update_traces 改颜色，结果笛卡尔坐标轴、字体、网格、
悬浮框仍然是 Plotly 默认的「科技蓝白」，跟纸面完全不搭。
这里注册一个全局 template，所有图表默认继承，新加图也不用再管。

用法：
    from ui_charts import apply_chart_theme, PALETTE
    apply_chart_theme()          # 启动时调一次
"""
from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

# 和界面主题共用的一套颜色
PALETTE = ["#9CB8A4", "#D6A6A2", "#8AA6BF", "#E6D2A2", "#A79BC0", "#B9CBB2", "#CBB8C6"]

INK = "#3B3A45"
SOFT = "#6C6875"
PAPER = "#FDFBF6"
GRID = "rgba(120,118,130,.20)"
FONT = "LXGW WenKai, Noto Sans SC, serif"

TEMPLATE_NAME = "handbook"


def _axis(title: str = "") -> dict:
    return dict(
        gridcolor=GRID,
        gridwidth=1,
        griddash="dot",
        zeroline=False,
        showline=False,
        ticks="",
        title=dict(text=title, font=dict(color=SOFT, size=13)),
        tickfont=dict(color=SOFT, size=13),
        automargin=True,
    )


def apply_chart_theme() -> None:
    """注册并设为默认模板。必须在画任何图之前调用。"""
    tpl = go.layout.Template()
    tpl.layout = go.Layout(
        font=dict(family=FONT, size=14, color=INK),
        # 画布全透明，让卡片的纸色透上来（否则白色方块会盖住圆角边框）
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=PALETTE,
        margin=dict(l=8, r=96, t=20, b=10),   # 右边留宽：plotly 画的 SVG 往往比容器宽，留足才不会被裁掉末位刻度
        xaxis=_axis(),
        yaxis=_axis(),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, x=0,
            bgcolor="rgba(0,0,0,0)", font=dict(color=SOFT, size=13),
        ),
        hoverlabel=dict(
            bgcolor=PAPER, bordercolor=INK,
            # 默认是居中：两行长短不一时看着像没对齐，统一改左对齐
            align="left",
            font=dict(family=FONT, size=14, color=INK),
        ),
        bargap=0.46,
        bargroupgap=0.16,
        barcornerradius=8,      # 圆角条形，直角太硬，不像手帐
    )
    pio.templates[TEMPLATE_NAME] = tpl
    pio.templates.default = TEMPLATE_NAME


def style_pie(fig, hole: float = 0.52):
    """环形图：切片之间留一道纸色缝隙，像手帐里贴的色纸。"""
    fig.update_traces(
        hole=hole,
        marker=dict(line=dict(color="#FDFBF6", width=3)),
        textfont=dict(family=FONT, size=12, color=INK),
        textinfo="percent",
        sort=False,
    )
    fig.update_layout(showlegend=True)
    return fig


def style_bar(fig, horizontal: bool = False):
    """条形图：去掉描边、圆一点、数值贴在条上。"""
    fig.update_traces(
        marker_line_width=0,
        textfont=dict(family=FONT, size=12, color="#FFFDF7"),
    )
    if horizontal:
        y_axis = _axis()
        y_axis.update(showgrid=False, tickfont=dict(color=INK, size=13))
        fig.update_layout(xaxis=_axis("金额（元）"), yaxis=y_axis)
    return fig
