"""
回调函数模块 - 处理Dash应用的所有回调逻辑
包含文件上传、历史记录表格交互等回调函数
"""
import base64
import json
import time
import traceback
import uuid
import math

from typing import Dict, Optional, Union, TypedDict, Tuple, List, Any
from collections import defaultdict

import pandas as pd
import numpy as np

# SPMID导入
from spmid.spmid_analyzer import SPMIDAnalyzer
import spmid


from dash import html, no_update
from dash._callback import NoUpdate
            
import dash
import dash.dependencies
import dash.dcc as dcc
import dash_bootstrap_components as dbc
from dash import Input, Output, State, ALL, callback_context, dcc, dash_table
from dash._callback_context import CallbackContext
from datetime import datetime

import plotly.graph_objects as go
from plotly.graph_objects import Figure

from scipy import stats
from ui.layout_components import create_report_layout, empty_figure, create_multi_algorithm_upload_area, create_multi_algorithm_management_area
from backend.session_manager import SessionManager
from ui.ui_processor import UIProcessor
from ui.multi_file_upload_handler import MultiFileUploadHandler
from ui.waterfall_jump_handler import WaterfallJumpHandler
from ui.delay_time_series_handler import DelayTimeSeriesHandler
from ui.relative_delay_distribution_handler import RelativeDelayDistributionHandler
from ui.delay_value_click_handler import DelayValueClickHandler
from ui.delay_histogram_click_handler import DelayHistogramClickHandler
from grade_detail_callbacks import register_all_callbacks
from utils.logger import Logger
# 后端类型导入
from backend.piano_analysis_backend import PianoAnalysisBackend



logger = Logger.get_logger()

# 自定义类型定义

class AlgorithmMetadata:
    """算法元数据的类型定义"""
    algorithm_name: str
    display_name: str
    filename: str

class OffsetAlignmentDataItem(TypedDict):
    """偏移对齐数据项的类型定义"""
    record_index: int
    replay_index: int
    key_id: int
    record_keyon: float
    replay_keyon: float
    keyon_offset: float
    record_keyoff: float
    replay_keyoff: float
    duration_offset: float
    average_offset: float
    record_duration: float
    replay_duration: float
    duration_diff: float

class OffsetAlignmentTableItem(TypedDict):
    """偏移对齐表格数据项的类型定义"""
    algorithm_name: str
    key_id: Union[int, str]
    count: int
    median: Union[float, str]
    mean: Union[float, str]
    std: Union[float, str]
    variance: Union[float, str]
    min: Union[float, str]
    max: Union[float, str]
    range: Union[float, str]
    status: str

class SPMIDNote:
    """SPMID音符对象的类型定义"""
    id: int
    hammers: pd.Series  # 锤击数据，pandas Series对象，索引为时间戳

class AlgorithmInstance:
    """算法实例的类型定义"""
    metadata: AlgorithmMetadata
    analyzer: Optional[SPMIDAnalyzer]  # SPMID分析器实例

    def is_ready(self) -> bool:
        """检查算法是否就绪"""
        pass

# 状态字典类型定义
class StateDict(TypedDict, total=False):
    """状态字典类型定义"""
    has_upload: bool
    upload_content: Optional[str]
    filename: Optional[str]
    has_history: bool
    history_id: Optional[str]
    last_upload_content: Optional[str]
    last_history_id: Optional[str]

# 文件上传结果数据类型定义
class UploadResultData(TypedDict):
    """文件上传成功时的结果数据字典"""
    filename: str
    record_count: int
    replay_count: int
    history_id: str

def _create_empty_figure_for_callback(title: str) -> Figure:
    """创建用于回调的空Plotly figure对象"""
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


def _detect_trigger_source(ctx: CallbackContext, backend: Optional[PianoAnalysisBackend],
                          contents: Optional[str], filename: Optional[str], history_id: Optional[str]) -> str:
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

def _get_current_state(contents: Optional[str], filename: Optional[str], history_id: Optional[str]) -> StateDict:
    """获取当前状态信息"""
    return {
        'has_upload': bool(contents and filename),
        'has_history': history_id is not None,
        'upload_content': contents,
        'filename': filename,
        'history_id': history_id
    }

def _get_previous_state(backend: Optional[PianoAnalysisBackend]) -> StateDict:
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

def _detect_trigger_from_context(ctx: CallbackContext, current_state: StateDict, previous_state: StateDict,
                               backend: PianoAnalysisBackend, current_time: float) -> Optional[str]:
    """从回调上下文检测触发源"""
    if not ctx.triggered:
        return None
    
    recent_trigger = ctx.triggered[0]['prop_id']
    
    # 检查历史记录选择触发
    if 'history-dropdown' in recent_trigger:
        return _handle_history_trigger(current_state, previous_state, backend, current_time)
    
    return None

def _handle_upload_trigger(current_state: StateDict, previous_state: StateDict,
                          backend: PianoAnalysisBackend, current_time: float) -> Optional[str]:
    """处理文件上传触发 - 允许重复上传相同文件以进行一致性验证"""
    # 注意：HTML文件输入在选择相同文件时不会触发change事件
    # 所以我们不依赖current_state['has_upload']，而是只要触发了回调就处理

    # 记录上传尝试，无论是否有新内容
    filename = current_state.get('filename', 'unknown')
    logger.info(f"[UPLOAD] 文件上传回调被触发: {filename}")

    # 检查是否是重复验证（使用相同文件）
    is_repeat_verification = False
    upload_content = current_state.get('upload_content')

    if not upload_content:
        # 没有新内容，使用上次的内容（重复验证场景）
        upload_content = previous_state.get('last_upload_content')
        if upload_content:
            is_repeat_verification = True
            logger.info(f"🔄 检测到重复验证请求：使用相同文件重新处理")
            logger.info(f"🎯 这将是数据一致性验证的第 {getattr(backend, '_analysis_count', 0) + 1} 次分析")
        else:
            logger.warning(f"[UPLOAD] 没有可用的文件内容")
            return None
    else:
        logger.info(f"📁 新文件上传: {filename}")

    # 记录验证状态
    if is_repeat_verification:
        backend._is_repeat_verification = True
    else:
        backend._is_repeat_verification = False

    _update_upload_state(backend, upload_content, current_time, filename)
    return 'upload'

def _handle_history_trigger(current_state: StateDict, previous_state: StateDict,
                           backend: PianoAnalysisBackend, current_time: float) -> Optional[str]:
    """处理历史记录选择触发"""
    if not current_state['has_history']:
        return None
    
    # 检查历史记录选择是否发生变化
    if current_state['history_id'] != previous_state['last_history_id']:
        _update_history_state(backend, current_state['history_id'], current_time)
        logger.info(f"[PROCESS] 检测到历史记录选择变化: {current_state['history_id']}")
        return 'history'
    else:
        logger.warning("[WARNING] 历史记录选择未变化，跳过重复处理")
        return 'skip'

def _detect_trigger_from_state_change(current_state: StateDict, previous_state: StateDict,
                                     backend: PianoAnalysisBackend, current_time: float) -> Optional[str]:
    """基于状态变化智能检测触发源"""
    # 文件上传现在由统一管理器处理，这里只处理历史记录
    if (current_state['has_history'] and
          current_state['history_id'] != previous_state['last_history_id']):
        _update_history_state(backend, current_state['history_id'], current_time)
        logger.info(f"[PROCESS] 智能检测到历史记录选择: {current_state['history_id']}")
        return 'history'
    
    return None

def _update_upload_state(backend: PianoAnalysisBackend, upload_content: str, current_time: float, filename: str = None) -> None:
    """更新文件上传状态"""
    backend._last_upload_content = upload_content
    backend._last_upload_filename = filename or getattr(backend, '_last_upload_filename', 'unknown')
    backend._last_upload_time = current_time
    backend._data_source = 'upload'

def _update_history_state(backend: PianoAnalysisBackend, history_id: str, current_time: float) -> None:
    """更新历史记录选择状态"""
    backend._last_selected_history_id = history_id
    backend._last_history_time = current_time
    backend._data_source = 'history'


def _process_file_upload_result(success: bool, result_data: Optional[UploadResultData], 
                                error_msg: Optional[str], filename: Optional[str]) -> Tuple[Optional[html.Div], Optional[html.Div]]:
    """
    处理文件上传结果并生成UI内容
    
    Args:
        success: 文件上传是否成功
        result_data: 成功时的结果数据字典，包含filename、record_count、replay_count、history_id
        error_msg: 失败时的错误信息
        filename: 上传的文件名
        
    Returns:
        Tuple[Optional[html.Div], Optional[html.Div]]: 
            - 第一个元素：成功时的信息内容（html.Div），失败时为None
            - 第二个元素：失败时的错误内容（html.Div），成功时为None
    """
    ui_processor = UIProcessor()

    if success:
        info_content = ui_processor.create_upload_success_content(result_data)
        error_content = None
    else:
        info_content = None
        error_content = ui_processor.create_upload_error_content(filename, error_msg)

    return info_content, error_content

def _handle_upload_error(error_msg, error_content):
    """处理上传错误情况"""
    if error_content:
        if error_msg and ("轨道" in error_msg or "track" in error_msg.lower() or "SPMID文件只包含" in error_msg):
            fig = _create_empty_figure_for_callback("[ERROR] SPMID文件只包含 1 个轨道，需要至少2个轨道（录制+播放）才能进行分析")
        else:
            fig = _create_empty_figure_for_callback("文件类型不符")
        # 顺序: fig, report, history_options, time_min, time_max, time_value, time_status
        return fig, error_content, no_update, 0, 1000, [0, 1000], "显示全部时间范围"
    else:
        fig = _create_empty_figure_for_callback("文件上传失败")
        error_div = html.Div([
            html.H4("文件上传失败", className="text-center text-danger"),
            html.P("请检查文件格式或联系管理员。", className="text-center")
        ])
        return fig, error_div, no_update, 0, 1000, [0, 1000], "显示全部时间范围"

def _handle_history_selection(history_id, backend):
    """处理历史记录选择操作"""
    logger.info(f"[PROCESS] 加载历史记录: {history_id}")
    
    # 使用HistoryManager处理历史记录选择（包含状态初始化）
    success, result_data, error_msg = backend.history_manager.process_history_selection(history_id, backend)
    
    # 使用UIProcessor生成UI内容
    ui_processor = UIProcessor()

    if success:
        if result_data['has_file_content']:
            # 执行数据分析
            backend._perform_error_analysis()
            
            # 自动生成瀑布图和报告
            waterfall_fig = backend.generate_waterfall_plot()
            report_content = ui_processor.generate_history_report(backend, result_data['filename'], result_data['history_id'])
        else:
            # 没有文件内容，只显示基本信息
            waterfall_fig = ui_processor.create_empty_figure("历史记录无文件内容")
            report_content = ui_processor.create_history_basic_info_content(result_data)
    else:
        waterfall_fig = ui_processor.create_empty_figure("历史记录加载失败")
        report_content = ui_processor.create_error_content("历史记录加载失败", error_msg)
    
    if waterfall_fig and report_content:
        logger.info("[OK] 历史记录加载完成，返回瀑布图和报告")
        
        # 获取键ID筛选相关数据
        available_keys = backend.get_available_keys()
        key_options = [{'label': f'键位 {key_id}', 'value': key_id} for key_id in available_keys]
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
        
        # 历史记录情况下，当前筛选值取后端已设置的filtered_keys
        kstatus = backend.get_key_filter_status()
        current_value = kstatus.get('filtered_keys', []) if kstatus else []
        return waterfall_fig, report_content, no_update, key_options, key_status_text, current_value, no_update, no_update, no_update, time_status_text
    else:
        logger.error("[ERROR] 历史记录加载失败")
        empty_fig = _create_empty_figure_for_callback("历史记录加载失败")
        error_content = html.Div([
            html.H4("历史记录加载失败", className="text-center text-danger"),
            html.P("请尝试选择其他历史记录", className="text-center")
        ])
        return empty_fig, error_content, no_update, 0, 1000, [0, 1000], "显示全部时间范围", no_update


def _handle_waterfall_button(backend):
    """处理瀑布图按钮点击"""
    current_data_source = getattr(backend, '_data_source', 'none') if backend else 'none'
    logger.info(f"[PROCESS] 生成瀑布图（数据源: {current_data_source}）")
    
    # 检查是否有已加载的数据 - 改为检查更基本的数据状态
    has_data = (backend.analyzer and 
                (backend.plot_generator.valid_record_data or backend.plot_generator.valid_replay_data or
                 (hasattr(backend.analyzer, 'valid_record_data') and backend.analyzer.valid_record_data) or
                 (hasattr(backend.analyzer, 'valid_replay_data') and backend.analyzer.valid_replay_data)))
    
    if has_data:
        fig = backend.generate_waterfall_plot()
        
        # 获取实际的时间范围并更新滑动条
        try:
            time_range = backend.get_time_range()
            time_min, time_max = time_range
            
            # 确保时间范围是有效的
            if isinstance(time_min, (int, float)) and isinstance(time_max, (int, float)) and time_min < time_max:
                # 创建合理的标记点
                range_size = time_max - time_min
                if range_size <= 1000:
                    step = max(1, range_size // 5)
                elif range_size <= 10000:
                    step = max(10, range_size // 10)
                else:
                    step = max(100, range_size // 20)
                
                marks = {}
                for i in range(int(time_min), int(time_max) + 1, step):
                    if i == time_min or i == time_max or (i - time_min) % (step * 2) == 0:
                        marks[i] = str(i)
                
                logger.info(f"⏰ 瀑布图按钮更新滑动条: min={time_min}, max={time_max}, 范围={range_size}")
                # key_value 不在此回调中更新
                return fig, no_update, no_update, time_min, time_max, [time_min, time_max], "显示全部时间范围"
            else:
                logger.warning(f"[WARNING] 时间范围无效: {time_range}")
                return fig, no_update, no_update, 0, 1000, [0, 1000], "显示全部时间范围"
        except Exception as e:
            logger.error(f"[ERROR] 获取时间范围失败: {e}")
            return fig, no_update, no_update, 0, 1000, [0, 1000], "显示全部时间范围", no_update
    else:
        if current_data_source == 'history':
            empty_fig = _create_empty_figure_for_callback("请选择历史记录或上传新文件")
        else:
            empty_fig = _create_empty_figure_for_callback("请先上传SPMID文件")
            return empty_fig, no_update, no_update, 0, 1000, [0, 1000], "显示全部时间范围"


def register_callbacks(app, session_manager: SessionManager, history_manager):
    """注册所有回调函数"""

    # 导入回调模块
    from ui.session_callbacks import register_session_callbacks
    from ui.upload_history_callbacks import register_upload_history_callbacks
    from ui.algorithm_callbacks import register_algorithm_callbacks
    from ui.scatter_callbacks import register_scatter_callbacks

    # 注册会话和初始化管理回调
    register_session_callbacks(app, session_manager, history_manager)

    # 注册文件上传和历史记录管理回调
    register_upload_history_callbacks(app, session_manager)

    # 注册算法管理回调
    register_algorithm_callbacks(app, session_manager)

    # 注册散点图回调
    register_scatter_callbacks(app, session_manager)

    # 创建瀑布图跳转处理器实例
    waterfall_jump_handler = WaterfallJumpHandler(session_manager)

    # 创建延时时间序列图处理器实例
    delay_time_series_handler = DelayTimeSeriesHandler(session_manager)

    # 创建相对延时分布图处理器实例
    relative_delay_distribution_handler = RelativeDelayDistributionHandler(session_manager)

    # 创建延迟值点击处理器实例
    delay_value_click_handler = DelayValueClickHandler(session_manager)

    # 创建延时直方图点击处理器实例
    delay_histogram_click_handler = DelayHistogramClickHandler(session_manager)

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
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update, no_update, no_update
        
        # 检查是否有数据
        if not hasattr(backend, 'all_error_notes') or not backend.all_error_notes:
            logger.warning("[WARNING] 没有分析数据，无法应用时间筛选")
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
                    logger.warning(f"[WARNING] 时间范围无效: {time_range}")
                    backend.set_time_filter(None)
                    # 重置滑块到原始范围
                    slider_value = [int(original_min), int(original_max)]
            else:
                backend.set_time_filter(None)
                logger.info("⏰ 清除时间轴筛选（无效范围）")
                # 重置滑块到原始范围
                slider_value = [int(original_min), int(original_max)]
        else:
            logger.warning(f"[WARNING] 未识别的时间筛选触发器: {trigger_id}")
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
            logger.error(f"[ERROR] 时间筛选后生成瀑布图失败: {e}")
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
        logger.info(f"[PROCESS] 时间范围输入确认回调被触发: n_clicks={n_clicks}, start_time={start_time}, end_time={end_time}")
        
        if not n_clicks or n_clicks <= 0:
            logger.info("[WARNING] 按钮未点击，跳过处理")
            return no_update, no_update, no_update, no_update, no_update, no_update
        
        backend = session_manager.get_backend(session_id)
        if not backend:
            logger.warning("[WARNING] 无效的会话ID")
            return no_update, "无效的会话ID", no_update, no_update, no_update, no_update
        
        if start_time is None or end_time is None:
            logger.warning("[WARNING] 时间范围输入为空")
            return no_update, "请输入有效的时间范围", no_update, no_update, no_update, no_update
        
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update
        
        try:
            logger.info(f"[PROCESS] 调用后端更新时间范围: start_time={start_time}, end_time={end_time}")
            # 调用后端方法更新时间范围
            success, message = backend.update_time_range_from_input(start_time, end_time)
            
            if success:
                logger.info(f"[OK] 后端时间范围更新成功: {message}")
                # 重新生成瀑布图（使用新的时间范围）
                fig = backend.generate_waterfall_plot()
                
                # 更新滑动条的范围和当前值
                new_min = int(start_time)
                new_max = int(end_time)
                new_value = [new_min, new_max]
                
                # 创建新的标记点
                range_size = new_max - new_min
                if range_size <= 1000:
                    step = max(1, range_size // 5)
                elif range_size <= 10000:
                    step = max(10, range_size // 10)
                else:
                    step = max(100, range_size // 20)
                
                new_marks = {}
                for i in range(new_min, new_max + 1, step):
                    if i == new_min or i == new_max or (i - new_min) % (step * 2) == 0:
                        new_marks[i] = str(i)
                
                logger.info(f"[OK] 时间范围更新成功: {message}")
                logger.info(f"⏰ 更新滑动条范围: min={new_min}, max={new_max}, value={new_value}")
                logger.info(f"⏰ 新标记点: {new_marks}")
                status_message = f"[OK] {message}"
                status_style = {'color': '#28a745', 'fontWeight': 'bold'}
                
                return fig, html.Span(status_message, style=status_style), new_min, new_max, new_value, new_marks
            else:
                logger.warning(f"[WARNING] 时间范围更新失败: {message}")
                status_message = f"[ERROR] {message}"
                status_style = {'color': '#dc3545', 'fontWeight': 'bold'}
                
                return no_update, html.Span(status_message, style=status_style), no_update, no_update, no_update, no_update
                
        except Exception as e:
            logger.error(f"[ERROR] 时间范围输入确认失败: {e}")
            logger.error(traceback.format_exc())
            
            error_message = f"[ERROR] 时间范围更新失败: {str(e)}"
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
        
        backend = session_manager.get_backend(session_id)
        if not backend:
            logger.warning("[WARNING] 无效的会话ID")
            return no_update, "无效的会话ID", no_update, no_update, no_update, no_update
        
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update
        
        try:
            # 重置显示时间范围
            backend.reset_display_time_range()
            
            # 重新生成瀑布图
            fig = backend.generate_waterfall_plot()
            
            # 获取原始数据时间范围并重置滑动条到原始范围
            original_min, original_max = backend.get_time_range()
            new_value = [int(original_min), int(original_max)]
            
            logger.info("[OK] 显示时间范围重置成功")
            status_message = "[OK] 显示时间范围已重置到原始数据范围"
            status_style = {'color': '#28a745', 'fontWeight': 'bold'}
            
            return fig, html.Span(status_message, style=status_style), no_update, no_update, new_value, no_update
                
        except Exception as e:
            logger.error(f"[ERROR] 重置显示时间范围失败: {e}")
            logger.error(traceback.format_exc())
            
            error_message = f"[ERROR] 重置显示时间范围失败: {str(e)}"
            error_style = {'color': '#dc3545', 'fontWeight': 'bold'}
            
            return no_update, html.Span(error_message, style=error_style), no_update, no_update, no_update, no_update

    # 偏移对齐分析 - 页面加载时自动生成
    @app.callback(
        Output('offset-alignment-plot', 'children', allow_duplicate=True),
        Output('offset-alignment-table', 'data', allow_duplicate=True),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def auto_generate_alignment_on_load(report_content, session_id):
        """报告内容加载时，自动生成偏移对齐柱状图与表格"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update, no_update
        
        try:
            # 检查是否有激活的算法
            active_algorithms = backend.get_active_algorithms()
            if not active_algorithms:
                logger.debug("[DEBUG] 没有激活的算法，跳过偏移对齐分析生成")
                empty = backend.plot_generator._create_empty_plot("没有激活的算法")
                return [dcc.Graph(figure=empty)], []
            
            result = backend.generate_offset_alignment_plot()
            table_data = backend.get_offset_alignment_data()
            
            children = []
            if isinstance(result, list):
                # 多图模式：返回多个独立的图表
                for item in result:
                    fig = item.get('figure')
                    
                    # 创建单个图表的容器
                    children.append(html.Div([
                        dcc.Graph(
                            figure=fig,
                            style={'height': '500px'},
                            config={'displayModeBar': True}
                        )
                    ], className="mb-4", style={'border': '1px solid #eee', 'padding': '10px', 'borderRadius': '5px', 'backgroundColor': 'white', 'boxShadow': '0 1px 3px rgba(0,0,0,0.1)'}))
            else:
                # 单图模式 (Legacy)：返回单个图表
                children.append(dcc.Graph(
                    figure=result,
                    style={'height': '800px'}
                ))
            
            logger.info("[OK] 偏移对齐分析（自动）生成成功")
            return children, table_data
            
        except Exception as e:
            logger.error(f"[ERROR] 自动生成偏移对齐分析失败: {e}")
            logger.error(traceback.format_exc())
            empty = backend.plot_generator._create_empty_plot(f"生成失败: {str(e)}")
            return [dcc.Graph(figure=empty)], no_update

    # 更新按键与相对延时散点图的曲子选择器选项
    @app.callback(
        [Output({'type': 'key-delay-scatter-algorithm-selector', 'index': ALL}, 'options'),
         Output({'type': 'key-delay-scatter-algorithm-selector', 'index': ALL}, 'value')],
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def update_key_delay_scatter_algorithm_selector(report_content, session_id):
        backend = session_manager.get_backend(session_id)
        if not backend or not hasattr(backend, 'multi_algorithm_manager'):
            return [], []
            
        try:
            active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()
            if not active_algorithms:
                return [], []
            
            options = []
            values = []
            for alg in active_algorithms:
                unique_name = alg.metadata.algorithm_name  # unique_algorithm_name
                display_name = alg.metadata.display_name    # 用户输入的算法名
                filename = alg.metadata.filename            # 原始文件名

                # 创建更具描述性的标签：算法名 (文件名)
                # 例如：pid (11-21-音阶测试pid.spmid)
                descriptive_label = f"{display_name} ({filename})"
                options.append({'label': descriptive_label, 'value': unique_name})
                values.append(unique_name)
            
            # 返回列表以匹配 Pattern Matching Output
            return [options], [values]
            
        except Exception as e:
            logger.error(f"[ERROR] 更新曲子选择器失败: {e}")
            return [], []

    def _validate_multi_algorithm_analysis(backend):
        """验证多算法模式并获取分析结果"""
        # 使用统一的模式检查方法
        mode, algorithm_count = backend.get_current_analysis_mode()

        if mode != "multi":
            logger.warning(f"[WARNING] 当前为{mode}模式，无法生成相对延时分布图（需要多算法模式）")
            return None, html.Div([
                dbc.Alert("需要多算法模式才能生成相对延时分布图", color="warning")
            ])

        # 获取分析结果
        analysis_result = backend.get_same_algorithm_relative_delay_analysis()
        if analysis_result.get('status') != 'success':
            return None, html.Div([
                dbc.Alert(analysis_result.get('message', '分析失败'), color="danger")
            ])

        algorithm_groups = analysis_result.get('algorithm_groups', {})
        if not algorithm_groups:
            return None, html.Div([
                dbc.Alert("没有算法组数据", color="warning")
            ])

        return analysis_result, None

    def _collect_songs_data(algorithm_groups):
        """收集所有需要绘制的曲子信息"""
        all_songs = []
        for display_name, group_data in algorithm_groups.items():
            song_data = group_data.get('song_data', [])
            group_relative_delays = group_data.get('relative_delays', [])

            if not group_relative_delays:
                continue

            # 添加每个曲子
            for song_info in song_data:
                song_relative_delays = song_info.get('relative_delays', [])
                if song_relative_delays:
                    filename_display = song_info.get('filename_display', song_info.get('filename', '未知文件'))
                    all_songs.append((display_name, filename_display, song_relative_delays, None, song_info))

            # 添加汇总
            all_songs.append((display_name, '汇总', None, group_relative_delays, None))

        return all_songs

    def _create_overall_velocity_plot(algorithm_groups):
        """生成整体锤速对比图"""
        try:
            # 收集所有算法组的锤速数据
            all_velocity_data = _collect_velocity_data(algorithm_groups)

            if not all_velocity_data:
                return None

            # 按按键ID和算法分组计算平均锤速差值
            key_algorithm_stats = _process_velocity_statistics(all_velocity_data)

            # 计算每个按键在每个算法+曲子组合下的平均锤速差值
            all_key_ids = sorted(key_algorithm_stats.keys())
            all_algorithm_filenames = sorted(set(item['algorithm_filename'] for item in all_velocity_data))

            plot_data = _prepare_multi_algorithm_velocity_plot_data(key_algorithm_stats, all_algorithm_filenames, all_key_ids)

            # 创建整体锤速对比图
            return _create_velocity_figure(plot_data)

        except Exception as e:
            logger.warning(f"生成整体锤速对比图失败: {e}")
            return None

    def _create_velocity_control_panel(plot_data):
        """创建锤速对比图的控制面板"""
        if not plot_data:
            return html.Div("无数据")

        # 提取所有算法+曲子名称
        algorithm_filenames = [data['algorithm_filename'] for data in plot_data]

        # 创建颜色映射
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']

        # 创建控制选项
        control_options = []
        for i, algorithm_filename in enumerate(algorithm_filenames):
            color = colors[i % len(colors)]
            control_options.append({
                'label': html.Div([
                    html.Span('●', style={'color': color, 'marginRight': '8px', 'fontSize': '12px'}),
                    html.Span(algorithm_filename, style={'fontSize': '12px'})
                ], style={'display': 'flex', 'alignItems': 'center'}),
                'value': algorithm_filename
            })

        return dbc.Checklist(
            id='velocity-plot-legend-control',
            options=control_options,
            value=algorithm_filenames,  # 默认全部选中
            inline=False,
            style={'columnCount': 2, 'columnGap': '20px'}  # 两列布局
        )

    def _collect_velocity_data(algorithm_groups):
        """收集所有算法组的锤速数据"""
        all_velocity_data = []
        for display_name, group_data in algorithm_groups.items():
            song_data = group_data.get('song_data', [])
            for song_info in song_data:
                hammer_velocity_diffs = song_info.get('hammer_velocity_diffs', [])
                filename_display = song_info.get('filename_display', song_info.get('filename', '未知文件'))
                if hammer_velocity_diffs:
                    for item in hammer_velocity_diffs:
                        all_velocity_data.append({
                            'algorithm': display_name,
                            'filename': filename_display,
                            'algorithm_filename': f'{display_name} - {filename_display}',
                            'key_id': item['key_id'],
                            'velocity_diff': item['velocity_diff'],
                            'record_velocity': item['record_velocity'],
                            'replay_velocity': item['replay_velocity']
                        })
        return all_velocity_data

    def _process_velocity_statistics(all_velocity_data):
        """按按键ID和算法+曲子分组计算平均锤速差值"""
        key_algorithm_stats = defaultdict(lambda: defaultdict(list))

        for item in all_velocity_data:
            key_id = item['key_id']
            algorithm_filename = item['algorithm_filename']
            key_algorithm_stats[key_id][algorithm_filename].append(item['velocity_diff'])

        return key_algorithm_stats

    def _prepare_multi_algorithm_velocity_plot_data(key_algorithm_stats, all_algorithm_filenames, all_key_ids):
        """为多个算法+曲子组合准备绘图数据"""
        plot_data = []

        for algorithm_filename in all_algorithm_filenames:
            x_keys = []
            y_diffs = []
            hover_texts = []

            for key_id in all_key_ids:
                if algorithm_filename in key_algorithm_stats[key_id]:
                    diffs = key_algorithm_stats[key_id][algorithm_filename]
                    avg_diff = np.mean(diffs)
                    x_keys.append(str(key_id))
                    y_diffs.append(avg_diff)

                    # 计算平均播放锤速
                    record_vel = 100  # 默认录制锤速
                    replay_vel = record_vel + avg_diff
                    hover_texts.append(f'按键 {key_id}<br>{algorithm_filename}<br>锤速差值: {avg_diff:.1f}<br>录制锤速: {record_vel}<br>平均播放锤速: {replay_vel:.1f}')
                else:
                    x_keys.append(str(key_id))
                    y_diffs.append(0)  # 没有数据时显示0
                    hover_texts.append(f'按键 {key_id}<br>{algorithm_filename}<br>无数据')

            if y_diffs:  # 只有有数据时才添加
                plot_data.append({
                    'algorithm_filename': algorithm_filename,
                    'x': x_keys,
                    'y': y_diffs,
                    'hovertext': hover_texts
                })

        return plot_data

    def _create_velocity_figure(plot_data):
        """创建整体锤速对比图表"""
        if not plot_data:
            return None

        velocity_fig = go.Figure()

        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']
        for i, data in enumerate(plot_data):
            color = colors[i % len(colors)]
            velocity_fig.add_trace(go.Bar(
                x=data['x'],
                y=data['y'],
                name=data['algorithm_filename'],
                marker=dict(color=color, opacity=0.8),
                hovertext=data['hovertext'],
                hovertemplate='%{hovertext}<extra></extra>'
            ))

        # 添加零线
        velocity_fig.add_hline(
            y=0,
            line_dash="dash",
            line_color="red",
            opacity=0.7
        )

        velocity_fig.update_layout(
            title='同种算法不同曲子的锤速对比',
            xaxis_title='按键ID',
            yaxis_title='锤速差值 (播放锤速 - 录制锤速)',
            height=500,
            template='plotly_white',
            barmode='group',  # 分组柱状图
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                bgcolor='rgba(255, 255, 255, 0.8)',
                bordercolor='rgba(0, 0, 0, 0.2)',
                borderwidth=1
            ),
            showlegend=True
        )

        # 创建控制面板
        control_panel = _create_velocity_control_panel(plot_data)

        # 返回包含图表和控制面板的容器
        return html.Div([
            html.Div([
                html.H6("图注控制", className="mb-2", style={'color': '#2c3e50', 'fontWeight': 'bold'}),
                control_panel
            ], className="mb-3", style={'backgroundColor': '#f8f9fa', 'padding': '15px', 'borderRadius': '8px', 'border': '1px solid #dee2e6'}),
            dcc.Graph(
                id='overall-hammer-velocity-comparison-plot',
                figure=velocity_fig,
                config={
                    'displayModeBar': True,
                    'displaylogo': False,
                    'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d'],
                    'modeBarButtonsToAdd': []
                },
                style={'height': '500px'}
            )
        ])

    def _create_subplot_figure(subplot_idx, display_name, filename_display, delays_array, base_color):
        """为单个子图创建图表"""
        

        # 生成子图标题
        if filename_display == '汇总':
            subplot_title = f'{display_name} (汇总)'
        else:
            subplot_title = f'{display_name} - {filename_display}'

        # 计算直方图数据
        hist, bin_edges = np.histogram(delays_array, bins=50, density=False)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

        # 为每个bin创建customdata
        customdata_list = []
        for i, bin_center in enumerate(bin_centers):
            bin_left = bin_edges[i]
            bin_right = bin_edges[i + 1]
            customdata_list.append([
                subplot_idx,
                display_name,
                filename_display,
                bin_center,
                bin_left,
                bin_right
            ])

        # 计算密度曲线
        bin_width = bin_edges[1] - bin_edges[0]
        try:
            if len(delays_array) < 2 or np.std(delays_array) == 0:
                raise ValueError("Insufficient data or zero variance")
                
            kde = stats.gaussian_kde(delays_array)
            x_density = np.linspace(delays_array.min(), delays_array.max(), 200)
            # 修正：乘以bin_width
            y_density = kde(x_density) * len(delays_array) * bin_width
        except:
            # KDE计算失败（如数据点太少或全相同），不绘制曲线
            y_density = []
            x_density = []

        # 创建独立的图表
        fig = go.Figure()

        # 添加直方图
        fig.add_trace(
            go.Bar(
                x=bin_centers,
                y=hist,
                name='相对延时分布',
                marker=dict(
                    color=f'rgba({int(base_color[1:3], 16)}, {int(base_color[3:5], 16)}, {int(base_color[5:7], 16)}, 0.6)',
                    line=dict(color=base_color, width=1.5 if filename_display == '汇总' else 1)
                ),
                opacity=0.7,
                showlegend=False,
                hovertemplate=f'相对延时: %{{x:.2f}} ms<br>频数: %{{y}}<extra></extra>',
                customdata=customdata_list
            )
        )

        # 添加密度曲线
        fig.add_trace(
            go.Scatter(
                x=x_density,
                y=y_density,
                mode='lines',
                name='密度曲线',
                line=dict(
                    color=base_color,
                    width=3 if filename_display == '汇总' else 2,
                    dash='dash' if filename_display == '汇总' else 'solid'
                ),
                showlegend=False,
                hovertemplate=f'相对延时: %{{x:.2f}} ms<br>密度: %{{y:.2f}}<extra></extra>'
            )
        )

        # 计算统计量
        mean = np.mean(delays_array)
        std = np.std(delays_array)
        median = np.median(delays_array)

        # 添加±1σ、±2σ、±3σ区间
        for sigma, color in [(1, 'rgba(255, 0, 0, 0.08)'), (2, 'rgba(255, 0, 0, 0.12)'), (3, 'rgba(255, 0, 0, 0.15)')]:
            fig.add_vrect(
                x0=mean - sigma * std,
                x1=mean + sigma * std,
                fillcolor=color,
                layer="below",
                line_width=0
            )

        # 添加均值线
        fig.add_vline(
            x=mean,
            line_dash="dash",
            line_color="green",
            line_width=1.5
        )

        # 添加中位数线
        fig.add_vline(
            x=median,
            line_dash="dot",
            line_color="orange",
            line_width=1.5
        )

        # 更新布局
        fig.update_layout(
            title=subplot_title,
            xaxis_title='相对延时 (ms)',
            yaxis_title='频数',
            height=500,
            template='plotly_white',
            showlegend=False
        )

        return fig

    def _create_subplot_velocity_plot(subplot_title, song_info, subplot_idx):
        """为单个子图创建锤速对比图"""
        

        if not song_info or 'hammer_velocity_diffs' not in song_info:
            return None

        hammer_velocity_diffs = song_info['hammer_velocity_diffs']
        if not hammer_velocity_diffs:
            return None

        # 按按键ID分组计算平均锤速差值
        key_velocity_stats = defaultdict(list)

        for item in hammer_velocity_diffs:
            key_id = item['key_id']
            key_velocity_stats[key_id].append(item['velocity_diff'])

        # 计算每个按键的平均锤速差值
        key_avg_diffs = {}
        for key_id, diffs in key_velocity_stats.items():
            key_avg_diffs[key_id] = np.mean(diffs)

        if not key_avg_diffs:
            return None

        # 排序按键ID
        sorted_keys = sorted(key_avg_diffs.keys())
        x_keys = [str(k) for k in sorted_keys]
        y_diffs = [key_avg_diffs[k] for k in sorted_keys]

        # 创建锤速对比图
        velocity_fig = go.Figure()
        velocity_fig.add_trace(go.Bar(
            x=x_keys,
            y=y_diffs,
            name='锤速差值',
            marker=dict(
                color='#ff9800',
                opacity=0.8,
                line=dict(color='#e65100', width=1)
            ),
            hovertemplate='<b>按键 %{x}</b><br>' +
                         '平均锤速差值: %{y:.1f}<br>' +
                         '<b>录制锤速: 100</b><br>' +
                         '<b>平均播放锤速: %{customdata:.1f}</b><extra></extra>',
            customdata=[100 + diff for diff in y_diffs]  # 播放锤速 = 录制锤速 + 差值
        ))

        # 添加零线
        velocity_fig.add_hline(
            y=0,
            line_dash="dash",
            line_color="red",
            opacity=0.7
        )

        velocity_fig.update_layout(
            title=f'{subplot_title} - 锤速对比',
            xaxis_title='按键ID',
            yaxis_title='锤速差值 (播放锤速 - 录制锤速)',
            height=400,
            template='plotly_white',
            showlegend=False
        )

        return dcc.Graph(
            id={'type': 'hammer-velocity-comparison-plot', 'index': subplot_idx},
            figure=velocity_fig,
            style={'height': '400px', 'marginTop': '20px'}
        )

    def _create_subplot_container(subplot_idx, fig, velocity_plot, display_name, filename_display):
        """创建完整的子图容器"""
        # 创建图表和表格容器（使用字典形式的ID以支持Pattern Matching Callbacks）
        plot_id = {'type': 'relative-delay-distribution-plot', 'index': subplot_idx}
        table_id = {'type': 'relative-delay-distribution-table', 'index': subplot_idx}
        title_id = {'type': 'relative-delay-distribution-title', 'index': subplot_idx}
        info_id = {'type': 'relative-delay-distribution-info', 'index': subplot_idx}
        container_id = {'type': 'relative-delay-distribution-container', 'index': subplot_idx}

        # 添加相对延时分布图
        plot_elements = [
            dcc.Graph(
                id=plot_id,
                figure=fig,
                style={'height': '500px'}
            )
        ]

        # 如果有锤速对比图，也添加进去
        if velocity_plot:
            plot_elements.append(velocity_plot)

        return html.Div([
            *plot_elements,
            html.P("💡 提示：点击直方图中的柱状图区域，可查看该相对延时范围内的数据点详情",
                   className="text-muted",
                   style={'fontSize': '12px', 'marginTop': '10px', 'marginBottom': '10px'}),
            html.Div([
                html.Div(id=title_id,
                        style={'marginTop': '15px', 'marginBottom': '10px',
                               'fontSize': '16px', 'fontWeight': 'bold',
                               'color': '#9c27b0', 'padding': '8px 12px',
                               'backgroundColor': '#f3e5f5', 'borderRadius': '4px',
                               'borderLeft': '4px solid #9c27b0', 'display': 'none'}),
                html.Div(id=info_id,
                        style={'marginBottom': '10px', 'fontSize': '14px', 'fontWeight': 'bold', 'color': '#2c3e50', 'display': 'none'}),
                dash_table.DataTable(
                    id=table_id,
                    columns=[
                        {"name": "算法名称", "id": "algorithm_name"},
                        {"name": "按键ID", "id": "key_id"},
                        {"name": "相对延时(ms)", "id": "relative_delay_ms", "type": "numeric", "format": {"specifier": ".2f"}},
                        {"name": "绝对延时(ms)", "id": "absolute_delay_ms", "type": "numeric", "format": {"specifier": ".2f"}},
                        {"name": "录制索引", "id": "record_index"},
                        {"name": "播放索引", "id": "replay_index"},
                        {"name": "录制开始(0.1ms)", "id": "record_keyon"},
                        {"name": "播放开始(0.1ms)", "id": "replay_keyon"},
                        {"name": "持续时间差(0.1ms)", "id": "duration_offset"},
                    ],
                    data=[],
                    page_action='none',
                    style_cell={
                        'textAlign': 'center',
                        'fontSize': '12px',
                        'fontFamily': 'Arial, sans-serif',
                        'padding': '8px',
                        'overflow': 'hidden',
                        'textOverflow': 'ellipsis',
                    },
                    style_header={
                        'backgroundColor': '#f8f9fa',
                        'fontWeight': 'bold',
                        'border': '1px solid #dee2e6',
                        'position': 'sticky',
                        'top': 0,
                        'zIndex': 1
                    },
                    style_data={
                        'whiteSpace': 'normal',
                        'height': 'auto',
                    },
                    style_table={
                        'overflowX': 'auto',
                        'overflowY': 'auto',
                        'maxHeight': '600px',
                    }
                )
            ], style={'display': 'none'}, id=container_id)
        ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'})

    # 锤速对比图控制面板回调
    @app.callback(
        Output('overall-hammer-velocity-comparison-plot', 'figure'),
        [Input('velocity-plot-legend-control', 'value')],
        [State('overall-hammer-velocity-comparison-plot', 'figure')],
        prevent_initial_call=True
    )
    def update_velocity_plot_visibility(selected_algorithms, current_figure):
        """根据控制面板的选择更新锤速对比图的可见性"""
        if not current_figure or not current_figure.data:
            return current_figure

        # 更新每个trace的可见性
        for i, trace in enumerate(current_figure.data):
            algorithm_filename = trace.name
            trace.visible = algorithm_filename in selected_algorithms

        return current_figure


    # 同种算法相对延时分布图回调 - 报告内容加载时自动生成
    @app.callback(
        Output('relative-delay-distribution-container', 'children'),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_generate_relative_delay_distribution_plot(report_content, session_id):
        """处理同种算法相对延时分布图自动生成 - 当报告内容更新时触发，为每个子图创建独立的图表和表格区域"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update

        try:
            # 验证多算法模式和获取分析结果
            analysis_result, error_div = _validate_multi_algorithm_analysis(backend)
            if error_div:
                return error_div

            algorithm_groups = analysis_result.get('algorithm_groups', {})

            # 收集所有需要绘制的曲子信息
            all_songs = _collect_songs_data(algorithm_groups)

            if not all_songs:
                return html.Div([
                    dbc.Alert("没有有效的相对延时数据", color="warning")
                ])
            
            # 生成整体锤速对比图
            overall_velocity_plot = _create_overall_velocity_plot(algorithm_groups)

            # 为每个子图创建独立的图表和表格区域
            children = []
            algorithm_color_map = {}
            color_idx = 0

            # 在最上方添加整体锤速对比图
            if overall_velocity_plot:
                children.append(
                    html.Div([
                        html.H5("整体锤速对比", className="mb-3",
                               style={'color': '#ff9800', 'fontWeight': 'bold', 'textAlign': 'center'}),
                        overall_velocity_plot
                    ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'})
                )

            # 颜色方案
            colors = [
                '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728',
                '#9467bd', '#8c564b', '#e377c2', '#7f7f7f'
            ]

            for subplot_idx, (display_name, filename_display, song_relative_delays, group_relative_delays, song_info) in enumerate(all_songs, 1):
                # 确定使用的数据
                if filename_display == '汇总':
                    delays_array = np.array(group_relative_delays)
                else:
                    delays_array = np.array(song_relative_delays)

                if len(delays_array) == 0:
                    continue

                # 获取或分配颜色
                if display_name not in algorithm_color_map:
                    algorithm_color_map[display_name] = colors[color_idx % len(colors)]
                    color_idx += 1
                base_color = algorithm_color_map[display_name]

                # 生成子图标题
                if filename_display == '汇总':
                    subplot_title = f'{display_name} (汇总)'
                else:
                    subplot_title = f'{display_name} - {filename_display}'

                # 创建子图图表
                fig = _create_subplot_figure(subplot_idx, display_name, filename_display, delays_array, base_color)

                # 生成锤速对比图（仅对非汇总的曲子）
                velocity_plot = None
                if filename_display != '汇总':
                    velocity_plot = _create_subplot_velocity_plot(subplot_title, song_info, subplot_idx)

                # 创建完整的子图容器
                subplot_container = _create_subplot_container(subplot_idx, fig, velocity_plot, display_name, filename_display)
                children.append(subplot_container)
            
            logger.info("[OK] 同种算法相对延时分布图生成成功")
            return children
            
        except Exception as e:
            logger.error(f"[ERROR] 生成相对延时分布图失败: {e}")
            logger.error(traceback.format_exc())
            return html.Div([
                dbc.Alert(f"生成失败: {str(e)}", color="danger")
            ])
    
    # 同种算法相对延时分布图点击回调 - 显示指定相对延时范围内的数据点详情
    # 使用Pattern Matching Callbacks处理动态生成的图表点击
    @app.callback(
        [Output({'type': 'relative-delay-distribution-table', 'index': dash.dependencies.MATCH}, 'data'),
         Output({'type': 'relative-delay-distribution-table', 'index': dash.dependencies.MATCH}, 'style_table'),
         Output({'type': 'relative-delay-distribution-info', 'index': dash.dependencies.MATCH}, 'children'),
         Output({'type': 'relative-delay-distribution-container', 'index': dash.dependencies.MATCH}, 'style'),
         Output({'type': 'relative-delay-distribution-title', 'index': dash.dependencies.MATCH}, 'children')],
        [Input({'type': 'relative-delay-distribution-plot', 'index': dash.dependencies.MATCH}, 'clickData')],
        [State('session-id', 'data'),
         State({'type': 'relative-delay-distribution-plot', 'index': dash.dependencies.MATCH}, 'id')],
        prevent_initial_call=True
    )
    def handle_relative_delay_distribution_click(click_data, session_id, plot_id):
        """处理同种算法相对延时分布图点击事件，显示该相对延时范围内的数据点详情"""
        return relative_delay_distribution_handler.handle_click(click_data, session_id, plot_id)
    
    def _find_algorithm_by_indices(algorithms, record_index, replay_index, log_prefix=""):
        """[Helper] 在算法列表中通过匹配对索引查找算法实例"""
        for alg in algorithms:
            if alg.analyzer and hasattr(alg.analyzer, 'matched_pairs'):
                for r_idx, p_idx, _, _ in alg.analyzer.matched_pairs:
                    if r_idx == record_index and p_idx == replay_index:
                        logger.info(f"{log_prefix} 通过匹配对找到算法实例: {alg.metadata.algorithm_name}")
                        return alg
        return None
    
    def _find_target_algorithm_instance(backend, algorithm_name, record_index, replay_index):
        """[Helper] 在多算法模式下查找目标算法实例"""
        if not backend.multi_algorithm_mode or not backend.multi_algorithm_manager:
            return None
            
        all_algorithms = backend.multi_algorithm_manager.get_all_algorithms()
        
        # 1. 首先尝试精确匹配算法名称
        candidate_algorithms = [alg for alg in all_algorithms if alg.metadata.algorithm_name == algorithm_name]
        logger.info(f"🔍 找到 {len(candidate_algorithms)} 个匹配算法名称的算法实例: {algorithm_name}")
        
        # 2. 在候选算法中通过匹配对查找
        if candidate_algorithms:
            target_alg = _find_algorithm_by_indices(
                candidate_algorithms, record_index, replay_index,
                "[OK] 在候选算法中"
            )
            if target_alg:
                return target_alg

            # 如果只有一个候选但未找到匹配对，则勉强使用
            if len(candidate_algorithms) == 1:
                logger.warning(f"[WARNING] 只有一个候选算法但未找到明确匹配对，尝试使用: {algorithm_name}")
                return candidate_algorithms[0]

        # 3. 如果精确匹配失败，在所有算法中全局查找
        logger.info(f"[WARNING] 算法名称匹配失败，尝试全局查找")
        return _find_algorithm_by_indices(
            all_algorithms, record_index, replay_index,
            "[OK] 全局查找"
        )

    def _get_notes_and_center_time(target_algorithm, record_index, replay_index, key_id):
        """[Helper] 获取录制/播放音符对象及中心时间"""
        if not target_algorithm or not target_algorithm.analyzer:
            return None, None, None

        # 从 matched_pairs 获取匹配的音符对
        matched_pairs = getattr(target_algorithm.analyzer, 'matched_pairs', [])
        
        for r_idx, p_idx, r_note, p_note in matched_pairs:
            if r_idx == record_index and p_idx == replay_index:
                # 如果指定了key_id，进行额外验证
                if key_id is not None and r_note.id != key_id:
                    continue
                        
            # 计算中心时间（keyon时间）
            r_offset = r_note.after_touch.index[0] + r_note.offset if hasattr(r_note, 'after_touch') and not r_note.after_touch.empty else r_note.offset
            p_offset = p_note.after_touch.index[0] + p_note.offset if hasattr(p_note, 'after_touch') and not p_note.after_touch.empty else p_note.offset
            center_time_ms = ((r_offset + p_offset) / 2.0) / 10.0

        return r_note, p_note, center_time_ms

        # 如果在 matched_pairs 中找不到匹配的音符对，直接返回None
        return None, None, None
    
    # 同种算法相对延时分布图详情表格点击回调 - 显示录制与播放对比曲线
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True)],
        [Input({'type': 'relative-delay-distribution-table', 'index': dash.dependencies.ALL}, 'active_cell'),
         Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State({'type': 'relative-delay-distribution-table', 'index': dash.dependencies.ALL}, 'data'),
         State('session-id', 'data'),
         State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_relative_delay_distribution_table_click(active_cells, close_modal_clicks, close_btn_clicks, table_data_list, session_id, current_style):
        """处理同种算法相对延时分布图详情表格点击，显示录制与播放对比曲线（悬浮窗）并支持跳转到瀑布图"""
        # 1. 检测触发源与关闭操作
        ctx = callback_context
        if not ctx.triggered:
            return current_style, [], no_update
        
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        if trigger_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            return {'display': 'none'}, [], no_update
            
        # 2. 获取 Backend
        backend = session_manager.get_backend(session_id)
        if not backend:
            return current_style, [], no_update
        
        # 3. 获取触发的表格行数据
        try:
            triggered_table_idx = next((i for i, cell in enumerate(active_cells) if cell), None)
            if triggered_table_idx is None or triggered_table_idx >= len(table_data_list):
                return current_style, [], no_update

            table_data = table_data_list[triggered_table_idx]
            active_cell = active_cells[triggered_table_idx]

            if not active_cell or not table_data:
                return current_style, [], no_update

            row_data = table_data[active_cell.get('row')]
            record_index = int(row_data.get('record_index'))
            replay_index = int(row_data.get('replay_index'))
            key_id = int(row_data.get('key_id')) if row_data.get('key_id') != 'N/A' else None
            algorithm_name = row_data.get('algorithm_name')
            
            logger.info(f"[STATS] 点击行: rec={record_index}, rep={replay_index}, key={key_id}, alg={algorithm_name}")

            # 4. 查找目标算法实例
            if backend.multi_algorithm_mode:
                target_algorithm = _find_target_algorithm_instance(backend, algorithm_name, record_index, replay_index)
                if not target_algorithm:
                    logger.warning(f"[WARNING] 未找到匹配算法: {algorithm_name}")
                    return current_style, [], no_update
                final_algorithm_name = target_algorithm.metadata.algorithm_name
            else:
                logger.warning("[WARNING] 非多算法模式或无效调用")
                return current_style, [], no_update
            
            # 5. 获取音符数据与时间
            record_note, replay_note, center_time_ms = _get_notes_and_center_time(target_algorithm, record_index, replay_index, key_id)
            
            if not record_note or not replay_note:
                logger.error("[ERROR] 无法获取音符对象")
                # 如果有center_time_ms但没音符，也可以继续吗？目前逻辑似乎需要音符来画图
                if center_time_ms is None:
                    return current_style, [], no_update

            # 6. 生成对比曲线图
            mean_delay = 0.0
            if target_algorithm.analyzer:
                mean_delay = target_algorithm.analyzer.get_mean_error() / 10.0

            detail_figure = spmid.plot_note_comparison_plotly(
                record_note, 
                replay_note, 
                algorithm_name=final_algorithm_name,
                other_algorithm_notes=[],
                mean_delays={final_algorithm_name: mean_delay}
            )
            
            if not detail_figure:
                return current_style, [], no_update
            
            # 7. 构建返回数据
            source_subplot_idx = triggered_table_idx + 1 # 假设索引+1
            point_info = {
                'algorithm_name': final_algorithm_name,
                'record_idx': record_index,
                'replay_idx': replay_index,
                'key_id': key_id,
                'source_plot_id': 'relative-delay-distribution-plot',
                'source_subplot_idx': source_subplot_idx,
                'center_time_ms': center_time_ms
            }
            
            modal_style = {
                'display': 'block',
                'position': 'fixed',
                'zIndex': '9999',
                'left': '0', 'top': '0',
                'width': '100%', 'height': '100%',
                'backgroundColor': 'rgba(0,0,0,0.6)',
                'backdropFilter': 'blur(5px)'
            }
            
            return modal_style, [dcc.Graph(figure=detail_figure, style={'height': '600px'})], point_info

        except Exception as e:
            logger.error(f"[ERROR] 处理表格点击失败: {e}")
            logger.error(traceback.format_exc())
        return current_style, [], no_update

    # 延时时间序列图回调 - 报告内容加载时自动生成
    @app.callback(
        [Output('raw-delay-time-series-plot', 'figure'),
         Output('relative-delay-time-series-plot', 'figure')],
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_generate_delay_time_series(report_content, session_id):
        """处理延时时间序列图自动生成 - 当报告内容更新时触发"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return [no_update, no_update]

        try:
            # 检查是否在多算法模式
            # 检查是否有激活的算法
            active_algorithms = backend.get_active_algorithms()
            if not active_algorithms:
                logger.debug("[DEBUG] 没有激活的算法，跳过延时时间序列图生成")
                empty_plot = backend.plot_generator._create_empty_plot("没有激活的算法")
                return [empty_plot, empty_plot]

            result = backend.generate_delay_time_series_plot()

            # 检查返回的是否是字典（两个图表）还是单个图表
            if isinstance(result, dict) and 'raw_delay_plot' in result and 'relative_delay_plot' in result:
                logger.info("[OK] 延时时间序列图生成成功（分离模式）")
                return [result['raw_delay_plot'], result['relative_delay_plot']]
            else:
                # 单算法模式 - 两个图表都显示相同的内容
                logger.info("[OK] 延时时间序列图生成成功（单算法模式）")
                return [result, result]

        except Exception as e:
            logger.error(f"[ERROR] 生成延时时间序列图失败: {e}")
            logger.error(traceback.format_exc())
            empty_plot = backend.plot_generator._create_empty_plot(f"生成时间序列图失败: {str(e)}")
            return [empty_plot, empty_plot]
    
    # 延时时间序列图点击回调 - 只处理关闭按钮（单算法模式）
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True)],
        [Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_delay_time_series_click(close_modal_clicks, close_btn_clicks, current_style):
        """处理延时时间序列图点击，显示音符分析曲线（悬浮窗）并支持跳转到瀑布图"""
        """处理延时时间序列图模态框的关闭按钮（单算法模式）"""
        logger.info("[START] handle_delay_time_series_click 关闭按钮回调被触发")

        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            return current_style, [], no_update

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        logger.info(f"🔍 触发ID: {trigger_id}")

        # 如果点击了关闭按钮，隐藏模态框
        if trigger_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            modal_style = {
                'display': 'none',
                'position': 'fixed',
                'zIndex': '9999',
                'left': '0',
                'top': '0',
                'width': '100%',
                'height': '100%',
                'backgroundColor': 'rgba(0,0,0,0.6)',
                'backdropFilter': 'blur(5px)'
            }
            return modal_style, [], no_update

        return current_style, [], no_update
                    
    # 延时时间序列图点击回调 - 多算法模式（监听所有时间序列图）
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True),
         Output('raw-delay-time-series-plot', 'clickData', allow_duplicate=True),
         Output('relative-delay-time-series-plot', 'clickData', allow_duplicate=True)],
        [Input('raw-delay-time-series-plot', 'clickData'),
         Input('relative-delay-time-series-plot', 'clickData'),
         Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State('session-id', 'data'),
         State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_delay_time_series_click_multi(raw_click_data, relative_click_data, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理延时时间序列图点击（多算法模式），显示音符分析曲线（悬浮窗）"""
        return delay_time_series_handler.handle_delay_time_series_click_multi(
            raw_click_data, relative_click_data, close_modal_clicks, close_btn_clicks, session_id, current_style
        )

    # 最大/最小延迟字段点击回调 - 显示对应按键的曲线对比图
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True)],
        [Input({'type': 'max-delay-value', 'algorithm': dash.ALL}, 'n_clicks'),
         Input({'type': 'min-delay-value', 'algorithm': dash.ALL}, 'n_clicks'),
         Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State({'type': 'max-delay-value', 'algorithm': dash.ALL}, 'id'),
         State({'type': 'min-delay-value', 'algorithm': dash.ALL}, 'id'),
         State('session-id', 'data'),
         State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_delay_value_click(max_clicks_list, min_clicks_list, close_modal_clicks, close_btn_clicks, 
                                  max_ids_list, min_ids_list, session_id, current_style):
        """处理最大/最小延迟字段点击，显示对应按键的曲线对比图"""
        return delay_value_click_handler.handle_delay_value_click(
            max_clicks_list, min_clicks_list, close_modal_clicks, close_btn_clicks,
            max_ids_list, min_ids_list, session_id, current_style
        )
    
    # 延时分布直方图回调 - 报告内容加载时自动生成
    @app.callback(
        Output('delay-histogram-plot', 'figure'),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_generate_delay_histogram(report_content, session_id):
        """处理延时直方图自动生成 - 当报告内容更新时触发"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update
        
        try:
            # 检查是否在多算法模式
            # 检查是否有激活的算法
            active_algorithms = backend.get_active_algorithms()
            if not active_algorithms:
                logger.debug("[DEBUG] 没有激活的算法，跳过延时直方图生成")
                return backend.plot_generator._create_empty_plot("没有激活的算法")
            
            fig = backend.generate_delay_histogram_plot()
            logger.info("[OK] 延时直方图生成成功")
            return fig
        except Exception as e:
            logger.error(f"[ERROR] 生成延时直方图失败: {e}")
            logger.error(traceback.format_exc())
            return backend.plot_generator._create_empty_plot(f"生成直方图失败: {str(e)}")

    # 导出延时分布直方图数据为CSV
    @app.callback(
        Output('export-delay-histogram-status', 'children'),
        Input('export-delay-histogram-csv', 'n_clicks'),
        State('session-id', 'data'),
        prevent_initial_call=True
    )
    def export_delay_histogram_csv(n_clicks, session_id):
        """导出延时分布直方图数据为CSV文件"""
        import os

        backend = session_manager.get_backend(session_id)
        if not backend:
            return html.Div("❌ 后端未初始化", style={'color': '#dc3545'})

        try:
            # 检查是否在多算法模式
            if backend.multi_algorithm_mode and backend.multi_algorithm_manager:
                # 多算法模式：导出多算法数据
                active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()
                if not active_algorithms:
                    return html.Div("❌ 没有激活的算法", style={'color': '#dc3545'})

                csv_paths = backend.multi_algorithm_plot_generator.export_multi_algorithm_delay_histogram_data_to_csv(active_algorithms)
            else:
                # 单算法模式：导出单算法数据
                csv_path = backend.export_delay_histogram_data_to_csv()
                csv_paths = [csv_path] if csv_path else None

            if csv_paths and len(csv_paths) > 0:
                if len(csv_paths) == 1:
                    filename = os.path.basename(csv_paths[0])
                    return html.Div([
                        html.I(className="fas fa-check-circle", style={'color': '#28a745', 'marginRight': '8px'}),
                        f"✅ 数据已导出: {filename}"
                    ], style={'color': '#28a745'})
                else:
                    filenames = [os.path.basename(path) for path in csv_paths]
                    return html.Div([
                        html.I(className="fas fa-check-circle", style={'color': '#28a745', 'marginRight': '8px'}),
                        f"✅ 数据已导出 {len(csv_paths)} 个文件: {', '.join(filenames)}"
                    ], style={'color': '#28a745'})
            else:
                return html.Div("❌ 导出失败，请检查数据", style={'color': '#dc3545'})

        except Exception as e:
            logger.error(f"导出延时分布数据失败: {e}")
            return html.Div(f"❌ 导出异常: {str(e)}", style={'color': '#dc3545'})

    # 导出匹配前数据为CSV（测试功能）
    @app.callback(
        Output('export-pre-match-status', 'children'),
        Input('export-pre-match-csv', 'n_clicks'),
        State('session-id', 'data'),
        prevent_initial_call=True
    )
    def export_pre_match_csv(n_clicks, session_id):
        """导出匹配前的数据为CSV文件（测试功能）"""
        import os

        backend = session_manager.get_backend(session_id)
        if not backend:
            return html.Div("❌ 后端未初始化", style={'color': '#dc3545'})

        try:
            # 检查当前模式
            if hasattr(backend, 'multi_algorithm_mode') and backend.multi_algorithm_mode:
                # 多算法模式
                active_algorithms = backend.get_active_algorithms()
                if not active_algorithms:
                    return html.Div("❌ 没有激活的算法", style={'color': '#dc3545'})

                csv_paths = backend.multi_algorithm_plot_generator.export_multi_algorithm_pre_match_data_to_csv(active_algorithms)
            else:
                # 单算法模式
                csv_paths = backend.export_pre_match_data_to_csv()
                if csv_paths and not isinstance(csv_paths, list):
                    csv_paths = [csv_paths]  # 统一转换为列表格式

            if csv_paths:
                if len(csv_paths) > 1:
                    # 多文件情况
                    filenames = [os.path.basename(path) for path in csv_paths]
                    return html.Div([
                        html.I(className="fas fa-check-circle", style={'color': '#28a745', 'marginRight': '8px'}),
                        f"✅ 匹配前数据已导出 {len(csv_paths)} 个文件: {', '.join(filenames)}"
                    ], style={'color': '#28a745'})
                else:
                    # 单文件情况
                    filename = os.path.basename(csv_paths[0])
                    return html.Div([
                        html.I(className="fas fa-check-circle", style={'color': '#28a745', 'marginRight': '8px'}),
                        f"✅ 匹配前数据已导出: {filename}"
                    ], style={'color': '#28a745'})
            else:
                return html.Div("❌ 导出失败，请检查数据", style={'color': '#dc3545'})

        except Exception as e:
            logger.error(f"导出匹配前数据失败: {e}")
            return html.Div(f"❌ 导出异常: {str(e)}", style={'color': '#dc3545'})


    # 延时分布直方图点击回调 - 显示指定延时范围内的数据点详情
    @app.callback(
        [Output('delay-histogram-detail-table', 'data'),
         Output('delay-histogram-detail-table', 'style_table'),
         Output('delay-histogram-selection-info', 'children')],
        [Input('delay-histogram-plot', 'clickData')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_delay_histogram_click(click_data, session_id):
        """处理延时直方图点击事件，显示该延时范围内的数据点详情"""
        return delay_histogram_click_handler.handle_delay_histogram_click(click_data, session_id)
    
    # 延时分布直方图详情表格点击回调 - 显示录制与播放对比曲线
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True)],
        [Input('delay-histogram-detail-table', 'active_cell'),
         Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State('delay-histogram-detail-table', 'data'),
         State('session-id', 'data'),
         State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_delay_histogram_table_click(active_cell, close_modal_clicks, close_btn_clicks, table_data, session_id, current_style):
        """处理延时分布直方图详情表格点击，显示录制与播放对比曲线（悬浮窗）并支持跳转到瀑布图"""
        
        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            return current_style, [], no_update
        
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        logger.debug(f"[DEBUG] 延时直方图表格点击回调触发：trigger_id={trigger_id}")
        
        # 如果点击了关闭按钮，隐藏模态框
        if trigger_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            logger.info("[OK] 关闭按键曲线对比模态框")
            modal_style = {
                'display': 'none',
                'position': 'fixed',
                'zIndex': '9999',
                'left': '0',
                'top': '0',
                'width': '100%',
                'height': '100%',
                'backgroundColor': 'rgba(0,0,0,0.6)',
                'backdropFilter': 'blur(5px)'
            }
            return modal_style, [], no_update
        
        # 如果是表格点击
        if trigger_id == 'delay-histogram-detail-table':
            backend = session_manager.get_backend(session_id)
            if not backend:
                logger.warning("[WARNING] 没有找到backend")
                return current_style, [], no_update
            
            if not active_cell or not table_data:
                logger.warning("[WARNING] active_cell或table_data为空")
                return current_style, [], no_update
            
            try:
                # 获取点击的行数据
                row_idx = active_cell.get('row')
                if row_idx is None or row_idx >= len(table_data):
                    logger.warning(f"[WARNING] 行索引超出范围: row_idx={row_idx}, table_data长度={len(table_data)}")
                    return current_style, [], no_update
                
                row_data = table_data[row_idx]
                record_index = row_data.get('record_index')
                replay_index = row_data.get('replay_index')
                key_id = row_data.get('key_id')  # 获取按键ID用于验证
                algorithm_name = row_data.get('algorithm_name')  # 可能为 None（单算法模式）
                
                logger.info(f"[STATS] 点击的行数据: record_index={record_index}, replay_index={replay_index}, key_id={key_id}, algorithm_name={algorithm_name}")
                print(f"[STATS] 点击的行数据: record_index={record_index}, replay_index={replay_index}, key_id={key_id}, algorithm_name={algorithm_name}")
                
                # 检查索引是否有效
                if record_index == 'N/A' or replay_index == 'N/A' or record_index is None or replay_index is None:
                    logger.warning("[WARNING] 索引无效")
                    return current_style, [], no_update
                
                try:
                    record_index = int(record_index)
                    replay_index = int(replay_index)
                    if key_id and key_id != 'N/A':
                        key_id = int(key_id)
                    else:
                        key_id = None
                except (ValueError, TypeError) as e:
                    logger.warning(f"[WARNING] 无法转换索引或key_id: record_index={record_index}, replay_index={replay_index}, key_id={key_id}, error={e}")
                    return current_style, [], no_update
                
                # 获取对应的音符数据 - 必须从matched_pairs中获取，确保是配对的
                record_note = None
                replay_note = None
                center_time_ms = None  # 用于跳转的时间信息
                
                # 检查是否在多算法模式且提供了算法名称
                if backend.multi_algorithm_mode and backend.multi_algorithm_manager and algorithm_name and algorithm_name != 'N/A':
                    # 多算法模式：从指定算法获取数据
                    active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()
                    target_algorithm = None
                    for alg in active_algorithms:
                        if alg.metadata.algorithm_name == algorithm_name:
                            target_algorithm = alg
                            break
                    
                    if not target_algorithm or not target_algorithm.analyzer:
                        logger.warning(f"[WARNING] 未找到算法: {algorithm_name}")
                        return current_style, [], no_update
                    
                    # 从matched_pairs中查找匹配对，确保record_index和replay_index对应同一个匹配对
                    matched_pairs = target_algorithm.analyzer.matched_pairs if hasattr(target_algorithm.analyzer, 'matched_pairs') else []
                    if not matched_pairs:
                        logger.warning("[WARNING] 算法没有匹配对数据")
                        return current_style, [], no_update
                    
                    # 查找匹配对：record_index和replay_index必须同时匹配
                    found_pair = False
                    for r_idx, p_idx, r_note, p_note in matched_pairs:
                        if r_idx == record_index and p_idx == replay_index:
                            # 验证key_id（如果提供了）
                            if key_id is not None and r_note.id != key_id:
                                logger.warning(f"[WARNING] key_id不匹配: 表格中的key_id={key_id}, 匹配对中的key_id={r_note.id}")
                                continue
                            record_note = r_note
                            replay_note = p_note
                            found_pair = True
                            logger.info(f"[OK] 从matched_pairs中找到匹配对: record_index={record_index}, replay_index={replay_index}, key_id={r_note.id}")
                            print(f"[OK] 从matched_pairs中找到匹配对: record_index={record_index}, replay_index={replay_index}, key_id={r_note.id}")
                            
                            # 计算keyon时间，用于跳转
                            try:
                                record_keyon = r_note.after_touch.index[0] + r_note.offset if hasattr(r_note, 'after_touch') and not r_note.after_touch.empty else r_note.offset
                                replay_keyon = p_note.after_touch.index[0] + p_note.offset if hasattr(p_note, 'after_touch') and not p_note.after_touch.empty else p_note.offset
                                center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0  # 转换为ms
                            except Exception as e:
                                logger.warning(f"[WARNING] 计算时间信息失败: {e}")
                                # 备用方案：从 offset_data 获取
                                if target_algorithm.analyzer.note_matcher:
                                    try:
                                        offset_data = target_algorithm.analyzer.note_matcher.get_offset_alignment_data()
                                        if offset_data:
                                            for item in offset_data:
                                                if item.get('record_index') == record_index and item.get('replay_index') == replay_index:
                                                    record_keyon = item.get('record_keyon', 0)
                                                    replay_keyon = item.get('replay_keyon', 0)
                                                    if record_keyon and replay_keyon:
                                                        center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0
                                                        break
                                    except Exception as e2:
                                        logger.warning(f"[WARNING] 从offset_data获取时间信息失败: {e2}")
                            
                            break
                    
                    if not found_pair:
                        logger.warning(f"[WARNING] 未找到匹配对: record_index={record_index}, replay_index={replay_index}")
                        return current_style, [], no_update
                    
                    # 使用算法名称
                    final_algorithm_name = algorithm_name
                else:
                    # 单算法模式
                    if not backend.analyzer:
                        logger.warning("[WARNING] 没有分析器")
                        return current_style, [], no_update
                    
                    # 从matched_pairs中查找匹配对
                    matched_pairs = backend.analyzer.matched_pairs if hasattr(backend.analyzer, 'matched_pairs') else []
                    if not matched_pairs:
                        logger.warning("[WARNING] 没有匹配对数据")
                        return current_style, [], no_update
                    
                    # 查找匹配对：record_index和replay_index必须同时匹配
                    found_pair = False
                    for r_idx, p_idx, r_note, p_note in matched_pairs:
                        if r_idx == record_index and p_idx == replay_index:
                            # 验证key_id（如果提供了）
                            if key_id is not None and r_note.id != key_id:
                                logger.warning(f"[WARNING] key_id不匹配: 表格中的key_id={key_id}, 匹配对中的key_id={r_note.id}")
                                continue
                            record_note = r_note
                            replay_note = p_note
                            found_pair = True
                            logger.info(f"[OK] 从matched_pairs中找到匹配对: record_index={record_index}, replay_index={replay_index}, key_id={r_note.id}")
                            print(f"[OK] 从matched_pairs中找到匹配对: record_index={record_index}, replay_index={replay_index}, key_id={r_note.id}")
                            
                            # 计算keyon时间，用于跳转
                            try:
                                record_keyon = r_note.after_touch.index[0] + r_note.offset if hasattr(r_note, 'after_touch') and not r_note.after_touch.empty else r_note.offset
                                replay_keyon = p_note.after_touch.index[0] + p_note.offset if hasattr(p_note, 'after_touch') and not p_note.after_touch.empty else p_note.offset
                                center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0  # 转换为ms
                            except Exception as e:
                                logger.warning(f"[WARNING] 计算时间信息失败: {e}")
                                # 备用方案：从 offset_data 获取
                                if backend.analyzer.note_matcher:
                                    try:
                                        offset_data = backend.analyzer.note_matcher.get_offset_alignment_data()
                                        if offset_data:
                                            for item in offset_data:
                                                if item.get('record_index') == record_index and item.get('replay_index') == replay_index:
                                                    record_keyon = item.get('record_keyon', 0)
                                                    replay_keyon = item.get('replay_keyon', 0)
                                                    if record_keyon and replay_keyon:
                                                        center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0
                                                        break
                                    except Exception as e2:
                                        logger.warning(f"[WARNING] 从offset_data获取时间信息失败: {e2}")
                            
                            break
                    
                    if not found_pair:
                        logger.warning(f"[WARNING] 未找到匹配对: record_index={record_index}, replay_index={replay_index}")
                        return current_style, [], no_update
                    
                    # 单算法模式，algorithm_name 可能为 None
                    final_algorithm_name = algorithm_name if algorithm_name and algorithm_name != 'N/A' else None
                
                # 在多算法模式下，查找所有算法中匹配到同一个录制音符的播放音符
                other_algorithm_notes = []  # [(algorithm_name, play_note), ...]
                if backend.multi_algorithm_mode and backend.multi_algorithm_manager:
                    active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()
                    for alg in active_algorithms:
                        if alg.metadata.algorithm_name == final_algorithm_name:
                            continue  # 跳过当前算法（已经绘制）
                        
                        if not alg.analyzer or not hasattr(alg.analyzer, 'matched_pairs'):
                            continue
                        
                        matched_pairs = alg.analyzer.matched_pairs
                        # 查找匹配到同一个record_index的播放音符
                        for r_idx, p_idx, r_note, p_note in matched_pairs:
                            if r_idx == record_index:
                                other_algorithm_notes.append((alg.metadata.algorithm_name, p_note))
                                logger.info(f"[OK] 找到算法 '{alg.metadata.algorithm_name}' 的匹配播放音符")
                                break
                
                # 按键延时散点图使用算法平均误差作为延时基准
                mean_delays = {}
                if backend.multi_algorithm_mode and backend.multi_algorithm_manager and final_algorithm_name:
                    # 多算法模式
                    algorithm = backend.multi_algorithm_manager.get_algorithm(final_algorithm_name)
                    if algorithm and algorithm.analyzer:
                        mean_error_0_1ms = algorithm.analyzer.get_mean_error()
                        mean_delays[final_algorithm_name] = mean_error_0_1ms / 10.0
                    else:
                        logger.error(f"[ERROR] 无法获取算法 '{final_algorithm_name}' 的平均延时")
                        return current_style, [], no_update
                else:
                    # 单算法模式
                    if backend.analyzer:
                        mean_error_0_1ms = backend.analyzer.get_mean_error()
                        mean_delays[final_algorithm_name or 'default'] = mean_error_0_1ms / 10.0
                    else:
                        logger.error("[ERROR] 无法获取单算法模式的平均延时")
                        return current_style, [], no_update, no_update
                
                # 生成对比曲线图（包含其他算法的播放曲线）
                detail_figure_combined = spmid.plot_note_comparison_plotly(
                    record_note, 
                    replay_note, 
                    algorithm_name=final_algorithm_name,
                    other_algorithm_notes=other_algorithm_notes,  # 传递其他算法的播放音符
                    mean_delays=mean_delays
                )
                
                if not detail_figure_combined:
                    logger.error("[ERROR] 曲线生成失败")
                    return current_style, [], no_update, no_update
                
                logger.info(f"[OK] 成功生成对比曲线: record_index={record_index}, replay_index={replay_index}")
                print(f"[OK] 成功生成对比曲线: record_index={record_index}, replay_index={replay_index}")
                
                # 存储当前点击的数据点信息，用于跳转按钮
                point_info = {
                    'algorithm_name': final_algorithm_name,
                    'record_idx': record_index,
                    'replay_idx': replay_index,
                    'key_id': key_id,
                    'source_plot_id': 'delay-histogram-detail-table',  # 记录来源图表ID
                    'center_time_ms': center_time_ms  # 预先计算的时间信息
                }
                
                # 显示模态框
                modal_style = {
                    'display': 'block',
                    'position': 'fixed',
                    'zIndex': '9999',
                    'left': '0',
                    'top': '0',
                    'width': '100%',
                    'height': '100%',
                    'backgroundColor': 'rgba(0,0,0,0.6)',
                    'backdropFilter': 'blur(5px)'
                }
                
                # 创建模态框内容（只包含图表，按钮已在布局中定义）
                # 使用与 handle_waterfall_click 相同的格式
                rendered_row = dcc.Graph(figure=detail_figure_combined, style={'height': '600px'})
                
                return modal_style, [rendered_row], point_info
                
            except Exception as e:
                logger.error(f"[ERROR] 处理延时直方图表格点击失败: {e}")
                logger.error(traceback.format_exc())
                return current_style, [], no_update
        
        return current_style, [], no_update

    # ==================== 多算法对比模式回调 ====================
    
    # 多算法模式初始化回调 - 在会话初始化时自动触发
    @app.callback(
        [Output('multi-algorithm-upload-area', 'style', allow_duplicate=True),
         Output('multi-algorithm-upload-area', 'children'),
         Output('multi-algorithm-management-area', 'style', allow_duplicate=True),
         Output('multi-algorithm-management-area', 'children'),
         Output('main-plot', 'figure', allow_duplicate=True),
         Output('report-content', 'children', allow_duplicate=True)],
        [Input('session-id', 'data')],
        prevent_initial_call='initial_duplicate',
        prevent_duplicate=True
    )
    def initialize_multi_algorithm_mode(session_id):
        """初始化多算法模式 - 确保上传区域和管理区域显示"""
        logger.info(f"[PROCESS] 初始化多算法模式: session_id={session_id}")
        
        if not session_id:
            return no_update, no_update, no_update, no_update, no_update, no_update
        
        session_id, backend = session_manager.get_or_create_backend(session_id)
        if not backend:
            logger.warning("[WARNING] 无法获取backend实例")
            return no_update, no_update, no_update, no_update, no_update, no_update
        
        try:
            # 多算法模式始终启用
            # 确保multi_algorithm_manager已初始化
            if not backend.multi_algorithm_manager:
                backend._ensure_multi_algorithm_manager()
            has_existing_data = False
            existing_filename = None
            logger.info("[OK] 多算法模式已就绪")
            
            success = True
            if success:
                upload_style = {'display': 'block'}
                try:
                    upload_area = create_multi_algorithm_upload_area()
                    logger.info("[OK] 创建多算法上传区域成功")
                except Exception as e:
                    logger.error(f"[ERROR] 创建多算法上传区域失败: {e}")
                    upload_area = html.Div("上传区域创建失败", style={'color': '#dc3545'})
                
                management_style = {'display': 'block'}
                try:
                    management_area = create_multi_algorithm_management_area()
                    logger.info("[OK] 创建多算法管理区域成功")
                except Exception as e:
                    logger.error(f"[ERROR] 创建多算法管理区域失败: {e}")
                    management_area = html.Div("管理区域创建失败", style={'color': '#dc3545'})
            else:
                upload_style = {'display': 'block'}  # 即使失败也显示，让用户知道有问题
                upload_area = html.Div("多算法模式启用失败", style={'color': '#dc3545'})
                management_style = {'display': 'block'}
                management_area = html.Div("多算法模式启用失败", style={'color': '#dc3545'})
            
            # 检查是否有激活的算法，更新瀑布图
            plot_fig = no_update
            report_content = no_update
            
            active_algorithms = backend.get_active_algorithms()
            # 进一步检查：只有算法真正有数据（analyzer存在且有matched_pairs）才生成图形
            algorithms_with_data = []
            for alg in active_algorithms:
                if alg.analyzer and hasattr(alg.analyzer, 'matched_pairs') and alg.analyzer.matched_pairs:
                    algorithms_with_data.append(alg)
            
            if algorithms_with_data:
                try:
                    logger.info(f"[PROCESS] 更新瀑布图，共 {len(algorithms_with_data)} 个有数据的激活算法")
                    plot_fig = backend.generate_waterfall_plot()
                    report_content = create_report_layout(backend)
                except Exception as e:
                    logger.error(f"[ERROR] 更新瀑布图失败: {e}")
                    plot_fig = _create_empty_figure_for_callback(f"更新失败: {str(e)}")
                    # 使用 create_report_layout 确保包含所有必需的组件
                    try:
                        report_content = create_report_layout(backend)
                    except:
                        # 如果 create_report_layout 也失败，返回包含必需组件的错误布局
                        empty_fig = {}
                        report_content = html.Div([
                            html.H4("更新失败", className="text-center text-danger"),
                            html.P(f"错误信息: {str(e)}", className="text-center"),
                            # 包含所有必需的图表组件（隐藏），确保回调函数不会报错
                            dcc.Graph(id='key-delay-scatter-plot', figure=empty_fig, style={'display': 'none'}),
                            dcc.Graph(id='key-delay-zscore-scatter-plot', figure=empty_fig, style={'display': 'none'}),
                            dcc.Graph(id='hammer-velocity-delay-scatter-plot', figure=empty_fig, style={'display': 'none'}),
                            html.Div(id='offset-alignment-plot', style={'display': 'none'}),
                            html.Div([
                                dash_table.DataTable(
                                    id='offset-alignment-table',
                                    data=[],
                                    columns=[]
                                )
                            ], style={'display': 'none'})
                        ])
            else:
                # 没有激活的算法时，不调用 create_report_layout，直接返回空布局
                # 避免在没有数据时执行不必要的操作
                logger.info("[INFO] 没有激活的算法，跳过图形生成，返回空布局")
                empty_fig = {}
                report_content = html.Div([
                        html.H4("暂无数据", className="text-center text-muted"),
                        html.P("请至少激活一个算法以查看分析报告", className="text-center text-muted"),
                        # 包含所有必需的图表组件（隐藏），确保回调函数不会报错
                        dcc.Graph(id='key-delay-scatter-plot', figure=empty_fig, style={'display': 'none'}),
                        dcc.Graph(id='key-delay-zscore-scatter-plot', figure=empty_fig, style={'display': 'none'}),
                        dcc.Graph(id='hammer-velocity-delay-scatter-plot', figure=empty_fig, style={'display': 'none'}),
                        # key-hammer-velocity-scatter-plot 已删除（功能与按键-力度交互效应图重复）
                        dcc.Graph(id='key-force-interaction-plot', figure=empty_fig, style={'display': 'none'}),
                        dcc.Graph(id='relative-delay-distribution-plot', figure=empty_fig, style={'display': 'none'}),
                        html.Div(id='offset-alignment-plot', style={'display': 'none'}),
                        dcc.Graph(id='delay-time-series-plot', figure=empty_fig, style={'display': 'none'}),
                        dcc.Graph(id='delay-histogram-plot', figure=empty_fig, style={'display': 'none'}),
                        html.Div([
                            dash_table.DataTable(
                                id='offset-alignment-table',
                                data=[],
                                columns=[]
                            )
                        ], style={'display': 'none'}),
                        html.Div([
                            dash_table.DataTable(
                                id='delay-histogram-detail-table',
                                data=[],
                                columns=[
                                    {"name": "算法名称", "id": "algorithm_name"},
                                    {"name": "按键ID", "id": "key_id"},
                                    {"name": "延时(ms)", "id": "delay_ms"},
                                    {"name": "录制索引", "id": "record_index"},
                                    {"name": "播放索引", "id": "replay_index"},
                                    {"name": "录制开始(0.1ms)", "id": "record_keyon"},
                                    {"name": "播放开始(0.1ms)", "id": "replay_keyon"},
                                    {"name": "持续时间差(0.1ms)", "id": "duration_offset"},
                                ]
                            )
                        ], style={'display': 'none'}),
                        html.Div(id='delay-histogram-selection-info', style={'display': 'none'})
                        ])
            
            logger.info(f"[OK] 多算法模式初始化完成")
            return upload_style, upload_area, management_style, management_area, plot_fig, report_content
            
        except Exception as e:
            logger.error(f"[ERROR] 初始化多算法模式失败: {e}")
            logger.error(traceback.format_exc())
            return (
                {'display': 'block'}, 
                html.Div("初始化失败", style={'color': '#dc3545'}), 
                {'display': 'block'}, 
                html.Div("初始化失败", style={'color': '#dc3545'}), 
                no_update, 
                no_update
            )
    

    
    
    
    
    
    # 更新单键选择器的选项
    @app.callback(
        Output('single-key-selector', 'options'),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def update_single_key_selector_options(report_content, session_id):
        backend = session_manager.get_backend(session_id)
        if not backend or not hasattr(backend, 'multi_algorithm_manager'):
            return []
            
        try:
            active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()
            if not active_algorithms:
                return []
                
            all_keys = set()
            for alg in active_algorithms:
                if alg.analyzer and alg.analyzer.note_matcher:
                    offset_data = alg.analyzer.note_matcher.get_offset_alignment_data()
                    if offset_data:
                        for item in offset_data:
                            if item.get('key_id') is not None:
                                all_keys.add(item.get('key_id'))
                                
            sorted_keys = sorted(list(all_keys))
            return [{'label': f'Key {k}', 'value': k} for k in sorted_keys]
            
        except Exception as e:
            logger.error(f"[ERROR] 更新单键选择器失败: {e}")
            return []

    # 单键多曲延时对比图自动生成回调
    @app.callback(
        Output('single-key-delay-comparison-plot', 'figure'),
        [Input('single-key-selector', 'value'),
         Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_generate_single_key_comparison_plot(key_id, report_content, session_id):
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update

        if not key_id:
            # 返回空图表提示
            return {
                "layout": {
                    "xaxis": {"visible": False},
                    "yaxis": {"visible": False},
                    "annotations": [
                        {
                            "text": "请选择一个按键进行分析",
                            "xref": "paper",
                            "yref": "paper",
                            "showarrow": False,
                            "font": {"size": 20},
                            "x": 0.5,
                            "y": 0.5
                        }
                    ]
                }
            }
            
        try:
            fig = backend.generate_single_key_delay_comparison_plot(key_id)
            return fig
        except Exception as e:
            logger.error(f"[ERROR] 生成单键对比图失败: {e}")
            return backend.plot_generator._create_empty_plot(f"生成失败: {str(e)}")

    # 按键延时分析表格点击回调 - 显示按键曲线对比（悬浮窗）并支持跳转到瀑布图
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True)],
        [Input('offset-alignment-table', 'active_cell'),
         Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State('offset-alignment-table', 'data'),
         State('session-id', 'data'),
         State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_key_table_click(active_cell, close_modal_clicks, close_btn_clicks, table_data, session_id, current_style):
        """处理按键延时分析表格点击，显示按键曲线对比（悬浮窗）并支持跳转到瀑布图"""
        
        
        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            logger.debug("[WARNING] 按键表格点击回调：没有触发源")
            return current_style, [], no_update
        
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        logger.debug(f"[DEBUG] 按键表格点击回调触发：trigger_id={trigger_id}")
        
        # 如果点击了关闭按钮，隐藏模态框
        if trigger_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            logger.info("[OK] 关闭按键曲线对比模态框")
            modal_style = {
                'display': 'none',
                'position': 'fixed',
                'zIndex': '9999',
                'left': '0',
                'top': '0',
                'width': '100%',
                'height': '100%',
                'backgroundColor': 'rgba(0,0,0,0.6)',
                'backdropFilter': 'blur(5px)'
            }
            return modal_style, [], no_update
        
        # 如果是表格点击
        if trigger_id == 'offset-alignment-table':
            logger.info(f"[PROCESS] 表格点击：active_cell={active_cell}, table_data长度={len(table_data) if table_data else 0}")
            backend = session_manager.get_backend(session_id)
            if not backend:
                logger.warning("[WARNING] 没有找到backend")
                return current_style, [], no_update
            if not active_cell or not table_data:
                logger.warning("[WARNING] active_cell或table_data为空")
                return current_style, [], no_update
            
            try:
                # 获取点击的行数据
                row_idx = active_cell.get('row')
                if row_idx is None or row_idx >= len(table_data):
                    return current_style, [], no_update
                
                row_data = table_data[row_idx]
                algorithm_name = row_data.get('algorithm_name')
                key_id_str = row_data.get('key_id')
                
                # 跳过汇总行
                if key_id_str in ['总体', '汇总'] or not algorithm_name:
                    return current_style, [], no_update
                
                # 转换按键ID
                try:
                    key_id = int(key_id_str)
                except (ValueError, TypeError):
                    return current_style, [], no_update
                
                # 检查是否在多算法模式
                if not backend.multi_algorithm_mode or not backend.multi_algorithm_manager:
                    logger.info("[INFO] 不在多算法模式，不显示曲线对比图")
                    return current_style, [], no_update
                
                # 获取激活的算法列表
                active_algorithms = backend.get_active_algorithms()
                if len(active_algorithms) < 2:
                    modal_style = {
                        'display': 'block',
                        'position': 'fixed',
                        'zIndex': '9999',
                        'left': '0',
                        'top': '0',
                        'width': '100%',
                        'height': '100%',
                        'backgroundColor': 'rgba(0,0,0,0.6)',
                        'backdropFilter': 'blur(5px)'
                    }
                    return modal_style, [html.Div([
                        html.P("需要至少2个激活的算法才能进行对比", className="text-muted text-center")
                    ])], no_update
                
                # 获取所有激活算法的匹配对
                algorithm_pairs_dict = {}
                all_timestamps = set()
                
                for alg in active_algorithms:
                    alg_name = alg.metadata.algorithm_name
                    pairs = backend.get_key_matched_pairs_by_algorithm(alg_name, key_id)
                    if pairs:
                        algorithm_pairs_dict[alg_name] = pairs
                        for _, _, _, _, timestamp in pairs:
                            all_timestamps.add(timestamp)
                
                if not algorithm_pairs_dict:
                    modal_style = {
                        'display': 'block',
                        'position': 'fixed',
                        'zIndex': '9999',
                        'left': '0',
                        'top': '0',
                        'width': '100%',
                        'height': '100%',
                        'backgroundColor': 'rgba(0,0,0,0.6)',
                        'backdropFilter': 'blur(5px)'
                    }
                    return modal_style, [html.Div([
                        html.P(f"按键ID {key_id} 在所有激活算法中都没有匹配数据", className="text-muted text-center")
                    ])], no_update
                
                # 选择前两个有数据的算法进行对比
                alg_names = list(algorithm_pairs_dict.keys())[:2]
                if len(alg_names) < 2:
                    # 如果只有一个算法有数据，选择前两个激活的算法（即使第二个没有数据）
                    alg_names = [alg.metadata.algorithm_name for alg in active_algorithms[:2]]
                    if alg_names[0] not in algorithm_pairs_dict:
                        alg_names[0] = list(algorithm_pairs_dict.keys())[0]
                
                alg1_name = alg_names[0]
                alg2_name = alg_names[1]
                
                alg1_pairs = algorithm_pairs_dict.get(alg1_name, [])
                alg2_pairs = algorithm_pairs_dict.get(alg2_name, [])
                
                # 生成对比曲线图
                from plotly.subplots import make_subplots
                
                comparison_rows = []
                
                # 使用双指针按时间戳对齐
                # 注意：两个算法处理的是完全不同的SPMID文件，各自有独立的录制数据和播放数据
                # - 算法A：SPMID文件1的录制数据1 vs 播放数据1
                # - 算法B：SPMID文件2的录制数据2 vs 播放数据2
                # 它们之间没有任何关联，record_index和record_keyon都是各自文件内的
                # 步骤：
                # - 提取两个算法的时间戳序列（单位：0.1ms，record_keyon是各自文件内录制按键开始时间）
                # - 使用两个指针在合并时间线上前进，尽量将时间临近的配对，否则单侧显示
                ALIGN_WINDOW_01MS = 200  # 对齐窗口：200(0.1ms) = 20ms
                
                alg1_pairs_sorted = sorted(alg1_pairs, key=lambda p: p[4])
                alg2_pairs_sorted = sorted(alg2_pairs, key=lambda p: p[4])
                i, j = 0, 0
                while i < len(alg1_pairs_sorted) or j < len(alg2_pairs_sorted):
                    if i < len(alg1_pairs_sorted) and j < len(alg2_pairs_sorted):
                        t1 = alg1_pairs_sorted[i][4]
                        t2 = alg2_pairs_sorted[j][4]
                        diff = abs(t1 - t2)
                        if diff <= ALIGN_WINDOW_01MS:
                            # 配对显示
                            comparison_rows.append((alg1_pairs_sorted[i], alg2_pairs_sorted[j], t1, t2))
                            i += 1
                            j += 1
                        elif t1 < t2:
                            # 左侧单独显示
                            comparison_rows.append((alg1_pairs_sorted[i], None, t1, None))
                            i += 1
                        else:
                            # 右侧单独显示
                            comparison_rows.append((None, alg2_pairs_sorted[j], None, t2))
                            j += 1
                    elif i < len(alg1_pairs_sorted):
                        t1 = alg1_pairs_sorted[i][4]
                        comparison_rows.append((alg1_pairs_sorted[i], None, t1, None))
                        i += 1
                    else:
                        t2 = alg2_pairs_sorted[j][4]
                        comparison_rows.append((None, alg2_pairs_sorted[j], None, t2))
                        j += 1
                
                # 为每个对齐项创建对比图
                rendered_rows = []
                for alg1_pair, alg2_pair, t1, t2 in comparison_rows:
                    if not alg1_pair and not alg2_pair:
                        continue
                    
                    # 创建左右对比的子图，标题显示各自时间
                    # record_keyon：各自SPMID文件内录制按键开始时间（两个文件独立，时间戳无关联）
                    if alg1_pair and t1 is not None:
                        title1 = f"{alg1_name}<br>录制按键开始: {t1/10:.2f}ms"
                    else:
                        title1 = f"{alg1_name} (无数据)"
                    
                    if alg2_pair and t2 is not None:
                        title2 = f"{alg2_name}<br>录制按键开始: {t2/10:.2f}ms"
                    else:
                        title2 = f"{alg2_name} (无数据)"
                    
                    fig = make_subplots(
                        rows=1, cols=2,
                        subplot_titles=(title1, title2),
                        horizontal_spacing=0.15
                    )
                    
                    # 左侧：算法1的曲线
                    if alg1_pair:
                        _, _, record_note1, replay_note1, _ = alg1_pair
                        if record_note1 and hasattr(record_note1, 'after_touch') and not record_note1.after_touch.empty:
                            x_at = (record_note1.after_touch.index + record_note1.offset) / 10.0
                            y_at = record_note1.after_touch.values
                            fig.add_trace(go.Scatter(x=x_at, y=y_at, mode='lines', name='录制触后', 
                                                    line=dict(color='blue', width=2), showlegend=False), row=1, col=1)
                        if record_note1 and hasattr(record_note1, 'hammers') and not record_note1.hammers.empty:
                            x_hm = (record_note1.hammers.index + record_note1.offset) / 10.0
                            y_hm = record_note1.hammers.values
                            fig.add_trace(go.Scatter(x=x_hm, y=y_hm, mode='markers', name='录制锤子',
                                                    marker=dict(color='blue', size=6), showlegend=False), row=1, col=1)
                        if replay_note1 and hasattr(replay_note1, 'after_touch') and not replay_note1.after_touch.empty:
                            x_at = (replay_note1.after_touch.index + replay_note1.offset) / 10.0
                            y_at = replay_note1.after_touch.values
                            fig.add_trace(go.Scatter(x=x_at, y=y_at, mode='lines', name='回放触后',
                                                    line=dict(color='red', width=2), showlegend=False), row=1, col=1)
                        if replay_note1 and hasattr(replay_note1, 'hammers') and not replay_note1.hammers.empty:
                            x_hm = (replay_note1.hammers.index + replay_note1.offset) / 10.0
                            y_hm = replay_note1.hammers.values
                            fig.add_trace(go.Scatter(x=x_hm, y=y_hm, mode='markers', name='回放锤子',
                                                    marker=dict(color='red', size=6), showlegend=False), row=1, col=1)
                    
                    # 右侧：算法2的曲线
                    if alg2_pair:
                        _, _, record_note2, replay_note2, _ = alg2_pair
                        if record_note2 and hasattr(record_note2, 'after_touch') and not record_note2.after_touch.empty:
                            x_at = (record_note2.after_touch.index + record_note2.offset) / 10.0
                            y_at = record_note2.after_touch.values
                            fig.add_trace(go.Scatter(x=x_at, y=y_at, mode='lines', name='录制触后',
                                                    line=dict(color='blue', width=2), showlegend=False), row=1, col=2)
                        if record_note2 and hasattr(record_note2, 'hammers') and not record_note2.hammers.empty:
                            x_hm = (record_note2.hammers.index + record_note2.offset) / 10.0
                            y_hm = record_note2.hammers.values
                            fig.add_trace(go.Scatter(x=x_hm, y=y_hm, mode='markers', name='录制锤子',
                                                    marker=dict(color='blue', size=6), showlegend=False), row=1, col=2)
                        if replay_note2 and hasattr(replay_note2, 'after_touch') and not replay_note2.after_touch.empty:
                            x_at = (replay_note2.after_touch.index + replay_note2.offset) / 10.0
                            y_at = replay_note2.after_touch.values
                            fig.add_trace(go.Scatter(x=x_at, y=y_at, mode='lines', name='回放触后',
                                                    line=dict(color='red', width=2), showlegend=False), row=1, col=2)
                        if replay_note2 and hasattr(replay_note2, 'hammers') and not replay_note2.hammers.empty:
                            x_hm = (replay_note2.hammers.index + replay_note2.offset) / 10.0
                            y_hm = replay_note2.hammers.values
                            fig.add_trace(go.Scatter(x=x_hm, y=y_hm, mode='markers', name='回放锤子',
                                                    marker=dict(color='red', size=6), showlegend=False), row=1, col=2)
                    
                    # 主标题
                    title_text = f"按键ID {key_id} 曲线对比"
                    
                    fig.update_layout(
                        title=title_text,
                        height=400,
                        showlegend=False
                    )
                    fig.update_xaxes(title_text="时间 (ms)", row=1, col=1)
                    fig.update_xaxes(title_text="时间 (ms)", row=1, col=2)
                    fig.update_yaxes(title_text="值", row=1, col=1)
                    fig.update_yaxes(title_text="值", row=1, col=2)
                    
                    rendered_rows.append(
                        dbc.Row([
                            dbc.Col([
                                dcc.Graph(figure=fig, style={'height': '400px'})
                            ], width=12)
                        ], className="mb-3")
                    )
                
                if not rendered_rows:
                    modal_style = {
                        'display': 'block',
                        'position': 'fixed',
                        'zIndex': '9999',
                        'left': '0',
                        'top': '0',
                        'width': '100%',
                        'height': '100%',
                        'backgroundColor': 'rgba(0,0,0,0.6)',
                        'backdropFilter': 'blur(5px)'
                    }
                    return modal_style, [html.Div([
                        html.P(f"按键ID {key_id} 没有可显示的对比数据", className="text-muted text-center")
                    ])], no_update
                
                # 计算时间信息，用于跳转时直接使用
                center_time_ms = None
                record_idx = None
                replay_idx = None
                first_algorithm_name = None
                
                try:
                    # 获取第一个匹配对用于跳转
                    if alg1_pairs:
                        first_pair = alg1_pairs[0]
                        record_idx, replay_idx, record_note, replay_note, _ = first_pair
                        first_algorithm_name = alg1_name
                        
                        if record_note and replay_note:
                            try:
                                # 计算keyon时间
                                record_keyon = record_note.after_touch.index[0] + record_note.offset if hasattr(record_note, 'after_touch') and not record_note.after_touch.empty else record_note.offset
                                replay_keyon = replay_note.after_touch.index[0] + replay_note.offset if hasattr(replay_note, 'after_touch') and not replay_note.after_touch.empty else replay_note.offset
                                center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0  # 转换为ms
                                logger.info(f"[OK] 计算得到center_time_ms: {center_time_ms}ms")
                            except Exception as e:
                                logger.warning(f"[WARNING] 计算时间信息失败: {e}")
                                # 备用方案：从 offset_data 获取
                                try:
                                    algorithm = backend.multi_algorithm_manager.get_algorithm(alg1_name)
                                    if algorithm and algorithm.analyzer and algorithm.analyzer.note_matcher:
                                        offset_data = algorithm.analyzer.note_matcher.get_offset_alignment_data()
                                        if offset_data:
                                            for item in offset_data:
                                                if item.get('record_index') == record_idx and item.get('replay_index') == replay_idx:
                                                    record_keyon = item.get('record_keyon', 0)
                                                    replay_keyon = item.get('replay_keyon', 0)
                                                    if record_keyon and replay_keyon:
                                                        center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0
                                                        logger.info(f"[OK] 从offset_data获取center_time_ms: {center_time_ms}ms")
                                                        break
                                except Exception as e2:
                                    logger.warning(f"[WARNING] 从offset_data获取时间信息失败: {e2}")
                except Exception as e:
                    logger.warning(f"[WARNING] 获取跳转信息失败: {e}")
                
                # 存储当前点击的数据点信息，用于跳转按钮
                point_info = {
                    'algorithm_name': first_algorithm_name,
                    'record_idx': record_idx,
                    'replay_idx': replay_idx,
                    'key_id': key_id,
                    'source_plot_id': 'offset-alignment-table',  # 记录来源表格ID
                    'center_time_ms': center_time_ms  # 预先计算的时间信息
                }
                
                # 显示模态框
                modal_style = {
                    'display': 'block',
                    'position': 'fixed',
                    'zIndex': '9999',
                    'left': '0',
                    'top': '0',
                    'width': '100%',
                    'height': '100%',
                    'backgroundColor': 'rgba(0,0,0,0.6)',
                    'backdropFilter': 'blur(5px)'
                }
                
                return modal_style, rendered_rows, point_info
                
            except Exception as e:
                logger.error(f"[ERROR] 生成按键曲线对比失败: {e}")
                logger.error(traceback.format_exc())
                modal_style = {
                    'display': 'block',
                    'position': 'fixed',
                    'zIndex': '9999',
                    'left': '0',
                    'top': '0',
                    'width': '100%',
                    'height': '100%',
                    'backgroundColor': 'rgba(0,0,0,0.6)',
                    'backdropFilter': 'blur(5px)'
                }
                return modal_style, [html.Div([
                    html.P(f"生成对比图失败: {str(e)}", className="text-danger text-center")
                ])], no_update
        
        # 其他情况，保持当前状态
        return current_style, [], no_update
    
    # 瀑布图点击回调 - 显示曲线对比（悬浮窗）
    @app.callback(
        [Output('waterfall-curves-modal', 'style'),
         Output('waterfall-curves-comparison-container', 'children')],
        [Input('main-plot', 'clickData'),
         Input('close-waterfall-curves-modal', 'n_clicks'),
         Input('close-waterfall-curves-modal-btn', 'n_clicks')],
        [State('session-id', 'data'),
         State('waterfall-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_waterfall_click(click_data, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理瀑布图点击，显示曲线对比（悬浮窗）"""
        
        
        
        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            print("[ERROR] 没有触发源")
            return current_style, []
        
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        print(f"🔍 触发ID: {trigger_id}")
        
        # 如果点击了关闭按钮，隐藏模态框
        if trigger_id in ['close-waterfall-curves-modal', 'close-waterfall-curves-modal-btn']:
            print("[OK] 关闭瀑布图曲线模态框")
            modal_style = {
                'display': 'none',
                'position': 'fixed',
                'zIndex': '9999',
                'left': '0',
                'top': '0',
                'width': '100%',
                'height': '100%',
                'backgroundColor': 'rgba(0,0,0,0.6)',
                'backdropFilter': 'blur(5px)'
            }
            return modal_style, []
        
        # 如果是瀑布图点击
        if trigger_id == 'main-plot' and click_data:
            print("[TARGET] 检测到瀑布图点击！")
            
            backend = session_manager.get_backend(session_id)
            if not backend:
                print("[ERROR] backend为空")
                return current_style, []
            
            try:
                if 'points' not in click_data or len(click_data['points']) == 0:
                    print("[ERROR] clickData中没有points")
                    return current_style, []
                
                point = click_data['points'][0]
                
                # 优先从customdata获取信息，如果没有则从坐标获取
                algorithm_name = None
                key_id = None
                data_type = None
                index = None
                
                if point.get('customdata'):
                    # 有customdata：点击到了起始时间
                    raw_customdata = point['customdata']
                    customdata = raw_customdata[0] if isinstance(raw_customdata, list) and len(raw_customdata) > 0 and isinstance(raw_customdata[0], list) else raw_customdata
                else:
                    # 没有customdata，设置为空
                    customdata = None
                
                print(f"[DATA] customdata: {customdata}")

                if isinstance(customdata, list) and len(customdata) >= 7:
                    # 从customdata提取信息：[t_on/10, t_off/10, original_key_id, value, label, index, algorithm_name]
                    algorithm_name = customdata[6]
                    key_id = int(customdata[2])
                    data_type = customdata[4]  # 'record' 或 'play'
                    index = int(customdata[5])
                    print(f"[STATS] 从customdata提取: algorithm_name={algorithm_name}, key_id={key_id}, data_type={data_type}, index={index}")
                
                # 如果没有customdata，从点击坐标查找对应的音符
                if not algorithm_name or key_id is None or index is None:
                    # 获取点击的坐标
                    click_x = point.get('x')  # 时间（ms）
                    click_y = point.get('y')  # 按键ID
                    
                    if click_x is None or click_y is None:
                        print("[ERROR] 无法从坐标获取点击位置")
                        return current_style, []
                    
                    print(f"[LOCATION] 从坐标获取: x={click_x}ms, y={click_y}")
                    
                    # 在多算法模式下，需要根据y坐标判断是哪个算法
                    if backend.multi_algorithm_mode and backend.multi_algorithm_manager:
                        active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()
                        algorithm_y_range = 100  # 每个算法偏移100个单位
                        
                        # 根据y坐标找到对应的算法和实际按键ID
                        for alg_idx, alg in enumerate(active_algorithms):
                            alg_y_offset = alg_idx * algorithm_y_range
                            if alg_y_offset <= click_y < alg_y_offset + algorithm_y_range:
                                algorithm_name = alg.metadata.algorithm_name
                                key_id = int(click_y - alg_y_offset)
                                print(f"[OK] 找到算法: {algorithm_name}, 实际按键ID: {key_id}")
                                break
                    else:
                        # 单算法模式
                        key_id = int(click_y)
                        algorithm_name = None
                    
                    if not algorithm_name and backend.multi_algorithm_mode:
                        print("[ERROR] 无法确定算法")
                        return current_style, []
                    
                    # 根据时间和按键ID查找对应的音符
                # 获取算法对象
                    if not backend.multi_algorithm_manager:
                        backend._ensure_multi_algorithm_manager()
                    
                    if algorithm_name:
                        algorithm = backend.multi_algorithm_manager.get_algorithm(algorithm_name)
                    else:
                        # 单算法模式
                        algorithm = None
                        if backend.analyzer:
                            # 使用offset_data查找
                            if backend.analyzer.note_matcher:
                                offset_data = backend.analyzer.note_matcher.get_offset_alignment_data()
                                if offset_data:
                                    # 查找时间范围内的音符
                                    click_time_01ms = click_x * 10  # 转换为0.1ms单位
                                    for item in offset_data:
                                        item_key_id = item.get('key_id')
                                        # 确保key_id类型一致
                                        try:
                                            item_key_id = int(item_key_id) if item_key_id is not None else None
                                        except (ValueError, TypeError):
                                            continue
                                        
                                        record_keyon = item.get('record_keyon', 0)
                                        record_keyoff = item.get('record_keyoff', 0)
                                        # 如果没有record_keyoff，使用record_keyon + record_duration
                                        if record_keyoff == 0:
                                            record_duration = item.get('record_duration', 0)
                                            record_keyoff = record_keyon + record_duration
                                        
                                        if item_key_id == key_id and record_keyon <= click_time_01ms <= record_keyoff:
                                            index = item.get('record_index')
                                            data_type = 'record'
                                            print(f"[OK] 单算法模式: 找到音符 index={index}, data_type={data_type}, 时间范围: {record_keyon/10:.1f}ms - {record_keyoff/10:.1f}ms, 点击时间: {click_time_01ms/10:.1f}ms")
                                            break
                    
                    if algorithm_name and not algorithm:
                        print("[ERROR] 无法获取算法对象")
                        return current_style, []
                    
                    # 多算法模式：从offset_data查找
                    if algorithm_name and algorithm and algorithm.analyzer and algorithm.analyzer.note_matcher:
                        offset_data = algorithm.analyzer.note_matcher.get_offset_alignment_data()
                        if offset_data:
                            click_time_01ms = click_x * 10  # 转换为0.1ms单位
                            for item in offset_data:
                                item_key_id = item.get('key_id')
                                # 确保key_id类型一致
                                try:
                                    item_key_id = int(item_key_id) if item_key_id is not None else None
                                except (ValueError, TypeError):
                                    continue
                                
                                record_keyon = item.get('record_keyon', 0)
                                record_keyoff = item.get('record_keyoff', 0)
                                # 如果没有record_keyoff，使用record_keyon + record_duration
                                if record_keyoff == 0:
                                    record_duration = item.get('record_duration', 0)
                                    record_keyoff = record_keyon + record_duration
                                
                                if item_key_id == key_id and record_keyon <= click_time_01ms <= record_keyoff:
                                    index = item.get('record_index')
                                    data_type = 'record'
                                    print(f"[OK] 多算法模式: 找到音符 index={index}, data_type={data_type}, 时间范围: {record_keyon/10:.1f}ms - {record_keyoff/10:.1f}ms, 点击时间: {click_time_01ms/10:.1f}ms")
                                    break
                
                if key_id is None or index is None:
                    print(f"[ERROR] 无法确定按键信息: key_id={key_id}, index={index}")
                    print(f"🔍 调试信息: click_x={point.get('x')}, click_y={point.get('y')}, algorithm_name={algorithm_name}")
                    if not point.get('customdata'):
                        print(f"[WARNING] 没有customdata，尝试从坐标查找失败")
                    return current_style, []
                
                print(f"[STATS] 最终提取的数据: algorithm_name={algorithm_name}, key_id={key_id}, data_type={data_type}, index={index}")
                
                # 获取算法对象
                algorithm = None
                if backend.multi_algorithm_mode:
                    if not algorithm_name:
                        print("[ERROR] 多算法模式下无法确定算法名称")
                        return current_style, []
                if not backend.multi_algorithm_manager:
                    backend._ensure_multi_algorithm_manager()
                algorithm = None
                if backend.multi_algorithm_manager:
                    algorithm = backend.multi_algorithm_manager.get_algorithm(algorithm_name)
                    print(f"[DEBUG] 查找算法: algorithm_name='{algorithm_name}', algorithm={algorithm is not None}")
                    if algorithm:
                        print(f"[DEBUG] 算法状态: is_active={algorithm.is_active}, is_ready={algorithm.is_ready()}, analyzer={algorithm.analyzer is not None}")
                    if not algorithm or not algorithm.analyzer:
                        print(f"[ERROR] 算法对象或analyzer为空: algorithm={algorithm is not None}, analyzer={algorithm.analyzer is not None if algorithm else None}")

                        # 调试：列出所有可用算法
                        all_algorithms = backend.multi_algorithm_manager.get_all_algorithms()
                        print(f"[DEBUG] 所有可用算法: {[alg.metadata.algorithm_name for alg in all_algorithms]}")

                        # 如果是多算法模式但找不到算法，尝试单算法模式
                        if backend.analyzer:
                            print("[INFO] 尝试使用单算法模式")
                            algorithm = None  # 标记为单算法模式
                        else:
                            return current_style, []
                else:
                    # 单算法模式
                    if not backend.analyzer:
                        print("[ERROR] analyzer为空")
                        return current_style, []
                    algorithm = None  # 单算法模式下不需要algorithm对象
                
                # 获取matched_pairs（已保存的配对数据）
                if algorithm is not None:
                    # 多算法模式
                    matched_pairs = algorithm.analyzer.matched_pairs if hasattr(algorithm.analyzer, 'matched_pairs') else []
                    valid_record_data = algorithm.analyzer.valid_record_data if hasattr(algorithm.analyzer, 'valid_record_data') else []
                    valid_replay_data = algorithm.analyzer.valid_replay_data if hasattr(algorithm.analyzer, 'valid_replay_data') else []
                else:
                    # 单算法模式
                    matched_pairs = backend.analyzer.matched_pairs if hasattr(backend.analyzer, 'matched_pairs') else []
                    valid_record_data = backend.analyzer.valid_record_data if hasattr(backend.analyzer, 'valid_record_data') else []
                    valid_replay_data = backend.analyzer.valid_replay_data if hasattr(backend.analyzer, 'valid_replay_data') else []
                
                # 步骤1：先判断这个按键ID（通过index）是否在matched_pairs中有匹配对
                has_matched_pair = False
                record_note = None
                replay_note = None
                
                print(f"🔍 开始查找匹配对: key_id={key_id}, data_type={data_type}, index={index}")
                print(f"[STATS] matched_pairs数量: {len(matched_pairs)}")
                
                # 根据data_type和index在matched_pairs中查找
                if data_type == 'record':
                    # 点击的是录制线，查找r_idx == index的匹配对
                    print(f"🔍 在matched_pairs中查找: r_idx == {index}")
                    for r_idx, p_idx, r_note, p_note in matched_pairs:
                        if r_idx == index and r_note.id == key_id:
                            # 找到匹配对
                            has_matched_pair = True
                            record_note = r_note
                            replay_note = p_note
                            print(f"[OK] 找到完整匹配对！")
                            break
                else:
                    # 点击的是播放线，查找p_idx == index的匹配对
                    print(f"🔍 在matched_pairs中查找: p_idx == {index}")
                    for r_idx, p_idx, r_note, p_note in matched_pairs:
                        if p_idx == index and p_note.id == key_id:
                            # 找到匹配对
                            has_matched_pair = True
                            record_note = r_note
                            replay_note = p_note
                            print(f"[OK] 找到完整匹配对！")
                            break
                
                print(f"[TARGET] 匹配结果: has_matched_pair={has_matched_pair}")
                
                # 步骤2：根据匹配结果生成曲线
                if has_matched_pair:
                    # 获取当前算法的display_name，用于判断是否是同种算法的不同曲子
                    current_display_name = None
                    if algorithm and algorithm.metadata:
                        current_display_name = algorithm.metadata.display_name

                    # 在多算法模式下，查找所有算法中匹配到同一个录制音符的播放音符
                    # 但是，对于同种算法的不同曲子（相同display_name），不添加其他算法的曲线
                    other_algorithm_notes = []  # [(algorithm_name, play_note), ...]
                    if backend.multi_algorithm_mode and backend.multi_algorithm_manager:
                        active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()
                        for alg in active_algorithms:
                            if alg.metadata.algorithm_name == algorithm_name:
                                continue  # 跳过当前算法（已经绘制）

                            # 如果是同种算法的不同曲子（相同display_name），跳过
                            if current_display_name and alg.metadata.display_name == current_display_name:
                                logger.info(f"[SKIP] 跳过同种算法的不同曲子: {alg.metadata.algorithm_name} (display_name={alg.metadata.display_name})")
                                continue

                            if not alg.analyzer or not hasattr(alg.analyzer, 'matched_pairs'):
                                continue

                            alg_matched_pairs = alg.analyzer.matched_pairs
                            # 查找匹配到同一个record_index的播放音符
                            for r_idx, p_idx, r_note, p_note in alg_matched_pairs:
                                if r_idx == index and r_note.id == key_id:
                                    other_algorithm_notes.append((alg.metadata.algorithm_name, p_note))
                                    logger.info(f"[OK] 找到算法 '{alg.metadata.algorithm_name}' 的匹配播放音符")
                                    break

                    # 有匹配对：绘制录制+播放对比曲线
                    # 对于同种算法的不同曲子，other_algorithm_notes为空，只显示录制和播放曲线

                    # 计算各算法的平均延时
                    mean_delays = {}
                    if not algorithm or not algorithm.analyzer:
                        print(f"[ERROR] 算法对象或分析器为空，无法计算平均延时")
                        return current_style, []

                    mean_error_0_1ms = algorithm.analyzer.get_mean_error()
                    mean_delays[algorithm_name] = mean_error_0_1ms / 10.0  # 转换为毫秒

                    # 为其他算法也计算平均延时
                    for other_alg_name, _ in other_algorithm_notes:
                        if backend.multi_algorithm_mode and backend.multi_algorithm_manager:
                            other_alg = None
                            for alg in backend.multi_algorithm_manager.get_active_algorithms():
                                if alg.metadata.algorithm_name == other_alg_name:
                                    other_alg = alg
                                    break
                            if other_alg and other_alg.analyzer:
                                other_mean_error_0_1ms = other_alg.analyzer.get_mean_error()
                                mean_delays[other_alg_name] = other_mean_error_0_1ms / 10.0  # 转换为毫秒
                            else:
                                print(f"[ERROR] 其他算法 '{other_alg_name}' 对象或分析器为空")
                                return current_style, []

                    detail_figure_combined = spmid.plot_note_comparison_plotly(
                        record_note,
                        replay_note,
                        algorithm_name=algorithm_name,
                        other_algorithm_notes=other_algorithm_notes,  # 对于同种算法的不同曲子，这是空列表
                        mean_delays=mean_delays
                    )
                    print(f"[OK] 按键ID {key_id} 有匹配对，绘制录制+播放对比曲线（同种算法不同曲子时不显示其他算法曲线）")
                else:
                    # 没有匹配对：只绘制这个数据点的数据（可能是录制，也可能是播放）
                    # 对于匹配失败的音符，需要从原始数据中查找正确的音符对象
                    print(f"[INFO] 未找到匹配对，尝试查找匹配失败的音符数据")

                    # 首先尝试直接索引
                    found_note = False
                    if data_type == 'record' and index >= 0 and index < len(valid_record_data):
                        record_note = valid_record_data[index]
                        replay_note = None
                        # 验证按键ID是否匹配
                        if hasattr(record_note, 'id') and record_note.id == key_id:
                            found_note = True
                            print(f"[OK] 通过直接索引找到录制音符: index={index}, key_id={key_id}")
                        else:
                            record_note = None
                            print(f"[WARNING] 直接索引的录制音符key_id不匹配: 期望{key_id}, 实际{record_note.id if record_note else 'N/A'}")

                    elif data_type == 'play' and index >= 0 and index < len(valid_replay_data):
                        record_note = None
                        replay_note = valid_replay_data[index]
                        # 验证按键ID是否匹配
                        if hasattr(replay_note, 'id') and replay_note.id == key_id:
                            found_note = True
                            print(f"[OK] 通过直接索引找到播放音符: index={index}, key_id={key_id}")
                        else:
                            replay_note = None
                            print(f"[WARNING] 直接索引的播放音符key_id不匹配: 期望{key_id}, 实际{replay_note.id if replay_note else 'N/A'}")

                    # 如果直接索引失败，尝试通过key_id遍历查找
                    if not found_note:
                        print(f"[INFO] 直接索引失败，尝试通过key_id遍历查找")
                        if data_type == 'record':
                            for i, note in enumerate(valid_record_data):
                                if hasattr(note, 'id') and note.id == key_id:
                                    record_note = note
                                    replay_note = None
                                    found_note = True
                                    print(f"[OK] 通过遍历找到录制音符: array_index={i}, key_id={key_id}")
                                    break
                        elif data_type == 'play':
                            for i, note in enumerate(valid_replay_data):
                                if hasattr(note, 'id') and note.id == key_id:
                                    record_note = None
                                    replay_note = note
                                    found_note = True
                                    print(f"[OK] 通过遍历找到播放音符: array_index={i}, key_id={key_id}")
                                    break

                    # 如果仍然找不到，尝试从错误数据中查找（丢锤、多锤）
                    if not found_note:
                        print(f"[INFO] 在有效数据中未找到，尝试从错误数据中查找")
                        # 获取错误数据
                        drop_hammers = getattr(algorithm.analyzer if algorithm else backend.analyzer, 'drop_hammers', [])
                        multi_hammers = getattr(algorithm.analyzer if algorithm else backend.analyzer, 'multi_hammers', [])

                        # 检查丢锤数据
                        for error_note in drop_hammers:
                            if hasattr(error_note, 'infos') and error_note.infos:
                                for note_info in error_note.infos:
                                    if hasattr(note_info, 'keyId') and note_info.keyId == key_id:
                                        # 对于丢锤，只显示录制数据
                                        if data_type == 'record':
                                            # 尝试从valid_record_data中找到对应的音符
                                            for note in valid_record_data:
                                                if hasattr(note, 'id') and note.id == key_id:
                                                    record_note = note
                                                    replay_note = None
                                                    found_note = True
                                                    print(f"[OK] 从丢锤数据中找到录制音符: key_id={key_id}")
                                                    break
                                        break
                            if found_note:
                                break

                        # 如果还没找到，检查多锤数据
                        if not found_note:
                            for error_note in multi_hammers:
                                if hasattr(error_note, 'infos') and error_note.infos:
                                    for note_info in error_note.infos:
                                        if hasattr(note_info, 'keyId') and note_info.keyId == key_id:
                                            # 对于多锤，只显示播放数据
                                            if data_type == 'play':
                                                # 尝试从valid_replay_data中找到对应的音符
                                                for note in valid_replay_data:
                                                    if hasattr(note, 'id') and note.id == key_id:
                                                        record_note = None
                                                        replay_note = note
                                                        found_note = True
                                                        print(f"[OK] 从多锤数据中找到播放音符: key_id={key_id}")
                                                        break
                                            break
                                if found_note:
                                    break

                    if not found_note:
                        print(f"[ERROR] 无法找到任何匹配的音符数据: key_id={key_id}, data_type={data_type}")
                        return current_style, []

                    # 计算平均延时（对于匹配失败的音符，使用0作为平均延时，不进行偏移）
                    mean_delays = {algorithm_name: 0.0}  # 不进行时间轴偏移

                    detail_figure_combined = spmid.plot_note_comparison_plotly(
                        record_note, replay_note,
                        algorithm_name=algorithm_name,
                        mean_delays=mean_delays
                    )
                    print(f"[OK] 匹配失败的按键ID {key_id} 找到音符数据，只绘制单侧曲线（无偏移）")
                
                if not detail_figure_combined:
                    print("[ERROR] 曲线生成失败")
                    return current_style, []
                
                # 显示模态框
                modal_style = {
                    'display': 'block',
                    'position': 'fixed',
                    'zIndex': '9999',
                    'left': '0',
                    'top': '0',
                    'width': '100%',
                    'height': '100%',
                    'backgroundColor': 'rgba(0,0,0,0.6)',
                    'backdropFilter': 'blur(5px)'
                }
                

                
                # 生成全过程处理图
                processing_stages_figure = None
                if backend.force_curve_analyzer and record_note and replay_note:
                    try:
                        comparison_result = backend.force_curve_analyzer.compare_curves(record_note, replay_note)
                        if comparison_result:
                            processing_stages_figure = backend.force_curve_analyzer.visualize_all_processing_stages(comparison_result)
                    except Exception as e:
                        print(f"[ERROR] 生成全过程处理图失败: {e}")

                # 构建模态框内容：使用Tabs展示对比图和全过程图
                modal_content = [
                    dcc.Tabs([
                        dcc.Tab(label='曲线对比', children=[
                            dcc.Graph(
                                figure=detail_figure_combined, 
                                style={'height': '700px'},
                                config={'scrollZoom': True, 'displayModeBar': True}
                            )
                        ]),
                        dcc.Tab(label='处理全过程', children=[
                            html.Div(
                                style={'height': '85vh', 'overflowY': 'auto', 'padding': '10px'},
                                children=[
                            dcc.Graph(
                                figure=processing_stages_figure if processing_stages_figure else go.Figure(),
                                        style={'height': f"{processing_stages_figure.layout.height}px"} if processing_stages_figure and processing_stages_figure.layout.height else {'height': '2000px'},
                                        config={'scrollZoom': True, 'displayModeBar': True, 'responsive': True}
                            ) if processing_stages_figure else html.Div("无法生成处理全过程图（可能只有单侧数据）", className="text-center p-3 text-muted")
                                ]
                            )
                        ])
                    ])
                ]
                
                rendered_row = html.Div(modal_content)
                
                print("[OK] 显示模态框")
                return modal_style, [rendered_row]
                
            except Exception as e:
                logger.error(f"[ERROR] 瀑布图点击处理失败: {e}")
                logger.error(traceback.format_exc())
                print(traceback.format_exc())
                return current_style, []
        
        # 其他情况，保持当前状态
        return current_style, []

    # 跳转到瀑布图按钮回调
    @app.callback(
        [Output('main-plot', 'figure', allow_duplicate=True),
         Output('main-tabs', 'value', allow_duplicate=True),
         Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('jump-source-plot-id', 'data', allow_duplicate=True)],
        [Input('jump-to-waterfall-btn', 'n_clicks'),
         Input('jump-to-waterfall-btn-from-modal', 'n_clicks')],
        [State('session-id', 'data'),
         State('current-clicked-point-info', 'data')],
        prevent_initial_call=True
    )
    def handle_jump_to_waterfall(n_clicks, n_clicks_from_modal, session_id, point_info):
        """处理跳转到瀑布图按钮点击"""
        return waterfall_jump_handler.handle_jump_to_waterfall(n_clicks or n_clicks_from_modal, session_id, point_info)
    
    # 返回报告界面按钮回调
    @app.callback(
        [Output('main-tabs', 'value', allow_duplicate=True),
         Output('scroll-to-plot-trigger', 'data', allow_duplicate=True),
         Output('grade-detail-section-scroll-trigger', 'data', allow_duplicate=True)],
        [Input('btn-return-to-report', 'n_clicks')],
        [State('jump-source-plot-id', 'data')],
        prevent_initial_call=True
    )
    def handle_return_to_report(n_clicks, source_plot_id):
        """处理返回报告界面按钮点击，并触发滚动到来源图表"""
        if n_clicks and n_clicks > 0:
            logger.info(f"[PROCESS] 返回报告界面，来源图表: {source_plot_id}")
            
            # 如果是相对延时分布图，需要特殊处理
            if isinstance(source_plot_id, dict):
                # 从point_info中获取子图索引
                # source_plot_id 可能包含子图索引信息
                if source_plot_id.get('type') == 'relative-delay-distribution-plot':
                    subplot_idx = source_plot_id.get('index')
                    if subplot_idx is not None:
                        # 返回包含子图索引的滚动数据
                        scroll_data = {
                            'plot_type': 'relative-delay-distribution',
                            'subplot_index': int(subplot_idx)  # 确保是整数
                        }
                        return 'report-tab', scroll_data, no_update
                # 其他情况，返回原始数据（但需要确保是JSON可序列化的）
                return 'report-tab', source_plot_id, no_update
            elif isinstance(source_plot_id, str) and source_plot_id == 'relative-delay-distribution-plot':
                # 需要从point_info中获取子图索引
                # 但由于这里没有point_info，我们需要通过其他方式获取
                # 暂时返回一个通用的滚动数据，让客户端回调处理
                scroll_data = {
                    'plot_type': 'relative-delay-distribution',
                    'subplot_index': None  # 客户端会尝试找到第一个可见的子图
                }
                return 'report-tab', scroll_data, no_update
            elif source_plot_id == 'grade-detail-curves-modal':
                # 从评级统计模态框跳转回来，滚动到评级统计区域
                section_scroll_data = {'scroll_to': 'grade_detail_section'}
                logger.info("[PROCESS] 从评级统计跳转回来，触发区域滚动")
                return 'report-tab', no_update, section_scroll_data
            elif source_plot_id in ['error-table-drop', 'error-table-multi']:
                # 从错误表格模态框跳转回来，滚动到对应的错误表格区域
                error_table_scroll_data = {'scroll_to': 'error_table_section', 'table_type': source_plot_id.split('-')[-1]}
                logger.info(f"[PROCESS] 从{source_plot_id}跳转回来，触发错误表格区域滚动")
                return 'report-tab', no_update, error_table_scroll_data
            elif source_plot_id in ['raw-delay-time-series-plot', 'relative-delay-time-series-plot']:
                # 从延时时间序列图跳转回来，滚动到对应的时间序列图区域
                time_series_scroll_data = {'scroll_to': 'delay_time_series_section', 'plot_type': source_plot_id}
                logger.info(f"[PROCESS] 从{source_plot_id}跳转回来，触发时间序列图区域滚动")
                return 'report-tab', no_update, time_series_scroll_data
            else:
                # 普通图表，直接返回ID（字符串）
                if source_plot_id:
                    return 'report-tab', str(source_plot_id), no_update
                else:
                    return 'report-tab', None, no_update

            return no_update, no_update, no_update
    
    # 客户端回调：滚动到指定图表
    app.clientside_callback(
        """
        function(scroll_data) {
            if (scroll_data === null || scroll_data === undefined) {
                return window.dash_clientside.no_update;
            }
            
            try {
                // 如果是相对延时分布图的滚动数据（对象格式）
                if (typeof scroll_data === 'object' && scroll_data !== null && scroll_data.plot_type === 'relative-delay-distribution') {
                    const subplotIndex = scroll_data.subplot_index;
                    // 等待一小段时间，确保标签页切换完成
                    setTimeout(function() {
                        try {
                            // 查找所有相对延时分布图的子图容器
                            // 子图容器的结构：每个子图都在一个Div中，包含Graph元素
                            const allContainers = document.querySelectorAll('[id*="relative-delay-distribution"]');
                            let targetElement = null;
                            
                            // 如果指定了子图索引，尝试找到对应的子图
                            if (subplotIndex) {
                                // 查找包含指定索引的子图容器
                                // 由于Pattern Matching Callbacks，ID格式是动态的
                                // 我们需要通过遍历所有容器来找到对应的子图
                                let currentIndex = 1;
                                allContainers.forEach(function(container) {
                                    // 检查是否是图表容器（包含Graph元素）
                                    const graphElement = container.querySelector('.js-plotly-plot');
                                    if (graphElement && currentIndex === subplotIndex) {
                                        targetElement = container;
                                    }
                                    if (graphElement) {
                                        currentIndex++;
                                    }
                                });
                            }
                            
                            // 如果找到了目标元素，滚动到它
                            if (targetElement) {
                                const elementPosition = targetElement.getBoundingClientRect().top + window.pageYOffset;
                                const offsetPosition = elementPosition - 100;
                                window.scrollTo({
                                    top: offsetPosition,
                                    behavior: 'smooth'
                                });
                            } else if (allContainers.length > 0) {
                                // 如果找不到，滚动到第一个可见的相对延时分布图子图
                                const firstContainer = allContainers[0];
                                const elementPosition = firstContainer.getBoundingClientRect().top + window.pageYOffset;
                                const offsetPosition = elementPosition - 100;
                                window.scrollTo({
                                    top: offsetPosition,
                                    behavior: 'smooth'
                                });
                            }
                        } catch (e) {
                            console.error('滚动到相对延时分布图失败:', e);
                        }
                    }, 300);
                    return window.dash_clientside.no_update;
                }
                
                // 普通图表ID（字符串）
                if (typeof scroll_data === 'string') {
                    const plot_id = scroll_data;
                    // 等待一小段时间，确保标签页切换完成
                    setTimeout(function() {
                        try {
                            // 查找对应的图表元素
                            const plotElement = document.getElementById(plot_id);
                            if (plotElement) {
                                // 滚动到图表位置，并添加一些偏移量（向上偏移100px，避免被顶部导航栏遮挡）
                                const elementPosition = plotElement.getBoundingClientRect().top + window.pageYOffset;
                                const offsetPosition = elementPosition - 100;
                                
                                window.scrollTo({
                                    top: offsetPosition,
                                    behavior: 'smooth'  // 平滑滚动
                                });
                            }
                        } catch (e) {
                            console.error('滚动到图表失败:', e);
                        }
                    }, 300);  // 延迟300ms，确保DOM更新完成
                }
            } catch (e) {
                console.error('客户端回调错误:', e);
            }
            
            return window.dash_clientside.no_update;
        }
        """,
        Output('scroll-to-plot-trigger', 'data', allow_duplicate=True),
        Input('scroll-to-plot-trigger', 'data'),
        prevent_initial_call=True
    )
    
    # 客户端回调：滚动到相对延时分布图的对应子图位置
    app.clientside_callback(
        """
        function(scroll_data) {
            if (!scroll_data || !scroll_data.subplot_index) {
                return window.dash_clientside.no_update;
            }
            
            const subplotIndex = scroll_data.subplot_index;
            const graphElement = document.getElementById('relative-delay-distribution-plot');
            if (!graphElement) {
                return window.dash_clientside.no_update;
            }
            
            // 计算子图的位置（每个子图高度约500px）
            const baseHeightPerSubplot = 500;
            const subplotTop = (subplotIndex - 1) * baseHeightPerSubplot;
            
            // 获取图表元素的位置
            setTimeout(function() {
                const graphRect = graphElement.getBoundingClientRect();
                const absoluteGraphTop = graphRect.top + window.pageYOffset;
                const targetScrollTop = absoluteGraphTop + subplotTop;
                
                // 滚动到对应子图位置
                window.scrollTo({
                    top: targetScrollTop,
                    behavior: 'smooth'
                });
                
                // 延迟后滚动到表格位置
                setTimeout(function() {
                    const tableContainer = document.getElementById('relative-delay-distribution-table-container');
                    if (tableContainer) {
                        const tableRect = tableContainer.getBoundingClientRect();
                        const absoluteTableTop = tableRect.top + window.pageYOffset;
                        const offset = 100;
                        window.scrollTo({
                            top: absoluteTableTop - offset,
                            behavior: 'smooth'
                        });
                    }
                }, 500);
            }, 300);
            
            return window.dash_clientside.no_update;
        }
        """,
        Output('relative-delay-distribution-scroll-trigger', 'data', allow_duplicate=True),
        Input('relative-delay-distribution-scroll-trigger', 'data'),
        prevent_initial_call=True
    )

    # 客户端回调：评级统计返回时滚动到对应行
    app.clientside_callback(
        """
        function(scroll_data) {
            if (!scroll_data || !scroll_data.table_index || scroll_data.row_index === undefined) {
                return window.dash_clientside.no_update;
            }

            const tableIndex = scroll_data.table_index;
            const rowIndex = scroll_data.row_index;

            // 查找对应的表格
            const tableSelector = `[data-dash-component-id*="grade-detail-datatable"][data-dash-component-id*="${tableIndex}"]`;
            const tableElement = document.querySelector(tableSelector);

            if (!tableElement) {
                console.warn('Grade detail table not found:', tableSelector);
                return window.dash_clientside.no_update;
            }

            // 模拟点击对应行来激活它
            setTimeout(function() {
                try {
                    // 构造表格行的选择器
                    // Dash表格的行通常有特定的类名和结构
                    const tableBody = tableElement.querySelector('.dash-table-body');
                    if (tableBody) {
                        const rows = tableBody.querySelectorAll('.dash-table-row');
                        if (rows && rows.length > rowIndex) {
                            const targetRow = rows[rowIndex];

                            // 滚动到目标行
                            targetRow.scrollIntoView({
                                behavior: 'smooth',
                                block: 'center'
                            });

                            // 触发行的点击事件来激活它
                            // 注意：这可能需要根据Dash表格的具体实现进行调整
                            setTimeout(function() {
                                // 尝试设置active_cell（如果可能的话）
                                // 这是一个简化的实现，实际可能需要更复杂的逻辑
                                console.log('Scrolled to grade detail table row:', rowIndex);
                            }, 300);
                        } else {
                            console.warn('Target row not found in grade detail table:', rowIndex);
                        }
                    }
                } catch (error) {
                    console.error('Error scrolling to grade detail table row:', error);
                }
            }, 500);  // 等待模态框显示后再滚动

            return window.dash_clientside.no_update;
        }
        """,
        Output('grade-detail-return-scroll-trigger', 'data', allow_duplicate=True),
        Input('grade-detail-return-scroll-trigger', 'data'),
        prevent_initial_call=True
    )

    # 客户端回调：滚动到评级统计区域
    app.clientside_callback(
        """
        function(scroll_data) {
            if (!scroll_data) {
                return window.dash_clientside.no_update;
            }

            if (scroll_data.scroll_to === 'grade_detail_section') {
                // 查找评级统计区域
                // 优先查找有特定ID的卡片
                let targetElement = document.getElementById('grade-statistics-card');

                if (!targetElement) {
                    // 如果没找到特定ID，查找所有卡片，寻找包含"匹配质量评级统计"的标题
                    const allCards = document.querySelectorAll('.card');
                    for (let card of allCards) {
                        const header = card.querySelector('h4');
                        if (header && header.textContent && header.textContent.includes('匹配质量评级统计')) {
                            targetElement = card;
                            console.log('Found grade detail card by title:', header.textContent);
                            break;
                        }
                    }
                }

                // 如果还是没找到，尝试查找包含grade-detail的元素
                if (!targetElement) {
                    const gradeDetailElements = document.querySelectorAll('[id*="grade-detail"]');
                    if (gradeDetailElements.length > 0) {
                        // 向上查找最近的卡片容器
                        targetElement = gradeDetailElements[0].closest('.card') || gradeDetailElements[0];
                        console.log('Found grade detail element by fallback');
                    }
                }

                if (targetElement) {
                    setTimeout(function() {
                        try {
                            // 滚动到评级统计区域
                            targetElement.scrollIntoView({
                                behavior: 'smooth',
                                block: 'start',
                                inline: 'nearest'
                            });

                            console.log('Scrolled to grade detail section successfully');
                        } catch (error) {
                            console.error('Error scrolling to grade detail section:', error);
                        }
                    }, 500);  // 等待更长时间让页面完全加载
                } else {
                    console.warn('Grade detail section not found. Available cards:');
                    const cards = document.querySelectorAll('.card');
                    for (let card of cards) {
                        const header = card.querySelector('h4');
                        if (header) {
                            console.warn('Card header:', header.textContent);
                        }
                    }
                }
            } else if (scroll_data.scroll_to === 'error_table_section') {
                // 查找错误表格区域
                const tableType = scroll_data.table_type; // 'drop' 或 'multi'
                let targetElement = null;

                if (tableType === 'drop') {
                    // 查找丢锤表格
                    const dropTables = document.querySelectorAll('[id*="drop-hammers-table"]');
                    if (dropTables.length > 0) {
                        targetElement = dropTables[0].closest('.card') || dropTables[0];
                        console.log('Found drop hammers table');
                    }
                } else if (tableType === 'multi') {
                    // 查找多锤表格
                    const multiTables = document.querySelectorAll('[id*="multi-hammers-table"]');
                    if (multiTables.length > 0) {
                        targetElement = multiTables[0].closest('.card') || multiTables[0];
                        console.log('Found multi hammers table');
                    }
                }

                if (targetElement) {
                    setTimeout(function() {
                        try {
                            // 滚动到错误表格区域
                            targetElement.scrollIntoView({
                                behavior: 'smooth',
                                block: 'start',
                                inline: 'nearest'
                            });

                            console.log(`Scrolled to ${tableType} hammers table section successfully`);
                        } catch (error) {
                            console.error(`Error scrolling to ${tableType} hammers table section:`, error);
                        }
                    }, 500);
                } else {
                    console.warn(`${tableType} hammers table section not found`);
                }
            } else if (scroll_data.scroll_to === 'delay_time_series_section') {
                // 查找延时时间序列图区域
                const plotType = scroll_data.plot_type; // 'raw-delay-time-series-plot' 或 'relative-delay-time-series-plot'
                let targetElement = null;

                // 根据图表类型查找对应的图表
                if (plotType === 'raw-delay-time-series-plot') {
                    // 查找原始延时时间序列图
                    targetElement = document.getElementById('raw-delay-time-series-plot');
                    if (targetElement) {
                        // 向上查找最近的卡片容器
                        targetElement = targetElement.closest('.card') || targetElement;
                        console.log('Found raw delay time series plot');
                    }
                } else if (plotType === 'relative-delay-time-series-plot') {
                    // 查找相对延时时间序列图
                    targetElement = document.getElementById('relative-delay-time-series-plot');
                    if (targetElement) {
                        // 向上查找最近的卡片容器
                        targetElement = targetElement.closest('.card') || targetElement;
                        console.log('Found relative delay time series plot');
                    }
                }

                // 如果没找到特定图表，尝试查找包含时间序列图标题的卡片
                if (!targetElement) {
                    const allCards = document.querySelectorAll('.card');
                    for (let card of allCards) {
                        const header = card.querySelector('h6');
                        if (header && header.textContent) {
                            if (plotType === 'raw-delay-time-series-plot' &&
                                header.textContent.includes('原始延时时间序列图')) {
                                targetElement = card;
                                console.log('Found raw delay time series card by title');
                                break;
                            } else if (plotType === 'relative-delay-time-series-plot' &&
                                     header.textContent.includes('相对延时时间序列图')) {
                                targetElement = card;
                                console.log('Found relative delay time series card by title');
                                break;
                            }
                        }
                    }
                }

                if (targetElement) {
                    setTimeout(function() {
                        try {
                            // 滚动到时间序列图区域
                            targetElement.scrollIntoView({
                                behavior: 'smooth',
                                block: 'start',
                                inline: 'nearest'
                            });

                            console.log(`Scrolled to ${plotType} successfully`);
                        } catch (error) {
                            console.error(`Error scrolling to ${plotType}:`, error);
                        }
                    }, 500);  // 等待页面完全加载
                } else {
                    console.warn(`${plotType} not found. Available cards:`);
                    const cards = document.querySelectorAll('.card');
                    for (let card of cards) {
                        const header = card.querySelector('h6');
                        if (header) {
                            console.warn('Card header:', header.textContent);
                        }
                    }
                }
            }

            return window.dash_clientside.no_update;
        }
        """,
        Output('grade-detail-section-scroll-trigger', 'data', allow_duplicate=True),
        Input('grade-detail-section-scroll-trigger', 'data'),
        prevent_initial_call=True
    )



    # ==================== 曲线对齐测试回调 ====================
    @app.callback(
        Output('curve-alignment-test-result', 'children'),
        Input('btn-test-curve-alignment', 'n_clicks'),
        State('session-id', 'data'),
        prevent_initial_call=True
    )
    def handle_test_curve_alignment(n_clicks, session_id):
        """处理曲线对齐测试按钮点击"""
        if n_clicks is None or n_clicks == 0:
            return html.Div("点击按钮开始测试", 
                           className="text-muted text-center",
                           style={'padding': '20px', 'fontSize': '14px'})
        
        try:
            backend = session_manager.get_backend(session_id)
            if not backend:
                return html.Div([
                    dbc.Alert("[WARNING] 无法获取backend，请先上传数据", color="warning")
                ])
            
            # 执行测试
            test_result = backend.test_curve_alignment()
            
            if test_result is None or test_result.get('status') != 'success':
                error_msg = test_result.get('message', '测试失败') if test_result else '测试失败'
                return html.Div([
                    dbc.Alert([
                        html.I(className="fas fa-exclamation-triangle me-2"),
                        html.Strong(f"测试失败: {error_msg}")
                    ], color="danger")
                ])
            
            result = test_result['result']
            comparison_fig = test_result.get('comparison_figure')  # 对齐前后对比图（向后兼容）
            all_stages_fig = test_result.get('all_stages_figure')  # 所有处理阶段的对比图 (兼容旧版)
            individual_stage_figures = test_result.get('individual_stage_figures', []) # 新版独立图表列表
            
            # 构建结果显示
            children = []
            
            # 渲染所有处理阶段的图表
            # 优先使用新的独立图表列表
            if individual_stage_figures:
                children.append(html.H6("各处理阶段曲线对比（播放曲线对齐到录制曲线）", 
                           className="mb-3",
                           style={'color': '#2c3e50', 'fontWeight': 'bold'}))
                
                for stage_info in individual_stage_figures:
                    title = stage_info.get('title', '未知阶段')
                    fig = stage_info.get('figure')
                    
                    if fig:
                        children.append(html.Div([
                            html.H6(title, className="mt-4 mb-2", style={'fontSize': '14px', 'fontWeight': 'bold', 'color': '#555'}),
                            dcc.Graph(
                                figure=fig, 
                                config={'displayModeBar': True}
                            )
                        ], className="mb-2"))
            
            # 如果没有新版图表，回退到旧版大图
            elif all_stages_fig is not None:
                children.append(html.Div([
                    html.H6("各处理阶段曲线对比（播放曲线对齐到录制曲线）", 
                           className="mb-3",
                           style={'color': '#2c3e50', 'fontWeight': 'bold'}),
                    dcc.Graph(figure=all_stages_fig, style={'height': '2800px', 'minHeight': '2000px'})
                ], className="mb-4"))
            
            # 相似度信息
            children.append(
                html.Div([
                    html.H6("相似度结果", className="mb-3",
                           style={'color': '#2c3e50', 'fontWeight': 'bold'}),
                    dbc.Row([
                        dbc.Col([
                            dbc.Card([
                                dbc.CardBody([
                                    html.Small("上升沿相似度", className="text-muted d-block mb-1"),
                                    html.H4(f"{result.get('rising_edge_similarity', 0):.3f}", 
                                           style={'color': '#1f77b4', 'fontWeight': 'bold'})
                                ])
                            ], color="primary", outline=True)
                        ], width=4),
                        dbc.Col([
                            dbc.Card([
                                dbc.CardBody([
                                    html.Small("下降沿相似度", className="text-muted d-block mb-1"),
                                    html.H4(f"{result.get('falling_edge_similarity', 0):.3f}", 
                                           style={'color': '#ff7f0e', 'fontWeight': 'bold'})
                                ])
                            ], color="warning", outline=True)
                        ], width=4),
                        dbc.Col([
                            dbc.Card([
                                dbc.CardBody([
                                    html.Small("整体相似度", className="text-muted d-block mb-1"),
                                    html.H4(f"{result.get('overall_similarity', 0):.3f}", 
                                           style={'color': '#2ca02c', 'fontWeight': 'bold'})
                                ])
                            ], color="success", outline=True)
                        ], width=4)
                    ], className="mb-3"),
                ], className="mb-4")
            )

            # 特征量化分析表格
            record_feat = result.get('record_features', {})
            replay_feat = result.get('replay_features', {})
            feat_diff = result.get('feature_comparison', {})
            
            if record_feat and replay_feat:
                import pandas as pd
                
                # 准备表格数据
                table_data = [
                    {
                        "指标": "峰值力度 (Peak)", 
                        "录制值": f"{record_feat.get('peak_value', 0):.1f}", 
                        "播放值": f"{replay_feat.get('peak_value', 0):.1f}", 
                        "差异": f"{feat_diff.get('peak_diff', 0):.1f}",
                        "说明": "Max Value"
                    },
                    {
                        "指标": "峰值时间 (Time)", 
                        "录制值": f"{record_feat.get('peak_time', 0):.1f}ms", 
                        "播放值": f"{replay_feat.get('peak_time', 0):.1f}ms", 
                        "差异": f"{feat_diff.get('peak_time_lag', 0):.1f}ms",
                        "说明": "Time Lag"
                    },
                    {
                        "指标": "上升时间 (Rise Time)", 
                        "录制值": f"{record_feat.get('rise_time_ms', 0):.1f}ms", 
                        "播放值": f"{replay_feat.get('rise_time_ms', 0):.1f}ms", 
                        "差异": f"{feat_diff.get('rise_time_diff', 0):.1f}ms",
                        "说明": "10% -> 90%"
                    },
                    {
                        "指标": "上升斜率 (Rise Slope)", 
                        "录制值": f"{record_feat.get('rise_slope', 0):.2f}", 
                        "播放值": f"{replay_feat.get('rise_slope', 0):.2f}", 
                        "差异": f"{replay_feat.get('rise_slope', 0) - record_feat.get('rise_slope', 0):.2f}",
                        "说明": "Value / ms"
                    },
                    {
                        "指标": "下降时间 (Fall Time)", 
                        "录制值": f"{record_feat.get('fall_time_ms', 0):.1f}ms", 
                        "播放值": f"{replay_feat.get('fall_time_ms', 0):.1f}ms", 
                        "差异": f"{feat_diff.get('fall_time_diff', 0):.1f}ms",
                        "说明": "90% -> 10%"
                    },
                    {
                        "指标": "下降斜率 (Fall Slope)", 
                        "录制值": f"{record_feat.get('fall_slope', 0):.2f}", 
                        "播放值": f"{replay_feat.get('fall_slope', 0):.2f}", 
                        "差异": f"{replay_feat.get('fall_slope', 0) - record_feat.get('fall_slope', 0):.2f}",
                        "说明": "Value / ms"
                    },
                    {
                        "指标": "抖动度 (Jitter RMSE)", 
                        "录制值": f"{record_feat.get('jitter', 0):.2f}", 
                        "播放值": f"{replay_feat.get('jitter', 0):.2f}", 
                        "差异": f"x{feat_diff.get('jitter_ratio', 0):.2f}",
                        "说明": "Raw - Smooth"
                    }
                ]
                
                table_header = [
                    html.Thead(html.Tr([html.Th(col) for col in ["指标", "录制值", "播放值", "差异", "说明"]]))
                ]
                table_body = [
                    html.Tbody([
                        html.Tr([
                            html.Td(row["指标"], style={'fontWeight': 'bold'}),
                            html.Td(row["录制值"]),
                            html.Td(row["播放值"]),
                            html.Td(row["差异"], style={'color': 'red' if 'x' in row['差异'] and float(row['差异'][1:]) > 2 else 'black'}),
                            html.Td(row["说明"], style={'fontSize': '0.85em', 'color': '#666'})
                        ]) for row in table_data
                    ])
                ]
                
                children.append(html.Div([
                    html.H6("物理特征量化分析", className="mb-3", style={'color': '#2c3e50', 'fontWeight': 'bold'}),
                    dbc.Table(table_header + table_body, bordered=True, hover=True, striped=True, className="mb-4")
                ]))

            
            # 其他信息
            children.append(html.Div([
                    dbc.Row([
                        dbc.Col([
                            html.Small(f"DTW距离: {result.get('dtw_distance', 0):.3f}", 
                                      className="text-muted"),
                            html.Br(),
                            html.Small(f"测试数据: record_index={test_result.get('record_index', 'N/A')}, "
                                      f"replay_index={test_result.get('replay_index', 'N/A')}", 
                                      className="text-muted")
                        ], width=12)
                    ])
                ], className="mb-4")
            )
            
            # 对齐前后对比图
            if comparison_fig:
                children.append(
                    html.Div([
                        html.H6("对齐前后对比", className="mb-3",
                               style={'color': '#2c3e50', 'fontWeight': 'bold'}),
                        dcc.Graph(
                            figure=comparison_fig,
                            style={'height': '800px'}
                        )
                    ], className="mb-4")
                )
            else:
                children.append(
                    html.Div([
                        dbc.Alert("[WARNING] 无法生成对齐对比图", color="warning")
                    ])
                )
            
            return html.Div(children)
            
        except Exception as e:
            logger.error(f"[ERROR] 曲线对齐测试失败: {e}")
            
            logger.error(traceback.format_exc())
            return html.Div([
                dbc.Alert([
                    html.I(className="fas fa-exclamation-triangle me-2"),
                    html.Strong(f"测试失败: {str(e)}")
                ], color="danger")
            ])

    # 丢锤和多锤表格点击回调 - 显示曲线对比（悬浮窗）并支持跳转到瀑布图
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True)],
        [Input({'type': 'drop-hammers-table', 'index': dash.ALL}, 'active_cell'),
         Input({'type': 'multi-hammers-table', 'index': dash.ALL}, 'active_cell'),
         Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State({'type': 'drop-hammers-table', 'index': dash.ALL}, 'data'),
         State({'type': 'multi-hammers-table', 'index': dash.ALL}, 'data'),
         State('session-id', 'data'),
         State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_error_tables_click(active_cells_multi_drop, active_cells_multi_multi, close_modal_clicks, close_btn_clicks,
                                 data_multi_drop, data_multi_multi, session_id, current_style):
        """处理丢锤和多锤表格点击，显示曲线对比（悬浮窗）并支持跳转到瀑布图"""
        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            return current_style, [], no_update

        trigger_id = ctx.triggered[0]['prop_id']
        trigger_value = ctx.triggered[0].get('value')

        # 如果点击了关闭按钮，隐藏模态框
        if trigger_id in ['close-key-curves-modal.n_clicks', 'close-key-curves-modal-btn.n_clicks']:
            return {'display': 'none'}, [], no_update

        # 处理表格点击
        table_type = None
        active_cell = None
        table_data = None
        algorithm_name = None

        # 解析触发源
        if 'drop-hammers-table' in trigger_id:
            table_type = 'drop'
        elif 'multi-hammers-table' in trigger_id:
            table_type = 'multi'

        if not table_type:
            return current_style, [], no_update

        # 获取对应的数据和active_cell
        try:
            # 解析ID
            id_parts = json.loads(trigger_id.split('.')[0])
            algorithm_name = id_parts.get('index', 'single')  # 默认单算法模式

            # 根据表格类型获取对应的数据
            if table_type == 'drop':
                # 找到对应的active_cell和data
                table_index = None
                for i, cell in enumerate(active_cells_multi_drop):
                    if cell is not None:
                        table_index = i
                        active_cell = cell
                        table_data = data_multi_drop[i] if i < len(data_multi_drop) else None
                        break
            else:  # multi
                # 找到对应的active_cell和data
                table_index = None
                for i, cell in enumerate(active_cells_multi_multi):
                    if cell is not None:
                        table_index = i
                        active_cell = cell
                        table_data = data_multi_multi[i] if i < len(data_multi_multi) else None
                        break

        except (json.JSONDecodeError, KeyError, IndexError):
            return current_style, [], no_update

        if not active_cell or not table_data:
            return current_style, [], no_update

        # 获取后端实例
        backend = session_manager.get_backend(session_id)
        if not backend:
            return current_style, [], no_update

        try:
            # 获取点击的行数据
            row_idx = active_cell.get('row')
            if row_idx is None or row_idx >= len(table_data):
                return current_style, [], no_update

            row_data = table_data[row_idx]

            # 获取音符信息
            data_type = row_data.get('data_type')
            key_id_str = row_data.get('keyId')
            global_index = row_data.get('index')

            if key_id_str == '无匹配':
                # 这是没有数据的行，跳过
                return current_style, [], no_update
            
            # 转换key_id为整数
            try:
                key_id = int(key_id_str) if isinstance(key_id_str, (int, float, str)) and str(key_id_str).isdigit() else None
                if key_id is None:
                    logger.warning(f"[WARNING] 无法转换keyId为整数: {key_id_str}")
                    return current_style, [], no_update
            except (ValueError, TypeError):
                logger.warning(f"[WARNING] keyId转换失败: {key_id_str}")
                return current_style, [], no_update

            # 根据表格类型确定数据类型
            if table_type == 'drop':
                # 丢锤：只有录制数据
                available_data = 'record'
                data_label = '录制'
            else:  # multi
                # 多锤：只有播放数据
                available_data = 'replay'
                data_label = '播放'

            # 查找对应的音符数据
            # 对于丢锤/多锤，应该使用initial_valid_record_data/initial_valid_replay_data
            # 并且使用global_index（即表格中的index字段）作为数组索引
            note_data = None
            
            # 确保global_index是整数类型
            try:
                if isinstance(global_index, str):
                    # 如果是字符串，尝试转换
                    if global_index == '无匹配':
                        return current_style, [], no_update
                    global_index = int(global_index)
            except (ValueError, TypeError):
                logger.warning(f"[WARNING] 无法转换global_index: {global_index}")
                return current_style, [], no_update
            
            if algorithm_name == 'single':
                # 单算法模式
                if available_data == 'record':
                    # 丢锤：使用initial_valid_record_data
                    initial_data = getattr(backend.analyzer, 'initial_valid_record_data', None)
                else:
                    # 多锤：使用initial_valid_replay_data
                    initial_data = getattr(backend.analyzer, 'initial_valid_replay_data', None)

                if initial_data:
                    # 优先通过key_id查找音符数据，确保与表格显示一致
                    logger.info(f"[DEBUG] 单算法模式通过key_id查找音符数据: {key_id}")
                    for i, note in enumerate(initial_data):
                        if getattr(note, 'id', None) == key_id:
                            note_data = note
                            logger.info(f"[DEBUG] 单算法模式通过key_id查找成功: 索引{i}, key_id={key_id}")
                            break

                    # 如果通过key_id没找到，降级使用索引查找（向后兼容）
                    if not note_data and 0 <= global_index < len(initial_data):
                        candidate_note = initial_data[global_index]
                        candidate_key_id = getattr(candidate_note, 'id', None)
                        if candidate_key_id == key_id:
                            # 索引查找成功且key_id匹配
                            note_data = candidate_note
                            logger.info(f"[DEBUG] 单算法模式索引查找成功且key_id匹配: global_index={global_index}, key_id={key_id}")
                        else:
                            logger.warning(f"[WARNING] 单算法模式索引位置的key_id不匹配: 期望{key_id}, 实际{candidate_key_id}, 跳过绘制")
            else:
                # 多算法模式
                active_algorithms = backend.get_active_algorithms()
                logger.info(f"[DEBUG] 多算法模式查找 - 算法名称: {algorithm_name}, 活动算法数量: {len(active_algorithms)}")
                logger.info(f"[DEBUG] 活动算法列表: {[f'{alg.metadata.algorithm_name}(active={alg.is_active}, ready={alg.is_ready()})' for alg in active_algorithms]}")

                # 首先尝试在活动算法中查找
                target_algorithm = next((alg for alg in active_algorithms if alg.metadata.algorithm_name == algorithm_name), None)

                # 如果在活动算法中没找到，尝试在所有算法中查找（可能有未激活的算法）
                if not target_algorithm:
                    all_algorithms = backend.multi_algorithm_manager.algorithms.values() if backend.multi_algorithm_manager else []
                    target_algorithm = next((alg for alg in all_algorithms if alg.metadata.algorithm_name == algorithm_name), None)
                    if target_algorithm:
                        logger.warning(f"[WARNING] 在非活动算法中找到目标算法: {algorithm_name}, 激活状态: {target_algorithm.is_active}")
                    else:
                        logger.error(f"[ERROR] 在所有算法中都未找到目标算法: {algorithm_name}")
                        all_names = [alg.metadata.algorithm_name for alg in all_algorithms] if all_algorithms else []
                        logger.error(f"[ERROR] 所有可用算法: {all_names}")

                if not target_algorithm:
                    logger.error(f"[ERROR] 未找到匹配的算法实例: {algorithm_name}")
                    logger.error(f"[ERROR] 可用算法: {[alg.metadata.algorithm_name for alg in active_algorithms]}")
                    return current_style, [], no_update

                if not target_algorithm.analyzer:
                    logger.error(f"[ERROR] 目标算法没有分析器: {algorithm_name}")
                    return current_style, [], no_update

                logger.info(f"[DEBUG] 找到目标算法: {target_algorithm.metadata.algorithm_name}")

                # 尝试通过索引直接查找音符数据
                note_data = None
                initial_data = None

                if available_data == 'record':
                    # 丢锤：使用initial_valid_record_data
                    initial_data = getattr(target_algorithm.analyzer, 'initial_valid_record_data', None)
                    data_type_name = "initial_valid_record_data"
                else:
                    # 多锤：使用initial_valid_replay_data
                    initial_data = getattr(target_algorithm.analyzer, 'initial_valid_replay_data', None)
                    data_type_name = "initial_valid_replay_data"

                logger.info(f"[DEBUG] {data_type_name} - 数据长度: {len(initial_data) if initial_data else 0}, 索引: {global_index}")

                if initial_data:
                    # 优先通过key_id查找音符数据，确保与表格显示一致
                    logger.info(f"[DEBUG] 通过key_id查找音符数据: {key_id}")
                    for i, note in enumerate(initial_data):
                        if getattr(note, 'id', None) == key_id:
                            note_data = note
                            logger.info(f"[DEBUG] 通过key_id查找成功: 索引{i}, key_id={key_id}")
                            break

                    # 如果通过key_id没找到，降级使用索引查找（向后兼容）
                    if not note_data and 0 <= global_index < len(initial_data):
                        candidate_note = initial_data[global_index]
                        candidate_key_id = getattr(candidate_note, 'id', None)
                        if candidate_key_id == key_id:
                            # 索引查找成功且key_id匹配
                            note_data = candidate_note
                            logger.info(f"[DEBUG] 索引查找成功且key_id匹配: global_index={global_index}, key_id={key_id}")
                        else:
                            logger.warning(f"[WARNING] 索引位置的key_id不匹配: 期望{key_id}, 实际{candidate_key_id}, 跳过绘制")

                    if not note_data:
                        logger.error(f"[ERROR] 无法找到匹配的音符数据: key_id={key_id}, 索引={global_index}, 数据长度={len(initial_data)}")
                        return current_style, [], no_update
                else:
                    logger.error(f"[ERROR] 没有找到{data_type_name}数据")
                    return current_style, [], no_update

            if not note_data:
                return current_style, [], no_update

            # 确保key_id与note_data中的id一致
            actual_key_id = getattr(note_data, 'id', key_id)
            if actual_key_id != key_id:
                logger.info(f"🔍 key_id不一致: 表格中={key_id}, note_data中={actual_key_id}, 使用note_data中的值")
                key_id = actual_key_id

            # 生成曲线图（只显示有数据的部分）
            fig = _create_single_data_curve_figure(note_data, key_id, data_label, algorithm_name)

            # 计算时间信息，用于跳转到瀑布图
            center_time_ms = None
            record_idx = None
            replay_idx = None
            
            try:
                # 对于丢锤：只有录制数据，record_idx就是global_index（在initial_valid_record_data中的索引）
                # 对于多锤：只有播放数据，replay_idx就是global_index（在initial_valid_replay_data中的索引）
                if table_type == 'drop':
                    # 丢锤：只有录制数据
                    record_idx = global_index  # 在initial_valid_record_data中的索引
                    replay_idx = None  # 丢锤没有播放数据
                    
                    # 从表格数据中获取keyOn时间（已经是ms单位）
                    try:
                        key_on_str = row_data.get('keyOn', '')
                        if key_on_str and key_on_str != '无匹配':
                            center_time_ms = float(key_on_str)
                        else:
                            # 备用方案：从note_data计算
                            if note_data and hasattr(note_data, 'after_touch') and not note_data.after_touch.empty:
                                center_time_ms = (note_data.after_touch.index[0] + note_data.offset) / 10.0
                            elif note_data and hasattr(note_data, 'hammers') and not note_data.hammers.empty:
                                center_time_ms = (note_data.hammers.index[0] + note_data.offset) / 10.0
                            elif note_data and hasattr(note_data, 'offset'):
                                center_time_ms = note_data.offset / 10.0
                    except (ValueError, TypeError):
                        # 如果转换失败，使用备用方案
                        if note_data and hasattr(note_data, 'after_touch') and not note_data.after_touch.empty:
                            center_time_ms = (note_data.after_touch.index[0] + note_data.offset) / 10.0
                        elif note_data and hasattr(note_data, 'hammers') and not note_data.hammers.empty:
                            center_time_ms = (note_data.hammers.index[0] + note_data.offset) / 10.0
                        elif note_data and hasattr(note_data, 'offset'):
                            center_time_ms = note_data.offset / 10.0
                else:  # multi
                    # 多锤：只有播放数据
                    record_idx = None  # 多锤没有录制数据
                    replay_idx = global_index  # 在initial_valid_replay_data中的索引
                    
                    # 从表格数据中获取keyOn时间（已经是ms单位）
                    try:
                        key_on_str = row_data.get('keyOn', '')
                        if key_on_str and key_on_str != '无匹配':
                            center_time_ms = float(key_on_str)
                        else:
                            # 备用方案：从note_data计算
                            if note_data and hasattr(note_data, 'after_touch') and not note_data.after_touch.empty:
                                center_time_ms = (note_data.after_touch.index[0] + note_data.offset) / 10.0
                            elif note_data and hasattr(note_data, 'hammers') and not note_data.hammers.empty:
                                center_time_ms = (note_data.hammers.index[0] + note_data.offset) / 10.0
                            elif note_data and hasattr(note_data, 'offset'):
                                center_time_ms = note_data.offset / 10.0
                    except (ValueError, TypeError):
                        # 如果转换失败，使用备用方案
                        if note_data and hasattr(note_data, 'after_touch') and not note_data.after_touch.empty:
                            center_time_ms = (note_data.after_touch.index[0] + note_data.offset) / 10.0
                        elif note_data and hasattr(note_data, 'hammers') and not note_data.hammers.empty:
                            center_time_ms = (note_data.hammers.index[0] + note_data.offset) / 10.0
                        elif note_data and hasattr(note_data, 'offset'):
                            center_time_ms = note_data.offset / 10.0
            except Exception as e:
                logger.warning(f"[WARNING] 计算时间信息失败: {e}")
                logger.error(traceback.format_exc())

            # 准备跳转信息
            clicked_info = {
                'key_id': key_id,
                'algorithm_name': algorithm_name,
                'data_type': data_type,
                'global_index': global_index,
                'available_data': available_data,  # 标记有哪些数据可用
                'source_plot_id': f'error-table-{table_type}',  # 标识来源是错误表格
                'record_idx': record_idx,  # 录制数据索引
                'replay_idx': replay_idx,  # 播放数据索引
                'center_time_ms': center_time_ms  # 预先计算的时间信息
            }

            # 显示模态框 - 使用与其他回调函数一致的样式，避免嵌套
            modal_style = {
                'display': 'block',
                'position': 'fixed',
                'zIndex': '9999',
                'left': '0',
                'top': '0',
                'width': '100%',
                'height': '100%',
                'backgroundColor': 'rgba(0,0,0,0.6)',
                'backdropFilter': 'blur(5px)'
            }

            # 直接返回图形，不添加额外的容器包裹，避免多余的框
            return modal_style, [dcc.Graph(figure=fig, style={'height': '500px'})], clicked_info

        except Exception as e:
            logger.error(f"[ERROR] 处理错误表格点击失败: {e}")
            return current_style, [], no_update

    def _create_single_data_curve_figure(note_data, key_id, data_label, algorithm_name):
        """创建只显示单侧数据的曲线图"""
        from plotly.subplots import make_subplots

        try:
            # 创建子图
            fig = make_subplots(
                rows=1, cols=1,
                subplot_titles=[f'按键 {key_id} - {data_label}数据曲线 ({algorithm_name})']
            )

            # 提取数据
            if hasattr(note_data, 'after_touch') and note_data.after_touch is not None and len(note_data.after_touch.index) > 0:
                # 使用after_touch数据
                time_data = note_data.after_touch.index
                value_data = note_data.after_touch.values if hasattr(note_data.after_touch, 'values') else [0] * len(time_data)
            elif hasattr(note_data, 'hammers') and note_data.hammers is not None and len(note_data.hammers.index) > 0:
                # 使用hammers数据
                time_data = note_data.hammers.index
                value_data = note_data.hammers.values if hasattr(note_data.hammers, 'values') else [0] * len(time_data)
            else:
                # 没有可用数据
                fig.add_annotation(
                    text="无可用数据",
                    xref="paper", yref="paper",
                    x=0.5, y=0.5,
                    showarrow=False
                )
                return fig

            # 转换为毫秒
            time_ms = [t / 10.0 for t in time_data]

            # 添加曲线
            fig.add_trace(
                go.Scatter(
                    x=time_ms,
                    y=value_data,
                    mode='lines+markers',
                    name=f'{data_label}数据',
                    line=dict(color='blue', width=2),
                    marker=dict(size=6, color='blue')
                ),
                row=1, col=1
            )

            # 更新布局
            fig.update_layout(
                height=400,
                showlegend=True,
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                ),
                hovermode='x unified'
            )

            # 更新坐标轴标签
            fig.update_xaxes(title_text="时间 (ms)", row=1, col=1)
            fig.update_yaxes(title_text="触后值", row=1, col=1)

            return fig

        except Exception as e:
            logger.error(f"[ERROR] 创建单侧数据曲线图失败: {e}")
            # 返回错误图表
            error_fig = go.Figure()
            error_fig.add_annotation(
                text=f"生成曲线图失败: {str(e)}",
                xref="paper", yref="paper",
                x=0.5, y=0.5,
                showarrow=False
            )
            return error_fig

    # 单算法模式错误表格数据填充回调
    # 注册评级统计详情回调
    register_all_callbacks(app, session_manager)


