"""
历史记录浏览器回调函数
"""
import asyncio
import time
import json
import traceback
import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, no_update
from backend.session_manager import SessionManager
from utils.logger import Logger

logger = Logger.get_logger()


# ==================== 内部处理器 (Handlers) ====================

def _handle_update_history_table(n_clicks, search_term, active_tab, trigger_data, session_id, session_manager: SessionManager):
    """刷新并显示历史记录表格的业务逻辑"""
    logger.debug(f"🔄 [History] update_history_table 触发: active_tab={active_tab}, session_id={session_id}")
    
    # 兼容 tab-history 和可能的索引 tab-1
    if active_tab not in ['tab-history', 'tab-1']:
        return no_update
        
    logger.debug(f"🔄 [History] update_history_table 正在执行... n_clicks={n_clicks}, search={search_term}")
        
    backend = session_manager.get_backend(session_id)
    if not backend:
        logger.warning(f"⚠️ [History] Backend 尚未就绪 (session={session_id})")
        return html.Div("正在连接数据库...", className='text-muted small text-center p-3')
        
    if not backend.history_manager:
        logger.warning(f"⚠️ [History] HistoryManager 尚未就绪")
        return html.Div("数据库管理器未就绪", className='text-danger text-center p-3')

    try:
        # 获取所有记录
        records = backend.history_manager.get_all_records(limit=100)
        
        # 搜索过滤
        if search_term:
            search_term = search_term.lower()
            records = [r for r in records if search_term in r['filename'].lower()]

        if not records:
            return html.Div("暂无符合条件的历史记录", className='text-muted text-center p-3')

        # 转换为表格数据
        table_header = html.Thead(html.Tr([
            html.Th("文件名", style={'fontSize': '12px'}),
            html.Th("配置 (电机/算法/琴)", style={'fontSize': '12px'}),
            html.Th("文件日期", style={'fontSize': '12px'}),
            html.Th("上传日期", style={'fontSize': '12px'}),
            html.Th("操作", style={'fontSize': '12px', 'textAlign': 'center'})
        ]))

        rows = []
        for r in records:
            config_str = f"{r['motor_type']} | {r['algorithm']} | {r['piano_type']}"
            rows.append(html.Tr([
                html.Td(r['filename'], style={'fontSize': '11px', 'maxWidth': '150px', 'overflow': 'hidden', 'textOverflow': 'ellipsis'}),
                html.Td(config_str, style={'fontSize': '11px'}),
                html.Td(r['file_date'], style={'fontSize': '11px'}),
                html.Td(r['created_at'], style={'fontSize': '11px'}),
                html.Td(
                    html.Button(
                        "加载",
                        id={'type': 'load-history-btn', 'index': r['id']},
                        className='btn btn-outline-info btn-sm py-0 px-2',
                        style={'fontSize': '11px'}
                    ),
                    style={'textAlign': 'center'}
                )
            ]))

        return dbc.Table(
            [table_header, html.Tbody(rows)],
            bordered=True,
            hover=True,
            responsive=True,
            striped=True,
            size='sm'
        )
    except Exception as e:
        logger.error(f"渲染历史表格失败: {e}")
        return html.Div(f"加载失败: {str(e)}", className='text-danger small')


def _handle_load_from_history(n_clicks_list, session_id, session_manager: SessionManager):
    """处理从历史记录加载算法的业务逻辑"""
    ctx = dash.callback_context
    # 1. 基础状态检查
    if not ctx.triggered or not any(v for v in n_clicks_list if v):
        return no_update, no_update

    # 2. 核心逻辑执行（统一捕获意外错误）
    try:
        # 解析触发器 ID
        prop_id = ctx.triggered[0]['prop_id']
        button_id_str = prop_id.split('.')[0]
        button_id = json.loads(button_id_str)
        record_id = button_id['index']
        
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update, no_update

        # 处理异步加载
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success, result = loop.run_until_complete(backend.load_algorithm_from_history(record_id))
        loop.close()
        
        # 根据结果输出日志并返回
        if success:
            logger.info(f"✅ 从历史记录 ID={record_id} 成功加载算法")
            # 触发 algorithm-list-trigger 更新，让 UI 列表刷新
            return time.time(), no_update
        
        logger.error(f"❌ 加载历史记录失败: {result}")
        return no_update, no_update

    except Exception as e:
        # 捕获包括 ID 解析、后端调用在内的所有未预料到的异常
        logger.error(f"加载历史记录时发生意外错误: {e}")
        logger.error(traceback.format_exc())
        return no_update, no_update


# ==================== 回调注册 (Registration) ====================

def register_history_callbacks(app, session_manager: SessionManager):
    """注册历史记录相关的回调"""

    @app.callback(
        Output('history-table-container', 'children'),
        [Input('refresh-history-btn', 'n_clicks'),
         Input('history-search-input', 'value'),
         Input('file-management-tabs', 'active_tab'),
         Input('algorithm-list-trigger', 'data')],
        [State('session-id', 'data')],
        prevent_initial_call=False
    )
    def update_history_table(n_clicks, search_term, active_tab, trigger_data, session_id):
        return _handle_update_history_table(n_clicks, search_term, active_tab, trigger_data, session_id, session_manager)

    @app.callback(
        [Output('algorithm-list-trigger', 'data', allow_duplicate=True),
         Output('history-browser-container', 'style')], # 借用 style 做辅助反馈
        [Input({'type': 'load-history-btn', 'index': dash.ALL}, 'n_clicks')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def load_from_history(n_clicks_list, session_id):
        return _handle_load_from_history(n_clicks_list, session_id, session_manager)
