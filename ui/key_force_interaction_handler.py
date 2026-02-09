"""
按键-力度交互效应图处理器 - 处理按键力度交互效应图的交互
"""

import traceback
from typing import Optional, Tuple, List, Any, Union, Dict

from dash import no_update

from backend.piano_analysis_backend import PianoAnalysisBackend
from ui.scatter_handler_base import ScatterHandlerBase
from utils.logger import Logger


logger = Logger.get_logger()


class KeyForceInteractionHandler(ScatterHandlerBase):
    """
    按键-力度交互效应图处理器
    
    负责处理按键-力度交互效应图的点击交互
    """
    
    def handle_key_force_interaction_plot_click(self, click_data, session_id, current_style):
        """处理按键-力度交互效应图点击，显示对应按键的曲线对比（悬浮窗）"""
        plot_id = self._get_triggered_plot_id()
        if not plot_id:
            return no_update, no_update, no_update
            
        if plot_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            return self._handle_modal_close()
        
        if plot_id == 'key-force-interaction-plot':
            if not click_data or 'points' not in click_data:
                return current_style, [], no_update
            return self._handle_interaction_click_logic(click_data, session_id, current_style)
        
        return no_update, no_update, no_update
    
    # ==================== 私有方法 ====================
    
    def _handle_interaction_click_logic(self, click_data, session_id, current_style):
        """处理按键-力度交互效应图点击的具体逻辑"""
        backend = self.session_manager.get_backend(session_id)
        if not backend:
            return current_style, [], no_update
        
        try:
            # 解析数据 (customdata格式: [record_index, replay_index, key_id, absolute_delay, algorithm_name, replay_velocity, relative_delay])
            parsed = self._parse_plot_click_data(click_data, "按键-力度交互效应图", 7)
            if not parsed:
                return current_style, [], no_update
            
            customdata = parsed['customdata']
            record_idx = customdata[0]
            replay_idx = customdata[1]
            key_id = customdata[2]
            algorithm_name = customdata[4]
            
            # 计算中心时间
            center_time_ms = self._calculate_center_time_for_note_pair(backend, record_idx, replay_idx, algorithm_name)
            
            point_info = {
                'algorithm_name': algorithm_name,
                'record_idx': record_idx,
                'replay_idx': replay_idx,
                'key_id': key_id,
                'source_plot_id': 'key-force-interaction-plot',
                'center_time_ms': center_time_ms
            }
            
            # 生成详细曲线图
            figures = self._generate_key_delay_detail_plots(backend, {
                'algorithm_name': algorithm_name,
                'record_index': record_idx,
                'replay_index': replay_idx
            })
            
            if figures[2]: # combined_figure
                return self._create_modal_response(figures[2], point_info, height='800px')
                
            return current_style, [], no_update
                
        except Exception as e:
            logger.error(f"[ERROR] 处理按键-力度交互效应图点击失败: {e}")
            logger.error(traceback.format_exc())
            return current_style, [], no_update
