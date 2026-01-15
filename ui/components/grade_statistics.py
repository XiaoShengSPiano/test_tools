"""
评级统计组件
用于显示匹配质量评级统计信息
"""
from dash import html
import dash_bootstrap_components as dbc
from utils.constants import GRADE_CONFIGS, GRADE_LEVELS


def create_grade_statistics_card(graded_stats, algorithm_name=None):
    """
    创建评级统计卡片
    
    Args:
        graded_stats: 评级统计数据
        algorithm_name: 算法名称（None表示单算法模式）
        
    Returns:
        dbc.Card: 评级统计卡片组件
    """
    # 使用现有的create_grade_statistics_rows函数
    from ui.layout_components import create_grade_statistics_rows
    
    rows = create_grade_statistics_rows(graded_stats, algorithm_name)
    
    return dbc.Card([
        dbc.CardHeader([
            html.H4([
                html.I(className="fas fa-chart-pie me-2", style={'color': '#6f42c1'}),
                "匹配质量评级统计"
            ], className="mb-0")
        ]),
        dbc.CardBody(rows)
    ], className="shadow-sm mb-4")


def create_grade_detail_table_placeholder(table_id='single'):
    """
    创建评级详情表格占位符（默认隐藏）
    
    Args:
        table_id: 表格ID标识
        
    Returns:
        html.Div: 表格占位符
    """
    from dash import dash_table
    
    return html.Div(
        id={'type': 'grade-detail-table', 'index': table_id},
        style={'display': 'none', 'marginTop': '20px'},
        children=[
            html.H5("详细数据", className="mb-3"),
            dash_table.DataTable(
                id={'type': 'grade-detail-datatable', 'index': table_id},
                columns=[],
                data=[],
                page_action='none',
                fixed_rows={'headers': True},
                style_table={
                    'maxHeight': '400px',
                    'overflowY': 'auto',
                    'overflowX': 'auto'
                },
                style_cell={
                    'textAlign': 'center',
                    'fontSize': '14px',
                    'fontFamily': 'Arial, sans-serif',
                    'padding': '8px',
                    'minWidth': '80px'
                },
                style_header={
                    'backgroundColor': '#f8f9fa',
                    'fontWeight': 'bold',
                    'borderBottom': '2px solid #dee2e6'
                }
            )
        ]
    )
