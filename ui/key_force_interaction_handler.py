"""
按键-力度交互效应图处理器 - 处理按键力度交互效应图的交互
"""

import traceback
from typing import Optional, Tuple, List, Any, Union, Dict

from dash import html, dcc, no_update
from dash._callback import NoUpdate
from dash._callback_context import callback_context
from plotly.graph_objs import Figure

from backend.piano_analysis_backend import PianoAnalysisBackend
from backend.session_manager import SessionManager
from ui.scatter_handler_base import ScatterHandlerBase
from utils.logger import Logger


logger = Logger.get_logger()


class KeyForceInteractionHandler(ScatterHandlerBase):
    """
    按键-力度交互效应图处理器
    
    负责处理按键-力度交互效应图的点击交互
    """
    
    def handle_key_force_interaction_plot_click(
        self, click_data: Optional[Dict[str, Any]],
        close_modal_clicks: Optional[int],
        close_btn_clicks: Optional[int],
        session_id: str,
        current_style: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[Union[html.Div, dcc.Graph]], Union[Figure, NoUpdate], Dict[str, Any], Optional[Dict[str, Any]]]:
        """处理按键-力度交互效应图点击，显示对应按键的曲线对比（悬浮窗）"""
        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            logger.debug("[WARNING] 按键-力度交互效应图点击回调：没有触发源")
            return current_style, [], no_update, no_update, no_update
        
        trigger_prop = ctx.triggered[0]['prop_id']
        trigger_id = trigger_prop.split('.')[0]
        logger.info(f"[INFO] 按键-力度交互效应图点击回调触发：prop_id={trigger_prop}, trigger_id={trigger_id}, click_data={click_data is not None}, close_modal_clicks={close_modal_clicks}, close_btn_clicks={close_btn_clicks}")
        
        # 如果点击了关闭按钮，只有当模态框是由本回调打开时才处理
        if trigger_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            if current_style and current_style.get('display') == 'block' and click_data is not None:
                result = self._handle_modal_close_trigger()
                return result[0], result[1], result[2], result[3], result[4]
            return no_update, no_update, no_update, no_update, no_update
        
        # 如果是按键-力度交互效应图点击
        if trigger_id == 'key-force-interaction-plot':
            if not click_data or 'points' not in click_data or not click_data['points']:
                logger.warning("[WARNING] 按键-力度交互效应图点击 - click_data无效")
                return current_style, [], no_update, no_update, no_update
            return self._handle_key_force_interaction_plot_click_logic(click_data, session_id, current_style)
        
        # 默认返回
        return current_style, [], no_update, no_update, no_update
    
    # ==================== 私有方法 ====================
    
    def _handle_modal_close_trigger(self) -> Tuple[Dict[str, Any], List[Union[html.Div, dcc.Graph]], Union[Figure, NoUpdate], Dict[str, Any], Optional[Dict[str, Any]]]:
        """处理模态框关闭按钮的通用逻辑"""
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
        return modal_style, [], no_update, no_update, no_update
    
    def _handle_key_force_interaction_plot_click_logic(self, click_data, session_id, current_style):
        """处理按键-力度交互效应图点击的具体逻辑"""
        logger.info(f"[PROCESS] 按键-力度交互效应图点击：click_data={click_data}")
        
        backend = self.session_manager.get_backend(session_id)
        if not backend:
            logger.warning("[WARNING] 没有找到backend")
            return current_style, [], no_update, no_update, no_update
        
        try:
            # 解析点击数据 - 按键-力度交互效应图需要至少7个元素的customdata
            parsed_data = self._parse_plot_click_data(click_data, "按键-力度交互效应图", 7)
            if not parsed_data:
                return current_style, [], no_update, no_update, no_update
            
            customdata = parsed_data['customdata']
            
            # 按键-力度交互效应图的customdata格式: [key_id, algorithm_name, replay_velocity, relative_delay, absolute_delay, record_index, replay_index]
            key_id = customdata[0]
            algorithm_display_name = customdata[1] if customdata[1] else None
            replay_velocity = customdata[2]
            relative_delay = customdata[3]
            absolute_delay = customdata[4]
            record_idx = customdata[5]
            replay_idx = customdata[6]
            
            if record_idx is None or replay_idx is None:
                logger.warning(f"[WARNING] 按键-力度交互效应图点击 - 缺少索引信息: record_idx={record_idx}, replay_idx={replay_idx}")
                return current_style, [], no_update, no_update, no_update
            
            logger.info(f"🖱️ 按键-力度交互效应图点击: 算法={algorithm_display_name}, 按键={key_id}, 锤速={replay_velocity}, record_idx={record_idx}, replay_idx={replay_idx}")
            
            # 生成详细曲线图
            detail_figure1, detail_figure2, detail_figure_combined = self._generate_key_delay_detail_plots(backend, {
                'algorithm_name': algorithm_display_name,
                'record_index': record_idx,
                'replay_index': replay_idx
            })
            
            # 计算中心时间用于瀑布图跳转
            center_time_ms = self._calculate_key_force_center_time(backend, {
                'algorithm_name': algorithm_display_name,
                'record_index': record_idx,
                'replay_index': replay_idx
            })
            
            point_info = {
                'algorithm_name': algorithm_display_name,
                'record_idx': record_idx,
                'replay_idx': replay_idx,
                'key_id': key_id,
                'source_plot_id': 'key-force-interaction-plot',
                'center_time_ms': center_time_ms
            }
            
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
                
                return modal_style, [dcc.Graph(
                    figure=detail_figure_combined,
                    style={'height': '800px'}
                )], no_update, point_info, no_update
            else:
                logger.warning("[WARNING] 按键-力度交互效应图点击回调 - 图表生成失败，部分图表为None")
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
                return modal_style, [html.Div([
                    html.P(f"无法生成详细图表", className="text-danger text-center")
                ])], no_update, no_update, no_update
                
        except Exception as e:
            logger.error(f"[ERROR] 处理按键-力度交互效应图点击失败: {e}")
            logger.error(traceback.format_exc())
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
            return modal_style, [html.Div([
                html.P(f"处理点击失败: {str(e)}", className="text-danger text-center")
            ])], no_update, no_update, no_update
    
    def _calculate_key_force_center_time(self, backend: PianoAnalysisBackend, click_data: Dict[str, Any]) -> Optional[float]:
        """
        计算按键-力度交互效应图点击点的中心时间
        
        Args:
            backend: 后端实例
            click_data: 点击数据
            
        Returns:
            Optional[float]: 中心时间（毫秒），计算失败返回None
        """
        try:
            algorithm_name = click_data.get('algorithm_name')
            record_index = click_data.get('record_index')
            replay_index = click_data.get('replay_index')
            
            if record_index is None or replay_index is None:
                return None
            
            # 使用基类的方法计算中心时间
            return self._calculate_center_time_for_note_pair(backend, record_index, replay_index, algorithm_name)
            
        except Exception as e:
            logger.warning(f"[WARNING] 计算按键-力度交互效应图中心时间失败: {e}")
            return None
    
    def _generate_key_delay_detail_plots(self, backend: PianoAnalysisBackend, click_data: Dict[str, Any]) -> Tuple[Any, Any, Any]:
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
