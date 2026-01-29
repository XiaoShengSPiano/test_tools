"""
延时时间序列图点击处理器
重构自 ui/callbacks.py 中的 handle_delay_time_series_click_multi 函数
"""

import logging
import traceback
from typing import Dict, List, Optional, Tuple, Any
from dash import no_update, dcc
import dash
from dash._callback_context import CallbackContext

logger = logging.getLogger(__name__)


class DelayTimeSeriesHandler:
    """延时时间序列图点击处理器类"""

    def __init__(self, session_manager=None):
        self.session_manager = session_manager

    def set_session_manager(self, session_manager):
        """设置 session_manager（用于延迟初始化）"""
        self.session_manager = session_manager

    def handle_delay_time_series_click_multi(self, raw_click_data, relative_click_data, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理延时时间序列图点击（多算法模式），显示音符分析曲线（悬浮窗）"""
        logger.info("[START] handle_delay_time_series_click_multi 回调被触发")

        # 检测触发源
        ctx = dash.callback_context
        if not ctx.triggered:
            return current_style, [], no_update, no_update, no_update

        trigger_result = self._handle_trigger_detection(ctx)
        if trigger_result.get('is_close_button'):
            return trigger_result['modal_style'], [], no_update, no_update, no_update

        if trigger_result.get('should_skip'):
            return current_style, [], no_update, no_update, no_update

        trigger_id = trigger_result.get('trigger_id')

        # 获取后端
        backend = self.session_manager.get_backend(session_id)
        if not backend:
            logger.warning("[WARNING] backend为空")
            return current_style, [], no_update, no_update, no_update

        # 确定点击数据来源
        # 确定点击数据来源
        if trigger_id == 'scatter-analysis-raw-delay-plot':
            delay_click_data = raw_click_data
            source_plot_id = 'scatter-analysis-raw-delay-plot'
            logger.info("[INFO] 点击来自原始延时图")
        elif trigger_id == 'scatter-analysis-relative-delay-plot':
            delay_click_data = relative_click_data
            source_plot_id = 'scatter-analysis-relative-delay-plot'
            logger.info("[INFO] 点击来自相对延时图")
        else:
            logger.warning("[WARNING] 未知的触发源")
            return current_style, [], no_update, no_update, no_update

        try:
            # 验证和解析点击数据
            validation_result = self._validate_click_data(delay_click_data)
            if not validation_result['valid']:
                return current_style, [], no_update, no_update, no_update

            # 提取点击点信息
            point_data = self._extract_point_data(validation_result['point'])

            # 查找匹配的算法和音符
            match_result = self._find_algorithm_match(backend, point_data)
            if not match_result['found']:
                return current_style, [], no_update, no_update, no_update

            # 计算时间信息
            time_result = self._calculate_time_info(backend, match_result, point_data)

            # 生成图表
            chart_result = self._generate_chart(backend, match_result, point_data, time_result)

            if not chart_result['success']:
                modal_style = self._create_modal_style()
                return modal_style, [], no_update, no_update, no_update

            # 准备返回数据
            return_data = self._prepare_return_data(match_result, point_data, chart_result, time_result, source_plot_id)

            logger.info("[OK] 延时时间序列图点击处理成功（多算法模式）")
            return return_data['modal_style'], return_data['rendered_row'], return_data['point_info'], no_update, no_update

        except Exception as e:
            logger.error(f"[ERROR] 处理延时时间序列图点击失败（多算法模式）: {e}")
            logger.error(traceback.format_exc())
            return current_style, [], no_update, no_update, no_update

    def _handle_trigger_detection(self, ctx: CallbackContext) -> Dict[str, Any]:
        """处理触发源检测"""
        trigger_id_raw = ctx.triggered[0]['prop_id'].split('.')[0]
        logger.info(f"🔍 原始触发ID: {trigger_id_raw}")

        # 解析 Plot ID (支持字典模式匹配)
        plot_id = trigger_id_raw
        if trigger_id_raw.startswith('{'):
            try:
                import json
                plot_id = json.loads(trigger_id_raw).get('id', trigger_id_raw)
            except Exception:
                pass

        # 如果点击了关闭按钮，隐藏模态框
        if plot_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
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
            return {
                'is_close_button': True,
                'modal_style': modal_style
            }

        # 只有在点击了时间序列图时才处理
        # 注意：这里需要检查解析后的 plot_id
        if plot_id not in ['raw-delay-time-series-plot', 'relative-delay-time-series-plot'] or not ctx.triggered[0]['value']:
            return {'should_skip': True}

        logger.info(f"[TARGET] 检测到 {plot_id} 点击")
        return {'is_close_button': False, 'should_skip': False, 'trigger_id': plot_id}

    def _validate_click_data(self, delay_click_data) -> Dict[str, Any]:
        """验证点击数据"""
        if 'points' not in delay_click_data or len(delay_click_data['points']) == 0:
            logger.warning("[WARNING] clickData中没有points")
            return {'valid': False}

        point = delay_click_data['points'][0]
        if not point.get('customdata'):
            logger.warning("[WARNING] point中没有customdata")
            return {'valid': False}

        return {'valid': True, 'point': point}

    def _extract_point_data(self, point) -> Dict[str, Any]:
        """提取点击点数据"""
        customdata = point['customdata']
        logger.info(f"[DATA] customdata: {customdata}")

        if not isinstance(customdata, list) or len(customdata) < 3:
            raise ValueError(f"customdata格式错误: {customdata}")

        key_id = customdata[0]
        record_index = customdata[1]
        replay_index = customdata[2]
        algorithm_name = customdata[3] if len(customdata) > 3 else None

        logger.info(f"[STATS] 提取的数据: key_id={key_id}, record_index={record_index}, replay_index={replay_index}, algorithm_name={algorithm_name}")

        return {
            'key_id': key_id,
            'record_index': record_index,
            'replay_index': replay_index,
            'algorithm_name': algorithm_name,
            'customdata': customdata
        }

    def _find_algorithm_match(self, backend, point_data) -> Dict[str, Any]:
        """查找匹配的算法和音符"""
        key_id = point_data['key_id']
        record_index = point_data['record_index']
        replay_index = point_data['replay_index']
        algorithm_name = point_data['algorithm_name']

        record_note = None
        replay_note = None
        final_algorithm_name = None

        active_algorithms = backend.multi_algorithm_manager.get_active_algorithms() if backend.multi_algorithm_manager else []
        if len(active_algorithms) > 1:
            # 多算法模式
            algorithm = backend.multi_algorithm_manager.get_algorithm(algorithm_name)
            if algorithm and algorithm.analyzer and hasattr(algorithm.analyzer, 'matched_pairs'):
                matched_pairs = algorithm.analyzer.matched_pairs
                for rec_note, rep_note, match_type, error_ms in matched_pairs:
                    # 使用UUID进行比较（因为offset_data中使用UUID作为index）
                    if str(rec_note.uuid) == str(record_index) and str(rep_note.uuid) == str(replay_index):
                        record_note = rec_note
                        replay_note = rep_note
                        final_algorithm_name = algorithm_name
                        logger.info(f"[OK] 在多算法模式中找到匹配对 (UUID匹配)")
                        break
        else:
            # 单算法模式
            analyzer = backend._get_current_analyzer()
            if analyzer and hasattr(analyzer, 'matched_pairs'):
                matched_pairs = analyzer.matched_pairs
                for rec_note, rep_note, match_type, error_ms in matched_pairs:
                    # 使用UUID进行比较
                    if str(rec_note.uuid) == str(record_index) and str(rep_note.uuid) == str(replay_index):
                        record_note = rec_note
                        replay_note = rep_note
                        final_algorithm_name = None
                        logger.info(f"[OK] 在单算法模式中找到匹配对 (UUID匹配)")
                        break

        if not record_note or not replay_note:
            logger.warning("[WARNING] 未找到匹配对")
            return {'found': False}

        return {
            'found': True,
            'record_note': record_note,
            'replay_note': replay_note,
            'final_algorithm_name': final_algorithm_name,
            'algorithm_name': algorithm_name
        }

    def _calculate_time_info(self, backend, match_result, point_data) -> Dict[str, Any]:
        """计算时间信息"""
        record_note = match_result['record_note']
        replay_note = match_result['replay_note']
        algorithm_name = match_result['algorithm_name']
        customdata = point_data['customdata']

        center_time_ms = None

        # 计算keyon时间
        try:
            record_keyon = record_note.after_touch.index[0] + record_note.offset if hasattr(record_note, 'after_touch') and not record_note.after_touch.empty else record_note.offset
            replay_keyon = replay_note.after_touch.index[0] + replay_note.offset if hasattr(replay_note, 'after_touch') and not replay_note.after_touch.empty else replay_note.offset
            center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0  # 转换为ms
        except Exception as e:
            logger.warning(f"[WARNING] 计算时间信息失败: {e}")
            # 备用方案：从 customdata 获取时间信息（如果可用）
            if len(customdata) >= 7:
                record_time = customdata[7] if len(customdata) > 7 else None
                replay_time = customdata[6] if len(customdata) > 6 else None
                if record_time is not None and replay_time is not None:
                    center_time_ms = ((record_time + replay_time) / 2.0) / 10.0

        # 备用方案：从 offset_data 获取
        if center_time_ms is None:
            active_algorithms = backend.multi_algorithm_manager.get_active_algorithms() if backend.multi_algorithm_manager else []
            if len(active_algorithms) > 1 and algorithm_name:
                algorithm = backend.multi_algorithm_manager.get_algorithm(algorithm_name)
                if algorithm and algorithm.analyzer.note_matcher:
                    try:
                        offset_data = algorithm.analyzer.note_matcher.get_offset_alignment_data()
                        if offset_data:
                            for item in offset_data:
                                if item.get('record_index') == point_data['record_index'] and item.get('replay_index') == point_data['replay_index']:
                                    record_keyon = item.get('record_keyon', 0)
                                    replay_keyon = item.get('replay_keyon', 0)
                                    if record_keyon and replay_keyon:
                                        center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0
                                        break
                    except Exception as e:
                        logger.warning(f"[WARNING] 从offset_data获取时间信息失败: {e}")

        return {'center_time_ms': center_time_ms}

    def _generate_chart(self, backend, match_result, point_data, time_result) -> Dict[str, Any]:
        """生成图表"""
        try:
            record_fig, replay_fig, comparison_fig = backend.generate_multi_algorithm_scatter_detail_plot_by_indices(
                match_result['algorithm_name'], point_data['record_index'], point_data['replay_index']
            )
            if not comparison_fig:
                logger.warning("[WARNING] 多算法模式曲线生成失败")
                return {'success': False}

            logger.info("[OK] 多算法模式曲线生成成功")
            return {'success': True, 'figure': comparison_fig}

        except Exception as e:
            logger.error(f"[ERROR] 多算法模式生成曲线失败: {e}")
            return {'success': False}

    def _create_modal_style(self) -> Dict[str, str]:
        """创建模态框样式"""
        return {
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

    def _prepare_return_data(self, match_result, point_data, chart_result, time_result, source_plot_id) -> Dict[str, Any]:
        """准备返回数据"""

        # 保存点击点信息
        point_info = {
            'key_id': point_data['key_id'],
            'record_idx': point_data['record_index'],
            'replay_idx': point_data['replay_index'],
            'algorithm_name': match_result['final_algorithm_name'],
            'source_plot_id': source_plot_id,
            'center_time_ms': time_result['center_time_ms']  # 预先计算的时间信息
        }

        rendered_row = dcc.Graph(figure=chart_result['figure'], style={'height': '800px'})

        return {
            'modal_style': self._create_modal_style(),
            'rendered_row': [rendered_row],
            'point_info': point_info
        }


# 创建全局处理器实例
delay_time_series_handler = DelayTimeSeriesHandler(None)  # session_manager 会在注册时设置
