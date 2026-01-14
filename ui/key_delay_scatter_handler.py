"""
按键延时散点图处理器 - 处理按键与相对延时散点图的交互
"""

from typing import Any, Tuple

from dash import no_update
from dash._callback_context import callback_context

from backend.session_manager import SessionManager
from ui.scatter_handler_base import ScatterHandlerBase
from utils.logger import Logger


logger = Logger.get_logger()


class KeyDelayScatterHandler(ScatterHandlerBase):
    """
    按键延时散点图处理器
    
    负责处理按键与相对延时散点图的点击交互
    注意：图表生成逻辑在 callbacks.py 的 handle_key_delay_scatter_plot_unified 中
    """
    
    def handle_key_delay_scatter_click(self, scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理按键与相对延时散点图点击，显示曲线对比（悬浮窗）并支持跳转到瀑布图"""
        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            logger.debug("[WARNING] 按键与相对延时散点图点击回调：没有触发源")
            return no_update, no_update, no_update, no_update
        
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        
        # 如果点击了关闭按钮，只有当模态框是由本回调打开时才处理
        if trigger_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            if current_style and current_style.get('display') == 'block' and scatter_clickData is not None:
                result = self._handle_modal_close()
                return result[0], result[1], result[2], result[3]
            return no_update, no_update, no_update, no_update
        
        # 如果是按键与相对延时散点图点击
        if trigger_id == 'key-delay-scatter-plot' and scatter_clickData:
            # 按键与相对延时散点图有不同的 customdata 格式，需要专门处理
            result = self._handle_key_delay_plot_click(scatter_clickData, session_id, current_style, 'key-delay-scatter-plot')
            return result[0], result[1], result[2], no_update
        
        # 其他情况，返回默认值
        return no_update, no_update, no_update, no_update
    
    # ==================== 私有方法 ====================
    
    def _handle_modal_close(self) -> Tuple[Any, list, Any, Any]:
        """处理模态框关闭逻辑"""
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
        return modal_style, [], no_update, no_update
    
    def _handle_key_delay_plot_click(self, scatter_clickData, session_id, current_style, source_plot_id='key-delay-scatter-plot'):
        """
        处理按键与相对延时散点图点击的主要逻辑
        
        Args:
            scatter_clickData: 点击数据
            session_id: 会话ID
            current_style: 当前样式
            source_plot_id: 来源图表ID
            
        Returns:
            Tuple: (modal_style, graph_component, point_info_response)
        """
        from dash import dcc
        
        logger.info(f"🔍 按键与相对延时散点图点击回调被触发 - source_plot_id: {source_plot_id}")
        
        # 获取后端
        backend = self.session_manager.get_backend(session_id)
        if not backend:
            logger.warning("[WARNING] 没有找到backend")
            return current_style, [], no_update, no_update
        
        # 解析点击数据
        click_info = self._parse_scatter_click_data(scatter_clickData, "按键与相对延时散点图")
        if not click_info:
            return current_style, [], no_update, no_update
        
        record_index, replay_index, key_id, algorithm_name = click_info
        logger.info(f"🖱️ 按键与相对延时散点图点击: 算法={algorithm_name}, 按键={key_id}, record_index={record_index}, replay_index={replay_index}")
        
        # 计算中心时间
        center_time_ms = self._calculate_center_time_for_note_pair(backend, record_index, replay_index, algorithm_name)
        
        # 构建点信息
        point_info = {
            'algorithm_name': algorithm_name,
            'record_idx': record_index,
            'replay_idx': replay_index,
            'key_id': key_id,
            'source_plot_id': source_plot_id,
            'center_time_ms': center_time_ms
        }
        
        # 生成详细曲线图
        detail_figure1, detail_figure2, detail_figure_combined = self._generate_key_delay_detail_plots(backend, {
            'algorithm_name': algorithm_name,
            'record_index': record_index,
            'replay_index': replay_index
        })
        
        # 检查图表生成是否成功
        if detail_figure1 and detail_figure2 and detail_figure_combined:
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
            return modal_style, dcc.Graph(figure=detail_figure_combined, style={'height': '600px'}), point_info
        else:
            logger.warning("[WARNING] 按键与相对延时散点图点击回调 - 图表生成失败，部分图表为None")
            return current_style, [], no_update, no_update
    
    def _generate_key_delay_detail_plots(self, backend, click_data):
        """生成按键延时图的详细曲线图"""
        if click_data.get('algorithm_name'):
            # 多算法模式
            algorithm_name_param = click_data['algorithm_name']
            logger.info(f"🔍 调用backend.generate_multi_algorithm_scatter_detail_plot_by_indices: algorithm_name='{algorithm_name_param}', record_index={click_data['record_index']}, replay_index={click_data['replay_index']}")
            
            detail_figure1, detail_figure2, detail_figure_combined = backend.generate_multi_algorithm_scatter_detail_plot_by_indices(
                algorithm_name=algorithm_name_param,
                record_index=click_data['record_index'],
                replay_index=click_data['replay_index']
            )
        else:
            # 单算法模式
            detail_figure1, detail_figure2, detail_figure_combined = backend.generate_scatter_detail_plot_by_indices(
                record_index=click_data['record_index'],
                replay_index=click_data['replay_index']
            )
        
        logger.info(f"🔍 按键延时图生成结果: figure1={detail_figure1 is not None}, figure2={detail_figure2 is not None}, figure_combined={detail_figure_combined is not None}")
        
        return detail_figure1, detail_figure2, detail_figure_combined
