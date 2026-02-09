"""
延时时间序列图点击处理器
重构自 ui/callbacks.py 中的 handle_delay_time_series_click_multi 函数
"""

import logging
import traceback
from typing import Dict, Any, Tuple

from dash import no_update
from ui.scatter_handler_base import ScatterHandlerBase


logger = logging.getLogger(__name__)


class DelayTimeSeriesHandler(ScatterHandlerBase):
    """
    延时时间序列图点击处理器类
    
    继承自 ScatterHandlerBase，提供标准化的点击处理逻辑
    """

    def handle_delay_time_series_click_multi(self, raw_click_data, relative_click_data, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理延时时间序列图点击（多算法模式），显示音符分析曲线（悬浮窗）"""
        
        plot_id = self._get_triggered_plot_id()
        if not plot_id:
            return no_update, no_update, no_update
            
        # 1. 弹窗关闭逻辑
        if plot_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            return self._handle_modal_close()
            
        # 2. 检查触发源
        if plot_id == 'raw-delay-time-series-plot':
            click_data = raw_click_data
        elif plot_id == 'relative-delay-time-series-plot':
            click_data = relative_click_data
        else:
            return no_update, no_update, no_update

        if not click_data:
            return current_style, [], no_update

        backend = self.session_manager.get_backend(session_id)
        if not backend:
            return current_style, [], no_update

        try:
            # 3. 解析数据 (TimeSeries图的customdata长度至少包含前4位关键信息)
            parsed = self._parse_plot_click_data(click_data, "延时时间序列图", 4)
            if not parsed:
                return current_style, [], no_update
                
            customdata = parsed['customdata']
            key_id = customdata[0]
            record_index = customdata[1]  # UUID 或 Index
            replay_index = customdata[2]  # UUID 或 Index
            algorithm_name = customdata[3] if len(customdata) > 3 else None
            
            # 4. 计算中心时间 (基础类提供的高级查找，支持 UUID 匹配)
            center_time_ms = self._calculate_center_time_for_note_pair(backend, record_index, replay_index, algorithm_name)
            
            point_info = {
                'key_id': key_id,
                'record_idx': record_index,
                'replay_idx': replay_index,
                'algorithm_name': algorithm_name,
                'source_plot_id': plot_id,
                'center_time_ms': center_time_ms
            }
            
            # 5. 生成详细曲线图 (利用统一的 backend 映射)
            figures = self._generate_key_delay_detail_plots(backend, {
                'algorithm_name': algorithm_name,
                'record_index': record_index,
                'replay_index': replay_index
            })
            
            # Combined figure is the 3rd element
            if figures[2]:
                logger.info(f"[OK] 延时时间序列图详情生成成功: (算法={algorithm_name}, record={record_index})")
                return self._create_modal_response(figures[2], point_info, height='800px')
                
            return current_style, [], no_update

        except Exception as e:
            logger.error(f"[ERROR] 处理延时时间序列图点击失败: {e}")
            logger.error(traceback.format_exc())
            return current_style, [], no_update


# 创建全局处理器实例
delay_time_series_handler = DelayTimeSeriesHandler(None)  # session_manager 会在注册时设置
