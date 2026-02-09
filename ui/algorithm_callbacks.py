"""
算法管理回调函数模块
包含算法添加、删除、更新等管理相关的回调逻辑
"""

import time
import traceback
import json
import warnings
from typing import Optional, Tuple, List, Any, Union, Dict

import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, no_update
from dash import Input, Output, State
from dash._callback_context import callback_context

from ui.multi_file_upload_handler import MultiFileUploadHandler
from utils.logger import Logger

# Suppress dash_table deprecation warning
warnings.filterwarnings('ignore', message='.*dash_table package is deprecated.*', category=UserWarning)

logger = Logger.get_logger()


def _create_status_display(status: str, is_ready: bool) -> Tuple[html.I, str]:
    """创建状态显示组件"""
    status_configs = {
        ('ready', True): ("fas fa-check-circle", "#28a745", "就绪"),
        ('loading', None): ("fas fa-spinner fa-spin", "#17a2b8", "加载中"),
        ('error', None): ("fas fa-exclamation-circle", "#dc3545", "错误"),
    }

    # 默认状态
    icon_class, color, text = "fas fa-clock", "#ffc107", "等待中"

    for (s, r), (cls, col, txt) in status_configs.items():
        if s == status and (r is None or r == is_ready):
            icon_class, color, text = cls, col, txt
            break

    status_icon = html.I(className=icon_class, style={'color': color, 'marginRight': '5px'})
    return status_icon, text


def _create_algorithm_card(alg_info: dict) -> dbc.Card:
    """创建算法卡片组件"""
    alg_name = alg_info['algorithm_name']
    display_name = alg_info.get('display_name', alg_name)
    filename = alg_info['filename']
    color = alg_info['color']
    is_active = alg_info.get('is_active', True)

    status_icon, status_text = _create_status_display(alg_info['status'], alg_info['is_ready'])

    return dbc.Card([
        dbc.CardBody([
            html.Div([
                html.Div([
                    html.Span(display_name, style={'fontWeight': 'bold', 'fontSize': '14px', 'color': color}),
                    html.Br(),
                    html.Small(filename, style={'color': '#6c757d', 'fontSize': '11px'}),
                    html.Br(),
                    html.Small([status_icon, status_text], style={'fontSize': '11px'})
                ], style={'flex': '1'}),
                html.Div([
                    dbc.Switch(
                        id={'type': 'algorithm-toggle', 'index': alg_name},
                        label='显示',
                        value=is_active,
                        style={'fontSize': '12px'}
                    ),
                    dbc.Button(
                        "删除",
                        id={'type': 'algorithm-delete-btn', 'index': alg_name},
                        color='danger',
                        size='sm',
                        n_clicks=0,
                        style={'marginTop': '5px', 'width': '100%'}
                    )
                ], style={'marginLeft': '10px'})
            ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center'})
        ])
    ], className='mb-2', style={'border': f'2px solid {color}', 'borderRadius': '5px'})


def _parse_trigger_index(trigger_id: str) -> Optional[str]:
    """解析模式匹配ID中的index字段"""
    try:
        trigger_data = json.loads(trigger_id.split('.')[0])
        return trigger_data.get('index')
    except (json.JSONDecodeError, KeyError, IndexError):
        return None


def _update_ui_state(backend, store_data: Optional[Dict[str, Any]]) -> Tuple[html.Div, html.Span, Dict[str, Any]]:
    """
    统一更新文件列表和状态文本的逻辑
    """
    algorithms = backend.get_all_algorithms()
    added_filenames = {alg.get('filename', '') for alg in algorithms}
    
    # 默认状态
    file_list = []
    status_text = html.Span("", style={'color': '#6c757d'})
    updated_store = {'contents': [], 'filenames': [], 'file_ids': [], 'history_hints': []}

    if store_data and 'filenames' in store_data:
        contents = store_data.get('contents', [])
        filenames = store_data.get('filenames', [])
        file_ids = store_data.get('file_ids', [])
        history_hints = store_data.get('history_hints', [])

        filtered_data = {'contents': [], 'filenames': [], 'file_ids': [], 'history_hints': []}
        file_items = []
        upload_handler = MultiFileUploadHandler()

        for i, filename in enumerate(filenames):
            if filename not in added_filenames:
                # 收集未添加的文件数据
                filtered_data['filenames'].append(filename)
                if i < len(contents): filtered_data['contents'].append(contents[i])
                if i < len(file_ids): filtered_data['file_ids'].append(file_ids[i])
                hint = history_hints[i] if i < len(history_hints) else None
                filtered_data['history_hints'].append(hint)
                
                # 创建UI卡片
                file_card = upload_handler.create_file_card(
                    file_ids[i] if i < len(file_ids) else f"temp-{i}", 
                    filename, 
                    existing_record=hint
                )
                file_items.append(file_card)

        updated_store = filtered_data
        file_list = html.Div(file_items)
        if filtered_data['filenames']:
            status_text = html.Span(
                f"共 {len(filtered_data['filenames'])} 个待处理文件",
                style={'color': '#17a2b8', 'fontWeight': 'bold'}
            )

    return file_list, status_text, updated_store


def register_algorithm_callbacks(app, session_manager):
    """注册算法管理相关的回调函数"""

    @app.callback(
        [Output('multi-algorithm-file-list', 'children', allow_duplicate=True),
         Output('multi-algorithm-upload-status', 'children', allow_duplicate=True),
         Output('multi-algorithm-files-store', 'data', allow_duplicate=True)],
        Input('algorithm-management-trigger', 'data'),
        State('session-id', 'data'),
        State('multi-algorithm-files-store', 'data'),
        prevent_initial_call=True
    )
    def refresh_file_list(trigger, session_id, store_data):
        """算法状态变更（添加或管理）后刷新文件列表"""
        backend = session_manager.get_backend(session_id)
        if not backend: return no_update, no_update, no_update
        return _update_ui_state(backend, store_data)

    @app.callback(
        Output('algorithm-list-trigger', 'data', allow_duplicate=True),
        [Input({'type': 'algorithm-upload-success', 'index': dash.dependencies.ALL}, 'data')],
        prevent_initial_call=True
    )
    def on_upload_success(upload_data):
        return time.time()
    
    @app.callback(
        Output('algorithm-management-trigger', 'data', allow_duplicate=True),
        [Input('algorithm-list-trigger', 'data'),
         Input({'type': 'algorithm-toggle', 'index': dash.dependencies.ALL}, 'value')],
        prevent_initial_call=True
    )
    def on_algo_change(trigger, toggle_values):
        return time.time()

    @app.callback(
        [Output('algorithm-list', 'children', allow_duplicate=True),
         Output('algorithm-management-status', 'children', allow_duplicate=True),
         Output('active-algo-count-badge', 'children')],
        [Input('algorithm-list-trigger', 'data')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def update_algorithm_list(trigger, session_id):
        backend = session_manager.get_backend(session_id)
        if not backend: return [], "", "0"

        algorithms = backend.get_all_algorithms()
        if not algorithms:
            return [], html.Span("暂无算法，请上传文件", style={'color': '#6c757d'}), "0"

        cards = []
        for alg in algorithms:
            # 确保激活状态存在
            if alg.get('is_active') is None:
                alg_obj = backend.multi_algorithm_manager.get_algorithm(alg['algorithm_name'])
                if alg_obj: alg_obj.is_active = True
                alg['is_active'] = True
            
            cards.append(_create_algorithm_card(alg))

        status = html.Span(f"共 {len(algorithms)} 个算法", style={'color': '#6c757d'})
        return cards, status, str(len(algorithms))

    @app.callback(
        [Output('algorithm-list-trigger', 'data', allow_duplicate=True),
         Output('multi-algorithm-file-list', 'children', allow_duplicate=True),
         Output('multi-algorithm-upload-status', 'children', allow_duplicate=True),
         Output('multi-algorithm-files-store', 'data', allow_duplicate=True)],
        [Input({'type': 'algorithm-toggle', 'index': dash.dependencies.ALL}, 'value'),
         Input({'type': 'algorithm-delete-btn', 'index': dash.dependencies.ALL}, 'n_clicks')],
        [State({'type': 'algorithm-toggle', 'index': dash.dependencies.ALL}, 'id'),
         State({'type': 'algorithm-delete-btn', 'index': dash.dependencies.ALL}, 'id'),
         State('session-id', 'data'),
         State('multi-algorithm-files-store', 'data')],
        prevent_initial_call=True
    )
    def handle_management(toggle_vals, del_clicks, toggle_ids, del_ids, session_id, store_data):
        backend = session_manager.get_backend(session_id)
        if not backend: return no_update, no_update, no_update, no_update

        ctx = callback_context
        if not ctx.triggered: return no_update, no_update, no_update, no_update

        trigger_id = ctx.triggered[0]['prop_id']
        algo_name = _parse_trigger_index(trigger_id)
        if not algo_name: return no_update, no_update, no_update, no_update

        # 处理开关切换
        if 'algorithm-toggle' in trigger_id:
            for i, tid in enumerate(toggle_ids):
                if tid and tid.get('index') == algo_name:
                    val = toggle_vals[i]
                    alg = backend.multi_algorithm_manager.get_algorithm(algo_name)
                    if alg: alg.is_active = val
                    break
        
        # 处理删除
        elif 'algorithm-delete-btn' in trigger_id:
            backend.remove_algorithm(algo_name)

        # 统一返回：触发列表更新，并同步更新文件上传区的待处理列表
        file_list, status_text, updated_store = _update_ui_state(backend, store_data)
        return time.time(), file_list, status_text, updated_store
