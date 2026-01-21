#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
播放音轨对比分析页面
"""

from dash import html, dcc, dash_table
import dash_bootstrap_components as dbc
import json


def layout():
    """创建播放音轨对比页面布局"""
    
    return dbc.Container([
        # 页面标题
        dbc.Row([
            dbc.Col([
                html.H2([
                    html.I(className="bi bi-bar-chart-line me-2"),
                    "播放音轨对比分析"
                ], className="mb-3"),
                html.P([
                    "从全局文件管理中选择已上传的SPMID文件，对比不同播放音轨的时序和锤速差异"
                ], className="text-muted"),
                html.Hr()
            ])
        ], className="mb-4"),
        
        # 提示信息（如果没有文件）
        html.Div(
            id='track-comparison-file-prompt',
            children=[
                dbc.Alert([
                    html.I(className="bi bi-info-circle me-2"),
                    "请先在页面顶部的",
                    html.Strong(" 文件管理 ", className="mx-1"),
                    "区域上传至少2个SPMID文件"
                ], color="info", className="mb-4")
            ]
        ),
        
        # 音轨选择区域
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.I(className="bi bi-music-note-list me-2"),
                        "选择要对比的播放音轨"
                    ]),
                    dbc.CardBody([
                        html.Div(id='track-selection-content')
                    ])
                ], className="shadow-sm")
            ])
        ], className="mb-4"),
        
        # 对比设置区域
        html.Div(
            id='comparison-settings-area',
            children=[
                dbc.Row([
                    dbc.Col([
                        dbc.Card([
                            dbc.CardHeader([
                                html.I(className="bi bi-gear me-2"),
                                "对比配置"
                            ]),
                            dbc.CardBody([
                                html.Div(id='comparison-settings-content')
                            ])
                        ], className="shadow-sm")
                    ])
                ], className="mb-4")
            ],
            style={'display': 'none'}  # 初始隐藏
        ),
        
        # 对比结果区域
        html.Div(
            id='comparison-results-area',
            style={'display': 'none'}
        ),

        # 隐藏div用于存储当前表格状态（避免修改store）
        html.Div(
            id='current-table-state',
            style={'display': 'none'},
            children=json.dumps({'compare_name': None, 'grade_key': None})
        ),

        # Store用于存储准备好的表格数据（中间层）
        dcc.Store(id='track-comparison-table-data-store', data={}),

                # 详细对比表格区域（默认隐藏）
                html.Div(
                    id='track-comparison-detail-table-area',
                    style={'display': 'none', 'marginTop': '20px'},
                    children=[
                        html.H5("详细对比数据", className="mb-3"),

                        # 按键筛选器区域
                        html.Div(
                            id='track-comparison-key-filter-area',
                            style={'display': 'none', 'marginBottom': '15px'},  # 默认隐藏，与表格同步显示
                            children=[
                                dbc.Row([
                                    dbc.Col([
                                        html.Label("按键筛选:", className="form-label fw-bold me-2"),
                                        dcc.Dropdown(
                                            id='track-comparison-key-filter',  # 全局ID，因为只有一个筛选器
                                            options=[
                                                {'label': '请选择按键...', 'value': ''},
                                                {'label': '全部按键', 'value': 'all'}
                                                # 其他按键选项将在回调中动态添加
                                            ],
                                            value='',  # 默认不选择
                                            clearable=False,
                                            style={'width': '200px', 'display': 'inline-block'}
                                        )
                                    ], width='auto'),
                                    dbc.Col([
                                        html.Small(
                                            "选择特定按键查看其详细对比信息",
                                            className="text-muted"
                                        )
                                    ], width=True)
                                ], className="align-items-center")
                            ]
                        ),

                        # 表格容器 - 添加滚动容器确保表头和数据同步滚动
                        html.Div(
                            style={
                                'width': '100%',
                                'overflowX': 'auto',  # 确保容器级别的水平滚动
                                'border': '1px solid #dee2e6',
                                'borderRadius': '0.375rem'
                            },
                            children=[
                                dash_table.DataTable(
                    id='track-comparison-detail-datatable',
                    columns=[],
                    data=[],
                    page_action='native',
                    page_current=0,
                    page_size=20,
                    fixed_rows={'headers': True},  # 固定表头
                    active_cell=None,  # 启用active_cell功能
                    style_table={
                        'maxHeight': '350px',  # 稍微减少匹配数据表格高度
                        'overflowY': 'auto',
                        'overflowX': 'auto'
                    },
                    style_cell={
                        'textAlign': 'center',
                        'fontSize': '14px',
                        'fontFamily': 'Arial, sans-serif',
                        'padding': '8px',
                        'minWidth': '60px',
                        'cursor': 'pointer'  # 添加指针样式，提示可点击
                    },
                    style_header={
                        'backgroundColor': '#f8f9fa',
                        'fontWeight': 'bold',
                        'borderBottom': '2px solid #dee2e6',
                        'whiteSpace': 'normal',  # 允许表头文字换行
                        'textAlign': 'center',
                        'padding': '6px 4px',
                        'minHeight': '40px'  # 确保表头有足够高度显示换行文字
                    },
                    style_data_conditional=[
                        # 根据数据类型设置不同的背景色
                        {
                            'if': {'filter_query': '{数据类型} = "标准"'},
                            'backgroundColor': '#e8f5e8',  # 浅绿色背景
                            'color': '#000000'
                        },
                        {
                            'if': {'filter_query': '{数据类型} = "对比"'},
                            'backgroundColor': '#fff3cd',  # 浅黄色背景
                            'color': '#000000'
                        },
                        # 每组数据之间的分隔（浅灰色边框）
                        {
                            'if': {'filter_query': '{数据类型} = "对比"'},
                            'borderBottom': '1px solid #dee2e6'
                        },
                        # 差值列的特殊样式（空值时显示为灰色）
                        {
                            'if': {'column_id': ['keyon时间差', '锤击时间差', '持续时间差', '锤速差'], 'filter_query': '{数据类型} = "标准"'},
                            'backgroundColor': '#f8f9fa',
                            'color': '#6c757d'
                        },
                        # 悬停样式 - 提供视觉反馈
                        {
                            'if': {'state': 'active'},
                            'backgroundColor': 'rgba(0, 116, 217, 0.3)',
                            'border': '1px solid rgb(0, 116, 217)'
                        }
                    ]
                )
                            ]  # 结束表格容器
                        ),
                html.Hr(className="my-3"),

                # 异常匹配数据展示区域
                html.Div(
                    id='track-comparison-anomaly-area',
                    style={'display': 'none', 'marginTop': '20px', 'marginBottom': '20px'},
                    children=[
                        html.H5("异常匹配数据", className="mb-3"),
                        html.Div(
                            id='track-comparison-anomaly-empty',
                            style={'display': 'none', 'textAlign': 'center', 'padding': '40px', 'minHeight': '200px'},
                            children=[
                                html.P("数据为空", className="text-muted mb-0")
                            ]
                        ),
                        # 表格容器 - 添加滚动容器确保表头和数据同步滚动
                        html.Div(
                            style={
                                'width': '100%',
                                'overflowX': 'auto',  # 确保容器级别的水平滚动
                                'border': '1px solid #dee2e6',
                                'borderRadius': '0.375rem'
                            },
                            children=[
                                dash_table.DataTable(
                                    id='track-comparison-anomaly-table',
                            columns=[],
                            data=[],
                            page_action='native',
                            page_current=0,
                            page_size=20,
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
                                'borderBottom': '2px solid #dee2e6',
                                'whiteSpace': 'normal',  # 允许表头文字换行
                                'textAlign': 'center',
                                'padding': '6px 4px',
                                'minHeight': '40px'  # 确保表头有足够高度显示换行文字
                            },
                            style_data_conditional=[
                                # 根据数据类型设置不同的背景色
                                {
                                    'if': {'filter_query': '{数据类型} = "标准"'},
                                    'backgroundColor': '#e8f5e8',  # 浅绿色背景
                                    'color': '#000000'
                                },
                                {
                                    'if': {'filter_query': '{数据类型} = "对比"'},
                                    'backgroundColor': '#fff3cd',  # 浅黄色背景
                                    'color': '#000000'
                                },
                                # 每组数据之间的分隔（浅灰色边框）
                                {
                                    'if': {'filter_query': '{数据类型} = "对比"'},
                                    'borderBottom': '1px solid #dee2e6'
                                },
                                # 差值列的特殊样式（空值时显示为灰色）
                                {
                                    'if': {'column_id': ['keyon时间差', '锤击时间差', '持续时间差', '锤速差', '锤速还原百分比'], 'filter_query': '{数据类型} = "标准"'},
                                    'backgroundColor': '#f8f9fa',
                                    'color': '#6c757d'
                                },
                                # 悬停样式 - 提供视觉反馈
                                {
                                    'if': {'state': 'active'},
                                    'backgroundColor': 'rgba(0, 116, 217, 0.3)',
                                    'border': '1px solid rgb(0, 116, 217)'
                                }
                            ]
                        )
                            ]  # 结束表格容器
                        )
                    ]
                ),

                # 未匹配数据展示区域
                html.Div(
                    id='track-comparison-unmatched-area',
                    style={'display': 'none', 'marginTop': '30px', 'marginBottom': '30px'},  # 增加上下间距
                    children=[
                        html.H5("未匹配数据详情", className="mb-4"),

                        # 空状态显示
                        html.Div(
                            id='track-comparison-unmatched-empty',
                            style={'display': 'none', 'textAlign': 'center', 'padding': '40px', 'minHeight': '200px'},
                            children=[
                                html.P("数据为空", className="text-muted mb-0")
                            ]
                        ),

                        # 标准未匹配数据
                        html.Div(
                            id='track-comparison-unmatched-baseline-area',
                            style={'marginBottom': '30px', 'display': 'none'},  # 增加表格间距，默认隐藏
                            children=[
                                html.H6("标准音轨未匹配音符", className="text-warning mb-2"),
                                # 表格容器 - 添加滚动容器确保表头和数据同步滚动
                                html.Div(
                                    style={
                                        'width': '100%',
                                        'overflowX': 'auto',  # 确保容器级别的水平滚动
                                        'border': '1px solid #dee2e6',
                                        'borderRadius': '0.375rem'
                                    },
                                    children=[
                                        dash_table.DataTable(
                                    id='track-comparison-unmatched-baseline-table',
                                    columns=[],
                                    data=[],
                                    page_action='native',
                                    page_current=0,
                                    page_size=10,
                                    style_table={
                                        'maxHeight': '400px',  # 增加未匹配数据表格高度
                                        'overflowY': 'auto',
                                        'overflowX': 'auto'   # 添加水平滚动支持
                                    },
                                    style_cell={
                                        'textAlign': 'center',
                                        'fontSize': '12px',
                                        'padding': '6px',
                                        'minWidth': '80px'   # 设置最小宽度防止列被压缩
                                    },
                                    style_header={
                                        'backgroundColor': '#f8f9fa',
                                        'fontWeight': 'bold',
                                        'whiteSpace': 'normal',  # 允许表头文字换行
                                        'textAlign': 'center',
                                        'padding': '4px 2px',
                                        'minHeight': '35px'  # 确保表头有足够高度显示换行文字
                                    }
                                )
                                    ]  # 结束表格容器
                                )
                            ]
                        ),

                        # 对比未匹配数据
                        html.Div(
                            id='track-comparison-unmatched-compare-area',
                            style={'display': 'none'},  # 默认隐藏
                            children=[
                                html.H6("对比音轨未匹配音符", className="text-danger mb-2"),
                                # 表格容器 - 添加滚动容器确保表头和数据同步滚动
                                html.Div(
                                    style={
                                        'width': '100%',
                                        'overflowX': 'auto',  # 确保容器级别的水平滚动
                                        'border': '1px solid #dee2e6',
                                        'borderRadius': '0.375rem'
                                    },
                                    children=[
                                        dash_table.DataTable(
                                    id='track-comparison-unmatched-compare-table',
                                    columns=[],
                                    data=[],
                                    page_action='native',
                                    page_current=0,
                                    page_size=10,
                                    style_table={
                                        'maxHeight': '400px',  # 增加未匹配数据表格高度
                                        'overflowY': 'auto',
                                        'overflowX': 'auto'   # 添加水平滚动支持
                                    },
                                    style_cell={
                                        'textAlign': 'center',
                                        'fontSize': '12px',
                                        'padding': '6px',
                                        'minWidth': '80px'   # 设置最小宽度防止列被压缩
                                    },
                                    style_header={
                                        'backgroundColor': '#f8f9fa',
                                        'fontWeight': 'bold',
                                        'whiteSpace': 'normal',  # 允许表头文字换行
                                        'textAlign': 'center',
                                        'padding': '4px 2px',
                                        'minHeight': '35px'  # 确保表头有足够高度显示换行文字
                                    }
                                )
                                    ]  # 结束表格容器
                                )
                            ]
                        )
                    ]
                ),

                html.Div([
                    dbc.Button(
                        "隐藏表格",
                        id="hide-track-comparison-detail-table",
                        color="secondary",
                        size="sm",
                        className="me-2"
                    ),
                    html.Small(
                        "点击其他评级按钮可切换显示不同等级的数据",
                        className="text-muted"
                    )
                ], className="d-flex justify-content-between align-items-center")
            ]
        ),

        # 隐藏的数据存储
        dcc.Store(id='track-comparison-store', data={'selected_tracks': [], 'baseline_id': None})
        
    ], fluid=True, className="py-4")
