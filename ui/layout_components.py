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
                                        style={'height': '1200px'},  # 两个图表的总高度
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
    source_info = backend.get_data_source_info()
    data_source = source_info.get('filename') or "未知数据源"

    # 计算延时误差统计指标（用于在数据概览下方显示）
    try:
        # 概览页的“平均延时”采用绝对值口径：使用 MAE 作为平均延时
        mae_0_1ms_for_avg = backend.get_mean_absolute_error()
        average_delay_ms = mae_0_1ms_for_avg / 10.0
    except Exception:
        average_delay_ms = 0.0
    
    # 计算已配对按键的方差（ms²）
    try:
        # 后端返回单位为(0.1ms)²，这里转换为ms²需要除以100
        variance_0_1ms_squared = backend.get_variance()
        variance_ms_squared = variance_0_1ms_squared / 100.0
    except Exception:
        variance_ms_squared = 0.0
    
    # 计算已配对按键的标准差（ms）
    try:
        # 后端返回单位为0.1ms，这里转换为ms需要除以10
        std_0_1ms = backend.get_standard_deviation()
        std_ms = std_0_1ms / 10.0
    except Exception:
        std_ms = 0.0
    
    # 计算平均绝对误差（MAE，ms）
    try:
        # 后端返回单位为0.1ms，这里转换为ms需要除以10
        mae_0_1ms = backend.get_mean_absolute_error()
        mae_ms = mae_0_1ms / 10.0
    except Exception:
        mae_ms = 0.0
    
    # 计算均方误差（MSE，ms²）
    try:
        # 后端返回单位为(0.1ms)²，这里转换为ms²需要除以100
        mse_0_1ms_squared = backend.get_mean_squared_error()
        mse_ms_squared = mse_0_1ms_squared / 100.0
    except Exception:
        mse_ms_squared = 0.0
    
    # 计算平均误差（ME，ms，带符号）
    try:
        # 后端返回单位为0.1ms，这里转换为ms需要除以10
        me_0_1ms = backend.get_mean_error()
        me_ms = me_0_1ms / 10.0
    except Exception:
        me_ms = 0.0
    
    

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
                            # 第一行：基础统计指标（准确率、丢锤数、多锤数、已配对音符数）
                            dbc.Row([
                                dbc.Col([
                                    html.Div([
                                        html.H3(f"{summary['accuracy']:.1f}%", className="text-success mb-1"),
                                        html.P("准确率", className="text-muted mb-0"),
                                        html.Small("成功匹配音符数/总有效音符数", className="text-muted", style={'fontSize': '10px'})
                                    ], className="text-center")
                                ], width=3),
                                dbc.Col([
                                    html.Div([
                                        html.H3(f"{summary['drop_hammers']}", className="text-warning mb-1"),
                                        html.P("丢锤数", className="text-muted mb-0"),
                                        html.Small("录制有但播放没有", className="text-muted", style={'fontSize': '10px'})
                                    ], className="text-center")
                                ], width=3),
                                dbc.Col([
                                    html.Div([
                                        html.H3(f"{summary['multi_hammers']}", className="text-info mb-1"),
                                        html.P("多锤数", className="text-muted mb-0"),
                                        html.Small("播放有但录制没有", className="text-muted", style={'fontSize': '10px'})
                                    ], className="text-center")
                                ], width=3),
                                dbc.Col([
                                    html.Div([
                                        html.H3(f"{summary.get('matching_analysis', {}).get('matched_pairs', 0)}", className="text-secondary mb-1"),
                                        html.P("已配对音符数", className="text-muted mb-0"),
                                        html.Small("成功匹配的record-play配对数量", className="text-muted", style={'fontSize': '10px'})
                                    ], className="text-center")
                                ], width=3)
                            ])
                        ])
                    ], className="shadow-sm mb-4")
                ])
            ]),
        
        # 延时误差统计指标 - 在数据概览下方（之前删掉的数据）
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
                        # 第一行：平均延时、总体方差、总体标准差、平均绝对误差
                        dbc.Row([
                            dbc.Col([
                                html.Div([
                                    html.H3(f"{average_delay_ms:.2f} ms", className="text-primary mb-1"),
                                    html.P("平均延时（绝对值口径，等同MAE）", className="text-muted mb-0"),
                                    html.Small("平均(|keyon_offset|)，用于衡量误差大小，避免正负抵消", className="text-muted", style={'fontSize': '10px'})
                                ], className="text-center")
                            ], width=3),
                            dbc.Col([
                                html.Div([
                                    html.H3(f"{variance_ms_squared:.2f} ms²", className="text-danger mb-1"),
                                    html.P("总体方差", className="text-muted mb-0"),
                                    html.Small("所有已匹配按键对的keyon_offset的总体方差", className="text-muted", style={'fontSize': '10px'})
                                ], className="text-center")
                            ], width=3),
                            dbc.Col([
                                html.Div([
                                    html.H3(f"{std_ms:.2f} ms", className="text-info mb-1"),
                                    html.P("总体标准差", className="text-muted mb-0"),
                                    html.Small("所有已匹配按键对的keyon_offset的总体标准差", className="text-muted", style={'fontSize': '10px'})
                                ], className="text-center")
                            ], width=3),
                            dbc.Col([
                                html.Div([
                                    html.H3(f"{mae_ms:.2f} ms", className="text-warning mb-1"),
                                    html.P("平均绝对误差(MAE)", className="text-muted mb-0"),
                                    html.Small("已匹配按键对的延时绝对值的平均", className="text-muted", style={'fontSize': '10px'})
                                ], className="text-center")
                            ], width=3)
                        ], className="mb-3"),
                        
                        # 第二行：均方误差、平均误差
                        dbc.Row([
                            dbc.Col([
                                html.Div([
                                    html.H3(f"{mse_ms_squared:.2f} ms²", className="text-info mb-1"),
                                    html.P("均方误差(MSE)", className="text-muted mb-0"),
                                    html.Small("所有匹配对延时平方的平均", className="text-muted", style={'fontSize': '10px'})
                                ], className="text-center")
                            ], width=3),
                            dbc.Col([
                                html.Div([
                                    html.H3(f"{me_ms:.2f} ms", className="text-secondary mb-1"),
                                    html.P("平均误差(ME)（带符号）", className="text-muted mb-0"),
                                    html.Small("mean(keyon_offset)，反映系统性提前/滞后方向，不等同平均延时", className="text-muted", style={'fontSize': '10px'})
                                ], className="text-center")
                            ], width=3),
                            dbc.Col([], width=6)  # 占位，保持布局平衡
                        ])
                    ])
                ], className="shadow-sm mb-4")
            ], width=12)
        ]),
        
        # 延时与按键差异分析区域（EDA）
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H4([
                            html.I(className="fas fa-chart-line", style={'marginRight': '10px', 'color': '#1976d2'}),
                            "延时与按键差异分析（EDA）"
                        ], className="mb-0")
                    ]),
                    dbc.CardBody([
                        # EDA分析区域（已移除抖动点图，使用散点图替代）
                        html.Div([
                            html.P("延时与按键差异分析请参考下方的散点图", className="text-muted", style={'fontSize': '14px', 'textAlign': 'center', 'padding': '20px'})
                        ]),
                    ])
                ], className="shadow-sm mb-4")
            ], width=12)
        ]),
        
        # 柱状图分析区域 - 独立全宽区域
        dbc.Row([
            dbc.Col([
                # 偏移对齐分析柱状图（自动生成）
                html.Div([
                    dbc.Row([
                        dbc.Col([
                            html.H6("偏移对齐分析柱状图", className="mb-2",
                                   style={'color': '#6f42c1', 'fontWeight': 'bold', 'borderBottom': '2px solid #6f42c1', 'paddingBottom': '5px'}),
                        ], width=12)
                    ]),
                    dcc.Graph(
                        id='offset-alignment-plot',
                        figure={},
                        style={'height': '2200px'}  # 增大高度以匹配后端图表高度
                    ),
                ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
                
            ], width=12)
        ]),
        
        # 按键与延时散点图区域 - 在柱状图下方，表格上方
        dbc.Row([
            dbc.Col([
                html.Div([
                    dbc.Row([
                        dbc.Col([
                            html.H6("按键与延时散点图", className="mb-2",
                                   style={'color': '#1976d2', 'fontWeight': 'bold', 'borderBottom': '2px solid #1976d2', 'paddingBottom': '5px'}),
                        ], width=12)
                    ]),
                    dcc.Graph(
                        id='key-delay-scatter-plot',
                        figure={},
                        style={'height': '500px'}
                    ),
                ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
                
            ], width=12)
        ]),
        
        # 锤速与延时散点图区域 - 在按键与延时散点图下方，表格上方
        dbc.Row([
            dbc.Col([
                html.Div([
                    dbc.Row([
                        dbc.Col([
                            html.H6("锤速与延时散点图", className="mb-2",
                                   style={'color': '#d32f2f', 'fontWeight': 'bold', 'borderBottom': '2px solid #d32f2f', 'paddingBottom': '5px'}),
                        ], width=12)
                    ]),
                    dcc.Graph(
                        id='hammer-velocity-delay-scatter-plot',
                        figure={},
                        style={'height': '500px'}
                    ),
                ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
                
            ], width=12)
        ]),
        
        # 按键与锤速散点图区域（颜色表示延时）- 在锤速与延时散点图下方，表格上方
        dbc.Row([
            dbc.Col([
                html.Div([
                    dbc.Row([
                        dbc.Col([
                            html.H6("按键与锤速散点图（颜色表示延时）", className="mb-2",
                                   style={'color': '#7b1fa2', 'fontWeight': 'bold', 'borderBottom': '2px solid #7b1fa2', 'paddingBottom': '5px'}),
                        ], width=12)
                    ]),
                    dcc.Graph(
                        id='key-hammer-velocity-scatter-plot',
                        figure={},
                        style={'height': '500px'}
                    ),
                ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
                
            ], width=12)
        ]),

        # 延时分布直方图（附正态拟合曲线）- 在按键与锤速散点图下方，表格上方
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
        
        # 延时与按键关系分析区域 - 已注释，因为箱线图与柱状图的均值子图重复
        # dbc.Row([
        #     dbc.Col([
        #         html.Div([
        #             dbc.Row([
        #                 dbc.Col([
        #                     html.H5("📊 延时与按键关系分析", className="mb-3",
        #                            style={'color': '#1976d2', 'fontWeight': 'bold', 'fontSize': '20px', 'borderBottom': '3px solid #1976d2', 'paddingBottom': '10px'}),
        #                 ], width=12)
        #             ]),
        #             # 箱线图
        #             dbc.Row([
        #                 dbc.Col([
        #                     html.H6("各按键延时分布箱线图", className="mb-2",
        #                            style={'color': '#1976d2', 'fontWeight': 'bold'}),
        #                     dcc.Graph(
        #                         id='delay-by-key-boxplot',
        #                         figure={},
        #                         style={'height': '500px'}
        #                     ),
        #                 ], width=12)
        #             ], className="mb-3"),
        #             # 统计分析结果表格
        #             dbc.Row([
        #                 dbc.Col([
        #                     html.H6("统计分析结果", className="mb-2",
        #                            style={'color': '#1976d2', 'fontWeight': 'bold'}),
        #                     html.Div(id='delay-by-key-analysis-stats', children=[])
        #                 ], width=12)
        #             ])
        #         ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
        #     ], width=12)
        # ]),
        
        # 延时与锤速关系分析区域 - 已注释
        # dbc.Row([
        #     dbc.Col([
        #         html.Div([
        #             dbc.Row([
        #                 dbc.Col([
        #                     html.H5("📈 延时与锤速关系分析", className="mb-3",
        #                            style={'color': '#d32f2f', 'fontWeight': 'bold', 'fontSize': '20px', 'borderBottom': '3px solid #d32f2f', 'paddingBottom': '10px'}),
        #                 ], width=12)
        #             ]),
        #             # 散点图+回归线
        #             dbc.Row([
        #                 dbc.Col([
        #                     html.H6("延时与锤速散点图（含回归分析）", className="mb-2",
        #                            style={'color': '#d32f2f', 'fontWeight': 'bold'}),
        #                     dcc.Graph(
        #                         id='delay-by-velocity-analysis-plot',
        #                         figure={},
        #                         style={'height': '500px'}
        #                     ),
        #                 ], width=12)
        #             ], className="mb-3"),
        #             # 统计分析结果
        #             dbc.Row([
        #                 dbc.Col([
        #                     html.H6("相关性分析结果", className="mb-2",
        #                            style={'color': '#d32f2f', 'fontWeight': 'bold'}),
        #                     html.Div(id='delay-by-velocity-analysis-stats', children=[])
        #                 ], width=12)
        #             ])
        #         ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
        #     ], width=12)
        # ]),
            
            # 主要内容区域：丢锤和多锤表格左右并排显示
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
                            # 去掉分页，显示所有数据
                            page_action='none',
                            style_cell={
                                'textAlign': 'center',
                                'fontSize': '14px',  # 增大字体从10px到14px
                                'fontFamily': 'Arial, sans-serif',
                                'padding': '10px',  # 增大内边距从6px到10px
                                'overflow': 'hidden',
                                'textOverflow': 'ellipsis',
                                'minWidth': '80px',
                            },
                            style_cell_conditional=[
                                {'if': {'column_id': 'data_type'}, 'width': '16%'},
                                {'if': {'column_id': 'keyId'}, 'width': '14%'},
                                {'if': {'column_id': 'keyOn'}, 'width': '18%'},
                                {'if': {'column_id': 'keyOff'}, 'width': '18%'},
                                {'if': {'column_id': 'index'}, 'width': '12%'},
                                {'if': {'column_id': 'analysis_reason'}, 'width': '22%'},
                            ],
                            style_header={
                                'backgroundColor': '#f8d7da',
                                'fontWeight': 'bold',
                                'border': '2px solid #dee2e6',
                                'fontSize': '15px',  # 增大表头字体从10px到15px
                                'color': '#721c24',
                                'textAlign': 'center',
                                'padding': '12px',  # 增大表头内边距
                                'whiteSpace': 'normal',
                                'height': 'auto'
                            },
                            style_data={
                                'border': '1px solid #dee2e6',
                                'fontSize': '14px',  # 增大数据字体从9px到14px
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
                            row_selectable=False,  # 禁用行选择，不显示选择列
                            sort_action="native",
                            filter_action="none",  # 禁用筛选功能，不显示过滤行
                            style_table={
                                'height': 'calc(75vh - 200px)',  # 增大表格高度
                                'overflowY': 'auto', 
                                'overflowX': 'auto',
                                'border': '2px solid #dee2e6', 
                                'borderRadius': '8px',
                                'minHeight': '400px'
                            }
                        ),
                    ], style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '10px', 'boxShadow': '0 4px 12px rgba(0,0,0,0.15)', 'height': '100%'}),
                ], width=6, className="pr-2"),  # 左侧列，宽度50%
                
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
                            # 去掉分页，显示所有数据
                            page_action='none',
                            style_cell={
                                'textAlign': 'center',
                                'fontSize': '14px',  # 增大字体从10px到14px
                                'fontFamily': 'Arial, sans-serif',
                                'padding': '10px',  # 增大内边距从6px到10px
                                'overflow': 'hidden',
                                'textOverflow': 'ellipsis',
                                'minWidth': '80px',
                            },
                            style_cell_conditional=[
                                {'if': {'column_id': 'data_type'}, 'width': '16%'},
                                {'if': {'column_id': 'keyId'}, 'width': '14%'},
                                {'if': {'column_id': 'keyOn'}, 'width': '18%'},
                                {'if': {'column_id': 'keyOff'}, 'width': '18%'},
                                {'if': {'column_id': 'index'}, 'width': '12%'},
                                {'if': {'column_id': 'analysis_reason'}, 'width': '22%'},
                            ],
                            style_header={
                                'backgroundColor': '#fff3cd',
                                'fontWeight': 'bold',
                                'border': '2px solid #dee2e6',
                                'fontSize': '15px',  # 增大表头字体从10px到15px
                                'color': '#856404',
                                'textAlign': 'center',
                                'padding': '12px',  # 增大表头内边距
                                'whiteSpace': 'normal',
                                'height': 'auto'
                            },
                            style_data={
                                'border': '1px solid #dee2e6',
                                'fontSize': '14px',  # 增大数据字体从9px到14px
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
                            row_selectable=False,  # 禁用行选择，不显示选择列
                            sort_action="native",
                            filter_action="none",  # 禁用筛选功能，不显示过滤行
                            style_table={
                                'height': 'calc(75vh - 200px)',  # 增大表格高度
                                'overflowY': 'auto', 
                                'overflowX': 'auto',
                                'border': '2px solid #dee2e6', 
                                'borderRadius': '8px',
                                'minHeight': '400px'
                            }
                        ),
                    ], style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '10px', 'boxShadow': '0 4px 12px rgba(0,0,0,0.15)', 'height': '100%'}),
                ], width=6, className="pl-2"),  # 右侧列，宽度50%
            ], className="mb-4"),
            
            # 无效音符统计表格（单独一行）
            dbc.Row([
                dbc.Col([

                    # 无效音符统计表格
                    html.Div([
                        dbc.Row([
                            dbc.Col([
                                html.H6("无效音符统计", className="mb-2",
                                       style={'color': '#6c757d', 'fontWeight': 'bold', 'borderBottom': '2px solid #6c757d', 'paddingBottom': '5px'}),
                            ], width=12)
                        ]),
                        dash_table.DataTable(
                            id='invalid-notes-table',
                            columns=[
                                {"name": "数据类型", "id": "data_type"},
                                {"name": "总音符数", "id": "total_notes"},
                                {"name": "有效音符", "id": "valid_notes"},
                                {"name": "无效音符", "id": "invalid_notes"},
                                {"name": "持续时间过短", "id": "duration_too_short"},
                                {"name": "数据为空", "id": "empty_data"},
                                {"name": "不发声音符", "id": "silent_notes"},
                                {"name": "其他错误", "id": "other_errors"}
                            ],
                            data=backend.get_invalid_notes_table_data(),
                            page_action='none',  # 去掉分页，显示所有数据
                            style_cell={
                                'textAlign': 'center',
                                'fontSize': '14px',  # 增大字体从10px到14px
                                'fontFamily': 'Arial, sans-serif',
                                'padding': '10px',  # 增大内边距从6px到10px
                                'overflow': 'hidden',
                                'textOverflow': 'ellipsis',
                                'minWidth': '100px',
                            },
                            style_cell_conditional=[
                                {'if': {'column_id': 'data_type'}, 'width': '15%'},
                                {'if': {'column_id': 'total_notes'}, 'width': '13%'},
                                {'if': {'column_id': 'valid_notes'}, 'width': '13%'},
                                {'if': {'column_id': 'invalid_notes'}, 'width': '13%'},
                                {'if': {'column_id': 'duration_too_short'}, 'width': '15%'},
                                {'if': {'column_id': 'empty_data'}, 'width': '12%'},
                                {'if': {'column_id': 'silent_notes'}, 'width': '12%'},
                                {'if': {'column_id': 'other_errors'}, 'width': '10%'},
                            ],
                            style_header={
                                'backgroundColor': '#e9ecef',
                                'fontWeight': 'bold',
                                'border': '2px solid #dee2e6',
                                'fontSize': '15px',  # 增大表头字体从10px到15px
                                'color': '#495057',
                                'textAlign': 'center',
                                'padding': '12px',  # 增大表头内边距
                                'whiteSpace': 'normal',
                                'height': 'auto'
                            },
                            style_data={
                                'border': '1px solid #dee2e6',
                                'fontSize': '14px',  # 增大数据字体从9px到14px
                                'padding': '10px'
                            },
                            style_data_conditional=[
                                {
                                    'if': {'filter_query': '{data_type} = 录制数据'},
                                    'backgroundColor': '#f8f9fa',
                                    'fontWeight': 'bold'
                                },
                                {
                                    'if': {'filter_query': '{data_type} = 播放数据'},
                                    'backgroundColor': '#ffffff'
                                },
                                {
                                    'if': {'row_index': 'odd'},
                                    'backgroundColor': '#fafafa'
                                }
                            ],
                            sort_action="native",
                            filter_action="none",  # 禁用筛选功能，不显示过滤行
                            style_table={
                                'height': 'calc(40vh - 120px)',  # 增大表格高度
                                'overflowY': 'auto', 
                                'overflowX': 'auto',
                                'border': '2px solid #dee2e6', 
                                'borderRadius': '8px',
                                'minHeight': '250px'
                            }
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
                                {"name": "标准差(ms)", "id": "std"},
                                {"name": "方差(ms²)", "id": "variance"},
                                {"name": "最小值(ms)", "id": "min"},
                                {"name": "最大值(ms)", "id": "max"},
                                {"name": "极差(ms)", "id": "range"},
                                {"name": "状态", "id": "status"}
                            ],
                            data=backend.get_offset_alignment_data(),
                            page_action='none',  # 去掉分页，显示所有数据
                            style_cell={
                                'textAlign': 'center',
                                'fontSize': '14px',  # 增大字体从10px到14px
                                'fontFamily': 'Arial, sans-serif',
                                'padding': '10px',  # 增大内边距从6px到10px
                                'overflow': 'hidden',
                                'textOverflow': 'ellipsis',
                                'minWidth': '100px',
                            },
                            style_cell_conditional=[
                                {'if': {'column_id': 'key_id'}, 'width': '9%'},
                                {'if': {'column_id': 'count'}, 'width': '9%'},
                                {'if': {'column_id': 'median'}, 'width': '9%'},
                                {'if': {'column_id': 'mean'}, 'width': '9%'},
                                {'if': {'column_id': 'std'}, 'width': '9%'},
                                {'if': {'column_id': 'variance'}, 'width': '10%'},
                                {'if': {'column_id': 'min'}, 'width': '9%'},
                                {'if': {'column_id': 'max'}, 'width': '9%'},
                                {'if': {'column_id': 'range'}, 'width': '9%'},
                                {'if': {'column_id': 'status'}, 'width': '18%'},
                            ],
                            style_header={
                                'backgroundColor': '#e2d9f3',
                                'fontWeight': 'bold',
                                'border': '2px solid #dee2e6',
                                'fontSize': '15px',  # 增大表头字体从10px到15px
                                'color': '#6f42c1',
                                'textAlign': 'center',
                                'padding': '12px',  # 增大表头内边距
                                'whiteSpace': 'normal',
                                'height': 'auto'
                            },
                            style_data={
                                'border': '1px solid #dee2e6',
                                'fontSize': '14px',  # 增大数据字体从9px到14px
                                'padding': '10px'
                            },
                            style_data_conditional=[
                                {
                                    'if': {'filter_query': '{key_id} = 总体'},
                                    'backgroundColor': '#f8f9fa',
                                    'color': '#6f42c1',
                                    'fontWeight': 'bold'
                                },
                                {
                                    'if': {'filter_query': '{key_id} = 汇总'},
                                    'backgroundColor': '#e3f2fd',
                                    'fontWeight': 'bold',
                                    'color': '#1976d2'
                                },
                                {
                                    'if': {'filter_query': '{status} = matched'},
                                    'backgroundColor': '#d4edda',
                                    'color': '#155724'
                                },
                                {
                                    'if': {'filter_query': '{status} contains invalid'},
                                    'backgroundColor': '#f8d7da',
                                    'color': '#721c24'
                                }
                            ],
                            sort_action="native",
                            filter_action="none",  # 禁用筛选功能，不显示过滤行
                            style_table={
                                'height': 'calc(50vh - 150px)',  # 增大表格高度
                                'overflowY': 'auto', 
                                'overflowX': 'auto',
                                'border': '2px solid #dee2e6', 
                                'borderRadius': '8px',
                                'minHeight': '300px'
                            }
                        ),
                    ], className="mb-3", style={'backgroundColor': '#ffffff', 'padding': '15px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
                    
                    
                ], width=12)  # 改为占满整行，删除右侧的对比分析图和详细数据信息
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
