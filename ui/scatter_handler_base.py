"""
散点图处理器基类 - 包含所有散点图处理器共享的通用方法
"""
import json
import traceback
from typing import Optional, Tuple, List, Any, Union, Dict

import pandas as pd
from dash import no_update, dcc, html
from dash._callback import NoUpdate
from dash._callback_context import callback_context

from backend.session_manager import SessionManager
from backend.piano_analysis_backend import PianoAnalysisBackend
from backend.multi_algorithm_manager import AlgorithmDataset
from utils.logger import Logger
from spmid.spmid_reader import Note


logger = Logger.get_logger()


class ScatterHandlerBase:
    """
    散点图处理器基类
    
    包含所有散点图处理器共享的通用辅助方法，提供：
    - 时间计算
    - 音符数据查找
    - 分析器管理
    - 图表生成通用逻辑
    - 统一的UI交互逻辑 (弹窗、样式、ID解析)
    """
    
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
    
    # ==================== 时间计算相关 ====================
    
    def _get_time_from_offset_data(self, note_matcher: Any, record_index: int, replay_index: int) -> Optional[Tuple[float, float]]:
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
            offset_data = note_matcher.get_precision_offset_alignment_data()
            if not offset_data:
                return None
            
            for item in offset_data:
                if item.get('record_index') == record_index and item.get('replay_index') == replay_index:
                    record_keyon = item.get('record_keyon', 0)
                    replay_keyon = item.get('replay_keyon', 0)
                    if record_keyon and replay_keyon:
                        return record_keyon, replay_keyon
            return None
        except Exception as e:
            logger.warning(f"[WARNING] 从offset_data获取时间信息失败 (record_index={record_index}, replay_index={replay_index}): {e}")
            return None
    
    def _calculate_center_time_ms(self, record_keyon: float, replay_keyon: float) -> float:
        """
        计算中心时间并转换为毫秒
        
        Args:
            record_keyon: 录制音符开始时间（0.1ms单位）
            replay_keyon: 播放音符开始时间（0.1ms单位）
            
        Returns:
            float: 中心时间（毫秒）
        """
        return ((record_keyon + replay_keyon) / 2.0) / 10.0
    
    def _calculate_center_time_for_note_pair(self, backend: PianoAnalysisBackend, record_index: int, 
                                            replay_index: int, algorithm_name: Optional[str]) -> Optional[float]:
        """
        计算指定音符对的中心时间（毫秒），仅使用精确匹配对数据
        
        Args:
            backend: 后端实例
            record_index: 录制音符索引
            replay_index: 播放音符索引
            algorithm_name: 算法名称（多算法模式）或None（单算法模式）
            
        Returns:
            Optional[float]: 中心时间（毫秒），计算失败返回None
        """
        # 获取分析器
        analyzer = self._get_analyzer_for_algorithm(backend, algorithm_name)
        if not analyzer:
            logger.warning(f"无法获取分析器")
            return None
        
        # 获取匹配对 (matched_pairs) - 处理单算法和多算法模式的差异
        if hasattr(analyzer, 'matched_pairs'):
            # SPMIDAnalyzer 或 AlgorithmDataset (如果有该属性)
            matched_pairs = analyzer.matched_pairs
        elif hasattr(analyzer, 'note_matcher') and hasattr(analyzer.note_matcher, 'matched_pairs'):
            # 常见情况：从 note_matcher 获取
            matched_pairs = analyzer.note_matcher.matched_pairs
        else:
            logger.warning(f"无法获取 matched_pairs")
            return None
        
        if not matched_pairs:
            logger.warning(f"matched_pairs 为空")
            return None
        
        # 从 matched_pairs 中查找对应的 Note 对象
        record_note, replay_note = self._find_notes_in_precision_pairs(
            matched_pairs, record_index, replay_index
        )
        
        if not record_note or not replay_note:
            logger.warning(f"⚠️ 在precision_matched_pairs中未找到Note对象: record_index={record_index}, replay_index={replay_index}")
            return None
        
        # 直接使用Note.key_on_ms并返回中心时间
        if record_note.key_on_ms is None or replay_note.key_on_ms is None:
            logger.warning(f"[WARNING] Note对象没有key_on_ms数据: record={record_note.key_on_ms}, replay={replay_note.key_on_ms}")
            return None
        
        return (record_note.key_on_ms + replay_note.key_on_ms) / 2.0
    
    
    # ==================== 音符数据查找相关 ====================
    
    def _find_notes_from_precision_data(self, backend: PianoAnalysisBackend, record_index: int, 
                                       replay_index: int, algorithm_name: Optional[str]):
        """
        从precision_matched_pairs中查找音符对象
        
        Args:
            backend: 后端实例
            record_index: 录制音符索引
            replay_index: 播放音符索引
            algorithm_name: 算法名称
            
        Returns:
            Tuple[record_note, replay_note]: 音符对象，未找到返回(None, None)
        """
        analyzer = self._get_analyzer_for_algorithm(backend, algorithm_name)
        if not analyzer:
            return None, None
        
        # 获取匹配对（统一从note_matcher获取）
        if not analyzer.note_matcher:
            logger.warning(f"[WARNING] 算法 {algorithm_name} 缺少note_matcher")
            return None, None
        
        matched_pairs = analyzer.note_matcher.matched_pairs
        
        if not matched_pairs:
            logger.warning(f"[WARNING] 算法 {algorithm_name} 的 matched_pairs 为空")
            return None, None
        
        return self._find_notes_in_precision_pairs(matched_pairs, record_index, replay_index)
    
    def _find_notes_in_precision_pairs(self, precision_matched_pairs, record_index: Any, replay_index: Any):
        """
        在精确匹配对中查找指定索引/UUID的音符对象
        
        Args:
            precision_matched_pairs: 精确匹配对列表 (record_note, replay_note, match_type, keyon_error_ms)
            record_index: 录制音符索引或UUID
            replay_index: 播放音符索引或UUID
            
        Returns:
            Tuple[record_note, replay_note]: 音符对象，未找到返回(None, None)
        """
        for rec_note, rep_note, match_type, error_ms in precision_matched_pairs:
            # 比较UUID（支持字符串比较，确保UUID一致）
            if str(rec_note.uuid) == str(record_index) and str(rep_note.uuid) == str(replay_index):
                return rec_note, rep_note
        return None, None
    
    # ==================== 分析器管理相关 ====================
    
    def _get_analyzer_for_algorithm(self, backend: PianoAnalysisBackend, algorithm_name: Optional[str]):
        """
        获取指定算法的分析器实例
        
        Args:
            backend: 后端实例
            algorithm_name: 算法名称（多算法模式）或None（单算法模式）
            
        Returns:
            SPMIDAnalyzer实例，获取失败返回None
        """
        if algorithm_name:
            # 多算法模式：根据算法名称获取对应的SPMIDAnalyzer
            if backend.multi_algorithm_manager:
                active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()
                for algorithm in active_algorithms:
                    if algorithm.metadata.algorithm_name == algorithm_name:
                        return algorithm.analyzer  # 返回analyzer而不是algorithm
            logger.warning(f"[WARNING] 未找到算法: {algorithm_name}")
            return None
        else:
            # 单算法模式：直接返回backend的analyzer
            return backend._get_current_analyzer()
    
    def _check_analyzer_or_multi_mode(self, backend):
        """检查是否有可用的分析器或多算法模式"""
        return backend._get_current_analyzer() is not None or (
            backend.multi_algorithm_manager and 
            len(backend.multi_algorithm_manager.get_active_algorithms()) > 0
        )
    
    def _check_active_algorithms(self, backend):
        """检查是否有活跃的算法"""
        return backend.multi_algorithm_manager and len(backend.multi_algorithm_manager.get_active_algorithms()) > 0
    
    def _check_at_least_two_algorithms(self, backend, error_message: str = "需要至少2个算法进行对比"):
        """检查是否有至少两个活跃的算法"""
        if not backend.multi_algorithm_manager:
            return False
        active_count = len(backend.multi_algorithm_manager.get_active_algorithms())
        if active_count < 2:
            logger.warning(f"[WARNING] {error_message}: 当前只有{active_count}个算法")
            return False
        return True
    
    # ==================== 图表生成相关 ====================
    
    def _plot_single_note(self, backend, record_note=None, replay_note=None, mean_delays=None, algorithm_name=None):
        """生成单个音符的对比图"""
        return backend.plot_generator.generate_note_comparison_plot(
            record_note, replay_note, algorithm_name=algorithm_name, 
            other_algorithm_notes=[], mean_delays=mean_delays or {}
        )
    
    def _plot_combined_notes(self, backend, record_note, replay_note, mean_delays=None, algorithm_name=None):
        """生成组合音符的对比图"""
        return backend.plot_generator.generate_note_comparison_plot(
            record_note, replay_note, algorithm_name=algorithm_name,
            other_algorithm_notes=[], mean_delays=mean_delays or {}
        )

    def _generate_key_delay_detail_plots(self, backend: PianoAnalysisBackend, click_data: Dict[str, Any]) -> Tuple[Any, Any, Any]:
        """
        统一生成按键延时图的详细曲线图的方法
        
        Args:
            backend: 后端实例
            click_data: 包含 'algorithm_name', 'record_index', 'replay_index' 的字典
            
        Returns:
            Tuple[Any, Any, Any]: (figure1, figure2, combined_figure)
        """
        algorithm_name = click_data.get('algorithm_name')
        record_index = click_data.get('record_index')
        replay_index = click_data.get('replay_index')

        if algorithm_name:
            # 多算法模式
            logger.debug(f"[DEBUG] 调用backend.generate_multi_algorithm_scatter_detail_plot_by_indices: algorithm_name='{algorithm_name}', record_index={record_index}, replay_index={replay_index}")
            return backend.generate_multi_algorithm_scatter_detail_plot_by_indices(
                algorithm_name=algorithm_name,
                record_index=record_index,
                replay_index=replay_index
            )
        else:
            # 单算法模式
            logger.debug(f"[DEBUG] 调用backend.generate_scatter_detail_plot_by_indices: record_index={record_index}, replay_index={replay_index}")
            return backend.generate_scatter_detail_plot_by_indices(
                record_index=record_index,
                replay_index=replay_index
            )
    
    # ==================== 数据解析相关 ====================
    
    def _parse_scatter_click_data(self, scatter_clickData, plot_name: str) -> Optional[Tuple[int, int, int, Optional[str]]]:
        """
        解析散点图点击数据
        
        Args:
            scatter_clickData: 点击数据
            plot_name: 图表名称（用于日志）
            
        Returns:
            Optional[Tuple[record_index, replay_index, key_id, algorithm_name]]
        """
        if not scatter_clickData or 'points' not in scatter_clickData or not scatter_clickData['points']:
            return None
        
        try:
            point = scatter_clickData['points'][0]
            customdata = point.get('customdata')
            
            if not customdata or not isinstance(customdata, (list, tuple)) or len(customdata) < 4:
                logger.warning(f"[WARNING] {plot_name}点击数据customdata格式不正确: {customdata}")
                return None
            
            record_index = customdata[0]
            replay_index = customdata[1]
            key_id = int(customdata[2]) if customdata[2] is not None else None
            algorithm_name = customdata[4] if len(customdata) > 4 else None
            
            return record_index, replay_index, key_id, algorithm_name
            
        except Exception as e:
            logger.error(f"[ERROR] 解析{plot_name}点击数据失败: {e}")
            logger.error(traceback.format_exc())
            return None
    
    def _generate_scatter_plot_with_validation(self, session_id: str, backend_method, plot_name: str,
                                               check_multi_algorithm: bool = False, 
                                               min_algorithms: int = 0,
                                               **kwargs) -> Union[Any, NoUpdate]:
        """
        生成散点图并进行验证
        
        Args:
            session_id: 会话ID
            backend_method: 后端生成方法（可调用对象）
            plot_name: 图表名称
            check_multi_algorithm: 是否检查多算法模式
            min_algorithms: 最小算法数量要求
            **kwargs: 传递给backend_method的额外参数
            
        Returns:
            图表对象或NoUpdate
        """
        backend = self.session_manager.get_backend(session_id)
        if not backend:
            logger.warning(f"[WARNING] 无法获取backend (session_id={session_id})")
            return no_update
        
        # 检查多算法模式（如果需要）
        if check_multi_algorithm:
            if not self._check_at_least_two_algorithms(backend, f"生成{plot_name}需要至少{min_algorithms}个算法"):
                return no_update
        else:
            # 检查是否有分析器或多算法模式
            if not self._check_analyzer_or_multi_mode(backend):
                logger.warning(f"[WARNING] 没有可用的分析器，无法生成{plot_name}")
                return no_update
        
        try:
            fig = backend_method(**kwargs)
            logger.info(f"[OK] {plot_name}生成成功")
            return fig
        except Exception as e:
            logger.error(f"[ERROR] 生成{plot_name}失败: {e}")
            logger.error(traceback.format_exc())
            return backend.plot_generator._create_empty_plot(f"生成{plot_name}失败: {str(e)}")
    
    # ==================== 延时计算相关 ====================
    
    def _get_specific_delay_for_note_pair(self, backend: PianoAnalysisBackend, record_index: int, 
                                          replay_index: int, algorithm_name: Optional[str]) -> Optional[float]:
        """
        获取指定音符对的特定延时值
        
        Args:
            backend: 后端实例
            record_index: 录制音符索引
            replay_index: 播放音符索引
            algorithm_name: 算法名称
            
        Returns:
            Optional[float]: 延时值（毫秒），获取失败返回None
        """
        analyzer = self._get_analyzer_for_algorithm(backend, algorithm_name)
        if not analyzer:
            return None
        
        # 从offset_data中查找延时
        try:
            if hasattr(analyzer, 'note_matcher'):
                offset_data = analyzer.note_matcher.get_precision_offset_alignment_data()
            elif hasattr(analyzer, 'offset_data'):
                offset_data = analyzer.offset_data
            else:
                return None
            
            if offset_data:
                for item in offset_data:
                    if item.get('record_index') == record_index and item.get('replay_index') == replay_index:
                        delay = item.get('offset', 0) / 10.0  # 转换为毫秒
                        return delay
        except Exception as e:
            logger.warning(f"[WARNING] 获取特定延时失败: {e}")
        
        return None
    
    # ==================== 其他辅助方法 ====================
    
    def _parse_plot_click_data(self, click_data: Dict[str, Any], plot_name: str, expected_customdata_length: int) -> Optional[Dict[str, Any]]:
        """
        解析散点图点击数据的通用逻辑
        
        Args:
            click_data: 点击数据
            plot_name: 图表名称（用于日志）
            expected_customdata_length: 期望的customdata长度
            
        Returns:
            Optional[Dict]: 解析后的数据，包含customdata和相关信息
        """
        if not click_data or 'points' not in click_data or not click_data['points']:
            logger.warning(f"[WARNING] {plot_name}点击 - click_data为空或没有points")
            return None
        
        point = click_data['points'][0]
        logger.debug(f"[DEBUG] {plot_name}点击 - 点击点数据: {point}")
        
        if not point.get('customdata'):
            logger.warning(f"[WARNING] {plot_name}点击 - 点没有customdata")
            return None
        
        # 安全地提取customdata
        raw_customdata = point['customdata']
        logger.debug(f"[DEBUG] {plot_name}点击 - raw_customdata类型: {type(raw_customdata)}, 值: {raw_customdata}")
        
        if isinstance(raw_customdata, list) and len(raw_customdata) > 0:
            customdata = raw_customdata[0] if isinstance(raw_customdata[0], list) else raw_customdata
        else:
            customdata = raw_customdata
        
        if not isinstance(customdata, list):
            logger.warning(f"[WARNING] {plot_name}点击 - customdata不是列表类型: {type(customdata)}, 值: {customdata}")
            return None
        
        logger.debug(f"[DEBUG] {plot_name}点击 - customdata: {customdata}, 长度: {len(customdata)}")
        
        if len(customdata) < expected_customdata_length:
            logger.warning(f"[WARNING] {plot_name}点击 - customdata长度不足: {len(customdata)}，期望至少{expected_customdata_length}个元素")
            return None
        
        return {
            'point': point,
            'customdata': customdata,
            'raw_customdata': raw_customdata
        }
    
    def _build_velocity_data_item(self, item, algorithm_name: str, record_note, replay_note, 
                                  record_velocity: float, replay_velocity: float):
        """
        构建速度数据项
        """
        return {
            'algorithm_name': algorithm_name,
            'display_name': item.get('display_name', algorithm_name),
            'filename': item.get('filename', ''),
            'key_id': item.get('key_id', 0),
            'record_index': item.get('record_index', 0),
            'replay_index': item.get('replay_index', 0),
            'record_velocity': record_velocity,
            'replay_velocity': replay_velocity,
            'velocity_diff': record_velocity - replay_velocity,
            'record_hammer_time_ms': item.get('record_keyon', 0) / 10.0,
            'replay_hammer_time_ms': item.get('replay_keyon', 0) / 10.0,
            'absolute_delay': item.get('relative_delay', 0),  # 使用relative_delay作为absolute_delay
            'record_note': record_note,
            'replay_note': replay_note
        }

    # ==================== 统一UI交互逻辑 ====================

    def _get_modal_style(self, show: bool = True) -> Dict[str, Any]:
        """统一获取模态框样式"""
        return {
            'display': 'block' if show else 'none',
            'position': 'fixed',
            'zIndex': '9999',
            'left': '0',
            'top': '0',
            'width': '100%',
            'height': '100%',
            'backgroundColor': 'rgba(0,0,0,0.6)',
            'backdropFilter': 'blur(5px)'
        }

    def _get_triggered_plot_id(self) -> Optional[str]:
        """解析触发回调的Plot ID"""
        ctx = callback_context
        if not ctx.triggered:
            return None
        
        trigger_id_raw = ctx.triggered[0]['prop_id'].split('.')[0]
        if trigger_id_raw.startswith('{'):
            try:
                
                return json.loads(trigger_id_raw).get('id', trigger_id_raw)
            except Exception:
                return trigger_id_raw
        return trigger_id_raw

    def _create_modal_response(self, combined_figure: Any, point_info: Dict[str, Any], height: str = '600px') -> Tuple[Dict[str, Any], List[Any], Dict[str, Any]]:
        """
        统一创建模态框响应 (所有Handler需返回此三元组)
        
        Returns:
            Tuple[style, children, point_info]
        """
        return (
            self._get_modal_style(True),
            [dcc.Graph(figure=combined_figure, style={'height': height})],
            point_info
        )

    def _handle_modal_close(self) -> Tuple[Dict[str, Any], List[Any], NoUpdate]:
        """统一处理模态框关闭逻辑"""
        return self._get_modal_style(False), [], no_update
