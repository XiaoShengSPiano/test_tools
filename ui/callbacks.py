"""
回调函数模块 - 处理Dash应用的所有回调逻辑
包含文件上传、历史记录表格交互等回调函数
"""
import uuid
import base64
import os
import time
from datetime import datetime
from dash import Input, Output, State, callback_context, no_update, html, dcc
import dash_bootstrap_components as dbc
from ui.layout_components import create_report_layout, create_detail_content, empty_figure
from backend.piano_analysis_backend import PianoAnalysisBackend
from backend.data_manager import DataManager
from ui.ui_processor import UIProcessor
from utils.pdf_generator import PDFReportGenerator
from utils.logger import Logger

logger = Logger.get_logger()


def _create_empty_figure_for_callback(title):
    """创建用于回调的空Plotly figure对象"""
    import plotly.graph_objects as go

    fig = go.Figure()
    fig.add_annotation(
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        text=title,
        showarrow=False,
        font=dict(size=16, color="gray"),
        align="center"
    )

    fig.update_layout(
        title=title,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        height=600,
        template='plotly_white',
        showlegend=False
    )

    return fig


def _detect_trigger_source(ctx, backend, contents, filename, history_id):
    """
    检测用户操作的触发源，确定需要执行的处理逻辑
    
    触发源优先级（从高到低）：
    1. 新文件上传 - 最高优先级，会重新加载数据
    2. 历史记录选择 - 中等优先级，会切换数据源
    3. 按钮点击 - 最低优先级，基于当前数据生成视图
    
    Args:
        ctx: Dash回调上下文，包含触发信息
        backend: 后端实例，用于状态管理
        contents: 上传文件的内容（base64编码）
        filename: 上传文件的文件名
        history_id: 选择的历史记录ID
        
    Returns:
        str: 触发源类型 ('upload', 'history', 'waterfall', 'report', 'skip')
             - 'upload': 新文件上传
             - 'history': 历史记录选择
             - 'waterfall': 瀑布图按钮点击
             - 'report': 报告按钮点击
             - 'skip': 跳过处理（重复操作）
    """
    # 获取当前状态信息
    current_time = time.time()
    current_state = _get_current_state(contents, filename, history_id)
    previous_state = _get_previous_state(backend)
    
    # 从回调上下文检测触发源
    trigger_source = _detect_trigger_from_context(ctx, current_state, previous_state, backend, current_time)
    
    # 如果无法从上下文确定，则基于状态变化智能判断
    if not trigger_source:
        trigger_source = _detect_trigger_from_state_change(current_state, previous_state, backend, current_time)
    
    # 记录最终结果
    data_source = getattr(backend, '_data_source', 'none') if backend else 'none'
    logger.info(f"🔍 最终确定触发源: {trigger_source}, 当前数据源: {data_source}")
    return trigger_source

def _get_current_state(contents, filename, history_id):
    """获取当前状态信息"""
    return {
        'has_upload': contents and filename,
        'has_history': history_id is not None,
        'upload_content': contents,
        'filename': filename,
        'history_id': history_id
    }

def _get_previous_state(backend):
    """获取上次的状态信息"""
    if not backend:
        return {
            'last_upload_content': None,
            'last_history_id': None
        }
    
    return {
        'last_upload_content': getattr(backend, '_last_upload_content', None),
        'last_history_id': getattr(backend, '_last_selected_history_id', None)
    }

def _detect_trigger_from_context(ctx, current_state, previous_state, backend, current_time):
    """从回调上下文检测触发源"""
    if not ctx.triggered:
        return None
    
    recent_trigger = ctx.triggered[0]['prop_id']
    
    # 检查文件上传触发
    if 'upload-spmid-data' in recent_trigger:
        return _handle_upload_trigger(current_state, previous_state, backend, current_time)
    
    # 检查历史记录选择触发
    elif 'history-dropdown' in recent_trigger:
        return _handle_history_trigger(current_state, previous_state, backend, current_time)
    
    # 检查按钮点击触发
    elif 'btn-waterfall' in recent_trigger:
        return 'waterfall'
    elif 'btn-report' in recent_trigger:
        return 'report'
    
    return None

def _handle_upload_trigger(current_state, previous_state, backend, current_time):
    """处理文件上传触发"""
    if not current_state['has_upload']:
        return None
    
    # 检查文件内容是否发生变化
    if current_state['upload_content'] != previous_state['last_upload_content']:
        _update_upload_state(backend, current_state['upload_content'], current_time)
        logger.info(f"🔄 检测到新文件上传: {current_state['filename']}")
        return 'upload'
    else:
        logger.warning("⚠️ 文件内容未变化，跳过重复处理")
        return 'skip'

def _handle_history_trigger(current_state, previous_state, backend, current_time):
    """处理历史记录选择触发"""
    if not current_state['has_history']:
        return None
    
    # 检查历史记录选择是否发生变化
    if current_state['history_id'] != previous_state['last_history_id']:
        _update_history_state(backend, current_state['history_id'], current_time)
        logger.info(f"🔄 检测到历史记录选择变化: {current_state['history_id']}")
        return 'history'
    else:
        logger.warning("⚠️ 历史记录选择未变化，跳过重复处理")
        return 'skip'

def _detect_trigger_from_state_change(current_state, previous_state, backend, current_time):
    """基于状态变化智能检测触发源"""
    # 检查是否有新的文件上传
    if (current_state['has_upload'] and 
        current_state['upload_content'] != previous_state['last_upload_content']):
        _update_upload_state(backend, current_state['upload_content'], current_time)
        logger.info(f"🔄 智能检测到新文件上传: {current_state['filename']}")
        return 'upload'
    
    # 检查是否有新的历史记录选择
    elif (current_state['has_history'] and 
          current_state['history_id'] != previous_state['last_history_id']):
        _update_history_state(backend, current_state['history_id'], current_time)
        logger.info(f"🔄 智能检测到历史记录选择: {current_state['history_id']}")
        return 'history'
    
    return None

def _update_upload_state(backend, upload_content, current_time):
    """更新文件上传状态"""
    backend._last_upload_content = upload_content
    backend._last_upload_time = current_time
    backend._data_source = 'upload'

def _update_history_state(backend, history_id, current_time):
    """更新历史记录选择状态"""
    backend._last_selected_history_id = history_id
    backend._last_history_time = current_time
    backend._data_source = 'history'


def _handle_file_upload(contents, filename, backend, key_filter):
    """处理文件上传操作"""
    logger.info(f"🔄 处理文件上传: {filename}")
    
    # 使用backend中的DataManager处理文件上传
    success, result_data, error_msg = backend.process_file_upload(contents, filename)
    
    if success:
        # 使用UIProcessor生成成功内容
        ui_processor = UIProcessor()
        info_content = ui_processor.create_upload_success_content(result_data)
        error_content = None
    else:
        # 使用UIProcessor生成错误内容
        ui_processor = UIProcessor()
        info_content = None
        error_content = ui_processor.create_upload_error_content(filename, error_msg)
    
    if info_content and not error_content:
        # 执行数据分析
        backend._perform_error_analysis()
        
        # 设置键ID筛选
        if key_filter:
            backend.set_key_filter(key_filter)
        else:
            backend.set_key_filter(None)
        
        fig = backend.generate_waterfall_plot()
        report_content = create_report_layout(backend)
        
        # 不在这里更新历史记录选项，避免与初始化回调冲突
        # 历史记录选项由专门的初始化和搜索回调管理
        
        # 获取键ID和时间筛选相关数据
        key_options = backend.get_available_keys()
        key_status = backend.get_key_filter_status()
        
        # 将key_status转换为可渲染的字符串
        if key_status['enabled']:
            key_status_text = f"已筛选 {len(key_status['filtered_keys'])} 个键位 (共 {key_status['total_available_keys']} 个)"
        else:
            key_status_text = f"显示全部 {key_status['total_available_keys']} 个键位"
        
        # 完全避免更新滑块属性，防止无限递归
        time_status = backend.get_time_filter_status()
        
        # 将time_status转换为可渲染的字符串
        if time_status['enabled']:
            time_status_text = f"时间范围: {time_status['start_time']:.2f}s - {time_status['end_time']:.2f}s (时长: {time_status['duration']:.2f}s)"
        else:
            time_status_text = "显示全部时间范围"
        
        logger.info("✅ 文件上传处理完成，清空历史记录选择，显示新文件数据")
        return fig, report_content, no_update, key_options, key_status_text, no_update, no_update, no_update, time_status_text
    else:
        # 处理上传错误
        if error_content:
            if error_msg and ("轨道" in error_msg or "track" in error_msg.lower() or "SPMID文件只包含" in error_msg):
                fig = _create_empty_figure_for_callback("❌ SPMID文件只包含 1 个轨道，需要至少2个轨道（录制+播放）才能进行分析")
            else:
                fig = _create_empty_figure_for_callback("文件类型不符")
            return fig, error_content, no_update, [], "显示全部键位", 0, 1000, [0, 1000], "显示全部时间范围"
        else:
            fig = _create_empty_figure_for_callback("文件上传失败")
            error_div = html.Div([
                html.H4("文件上传失败", className="text-center text-danger"),
                html.P("请检查文件格式或联系管理员。", className="text-center")
            ])
            return fig, error_div, no_update, [], "显示全部键位", 0, 1000, [0, 1000], "显示全部时间范围"


def _handle_history_selection(history_id, backend):
    """处理历史记录选择操作"""
    logger.info(f"🔄 加载历史记录: {history_id}")
    
    # 使用HistoryManager处理历史记录选择（包含状态初始化）
    success, result_data, error_msg = backend.history_manager.process_history_selection(history_id, backend)
    
    # 使用UIProcessor生成UI内容
    ui_processor = UIProcessor()

    if success:
        if result_data['has_file_content']:
            # 执行数据分析
            backend._perform_error_analysis()
            
            # 有文件内容，生成瀑布图和报告
            waterfall_fig = ui_processor.generate_history_waterfall(backend, result_data['filename'], result_data['main_record'])
            report_content = ui_processor.generate_history_report(backend, result_data['filename'], result_data['history_id'])
        else:
            # 没有文件内容，只显示基本信息
            waterfall_fig = ui_processor.create_empty_figure("历史记录无文件内容")
            report_content = ui_processor.create_history_basic_info_content(result_data)
    else:
        waterfall_fig = ui_processor.create_empty_figure("历史记录加载失败")
        report_content = ui_processor.create_error_content("历史记录加载失败", error_msg)
    
    if waterfall_fig and report_content:
        logger.info("✅ 历史记录加载完成，返回瀑布图和报告")
        
        # 获取键ID筛选相关数据
        key_options = backend.get_available_keys()
        key_status = backend.get_key_filter_status()
        
        # 将key_status转换为可渲染的字符串
        if key_status['enabled']:
            key_status_text = f"已筛选 {len(key_status['filtered_keys'])} 个键位 (共 {key_status['total_available_keys']} 个)"
        else:
            key_status_text = f"显示全部 {key_status['total_available_keys']} 个键位"
        
        # 完全避免更新滑块属性，防止无限递归
        time_status = backend.get_time_filter_status()
        
        # 将time_status转换为可渲染的字符串
        if time_status['enabled']:
            time_status_text = f"时间范围: {time_status['start_time']:.2f}s - {time_status['end_time']:.2f}s (时长: {time_status['duration']:.2f}s)"
        else:
            time_status_text = "显示全部时间范围"
        
        return waterfall_fig, report_content, no_update, key_options, key_status_text, no_update, no_update, no_update, time_status_text
    else:
        logger.error("❌ 历史记录加载失败")
        empty_fig = _create_empty_figure_for_callback("历史记录加载失败")
        error_content = html.Div([
            html.H4("历史记录加载失败", className="text-center text-danger"),
            html.P("请尝试选择其他历史记录", className="text-center")
        ])
        return empty_fig, error_content, no_update, [], "显示全部键位", 0, 1000, [0, 1000], "显示全部时间范围"


def _handle_waterfall_button(backend):
    """处理瀑布图按钮点击"""
    current_data_source = getattr(backend, '_data_source', 'none') if backend else 'none'
    logger.info(f"🔄 生成瀑布图（数据源: {current_data_source}）")
    
    # 检查是否有已加载的数据
    if hasattr(backend, 'all_error_notes') and backend.all_error_notes:
        fig = backend.generate_waterfall_plot()
        return fig, no_update, no_update, [], "显示全部键位", 0, 1000, [0, 1000], "显示全部时间范围"
    else:
        if current_data_source == 'history':
            empty_fig = _create_empty_figure_for_callback("请选择历史记录或上传新文件")
        else:
            empty_fig = _create_empty_figure_for_callback("请先上传SPMID文件")
        return empty_fig, no_update, no_update, [], "显示全部键位", 0, 1000, [0, 1000], "显示全部时间范围"


def _handle_report_button(backend):
    """处理报告按钮点击"""
    current_data_source = getattr(backend, '_data_source', 'none') if backend else 'none'
    logger.info(f"🔄 生成分析报告（数据源: {current_data_source}）")
    
    # 检查是否有已加载的数据
    if hasattr(backend, 'all_error_notes') and backend.all_error_notes:
        report_content = create_report_layout(backend)
        return no_update, report_content, no_update, no_update, no_update, no_update, no_update, no_update, no_update
    else:
        if current_data_source == 'history':
            error_content = html.Div([
                html.H4("请选择历史记录或上传新文件", className="text-center text-warning"),
                html.P("需要先选择历史记录或上传SPMID文件才能生成报告", className="text-center")
            ])
        else:
            error_content = html.Div([
                html.H4("请先上传SPMID文件", className="text-center text-warning"),
                html.P("需要先上传并分析SPMID文件才能生成报告", className="text-center")
            ])
        return no_update, error_content, no_update, no_update, no_update, no_update, no_update, no_update, no_update


def _handle_fallback_logic(contents, filename, history_id, backend):
    """兜底逻辑：基于现有状态判断"""
    if contents and filename and not history_id:
        logger.info(f"🔄 兜底处理文件上传: {filename}")
        
        # 使用backend中的DataManager处理文件上传
        success, result_data, error_msg = backend.process_file_upload(contents, filename)
        fig = backend.generate_waterfall_plot()
        report_content = create_report_layout(backend)
        
        # 不在这里更新历史记录选项，避免循环调用
        return fig, report_content, no_update, [], "显示全部键位", 0, 1000, [0, 1000], "显示全部时间范围"
        
    elif history_id:
        logger.info(f"🔄 兜底处理历史记录: {history_id}")
        
        # 使用UIProcessor生成UI内容
        ui_processor = UIProcessor()
        # 使用HistoryManager处理历史记录选择（包含状态初始化）
        success, result_data, error_msg = backend.history_manager.process_history_selection(history_id, backend)
        
        if success:
            if result_data['has_file_content']:
                # 有文件内容，生成瀑布图和报告
                waterfall_fig = ui_processor.generate_history_waterfall(backend, result_data['filename'], result_data['main_record'])
                report_content = ui_processor.generate_history_report(backend, result_data['filename'], result_data['history_id'])
            else:
                # 没有文件内容，只显示基本信息
                waterfall_fig = ui_processor.create_empty_figure("历史记录无文件内容")
                report_content = ui_processor.create_history_basic_info_content(result_data)
        else:
            waterfall_fig = ui_processor.create_empty_figure("历史记录加载失败")
            report_content = ui_processor.create_error_content("历史记录加载失败", error_msg)
        if waterfall_fig and report_content:
            return waterfall_fig, report_content, no_update, [], "显示全部键位", 0, 1000, [0, 1000], "显示全部时间范围"
        else:
            empty_fig = _create_empty_figure_for_callback("历史记录加载失败")
            error_content = html.Div([
                html.H4("历史记录加载失败", className="text-center text-danger"),
                html.P("请尝试选择其他历史记录", className="text-center")
            ])
            return empty_fig, error_content, no_update, [], "显示全部键位", 0, 1000, [0, 1000], "显示全部时间范围"

    # 最终兜底：无上传、无历史选择、无触发
    placeholder_fig = _create_empty_figure_for_callback("等待操作：请上传文件或选择历史记录")
    return placeholder_fig, no_update, no_update, [], "显示全部键位", 0, 1000, [0, 1000], "显示全部时间范围"


def register_callbacks(app, backends, history_manager):
    """注册所有回调函数"""

    @app.callback(
        Output('session-id', 'data'),
        Input('session-id', 'data'),
        prevent_initial_call=True
    )
    def init_session(session_data):
        """初始化会话ID"""
        if session_data is None:
            return str(uuid.uuid4())
        return session_data

    # 主要的数据处理回调
    @app.callback(
        [Output('main-plot', 'figure'),
         Output('report-content', 'children'),
         Output('history-dropdown', 'options'),
         Output('key-filter-dropdown', 'options'),
         Output('key-filter-status', 'children'),
         Output('time-filter-slider', 'min'),
         Output('time-filter-slider', 'max'),
         Output('time-filter-slider', 'value'),
         Output('time-filter-status', 'children')],
        [Input('upload-spmid-data', 'contents'),
         Input('btn-waterfall', 'n_clicks'),
         Input('btn-report', 'n_clicks'),
         Input('history-dropdown', 'value'),
         Input('key-filter-dropdown', 'value'),
         Input('btn-show-all-keys', 'n_clicks')],
        [State('upload-spmid-data', 'filename'),
         State('session-id', 'data')],
        prevent_initial_call=True
    )
    def process_data(contents, waterfall_clicks, report_clicks, history_id, key_filter, show_all_keys, filename, session_id):
        """处理数据的主要回调函数"""

        # 获取触发上下文
        ctx = callback_context

        # 初始化后端实例
        if session_id not in backends:
            backends[session_id] = PianoAnalysisBackend(session_id, history_manager)
        backend = backends[session_id]

        try:
            # 检测触发源
            trigger_source = _detect_trigger_source(ctx, backend, contents, filename, history_id)
            
            if trigger_source == 'skip':
                return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update

            # 根据触发源分发处理
            if trigger_source == 'upload' and contents and filename:
                return _handle_file_upload(contents, filename, backend, key_filter)
                
            elif trigger_source == 'history' and history_id:
                return _handle_history_selection(history_id, backend)
                
            elif trigger_source == 'waterfall':
                return _handle_waterfall_button(backend)
                
            elif trigger_source == 'report':
                return _handle_report_button(backend)
                
            else:
                # 兜底逻辑
                return _handle_fallback_logic(contents, filename, history_id, backend)

        except Exception as e:
            logger.error(f"❌ 处理数据失败: {e}")
            import traceback
            logger.error(traceback.format_exc())

            # 返回错误状态的figure和内容
            error_fig = _create_empty_figure_for_callback(f"处理失败: {str(e)}")
            error_content = html.Div([
                html.H4("处理失败", className="text-center text-danger"),
                html.P(f"错误信息: {str(e)}", className="text-center")
            ])
            return error_fig, error_content, no_update, [], "显示全部键位", 0, 1000, [0, 1000], "显示全部时间范围"


    # 只在报告页面存在时注册表格回调
    @app.callback(
        [Output('drop-hammers-table', 'selected_rows'),
         Output('multi-hammers-table', 'selected_rows'),
         Output('detail-info', 'children'),
         Output('image-container', 'children')],
        [Input('drop-hammers-table', 'selected_rows'),
         Input('multi-hammers-table', 'selected_rows')],
        [State('drop-hammers-table', 'data'),
         State('multi-hammers-table', 'data'),
         State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_table_selection(drop_selected, multi_selected, drop_data, multi_data, session_id):
        """处理表格选择回调"""
        try:
            # 获取后端实例
            if session_id not in backends:
                detail_content, image_content = _create_default_placeholder_content()
                return [], [], detail_content, image_content
            backend = backends[session_id]
            
            # 确定触发源（表格选择）
            trigger_id = None
            if drop_selected:
                trigger_id = 'drop-hammers-table'
            elif multi_selected:
                trigger_id = 'multi-hammers-table'
            
            # 处理选择逻辑
            drop_rows, multi_rows, detail_content, image_content = _handle_table_selection(
                trigger_id, drop_selected, multi_selected, drop_data, multi_data, backend
            )
            
            return drop_rows, multi_rows, detail_content, image_content
            
        except Exception as e:
            logger.error(f"表格选择回调处理失败: {e}")
            detail_content, image_content = _create_default_placeholder_content()
            return [], [], detail_content, image_content

    def _create_default_placeholder_content(*args, **kwargs):
        """创建默认的占位符内容"""
        detail_content = html.Div([
            html.I(className="fas fa-info-circle", style={'fontSize': '24px', 'color': '#6c757d', 'marginBottom': '8px'}),
            html.P("请选择左侧表格中的条目查看对比图",
                   className="text-muted text-center",
                   style={'fontSize': '12px'})
        ], className="d-flex flex-column align-items-center justify-content-center h-100")

        image_content = html.Div([
            html.I(className="fas fa-chart-line", style={'fontSize': '36px', 'color': '#6c757d', 'marginBottom': '10px'}),
            html.P("请选择左侧表格中的条目来查看对比图",
                   className="text-muted text-center",
                   style={'fontSize': '12px'})
        ], className="d-flex flex-column align-items-center justify-content-center h-100")

        return detail_content, image_content

    def _create_error_image_content(error_msg):
        """创建错误图片内容"""
        return html.Div([
            html.I(className="fas fa-exclamation-triangle", style={'fontSize': '24px', 'color': '#dc3545', 'marginBottom': '8px'}),
            html.P(f"图片加载失败: {error_msg}", className="text-danger text-center", style={'fontSize': '12px'})
        ], className="d-flex flex-column align-items-center justify-content-center h-100")

    def _generate_image_content(backend, global_index):
        """生成图片内容"""
        try:
            image_base64 = backend.get_note_image_base64(global_index)
            return dcc.Loading(
                children=[html.Img(src=image_base64, style={'width': '100%', 'height': 'auto', 'maxHeight': '360px'})],
                type="default"
            )
        except Exception as e:
            return _create_error_image_content(str(e))

    def _process_selected_row(selected_row, backend):
        """处理选中的行数据"""
        global_index = selected_row['global_index']
        
        if global_index < len(backend.all_error_notes):
            error_note = backend.all_error_notes[global_index]
            detail_content = create_detail_content(error_note)
            image_content = _generate_image_content(backend, global_index)
            return detail_content, image_content
        
        # 如果索引超出范围，返回默认内容
        return _create_default_placeholder_content()

    def _handle_table_selection(trigger_id, drop_selected, multi_selected, drop_data, multi_data, backend):
        """处理表格选择逻辑"""
        drop_rows = []
        multi_rows = []
        detail_content, image_content = _create_default_placeholder_content()

        if trigger_id == 'drop-hammers-table' and drop_selected:
            # 丢锤表格被选择，清除多锤表格选择
            drop_rows = drop_selected
            multi_rows = []
            
            if drop_data and drop_selected:
                detail_content, image_content = _process_selected_row(
                    drop_data[drop_selected[0]], backend
                )

        elif trigger_id == 'multi-hammers-table' and multi_selected:
            # 多锤表格被选择，清除丢锤表格选择
            drop_rows = []
            multi_rows = multi_selected
            
            if multi_data and multi_selected:
                detail_content, image_content = _process_selected_row(
                    multi_data[multi_selected[0]], backend
                )

        return drop_rows, multi_rows, detail_content, image_content


    # 添加时间滑块初始化回调 - 当数据加载完成后自动设置合理的时间范围
    @app.callback(
        [Output('time-filter-slider', 'min', allow_duplicate=True),
         Output('time-filter-slider', 'max', allow_duplicate=True),
         Output('time-filter-slider', 'value', allow_duplicate=True),
         Output('time-filter-slider', 'marks', allow_duplicate=True)],
        Input('report-content', 'children'),
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def initialize_time_slider_on_data_load(report_content, session_id):
        """当数据加载完成后初始化时间滑块"""
        if not session_id or session_id not in backends:
            return no_update, no_update, no_update, no_update
        
        backend = backends[session_id]
        
        # 只有当有分析数据时才更新滑块
        if not hasattr(backend, 'all_error_notes') or not backend.all_error_notes:
            return no_update, no_update, no_update, no_update
        
        try:
            # 获取实际的时间范围
            time_range = backend.get_time_range()
            time_min, time_max = time_range
            
            # 确保时间范围是有效的
            if not isinstance(time_min, (int, float)) or not isinstance(time_max, (int, float)):
                return no_update, no_update, no_update, no_update
            
            if time_min >= time_max:
                return no_update, no_update, no_update, no_update
            
            # 转换为整数，避免滑块精度问题
            time_min, time_max = int(time_min), int(time_max)
            
            # 创建合理的标记点
            range_size = time_max - time_min
            if range_size <= 1000:
                step = max(1, range_size // 5)
            elif range_size <= 10000:
                step = max(10, range_size // 10)
            else:
                step = max(100, range_size // 20)
            
            marks = {}
            for i in range(time_min, time_max + 1, step):
                if i == time_min or i == time_max or (i - time_min) % (step * 2) == 0:
                    marks[i] = str(i)
            
            logger.info(f"⏰ 初始化时间滑块: min={time_min}, max={time_max}, 范围={range_size}")
            
            return time_min, time_max, [time_min, time_max], marks
            
        except Exception as e:
            logger.warning(f"⚠️ 初始化时间滑块失败: {e}")
            return no_update, no_update, no_update, no_update

    # 添加初始化历史记录下拉菜单的回调 - 只在应用启动时初始化一次
    @app.callback(
        [Output('history-dropdown', 'options', allow_duplicate=True),
         Output('history-dropdown', 'value', allow_duplicate=True)],
        Input('session-id', 'data'),
        prevent_initial_call='initial_duplicate'  # 修复：使用 initial_duplicate 允许初始调用和重复输出
    )
    def initialize_history_dropdown(session_id):
        """初始化历史记录下拉框选项 - 只在会话初始化时调用一次"""
        # 检查是否已经初始化过
        if hasattr(initialize_history_dropdown, '_initialized'):
            return no_update, no_update
        
        try:
            # 获取历史记录列表
            history_list = history_manager.get_history_list(limit=100)

            if not history_list:
                initialize_history_dropdown._initialized = True
                return [], None

            # 转换为下拉框选项格式
            options = []
            for record in history_list:
                label = f"{record['filename']} ({record['timestamp'][:19] if record['timestamp'] else '未知时间'}) - 多锤:{record['multi_hammers']} 丢锤:{record['drop_hammers']}"
                options.append({
                    'label': label,
                    'value': record['id']
                })

            logger.info(f"✅ 初始化历史记录下拉菜单，找到 {len(options)} 条记录")
            initialize_history_dropdown._initialized = True
            return options, None  # 返回选项列表，但不预选任何项

        except Exception as e:
            logger.error(f"❌ 初始化历史记录下拉框失败: {e}")
            initialize_history_dropdown._initialized = True
            return [], None

    @app.callback(
        Output('history-dropdown', 'options', allow_duplicate=True),
        [Input('history-search', 'value'),
         Input('session-id', 'data')],
        prevent_initial_call=True  # 修改为True，防止初始化时重复调用
    )
    def update_history_dropdown_search(search_value, session_id):
        """更新历史记录下拉框选项 - 仅搜索触发"""
        try:
            # 获取历史记录列表
            history_list = history_manager.get_history_list(limit=100)

            if not history_list:
                return []

            # 转换为下拉框选项格式
            options = []
            for record in history_list:
                label = f"{record['filename']} ({record['timestamp'][:19] if record['timestamp'] else '未知时间'}) - 多锤:{record['multi_hammers']} 丢锤:{record['drop_hammers']}"

                # 如果有搜索值，则过滤选项
                if search_value and search_value.lower() not in label.lower():
                    continue

                options.append({
                    'label': label,
                    'value': record['id']
                })

            return options

        except Exception as e:
            logger.error(f"❌ 更新历史记录下拉框失败: {e}")
            return []

    @app.callback(
        Output('spmid-filename', 'children'),
        Input('upload-spmid-data', 'contents'),
        State('upload-spmid-data', 'filename'),
        prevent_initial_call=True
    )
    def update_spmid_filename(contents, filename):
        """更新SPMID文件名显示"""
        if filename:
            return html.Div([
                html.I(className="fas fa-file-audio", style={'marginRight': '8px', 'color': '#28a745'}),
                html.Span(f"已选择: {filename}", style={'color': '#28a745', 'fontWeight': 'bold'})
            ])
        return ""




        # 点击plot的点显示详细图像
    @app.callback(
        [Output('detail-modal', 'style'),
        Output('detail-plot', 'figure'),
        Output('detail-plot2', 'figure'),
        Output('detail-plot-combined', 'figure')],
        [Input('main-plot', 'clickData'),
        Input('close-modal', 'n_clicks'),
        Input('close-modal-btn', 'n_clicks')],
        [State('detail-modal', 'style'),
        State('session-id', 'data')]
        )
    def update_plot(clickData, close_clicks, close_btn_clicks, current_style, session_id):
        """更新详细图表 - 支持多用户会话"""
        from dash import no_update

        # if session_id is None:
        if session_id not in backends:
            return current_style, no_update, no_update, no_update

        # 获取用户会话数据
        backend = backends[session_id]
        if backend is None:
            return current_style, no_update, no_update, no_update

        ctx = callback_context
        if not ctx.triggered:
            return current_style, no_update, no_update, no_update

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if trigger_id == 'main-plot' and clickData:
            # 从会话中获取数据
            # 检查数据是否已加载

            # 获取点击的点数据
            if 'points' in clickData and len(clickData['points']) > 0:
                point = clickData['points'][0]
                # logger.debug(f"点击点: {point}")

                if point.get('customdata') is None:
                    return current_style, no_update, no_update, no_update
                print(point['customdata'])
                key_id = point['customdata'][2]
                key_on = point['customdata'][0]
                key_off = point['customdata'][1]
                data_type = point['customdata'][4]
                index = point['customdata'][5]

                # todo
                detail_figure1, detail_figure2, detail_figure_combined = backend.generate_watefall_conbine_plot_by_index(index=index, is_record=(data_type=='record'))

                # 更新模态框样式为显示状态
                modal_style = {
                    'display': 'block',
                    'position': 'fixed',
                    'zIndex': '1000',
                    'left': '0',
                    'top': '0',
                    'width': '100%',
                    'height': '100%',
                    'backgroundColor': 'rgba(0,0,0,0.6)',
                    'backdropFilter': 'blur(5px)'
                }

                logger.info("🔄 显示详细分析模态框")
                return modal_style, detail_figure1, detail_figure2, detail_figure_combined
            else:
                logger.warning("点击数据格式不正确")
                return current_style, no_update, no_update, no_update

        elif trigger_id in ['close-modal', 'close-modal-btn']:
            # 关闭模态框
            modal_style = {
                'display': 'none',
                'position': 'fixed',
                'zIndex': '1000',
                'left': '0',
                'top': '0',
                'width': '100%',
                'height': '100%',
                'backgroundColor': 'rgba(0,0,0,0.6)',
                'backdropFilter': 'blur(5px)'
            }
            return modal_style, no_update, no_update, no_update

        else:
            return current_style, no_update, no_update, no_update


    # 修复PDF导出回调，添加加载动画和异常处理
    # PDF导出 - 第一步：显示加载动画
    @app.callback(
        Output('pdf-status', 'children'),
        [Input('btn-export-pdf', 'n_clicks')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def show_pdf_loading(n_clicks, session_id):
        """第一步：立即显示PDF生成加载动画"""
        if not n_clicks:
            return no_update

        # 检查会话和后端实例
        if not session_id or session_id not in backends:
            return dbc.Alert("❌ 会话已过期，请刷新页面", color="warning", duration=3000)

        backend = backends[session_id]
        if not backend or not hasattr(backend, 'all_error_notes') or not backend.all_error_notes:
            return dbc.Alert("❌ 没有可导出的数据，请先上传SPMID文件并生成分析报告", color="warning", duration=4000)

        # 显示加载动画
        return dcc.Loading(
            children=[
                dbc.Alert([
                    html.I(className="fas fa-file-pdf", style={'marginRight': '8px'}),
                    f"正在生成PDF报告，包含 {len(backend.all_error_notes)} 个异常的完整分析，请稍候..."
                ], color="info", style={'margin': '0'})
            ],
            type="dot",
            color="#dc3545",
            style={'textAlign': 'center'}
        )

    # PDF导出 - 第二步：实际生成PDF
    @app.callback(
        Output('download-pdf', 'data'),
        [Input('pdf-status', 'children')],
        [State('session-id', 'data'),
         State('btn-export-pdf', 'n_clicks')],
        prevent_initial_call=True
    )
    def generate_pdf_after_loading(pdf_status, session_id, n_clicks):
        """第二步：在显示加载动画后实际生成PDF"""
        # 只有当状态显示为加载中时才执行
        if not pdf_status or not n_clicks:
            return no_update

        # 检查是否是加载状态
        try:
            if isinstance(pdf_status, dict) and 'props' in pdf_status:
                # 这是一个Loading组件，表示正在加载
                pass
            else:
                # 不是加载状态，不执行
                return no_update
        except:
            return no_update

        # 检查会话和后端实例
        if not session_id or session_id not in backends:
            return no_update

        backend = backends[session_id]
        if not backend or not hasattr(backend, 'all_error_notes') or not backend.all_error_notes:
            return no_update

        try:
            # 添加延迟确保加载动画显示
            time.sleep(0.3)

            # 生成PDF报告
            source_info = backend.get_data_source_info() 
            current_filename = source_info.get('filename') or "未知文件"
            pdf_generator = PDFReportGenerator(backend)
            pdf_data = pdf_generator.generate_pdf_report(current_filename)

            if not pdf_data:
                return no_update

            # 生成安全的文件名
            import re
            safe_filename = re.sub(r'[<>:"/\\|?*]', '_', current_filename or "未知文件")
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"SPMID_完整分析报告_{safe_filename}_{timestamp}.pdf"

            # 确保PDF数据是base64编码的字符串
            if isinstance(pdf_data, bytes):
                pdf_data_b64 = base64.b64encode(pdf_data).decode('utf-8')
            else:
                pdf_data_b64 = pdf_data

            # 构建下载数据
            download_data = {
                'content': pdf_data_b64,
                'filename': filename,
                'type': 'application/pdf',
                'base64': True
            }

            return download_data

        except Exception as e:
            logger.error(f"PDF生成失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return no_update

    # PDF导出 - 第三步：显示完成状态
    @app.callback(
        [Output('pdf-status', 'children', allow_duplicate=True)],
        [Input('download-pdf', 'data')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def show_pdf_completion(download_data, session_id):
        """第三步：显示PDF生成完成状态"""
        if not download_data:
            return [no_update]

        # 检查会话
        if not session_id or session_id not in backends:
            return [no_update]

        backend = backends[session_id]
        if not backend:
            return [no_update]

        # 显示成功状态
        success_alert = dbc.Alert([
            html.I(className="fas fa-check-circle", style={'marginRight': '8px'}),
            f"✅ PDF报告生成成功！包含 {len(backend.all_error_notes) if hasattr(backend, 'all_error_notes') else 0} 个异常的完整分析，已开始下载"
        ], color="success", duration=5000)

        return [success_alert]

    # 键ID筛选回调函数
    @app.callback(
        [Output('main-plot', 'figure', allow_duplicate=True),
         Output('key-filter-status', 'children', allow_duplicate=True),
         Output('key-filter-dropdown', 'options', allow_duplicate=True)],
        [Input('key-filter-dropdown', 'value'),
         Input('btn-show-all-keys', 'n_clicks')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_key_filter(key_filter, show_all_clicks, session_id):
        """处理键ID筛选"""
        if not session_id or session_id not in backends:
            return no_update, no_update, no_update
        
        backend = backends[session_id]
        
        # 检查是否有数据
        if not backend.record_data and not backend.replay_data:
            return no_update, no_update, no_update
        
        # 获取触发上下文
        ctx = callback_context
        if not ctx.triggered:
            return no_update, no_update, no_update
        
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        
        # 处理"显示全部键位"按钮
        if trigger_id == 'btn-show-all-keys' and show_all_clicks and show_all_clicks > 0:
            backend.set_key_filter(None)
            key_filter = None
            logger.info("🔍 重置键ID筛选")
        # 处理键ID下拉框选择
        elif trigger_id == 'key-filter-dropdown':
            if key_filter:
                backend.set_key_filter(key_filter)
                logger.info(f"🔍 应用键ID筛选: {key_filter}")
            else:
                backend.set_key_filter(None)
                logger.info("🔍 清除键ID筛选")
        else:
            return no_update, no_update, no_update
        
        # 重新生成瀑布图
        fig = backend.generate_waterfall_plot()
        key_status = backend.get_key_filter_status()
        
        # 将key_status转换为可渲染的字符串
        if key_status['enabled']:
            key_status_text = f"已筛选 {len(key_status['filtered_keys'])} 个键位 (共 {key_status['total_available_keys']} 个)"
        else:
            key_status_text = f"显示全部 {key_status['total_available_keys']} 个键位"
        
        logger.info(f"🔍 键ID筛选状态: {key_status}")
        
        # 获取键ID选项
        key_options = backend.get_available_keys()
        
        return fig, key_status_text, key_options

    # 时间轴筛选回调函数
    @app.callback(
        [Output('main-plot', 'figure', allow_duplicate=True),
         Output('time-filter-status', 'children', allow_duplicate=True),
         Output('time-filter-slider', 'value', allow_duplicate=True)],
        [Input('btn-apply-time-filter', 'n_clicks'),
         Input('btn-reset-time-filter', 'n_clicks')],
        [State('session-id', 'data'),
         State('time-filter-slider', 'value')],
        prevent_initial_call=True
    )
    def handle_time_filter(apply_clicks, reset_clicks, session_id, time_range):
        """处理时间轴筛选"""
        if not session_id or session_id not in backends:
            return no_update, no_update, no_update
        
        backend = backends[session_id]
        
        # 检查是否有数据
        if not hasattr(backend, 'all_error_notes') or not backend.all_error_notes:
            logger.warning("⚠️ 没有分析数据，无法应用时间筛选")
            return no_update, no_update, no_update
        
        # 获取触发上下文
        ctx = callback_context
        if not ctx.triggered:
            return no_update, no_update, no_update
        
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        logger.info(f"⏰ 时间筛选触发器: {trigger_id}")
        
        # 获取原始时间范围（用于重置）
        original_time_range = backend.get_time_range()
        original_min, original_max = original_time_range
        slider_value = no_update
        
        # 处理"重置时间范围"按钮
        if trigger_id == 'btn-reset-time-filter' and reset_clicks and reset_clicks > 0:
            backend.set_time_filter(None)
            logger.info("⏰ 重置时间范围筛选")
            # 重置滑块到原始范围
            slider_value = [int(original_min), int(original_max)]
            logger.info(f"⏰ 重置滑块到原始范围: {slider_value}")
            
        # 处理"应用时间筛选"按钮
        elif trigger_id == 'btn-apply-time-filter' and apply_clicks and apply_clicks > 0:
            if time_range and len(time_range) == 2 and time_range[0] != time_range[1]:
                # 验证时间范围的合理性
                start_time, end_time = time_range
                if start_time < end_time:
                    backend.set_time_filter(time_range)
                    logger.info(f"⏰ 应用时间轴筛选: {time_range}")
                    # 保持当前滑块值
                    slider_value = no_update
                else:
                    logger.warning(f"⚠️ 时间范围无效: {time_range}")
                    backend.set_time_filter(None)
                    # 重置滑块到原始范围
                    slider_value = [int(original_min), int(original_max)]
            else:
                backend.set_time_filter(None)
                logger.info("⏰ 清除时间轴筛选（无效范围）")
                # 重置滑块到原始范围
                slider_value = [int(original_min), int(original_max)]
        else:
            logger.warning(f"⚠️ 未识别的时间筛选触发器: {trigger_id}")
            return no_update, no_update, no_update
        
        try:
            # 重新生成瀑布图
            fig = backend.generate_waterfall_plot()
            time_status = backend.get_time_filter_status()
            
            # 将time_status转换为可渲染的字符串
            if time_status['enabled']:
                time_status_text = f"时间范围: {time_status['start_time']:.2f}s - {time_status['end_time']:.2f}s (时长: {time_status['duration']:.2f}s)"
            else:
                time_status_text = "显示全部时间范围"
            
            logger.info(f"⏰ 时间轴筛选状态: {time_status}")
            
            return fig, time_status_text, slider_value
        except Exception as e:
            logger.error(f"❌ 时间筛选后生成瀑布图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # 返回错误提示图
            error_fig = _create_empty_figure_for_callback(f"时间筛选失败: {str(e)}")
            return error_fig, "时间筛选出错，请重试", no_update


    # 时间范围输入确认回调函数
    @app.callback(
        [Output('main-plot', 'figure', allow_duplicate=True),
         Output('time-range-input-status', 'children', allow_duplicate=True),
         Output('time-filter-slider', 'min', allow_duplicate=True),
         Output('time-filter-slider', 'max', allow_duplicate=True),
         Output('time-filter-slider', 'value', allow_duplicate=True),
         Output('time-filter-slider', 'marks', allow_duplicate=True)],
        [Input('btn-confirm-time-range', 'n_clicks')],
        [State('session-id', 'data'),
         State('time-range-start-input', 'value'),
         State('time-range-end-input', 'value')],
        prevent_initial_call=True
    )
    def handle_time_range_input_confirmation(n_clicks, session_id, start_time, end_time):
        """处理时间范围输入确认"""
        if not n_clicks or n_clicks <= 0:
            return no_update, no_update, no_update, no_update, no_update, no_update
        
        if not session_id or session_id not in backends:
            logger.warning("⚠️ 无效的会话ID")
            return no_update, "无效的会话ID", no_update, no_update, no_update, no_update
        
        backend = backends[session_id]
        
        try:
            # 调用后端方法更新时间范围
            success, message = backend.update_time_range_from_input(start_time, end_time)
            
            if success:
                # 重新生成瀑布图（使用新的时间范围）
                fig = backend.generate_waterfall_plot()
                
                # 只更新滑动条的当前值，不改变滑动条的范围和标记点
                new_value = [int(start_time), int(end_time)]
                
                logger.info(f"✅ 时间范围更新成功: {message}")
                status_message = f"✅ {message}"
                status_style = {'color': '#28a745', 'fontWeight': 'bold'}
                
                return fig, html.Span(status_message, style=status_style), no_update, no_update, new_value, no_update
            else:
                logger.warning(f"⚠️ 时间范围更新失败: {message}")
                status_message = f"❌ {message}"
                status_style = {'color': '#dc3545', 'fontWeight': 'bold'}
                
                return no_update, html.Span(status_message, style=status_style), no_update, no_update, no_update, no_update
                
        except Exception as e:
            logger.error(f"❌ 时间范围输入确认失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            error_message = f"❌ 时间范围更新失败: {str(e)}"
            error_style = {'color': '#dc3545', 'fontWeight': 'bold'}
            
            return no_update, html.Span(error_message, style=error_style), no_update, no_update, no_update, no_update


    # 重置显示时间范围回调函数
    @app.callback(
        [Output('main-plot', 'figure', allow_duplicate=True),
         Output('time-range-input-status', 'children', allow_duplicate=True),
         Output('time-filter-slider', 'min', allow_duplicate=True),
         Output('time-filter-slider', 'max', allow_duplicate=True),
         Output('time-filter-slider', 'value', allow_duplicate=True),
         Output('time-filter-slider', 'marks', allow_duplicate=True)],
        [Input('btn-reset-display-time-range', 'n_clicks')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_reset_display_time_range(n_clicks, session_id):
        """处理重置显示时间范围"""
        if not n_clicks or n_clicks <= 0:
            return no_update, no_update, no_update, no_update, no_update, no_update
        
        if not session_id or session_id not in backends:
            logger.warning("⚠️ 无效的会话ID")
            return no_update, "无效的会话ID", no_update, no_update, no_update, no_update
        
        backend = backends[session_id]
        
        try:
            # 重置显示时间范围
            backend.reset_display_time_range()
            
            # 重新生成瀑布图
            fig = backend.generate_waterfall_plot()
            
            # 获取原始数据时间范围并重置滑动条到原始范围
            original_min, original_max = backend.get_time_range()
            new_value = [int(original_min), int(original_max)]
            
            logger.info("✅ 显示时间范围重置成功")
            status_message = "✅ 显示时间范围已重置到原始数据范围"
            status_style = {'color': '#28a745', 'fontWeight': 'bold'}
            
            return fig, html.Span(status_message, style=status_style), no_update, no_update, new_value, no_update
                
        except Exception as e:
            logger.error(f"❌ 重置显示时间范围失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            error_message = f"❌ 重置显示时间范围失败: {str(e)}"
            error_style = {'color': '#dc3545', 'fontWeight': 'bold'}
            
            return no_update, html.Span(error_message, style=error_style), no_update, no_update, no_update, no_update
