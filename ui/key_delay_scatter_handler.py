"""
按键延时散点图处理器 - 处理按键与相对延时散点图的交互
"""

from typing import Any, Tuple, Dict

from dash import no_update
from ui.scatter_handler_base import ScatterHandlerBase
from utils.logger import Logger


logger = Logger.get_logger()


class KeyDelayScatterHandler(ScatterHandlerBase):
    """
    按键延时散点图处理器
    
    负责处理按键与相对延时散点图的点击交互
    注意：图表生成逻辑在 scatter_callbacks.py 中直接通过 backend 调用
    """
    
    def handle_key_delay_scatter_click(self, scatter_clickData, session_id, current_style):
        """处理按键与相对延时散点图点击，显示曲线对比（悬浮窗）"""
        plot_id = self._get_triggered_plot_id()
        if not plot_id:
            return no_update, no_update, no_update
            
        if plot_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            return self._handle_modal_close()
        
        if plot_id == 'key-delay-scatter-plot':
            if not scatter_clickData:
                return current_style, [], no_update
            return self._handle_key_delay_plot_click(scatter_clickData, session_id, current_style)
            
        return no_update, no_update, no_update
    
    # ==================== 私有方法 ====================
    
    def _handle_key_delay_plot_click(self, scatter_clickData: Dict[str, Any], session_id: str, current_style: Dict[str, Any]) -> Tuple[Dict[str, Any], Any, Any]:
        """处理按键与相对延时散点图点击的主要逻辑"""
        backend = self.session_manager.get_backend(session_id)
        if not backend:
            return current_style, [], no_update
        
        # 解析数据
        parsed = self._parse_plot_click_data(scatter_clickData, "按键与相对延时散点图", 4)
        if not parsed:
            return current_style, [], no_update
            
        customdata = parsed['customdata']
        record_index = customdata[0]
        replay_index = customdata[1]
        key_id = customdata[2]
        algorithm_name = customdata[4] if len(customdata) > 4 else None
        
        # 计算中心时间
        center_time_ms = self._calculate_center_time_for_note_pair(backend, record_index, replay_index, algorithm_name)
        
        point_info = {
            'algorithm_name': algorithm_name,
            'record_idx': record_index,
            'replay_idx': replay_index,
            'key_id': key_id,
            'source_plot_id': 'key-delay-scatter-plot',
            'center_time_ms': center_time_ms
        }
        
        # 生成详细曲线图
        figures = self._generate_key_delay_detail_plots(backend, {
            'algorithm_name': algorithm_name,
            'record_index': record_index,
            'replay_index': replay_index
        })
        
        if figures[2]: # combined_figure
            return self._create_modal_response(figures[2], point_info)
            
        return current_style, [], no_update
