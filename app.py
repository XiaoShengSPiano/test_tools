"""
钢琴数据分析工具 - 主应用入口
"""
import os
import warnings
from typing import Optional

import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, callback, Input, Output, State

# 本地模块导入
from backend.history_manager import HistoryManager
from backend.session_manager import SessionManager
from ui.callbacks import register_callbacks
from utils.logger import Logger

# 常量定义
HOST = '0.0.0.0'
PORT = 10000
DEBUG = True

# 抑制来自 dash 及其依赖库的日期解析弃用警告
warnings.filterwarnings('ignore', category=DeprecationWarning, message='.*Parsing dates.*')


class ApplicationManager:
    """应用管理器 - 使用单例模式管理核心组件"""

    _instance: Optional['ApplicationManager'] = None
    _history_manager: Optional[HistoryManager] = None
    _session_manager: Optional[SessionManager] = None
    _app: Optional[dash.Dash] = None

    def __new__(cls) -> 'ApplicationManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def history_manager(self) -> HistoryManager:
        """获取历史管理器单例"""
        if self._history_manager is None:
            # 检查是否禁用数据库功能
            disable_db = os.environ.get('DISABLE_DATABASE', 'false').lower() == 'true'
            self._history_manager = HistoryManager(disable_database=disable_db)
        return self._history_manager

    @property
    def session_manager(self) -> SessionManager:
        """获取会话管理器单例"""
        if self._session_manager is None:
            self._session_manager = SessionManager(self.history_manager)
        return self._session_manager

    @property
    def app(self) -> dash.Dash:
        """获取Dash应用单例"""
        if self._app is None:
            self._app = self._create_app()
        return self._app

    def _create_app(self) -> dash.Dash:
        """创建并配置Dash应用"""
        app = dash.Dash(
            __name__, 
            external_stylesheets=[dbc.themes.BOOTSTRAP, 
                                 "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css"],
            suppress_callback_exceptions=True
        )
        
        # 导入导航组件
        from ui.components.navigation import create_navbar
        
        # 使用dcc.Location实现多页面
        app.layout = dbc.Container([
            # URL路由组件
            dcc.Location(id='url', refresh=False),
            
            # 全局Store（保持会话状态）
            dcc.Store(id='session-id', storage_type='session'),
            dcc.Store(id='current-clicked-point-info', data=None),
            dcc.Store(id='multi-algorithm-files-store', data={'contents': [], 'filenames': []}),
            dcc.Store(id='algorithm-list-trigger', data=0),
            dcc.Store(id='algorithm-management-trigger', data=0),
            
            # 导航栏
            create_navbar(),
            
            # 全局文件管理区域（所有页面共享）
            self._create_global_file_management(),
            
            # 页面内容容器（通过回调动态切换）
            html.Div(id='page-content'),
            
            # 全局模态框（保留，用于曲线对比等功能）
            html.Div(
                id='key-curves-modal',
                style={'display': 'none'},
                children=[
                    html.Div(
                        id='key-curves-modal-content',
                        children=[
                            html.Button('×', id='close-key-curves-modal', 
                                      style={'position': 'absolute', 'right': '20px', 'top': '20px',
                                             'fontSize': '30px', 'background': 'none', 'border': 'none',
                                             'color': 'white', 'cursor': 'pointer', 'zIndex': '10000'}),
                            html.Div(id='key-curves-comparison-container'),
                            dbc.Button('关闭', id='close-key-curves-modal-btn', 
                                      color='secondary', size='lg',
                                      style={'position': 'absolute', 'bottom': '30px', 'right': '30px'})
                        ]
                    )
                ]
            ),
            
        ], fluid=True)
        
        # 注册页面路由回调（在注册其他回调之前）
        self._register_page_routing(app)
        
        # 注册全局文件管理折叠回调
        self._register_global_file_management_callbacks(app)
        
        # 注册各页面的回调
        self._register_page_callbacks(app)
        
        # 注册回调（保持现有回调逻辑）
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
                            "文件管理"
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
                        style={'textDecoration': 'none'}
                    )
                ], style={'backgroundColor': '#fff8e1', 'padding': '8px 15px'}),
                dbc.Collapse([
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.Div([
                                    html.Label([
                                        html.I(className="fas fa-upload me-1"),
                                        "上传文件"
                                    ], className="fw-bold mb-2 small"),
                                    html.Div(id='multi-algorithm-upload-area', 
                                            children=create_multi_algorithm_upload_area())
                                ]),
                            ], md=6),
                            dbc.Col([
                                html.Div([
                                    html.Label([
                                        html.I(className="fas fa-list me-1"),
                                        "已加载文件"
                                    ], className="fw-bold mb-2 small"),
                                    html.Div(id='multi-algorithm-management-area', 
                                            children=create_multi_algorithm_management_area())
                                ]),
                            ], md=6),
                        ])
                    ], style={'padding': '12px'})
                ], id="global-file-management-collapse", is_open=False)  # 默认折叠
            ], className="shadow-sm mb-3", style={'borderRadius': '8px'})
        ], fluid=True, className="px-3")
    
    def _register_global_file_management_callbacks(self, app):
        """注册全局文件管理折叠回调"""
        @app.callback(
            [
                Output('global-file-management-collapse', 'is_open'),
                Output('global-file-management-collapse-icon', 'className'),
            ],
            Input('collapse-global-file-management-btn', 'n_clicks'),
            State('global-file-management-collapse', 'is_open'),
            prevent_initial_call=True
        )
        def toggle_global_file_management(n_clicks, is_open):
            """切换全局文件管理区域的折叠状态"""
            if n_clicks:
                new_state = not is_open
                icon_class = "fas fa-chevron-down" if new_state else "fas fa-chevron-right"
                return new_state, icon_class
            return is_open, "fas fa-chevron-down"
    
    def _register_page_callbacks(self, app):
        """注册各页面的回调"""
        # 注册报告页面回调
        from pages.report import register_callbacks as register_report_callbacks
        register_report_callbacks(app, self.session_manager)
        
        # 注册瀑布图页面回调
        from pages.waterfall import register_callbacks as register_waterfall_callbacks
        register_waterfall_callbacks(app, self.session_manager)
        
        # 注册散点图页面回调
        from pages.scatter_analysis import register_callbacks as register_scatter_callbacks
        register_scatter_callbacks(app, self.session_manager)
    
    def _handle_page_routing(self, pathname):
        """
        处理页面路由逻辑

        Args:
            pathname: URL路径

        Returns:
            对应页面的布局组件
        """
        if pathname == '/' or pathname == '/report':
            # 异常检测报告页
            from pages.report import layout
            return layout()
        elif pathname == '/waterfall':
            # 瀑布图分析页
            from pages.waterfall import layout
            return layout()
        elif pathname == '/scatter':
            # 散点图分析页
            from pages.scatter_analysis import layout
            return layout()
        else:
            # 404页面
            return dbc.Alert([
                html.H4("404 - 页面未找到"),
                html.P(f"路径 '{pathname}' 不存在"),
                dbc.Button("返回首页", href="/", color="primary")
            ], color="warning", className="mt-4")

    def _register_page_routing(self, app):
        """注册页面路由回调"""
        @app.callback(
            Output('page-content', 'children'),
            Input('url', 'pathname')
        )
        def display_page(pathname):
            """根据URL路径显示对应页面"""
            return self._handle_page_routing(pathname)

    def run(self) -> None:
        """运行应用"""
        logger = Logger.get_logger()

        # 只在主进程中记录启动信息，避免Flask debug模式下的重复日志
        if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
            logger.info(f"🌐 访问地址: http://{HOST}:{PORT}")

        self.app.run(debug=DEBUG, host=HOST, port=PORT)


# 创建应用管理器实例
app_manager = ApplicationManager()

# 导出常用对象以保持向后兼容
app = app_manager.app
history_manager = app_manager.history_manager
session_manager = app_manager.session_manager

if __name__ == '__main__':
    app_manager.run()
