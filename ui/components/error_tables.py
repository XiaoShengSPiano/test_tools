"""
错误统计表格组件
用于显示丢锤、多锤、无效音符等错误信息
"""
from dash import html, dash_table
import dash_bootstrap_components as dbc
from utils.logger import Logger

logger = Logger.get_logger()


def create_error_statistics_section(backend, active_algorithms):
    """
    创建错误统计区域
    
    Args:
        backend: 后端实例（PianoAnalysisBackend）
        active_algorithms: 活跃的算法列表（List[AlgorithmDataset]）
        
    Returns:
        list: 包含错误统计UI组件的列表（卡片+占位符）
    """
    sections = []
    
    # 为每个算法创建错误统计
    for algorithm in active_algorithms:
        if not algorithm.analyzer:
            continue

        algorithm_name = algorithm.metadata.algorithm_name
        
        # 通过backend获取错误统计（统一数据获取路径）
        error_stats = backend.get_algorithm_statistics(algorithm)  # 传入对象而非字符串
        if not error_stats or 'error' in error_stats:
            continue
        
        # 创建单个算法的错误统计卡片和占位符
        components = create_single_algorithm_error_card(
            algorithm_name,
            error_stats,
            algorithm
        )
        sections.extend(components)  # extend而非append，因为返回的是列表
    
    return sections


def create_single_algorithm_error_card(algorithm_name, error_stats, algorithm):
    """
    创建单个算法的错误统计卡片
    
    Args:
        algorithm_name: 算法名称
        error_stats: 错误统计数据
        algorithm: 算法对象
        
    Returns:
        list: [错误统计卡片, 无效音符详情表格占位符]
    """
    # 获取错误统计数据（使用清晰的字段名）
    drop_hammers = error_stats.get('drop_hammers', 0)
    multi_hammers = error_stats.get('multi_hammers', 0)
    record_invalid = error_stats.get('invalid_record_notes', 0)
    replay_invalid = error_stats.get('invalid_replay_notes', 0)
    
    card = dbc.Card([
        dbc.CardHeader([
            html.H4([
                html.I(className="fas fa-exclamation-triangle me-2", style={'color': '#dc3545'}),
                f"错误统计 - {algorithm_name}"
            ], className="mb-0")
        ]),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Div([
                        dbc.Button(
                            html.H3(str(drop_hammers), className="text-danger mb-0"),
                            id={'type': 'hammer-error-btn', 'index': f"{algorithm_name}_drop"},
                            color="link",
                            className="p-0",
                            style={'textDecoration': 'none', 'cursor': 'pointer'}
                        ),
                        html.P("丢锤数", className="text-muted mb-0 mt-1")
                    ], className="text-center")
                ], width=3),
                dbc.Col([
                    html.Div([
                        dbc.Button(
                            html.H3(str(multi_hammers), className="text-warning mb-0"),
                            id={'type': 'hammer-error-btn', 'index': f"{algorithm_name}_multi"},
                            color="link",
                            className="p-0",
                            style={'textDecoration': 'none', 'cursor': 'pointer'}
                        ),
                        html.P("多锤数", className="text-muted mb-0 mt-1")
                    ], className="text-center")
                ], width=3),
                dbc.Col([
                    html.Div([
                        dbc.Button(
                            html.H3(str(record_invalid), className="text-danger mb-0"),
                            id={'type': 'invalid-notes-btn', 'index': f"{algorithm_name}_record"},
                            color="link",
                            className="p-0",
                            style={'textDecoration': 'none', 'cursor': 'pointer'}
                        ),
                        html.P("录制无效音符", className="text-muted mb-0 mt-1")
                    ], className="text-center")
                ], width=3),
                dbc.Col([
                    html.Div([
                        dbc.Button(
                            html.H3(str(replay_invalid), className="text-danger mb-0"),
                            id={'type': 'invalid-notes-btn', 'index': f"{algorithm_name}_replay"},
                            color="link",
                            className="p-0",
                            style={'textDecoration': 'none', 'cursor': 'pointer'}
                        ),
                        html.P("播放无效音符", className="text-muted mb-0 mt-1")
                    ], className="text-center")
                ], width=3),
            ])
        ])
    ], className="shadow-sm mb-3")

    # 添加锤击错误详情表格占位符（默认隐藏）
    hammer_details_placeholder = html.Div([
        html.Div(
            id={'type': 'hammer-error-details', 'index': algorithm_name},
            style={'display': 'none'},
            className="mt-3"
        ),
        # 清除按钮（默认隐藏）
        html.Div(
            dbc.Button(
                [html.I(className="fas fa-times me-2"), "清除详情"],
                id={'type': 'hammer-error-clear-btn', 'index': algorithm_name},
                color="secondary",
                size="sm",
                className="mt-2"
            ),
            id={'type': 'hammer-error-clear-container', 'index': algorithm_name},
            style={'display': 'none', 'textAlign': 'center'}
        )
    ])

    # 添加无效音符详情表格占位符（默认隐藏）
    invalid_details_placeholder = html.Div([
        html.Div(
            id={'type': 'invalid-notes-details', 'index': algorithm_name},
            style={'display': 'none'},
            className="mt-3"
        ),
        # 清除按钮（默认隐藏）
        html.Div(
            dbc.Button(
                [html.I(className="fas fa-times me-2"), "清除详情"],
                id={'type': 'invalid-notes-clear-btn', 'index': algorithm_name},
                color="secondary",
                size="sm",
                className="mt-2"
            ),
            id={'type': 'invalid-notes-clear-container', 'index': algorithm_name},
            style={'display': 'none'}
        )
    ], className="mb-4")
    
    return [card, hammer_details_placeholder, invalid_details_placeholder]


def create_error_detail_tables(backend, algorithm_name):
    """
    创建错误详情表格（无效音符列表等）
    
    Args:
        backend: 后端实例
        algorithm_name: 算法名称
        
    Returns:
        html.Div: 包含多个错误详情表格的容器
    """
    try:
        # 获取无效音符表格数据
        invalid_notes_data = backend.get_invalid_notes_table_data(algorithm_name)
        
        # 获取无效音符详情数据（录制和播放）
        invalid_record_data = backend.get_invalid_notes_detail_table_data(
            algorithm_name, 'record'
        )
        invalid_replay_data = backend.get_invalid_notes_detail_table_data(
            algorithm_name, 'replay'
        )
        
        return html.Div([
            # 无效音符统计表
            _create_invalid_notes_table(invalid_notes_data, algorithm_name),
            
            # 无效音符详情表（录制）
            _create_invalid_detail_table(invalid_record_data, algorithm_name, 'record'),
            
            # 无效音符详情表（播放）
            _create_invalid_detail_table(invalid_replay_data, algorithm_name, 'replay'),
        ])
        
    except Exception as e:
        return html.Div([
            dbc.Alert(f"加载错误表格失败: {str(e)}", color="danger")
        ])


def _create_invalid_notes_table(data, algorithm_name):
    """创建无效音符统计表"""
    if not data:
        return html.Div()
    
    return dbc.Card([
        dbc.CardHeader([
            html.H5([
                html.I(className="fas fa-table me-2"),
                f"无效音符统计 - {algorithm_name}"
            ])
        ]),
        dbc.CardBody([
            dash_table.DataTable(
                data=data,
                columns=[
                    {"name": "无效原因", "id": "reason"},
                    {"name": "录制数据", "id": "record_count"},
                    {"name": "播放数据", "id": "replay_count"},
                ],
                style_table={'overflowX': 'auto'},
                style_cell={'textAlign': 'center', 'padding': '10px'},
                style_header={
                    'backgroundColor': '#f8f9fa',
                    'fontWeight': 'bold'
                }
            )
        ])
    ], className="shadow-sm mb-4")


def _create_hammer_error_detail_table(data, algorithm_name, error_type):
    """创建锤击错误详情表"""
    type_name = "丢锤错误" if error_type == 'drop' else "多锤错误"

    # 如果没有数据，显示提示信息
    if not data:
        return dbc.Card([
            dbc.CardHeader([
                html.H5([
                    html.I(className="fas fa-list me-2"),
                    f"{type_name}详细列表 - {algorithm_name}"
                ])
            ]),
            dbc.CardBody([
                html.Div([
                    html.I(className="fas fa-info-circle text-muted me-2"),
                    html.Span("暂无数据", className="text-muted")
                ], style={'textAlign': 'center', 'padding': '20px'})
            ])
        ], className="shadow-sm mb-4")

    # 生成唯一的表格ID
    table_id = {'type': 'error-detail-table', 'index': f"{algorithm_name}_{error_type}"}

    return dbc.Card([
        dbc.CardHeader([
            html.H5([
                html.I(className="fas fa-list me-2"),
                f"{type_name}详细列表 - {algorithm_name}",
                html.Small(" (点击行查看按键曲线)", className="text-muted ms-2", style={'fontSize': '0.8rem'})
            ])
        ]),
        dbc.CardBody([
            dash_table.DataTable(
                id=table_id,
                data=data,
                page_size=5,
                style_table={'overflowX': 'auto'},
                style_cell={
                    'textAlign': 'center',
                    'padding': '8px',
                    'cursor': 'pointer'
                },
                style_header={
                    'backgroundColor': '#f8f9fa',
                    'fontWeight': 'bold'
                },
                style_data_conditional=[
                    {
                        'if': {'state': 'active'},
                        'backgroundColor': 'rgba(0, 116, 217, 0.3)',
                        'border': '1px solid rgb(0, 116, 217)'
                    }
                ]
            )
        ])
    ], className="shadow-sm mb-4")


def _create_invalid_detail_table(data, algorithm_name, data_type):
    """创建无效音符详情表"""
    if not data:
        return html.Div()

    type_name = "录制数据" if data_type == 'record' else "播放数据"
    
    # 生成唯一的表格ID
    table_id = {'type': 'error-detail-table', 'index': f"{algorithm_name}_invalid_{data_type}"}

    return dbc.Card([
        dbc.CardHeader([
            html.H5([
                html.I(className="fas fa-list me-2"),
                f"无效音符详细列表 - {type_name} - {algorithm_name}",
                html.Small(" (点击行查看按键曲线)", className="text-muted ms-2", style={'fontSize': '0.8rem'})
            ])
        ]),
        dbc.CardBody([
            dash_table.DataTable(
                id=table_id,
                data=data,
                page_size=5,
                style_table={'overflowX': 'auto'},
                style_cell={
                    'textAlign': 'center',
                    'padding': '8px',
                    'cursor': 'pointer'
                },
                style_header={
                    'backgroundColor': '#f8f9fa',
                    'fontWeight': 'bold'
                },
                style_data_conditional=[
                    {
                        'if': {'state': 'active'},
                        'backgroundColor': 'rgba(0, 116, 217, 0.3)',
                        'border': '1px solid rgb(0, 116, 217)'
                    }
                ]
            )
        ])
    ], className="shadow-sm mb-4")
