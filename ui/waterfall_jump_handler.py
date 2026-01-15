"""
瀑布图跳转处理器
重构自 ui/callbacks.py 中的 handle_jump_to_waterfall 函数
继承 ScatterHandlerBase 以复用通用功能
"""

import logging
import traceback
from typing import Optional
from dash import no_update
from backend.session_manager import SessionManager
from backend.piano_analysis_backend import PianoAnalysisBackend
from ui.scatter_handler_base import ScatterHandlerBase

logger = logging.getLogger(__name__)


class WaterfallJumpHandler(ScatterHandlerBase):
    """瀑布图跳转处理器类 - 继承自 ScatterHandlerBase"""

    def __init__(self, session_manager: SessionManager):
        super().__init__(session_manager)

    def handle_jump_to_waterfall(self, n_clicks, session_id, point_info):
        """处理跳转到瀑布图按钮点击"""
        from dash import callback_context

        ctx = callback_context
        if not ctx.triggered:
            return no_update, no_update, no_update, no_update

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        if trigger_id != 'jump-to-waterfall-btn':
            return no_update, no_update, no_update, no_update

        if not n_clicks or n_clicks == 0:
            return no_update, no_update, no_update, no_update

        if not point_info:
            logger.warning("[WARNING] 没有存储的数据点信息，无法跳转")
            return no_update, no_update, no_update, no_update

        # 获取来源图表ID和子图索引
        source_plot_id = point_info.get('source_plot_id', None)
        source_subplot_idx = point_info.get('source_subplot_idx', None)

        # 如果是相对延时分布图，构建包含子图索引的字典
        if source_plot_id == 'relative-delay-distribution-plot' and source_subplot_idx is not None:
            source_plot_id = {
                'type': 'relative-delay-distribution-plot',
                'index': source_subplot_idx
            }

        backend = self.session_manager.get_backend(session_id)
        if not backend:
            logger.warning("[WARNING] 没有找到backend")
            return no_update, no_update, no_update, no_update

        try:
            # 验证和提取数据点信息
            data_validation = self._validate_point_info(point_info)
            if not data_validation['valid']:
                return no_update, no_update, no_update, no_update

            algorithm_name = data_validation['algorithm_name']
            record_idx = data_validation['record_idx']
            replay_idx = data_validation['replay_idx']
            key_id = data_validation['key_id']
            is_error_table = data_validation['is_error_table']

            logger.info(f"[PROCESS] 跳转到瀑布图: 算法={algorithm_name}, record_idx={record_idx}, replay_idx={replay_idx}, 按键={key_id}")

            # 生成瀑布图
            waterfall_fig = self._generate_waterfall_plot(backend)
            if not waterfall_fig:
                return no_update, no_update, no_update, no_update

            # 计算时间信息
            center_time_ms = self._calculate_jump_center_time_ms(
                point_info, algorithm_name, record_idx, replay_idx,
                key_id, is_error_table, backend
            )

            # 添加标记到瀑布图
            if center_time_ms is not None and key_id is not None:
                self._add_jump_markers_to_waterfall(
                    waterfall_fig, center_time_ms, key_id, algorithm_name,
                    source_plot_id, backend
                )

            # 关闭模态框
            modal_style = self._get_modal_close_style()

            # 返回更新后的瀑布图、切换到瀑布图标签页、关闭模态框、保存来源图表ID
            return waterfall_fig, 'waterfall-tab', modal_style, source_plot_id

        except Exception as e:
            logger.error(f"[ERROR] 跳转到瀑布图失败: {e}")
            logger.error(traceback.format_exc())
            return no_update, no_update, no_update, no_update

    def _validate_point_info(self, point_info):
        """验证和提取数据点信息"""
        algorithm_name = point_info.get('algorithm_name')
        record_idx = point_info.get('record_idx')
        replay_idx = point_info.get('replay_idx')
        key_id = point_info.get('key_id')
        source_plot_id = point_info.get('source_plot_id', '')

        # 检查是否来自错误表格（丢锤/多锤）
        is_error_table = source_plot_id and 'error-table' in source_plot_id

        if not is_error_table and (record_idx is None or replay_idx is None):
            # 非错误表格需要完整的record_idx和replay_idx
            logger.warning(f"[WARNING] 数据点信息不完整: {point_info}")
            return {'valid': False}
        elif is_error_table and record_idx is None and replay_idx is None:
            # 错误表格至少需要一个索引
            logger.warning(f"[WARNING] 错误表格数据点信息不完整: {point_info}")
            return {'valid': False}

        return {
            'valid': True,
            'algorithm_name': algorithm_name,
            'record_idx': record_idx,
            'replay_idx': replay_idx,
            'key_id': key_id,
            'is_error_table': is_error_table
        }

    def _generate_waterfall_plot(self, backend):
        """生成瀑布图"""
        waterfall_fig = backend.generate_waterfall_plot()
        if not waterfall_fig:
            logger.warning(f"[WARNING] 瀑布图生成失败")
        return waterfall_fig

    def _calculate_jump_center_time_ms(self, point_info, algorithm_name, record_idx, replay_idx, key_id, is_error_table, backend):
        """
        计算跳转点的中心时间（毫秒）
        
        优先使用 point_info 中预先计算的时间，否则使用继承的方法计算
        """
        # 优先使用 point_info 中预先计算的时间信息
        center_time_ms = point_info.get('center_time_ms')

        # 对于错误表格（丢锤/多锤），如果已经有center_time_ms，直接使用
        if is_error_table and center_time_ms is not None:
            logger.info(f"[OK] 使用错误表格预先计算的时间信息: center_time_ms={center_time_ms:.1f}ms")
            return center_time_ms

        # 如果没有预先计算的时间信息，使用继承的方法计算
        if center_time_ms is None:
            try:
                logger.info(f"🔍 开始计算跳转点时间: algorithm_name={algorithm_name}, record_idx={record_idx}, replay_idx={replay_idx}, key_id={key_id}")
                
                # 使用继承的统一方法计算时间
                center_time_ms = self._calculate_center_time_for_note_pair(
                    backend, record_idx, replay_idx, algorithm_name
                )
                
                # 如果标准方法失败且是错误表格，尝试从初始数据获取
                if center_time_ms is None and is_error_table:
                    center_time_ms = self._calculate_time_from_error_table(
                        backend, algorithm_name, record_idx, replay_idx
                    )

            except Exception as e:
                logger.warning(f"[WARNING] 计算时间信息失败: {e}")
                logger.error(traceback.format_exc())

        if center_time_ms is not None:
            logger.info(f"[OK] 计算得到时间信息: center_time_ms={center_time_ms:.1f}ms")

        logger.info(f"🔍 最终结果: center_time_ms={center_time_ms}, key_id={key_id}")
        return center_time_ms

    def _calculate_time_from_error_table(self, backend: PianoAnalysisBackend, 
                                         algorithm_name: Optional[str], 
                                         record_idx: Optional[int], 
                                         replay_idx: Optional[int]) -> Optional[float]:
        """
        从错误表格（丢锤/多锤）获取时间信息
        
        Args:
            backend: 后端实例
            algorithm_name: 算法名称（多算法模式）
            record_idx: 录制音符索引
            replay_idx: 播放音符索引
            
        Returns:
            Optional[float]: 时间（毫秒），失败返回 None
        """
        # 获取分析器
        analyzer = self._get_analyzer_for_algorithm(backend, algorithm_name)
        if not analyzer:
            return None
        
        # 从初始数据获取时间
        if record_idx is not None:
            # 丢锤：从录制数据获取时间
            initial_data = getattr(analyzer, 'initial_valid_record_data', [])
            if record_idx < len(initial_data):
                note = initial_data[record_idx]
                time_ms = self._extract_time_from_note_ms(note)
                if time_ms is not None:
                    logger.info(f"[OK] 错误表格(丢锤): 从录制数据获取时间，time_ms={time_ms:.1f}ms")
                    return time_ms
        
        if replay_idx is not None:
            # 多锤：从播放数据获取时间
            initial_data = getattr(analyzer, 'initial_valid_replay_data', [])
            if replay_idx < len(initial_data):
                note = initial_data[replay_idx]
                time_ms = self._extract_time_from_note_ms(note)
                if time_ms is not None:
                    logger.info(f"[OK] 错误表格(多锤): 从播放数据获取时间，time_ms={time_ms:.1f}ms")
                    return time_ms
        
        return None
    
    def _extract_time_from_note_ms(self, note) -> Optional[float]:
        """
        从音符对象中提取时间信息（毫秒）
        
        Args:
            note: Note对象
            
        Returns:
            Optional[float]: 时间（毫秒），失败返回 None
        """
        if note.key_on_ms is not None:
            return note.key_on_ms

        return None

    def _add_jump_markers_to_waterfall(self, waterfall_fig, center_time_ms, key_id, algorithm_name, source_plot_id, backend):
        """在瀑布图中添加跳转标记"""
        try:
            import plotly.graph_objects as go
        except ImportError:
            logger.warning("[WARNING] 无法导入 plotly.graph_objects，跳过添加标记")
            return

        # 计算标记的y位置
        marker_y = self._calculate_marker_y_position(key_id, algorithm_name, source_plot_id, backend)

        logger.info(f"🔍 最终标记位置: x={center_time_ms:.2f}ms, y={marker_y:.2f}, key_id={key_id}")

        # 添加垂直参考线标记跳转的数据点
        self._add_vertical_reference_line(waterfall_fig, center_time_ms, key_id, algorithm_name)

        # 在按键位置添加一个醒目的标记点
        self._add_highlight_marker(waterfall_fig, center_time_ms, marker_y, key_id, algorithm_name)

        logger.info(f"[OK] 已在瀑布图中添加跳转标记: 按键={key_id}, 时间={center_time_ms:.1f}ms, y位置={marker_y:.1f}")

    def _calculate_marker_y_position(self, key_id, algorithm_name, source_plot_id, backend):
        """计算标记的Y轴位置"""
        try:
            marker_y = float(key_id)
            logger.info(f"🔍 初始marker_y={marker_y} (key_id={key_id})")
        except (ValueError, TypeError):
            logger.warning(f"[WARNING] 无法转换key_id为float: {key_id}")
            marker_y = 0.0

        # 检查是否是错误表格（丢锤/多锤）
        is_error_table = source_plot_id and 'error-table' in str(source_plot_id)
        logger.info(f"🔍 is_error_table={is_error_table}, source_plot_id={source_plot_id}")

        if is_error_table:
            # 错误表格：根据表格类型决定是否添加0.2偏移
            if source_plot_id == 'error-table-multi' or (isinstance(source_plot_id, str) and 'error-table-multi' in source_plot_id):
                # 多锤：replay类型，需要添加0.2偏移
                marker_y += 0.2
                logger.info(f"🔍 多锤：添加0.2偏移，marker_y={marker_y}")
            else:
                # 丢锤：record类型，不需要添加0.2偏移
                logger.info(f"🔍 丢锤：不添加0.2偏移，marker_y={marker_y}")

        active_algorithms = backend.multi_algorithm_manager.get_active_algorithms() if backend.multi_algorithm_manager else []
        if algorithm_name and len(active_algorithms) > 1:
            # 多算法模式：需要找到该算法对应的y偏移
            marker_y = self._apply_algorithm_y_offset(marker_y, algorithm_name, backend)
        else:
            logger.info(f"🔍 单算法模式或无算法名称，marker_y={marker_y}")

        return marker_y

    def _apply_algorithm_y_offset(self, marker_y, algorithm_name, backend):
        """应用多算法模式的Y轴偏移"""
        active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()
        algorithm_y_offset = 0
        algorithm_y_range = 100  # 每个算法偏移100个单位
        for idx, alg in enumerate(active_algorithms):
            if alg.metadata.algorithm_name == algorithm_name:
                algorithm_y_offset = idx * algorithm_y_range
                break
        marker_y = marker_y + algorithm_y_offset
        logger.info(f"🔍 多算法模式：添加algorithm_y_offset={algorithm_y_offset}，最终marker_y={marker_y}")
        return marker_y

    def _add_vertical_reference_line(self, waterfall_fig, center_time_ms, key_id, algorithm_name):
        """添加垂直参考线"""
        waterfall_fig.add_vline(
            x=center_time_ms,
            line_dash="dash",
            line_color="red",
            line_width=4,
            opacity=0.9,
            annotation_text=f"跳转点: 按键 {key_id}" + (f" (算法: {algorithm_name})" if algorithm_name else ""),
            annotation_position="top",
            annotation=dict(
                font=dict(size=16, color="red", family="Arial Black"),
                bgcolor="rgba(255, 255, 255, 0.9)",
                bordercolor="red",
                borderwidth=2,
                borderpad=4
            )
        )

    def _add_highlight_marker(self, waterfall_fig, center_time_ms, marker_y, key_id, algorithm_name):
        """添加高亮标记点"""
        import plotly.graph_objects as go

        waterfall_fig.add_trace(go.Scatter(
            x=[center_time_ms],
            y=[marker_y],
            mode='markers+text',
            marker=dict(
                size=25,
                color='red',
                symbol='star',
                line=dict(width=3, color='white'),
                opacity=0.9
            ),
            text=[f"按键 {key_id}"],
            textposition="top center",
            textfont=dict(size=16, color="red", family="Arial Black", weight="bold"),
            name='跳转标记',
            showlegend=False,
            hovertemplate=f'<b>[TARGET] 跳转点</b><br>按键: {key_id}<br>时间: {center_time_ms:.1f}ms' + (f'<br>算法: {algorithm_name}' if algorithm_name else '') + '<extra></extra>'
        ))

    def _get_modal_close_style(self):
        """获取关闭模态框的样式"""
        return {
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
