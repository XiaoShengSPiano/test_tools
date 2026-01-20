#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
播放音轨对比分析页面
"""

from dash import html, dcc, dash_table
import dash_bootstrap_components as dbc


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

        # 详细对比表格区域（默认隐藏）
        html.Div(
            id='track-comparison-detail-table-area',
            style={'display': 'none', 'marginTop': '20px'},
            children=[
                html.H5("详细对比数据", className="mb-3"),
                dash_table.DataTable(
                    id='track-comparison-detail-datatable',
                    columns=[],
                    data=[],
                    page_action='none',
                    fixed_rows={'headers': True},  # 固定表头
                    active_cell=None,  # 启用active_cell功能
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
                        'minWidth': '80px',
                        'cursor': 'pointer'  # 添加指针样式，提示可点击
                    },
                    style_header={
                        'backgroundColor': '#f8f9fa',
                        'fontWeight': 'bold',
                        'borderBottom': '2px solid #dee2e6'
                    },
                    style_data_conditional=[
                        # 交替行颜色区分（模拟原来的录制/播放行区分）
                        {
                            'if': {'row_index': 'even'},
                            'backgroundColor': '#ffffff',  # 白色背景
                            'color': '#000000'
                        },
                        {
                            'if': {'row_index': 'odd'},
                            'backgroundColor': '#e3f2fd',   # 浅蓝色背景
                            'color': '#000000'
                        },
                        # 不同按键之间的分隔（浅灰色边框）
                        {
                            'if': {'row_index': 'odd'},
                            'borderBottom': '1px solid #e0e0e0'
                        },
                        # 悬停样式 - 提供视觉反馈
                        {
                            'if': {'state': 'active'},
                            'backgroundColor': 'rgba(0, 116, 217, 0.3)',
                            'border': '1px solid rgb(0, 116, 217)'
                        }
                    ]
                ),
                html.Hr(className="my-3"),
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
