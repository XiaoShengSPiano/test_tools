"""
UI布局模块 - 定义Dash应用的界面布局
包含主界面、报告布局等UI组件
"""
import traceback
import dash_bootstrap_components as dbc
from dash import dcc, html, dash_table
import plotly.graph_objects as go

from utils.logger import Logger
from utils.constants import GRADE_DISPLAY_CONFIG, GRADE_LEVELS

logger = Logger.get_logger()


# 创建空白图形
empty_figure = go.Figure()
empty_figure.add_annotation(
    text="请上传数据文件并点击加载数据按钮",
    xref="paper", yref="paper",
    x=0.5, y=0.5, showarrow=False,
    font=dict(size=20, color='gray')
)

# 兼容性别名 - 使用统一的全局配置
GRADE_CONFIGS = GRADE_DISPLAY_CONFIG

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
    print(f"最终总匹配对数 total_count: {total_count}")

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

empty_figure.update_layout(
    title='钢琴数据分析工具 - 等待数据加载',
    xaxis_title='Time (ms)',
    yaxis_title='Key ID (1-88: keys, 89-90: pedals)',
    height=None,
    width=None,
    template='simple_white',
    autosize=True,
    margin=dict(l=60, r=60, t=100, b=60),
    showlegend=False,
    paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='rgba(0,0,0,0)',
    font=dict(size=12)
)


def create_multi_algorithm_upload_area():
    """创建多算法上传区域"""
    return html.Div([
        html.Label("多算法上传", style={
            'fontWeight': 'bold',
            'color': '#2c3e50',
            'marginBottom': '10px',
            'fontSize': '16px'
        }),
        dbc.Row([
            dbc.Col([
                dcc.Upload(
                    id='upload-multi-algorithm-data',
                    children=html.Div([
                        html.I(className="fas fa-upload",
                              style={'fontSize': '32px', 'color': '#28a745', 'marginBottom': '10px'}),
                        html.Br(),
                        html.Span('上传算法文件（支持多选）', style={'fontSize': '14px', 'color': '#6c757d'})
                    ], style={
                        'textAlign': 'center',
                        'padding': '20px',
                        'border': '2px dashed #28a745',
                        'borderRadius': '8px',
                        'backgroundColor': '#f8f9fa',
                        'cursor': 'pointer'
                    }),
                    multiple=True
                )
            ], width=10),
            dbc.Col([
                dbc.Button(
                    "🔄 重置",
                    id='reset-multi-algorithm-upload',
                    color='secondary',
                    size='sm',
                    n_clicks=0,
                    style={'height': '100%', 'width': '100%'},
                    title='如果重复上传同一文件没有反应，请点击此按钮重置上传区域'
                )
            ], width=2)
        ]),
        html.Div(id='multi-algorithm-upload-status', style={'marginTop': '10px', 'fontSize': '12px'}),
        # 文件列表区域（上传后显示）
        html.Div(id='multi-algorithm-file-list', style={'marginTop': '15px'})
    ])


def create_multi_algorithm_management_area():
    """创建多算法管理区域"""
    return html.Div([
        html.Label("📊 算法管理", style={
            'fontWeight': 'bold',
            'color': '#2c3e50',
            'marginBottom': '10px',
            'fontSize': '16px'
        }),
        # 现有数据迁移提示区域（默认隐藏，由回调动态更新）
        html.Div(id='existing-data-migration-area', style={'display': 'none'}, className='mb-3'),
        # 迁移相关的组件（始终存在，但默认隐藏，由回调控制显示）
        dbc.Input(
            id='existing-data-algorithm-name-input',
            type='text',
            placeholder='输入算法名称',
            style={'display': 'none', 'marginBottom': '10px'}
        ),
        dbc.Button(
            "确认迁移",
            id='confirm-migrate-existing-data-btn',
            color='primary',
            size='sm',
            n_clicks=0,
            style={'display': 'none'}
        ),
        html.Div(id='algorithm-list', children=[]),
        html.Div(id='algorithm-management-status', 
                style={'fontSize': '12px', 'color': '#6c757d', 'marginTop': '10px'})
    ])



def create_main_layout():
    """创建主界面布局"""
    return html.Div([
        # 隐藏的会话ID存储
        dcc.Store(id='session-id', storage_type='session'),
        # 存储多算法上传的文件内容（用于确认添加时获取）
        dcc.Store(id='multi-algorithm-files-store', data={'contents': [], 'filenames': []}),
        # 触发算法列表更新的 Store（当算法添加/删除时更新）
        dcc.Store(id='algorithm-list-trigger', data=0),
        # 触发算法管理更新的 Store（当算法添加成功时更新文件列表）
        dcc.Store(id='algorithm-management-trigger', data=0),
        # 存储当前点击的数据点信息，用于跳转到瀑布图
        dcc.Store(id='current-clicked-point-info', data=None),


        # 页面标题
        dbc.Container([
            dbc.Row([
                dbc.Col([
                    html.H1("🎹 钢琴数据分析工具",
                           className="text-center mb-4",
                           style={'color': '#2c3e50', 'fontWeight': 'bold'})
                ])
            ])
        ], fluid=True, className="mb-3"),

        # 上传容器 - 位于顶部
        dbc.Container([
            dbc.Card([
                dbc.CardBody([
                    dbc.Row([
                        # 左侧上传区域（多算法模式，默认显示）
                        dbc.Col([
                            html.Div(id='multi-algorithm-upload-area', children=create_multi_algorithm_upload_area())
                        ], width=5),

                        # 中间算法管理区域（多算法模式，默认显示）
                        dbc.Col([
                            html.Div(id='multi-algorithm-management-area', children=create_multi_algorithm_management_area())
                        ], width=3),

                        # 右侧历史记录和按钮区域
                        dbc.Col([
                            # 历史记录区域
                            html.Div([
                                html.Label("📚 历史记录", style={
                                    'fontWeight': 'bold',
                                    'color': '#2c3e50',
                                    'marginBottom': '10px',
                                    'fontSize': '16px'
                                }),
                                dcc.Input(
                                    id='history-search',
                                    type='text',
                                    placeholder='搜索历史记录...',
                                    style={
                                        'width': '100%',
                                        'padding': '8px 12px',
                                        'fontSize': '14px',
                                        'border': '1px solid #ced4da',
                                        'borderRadius': '5px',
                                        'marginBottom': '10px'
                                    }
                                ),
                                dcc.Dropdown(
                                    id='history-dropdown',
                                    options=[],
                                    placeholder="选择历史记录...",
                                    style={'marginBottom': '20px'},
                                    clearable=True,
                                    searchable=True
                                )
                            ]),


                            # 时间轴筛选组件
                            html.Div([
                                html.Label("⏰ 时间范围筛选", style={
                                    'fontWeight': 'bold',
                                    'color': '#2c3e50',
                                    'marginBottom': '10px',
                                    'fontSize': '16px'
                                }),
                                
                                # 新增：直接时间范围输入组件
                                html.Div([
                                    html.Label("直接设置时间范围 (100us):", style={'fontSize': '14px', 'marginBottom': '5px', 'fontWeight': 'bold'}),
                                    dbc.Row([
                                        dbc.Col([
                                            html.Label("开始时间:", style={'fontSize': '12px'}),
                                            dbc.Input(
                                                id='time-range-start-input',
                                                type='number',
                                                placeholder='开始时间',
                                                min=0,
                                                step=1,
                                                size='sm'
                                            )
                                        ], width=4),
                                        dbc.Col([
                                            html.Label("结束时间:", style={'fontSize': '12px'}),
                                            dbc.Input(
                                                id='time-range-end-input',
                                                type='number',
                                                placeholder='结束时间',
                                                min=0,
                                                step=1,
                                                size='sm'
                                            )
                                        ], width=4),
                                        dbc.Col([
                                            html.Label("操作:", style={'fontSize': '12px'}),
                                            html.Div([
                                                dbc.Button("确认更新", id='btn-confirm-time-range', 
                                                         color='success', size='sm',
                                                         className='btn btn-success btn-sm'),
                                                dbc.Button("重置", id='btn-reset-display-time-range', 
                                                         color='warning', size='sm',
                                                         className='btn btn-warning btn-sm',
                                                         style={'marginLeft': '5px'})
                                            ])
                                        ], width=4)
                                    ], className='mb-2'),
                                    html.Div(id='time-range-input-status', style={'fontSize': '12px', 'marginBottom': '10px'})
                                ], style={'backgroundColor': '#f8f9fa', 'padding': '10px', 'borderRadius': '5px', 'marginBottom': '15px'}),
                                
                                html.Div([
                                    html.Label("滑块时间范围 (100us):", style={'fontSize': '14px', 'marginBottom': '5px'}),
                                    dcc.RangeSlider(
                                        id='time-filter-slider',
                                        min=0, max=1000, step=10,
                                        value=[0, 1000],
                                        tooltip={"placement": "bottom", "always_visible": False},
                                        marks={i: str(i) for i in range(0, 1001, 500)},
                                        updatemode='mouseup'
                                    ),
                                    html.Div([
                                        dbc.Button("应用时间筛选", id='btn-apply-time-filter', 
                                                 color='info', size='sm', 
                                                 className='btn btn-outline-info btn-sm'),
                                        dbc.Button("重置时间范围", id='btn-reset-time-filter', 
                                                 color='secondary', size='sm', 
                                                 className='btn btn-outline-secondary btn-sm',
                                                 style={'marginLeft': '10px'})
                                    ], style={'marginBottom': '10px'}),
                                    html.Div(id='time-filter-status', 
                                            style={'fontSize': '12px', 'color': '#17a2b8', 'fontWeight': 'bold'})
                                ])
                            ], style={'marginBottom': '20px'}),

                            # 操作按钮组
                            html.Div([
                                html.Label("🔧 分析功能", style={
                                    'fontWeight': 'bold',
                                    'color': '#2c3e50',
                                    'marginBottom': '10px',
                                    'fontSize': '16px'
                                }),
                                # 自动生成瀑布图和报告，无需按钮
                                html.Div(style={'height': '10px'})
                            ])
                        ], width=6)
                    ])
                ])
            ])
        ], fluid=True, className="mb-4"),

        # 标签页容器
        dbc.Container([
            dcc.Tabs(id="main-tabs", value="waterfall-tab", children=[
                dcc.Tab(label="🌊 瀑布图分析", value="waterfall-tab", children=[
                    html.Div(id="waterfall-content", style={'padding': '20px', 'width': '100%'}, children=[
                        # 返回按钮 - 返回到报告界面
                        html.Div([
                            dbc.Button([
                                html.I(className="fas fa-arrow-left me-2"),
                                "返回报告界面"
                            ], id='btn-return-to-report', color='secondary', size='md', className='mb-3')
                        ], style={'marginBottom': '15px'}),
                        dcc.Graph(
                            id='main-plot', 
                            figure=empty_figure, 
                            style={"height": "1500px", "width": "100%"},  # 固定高度和宽度，避免Tab切换时大小变化
                            config={
                                'displayModeBar': True,
                                'displaylogo': False,
                                'modeBarButtonsToRemove': ['lasso2d', 'select2d'],  # 保留pan2d按钮，支持拖动
                                'scrollZoom': True,  # 启用鼠标滚轮缩放
                                'doubleClick': 'reset'  # 双击重置缩放
                            }
                        )
                    ]),
                    # 模态框 - 用于显示点击后的详细信息
                    html.Div([
                        html.Div([
                            # 模态框头部
                            html.Div([
                                html.H3("钢琴按键力度曲线详情", className="modal-title", style={
                                    'color': '#333',
                                    'fontWeight': 'bold',
                                    'margin': '0'
                                }),
                                html.Button(
                                    "×",
                                    id="close-modal-old",
                                    className="close",
                                    style={
                                        'float': 'right',
                                        'fontSize': '28px',
                                        'fontWeight': 'bold',
                                        'border': 'none',
                                        'background': 'none',
                                        'color': '#666',
                                        'cursor': 'pointer',
                                        'padding': '0',
                                        'width': '30px',
                                        'height': '30px',
                                        'lineHeight': '30px'
                                    }
                                )
                            ], className="modal-header", style={
                                'borderBottom': '1px solid #dee2e6',
                                'padding': '15px 20px',
                                'display': 'flex',
                                'justifyContent': 'space-between',
                                'alignItems': 'center'
                            }),

                            # 模态框主体 - 合并对比图表
                            html.Div([
                                html.Div([
                                    html.H4("合并对比力度曲线", style={
                                            'textAlign': 'center',
                                            'color': '#2c3e50',
                                            'marginBottom': '15px',
                                            'fontWeight': 'bold'
                                        }),
                                        dcc.Graph(
                                        id='detail-plot-combined-old',
                                        style={'height': '800px'},
                                            config={
                                                'displayModeBar': True,
                                                'displaylogo': False,
                                                'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d']
                                            }
                                        )
                                    ], style={
                                    'width': '100%',
                                        'padding': '10px'
                                })
                            ], id='modal-content-old', className="modal-body", style={
                                'padding': '20px',
                                'maxHeight': '90vh',
                                'overflowY': 'auto'
                                    }),

                            # 模态框底部
                                    html.Div([
                                html.Button(
                                    "关闭",
                                    id="close-modal-btn-old",
                                    className="btn btn-primary",
                                    style={
                                        'backgroundColor': '#007bff',
                                        'borderColor': '#007bff',
                                        'padding': '8px 20px',
                                        'borderRadius': '5px',
                                        'border': 'none',
                                        'color': 'white',
                                        'cursor': 'pointer'
                                    }
                                )
                            ], className="modal-footer", style={
                                'borderTop': '1px solid #dee2e6',
                                'padding': '15px 20px',
                                'textAlign': 'right'
                            })

                        ], className="modal-content", style={
                            'backgroundColor': 'white',
                            'margin': '1% auto',
                            'padding': '0',
                            'border': 'none',
                            'width': '95%',
                            'maxWidth': '1600px',
                            'borderRadius': '10px',
                            'boxShadow': '0 4px 20px rgba(0,0,0,0.3)',
                            'maxHeight': '98vh',
                            'overflow': 'hidden'
                        })

                    ], id="detail-modal-old", className="modal", style={
                        'display': 'none',
                        'position': 'fixed',
                        'zIndex': '1000',
                        'left': '0',
                        'top': '0',
                        'width': '100%',
                        'height': '100%',
                        'backgroundColor': 'rgba(0,0,0,0.6)',
                        'backdropFilter': 'blur(5px)'
                    }),

                ]),
                dcc.Tab(label="📊 异常检测报告", value="report-tab", children=[
                    html.Div(id="report-content", style={'padding': '20px'})
                ])
            ])
        ], fluid=True),
        # 关键：这些组件必须在主布局的顶层直接存在，用于支持回调
        # Dash 在注册回调时会检查 Input 组件是否存在，即使设置了 suppress_callback_exceptions=True
        # 重要：这些组件必须直接放在主布局的顶层，不能放在任何容器中，否则 Dash 可能无法识别
        # 这些组件会被 report-content 中的同名组件覆盖（当 report-content 有内容时）
        # 但当 report-content 为空时，这些隐藏版本会确保回调函数不会报错
        dcc.Graph(id='key-delay-scatter-plot', figure={}, style={'display': 'none'}),
        dcc.Graph(id='key-delay-zscore-scatter-plot', figure={}, style={'display': 'none'}),
        dcc.Graph(id='hammer-velocity-delay-scatter-plot', figure={}, style={'display': 'none'}),
        dcc.Graph(id='key-force-interaction-plot', figure={}, style={'display': 'none'}),
        dcc.Store(id='key-force-interaction-selected-keys', data=[]),  # 存储选中的按键列表
        dcc.Graph(id='relative-delay-distribution-plot', figure={}, style={'display': 'none'}),
        html.Div(id='offset-alignment-plot', style={'display': 'none'}),
        dcc.Graph(id='delay-time-series-plot', figure={}, style={'display': 'none'}),
        dcc.Graph(id='delay-histogram-plot', figure={}, style={'display': 'none'}),
        html.Div([
            dash_table.DataTable(
                id='offset-alignment-table',
                data=[],
                columns=[]
            )
        ], style={'display': 'none'}),
        # 相对延时分布图相关组件
        html.Div([
            html.Div(id='relative-delay-distribution-subplot-title', style={'display': 'none'}),
            html.Div(id='relative-delay-distribution-selection-info', style={'display': 'none'}),
            dash_table.DataTable(
                id='relative-delay-distribution-detail-table',
                data=[],
                columns=[
                    {"name": "算法名称", "id": "algorithm_name"},
                    {"name": "按键ID", "id": "key_id"},
                    {"name": "相对延时(ms)", "id": "relative_delay_ms", "type": "numeric", "format": {"specifier": ".2f"}},
                    {"name": "绝对延时(ms)", "id": "absolute_delay_ms", "type": "numeric", "format": {"specifier": ".2f"}},
                    {"name": "录制索引", "id": "record_index"},
                    {"name": "播放索引", "id": "replay_index"},
                    {"name": "录制开始(0.1ms)", "id": "record_keyon"},
                    {"name": "播放开始(0.1ms)", "id": "replay_keyon"},
                    {"name": "持续时间差(0.1ms)", "id": "duration_offset"},
                ],
                page_action='none',
                style_cell={
                    'textAlign': 'center',
                    'fontSize': '12px',
                    'fontFamily': 'Arial, sans-serif',
                    'padding': '8px',
                    'overflow': 'hidden',
                    'textOverflow': 'ellipsis',
                },
                style_header={
                    'backgroundColor': '#f8f9fa',
                    'fontWeight': 'bold',
                    'border': '1px solid #dee2e6',
                    'position': 'sticky',
                    'top': 0,
                    'zIndex': 1
                },
                style_data={
                    'whiteSpace': 'normal',
                    'height': 'auto',
                },
                style_table={
                    'overflowX': 'auto',
                    'overflowY': 'auto',
                    'maxHeight': '600px',
                }
            )
        ], style={'display': 'none'}, id='relative-delay-distribution-table-container'),
        # 存储跳转来源图表ID，用于返回时滚动定位
        dcc.Store(id='jump-source-plot-id', data=None),
        # 滚动触发Store，用于客户端回调
        dcc.Store(id='scroll-to-plot-trigger', data=None),
        # 相对延时分布图滚动触发Store
        dcc.Store(id='relative-delay-distribution-scroll-trigger', data=None),
        # 评级统计区域滚动触发Store
        dcc.Store(id='grade-detail-section-scroll-trigger', data=None),
        # 评级统计表格返回滚动触发Store
        dcc.Store(id='grade-detail-return-scroll-trigger', data=None),
        # 将模态框移到主布局顶层，确保在所有Tab中都能显示
        html.Div([
            html.Div([
                html.Div([
                    html.Div([
                        html.H4("详细分析", style={'margin': '0', 'padding': '15px 20px', 'borderBottom': '1px solid #dee2e6'}),
                        html.Button("×", id="close-modal", className="close", style={
                            'position': 'absolute',
                            'right': '15px',
                            'top': '15px',
                            'fontSize': '28px',
                            'fontWeight': 'bold',
                            'background': 'none',
                            'border': 'none',
                            'cursor': 'pointer',
                            'color': '#aaa'
                        })
                    ], style={'position': 'relative', 'borderBottom': '1px solid #dee2e6'}),
                    html.Div([
                        html.Div([
                                    dcc.Graph(
                                        id='detail-plot-combined',
                                style={'height': '800px'},
                                        config={
                                            'displayModeBar': True,
                                            'displaylogo': False,
                                            'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d']
                                        }
                                    )
                                ], style={
                                    'width': '100%',
                                    'padding': '10px'
                                })
                            ], id='modal-content', className="modal-body", style={
                                'padding': '20px',
                                'maxHeight': '90vh',
                                'overflowY': 'auto'
                            }),
                            html.Div([
                                html.Button(
                                    "关闭",
                                    id="close-modal-btn",
                                    className="btn btn-primary",
                                    style={
                                        'backgroundColor': '#007bff',
                                        'borderColor': '#007bff',
                                        'padding': '8px 20px',
                                        'borderRadius': '5px',
                                        'border': 'none',
                                        'color': 'white',
                                        'cursor': 'pointer'
                                    }
                                )
                            ], className="modal-footer", style={
                                'borderTop': '1px solid #dee2e6',
                                'padding': '15px 20px',
                                'textAlign': 'right'
                            })
                        ], className="modal-content", style={
                            'backgroundColor': 'white',
                            'margin': '1% auto',
                            'padding': '0',
                            'border': 'none',
                            'width': '95%',
                            'maxWidth': '1600px',
                            'borderRadius': '10px',
                            'boxShadow': '0 4px 20px rgba(0,0,0,0.3)',
                            'maxHeight': '98vh',
                            'overflow': 'hidden'
                        })
                    ], id="detail-modal", className="modal", style={
                        'display': 'none',
                        'position': 'fixed',
                'zIndex': '9999',
                        'left': '0',
                        'top': '0',
                        'width': '100%',
                        'height': '100%',
                        'backgroundColor': 'rgba(0,0,0,0.6)',
                        'backdropFilter': 'blur(5px)'
            }),

            # 评级统计曲线对比模态框（悬浮窗）
            html.Div([
                html.Div([
                    html.Div([
                        html.Div([
                            html.H4("评级统计曲线对比", style={'margin': '0', 'padding': '10px 20px', 'borderBottom': '1px solid #dee2e6'}),
                            html.Button("×", id="close-grade-detail-curves-modal", className="close", style={
                                'position': 'absolute',
                                'right': '15px',
                                'top': '15px',
                                'fontSize': '28px',
                                'fontWeight': 'bold',
                                'background': 'none',
                                'border': 'none',
                                'cursor': 'pointer',
                                'color': '#aaa'
                            })
                        ], style={'position': 'relative', 'borderBottom': '1px solid #dee2e6'}),
                        html.Div([
                            html.Div(id='grade-detail-curves-comparison-container', children=[])
                        ], id='grade-detail-curves-modal-content', className="modal-body", style={
                            'padding': '10px 20px 20px 20px',
                            'maxHeight': '90vh',
                            'overflowY': 'auto'
                        })
                    ], className="modal-content", style={
                        'position': 'relative',
                        'backgroundColor': '#fff',
                        'margin': '5% auto',
                        'padding': '0',
                        'border': '1px solid #888',
                        'width': '90%',
                        'maxWidth': '1200px',
                        'borderRadius': '8px',
                        'boxShadow': '0 4px 6px rgba(0,0,0,0.1)'
                    })
                ], className="modal-dialog", style={
                    'margin': '5% auto',
                    'maxWidth': '1200px'
                })
            ], id="grade-detail-curves-modal", className="modal", style={
                'display': 'none',
                'position': 'fixed',
                'zIndex': '9999',
                'left': '0',
                'top': '0',
                'width': '100%',
                'height': '100%',
                'backgroundColor': 'rgba(0,0,0,0.6)',
                'backdropFilter': 'blur(5px)'
            }),

            # 按键曲线对比模态框（悬浮窗）
            html.Div([
                html.Div([
                    html.Div([
                        html.Div([
                            html.H4("按键曲线对比", style={'margin': '0', 'padding': '10px 20px', 'borderBottom': '1px solid #dee2e6'}),  # 减少顶部padding：从15px改为10px
                            html.Button("×", id="close-key-curves-modal", className="close", style={
                                'position': 'absolute',
                                'right': '15px',
                                'top': '15px',
                                'fontSize': '28px',
                                'fontWeight': 'bold',
                                'background': 'none',
                                'border': 'none',
                                'cursor': 'pointer',
                                'color': '#aaa'
                            })
                        ], style={'position': 'relative', 'borderBottom': '1px solid #dee2e6'}),
                        html.Div([
                            dcc.Tabs(id="key-curves-comparison-tabs", value="curves-tab", children=[
                                dcc.Tab(label="📈 曲线对比", value="curves-tab", children=[
                                    html.Div(id='key-curves-comparison-container', children=[])
                                ]),
                                dcc.Tab(label="🔍 相似度分析", value="similarity-tab", children=[
                                    create_similarity_analysis_ui()
                                ])
                            ])
                        ], id='key-curves-modal-content', className="modal-body", style={
                            'padding': '10px 20px 20px 20px',  # 减少顶部padding：从20px改为10px
                            'maxHeight': '90vh',
                            'overflowY': 'auto'
                        }),
                        html.Div([
                            html.Button(
                                "跳转到瀑布图",
                                id="jump-to-waterfall-btn",
                                className="btn btn-success",
                                style={
                                    'backgroundColor': '#28a745',
                                    'borderColor': '#28a745',
                                    'padding': '8px 20px',
                                    'borderRadius': '5px',
                                    'border': 'none',
                                    'color': 'white',
                                    'cursor': 'pointer',
                                    'marginRight': '10px'
                                }
                            ),
                            html.Button(
                                "关闭",
                                id="close-key-curves-modal-btn",
                                className="btn btn-primary",
                                style={
                                    'backgroundColor': '#007bff',
                                    'borderColor': '#007bff',
                                    'padding': '8px 20px',
                                    'borderRadius': '5px',
                                    'border': 'none',
                                    'color': 'white',
                                    'cursor': 'pointer'
                                }
                            )
                        ], className="modal-footer", style={
                            'borderTop': '1px solid #dee2e6',
                            'padding': '15px 20px',
                            'textAlign': 'right'
                        })
                    ], className="modal-content", style={
                        'backgroundColor': 'white',
                        'margin': '0.5% auto',  # 减少顶部margin：从1%改为0.5%
                        'padding': '0',
                        'border': 'none',
                        'width': '95%',
                        'maxWidth': '1600px',
                        'borderRadius': '10px',
                        'boxShadow': '0 4px 20px rgba(0,0,0,0.3)',
                        'maxHeight': '98vh',
                        'overflow': 'hidden'
                    })
                ], id="key-curves-modal", className="modal", style={
                    'display': 'none',
                    'position': 'fixed',
                    'zIndex': '9999',
                    'left': '0',
                    'top': '0',
                    'width': '100%',
                    'height': '100%',
                    'backgroundColor': 'rgba(0,0,0,0.6)',
                    'backdropFilter': 'blur(5px)'
                })
            ]),
            # 瀑布图专用曲线对比模态框（避免与其他功能冲突）
            html.Div([
                html.Div([
                    html.Div([
                        html.Div([
                            html.H4("按键曲线对比 (瀑布图)", style={'margin': '0', 'padding': '10px 20px', 'borderBottom': '1px solid #dee2e6'}),
                            html.Button("×", id="close-waterfall-curves-modal", className="close", style={
                                'position': 'absolute',
                                'right': '15px',
                                'top': '15px',
                                'fontSize': '28px',
                                'fontWeight': 'bold',
                                'background': 'none',
                                'border': 'none',
                                'cursor': 'pointer',
                                'color': '#aaa'
                            })
                        ], style={'position': 'relative', 'borderBottom': '1px solid #dee2e6'}),
                        html.Div([
                            html.Div(id='waterfall-curves-comparison-container', children=[])
                        ], id='waterfall-curves-modal-content', className="modal-body", style={
                            'padding': '10px 20px 20px 20px',
                            'maxHeight': '90vh',
                            'overflowY': 'auto'
                        }),
                        html.Div([
                            html.Button(
                                "跳转到瀑布图",
                                id="jump-to-waterfall-btn-from-modal",
                                className="btn btn-success",
                                style={
                                    'backgroundColor': '#28a745',
                                    'borderColor': '#28a745',
                                    'padding': '8px 20px',
                                    'borderRadius': '5px',
                                    'border': 'none',
                                    'color': 'white',
                                    'cursor': 'pointer',
                                    'marginRight': '10px'
                                }
                            ),
                            html.Button(
                                "关闭",
                                id="close-waterfall-curves-modal-btn",
                                className="btn btn-primary",
                                style={
                                    'backgroundColor': '#007bff',
                                    'borderColor': '#007bff',
                                    'padding': '8px 20px',
                                    'borderRadius': '5px',
                                    'border': 'none',
                                    'color': 'white',
                                    'cursor': 'pointer'
                                }
                            )
                        ], className="modal-footer", style={
                            'borderTop': '1px solid #dee2e6',
                            'padding': '15px 20px',
                            'textAlign': 'right'
                        })
                    ], className="modal-content", style={
                        'backgroundColor': 'white',
                        'margin': '0.5% auto',
                        'padding': '0',
                        'border': 'none',
                        'width': '95%',
                        'maxWidth': '1600px',
                        'borderRadius': '10px',
                        'boxShadow': '0 4px 20px rgba(0,0,0,0.3)',
                        'maxHeight': '98vh',
                        'overflow': 'hidden'
                    })
                ], id="waterfall-curves-modal", className="modal", style={
                    'display': 'none',
                    'position': 'fixed',
                    'zIndex': '9999',
                    'left': '0',
                    'top': '0',
                    'width': '100%',
                    'height': '100%',
                    'backgroundColor': 'rgba(0,0,0,0.6)',
                    'backdropFilter': 'blur(5px)'
                })
            ])
        ])

    ], style={
        'fontFamily': 'Arial, sans-serif',
        'backgroundColor': '#f8f9fa',
        'minHeight': '100vh'
    })


def _create_single_algorithm_overview_row(algorithm, algorithm_name, backend=None):
    """为单个算法创建数据概览行（不包含卡片，只返回行内容）"""

    try:
        # 获取完整统计信息：使用统一的后端统计服务
        if not backend or not hasattr(backend, 'get_algorithm_statistics'):
            raise ValueError("后端对象或get_algorithm_statistics方法不可用")

        # 获取错误统计信息
        stats = backend.get_algorithm_statistics(algorithm)
        drop_count = stats['drop_count']
        multi_count = stats['multi_count']

        # 生成数据概览行（带算法名称标识）
        overview_row = html.Div([
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.Small(f"算法: {algorithm_name}", className="text-muted", style={'fontSize': '12px', 'fontWeight': 'bold', 'display': 'block', 'marginBottom': '8px'})
                    ])
                ], width=12)
            ], className="mb-2"),
                            dbc.Row([
                                dbc.Col([
                                    html.Div([
                        html.H3(f"{drop_count}", className="text-warning mb-1"),
                                        html.P("丢锤数", className="text-muted mb-0"),
                                        html.Small("录制有但播放没有", className="text-muted", style={'fontSize': '10px'})
                                    ], className="text-center")
                                ], width=4),
                                dbc.Col([
                                    html.Div([
                        html.H3(f"{multi_count}", className="text-info mb-1"),
                                        html.P("多锤数", className="text-muted mb-0"),
                                        html.Small("播放有但录制没有", className="text-muted", style={'fontSize': '10px'})
                                    ], className="text-center")
                                ], width=4)
            ], className="mb-3")
        ], className="mb-3", style={'borderBottom': '1px solid #dee2e6', 'paddingBottom': '15px'})
        
        return overview_row

    except Exception as e:
        # 检查是否是后端不可用的严重错误
        if isinstance(e, ValueError) and "后端对象或get_algorithm_statistics方法不可用" in str(e):
            # 后端不可用，直接重新抛出
            raise
        else:
            # 其他异常（包括后端计算失败、数据处理错误等），记录日志但不抛出，保持向后兼容
            logger.error(f"❌ 获取算法 '{algorithm_name}' 的数据概览失败: {e}")
            logger.error(traceback.format_exc())
            return None


def _create_single_algorithm_error_stats_row(algorithm, algorithm_name):
    """为单个算法创建延时误差统计指标行（不包含卡片，只返回行内容）"""
    try:
        # 获取算法的统计数据
        if not algorithm.analyzer:
            return None
        
        # 计算延时误差统计指标（只使用精确匹配数据）
        mae_0_1ms = algorithm.analyzer.get_mean_absolute_error() if hasattr(algorithm.analyzer, 'get_mean_absolute_error') else 0.0
        variance_0_1ms_squared = algorithm.analyzer.get_variance() if hasattr(algorithm.analyzer, 'get_variance') else 0.0
        std_0_1ms = algorithm.analyzer.get_standard_deviation() if hasattr(algorithm.analyzer, 'get_standard_deviation') else 0.0
        me_0_1ms = algorithm.analyzer.get_mean_error() if hasattr(algorithm.analyzer, 'get_mean_error') else 0.0
        rmse_0_1ms = algorithm.analyzer.get_root_mean_squared_error() if hasattr(algorithm.analyzer, 'get_root_mean_squared_error') else 0.0
        cv = algorithm.analyzer.get_coefficient_of_variation() if hasattr(algorithm.analyzer, 'get_coefficient_of_variation') else 0.0

        # 记录平均误差用于调试
        logger.debug(f"📊 [{algorithm_name}] 平均误差ME: {me_0_1ms/10:.2f}ms")
        
        variance_ms_squared = variance_0_1ms_squared / 100.0
        std_ms = std_0_1ms / 10.0
        mae_ms = mae_0_1ms / 10.0
        me_ms = me_0_1ms / 10.0
        rmse_ms = rmse_0_1ms / 10.0
        
        # 计算按键延时的最大值和最小值（从正常匹配按键的keyon_offset）
        max_delay_ms = None
        min_delay_ms = None
        max_delay_item = None  # 保存最大延迟对应的完整数据项
        min_delay_item = None  # 保存最小延迟对应的完整数据项
        if hasattr(algorithm.analyzer, 'note_matcher') and algorithm.analyzer.note_matcher:
            try:
                # 只使用精确匹配对的数据（误差 ≤ 50ms），与统计指标保持一致
                offset_data = algorithm.analyzer.note_matcher.get_precision_offset_alignment_data()
                if offset_data:
                    # 提取所有校准后的偏移（单位：0.1ms，带符号，去除全局系统延时）
                    corrected_offsets = [item.get('corrected_offset', 0) for item in offset_data]
                    if corrected_offsets:
                        # 转换为ms单位
                        corrected_offsets_ms = [offset / 10.0 for offset in corrected_offsets]
                        max_delay_ms = max(corrected_offsets_ms)
                        min_delay_ms = min(corrected_offsets_ms)

                        # 找到对应的数据项
                        for item in offset_data:
                            item_delay_ms = item.get('corrected_offset', 0) / 10.0
                            if max_delay_item is None or item_delay_ms == max_delay_ms:
                                max_delay_item = item
                            if min_delay_item is None or item_delay_ms == min_delay_ms:
                                min_delay_item = item

                        # 添加日志输出
                        logger.info(f"📊 [{algorithm_name}] 延时范围统计 (精确匹配数据):")
                        logger.info(f"   最大延时: {max_delay_ms:.2f}ms (基于{len(corrected_offsets)}个精确匹配对)")
                        logger.info(f"   最小延时: {min_delay_ms:.2f}ms")
            except Exception as e:
                logger.warning(f"⚠️ 计算按键延时最大值/最小值失败: {e}")
        
        # 生成延时误差统计指标行（带算法名称标识）
        error_stats_row = html.Div([
                            dbc.Row([
                                dbc.Col([
                                    html.Div([
                        html.Small(f"算法: {algorithm_name}", className="text-muted", style={'fontSize': '12px', 'fontWeight': 'bold', 'display': 'block', 'marginBottom': '8px'})
                    ])
                ], width=12)
            ], className="mb-2"),
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.H3(f"{me_ms:.2f} ms", className="text-secondary mb-1"),
                        html.P("平均延时", className="text-muted mb-0"),
                        html.Small("所有已匹配按键对的keyon_offset的算术平均（带符号）", className="text-muted", style={'fontSize': '10px'})
                    ], className="text-center")
                ], width=4),
                dbc.Col([
                    html.Div([
                        html.H3(f"{variance_ms_squared:.2f} ms²", className="text-danger mb-1"),
                        html.P("方差", className="text-muted mb-0"),
                        html.Small("所有已匹配按键对的keyon_offset的方差", className="text-muted", style={'fontSize': '10px'})
                    ], className="text-center")
                ], width=4),
                dbc.Col([
                    html.Div([
                        html.H3(f"{std_ms:.2f} ms", className="text-info mb-1"),
                        html.P("标准差", className="text-muted mb-0"),
                        html.Small("所有已匹配按键对的keyon_offset的标准差", className="text-muted", style={'fontSize': '10px'})
                    ], className="text-center")
                ], width=4)
            ], className="mb-3"),
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.H3(f"{mae_ms:.2f} ms", className="text-warning mb-1"),
                        html.P("平均绝对误差(MAE)", className="text-muted mb-0"),
                        html.Small("已匹配按键对的延时绝对值的平均", className="text-muted", style={'fontSize': '10px'})
                    ], className="text-center")
                ], width=4),
                dbc.Col([
                    html.Div([
                        html.H3(f"{rmse_ms:.2f} ms", className="text-success mb-1"),
                        html.P("均方根误差(RMSE)", className="text-muted mb-0"),
                        html.Small("对大偏差更敏感", className="text-muted", style={'fontSize': '10px'})
                    ], className="text-center")
                ], width=4),
                dbc.Col([
                    html.Div([
                        html.H3(f"{cv:.2f}%", className="text-primary mb-1"),
                        html.P("变异系数(CV)", className="text-muted mb-0"),
                        html.Small("标准差与均值的比值，反映相对变异程度", className="text-muted", style={'fontSize': '10px'})
                    ], className="text-center")
                ], width=4)
            ], className="mb-3"),
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.Div(
                            f"{max_delay_ms:.2f} ms" if max_delay_ms is not None else "N/A", 
                            className="text-danger mb-1",
                            id={"type": "max-delay-value", "algorithm": algorithm_name},
                            style={
                                'cursor': 'pointer', 
                                'userSelect': 'none',
                                'fontSize': '1.75rem',
                                'fontWeight': '500',
                                'lineHeight': '1.2'
                            },
                            title="点击查看对应按键的曲线对比图"
                        ),
                        html.P("最大偏差", className="text-muted mb-0"),
                        html.Small("已匹配按键中的最大延时（点击数值查看曲线）", className="text-muted", style={'fontSize': '10px'})
                    ], className="text-center")
                ], width=6),
                dbc.Col([
                    html.Div([
                        html.Div(
                            f"{min_delay_ms:.2f} ms" if min_delay_ms is not None else "N/A", 
                            className="text-info mb-1",
                            id={"type": "min-delay-value", "algorithm": algorithm_name},
                            style={
                                'cursor': 'pointer', 
                                'userSelect': 'none',
                                'fontSize': '1.75rem',
                                'fontWeight': '500',
                                'lineHeight': '1.2'
                            },
                            title="点击查看对应按键的曲线对比图"
                        ),
                        html.P("最小偏差", className="text-muted mb-0"),
                        html.Small("已匹配按键中的最小偏差（点击数值查看曲线）", className="text-muted", style={'fontSize': '10px'})
                    ], className="text-center")
                ], width=6)
            ])
        ], className="mb-3", style={'borderBottom': '1px solid #dee2e6', 'paddingBottom': '15px'})
        
        return error_stats_row
        
    except Exception as e:
        logger.error(f"❌ 获取算法 '{algorithm_name}' 的延时误差统计指标失败: {e}")
        logger.error(traceback.format_exc())
        return None


def _create_single_algorithm_error_tables(algorithm, algorithm_name):
    """
    为单个算法创建丢锤和多锤问题表格
    
    Args:
        algorithm: AlgorithmDataset实例
        algorithm_name: 算法名称
        
    Returns:
        Tuple[html.Div, html.Div]: (丢锤表格区域, 多锤表格区域)
    """
    try:
        if not algorithm.analyzer:
            return None, None
        
        # 获取错误数据（ErrorNote对象列表）
        drop_hammers = algorithm.analyzer.drop_hammers if hasattr(algorithm.analyzer, 'drop_hammers') else []
        multi_hammers = algorithm.analyzer.multi_hammers if hasattr(algorithm.analyzer, 'multi_hammers') else []
        
        # 获取匹配失败原因（用于更详细的分析）
        failure_reasons = {}
        if algorithm.analyzer and hasattr(algorithm.analyzer, 'note_matcher'):
            failure_reasons = getattr(algorithm.analyzer.note_matcher, 'failure_reasons', {})
        
        # 转换为表格数据格式
        drop_hammers_data = []
        for error_note in drop_hammers:
            # ErrorNote对象包含notes列表，每个元素是Note对象（保留完整数据）
            if len(error_note.notes) > 0:
                rec_note = error_note.notes[0]  # 获取第一个Note对象
                
                # 获取详细的匹配失败原因
                analysis_reason = '丢锤（录制有，播放无）'
                # Note对象没有index属性，使用global_index
                if ('record', error_note.global_index) in failure_reasons:
                    analysis_reason = failure_reasons[('record', error_note.global_index)]
                
                # Note对象的时间属性已经是ms，直接使用
                row = {
                    'data_type': 'record',
                    'keyId': rec_note.id,
                    'keyOn': f"{rec_note.key_on_ms:.2f}" if rec_note.key_on_ms is not None else 'N/A',
                    'keyOff': f"{rec_note.key_off_ms:.2f}" if rec_note.key_off_ms is not None else 'N/A',
                    'index': error_note.global_index,
                    'analysis_reason': analysis_reason
                }
                drop_hammers_data.append(row)
                
                # 播放行显示"无匹配"
                drop_hammers_data.append({
                    'data_type': 'play',
                    'keyId': '无匹配',
                    'keyOn': '无匹配',
                    'keyOff': '无匹配',
                    'index': '无匹配',
                    'analysis_reason': ''
                })
        
        multi_hammers_data = []
        for error_note in multi_hammers:
            # ErrorNote对象包含notes列表，每个元素是Note对象（保留完整数据）
            if len(error_note.notes) > 0:
                play_note = error_note.notes[0]  # 获取第一个Note对象
                
                # 多锤的分析原因
                analysis_reason = '多锤（播放有，录制无）'
                
                # 录制行显示"无匹配"
                multi_hammers_data.append({
                    'data_type': 'record',
                    'keyId': '无匹配',
                    'keyOn': '无匹配',
                    'keyOff': '无匹配',
                    'index': '无匹配',
                    'analysis_reason': ''
                })
                
                # 播放行显示实际数据
                # Note对象的时间属性已经是ms，直接使用
                row = {
                    'data_type': 'play',
                    'keyId': play_note.id,
                    'keyOn': f"{play_note.key_on_ms:.2f}" if play_note.key_on_ms is not None else 'N/A',
                    'keyOff': f"{play_note.key_off_ms:.2f}" if play_note.key_off_ms is not None else 'N/A',
                    'index': error_note.global_index,
                    'analysis_reason': analysis_reason
                }
                multi_hammers_data.append(row)
        
        # 创建丢锤表格
        drop_hammers_table = html.Div([
            dbc.Row([
                dbc.Col([
                    html.H6(f"丢锤问题列表 - {algorithm_name}", className="mb-2",
                           style={'color': '#721c24', 'fontWeight': 'bold', 'fontSize': '16px', 'borderBottom': '2px solid #721c24', 'paddingBottom': '5px'}),
                ], width=12)
            ]),
            dash_table.DataTable(
                id={'type': 'drop-hammers-table', 'index': algorithm_name},
                columns=[
                    {"name": "数据类型", "id": "data_type"},
                    {"name": "键位ID", "id": "keyId"},
                    {"name": "按下时间(ms)", "id": "keyOn"},
                    {"name": "释放时间(ms)", "id": "keyOff"},
                    {"name": "index", "id": "index"},
                    {"name": "未匹配原因", "id": "analysis_reason"},
                ],
                data=drop_hammers_data,
                page_action='none',
                style_cell={
                    'textAlign': 'center',
                    'fontSize': '13px',
                    'fontFamily': 'Arial, sans-serif',
                    'padding': '8px',
                    'overflow': 'hidden',
                    'textOverflow': 'ellipsis',
                    'minWidth': '70px',
                },
                style_cell_conditional=[
                    {'if': {'column_id': 'data_type'}, 'width': '14%'},
                    {'if': {'column_id': 'keyId'}, 'width': '12%'},
                    {'if': {'column_id': 'keyOn'}, 'width': '16%'},
                    {'if': {'column_id': 'keyOff'}, 'width': '16%'},
                    {'if': {'column_id': 'index'}, 'width': '10%'},
                    {'if': {'column_id': 'analysis_reason'}, 'width': '32%'},
                ],
                style_header={
                    'backgroundColor': '#f8d7da',
                    'fontWeight': 'bold',
                    'border': '2px solid #dee2e6',
                    'fontSize': '14px',
                    'color': '#721c24',
                    'textAlign': 'center',
                    'padding': '10px',
                    'whiteSpace': 'normal',
                    'height': 'auto',
                    'position': 'sticky',
                    'top': 0,
                    'zIndex': 1
                },
                style_data={
                    'border': '1px solid #dee2e6',
                    'fontSize': '13px',
                    'padding': '8px'
                },
                style_data_conditional=[
                    {
                        'if': {'filter_query': '{data_type} = record'},
                        'fontWeight': 'bold',
                        'backgroundColor': '#ffeaea'
                    },
                    {
                        'if': {'row_index': 'odd'},
                        'backgroundColor': '#fafafa'
                    }
                ],
                row_selectable=False,
                sort_action="native",
                filter_action="none",
                style_table={
                    'height': '300px',
                    'overflowY': 'auto',
                    'overflowX': 'auto',
                    'border': '2px solid #dee2e6',
                    'borderRadius': '8px',
                    'minHeight': '150px'
                }
            ),
        ], style={'backgroundColor': '#ffffff', 'padding': '15px', 'borderRadius': '8px', 'boxShadow': '0 2px 6px rgba(0,0,0,0.1)', 'marginBottom': '15px'})
        
        # 创建多锤表格
        multi_hammers_table = html.Div([
                            dbc.Row([
                                dbc.Col([
                    html.H6(f"多锤问题列表 - {algorithm_name}", className="mb-2",
                           style={'color': '#856404', 'fontWeight': 'bold', 'fontSize': '16px', 'borderBottom': '2px solid #856404', 'paddingBottom': '5px'}),
                ], width=12)
            ]),
            dash_table.DataTable(
                id={'type': 'multi-hammers-table', 'index': algorithm_name},
                columns=[
                    {"name": "数据类型", "id": "data_type"},
                    {"name": "键位ID", "id": "keyId"},
                    {"name": "按下时间(ms)", "id": "keyOn"},
                    {"name": "释放时间(ms)", "id": "keyOff"},
                    {"name": "index", "id": "index"},
                    {"name": "未匹配原因", "id": "analysis_reason"},
                ],
                data=multi_hammers_data,
                page_action='none',
                style_cell={
                    'textAlign': 'center',
                    'fontSize': '13px',
                    'fontFamily': 'Arial, sans-serif',
                    'padding': '8px',
                    'overflow': 'hidden',
                    'textOverflow': 'ellipsis',
                    'minWidth': '70px',
                },
                style_cell_conditional=[
                    {'if': {'column_id': 'data_type'}, 'width': '14%'},
                    {'if': {'column_id': 'keyId'}, 'width': '12%'},
                    {'if': {'column_id': 'keyOn'}, 'width': '16%'},
                    {'if': {'column_id': 'keyOff'}, 'width': '16%'},
                    {'if': {'column_id': 'index'}, 'width': '10%'},
                    {'if': {'column_id': 'analysis_reason'}, 'width': '32%'},
                ],
                style_header={
                    'backgroundColor': '#fff3cd',
                    'fontWeight': 'bold',
                    'border': '2px solid #dee2e6',
                    'fontSize': '14px',
                    'color': '#856404',
                    'textAlign': 'center',
                    'padding': '10px',
                    'whiteSpace': 'normal',
                    'height': 'auto',
                    'position': 'sticky',
                    'top': 0,
                    'zIndex': 1
                },
                style_data={
                    'border': '1px solid #dee2e6',
                    'fontSize': '13px',
                    'padding': '8px'
                },
                style_data_conditional=[
                    {
                        'if': {'filter_query': '{data_type} = play'},
                        'backgroundColor': '#fffef5'
                    },
                    {
                        'if': {'row_index': 'odd'},
                        'backgroundColor': '#fafafa'
                    }
                ],
                row_selectable=False,
                sort_action="native",
                filter_action="none",
                style_table={
                    'height': '300px',
                    'overflowY': 'auto',
                    'overflowX': 'auto',
                    'border': '2px solid #dee2e6',
                    'borderRadius': '8px',
                    'minHeight': '150px'
                }
            ),
        ], style={'backgroundColor': '#ffffff', 'padding': '15px', 'borderRadius': '8px', 'boxShadow': '0 2px 6px rgba(0,0,0,0.1)', 'marginBottom': '15px'})
        
        return drop_hammers_table, multi_hammers_table
        
    except Exception as e:
        logger.error(f"创建算法 {algorithm_name} 错误表格失败: {e}")
        logger.error(traceback.format_exc())
        return None, None


def _create_error_tables_row_for_algorithm(algorithm):
    """
    为单个算法创建一行错误表格（丢锤和多锤左右并排）
    
    Args:
        algorithm: AlgorithmDataset实例
        
    Returns:
        dbc.Row: 包含丢锤和多锤表格的行
    """
    algorithm_name = algorithm.metadata.algorithm_name
    drop_table, multi_table = _create_single_algorithm_error_tables(algorithm, algorithm_name)
    
    if drop_table and multi_table:
        return dbc.Row([
            dbc.Col([drop_table], width=6, className="pr-2"),
            dbc.Col([multi_table], width=6, className="pl-2"),
        ], className="mb-3")
    else:
        # 如果没有数据，返回空行
        return dbc.Row([
                dbc.Col([
                    html.Div([
                    html.P(f"算法 {algorithm_name} 暂无错误数据", className="text-center text-muted", style={'padding': '20px'})
                ], style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px'})
            ], width=12)
        ], className="mb-3")


def _hex_to_rgba(hex_color, alpha=0.3):
    """将十六进制颜色转换为RGBA格式，用于表格背景色
    
    Args:
        hex_color: 十六进制颜色值（如 '#1f77b4'）
        alpha: 透明度（0-1），默认0.3，确保颜色足够明显
    
    Returns:
        RGBA格式的颜色字符串（如 'rgba(31, 119, 180, 0.3)'）
    """
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f'rgba({r}, {g}, {b}, {alpha})'

def create_report_layout(backend):
    """创建完整的报告分析布局（仅支持多算法模式）"""
    # 多算法模式：为每个算法生成一行数据概览和一行延时误差统计指标
    active_algorithms = backend.get_active_algorithms()
    
    # 获取算法颜色映射（用于表格行背景色）
    algorithm_colors = {}
    for algorithm in active_algorithms:
        if hasattr(algorithm, 'color'):
            algorithm_colors[algorithm.metadata.algorithm_name] = algorithm.color
    
    # 用于收集所有行内容
    all_rows = []

    # 检查是否有数据可以显示（单算法或多算法）
    has_data = bool(active_algorithms) or (backend._get_current_analyzer() is not None)

    # 获取数据源信息（在所有模式下都需要）
    source_info = backend.get_data_source_info() if hasattr(backend, 'get_data_source_info') else {}

    # 处理单算法模式
    if not active_algorithms and backend._get_current_analyzer() is not None:
        # 单算法模式：显示评级统计
        graded_rows = []  # 初始化变量
        if backend and hasattr(backend, 'get_graded_error_stats'):
            try:
                graded_stats = backend.get_graded_error_stats()
                if graded_stats and 'error' not in graded_stats:
                    # 构建评级统计内容

                    # 使用统一函数创建评级统计UI
                    graded_rows.extend(create_grade_statistics_rows(graded_stats, algorithm_name=None))

            except Exception as e:
                logger.warning(f"创建单算法评级统计卡片失败: {e}")
                graded_rows = []

        # 单算法模式：直接返回包含评级统计的布局
        data_source = source_info.get('filename') or "单算法分析"

        # 构建单算法模式的完整布局
        layout_rows = []

        # 添加评级统计卡片（总是创建，即使没有数据）
        if True:  # 总是创建评级统计卡片
            layout_rows.append(
                dbc.Row([
                    dbc.Col([
                        dbc.Card([
                            dbc.CardHeader([
                                html.H4([
                                    html.I(className="fas fa-chart-pie", style={'marginRight': '10px', 'color': '#6f42c1'}),
                                    "匹配质量评级统计"
                                ], className="mb-0")
                            ]),
                            dbc.CardBody([
                                *graded_rows,
                                # 详细表格区域（默认隐藏）- 为每个评级创建单独的表格
                                # 注意：这里需要动态创建，但为了简化，我们只创建一个通用表格
                                # 在单算法模式下，所有按钮共享同一个表格
                                html.Div(
                                    id={'type': 'grade-detail-table', 'index': 'single'},
                                    style={'display': 'none', 'marginTop': '20px'},
                                    children=[
                                        html.H5("详细数据", className="mb-3"),
                                        dash_table.DataTable(
                                            id={'type': 'grade-detail-datatable', 'index': 'single'},
                                            columns=[],
                                            data=[],
                                            page_action='none',
                                            fixed_rows={'headers': True},  # 固定表头
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
                            ])
                        ], className="shadow-sm mb-4")
                    ], width=12)
                ])
            )

        # 添加其他单算法内容（数据概览、延时误差统计、错误表格等）
        analyzer = backend._get_current_analyzer()
        if analyzer:
            overview_row = _create_single_algorithm_overview_row(analyzer, data_source, backend)
            error_stats_row = _create_single_algorithm_error_stats_row(analyzer, data_source)

            if overview_row:
                layout_rows.append(overview_row)
            if error_stats_row:
                layout_rows.append(error_stats_row)

        # 返回单算法模式的完整布局
        return html.Div([
            dbc.Container([
                dbc.Row([
                    dbc.Col([
                        html.H2(f"分析报告 - {data_source}", className="text-center mb-3",
                               style={'color': '#2E86AB', 'fontWeight': 'bold', 'textShadow': '1px 1px 2px rgba(0,0,0,0.1)'}),
                    ], width=12)
                ], className="mb-4"),

                # 单算法内容
                *layout_rows,

                # 其余内容（图表、表格等）- 与多算法模式保持一致
                # 柱状图分析区域 - 独立全宽区域
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            dbc.Row([
                                dbc.Col([
                                    html.H6("按键延时分析条形图", className="mb-2",
                                           style={'color': '#6f42c1', 'fontWeight': 'bold', 'borderBottom': '2px solid #6f42c1', 'paddingBottom': '5px'}),
                                ], width=12)
                            ]),
                            html.Div(id='offset-alignment-plot'),
                        ], className="mt-4")
                    ], width=12)
                ]),

                # 图表区域
                dbc.Row([
                    dbc.Col([
                        dcc.Graph(id='key-delay-scatter-plot'),
                        html.Div(id='key-delay-zscore-scatter-plot'),
                        dcc.Graph(id='hammer-velocity-delay-scatter-plot'),
                        dcc.Graph(id='key-force-interaction-plot'),
                        dcc.Graph(id='relative-delay-distribution-plot'),
                        html.Div(id='hammer-velocity-comparison-plot'),
                        dash_table.DataTable(id='offset-alignment-table')
                    ], width=12)
                ]),

                # 错误表格（单算法模式）
                _create_single_algorithm_error_tables(analyzer, data_source) if analyzer else html.Div(),

            ], fluid=True),
        ], style={'padding': '20px'})

    if not has_data:
        # 没有数据，显示提示
        # 关键：必须包含所有回调函数需要的组件，否则 Dash 会报错
        empty_fig = {}
        return html.Div([
            html.H4("暂无数据", className="text-center text-muted"),
            html.P("请先上传并分析SPMID文件", className="text-center text-muted"),
            # 包含所有必需的图表组件（隐藏），确保回调函数不会报错
            dcc.Graph(id='key-delay-scatter-plot', figure=empty_fig, style={'display': 'none'}),
            dcc.Graph(id='key-delay-zscore-scatter-plot', figure=empty_fig, style={'display': 'none'}),
            dcc.Graph(id='hammer-velocity-delay-scatter-plot', figure=empty_fig, style={'display': 'none'}),
            dcc.Graph(id='hammer-velocity-comparison-plot', figure=empty_fig, style={'display': 'none'}),
            # key-hammer-velocity-scatter-plot 已删除（功能与按键-力度交互效应图重复）
            # force-delay-by-key-scatter-plot 已删除（功能与按键-力度交互效应图重复）
            dcc.Graph(id='key-force-interaction-plot', figure=empty_fig, style={'display': 'none'}),
            dcc.Store(id='key-force-interaction-selected-algorithms', data=[]),
            dcc.Store(id='key-force-interaction-selected-keys', data=[]),
            dcc.Graph(id='relative-delay-distribution-plot', figure=empty_fig, style={'display': 'none'}),
            html.Div(id='offset-alignment-plot', style={'display': 'none'}),
            dcc.Graph(id='delay-time-series-plot', figure=empty_fig, style={'display': 'none'}),
            dcc.Graph(id='delay-histogram-plot', figure=empty_fig, style={'display': 'none'}),
            html.Div([
                dash_table.DataTable(
                    id='offset-alignment-table',
                    data=[],
                    columns=[]
                )
            ], style={'display': 'none'}),
        ])
    
    # 为每个算法生成数据概览和延时误差统计指标（合并到同一个卡片中）
    overview_rows = []
    error_stats_rows = []
    
    for algorithm in active_algorithms:
        algorithm_name = algorithm.metadata.algorithm_name
        overview_row = _create_single_algorithm_overview_row(algorithm, algorithm_name, backend)
        error_stats_row = _create_single_algorithm_error_stats_row(algorithm, algorithm_name)
        
        if overview_row:
            overview_rows.append(overview_row)
        if error_stats_row:
            error_stats_rows.append(error_stats_row)
    
    # 创建合并的数据概览卡片（包含所有算法）
    all_rows = []
    if overview_rows:
        all_rows.append(
                dbc.Row([
                    dbc.Col([
                        dbc.Card([
                            dbc.CardHeader([
                                html.H4([
                                    html.I(className="fas fa-chart-pie", style={'marginRight': '10px', 'color': '#28a745'}),
                                    "数据统计概览"
                                ], className="mb-0")
                            ]),
                            dbc.CardBody([
                                *overview_rows
                        ])
                    ], className="shadow-sm mb-4")
                    ], width=12)
                ])
            )
    
    # 创建合并的延时误差统计指标卡片（包含所有算法）
    if error_stats_rows:
        all_rows.append(
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            html.H4([
                                html.I(className="fas fa-chart-bar", style={'marginRight': '10px', 'color': '#dc3545'}),
                                "延时误差统计指标"
                            ], className="mb-0")
                        ]),
                        dbc.CardBody([
                            *error_stats_rows
                        ])
                    ], className="shadow-sm mb-4")
                ], width=12)
            ])
        )
    
    # 创建评级统计卡片 - 为每个算法分别显示
    if active_algorithms:
        # 多算法模式：为每个算法分别创建评级统计
        for algorithm in active_algorithms:
            if algorithm.analyzer and algorithm.analyzer.note_matcher:
                try:
                    alg_stats = algorithm.analyzer.note_matcher.get_graded_error_stats()
                    if alg_stats and 'error' not in alg_stats:
                        # 构建该算法的评级统计内容
                        graded_rows = []
                        algorithm_name = algorithm.metadata.algorithm_name

                        # 使用统一函数创建评级统计UI
                        graded_rows.extend(create_grade_statistics_rows(alg_stats, algorithm_name=algorithm_name))

                        # 添加该算法的评级统计卡片
                        if graded_rows:
                            all_rows.append(
                                dbc.Row([
                                    dbc.Col([
                                        dbc.Card([
                                            dbc.CardHeader([
                                                html.H4([
                                                    html.I(className="fas fa-chart-pie", style={'marginRight': '10px', 'color': '#6f42c1'}),
                                                    f"{algorithm_name} - 匹配质量评级统计"
                                                ], className="mb-0")
                                            ]),
                                            dbc.CardBody([
                                                *graded_rows,
                                                # 详细表格区域（默认隐藏）
                                                html.Div(
                                                    id={'type': 'grade-detail-table', 'index': algorithm_name},
                                                    style={'display': 'none', 'marginTop': '20px'},
                                                    children=[
                                                        html.H5("详细数据", className="mb-3"),
                                                        dash_table.DataTable(
                                                            id={'type': 'grade-detail-datatable', 'index': algorithm_name},
                                                            columns=[],
                                                            data=[],
                                                            page_action='none',
                                                            fixed_rows={'headers': True},  # 固定表头
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
                                            ])
                                        ], className="shadow-sm mb-4")
                                    ], width=12)
                                ])
                            )

                except Exception as e:
                    logger.warning(f"创建算法 {algorithm.metadata.algorithm_name} 的评级统计卡片失败: {e}")
    else:
        # 单算法模式：汇总显示评级统计
        analyzer = backend._get_current_analyzer() if backend else None
        if analyzer and analyzer.note_matcher:
            try:
                graded_stats = analyzer.note_matcher.get_graded_error_stats()
                if graded_stats and 'error' not in graded_stats:
                    # 构建评级统计内容
                    graded_rows = []

                    # 总体统计
                    total_count = sum(graded_stats.get(level, {}).get('count', 0)
                                    for level in ['correct', 'minor', 'moderate', 'large', 'major'])

                    if total_count > 0:
                        graded_rows.append(
                            dbc.Row([
                                dbc.Col([
                                    html.Div([
                                        html.H3(f"{total_count}", className="text-info mb-1"),
                                        html.P("总匹配对数", className="text-muted mb-0"),
                                        html.Small("所有类型的匹配对", className="text-muted", style={'fontSize': '10px'})
                                    ], className="text-center")
                                ], width=12)
                            ], className="mb-3")
                        )

                        # 分级统计 - 横排显示
                        grade_configs = [
                            ('correct', '优秀 (≤20ms)', 'success'),
                            ('minor', '良好 (20-30ms)', 'warning'),
                            ('moderate', '一般 (30-50ms)', 'info'),
                            ('large', '较差 (50-100ms)', 'danger'),
                            ('severe', '严重 (100-200ms)', 'dark')
                            # 注意：不再显示失败匹配，只统计成功匹配的质量分布
                        ]

                        # 创建横排的评级统计行
                        grade_cols = []
                        for grade_key, grade_name, color_class in grade_configs:
                            if grade_key in graded_stats:
                                grade_data = graded_stats[grade_key]
                                count = grade_data.get('count', 0)
                                percentage = grade_data.get('percent', 0.0)

                                grade_cols.append(
                                    dbc.Col([
                                        html.Div([
                                            html.H3(f"{count}", className=f"text-{color_class} mb-1"),
                                            html.P(f"{grade_name}", className="text-muted mb-0"),
                                            html.Small(f"{percentage:.1f}%", className="text-muted", style={'fontSize': '10px'})
                                        ], className="text-center")
                                    ], width='auto', className="px-2")  # width='auto' 让列自适应宽度，px-2 添加水平间距
                                )

                        if grade_cols:
                            graded_rows.append(
                                dbc.Row(grade_cols, className="mb-3 justify-content-center")
                            )

                    # 添加评级统计卡片
                    if graded_rows:
                        all_rows.append(
                            dbc.Row([
                                dbc.Col([
                                    dbc.Card([
                                        dbc.CardHeader([
                                            html.H4([
                                                html.I(className="fas fa-chart-pie", style={'marginRight': '10px', 'color': '#6f42c1'}),
                                                "匹配质量评级统计"
                                            ], className="mb-0")
                                        ]),
                                        dbc.CardBody([
                                            *graded_rows
                                        ])
                                    ], className="shadow-sm mb-4")
                                ], width=12)
                            ])
                        )

            except Exception as e:
                logger.warning(f"创建评级统计卡片失败: {e}")

    # 数据源信息已在前面获取
    data_source = source_info.get('filename') or "多算法对比"

    # 添加持续时间差异表格区域
    duration_diff_table_row = _create_duration_diff_table_row(backend, active_algorithms)
    if duration_diff_table_row:
        all_rows.append(duration_diff_table_row)

    return html.Div([
        dbc.Container([
            dbc.Row([
                dbc.Col([
                    html.H2(f"分析报告 - {data_source}", className="text-center mb-3",
                           style={'color': '#2E86AB', 'fontWeight': 'bold', 'textShadow': '1px 1px 2px rgba(0,0,0,0.1)'}),
                ], width=12)
            ], className="mb-4"),

                # 多算法数据概览和延时误差统计指标（每个算法一行）
                *all_rows,
                
                # 为每个算法创建独立的丢锤和多锤表格
                *[_create_error_tables_row_for_algorithm(alg) for alg in active_algorithms if alg.analyzer],
                
                # 其余内容（图表、表格等）- 与单算法模式保持一致
        # 柱状图分析区域 - 独立全宽区域
        dbc.Row([
            dbc.Col([
                html.Div([
                    dbc.Row([
                        dbc.Col([
                                    html.H6("按键延时分析条形图", className="mb-2",
                                   style={'color': '#6f42c1', 'fontWeight': 'bold', 'borderBottom': '2px solid #6f42c1', 'paddingBottom': '5px'}),
                                ], width=12)
                    ]),
                    html.Div(
                        id='offset-alignment-plot',
                        children=[],
                        style={'minHeight': '500px'}
                    ),
                ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
            ], width=12)
        ]),
        
        # 按键与相对延时散点图区域
        dbc.Row([
            dbc.Col([
                html.Div([
                    dbc.Row([
                        dbc.Col([
                            html.H6("按键与相对延时散点图", className="mb-2",
                                   style={'color': '#1976d2', 'fontWeight': 'bold', 'borderBottom': '2px solid #1976d2', 'paddingBottom': '5px'}),
                        ], width=6),
                        dbc.Col([
                            dbc.Checkbox(
                                id={'type': 'key-delay-scatter-common-keys-only', 'index': 0},
                                label="只显示公共按键",
                                value=False,
                                style={'fontSize': '14px', 'fontWeight': 'bold', 'display': 'inline-block'}
                            )
                        ], width=2, style={'textAlign': 'right', 'paddingTop': '5px'}),
                        dbc.Col([
                            dcc.Dropdown(
                                id={'type': 'key-delay-scatter-algorithm-selector', 'index': 0},
                                multi=True,
                                placeholder="选择参与对比的曲子",
                                style={'fontSize': '12px'}
                            )
                        ], width=4)
                    ]),
                    dcc.Graph(
                        id='key-delay-scatter-plot',
                        figure={},
                        style={'height': '800px'}  # 增加高度，从500px改为800px
                    ),
                ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
            ], width=12)
        ]),

        # 锤速与相对延时散点图区域
        dbc.Row([
            dbc.Col([
                html.Div([
                    dbc.Row([
                        dbc.Col([
                    html.H6("锤速与相对延时散点图", className="mb-2",
                           style={'color': '#9c27b0', 'fontWeight': 'bold', 'borderBottom': '2px solid #9c27b0', 'paddingBottom': '5px'}),
                        ], width=12)
                    ]),
                    dcc.Graph(
                id='hammer-velocity-relative-delay-scatter-plot',
                        figure={},
                        style={'height': '800px'}  # 增加高度，从500px改为800px，与其他散点图保持一致
                    ),
                ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
    ], width=12)
        ]),

        # 按键与延时Z-Score标准化散点图区域（算法数量<2时隐藏）
        dbc.Row([
            dbc.Col([
                html.Div([
                    dbc.Row([
                        dbc.Col([
                                    html.H6("按键与延时Z-Score标准化散点图", className="mb-2",
                                           style={'color': '#9c27b0', 'fontWeight': 'bold', 'borderBottom': '2px solid #9c27b0', 'paddingBottom': '5px'}),
                        ], width=12)
                    ]),
                    dcc.Graph(
                                id='key-delay-zscore-scatter-plot',
                        figure={},
                        style={'height': '800px'}
                    ),
                ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
                    ], width=12)
                ], style={'display': 'none'} if len(backend.get_active_algorithms()) < 2 else {}),

                # 锤速与延时Z-Score标准化散点图区域（算法数量<2时隐藏）
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            dbc.Row([
                                dbc.Col([
                            html.H6("锤速与延时Z-Score标准化散点图", className="mb-2",
                                   style={'color': '#d32f2f', 'fontWeight': 'bold', 'borderBottom': '2px solid #d32f2f', 'paddingBottom': '5px'}),
                                ], width=12)
                            ]),
                            dcc.Graph(
                        id='hammer-velocity-delay-scatter-plot',
                                figure={},
                                style={'height': '800px'}  # 增加高度，从500px改为800px，与其他散点图保持一致
                            ),
                        ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
            ], width=12)
        ], style={'display': 'none'} if not (hasattr(backend, 'get_active_algorithms') and
                       len(backend.get_active_algorithms()) >= 2) else {}),

        # 锤速对比图区域
        dbc.Row([
            dbc.Col([
                html.Div([
                    dbc.Row([
                        dbc.Col([
                            html.H6("锤速对比图", className="mb-2",
                                   style={'color': '#ff9800', 'fontWeight': 'bold', 'borderBottom': '2px solid #ff9800', 'paddingBottom': '5px'}),
                        ], width=12)
                    ]),
                    dcc.Graph(
                        id='hammer-velocity-comparison-plot',
                        figure={},
                        style={'height': '800px'}
                    ),
                ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
            ], width=12)
        ]),

        # 按键-力度交互效应图
        dbc.Row([
            dbc.Col([
                html.Div([
                    dbc.Row([
                        dbc.Col([
                            html.H6("按键-力度交互效应图", className="mb-2",
                                   style={'color': '#c2185b', 'fontWeight': 'bold', 'borderBottom': '2px solid #c2185b', 'paddingBottom': '5px'}),
                        ], width=8),
                        dbc.Col([
                            dcc.Dropdown(
                                id='key-force-interaction-key-selector',
                                placeholder='选择按键（留空显示全部）',
                                clearable=True,
                                style={'fontSize': '12px'}
                            )
                        ], width=4)
                    ]),
                    dcc.Graph(
                        id='key-force-interaction-plot',
                        figure={},
                        style={'height': '800px'}  # 增加高度，与锤速对比图和其他散点图保持一致
                    ),
                    dcc.Store(id='key-force-interaction-selected-keys', data=[]),  # 存储选中的按键列表
                ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
            ], width=12)
        ]),

        # 单键多曲延时对比区域
        dbc.Row([
            dbc.Col([
                html.Div([
                    dbc.Row([
                        dbc.Col([
                            html.H6("单键多曲延时对比", className="mb-2",
                                   style={'color': '#009688', 'fontWeight': 'bold', 'borderBottom': '2px solid #009688', 'paddingBottom': '5px'}),
                        ], width=8),
                        dbc.Col([
                            dcc.Dropdown(
                                id='single-key-selector',
                                placeholder='选择要分析的按键',
                                clearable=True,
                                style={'fontSize': '12px'}
                            )
                        ], width=4)
                    ]),
                    dcc.Graph(
                        id='single-key-delay-comparison-plot',
                        figure={},
                        style={'height': '400px'}
                    ),
                ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'})
            ], width=12)
        ]),

        # 同种算法相对延时分布图
        dbc.Row([
            dbc.Col([
                html.Div([
                    dbc.Row([
                        dbc.Col([
                            html.H6("同种算法不同曲子的相对延时分布图", className="mb-2",
                                   style={'color': '#9c27b0', 'fontWeight': 'bold', 'borderBottom': '2px solid #9c27b0', 'paddingBottom': '5px'}),
                        ], width=12)
                    ]),
                    html.Div(id='relative-delay-distribution-container', children=[])
                ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
            ], width=12)
        ]),
        
        # 曲线对齐测试区域
        create_curve_alignment_test_area(),

        # 延时时间序列图
        dbc.Row([
            dbc.Col([
                html.Div([
                    dbc.Row([
                        dbc.Col([
                            html.H6("延时时间序列图", className="mb-2",
                                   style={'color': '#2c3e50', 'fontWeight': 'bold', 'borderBottom': '2px solid #2c3e50', 'paddingBottom': '5px'}),
                        ], width=12)
                    ]),
                    # 原始延时时间序列图
                    dcc.Graph(
                        id='raw-delay-time-series-plot',
                        figure={},
                        style={'height': '500px', 'marginBottom': '20px'}
                    ),
                    # 相对延时时间序列图
                    dcc.Graph(
                        id='relative-delay-time-series-plot',
                        figure={},
                        style={'height': '500px'}
                    ),
                ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
            ], width=12)
        ]),
        
        # 延时分布直方图（附正态拟合曲线）- 使用相对时延
        dbc.Row([
            dbc.Col([
                html.Div([
                    dbc.Row([
                        dbc.Col([
                            html.H6("延时分布直方图（附正态拟合曲线）", className="mb-2",
                                   style={'color': '#2c3e50', 'fontWeight': 'bold', 'borderBottom': '2px solid #2c3e50', 'paddingBottom': '5px'}),
                        ], width=12)
                    ]),
                    dcc.Graph(
                        id='delay-histogram-plot',
                        figure={},
                        style={'height': '500px'}
                    ),
                ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
            ], width=12)
        ]),
        
        # 主要内容区域：为每个算法创建独立的丢锤和多锤表格（已在上面通过列表展开添加）
        # 这里保留原有的单算法模式表格（用于向后兼容，但多算法模式下不会使用）
        dbc.Row([
                # 左侧：丢锤问题表格
                dbc.Col([
                    html.Div([
                        dbc.Row([
                            dbc.Col([
                                html.H5("丢锤问题列表", className="mb-3",
                                       style={'color': '#721c24', 'fontWeight': 'bold', 'fontSize': '18px', 'borderBottom': '3px solid #721c24', 'paddingBottom': '8px'}),
                            ], width=12)
                        ]),
                        dash_table.DataTable(
                            id='drop-hammers-table',
                            columns=[
                                {"name": "数据类型", "id": "data_type"},
                                {"name": "键位ID", "id": "keyId"},
                                {"name": "按下时间(ms)", "id": "keyOn"},
                                {"name": "释放时间(ms)", "id": "keyOff"},
                                {"name": "index", "id": "index"},
                                {"name": "未匹配原因", "id": "analysis_reason"},
                            ],
                            data=backend.get_error_table_data('丢锤'),
                            page_action='none',
                            style_cell={
                                'textAlign': 'center',
                                    'fontSize': '14px',
                                'fontFamily': 'Arial, sans-serif',
                                    'padding': '10px',
                                'overflow': 'hidden',
                                'textOverflow': 'ellipsis',
                                'minWidth': '80px',
                            },
                                style_cell_conditional=(
                                    # 多算法模式：添加算法名称列的宽度
                                    [{'if': {'column_id': 'algorithm_name'}, 'width': '12%'}] if (
                                        hasattr(backend, 'multi_algorithm_manager') and
                                        backend.multi_algorithm_manager and
                                        len(backend.multi_algorithm_manager.get_active_algorithms()) > 1
                                    ) else []
                                ) + [
                                    {'if': {'column_id': 'data_type'}, 'width': '14%'},
                                    {'if': {'column_id': 'keyId'}, 'width': '12%'},
                                    {'if': {'column_id': 'keyOn'}, 'width': '16%'},
                                    {'if': {'column_id': 'keyOff'}, 'width': '16%'},
                                    {'if': {'column_id': 'index'}, 'width': '10%'},
                                    {'if': {'column_id': 'analysis_reason'}, 'width': '20%'},
                            ],
                            style_header={
                                'backgroundColor': '#f8d7da',
                                'fontWeight': 'bold',
                                'border': '2px solid #dee2e6',
                                    'fontSize': '15px',
                                'color': '#721c24',
                                'textAlign': 'center',
                                    'padding': '12px',
                                'whiteSpace': 'normal',
                                'height': 'auto',
                                'position': 'sticky',
                                'top': 0,
                                'zIndex': 1
                            },
                            style_data={
                                'border': '1px solid #dee2e6',
                                    'fontSize': '14px',
                                'padding': '10px'
                            },
                            style_data_conditional=[
                                {
                                    'if': {'filter_query': '{data_type} = record'},
                                    'fontWeight': 'bold',
                                    'backgroundColor': '#ffeaea'
                                },
                                {
                                    'if': {'filter_query': '{data_type} = play'},
                                    'backgroundColor': '#fffafa'
                                },
                                {
                                    'if': {'filter_query': '{keyOn} = 无匹配'},
                                    'backgroundColor': '#f5f5f5',
                                    'color': '#6c757d',
                                    'fontStyle': 'italic'
                                },
                                {
                                    'if': {'row_index': 'odd'},
                                    'backgroundColor': '#fafafa'
                                }
                            ],
                                row_selectable=False,
                            sort_action="native",
                                filter_action="none",
                            style_table={
                                    'height': 'calc(75vh - 200px)',
                                'overflowY': 'auto', 
                                'overflowX': 'auto',
                                'border': '2px solid #dee2e6', 
                                'borderRadius': '8px',
                                'minHeight': '400px'
                            }
                        ),
                    ], style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '10px', 'boxShadow': '0 4px 12px rgba(0,0,0,0.15)', 'height': '100%'}),
                    ], width=6, className="pr-2"),
                
                # 右侧：多锤问题表格
                dbc.Col([
                    html.Div([
                        dbc.Row([
                            dbc.Col([
                                html.H5("多锤问题列表", className="mb-3",
                                       style={'color': '#856404', 'fontWeight': 'bold', 'fontSize': '18px', 'borderBottom': '3px solid #856404', 'paddingBottom': '8px'}),
                            ], width=12)
                        ]),
                        dash_table.DataTable(
                            id='multi-hammers-table',
                            columns=[
                                {"name": "数据类型", "id": "data_type"},
                                {"name": "键位ID", "id": "keyId"},
                                {"name": "按下时间(ms)", "id": "keyOn"},
                                {"name": "释放时间(ms)", "id": "keyOff"},
                                {"name": "index", "id": "index"},
                                {"name": "未匹配原因", "id": "analysis_reason"},
                            ],
                            data=backend.get_error_table_data('多锤'),
                            page_action='none',
                            style_cell={
                                'textAlign': 'center',
                                    'fontSize': '14px',
                                'fontFamily': 'Arial, sans-serif',
                                    'padding': '10px',
                                'overflow': 'hidden',
                                'textOverflow': 'ellipsis',
                                'minWidth': '80px',
                            },
                                style_cell_conditional=(
                                    # 多算法模式：添加算法名称列的宽度
                                    [{'if': {'column_id': 'algorithm_name'}, 'width': '12%'}] if (
                                        hasattr(backend, 'multi_algorithm_manager') and
                                        backend.multi_algorithm_manager and
                                        len(backend.multi_algorithm_manager.get_active_algorithms()) > 1
                                    ) else []
                                ) + [
                                    {'if': {'column_id': 'data_type'}, 'width': '14%'},
                                    {'if': {'column_id': 'keyId'}, 'width': '12%'},
                                    {'if': {'column_id': 'keyOn'}, 'width': '16%'},
                                    {'if': {'column_id': 'keyOff'}, 'width': '16%'},
                                    {'if': {'column_id': 'index'}, 'width': '10%'},
                                    {'if': {'column_id': 'analysis_reason'}, 'width': '20%'},
                            ],
                            style_header={
                                'backgroundColor': '#fff3cd',
                                'fontWeight': 'bold',
                                'border': '2px solid #dee2e6',
                                    'fontSize': '15px',
                                'color': '#856404',
                                'textAlign': 'center',
                                    'padding': '12px',
                                'whiteSpace': 'normal',
                                'height': 'auto',
                                'position': 'sticky',
                                'top': 0,
                                'zIndex': 1
                            },
                            style_data={
                                'border': '1px solid #dee2e6',
                                    'fontSize': '14px',
                                'padding': '10px'
                            },
                            style_data_conditional=[
                                {
                                    'if': {'filter_query': '{data_type} = record'},
                                    'fontWeight': 'bold',
                                    'backgroundColor': '#fff8e1'
                                },
                                {
                                    'if': {'filter_query': '{data_type} = play'},
                                    'backgroundColor': '#fffef5'
                                },
                                {
                                    'if': {'filter_query': '{keyOn} = 无匹配'},
                                    'backgroundColor': '#f5f5f5',
                                    'color': '#6c757d',
                                    'fontStyle': 'italic'
                                },
                                {
                                    'if': {'row_index': 'odd'},
                                    'backgroundColor': '#fafafa'
                                }
                            ],
                                row_selectable=False,
                            sort_action="native",
                                filter_action="none",
                            style_table={
                                    'height': 'calc(75vh - 200px)',
                                'overflowY': 'auto', 
                                'overflowX': 'auto',
                                'border': '2px solid #dee2e6', 
                                'borderRadius': '8px',
                                'minHeight': '400px'
                            }
                        ),
                    ], style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '10px', 'boxShadow': '0 4px 12px rgba(0,0,0,0.15)', 'height': '100%'}),
                    ], width=6, className="pl-2"),
                ], className="mb-4", style={'display': 'none'}),  # 多算法模式下隐藏，使用上面的独立表格
            
            # 无效音符统计表格（单独一行）
            dbc.Row([
                dbc.Col([
                    html.Div([
                        dbc.Row([
                            dbc.Col([
                                html.H6("无效音符统计", className="mb-2",
                                       style={'color': '#6c757d', 'fontWeight': 'bold', 'borderBottom': '2px solid #6c757d', 'paddingBottom': '5px'}),
                            ], width=12)
                        ]),
                        dash_table.DataTable(
                            id='invalid-notes-table',
                                columns=(
                                    [{"name": "算法名称", "id": "algorithm_name"}] if True else []
                                ) + [
                                {"name": "数据类型", "id": "data_type"},
                                {"name": "总音符数", "id": "total_notes"},
                                {"name": "有效音符", "id": "valid_notes"},
                                {"name": "无效音符", "id": "invalid_notes"},
                                {"name": "压感值过低", "id": "low_after_value"},
                                {"name": "持续时间过短", "id": "short_duration"},
                                {"name": "数据为空", "id": "empty_data"},
                                {"name": "其他错误", "id": "other_errors"}
                            ],
                            data=backend.get_invalid_notes_table_data(),
                                page_action='none',
                            style_cell={
                                'textAlign': 'center',
                                    'fontSize': '14px',
                                'fontFamily': 'Arial, sans-serif',
                                    'padding': '10px',
                                'overflow': 'hidden',
                                'textOverflow': 'ellipsis',
                                'minWidth': '100px',
                            },
                                style_cell_conditional=(
                                    [{'if': {'column_id': 'algorithm_name'}, 'width': '12%'}] if True else []
                                ) + [
                                    {'if': {'column_id': 'data_type'}, 'width': '13%' if True else '15%'},
                                    {'if': {'column_id': 'total_notes'}, 'width': '11%' if True else '13%'},
                                    {'if': {'column_id': 'valid_notes'}, 'width': '11%' if True else '13%'},
                                    {'if': {'column_id': 'invalid_notes'}, 'width': '11%' if True else '13%'},
                                    {'if': {'column_id': 'low_after_value'}, 'width': '12%' if True else '14%'},
                                    {'if': {'column_id': 'short_duration'}, 'width': '13%' if True else '15%'},
                                    {'if': {'column_id': 'empty_data'}, 'width': '10%' if True else '12%'},
                                    {'if': {'column_id': 'other_errors'}, 'width': '9%' if True else '10%'},
                            ],
                            style_header={
                                'backgroundColor': '#e9ecef',
                                'fontWeight': 'bold',
                                'border': '2px solid #dee2e6',
                                    'fontSize': '15px',
                                'color': '#495057',
                                'textAlign': 'center',
                                    'padding': '12px',
                                'whiteSpace': 'normal',
                                'height': 'auto',
                                'position': 'sticky',
                                'top': 0,
                                'zIndex': 1
                            },
                            style_data={
                                'border': '1px solid #dee2e6',
                                    'fontSize': '14px',
                                'padding': '10px'
                            },
                                style_data_conditional=(
                                    # 多算法模式：为算法名称列添加特殊样式
                                    [
                                        {
                                            'if': {'column_id': 'algorithm_name'},
                                            'fontWeight': 'bold',
                                            'fontSize': '15px',
                                            'backgroundColor': '#e3f2fd',
                                            'borderLeft': '4px solid #1976d2',
                                            'color': '#1976d2'
                                        }
                                    ] if True else []
                                ) + [
                                {
                                    'if': {'filter_query': '{data_type} = 录制数据'},
                                    'backgroundColor': '#f8f9fa',
                                    'fontWeight': 'bold'
                                },
                                {
                                        'if': {'filter_query': '{data_type} = 回放数据'},
                                    'backgroundColor': '#ffffff'
                                },
                                {
                                    'if': {'row_index': 'odd'},
                                    'backgroundColor': '#fafafa'
                                }
                            ],
                            sort_action="native",
                                filter_action="none",
                            style_table={
                                    'height': 'calc(40vh - 120px)',
                                'overflowY': 'auto', 
                                'overflowX': 'auto',
                                'border': '2px solid #dee2e6', 
                                'borderRadius': '8px',
                                'minHeight': '250px'
                            }
                        ),
                    ], className="mb-3", style={'backgroundColor': '#ffffff', 'padding': '15px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
                    
                    # 无效音符详细信息表格 - 录制数据
                    html.Div([
                        dbc.Row([
                            dbc.Col([
                                html.H6("无效音符详细列表 - 录制数据", className="mb-2",
                                       style={'color': '#dc3545', 'fontWeight': 'bold', 'borderBottom': '2px solid #dc3545', 'paddingBottom': '5px'}),
                            ], width=12)
                        ]),
                        dash_table.DataTable(
                            id='invalid-notes-detail-record-table',
                            columns=[
                                {"name": "数据类型", "id": "data_type"},
                                {"name": "键位ID", "id": "key_id"},
                                {"name": "按下时间(ms)", "id": "key_on_ms"},
                                {"name": "释放时间(ms)", "id": "key_off_ms"},
                                {"name": "持续时间", "id": "duration_ms"},
                                {"name": "第一个锤击时间", "id": "first_hammer_time_ms"},
                                {"name": "无效原因", "id": "invalid_reason"}
                            ],
                            data=backend.get_invalid_notes_detail_table_data('录制'),
                            page_action='native',
                            page_size=10,
                            style_cell={
                                'textAlign': 'center',
                                'fontSize': '13px',
                                'fontFamily': 'Arial, sans-serif',
                                'padding': '8px',
                                'overflow': 'hidden',
                                'textOverflow': 'ellipsis',
                                'minWidth': '80px',
                            },
                            style_cell_conditional=[
                                {'if': {'column_id': 'data_type'}, 'width': '12%'},
                                {'if': {'column_id': 'key_id'}, 'width': '10%'},
                                {'if': {'column_id': 'key_on_ms'}, 'width': '15%'},
                                {'if': {'column_id': 'key_off_ms'}, 'width': '15%'},
                                {'if': {'column_id': 'duration_ms'}, 'width': '13%'},
                                {'if': {'column_id': 'first_hammer_time_ms'}, 'width': '15%'},
                                {'if': {'column_id': 'invalid_reason'}, 'width': '20%'},
                            ],
                            style_header={
                                'backgroundColor': '#f8d7da',
                                'fontWeight': 'bold',
                                'border': '2px solid #f5c6cb',
                                'fontSize': '14px',
                                'color': '#721c24',
                                'textAlign': 'center',
                                'padding': '10px',
                                'whiteSpace': 'normal',
                                'height': 'auto'
                            },
                            style_data={
                                'border': '1px solid #f5c6cb',
                                'fontSize': '13px',
                                'padding': '8px'
                            },
                            style_data_conditional=[
                                {
                                    'if': {'row_index': 'odd'},
                                    'backgroundColor': '#fff5f5'
                                }
                            ],
                            style_table={
                                'height': '300px',
                                'overflowY': 'auto', 
                                'overflowX': 'auto',
                                'border': '2px solid #f5c6cb', 
                                'borderRadius': '8px'
                            }
                        ),
                    ], className="mb-3", style={'backgroundColor': '#ffffff', 'padding': '15px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
                    
                    # 无效音符详细信息表格 - 播放数据
                    html.Div([
                        dbc.Row([
                            dbc.Col([
                                html.H6("无效音符详细列表 - 播放数据", className="mb-2",
                                       style={'color': '#0056b3', 'fontWeight': 'bold', 'borderBottom': '2px solid #0056b3', 'paddingBottom': '5px'}),
                            ], width=12)
                        ]),
                        dash_table.DataTable(
                            id='invalid-notes-detail-replay-table',
                            columns=[
                                {"name": "数据类型", "id": "data_type"},
                                {"name": "键位ID", "id": "key_id"},
                                {"name": "按下时间(ms)", "id": "key_on_ms"},
                                {"name": "释放时间(ms)", "id": "key_off_ms"},
                                {"name": "持续时间", "id": "duration_ms"},
                                {"name": "第一个锤击时间", "id": "first_hammer_time_ms"},
                                {"name": "无效原因", "id": "invalid_reason"}
                            ],
                            data=backend.get_invalid_notes_detail_table_data('播放'),
                            page_action='native',
                            page_size=10,
                            style_cell={
                                'textAlign': 'center',
                                'fontSize': '13px',
                                'fontFamily': 'Arial, sans-serif',
                                'padding': '8px',
                                'overflow': 'hidden',
                                'textOverflow': 'ellipsis',
                                'minWidth': '80px',
                            },
                            style_cell_conditional=[
                                {'if': {'column_id': 'data_type'}, 'width': '12%'},
                                {'if': {'column_id': 'key_id'}, 'width': '10%'},
                                {'if': {'column_id': 'key_on_ms'}, 'width': '15%'},
                                {'if': {'column_id': 'key_off_ms'}, 'width': '15%'},
                                {'if': {'column_id': 'duration_ms'}, 'width': '13%'},
                                {'if': {'column_id': 'first_hammer_time_ms'}, 'width': '15%'},
                                {'if': {'column_id': 'invalid_reason'}, 'width': '20%'},
                            ],
                            style_header={
                                'backgroundColor': '#d1ecf1',
                                'fontWeight': 'bold',
                                'border': '2px solid #bee5eb',
                                'fontSize': '14px',
                                'color': '#0c5460',
                                'textAlign': 'center',
                                'padding': '10px',
                                'whiteSpace': 'normal',
                                'height': 'auto'
                            },
                            style_data={
                                'border': '1px solid #bee5eb',
                                'fontSize': '13px',
                                'padding': '8px'
                            },
                            style_data_conditional=[
                                {
                                    'if': {'row_index': 'odd'},
                                    'backgroundColor': '#f0f8ff'
                                }
                            ],
                            style_table={
                                'height': '300px',
                                'overflowY': 'auto', 
                                'overflowX': 'auto',
                                'border': '2px solid #bee5eb', 
                                'borderRadius': '8px'
                            }
                        ),
                    ], className="mb-3", style={'backgroundColor': '#ffffff', 'padding': '15px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),

                    # 偏移对齐数据表格
                    html.Div([
                        dbc.Row([
                            dbc.Col([
                                    html.H6("按键延时分析", className="mb-2",
                                       style={'color': '#6f42c1', 'fontWeight': 'bold', 'borderBottom': '2px solid #6f42c1', 'paddingBottom': '5px'}),
                            ], width=12)
                        ]),
                        dash_table.DataTable(
                            id='offset-alignment-table',
                                columns=(
                                    # 多算法模式：添加"算法名称"列
                                    [{"name": "算法名称", "id": "algorithm_name"}] if True else []
                                ) + [
                                {"name": "键位ID", "id": "key_id"},
                                {"name": "配对数", "id": "count"},
                                {"name": "中位数(ms)", "id": "median"},
                                {"name": "均值(ms)", "id": "mean"},
                                {"name": "标准差(ms)", "id": "std"},
                                    {"name": "方差(ms²)", "id": "variance"},
                                    {"name": "最小值(ms)", "id": "min"},
                                    {"name": "最大值(ms)", "id": "max"},
                                    {"name": "极差(ms)", "id": "range"},
                                {"name": "状态", "id": "status"}
                            ],
                            data=active_algorithms[0].get_key_statistics_table_data() if active_algorithms else [],
                                page_action='none',
                            style_cell={
                                'textAlign': 'center',
                                    'fontSize': '14px',
                                'fontFamily': 'Arial, sans-serif',
                                    'padding': '10px',
                                'overflow': 'hidden',
                                'textOverflow': 'ellipsis',
                                'minWidth': '100px',
                            },
                                style_cell_conditional=(
                                    # 多算法模式：添加"算法名称"列的样式
                                    [{'if': {'column_id': 'algorithm_name'}, 'width': '10%'}] if True else []
                                ) + [
                                    {'if': {'column_id': 'key_id'}, 'width': '8%' if True else '10%'},
                                    {'if': {'column_id': 'count'}, 'width': '8%' if True else '10%'},
                                    {'if': {'column_id': 'median'}, 'width': '8%' if True else '10%'},
                                    {'if': {'column_id': 'mean'}, 'width': '8%' if True else '10%'},
                                    {'if': {'column_id': 'std'}, 'width': '8%' if True else '10%'},
                                    {'if': {'column_id': 'variance'}, 'width': '9%' if True else '10%'},
                                    {'if': {'column_id': 'min'}, 'width': '8%' if True else '10%'},
                                    {'if': {'column_id': 'max'}, 'width': '8%' if True else '10%'},
                                    {'if': {'column_id': 'range'}, 'width': '8%' if True else '10%'},
                                    {'if': {'column_id': 'status'}, 'width': '15%' if True else '10%'},
                            ],
                            style_header={
                                    'backgroundColor': '#e3f2fd',
                                'fontWeight': 'bold',
                                'border': '2px solid #dee2e6',
                                    'fontSize': '15px',
                                    'color': '#1976d2',
                                'textAlign': 'center',
                                    'padding': '12px',
                                'whiteSpace': 'normal',
                                'height': 'auto',
                                'position': 'sticky',
                                'top': 0,
                                'zIndex': 1
                            },
                            style_data={
                                'border': '1px solid #dee2e6',
                                    'fontSize': '14px',
                                'padding': '10px'
                            },
                                style_data_conditional=(
                                    # 多算法模式：为算法名称列添加特殊样式
                                    # 注意：算法名称列的背景色会与行背景色叠加，所以只设置字体样式
                                    [
                                        {
                                            'if': {'column_id': 'algorithm_name'},
                                            'fontWeight': 'bold',
                                            'fontSize': '15px',
                                            'color': '#1976d2'
                                        }
                                    ] if True else []
                                ) + [
                                    # 多算法模式：为每种算法添加不同的行背景色（放在最后，确保优先级最高）
                                    # 每种算法的所有行使用相同的背景色，便于区分不同算法
                                    *([
                                        {
                                            # 使用filter_query匹配算法名称
                                            'if': {'filter_query': f'{{algorithm_name}} = "{alg_name}"'},
                                            'backgroundColor': _hex_to_rgba(alg_color, alpha=0.25)
                                        }
                                        for alg_name, alg_color in algorithm_colors.items()
                                    ] if True else []),
                                    # 为每种算法的奇偶行添加轻微的颜色差异（像多锤表格一样）
                                    *([
                                        {
                                            'if': {
                                                'filter_query': f'{{algorithm_name}} = "{alg_name}"',
                                                'row_index': 'odd'
                                            },
                                            'backgroundColor': _hex_to_rgba(alg_color, alpha=0.35)
                                        }
                                        for alg_name, alg_color in algorithm_colors.items()
                                    ] if True else []),
                                {
                                    'if': {'filter_query': '{key_id} = 总体'},
                                    'color': '#6f42c1',
                                    'fontWeight': 'bold'
                                },
                                    {
                                        'if': {'filter_query': '{key_id} = 汇总'},
                                        'fontWeight': 'bold',
                                        'color': '#1976d2'
                                },
                                {
                                    'if': {'filter_query': '{status} = matched'},
                                    'color': '#155724'
                                },
                                {
                                    'if': {'filter_query': '{status} contains invalid'},
                                    'color': '#721c24'
                                    },
                                    # 多算法模式：为按键ID列添加特殊样式，便于区分不同按键组
                                    # 注意：这里只设置字体和颜色，不设置背景色，避免覆盖行背景色
                                    {
                                        'if': {'column_id': 'key_id'},
                                        'fontWeight': 'bold',
                                        'fontSize': '15px',
                                        'color': '#856404'
                                    } if True else {}
                            ],
                            sort_action="native",
                                filter_action="none",
                            style_table={
                                    'height': 'calc(50vh - 150px)',
                                'overflowY': 'auto', 
                                'overflowX': 'auto',
                                'border': '2px solid #dee2e6', 
                                'borderRadius': '8px',
                                'minHeight': '300px'
                            }
                        ),
                    ], className="mb-3", style={'backgroundColor': '#ffffff', 'padding': '15px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
                    ], width=12)
            ])
        ], fluid=True, style={'padding': '20px', 'backgroundColor': '#f5f5f5', 'minHeight': '100vh'})
    ], id='report-layout-container')


def create_detail_content(error_note):
    """创建详细信息内容"""
    details = []

    # 异常类型标签
    details.append(
        dbc.Row([
            dbc.Col([
                dbc.Badge(f"{error_note.error_type}",
                         color="danger" if error_note.error_type == '丢锤' else "warning",
                         className="me-2"),
                html.Span("异常类型", style={'fontSize': '14px', 'fontWeight': 'bold'})
            ], width=12)
        ], className="mb-3")
    )

    # 录制数据信息
    if len(error_note.notes) > 0:
        record_note = error_note.notes[0]  # Note对象
        record_diff = error_note.diffs[0] if len(error_note.diffs) > 0 else None

        details.append(
            dbc.Card([
                dbc.CardHeader([
                    html.I(className="fas fa-microphone me-2", style={'color': '#0d6efd'}),
                    html.Strong("录制数据", style={'color': '#0d6efd', 'fontSize': '13px'})
                ], style={'padding': '8px 12px', 'backgroundColor': '#e7f3ff', 'border': 'none'}),
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            html.Small("键位ID", className="text-muted d-block"),
                            html.Strong(f"{record_note.id}", style={'fontSize': '14px'})
                        ], width=6),
                        dbc.Col([
                            html.Small("持续时间", className="text-muted d-block"),
                            html.Strong(f"{record_note.duration_ms:.2f}ms" if record_note.duration_ms is not None else 'N/A', style={'fontSize': '14px'})
                        ], width=6)
                    ], className="mb-2"),
                    dbc.Row([
                        dbc.Col([
                            html.Small("按下时间", className="text-muted d-block"),
                            html.Span(f"{record_note.key_on_ms:.2f}ms" if record_note.key_on_ms is not None else 'N/A', style={'fontSize': '12px'})
                        ], width=6),
                        dbc.Col([
                            html.Small("释放时间", className="text-muted d-block"),
                            html.Span(f"{record_note.key_off_ms:.2f}ms" if record_note.key_off_ms is not None else 'N/A', style={'fontSize': '12px'})
                        ], width=6)
                    ])
                ], style={'padding': '10px'})
            ], className="mb-2", style={'border': '1px solid #dee2e6'})
        )

        if record_diff:
            details.append(
                dbc.Card([
                    dbc.CardHeader([
                        html.I(className="fas fa-chart-bar me-2", style={'color': '#0d6efd'}),
                        html.Strong("录制统计数据", style={'color': '#0d6efd', 'fontSize': '13px'})
                    ], style={'padding': '8px 12px', 'backgroundColor': '#e7f3ff', 'border': 'none'}),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.Small("均值", className="text-muted d-block"),
                                html.Strong(f"{record_diff.mean:.3f}", style={'fontSize': '12px'})
                            ], width=6),
                            dbc.Col([
                                html.Small("标准差", className="text-muted d-block"),
                                html.Strong(f"{record_diff.std:.3f}", style={'fontSize': '12px'})
                            ], width=6)
                        ], className="mb-1"),
                        dbc.Row([
                            dbc.Col([
                                html.Small("最大值", className="text-muted d-block"),
                                html.Span(f"{record_diff.max:.3f}", style={'fontSize': '12px'})
                            ], width=6),
                            dbc.Col([
                                html.Small("最小值", className="text-muted d-block"),
                                html.Span(f"{record_diff.min:.3f}", style={'fontSize': '12px'})
                            ], width=6)
                        ])
                    ], style={'padding': '10px'})
                ], className="mb-2", style={'border': '1px solid #dee2e6'})
            )

    # 播放数据信息（如果有）
    if len(error_note.notes) > 1:
        play_note = error_note.notes[1]  # Note对象
        play_diff = error_note.diffs[1] if len(error_note.diffs) > 1 else None

        details.append(
            dbc.Card([
                dbc.CardHeader([
                    html.I(className="fas fa-play me-2", style={'color': '#dc3545'}),
                    html.Strong("播放数据", style={'color': '#dc3545', 'fontSize': '13px'})
                ], style={'padding': '8px 12px', 'backgroundColor': '#f8d7da', 'border': 'none'}),
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            html.Small("键位ID", className="text-muted d-block"),
                            html.Strong(f"{play_note.id}", style={'fontSize': '14px'})
                        ], width=6),
                        dbc.Col([
                            html.Small("持续时间", className="text-muted d-block"),
                            html.Strong(f"{play_note.duration_ms:.2f}ms" if play_note.duration_ms is not None else 'N/A', style={'fontSize': '14px'})
                        ], width=6)
                    ], className="mb-2"),
                    dbc.Row([
                        dbc.Col([
                            html.Small("按下时间", className="text-muted d-block"),
                            html.Span(f"{play_note.key_on_ms:.2f}ms" if play_note.key_on_ms is not None else 'N/A', style={'fontSize': '12px'})
                        ], width=6),
                        dbc.Col([
                            html.Small("释放时间", className="text-muted d-block"),
                            html.Span(f"{play_note.key_off_ms:.2f}ms" if play_note.key_off_ms is not None else 'N/A', style={'fontSize': '12px'})
                        ], width=6)
                    ])
                ], style={'padding': '10px'})
            ], className="mb-2", style={'border': '1px solid #dee2e6'})
        )

        if play_diff:
            details.append(
                dbc.Card([
                    dbc.CardHeader([
                        html.I(className="fas fa-chart-bar me-2", style={'color': '#dc3545'}),
                        html.Strong("播放统计数据", style={'color': '#dc3545', 'fontSize': '13px'})
                    ], style={'padding': '8px 12px', 'backgroundColor': '#f8d7da', 'border': 'none'}),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.Small("均值", className="text-muted d-block"),
                                html.Strong(f"{play_diff.mean:.3f}", style={'fontSize': '12px'})
                            ], width=6),
                            dbc.Col([
                                html.Small("标准差", className="text-muted d-block"),
                                html.Strong(f"{play_diff.std:.3f}", style={'fontSize': '12px'})
                            ], width=6)
                        ], className="mb-1"),
                        dbc.Row([
                            dbc.Col([
                                html.Small("最大值", className="text-muted d-block"),
                                html.Span(f"{play_diff.max:.3f}", style={'fontSize': '12px'})
                            ], width=6),
                            dbc.Col([
                                html.Small("最小值", className="text-muted d-block"),
                                html.Span(f"{play_diff.min:.3f}", style={'fontSize': '12px'})
                            ], width=6)
                        ])
                    ], style={'padding': '10px'})
                ], className="mb-2", style={'border': '1px solid #dee2e6'})
            )
    else:
        # 没有播放数据的情况（主要针对丢锤或部分多锤）
        details.append(
            dbc.Alert([
                html.I(className="fas fa-exclamation-triangle me-2"),
                html.Strong("无播放数据匹配")
            ], color="warning", className="mb-2")
        )

    return details


def create_curve_alignment_test_area():
    """创建曲线对齐测试区域"""
    return dbc.Row([
        dbc.Col([
            html.Div([
                dbc.Row([
                    dbc.Col([
                        html.H6("曲线对齐测试", className="mb-2",
                               style={'color': '#2c3e50', 'fontWeight': 'bold', 'borderBottom': '2px solid #2c3e50', 'paddingBottom': '5px'}),
                        html.P("使用延时时间序列图的第一个数据点测试曲线对齐功能", 
                               className="text-muted", 
                               style={'fontSize': '12px', 'marginBottom': '10px'}),
                    ], width=12)
                ]),
                dbc.Row([
                    dbc.Col([
                        dbc.Button([
                            html.I(className="fas fa-play me-2"),
                            "开始测试"
                        ], id='btn-test-curve-alignment', color='primary', size='md', className='mb-3'),
                    ], width=12)
                ]),
                html.Div(id='curve-alignment-test-result', children=[
                    html.Div("点击按钮开始测试", 
                            className="text-muted text-center",
                            style={'padding': '20px', 'fontSize': '14px'})
                ])
            ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
        ], width=12)
    ])

    # 相似度详情模态框
    html.Div([
        html.Div([
            html.Div([
                html.Div([
                    html.H4("相似度详情", style={'margin': '0', 'padding': '10px 20px', 'borderBottom': '1px solid #dee2e6'}),
                    html.Button("×", id="close-similarity-detail-modal", className="close", style={
                        'position': 'absolute',
                        'right': '15px',
                        'top': '15px',
                        'fontSize': '28px',
                        'fontWeight': 'bold',
                        'background': 'none',
                        'border': 'none',
                        'cursor': 'pointer',
                        'color': '#aaa'
                    })
                ], style={'position': 'relative', 'borderBottom': '1px solid #dee2e6'}),
                html.Div([
                    html.Div(id='similarity-detail-content', children=[])
                ], id='similarity-detail-modal-body', className="modal-body", style={
                    'padding': '20px',
                    'maxHeight': '70vh',
                    'overflowY': 'auto'
                }),
                html.Div([
                    html.Button(
                        "关闭",
                        id="close-similarity-detail-modal-btn",
                        className="btn btn-primary",
                        style={
                            'backgroundColor': '#007bff',
                            'borderColor': '#007bff',
                            'padding': '8px 20px',
                            'borderRadius': '5px',
                            'border': 'none',
                            'color': 'white',
                            'cursor': 'pointer'
                        }
                    )
                ], className="modal-footer", style={
                    'borderTop': '1px solid #dee2e6',
                    'padding': '15px 20px',
                    'textAlign': 'right'
                })
            ], className="modal-content", style={
                'backgroundColor': 'white',
                'margin': '5% auto',
                'padding': '0',
                'border': 'none',
                'width': '80%',
                'maxWidth': '1000px',
                'borderRadius': '10px',
                'boxShadow': '0 4px 20px rgba(0,0,0,0.3)',
                'maxHeight': '90vh'
            })
        ], id="similarity-detail-modal", className="modal", style={
            'display': 'none',
            'position': 'fixed',
            'zIndex': '10000',
            'left': '0',
            'top': '0',
            'width': '100%',
            'height': '100%',
            'backgroundColor': 'rgba(0,0,0,0.7)',
            'backdropFilter': 'blur(5px)'
        })
    ]),


def _create_duration_diff_table_row(backend, active_algorithms):
    """创建持续时间差异表格行"""
    try:
        # 获取持续时间差异数据
        duration_diff_data = _get_duration_diff_data(backend, active_algorithms)
        if not duration_diff_data:
            return None

        return dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H4([
                            html.I(className="fas fa-scissors", style={'marginRight': '10px', 'color': '#17a2b8'}),
                            "拆分的按键数据"
                        ], className="mb-0")
                    ]),
                    dbc.CardBody([
                        html.P(f"找到 {len(duration_diff_data)} 个需要拆分的按键数据",
                               className="text-muted mb-3"),
                        dash_table.DataTable(
                            id='duration-diff-table',
                            columns=[
                                {"name": "序号", "id": "index", "type": "numeric"},
                                {"name": "按键ID", "id": "key_id", "type": "text"},
                                {"name": "录制索引", "id": "record_idx", "type": "numeric"},
                                {"name": "播放索引", "id": "replay_idx", "type": "numeric"},
                                {"name": "录制持续时间(ms)", "id": "record_duration", "type": "numeric", "format": {"specifier": ".1f"}},
                                {"name": "播放持续时间(ms)", "id": "replay_duration", "type": "numeric", "format": {"specifier": ".1f"}},
                                {"name": "持续时间比值", "id": "duration_ratio", "type": "numeric", "format": {"specifier": ".2f"}},
                                {"name": "录制keyon(ms)", "id": "record_keyon", "type": "numeric", "format": {"specifier": ".1f"}},
                                {"name": "录制keyoff(ms)", "id": "record_keyoff", "type": "numeric", "format": {"specifier": ".1f"}},
                                {"name": "播放keyon(ms)", "id": "replay_keyon", "type": "numeric", "format": {"specifier": ".1f"}},
                                {"name": "播放keyoff(ms)", "id": "replay_keyoff", "type": "numeric", "format": {"specifier": ".1f"}}
                            ],
                            data=duration_diff_data,
                            page_size=15,
                            style_table={
                                "overflowX": "auto",
                                "maxHeight": "500px"
                            },
                            style_cell={
                                "textAlign": "center",
                                "padding": "8px",
                                "minWidth": "80px",
                                "maxWidth": "150px",
                                "fontSize": "14px",
                                "fontFamily": "Arial, sans-serif"
                            },
                            style_header={
                                "backgroundColor": "#f8f9fa",
                                "fontWeight": "bold",
                                "borderBottom": "2px solid #dee2e6"
                            },
                            style_data_conditional=[
                                {
                                    'if': {'state': 'active'},
                                    'backgroundColor': 'rgba(0, 116, 217, 0.1)',
                                    'border': '1px solid rgb(0, 116, 217)'
                                },
                                {
                                    'if': {'state': 'selected'},
                                    'backgroundColor': 'rgba(0, 116, 217, 0.2)',
                                    'border': '1px solid rgb(0, 116, 217)'
                                }
                            ],
                            style_data={
                                'cursor': 'pointer'
                            },
                            sort_action="native",
                            sort_by=[{"column_id": "record_keyon", "direction": "asc"}],
                            filter_action="none",
                            row_selectable=False,
                            cell_selectable=True,
                            tooltip_header={
                                "index": "匹配对序号",
                                "key_id": "钢琴按键ID",
                                "record_idx": "录制数据中的索引",
                                "replay_idx": "播放数据中的索引",
                                "record_duration": "录制时的按键持续时间",
                                "replay_duration": "播放时的按键持续时间",
                                "duration_ratio": "播放持续时间/录制持续时间"
                            }
                        )
                    ])
                ], className="shadow-sm mb-4")
            ], width=12)
        ])

    except Exception as e:
        logger.error(f"创建持续时间差异表格失败: {e}")
        return None


def _get_duration_diff_data(backend, active_algorithms):
    """获取持续时间差异数据"""
    try:
        duration_diff_pairs = []

        # 从算法中获取持续时间差异数据
        if active_algorithms:
            # 多算法模式
            for algorithm in active_algorithms:
                if hasattr(algorithm.analyzer, "note_matcher") and hasattr(algorithm.analyzer.note_matcher, "duration_diff_pairs"):
                    diff_pairs = algorithm.analyzer.note_matcher.duration_diff_pairs
                    if diff_pairs:
                        duration_diff_pairs.extend(diff_pairs)
        elif backend and hasattr(backend, "_get_current_analyzer"):
            # 单算法模式
            analyzer = backend._get_current_analyzer()
            if analyzer and hasattr(analyzer, "note_matcher") and hasattr(analyzer.note_matcher, "duration_diff_pairs"):
                diff_pairs = analyzer.note_matcher.duration_diff_pairs
                if diff_pairs:
                    duration_diff_pairs.extend(diff_pairs)

        if not duration_diff_pairs:
            return []

        # 转换为表格数据格式
        table_data = []
        for i, pair in enumerate(duration_diff_pairs):
            if len(pair) >= 11:
                record_idx, replay_idx, record_note, replay_note, record_duration, replay_duration, duration_ratio, record_keyon, record_keyoff, replay_keyon, replay_keyoff = pair

                table_data.append({
                    "index": i + 1,
                    "key_id": record_note.id if record_note else "N/A",
                    "record_idx": record_idx,
                    "replay_idx": replay_idx,
                    "record_duration": float(record_duration),
                    "replay_duration": float(replay_duration),
                    "duration_ratio": float(duration_ratio),
                    "record_keyon": float(record_keyon) if record_keyon is not None else None,
                    "record_keyoff": float(record_keyoff) if record_keyoff is not None else None,
                    "replay_keyon": float(replay_keyon) if replay_keyon is not None else None,
                    "replay_keyoff": float(replay_keyoff) if replay_keyoff is not None else None
                })

        # 默认按 record_keyon 升序排序（在表格组件中设置）

        return table_data

    except Exception as e:
        logger.error(f"获取持续时间差异数据失败: {e}")
        return []


def create_similarity_analysis_ui():
    """创建相似度分析UI组件"""
    return html.Div([
        # 加载提示
        html.Div([
            html.Div([
                html.I(className="fas fa-spinner fa-spin me-2"),
                "正在分析相似度..."
            ], className="text-muted text-center", style={'padding': '40px'})
        ], id="similarity-loading-indicator", style={'display': 'none'}),
        # 分析结果容器
        html.Div(id="similarity-analysis-results", children=[])
    ], className="mb-4")
