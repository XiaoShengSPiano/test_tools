"""
散点图回调模块 - 处理所有散点图相关的交互逻辑
包含 Z-Score、按键延时、锤速散点图的点击处理
"""

import traceback
from typing import Optional, Tuple, List, Any, Union, Dict, TypedDict


import spmid

import pandas as pd
import plotly.graph_objects as go
from plotly.graph_objs import Figure

from dash import html, dcc, no_update
from dash._callback import NoUpdate
from dash import Input, Output, State, ALL
from dash._callback_context import callback_context

from backend.session_manager import SessionManager
from backend.piano_analysis_backend import PianoAnalysisBackend
from backend.multi_algorithm_manager import AlgorithmDataset
from utils.logger import Logger

from spmid.spmid_reader import Note


logger = Logger.get_logger()



# Type definitions
class ZScoreClickData(TypedDict):
    """Z-Score散点图点击数据的类型定义"""
    record_index: int
    replay_index: int
    key_id: Optional[int]
    algorithm_name: str


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
    record_note: Note  # 录制音符对象，用于生成详细图表
    replay_note: Note  # 播放音符对象，用于生成详细图表


class ScatterPlotHandler:
    """
    散点图处理器 - 统一处理所有散点图相关的回调逻辑

    封装了 Z-Score、按键延时、锤速散点图的点击处理，
    提供统一的接口和错误处理机制。
    """

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager

    def _extract_zscore_customdata(self, raw_customdata: Any) -> Optional[ZScoreClickData]:
        """
        提取和验证Z-Score散点图的customdata

        Args:
            raw_customdata: 原始customdata

        Returns:
            Optional[ZScoreClickData]: 提取的点击数据，失败返回None
        """
        # logger.info(f"🔍 Z-Score标准化散点图点击 - raw_customdata类型: {type(raw_customdata)}, 值: {raw_customdata}")

        if isinstance(raw_customdata, list) and len(raw_customdata) > 0:
            customdata = raw_customdata[0] if isinstance(raw_customdata[0], list) else raw_customdata
        else:
            customdata = raw_customdata

        if not isinstance(customdata, list):
            logger.warning(f"[WARNING] Z-Score标准化散点图点击 - customdata不是列表类型: {type(customdata)}, 值: {customdata}")
            return None

        # logger.info(f"🔍 Z-Score标准化散点图点击 - customdata: {customdata}, 长度: {len(customdata)}")

        if len(customdata) < 5:
            logger.warning(f"[WARNING] Z-Score标准化散点图点击 - customdata长度不足: {len(customdata)}")
            return None

        # Z-Score散点图的customdata格式: [record_index, replay_index, key_id_int, delay_ms, algorithm_name]
        # 单算法模式: [record_index, replay_index, key_id_int, delay_ms] (4个元素)
        # 多算法模式: [record_index, replay_index, key_id_int, delay_ms, algorithm_name] (5个元素)
        record_index = customdata[0]
        replay_index = customdata[1]
        key_id = customdata[2] if len(customdata) > 2 else None
        algorithm_name = customdata[4] if len(customdata) > 4 else None

        # logger.info(f"🖱️ Z-Score标准化散点图点击: 算法={algorithm_name}, record_index={record_index}, replay_index={replay_index}, key_id={key_id}")

        return {
            'record_index': record_index,
            'replay_index': replay_index,
            'key_id': key_id,
            'algorithm_name': algorithm_name
        }

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

    def _calculate_center_time_for_note_pair(self, backend: PianoAnalysisBackend, record_index: int, replay_index: int, algorithm_name: Optional[str]) -> Optional[float]:
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

        # 获取precision_matched_pairs - 处理单算法和多算法模式的差异
        if hasattr(analyzer, 'precision_matched_pairs'):
            # 多算法模式：analyzer是AlgorithmDataset对象
            precision_matched_pairs = analyzer.precision_matched_pairs
        elif hasattr(analyzer, 'note_matcher') and hasattr(analyzer.note_matcher, 'precision_matched_pairs'):
            # 单算法模式：analyzer是SPMIDAnalyzer对象
            precision_matched_pairs = analyzer.note_matcher.precision_matched_pairs
        else:
            logger.warning(f"无法获取precision_matched_pairs")
            return None

        if not precision_matched_pairs:
            logger.warning(f" precision_matched_pairs为空")
            return None

        # 从precision_matched_pairs中查找对应的Note对象
        record_note, replay_note = self._find_notes_in_precision_pairs(
            precision_matched_pairs, record_index, replay_index
        )

        if not record_note or not replay_note:
            logger.warning(f"⚠️ 在precision_matched_pairs中未找到Note对象: record_index={record_index}, replay_index={replay_index}")
            return None

        # 计算keyon时间并返回中心时间
        record_keyon = self._calculate_note_keyon_time(record_note)
        replay_keyon = self._calculate_note_keyon_time(replay_note)

        if record_keyon is None or replay_keyon is None:
            logger.warning(f"[WARNING] 计算keyon时间失败: record_keyon={record_keyon}, replay_keyon={replay_keyon}")
            return None

        return self._calculate_center_time_ms(record_keyon, replay_keyon)

    def _calculate_note_keyon_time(self, note) -> Optional[float]:
        """
        计算音符的按键开始时间（0.1ms单位）

        Args:
            note: Note对象

        Returns:
            Optional[float]: keyon时间（0.1ms单位），计算失败返回None
        """
        try:
            if hasattr(note, 'after_touch') and note.after_touch is not None and hasattr(note.after_touch, 'index') and len(note.after_touch.index) > 0:
                return note.after_touch.index[0] + getattr(note, 'offset', 0)
            else:
                logger.warning(f"[WARNING] Note对象缺少after_touch和hammers数据")
                return None
        except (IndexError, AttributeError, TypeError) as e:
            logger.warning(f"[WARNING] 计算keyon时间失败: {e}")
            return None

    def _calculate_key_force_center_time(self, backend: PianoAnalysisBackend, click_data: Dict[str, Any]) -> Optional[float]:
        """
        计算按键-力度交互效应图点击的中心时间

        Args:
            backend: 后端实例
            click_data: 点击数据

        Returns:
            Optional[float]: 中心时间（毫秒），计算失败返回None
        """
        try:
            # 获取分析器
            analyzer = self._get_analyzer_for_algorithm(backend, click_data['algorithm_name'])
            if not analyzer or not analyzer.note_matcher:
                return None

            record_index = click_data['record_index']
            replay_index = click_data['replay_index']

            # 从预计算的 offset_data 中获取时间信息
            keyon_times = self._get_time_from_offset_data(analyzer.note_matcher, record_index, replay_index)
            if keyon_times:
                record_keyon, replay_keyon = keyon_times
                return self._calculate_center_time_ms(record_keyon, replay_keyon)

            return None

        except Exception as e:
            logger.warning(f"[WARNING] 计算按键-力度交互效应图时间信息失败: {e}")
            return None

    def _calculate_zscore_center_time(self, backend: PianoAnalysisBackend, click_data: ZScoreClickData) -> Optional[float]:
        """
        计算Z-Score散点图点击的中心时间

        Args:
            backend: 后端实例
            click_data: 点击数据

        Returns:
            Optional[float]: 中心时间（毫秒），计算失败返回None
        """
        try:
            # 获取分析器
            analyzer = self._get_analyzer_for_algorithm(backend, click_data['algorithm_name'])
            if not analyzer or not analyzer.note_matcher:
                return None

            record_index = click_data['record_index']
            replay_index = click_data['replay_index']

            # 从预计算的 offset_data 中获取时间信息
            keyon_times = self._get_time_from_offset_data(analyzer.note_matcher, record_index, replay_index)
            if keyon_times:
                record_keyon, replay_keyon = keyon_times
                return self._calculate_center_time_ms(record_keyon, replay_keyon)

            return None

        except Exception as e:
            logger.warning(f"[WARNING] 计算时间信息失败: {e}")
            return None

    def _generate_detail_plots(self, backend: PianoAnalysisBackend, click_data: Dict[str, Any], data_source: str = 'matched_pairs') -> Tuple[Any, Any, Any]:
        """
        生成散点图点击的详细曲线图

        Args:
            backend: 后端实例
            click_data: 点击数据，包含 algorithm_name, record_index, replay_index 等
            data_source: 数据源类型 ('matched_pairs' 或 'precision_data')

        Returns:
            Tuple[Any, Any, Any]: (录制图, 播放图, 对比图)
        """
        try:
            if data_source == 'precision_data':
                # 锤速对比图：使用专门的处理函数
                return self._generate_velocity_comparison_detail_plots(backend, click_data)
            else:
                # 按键延时图：使用专门的处理函数
                return self._generate_key_delay_detail_plots(backend, click_data)

        except Exception as e:
            logger.error(f"[ERROR] 生成详细图表失败 ({data_source}): {e}")
            logger.error(traceback.format_exc())
            return None, None, None

    def _generate_velocity_comparison_detail_plots(self, backend: PianoAnalysisBackend, click_data: Dict[str, Any]) -> Tuple[Any, Any, Any]:
        """
        生成锤速对比图的详细曲线图
        """
        # 验证必要参数
        algorithm_name = click_data.get('algorithm_name')
        record_index = click_data.get('record_index')
        replay_index = click_data.get('replay_index')

        if not algorithm_name or record_index is None or replay_index is None:
            logger.error(f"[ERROR] 锤速对比图缺少必要参数: algorithm_name={algorithm_name}, record_index={record_index}, replay_index={replay_index}")
            return None, None, None

        # 从后端查找Note对象
        record_note, replay_note = self._find_notes_from_precision_data(backend, record_index, replay_index, algorithm_name)

        if not record_note or not replay_note:
            logger.error(f"[ERROR] 无法找到锤速对比图的Note对象: algorithm_name={algorithm_name}, record_index={record_index}, replay_index={replay_index}")
            return None, None, None

        # 计算平均延时
        try:
            mean_delays = self._calculate_delays_for_velocity_comparison_click(
                backend, algorithm_name
            )
        except RuntimeError as e:
            logger.error(f"[ERROR] 计算平均延时失败: {e}")
            return None, None, None

        logger.info(f"🔧 锤速对比图使用算法平均延时: record_index={record_index}, replay_index={replay_index}, algorithm_name={algorithm_name}, mean_delays={mean_delays}")

        # 生成图表
        algorithm_name_for_plot = click_data.get('algorithm_name')
        detail_figure1 = self._plot_single_note(record_note, None, mean_delays, algorithm_name_for_plot)
        detail_figure2 = self._plot_single_note(None, replay_note, mean_delays, algorithm_name_for_plot)
        detail_figure_combined = self._plot_combined_notes(record_note, replay_note, mean_delays, algorithm_name_for_plot)

        logger.info(f"🔍 锤速对比图生成结果: figure1={detail_figure1 is not None}, figure2={detail_figure2 is not None}, figure_combined={detail_figure_combined is not None}")

        return detail_figure1, detail_figure2, detail_figure_combined

    def _generate_key_delay_detail_plots(self, backend: PianoAnalysisBackend, click_data: Dict[str, Any]) -> Tuple[Any, Any, Any]:
        """
        生成按键延时图的详细曲线图
        """
        if click_data.get('algorithm_name'):
            # 多算法模式
            algorithm_name_param = click_data['algorithm_name']
            logger.info(f"🔍 调用backend.generate_multi_algorithm_scatter_detail_plot_by_indices: algorithm_name='{algorithm_name_param}', record_index={click_data['record_index']}, replay_index={click_data['replay_index']}")

            detail_figure1, detail_figure2, detail_figure_combined = backend.generate_multi_algorithm_scatter_detail_plot_by_indices(
                algorithm_name=algorithm_name_param,
                record_index=click_data['record_index'],
                replay_index=click_data['replay_index']
            )
        else:
            # 单算法模式
            detail_figure1, detail_figure2, detail_figure_combined = backend.generate_scatter_detail_plot_by_indices(
                record_index=click_data['record_index'],
                replay_index=click_data['replay_index']
            )

        logger.info(f"🔍 按键延时图生成结果: figure1={detail_figure1 is not None}, figure2={detail_figure2 is not None}, figure_combined={detail_figure_combined is not None}")

        return detail_figure1, detail_figure2, detail_figure_combined

    def _calculate_delays_for_velocity_comparison_click(
        self,
        backend: PianoAnalysisBackend,
        algorithm_name: Optional[str]
    ) -> Dict[str, float]:
        """
        锤速对比图点击的延时计算函数

        Args:
            backend: 后端实例
            algorithm_name: 算法名称（多算法模式）或None（单算法模式）

        Returns:
            Dict[str, float]: 延时字典，格式为 {algorithm_name: delay_ms} 或 {'default': delay_ms}

        Raises:
            RuntimeError: 如果无法获取分析器
        """
        # 验证后端状态和确定延时键名
        if algorithm_name and backend.multi_algorithm_manager:
            # 多算法模式：验证算法存在并获取平均延时
            algorithm = backend.multi_algorithm_manager.get_algorithm(algorithm_name)
            if not algorithm or not algorithm.analyzer:
                error_msg = f"无法获取算法 '{algorithm_name}' 的分析器"
                logger.error(f"[ERROR] {error_msg}")
                raise RuntimeError(error_msg)
            # 获取算法平均延时
            mean_error_0_1ms = algorithm.analyzer.get_mean_error()
            delay_value = mean_error_0_1ms / 10.0
            delay_key = algorithm_name
        else:
            # 单算法模式
            analyzer = backend._get_current_analyzer()
            if analyzer:
                mean_error_0_1ms = analyzer.get_mean_error()
                delay_value = mean_error_0_1ms / 10.0
                delay_key = 'default'
            else:
                error_msg = "后端没有分析器"
                logger.error(f"[ERROR] {error_msg}")
                raise RuntimeError(error_msg)
            logger.error(f"[ERROR] {error_msg}")
            raise RuntimeError(error_msg)

        return {delay_key: delay_value}

    def _plot_single_note(self, record_note=None, replay_note=None, mean_delays=None, algorithm_name=None):
        """生成单个音符的图表"""
        try:
            return spmid.plot_note_comparison_plotly(record_note, replay_note, algorithm_name=algorithm_name, mean_delays=mean_delays)
        except Exception as e:
            logger.error(f"[ERROR] 生成单个音符图表失败: {e}")
            return None

    def _plot_combined_notes(self, record_note, replay_note, mean_delays=None, algorithm_name=None):
        """生成两个音符对比的图表"""
        try:
            return spmid.plot_note_comparison_plotly(record_note, replay_note, algorithm_name=algorithm_name, mean_delays=mean_delays)
        except Exception as e:
            logger.error(f"[ERROR] 生成对比图表失败: {e}")
            return None

    def _find_notes_from_precision_data(self, backend: PianoAnalysisBackend, record_index: int, replay_index: int, algorithm_name: Optional[str]):
        """
        从precision数据中查找对应的Note对象

        Args:
            backend: 后端实例
            record_index: 录制音符索引
            replay_index: 播放音符索引
            algorithm_name: 算法名称（多算法模式）或None（单算法模式）

        Returns:
            Tuple[Optional[Note], Optional[Note]]: (record_note, replay_note)
        """
        # 获取分析器
        analyzer = self._get_analyzer_for_algorithm(backend, algorithm_name)
        if not analyzer or not analyzer.note_matcher:
            return None, None

        # 获取precision数据
        precision_data = analyzer.note_matcher.get_precision_offset_alignment_data()
        if not precision_data:
            logger.warning("⚠️ 没有precision数据")
            return None, None

        # 从precision数据中找到对应的索引，然后从precision_matched_pairs中查找Note对象
        for item in precision_data:
            if (item.get('record_index') == record_index and
                item.get('replay_index') == replay_index):

                # 获取precision_matched_pairs - 处理单算法和多算法模式的差异
                if hasattr(analyzer, 'precision_matched_pairs'):
                    # 多算法模式：analyzer是AlgorithmDataset对象
                    precision_matched_pairs = analyzer.precision_matched_pairs
                elif hasattr(analyzer, 'note_matcher') and hasattr(analyzer.note_matcher, 'precision_matched_pairs'):
                    # 单算法模式：analyzer是SPMIDAnalyzer对象
                    precision_matched_pairs = analyzer.note_matcher.precision_matched_pairs
                else:
                    logger.warning(f"⚠️ 无法获取precision_matched_pairs")
                    return None, None

                if not precision_matched_pairs:
                    logger.warning(f"⚠️ precision_matched_pairs为空")
                    return None, None

                # 在precision_matched_pairs中查找对应的Note对象
                record_note, replay_note = self._find_notes_in_precision_pairs(
                    precision_matched_pairs, record_index, replay_index
                )

                if record_note and replay_note:
                    return record_note, replay_note
                else:
                    logger.warning(f"⚠️ 在precision_matched_pairs中未找到Note对象: record_index={record_index}, replay_index={replay_index}")
                    return None, None

        logger.warning(f"⚠️ 在precision数据中未找到匹配的索引: record_index={record_index}, replay_index={replay_index}")
        return None, None

    def _get_analyzer_for_algorithm(self, backend: PianoAnalysisBackend, algorithm_name: Optional[str]):
        """
        获取指定算法的分析器

        Args:
            backend: 后端实例
            algorithm_name: 算法名称（支持algorithm_name或display_name）

        Returns:
            analyzer: 分析器实例或None
        """
        try:
            if algorithm_name:
                # 多算法模式
                if not backend.multi_algorithm_manager:
                    logger.warning("⚠️ 多算法管理器不存在")
                    return None

                # 首先尝试作为algorithm_name（内部ID）查找
                algorithm = backend.multi_algorithm_manager.get_algorithm(algorithm_name)
                if algorithm:
                    return algorithm.analyzer

                # 如果没找到，尝试作为display_name查找
                for alg in backend.multi_algorithm_manager.get_all_algorithms():
                    if alg.metadata.display_name == algorithm_name:
                        return alg.analyzer

                # 如果还没找到，尝试作为filename查找
                for alg in backend.multi_algorithm_manager.get_all_algorithms():
                    if alg.metadata.filename == algorithm_name:
                        return alg.analyzer

                logger.warning(f"⚠️ 算法 '{algorithm_name}' 不存在（尝试了algorithm_name、display_name和filename）")
                return None
            else:
                # 单算法模式
                return backend._get_current_analyzer()

        except Exception as e:
            logger.error(f"[ERROR] 获取分析器失败: {e}")
            return None

    def _get_specific_delay_for_note_pair(self, backend: PianoAnalysisBackend, record_index: int, replay_index: int, algorithm_name: Optional[str]) -> Optional[float]:
        """
        获取指定音符对的精确延时偏移（毫秒）

        Args:
            backend: 后端实例
            record_index: 录制音符索引
            replay_index: 播放音符索引
            algorithm_name: 算法名称（多算法模式）或None（单算法模式）

        Returns:
            Optional[float]: 延时偏移（毫秒），如果找不到则返回None
        """
        # 获取分析器
        analyzer = self._get_analyzer_for_algorithm(backend, algorithm_name)
        if not analyzer or not analyzer.note_matcher:
            return None

        # 获取precision数据
        precision_data = analyzer.note_matcher.get_precision_offset_alignment_data()
        if not precision_data:
            logger.warning("⚠️ 没有precision数据")
            return None

        # 从precision数据中查找对应的延时
        for item in precision_data:
            if (item.get('record_index') == record_index and
                item.get('replay_index') == replay_index):
                keyon_offset = item.get('keyon_offset', 0)
                # 转换为毫秒（带符号）
                delay_ms = keyon_offset / 10.0
                logger.debug(f"🔍 找到精确延时: record_index={record_index}, replay_index={replay_index}, keyon_offset={keyon_offset}, delay_ms={delay_ms}")
                return delay_ms

        logger.warning(f"⚠️ 在precision数据中未找到延时信息: record_index={record_index}, replay_index={replay_index}")
        return None

    def _create_zscore_modal_response(self, detail_figure_combined: Any, point_info: Dict[str, Any]) -> Tuple[Dict[str, Any], Any, Dict[str, Any]]:
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

    def _handle_zscore_modal_close(self) -> Tuple[Dict[str, Any], List[Any], NoUpdate, NoUpdate]:
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
        return modal_style, [], no_update, no_update

    def _handle_zscore_plot_click(self, zscore_scatter_clickData: Optional[Dict[str, Any]], session_id: str, current_style: Dict[str, Any], source_plot_id: str = 'key-delay-zscore-scatter-plot') -> Tuple[Dict[str, Any], List[Any], Union[Dict[str, Any], NoUpdate]]:
        """处理Z-Score散点图点击的主要逻辑"""
        logger.info(f"🔍 散点图点击回调被触发 - source_plot_id: {source_plot_id}, clickData: {zscore_scatter_clickData is not None}")

        backend = self.session_manager.get_backend(session_id)
        if not backend:
            logger.warning("[WARNING] 没有找到backend")
            return current_style, [], no_update, no_update

        # 验证点击数据 - Z-Score图表需要至少5个元素的customdata
        parsed_data = self._parse_plot_click_data(zscore_scatter_clickData, "Z-Score标准化散点图", 5)
        if not parsed_data:
            return current_style, [], no_update, no_update

        # 提取customdata
        click_data = self._extract_zscore_customdata(parsed_data['raw_customdata'])
        if not click_data:
            return current_style, [], no_update, no_update

        # 计算中心时间
        center_time_ms = self._calculate_zscore_center_time(backend, click_data)

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
        detail_figure1, detail_figure2, detail_figure_combined = self._generate_detail_plots(backend, click_data, 'matched_pairs')

        # 检查图表生成是否成功
        if detail_figure1 and detail_figure2 and detail_figure_combined:
            modal_style, graph_component, point_info_response = self._create_zscore_modal_response(detail_figure_combined, point_info)
            return modal_style, graph_component, no_update, point_info_response, None
        else:
            logger.warning("[WARNING] Z-Score标准化散点图点击回调 - 图表生成失败，部分图表为None")
            return current_style, [], no_update, no_update, no_update

    def handle_zscore_scatter_click(self, zscore_scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理Z-Score标准化散点图点击，显示曲线对比（悬浮窗）并支持跳转到瀑布图"""
        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            logger.debug("[WARNING] Z-Score散点图点击回调：没有触发源")
            return no_update, no_update, no_update, no_update

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

        # 如果点击了关闭按钮，只有当模态框是由本回调打开时才处理
        if trigger_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            if current_style and current_style.get('display') == 'block' and zscore_scatter_clickData is not None:
                result = self._handle_zscore_modal_close()
                return result[0], result[1], result[2], result[3]
            return no_update, no_update, no_update, no_update

        # 如果是Z-Score散点图点击
        if trigger_id == 'key-delay-zscore-scatter-plot' and zscore_scatter_clickData:
            result = self._handle_zscore_plot_click(zscore_scatter_clickData, session_id, current_style, 'key-delay-zscore-scatter-plot')
            return result[0], result[1], result[2], no_update

        # 其他情况，返回默认值
        return no_update, no_update, no_update, no_update

    def handle_key_delay_scatter_click(self, scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理按键与相对延时散点图点击，显示曲线对比（悬浮窗）并支持跳转到瀑布图"""
        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            logger.debug("[WARNING] 按键与相对延时散点图点击回调：没有触发源")
            return no_update, no_update, no_update, no_update

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

        # 如果点击了关闭按钮，只有当模态框是由本回调打开时才处理
        if trigger_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            if current_style and current_style.get('display') == 'block' and scatter_clickData is not None:
                result = self._handle_zscore_modal_close()
                return result[0], result[1], result[2], result[3]
            return no_update, no_update, no_update, no_update

        # 如果是按键与相对延时散点图点击
        if trigger_id == 'key-delay-scatter-plot' and scatter_clickData:
            # 按键与相对延时散点图有不同的 customdata 格式，需要专门处理
            result = self._handle_key_delay_plot_click(scatter_clickData, session_id, current_style, 'key-delay-scatter-plot')
            return result[0], result[1], result[2], no_update

        # 其他情况，返回默认值
        return no_update, no_update, no_update, no_update

    def handle_hammer_velocity_scatter_click(self, scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理锤速与延时Z-Score标准化散点图点击，显示曲线对比（悬浮窗）"""
        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            logger.debug("[WARNING] 锤速与延时Z-Score标准化散点图点击回调：没有触发源")
            return no_update, no_update, no_update

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

        # 如果点击了关闭按钮，只有当模态框是显示状态时才处理
        # 避免与其他回调冲突（如 duration-diff-table 的回调）
        if trigger_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            # 检查模态框是否真的打开了（由本回调打开的）
            if current_style and current_style.get('display') == 'block':
                # 进一步检查：只有当有点击数据存在时才关闭（说明是从本回调打开的）
                if scatter_clickData is not None:
                    result = self._handle_zscore_modal_close()
                    return result[0], result[1], result[2]
            # 不是本回调打开的，不处理，让其他回调处理
            return no_update, no_update, no_update

        # 如果是锤速与延时Z-Score标准化散点图点击
        if trigger_id == 'hammer-velocity-delay-scatter-plot' and scatter_clickData:
            result = self._handle_hammer_velocity_plot_click(scatter_clickData, session_id, current_style, 'hammer-velocity-delay-scatter-plot')
            return result[0], result[1], result[2]

        # 其他情况，返回默认值
        return no_update, no_update, no_update

    def handle_hammer_velocity_relative_delay_plot_click(self, scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理锤速与延时Z-Score标准化散点图点击，显示曲线对比（悬浮窗）"""
        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            logger.debug("[WARNING] 锤速与延时Z-Score标准化散点图点击回调：没有触发源")
            return no_update, no_update, no_update, no_update

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

        # 如果点击了关闭按钮，只有当模态框是由本回调打开时才处理
        if trigger_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            if current_style and current_style.get('display') == 'block' and scatter_clickData is not None:
                result = self._handle_zscore_modal_close()
                return result[0], result[1], result[2], result[3]
            return no_update, no_update, no_update, no_update

        # 如果是锤速与延时Z-Score标准化散点图点击
        if trigger_id == 'hammer-velocity-relative-delay-scatter-plot' and scatter_clickData:
            result = self._handle_hammer_velocity_relative_delay_plot_click(scatter_clickData, session_id, current_style, 'hammer-velocity-relative-delay-scatter-plot')
            return result[0], result[1], result[2], no_update

        # 其他情况，返回默认值
        return no_update, no_update, no_update, no_update

    def _handle_hammer_velocity_relative_delay_plot_click(self, scatter_clickData, session_id, current_style, source_plot_id='hammer-velocity-relative-delay-scatter-plot'):
        """处理锤速与延时Z-Score标准化散点图点击的主要逻辑"""
        logger.info(f"🔍 锤速与延时Z-Score标准化散点图点击回调被触发 - source_plot_id: {source_plot_id}, clickData: {scatter_clickData is not None}")

        # 验证点击数据
        if 'points' not in scatter_clickData or len(scatter_clickData['points']) == 0:
            logger.warning("[WARNING] 锤速与延时Z-Score标准化散点图点击回调 - scatter_clickData无效或没有points")
            return current_style, [], no_update, no_update

        point = scatter_clickData['points'][0]

        if not point.get('customdata'):
            logger.warning("[WARNING] 锤速与延时Z-Score标准化散点图点击 - 点没有customdata")
            return current_style, [], no_update, no_update

        # 提取customdata - 锤速与延时Z-Score标准化散点图格式: [delay_ms, original_velocity, record_idx, replay_idx, algorithm_name, key_id]
        raw_customdata = point['customdata']

        if isinstance(raw_customdata, list) and len(raw_customdata) > 0:
            customdata = raw_customdata[0] if isinstance(raw_customdata[0], list) else raw_customdata
        else:
            customdata = raw_customdata

        if not isinstance(customdata, list) or len(customdata) < 6:
            logger.warning(f"[WARNING] 锤速与延时Z-Score标准化散点图点击 - customdata无效: {customdata}")
            return current_style, [], no_update, no_update

        # 解析锤速与延时Z-Score标准化散点图的customdata格式: [delay_ms, original_velocity, record_idx, replay_idx, algorithm_name, key_id]
        delay_ms = customdata[0]
        original_velocity = customdata[1]
        record_index = customdata[2]
        replay_index = customdata[3]
        algorithm_name = customdata[4]
        key_id = customdata[5]

        logger.info(f"🖱️ 锤速与延时Z-Score标准化散点图点击: 算法={algorithm_name}, 按键={key_id}, record_index={record_index}, replay_index={replay_index}")

        key_delay_click_data = {
            'points': [{
                'customdata': [record_index, replay_index, key_id, delay_ms, algorithm_name]  # 按键与相对延时散点图的customdata格式
            }]
        }

        result = self._handle_key_delay_plot_click(key_delay_click_data, session_id, current_style, 'hammer-velocity-relative-delay-scatter-plot')

        # 如果成功，更新点信息以包含锤速相关信息
        if result[0].get('display') == 'block' and len(result) > 2 and isinstance(result[2], dict):
            # 更新点信息，添加锤速信息
            result[2]['锤速'] = f"{original_velocity:.0f}"
            result[2]['相对延时'] = f"{delay_ms:.2f}ms"
            result[2]['绝对延时'] = f"{delay_ms:.2f}ms"

        return result

    def _handle_hammer_velocity_plot_click(self, scatter_clickData, session_id, current_style, source_plot_id='hammer-velocity-delay-scatter-plot'):
        """处理锤速与延时Z-Score标准化散点图点击的主要逻辑 """
        logger.info(f"🔍 锤速与延时Z-Score标准化散点图点击回调被触发 - source_plot_id: {source_plot_id}, clickData: {scatter_clickData is not None}")

        # 验证点击数据
        if 'points' not in scatter_clickData or len(scatter_clickData['points']) == 0:
            logger.warning("[WARNING] 锤速与延时Z-Score标准化散点图点击回调 - scatter_clickData无效或没有points")
            return current_style, [], no_update, no_update

        point = scatter_clickData['points'][0]

        if not point.get('customdata'):
            logger.warning("[WARNING] 锤速与延时Z-Score标准化散点图点击 - 点没有customdata")
            return current_style, [], no_update, no_update

        # 提取customdata - 锤速与延时Z-Score标准化散点图格式: [delay_ms, original_velocity, record_idx, replay_idx, algorithm_name, key_id]
        raw_customdata = point['customdata']

        if isinstance(raw_customdata, list) and len(raw_customdata) > 0:
            customdata = raw_customdata[0] if isinstance(raw_customdata[0], list) else raw_customdata
        else:
            customdata = raw_customdata

        if not isinstance(customdata, list) or len(customdata) < 6:
            logger.warning(f"[WARNING] 锤速与延时Z-Score标准化散点图点击 - customdata无效: {customdata}")
            return current_style, [], no_update, no_update

        # 解析锤速与延时Z-Score标准化散点图的customdata格式: [delay_ms, original_velocity, record_idx, replay_idx, algorithm_name, key_id]
        delay_ms = customdata[0]
        original_velocity = customdata[1]
        record_index = customdata[2]
        replay_index = customdata[3]
        algorithm_name = customdata[4]
        key_id = customdata[5]

        logger.info(f"🖱️ 锤速与延时Z-Score标准化散点图点击: 算法={algorithm_name}, 按键={key_id}, record_index={record_index}, replay_index={replay_index}")

        key_delay_click_data = {
            'points': [{
                'customdata': [record_index, replay_index, key_id, delay_ms, algorithm_name]  # 按键与相对延时散点图的customdata格式
            }]
        }

        result = self._handle_key_delay_plot_click(key_delay_click_data, session_id, current_style, 'hammer-velocity-delay-scatter-plot')

        # 如果成功，更新点信息以包含锤速相关信息
        if result[0].get('display') == 'block' and len(result) > 2 and isinstance(result[2], dict):
            # 更新点信息，添加锤速信息
            result[2]['锤速'] = f"{original_velocity:.0f}"
            result[2]['延时'] = f"{delay_ms:.2f}ms"
            result[2]['Z-Score延时'] = f"{delay_ms:.2f}ms"

        return result

    def _handle_key_delay_plot_click(self, scatter_clickData, session_id, current_style, source_plot_id='key-delay-scatter-plot'):
        """
        处理按键与相对延时散点图点击的主要逻辑

        Args:
            scatter_clickData: 点击数据
            session_id: 会话ID
            current_style: 当前样式
            source_plot_id: 来源图表ID

        Returns:
            Tuple: (modal_style, graph_component, point_info_response)
        """
        logger.info(f"🔍 按键与相对延时散点图点击回调被触发 - source_plot_id: {source_plot_id}")

        # 获取后端
        backend = self.session_manager.get_backend(session_id)
        if not backend:
            logger.warning("[WARNING] 没有找到backend")
            return current_style, [], no_update, no_update

        # 解析点击数据
        click_info = self._parse_scatter_click_data(scatter_clickData, "按键与相对延时散点图")
        if not click_info:
            return current_style, [], no_update, no_update

        record_index, replay_index, key_id, algorithm_name = click_info
        logger.info(f"🖱️ 按键与相对延时散点图点击: 算法={algorithm_name}, 按键={key_id}, record_index={record_index}, replay_index={replay_index}")

        # 计算中心时间
        center_time_ms = self._calculate_center_time_for_note_pair(backend, record_index, replay_index, algorithm_name)

        # 构建点信息
        point_info = {
            'algorithm_name': algorithm_name,
            'record_idx': record_index,
            'replay_idx': replay_index,
            'key_id': key_id,
            'source_plot_id': source_plot_id,
            'center_time_ms': center_time_ms
        }

        # 生成详细曲线图
        detail_figure1, detail_figure2, detail_figure_combined = self._generate_detail_plots(backend, {
            'algorithm_name': algorithm_name,
            'record_index': record_index,
            'replay_index': replay_index
        }, 'matched_pairs')

        # 检查图表生成是否成功
        if detail_figure1 and detail_figure2 and detail_figure_combined:
            modal_style, graph_component, point_info_response = self._create_zscore_modal_response(detail_figure_combined, point_info)
            return modal_style, graph_component, point_info_response
        else:
            logger.warning("[WARNING] 按键与相对延时散点图点击回调 - 图表生成失败，部分图表为None")
            return current_style, [], no_update, no_update

    def _parse_scatter_click_data(self, scatter_clickData, plot_name: str) -> Optional[Tuple[int, int, int, Optional[str]]]:
        """
        解析散点图点击数据

        Args:
            scatter_clickData: 点击数据
            plot_name: 图表名称（用于日志）

        Returns:
            Optional[Tuple[int, int, int, Optional[str]]]: (record_index, replay_index, key_id, algorithm_name)
        """
        # 验证点击数据
        if 'points' not in scatter_clickData or len(scatter_clickData['points']) == 0:
            logger.warning(f"[WARNING] {plot_name}点击回调 - scatter_clickData无效或没有points")
            return None

        point = scatter_clickData['points'][0]
        logger.info(f"🔍 {plot_name}点击 - 点击点数据: {point}")

        if not point.get('customdata'):
            logger.warning(f"[WARNING] {plot_name}点击 - 点没有customdata")
            return None

        # 提取customdata
        raw_customdata = point['customdata']
        logger.info(f"🔍 {plot_name}点击 - raw_customdata类型: {type(raw_customdata)}, 值: {raw_customdata}")

        if isinstance(raw_customdata, list) and len(raw_customdata) > 0:
            customdata = raw_customdata[0] if isinstance(raw_customdata[0], list) else raw_customdata
        else:
            customdata = raw_customdata

        if not isinstance(customdata, list):
            logger.warning(f"[WARNING] {plot_name}点击 - customdata不是列表类型: {type(customdata)}, 值: {customdata}")
            return None

        logger.info(f"🔍 {plot_name}点击 - customdata: {customdata}, 长度: {len(customdata)}")

        if len(customdata) < 4:
            logger.warning(f"[WARNING] {plot_name}点击 - customdata长度不足: {len(customdata)}")
            return None

        # 解析数据: [record_index, replay_index, key_id, delay_ms, display_name?, ...]
        record_index = customdata[0]
        replay_index = customdata[1]
        key_id = customdata[2]
        algorithm_name = customdata[4] if len(customdata) > 4 else None

        return record_index, replay_index, key_id, algorithm_name

    def _generate_scatter_plot_with_validation(self, session_id: str, backend_method, plot_name: str,
                                             prerequisite_check=None, validation_func=None) -> Union[Any, NoUpdate]:
        """
        通用的散点图生成方法，包含会话管理、前提条件检查、错误处理

        Args:
            session_id: 会话ID
            backend_method: 后端生成图表的方法
            plot_name: 图表名称（用于日志）
            prerequisite_check: 前提条件检查函数，返回(True, None)或(False, error_message)
            validation_func: 图表验证函数，用于验证生成结果的正确性

        Returns:
            图表对象或NoUpdate
        """
        backend = self.session_manager.get_backend(session_id)
        if not backend:
            return no_update

        try:
            # 执行前提条件检查
            if prerequisite_check:
                check_passed, error_msg = prerequisite_check(backend)
                if not check_passed:
                    logger.warning(f"[WARNING] {error_msg}")
                    return backend.plot_generator._create_empty_plot(error_msg)

            # 生成图表
            fig = backend_method()

            # 执行验证（如果提供）
            if validation_func and fig:
                validation_func(fig)

            logger.info(f"[OK] {plot_name}生成成功")
            return fig

        except Exception as e:
            logger.error(f"[ERROR] 生成{plot_name}失败: {e}")
            logger.error(traceback.format_exc())
            return backend.plot_generator._create_empty_plot(f"生成{plot_name}失败: {str(e)}")

    def _check_analyzer_or_multi_mode(self, backend):
        """检查是否有至少2个活跃算法（Z-Score图表需要至少2个算法进行对比）"""
        try:
            active_algorithms = backend.get_active_algorithms()
            has_at_least_two_algorithms = bool(active_algorithms) and len(active_algorithms) >= 2
            return has_at_least_two_algorithms, "Z-Score标准化散点图需要至少2个算法进行对比"
        except Exception:
            return False, "获取激活算法失败"

    def _check_active_algorithms(self, backend):
        """检查是否有激活的算法"""
        try:
            active_algorithms = backend.get_active_algorithms()
            return bool(active_algorithms), "没有激活的算法，跳过散点图生成"
        except Exception:
            return False, "获取激活算法失败"

    def _check_at_least_two_algorithms(self, backend, error_message: str = "需要至少2个算法进行对比"):
        """检查是否有至少2个激活的算法"""
        try:
            active_algorithms = backend.get_active_algorithms()
            has_at_least_two = bool(active_algorithms) and len(active_algorithms) >= 2
            return has_at_least_two, error_message
        except Exception:
            return False, "获取激活算法失败"

    def _validate_zscore_plot(self, fig):
        """验证Z-Score图表是否正确生成"""
        if hasattr(fig, 'data') and len(fig.data) > 0:
            first_trace = fig.data[0]
            if hasattr(first_trace, 'y') and len(first_trace.y) > 0:
                first_y = first_trace.y[0] if hasattr(first_trace.y, '__getitem__') else first_trace.y
                logger.info(f"🔍 Z-Score图表验证: 第一个数据点的y值={first_y} (应该是Z-Score值，通常在-3到3之间)")

    def generate_zscore_scatter_plot(self, session_id: str) -> Union[Any, NoUpdate]:
        """生成按键与延时Z-Score标准化散点图"""
        return self._generate_scatter_plot_with_validation(
            session_id,
            lambda: self.session_manager.get_backend(session_id).generate_key_delay_zscore_scatter_plot(),
            "按键与延时Z-Score标准化散点图",
            prerequisite_check=self._check_analyzer_or_multi_mode,
            validation_func=self._validate_zscore_plot
        )

    def generate_hammer_velocity_scatter_plot(self, session_id: str) -> Union[Any, NoUpdate]:
        """生成锤速与延时Z-Score标准化散点图（需要至少2个算法）"""
        return self._generate_scatter_plot_with_validation(
            session_id,
            lambda: self.session_manager.get_backend(session_id).generate_hammer_velocity_delay_scatter_plot(),
            "锤速与延时Z-Score标准化散点图",
            prerequisite_check=lambda backend: self._check_at_least_two_algorithms(backend, "锤速与延时Z-Score标准化散点图需要至少2个算法进行对比")
        )

    def generate_hammer_velocity_relative_delay_scatter_plot(self, session_id: str) -> Union[Any, NoUpdate]:
        """生成锤速与相对延时散点图"""
        return self._generate_scatter_plot_with_validation(
            session_id,
            lambda: self.session_manager.get_backend(session_id).generate_hammer_velocity_relative_delay_scatter_plot(),
            "锤速与相对延时散点图",
            prerequisite_check=self._check_active_algorithms
        )

    def handle_generate_hammer_velocity_comparison_plot(self, report_content: html.Div, session_id: str) -> Figure:
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
        backend = self.session_manager.get_backend(session_id)
        if not backend:
            return go.Figure()  # 返回空图表而不是 no_update

        try:
            logger.info("[DEBUG] 开始生成锤速对比图")

            # 验证环境条件
            if not self._validate_velocity_comparison_prerequisites(backend):
                logger.warning("[WARNING] 锤速对比图前提条件验证失败")
                return go.Figure()  # 返回空图表

            # 收集锤速数据
            logger.info("[DEBUG] 开始收集锤速数据")
            velocity_data = self._collect_velocity_comparison_data(backend)
            logger.info(f"[DEBUG] 收集到 {len(velocity_data)} 个锤速数据点")

            if not velocity_data:
                logger.warning("[WARNING] 没有收集到锤速数据")
                return go.Figure()  # 返回空图表

            # 生成对比图表
            logger.info("[DEBUG] 开始生成锤速对比图表")
            fig = self._create_velocity_comparison_plot(velocity_data)
            logger.info("[DEBUG] 锤速对比图表生成完成")
            return fig

        except Exception as e:
            logger.error(f"[ERROR] 生成锤速对比图失败: {e}")
            logger.error(traceback.format_exc())
            return go.Figure()  # 返回空图表

    def handle_key_force_interaction_plot_click(
        self, click_data: Optional[Dict[str, Any]],
        close_modal_clicks: Optional[int],
        close_btn_clicks: Optional[int],
        session_id: str,
        current_style: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[Union[html.Div, dcc.Graph]], Union[Figure, NoUpdate], Dict[str, Any], Optional[Dict[str, Any]]]:
        """处理按键-力度交互效应图点击，显示对应按键的曲线对比（悬浮窗）"""
        from dash import callback_context

        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            logger.debug("[WARNING] 按键-力度交互效应图点击回调：没有触发源")
            return current_style, [], no_update, no_update, no_update

        trigger_prop = ctx.triggered[0]['prop_id']
        trigger_id = trigger_prop.split('.')[0]
        logger.info(f"[INFO] 按键-力度交互效应图点击回调触发：prop_id={trigger_prop}, trigger_id={trigger_id}, click_data={click_data is not None}, close_modal_clicks={close_modal_clicks}, close_btn_clicks={close_btn_clicks}")

        # 如果点击了关闭按钮，只有当模态框是由本回调打开时才处理
        if trigger_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            if current_style and current_style.get('display') == 'block' and click_data is not None:
                result = self._handle_modal_close_trigger()
                return result[0], result[1], result[2], result[3]
            return no_update, no_update, no_update, no_update, no_update

        # 如果是按键-力度交互效应图点击
        if trigger_id == 'key-force-interaction-plot':
            if not click_data or 'points' not in click_data or not click_data['points']:
                logger.warning("[WARNING] 按键-力度交互效应图点击 - click_data无效")
                return current_style, [], no_update, no_update, no_update
            return self._handle_key_force_interaction_plot_click_logic(click_data, session_id, current_style)

        # 默认返回
        return current_style, [], no_update, no_update, no_update

    def _handle_modal_close_trigger(self) -> Tuple[Dict[str, Any], List[Union[html.Div, dcc.Graph]], Union[Figure, NoUpdate], Dict[str, Any], Optional[Dict[str, Any]]]:
        """处理模态框关闭按钮的通用逻辑"""
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
        logger.info(f"🔍 {plot_name}点击 - 点击点数据: {point}")

        if not point.get('customdata'):
            logger.warning(f"[WARNING] {plot_name}点击 - 点没有customdata")
            return None

        # 安全地提取customdata
        raw_customdata = point['customdata']
        logger.info(f"{plot_name}点击 - raw_customdata类型: {type(raw_customdata)}, 值: {raw_customdata}")

        if isinstance(raw_customdata, list) and len(raw_customdata) > 0:
            customdata = raw_customdata[0] if isinstance(raw_customdata[0], list) else raw_customdata
        else:
            customdata = raw_customdata

        if not isinstance(customdata, list):
            logger.warning(f"[WARNING] {plot_name}点击 - customdata不是列表类型: {type(customdata)}, 值: {customdata}")
            return None

        logger.info(f"🔍 {plot_name}点击 - customdata: {customdata}, 长度: {len(customdata)}")

        if len(customdata) < expected_customdata_length:
            logger.warning(f"[WARNING] {plot_name}点击 - customdata长度不足: {len(customdata)}，期望至少{expected_customdata_length}个元素")
            return None

        return {
            'point': point,
            'customdata': customdata,
            'raw_customdata': raw_customdata
        }

    def _handle_key_force_interaction_plot_click_logic(self, click_data, session_id, current_style):
        """处理按键-力度交互效应图点击的具体逻辑"""
        logger.info(f"[PROCESS] 按键-力度交互效应图点击：click_data={click_data}")

        backend = self.session_manager.get_backend(session_id)
        if not backend:
            logger.warning("[WARNING] 没有找到backend")
            return current_style, [], no_update, no_update, no_update

        try:
            # 解析点击数据 - 按键-力度交互效应图需要至少7个元素的customdata
            parsed_data = self._parse_plot_click_data(click_data, "按键-力度交互效应图", 7)
            if not parsed_data:
                return current_style, [], no_update, no_update, no_update

            customdata = parsed_data['customdata']

            # 按键-力度交互效应图的customdata格式: [key_id, algorithm_name, replay_velocity, relative_delay, absolute_delay, record_index, replay_index]
            key_id = customdata[0]
            algorithm_display_name = customdata[1] if customdata[1] else None
            replay_velocity = customdata[2]
            relative_delay = customdata[3]
            absolute_delay = customdata[4]
            record_idx = customdata[5]
            replay_idx = customdata[6]

            if record_idx is None or replay_idx is None:
                logger.warning(f"[WARNING] 按键-力度交互效应图点击 - 缺少索引信息: record_idx={record_idx}, replay_idx={replay_idx}")
                return current_style, [], no_update, no_update, no_update

            logger.info(f"🖱️ 按键-力度交互效应图点击: 算法={algorithm_display_name}, 按键={key_id}, 锤速={replay_velocity}, record_idx={record_idx}, replay_idx={replay_idx}")

            # 生成详细曲线图
            detail_figure1, detail_figure2, detail_figure_combined = self._generate_detail_plots(backend, {
                'algorithm_name': algorithm_display_name,
                'record_index': record_idx,
                'replay_index': replay_idx
            }, 'matched_pairs')

            # 计算中心时间用于瀑布图跳转
            center_time_ms = self._calculate_key_force_center_time(backend, {
                'algorithm_name': algorithm_display_name,
                'record_index': record_idx,
                'replay_index': replay_idx
            })

            point_info = {
                'algorithm_name': algorithm_display_name,
                'record_idx': record_idx,
                'replay_idx': replay_idx,
                'key_id': key_id,
                'source_plot_id': 'key-force-interaction-plot',
                'center_time_ms': center_time_ms
            }

            # 检查图表生成是否成功
            if detail_figure1 and detail_figure2 and detail_figure_combined:
                modal_style, graph_component, point_info_response = self._create_zscore_modal_response(detail_figure_combined, point_info)
                return modal_style, graph_component, no_update, point_info_response, None
            else:
                logger.warning("[WARNING] 按键-力度交互效应图点击回调 - 图表生成失败，部分图表为None")
                return current_style, [], no_update, no_update, no_update

        except Exception as e:
            logger.error(f"[ERROR] 按键-力度交互效应图点击处理失败: {e}")
            logger.error(traceback.format_exc())
            return current_style, [], no_update, no_update, no_update

    def _handle_hammer_velocity_comparison_click_logic(self, click_data, session_id, current_style):
        """处理锤速对比图点击的具体逻辑"""
        logger.info(f"[PROCESS] 锤速对比图点击：click_data={click_data}")

        backend = self.session_manager.get_backend(session_id)
        if not backend:
            logger.warning("[WARNING] 没有找到backend")
            return current_style, [], no_update, no_update, no_update

        try:
            # 解析点击数据 - 锤速对比图需要至少8个元素的customdata
            parsed_data = self._parse_plot_click_data(click_data, "锤速对比图", 8)
            if not parsed_data:
                return current_style, [], no_update, no_update, no_update

            customdata = parsed_data['customdata']

            # 解析锤速对比图的customdata格式: [key_id, algorithm_name, record_velocity, replay_velocity, velocity_diff, absolute_delay, record_index, replay_index]
            key_id = int(customdata[0])
            algorithm_name = customdata[1]
            record_index = int(customdata[6])  # record_index在第7位（索引6）
            replay_index = int(customdata[7])  # replay_index在第8位（索引7）

            logger.info(f"🖱️ 锤速对比图点击: 算法={algorithm_name}, 按键={key_id}, record_index={record_index}, replay_index={replay_index}")

            # 构造click_data，包含算法名称、索引信息和customdata
            plot_click_data = {
                'algorithm_name': algorithm_name,
                'record_index': record_index,
                'replay_index': replay_index,
                'customdata': [customdata]  # 传递处理后的customdata以获取延时信息
            }

            detail_figure1, detail_figure2, detail_figure_combined = self._generate_detail_plots(backend, plot_click_data, data_source='precision_data')

            logger.info(f"🔍 锤速对比图生成结果: detail_figure1={detail_figure1 is not None}, detail_figure2={detail_figure2 is not None}, detail_figure_combined={detail_figure_combined is not None}")

            # 计算中心时间
            center_time_ms = self._calculate_center_time_for_note_pair(backend, record_index, replay_index, algorithm_name)

            # 存储点击点信息
            point_info = {
                'key_id': key_id,
                'algorithm_name': algorithm_name,
                'record_idx': record_index,
                'replay_idx': replay_index,
                'source_plot_id': 'hammer-velocity-comparison-plot',
                'center_time_ms': center_time_ms
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
            )], no_update, point_info, no_update

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

    def handle_hammer_velocity_comparison_click(
        self, click_data: Optional[Dict[str, Any]],
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

        trigger_prop = ctx.triggered[0]['prop_id']
        trigger_id = trigger_prop.split('.')[0]
        logger.info(f"[INFO] 锤速对比图点击回调触发：prop_id={trigger_prop}, trigger_id={trigger_id}, click_data={click_data is not None}, close_modal_clicks={close_modal_clicks}, close_btn_clicks={close_btn_clicks}")

        # 如果点击了关闭按钮，隐藏模态框
        if trigger_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            return self._handle_modal_close_trigger()

        # 如果是锤速对比图点击
        if trigger_id == 'hammer-velocity-comparison-plot':
            if not click_data or 'points' not in click_data or not click_data['points']:
                logger.warning("[WARNING] 锤速对比图点击 - click_data无效")
                return current_style, [], no_update, no_update, no_update
            return self._handle_hammer_velocity_comparison_click_logic(click_data, session_id, current_style)

        # 其他情况，保持当前状态
        return current_style, [], no_update, no_update, no_update


    # ==================== 锤速对比图相关方法 ====================

    def _validate_velocity_comparison_prerequisites(self, backend: PianoAnalysisBackend) -> bool:
        """
        验证生成锤速对比图的必要前提条件

        Args:
            backend: 后端实例

        Returns:
            bool: 是否满足生成条件
        """
        # 使用通用的分析模式判断方法
        mode, algorithm_count = backend.get_current_analysis_mode()

        if mode == "multi":
            # 有活跃的多算法数据
            logger.info(f"[INFO] 检测到多算法模式，活跃算法数量: {algorithm_count}")
            return True
        elif mode == "single":
            # 没有活跃的多算法，但有单算法分析器
            logger.info("[INFO] 检测到单算法模式，支持生成锤速对比图（显示该算法的锤速分布）")
            return True
        else:
            # 两者都没有
            logger.warning("[WARNING] 没有可用的分析器，无法生成锤速对比图")
            return False

    def _collect_velocity_comparison_data(self, backend: PianoAnalysisBackend) -> List[VelocityDataItem]:
        """
        收集锤速对比数据 - 从精确匹配对获取数据

        Args:
            backend: 后端实例

        Returns:
            List[VelocityDataItem]: 锤速对比数据列表
        """
        velocity_data = []

        try:
            # 使用通用的分析模式判断方法
            mode, algorithm_count = backend.get_current_analysis_mode()

            if mode == "multi":
                # 多算法模式：从每个活跃算法的精确匹配对收集数据
                logger.info(f"[INFO] 多算法模式：从精确匹配对收集锤速对比数据，活跃算法数量: {algorithm_count}")

                active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()
                logger.info(f"[INFO] 活跃算法列表: {[alg.metadata.algorithm_name for alg in active_algorithms]}")
                for algorithm in active_algorithms:
                    logger.debug(f"[DEBUG] 处理算法: {algorithm.metadata.algorithm_name}")
                    algorithm_velocity_data = self._extract_velocity_data_from_precision_matches(algorithm)
                    logger.info(f"[INFO] 算法 {algorithm.metadata.algorithm_name} 收集到 {len(algorithm_velocity_data)} 个锤速数据点")
                    velocity_data.extend(algorithm_velocity_data)
            elif mode == "single":
                # 单算法模式：从单算法的精确匹配对收集数据
                logger.info("[INFO] 单算法模式：从精确匹配对收集锤速数据")

                # 创建临时算法对象来复用逻辑
                class TempAlgorithmDataset:
                    def __init__(self, analyzer, algorithm_name="单算法"):
                        self.analyzer = analyzer
                        self.metadata = type('Metadata', (), {'algorithm_name': algorithm_name})()
                        # 为单算法模式添加获取精确数据的便捷方法
                        self.get_precision_offset_alignment_data = lambda: analyzer.note_matcher.get_precision_offset_alignment_data() if analyzer and analyzer.note_matcher else []

                temp_algorithm = TempAlgorithmDataset(backend._get_current_analyzer(), "单算法")
                algorithm_velocity_data = self._extract_velocity_data_from_precision_matches(temp_algorithm)
                velocity_data.extend(algorithm_velocity_data)
            else:
                logger.warning("[WARNING] 没有可用的分析器")
                return []

            logger.info(f"[INFO] 锤速对比数据收集完成，总数据点数量: {len(velocity_data)}")
            return velocity_data

        except Exception as e:
            logger.error(f"[ERROR] 收集锤速对比数据失败: {e}")
            logger.error(traceback.format_exc())
            return []

    def _extract_velocity_data_from_precision_matches(self, algorithm: AlgorithmDataset) -> List[VelocityDataItem]:
        """
        从精确匹配对中提取锤速数据

        Args:
            algorithm: 算法数据集

        Returns:
            List[VelocityDataItem]: 该算法的锤速数据列表
        """
        # 验证算法有效性
        if not algorithm.analyzer or not algorithm.analyzer.note_matcher:
            return []

        # 获取精确匹配数据
        precision_data = algorithm.analyzer.note_matcher.get_precision_offset_alignment_data()
        if not precision_data:
            return []

        velocity_data = []

        # 处理每个精确匹配对
        for item in precision_data:
            try:
                # 提取基础信息
                record_index = item.get('record_index')
                replay_index = item.get('replay_index')
                key_id = item.get('key_id')

                if not all([record_index is not None, replay_index is not None, key_id is not None]):
                    continue

                # 获取precision_matched_pairs - 处理单算法和多算法模式的差异
                if hasattr(algorithm.analyzer, 'precision_matched_pairs'):
                    # 多算法模式：analyzer是AlgorithmDataset对象
                    precision_matched_pairs = algorithm.analyzer.precision_matched_pairs
                elif hasattr(algorithm.analyzer, 'note_matcher') and hasattr(algorithm.analyzer.note_matcher, 'precision_matched_pairs'):
                    # 单算法模式：analyzer是SPMIDAnalyzer对象
                    precision_matched_pairs = algorithm.analyzer.note_matcher.precision_matched_pairs
                else:
                    logger.warning(f"[WARNING] 无法获取precision_matched_pairs")
                    continue

                if not precision_matched_pairs:
                    logger.warning(f"[WARNING] precision_matched_pairs为空")
                    continue

                # 查找对应的音符对
                record_note, replay_note = self._find_notes_in_precision_pairs(
                    precision_matched_pairs, record_index, replay_index
                )

                if not record_note or not replay_note:
                    continue

                # 提取锤速
                record_velocity = self._get_velocity_from_note(record_note)
                replay_velocity = self._get_velocity_from_note(replay_note)

                if record_velocity is None or replay_velocity is None:
                    continue

                # 构建数据项
                velocity_item = self._build_velocity_data_item(
                    item, algorithm.metadata.algorithm_name,
                    record_note, replay_note, record_velocity, replay_velocity
                )

                velocity_data.append(velocity_item)

            except Exception as e:
                logger.warning(f"[WARNING] 处理精确匹配项失败 (record_index={record_index}, replay_index={replay_index}): {e}")
                continue

        return velocity_data

    def _find_notes_in_precision_pairs(self, precision_matched_pairs, record_index: int, replay_index: int):
        """在精确匹配对中查找音符对象"""
        if not precision_matched_pairs:
            return None, None

        for r_idx, p_idx, r_note, p_note in precision_matched_pairs:
            if r_idx == record_index and p_idx == replay_index:
                return r_note, p_note

        return None, None

    def _build_velocity_data_item(self, item, algorithm_name: str, record_note, replay_note, record_velocity: float, replay_velocity: float):
        """构建锤速数据项"""
        # 时间转换（微秒转毫秒）
        record_hammer_time_ms = item.get('record_keyon', 0) / 1000.0
        replay_hammer_time_ms = item.get('replay_keyon', 0) / 1000.0

        # 延时转换（0.1ms转ms）
        keyon_offset = item.get('keyon_offset', 0)
        absolute_delay_ms = keyon_offset / 10.0

        return {
            'record_index': item['record_index'],
            'replay_index': item['replay_index'],
            'record_velocity': record_velocity,
            'replay_velocity': replay_velocity,
            'key_id': item['key_id'],
            'algorithm_name': algorithm_name,
            'record_hammer_time_ms': record_hammer_time_ms,
            'replay_hammer_time_ms': replay_hammer_time_ms,
            'absolute_delay': absolute_delay_ms,
            'record_note': record_note,
            'replay_note': replay_note
        }

    def _get_velocity_from_note(self, note: Any) -> Optional[float]:
        """
        从音符的hammers中提取锤速

        Args:
            note: 音符对象

        Returns:
            Optional[float]: 锤速值，仅从hammers中获取
        """
        try:
            if not note:
                return None

            # 只从hammers数据中获取锤速
            if hasattr(note, 'hammers') and note.hammers is not None:
                if hasattr(note.hammers, 'values') and len(note.hammers.values) > 0:
                    hammer_velocity = note.hammers.values[0]
                    if hammer_velocity is not None and not pd.isna(hammer_velocity):
                        return float(hammer_velocity)
                elif hasattr(note.hammers, 'iloc') and len(note.hammers) > 0:
                    hammer_velocity = note.hammers.iloc[0]
                    if hammer_velocity is not None and not pd.isna(hammer_velocity):
                        return float(hammer_velocity)

            return None

        except Exception as e:
            logger.warning(f"[WARNING] 从音符提取锤速失败: {e}")
            return None

    def _get_velocity_from_hammers(self, hammers: Any) -> Optional[float]:
        """
        从锤子数据中提取锤速

        Args:
            hammers: 锤子数据

        Returns:
            Optional[float]: 锤速值
        """
        try:
            # 尝试多种方式获取锤速
            if hasattr(hammers, 'velocity') and not pd.isna(hammers.velocity):
                return float(hammers.velocity)
            elif hasattr(hammers, 'hammer_velocity') and not pd.isna(hammers.hammer_velocity):
                return float(hammers.hammer_velocity)
            elif hasattr(hammers, 'values') and len(hammers.values) > 0:
                first_value = hammers.values[0]
                if not pd.isna(first_value):
                    return float(first_value)
            else:
                logger.debug(f"[DEBUG] 锤子数据没有有效锤速: {type(hammers)}")
                return None

        except Exception as e:
            logger.debug(f"[DEBUG] 从锤子数据提取锤速失败: {e}")
            return None

    def _create_velocity_comparison_plot(self, velocity_data: List[VelocityDataItem]) -> Figure:
        """
        创建锤速对比散点图

        Args:
            velocity_data: 锤速数据列表

        Returns:
            Figure: 配置完整的图表对象
        """
        if not velocity_data:
            logger.warning("[WARNING] 没有锤速数据，创建空图表")
            return go.Figure()

        try:
            # 按算法分组数据
            algorithm_groups = {}
            for item in velocity_data:
                alg_name = item['algorithm_name']
                if alg_name not in algorithm_groups:
                    algorithm_groups[alg_name] = []
                algorithm_groups[alg_name].append(item)

            # 创建图表
            fig = go.Figure()

            # 为每个算法添加散点图
            colors = ['blue', 'red', 'green', 'orange', 'purple', 'brown', 'pink', 'gray', 'olive', 'cyan']

            for idx, (alg_name, data) in enumerate(algorithm_groups.items()):
                color = colors[idx % len(colors)]

                plot_data = self._prepare_velocity_plot_data(data)

                fig.add_trace(go.Scatter(
                    x=plot_data['x_values'],
                    y=plot_data['y_values'],
                    mode='markers',
                    name=f'{alg_name} ({len(data)}点)',
                    marker=dict(
                        color=color,
                        size=8,
                        opacity=0.7,
                        line=dict(width=1, color='white')
                    ),
                    text=plot_data['hover_texts'],
                    customdata=plot_data['custom_data'],
                    hovertemplate='<b>%{text}</b><br>' +
                                '算法: ' + alg_name + '<extra></extra>'
                ))

            # 配置布局
            fig.update_layout(
                title=dict(
                    x=0.5,
                    font=dict(size=16, weight='bold')
                ),
                xaxis=dict(
                    title='按键ID',
                    gridcolor='lightgray',
                    showgrid=True,
                    zeroline=True,
                    zerolinecolor='lightgray',
                    tickmode='linear',
                    dtick=1  # 按键ID通常是整数
                ),
                yaxis=dict(
                    title='锤速差值 (播放锤速 - 录制锤速)',
                    gridcolor='lightgray',
                    showgrid=True,
                    zeroline=True,
                    zerolinecolor='red',  # 高亮零线
                    zerolinewidth=2
                ),
                plot_bgcolor='white',
                paper_bgcolor='white',
                hovermode='closest',
                showlegend=True,
                legend=dict(
                    x=0.01,  # 更靠左
                    y=1.02,  # 移到图表上方
                    xanchor='left',
                    yanchor='bottom',  # 从图注底部定位，这样会完全在图表上方
                    bgcolor='rgba(255,255,255,0.95)',
                    bordercolor='gray',
                    borderwidth=1,
                    font=dict(size=10),
                    orientation='h'  # 水平排列图注
                )
            )

            # 添加水平参考线（锤速差值=0，表示理想情况）
            fig.add_shape(
                type='line',
                x0=min(item['key_id'] for item in velocity_data),
                y0=0,
                x1=max(item['key_id'] for item in velocity_data),
                y1=0,
                line=dict(color='red', width=2, dash='dash'),
                name='理想基准线 (锤速差值=0)'
            )

            logger.info(f"[INFO] 锤速对比图创建完成，包含 {len(algorithm_groups)} 个算法，{len(velocity_data)} 个数据点")
            return fig

        except Exception as e:
            logger.warning(f"[WARNING] 创建锤速对比图失败: {e}")
            return go.Figure()

    def _prepare_velocity_plot_data(self, algorithm_data: List[VelocityDataItem]) -> Dict[str, Union[List[str], List[float], List[str]]]:
        """
        准备绘图数据

        Args:
            algorithm_data: 单个算法的锤速数据

        Returns:
            Dict: 包含x_values, y_values, hover_texts, custom_data的字典
        """
        x_values = []
        y_values = []
        hover_texts = []
        custom_data = []

        for item in algorithm_data:
            # 横轴：按键ID
            x_values.append(item['key_id'])
            # 纵轴：播放锤速 - 录制锤速的差值
            velocity_diff = item['replay_velocity'] - item['record_velocity']
            y_values.append(velocity_diff)

            # 创建悬浮文本
            hover_text = (
                f'按键: {item["key_id"]}<br>'
                f'录制锤速: {item["record_velocity"]:.0f}<br>'
                f'播放锤速: {item["replay_velocity"]:.0f}<br>'
                f'锤速差值: {velocity_diff:+.0f}<br>'
                f'录制锤子时间: {item["record_hammer_time_ms"]:.2f} ms<br>'
                f'播放锤子时间: {item["replay_hammer_time_ms"]:.2f} ms'
            )
            hover_texts.append(hover_text)
            # customdata 包含 [按键ID, 算法名称, 录制锤速, 播放锤速, 锤速差值, 绝对延时, 录制索引, 播放索引] 用于点击回调
            velocity_diff = item['replay_velocity'] - item['record_velocity']
            custom_data.append([
                item["key_id"],
                item["algorithm_name"],
                item["record_velocity"],
                item["replay_velocity"],
                velocity_diff,
                item["absolute_delay"],
                item["record_index"],
                item["replay_index"]
            ])

        return {
            'x_values': x_values,
            'y_values': y_values,
            'hover_texts': hover_texts,
            'custom_data': custom_data
        }


def register_scatter_callbacks(app, session_mgr: SessionManager):
    """注册散点图相关的回调函数"""
    handler = ScatterPlotHandler(session_mgr)

    # Z-Score散点图生成回调
    @app.callback(
        Output('key-delay-zscore-scatter-plot', 'figure'),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_generate_zscore_scatter_plot(report_content, session_id):
        """处理按键与延时Z-Score标准化散点图自动生成 - 当报告内容更新时触发"""
        return handler.generate_zscore_scatter_plot(session_id)

    # 锤速与延时Z-Score标准化散点图生成回调
    @app.callback(
        Output('hammer-velocity-relative-delay-scatter-plot', 'figure'),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_generate_hammer_velocity_relative_delay_scatter_plot(report_content, session_id):
        """处理锤速与延时Z-Score标准化散点图自动生成 - 当报告内容更新时触发"""
        return handler.generate_hammer_velocity_relative_delay_scatter_plot(session_id)

    # 锤速与延时Z-Score标准化散点图点击回调
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True),
         Output('hammer-velocity-relative-delay-scatter-plot', 'clickData', allow_duplicate=True)],
        [Input('hammer-velocity-relative-delay-scatter-plot', 'clickData'),
         Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State('session-id', 'data'),
         State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_hammer_velocity_relative_delay_scatter_click(scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style):
        return handler.handle_hammer_velocity_relative_delay_plot_click(scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style)

    # 锤速与延时Z-Score散点图生成回调
    @app.callback(
        Output('hammer-velocity-delay-scatter-plot', 'figure'),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_generate_hammer_velocity_scatter_plot(report_content, session_id):
        """处理锤速与延时Z-Score标准化散点图自动生成 - 当报告内容更新时触发"""
        return handler.generate_hammer_velocity_scatter_plot(session_id)

    # Z-Score散点图点击回调
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
        """处理Z-Score标准化散点图点击，显示曲线对比（专用模态框）"""
        return handler.handle_zscore_scatter_click(zscore_scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style)

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
        """处理按键与相对延时散点图点击，显示曲线对比（专用模态框）"""
        return handler.handle_key_delay_scatter_click(scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style)

    # 锤速与延时Z-Score标准化散点图点击回调
    @app.callback(
        Output('key-curves-modal', 'style', allow_duplicate=True),
        Output('key-curves-comparison-container', 'children', allow_duplicate=True),
        Output('current-clicked-point-info', 'data', allow_duplicate=True),
        Input('hammer-velocity-delay-scatter-plot', 'clickData'),
        Input('close-key-curves-modal', 'n_clicks'),
        Input('close-key-curves-modal-btn', 'n_clicks'),
        State('session-id', 'data'),
        State('key-curves-modal', 'style'),
        prevent_initial_call=True
    )
    def handle_hammer_velocity_scatter_click(scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style):
        return handler.handle_hammer_velocity_scatter_click(scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style)

    # 锤速对比图生成回调
    @app.callback(
        Output('hammer-velocity-comparison-plot', 'figure'),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def callback_generate_hammer_velocity_comparison_plot(report_content, session_id):
        """处理锤速对比图自动生成 - 当报告内容更新时触发"""
        return handler.handle_generate_hammer_velocity_comparison_plot(report_content, session_id)

    # 按键与相对延时散点图生成回调
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
        # 获取后端实例
        backend = session_mgr.get_backend(session_id)
        if not backend:
            return no_update

        # 解析 Pattern Matching Inputs - 简化参数提取
        common_keys_filter = common_keys_filter_values[0] if common_keys_filter_values else False
        algorithm_selector = algorithm_selector_values[0] if algorithm_selector_values else []

        # 判断触发源类型 - 简化逻辑
        ctx = callback_context
        if not ctx.triggered:
            return no_update

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        is_report_content_trigger = trigger_id == 'report-content'
        is_filter_trigger = 'key-delay-scatter-' in trigger_id

        # 提前判断分析模式
        active_algorithms = backend.multi_algorithm_manager.get_active_algorithms() if backend.multi_algorithm_manager else []
        is_multi_mode = len(active_algorithms) > 1
        has_analyzer = backend._get_current_analyzer() is not None

        try:
            # 单算法模式：只响应报告内容更新
            if not is_multi_mode and has_analyzer:
                if not is_report_content_trigger:
                    return no_update  # 单算法模式忽略筛选控件变化

                fig = backend.generate_key_delay_scatter_plot(
                    only_common_keys=False,
                    selected_algorithm_names=[]
                )
                logger.info("[OK] 单算法模式按键与相对延时散点图生成成功")
                return fig

            # 多算法模式：响应所有变化
            if is_multi_mode:
                fig = backend.generate_key_delay_scatter_plot(
                    only_common_keys=bool(common_keys_filter),
                    selected_algorithm_names=algorithm_selector or []
                )

                log_msg = "[OK] 多算法模式按键与相对延时散点图数据加载成功" if is_report_content_trigger else "[OK] 多算法模式按键与相对延时散点图筛选更新成功"
                logger.info(log_msg)
                return fig

            # 无分析器情况
            logger.warning("[WARNING] 没有有效的分析器，无法生成按键与相对延时散点图")
            return no_update

        except Exception as e:
            error_msg = f"按键与相对延时散点图处理失败: {str(e)}"
            logger.error(f"[ERROR] {error_msg}")

            return backend.plot_generator._create_empty_plot(error_msg) if backend else no_update

    # 锤速对比图点击回调
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
    def callback_hammer_velocity_comparison_click(
        click_data: Optional[Dict[str, Any]],
        close_modal_clicks: Optional[int],
        close_btn_clicks: Optional[int],
        session_id: str,
        current_style: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[Union[html.Div, dcc.Graph]], Union[Figure, NoUpdate], Dict[str, Any], Optional[Dict[str, Any]]]:
        """处理锤速对比图点击，显示对应按键的曲线对比（悬浮窗）"""
        return handler.handle_hammer_velocity_comparison_click(
            click_data, close_modal_clicks, close_btn_clicks, session_id, current_style
        )

    # 按键-力度交互效应图点击回调
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
    def handle_key_force_interaction_plot_click_callback(click_data, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理按键-力度交互效应图点击回调"""
        return handler.handle_key_force_interaction_plot_click(click_data, close_modal_clicks, close_btn_clicks, session_id, current_style)

    # 注册按键-力度交互效应图回调
    register_key_force_interaction_callbacks(app, session_mgr)


# 按键-力度交互效应图相关函数
def _prepare_key_force_interaction_figure(trigger_id: str, backend, current_figure):
    """准备按键-力度交互效应图表对象"""
    # 如果是report-content变化，需要重新生成图表
    if trigger_id == 'report-content':
        # 检查是否有激活的算法
        active_algorithms = backend.get_active_algorithms()
        if not active_algorithms:
            logger.debug("[DEBUG] 没有激活的算法，跳过交互效应图生成")
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


def _update_data_trace_visibility(data_list: List, selected_keys: List[int]):
    """更新数据trace的可见性 - 只根据按键选择控制"""
    visible_count = 0
    total_data_traces = 0

    for trace_idx, trace in enumerate(data_list):
        total_data_traces += 1

        # 从trace的customdata中提取按键信息
        key_id = None
        algorithm_name = None
        showlegend = False
        if isinstance(trace, dict):
            customdata = trace.get('customdata')
            legendgroup = trace.get('legendgroup', '')
            showlegend = trace.get('showlegend', False)
        else:
            customdata = trace.customdata if hasattr(trace, 'customdata') else None
            legendgroup = trace.legendgroup if hasattr(trace, 'legendgroup') else ''
            showlegend = trace.showlegend if hasattr(trace, 'showlegend') else False

        if customdata:
            try:
                if hasattr(customdata, '__iter__') and not isinstance(customdata, str):
                    if not isinstance(customdata, list):
                        customdata = list(customdata)

                    if len(customdata) > 0:
                        first_point = customdata[0]
                        if hasattr(first_point, '__iter__') and not isinstance(first_point, str):
                            if not isinstance(first_point, list):
                                first_point = list(first_point)

                            # customdata格式: [key_id, algorithm_name, ...]
                            if len(first_point) >= 2:
                                key_id = int(first_point[0])
                                algorithm_name = first_point[1] if first_point[1] else None
            except Exception as e:
                logger.debug(f"[TRACE] 提取按键ID失败: {e}")

        # 特殊处理：如果是显示图注的trace，始终保持可见
        # 这样图注始终显示，用户可以通过图注控制整个算法的显示
        is_legend_trace = showlegend and legendgroup.startswith('algorithm_')

        # 确定可见性：按键选择是唯一的过滤条件
        if selected_keys:
            # 选择了特定按键：只显示该按键的数据，完全过滤掉其他数据
            target_visible = key_id is not None and key_id in selected_keys
        else:
            # 没有选择按键：显示所有数据和图注
            target_visible = True

        if target_visible:
            visible_count += 1

        # 更新可见性
        if isinstance(trace, dict):
            trace['visible'] = target_visible
            data_list[trace_idx] = trace
        else:
            trace.visible = target_visible


def handle_generate_key_force_interaction_plot_with_session(session_manager: SessionManager, report_content, selected_keys, session_id, current_figure):
    """处理按键-力度交互效应图自动生成和更新 - 根据选中的按键更新可见性"""
    ctx = callback_context
    if not ctx.triggered:
        return no_update

    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

    backend = session_manager.get_backend(session_id)
    if not backend:
        return no_update

    try:
        # 根据选中的按键更新可见性
        selected_keys = selected_keys or []

        # 准备图表对象
        fig = _prepare_key_force_interaction_figure(trigger_id, backend, current_figure)
        if fig is no_update or isinstance(fig, str):  # 如果是空图或错误，直接返回
            return fig

        # 将fig.data转换为可修改的list
        data_list = list(fig.data)

        # 更新数据trace的可见性
        _update_data_trace_visibility(data_list, selected_keys)

        # 将修改后的trace列表赋值回fig.data
        fig.data = data_list

        logger.info(f"[OK] 按键-力度交互效应图更新成功 (触发器: {trigger_id})")
        return fig

    except Exception as e:
        logger.error(f"[ERROR] 生成/更新按键-力度交互效应图失败: {e}")
        logger.error(traceback.format_exc())
        return backend.plot_generator._create_empty_plot(f"生成交互效应图失败: {str(e)}")


def update_key_selector_options(figure):
    """根据图表数据更新按键选择器的选项"""
    if not figure or 'data' not in figure:
        return []

    # 提取所有按键ID
    key_ids = set()
    for trace in figure['data']:
        customdata = trace.get('customdata')
        if customdata:
            try:
                if hasattr(customdata, '__iter__') and not isinstance(customdata, str):
                    if not isinstance(customdata, list):
                        customdata = list(customdata)

                    if len(customdata) > 0:
                        first_point = customdata[0]
                        if hasattr(first_point, '__iter__') and not isinstance(first_point, str):
                            if not isinstance(first_point, list):
                                first_point = list(first_point)

                            # customdata格式: [key_id, algorithm_name, replay_velocity, relative_delay, absolute_delay, record_index, replay_index]
                            if len(first_point) >= 1:
                                key_id = int(first_point[0])
                                key_ids.add(key_id)
            except Exception as e:
                logger.debug(f"[TRACE] 从trace提取按键ID失败: {e}")

    # 生成下拉选项
    options = [{'label': f'按键 {key_id}', 'value': key_id} for key_id in sorted(key_ids)]
    return options


def update_selected_keys_from_dropdown(selected_key):
    """当下拉菜单选择改变时，更新selected_keys"""
    if selected_key is None:
        return []
    return [selected_key]


# 注册按键-力度交互效应图的回调
def register_key_force_interaction_callbacks(app, session_manager: SessionManager):
    """注册按键-力度交互效应图相关的回调函数"""
    # 注意：这里不再需要global声明，因为我们通过闭包捕获session_manager

    # 更新按键选择器选项
    @app.callback(
        Output('key-force-interaction-key-selector', 'options'),
        [Input('key-force-interaction-plot', 'figure')],
        prevent_initial_call=True
    )
    def callback_update_key_selector_options(figure):
        return update_key_selector_options(figure)

    # 当下拉菜单选择改变时，更新selected_keys
    @app.callback(
        Output('key-force-interaction-selected-keys', 'data'),
        [Input('key-force-interaction-key-selector', 'value')],
        prevent_initial_call=True
    )
    def callback_update_selected_keys_from_dropdown(selected_key):
        return update_selected_keys_from_dropdown(selected_key)

    # 按键-力度交互效应图自动生成和更新回调函数
    @app.callback(
        Output('key-force-interaction-plot', 'figure'),
        [Input('report-content', 'children'),
         Input('key-force-interaction-selected-keys', 'data')],
        [State('session-id', 'data'),
         State('key-force-interaction-plot', 'figure')],
        prevent_initial_call=True
    )
    def callback_handle_generate_key_force_interaction_plot(report_content, selected_keys, session_id, current_figure):
        return handle_generate_key_force_interaction_plot_with_session(session_manager, report_content, selected_keys, session_id, current_figure)