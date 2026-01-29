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