"""
相对延时分布图点击处理器
重构自 ui/callbacks.py 中的 handle_relative_delay_distribution_click 函数
"""

import logging
import numpy as np
from typing import Dict, List, Any, Tuple, Optional

logger = logging.getLogger(__name__)


class RelativeDelayDistributionHandler:
    """相对延时分布图点击处理器类"""

    def __init__(self, session_manager):
        self.session_manager = session_manager

    def handle_click(self, click_data, session_id, plot_id) -> Tuple[List[Dict], Dict, str, Dict, str]:
        """处理相对延时分布图点击事件"""
        try:
            # 验证输入并初始化
            validation_result = self._validate_inputs_and_init(click_data, session_id, plot_id)
            if not validation_result['valid']:
                return validation_result['result']

            backend = validation_result['backend']
            click_data = validation_result['click_data']
            plot_id = validation_result['plot_id']

            # 解析子图信息
            subplot_result = self._parse_subplot_info(plot_id)
            if not subplot_result['valid']:
                return subplot_result['result']

            subplot_idx = subplot_result['subplot_idx']

            # 处理点击数据
            click_result = self._process_click_data(click_data, backend, subplot_idx)
            if not click_result['valid']:
                return click_result['result']

            x_value = click_result['x_value']
            target_info = click_result['target_info']
            all_songs = click_result['all_songs']

            # 获取数据点
            data_result = self._get_data_points_in_range(backend, target_info, x_value)
            if not data_result['valid']:
                return data_result['result']

            data_points = data_result['data_points']
            bin_left = data_result['bin_left']
            bin_right = data_result['bin_right']
            subplot_index = data_result['subplot_index']
            subplot_title = data_result['subplot_title']

            # 准备表格数据
            table_result = self._prepare_table_data(data_points, bin_left, bin_right)

            return table_result['table_data'], table_result['table_style'], \
                   table_result['info_text'], table_result['modal_style'], \
                   table_result['subplot_title']

        except Exception as e:
            logger.error(f"[ERROR] 处理相对延时分布图点击事件失败: {e}")
            return [], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px'}, \
                   f"处理失败: {str(e)}", {'display': 'none'}, ""

    def _validate_inputs_and_init(self, click_data, session_id, plot_id) -> Dict[str, Any]:
        """验证输入并初始化"""
        logger.info(f"🔍 相对延时分布图点击回调被触发，click_data: {click_data}")

        backend = self.session_manager.get_backend(session_id)
        if not backend:
            logger.warning("[WARNING] backend 为空")
            return {
                'valid': False,
                'result': ([], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px'},
                          "", {'display': 'none'}, "")
            }

        # 如果没有点击数据，隐藏表格
        if not click_data:
            logger.info("[WARNING] click_data 为空")
            return {
                'valid': False,
                'result': ([], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px'},
                          "", {'display': 'none'}, "")
            }

        if 'points' not in click_data or not click_data['points']:
            logger.info("[WARNING] click_data 中没有 points 或 points 为空")
            return {
                'valid': False,
                'result': ([], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px'},
                          "", {'display': 'none'}, "")
            }

        return {
            'valid': True,
            'backend': backend,
            'click_data': click_data,
            'plot_id': plot_id
        }

    def _parse_subplot_info(self, plot_id) -> Dict[str, Any]:
        """解析子图信息"""
        # 从plot_id获取子图索引（Pattern Matching Callbacks）
        subplot_idx = plot_id.get('index') if isinstance(plot_id, dict) else None
        if subplot_idx is None:
            logger.warning("[WARNING] 无法从plot_id获取子图索引")
            return {
                'valid': False,
                'result': ([], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px'},
                          "", {'display': 'none'}, "")
            }

        logger.info(f"[STATS] 点击的子图索引: {subplot_idx}")
        return {
            'valid': True,
            'subplot_idx': subplot_idx
        }

    def _process_click_data(self, click_data, backend, subplot_idx) -> Dict[str, Any]:
        """处理点击数据"""
        # 获取点击的柱状图信息
        point = click_data['points'][0]
        logger.info(f"[STATS] 点击的 point 数据: {point}")

        # 获取点击的x值（相对延时值）
        x_value = point.get('x')
        if x_value is None:
            logger.warning("[WARNING] point 中没有 x 值")
            return {
                'valid': False,
                'result': ([], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px'},
                          "", {'display': 'none'}, "")
            }

        # 获取分析结果以确定子图信息
        analysis_result = backend.get_same_algorithm_relative_delay_analysis()
        if analysis_result.get('status') != 'success':
            logger.warning("[WARNING] 无法获取分析结果")
            return {
                'valid': False,
                'result': ([], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px'},
                          "", {'display': 'none'}, "")
            }

        algorithm_groups = analysis_result.get('algorithm_groups', {})
        if not algorithm_groups:
            logger.warning("[WARNING] 没有算法组数据")
            return {
                'valid': False,
                'result': ([], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px'},
                          "", {'display': 'none'}, "")
            }

        # 构建子图列表
        all_songs = self._build_subplot_list(algorithm_groups)

        # 根据subplot_idx直接确定目标子图（索引从1开始）
        if subplot_idx < 1 or subplot_idx > len(all_songs):
            logger.warning(f"[WARNING] 子图索引超出范围: subplot_idx={subplot_idx}, 总子图数={len(all_songs)}")
            return {
                'valid': False,
                'result': ([], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px'},
                          "", {'display': 'none'}, "")
            }

        target_info = all_songs[subplot_idx - 1]
        logger.info(f"[OK] 确定的子图: subplot_idx={subplot_idx}, display_name={target_info[0]}, filename_display={target_info[1]}")

        return {
            'valid': True,
            'x_value': x_value,
            'target_info': target_info,
            'all_songs': all_songs
        }

    def _build_subplot_list(self, algorithm_groups) -> List[Tuple]:
        """构建子图列表"""
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
                    all_songs.append((display_name, filename_display, song_relative_delays, None))

            # 添加汇总
            all_songs.append((display_name, '汇总', None, group_relative_delays))

        return all_songs

    def _get_data_points_in_range(self, backend, target_info, x_value) -> Dict[str, Any]:
        """获取指定范围内的数据点"""
        target_display_name, target_filename_display, song_relative_delays, group_relative_delays = target_info

        # 确定使用的数据
        if target_filename_display == '汇总':
            target_delays = np.array(group_relative_delays)
        else:
            target_delays = np.array(song_relative_delays)

        if len(target_delays) == 0:
            logger.warning(f"[WARNING] 目标子图没有数据")
            return {
                'valid': False,
                'result': ([], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px'},
                          "", {'display': 'none'}, "")
            }

        # 计算bin范围
        hist, bin_edges = np.histogram(target_delays, bins=50, density=False)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

        # 找到包含x_value的bin
        bin_idx = np.argmin(np.abs(bin_centers - x_value))
        if bin_idx >= len(bin_edges) - 1:
            bin_idx = len(bin_edges) - 2

        bin_left = float(bin_edges[bin_idx])
        bin_right = float(bin_edges[bin_idx + 1])

        logger.info(f"[STATS] 确定的bin范围: [{bin_left:.2f}, {bin_right:.2f}]")

        # 获取该相对延时范围内的数据点
        data_points = backend.get_relative_delay_range_data_points_by_subplot(
            target_display_name, target_filename_display, bin_left, bin_right
        )

        # 注意：subplot_index 在这里暂时设为 None，因为需要从 all_songs 中计算
        # 但这个逻辑在原来的代码中是冗余的，因为我们已经在 _process_click_data 中确定了目标子图
        subplot_index = None

        # 生成子图标题
        if target_filename_display == '汇总':
            subplot_title = f"[STATS] {target_display_name} (汇总) - 数据详情"
        else:
            subplot_title = f"[STATS] {target_display_name} - {target_filename_display} - 数据详情"

        return {
            'valid': True,
            'data_points': data_points,
            'bin_left': bin_left,
            'bin_right': bin_right,
            'subplot_index': subplot_index,
            'subplot_title': subplot_title
        }

    def _prepare_table_data(self, data_points, bin_left, bin_right) -> Dict[str, Any]:
        """准备表格数据"""
        if not data_points:
            info_text = f"相对延时范围 [{bin_left:.2f}ms, {bin_right:.2f}ms] 内没有数据点"
            return {
                'table_data': [],
                'table_style': {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px'},
                'info_text': info_text,
                'modal_style': {'display': 'block'},
                'subplot_title': ""
            }

        # 准备表格数据
        table_data = []
        for item in data_points:
            table_data.append({
                'algorithm_name': item.get('algorithm_name', 'N/A'),
                'key_id': item.get('key_id', 'N/A'),
                'relative_delay_ms': item.get('relative_delay_ms', 0.0),
                'absolute_delay_ms': item.get('absolute_delay_ms', 0.0),
                'record_index': item.get('record_index', 'N/A'),
                'replay_index': item.get('replay_index', 'N/A'),
                'record_keyon': item.get('record_keyon', 'N/A'),
                'replay_keyon': item.get('replay_keyon', 'N/A'),
                'duration_offset': item.get('duration_offset', 'N/A'),
            })

        # 显示信息
        info_text = f"相对延时范围 [{bin_left:.2f}ms, {bin_right:.2f}ms] 内共有 {len(data_points)} 个数据点"

        # 显示表格，添加垂直滚动条，限制最大高度为600px
        table_style = {
            'overflowX': 'auto',
            'overflowY': 'auto',
            'maxHeight': '600px',
        }

        return {
            'table_data': table_data,
            'table_style': table_style,
            'info_text': info_text,
            'modal_style': {'display': 'block'},
            'subplot_title': ""
        }
    
    def handle_table_click(self, active_cells, close_modal_clicks, close_btn_clicks, 
                          table_data_list, session_id, current_style):
        """
        处理相对延时分布图详情表格点击，显示录制与播放对比曲线
        
        Args:
            active_cells: 活动单元格列表
            close_modal_clicks: 关闭按钮点击次数
            close_btn_clicks: 关闭按钮2点击次数
            table_data_list: 表格数据列表
            session_id: 会话ID
            current_style: 当前模态框样式
            
        Returns:
            Tuple[modal_style, comparison_container_children, clicked_point_info]
        """
        from dash import no_update, dcc
        from dash._callback_context import callback_context
        
        try:
            # 检测触发源
            trigger_result = self._handle_table_trigger_detection(close_modal_clicks, close_btn_clicks)
            if trigger_result.get('is_close'):
                return trigger_result['modal_style'], [], no_update
            if trigger_result.get('should_skip'):
                return current_style, [], no_update
            
            # 获取后端
            backend = self.session_manager.get_backend(session_id)
            if not backend:
                logger.warning("[WARNING] backend为空")
                return current_style, [], no_update
            
            # 解析表格点击数据
            table_result = self._parse_table_click_data(active_cells, table_data_list)
            if not table_result['valid']:
                return current_style, [], no_update
            
            # 查找目标算法和音符
            match_result = self._find_algorithm_and_notes(
                backend, 
                table_result['algorithm_name'],
                table_result['record_index'],
                table_result['replay_index'],
                table_result['key_id']
            )
            if not match_result['valid']:
                return current_style, [], no_update
            
            # 生成对比图表
            chart_result = self._generate_table_comparison_chart(
                backend,
                match_result['record_note'],
                match_result['replay_note'],
                match_result['algorithm_name'],
                match_result['target_algorithm']
            )
            
            # 准备返回数据
            return self._prepare_table_click_return_data(
                chart_result['figure'],
                match_result,
                table_result,
                table_result.get('triggered_table_idx', 0)
            )
            
        except Exception as e:
            logger.error(f"[ERROR] 处理表格点击失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return current_style, [], no_update
    
    def _handle_table_trigger_detection(self, close_modal_clicks, close_btn_clicks) -> Dict[str, Any]:
        """检测表格点击的触发源"""
        from dash._callback_context import callback_context
        
        ctx = callback_context
        if not ctx.triggered:
            return {'should_skip': True}
        
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        if trigger_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            return {
                'is_close': True,
                'modal_style': {'display': 'none'}
            }
        
        return {'is_close': False, 'should_skip': False}
    
    def _parse_table_click_data(self, active_cells, table_data_list) -> Dict[str, Any]:
        """解析表格点击数据"""
        try:
            # 获取触发的表格索引
            triggered_table_idx = next((i for i, cell in enumerate(active_cells) if cell), None)
            if triggered_table_idx is None or triggered_table_idx >= len(table_data_list):
                logger.warning("[WARNING] 未找到触发的表格")
                return {'valid': False}
            
            table_data = table_data_list[triggered_table_idx]
            active_cell = active_cells[triggered_table_idx]
            
            if not active_cell or not table_data:
                logger.warning("[WARNING] active_cell或table_data为空")
                return {'valid': False}
            
            # 获取行数据
            row_data = table_data[active_cell.get('row')]
            record_index = int(row_data.get('record_index'))
            replay_index = int(row_data.get('replay_index'))
            key_id = int(row_data.get('key_id')) if row_data.get('key_id') != 'N/A' else None
            algorithm_name = row_data.get('algorithm_name')
            
            logger.info(f"[STATS] 点击行: rec={record_index}, rep={replay_index}, key={key_id}, alg={algorithm_name}")
            
            return {
                'valid': True,
                'triggered_table_idx': triggered_table_idx,
                'record_index': record_index,
                'replay_index': replay_index,
                'key_id': key_id,
                'algorithm_name': algorithm_name
            }
        except Exception as e:
            logger.error(f"[ERROR] 解析表格数据失败: {e}")
            return {'valid': False}
    
    def _find_algorithm_and_notes(self, backend, algorithm_name, record_index, 
                                  replay_index, key_id) -> Dict[str, Any]:
        """查找目标算法实例和音符数据"""
        # 检查是否在多算法模式
        active_algorithms = backend.multi_algorithm_manager.get_active_algorithms() if backend.multi_algorithm_manager else []
        if len(active_algorithms) <= 1:
            logger.warning("[WARNING] 非多算法模式或无效调用")
            return {'valid': False}
        
        # 查找目标算法实例
        target_algorithm = None
        for algorithm in active_algorithms:
            if algorithm.metadata.algorithm_name == algorithm_name:
                # 验证matched_pairs中是否有此匹配对
                if algorithm.analyzer and hasattr(algorithm.analyzer, 'matched_pairs'):
                    for r_idx, p_idx, r_note, p_note in algorithm.analyzer.matched_pairs:
                        if r_idx == record_index and p_idx == replay_index:
                            target_algorithm = algorithm
                            break
                if target_algorithm:
                    break
        
        if not target_algorithm:
            logger.warning(f"[WARNING] 未找到匹配算法: {algorithm_name}")
            return {'valid': False}
        
        # 获取音符数据
        record_note = None
        replay_note = None
        center_time_ms = None
        
        for r_idx, p_idx, r_note, p_note in target_algorithm.analyzer.matched_pairs:
            if r_idx == record_index and p_idx == replay_index:
                record_note = r_note
                replay_note = p_note
                
                # 计算中心时间
                try:
                    record_keyon = r_note.after_touch.index[0] + r_note.offset if hasattr(r_note, 'after_touch') and not r_note.after_touch.empty else r_note.offset
                    replay_keyon = p_note.after_touch.index[0] + p_note.offset if hasattr(p_note, 'after_touch') and not p_note.after_touch.empty else p_note.offset
                    center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0
                except Exception as e:
                    logger.warning(f"[WARNING] 计算时间信息失败: {e}")
                    center_time_ms = None
                
                break
        
        if not record_note or not replay_note:
            logger.error("[ERROR] 无法获取音符对象")
            return {'valid': False}
        
        return {
            'valid': True,
            'target_algorithm': target_algorithm,
            'algorithm_name': target_algorithm.metadata.algorithm_name,
            'record_note': record_note,
            'replay_note': replay_note,
            'center_time_ms': center_time_ms
        }
    
    def _generate_table_comparison_chart(self, backend, record_note, replay_note, 
                                         algorithm_name, target_algorithm) -> Dict[str, Any]:
        """生成对比曲线图"""
        # 计算平均延时
        mean_delay = 0.0
        if target_algorithm.analyzer:
            mean_delay = target_algorithm.analyzer.get_mean_error() / 10.0
        
        # 生成图表
        detail_figure = backend.plot_generator.generate_note_comparison_plot(
            record_note,
            replay_note,
            algorithm_name=algorithm_name,
            other_algorithm_notes=[],
            mean_delays={algorithm_name: mean_delay}
        )
        
        if not detail_figure:
            logger.error("[ERROR] 图表生成失败")
            return {'valid': False}
        
        return {
            'valid': True,
            'figure': detail_figure
        }
    
    def _prepare_table_click_return_data(self, figure, match_result, table_result, 
                                         triggered_table_idx):
        """准备表格点击的返回数据"""
        from dash import dcc
        
        # 构建点击信息
        point_info = {
            'algorithm_name': match_result['algorithm_name'],
            'record_idx': table_result['record_index'],
            'replay_idx': table_result['replay_index'],
            'key_id': table_result['key_id'],
            'source_plot_id': 'relative-delay-distribution-plot',
            'source_subplot_idx': triggered_table_idx + 1,
            'center_time_ms': match_result['center_time_ms']
        }
        
        # 模态框样式
        modal_style = {
            'display': 'block',
            'position': 'fixed',
            'zIndex': '9999',
            'left': '0', 'top': '0',
            'width': '100%', 'height': '100%',
            'backgroundColor': 'rgba(0,0,0,0.6)',
            'backdropFilter': 'blur(5px)'
        }
        
        return modal_style, [dcc.Graph(figure=figure, style={'height': '600px'})], point_info


# 创建全局处理器实例
relative_delay_distribution_handler = RelativeDelayDistributionHandler(None)  # session_manager 会在注册时设置
