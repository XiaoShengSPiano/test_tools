"""
应用管理器 - 单例管理 HistoryManager、SessionManager、Dash 应用及布局/回调注册
"""
import os
from typing import Optional

import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State

from database.history_manager import SQLiteHistoryManager
from backend.session_manager import SessionManager
from ui.callbacks import register_callbacks
from utils.logger import Logger

logger = Logger.get_logger()

# 运行常量
HOST = '0.0.0.0'
PORT = 10000
DEBUG = True


class ApplicationManager:
    """应用管理器 - 使用单例模式管理核心组件"""

    _instance: Optional['ApplicationManager'] = None
    _history_manager: Optional[SQLiteHistoryManager] = None
    _session_manager: Optional[SessionManager] = None
    _app: Optional[dash.Dash] = None

    def __new__(cls) -> 'ApplicationManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def history_manager(self) -> SQLiteHistoryManager:
        """获取历史管理器单例 (Parquet & Database)"""
        if self._history_manager is None:
            self._history_manager = SQLiteHistoryManager()
        return self._history_manager

    @property
    def session_manager(self) -> SessionManager:
        """获取会话管理器单例"""
        if self._session_manager is None:
            self._session_manager = SessionManager(self.history_manager)
        return self._session_manager

    @property
    def app(self) -> dash.Dash:
        """获取 Dash 应用单例"""
        if self._app is None:
            self._app = self._create_app()
        return self._app

    def _create_app(self) -> dash.Dash:
        """创建并配置 Dash 应用"""
        app = dash.Dash(
            __name__,
            external_stylesheets=[
                dbc.themes.BOOTSTRAP,
                "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css",
            ],
            suppress_callback_exceptions=True,
        )

        from ui.components.navigation import create_navbar

        app.layout = dbc.Container([
            dcc.Location(id='url', refresh=False),
            dcc.Store(id='session-id', storage_type='session'),
            dcc.Store(id='current-clicked-point-info', data=None),
            dcc.Store(id='multi-algorithm-files-store', data={'contents': [], 'filenames': []}),
            dcc.Store(id='algorithm-list-trigger', data=0),
            dcc.Store(id='algorithm-management-trigger', data=0),
            dcc.Store(id='active-algorithm-store', storage_type='session'),
            dcc.Store(id='grade-detail-datatable-indices', data=[]),
            create_navbar(),
            self._create_global_file_management(),
            html.Div(id='page-content'),
            html.Div(
                id='key-curves-modal',
                style={'display': 'none'},
                children=[
                    html.Div(
                        id='key-curves-modal-content',
                        children=[
                            html.Button(
                                '×', id='close-key-curves-modal',
                                style={
                                    'position': 'absolute', 'right': '20px', 'top': '20px',
                                    'fontSize': '30px', 'background': 'none', 'border': 'none',
                                    'color': 'white', 'cursor': 'pointer', 'zIndex': '10000',
                                },
                            ),
                            html.Div(id='key-curves-comparison-container'),
                            dbc.Button(
                                '关闭', id='close-key-curves-modal-btn',
                                color='secondary', size='lg',
                                style={'position': 'absolute', 'bottom': '30px', 'right': '30px'},
                            ),
                        ],
                    ),
                ],
            ),
            html.Div([
                html.Div([
                    html.Div([
                        html.H4("评级统计曲线对比", style={'margin': '0', 'padding': '10px 20px', 'borderBottom': '1px solid #dee2e6'}),
                        html.Button("×", id="close-grade-detail-curves-modal", className="close", style={
                            'position': 'absolute', 'right': '15px', 'top': '10px', 'fontSize': '28px',
                            'fontWeight': 'bold', 'lineHeight': '1', 'color': '#000', 'textShadow': '0 1px 0 #fff',
                            'opacity': '0.5', 'background': 'none', 'border': 'none', 'cursor': 'pointer',
                        }),
                    ], style={'position': 'relative', 'borderBottom': '1px solid #dee2e6'}),
                    html.Div([
                        html.Div(id='grade-detail-curves-comparison-container', children=[]),
                    ], id='grade-detail-curves-modal-content', className="modal-body", style={
                        'padding': '10px 20px 20px 20px', 'maxHeight': '90vh', 'overflowY': 'auto',
                    }),
                ], style={
                    'position': 'relative', 'backgroundColor': 'white', 'borderRadius': '8px',
                    'boxShadow': '0 4px 20px rgba(0,0,0,0.3)', 'width': '90%', 'maxWidth': '1200px',
                    'maxHeight': '90vh', 'display': 'flex', 'flexDirection': 'column',
                }),
            ], id="grade-detail-curves-modal", className="modal", style={
                'display': 'none', 'position': 'fixed', 'zIndex': '9999', 'left': '0', 'top': '0',
                'width': '100%', 'height': '100%', 'backgroundColor': 'rgba(0,0,0,0.6)',
                'backdropFilter': 'blur(5px)', 'alignItems': 'center', 'justifyContent': 'center',
            }),
            # 隐藏的全局触发器 - 用于满足全局回调的 Input 需求
            html.Div(id='report-content', style={'display': 'none'}),
            # 隐藏的全局图表 - 用于满足旧回调对 main-plot 的 Output 需求
            dcc.Graph(id='main-plot', style={'display': 'none'})
        ], fluid=True)

        self._register_page_routing(app)
        self._register_global_file_management_callbacks(app)
        self._register_page_callbacks(app)
        register_callbacks(app, self.session_manager, self.history_manager)
        return app

    def _create_global_file_management(self):
        """创建全局文件管理区域（可折叠）"""
        from ui.layout_components import create_multi_algorithm_upload_area, create_multi_algorithm_management_area

        return dbc.Container([
            dbc.Card([
                dbc.CardHeader([
                    html.Div([
                        html.H6([
                            html.I(className="fas fa-folder-open me-2", style={'color': '#ff9800'}),
                            "文件管理",
                        ], className="mb-0 d-inline-block"),
                        html.Span(" · ", className="mx-2 text-muted"),
                        html.Small("全局管理SPMID文件", className="text-muted"),
                    ], className="d-inline-block"),
                    dbc.Button(
                        html.I(className="fas fa-chevron-down", id="global-file-management-collapse-icon"),
                        id="collapse-global-file-management-btn",
                        color="link",
                        size="sm",
                        className="float-end",
                        style={'textDecoration': 'none'},
                    ),
                ], style={'backgroundColor': '#fff8e1', 'padding': '8px 15px'}),
                dbc.Collapse([
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.Div([
                                    html.Label([html.I(className="fas fa-upload me-1"), "上传文件"], className="fw-bold mb-2 small"),
                                    html.Div(id='multi-algorithm-upload-area', children=create_multi_algorithm_upload_area()),
                                ]),
                            ], md=6),
                            dbc.Col([
                                html.Div([
                                    html.Label([html.I(className="fas fa-list me-1"), "已加载文件"], className="fw-bold mb-2 small"),
                                    html.Div(id='multi-algorithm-management-area', children=create_multi_algorithm_management_area()),
                                ]),
                            ], md=6),
                        ]),
                    ], style={'padding': '12px'}),
                ], id="global-file-management-collapse", is_open=False),
            ], className="shadow-sm mb-3", style={'borderRadius': '8px'}),
        ], fluid=True, className="px-3")

    def _register_global_file_management_callbacks(self, app: dash.Dash) -> None:
        """注册全局文件管理折叠回调"""
        @app.callback(
            [
                Output('global-file-management-collapse', 'is_open'),
                Output('global-file-management-collapse-icon', 'className'),
            ],
            Input('collapse-global-file-management-btn', 'n_clicks'),
            State('global-file-management-collapse', 'is_open'),
            prevent_initial_call=True,
        )
        def toggle_global_file_management(n_clicks, is_open):
            if n_clicks:
                new_state = not is_open
                icon_class = "fas fa-chevron-down" if new_state else "fas fa-chevron-right"
                return new_state, icon_class
            return is_open, "fas fa-chevron-down"

    def _register_page_callbacks(self, app: dash.Dash) -> None:
        """注册各页面的回调"""
        from pages.report import register_callbacks as register_report_callbacks
        from pages.waterfall import register_callbacks as register_waterfall_callbacks
        from pages.scatter_analysis import register_callbacks as register_scatter_callbacks
        from ui.consistency_callbacks import register_callbacks as register_consistency_callbacks
        from ui.waterfall_consistency_callbacks import register_callbacks as register_waterfall_consistency_callbacks
        from ui.history_callbacks import register_history_callbacks

        register_report_callbacks(app, self.session_manager)
        register_waterfall_callbacks(app, self.session_manager)
        register_scatter_callbacks(app, self.session_manager)
        register_consistency_callbacks(app, self.session_manager)
        register_waterfall_consistency_callbacks(app, self.session_manager)
        register_history_callbacks(app, self.session_manager)
        logger.debug("[DEBUG] History and Waterfall Consistency callbacks registered")

    def _handle_page_routing(self, pathname: str):
        """根据 pathname 返回对应页面布局"""
        if pathname == '/' or pathname == '/report':
            from pages.report import layout
            return layout()
        if pathname == '/waterfall':
            from pages.waterfall import layout
            return layout()
        if pathname == '/scatter':
            from pages.scatter_analysis import layout
            return layout()
        if pathname == '/track-comparison':
            from pages.track_comparison import layout
            return layout()
        return dbc.Alert([
            html.H4("404 - 页面未找到"),
            html.P(f"路径 '{pathname}' 不存在"),
            dbc.Button("返回首页", href="/", color="primary"),
        ], color="warning", className="mt-4")

    def _register_page_routing(self, app: dash.Dash) -> None:
        """注册页面路由回调"""
        @app.callback(
            Output('page-content', 'children'),
            Input('url', 'pathname'),
        )
        def display_page(pathname):
            return self._handle_page_routing(pathname)

    def run(self) -> None:
        """运行应用"""
        logger = Logger.get_logger()
        log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
        exact_match = os.environ.get('LOG_EXACT_MATCH', 'false').lower() == 'true'
        if log_level in ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'):
            Logger.set_level(log_level, exact_match=exact_match)
        if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
            logger.info(f"🌐 访问地址: http://{HOST}:{PORT}")
        self.app.run(debug=DEBUG, host=HOST, port=PORT)
