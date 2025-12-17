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
from grade_detail_callbacks import register_all_callbacks
from utils.logger import Logger
# 后端类型导入
from backend.piano_analysis_backend import PianoAnalysisBackend



logger = Logger.get_logger()

# 自定义类型定义
class VelocityDataItem(TypedDict):
    """锤速数据项的类型定义"""
    algorithm_name: str
    display_name: str
    filename: str  # 添加文件名以区分同种算法的不同文件
    key_id: int
    record_index: int  # 录制音符在matched_pairs中的索引
    replay_index: int  # 播放音符在matched_pairs中的索引
    record_velocity: float
    replay_velocity: float
    velocity_diff: float
    record_hammer_time_ms: float  # 录制第一个锤子时间（毫秒）
    replay_hammer_time_ms: float  # 播放第一个锤子时间（毫秒）

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

class ZScoreClickData(TypedDict):
    """Z-Score散点图点击数据的类型定义"""
    record_index: int
    replay_index: int
    key_id: Optional[int]
    algorithm_name: str

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

    # 创建瀑布图跳转处理器实例
    waterfall_jump_handler = WaterfallJumpHandler(session_manager)

    # 创建延时时间序列图处理器实例
    delay_time_series_handler = DelayTimeSeriesHandler(session_manager)

    # 创建相对延时分布图处理器实例
    relative_delay_distribution_handler = RelativeDelayDistributionHandler(session_manager)

    # 初始化回调：自动启用多算法模式
    @app.callback(
        Output('session-id', 'data'),
        Input('session-id', 'data'),
        prevent_initial_call=False
    )
    def init_session_and_enable_multi_algorithm(session_data):
        """初始化会话ID并自动启用多算法模式"""
        if session_data is None:
            session_id = str(uuid.uuid4())
        else:
            session_id = session_data
        
        # 多算法模式始终启用
        session_id, backend = session_manager.get_or_create_backend(session_id)
        if backend:
            # 确保multi_algorithm_manager已初始化
            if not backend.multi_algorithm_manager:
                backend._ensure_multi_algorithm_manager()
            logger.info("[OK] 多算法模式已就绪")
        
        return session_id

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
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update, no_update, no_update, no_update
        
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
            logger.warning(f"[WARNING] 初始化时间滑块失败: {e}")
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
            # 检查数据库功能是否已禁用
            if hasattr(history_manager, 'disable_database') and history_manager.disable_database:
                disabled_option = {
                    'label': '⚠️ 数据库功能已禁用',
                    'value': 'disabled',
                    'disabled': True
                }
                initialize_history_dropdown._initialized = True
                return [disabled_option], None

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

            logger.info(f"[OK] 初始化历史记录下拉菜单，找到 {len(options)} 条记录")
            initialize_history_dropdown._initialized = True
            return options, None  # 返回选项列表，但不预选任何项

        except Exception as e:
            logger.error(f"[ERROR] 初始化历史记录下拉框失败: {e}")
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
            # 检查数据库功能是否已禁用
            if hasattr(history_manager, 'disable_database') and history_manager.disable_database:
                return [{
                    'label': '⚠️ 数据库功能已禁用',
                    'value': 'disabled',
                    'disabled': True
                }]

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
            logger.error(f"[ERROR] 更新历史记录下拉框失败: {e}")
            return []


    def _validate_zscore_click_data(zscore_scatter_clickData: Dict[str, Any], backend: PianoAnalysisBackend) -> Optional[Dict[str, Any]]:
        """
        验证Z-Score散点图点击数据

        Args:
            zscore_scatter_clickData: 点击数据
            backend: 后端实例

        Returns:
            Optional[Dict[str, Any]]: 验证通过的点击点数据，失败返回None
        """
        if 'points' not in zscore_scatter_clickData or len(zscore_scatter_clickData['points']) == 0:
            logger.warning("[WARNING] Z-Score标准化散点图点击回调 - zscore_scatter_clickData无效或没有points")
            return None

        point = zscore_scatter_clickData['points'][0]
        logger.info(f"🔍 Z-Score标准化散点图点击 - 点击点数据: {point}")

        if not point.get('customdata'):
            logger.warning("[WARNING] Z-Score标准化散点图点击 - 点没有customdata")
            return None

        return point

    def _extract_zscore_customdata(raw_customdata: Any) -> Optional[ZScoreClickData]:
        """
        提取和验证Z-Score散点图的customdata

        Args:
            raw_customdata: 原始customdata

        Returns:
            Optional[ZScoreClickData]: 提取的点击数据，失败返回None
        """
        logger.info(f"🔍 Z-Score标准化散点图点击 - raw_customdata类型: {type(raw_customdata)}, 值: {raw_customdata}")

        if isinstance(raw_customdata, list) and len(raw_customdata) > 0:
            customdata = raw_customdata[0] if isinstance(raw_customdata[0], list) else raw_customdata
        else:
            customdata = raw_customdata

        if not isinstance(customdata, list):
            logger.warning(f"[WARNING] Z-Score标准化散点图点击 - customdata不是列表类型: {type(customdata)}, 值: {customdata}")
            return None

        logger.info(f"🔍 Z-Score标准化散点图点击 - customdata: {customdata}, 长度: {len(customdata)}")

        if len(customdata) < 5:
            logger.warning(f"[WARNING] Z-Score标准化散点图点击 - customdata长度不足: {len(customdata)}")
            return None

        # Z-Score散点图的customdata格式: [record_index, replay_index, key_id_int, delay_ms, algorithm_name]
        record_index = customdata[0]
        replay_index = customdata[1]
        key_id = customdata[2] if len(customdata) > 2 else None
        algorithm_name = customdata[4]

        logger.info(f"🖱️ Z-Score标准化散点图点击: 算法={algorithm_name}, record_index={record_index}, replay_index={replay_index}, key_id={key_id}")

        return {
            'record_index': record_index,
            'replay_index': replay_index,
            'key_id': key_id,
            'algorithm_name': algorithm_name
        }

    def _get_algorithm_for_zscore(backend: PianoAnalysisBackend, algorithm_name: str) -> Optional[Any]:
        """
        获取Z-Score分析的算法实例

        Args:
            backend: 后端实例
            algorithm_name: 算法名称

        Returns:
            Optional[Any]: 算法实例，获取失败返回None
        """
        if not algorithm_name or not backend.multi_algorithm_mode or not backend.multi_algorithm_manager:
            return None

        algorithm = backend.multi_algorithm_manager.get_algorithm(algorithm_name)
        if not algorithm or not algorithm.analyzer or not algorithm.analyzer.note_matcher:
            return None

        return algorithm

    def _get_time_from_offset_data(note_matcher: Any, record_index: int, replay_index: int) -> Optional[Tuple[float, float]]:
        """
        从预计算的offset_data中获取时间信息

        Args:
            note_matcher: 音符匹配器实例
            record_index: 录制音符索引
            replay_index: 播放音符索引

        Returns:
            Optional[Tuple[float, float]]: (record_keyon, replay_keyon)，获取失败返回None
        """
        try:
            offset_data = note_matcher.get_offset_alignment_data()
            if not offset_data:
                return None

            for item in offset_data:
                if item.get('record_index') == record_index and item.get('replay_index') == replay_index:
                    record_keyon = item.get('record_keyon', 0)
                    replay_keyon = item.get('replay_keyon', 0)
                    if record_keyon and replay_keyon:
                        return record_keyon, replay_keyon
            return None
        except Exception:
            return None

    def _calculate_time_from_notes(matched_pairs: List, record_index: int, replay_index: int) -> Optional[Tuple[float, float]]:
        """
        从matched_pairs中的音符直接计算时间信息

        Args:
            matched_pairs: 匹配对列表
            record_index: 录制音符索引
            replay_index: 播放音符索引

        Returns:
            Optional[Tuple[float, float]]: (record_keyon, replay_keyon)，计算失败返回None
        """
        try:
            for r_idx, p_idx, r_note, p_note in matched_pairs:
                if r_idx == record_index and p_idx == replay_index:
                    record_keyon = r_note.after_touch.index[0] + r_note.offset if hasattr(r_note, 'after_touch') and not r_note.after_touch.empty else r_note.offset
                    replay_keyon = p_note.after_touch.index[0] + p_note.offset if hasattr(p_note, 'after_touch') and not p_note.after_touch.empty else p_note.offset
                    return record_keyon, replay_keyon
            return None
        except Exception:
            return None

    def _calculate_center_time_ms(record_keyon: float, replay_keyon: float) -> float:
        """
        计算中心时间并转换为毫秒

        Args:
            record_keyon: 录制音符开始时间（0.1ms单位）
            replay_keyon: 播放音符开始时间（0.1ms单位）

        Returns:
            float: 中心时间（毫秒）
        """
        return ((record_keyon + replay_keyon) / 2.0) / 10.0

    def _calculate_zscore_center_time(backend: PianoAnalysisBackend, click_data: ZScoreClickData) -> Optional[float]:
        """
        计算Z-Score散点图点击的中心时间

        Args:
            backend: 后端实例
            click_data: 点击数据

        Returns:
            Optional[float]: 中心时间（毫秒），计算失败返回None
        """
        try:
            # 获取算法实例
            algorithm = _get_algorithm_for_zscore(backend, click_data['algorithm_name'])
            if not algorithm:
                return None

            record_index = click_data['record_index']
            replay_index = click_data['replay_index']

            # 优先从预计算的 offset_data 中获取时间信息
            keyon_times = _get_time_from_offset_data(algorithm.analyzer.note_matcher, record_index, replay_index)
            if keyon_times:
                record_keyon, replay_keyon = keyon_times
                return _calculate_center_time_ms(record_keyon, replay_keyon)

            # 如果 offset_data 中没有找到，降级到直接从音符计算
            keyon_times = _calculate_time_from_notes(algorithm.analyzer.matched_pairs, record_index, replay_index)
            if keyon_times:
                record_keyon, replay_keyon = keyon_times
                return _calculate_center_time_ms(record_keyon, replay_keyon)

            return None

        except Exception as e:
            logger.warning(f"[WARNING] 计算时间信息失败: {e}")
            return None

    def _generate_zscore_detail_plots(backend: PianoAnalysisBackend, click_data: ZScoreClickData) -> Tuple[Any, Any, Any]:
        """
        生成Z-Score散点图点击的详细曲线图

        Args:
            backend: 后端实例
            click_data: 点击数据

        Returns:
            Tuple[Any, Any, Any]: (录制图, 播放图, 对比图)
        """
        detail_figure1, detail_figure2, detail_figure_combined = backend.generate_multi_algorithm_scatter_detail_plot_by_indices(
            algorithm_name=click_data['algorithm_name'],
            record_index=click_data['record_index'],
            replay_index=click_data['replay_index']
        )

        logger.info(f"🔍 Z-Score标准化散点图点击回调 - 图表生成结果: figure1={detail_figure1 is not None}, figure2={detail_figure2 is not None}, figure_combined={detail_figure_combined is not None}")

        return detail_figure1, detail_figure2, detail_figure_combined

    def _create_zscore_modal_response(detail_figure_combined: Any, point_info: Dict[str, Any]) -> Tuple[Dict[str, Any], Any, Dict[str, Any]]:
        """
        创建Z-Score散点图的模态框响应

        Args:
            detail_figure_combined: 对比曲线图
            point_info: 点信息

        Returns:
            Tuple[Dict[str, Any], Any, Dict[str, Any]]: (模态框样式, 图表组件, 点信息)
        """
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

        logger.info("[OK] Z-Score标准化散点图点击回调 - 返回模态框和图表")
        return modal_style, dcc.Graph(figure=detail_figure_combined, style={'height': '600px'}), point_info

    def _handle_zscore_modal_close() -> Tuple[Dict[str, Any], List[Any], NoUpdate]:
        """处理Z-Score模态框关闭逻辑"""
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

    def _handle_zscore_plot_click(zscore_scatter_clickData: Optional[Dict[str, Any]], session_id: str, current_style: Dict[str, Any], source_plot_id: str = 'key-delay-zscore-scatter-plot') -> Tuple[Dict[str, Any], List[Any], Union[Dict[str, Any], NoUpdate]]:
        """处理Z-Score散点图点击的主要逻辑"""
        logger.info(f"🔍 散点图点击回调被触发 - source_plot_id: {source_plot_id}, clickData: {zscore_scatter_clickData is not None}")

        backend = session_manager.get_backend(session_id)
        if not backend:
            logger.warning("[WARNING] 没有找到backend")
            return current_style, [], no_update

        # 验证点击数据
        point = _validate_zscore_click_data(zscore_scatter_clickData, backend)
        if not point:
            return current_style, [], no_update

        # 提取customdata
        click_data = _extract_zscore_customdata(point['customdata'])
        if not click_data:
            return current_style, [], no_update

        # 计算中心时间
        center_time_ms = _calculate_zscore_center_time(backend, click_data)

        # 存储当前点击的数据点信息，用于跳转按钮
        point_info = {
            'algorithm_name': click_data['algorithm_name'],
            'record_idx': click_data['record_index'],
            'replay_idx': click_data['replay_index'],
            'key_id': click_data['key_id'],
            'source_plot_id': source_plot_id,  # 记录来源图表ID
            'center_time_ms': center_time_ms  # 预先计算的时间信息
        }

        # 生成详细曲线图
        detail_figure1, detail_figure2, detail_figure_combined = _generate_zscore_detail_plots(backend, click_data)

        # 检查图表生成是否成功
        if detail_figure1 and detail_figure2 and detail_figure_combined:
            modal_style, graph_component, point_info_response = _create_zscore_modal_response(detail_figure_combined, point_info)
            return modal_style, graph_component, point_info_response
        else:
            logger.warning("[WARNING] Z-Score标准化散点图点击回调 - 图表生成失败，部分图表为None")
            return current_style, [], no_update

    # Z-Score标准化散点图点击回调
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True),
         Output('key-delay-zscore-scatter-plot', 'clickData', allow_duplicate=True)],
        [Input('key-delay-zscore-scatter-plot', 'clickData'),
         Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State('session-id', 'data'),
         State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_zscore_scatter_click(zscore_scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理Z-Score标准化散点图点击，显示曲线对比（悬浮窗）并支持跳转到瀑布图"""
        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            logger.debug("[WARNING] Z-Score散点图点击回调：没有触发源")
            return current_style, [], no_update, no_update

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        logger.info(f"[PROCESS] Z-Score散点图点击回调触发：trigger_id={trigger_id}")

        # 如果点击了关闭按钮，隐藏模态框
        if trigger_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            result = _handle_zscore_modal_close()
            return result[0], result[1], result[2], None

        # 如果是Z-Score散点图点击
        if trigger_id == 'key-delay-zscore-scatter-plot' and zscore_scatter_clickData:
            result = _handle_zscore_plot_click(zscore_scatter_clickData, session_id, current_style, 'key-delay-zscore-scatter-plot')
            return result[0], result[1], result[2], no_update

        # 其他情况，返回默认值
        return current_style, [], no_update, no_update

    # 按键与相对延时散点图点击回调
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True),
         Output('key-delay-scatter-plot', 'clickData', allow_duplicate=True)],
        [Input('key-delay-scatter-plot', 'clickData'),
         Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State('session-id', 'data'),
         State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_key_delay_scatter_click(scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理按键与相对延时散点图点击，显示曲线对比（悬浮窗）并支持跳转到瀑布图"""
        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            logger.debug("[WARNING] 按键与相对延时散点图点击回调：没有触发源")
            return current_style, [], no_update, no_update

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        logger.info(f"[PROCESS] 按键与相对延时散点图点击回调触发：trigger_id={trigger_id}")

        # 如果点击了关闭按钮，隐藏模态框
        if trigger_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            result = _handle_zscore_modal_close()
            return result[0], result[1], result[2], None

        # 如果是按键与相对延时散点图点击
        if trigger_id == 'key-delay-scatter-plot' and scatter_clickData:
            # 复用 Z-Score 图表的点击处理逻辑，因为 customdata 格式应该是一样的
            result = _handle_zscore_plot_click(scatter_clickData, session_id, current_style, 'key-delay-scatter-plot')
            return result[0], result[1], result[2], no_update

        # 其他情况，返回默认值
        return current_style, [], no_update, no_update

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
                logger.warning("[WARNING] 没有激活的算法，无法生成偏移对齐分析")
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

    # 统一的按键与相对延时散点图回调函数 - 根据触发源和模式智能响应
    @app.callback(
        Output('key-delay-scatter-plot', 'figure'),
        [Input('report-content', 'children'),
         Input({'type': 'key-delay-scatter-common-keys-only', 'index': ALL}, 'value'),
         Input({'type': 'key-delay-scatter-algorithm-selector', 'index': ALL}, 'value')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_key_delay_scatter_plot_unified(report_content, common_keys_filter_values, algorithm_selector_values, session_id):
        """统一的按键与相对延时散点图回调函数 - 根据触发源和当前模式智能响应"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update

        # 解析 Pattern Matching Inputs
        # 如果组件不存在，列表为空；如果存在，列表包含一个值
        common_keys_filter = common_keys_filter_values[0] if common_keys_filter_values else False
        algorithm_selector = algorithm_selector_values[0] if algorithm_selector_values else []

        # 获取回调上下文，判断触发源
        ctx = dash.callback_context
        if not ctx.triggered:
            return no_update

        triggered_id_str = ctx.triggered[0]['prop_id'].split('.')[0]
        
        # 解析触发源ID类型
        triggered_type = None
        if '{' in triggered_id_str:
            try:
                # 简单判断是否为我们的筛选组件
                if 'key-delay-scatter-common-keys-only' in triggered_id_str:
                    triggered_type = 'filter_change'
                elif 'key-delay-scatter-algorithm-selector' in triggered_id_str:
                    triggered_type = 'filter_change'
                else:
                    triggered_type = 'other'
            except:
                triggered_type = 'other'
        else:
            triggered_type = 'report-content' if triggered_id_str == 'report-content' else 'other'

        try:
            # 判断当前是单算法模式还是多算法模式
            is_multi_algorithm_mode = hasattr(backend, 'multi_algorithm_mode') and backend.multi_algorithm_mode
            has_analyzer = bool(backend.analyzer)

            # 单算法模式：只响应 report-content 变化
            if not is_multi_algorithm_mode and has_analyzer:
                if triggered_type == 'report-content':
                    fig = backend.generate_key_delay_scatter_plot(
                        only_common_keys=False,
                        selected_algorithm_names=[]
                    )
                    logger.info("[OK] 单算法模式按键与相对延时散点图生成成功")
                    return fig
                else:
                    # 单算法模式不响应筛选控件变化
                    return no_update

            # 多算法模式：响应所有变化
            elif is_multi_algorithm_mode:
                # 处理筛选控件值
                only_common_keys = bool(common_keys_filter) if common_keys_filter is not None else False
                selected_algorithms = algorithm_selector if algorithm_selector is not None else []

                fig = backend.generate_key_delay_scatter_plot(
                    only_common_keys=only_common_keys,
                    selected_algorithm_names=selected_algorithms
                )

                if triggered_type == 'report-content':
                    logger.info("[OK] 多算法模式按键与相对延时散点图数据加载成功")
                else:
                    logger.info("[OK] 多算法模式按键与相对延时散点图筛选更新成功")
                return fig

            # 其他情况：无分析器，不响应
            else:
                logger.warning("[WARNING] 没有有效的分析器，无法生成按键与相对延时散点图")
                return no_update

        except Exception as e:
            error_msg = f"按键与相对延时散点图处理失败: {str(e)}"
            logger.error(f"[ERROR] {error_msg}")
            logger.error(traceback.format_exc())

            if backend:
                empty = backend.plot_generator._create_empty_plot(error_msg)
                return empty
            else:
                return no_update

    # 按键与延时Z-Score标准化散点图自动生成回调函数 - 当报告内容加载时自动生成
    @app.callback(
        Output('key-delay-zscore-scatter-plot', 'figure'),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_generate_scatter_plot(report_content, session_id):
        """处理按键与延时Z-Score标准化散点图自动生成 - 当报告内容更新时触发"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update
        
        try:
            # 检查是否有分析数据
            if not backend.analyzer and not (hasattr(backend, 'multi_algorithm_mode') and backend.multi_algorithm_mode):
                logger.warning("[WARNING] 没有分析器，无法生成Z-Score标准化散点图")
                empty = backend.plot_generator._create_empty_plot("没有分析器")
                return empty
            
            # 生成Z-Score标准化散点图
            zscore_fig = backend.generate_key_delay_zscore_scatter_plot()
            
            # 验证Z-Score图表是否正确生成
            if zscore_fig and hasattr(zscore_fig, 'data') and len(zscore_fig.data) > 0:
                # 检查第一个数据点的y值是否是Z-Score（应该在-3到3之间，而不是原始的延时值）
                first_trace = zscore_fig.data[0]
                if hasattr(first_trace, 'y') and len(first_trace.y) > 0:
                    first_y = first_trace.y[0] if hasattr(first_trace.y, '__getitem__') else first_trace.y
                    logger.info(f"🔍 Z-Score图表验证: 第一个数据点的y值={first_y} (应该是Z-Score值，通常在-3到3之间)")
            
            logger.info("[OK] 按键与延时Z-Score标准化散点图生成成功")
            return zscore_fig
            
        except Exception as e:
            logger.error(f"[ERROR] 生成Z-Score标准化散点图失败: {e}")
            logger.error(traceback.format_exc())
            empty = backend.plot_generator._create_empty_plot(f"生成Z-Score标准化散点图失败: {str(e)}")
            return empty


    # 锤速与延时散点图自动生成回调函数 - 当报告内容加载时自动生成
    @app.callback(
        Output('hammer-velocity-delay-scatter-plot', 'figure'),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_generate_hammer_velocity_scatter_plot(report_content, session_id):
        """处理锤速与延时散点图自动生成 - 当报告内容更新时触发"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update
        
        try:
            # 检查是否有激活的算法
            active_algorithms = backend.get_active_algorithms()
            if not active_algorithms:
                logger.warning("[WARNING] 没有激活的算法，无法生成散点图")
                return backend.plot_generator._create_empty_plot("没有激活的算法")
            
            # 生成锤速与延时散点图
            fig = backend.generate_hammer_velocity_delay_scatter_plot()
            
            logger.info("[OK] 锤速与延时散点图生成成功")
            return fig
            
        except Exception as e:
            logger.error(f"[ERROR] 生成散点图失败: {e}")
            logger.error(traceback.format_exc())
            
            return backend.plot_generator._create_empty_plot(f"生成散点图失败: {str(e)}")

    # 锤速对比图自动生成回调函数 - 当报告内容加载时自动生成
    @app.callback(
        Output('hammer-velocity-comparison-plot', 'figure'),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_generate_hammer_velocity_comparison_plot(report_content: html.Div, session_id: str) -> Figure:
        """
        处理锤速对比图自动生成 - 当报告内容更新时触发

        该函数生成一个散点图，显示不同算法（曲子）下各按键的锤速差值对比。
        横轴为按键ID，纵轴为锤速差值（播放锤速 - 录制锤速）。
        每个数据点代表一个具体的按键-算法组合，颜色区分不同算法。

        Args:
            report_content: 报告内容（触发器）
            session_id: 会话ID，用于获取后端实例

        Returns:
            plotly图表对象或空图表（当无数据或错误时）
        """
        backend = session_manager.get_backend(session_id)
        if not backend:
            return go.Figure()  # 返回空图表而不是 no_update

        try:
            # 验证环境条件
            if not _validate_velocity_comparison_prerequisites(backend):
                return go.Figure()  # 返回空图表

            # 收集锤速数据
            velocity_data = _collect_velocity_comparison_data(backend)
            if not velocity_data:
                return go.Figure()  # 返回空图表

            # 生成对比图表
            fig = _create_velocity_comparison_plot(velocity_data)
            return fig.figure if hasattr(fig, 'figure') else fig

        except Exception as e:
            logger.error(f"[ERROR] 生成锤速对比图失败: {e}")
            logger.error(traceback.format_exc())
            return go.Figure()  # 返回空图表

    def _validate_velocity_comparison_prerequisites(backend: PianoAnalysisBackend) -> bool:
        """
        验证生成锤速对比图的必要前提条件

        Args:
            backend: 后端实例

        Returns:
            bool: 是否满足生成条件
        """
        if not backend.multi_algorithm_mode or not backend.multi_algorithm_manager:
            logger.warning("[WARNING] 未启用多算法模式，无法生成锤速对比图")
            return False

        active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()
        if not active_algorithms:
            logger.warning("[WARNING] 没有激活的算法，无法生成锤速对比图")
            return False

        return True

    def _collect_velocity_comparison_data(backend: PianoAnalysisBackend) -> List[VelocityDataItem]:
        """
        从所有激活算法中收集锤速对比数据

        遍历每个算法，提取匹配对中的锤速信息，计算差值。

        Args:
            backend: 后端实例

        Returns:
            List[VelocityDataItem]: 锤速数据列表，每个元素包含完整的锤速信息
        """
        active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()
        all_velocity_data = []

        logger.info(f"[DEBUG] 开始收集锤速对比数据，激活算法数量: {len(active_algorithms)}")

        for algorithm in active_algorithms:
            if not algorithm.is_ready():
                logger.info(f"[DEBUG] 算法 {algorithm.metadata.algorithm_name} 未就绪，跳过")
                continue

            logger.info(f"[DEBUG] 处理算法: {algorithm.metadata.algorithm_name} ({algorithm.metadata.display_name})")

            # 从单个算法提取数据
            algorithm_velocity_data = _extract_single_algorithm_velocity_data(algorithm)
            logger.info(f"[DEBUG] 算法 {algorithm.metadata.algorithm_name} 提取到 {len(algorithm_velocity_data)} 个锤速数据点")
            all_velocity_data.extend(algorithm_velocity_data)

        logger.info(f"[DEBUG] 总共收集到 {len(all_velocity_data)} 个锤速数据点")
        return all_velocity_data

    def _extract_single_algorithm_velocity_data(algorithm: AlgorithmInstance) -> List[VelocityDataItem]:
        """
        从单个算法中提取锤速数据

        Args:
            algorithm: 算法实例

        Returns:
            List[VelocityDataItem]: 该算法的锤速数据列表
        """
        velocity_data = []

        # 检查算法是否有必要的分析器
        if not (algorithm.analyzer and algorithm.analyzer.note_matcher):
            logger.warning(f"[WARNING] 算法 {algorithm.metadata.algorithm_name} 缺少必要的分析器或音符匹配器")
            return velocity_data

        # 获取匹配对和偏移数据
        matched_pairs = algorithm.analyzer.note_matcher.get_matched_pairs()
        offset_data = algorithm.analyzer.note_matcher.get_offset_alignment_data()

        logger.info(f"[DEBUG] 算法 {algorithm.metadata.algorithm_name}: 匹配对数量={len(matched_pairs) if matched_pairs else 0}, 偏移数据数量={len(offset_data) if offset_data else 0}")

        if not (matched_pairs and offset_data):
            logger.warning(f"[WARNING] 算法 {algorithm.metadata.algorithm_name} 缺少匹配对或偏移数据")
            return velocity_data

        # 创建偏移数据的快速查找映射
        offset_map = _create_velocity_offset_map(offset_data)

        # 遍历匹配对，提取锤速数据
        valid_count = 0
        for record_idx, replay_idx, record_note, replay_note in matched_pairs:
            velocity_item = _extract_velocity_data_from_pair(
                record_idx, replay_idx, record_note, replay_note,
                offset_map, algorithm
            )
            if velocity_item:
                velocity_data.append(velocity_item)
                valid_count += 1

        logger.info(f"[DEBUG] 算法 {algorithm.metadata.algorithm_name}: 从 {len(matched_pairs)} 个匹配对中提取到 {valid_count} 个有效锤速数据点")
        return velocity_data

    def _create_velocity_offset_map(offset_data: List[OffsetAlignmentDataItem]) -> Dict[Tuple[int, int], OffsetAlignmentDataItem]:
        """
        创建偏移数据的快速查找映射

        Args:
            offset_data: 偏移数据列表

        Returns:
            Dict[Tuple[int, int], OffsetAlignmentDataItem]: (record_idx, replay_idx) -> offset_item 的映射
        """
        offset_map = {}
        for item in offset_data:
            record_idx = item.get('record_index')
            replay_idx = item.get('replay_index')
            if record_idx is not None and replay_idx is not None:
                offset_map[(record_idx, replay_idx)] = item
        return offset_map

    def _extract_velocity_data_from_pair(record_idx: int, replay_idx: int, record_note: SPMIDNote, replay_note: SPMIDNote, offset_map: Dict[Tuple[int, int], OffsetAlignmentDataItem], algorithm: AlgorithmInstance) -> Optional[VelocityDataItem]:
        """
        从单个匹配对中提取锤速数据

        Args:
            record_idx: 录制索引
            replay_idx: 播放索引
            record_note: 录制音符
            replay_note: 播放音符
            offset_map: 偏移数据映射
            algorithm: 算法实例

        Returns:
            Optional[VelocityDataItem]: 锤速数据项，包含差值计算，如果提取失败则返回None
        """
        # 检查是否存在对应的偏移数据
        if (record_idx, replay_idx) not in offset_map:
            return None

        # 提取锤速值
        record_velocity = _get_velocity_from_note(record_note, 'record')
        replay_velocity = _get_velocity_from_note(replay_note, 'replay')


        # 计算录制第一个锤子时间
        record_hammer_time_ms = 0.0
        try:
            if hasattr(record_note, 'hammers') and record_note.hammers is not None and not record_note.hammers.empty:
                record_hammer_time_ms = (record_note.hammers.index[0] + record_note.offset) / 10.0
        except Exception:
            record_hammer_time_ms = getattr(record_note, 'offset', 0) / 10.0

        # 计算播放第一个锤子时间
        replay_hammer_time_ms = 0.0
        try:
            if hasattr(replay_note, 'hammers') and replay_note.hammers is not None and not replay_note.hammers.empty:
                replay_hammer_time_ms = (replay_note.hammers.index[0] + replay_note.offset) / 10.0
        except Exception:
            replay_hammer_time_ms = getattr(replay_note, 'offset', 0) / 10.0

        # 只有当两个锤速都有效时才返回数据
        if record_velocity is not None and replay_velocity is not None:

            filename_display = algorithm.metadata.filename
            # 尝试从display_name中提取更友好的文件名（如果display_name包含文件名）
            # 这里简单处理，直接使用display_name作为主要标识，filename作为辅助
            
            return {
                'algorithm_name': algorithm.metadata.algorithm_name,
                'display_name': algorithm.metadata.display_name,
                'filename': algorithm.metadata.filename,
                'key_id': record_note.id,
                'record_index': record_idx,  # 添加录制音符索引
                'replay_index': replay_idx,  # 添加播放音符索引
                'record_velocity': record_velocity,
                'replay_velocity': replay_velocity,
                'velocity_diff': replay_velocity - record_velocity,
                'record_hammer_time_ms': record_hammer_time_ms,
                'replay_hammer_time_ms': replay_hammer_time_ms
            }

        return None

    def _get_velocity_from_note(note: SPMIDNote, note_type: str) -> Optional[float]:
        """
        从音符中安全地提取锤速值

        Args:
            note: 音符对象
            note_type: 音符类型描述（用于日志）

        Returns:
            Optional[float]: 锤速值，如果无法提取则返回None
        """
        try:
            if not hasattr(note, 'hammers'):
                logger.debug(f"提取{note_type}锤速失败: 音符没有hammers属性")
                return None

            hammers = getattr(note, 'hammers', None)
            if hammers is None:
                logger.debug(f"提取{note_type}锤速失败: hammers属性为None")
                return None

            # 对于pandas Series，使用empty属性检查是否为空
            if hasattr(hammers, 'empty'):
                if hammers.empty:
                    logger.debug(f"提取{note_type}锤速失败: hammers Series为空")
                    return None
                try:
                    first_value = hammers.values[0] if hasattr(hammers, 'values') else hammers[0]
                    # 检查值是否有效（不是NaN或None）
                    if pd.isna(first_value) or first_value is None:
                        logger.debug(f"提取{note_type}锤速失败: 第一个锤速值为无效值 {first_value}")
                        return None
                    return first_value
                except (IndexError, KeyError, TypeError) as e:
                    logger.debug(f"提取{note_type}锤速失败: 访问第一个值时出错 {e}")
                    return None
            # 对于其他序列类型，使用len()检查
            elif hasattr(hammers, '__len__'):
                if len(hammers) == 0:
                    logger.debug(f"提取{note_type}锤速失败: hammers序列为空")
                    return None
                try:
                    first_value = hammers.values[0] if hasattr(hammers, 'values') else hammers[0]
                    # 检查值是否有效（不是NaN或None）
                    if pd.isna(first_value) or first_value is None:
                        logger.debug(f"提取{note_type}锤速失败: 第一个锤速值为无效值 {first_value}")
                        return None
                    return first_value
                except (IndexError, KeyError, TypeError) as e:
                    logger.debug(f"提取{note_type}锤速失败: 访问第一个值时出错 {e}")
                    return None
            else:
                logger.debug(f"提取{note_type}锤速失败: hammers不是可迭代对象")
                return None

        except (AttributeError, IndexError, KeyError, TypeError) as e:
            logger.debug(f"提取{note_type}锤速失败: {e}")
        return None

    def _create_velocity_comparison_plot(velocity_data: List[VelocityDataItem]) -> Figure:
        """
        创建锤速对比散点图

        Args:
            velocity_data: 锤速数据列表

        Returns:
            Figure: 配置完整的图表对象
        """
        logger.info(f"[DEBUG] 开始创建锤速对比图，输入数据点数量: {len(velocity_data)}")

        if not velocity_data:
            logger.warning("[WARNING] 没有锤速数据，创建空图表")
            return go.Figure()

        velocity_fig = go.Figure()

        # 定义颜色方案
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f']

        # 为每个算法+文件组合分配颜色并添加散点
        # 创建算法+文件的唯一标识符
        # 使用 filename 来区分同种算法的不同文件
        unique_algorithm_files = list(set(f"{item['display_name']} - {item['filename']}" for item in velocity_data))

        logger.info(f"[DEBUG] 发现 {len(unique_algorithm_files)} 个不同的算法+文件组合: {unique_algorithm_files}")

        for i, algorithm_file in enumerate(unique_algorithm_files):
            color = colors[i % len(colors)]
            # 根据 display_name 和 filename 组合来筛选数据
            algorithm_file_data = [item for item in velocity_data if f"{item['display_name']} - {item['filename']}" == algorithm_file]

            logger.info(f"[DEBUG] 算法文件 '{algorithm_file}' 有 {len(algorithm_file_data)} 个数据点")

            if algorithm_file_data:
                # 准备图表数据
                plot_data = _prepare_velocity_plot_data(algorithm_file_data)

                logger.info(f"[DEBUG] 添加trace: {algorithm_file}, 数据点数量: {len(plot_data['x_values'])}")

                # 从algorithm_file中提取display_name作为图注名称
                display_name = algorithm_file.split(' - ')[0] if ' - ' in algorithm_file else algorithm_file

                # 添加散点系列
                trace = go.Scatter(
                    x=plot_data['x_values'],
                    y=plot_data['y_values'],
                    mode='markers',
                    name=display_name,
                    marker=dict(
                        color=color,
                        size=8,
                        opacity=0.8,
                        line=dict(width=1, color='white')
                    ),
                    text=plot_data['hover_texts'],
                    customdata=plot_data['custom_data'],  # 添加自定义数据用于点击回调
                    hovertemplate='%{text}<extra></extra>',
                    showlegend=True  # 确保显示在图注中
                )
                velocity_fig.add_trace(trace)
                logger.info(f"[DEBUG] 已添加trace '{display_name}' 到图表，包含 {len(plot_data['x_values'])} 个数据点")

        # 添加参考线（零差值线）
        velocity_fig.add_hline(
            y=0,
            line_dash="dash",
            line_color="red",
            opacity=0.7
        )

        # 配置图表布局
        velocity_fig.update_layout(
            xaxis_title='按键ID',
            yaxis_title='锤速差值 (播放锤速 - 录制锤速)',
            height=500,
            template='plotly_white',
            hovermode='closest',
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="top",
                y=1.2,
                xanchor="left",
                x=0.0,
                bgcolor='rgba(255, 255, 255, 0.9)',
                bordercolor='rgba(0, 0, 0, 0.3)',
                borderwidth=1
            ),
            margin=dict(t=100, b=40, l=40, r=40)  # 为图注留出更多上方空间
        )

        logger.info("[OK] 锤速对比散点图生成成功")

        return velocity_fig


    def _prepare_velocity_plot_data(algorithm_data: List[VelocityDataItem]) -> Dict[str, Union[List[str], List[float], List[str]]]:
        """
        准备单个算法的图表数据显示

        Args:
            algorithm_data: 该算法的锤速数据列表

        Returns:
            Dict[str, List[Any]]: 包含x_values, y_values, hover_texts的图表数据字典
        """
        # 按key_id升序排序
        sorted_data = sorted(algorithm_data, key=lambda x: x['key_id'])

        x_values = [str(item['key_id']) for item in sorted_data]
        y_values = [item['velocity_diff'] for item in sorted_data]

        # 构建详细的悬停信息
        hover_texts = []
        custom_data = []
        for item in sorted_data:
            hover_text = (
                f'按键: {item["key_id"]}<br>'
                f'算法: {item["display_name"]}<br>'
                f'锤速差值: {item["velocity_diff"]:.1f}<br>'
                f'录制锤速: {item["record_velocity"]}<br>'
                f'播放锤速: {item["replay_velocity"]:.1f}<br>'
                f'录制锤子时间: {item["record_hammer_time_ms"]:.2f} ms<br>'
                f'播放锤子时间: {item["replay_hammer_time_ms"]:.2f} ms'
            )
            hover_texts.append(hover_text)
            # customdata 包含 [按键ID, 算法名称, 录制索引, 播放索引] 用于点击回调
            custom_data.append([item["key_id"], item["algorithm_name"], item["record_index"], item["replay_index"]])

        return {
            'x_values': x_values,
            'y_values': y_values,
            'hover_texts': hover_texts,
            'custom_data': custom_data
        }
    
    
    def _extract_algorithm_from_customdata(customdata):
        """从customdata中提取算法名称"""
        if not customdata or not isinstance(customdata, list) or len(customdata) == 0:
            return None

        try:
            first_point_data = customdata[0]
            if isinstance(first_point_data, list) and len(first_point_data) >= 2:
                return first_point_data[1]
        except (IndexError, TypeError) as e:
            logger.debug(f"[WARNING] 提取算法名称时出错: {e}")
            pass
        return None

    def _check_algorithm_name_match(trace_algorithm_name, target_algorithm_name):
        """检查算法名称是否匹配（包括括号处理）"""
        if not trace_algorithm_name or not target_algorithm_name:
            return False

        # 精确匹配
        if trace_algorithm_name == target_algorithm_name:
            return True

        # 如果目标算法名称包含括号，尝试匹配基础名称
        # 例如：算法A (文件名) 应该匹配 算法A
        if '(' in target_algorithm_name:
            base_name = target_algorithm_name.split('(')[0].strip()
            if trace_algorithm_name == base_name:
                return True

        # 如果trace算法名称包含括号，尝试匹配基础名称
        if '(' in trace_algorithm_name:
            base_name = trace_algorithm_name.split('(')[0].strip()
            if base_name == target_algorithm_name:
                return True

        return False

    def _check_algorithm_from_legendgroup(legendgroup, algorithm_name):
        """从legendgroup检查算法匹配"""
        if not legendgroup:
            return False

        # 精确匹配
        if legendgroup.startswith(f'data_{algorithm_name}_'):
            return True

        # 如果算法名称包含括号，尝试匹配基础名称
        if '(' in algorithm_name:
            base_name = algorithm_name.split('(')[0].strip()
            if legendgroup.startswith(f'data_{base_name}_'):
                return True

        return False

    def _check_dict_trace_algorithm(trace, algorithm_name):
        """检查dict类型trace是否属于指定算法"""
        # 首先尝试从customdata获取
        customdata = trace.get('customdata')
        trace_algorithm_name = _extract_algorithm_from_customdata(customdata)
        if trace_algorithm_name and _check_algorithm_name_match(trace_algorithm_name, algorithm_name):
            return True

        # 然后尝试从legendgroup获取
        legendgroup = trace.get('legendgroup')
        return _check_algorithm_from_legendgroup(legendgroup, algorithm_name)

    def _check_plotly_trace_algorithm(trace, algorithm_name):
        """检查Plotly trace对象是否属于指定算法"""
        # 首先尝试从customdata获取
        if hasattr(trace, 'customdata') and trace.customdata:
            trace_algorithm_name = _extract_algorithm_from_customdata(trace.customdata)
            if trace_algorithm_name and _check_algorithm_name_match(trace_algorithm_name, algorithm_name):
                return True

        # 然后尝试从legendgroup获取
        if hasattr(trace, 'legendgroup') and trace.legendgroup:
            return _check_algorithm_from_legendgroup(trace.legendgroup, algorithm_name)

        return False

    def trace_belongs_to_algorithm(trace, algorithm_name):
        """检查trace是否属于指定的算法"""
        if not algorithm_name:
            return False

        # 根据trace类型选择不同的检查方法
        if isinstance(trace, dict):
            return _check_dict_trace_algorithm(trace, algorithm_name)
        else:
            return _check_plotly_trace_algorithm(trace, algorithm_name)

    def _prepare_key_force_interaction_figure(trigger_id: str, backend, current_figure):
        """准备按键-力度交互效应图表对象"""
        # 如果是report-content变化，需要重新生成图表
        if trigger_id == 'report-content':
            # 检查是否有激活的算法
            active_algorithms = backend.get_active_algorithms()
            if not active_algorithms:
                logger.warning("[WARNING] 没有激活的算法，无法生成交互效应图")
                return backend.plot_generator._create_empty_plot("没有激活的算法")

            # 重新生成图表
            fig = backend.generate_key_force_interaction_plot()
        else:
            # 如果是选择变化，使用当前图表并更新可见性
            if current_figure and isinstance(current_figure, dict) and 'data' in current_figure:
                # 从dict创建Figure，确保所有属性都被正确加载
                fig = go.Figure(current_figure)
                # 确保data是trace对象列表，而不是dict列表
                if fig.data and isinstance(fig.data[0], dict):
                    # 如果data是dict列表，需要转换为trace对象
                    fig_data = []
                    for trace_dict in fig.data:
                        trace_type = trace_dict.get('type', 'scatter')
                        if trace_type == 'scatter':
                            fig_data.append(go.Scatter(trace_dict))
                        else:
                            fig_data.append(trace_dict)
                    fig.data = fig_data
            else:
                active_algorithms = backend.get_active_algorithms()
                if not active_algorithms:
                    return no_update
                fig = backend.generate_key_force_interaction_plot()

        return fig

    def _update_algorithm_control_traces(data_list: List, selected_algorithms: List[str]):
        """更新算法控制图注的透明度和大小"""
        # logger.info(f"[DRAW] 开始更新算法控制图注: 选中算法={selected_algorithms}")

        for trace_idx, trace in enumerate(data_list):
            # 处理dict类型的trace
            if isinstance(trace, dict):
                if trace.get('legendgroup') == 'algorithm_control':
                    if 'name' in trace and trace['name']:
                        algorithm_name = trace['name']
                        if 'marker' not in trace:
                            trace['marker'] = {}

                        # 选中时：颜色变浓（完全不透明）并且变大
                        # 未选中时：颜色变淡（半透明）并且变小
                        if algorithm_name in selected_algorithms:
                            trace['marker']['opacity'] = 1.0  # 选中时完全不透明，颜色更浓
                            trace['marker']['size'] = 18  # 选中时明显更大
                        else:
                            trace['marker']['opacity'] = 0.4  # 未选中时半透明，颜色较淡
                            trace['marker']['size'] = 12  # 未选中时正常大小

                        data_list[trace_idx] = trace
                        logger.info(f"[UPDATE] 更新算法控制图注 '{algorithm_name}' 透明度: {trace['marker']['opacity']} (选中: {algorithm_name in selected_algorithms})")
            else:
                # 处理Plotly trace对象
                if hasattr(trace, 'legendgroup') and trace.legendgroup == 'algorithm_control':
                    if hasattr(trace, 'name') and trace.name:
                        algorithm_name = trace.name
                        # 直接修改marker.opacity和size属性（对象引用已修改，不需要重新赋值）
                        if hasattr(trace, 'marker') and trace.marker is not None:
                            # 选中时：颜色变浓（完全不透明）并且变大
                            # 未选中时：颜色变淡（半透明）并且变小
                            if algorithm_name in selected_algorithms:
                                trace.marker.opacity = 1.0  # 选中时完全不透明，颜色更浓
                                trace.marker.size = 18  # 选中时明显更大
                            else:
                                trace.marker.opacity = 0.4  # 未选中时半透明，颜色较淡
                                trace.marker.size = 12  # 未选中时正常大小

    def _update_key_control_traces(data_list: List, selected_keys: List[int]):
        """更新按键控制图注的透明度和大小"""
        logger.info(f"[DRAW] 开始更新按键控制图注: 选中按键={selected_keys}")

        for trace_idx, trace in enumerate(data_list):
            # 处理dict类型的trace
            if isinstance(trace, dict):
                if trace.get('legendgroup') == 'key_control':
                    if 'name' in trace and trace['name']:
                        key_name = trace['name']
                        # 从按键名称中提取按键ID
                        import re
                        key_id_match = re.match(r'按键 (\d+)', key_name)
                        if key_id_match:
                            key_id = int(key_id_match.group(1))

                            if 'marker' not in trace:
                                trace['marker'] = {}

                            # 选中时：颜色变浓（完全不透明）并且变大
                            if key_id in selected_keys:
                                trace['marker']['opacity'] = 1.0  # 选中时完全不透明，颜色较浓
                                trace['marker']['size'] = 16  # 选中时变大
                            else:
                                trace['marker']['opacity'] = 0.4  # 未选中时半透明，颜色较淡
                                trace['marker']['size'] = 14  # 未选中时正常大小
                            data_list[trace_idx] = trace
            else:
                # 处理trace对象
                if hasattr(trace, 'legendgroup') and trace.legendgroup == 'key_control':
                    if hasattr(trace, 'name') and trace.name:
                        key_name = trace.name
                        # 从按键名称中提取按键ID
                        import re
                        key_id_match = re.match(r'按键 (\d+)', key_name)
                        if key_id_match:
                            key_id = int(key_id_match.group(1))

                            # 选中时：颜色变浓（完全不透明）并且变大
                            if key_id in selected_keys:
                                trace.marker.opacity = 1.0  # 选中时完全不透明，颜色较浓
                                trace.marker.size = 16  # 选中时变大
                            else:
                                trace.marker.opacity = 0.4  # 未选中时半透明，颜色较淡
                                trace.marker.size = 14  # 未选中时正常大小

    def trace_belongs_to_algorithm_and_key(trace, selected_algorithms: List[str], selected_keys: List[int]) -> bool:
        """检查trace是否属于选中的算法和按键（多选模式）"""
        # 从trace的customdata中提取算法和按键信息
        customdata = None
        if isinstance(trace, dict):
            customdata = trace.get('customdata')
        else:
            customdata = trace.customdata if hasattr(trace, 'customdata') else None

        if not customdata:
            logger.debug("[TRACE] trace没有customdata - 隐藏")
            return False

        # 转换为列表（处理numpy数组、tuple等）
        try:
            if hasattr(customdata, '__iter__') and not isinstance(customdata, str):
                # 确保customdata是列表格式
                if not isinstance(customdata, list):
                    customdata = list(customdata)
                
                if len(customdata) == 0:
                    logger.debug("[TRACE] customdata为空列表")
                    return False
                
                # 获取第一个数据点
                first_point = customdata[0]
                
                # 转换first_point为列表（如果需要）
                if hasattr(first_point, '__iter__') and not isinstance(first_point, str):
                    if not isinstance(first_point, list):
                        first_point = list(first_point)
                    
                    # customdata格式: [key_id, replay_velocity, relative_delay, absolute_delay, algorithm_name, mean_delay]
                    if len(first_point) >= 5:
                        trace_key_id = int(first_point[0])      # 索引0：按键ID
                        trace_algorithm = str(first_point[4]) if first_point[4] else ''  # 索引4：算法名称

                        # 如果没有选择任何算法或按键，则显示所有
                        if not selected_algorithms and not selected_keys:
                            return True
                        
                        # 算法匹配逻辑
                        if selected_algorithms:
                            # 如果选择了算法，trace的algorithm必须在选中列表中
                            # 空字符串algorithm表示单算法模式，不匹配任何多算法选择
                            algorithm_match = bool(trace_algorithm and trace_algorithm in selected_algorithms)
                        else:
                            # 如果没有选择任何算法，所有trace都匹配（无论algorithm是否为空）
                            algorithm_match = True
                        
                        # 按键匹配：如果选择了按键，则必须匹配；否则任何按键都可以
                        key_match = True
                        if selected_keys:
                            key_match = trace_key_id in selected_keys
                        
                        # 必须同时满足算法和按键条件（AND逻辑）
                        result = algorithm_match and key_match
                        
                        # 详细日志
                        if selected_keys and trace_key_id in selected_keys:
                            logger.info(f"[TRACE] ★ key={trace_key_id}, alg='{trace_algorithm}', selected_algs={selected_algorithms}, selected_keys={selected_keys}, alg_match={algorithm_match}, key_match={key_match}, result={result}")

                        return result
                    else:
                        logger.debug(f"[TRACE] first_point长度不足: {len(first_point)}, 内容: {first_point}")
                else:
                    logger.debug(f"[TRACE] first_point不可迭代, 类型: {type(first_point)}, 内容: {first_point}")
            else:
                logger.debug(f"[TRACE] customdata不可迭代, 类型: {type(customdata)}")
                
        except Exception as e:
            logger.error(f"[TRACE] 处理customdata时出错: {e}, 类型: {type(customdata)}")
            import traceback
            logger.error(traceback.format_exc())
        
        return False

    def _update_data_trace_visibility(data_list: List, selected_algorithms: List[str], selected_keys: List[int], trace_belongs_to_algorithm_and_key):
        """更新数据trace的可见性"""
        visible_count = 0
        total_data_traces = 0
        
        
        for trace_idx, trace in enumerate(data_list):
            # 跳过控制图注项
            legendgroup = trace.get('legendgroup') if isinstance(trace, dict) else (trace.legendgroup if hasattr(trace, 'legendgroup') else None)
            if legendgroup in ['algorithm_control', 'key_control']:
                continue

            total_data_traces += 1
            
            # 数据trace：多选模式，需要同时满足算法和按键条件
            target_visible = trace_belongs_to_algorithm_and_key(trace, selected_algorithms, selected_keys)
            
            if target_visible:
                visible_count += 1
                pass
            else:
                pass

            # 更新可见性
            if isinstance(trace, dict):
                trace['visible'] = target_visible
                data_list[trace_idx] = trace
            else:
                trace.visible = target_visible
        

    # 更新按键选择下拉菜单的选项
    @app.callback(
        Output('key-force-interaction-key-selector', 'options'),
        [Input('key-force-interaction-plot', 'figure')],
        prevent_initial_call=True
    )
    def update_key_selector_options(figure):
        """根据图表数据更新按键选择器的选项"""
        if not figure or 'data' not in figure:
            return []
        
        # 提取所有按键ID
        key_ids = set()
        for trace in figure['data']:
            legendgroup = trace.get('legendgroup', '')
            # 只从数据trace中提取按键ID（不是控制图注）
            if legendgroup and legendgroup.startswith('data_') and '_key_' in legendgroup:
                try:
                    # legendgroup格式：data_算法名_key_按键ID
                    key_part = legendgroup.split('_key_')[1]
                    key_id = int(key_part)
                    key_ids.add(key_id)
                except:
                    pass
        
        # 生成下拉选项
        options = [{'label': f'按键 {key_id}', 'value': key_id} for key_id in sorted(key_ids)]
        return options
    
    # 当下拉菜单选择改变时，更新selected_keys
    @app.callback(
        Output('key-force-interaction-selected-keys', 'data'),
        [Input('key-force-interaction-key-selector', 'value')],
        prevent_initial_call=True
    )
    def update_selected_keys_from_dropdown(selected_key):
        """当下拉菜单选择改变时，更新selected_keys"""
        if selected_key is None:
            return []
        return [selected_key]

    # 按键-力度交互效应图自动生成和更新回调函数
    @app.callback(
        Output('key-force-interaction-plot', 'figure'),
        [Input('report-content', 'children'),
         Input('key-force-interaction-selected-algorithms', 'data'),
         Input('key-force-interaction-selected-keys', 'data')],
        [State('session-id', 'data'),
         State('key-force-interaction-plot', 'figure')],
        prevent_initial_call=True
    )
    def handle_generate_key_force_interaction_plot(report_content, selected_algorithms, selected_keys, session_id, current_figure):
        """处理按键-力度交互效应图自动生成和更新 - 根据选中的算法和按键更新可见性"""
        ctx = dash.callback_context
        if not ctx.triggered:
            return no_update

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update

        try:
            # 根据选中的算法和按键更新可见性
            selected_algorithms = selected_algorithms or []
            selected_keys = selected_keys or []

            # 准备图表对象
            fig = _prepare_key_force_interaction_figure(trigger_id, backend, current_figure)
            if fig is no_update or isinstance(fig, str):  # 如果是空图或错误，直接返回
                return fig

            # 将fig.data转换为可修改的list
            data_list = list(fig.data)

            # 更新算法控制图注的透明度
            _update_algorithm_control_traces(data_list, selected_algorithms)

            # 更新按键控制图注的透明度
            _update_key_control_traces(data_list, selected_keys)

            # 更新数据trace的可见性
            _update_data_trace_visibility(data_list, selected_algorithms, selected_keys, trace_belongs_to_algorithm_and_key)

            # 将修改后的trace列表赋值回fig.data
            fig.data = data_list

            logger.info(f"[OK] 按键-力度交互效应图更新成功 (触发器: {trigger_id})")
            return fig

        except Exception as e:
            logger.error(f"[ERROR] 生成/更新按键-力度交互效应图失败: {e}")
            logger.error(traceback.format_exc())
            return backend.plot_generator._create_empty_plot(f"生成交互效应图失败: {str(e)}")

    def _validate_multi_algorithm_analysis(backend):
        """验证多算法模式并获取分析结果"""
        # 检查是否在多算法模式
        if not backend.multi_algorithm_mode or not backend.multi_algorithm_manager:
            logger.warning("[WARNING] 未启用多算法模式，无法生成相对延时分布图")
            return None, html.Div([
                dbc.Alert("未启用多算法模式", color="warning")
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
    
    def _find_target_algorithm_instance(backend, algorithm_name, record_index, replay_index):
        """[Helper] 在多算法模式下查找目标算法实例"""
        if not backend.multi_algorithm_mode or not backend.multi_algorithm_manager:
            return None
            
        all_algorithms = backend.multi_algorithm_manager.get_all_algorithms()
        target_algorithm = None
        
        # 1. 首先尝试精确匹配算法名称
        candidate_algorithms = [alg for alg in all_algorithms if alg.metadata.algorithm_name == algorithm_name]
        logger.info(f"🔍 找到 {len(candidate_algorithms)} 个匹配算法名称的算法实例: {algorithm_name}")
        
        # 2. 如果有多个或只有一个候选算法，通过匹配对进一步验证
        if candidate_algorithms:
            for alg in candidate_algorithms:
                if alg.analyzer and hasattr(alg.analyzer, 'matched_pairs'):
                    for r_idx, p_idx, _, _ in alg.analyzer.matched_pairs:
                        if r_idx == record_index and p_idx == replay_index:
                            logger.info(f"[OK] 通过匹配对找到正确的算法实例: {alg.metadata.algorithm_name}")
                            return alg
                            
            # 如果没有找到匹配对，但只有一个候选，且没有匹配对数据（可能未初始化），则勉强使用
            if len(candidate_algorithms) == 1:
                logger.warning(f"[WARNING] 只有一个候选算法但未找到明确匹配对，尝试使用: {algorithm_name}")
                return candidate_algorithms[0]

        # 3. 如果精确匹配失败，尝试全局查找（用于汇总图等情况）
        logger.info(f"[WARNING] 算法名称匹配失败，尝试在所有算法中通过索引查找")
        for alg in all_algorithms:
            if alg.analyzer and hasattr(alg.analyzer, 'matched_pairs'):
                for r_idx, p_idx, _, _ in alg.analyzer.matched_pairs:
                    if r_idx == record_index and p_idx == replay_index:
                        logger.info(f"[OK] 通过匹配对全局找到算法实例: {alg.metadata.algorithm_name}")
                        return alg
                        
        return None

    def _get_notes_and_center_time(target_algorithm, record_index, replay_index, key_id):
        """[Helper] 获取录制/播放音符对象及中心时间"""
        record_note = None
        replay_note = None
        center_time_ms = None
        
        if not target_algorithm or not target_algorithm.analyzer:
            return None, None, None

        # 1. 尝试从 matched_pairs 获取
        matched_pairs = getattr(target_algorithm.analyzer, 'matched_pairs', [])
        found_pair = False
        
        if matched_pairs:
            for r_idx, p_idx, r_note, p_note in matched_pairs:
                if r_idx == record_index and p_idx == replay_index:
                    if key_id is not None and r_note.id != key_id:
                        continue
                        
                    record_note = r_note
                    replay_note = p_note
                    found_pair = True
                    
                    # 计算keyon时间
                    r_offset = r_note.after_touch.index[0] + r_note.offset if hasattr(r_note, 'after_touch') and not r_note.after_touch.empty else r_note.offset
                    p_offset = p_note.after_touch.index[0] + p_note.offset if hasattr(p_note, 'after_touch') and not p_note.after_touch.empty else p_note.offset
                    center_time_ms = ((r_offset + p_offset) / 2.0) / 10.0
                    break
        
        # 2. 如果 matched_pairs 失败，尝试从 offset_data 获取（备用）
        if not found_pair and target_algorithm.analyzer.note_matcher:
            try:
                offset_data = target_algorithm.analyzer.note_matcher.get_offset_alignment_data()
                for item in offset_data or []:
                    if item.get('record_index') == record_index and item.get('replay_index') == replay_index:
                        r_keyon = item.get('record_keyon', 0)
                        p_keyon = item.get('replay_keyon', 0)
                        if r_keyon and p_keyon:
                            center_time_ms = ((r_keyon + p_keyon) / 2.0) / 10.0
                            logger.info(f"[OK] 从offset_data获取时间信息: {center_time_ms:.1f}ms")
                            
                            # 再次尝试在 matched_pairs 中找音符对象（可能之前key_id过滤太严？）
                            for r_idx, p_idx, r_note, p_note in matched_pairs:
                                if r_idx == record_index and p_idx == replay_index:
                                    record_note, replay_note = r_note, p_note
                                    found_pair = True
                                    break
                            break
            except Exception as e:
                logger.warning(f"[WARNING] 从offset_data获取信息失败: {e}")

        return record_note, replay_note, center_time_ms
    
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

            import spmid
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
        Output('delay-time-series-plot', 'figure'),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_generate_delay_time_series(report_content, session_id):
        """处理延时时间序列图自动生成 - 当报告内容更新时触发"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update

        try:
            # 检查是否在多算法模式
            # 检查是否有激活的算法
            active_algorithms = backend.get_active_algorithms()
            if not active_algorithms:
                logger.warning("[WARNING] 没有激活的算法，无法生成延时时间序列图")
                empty_plot = backend.plot_generator._create_empty_plot("没有激活的算法")
                return empty_plot

            result = backend.generate_delay_time_series_plot()

            # 检查返回的是否是字典（两个图表）还是单个图表
            if isinstance(result, dict) and 'raw_delay_plot' in result and 'relative_delay_plot' in result:
                logger.info("[OK] 延时时间序列图生成成功（分离模式）")
                # 在当前布局中，我们只有一个图表组件，合并两个图表或选择一个
                # 这里选择相对延时图作为主要显示
                return result['relative_delay_plot']
            else:
                # 单个图表模式
                logger.info("[OK] 延时时间序列图生成成功（单个图表模式）")
                return result

        except Exception as e:
            logger.error(f"[ERROR] 生成延时时间序列图失败: {e}")
            logger.error(traceback.format_exc())
            empty_plot = backend.plot_generator._create_empty_plot(f"生成时间序列图失败: {str(e)}")
            return empty_plot
    
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

    # 延时时间序列图点击回调 - 多算法模式（仅监听 delay-time-series-plot）
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True),
         Output('delay-time-series-plot', 'clickData', allow_duplicate=True)],
        [Input('delay-time-series-plot', 'clickData'),
         Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State('session-id', 'data'),
         State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
#     def handle_delay_time_series_click_multi(delay_click_data, close_modal_clicks, close_btn_clicks, session_id, current_style):
#         """处理延时时间序列图点击（多算法模式），显示音符分析曲线（悬浮窗）"""
        # 检测触发源
#         ctx = callback_context
#         if not ctx.triggered:
#             return current_style, [], no_update, no_update

#         trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
#         logger.info(f"🔍 触发ID: {trigger_id}")

        # 如果点击了关闭按钮，隐藏模态框
#         if trigger_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
#             modal_style = {
#                 'display': 'none',
#                 'position': 'fixed',
#                 'zIndex': '9999',
#                 'left': '0',
#                 'top': '0',
#                 'width': '100%',
#                 'height': '100%',
#                 'backgroundColor': 'rgba(0,0,0,0.6)',
#                 'backdropFilter': 'blur(5px)'
#             }
#             return modal_style, [], no_update, no_update

        # 只有在点击了 delay-time-series-plot 时才处理
#         if trigger_id != 'delay-time-series-plot' or not delay_click_data:
#             return current_style, [], no_update, no_update

#         logger.info(f"[TARGET] 检测到{trigger_id}点击")

#         backend = session_manager.get_backend(session_id)
#         if not backend:
#             logger.warning("[WARNING] backend为空")
#             return current_style, [], no_update, no_update

#         try:
#             if 'points' not in click_data or len(click_data['points']) == 0:
#                 logger.warning("[WARNING] clickData中没有points")
#                 return current_style, [], no_update, no_update

#             point = click_data['points'][0]
#             if not point.get('customdata'):
#                 logger.warning("[WARNING] point中没有customdata")
#                 return current_style, [], no_update, no_update

            # 提取customdata: [key_id, record_index, replay_index] 或 [key_id, record_index, replay_index, algorithm_name, ...]
            # 多算法模式可能包含更多信息: [key_id, record_index, replay_index, algorithm_name, delay, mean_delay, replay_time, record_time]
#             customdata = point['customdata']
#             logger.info(f"[DATA] customdata: {customdata}")

#             if not isinstance(customdata, list) or len(customdata) < 3:
#                 logger.warning(f"[WARNING] customdata格式错误: {customdata}")
#                 return current_style, [], no_update, no_update
                
#                 key_id = customdata[0]
#                 record_index = customdata[1]
#                 replay_index = customdata[2]
#                 algorithm_name = customdata[3] if len(customdata) > 3 else None
                
#                 logger.info(f"[STATS] 提取的数据: key_id={key_id}, record_index={record_index}, replay_index={replay_index}, algorithm_name={algorithm_name}")
                
                # 获取算法对象和匹配对
#                 record_note = None
#                 replay_note = None
#                 final_algorithm_name = None
                
                # 计算时间信息，用于跳转时直接使用
#                 center_time_ms = None
                
#                 if backend.multi_algorithm_mode and backend.multi_algorithm_manager and algorithm_name:
                    # 多算法模式
#                     algorithm = backend.multi_algorithm_manager.get_algorithm(algorithm_name)
#                     if not algorithm or not algorithm.analyzer:
#                         logger.warning(f"[WARNING] 算法 '{algorithm_name}' 不存在或analyzer为空")
#                         return current_style, [], no_update
                    
                    # 获取matched_pairs
#                     matched_pairs = algorithm.analyzer.matched_pairs if hasattr(algorithm.analyzer, 'matched_pairs') else []
                    
                    # 在matched_pairs中查找匹配对
#                     for r_idx, p_idx, r_note, p_note in matched_pairs:
#                         if r_idx == record_index and p_idx == replay_index:
#                             record_note = r_note
#                             replay_note = p_note
#                             final_algorithm_name = algorithm_name
#                             logger.info(f"[OK] 在多算法模式中找到匹配对")
                            
                            # 计算keyon时间
#                             try:
#                                 record_keyon = r_note.after_touch.index[0] + r_note.offset if hasattr(r_note, 'after_touch') and not r_note.after_touch.empty else r_note.offset
#                                 replay_keyon = p_note.after_touch.index[0] + p_note.offset if hasattr(p_note, 'after_touch') and not p_note.after_touch.empty else p_note.offset
#                                 center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0  # 转换为ms
#                             except Exception as e:
#                                 logger.warning(f"[WARNING] 计算时间信息失败: {e}")
                                # 备用方案：从 customdata 获取时间信息（如果可用）
#                                 if len(customdata) >= 7:
#                                     record_time = customdata[7] if len(customdata) > 7 else None
#                                     replay_time = customdata[6] if len(customdata) > 6 else None
#                                     if record_time is not None and replay_time is not None:
#                                         center_time_ms = ((record_time + replay_time) / 2.0) / 10.0
                            
#                             break
                    
                    # 备用方案：从 offset_data 获取
#                     if center_time_ms is None and algorithm.analyzer.note_matcher:
#                         try:
#                             offset_data = algorithm.analyzer.note_matcher.get_offset_alignment_data()
#                             if offset_data:
#                                 for item in offset_data:
#                                     if item.get('record_index') == record_index and item.get('replay_index') == replay_index:
#                                         record_keyon = item.get('record_keyon', 0)
#                                         replay_keyon = item.get('replay_keyon', 0)
#                                         if record_keyon and replay_keyon:
#                                             center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0
#                                             break
#                         except Exception as e:
#                             logger.warning(f"[WARNING] 从offset_data获取时间信息失败: {e}")
#                 else:
                    # 单算法模式
#                     if not backend.analyzer or not backend.analyzer.note_matcher:
#                         logger.warning("[WARNING] analyzer或note_matcher为空")
#                         return current_style, [], no_update, no_update
                    
#                     matched_pairs = backend.analyzer.matched_pairs if hasattr(backend.analyzer, 'matched_pairs') else []
                    
                    # 在matched_pairs中查找匹配对
#                     for r_idx, p_idx, r_note, p_note in matched_pairs:
#                         if r_idx == record_index and p_idx == replay_index:
#                             record_note = r_note
#                             replay_note = p_note
#                             final_algorithm_name = None
#                             logger.info(f"[OK] 在单算法模式中找到匹配对")
                            
                            # 计算keyon时间
#                             try:
#                                 record_keyon = r_note.after_touch.index[0] + r_note.offset if hasattr(r_note, 'after_touch') and not r_note.after_touch.empty else r_note.offset
#                                 replay_keyon = p_note.after_touch.index[0] + p_note.offset if hasattr(p_note, 'after_touch') and not p_note.after_touch.empty else p_note.offset
#                                 center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0  # 转换为ms
#                             except Exception as e:
#                                 logger.warning(f"[WARNING] 计算时间信息失败: {e}")
                            
#                             break
                    
                    # 备用方案：从 offset_data 获取
#                     if center_time_ms is None:
#                         try:
#                             offset_data = backend.analyzer.note_matcher.get_offset_alignment_data()
#                             if offset_data:
#                                 for item in offset_data:
#                                     if item.get('record_index') == record_index and item.get('replay_index') == replay_index:
#                                         record_keyon = item.get('record_keyon', 0)
#                                         replay_keyon = item.get('replay_keyon', 0)
#                                         if record_keyon and replay_keyon:
#                                             center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0
#                                             break
#                         except Exception as e:
#                             logger.warning(f"[WARNING] 从offset_data获取时间信息失败: {e}")
                
#                 if not record_note or not replay_note:
#                     logger.warning("[WARNING] 未找到匹配对")
#                     return current_style, [], no_update, no_update, no_update
                
                # 在多算法模式下，查找所有算法中匹配到同一个录制音符的播放音符
#                 other_algorithm_notes = []  # [(algorithm_name, play_note), ...]
#                 if backend.multi_algorithm_mode and backend.multi_algorithm_manager:
#                     active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()
#                     for alg in active_algorithms:
#                         if alg.metadata.algorithm_name == algorithm_name:
#                             continue  # 跳过当前算法（已经绘制）
                        
#                         if not alg.analyzer or not hasattr(alg.analyzer, 'matched_pairs'):
#                             continue
                        
#                         matched_pairs = alg.analyzer.matched_pairs
                        # 查找匹配到同一个record_index的播放音符
#                         for r_idx, p_idx, r_note, p_note in matched_pairs:
#                             if r_idx == record_index:
#                                 other_algorithm_notes.append((alg.metadata.algorithm_name, p_note))
#                                 logger.info(f"[OK] 找到算法 '{alg.metadata.algorithm_name}' 的匹配播放音符")
#                                 break
                
                # 计算平均延时
#                 mean_delays = {}
#                 if backend.multi_algorithm_mode and backend.multi_algorithm_manager and algorithm_name:
                    # 多算法模式
#                     algorithm = backend.multi_algorithm_manager.get_algorithm(algorithm_name)
#                     if algorithm and algorithm.analyzer:
#                         mean_error_0_1ms = algorithm.analyzer.get_mean_error()
#                         mean_delays[algorithm_name] = mean_error_0_1ms / 10.0  # 转换为毫秒
#                     else:
#                         logger.error(f"[ERROR] 无法获取算法 '{algorithm_name}' 的平均延时")
#                         return current_style, [], no_update
#                 else:
                    # 单算法模式
#                     if backend.analyzer:
#                         mean_error_0_1ms = backend.analyzer.get_mean_error()
#                         mean_delays[final_algorithm_name or 'default'] = mean_error_0_1ms / 10.0  # 转换为毫秒
#                     else:
#                         logger.error("[ERROR] 无法获取单算法模式的平均延时")
#                         return current_style, [], no_update, no_update
                
                # 生成对比曲线（包含其他算法的播放曲线）
#                 import spmid
#                 detail_figure_combined = spmid.plot_note_comparison_plotly(
#                     record_note, 
#                     replay_note, 
#                     algorithm_name=final_algorithm_name,
#                     other_algorithm_notes=other_algorithm_notes,  # 传递其他算法的播放音符
#                     mean_delays=mean_delays
#                 )
                
#                 if not detail_figure_combined:
#                     logger.error("[ERROR] 曲线生成失败")
#                     return current_style, [], no_update, no_update
                
                # 存储当前点击的数据点信息，用于跳转按钮
#                 point_info = {
#                     'algorithm_name': final_algorithm_name,
#                     'record_idx': record_index,
#                     'replay_idx': replay_index,
#                     'key_id': key_id,
#                     'source_plot_id': 'delay-time-series-plot',  # 记录来源图表ID
#                     'center_time_ms': center_time_ms  # 预先计算的时间信息
#                 }
                
                # 显示模态框
#                 modal_style = {
#                     'display': 'block',
#                     'position': 'fixed',
#                     'zIndex': '9999',
#                     'left': '0',
#                     'top': '0',
#                     'width': '100%',
#                     'height': '100%',
#                     'backgroundColor': 'rgba(0,0,0,0.6)',
#                     'backdropFilter': 'blur(5px)'
#                 }
                
#                 rendered_row = dcc.Graph(figure=detail_figure_combined, style={'height': '600px'})
                
#                 logger.info("[OK] 延时时间序列图点击处理成功")
#                 return modal_style, [rendered_row], point_info, no_update

#         except Exception as e:
#                 logger.error(f"[ERROR] 处理延时时间序列图点击失败: {e}")

#                 logger.error(traceback.format_exc())
#                 return current_style, [], no_update, no_update, no_update

#         return current_style, [], no_update, no_update, no_update

    # 延时时间序列图点击回调 - 多算法模式（仅监听 delay-time-series-plot）
#     @app.callback(
#         [Output('key-curves-modal', 'style', allow_duplicate=True),
#          Output('key-curves-comparison-container', 'children', allow_duplicate=True),
#          Output('current-clicked-point-info', 'data', allow_duplicate=True),
#          Output('delay-time-series-plot', 'clickData', allow_duplicate=True)],
#         [Input('delay-time-series-plot', 'clickData'),
#          Input('close-key-curves-modal', 'n_clicks'),
#          Input('close-key-curves-modal-btn', 'n_clicks')],
#         [State('session-id', 'data'),
#          State('key-curves-modal', 'style')],
#         prevent_initial_call=True
#     )
    def handle_delay_time_series_click_multi(delay_click_data, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理延时时间序列图点击（多算法模式），显示音符分析曲线（悬浮窗）"""
        return delay_time_series_handler.handle_delay_time_series_click_multi(
            delay_click_data, close_modal_clicks, close_btn_clicks, session_id, current_style
        )

    def handle_delay_value_click(max_clicks_list, min_clicks_list, close_modal_clicks, close_btn_clicks,
                                  max_ids_list, min_ids_list, session_id, current_style):
        """处理最大/最小延迟字段点击，显示对应按键的曲线对比图"""
        
        import dash
        
        logger.info("[START] handle_delay_value_click 回调被触发")

        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            return current_style, [], None
        
        trigger_id = ctx.triggered[0]['prop_id']
        trigger_value = ctx.triggered[0].get('value')
        logger.info(f"🔍 触发ID: {trigger_id}, 触发值: {trigger_value}")
        
        # 首先检查是否是关闭按钮的点击
        if trigger_id in ['close-key-curves-modal.n_clicks', 'close-key-curves-modal-btn.n_clicks']:
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
            return modal_style, [], None
        
        # 对于最大/最小延迟字段的点击，需要确保是真正的用户点击
        # 检查clicks列表中是否有任何值>0（真正的点击）
        has_real_click = False
        if max_clicks_list:
            for clicks in max_clicks_list:
                if clicks is not None and clicks > 0:
                    has_real_click = True
                    break
        if not has_real_click and min_clicks_list:
            for clicks in min_clicks_list:
                if clicks is not None and clicks > 0:
                    has_real_click = True
                    break
        
        # 如果没有真正的点击，可能是布局更新导致的，跳过处理
        if not has_real_click:
            logger.info(f"[WARNING] 没有检测到真正的用户点击（可能是布局更新），跳过处理: trigger_id={trigger_id}")
            return current_style, [], None
        
        # 如果点击了关闭按钮，隐藏模态框
        if trigger_id in ['close-key-curves-modal.n_clicks', 'close-key-curves-modal-btn.n_clicks']:
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
        
        # 解析触发ID，提取延迟类型和算法名称
        # 使用callback_context来准确识别哪个Input被触发
        delay_type = None
        algorithm_name = None

        try:
            # 从triggered信息中提取被触发的组件ID
            triggered_prop = ctx.triggered[0]
            prop_id_str = triggered_prop['prop_id']

            # prop_id格式可能是: {'type': 'max-delay-value', 'algorithm': 'xxx'}.n_clicks
            # 或者: {'type': 'min-delay-value', 'algorithm': 'xxx'}.n_clicks

            # 使用字符串解析来提取算法名称
            import ast
            if 'max-delay-value' in prop_id_str:
                delay_type = 'max'
                try:
                    # prop_id格式: {"type": "max-delay-value", "algorithm": "xxx"}.n_clicks
                    # 提取字典部分
                    dict_str = prop_id_str.split('.')[0]  # 去掉.n_clicks部分
                    id_dict = ast.literal_eval(dict_str)
                    algorithm_name = id_dict.get('algorithm')
                    if algorithm_name:
                        logger.info(f"[OK] 从prop_id解析得到最大延迟点击: 算法={algorithm_name}")
                    else:
                        logger.warning(f"[WARNING] prop_id中没有algorithm字段: {prop_id_str}")
                except Exception as e:
                    logger.warning(f"[WARNING] 解析prop_id失败: {prop_id_str}, 错误: {e}")
            elif 'min-delay-value' in prop_id_str:
                delay_type = 'min'
                try:
                    # prop_id格式: {"type": "min-delay-value", "algorithm": "xxx"}.n_clicks
                    # 提取字典部分
                    dict_str = prop_id_str.split('.')[0]  # 去掉.n_clicks部分
                    id_dict = ast.literal_eval(dict_str)
                    algorithm_name = id_dict.get('algorithm')
                    if algorithm_name:
                        logger.info(f"[OK] 从prop_id解析得到最小延迟点击: 算法={algorithm_name}")
                    else:
                        logger.warning(f"[WARNING] prop_id中没有algorithm字段: {prop_id_str}")
                except Exception as e:
                    logger.warning(f"[WARNING] 解析prop_id失败: {prop_id_str}, 错误: {e}")

            # 如果上面的方法没有找到，使用备用方法：检查哪个clicks列表有变化
            if not delay_type or not algorithm_name:
                logger.warning(f"[WARNING] 主要解析方法失败，使用备用方法")
                # 检查max_clicks_list中是否有点击
                if max_clicks_list:
                    for i, clicks in enumerate(max_clicks_list):
                        if clicks is not None and clicks > 0:
                            if max_ids_list and i < len(max_ids_list):
                                max_id = max_ids_list[i]
                                if max_id and isinstance(max_id, dict):
                                    algorithm_name = max_id.get('algorithm')
                                    delay_type = 'max'
                                    logger.info(f"[OK] 备用方法：检测到最大延迟点击: 算法={algorithm_name}, clicks={clicks}")
                                    break

                # 如果还没找到，检查min_clicks_list
                if not delay_type and min_clicks_list:
                    for i, clicks in enumerate(min_clicks_list):
                        if clicks is not None and clicks > 0:
                            if min_ids_list and i < len(min_ids_list):
                                min_id = min_ids_list[i]
                                if min_id and isinstance(min_id, dict):
                                    algorithm_name = min_id.get('algorithm')
                                    delay_type = 'min'
                                    logger.info(f"[OK] 备用方法：检测到最小延迟点击: 算法={algorithm_name}, clicks={clicks}")
                                    break
        except Exception as e:
            logger.warning(f"[WARNING] 解析触发ID失败: {e}, trigger_id={trigger_id}")
            
            logger.error(traceback.format_exc())
        
        if not delay_type or not algorithm_name:
            logger.warning(f"[WARNING] 无法解析延迟类型或算法名称: delay_id={trigger_id}, delay_type={delay_type}, algorithm_name={algorithm_name}")
            logger.warning(f"[WARNING] max_clicks_list: {max_clicks_list}, min_clicks_list: {min_clicks_list}")
            logger.warning(f"[WARNING] max_ids_list: {max_ids_list}, min_ids_list: {min_ids_list}")
            return current_style, [], None
        
        logger.info(f"[STATS] 延迟类型: {delay_type}, 算法名称: {algorithm_name}")
        
        backend = session_manager.get_backend(session_id)
        if not backend:
            logger.warning("[WARNING] backend为空")
            return current_style, [], None
        
        try:
            # 获取对应延迟类型的音符
            notes = backend.get_notes_by_delay_type(algorithm_name, delay_type)
            if notes is None:
                logger.warning(f"[WARNING] 无法获取{delay_type}延迟对应的音符")
                return current_style, [], None

            record_note, replay_note, record_index, replay_index = notes
            
            # 在多算法模式下，查找所有算法中匹配到同一个录制音符的播放音符
            other_algorithm_notes = []  # [(algorithm_name, play_note), ...]
            if backend.multi_algorithm_mode and backend.multi_algorithm_manager:
                active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()
                for alg in active_algorithms:
                    if alg.metadata.algorithm_name == algorithm_name:
                        continue  # 跳过当前算法（已经绘制）
                    
                    if not alg.analyzer or not hasattr(alg.analyzer, 'matched_pairs'):
                        continue
                    
                    matched_pairs = alg.analyzer.matched_pairs
                    # 查找匹配到同一个record_note的播放音符
                    for r_idx, p_idx, r_note, p_note in matched_pairs:
                        if r_note is record_note:  # 使用is比较对象引用
                            other_algorithm_notes.append((alg.metadata.algorithm_name, p_note))
                            logger.info(f"[OK] 找到算法 '{alg.metadata.algorithm_name}' 的匹配播放音符")
                            break
            
            # 计算平均延时，用于曲线偏移显示
            mean_delays = {}
            # 在多算法模式下找到对应的算法对象
            if backend.multi_algorithm_mode and backend.multi_algorithm_manager:
                active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()
                target_algorithm = None
                for alg in active_algorithms:
                    if alg.metadata.algorithm_name == algorithm_name:
                        target_algorithm = alg
                        break

                if target_algorithm and target_algorithm.analyzer:
                    mean_error_0_1ms = target_algorithm.analyzer.get_mean_error()
                    if mean_error_0_1ms is not None:
                        mean_delays[algorithm_name] = mean_error_0_1ms / 10.0  # 转换为ms单位
                        logger.info(f"[OK] 计算平均延时: {mean_delays[algorithm_name]:.2f}ms")
                    else:
                        logger.warning("[WARNING] 无法获取平均延时，使用默认值0")
                        mean_delays[algorithm_name] = 0.0
                else:
                    logger.warning("[WARNING] 未找到目标算法或分析器，使用默认平均延时0")
                    mean_delays[algorithm_name] = 0.0
            else:
                logger.warning("[WARNING] 非多算法模式，无法计算平均延时，使用默认值0")
                mean_delays[algorithm_name] = 0.0

            # 生成对比曲线（包含其他算法的播放曲线和平均延时偏移）
            import spmid
            detail_figure_combined = spmid.plot_note_comparison_plotly(
                record_note, 
                replay_note, 
                algorithm_name=algorithm_name,
                other_algorithm_notes=other_algorithm_notes,  # 传递其他算法的播放音符
                mean_delays=mean_delays
            )
            
            if not detail_figure_combined:
                logger.error("[ERROR] 曲线生成失败")
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
            
            rendered_row = dcc.Graph(figure=detail_figure_combined, style={'height': '600px'})

            # 设置点击点信息，用于跳转到瀑布图
            key_id = getattr(record_note, 'id', 'N/A') if record_note else 'N/A'
            clicked_point_info = {
                'algorithm_name': algorithm_name,
                'record_idx': record_index,
                'replay_idx': replay_index,
                'key_id': key_id,
                'source_plot_id': 'delay-value-click',  # 标识来源是延迟值点击
                'delay_type': delay_type
            }

            delay_type_name = "最大" if delay_type == 'max' else "最小"
            logger.info(f"[OK] {delay_type_name}延迟字段点击处理成功，算法: {algorithm_name}, 按键ID: {key_id}")
            return modal_style, [rendered_row], clicked_point_info
            
        except Exception as e:
            logger.error(f"[ERROR] 处理{delay_type}延迟字段点击失败: {e}")

            logger.error(traceback.format_exc())
        return current_style, [], None
    
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
                logger.warning("[WARNING] 没有激活的算法，无法生成延时直方图")
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

    # 重复验证一致性按钮
    @app.callback(
        Output('repeat-verification-status', 'children'),
        Input('repeat-verification-btn', 'n_clicks'),
        State('session-id', 'data'),
        prevent_initial_call=True
    )
    def repeat_verification(n_clicks, session_id):
        """重复验证系统计算一致性"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return html.Div("❌ 会话无效", style={'color': '#dc3545'})

        try:
            # 检查是否有之前的数据可以验证
            if not hasattr(backend, '_last_upload_content') or not backend._last_upload_content:
                return html.Div("❌ 没有可验证的历史数据，请先上传文件", style={'color': '#dc3545'})

            logger.info(f"🔄 用户主动触发重复验证 - 第 {getattr(backend, '_analysis_count', 0) + 1} 次分析")

            # 强制重新处理相同文件
            filename = getattr(backend, '_last_upload_filename', 'unknown')
            contents = backend._last_upload_content

            # 设置重复验证标志
            backend._is_repeat_verification = True

            # 重新处理文件
            success, result_data, error_msg = backend.process_spmid_upload(contents, filename)

            if success:
                analysis_count = getattr(backend, '_analysis_count', 1)
                return html.Div([
                    html.I(className="fas fa-check-circle", style={'color': '#28a745', 'marginRight': '8px'}),
                    f"✅ 重复验证完成（第 {analysis_count} 次分析）"
                ], style={'color': '#28a745'})
            else:
                return html.Div(f"❌ 重复验证失败: {error_msg}", style={'color': '#dc3545'})

        except Exception as e:
            logger.error(f"重复验证异常: {e}")
            return html.Div(f"❌ 验证异常: {str(e)}", style={'color': '#dc3545'})

        except Exception as e:
            logger.error(f"[ERROR] 导出延时分布数据失败: {e}")
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
        
        logger.info(f"🔍 延时直方图点击回调被触发，click_data: {click_data}")
        print(f"🔍 延时直方图点击回调被触发，click_data: {click_data}")
        
        backend = session_manager.get_backend(session_id)
        if not backend:
            logger.warning("[WARNING] backend 为空")
            return [], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px', 'display': 'none'}, ""
        
        # 如果没有点击数据，隐藏表格
        if not click_data:
            logger.info("[WARNING] click_data 为空")
            return [], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px', 'display': 'none'}, ""
        
        if 'points' not in click_data or not click_data['points']:
            logger.info(f"[WARNING] click_data 中没有 points 或 points 为空，click_data keys: {click_data.keys() if isinstance(click_data, dict) else 'not dict'}")
            return [], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px', 'display': 'none'}, ""
        
        try:
            # 获取点击的柱状图信息
            # Plotly Histogram 点击时，points[0] 包含 'x' 字段，表示该柱状图的中心 x 坐标
            # 我们需要获取该柱状图的 x 范围
            point = click_data['points'][0]
            logger.info(f"[STATS] 点击的 point 数据: {point}")
            print(f"[STATS] 点击的 point 数据: {point}")
            
            # 对于 Histogram，点击的 point 可能包含 'x'（中心值）或 'bin' 信息
            # 我们需要根据实际的 bin 范围来筛选数据
            # 如果 point 中有 'x'，我们可以用它作为参考，但更准确的是使用 'bin' 信息
            
            # 尝试获取 bin 范围
            if 'x' in point:
                x_value = point['x']
                
                # 获取所有延时数据来估算 bin 宽度
                # 支持单算法和多算法模式
                if backend.multi_algorithm_mode and backend.multi_algorithm_manager:
                    # 多算法模式：从所有激活算法收集数据
                    active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()
                    delays_ms = []
                    for algorithm in active_algorithms:
                        if algorithm.analyzer and algorithm.analyzer.note_matcher:
                            offset_data = algorithm.analyzer.get_offset_alignment_data()
                            if offset_data:
                                delays_ms.extend([item.get('keyon_offset', 0.0) / 10.0 for item in offset_data])
                else:
                    # 单算法模式
                    offset_data = backend.analyzer.get_offset_alignment_data() if backend.analyzer else []
                    if not offset_data:
                        return [], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px', 'display': 'none'}, ""
                    delays_ms = [item.get('keyon_offset', 0.0) / 10.0 for item in offset_data]
                
                if not delays_ms:
                    return [], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px', 'display': 'none'}, ""
                
                # 方法1：尝试从 point 中获取 bin 边界信息（如果 Plotly 提供了）
                # Plotly Histogram 的点击事件可能包含 'bin' 或 'x0', 'x1' 等信息
                if 'x0' in point and 'x1' in point:
                    # 如果 Plotly 直接提供了 bin 边界，使用它（最准确）
                    delay_min = point['x0']
                    delay_max = point['x1']
                else:
                    # 方法2：估算 bin 宽度
                    # 使用 Sturges' rule 估算 bin 数量
                    n = len(delays_ms)
                    if n > 1:
                        num_bins = min(50, max(10, int(1 + 3.322 * math.log10(n))))
                    else:
                        num_bins = 10
                    
                    data_range = max(delays_ms) - min(delays_ms)
                    estimated_bin_width = data_range / num_bins if num_bins > 0 else max(1.0, data_range / 10)
                    
                    # 计算 bin 的范围（以点击的 x 为中心）
                    delay_min = x_value - estimated_bin_width / 2
                    delay_max = x_value + estimated_bin_width / 2
                    
                    # 确保范围合理（至少 1ms 宽度，避免范围太小）
                    if delay_max - delay_min < 1.0:
                        delay_min = x_value - 0.5
                        delay_max = x_value + 0.5
            else:
                # 如果没有 x 值，无法确定范围
                return [], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px', 'display': 'none'}, ""
            
            # 获取该延时范围内的数据点
            data_points = backend.get_delay_range_data_points(delay_min, delay_max)
            
            if not data_points:
                info_text = f"延时范围 [{delay_min:.2f}ms, {delay_max:.2f}ms] 内没有数据点"
                return [], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px', 'display': 'none'}, info_text
            
            # 准备表格数据
            table_data = []
            for item in data_points:
                table_data.append({
                    'algorithm_name': item.get('algorithm_name', 'N/A'),
                    'key_id': item.get('key_id', 'N/A'),
                    'delay_ms': item.get('delay_ms', 0.0),
                    'record_index': item.get('record_index', 'N/A'),
                    'replay_index': item.get('replay_index', 'N/A'),
                    'record_keyon': item.get('record_keyon', 'N/A'),
                    'replay_keyon': item.get('replay_keyon', 'N/A'),
                    'duration_offset': item.get('duration_offset', 'N/A'),
                })
            
            # 显示信息
            info_text = f"延时范围 [{delay_min:.2f}ms, {delay_max:.2f}ms] 内共有 {len(data_points)} 个数据点"
            
            # 显示表格，添加垂直滚动条，限制最大高度为600px
            table_style = {
                'overflowX': 'auto',
                'overflowY': 'auto',
                'maxHeight': '600px',
                'display': 'block'
            }
            return table_data, table_style, info_text
            
        except Exception as e:
            logger.error(f"[ERROR] 处理延时直方图点击事件失败: {e}")
            logger.error(traceback.format_exc())
            return [], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px', 'display': 'none'}, f"处理失败: {str(e)}"
    
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
        logger.info(f"[PROCESS] 延时直方图表格点击回调触发：trigger_id={trigger_id}")
        print(f"[PROCESS] 延时直方图表格点击回调触发：trigger_id={trigger_id}")
        
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
                
                # 计算平均延时
                mean_delays = {}
                if backend.multi_algorithm_mode and backend.multi_algorithm_manager and final_algorithm_name:
                    # 多算法模式
                    algorithm = backend.multi_algorithm_manager.get_algorithm(final_algorithm_name)
                    if algorithm and algorithm.analyzer:
                        mean_error_0_1ms = algorithm.analyzer.get_mean_error()
                        mean_delays[final_algorithm_name] = mean_error_0_1ms / 10.0  # 转换为毫秒
                    else:
                        logger.error(f"[ERROR] 无法获取算法 '{final_algorithm_name}' 的平均延时")
                        return current_style, [], no_update
                else:
                    # 单算法模式
                    if backend.analyzer:
                        mean_error_0_1ms = backend.analyzer.get_mean_error()
                        mean_delays[final_algorithm_name or 'default'] = mean_error_0_1ms / 10.0  # 转换为毫秒
                    else:
                        logger.error("[ERROR] 无法获取单算法模式的平均延时")
                        return current_style, [], no_update, no_update
                
                # 生成对比曲线图（包含其他算法的播放曲线）
                import spmid
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
                            # key-hammer-velocity-scatter-plot 已删除（功能与按键-力度交互效应图重复）
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
                        dcc.Store(id='key-force-interaction-selected-algorithms', data=[]),
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
    
    @app.callback(
        [Output('upload-multi-algorithm-data', 'contents', allow_duplicate=True),
         Output('upload-multi-algorithm-data', 'filename', allow_duplicate=True),
         Output('multi-algorithm-file-list', 'children', allow_duplicate=True),
         Output('multi-algorithm-upload-status', 'children', allow_duplicate=True)],
        [Input('reset-multi-algorithm-upload', 'n_clicks')],
        prevent_initial_call=True
    )
    def reset_multi_algorithm_upload(n_clicks):
        """重置多算法上传区域，清除上传状态"""
        if not n_clicks:
            return no_update, no_update, no_update, no_update

        # 重置上传组件和状态
        return None, None, html.Div(), html.Span("上传区域已重置，可以重新选择文件", style={'color': '#17a2b8'})

    @app.callback(
        [Output('multi-algorithm-upload-area', 'style', allow_duplicate=True),
         Output('multi-algorithm-management-area', 'style', allow_duplicate=True),
         Output('multi-algorithm-file-list', 'children', allow_duplicate=True),
         Output('multi-algorithm-upload-status', 'children', allow_duplicate=True),
         Output('multi-algorithm-files-store', 'data', allow_duplicate=True)],
        [Input('upload-multi-algorithm-data', 'contents')],
        [State('upload-multi-algorithm-data', 'filename'),
         State('session-id', 'data'),
         State('multi-algorithm-files-store', 'data')],
        prevent_initial_call=True
    )
    def handle_multi_file_upload(contents_list, filename_list, session_id, store_data):
        """处理多文件上传，显示文件列表供用户输入算法名称"""
        # 获取后端实例
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update, no_update, no_update, no_update, no_update
        
        # 确保多算法模式已启用
        # 确保multi_algorithm_manager已初始化
        if not backend.multi_algorithm_manager:
            backend._ensure_multi_algorithm_manager()
        
        # 确保上传区域和管理区域始终显示
        upload_style = {'display': 'block'}
        management_style = {'display': 'block'}
        
        # 使用MultiFileUploadHandler处理文件上传
        upload_handler = MultiFileUploadHandler()
        file_list, status_text, new_store_data = upload_handler.process_uploaded_files(contents_list, filename_list, store_data, backend)
        
        return upload_style, management_style, file_list, status_text, new_store_data
    
    @app.callback(
        Output({'type': 'algorithm-status', 'index': dash.dependencies.MATCH}, 'children'),
        [Input({'type': 'confirm-algorithm-btn', 'index': dash.dependencies.MATCH}, 'n_clicks')],
        [State({'type': 'algorithm-name-input', 'index': dash.dependencies.MATCH}, 'value'),
         State({'type': 'confirm-algorithm-btn', 'index': dash.dependencies.MATCH}, 'id'),
         State('multi-algorithm-files-store', 'data'),
         State('session-id', 'data')],
        prevent_initial_call=True
    )
    def confirm_add_algorithm(n_clicks, algorithm_name, button_id, store_data, session_id):
        """确认添加算法"""
        if not n_clicks or not algorithm_name or not algorithm_name.strip():
            return html.Span("请输入算法名称", style={'color': '#ffc107'})
        
        # 获取后端实例
        backend = session_manager.get_backend(session_id)
        if not backend:
            return html.Span("会话无效", style={'color': '#dc3545'})
        
        # 确保多算法模式已启用
        # 确保multi_algorithm_manager已初始化
        if not backend.multi_algorithm_manager:
            backend._ensure_multi_algorithm_manager()
        
        if not store_data or 'contents' not in store_data or 'filenames' not in store_data:
            return html.Span("文件数据丢失，请重新上传", style={'color': '#dc3545'})
        
        try:
            # 使用MultiFileUploadHandler获取文件数据
            upload_handler = MultiFileUploadHandler()
            file_id = button_id['index']
            file_data = upload_handler.get_file_data_by_id(file_id, store_data)
            
            if not file_data:
                return html.Span("文件数据无效", style={'color': '#dc3545'})
            
            content, filename = file_data
            algorithm_name = algorithm_name.strip()
            
            # 异步添加算法
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success, error_msg = loop.run_until_complete(
                backend.add_algorithm(algorithm_name, filename, content)
            )
            loop.close()
            
            if success:
                # 确保新添加的算法默认显示（is_active 应该已经是 True，但确保一下）
                algorithm = backend.multi_algorithm_manager.get_algorithm(algorithm_name) if hasattr(backend, 'multi_algorithm_manager') else None
                if algorithm:
                    algorithm.is_active = True
                    logger.info(f"[OK] 确保算法 '{algorithm_name}' 默认显示: is_active={algorithm.is_active}")
                logger.info(f"[OK] 算法 '{algorithm_name}' 添加成功")
                return html.Span("[OK] 添加成功", style={'color': '#28a745', 'fontWeight': 'bold'})
            else:
                return html.Span(f"[ERROR] {error_msg}", style={'color': '#dc3545'})
            
        except Exception as e:
            logger.error(f"[ERROR] 添加算法失败: {e}")
            logger.error(traceback.format_exc())
            return html.Span(f"添加失败: {str(e)}", style={'color': '#dc3545'})
    
    @app.callback(
        Output('algorithm-list-trigger', 'data', allow_duplicate=True),
        [Input({'type': 'algorithm-status', 'index': dash.dependencies.ALL}, 'children'),
         Input('confirm-migrate-existing-data-btn', 'n_clicks')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def trigger_algorithm_list_update(status_children, migrate_clicks, session_id):
        """当算法状态改变时触发算法列表更新"""
        import time
        # 当算法状态改变或迁移按钮被点击时，触发列表更新
        # 这会在算法添加成功后自动触发，因为 algorithm-status 会更新
        # status_children 可能是 None 或空列表（当没有算法时），需要处理
        if status_children is None:
            status_children = []
        trigger_value = time.time()
        logger.info(f"[PROCESS] 触发算法列表更新: trigger_value={trigger_value}, status_children数量={len(status_children) if status_children else 0}")
        return trigger_value
    
    @app.callback(
        [Output('main-plot', 'figure', allow_duplicate=True),
         Output('report-content', 'children', allow_duplicate=True)],
        [Input('algorithm-list-trigger', 'data'),
         Input({'type': 'algorithm-toggle', 'index': dash.dependencies.ALL}, 'value')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def update_plot_on_algorithm_change(trigger_data, toggle_values, session_id):
        """当算法添加/删除/切换时，自动更新瀑布图和报告"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update, no_update
        
        # 确保多算法模式已启用
        # 确保multi_algorithm_manager已初始化
        if not backend.multi_algorithm_manager:
            backend._ensure_multi_algorithm_manager()
        
        # 检查是否有激活的算法
        active_algorithms = backend.get_active_algorithms()
        if not active_algorithms:
            # 没有激活的算法，显示空图表
            empty_fig = _create_empty_figure_for_callback("请至少激活一个算法以查看瀑布图")
            # 使用 create_report_layout 确保包含所有必需的组件
            empty_report = create_report_layout(backend)
            return empty_fig, empty_report
        
        try:
            # 生成多算法瀑布图
            logger.info(f"[PROCESS] 更新多算法瀑布图，共 {len(active_algorithms)} 个激活算法")
            fig = backend.generate_waterfall_plot()
            
            # 生成报告内容（多算法模式下的报告）
            report_content = create_report_layout(backend)
            
            logger.info("[OK] 多算法瀑布图和报告更新完成")
            return fig, report_content
            
        except Exception as e:
            logger.error(f"[ERROR] 更新多算法瀑布图失败: {e}")
            logger.error(traceback.format_exc())
            error_fig = _create_empty_figure_for_callback(f"更新失败: {str(e)}")
            # 使用 create_report_layout 确保包含所有必需的组件
            try:
                error_report = create_report_layout(backend)
            except:
                # 如果 create_report_layout 也失败，返回包含必需组件的错误布局
                empty_fig = {}
                error_report = html.Div([
                    html.H4("更新失败", className="text-center text-danger"),
                    html.P(f"错误信息: {str(e)}", className="text-center"),
                    # 包含所有必需的图表组件（隐藏），确保回调函数不会报错
                    dcc.Graph(id='key-delay-scatter-plot', figure=empty_fig, style={'display': 'none'}),
                    dcc.Graph(id='key-delay-zscore-scatter-plot', figure=empty_fig, style={'display': 'none'}),
                    dcc.Graph(id='hammer-velocity-delay-scatter-plot', figure=empty_fig, style={'display': 'none'}),
                    # key-hammer-velocity-scatter-plot 已删除（功能与按键-力度交互效应图重复）
                    html.Div(id='offset-alignment-plot', style={'display': 'none'}),
                    html.Div([
                        dash_table.DataTable(
                            id='offset-alignment-table',
                            data=[],
                            columns=[]
                        )
                    ], style={'display': 'none'})
                ])
            return error_fig, error_report
    
    @app.callback(
        [Output('existing-data-migration-area', 'style'),
         Output('existing-data-migration-area', 'children')],
        [Input('session-id', 'data'),
         Input('confirm-migrate-existing-data-btn', 'n_clicks')],
        [State('existing-data-algorithm-name-input', 'value')],
        prevent_initial_call=True
    )
    def handle_existing_data_migration(session_id_trigger, migrate_clicks, algorithm_name):
        """处理现有数据迁移区域的显示和迁移操作"""
        logger.info(f"[PROCESS] handle_existing_data_migration: migrate_clicks={migrate_clicks}")
        
        # 从 session_id_trigger 获取 session_id（它可能是 None 或实际值）
        session_id = session_id_trigger if session_id_trigger else None
        
        backend = session_manager.get_backend(session_id)
        if not backend:
            logger.warning("[WARNING] 无法获取backend实例（handle_existing_data_migration）")
            return {'display': 'none'}, None
        
        ctx = callback_context
        if not ctx.triggered:
            return {'display': 'none'}, None
        
        trigger_id = ctx.triggered[0]['prop_id']
        logger.info(f"🔍 触发源: {trigger_id}")
        
        try:
            # 如果是会话初始化触发
            if 'session-id' in trigger_id:
                # 多算法模式始终启用
                logger.info("[INFO] 多算法模式始终启用")
                
                # 检查是否有现有分析数据
                has_existing_data = False
                existing_filename = None
                
                try:
                    if backend.analyzer and backend.analyzer.note_matcher and hasattr(backend.analyzer, 'matched_pairs') and len(backend.analyzer.matched_pairs) > 0:
                        has_existing_data = True
                        data_source_info = backend.get_data_source_info()
                        existing_filename = data_source_info.get('filename', '未知文件')
                        logger.info(f"[OK] 检测到现有分析数据: {existing_filename}")
                except Exception as e:
                    logger.warning(f"[WARNING] 检查现有数据时出错: {e}")
                    has_existing_data = False
                
                if has_existing_data:
                    # 显示迁移提示（按钮和输入框在布局中已定义，通过显示它们）
                    migration_area = dbc.Alert([
                        html.H6("检测到现有分析数据", className="mb-2", style={'fontWeight': 'bold'}),
                        html.P(f"文件: {existing_filename}", style={'fontSize': '14px', 'marginBottom': '10px'}),
                        html.P("请为这个算法输入名称，以便在多算法模式下进行对比：", style={'fontSize': '14px', 'marginBottom': '10px'}),
                        html.Div(id='migration-components-placeholder', children=[
                            html.P("请在下方输入算法名称并点击确认迁移按钮", style={'fontSize': '12px', 'color': '#6c757d'})
                        ])
                    ], color='info', className='mb-3')
                    logger.info("[OK] 显示迁移提示区域")
                    return {'display': 'block'}, migration_area
                else:
                    logger.info("[INFO] 没有现有数据需要迁移")
                    return {'display': 'none'}, None
            
            # 如果是迁移按钮触发
            elif 'confirm-migrate-existing-data-btn' in trigger_id:
                if not migrate_clicks or not algorithm_name or not algorithm_name.strip():
                    return no_update, no_update
                
                try:
                    # 确保multi_algorithm_manager已初始化
                    if not backend.multi_algorithm_manager:
                        backend._ensure_multi_algorithm_manager()
                    
                    algorithm_name = algorithm_name.strip()
                    logger.info(f"📤 开始迁移现有数据到算法: {algorithm_name}")
                    success, error_msg = backend.migrate_existing_data_to_algorithm(algorithm_name)
                    
                    if success:
                        # 隐藏迁移区域
                        logger.info("[OK] 数据迁移成功")
                        return {'display': 'none'}, None
                    else:
                        # 显示错误信息
                        logger.error(f"[ERROR] 数据迁移失败: {error_msg}")
                        error_alert = dbc.Alert([
                            html.H6("迁移失败", className="mb-2", style={'fontWeight': 'bold', 'color': '#dc3545'}),
                            html.P(f"错误: {error_msg}", style={'fontSize': '14px'})
                        ], color='danger', className='mb-3')
                        return no_update, error_alert
                except Exception as e:
                    logger.error(f"[ERROR] 迁移数据时发生异常: {e}")
                    logger.error(traceback.format_exc())
                    error_alert = dbc.Alert([
                        html.H6("迁移失败", className="mb-2", style={'fontWeight': 'bold', 'color': '#dc3545'}),
                        html.P(f"异常: {str(e)}", style={'fontSize': '14px'})
                    ], color='danger', className='mb-3')
                    return no_update, error_alert
            else:
                # 未知触发源
                logger.warning(f"[WARNING] 未知触发源: {trigger_id}")
                return {'display': 'none'}, None
                
        except Exception as e:
            logger.error(f"[ERROR] handle_existing_data_migration 发生异常: {e}")
            logger.error(traceback.format_exc())
            return {'display': 'none'}, None
        
        return {'display': 'none'}, None
    
    @app.callback(
        [Output('algorithm-list', 'children', allow_duplicate=True),
         Output('algorithm-management-status', 'children', allow_duplicate=True)],
        [Input('algorithm-list-trigger', 'data')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def update_algorithm_list(trigger_data, session_id):
        """更新算法列表显示"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return [], ""
        
        backend = session_manager.get_backend(session_id)
        if not backend:
            return [], ""
        
        # 确保多算法模式已启用
        # 确保multi_algorithm_manager已初始化
        if not backend.multi_algorithm_manager:
            backend._ensure_multi_algorithm_manager()
        
        try:
            algorithms = backend.get_all_algorithms()
            
            if not algorithms:
                return [], html.Span("暂无算法，请上传文件", style={'color': '#6c757d'})
            
            algorithm_items = []
            for alg_info in algorithms:
                alg_name = alg_info['algorithm_name']  # 内部唯一标识（用于查找）
                display_name = alg_info.get('display_name', alg_name)  # 显示名称（用于UI显示）
                filename = alg_info['filename']
                status = alg_info['status']
                # 获取is_active，如果未设置或为None，则默认为True（新上传的文件应该默认显示）
                is_active = alg_info.get('is_active')
                if is_active is None:
                    is_active = True
                    # 如果is_active为None，确保算法对象中的is_active也被设置为True
                    algorithm = backend.multi_algorithm_manager.get_algorithm(alg_name) if hasattr(backend, 'multi_algorithm_manager') else None
                    if algorithm:
                        algorithm.is_active = True
                        logger.info(f"[OK] 确保算法 '{display_name}' 默认显示: is_active={is_active}")
                color = alg_info['color']
                is_ready = alg_info['is_ready']
                
                # 状态图标
                if status == 'ready' and is_ready:
                    status_icon = html.I(className="fas fa-check-circle", style={'color': '#28a745', 'marginRight': '5px'})
                    status_text = "就绪"
                elif status == 'loading':
                    status_icon = html.I(className="fas fa-spinner fa-spin", style={'color': '#17a2b8', 'marginRight': '5px'})
                    status_text = "加载中"
                elif status == 'error':
                    status_icon = html.I(className="fas fa-exclamation-circle", style={'color': '#dc3545', 'marginRight': '5px'})
                    status_text = "错误"
                else:
                    status_icon = html.I(className="fas fa-clock", style={'color': '#ffc107', 'marginRight': '5px'})
                    status_text = "等待中"
                
                # 显示/隐藏开关
                toggle_switch = dbc.Switch(
                    id={'type': 'algorithm-toggle', 'index': alg_name},
                    label='显示',
                    value=is_active,
                    style={'fontSize': '12px'}
                )
                
                algorithm_items.append(
                    dbc.Card([
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
                                    toggle_switch,
                                    dbc.Button("删除", 
                                             id={'type': 'algorithm-delete-btn', 'index': alg_name},
                                             color='danger',
                                             size='sm',
                                             n_clicks=0,
                                             style={'marginTop': '5px', 'width': '100%'})
                                ], style={'marginLeft': '10px'})
                            ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center'})
                        ])
                    ], className='mb-2', style={'border': f'2px solid {color}', 'borderRadius': '5px'})
                )
            
            # 创建算法列表（使用列表而不是Div，保持一致性）
            algorithm_list = algorithm_items  # 直接返回列表，Dash会自动处理
            status_text = html.Span(f"共 {len(algorithms)} 个算法", style={'color': '#6c757d'})
            
            return algorithm_list, status_text
            
        except Exception as e:
            logger.error(f"[ERROR] 更新算法列表失败: {e}")
            logger.error(traceback.format_exc())
            return [], html.Span(f"更新失败: {str(e)}", style={'color': '#dc3545'})
    
    @app.callback(
        [Output('algorithm-list', 'children', allow_duplicate=True),
         Output('algorithm-management-status', 'children', allow_duplicate=True),
         Output('algorithm-list-trigger', 'data', allow_duplicate=True),
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
    def handle_algorithm_management(toggle_values, delete_clicks_list, toggle_ids, delete_ids, session_id, store_data):
        """处理算法管理操作（显示/隐藏、删除）"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update, no_update, no_update, no_update, no_update, no_update
        
        # 确保多算法模式已启用
        # 确保multi_algorithm_manager已初始化
        if not backend.multi_algorithm_manager:
            backend._ensure_multi_algorithm_manager()
        
        ctx = callback_context
        if not ctx.triggered:
            return no_update, no_update, no_update, no_update, no_update, no_update
        
        trigger_id = ctx.triggered[0]['prop_id']
        
        # 标记是否删除了算法，用于更新文件列表
        algorithm_deleted = False
        deleted_algorithm_filename = None
        
        try:
            # 解析 trigger_id，格式通常是 '{"type":"...","index":"..."}.property'
            import json
            trigger_prop_id = trigger_id.split('.')[0]
            try:
                trigger_data = json.loads(trigger_prop_id)
                algorithm_name = trigger_data.get('index', '')
            except (json.JSONDecodeError, KeyError):
                logger.error(f"无法解析 trigger_id: {trigger_id}")
                return no_update, no_update, no_update, no_update, no_update, no_update
            
            if 'algorithm-toggle' in trigger_id:
                # 根据开关的新值设置显示/隐藏状态（而不是切换）
                # 找到对应的开关索引和值
                if toggle_values and toggle_ids:
                    for i, toggle_id in enumerate(toggle_ids):
                        if toggle_id and toggle_id.get('index') == algorithm_name:
                            new_value = toggle_values[i] if i < len(toggle_values) else None
                            if new_value is not None:
                                # 获取算法对象
                                algorithm = backend.multi_algorithm_manager.get_algorithm(algorithm_name) if hasattr(backend, 'multi_algorithm_manager') else None
                                if algorithm:
                                    # 直接设置为新值，而不是切换
                                    if algorithm.is_active != new_value:
                                        algorithm.is_active = new_value
                                        logger.info(f"[OK] 算法 '{algorithm_name}' 显示状态设置为: {'显示' if new_value else '隐藏'}")
                                    else:
                                        logger.debug(f"[INFO] 算法 '{algorithm_name}' 显示状态未变化: {new_value}")
                            break
                else:
                    # 如果找不到对应的开关，使用切换方式（向后兼容）
                    backend.toggle_algorithm(algorithm_name)
            elif 'algorithm-delete-btn' in trigger_id:
                # 删除算法
                # 检查是否有点击（n_clicks > 0）
                if delete_clicks_list:
                    # 找到对应的按钮索引
                    for i, delete_id in enumerate(delete_ids):
                        if delete_id and delete_id.get('index') == algorithm_name:
                            if delete_clicks_list[i] and delete_clicks_list[i] > 0:
                                # 在删除前获取算法信息，以便从文件列表中移除
                                algorithms_before = backend.get_all_algorithms()
                                for alg_info in algorithms_before:
                                    if alg_info['algorithm_name'] == algorithm_name:
                                        deleted_algorithm_filename = alg_info.get('filename', '')
                                        break
                                
                                backend.remove_algorithm(algorithm_name)
                                algorithm_deleted = True

                                logger.info(f"[OK] 算法 '{algorithm_name}' 已删除")
                                break
                    else:
                        return no_update, no_update, no_update, no_update, no_update, no_update
                else:
                    return no_update, no_update, no_update, no_update, no_update, no_update
            else:
                return no_update, no_update, no_update, no_update, no_update, no_update
            
            # 重新获取算法列表
            algorithms = backend.get_all_algorithms()
            
            # 更新文件列表：如果删除了算法，从文件列表中移除对应的文件
            # 无论是否删除了算法，都要更新文件列表，确保只显示未添加的文件
            file_list_children = no_update
            upload_status_text = no_update
            updated_store_data = no_update

            # 获取所有已添加算法的文件名
            added_filenames = set()
            for alg_info in algorithms:
                added_filenames.add(alg_info.get('filename', ''))
                
            # 如果删除了算法，或者有store_data，都需要更新文件列表
            if algorithm_deleted or (store_data and 'filenames' in store_data):
                # 从store_data中获取文件列表
                if store_data and 'contents' in store_data and 'filenames' in store_data:
                    contents_list = store_data.get('contents', [])
                    filenames_list = store_data.get('filenames', [])
                    file_ids = store_data.get('file_ids', [])
                    
                    # 过滤出未添加的文件
                    filtered_contents = []
                    filtered_filenames = []
                    filtered_file_ids = []
                    
                    for i, filename in enumerate(filenames_list):
                        if filename not in added_filenames:
                            if i < len(contents_list):
                                filtered_contents.append(contents_list[i])
                            filtered_filenames.append(filename)
                            if i < len(file_ids):
                                filtered_file_ids.append(file_ids[i])
                    
                    # 更新store_data
                    updated_store_data = {
                        'contents': filtered_contents,
                        'filenames': filtered_filenames,
                        'file_ids': filtered_file_ids
                    }

                    # 直接生成文件列表UI，使用现有的文件ID，避免重复合并
                    from ui.multi_file_upload_handler import MultiFileUploadHandler
                    upload_handler = MultiFileUploadHandler()
                    # 直接使用过滤后的文件列表生成UI，不调用process_uploaded_files避免重复合并
                    file_items = []
                    for i, (content, filename, file_id) in enumerate(zip(
                            filtered_contents, 
                            filtered_filenames, 
                        filtered_file_ids
                    )):
                        # 确保不会显示已添加的文件（双重检查）
                        if filename not in added_filenames:
                            file_card = upload_handler.create_file_card(file_id, filename)
                            file_items.append(file_card)
                    
                    file_list_children = html.Div(file_items) if file_items else []
                    # 生成上传状态文本
                    total_files = len(filtered_filenames)
                    if total_files > 0:
                        upload_status_text = html.Span(
                            f"共 {total_files} 个文件，请为每个文件输入算法名称",
                            style={'color': '#17a2b8', 'fontWeight': 'bold'}
                        )
                    else:
                        upload_status_text = html.Span("", style={'color': '#6c757d'})
                elif algorithm_deleted:
                    # 如果删除了算法但没有store_data，清空文件列表
                    file_list_children = []
                    upload_status_text = html.Span("", style={'color': '#6c757d'})
                    updated_store_data = {'contents': [], 'filenames': [], 'file_ids': []}
            
            if not algorithms:
                # 返回空列表和状态文本，以及触发更新
                empty_list = []  # 空列表，而不是 Div
                status_text = html.Span("暂无算法，请上传文件", style={'color': '#6c757d'})
                # 如果没有算法了，也清空文件列表
                if file_list_children == no_update:
                    file_list_children = []
                if updated_store_data == no_update:
                    updated_store_data = {'contents': [], 'filenames': [], 'file_ids': []}
                if upload_status_text == no_update:
                    upload_status_text = html.Span("", style={'color': '#6c757d'})
                return empty_list, status_text, time.time(), file_list_children, upload_status_text, updated_store_data
            
            algorithm_items = []
            for alg_info in algorithms:
                alg_name = alg_info['algorithm_name']
                filename = alg_info['filename']
                status = alg_info['status']
                is_active = alg_info['is_active']
                color = alg_info['color']
                is_ready = alg_info['is_ready']
                
                if status == 'ready' and is_ready:
                    status_icon = html.I(className="fas fa-check-circle", style={'color': '#28a745', 'marginRight': '5px'})
                    status_text = "就绪"
                elif status == 'loading':
                    status_icon = html.I(className="fas fa-spinner fa-spin", style={'color': '#17a2b8', 'marginRight': '5px'})
                    status_text = "加载中"
                elif status == 'error':
                    status_icon = html.I(className="fas fa-exclamation-circle", style={'color': '#dc3545', 'marginRight': '5px'})
                    status_text = "错误"
                else:
                    status_icon = html.I(className="fas fa-clock", style={'color': '#ffc107', 'marginRight': '5px'})
                    status_text = "等待中"
                
                toggle_switch = dbc.Switch(
                    id={'type': 'algorithm-toggle', 'index': alg_name},
                    label='显示',
                    value=is_active,
                    style={'fontSize': '12px'}
                )
                
                algorithm_items.append(
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.Div([
                                    html.Span(alg_name, style={'fontWeight': 'bold', 'fontSize': '14px', 'color': color}),
                                    html.Br(),
                                    html.Small(filename, style={'color': '#6c757d', 'fontSize': '11px'}),
                                    html.Br(),
                                    html.Small([status_icon, status_text], style={'fontSize': '11px'})
                                ], style={'flex': '1'}),
                                html.Div([
                                    toggle_switch,
                                    dbc.Button("删除", 
                                             id={'type': 'algorithm-delete-btn', 'index': alg_name},
                                             color='danger',
                                             size='sm',
                                             n_clicks=0,
                                             style={'marginTop': '5px', 'width': '100%'})
                                ], style={'marginLeft': '10px'})
                            ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center'})
                        ])
                    ], className='mb-2', style={'border': f'2px solid {color}', 'borderRadius': '5px'})
                )
            
            # 创建算法列表（使用列表而不是Div，保持一致性）
            algorithm_list = algorithm_items  # 直接返回列表，Dash会自动处理
            status_text = html.Span(f"共 {len(algorithms)} 个算法", style={'color': '#6c757d'})
            
            # 如果没有更新上传状态文本，根据文件列表生成
            if upload_status_text == no_update:
                if updated_store_data != no_update and isinstance(updated_store_data, dict):
                    total_files = len(updated_store_data.get('filenames', []))
                    if total_files > 0:
                        upload_status_text = html.Span(
                            f"共 {total_files} 个文件，请为每个文件输入算法名称",
                            style={'color': '#17a2b8', 'fontWeight': 'bold'}
                        )
                    else:
                        upload_status_text = html.Span("", style={'color': '#6c757d'})
                elif store_data and isinstance(store_data, dict):
                    total_files = len(store_data.get('filenames', []))
                    # 过滤掉已添加的文件
                    added_filenames = set()
                    for alg_info in algorithms:
                        added_filenames.add(alg_info.get('filename', ''))
                    filtered_count = sum(1 for f in store_data.get('filenames', []) if f not in added_filenames)
                    if filtered_count > 0:
                        upload_status_text = html.Span(
                            f"共 {filtered_count} 个文件，请为每个文件输入算法名称",
                            style={'color': '#17a2b8', 'fontWeight': 'bold'}
                        )
                    else:
                        upload_status_text = html.Span("", style={'color': '#6c757d'})
                else:
                    upload_status_text = html.Span("", style={'color': '#6c757d'})
            
            return algorithm_list, status_text, time.time(), file_list_children, upload_status_text, updated_store_data
            
        except Exception as e:
            logger.error(f"[ERROR] 处理算法管理操作失败: {e}")
            logger.error(traceback.format_exc())
            return no_update, no_update, no_update, no_update, no_update, no_update
    
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
        logger.info(f"[PROCESS] 按键表格点击回调触发：trigger_id={trigger_id}")
        
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
                import spmid
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
        
        
        print("=" * 80)
        print("[START] handle_waterfall_click 回调被触发！")
        print("=" * 80)
        
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
                import spmid
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
                    if data_type == 'record' and index >= 0 and index < len(valid_record_data):
                        record_note = valid_record_data[index]
                        replay_note = None
                    elif data_type == 'play' and index >= 0 and index < len(valid_replay_data):
                        record_note = None
                        replay_note = valid_replay_data[index]

                    # 计算平均延时
                    mean_delays = {}
                    if not algorithm or not algorithm.analyzer:
                        print(f"[ERROR] 算法对象或分析器为空，无法计算平均延时")
                        return current_style, []

                    mean_error_0_1ms = algorithm.analyzer.get_mean_error()
                    mean_delays[algorithm_name] = mean_error_0_1ms / 10.0  # 转换为毫秒

                    detail_figure_combined = spmid.plot_note_comparison_plotly(record_note, replay_note, algorithm_name=algorithm_name, mean_delays=mean_delays)
                    print(f"[WARNING] 按键ID {key_id} 无匹配对，只绘制单侧数据")
                
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
    
    # 按键-力度交互效应图点击回调 - 显示曲线对比（悬浮窗）
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('main-plot', 'figure', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True),
         Output('key-force-interaction-plot', 'clickData', allow_duplicate=True)],
        [Input('key-force-interaction-plot', 'clickData'),
         Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State('session-id', 'data'),
         State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_key_force_interaction_plot_click(click_data, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理按键-力度交互效应图点击，显示曲线对比（悬浮窗）并调整瀑布图显示范围"""
        from dash import callback_context
        
        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            logger.debug("[WARNING] 按键-力度交互效应图点击回调：没有触发源")
            return current_style, [], no_update, no_update, no_update
        
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        logger.info(f"[PROCESS] 按键-力度交互效应图点击回调触发：trigger_id={trigger_id}")
        
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
            return modal_style, [], no_update, no_update, no_update
        
        # 如果是散点图点击
        if trigger_id == 'key-force-interaction-plot':
            logger.info(f"[PROCESS] 按键-力度交互效应图点击：click_data={click_data}")
            backend = session_manager.get_backend(session_id)
            if not backend:
                logger.warning("[WARNING] 没有找到backend")
                return current_style, [], no_update, no_update, no_update

            if not click_data or 'points' not in click_data or not click_data['points']:
                logger.warning("[WARNING] click_data为空或没有points")
                return current_style, [], no_update, no_update, no_update
            
            try:
                # 获取点击的数据点
                point = click_data['points'][0]
                logger.info(f"🔍 按键-力度交互效应图点击 - 点击点数据: {point}")
                
                if not point.get('customdata'):
                    logger.warning("[WARNING] 按键-力度交互效应图点击 - 点没有customdata")
                    return current_style, [], no_update, no_update, no_update
                
                # 安全地提取customdata
                raw_customdata = point['customdata']
                logger.info(f"🔍 按键-力度交互效应图点击 - raw_customdata类型: {type(raw_customdata)}, 值: {raw_customdata}")
                
                if isinstance(raw_customdata, list) and len(raw_customdata) > 0:
                    customdata = raw_customdata[0] if isinstance(raw_customdata[0], list) else raw_customdata
                else:
                    customdata = raw_customdata
                
                # 确保customdata是列表类型
                if not isinstance(customdata, list):
                    logger.warning(f"[WARNING] 按键-力度交互效应图点击 - customdata不是列表类型: {type(customdata)}, 值: {customdata}")
                    return current_style, [], no_update, no_update, no_update
                
                logger.info(f"🔍 按键-力度交互效应图点击 - customdata: {customdata}, 长度: {len(customdata)}")
                
                # 解析customdata
                # 多算法模式: [key_id, algorithm_display_name, orig_force, abs_delay, rel_delay, record_idx, replay_idx]
                # 单算法模式: [key_id, orig_force, abs_delay, rel_delay, record_idx, replay_idx]
                if len(customdata) < 5:
                    logger.warning(f"[WARNING] customdata长度不足：{len(customdata)}，期望至少5个元素")
                    return current_style, [], no_update
                
                # 判断是单算法还是多算法模式
                if len(customdata) >= 8:
                    # 多算法模式：有algorithm_display_name
                    key_id = customdata[0]
                    algorithm_display_name = customdata[1]
                    original_velocity = customdata[2]
                    abs_delay = customdata[3]
                    rel_delay = customdata[4]
                    log10_force = customdata[5]  # 新增log10_force字段
                    record_idx = customdata[6]
                    replay_idx = customdata[7]
                else:
                    # 单算法模式：没有algorithm_display_name
                    key_id = customdata[0]
                    algorithm_display_name = None
                    original_velocity = customdata[1]
                    abs_delay = customdata[2]
                    rel_delay = customdata[3]
                    log10_force = customdata[4] if len(customdata) > 4 else None  # 单算法模式也可能有log10_force
                    record_idx = customdata[5] if len(customdata) > 5 else None
                    replay_idx = customdata[6] if len(customdata) > 6 else None
                
                if record_idx is None or replay_idx is None:
                    logger.warning(f"[WARNING] 按键-力度交互效应图点击 - 缺少索引信息: record_idx={record_idx}, replay_idx={replay_idx}")
                    return current_style, [], no_update
                
                logger.info(f"🖱️ 按键-力度交互效应图点击: 算法={algorithm_display_name}, 按键={key_id}, 锤速={original_velocity}, record_idx={record_idx}, replay_idx={replay_idx}")
                
                # 需要将algorithm_display_name转换为algorithm_name
                algorithm_name_for_waterfall = None
                if algorithm_display_name:
                    active_algorithms = backend.get_active_algorithms()
                    for alg in active_algorithms:
                        if alg.metadata.display_name == algorithm_display_name:
                            algorithm_name_for_waterfall = alg.metadata.algorithm_name
                            break
                        # 如果display_name包含文件名后缀，尝试匹配基础名称
                        if '(' in algorithm_display_name:
                            base_name = algorithm_display_name.split('(')[0].strip()
                            if alg.metadata.display_name == base_name:
                                algorithm_name_for_waterfall = alg.metadata.algorithm_name
                                break
                
                # 计算时间信息，用于跳转时直接使用
                center_time_ms = None
                try:
                    if algorithm_name_for_waterfall:
                        # 多算法模式
                        if backend.multi_algorithm_mode and backend.multi_algorithm_manager:
                            algorithm = backend.multi_algorithm_manager.get_algorithm(algorithm_name_for_waterfall)
                            if algorithm and algorithm.analyzer and algorithm.analyzer.note_matcher:
                                matched_pairs = algorithm.analyzer.matched_pairs
                                for r_idx, p_idx, r_note, p_note in matched_pairs:
                                    if r_idx == record_idx and p_idx == replay_idx:
                                        # 计算keyon时间
                                        record_keyon = r_note.after_touch.index[0] + r_note.offset if hasattr(r_note, 'after_touch') and not r_note.after_touch.empty else r_note.offset
                                        replay_keyon = p_note.after_touch.index[0] + p_note.offset if hasattr(p_note, 'after_touch') and not p_note.after_touch.empty else p_note.offset
                                        center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0  # 转换为ms
                                        break
                                # 备用方案：从 offset_data 获取
                                if center_time_ms is None:
                                    offset_data = algorithm.analyzer.note_matcher.get_offset_alignment_data()
                                    if offset_data:
                                        for item in offset_data:
                                            if item.get('record_index') == record_idx and item.get('replay_index') == replay_idx:
                                                record_keyon = item.get('record_keyon', 0)
                                                replay_keyon = item.get('replay_keyon', 0)
                                                if record_keyon and replay_keyon:
                                                    center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0
                                                    break
                    else:
                        # 单算法模式
                        if backend.analyzer and backend.analyzer.note_matcher:
                            matched_pairs = backend.analyzer.matched_pairs
                            for r_idx, p_idx, r_note, p_note in matched_pairs:
                                if r_idx == record_idx and p_idx == replay_idx:
                                    # 计算keyon时间
                                    record_keyon = r_note.after_touch.index[0] + r_note.offset if hasattr(r_note, 'after_touch') and not r_note.after_touch.empty else r_note.offset
                                    replay_keyon = p_note.after_touch.index[0] + p_note.offset if hasattr(p_note, 'after_touch') and not p_note.after_touch.empty else p_note.offset
                                    center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0  # 转换为ms
                                    break
                            # 备用方案：从 offset_data 获取
                            if center_time_ms is None:
                                offset_data = backend.analyzer.note_matcher.get_offset_alignment_data()
                                if offset_data:
                                    for item in offset_data:
                                        if item.get('record_index') == record_idx and item.get('replay_index') == replay_idx:
                                            record_keyon = item.get('record_keyon', 0)
                                            replay_keyon = item.get('replay_keyon', 0)
                                            if record_keyon and replay_keyon:
                                                center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0
                                                break
                except Exception as e:
                    logger.warning(f"[WARNING] 计算时间信息失败: {e}")
                
                # 存储当前点击的数据点信息，用于跳转按钮
                point_info = {
                    'algorithm_name': algorithm_name_for_waterfall,
                    'record_idx': record_idx,
                    'replay_idx': replay_idx,
                    'key_id': key_id,
                    'source_plot_id': 'key-force-interaction-plot',  # 记录来源图表ID
                    'center_time_ms': center_time_ms  # 预先计算的时间信息
                }
                
                # 不自动调整瀑布图，等待用户点击跳转按钮
                waterfall_fig = no_update
                
                # 如果是多算法模式且有算法名称，使用generate_multi_algorithm_scatter_detail_plot_by_indices
                if algorithm_display_name:
                    # 多算法模式：需要找到对应的算法内部名称
                    # 从algorithm_display_name找到对应的algorithm_name
                    active_algorithms = backend.get_active_algorithms()
                    algorithm_internal_name = None
                    for alg in active_algorithms:
                        if alg.metadata.display_name == algorithm_display_name:
                            algorithm_internal_name = alg.metadata.algorithm_name
                            break
                        # 如果display_name包含文件名后缀，尝试匹配基础名称
                        if '(' in algorithm_display_name:
                            base_name = algorithm_display_name.split('(')[0].strip()
                            if alg.metadata.display_name == base_name:
                                algorithm_internal_name = alg.metadata.algorithm_name
                                break
                    
                    if not algorithm_internal_name:
                        logger.warning(f"[WARNING] 未找到对应的算法内部名称: {algorithm_display_name}")
                        return current_style, [], no_update
                    
                    logger.info(f"🔍 调用generate_multi_algorithm_scatter_detail_plot_by_indices: algorithm_name={algorithm_internal_name}, record_index={record_idx}, replay_index={replay_idx}")

                    detail_figure1, detail_figure2, detail_figure_combined = backend.generate_multi_algorithm_scatter_detail_plot_by_indices(
                        algorithm_name=algorithm_internal_name,
                        record_index=record_idx,
                        replay_index=replay_idx
                    )

                    logger.info(f"🔍 按键-力度交互效应图点击回调 - 图表生成结果: figure1={detail_figure1 is not None}, figure2={detail_figure2 is not None}, figure_combined={detail_figure_combined is not None}")
                    if detail_figure_combined is None:
                        logger.error(f"❌ 图表生成失败 - 检查算法是否存在: {algorithm_internal_name}")
                        # 检查算法是否存在
                        if backend.multi_algorithm_manager:
                            algorithm = backend.multi_algorithm_manager.get_algorithm(algorithm_internal_name)
                            logger.error(f"❌ 算法对象: {algorithm is not None}")
                            if algorithm:
                                logger.error(f"❌ 算法is_ready: {algorithm.is_ready()}")
                                logger.error(f"❌ 算法analyzer: {algorithm.analyzer is not None}")
                                if algorithm.analyzer:
                                    logger.error(f"❌ 算法note_matcher: {algorithm.analyzer.note_matcher is not None}")
                                    if algorithm.analyzer.note_matcher:
                                        matched_pairs = algorithm.analyzer.note_matcher.get_matched_pairs()
                                        logger.error(f"❌ matched_pairs长度: {len(matched_pairs)}")
                                        # 检查record_index和replay_index是否存在
                                        found_pair = False
                                        for r_idx, p_idx, r_note, p_note in matched_pairs:
                                            if r_idx == record_idx and p_idx == replay_idx:
                                                found_pair = True
                                                break
                                        logger.error(f"❌ 找到匹配对: {found_pair}")
                    
                    if detail_figure1 and detail_figure2 and detail_figure_combined:
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
                        logger.info("[OK] 按键-力度交互效应图点击回调 - 返回模态框和图表")
                        return modal_style, dcc.Graph(figure=detail_figure_combined, style={'height': '600px'}), waterfall_fig, point_info, no_update
                    else:
                        logger.warning(f"[WARNING] 按键-力度交互效应图点击回调 - 图表生成失败，部分图表为None")
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
                            html.P("图表生成失败", className="text-danger text-center")
                        ])], waterfall_fig, point_info, no_update
                else:
                    # 单算法模式：使用generate_scatter_detail_plot_by_indices
                    detail_figure1, detail_figure2, detail_figure_combined = backend.generate_scatter_detail_plot_by_indices(
                        record_index=record_idx,
                        replay_index=replay_idx
                    )
                    
                    logger.info(f"🔍 按键-力度交互效应图点击回调（单算法） - 图表生成结果: figure1={detail_figure1 is not None}, figure2={detail_figure2 is not None}, figure_combined={detail_figure_combined is not None}")
                    
                    if detail_figure1 and detail_figure2 and detail_figure_combined:
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
                        logger.info("[OK] 按键-力度交互效应图点击回调（单算法） - 返回模态框和图表")
                        return modal_style, dcc.Graph(figure=detail_figure_combined, style={'height': '600px'}), waterfall_fig, point_info, no_update
                    else:
                        logger.warning(f"[WARNING] 按键-力度交互效应图点击回调（单算法） - 图表生成失败，部分图表为None")
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
                            html.P("图表生成失败", className="text-danger text-center")
                        ])], waterfall_fig, point_info, no_update
                
            except Exception as e:
                logger.error(f"[ERROR] 生成曲线对比失败: {e}")
                
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
                    html.P(f"生成曲线对比失败: {str(e)}", className="text-danger text-center")
                ])], no_update, no_update, no_update

        # 其他情况，保持当前状态
        return current_style, [], no_update, no_update, no_update
    
    # 跳转到瀑布图按钮回调
    @app.callback(
        [Output('main-plot', 'figure', allow_duplicate=True),
         Output('main-tabs', 'value', allow_duplicate=True),
         Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('jump-source-plot-id', 'data', allow_duplicate=True)],
        [Input('jump-to-waterfall-btn', 'n_clicks')],
        [State('session-id', 'data'),
         State('current-clicked-point-info', 'data')],
        prevent_initial_call=True
    )
    def handle_jump_to_waterfall(n_clicks, session_id, point_info):
        """处理跳转到瀑布图按钮点击"""
        return waterfall_jump_handler.handle_jump_to_waterfall(n_clicks, session_id, point_info)
    
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

    # 锤速与延时散点图点击回调 - 显示曲线对比（悬浮窗）并调整瀑布图
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('main-plot', 'figure', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True),
         Output('hammer-velocity-delay-scatter-plot', 'clickData', allow_duplicate=True)],
        [Input('hammer-velocity-delay-scatter-plot', 'clickData'),
         Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State('session-id', 'data'),
         State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_hammer_velocity_scatter_click(click_data, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理锤速与延时散点图点击，显示曲线对比（悬浮窗）并调整瀑布图显示范围"""
        from dash import callback_context

        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            logger.debug("[WARNING] 散点图点击回调：没有触发源")
            return current_style, [], no_update, no_update, no_update
        
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        logger.info(f"[PROCESS] 散点图点击回调触发：trigger_id={trigger_id}")
        
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
            return modal_style, [], no_update, no_update, no_update
        
        # 如果是散点图点击
        if trigger_id == 'hammer-velocity-delay-scatter-plot':
            logger.info(f"[PROCESS] 散点图点击：click_data={click_data}")
            backend = session_manager.get_backend(session_id)
            if not backend:
                logger.warning("[WARNING] 没有找到backend")
                return current_style, [], no_update, no_update, no_update

            if not click_data or 'points' not in click_data or not click_data['points']:
                logger.warning("[WARNING] click_data为空或没有points")
                return current_style, [], no_update, no_update, no_update
            
            try:
                # 获取点击的数据点
                point = click_data['points'][0]
                logger.info(f"🔍 散点图点击 - 点击点数据: {point}")
                
                if not point.get('customdata'):
                    logger.warning("[WARNING] 散点图点击 - 点没有customdata")
                    return current_style, [], no_update, no_update, no_update
                
                # 安全地提取customdata（参考Z-Score散点图的逻辑）
                raw_customdata = point['customdata']
                logger.info(f"🔍 散点图点击 - raw_customdata类型: {type(raw_customdata)}, 值: {raw_customdata}")
                
                if isinstance(raw_customdata, list) and len(raw_customdata) > 0:
                    customdata = raw_customdata[0] if isinstance(raw_customdata[0], list) else raw_customdata
                else:
                    customdata = raw_customdata
                
                # 确保customdata是列表类型
                if not isinstance(customdata, list):
                    logger.warning(f"[WARNING] 散点图点击 - customdata不是列表类型: {type(customdata)}, 值: {customdata}")
                    return current_style, [], no_update, no_update, no_update
                
                logger.info(f"🔍 散点图点击 - customdata: {customdata}, 长度: {len(customdata)}")
                
                # 解析customdata
                # 单算法模式: [delay_ms, original_velocity, record_idx, replay_idx, key_id]
                # 多算法模式: [delay_ms, original_velocity, record_idx, replay_idx, algorithm_name, key_id]
                if len(customdata) < 5:
                    logger.warning(f"[WARNING] customdata长度不足：{len(customdata)}，期望至少5个元素")
                    return current_style, [], no_update
                
                delay_ms = customdata[0]
                original_velocity = customdata[1]  # 原始锤速值（用于显示）
                record_idx = customdata[2]
                replay_idx = customdata[3]
                # 判断是单算法还是多算法模式
                if len(customdata) >= 6:
                    # 多算法模式：有algorithm_name
                    algorithm_name = customdata[4]
                    key_id = customdata[5]
                else:
                    # 单算法模式：没有algorithm_name
                    algorithm_name = None
                    key_id = customdata[4]
                
                logger.info(f"🖱️ 散点图点击: 算法={algorithm_name}, 按键={key_id}, 锤速={original_velocity}, record_idx={record_idx}, replay_idx={replay_idx}")
                
                # 计算时间信息，用于跳转时直接使用
                center_time_ms = None
                try:
                    if algorithm_name:
                        # 多算法模式
                        if backend.multi_algorithm_mode and backend.multi_algorithm_manager:
                            algorithm = backend.multi_algorithm_manager.get_algorithm(algorithm_name)
                            if algorithm and algorithm.analyzer and algorithm.analyzer.note_matcher:
                                matched_pairs = algorithm.analyzer.matched_pairs
                                for r_idx, p_idx, r_note, p_note in matched_pairs:
                                    if r_idx == record_idx and p_idx == replay_idx:
                                        # 计算keyon时间
                                        record_keyon = r_note.after_touch.index[0] + r_note.offset if hasattr(r_note, 'after_touch') and not r_note.after_touch.empty else r_note.offset
                                        replay_keyon = p_note.after_touch.index[0] + p_note.offset if hasattr(p_note, 'after_touch') and not p_note.after_touch.empty else p_note.offset
                                        center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0  # 转换为ms
                                        break
                                # 备用方案：从 offset_data 获取
                                if center_time_ms is None:
                                    offset_data = algorithm.analyzer.note_matcher.get_offset_alignment_data()
                                    if offset_data:
                                        for item in offset_data:
                                            if item.get('record_index') == record_idx and item.get('replay_index') == replay_idx:
                                                record_keyon = item.get('record_keyon', 0)
                                                replay_keyon = item.get('replay_keyon', 0)
                                                if record_keyon and replay_keyon:
                                                    center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0
                                                    break
                    else:
                        # 单算法模式
                        if backend.analyzer and backend.analyzer.note_matcher:
                            matched_pairs = backend.analyzer.matched_pairs
                            for r_idx, p_idx, r_note, p_note in matched_pairs:
                                if r_idx == record_idx and p_idx == replay_idx:
                                    # 计算keyon时间
                                    record_keyon = r_note.after_touch.index[0] + r_note.offset if hasattr(r_note, 'after_touch') and not r_note.after_touch.empty else r_note.offset
                                    replay_keyon = p_note.after_touch.index[0] + p_note.offset if hasattr(p_note, 'after_touch') and not p_note.after_touch.empty else p_note.offset
                                    center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0  # 转换为ms
                                    break
                            # 备用方案：从 offset_data 获取
                            if center_time_ms is None:
                                offset_data = backend.analyzer.note_matcher.get_offset_alignment_data()
                                if offset_data:
                                    for item in offset_data:
                                        if item.get('record_index') == record_idx and item.get('replay_index') == replay_idx:
                                            record_keyon = item.get('record_keyon', 0)
                                            replay_keyon = item.get('replay_keyon', 0)
                                            if record_keyon and replay_keyon:
                                                center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0
                                                break
                except Exception as e:
                    logger.warning(f"[WARNING] 计算时间信息失败: {e}")
                
                # 存储当前点击的数据点信息，用于跳转按钮
                point_info = {
                    'algorithm_name': algorithm_name,
                    'record_idx': record_idx,
                    'replay_idx': replay_idx,
                    'key_id': key_id,
                    'source_plot_id': 'hammer-velocity-delay-scatter-plot',  # 记录来源图表ID
                    'center_time_ms': center_time_ms  # 预先计算的时间信息
                }
                
                # 不自动调整瀑布图，等待用户点击跳转按钮
                waterfall_fig = no_update
                
                # 如果是多算法模式且有算法名称，使用generate_multi_algorithm_scatter_detail_plot_by_indices
                if algorithm_name:
                    # 多算法模式：使用与Z-Score散点图相同的方法
                    detail_figure1, detail_figure2, detail_figure_combined = backend.generate_multi_algorithm_scatter_detail_plot_by_indices(
                        algorithm_name=algorithm_name,
                        record_index=record_idx,
                        replay_index=replay_idx
                    )
                    
                    logger.info(f"🔍 散点图点击回调 - 图表生成结果: figure1={detail_figure1 is not None}, figure2={detail_figure2 is not None}, figure_combined={detail_figure_combined is not None}")
                    
                    if detail_figure1 and detail_figure2 and detail_figure_combined:
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
                        logger.info("[OK] 散点图点击回调 - 返回模态框和图表")
                        # 将Plotly figure对象包装在dcc.Graph组件中
                        return modal_style, dcc.Graph(figure=detail_figure_combined, style={'height': '600px'}), waterfall_fig, point_info, no_update
                    else:
                        logger.warning(f"[WARNING] 散点图点击回调 - 图表生成失败，部分图表为None")
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
                            html.P("图表生成失败", className="text-danger text-center")
                        ])], waterfall_fig, point_info, no_update
                else:
                    # 单算法模式：使用generate_scatter_detail_plot_by_indices
                    detail_figure1, detail_figure2, detail_figure_combined = backend.generate_scatter_detail_plot_by_indices(
                        record_index=record_idx,
                        replay_index=replay_idx
                    )
                    
                    logger.info(f"🔍 散点图点击回调（单算法） - 图表生成结果: figure1={detail_figure1 is not None}, figure2={detail_figure2 is not None}, figure_combined={detail_figure_combined is not None}")
                    
                    if detail_figure1 and detail_figure2 and detail_figure_combined:
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
                        logger.info("[OK] 散点图点击回调（单算法） - 返回模态框和图表")
                        # 将Plotly figure对象包装在dcc.Graph组件中
                        return modal_style, dcc.Graph(figure=detail_figure_combined, style={'height': '600px'}), waterfall_fig, point_info, no_update
                    else:
                        logger.warning(f"[WARNING] 散点图点击回调（单算法） - 图表生成失败，部分图表为None")
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
                            html.P("图表生成失败", className="text-danger text-center")
                        ])], waterfall_fig, point_info, no_update
                
            except Exception as e:
                logger.error(f"[ERROR] 生成曲线对比失败: {e}")
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
                ])], no_update, no_update, no_update

        # 其他情况，保持当前状态
        return current_style, [], no_update, no_update, no_update

    # ==================== 锤速对比图点击回调 ====================
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('main-plot', 'figure', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True),
         Output('hammer-velocity-comparison-plot', 'clickData', allow_duplicate=True)],
        [Input('hammer-velocity-comparison-plot', 'clickData'),
         Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State('session-id', 'data'),
         State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_hammer_velocity_comparison_click(
        click_data: Optional[Dict[str, Any]],
        close_modal_clicks: Optional[int],
        close_btn_clicks: Optional[int],
        session_id: str,
        current_style: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[Union[html.Div, dcc.Graph]], Union[Figure, NoUpdate], Dict[str, Any], Optional[Dict[str, Any]]]:
        """处理锤速对比图点击，显示对应按键的曲线对比（悬浮窗）"""
        from dash import callback_context

        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            logger.debug("[WARNING] 锤速对比图点击回调：没有触发源")
            return current_style, [], no_update, no_update, no_update

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        logger.info(f"[PROCESS] 锤速对比图点击回调触发：trigger_id={trigger_id}")

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
            return modal_style, [], no_update, no_update, no_update

        # 如果是锤速对比图点击
        if trigger_id == 'hammer-velocity-comparison-plot' and click_data:
            logger.info(f"[PROCESS] 锤速对比图点击：click_data={click_data}")

            backend = session_manager.get_backend(session_id)
            if not backend:
                logger.warning("[WARNING] 没有找到backend")
                return current_style, [], no_update, no_update, no_update

            try:
                # 解析点击数据
                point = click_data['points'][0]
                customdata = point.get('customdata', [])

                if len(customdata) >= 4:
                    key_id = int(customdata[0])
                    algorithm_name = customdata[1]
                    record_index = int(customdata[2])
                    replay_index = int(customdata[3])

                    logger.info(f"[INFO] 点击数据解析：key_id={key_id}, algorithm_name={algorithm_name}, record_index={record_index}, replay_index={replay_index}")

                    # 生成曲线对比图
                    if backend.multi_algorithm_mode:
                        # 多算法模式：使用与Z-Score散点图相同的方法
                        detail_figure1, detail_figure2, detail_figure_combined = backend.generate_multi_algorithm_scatter_detail_plot_by_indices(
                            algorithm_name=algorithm_name,
                            record_index=record_index,
                            replay_index=replay_index
                        )
                    else:
                        # 单算法模式：使用record_index和replay_index
                        detail_figure1, detail_figure2, detail_figure_combined = backend.generate_scatter_detail_plot_by_indices(
                            record_index, replay_index
                        )

                    if detail_figure_combined is None:
                        logger.error("[ERROR] 生成曲线对比图失败")
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
                            html.P("生成曲线对比图失败", className="text-danger text-center")
                        ])], no_update, no_update, no_update

                    # 生成瀑布图并调整显示范围
                    waterfall_fig = backend.generate_waterfall_plot()
                    if waterfall_fig:
                        # 调整瀑布图的显示范围以突出显示点击的按键
                        # 这里可以根据需要调整瀑布图的x轴范围

                        # 存储点击点信息用于其他组件使用
                        point_info = {
                            'key_id': key_id,
                            'algorithm_name': algorithm_name,
                            'source': 'hammer_velocity_comparison'
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

                        return modal_style, [dcc.Graph(
                                        figure=detail_figure_combined,
                            style={'height': '800px'}
                        )], waterfall_fig, point_info, no_update

                    else:
                        logger.error("[ERROR] 生成瀑布图失败")
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
                            html.P("生成瀑布图失败", className="text-danger text-center")
                        ])], no_update, no_update, no_update

                else:
                    logger.error("[ERROR] 点击数据格式错误")
                    return current_style, [], no_update, no_update, no_update

            except Exception as e:
                logger.error(f"[ERROR] 处理锤速对比图点击失败: {e}")
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
                    html.P(f"处理点击失败: {str(e)}", className="text-danger text-center")
                ])], no_update, no_update, no_update

        # 其他情况，保持当前状态
        return current_style, [], no_update, no_update, no_update

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


            
            if record_idx is None or replay_idx is None:
                logger.warning(f"[WARNING] 数据点信息不完整: {point_info}")
                return no_update, no_update
            
            logger.info(f"[PROCESS] 跳转到瀑布图: 算法={algorithm_name}, record_idx={record_idx}, replay_idx={replay_idx}")
            
            # 获取音符时间范围
            time_range = backend.get_note_time_range_for_waterfall(algorithm_name, record_idx, replay_idx, margin_ms=500.0)
            if not time_range:
                logger.warning(f"[WARNING] 无法获取音符时间范围")
                return no_update, no_update
            
            # 生成新的瀑布图
            waterfall_fig = backend.generate_waterfall_plot()
            if not waterfall_fig:
                logger.warning(f"[WARNING] 瀑布图生成失败")
                return no_update, no_update
            
            # 更新x轴范围
            if hasattr(waterfall_fig, 'update_xaxes'):
                waterfall_fig.update_xaxes(
                    range=[time_range[0], time_range[1]],
                    title='Time (ms)',
                    showgrid=True,
                    gridcolor='lightgray',
                    gridwidth=1
                )
                logger.info(f"[OK] 瀑布图已调整到时间范围: [{time_range[0]:.1f}, {time_range[1]:.1f}]ms")
            elif hasattr(waterfall_fig, 'update_layout'):
                waterfall_fig.update_layout(
                    xaxis=dict(
                        range=[time_range[0], time_range[1]],
                        title='Time (ms)',
                        showgrid=True,
                        gridcolor='lightgray',
                        gridwidth=1
                    )
                )
                logger.info(f"[OK] 瀑布图已调整到时间范围: [{time_range[0]:.1f}, {time_range[1]:.1f}]ms (使用update_layout)")
            else:
                logger.warning(f"[WARNING] 瀑布图对象不支持更新x轴范围")
            
            # 返回更新后的瀑布图和切换到瀑布图标签页
            return waterfall_fig, 'waterfall-tab'
            
        except Exception as e:
            logger.error(f"[ERROR] 跳转到瀑布图失败: {e}")

            logger.error(traceback.format_exc())
            return no_update, no_update

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
                    if initial_data and global_index < len(initial_data):
                        note_data = initial_data[global_index]
                else:
                    # 多锤：使用initial_valid_replay_data
                    initial_data = getattr(backend.analyzer, 'initial_valid_replay_data', None)
                    if initial_data and global_index < len(initial_data):
                        note_data = initial_data[global_index]
            else:
                # 多算法模式
                active_algorithms = backend.get_active_algorithms() if hasattr(backend, 'get_active_algorithms') else []
                target_algorithm = next((alg for alg in active_algorithms if alg.metadata.algorithm_name == algorithm_name), None)
                if target_algorithm and target_algorithm.analyzer:
                    if available_data == 'record':
                        # 丢锤：使用initial_valid_record_data
                        initial_data = getattr(target_algorithm.analyzer, 'initial_valid_record_data', None)
                        if initial_data and global_index < len(initial_data):
                            note_data = initial_data[global_index]
                    else:
                        # 多锤：使用initial_valid_replay_data
                        initial_data = getattr(target_algorithm.analyzer, 'initial_valid_replay_data', None)
                        if initial_data and global_index < len(initial_data):
                            note_data = initial_data[global_index]

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
        import plotly.graph_objects as go
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


