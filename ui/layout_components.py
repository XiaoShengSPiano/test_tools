"""
UI布局模块 - 定义Dash应用的界面布局
包含主界面、报告布局等UI组件
"""
import dash_bootstrap_components as dbc
from dash import dcc, html, dash_table
import plotly.graph_objects as go


# 创建空白图形
empty_figure = go.Figure()
empty_figure.add_annotation(
    text="请上传数据文件并点击加载数据按钮",
    xref="paper", yref="paper",
    x=0.5, y=0.5, showarrow=False,
    font=dict(size=20, color='gray')
)
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



def create_main_layout():
    """创建主界面布局"""
    return html.Div([
        # 隐藏的会话ID存储
        dcc.Store(id='session-id', storage_type='session'),

        # 隐藏的加载触发器
        dcc.Store(id='loading-trigger', storage_type='memory'),

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
                        # 左侧上传区域
                        dbc.Col([
                            html.Label("SPMID数据文件", style={
                                'fontWeight': 'bold',
                                'color': '#2c3e50',
                                'marginBottom': '10px',
                                'fontSize': '16px'
                            }),
                            # 文件上传组件
                            dcc.Upload(
                                id='upload-spmid-data',
                                children=html.Div([
                                    html.I(className="fas fa-cloud-upload-alt",
                                          style={'fontSize': '48px', 'color': '#007bff', 'marginBottom': '15px'}),
                                    html.Br(),
                                    html.Span('拖拽SPMID文件到此处或点击选择文件',
                                             style={'fontSize': '14px', 'color': '#6c757d'})
                                ], style={
                                    'textAlign': 'center',
                                    'padding': '30px',
                                    'border': '2px dashed #007bff',
                                    'borderRadius': '10px',
                                    'backgroundColor': '#f8f9fa',
                                    'cursor': 'pointer',
                                    'transition': 'all 0.3s ease'
                                }),
                                multiple=False
                            ),
                            html.Div(id='spmid-filename', style={'marginTop': '10px'})
                        ], width=6),

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

                            # 键ID筛选组件
                            html.Div([
                                html.Label("🔍 键位筛选", style={
                                    'fontWeight': 'bold',
                                    'color': '#2c3e50',
                                    'marginBottom': '10px',
                                    'fontSize': '16px'
                                }),
                                dcc.Dropdown(
                                    id='key-filter-dropdown',
                                    placeholder='选择要显示的键位ID（留空显示全部）',
                                    multi=True,
                                    style={'width': '100%', 'marginBottom': '10px'}
                                ),
                                html.Button('显示全部键位', id='btn-show-all-keys', n_clicks=0, 
                                          style={'marginBottom': '10px', 'width': '100%'}, 
                                          className='btn btn-outline-secondary btn-sm'),
                                html.Div(id='key-filter-status', 
                                        style={'fontSize': '12px', 'color': '#28a745', 'fontWeight': 'bold'})
                            ], style={'marginBottom': '20px'}),

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
                                dbc.ButtonGroup([
                                    dbc.Button([
                                        html.I(className="fas fa-chart-bar", style={'marginRight': '8px'}),
                                        "生成瀑布图"
                                    ], id='btn-waterfall', color='primary', size='lg'),
                                    dbc.Button([
                                        html.I(className="fas fa-file-alt", style={'marginRight': '8px'}),
                                        "生成报告"
                                    ], id='btn-report', color='success', size='lg')
                                ], style={'width': '100%'})
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
                    html.Div(id="waterfall-content", style={'padding': '20px'}, children=[
                        dcc.Graph(id='main-plot', figure=empty_figure, style={
                            "height": "1000px"
                        })
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
                                    id="close-modal",
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

                            # 模态框主体 - 左右分布的图表 + 合并图表
                            html.Div([
                                # 第一行：左右分布的图表
                                html.Div([
                                    # 左侧图表
                                    html.Div([
                                        html.H4("录制数据力度曲线", style={
                                            'textAlign': 'center',
                                            'color': '#2c3e50',
                                            'marginBottom': '15px',
                                            'fontWeight': 'bold'
                                        }),
                                        dcc.Graph(
                                            id='detail-plot',
                                            style={'height': '400px'},
                                            config={
                                                'displayModeBar': True,
                                                'displaylogo': False,
                                                'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d']
                                            }
                                        )
                                    ], style={
                                        'width': '48%',
                                        'float': 'left',
                                        'padding': '10px'
                                    }),

                                    # 右侧图表
                                    html.Div([
                                        html.H4("回放数据力度曲线", style={
                                            'textAlign': 'center',
                                            'color': '#2c3e50',
                                            'marginBottom': '15px',
                                            'fontWeight': 'bold'
                                        }),
                                        dcc.Graph(
                                            id='detail-plot2',
                                            style={'height': '400px'},
                                            config={
                                                'displayModeBar': True,
                                                'displaylogo': False,
                                                'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d']
                                            }
                                        )
                                    ], style={
                                        'width': '48%',
                                        'float': 'right',
                                        'padding': '10px'
                                    }),

                                    # 清除浮动
                                    html.Div(style={'clear': 'both'})
                                ]),

                                # 第二行：合并图表
                                html.Div([
                                    html.H4("合并对比力度曲线", style={
                                        'textAlign': 'center',
                                        'color': '#2c3e50',
                                        'marginTop': '20px',
                                        'marginBottom': '15px',
                                        'fontWeight': 'bold'
                                    }),
                                    dcc.Graph(
                                        id='detail-plot-combined',
                                        style={'height': '800px'},  # 两个图表的总高度
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

                            # 模态框底部
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
        ], fluid=True)

    ], style={
        'fontFamily': 'Arial, sans-serif',
        'backgroundColor': '#f8f9fa',
        'minHeight': '100vh'
    })


def create_report_layout(backend):
    """创建完整的报告分析布局"""
    summary = backend.get_summary_info()
    data_source = backend.current_filename or "未知数据源"

    return html.Div([
        # 下载组件 - 隐藏但必需
        dcc.Download(id='download-pdf'),

        dbc.Container([
            # 标题和PDF导出按钮
            dbc.Row([
                dbc.Col([
                    html.H2(f"分析报告 - {data_source}", className="text-center mb-3",
                           style={'color': '#2E86AB', 'fontWeight': 'bold', 'textShadow': '1px 1px 2px rgba(0,0,0,0.1)'}),
                ], width=8),
                dbc.Col([
                    html.Div([
                        dbc.Button([
                            html.I(className="fas fa-file-pdf", style={'marginRight': '8px'}),
                            "导出PDF报告"
                        ], id='btn-export-pdf', color='danger', size='sm', className='mb-2'),
                        html.Div(id='pdf-status')
                    ], className="text-end")
                ], width=4)
            ], className="mb-4"),

            # 数据统计概览
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
                            dbc.Row([
                                dbc.Col([
                                    html.Div([
                                        html.H3(f"{summary['total_notes']}", className="text-primary mb-1"),
                                        html.P("总检测数量", className="text-muted mb-0")
                                    ], className="text-center")
                                ], width=2),
                                dbc.Col([
                                    html.Div([
                                        html.H3(f"{summary['valid_notes']}", className="text-info mb-1"),
                                        html.P("有效音符", className="text-muted mb-0")
                                    ], className="text-center")
                                ], width=2),
                                dbc.Col([
                                    html.Div([
                                        html.H3(f"{summary['invalid_notes']}", className="text-secondary mb-1"),
                                        html.P("无效音符", className="text-muted mb-0")
                                    ], className="text-center")
                                ], width=2),
                                dbc.Col([
                                    html.Div([
                                        html.H3(f"{summary['multi_hammers']}", className="text-warning mb-1"),
                                        html.P("多锤异常", className="text-muted mb-0")
                                    ], className="text-center")
                                ], width=2),
                                dbc.Col([
                                    html.Div([
                                        html.H3(f"{summary['drop_hammers']}", className="text-danger mb-1"),
                                        html.P("丢锤异常", className="text-muted mb-0")
                                    ], className="text-center")
                                ], width=2),
                                dbc.Col([
                                    html.Div([
                                        html.H3(f"{summary['accuracy']:.1f}%", className="text-success mb-1"),
                                        html.P("准确率", className="text-muted mb-0")
                                    ], className="text-center")
                                ], width=2)
                            ])
                        ])
                    ], className="shadow-sm mb-4")
                ])
            ]),

            # 统计信息一行显示
            dbc.Row([
                dbc.Col([
                    html.Div(
                        f"多锤问题: {summary['multi_hammers_count']} 个  |  丢锤问题: {summary['drop_hammers_count']} 个  |  不发声锤子: {summary['silent_hammers_count']} 个  |  总计异常: {summary['total_errors']} 个",
                        className="text-center mb-3",
                        style={'fontSize': '16px', 'fontWeight': 'bold', 'color': '#495057',
                              'backgroundColor': '#f8f9fa', 'padding': '10px', 'borderRadius': '5px',
                              'border': '1px solid #dee2e6'}
                    )
                ], width=12)
            ]),

            # 主要内容区域
            dbc.Row([
                # 左侧：表格区域
                dbc.Col([
                    # 丢锤问题表格
                    html.Div([
                        dbc.Row([
                            dbc.Col([
                                html.H6("丢锤问题列表", className="mb-2",
                                       style={'color': '#721c24', 'fontWeight': 'bold', 'borderBottom': '2px solid #721c24', 'paddingBottom': '5px'}),
                            ], width=12)
                        ]),
                        dash_table.DataTable(
                            id='drop-hammers-table',
                            columns=[
                                {"name": "问题类型", "id": "problem_type"},
                                {"name": "数据类型", "id": "data_type"},
                                {"name": "键位", "id": "keyId"},
                                {"name": "按下时间", "id": "keyOn"},
                                {"name": "释放时间", "id": "keyOff"},
                                {"name": "均值", "id": "mean"},
                                {"name": "标准差", "id": "std"},
                                {"name": "最大值", "id": "max"},
                                {"name": "最小值", "id": "min"},
                                {"name": "index", "id": "index"},
                            ],
                            data=backend.get_drop_hammers_data(),
                            page_size=10,
                            style_cell={
                                'textAlign': 'center',
                                'fontSize': '10px',
                                'fontFamily': 'Arial',
                                'padding': '6px',
                                'overflow': 'hidden',
                                'textOverflow': 'ellipsis',
                            },
                            style_cell_conditional=[
                                {'if': {'column_id': 'problem_type'}, 'width': '15%'},
                                {'if': {'column_id': 'data_type'}, 'width': '12%'},
                                {'if': {'column_id': 'keyId'}, 'width': '10%'},
                                {'if': {'column_id': 'keyOn'}, 'width': '15%'},
                                {'if': {'column_id': 'keyOff'}, 'width': '15%'},
                                {'if': {'column_id': 'mean'}, 'width': '12%'},
                                {'if': {'column_id': 'std'}, 'width': '12%'},
                                {'if': {'column_id': 'max'}, 'width': '9%'},
                                {'if': {'column_id': 'min'}, 'width': '9%'},
                            ],
                            style_header={
                                'backgroundColor': '#f8d7da',
                                'fontWeight': 'bold',
                                'border': '1px solid #dee2e6',
                                'fontSize': '10px',
                                'color': '#721c24',
                                'textAlign': 'center'
                            },
                            style_data={
                                'border': '1px solid #dee2e6',
                                'fontSize': '9px'
                            },
                            style_data_conditional=[
                                {
                                    'if': {'filter_query': '{problem_type} = 丢锤'},
                                    'backgroundColor': '#f8d7da',
                                    'color': 'black',
                                },
                                {
                                    'if': {'filter_query': '{data_type} = record'},
                                    'fontWeight': 'bold'
                                },
                                {
                                    'if': {'filter_query': '{keyOn} = 无匹配'},
                                    'backgroundColor': '#f5f5f5',
                                    'color': '#6c757d',
                                    'fontStyle': 'italic'
                                }
                            ],
                            row_selectable="single",
                            selected_rows=[],
                            sort_action="native",
                            style_table={'height': 'calc(45vh - 120px)', 'overflowY': 'auto', 'border': '1px solid #dee2e6', 'borderRadius': '5px'}
                        ),
                    ], className="mb-3", style={'backgroundColor': '#ffffff', 'padding': '15px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),

                    # 多锤问题表格
                    html.Div([
                        dbc.Row([
                            dbc.Col([
                                html.H6("多锤问题列表", className="mb-2",
                                       style={'color': '#856404', 'fontWeight': 'bold', 'borderBottom': '2px solid #856404', 'paddingBottom': '5px'}),
                            ], width=12)
                        ]),
                        dash_table.DataTable(
                            id='multi-hammers-table',
                            columns=[
                                {"name": "问题类型", "id": "problem_type"},
                                {"name": "数据类型", "id": "data_type"},
                                {"name": "键位", "id": "keyId"},
                                {"name": "按下时间", "id": "keyOn"},
                                {"name": "释放时间", "id": "keyOff"},
                                {"name": "均值", "id": "mean"},
                                {"name": "标准差", "id": "std"},
                                {"name": "最大值", "id": "max"},
                                {"name": "最小值", "id": "min"},
                                {"name": "index", "id": "index"}
                            ],
                            data=backend.get_multi_hammers_data(),
                            page_size=10,
                            style_cell={
                                'textAlign': 'center',
                                'fontSize': '10px',
                                'fontFamily': 'Arial',
                                'padding': '6px',
                                'overflow': 'hidden',
                                'textOverflow': 'ellipsis',
                            },
                            style_cell_conditional=[
                                {'if': {'column_id': 'problem_type'}, 'width': '15%'},
                                {'if': {'column_id': 'data_type'}, 'width': '12%'},
                                {'if': {'column_id': 'keyId'}, 'width': '10%'},
                                {'if': {'column_id': 'keyOn'}, 'width': '15%'},
                                {'if': {'column_id': 'keyOff'}, 'width': '15%'},
                                {'if': {'column_id': 'mean'}, 'width': '12%'},
                                {'if': {'column_id': 'std'}, 'width': '12%'},
                                {'if': {'column_id': 'max'}, 'width': '9%'},
                                {'if': {'column_id': 'min'}, 'width': '9%'},
                            ],
                            style_header={
                                'backgroundColor': '#fff3cd',
                                'fontWeight': 'bold',
                                'border': '1px solid #dee2e6',
                                'fontSize': '10px',
                                'color': '#856404',
                                'textAlign': 'center'
                            },
                            style_data={
                                'border': '1px solid #dee2e6',
                                'fontSize': '9px'
                            },
                            style_data_conditional=[
                                {
                                    'if': {'filter_query': '{problem_type} = 多锤'},
                                    'backgroundColor': '#fff3cd',
                                    'color': 'black',
                                },
                                {
                                    'if': {'filter_query': '{data_type} = record'},
                                    'fontWeight': 'bold'
                                },
                                {
                                    'if': {'filter_query': '{keyOn} = 无匹配'},
                                    'backgroundColor': '#f5f5f5',
                                    'color': '#6c757d',
                                    'fontStyle': 'italic'
                                }
                            ],
                            row_selectable="single",
                            selected_rows=[],
                            sort_action="native",
                            style_table={'height': 'calc(45vh - 120px)', 'overflowY': 'auto', 'border': '1px solid #dee2e6', 'borderRadius': '5px'}
                        ),
                    ], className="mb-3", style={'backgroundColor': '#ffffff', 'padding': '15px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),

                    # 偏移对齐数据表格
                    html.Div([
                        dbc.Row([
                            dbc.Col([
                                html.H6("偏移对齐分析", className="mb-2",
                                       style={'color': '#6f42c1', 'fontWeight': 'bold', 'borderBottom': '2px solid #6f42c1', 'paddingBottom': '5px'}),
                            ], width=12)
                        ]),
                        dash_table.DataTable(
                            id='offset-alignment-table',
                            columns=[
                                {"name": "键位ID", "id": "key_id"},
                                {"name": "配对数", "id": "count"},
                                {"name": "中位数(ms)", "id": "median"},
                                {"name": "均值(ms)", "id": "mean"},
                                {"name": "标准差(ms)", "id": "std"}
                            ],
                            # todo
                            data=backend.get_offset_alignment_data(),
                            page_size=15,
                            style_cell={
                                'textAlign': 'center',
                                'fontSize': '10px',
                                'fontFamily': 'Arial',
                                'padding': '6px',
                                'overflow': 'hidden',
                                'textOverflow': 'ellipsis',
                            },
                            style_cell_conditional=[
                                {'if': {'column_id': 'key_id'}, 'width': '20%'},
                                {'if': {'column_id': 'count'}, 'width': '20%'},
                                {'if': {'column_id': 'median'}, 'width': '20%'},
                                {'if': {'column_id': 'mean'}, 'width': '20%'},
                                {'if': {'column_id': 'std'}, 'width': '20%'},
                            ],
                            style_header={
                                'backgroundColor': '#e2d9f3',
                                'fontWeight': 'bold',
                                'border': '1px solid #dee2e6',
                                'fontSize': '10px',
                                'color': '#6f42c1',
                                'textAlign': 'center'
                            },
                            style_data={
                                'border': '1px solid #dee2e6',
                                'fontSize': '9px'
                            },
                            style_data_conditional=[
                                {
                                    'if': {'filter_query': '{key_id} = 总体'},
                                    'backgroundColor': '#f8f9fa',
                                    'color': '#6f42c1',
                                    'fontWeight': 'bold'
                                }
                            ],
                            sort_action="native",
                            style_table={'height': 'calc(30vh - 100px)', 'overflowY': 'auto', 'border': '1px solid #dee2e6', 'borderRadius': '5px'}
                        ),
                    ], className="mb-3", style={'backgroundColor': '#ffffff', 'padding': '15px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
                ], width=6),

                # 右侧：图表和详情区域
                dbc.Col([
                    # 对比分析图
                    html.Div([
                        html.H6("对比分析图", className="mb-2",
                               style={'color': '#28a745', 'fontWeight': 'bold', 'borderBottom': '2px solid #28a745', 'paddingBottom': '5px'}),
                        html.Div(id="image-container", children=[
                            html.Div([
                                html.I(className="fas fa-chart-line", style={'fontSize': '36px', 'color': '#6c757d', 'marginBottom': '10px'}),
                                html.P("请选择左侧表格中的条目来查看对比图",
                                       className="text-muted text-center",
                                       style={'fontSize': '12px'})
                            ], className="d-flex flex-column align-items-center justify-content-center h-100")
                        ], style={'height': '380px', 'border': '2px dashed #dee2e6', 'borderRadius': '8px', 'backgroundColor': '#f8f9fa'})
                    ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '15px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),

                    # 详细数据信息
                    html.Div([
                        html.H6("详细数据信息", className="mb-2",
                               style={'color': '#17a2b8', 'fontWeight': 'bold', 'borderBottom': '2px solid #17a2b8', 'paddingBottom': '5px'}),
                        html.Div(id="detail-info", children=[
                            html.Div([
                                html.I(className="fas fa-info-circle", style={'fontSize': '24px', 'color': '#6c757d', 'marginBottom': '8px'}),
                                html.P("请选择左侧表格中的条目查看详细信息",
                                       className="text-muted text-center",
                                       style={'fontSize': '12px'})
                            ], className="d-flex flex-column align-items-center justify-content-center h-100")
                        ], style={'border': '1px solid #dee2e6', 'borderRadius': '8px', 'backgroundColor': '#ffffff', 'padding': '15px'})
                    ], style={'backgroundColor': '#f8f9fa', 'padding': '15px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'})
                ], width=6)
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
    if len(error_note.infos) > 0:
        record_info = error_note.infos[0]
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
                            html.Strong(f"{record_info.keyId}", style={'fontSize': '14px'})
                        ], width=6),
                        dbc.Col([
                            html.Small("持续时间", className="text-muted d-block"),
                            html.Strong(f"{record_info.keyOff - record_info.keyOn}", style={'fontSize': '14px'})
                        ], width=6)
                    ], className="mb-2"),
                    dbc.Row([
                        dbc.Col([
                            html.Small("按下时间", className="text-muted d-block"),
                            html.Span(f"{record_info.keyOn}", style={'fontSize': '12px'})
                        ], width=6),
                        dbc.Col([
                            html.Small("释放时间", className="text-muted d-block"),
                            html.Span(f"{record_info.keyOff}", style={'fontSize': '12px'})
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
    if len(error_note.infos) > 1:
        play_info = error_note.infos[1]
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
                            html.Strong(f"{play_info.keyId}", style={'fontSize': '14px'})
                        ], width=6),
                        dbc.Col([
                            html.Small("持续时间", className="text-muted d-block"),
                            html.Strong(f"{play_info.keyOff - play_info.keyOn}", style={'fontSize': '14px'})
                        ], width=6)
                    ], className="mb-2"),
                    dbc.Row([
                        dbc.Col([
                            html.Small("按下时间", className="text-muted d-block"),
                            html.Span(f"{play_info.keyOn}", style={'fontSize': '12px'})
                        ], width=6),
                        dbc.Col([
                            html.Small("释放时间", className="text-muted d-block"),
                            html.Span(f"{play_info.keyOff}", style={'fontSize': '12px'})
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
