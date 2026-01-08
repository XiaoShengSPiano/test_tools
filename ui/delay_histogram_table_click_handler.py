"""
延时直方图表格点击处理器
重构自 ui/callbacks.py 中的 handle_delay_histogram_table_click 函数
"""

import logging
import traceback
from typing import Dict, List, Optional, Tuple, Any
from dash import no_update
import dash
from dash._callback_context import CallbackContext

logger = logging.getLogger(__name__)


class DelayHistogramTableClickHandler:
    """延时直方图表格点击处理器类"""

    def __init__(self, session_manager=None):
        self.session_manager = session_manager

    def set_session_manager(self, session_manager):
        """设置 session_manager（用于延迟初始化）"""
        self.session_manager = session_manager

    def handle_delay_histogram_table_click(self, active_cell, close_modal_clicks, close_btn_clicks,
                                         table_data, session_id, current_style):
        """处理延时分布直方图详情表格点击，显示录制与播放对比曲线（悬浮窗）并支持跳转到瀑布图"""
        try:
            # 检测触发源
            ctx = dash.callback_context
            if not ctx.triggered:
                return current_style, [], no_update

            # 处理触发检测
            trigger_result = self._handle_trigger_detection(ctx)
            if trigger_result.get('is_close'):
                return trigger_result['modal_style'], [], no_update
            if trigger_result.get('should_skip'):
                return current_style, [], no_update

            # 验证和解析表格点击数据
            validation_result = self._validate_and_parse_table_data(active_cell, table_data)
            if not validation_result['valid']:
                return current_style, [], no_update

            row_data = validation_result['row_data']
            record_index = validation_result['record_index']
            replay_index = validation_result['replay_index']
            key_id = validation_result['key_id']
            algorithm_name = validation_result['algorithm_name']

            # 获取后端
            backend = self.session_manager.get_backend(session_id)
            if not backend:
                logger.warning("[WARNING] 没有找到backend")
                return current_style, [], no_update

            # 查找匹配的音符数据
            notes_result = self._find_matched_notes(backend, record_index, replay_index, key_id, algorithm_name)
            if not notes_result['valid']:
                return current_style, [], no_update

            record_note = notes_result['record_note']
            replay_note = notes_result['replay_note']
            final_algorithm_name = notes_result['final_algorithm_name']
            center_time_ms = notes_result['center_time_ms']

            # 查找其他算法的匹配音符
            other_notes_result = self._find_other_algorithm_notes(backend, final_algorithm_name, record_index)

            # 计算平均延时
            mean_delays_result = self._calculate_mean_delays(backend, final_algorithm_name)

            # 生成图表并返回
            chart_result = self._generate_chart_and_return(
                record_note, replay_note, final_algorithm_name,
                other_notes_result['other_algorithm_notes'], mean_delays_result['mean_delays'],
                record_index, replay_index, center_time_ms
            )

            return chart_result['modal_style'], chart_result['rendered_row'], chart_result['point_info']

        except Exception as e:
            logger.error(f"[ERROR] 处理延时直方图表格点击失败: {e}")
            logger.error(traceback.format_exc())
            return current_style, [], no_update

    def _handle_trigger_detection(self, ctx: CallbackContext) -> Dict[str, Any]:
        """处理触发源检测"""
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        logger.info(f"[PROCESS] 延时直方图表格点击回调触发：trigger_id={trigger_id}")

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
            return {'is_close': True, 'modal_style': modal_style}

        # 只有表格点击才继续处理
        if trigger_id != 'delay-histogram-detail-table':
            return {'should_skip': True}

        return {'continue': True}

    def _validate_and_parse_table_data(self, active_cell, table_data) -> Dict[str, Any]:
        """验证和解析表格点击数据"""
        if not active_cell or not table_data:
            logger.warning("[WARNING] active_cell或table_data为空")
            return {'valid': False}

        # 获取点击的行数据
        row_idx = active_cell.get('row')
        if row_idx is None or row_idx >= len(table_data):
            logger.warning(f"[WARNING] 行索引超出范围: row_idx={row_idx}, table_data长度={len(table_data)}")
            return {'valid': False}

        row_data = table_data[row_idx]
        record_index = row_data.get('record_index')
        replay_index = row_data.get('replay_index')
        key_id = row_data.get('key_id')  # 获取按键ID用于验证
        algorithm_name = row_data.get('algorithm_name')  # 可能为 None（单算法模式）

        logger.info(f"[STATS] 点击的行数据: record_index={record_index}, replay_index={replay_index}, key_id={key_id}, algorithm_name={algorithm_name}")

        # 检查索引是否有效
        if record_index == 'N/A' or replay_index == 'N/A' or record_index is None or replay_index is None:
            logger.warning("[WARNING] 索引无效")
            return {'valid': False}

        # 转换数据类型
        try:
            record_index = int(record_index)
            replay_index = int(replay_index)
            if key_id and key_id != 'N/A':
                key_id = int(key_id)
            else:
                key_id = None
        except (ValueError, TypeError) as e:
            logger.warning(f"[WARNING] 无法转换索引或key_id: record_index={record_index}, replay_index={replay_index}, key_id={key_id}, error={e}")
            return {'valid': False}

        return {
            'valid': True,
            'row_data': row_data,
            'record_index': record_index,
            'replay_index': replay_index,
            'key_id': key_id,
            'algorithm_name': algorithm_name
        }

    def _find_matched_notes(self, backend, record_index, replay_index, key_id, algorithm_name) -> Dict[str, Any]:
        """查找匹配的音符数据"""
        # 检查是否在多算法模式且提供了算法名称
        active_algorithms = backend.multi_algorithm_manager.get_active_algorithms() if backend.multi_algorithm_manager else []
        if len(active_algorithms) > 1 and algorithm_name and algorithm_name != 'N/A':
            return self._find_notes_multi_algorithm(backend, record_index, replay_index, key_id, algorithm_name)
        else:
            return self._find_notes_single_algorithm(backend, record_index, replay_index, key_id, algorithm_name)

    def _find_notes_multi_algorithm(self, backend, record_index, replay_index, key_id, algorithm_name) -> Dict[str, Any]:
        """多算法模式下查找音符"""
        active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()
        target_algorithm = None
        for alg in active_algorithms:
            if alg.metadata.algorithm_name == algorithm_name:
                target_algorithm = alg
                break

        if not target_algorithm or not target_algorithm.analyzer:
            logger.warning(f"[WARNING] 未找到算法: {algorithm_name}")
            return {'valid': False}

        # 从matched_pairs中查找匹配对
        matched_pairs = target_algorithm.analyzer.matched_pairs if hasattr(target_algorithm.analyzer, 'matched_pairs') else []
        if not matched_pairs:
            logger.warning("[WARNING] 算法没有匹配对数据")
            return {'valid': False}

        # 查找匹配对
        result = self._find_notes_from_matched_pairs(matched_pairs, record_index, replay_index, key_id, target_algorithm.analyzer)
        if result['valid']:
            result['final_algorithm_name'] = algorithm_name

        return result

    def _find_notes_single_algorithm(self, backend, record_index, replay_index, key_id, algorithm_name) -> Dict[str, Any]:
        """单算法模式下查找音符"""
        analyzer = backend._get_current_analyzer()
        if not analyzer:
            logger.warning("[WARNING] 没有分析器")
            return {'valid': False}

        # 从matched_pairs中查找匹配对
        matched_pairs = analyzer.matched_pairs if hasattr(analyzer, 'matched_pairs') else []
        if not matched_pairs:
            logger.warning("[WARNING] 没有匹配对数据")
            return {'valid': False}

        # 查找匹配对
        result = self._find_notes_from_matched_pairs(matched_pairs, record_index, replay_index, key_id, analyzer)
        if result['valid']:
            result['final_algorithm_name'] = algorithm_name if algorithm_name and algorithm_name != 'N/A' else None

        return result

    def _find_notes_from_matched_pairs(self, matched_pairs, record_index, replay_index, key_id, analyzer) -> Dict[str, Any]:
        """从matched_pairs中查找匹配的音符"""
        for r_idx, p_idx, r_note, p_note in matched_pairs:
            if r_idx == record_index and p_idx == replay_index:
                # 验证key_id（如果提供了）
                if key_id is not None and r_note.id != key_id:
                    logger.warning(f"[WARNING] key_id不匹配: 表格中的key_id={key_id}, 匹配对中的key_id={r_note.id}")
                    continue

                logger.info(f"[OK] 从matched_pairs中找到匹配对: record_index={record_index}, replay_index={replay_index}, key_id={r_note.id}")

                # 计算keyon时间，用于跳转
                center_time_ms = self._calculate_center_time(r_note, p_note, analyzer, record_index, replay_index)

                return {
                    'valid': True,
                    'record_note': r_note,
                    'replay_note': p_note,
                    'center_time_ms': center_time_ms
                }

        logger.warning(f"[WARNING] 未找到匹配对: record_index={record_index}, replay_index={replay_index}")
        return {'valid': False}

    def _calculate_center_time(self, r_note, p_note, analyzer, record_index, replay_index) -> Optional[float]:
        """计算中心时间"""
        try:
            record_keyon = r_note.after_touch.index[0] + r_note.offset if hasattr(r_note, 'after_touch') and not r_note.after_touch.empty else r_note.offset
            replay_keyon = p_note.after_touch.index[0] + p_note.offset if hasattr(p_note, 'after_touch') and not p_note.after_touch.empty else p_note.offset
            center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0  # 转换为ms
            return center_time_ms
        except Exception as e:
            logger.warning(f"[WARNING] 计算时间信息失败: {e}")
            # 备用方案：从 offset_data 获取
            if analyzer.note_matcher:
                try:
                    offset_data = analyzer.note_matcher.get_offset_alignment_data()
                    if offset_data:
                        for item in offset_data:
                            if item.get('record_index') == record_index and item.get('replay_index') == replay_index:
                                record_keyon = item.get('record_keyon', 0)
                                replay_keyon = item.get('replay_keyon', 0)
                                if record_keyon and replay_keyon:
                                    center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0
                                    return center_time_ms
                except Exception as e2:
                    logger.warning(f"[WARNING] 从offset_data获取时间信息失败: {e2}")
            return None

    def _find_other_algorithm_notes(self, backend, final_algorithm_name, record_index) -> Dict[str, Any]:
        """查找其他算法的匹配音符"""
        other_algorithm_notes = []  # [(algorithm_name, play_note), ...]

        active_algorithms = backend.multi_algorithm_manager.get_active_algorithms() if backend.multi_algorithm_manager else []
        if len(active_algorithms) > 1:
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

        return {'other_algorithm_notes': other_algorithm_notes}

    def _calculate_mean_delays(self, backend, final_algorithm_name) -> Dict[str, Any]:
        """计算平均延时"""
        mean_delays = {}

        active_algorithms = backend.multi_algorithm_manager.get_active_algorithms() if backend.multi_algorithm_manager else []
        if len(active_algorithms) > 1 and final_algorithm_name:
            # 多算法模式
            algorithm = backend.multi_algorithm_manager.get_algorithm(final_algorithm_name)
            if algorithm and algorithm.analyzer:
                mean_error_0_1ms = algorithm.analyzer.get_mean_error()
                mean_delays[final_algorithm_name] = mean_error_0_1ms / 10.0  # 转换为毫秒
            else:
                logger.error(f"[ERROR] 无法获取算法 '{final_algorithm_name}' 的平均延时")
                return {'valid': False}
        else:
            # 单算法模式
            analyzer = backend._get_current_analyzer()
            if analyzer:
                mean_error_0_1ms = analyzer.get_mean_error()
                mean_delays[final_algorithm_name or 'default'] = mean_error_0_1ms / 10.0  # 转换为毫秒
            else:
                logger.error("[ERROR] 无法获取单算法模式的平均延时")
                return {'valid': False}

        return {'mean_delays': mean_delays}

    def _generate_chart_and_return(self, record_note, replay_note, final_algorithm_name,
                                  other_algorithm_notes, mean_delays, record_index, replay_index, center_time_ms) -> Dict[str, Any]:
        """生成对比曲线图并准备返回数据"""
        try:
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
                return {'modal_style': {'display': 'none'}, 'rendered_row': [], 'point_info': None}

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

            rendered_row = dash.dcc.Graph(figure=detail_figure_combined, style={'height': '600px'})

            # 设置点击点信息，用于跳转到瀑布图
            key_id = getattr(record_note, 'id', 'N/A') if record_note else 'N/A'
            point_info = {
                'algorithm_name': final_algorithm_name,
                'record_idx': record_index,
                'replay_idx': replay_index,
                'key_id': key_id,
                'source_plot_id': 'delay-histogram-table',  # 标识来源是延时直方图表格
                'center_time_ms': center_time_ms
            }

            logger.info(f"[OK] 延时直方图表格点击处理成功，算法: {final_algorithm_name}, 按键ID: {key_id}")

            return {
                'modal_style': modal_style,
                'rendered_row': [rendered_row],
                'point_info': point_info
            }

        except Exception as e:
            logger.error(f"[ERROR] 生成图表失败: {e}")
            return {'modal_style': {'display': 'none'}, 'rendered_row': [], 'point_info': None}


# 创建全局处理器实例
delay_histogram_table_click_handler = DelayHistogramTableClickHandler(None)  # session_manager 会在注册时设置
