"""
UI辅助函数模块
提供通用的UI组件生成函数
"""

import plotly.graph_objects as go
from plotly.graph_objs import Figure


def create_empty_figure(title: str) -> Figure:
    """
    创建空的Plotly figure对象
    
    Args:
        title: 标题文本
        
    Returns:
        go.Figure: 空图表，中央显示标题文本
    """
    fig = go.Figure()
    fig.add_annotation(
        text=title,
        xref="paper", yref="paper",
        x=0.5, y=0.5, 
        xanchor='center', yanchor='middle',
        showarrow=False, 
        font=dict(size=16, color="gray")
    )
    fig.update_layout(
        title=title,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        plot_bgcolor='white',
        paper_bgcolor='white',
        showlegend=False
    )
    return fig
