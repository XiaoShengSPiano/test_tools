"""
延迟值点击处理器
重构自 ui/callbacks.py 中的 handle_delay_value_click 函数
"""

import logging
import ast
from typing import Dict, List, Optional, Tuple, Any
from dash import no_update, dcc
import dash
from dash._callback_context import CallbackContext

logger = logging.getLogger(__name__)


class DelayValueClickHandler:
    """延迟值点击处理器类"""

    def __init__(self, session_manager=None):
        self.session_manager = session_manager

    def set_session_manager(self, session_manager):
        """设置 session_manager（用于延迟初始化）"""
        self.session_manager = session_manager

    def handle_delay_value_click(self, max_clicks_list, min_clicks_list, close_modal_clicks, close_btn_clicks,
                                max_ids_list, min_ids_list, session_id, current_style):
        """处理最大/最小延迟字段点击，显示对应按键的曲线对比图"""
        try:
            logger.info("[START] handle_delay_value_click 回调被触发")

            # 检测触发源
            ctx = dash.callback_context
            if not ctx.triggered:
                logger.info("[DEBUG] 没有触发事件")
                return current_style, [], None

            # 处理触发检测
            trigger_result = self._handle_trigger_detection(ctx, max_clicks_list, min_clicks_list)
            if trigger_result.get('is_close'):
                logger.info("[DEBUG] 检测到关闭按钮点击")
                return trigger_result['modal_style'], [], None
            if trigger_result.get('should_skip'):
                logger.info("[DEBUG] 跳过处理（可能是布局更新）")
                return current_style, [], None

            # 解析触发信息
            parse_result = self._parse_trigger_info(ctx, max_clicks_list, min_clicks_list, max_ids_list, min_ids_list)
            if not parse_result['valid']:
                logger.error("[ERROR] 解析触发信息失败")
                return current_style, [], None

            delay_type = parse_result['delay_type']
            algorithm_name = parse_result['algorithm_name']
            logger.info(f"[DEBUG] 解析结果: delay_type={delay_type}, algorithm_name={algorithm_name}")

            # 获取后端
            backend = self.session_manager.get_backend(session_id)
            if not backend:
                logger.warning("[WARNING] backend为空")
                return current_style, [], None

            # 获取音符数据
            logger.info("[DEBUG] 开始获取音符数据")
            notes_result = self._get_notes_data(backend, algorithm_name, delay_type)
            if not notes_result['valid']:
                logger.error("[ERROR] 获取音符数据失败")
                return current_style, [], None

            record_note, replay_note, record_index, replay_index = notes_result['notes']
            logger.info(f"[DEBUG] 获取到音符数据: record_index={record_index}, replay_index={replay_index}")

            # 查找其他算法的匹配音符
            logger.info("[DEBUG] 开始查找其他算法的匹配音符")
            other_notes_result = self._find_other_algorithm_notes(backend, algorithm_name, record_note)
            logger.info(f"[DEBUG] 找到 {len(other_notes_result['other_algorithm_notes'])} 个其他算法的匹配音符")

            # 计算平均延时
            logger.info("[DEBUG] 开始计算平均延时")
            mean_delays_result = self._calculate_mean_delays(backend, algorithm_name)
            logger.info(f"[DEBUG] 平均延时计算完成: {mean_delays_result['mean_delays']}")

            # 生成图表并返回
            logger.info("[DEBUG] 开始生成图表")
            chart_result = self._generate_chart_and_return(
                record_note, replay_note, algorithm_name, delay_type,
                other_notes_result['other_algorithm_notes'], mean_delays_result['mean_delays'],
                record_index, replay_index
            )

            logger.info("[SUCCESS] 延迟值点击处理完成")
            return chart_result['modal_style'], chart_result['rendered_row'], chart_result['clicked_point_info']

        except Exception as e:
            logger.error(f"[ERROR] 处理延迟字段点击失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return current_style, [], None

    def _handle_trigger_detection(self, ctx: CallbackContext, max_clicks_list, min_clicks_list) -> Dict[str, Any]:
        """处理触发源检测"""
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
            return {'is_close': True, 'modal_style': modal_style}

        # 对于最大/最小延迟字段的点击，需要确保是真正的用户点击
        has_real_click = self._check_real_clicks(max_clicks_list, min_clicks_list)

        if not has_real_click:
            logger.info(f"[WARNING] 没有检测到真正的用户点击（可能是布局更新），跳过处理: trigger_id={trigger_id}")
            return {'should_skip': True}

        return {'continue': True}

    def _check_real_clicks(self, max_clicks_list, min_clicks_list) -> bool:
        """检查是否有真正的用户点击"""
        # 检查max_clicks_list中是否有任何值>0（真正的点击）
        if max_clicks_list:
            for clicks in max_clicks_list:
                if clicks is not None and clicks > 0:
                    return True

        # 检查min_clicks_list中是否有任何值>0（真正的点击）
        if min_clicks_list:
            for clicks in min_clicks_list:
                if clicks is not None and clicks > 0:
                    return True

        return False

    def _parse_trigger_info(self, ctx, max_clicks_list, min_clicks_list, max_ids_list, min_ids_list) -> Dict[str, Any]:
        """解析触发信息，提取延迟类型和算法名称"""
        # 从triggered信息中提取被触发的组件ID
        triggered_prop = ctx.triggered[0]
        prop_id_str = triggered_prop['prop_id']

        delay_type = None
        algorithm_name = None

        try:
            # 主要解析方法：从prop_id中解析
            if 'max-delay-value' in prop_id_str:
                delay_type = 'max'
                algorithm_name = self._extract_algorithm_from_prop_id(prop_id_str)
                if algorithm_name:
                    logger.info(f"[OK] 从prop_id解析得到最大延迟点击: 算法={algorithm_name}")
            elif 'min-delay-value' in prop_id_str:
                delay_type = 'min'
                algorithm_name = self._extract_algorithm_from_prop_id(prop_id_str)
                if algorithm_name:
                    logger.info(f"[OK] 从prop_id解析得到最小延迟点击: 算法={algorithm_name}")

            # 如果上面的方法没有找到，使用备用方法
            if not delay_type or not algorithm_name:
                logger.warning(f"[WARNING] 主要解析方法失败，使用备用方法")
                result = self._parse_trigger_info_fallback(max_clicks_list, min_clicks_list, max_ids_list, min_ids_list)
                delay_type = result.get('delay_type')
                algorithm_name = result.get('algorithm_name')

        except Exception as e:
            logger.warning(f"[WARNING] 解析触发ID失败: {e}, trigger_id={prop_id_str}")

        if not delay_type or not algorithm_name:
            logger.warning(f"[WARNING] 无法解析延迟类型或算法名称: prop_id={prop_id_str}, delay_type={delay_type}, algorithm_name={algorithm_name}")
            return {'valid': False}

        logger.info(f"[STATS] 延迟类型: {delay_type}, 算法名称: {algorithm_name}")
        return {
            'valid': True,
            'delay_type': delay_type,
            'algorithm_name': algorithm_name
        }

    def _extract_algorithm_from_prop_id(self, prop_id_str) -> Optional[str]:
        """从prop_id中提取算法名称"""
        try:
            # prop_id格式: {"type": "max-delay-value", "algorithm": "xxx"}.n_clicks
            # 提取字典部分
            dict_str = prop_id_str.split('.')[0]  # 去掉.n_clicks部分
            id_dict = ast.literal_eval(dict_str)
            return id_dict.get('algorithm')
        except Exception as e:
            logger.warning(f"[WARNING] 解析prop_id失败: {prop_id_str}, 错误: {e}")
            return None

    def _parse_trigger_info_fallback(self, max_clicks_list, min_clicks_list, max_ids_list, min_ids_list) -> Dict[str, Any]:
        """备用方法：通过检查clicks列表来解析触发信息"""
        result = {}

        # 检查max_clicks_list中是否有点击
        if max_clicks_list:
            for i, clicks in enumerate(max_clicks_list):
                if clicks is not None and clicks > 0:
                    if max_ids_list and i < len(max_ids_list):
                        max_id = max_ids_list[i]
                        if max_id and isinstance(max_id, dict):
                            result['algorithm_name'] = max_id.get('algorithm')
                            result['delay_type'] = 'max'
                            logger.info(f"[OK] 备用方法：检测到最大延迟点击: 算法={result['algorithm_name']}, clicks={clicks}")
                            break

        # 如果还没找到，检查min_clicks_list
        if not result.get('delay_type') and min_clicks_list:
            for i, clicks in enumerate(min_clicks_list):
                if clicks is not None and clicks > 0:
                    if min_ids_list and i < len(min_ids_list):
                        min_id = min_ids_list[i]
                        if min_id and isinstance(min_id, dict):
                            result['algorithm_name'] = min_id.get('algorithm')
                            result['delay_type'] = 'min'
                            logger.info(f"[OK] 备用方法：检测到最小延迟点击: 算法={result['algorithm_name']}, clicks={clicks}")
                            break

        return result

    def _get_notes_data(self, backend, algorithm_name, delay_type) -> Dict[str, Any]:
        """获取对应延迟类型的音符数据"""
        try:
            logger.info(f"[DEBUG] 调用 backend.get_notes_by_delay_type({algorithm_name}, {delay_type})")
            # 获取对应延迟类型的音符
            notes = backend.get_notes_by_delay_type(algorithm_name, delay_type)
            if notes is None:
                logger.warning(f"[WARNING] 无法获取{delay_type}延迟对应的音符")
                return {'valid': False}

            logger.info(f"[DEBUG] 成功获取音符数据: {type(notes)}")
            if isinstance(notes, tuple) and len(notes) == 4:
                logger.info(f"[DEBUG] 音符数据包含: record_note={type(notes[0])}, replay_note={type(notes[1])}, record_index={notes[2]}, replay_index={notes[3]}")

            return {
                'valid': True,
                'notes': notes
            }

        except Exception as e:
            logger.error(f"[ERROR] 获取音符数据失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {'valid': False}

    def _find_other_algorithm_notes(self, backend, algorithm_name, record_note) -> Dict[str, Any]:
        """查找其他算法中匹配的音符"""
        other_algorithm_notes = []  # [(algorithm_name, play_note), ...]

        active_algorithms = backend.multi_algorithm_manager.get_active_algorithms() if backend.multi_algorithm_manager else []
        if len(active_algorithms) > 1:
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

        return {'other_algorithm_notes': other_algorithm_notes}

    def _calculate_mean_delays(self, backend, algorithm_name) -> Dict[str, Any]:
        """获取平均延时 - 直接从已计算的统计数据中获取"""
        mean_delays = {}

        # 在多算法模式下从算法对象的统计数据中获取
        active_algorithms = backend.multi_algorithm_manager.get_active_algorithms() if backend.multi_algorithm_manager else []
        if len(active_algorithms) > 1:
            active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()
            target_algorithm = None
            for alg in active_algorithms:
                if alg.metadata.algorithm_name == algorithm_name:
                    target_algorithm = alg
                    break

            if target_algorithm:
                # 直接从已计算的统计数据中获取平均延时
                statistics = target_algorithm.get_statistics()
                mean_error_0_1ms = statistics.get('mean_error', 0.0)
                mean_delays[algorithm_name] = mean_error_0_1ms / 10.0  # 转换为ms单位
                logger.info(f"[OK] 从统计数据获取平均延时: {mean_delays[algorithm_name]:.2f}ms")
            else:
                logger.warning(f"[WARNING] 未找到算法 {algorithm_name}，使用默认平均延时0")
                mean_delays[algorithm_name] = 0.0
        else:
            # 单算法模式直接从backend获取
            analyzer = backend._get_current_analyzer()
            if analyzer:
                mean_error_0_1ms = analyzer.get_mean_error()
                mean_delays[algorithm_name] = mean_error_0_1ms / 10.0
                logger.info(f"[OK] 从单算法分析器获取平均延时: {mean_delays[algorithm_name]:.2f}ms")
            else:
                logger.warning("[WARNING] 单算法模式无分析器，使用默认平均延时0")
                mean_delays[algorithm_name] = 0.0

        return {'mean_delays': mean_delays}

    def _generate_chart_and_return(self, record_note, replay_note, algorithm_name, delay_type,
                                  other_algorithm_notes, mean_delays, record_index, replay_index) -> Dict[str, Any]:
        """生成对比曲线图并准备返回数据"""
        try:
            

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
                logger.error("[ERROR] 曲线生成失败 - spmid.plot_note_comparison_plotly 返回 None")
                return {'modal_style': {'display': 'none'}, 'rendered_row': [], 'clicked_point_info': None}

            logger.info(f"[DEBUG] 图表生成成功: {type(detail_figure_combined)}")

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

            return {
                'modal_style': modal_style,
                'rendered_row': [rendered_row],
                'clicked_point_info': clicked_point_info
            }

        except Exception as e:
            logger.error(f"[ERROR] 生成图表失败: {e}")
            return {'modal_style': {'display': 'none'}, 'rendered_row': [], 'clicked_point_info': None}


# 创建全局处理器实例
delay_value_click_handler = DelayValueClickHandler(None)  # session_manager 会在注册时设置
