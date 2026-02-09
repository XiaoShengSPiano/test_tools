"""
Z-Score散点图处理器 - 处理Z-Score标准化散点图的生成和交互
"""

import traceback
from typing import Optional, Tuple, Any, Dict, Union

from dash import no_update
from dash._callback import NoUpdate
from dash._callback_context import callback_context

from backend.piano_analysis_backend import PianoAnalysisBackend
from ui.scatter_handler_base import ScatterHandlerBase
from utils.logger import Logger


logger = Logger.get_logger()


class ZScoreScatterHandler(ScatterHandlerBase):
    """
    Z-Score散点图处理器
    
    负责处理Z-Score标准化散点图的生成、点击交互和数据管理
    """
    def generate_zscore_scatter_plot(self, session_id: str) -> Any:
        """生成按键与延时Z-Score标准化散点图"""
        backend = self.session_manager.get_backend(session_id)
        if not backend:
            logger.warning(f"[WARNING] 无法获取backend (session_id={session_id})")
            return no_update
        
        # 检查是否有分析器或多算法模式
        if not self._check_analyzer_or_multi_mode(backend):
            logger.warning(f"[WARNING] 没有可用的分析器，无法生成Z-Score散点图")
            return no_update
        
        try:
            fig = backend.generate_key_delay_zscore_scatter_plot()
            
            # 验证图表
            if not self._validate_zscore_plot(fig):
                logger.warning("[WARNING] Z-Score图表验证失败")
                return no_update
            
            logger.debug("[DEBUG] Z-Score散点图生成成功")
            return fig
        except Exception as e:
            logger.error(f"[ERROR] 生成Z-Score散点图失败: {e}")
            logger.error(traceback.format_exc())
            return backend.plot_generator._create_empty_plot(f"生成Z-Score散点图失败: {str(e)}")
    
    def handle_zscore_scatter_click(self, zscore_scatter_clickData, session_id, current_style):
        """处理Z-Score标准化散点图点击，显示曲线对比（悬浮窗）"""
        plot_id = self._get_triggered_plot_id()
        if not plot_id:
            return no_update, no_update, no_update
        
        # 1. 如果点击了关闭按钮
        if plot_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            # 注意：scatter_callbacks 已经处理了全局隐藏，这里仅作为子类流程的兜底
            return self._handle_modal_close()
        
        # 2. 如果是Z-Score散点图点击
        if plot_id == 'key-delay-zscore-scatter-plot':
            if not zscore_scatter_clickData or 'points' not in zscore_scatter_clickData:
                logger.warning("[WARNING] Z-Score标准化散点图点击 - clickData无效")
                return current_style, [], no_update
            
            return self._handle_zscore_plot_click(zscore_scatter_clickData, session_id, current_style)
        
        return no_update, no_update, no_update
    
    # ==================== 私有方法 ====================
    
    def _handle_zscore_plot_click(self, zscore_scatter_clickData: Dict[str, Any], session_id: str, current_style: Dict[str, Any]) -> Tuple[Dict[str, Any], Any, Any]:
        """处理Z-Score散点图点击的主要逻辑"""
        backend = self.session_manager.get_backend(session_id)
        if not backend:
            return current_style, [], no_update
        
        # 解析数据 (Z-Score散点图格式: [record_index, replay_index, key_id, delay_ms, algorithm_name])
        parsed = self._parse_plot_click_data(zscore_scatter_clickData, "Z-Score标准化散点图", 4)
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
            'source_plot_id': 'key-delay-zscore-scatter-plot',
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
    
    def _validate_zscore_plot(self, fig):
        """验证Z-Score图表是否正确生成"""
        return fig and hasattr(fig, 'data') and len(fig.data) > 0
