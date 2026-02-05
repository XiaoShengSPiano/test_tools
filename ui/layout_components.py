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
    """创建多算法上传区域 (现代精致卡片风格 - 回归原生结构)"""
    
    # 未激活标签：简洁文字风格，带悬停效果
    tab_style = {
        'padding': '12px 20px',
        'fontSize': '14px',
        'fontWeight': '500',
        'color': '#6c757d',
        'backgroundColor': 'transparent',
        'border': 'none',
        'borderBottom': '3px solid transparent',
        'transition': 'all 0.3s ease',
        'cursor': 'pointer',
    }
    
    # 激活标签：带亮蓝色下划线的现代风格
    active_tab_style = {
        'padding': '12px 20px',
        'fontSize': '14px',
        'fontWeight': 'bold',
        'color': '#0d6efd',
        'backgroundColor': 'transparent',
        'border': 'none',
        'borderBottom': '3px solid #0d6efd',
    }

    return dbc.Card([
        dbc.Tabs([
            # --- 标签页 1: 上传 ---
            dbc.Tab(
                label="📤 本地解析", 
                tab_id="tab-upload", 
                label_style=tab_style,
                active_label_style=active_tab_style,
                children=[
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                dcc.Upload(
                                    id='upload-multi-algorithm-data',
                                    children=html.Div([
                                        html.I(className="fas fa-cloud-upload-alt",
                                              style={'fontSize': '32px', 'color': '#0d6efd', 'marginBottom': '10px'}),
                                        html.Br(),
                                        html.Span('点击选择 或 拖拽 SPMID 文件至此处', 
                                                 style={'fontSize': '14px', 'color': '#495057'})
                                    ], style={
                                        'textAlign': 'center', 'padding': '30px', 'border': '2px dashed #0d6efd',
                                        'borderRadius': '12px', 'backgroundColor': '#f8fbff', 'cursor': 'pointer',
                                    }),
                                    multiple=True
                                )
                            ], width=9),
                            dbc.Col([
                                dbc.Button(
                                    [html.I(className="fas fa-redo me-2"), "重置"],
                                    id='reset-multi-algorithm-upload',
                                    color='secondary', outline=True, size='md',
                                    style={'height': '105px', 'width': '100%'},
                                )
                            ], width=3)
                        ]),
                        html.Div(id='multi-algorithm-upload-status', className="mt-3", 
                                children=html.Span("等待上传文件...", style={'color': '#6c757d', 'fontSize': '12px'})),
                        html.Div(id='multi-algorithm-file-list', 
                                style={'marginTop': '15px', 'maxHeight': '450px', 'overflowY': 'auto'})
                    ])
                ]
            ),
            
            # --- 标签页 2: 历史 ---
            dbc.Tab(
                label="🏛️ 历史记录", 
                tab_id="tab-history", 
                label_style=tab_style,
                active_label_style=active_tab_style,
                children=[
                    dbc.CardBody([
                        html.Div(id='history-browser-container', children=create_history_browser_area())
                    ])
                ]
            ),
        ], id="file-management-tabs", active_tab="tab-upload", className="px-3 pt-2 bg-light border-bottom")
    ], className="shadow-sm mb-4 border-light", style={'borderRadius': '12px', 'overflow': 'hidden'})


def create_history_browser_area():
    """创建并刷新历史记录浏览器"""
    return html.Div([
        dbc.Row([
            dbc.Col([
                dbc.Input(id='history-search-input', placeholder='搜索文件名...', size='sm', className='mb-2')
            ], width=8),
            dbc.Col([
                dbc.Button("刷新", id='refresh-history-btn', color='info', size='sm', className='w-100')
            ], width=4)
        ]),
        html.Div(id='history-table-container', children=[
            # 这里将来由回调填充 DataTable
            html.Div("正在连接数据库...", className='text-muted small text-center p-3')
        ], style={'maxHeight': '400px', 'overflowY': 'auto'})
    ])


def create_multi_algorithm_management_area():
    """创建多算法管理区域 (当前已加载到内存中的算法)"""
    return html.Div([
        html.Div([
            html.I(className="fas fa-microchip me-2", style={'color': '#17a2b8'}),
            html.Span("当前活跃算法 ", className="fw-bold text-info", style={'fontSize': '14px'}),
            dbc.Badge(id='active-algo-count-badge', color="info", pill=True, className="ms-2", children="0")
        ], className="mb-3 p-2 bg-light rounded border"),
        
        # 算法列表展示
        html.Div(id='algorithm-list', children=[], style={'maxHeight': '500px', 'overflowY': 'auto'}),
        
        html.Div(id='algorithm-management-status', 
                style={'fontSize': '12px', 'color': '#6c757d', 'marginTop': '10px'})
    ])
