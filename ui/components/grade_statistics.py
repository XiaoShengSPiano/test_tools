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


def create_delay_metrics_card(delay_metrics, algorithm_name=None):
    """
    创建延时误差统计指标卡片

    Args:
        delay_metrics: 延时误差统计指标数据
        algorithm_name: 算法名称（None表示单算法模式）

    Returns:
        dbc.Card: 延时误差统计指标卡片组件
    """
    if not delay_metrics or 'error' in delay_metrics:
        # 如果没有数据或有错误，返回简单的错误提示
        error_msg = delay_metrics.get('error', '暂无延时误差数据') if delay_metrics else '暂无延时误差数据'
        return dbc.Card([
            dbc.CardHeader([
                html.H4([
                    html.I(className="fas fa-chart-line me-2", style={'color': '#17a2b8'}),
                    "延时误差统计指标"
                ], className="mb-0")
            ]),
            dbc.CardBody([
                html.P(error_msg, className="text-muted")
            ])
        ], className="shadow-sm mb-4")

    # 样本数量
    sample_count = delay_metrics.get('sample_count', 0)

    # 创建指标行
    rows = []

    # 第一行：基本指标
    basic_metrics = dbc.Row([
        dbc.Col([
            html.Div([
                html.H3(f"{delay_metrics.get('mean_error', 0)/10:.2f}", className="text-primary mb-1"),
                html.P("平均延时(ms)", className="text-muted mb-0 small"),
            ], className="text-center p-2 border rounded")
        ], width=3),
        dbc.Col([
            html.Div([
                html.H3(f"{delay_metrics.get('std_deviation', 0)/10:.2f}", className="text-info mb-1"),
                html.P("标准差(ms)", className="text-muted mb-0 small"),
            ], className="text-center p-2 border rounded")
        ], width=3),
        dbc.Col([
            html.Div([
                html.H3(f"{delay_metrics.get('variance', 0)/100:.2f}", className="text-warning mb-1"),
                html.P("方差(ms²)", className="text-muted mb-0 small"),
            ], className="text-center p-2 border rounded")
        ], width=3),
        dbc.Col([
            html.Div([
                html.H3(f"{sample_count}", className="text-secondary mb-1"),
                html.P("样本数量", className="text-muted mb-0 small"),
            ], className="text-center p-2 border rounded")
        ], width=3),
    ], className="mb-3")

    # 第二行：误差指标
    error_metrics = dbc.Row([
        dbc.Col([
            html.Div([
                html.H3(f"{delay_metrics.get('mae', 0)/10:.2f}", className="text-success mb-1"),
                html.P("平均绝对误差(ms)", className="text-muted mb-0 small"),
            ], className="text-center p-2 border rounded")
        ], width=3),
        dbc.Col([
            html.Div([
                html.H3(f"{delay_metrics.get('rmse', 0)/10:.2f}", className="text-danger mb-1"),
                html.P("均方根误差(ms)", className="text-muted mb-0 small"),
            ], className="text-center p-2 border rounded")
        ], width=3),
        dbc.Col([
            html.Div([
                html.H3(f"{delay_metrics.get('cv', 0):.2f}%", className="text-dark mb-1"),
                html.P("变异系数(%)", className="text-muted mb-0 small"),
            ], className="text-center p-2 border rounded")
        ], width=3),
    ], className="mb-3")

    # 第三行：极值指标
    extreme_metrics = dbc.Row([
        dbc.Col([
            html.Div([
                html.H3(f"{delay_metrics.get('max_error', 0)/10:.2f}", className="text-warning mb-1"),
                html.P("最大偏差(ms)", className="text-muted mb-0 small"),
            ], className="text-center p-2 border rounded")
        ], width=4),
        dbc.Col([
            html.Div([
                html.H3(f"{delay_metrics.get('min_error', 0)/10:.2f}", className="text-info mb-1"),
                html.P("最小偏差(ms)", className="text-muted mb-0 small"),
            ], className="text-center p-2 border rounded")
        ], width=4),
        dbc.Col([
            html.Div([
                html.H3(f"{(delay_metrics.get('max_error', 0) - delay_metrics.get('min_error', 0))/10:.2f}", className="text-secondary mb-1"),
                html.P("偏差范围(ms)", className="text-muted mb-0 small"),
            ], className="text-center p-2 border rounded")
        ], width=4),
    ], className="mb-3")

    # 组合所有行
    card_body = dbc.CardBody([
        basic_metrics,
        error_metrics,
        extreme_metrics
    ])

    return dbc.Card([
        dbc.CardHeader([
            html.H4([
                html.I(className="fas fa-chart-line me-2", style={'color': '#17a2b8'}),
                f"延时误差统计指标{f' - {algorithm_name}' if algorithm_name else ''}"
            ], className="mb-0"),
            html.Small(f"基于 {sample_count} 个精确匹配对的统计结果", className="text-muted")
        ]),
        card_body
    ], className="shadow-sm mb-4")