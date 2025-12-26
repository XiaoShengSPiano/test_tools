"""
散点图回调模块 - 处理所有散点图相关的交互逻辑
包含 Z-Score、按键延时、锤速散点图的点击处理
"""

import time
import traceback
import json
from typing import Optional, Tuple, List, Any, Union, Dict, TypedDict

import dash
from dash import dash_table
import dash_bootstrap_components as dbc
from dash import html, dcc, no_update
from dash._callback import NoUpdate
from dash import Input, Output, State
from dash._callback_context import callback_context

from backend.session_manager import SessionManager
from backend.piano_analysis_backend import PianoAnalysisBackend
from utils.logger import Logger

logger = Logger.get_logger()


# Type definitions
class ZScoreClickData(TypedDict):
    """Z-Score散点图点击数据的类型定义"""
    record_index: int
    replay_index: int
    key_id: Optional[int]
    algorithm_name: str


class ScatterPlotHandler:
    """
    散点图处理器 - 统一处理所有散点图相关的回调逻辑

    封装了 Z-Score、按键延时、锤速散点图的点击处理，
    提供统一的接口和错误处理机制。
    """

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager

    def _create_empty_figure_for_callback(self, title: str) -> Any:
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
            margin=dict(l=20, r=20, t=60, b=20)
        )
        return fig

    def _handle_plot_update_error(self, error: Exception, backend) -> Any:
        """处理图表更新错误，返回错误图表"""
        logger.error(f"[ERROR] 更新散点图失败: {str(error)}")
        logger.error(traceback.format_exc())
        return self._create_empty_figure_for_callback(f"更新失败: {str(error)}")

    def _validate_zscore_click_data(self, zscore_scatter_clickData: Dict[str, Any], backend: PianoAnalysisBackend) -> Optional[Dict[str, Any]]:
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

    def _extract_zscore_customdata(self, raw_customdata: Any) -> Optional[ZScoreClickData]:
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

    def _get_algorithm_for_zscore(self, backend: PianoAnalysisBackend, display_name: str) -> Optional[Any]:
        """
        获取Z-Score分析的算法实例

        Args:
            backend: 后端实例
            display_name: 用户输入的算法显示名称

        Returns:
            Optional[Any]: 算法实例，获取失败返回None
        """
        if not display_name or not backend.multi_algorithm_mode or not backend.multi_algorithm_manager:
            return None

        # 根据 display_name 查找算法
        for algorithm in backend.multi_algorithm_manager.get_all_algorithms():
            if algorithm.metadata.display_name == display_name:
                if algorithm.analyzer and algorithm.analyzer.note_matcher:
                    return algorithm

        return None

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

    def _calculate_time_from_notes(self, matched_pairs: List, record_index: int, replay_index: int) -> Optional[Tuple[float, float]]:
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

    def _calculate_center_time_from_indices(self, backend, record_index: int, replay_index: int) -> Optional[float]:
        """
        从record_index和replay_index计算中心时间
        直接复用按键与相对延时散点图的逻辑

        Args:
            backend: 后端实例
            record_index: 录制音符索引
            replay_index: 播放音符索引

        Returns:
            Optional[float]: 中心时间（毫秒），失败返回None
        """
        if not backend.analyzer or not backend.analyzer.note_matcher:
            return None

        # 直接使用与按键与相对延时散点图相同的方式获取matched_pairs
        matched_pairs = backend.analyzer.matched_pairs

        # 在matched_pairs中查找对应的音符对
        for r_idx, p_idx, r_note, p_note in matched_pairs:
            if r_idx == record_index and p_idx == replay_index:
                # 计算keyon时间 - 与按键与相对延时散点图完全相同的逻辑
                record_keyon = r_note.after_touch.index[0] + r_note.offset if hasattr(r_note, 'after_touch') and not r_note.after_touch.empty else r_note.offset
                replay_keyon = p_note.after_touch.index[0] + p_note.offset if hasattr(p_note, 'after_touch') and not p_note.after_touch.empty else p_note.offset
                center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0  # 转换为ms
                return center_time_ms

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
            # 获取算法实例
            algorithm = self._get_algorithm_for_zscore(backend, click_data['algorithm_name'])
            if not algorithm:
                return None

            record_index = click_data['record_index']
            replay_index = click_data['replay_index']

            # 优先从预计算的 offset_data 中获取时间信息
            keyon_times = self._get_time_from_offset_data(algorithm.analyzer.note_matcher, record_index, replay_index)
            if keyon_times:
                record_keyon, replay_keyon = keyon_times
                return self._calculate_center_time_ms(record_keyon, replay_keyon)

            # 如果 offset_data 中没有找到，降级到直接从音符计算
            keyon_times = self._calculate_time_from_notes(algorithm.analyzer.matched_pairs, record_index, replay_index)
            if keyon_times:
                record_keyon, replay_keyon = keyon_times
                return self._calculate_center_time_ms(record_keyon, replay_keyon)

            return None

        except Exception as e:
            logger.warning(f"[WARNING] 计算时间信息失败: {e}")
            return None

    def _generate_detail_plots(self, backend: PianoAnalysisBackend, click_data: Dict[str, Any]) -> Tuple[Any, Any, Any]:
        """
        生成散点图点击的详细曲线图

        Args:
            backend: 后端实例
            click_data: 点击数据，包含 algorithm_name, record_index, replay_index

        Returns:
            Tuple[Any, Any, Any]: (录制图, 播放图, 对比图)
        """
        # 根据是否是多算法模式调用不同的方法
        if click_data.get('algorithm_name'):
            # 多算法模式
            detail_figure1, detail_figure2, detail_figure_combined = backend.generate_multi_algorithm_scatter_detail_plot_by_indices(
                algorithm_name=click_data['algorithm_name'],
                record_index=click_data['record_index'],
                replay_index=click_data['replay_index']
            )
        else:
            # 单算法模式
            detail_figure1, detail_figure2, detail_figure_combined = backend.generate_scatter_detail_plot_by_indices(
                record_index=click_data['record_index'],
                replay_index=click_data['replay_index']
            )

        logger.info(f"🔍 散点图点击回调 - 图表生成结果: figure1={detail_figure1 is not None}, figure2={detail_figure2 is not None}, figure_combined={detail_figure_combined is not None}")

        return detail_figure1, detail_figure2, detail_figure_combined

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

        # 验证点击数据
        point = self._validate_zscore_click_data(zscore_scatter_clickData, backend)
        if not point:
            return current_style, [], no_update, no_update

        # 提取customdata
        click_data = self._extract_zscore_customdata(point['customdata'])
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
        detail_figure1, detail_figure2, detail_figure_combined = self._generate_detail_plots(backend, click_data)

        # 检查图表生成是否成功
        if detail_figure1 and detail_figure2 and detail_figure_combined:
            modal_style, graph_component, point_info_response = self._create_zscore_modal_response(detail_figure_combined, point_info)
            return modal_style, graph_component, point_info_response
        else:
            logger.warning("[WARNING] Z-Score标准化散点图点击回调 - 图表生成失败，部分图表为None")
            return current_style, [], no_update, no_update

    def handle_zscore_scatter_click(self, zscore_scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理Z-Score标准化散点图点击，显示曲线对比（悬浮窗）并支持跳转到瀑布图"""
        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            logger.debug("[WARNING] Z-Score散点图点击回调：没有触发源")
            return current_style, [], no_update, no_update

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

        # 如果点击了关闭按钮，隐藏模态框
        if trigger_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            result = self._handle_zscore_modal_close()
            return result[0], result[1], result[2], result[3]

        # 如果是Z-Score散点图点击
        if trigger_id == 'key-delay-zscore-scatter-plot' and zscore_scatter_clickData:
            result = self._handle_zscore_plot_click(zscore_scatter_clickData, session_id, current_style, 'key-delay-zscore-scatter-plot')
            return result[0], result[1], result[2], no_update

        # 其他情况，返回默认值
        return current_style, [], no_update, no_update

    def handle_key_delay_scatter_click(self, scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理按键与相对延时散点图点击，显示曲线对比（悬浮窗）并支持跳转到瀑布图"""
        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            logger.debug("[WARNING] 按键与相对延时散点图点击回调：没有触发源")
            return current_style, [], no_update, no_update

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

        # 如果点击了关闭按钮，隐藏模态框
        if trigger_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            result = self._handle_zscore_modal_close()
            return result[0], result[1], result[2], result[3]

        # 如果是按键与相对延时散点图点击
        if trigger_id == 'key-delay-scatter-plot' and scatter_clickData:
            # 按键与相对延时散点图有不同的 customdata 格式，需要专门处理
            result = self._handle_key_delay_plot_click(scatter_clickData, session_id, current_style, 'key-delay-scatter-plot')
            return result[0], result[1], result[2], no_update

        # 其他情况，返回默认值
        return current_style, [], no_update, no_update

    def handle_hammer_velocity_scatter_click(self, scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理锤速与延时Z-Score标准化散点图点击，显示曲线对比（悬浮窗）"""
        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            logger.debug("[WARNING] 锤速与延时Z-Score标准化散点图点击回调：没有触发源")
            return current_style, [], no_update

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

        # 如果点击了关闭按钮，隐藏模态框
        if trigger_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            result = self._handle_zscore_modal_close()
            return result[0], result[1], result[2]

        # 如果是锤速与延时Z-Score标准化散点图点击
        if trigger_id == 'hammer-velocity-delay-scatter-plot' and scatter_clickData:
            result = self._handle_hammer_velocity_plot_click(scatter_clickData, session_id, current_style, 'hammer-velocity-delay-scatter-plot')
            return result[0], result[1], result[2]

        # 其他情况，返回默认值
        return current_style, [], no_update

    def handle_hammer_velocity_relative_delay_plot_click(self, scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理锤速与延时Z-Score标准化散点图点击，显示曲线对比（悬浮窗）"""
        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            logger.debug("[WARNING] 锤速与延时Z-Score标准化散点图点击回调：没有触发源")
            return current_style, [], no_update, no_update

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

        # 如果点击了关闭按钮，隐藏模态框
        if trigger_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            result = self._handle_zscore_modal_close()
            return result[0], result[1], result[2], result[3]

        # 如果是锤速与延时Z-Score标准化散点图点击
        if trigger_id == 'hammer-velocity-relative-delay-scatter-plot' and scatter_clickData:
            result = self._handle_hammer_velocity_relative_delay_plot_click(scatter_clickData, session_id, current_style, 'hammer-velocity-relative-delay-scatter-plot')
            return result[0], result[1], result[2], no_update

        # 其他情况，返回默认值
        return current_style, [], no_update, no_update

    def _handle_hammer_velocity_relative_delay_plot_click(self, scatter_clickData, session_id, current_style, source_plot_id='hammer-velocity-relative-delay-scatter-plot'):
        """处理锤速与延时Z-Score标准化散点图点击的主要逻辑 - 直接复用按键与相对延时散点图的逻辑"""
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

        # 直接复用按键与相对延时散点图的点击处理逻辑
        # 构造与按键与相对延时散点图相同格式的点击数据
        key_delay_click_data = {
            'points': [{
                'customdata': [record_index, replay_index, key_id, delay_ms, algorithm_name]  # 按键与相对延时散点图的customdata格式
            }]
        }

        # 直接调用按键与相对延时散点图的处理方法
        result = self._handle_key_delay_plot_click(key_delay_click_data, session_id, current_style, 'hammer-velocity-relative-delay-scatter-plot')

        # 如果成功，更新点信息以包含锤速相关信息
        if result[0].get('display') == 'block' and len(result) > 2 and isinstance(result[2], dict):
            # 更新点信息，添加锤速信息
            result[2]['锤速'] = f"{original_velocity:.0f}"
            result[2]['相对延时'] = f"{delay_ms:.2f}ms"
            result[2]['绝对延时'] = f"{delay_ms:.2f}ms"

        return result

    def _handle_hammer_velocity_plot_click(self, scatter_clickData, session_id, current_style, source_plot_id='hammer-velocity-delay-scatter-plot'):
        """处理锤速与延时Z-Score标准化散点图点击的主要逻辑"""
        logger.info(f"🔍 锤速与延时Z-Score标准化散点图点击回调被触发 - source_plot_id: {source_plot_id}, clickData: {scatter_clickData is not None}")

        backend = self.session_manager.get_backend(session_id)
        if not backend:
            logger.warning("[WARNING] 没有找到backend")
            return current_style, [], no_update, no_update

        # 验证点击数据
        if 'points' not in scatter_clickData or len(scatter_clickData['points']) == 0:
            logger.warning("[WARNING] 锤速与延时Z-Score标准化散点图点击回调 - scatter_clickData无效或没有points")
            return current_style, [], no_update, no_update

        point = scatter_clickData['points'][0]
        logger.info(f"🔍 锤速与延时Z-Score标准化散点图点击 - 点击点数据: {point}")

        if not point.get('customdata'):
            logger.warning("[WARNING] 锤速与延时Z-Score标准化散点图点击 - 点没有customdata")
            return current_style, [], no_update, no_update

        # 提取customdata - 锤速与延时Z-Score标准化散点图格式: [delay_ms, original_velocity, record_idx, replay_idx, algorithm_name, key_id]
        raw_customdata = point['customdata']
        logger.info(f"🔍 锤速与延时Z-Score标准化散点图点击 - raw_customdata类型: {type(raw_customdata)}, 值: {raw_customdata}")

        if isinstance(raw_customdata, list) and len(raw_customdata) > 0:
            customdata = raw_customdata[0] if isinstance(raw_customdata[0], list) else raw_customdata
        else:
            customdata = raw_customdata

        if not isinstance(customdata, list):
            logger.warning(f"[WARNING] 锤速与延时Z-Score标准化散点图点击 - customdata不是列表类型: {type(customdata)}, 值: {customdata}")
            return current_style, [], no_update, no_update

        logger.info(f"🔍 锤速与延时Z-Score标准化散点图点击 - customdata: {customdata}, 长度: {len(customdata)}")

        if len(customdata) < 6:
            logger.warning(f"[WARNING] 锤速与延时Z-Score标准化散点图点击 - customdata长度不足: {len(customdata)}")
            return current_style, [], no_update, no_update

        # 解析锤速与延时Z-Score标准化散点图的customdata格式: [delay_ms, original_velocity, record_idx, replay_idx, algorithm_name, key_id]
        delay_ms = customdata[0]
        original_velocity = customdata[1]
        record_index = customdata[2]
        replay_index = customdata[3]
        algorithm_name = customdata[4]
        key_id = customdata[5]

        logger.info(f"🖱️ 锤速与延时Z-Score标准化散点图点击: 算法={algorithm_name}, 按键={key_id}, record_index={record_index}, replay_index={replay_index}, 延时={delay_ms}ms, 锤速={original_velocity}")

        # 计算中心时间
        center_time_ms = None
        try:
            # 检查是否有多个活跃算法
            active_algorithms = []
            if backend.multi_algorithm_mode and backend.multi_algorithm_manager:
                active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()

            # 判断是否真正处于多算法模式（有多个活跃算法）
            is_multi_algorithm = len(active_algorithms) > 1

            if is_multi_algorithm and algorithm_name:
                # 多算法模式 - 查找指定的算法
                logger.debug(f"[DEBUG] 多算法模式，查找算法 '{algorithm_name}' 结果: {algorithm is not None}")
                algorithm = self._get_algorithm_for_zscore(backend, algorithm_name)
                if algorithm and algorithm.analyzer and algorithm.analyzer.note_matcher:
                    logger.info(f"[INFO] 使用多算法模式处理算法 '{algorithm_name}' (活跃算法数量: {len(active_algorithms)})")
                    # 创建临时backend对象，只包含analyzer
                    temp_backend = type('TempBackend', (), {'analyzer': algorithm.analyzer})()
                    center_time_ms = self._calculate_center_time_from_indices(temp_backend, record_index, replay_index)

                    # 备用方案：从 offset_data 获取
                    if center_time_ms is None:
                        logger.debug(f"[DEBUG] 主方案失败，尝试备用方案")
                        keyon_times = self._get_time_from_offset_data(algorithm.analyzer.note_matcher, record_index, replay_index)
                        if keyon_times:
                            record_keyon, replay_keyon = keyon_times
                            center_time_ms = self._calculate_center_time_ms(record_keyon, replay_keyon)
                            logger.debug(f"[DEBUG] 备用方案计算得到中心时间: {center_time_ms}ms")
                else:
                    logger.warning(f"⚠️ 算法 '{algorithm_name}' 不存在或没有分析器，降级到单算法模式")
                    # 降级到单算法模式
                    is_multi_algorithm = False
            else:
                logger.info(f"[INFO] 使用单算法模式处理 (活跃算法数量: {len(active_algorithms)}, algorithm_name: {algorithm_name})")

            # 单算法模式处理（包括只有一个算法的多算法模式，或从多算法模式降级下来的情况）
            if not is_multi_algorithm:
                center_time_ms = self._calculate_center_time_from_indices(backend, record_index, replay_index)

                # 备用方案：从 offset_data 获取
                if center_time_ms is None:
                    logger.debug(f"[DEBUG] 主方案失败，尝试备用方案")
                    if backend.analyzer and backend.analyzer.note_matcher:
                        keyon_times = self._get_time_from_offset_data(backend.analyzer.note_matcher, record_index, replay_index)
                        if keyon_times:
                            record_keyon, replay_keyon = keyon_times
                            center_time_ms = self._calculate_center_time_ms(record_keyon, replay_keyon)
                            logger.debug(f"[DEBUG] 备用方案计算得到中心时间: {center_time_ms}ms")

            if center_time_ms is None:
                logger.warning("[WARNING] 无法计算中心时间")
                return current_style, [], no_update, no_update

        except Exception as e:
            logger.error(f"[ERROR] 计算中心时间失败: {e}")
            return current_style, [], no_update, no_update

        # 生成详细图表
        try:
            logger.info(f"🎨 开始生成锤速与延时Z-Score标准化散点图的详细曲线图 - 中心时间: {center_time_ms}ms")

            # 生成详细曲线图 - 使用与按键与相对延时散点图相同的方法
            _, _, detail_figure_combined = self._generate_detail_plots(backend, {
                'algorithm_name': algorithm_name,
                'record_index': record_index,
                'replay_index': replay_index
            })

            if detail_figure_combined is None:
                logger.warning("[WARNING] 锤速与延时Z-Score标准化散点图点击回调 - 图表生成失败，部分图表为None")
                return current_style, [], no_update, no_update

            # 创建点信息
            point_info = {
                '算法': algorithm_name or '单算法',
                '按键ID': key_id,
                '录制索引': record_index,
                '播放索引': replay_index,
                '相对延时': ".2f",
                '绝对延时': ".2f",
                '锤速': f"{original_velocity:.0f}",
                '中心时间': f"{center_time_ms:.2f}ms"
            }

            # 返回模态框样式、图表和点信息
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

            logger.info("[OK] 锤速与延时Z-Score标准化散点图点击回调 - 返回模态框和图表")
            return modal_style, [dcc.Graph(figure=detail_figure_combined, style={'height': '600px'})], point_info, no_update

        except Exception as e:
            logger.error(f"[ERROR] 生成锤速与延时Z-Score标准化散点图详细图表失败: {e}")
            logger.error(traceback.format_exc())
            return current_style, [], no_update, no_update

    def _handle_hammer_velocity_plot_click(self, scatter_clickData, session_id, current_style, source_plot_id='hammer-velocity-delay-scatter-plot'):
        """处理锤速与延时Z-Score标准化散点图点击的主要逻辑"""
        logger.info(f"🔍 锤速与延时Z-Score标准化散点图点击回调被触发 - source_plot_id: {source_plot_id}, clickData: {scatter_clickData is not None}")

        backend = self.session_manager.get_backend(session_id)
        if not backend:
            logger.warning("[WARNING] 没有找到backend")
            return current_style, [], no_update, no_update

        # 验证点击数据
        if 'points' not in scatter_clickData or len(scatter_clickData['points']) == 0:
            logger.warning("[WARNING] 锤速与延时Z-Score标准化散点图点击回调 - scatter_clickData无效或没有points")
            return current_style, [], no_update, no_update

        point = scatter_clickData['points'][0]
        logger.info(f"🔍 锤速与延时Z-Score标准化散点图点击 - 点击点数据: {point}")

        if not point.get('customdata'):
            logger.warning("[WARNING] 锤速与延时Z-Score标准化散点图点击 - 点没有customdata")
            return current_style, [], no_update, no_update

        # 提取customdata - 锤速与延时Z-Score标准化散点图格式: [delay_ms, original_velocity, record_idx, replay_idx, algorithm_name, key_id]
        raw_customdata = point['customdata']
        logger.info(f"🔍 锤速与延时Z-Score标准化散点图点击 - raw_customdata类型: {type(raw_customdata)}, 值: {raw_customdata}")

        if isinstance(raw_customdata, list) and len(raw_customdata) > 0:
            customdata = raw_customdata[0] if isinstance(raw_customdata[0], list) else raw_customdata
        else:
            customdata = raw_customdata

        if not isinstance(customdata, list):
            logger.warning(f"[WARNING] 锤速与延时Z-Score标准化散点图点击 - customdata不是列表类型: {type(customdata)}, 值: {customdata}")
            return current_style, [], no_update, no_update

        logger.info(f"🔍 锤速与延时Z-Score标准化散点图点击 - customdata: {customdata}, 长度: {len(customdata)}")

        if len(customdata) < 6:
            logger.warning(f"[WARNING] 锤速与延时Z-Score标准化散点图点击 - customdata长度不足: {len(customdata)}")
            return current_style, [], no_update, no_update

        # 解析锤速与延时Z-Score标准化散点图的customdata格式: [delay_ms, original_velocity, record_idx, replay_idx, algorithm_name, key_id]
        delay_ms = customdata[0]
        original_velocity = customdata[1]
        record_index = customdata[2]
        replay_index = customdata[3]
        algorithm_name = customdata[4]
        key_id = customdata[5]

        logger.info(f"🖱️ 锤速与延时Z-Score标准化散点图点击: 算法={algorithm_name}, 按键={key_id}, record_index={record_index}, replay_index={replay_index}, 延时={delay_ms}ms, 锤速={original_velocity}")

        # 计算中心时间
        center_time_ms = None
        try:
            # 检查是否有多个活跃算法
            active_algorithms = []
            if backend.multi_algorithm_mode and backend.multi_algorithm_manager:
                active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()

            # 判断是否真正处于多算法模式（有多个活跃算法）
            is_multi_algorithm = len(active_algorithms) > 1

            if is_multi_algorithm and algorithm_name:
                # 多算法模式 - 查找指定的算法
                algorithm = self._get_algorithm_for_zscore(backend, algorithm_name)
                if algorithm and algorithm.analyzer and algorithm.analyzer.note_matcher:
                    logger.info(f"[INFO] 使用多算法模式处理算法 '{algorithm_name}' (活跃算法数量: {len(active_algorithms)})")
                    # 创建一个临时的backend对象，只包含analyzer
                    temp_backend = type('TempBackend', (), {'analyzer': algorithm.analyzer})()
                    center_time_ms = self._calculate_center_time_from_indices(temp_backend, record_index, replay_index)

                    
                else:
                    logger.warning(f"⚠️ 算法 '{algorithm_name}' 不存在或没有分析器，降级到单算法模式")
                    # 降级到单算法模式
                    is_multi_algorithm = False

            # 单算法模式处理（实际上是单活跃算法的多算法模式）
            if not is_multi_algorithm:
                logger.info(f"[INFO] 使用单算法模式处理 (活跃算法数量: {len(active_algorithms)})")

                # 始终从多算法管理器获取analyzer，因为系统现在只支持多算法模式
                if backend.multi_algorithm_manager and active_algorithms:
                    # 使用第一个活跃算法的analyzer
                    first_algorithm = active_algorithms[0]
                    if first_algorithm.analyzer:
                        # 创建临时backend对象
                        temp_backend = type('TempBackend', (), {'analyzer': first_algorithm.analyzer})()
                        center_time_ms = self._calculate_center_time_from_indices(temp_backend, record_index, replay_index)
                    else:
                        logger.warning("[WARNING] 单算法模式下的活跃算法也没有analyzer")
                        center_time_ms = None
                else:
                    logger.warning("[WARNING] 单算法模式下无法从多算法管理器获取analyzer")
                    center_time_ms = None

            if center_time_ms is None:
                logger.warning("[WARNING] 无法计算中心时间")
                return current_style, [], no_update, no_update

        except Exception as e:
            logger.error(f"[ERROR] 计算中心时间失败: {e}")
            return current_style, [], no_update, no_update

        # 生成详细图表
        try:
            logger.info(f"🎨 开始生成锤速与延时Z-Score标准化散点图的详细曲线图 - 中心时间: {center_time_ms}ms")

            # 生成详细曲线图 - 使用与按键与相对延时散点图相同的方法
            _, _, detail_figure_combined = self._generate_detail_plots(backend, {
                'algorithm_name': algorithm_name,
                'record_index': record_index,
                'replay_index': replay_index
            })

            if detail_figure_combined is None:
                logger.warning("[WARNING] 锤速与延时Z-Score标准化散点图点击回调 - 图表生成失败，部分图表为None")
                return current_style, [], no_update, no_update

            # 创建点信息
            point_info = {
                '算法': algorithm_name or '单算法',
                '按键ID': key_id,
                '录制索引': record_index,
                '播放索引': replay_index,
                '延时': f"{delay_ms:.2f}ms",
                '锤速': f"{original_velocity:.0f}",
                '中心时间': f"{center_time_ms:.2f}ms"
            }

            # 返回模态框样式、图表和点信息
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

            logger.info("[OK] 锤速与延时Z-Score标准化散点图点击回调 - 返回模态框和图表")
            return modal_style, [dcc.Graph(figure=detail_figure_combined, style={'height': '600px'})], point_info

        except Exception as e:
            logger.error(f"[ERROR] 生成锤速与延时Z-Score标准化散点图详细图表失败: {e}")
            logger.error(traceback.format_exc())
            return current_style, [], no_update, no_update


    def _handle_key_delay_plot_click(self, scatter_clickData, session_id, current_style, source_plot_id='key-delay-scatter-plot'):
        """处理按键与相对延时散点图点击的主要逻辑"""
        logger.info(f"🔍 按键与相对延时散点图点击回调被触发 - source_plot_id: {source_plot_id}, clickData: {scatter_clickData is not None}")

        backend = self.session_manager.get_backend(session_id)
        if not backend:
            logger.warning("[WARNING] 没有找到backend")
            return current_style, [], no_update, no_update

        # 验证点击数据
        if 'points' not in scatter_clickData or len(scatter_clickData['points']) == 0:
            logger.warning("[WARNING] 按键与相对延时散点图点击回调 - scatter_clickData无效或没有points")
            return current_style, [], no_update, no_update

        point = scatter_clickData['points'][0]
        logger.info(f"🔍 按键与相对延时散点图点击 - 点击点数据: {point}")

        if not point.get('customdata'):
            logger.warning("[WARNING] 按键与相对延时散点图点击 - 点没有customdata")
            return current_style, [], no_update, no_update

        # 提取customdata - 按键与相对延时散点图格式: [按键ID, 算法名称, 录制索引, 播放索引]
        raw_customdata = point['customdata']
        logger.info(f"🔍 按键与相对延时散点图点击 - raw_customdata类型: {type(raw_customdata)}, 值: {raw_customdata}")

        if isinstance(raw_customdata, list) and len(raw_customdata) > 0:
            customdata = raw_customdata[0] if isinstance(raw_customdata[0], list) else raw_customdata
        else:
            customdata = raw_customdata

        if not isinstance(customdata, list):
            logger.warning(f"[WARNING] 按键与相对延时散点图点击 - customdata不是列表类型: {type(customdata)}, 值: {customdata}")
            return current_style, [], no_update, no_update

        logger.info(f"🔍 按键与相对延时散点图点击 - customdata: {customdata}, 长度: {len(customdata)}")

        if len(customdata) < 4:
            logger.warning(f"[WARNING] 按键与相对延时散点图点击 - customdata长度不足: {len(customdata)}")
            return current_style, [], no_update, no_update

        # 解析按键与相对延时散点图的customdata格式: [record_index, replay_index, key_id, delay_ms, display_name?, ...]
        record_index = customdata[0]
        replay_index = customdata[1]
        key_id = customdata[2]
        algorithm_name = customdata[4] if len(customdata) > 4 else None

        logger.info(f"🖱️ 按键与相对延时散点图点击: 算法={algorithm_name}, 按键={key_id}, record_index={record_index}, replay_index={replay_index}")

        # 计算中心时间
        center_time_ms = None
        try:
            # 检查是否有多个活跃算法
            active_algorithms = []
            if backend.multi_algorithm_mode and backend.multi_algorithm_manager:
                active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()

            # 判断是否真正处于多算法模式（有多个活跃算法）
            is_multi_algorithm = len(active_algorithms) > 1

            if is_multi_algorithm and algorithm_name:
                # 多算法模式 - 查找指定的算法
                algorithm = self._get_algorithm_for_zscore(backend, algorithm_name)
                if algorithm and algorithm.analyzer and algorithm.analyzer.note_matcher:
                    logger.info(f"[INFO] 使用多算法模式处理算法 '{algorithm_name}' (活跃算法数量: {len(active_algorithms)})")
                    matched_pairs = algorithm.analyzer.matched_pairs
                    for r_idx, p_idx, r_note, p_note in matched_pairs:
                        if r_idx == record_index and p_idx == replay_index:
                            # 计算keyon时间
                            record_keyon = r_note.after_touch.index[0] + r_note.offset if hasattr(r_note, 'after_touch') and not r_note.after_touch.empty else r_note.offset
                            replay_keyon = p_note.after_touch.index[0] + p_note.offset if hasattr(p_note, 'after_touch') and not p_note.after_touch.empty else p_note.offset
                            center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0  # 转换为ms
                            break
                    # 备用方案：从 offset_data 获取
                    if center_time_ms is None:
                        keyon_times = self._get_time_from_offset_data(algorithm.analyzer.note_matcher, record_index, replay_index)
                        if keyon_times:
                            record_keyon, replay_keyon = keyon_times
                            center_time_ms = self._calculate_center_time_ms(record_keyon, replay_keyon)
                else:
                    logger.warning(f"[WARNING] 算法 '{algorithm_name}' 不存在，降级到单算法模式 (活跃算法数量: {len(active_algorithms)})")
            else:
                logger.info(f"[INFO] 使用单算法模式处理 (活跃算法数量: {len(active_algorithms)}, algorithm_name: {algorithm_name})")

            # 单算法模式处理（包括只有一个算法的多算法模式）
            if backend.analyzer and backend.analyzer.note_matcher:
                matched_pairs = backend.analyzer.matched_pairs
                for r_idx, p_idx, r_note, p_note in matched_pairs:
                    if r_idx == record_index and p_idx == replay_index:
                        # 计算keyon时间
                        record_keyon = r_note.after_touch.index[0] + r_note.offset if hasattr(r_note, 'after_touch') and not r_note.after_touch.empty else r_note.offset
                        replay_keyon = p_note.after_touch.index[0] + p_note.offset if hasattr(p_note, 'after_touch') and not p_note.after_touch.empty else p_note.offset
                        center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0  # 转换为ms
                        break
                # 备用方案：从 offset_data 获取
                if center_time_ms is None:
                    keyon_times = self._get_time_from_offset_data(backend.analyzer.note_matcher, record_index, replay_index)
                    if keyon_times:
                        record_keyon, replay_keyon = keyon_times
                        center_time_ms = self._calculate_center_time_ms(record_keyon, replay_keyon)
        except Exception as e:
            logger.warning(f"[WARNING] 计算时间信息失败: {e}")

        point_info = {
            'algorithm_name': algorithm_name,
            'record_idx': record_index,
            'replay_idx': replay_index,
            'key_id': key_id,
            'source_plot_id': source_plot_id,  # 记录来源图表ID
            'center_time_ms': center_time_ms  # 预先计算的时间信息
        }

        # 生成详细曲线图
        detail_figure1, detail_figure2, detail_figure_combined = self._generate_detail_plots(backend, {
            'algorithm_name': algorithm_name,
            'record_index': record_index,
            'replay_index': replay_index
        })

        # 检查图表生成是否成功
        if detail_figure1 and detail_figure2 and detail_figure_combined:
            modal_style, graph_component, point_info_response = self._create_zscore_modal_response(detail_figure_combined, point_info)
            return modal_style, graph_component, point_info_response
        else:
            logger.warning("[WARNING] 按键与相对延时散点图点击回调 - 图表生成失败，部分图表为None")
            return current_style, [], no_update, no_update

    def generate_zscore_scatter_plot(self, session_id: str) -> Union[Any, NoUpdate]:
        """生成按键与延时Z-Score标准化散点图"""
        backend = self.session_manager.get_backend(session_id)
        if not backend:
            return no_update

        try:
            # 检查是否有分析数据
            if not backend.analyzer and not (hasattr(backend, 'multi_algorithm_mode') and backend.multi_algorithm_mode):
                logger.warning("[WARNING] 没有分析器，无法生成Z-Score标准化散点图")
                return backend.plot_generator._create_empty_plot("没有分析器")

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
            return backend.plot_generator._create_empty_plot(f"生成Z-Score标准化散点图失败: {str(e)}")

    def generate_hammer_velocity_scatter_plot(self, session_id: str) -> Union[Any, NoUpdate]:
        """生成锤速与延时Z-Score标准化散点图"""
        backend = self.session_manager.get_backend(session_id)
        if not backend:
            return no_update

        try:
            # 检查是否有激活的算法
            active_algorithms = backend.get_active_algorithms()
            if not active_algorithms:
                logger.debug("[DEBUG] 没有激活的算法，跳过散点图生成")
                return backend.plot_generator._create_empty_plot("没有激活的算法")

            # 生成锤速与延时散点图
            fig = backend.generate_hammer_velocity_delay_scatter_plot()

            logger.info("[OK] 锤速与延时Z-Score标准化散点图生成成功")
            return fig

        except Exception as e:
            logger.error(f"[ERROR] 生成锤速与延时Z-Score标准化散点图失败: {e}")
            logger.error(traceback.format_exc())
            return backend.plot_generator._create_empty_plot(f"生成锤速与延时Z-Score标准化散点图失败: {str(e)}")

    def generate_hammer_velocity_relative_delay_scatter_plot(self, session_id: str) -> Union[Any, NoUpdate]:
        """生成锤速与延时Z-Score标准化散点图"""
        backend = self.session_manager.get_backend(session_id)
        if not backend:
            return no_update

        try:
            # 检查是否有激活的算法
            active_algorithms = backend.get_active_algorithms()
            if not active_algorithms:
                logger.debug("[DEBUG] 没有激活的算法，跳过散点图生成")
                return backend.plot_generator._create_empty_plot("没有激活的算法")

            # 生成锤速与延时Z-Score标准化散点图
            fig = backend.generate_hammer_velocity_relative_delay_scatter_plot()

            logger.info("[OK] 锤速与延时Z-Score标准化散点图生成成功")
            return fig

        except Exception as e:
            logger.error(f"[ERROR] 生成锤速与延时Z-Score标准化散点图失败: {e}")
            logger.error(traceback.format_exc())
            return backend.plot_generator._create_empty_plot(f"生成锤速与延时Z-Score标准化散点图失败: {str(e)}")


def register_scatter_callbacks(app, session_manager: SessionManager):
    """注册散点图相关的回调函数"""
    handler = ScatterPlotHandler(session_manager)

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