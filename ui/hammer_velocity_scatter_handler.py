"""
锤速散点图处理器 - 处理锤速相关散点图的生成和交互
包括：锤速与延时Z-Score散点图、锤速与相对延时散点图
"""

import traceback
from typing import Optional, Tuple, Union, Any, Dict

from dash import no_update
from dash._callback import NoUpdate

from backend.piano_analysis_backend import PianoAnalysisBackend
from ui.scatter_handler_base import ScatterHandlerBase
from utils.logger import Logger


logger = Logger.get_logger()


class HammerVelocityScatterHandler(ScatterHandlerBase):
    """
    锤速散点图处理器
    
    负责处理两种锤速相关的散点图：
    1. 锤速与延时Z-Score散点图
    2. 锤速与相对延时散点图
    """
    
    def generate_hammer_velocity_scatter_plot(self, session_id: str) -> Union[Any, NoUpdate]:
        """生成锤速与延时Z-Score标准化散点图（需要至少2个算法）"""
        backend = self.session_manager.get_backend(session_id)
        if not backend:
            logger.warning(f"[WARNING] 无法获取backend (session_id={session_id})")
            return no_update
        
        # 检查是否有至少2个算法
        if not self._check_at_least_two_algorithms(backend, "锤速与延时Z-Score标准化散点图需要至少2个算法进行对比"):
            return no_update
        
        try:
            fig = backend.generate_hammer_velocity_delay_scatter_plot()
            logger.info("[OK] 锤速与延时Z-Score散点图生成成功")
            return fig
        except Exception as e:
            logger.error(f"[ERROR] 生成锤速与延时Z-Score散点图失败: {e}")
            logger.error(traceback.format_exc())
            return backend.plot_generator._create_empty_plot(f"生成锤速与延时Z-Score散点图失败: {str(e)}")
    
    def generate_hammer_velocity_relative_delay_scatter_plot(self, session_id: str) -> Union[Any, NoUpdate]:
        """生成锤速与相对延时散点图"""
        backend = self.session_manager.get_backend(session_id)
        if not backend:
            logger.warning(f"[WARNING] 无法获取backend (session_id={session_id})")
            return no_update
        
        # 检查是否有活跃的算法
        if not self._check_active_algorithms(backend):
            logger.warning("[WARNING] 没有活跃的算法，无法生成锤速与相对延时散点图")
            return no_update
        
        try:
            fig = backend.generate_hammer_velocity_relative_delay_scatter_plot()
            logger.info("[OK] 锤速与相对延时散点图生成成功")
            return fig
        except Exception as e:
            logger.error(f"[ERROR] 生成锤速与相对延时散点图失败: {e}")
            logger.error(traceback.format_exc())
            return backend.plot_generator._create_empty_plot(f"生成锤速与相对延时散点图失败: {str(e)}")
    
    def handle_hammer_velocity_scatter_click(self, scatter_clickData, session_id, current_style):
        """处理各类型锤速散点图点击"""
        plot_id = self._get_triggered_plot_id()
        if not plot_id:
            return no_update, no_update, no_update
            
        if plot_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            return self._handle_modal_close()
        
        # 处理不同类型的锤速散点图点击
        if plot_id == 'hammer-velocity-delay-scatter-plot' and scatter_clickData:
             return self._handle_hammer_plot_click(scatter_clickData, session_id, current_style, plot_id)
        
        if plot_id in ['hammer-velocity-relative-delay-scatter-plot', 'relative-delay-distribution-plot'] and scatter_clickData:
             return self._handle_hammer_plot_click(scatter_clickData, session_id, current_style, plot_id)
             
        return no_update, no_update, no_update
    
    # ==================== 私有方法 ====================
    
    def _handle_hammer_plot_click(self, scatter_clickData: Dict[str, Any], session_id: str, current_style: Dict[str, Any], plot_id: str) -> Tuple[Dict[str, Any], Any, Any]:
        """统一处理各种锤速散点图点击"""
        backend = self.session_manager.get_backend(session_id)
        if not backend:
            return current_style, [], no_update

        # 解析点击数据
        # 锤速系列图表的 customdata 格式通常为: [delay_ms, original_velocity, record_idx, replay_idx, algorithm_name, key_id]
        parsed = self._parse_plot_click_data(scatter_clickData, "锤速散点图", 6)
        if not parsed:
            # 兼容模式：部分旧图表可能使用不同的格式
            return self._handle_legacy_hammer_click(scatter_clickData, session_id, current_style, plot_id)
            
        customdata = parsed['customdata']
        delay_ms = customdata[0]
        original_velocity = customdata[1]
        record_index = customdata[2]
        replay_index = customdata[3]
        algorithm_name = customdata[4]
        key_id = customdata[5]
        
        # 计算中心时间
        center_time_ms = self._calculate_center_time_for_note_pair(backend, record_index, replay_index, algorithm_name)
        
        point_info = {
            'algorithm_name': algorithm_name,
            'record_idx': record_index,
            'replay_idx': replay_index,
            'key_id': key_id,
            'source_plot_id': plot_id,
            'center_time_ms': center_time_ms,
            '锤速': f"{original_velocity:.0f}",
            '延时': f"{delay_ms:.2f}ms"
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

    def _handle_legacy_hammer_click(self, scatter_clickData, session_id, current_style, plot_id):
        # 兜底逻辑：如果格式不匹配，尝试按 KeyDelay 的 4 位格式解析
        parsed = self._parse_plot_click_data(scatter_clickData, "锤速散点图(旧)", 4)
        if not parsed:
             return current_style, [], no_update
        
        # ... 这里的逻辑与 ZScore 类似 ...
        # 为了保持严谨，暂不深入实现，当前版本已统一 customdata 格式
        return current_style, [], no_update
