"""
评级统计组件
用于显示匹配质量评级统计信息
"""
from dash import html
import dash_bootstrap_components as dbc
from utils.constants import GRADE_CONFIGS, GRADE_LEVELS
from utils.logger import Logger

logger = Logger.get_logger()


def create_grade_statistics_rows(graded_stats, algorithm_name=None):
    """统一创建评级统计UI组件

    Args:
        graded_stats: 评级统计数据
        algorithm_name: 算法名称（None表示单算法模式）

    Returns:
        list: 包含评级统计UI组件的列表
    """
    rows = []

    # 计算总匹配对数（只统计成功匹配的评级）
    total_count = sum(graded_stats.get(level, {}).get('count', 0)
                     for level in GRADE_LEVELS)

    if total_count > 0:
        # 总体统计行
        total_label = "所有类型的匹配对" if algorithm_name is None else f"{algorithm_name} - 所有类型的匹配对"
        rows.append(
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.H3(f"{total_count}", className="text-info mb-1"),
                        html.P("总匹配对数", className="text-muted mb-0"),
                        html.Small(total_label, className="text-muted", style={'fontSize': '10px'})
                    ], className="text-center")
                ], width=12)
            ], className="mb-3")
        )

        # 评级统计按钮行
        grade_cols = []
        for grade_key, grade_name, color_class in GRADE_CONFIGS:
            grade_data = graded_stats.get(grade_key, {})
            count = grade_data.get('count', 0)
            percentage = grade_data.get('percent', 0.0)

            # 构建按钮ID
            button_index = grade_key if algorithm_name is None else f"{algorithm_name}_{grade_key}"

            grade_cols.append(
                dbc.Col([
                    html.Div([
                        dbc.Button(
                            f"{count}",
                            id={'type': 'grade-detail-btn', 'index': button_index},
                            color=color_class,
                            size='lg',
                            className="mb-1",
                            disabled=(count == 0),
                            style={'fontSize': '24px', 'fontWeight': 'bold', 'width': '100%'}
                        ),
                        html.P(f"{grade_name}", className="text-muted mb-0"),
                        html.Small(f"{percentage:.1f}%", className="text-muted", style={'fontSize': '10px'})
                    ], className="text-center")
                ], width='auto', className="px-2")
            )


        if grade_cols:
            rows.append(
                dbc.Row(grade_cols, className="mb-3 justify-content-center")
            )

    return rows


def create_grade_statistics_card(graded_stats, algorithm_name=None):
    """
    创建评级统计卡片
    
    Args:
        graded_stats: 评级统计数据
        algorithm_name: 算法名称（None表示单算法模式）
        
    Returns:
        dbc.Card: 评级统计卡片组件
    """
    rows = create_grade_statistics_rows(graded_stats, algorithm_name)
    card = dbc.Card([
        dbc.CardHeader([
            html.H4([
                html.I(className="fas fa-chart-pie me-2", style={'color': '#6f42c1'}),
                "匹配质量评级统计"
            ], className="mb-0")
        ]),
        dbc.CardBody(rows)
    ], className="shadow-sm mb-4")
    return card


def create_grade_detail_table_placeholder(table_id='single'):
    """
    创建评级详情表格占位符（默认隐藏）
    
    Args:
        table_id: 表格ID标识
        
    Returns:
        html.Div: 表格占位符
    """
    from dash import dash_table, dcc

    out = html.Div(
        id={'type': 'grade-detail-table', 'index': table_id},
        style={'display': 'none', 'marginTop': '20px'},
        children=[
            # 存储当前激活的评级类型，用于按键过滤联动
            dcc.Store(id={'type': 'grade-detail-state-store', 'index': table_id}, data={'grade_key': None}),
            
            html.H5("详细数据", className="mb-3"),
            
            # 按键筛选器区域
            html.Div(
                id={'type': 'grade-detail-key-filter-area', 'index': table_id},
                style={'marginBottom': '15px'},
                children=[
                    dbc.Row([
                        dbc.Col([
                            html.Label("按键筛选:", className="form-label fw-bold me-2"),
                            dcc.Dropdown(
                                id={'type': 'grade-detail-key-filter', 'index': table_id},
                                options=[
                                    {'label': '请选择按键...', 'value': ''},
                                    {'label': '全部按键', 'value': 'all'}
                                ],
                                value='',
                                clearable=False,
                                style={'width': '200px', 'display': 'inline-block'}
                            )
                        ], width='auto'),
                        dbc.Col([
                            html.Small(
                                "选择特定按键查看该类别的详细信息",
                                className="text-muted"
                            )
                        ], width=True)
                    ], className="align-items-center")
                ]
            ),
            
            dash_table.DataTable(
                id={'type': 'grade-detail-datatable', 'index': table_id},
                columns=[],
                data=[],
                page_action='native',  # 启用客户端分页
                page_current=0,
                page_size=50,  # 每页显示50条数据
                fixed_rows={'headers': True},
                style_table={
                    'maxHeight': '400px',
                    'overflowY': 'auto',
                    'overflowX': 'auto'
                },
                style_cell={
                    'textAlign': 'center',
                    'fontSize': '12px',
                    'fontFamily': 'Arial, sans-serif',
                    'padding': '6px 3px',
                    'minWidth': '85px',
                    'maxWidth': '130px',
                    'whiteSpace': 'normal',
                    'cursor': 'pointer'
                },
                style_header={
                    'backgroundColor': '#f8f9fa',
                    'fontWeight': 'bold',
                    'borderBottom': '2px solid #dee2e6',
                    'whiteSpace': 'normal',
                    'height': 'auto',
                    'lineHeight': '1.2',
                    'fontSize': '11px',
                    'padding': '6px 3px',
                    'textAlign': 'center'
                },
                style_data_conditional=[
                    # 为差异列设置更大的宽度
                    {
                        'if': {'column_id': 'keyon_diff'},
                        'minWidth': '140px',
                        'width': '160px'
                    },
                    {
                        'if': {'column_id': 'duration_diff'},
                        'minWidth': '140px',
                        'width': '160px'
                    },
                    {
                        'if': {'column_id': 'hammer_time_diff'},
                        'minWidth': '140px',
                        'width': '160px'
                    },
                    # 为其他包含(ms)的列设置中等宽度
                    {
                        'if': {'column_id': ['keyOn', 'keyOff', 'hammer_times', 'duration']},
                        'minWidth': '110px',
                        'width': '125px'
                    },
                    # 录制行 - 纯白色
                    {
                        'if': {'filter_query': '{data_type} = "录制"'},
                        'backgroundColor': '#FFFFFF',
                        'color': 'black'
                    },
                    {
                        'if': {'filter_query': '{row_type} = "录制"'},
                        'backgroundColor': '#FFFFFF',
                        'color': 'black'
                    },
                    # 播放行 - 淡蓝色
                    {
                        'if': {'filter_query': '{data_type} = "播放"'},
                        'backgroundColor': '#E6F7FF',
                        'color': 'black'
                    },
                    {
                        'if': {'filter_query': '{row_type} = "播放"'},
                        'backgroundColor': '#E6F7FF',
                        'color': 'black'
                    },
                    # 悬停样式
                    {
                        'if': {'state': 'active'},
                        'backgroundColor': 'rgba(0, 116, 217, 0.3)',
                        'border': '1px solid rgb(0, 116, 217)'
                    }
                ]
            )
        ]
    )
  
    return out


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

    card = dbc.Card([
        dbc.CardHeader([
            html.H4([
                html.I(className="fas fa-chart-line me-2", style={'color': '#17a2b8'}),
                f"延时误差统计指标{f' - {algorithm_name}' if algorithm_name else ''}"
            ], className="mb-0"),
            html.Small(f"基于 {sample_count} 个精确匹配对的统计结果", className="text-muted")
        ]),
        card_body
    ], className="shadow-sm mb-4")
   
    return card