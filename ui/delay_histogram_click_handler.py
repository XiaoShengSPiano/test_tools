"""
延时直方图点击处理器
重构自 ui/callbacks.py 中的 handle_delay_histogram_click 函数
"""

import logging
import math
from typing import Dict, List, Optional, Tuple, Any
from dash import no_update

logger = logging.getLogger(__name__)


class DelayHistogramClickHandler:
    """延时直方图点击处理器类"""

    def __init__(self, session_manager=None):
        self.session_manager = session_manager

    def set_session_manager(self, session_manager):
        """设置 session_manager（用于延迟初始化）"""
        self.session_manager = session_manager

    def handle_delay_histogram_click(self, click_data, session_id) -> Tuple[List[Dict], Dict, str]:
        """处理延时直方图点击事件，显示该延时范围内的数据点详情"""
        try:
            logger.info(f"🔍 延时直方图点击回调被触发，click_data: {click_data}")

            # 验证输入并初始化
            validation_result = self._validate_inputs_and_init(click_data, session_id)
            if not validation_result['valid']:
                return validation_result['result']

            backend = validation_result['backend']

            # 解析点击数据
            click_result = self._parse_click_data(click_data, backend)
            if not click_result['valid']:
                return click_result['result']

            delay_min = click_result['delay_min']
            delay_max = click_result['delay_max']

            # 获取该延时范围内的数据点
            data_result = self._get_data_points_in_range(backend, delay_min, delay_max)
            if not data_result['valid']:
                return data_result['result']

            data_points = data_result['data_points']

            # 准备表格数据
            table_result = self._prepare_table_data(data_points, delay_min, delay_max)

            return table_result['table_data'], table_result['table_style'], table_result['info_text']

        except Exception as e:
            logger.error(f"[ERROR] 处理延时直方图点击事件失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return [], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px', 'display': 'none'}, f"处理失败: {str(e)}"

    def _validate_inputs_and_init(self, click_data, session_id) -> Dict[str, Any]:
        """验证输入并初始化"""
        backend = self.session_manager.get_backend(session_id)
        if not backend:
            logger.warning("[WARNING] backend 为空")
            return {
                'valid': False,
                'result': ([], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px', 'display': 'none'}, "")
            }

        # 如果没有点击数据，隐藏表格
        if not click_data:
            logger.info("[WARNING] click_data 为空")
            return {
                'valid': False,
                'result': ([], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px', 'display': 'none'}, "")
            }

        if 'points' not in click_data or not click_data['points']:
            logger.info(f"[WARNING] click_data 中没有 points 或 points 为空，click_data keys: {click_data.keys() if isinstance(click_data, dict) else 'not dict'}")
            return {
                'valid': False,
                'result': ([], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px', 'display': 'none'}, "")
            }

        return {
            'valid': True,
            'backend': backend
        }

    def _parse_click_data(self, click_data, backend) -> Dict[str, Any]:
        """解析点击数据，获取延时范围"""
        try:
            # 获取点击的柱状图信息
            point = click_data['points'][0]
            logger.info(f"[STATS] 点击的 point 数据: {point}")

            # 对于 Histogram，点击的 point 可能包含 'x'（中心值）或 'bin' 信息
            if 'x' not in point:
                logger.warning("[WARNING] point 中没有 x 值，无法确定范围")
                return {
                    'valid': False,
                    'result': ([], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px', 'display': 'none'}, "")
                }

            x_value = point['x']

            # 获取所有延时数据来估算 bin 宽度
            delays_ms = self._get_all_delay_data(backend)
            if not delays_ms:
                logger.warning("[WARNING] 没有延时数据")
                return {
                    'valid': False,
                    'result': ([], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px', 'display': 'none'}, "")
                }

            # 计算 bin 范围
            delay_min, delay_max = self._calculate_bin_range(x_value, delays_ms, point)

            return {
                'valid': True,
                'delay_min': delay_min,
                'delay_max': delay_max
            }

        except Exception as e:
            logger.error(f"[ERROR] 解析点击数据失败: {e}")
            return {
                'valid': False,
                'result': ([], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px', 'display': 'none'}, "")
            }

    def _get_all_delay_data(self, backend) -> List[float]:
        """获取所有延时数据"""
        delays_ms = []

        if backend.multi_algorithm_mode and backend.multi_algorithm_manager:
            # 多算法模式：从所有激活算法收集数据
            active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()
            for algorithm in active_algorithms:
                if algorithm.analyzer and algorithm.analyzer.note_matcher:
                    offset_data = algorithm.analyzer.get_offset_alignment_data()
                    if offset_data:
                        delays_ms.extend([item.get('keyon_offset', 0.0) / 10.0 for item in offset_data])
        else:
            # 单算法模式
            offset_data = backend.analyzer.get_offset_alignment_data() if backend.analyzer else []
            if offset_data:
                delays_ms = [item.get('keyon_offset', 0.0) / 10.0 for item in offset_data]

        return delays_ms

    def _calculate_bin_range(self, x_value: float, delays_ms: List[float], point: Dict) -> Tuple[float, float]:
        """计算 bin 范围"""
        # 方法1：尝试从 point 中获取 bin 边界信息（如果 Plotly 提供了）
        if 'x0' in point and 'x1' in point:
            # 如果 Plotly 直接提供了 bin 边界，使用它（最准确）
            delay_min = point['x0']
            delay_max = point['x1']
        else:
            # 方法2：估算 bin 宽度
            delay_min, delay_max = self._estimate_bin_range(x_value, delays_ms)

        return delay_min, delay_max

    def _estimate_bin_range(self, x_value: float, delays_ms: List[float]) -> Tuple[float, float]:
        """估算 bin 宽度和范围"""
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

        return delay_min, delay_max

    def _get_data_points_in_range(self, backend, delay_min: float, delay_max: float) -> Dict[str, Any]:
        """获取该延时范围内的数据点"""
        try:
            # 获取该延时范围内的数据点
            data_points = backend.get_delay_range_data_points(delay_min, delay_max)

            if not data_points:
                info_text = f"延时范围 [{delay_min:.2f}ms, {delay_max:.2f}ms] 内没有数据点"
                return {
                    'valid': False,
                    'result': ([], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px', 'display': 'none'}, info_text)
                }

            return {
                'valid': True,
                'data_points': data_points
            }

        except Exception as e:
            logger.error(f"[ERROR] 获取数据点失败: {e}")
            return {
                'valid': False,
                'result': ([], {'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '600px', 'display': 'none'}, f"获取数据点失败: {str(e)}")
            }

    def _prepare_table_data(self, data_points, delay_min: float, delay_max: float) -> Dict[str, Any]:
        """准备表格数据"""
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

        return {
            'table_data': table_data,
            'table_style': table_style,
            'info_text': info_text
        }


# 创建全局处理器实例
delay_histogram_click_handler = DelayHistogramClickHandler(None)  # session_manager 会在注册时设置
