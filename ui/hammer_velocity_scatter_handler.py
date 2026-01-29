"""
锤速散点图处理器 - 处理锤速相关散点图的生成和交互
包括：锤速与延时Z-Score散点图、锤速与相对延时散点图
"""

import traceback
from typing import Optional, Tuple, Union, Any, Dict

from dash import no_update
from dash._callback import NoUpdate
from dash._callback_context import callback_context

from backend.piano_analysis_backend import PianoAnalysisBackend
from backend.session_manager import SessionManager
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
    
    def handle_hammer_velocity_scatter_click(self, scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理锤速与延时Z-Score标准化散点图点击，显示曲线对比（悬浮窗）"""
        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            logger.debug("[WARNING] 锤速与延时Z-Score标准化散点图点击回调：没有触发源")
            return no_update, no_update, no_update
        
        trigger_id_raw = ctx.triggered[0]['prop_id'].split('.')[0]
        
        # 1. 解析 Plot ID
        plot_id = trigger_id_raw
        if trigger_id_raw.startswith('{'):
            try:
                import json
                plot_id = json.loads(trigger_id_raw).get('id', trigger_id_raw)
            except Exception:
                pass
        
        # 如果点击了关闭按钮，只有当模态框是显示状态时才处理
        if plot_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            # 检查模态框是否真的打开了（由本回调打开的）
            if current_style and current_style.get('display') == 'block':
                # 进一步检查：只有当有点击数据存在时才关闭（说明是从本回调打开的）
                if scatter_clickData is not None:
                    result = self._handle_modal_close()
                    return result[0], result[1], result[2]
            # 不是本回调打开的，不处理，让其他回调处理
            return no_update, no_update, no_update
        
        # 如果是锤速与延时Z-Score标准化散点图点击
        if plot_id == 'hammer-velocity-delay-scatter-plot' and scatter_clickData:
            result = self._handle_hammer_velocity_plot_click(scatter_clickData, session_id, current_style, 'hammer-velocity-delay-scatter-plot')
            return result[0], result[1], result[2]
        
        # 其他情况，返回默认值
        return no_update, no_update, no_update
    
    def handle_hammer_velocity_relative_delay_plot_click(self, scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理锤速与相对延时散点图点击，显示曲线对比（悬浮窗）"""
        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            logger.debug("[WARNING] 锤速与相对延时散点图点击回调：没有触发源")
            return no_update, no_update, no_update, no_update
        
        trigger_id_raw = ctx.triggered[0]['prop_id'].split('.')[0]
        
        # 1. 解析 Plot ID
        plot_id = trigger_id_raw
        if trigger_id_raw.startswith('{'):
            try:
                import json
                plot_id = json.loads(trigger_id_raw).get('id', trigger_id_raw)
            except Exception:
                pass
        
        # 如果点击了关闭按钮，只有当模态框是由本回调打开时才处理
        if plot_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            if current_style and current_style.get('display') == 'block' and scatter_clickData is not None:
                result = self._handle_modal_close()
                return result[0], result[1], result[2], result[3]
            return no_update, no_update, no_update, no_update
        
        # 如果是锤速与相对延时散点图点击
        if plot_id == 'hammer-velocity-relative-delay-scatter-plot' and scatter_clickData:
            result = self._handle_hammer_velocity_relative_delay_plot_click(scatter_clickData, session_id, current_style, 'hammer-velocity-relative-delay-scatter-plot')
            return result[0], result[1], result[2], no_update
        
        # 其他情况，返回默认值
        return no_update, no_update, no_update, no_update
    
    # ==================== 私有方法 ====================
    
    def _handle_modal_close(self) -> Tuple[Dict[str, Any], list, Any]:
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
    
    def _handle_hammer_velocity_relative_delay_plot_click(self, scatter_clickData, session_id, current_style, source_plot_id='hammer-velocity-relative-delay-scatter-plot'):
        """处理锤速与相对延时散点图点击的主要逻辑"""
        logger.info(f"🔍 锤速与相对延时散点图点击回调被触发 - source_plot_id: {source_plot_id}, clickData: {scatter_clickData is not None}")
        
        # 验证点击数据
        if 'points' not in scatter_clickData or len(scatter_clickData['points']) == 0:
            logger.warning("[WARNING] 锤速与相对延时散点图点击回调 - scatter_clickData无效或没有points")
            return current_style, [], no_update, no_update
        
        point = scatter_clickData['points'][0]
        
        if not point.get('customdata'):
            logger.warning("[WARNING] 锤速与相对延时散点图点击 - 点没有customdata")
            return current_style, [], no_update, no_update
        
        # 提取customdata - 锤速与相对延时散点图格式: [delay_ms, original_velocity, record_idx, replay_idx, algorithm_name, key_id]
        raw_customdata = point['customdata']
        
        if isinstance(raw_customdata, list) and len(raw_customdata) > 0:
            customdata = raw_customdata[0] if isinstance(raw_customdata[0], list) else raw_customdata
        else:
            customdata = raw_customdata
        
        if not isinstance(customdata, list) or len(customdata) < 6:
            logger.warning(f"[WARNING] 锤速与相对延时散点图点击 - customdata无效: {customdata}")
            return current_style, [], no_update, no_update
        
        # 解析锤速与相对延时散点图的customdata格式: [delay_ms, original_velocity, record_idx, replay_idx, algorithm_name, key_id]
        delay_ms = customdata[0]
        original_velocity = customdata[1]
        record_index = customdata[2]
        replay_index = customdata[3]
        algorithm_name = customdata[4]
        key_id = customdata[5]
        
        logger.info(f"🖱️ 锤速与相对延时散点图点击: 算法={algorithm_name}, 按键={key_id}, record_index={record_index}, replay_index={replay_index}")
        
        # 转换为按键延时格式并处理
        key_delay_click_data = {
            'points': [{
                'customdata': [record_index, replay_index, key_id, delay_ms, algorithm_name]
            }]
        }
        
        result = self._handle_key_delay_plot_click(key_delay_click_data, session_id, current_style, source_plot_id)
        
        # 如果成功，更新点信息以包含锤速相关信息
        if result[0].get('display') == 'block' and len(result) > 2 and isinstance(result[2], dict):
            result[2]['锤速'] = f"{original_velocity:.0f}"
            result[2]['相对延时'] = f"{delay_ms:.2f}ms"
            result[2]['绝对延时'] = f"{delay_ms:.2f}ms"
        
        return result
    
    def _handle_hammer_velocity_plot_click(self, scatter_clickData, session_id, current_style, source_plot_id='hammer-velocity-delay-scatter-plot'):
        """处理锤速与延时Z-Score散点图点击的主要逻辑"""
        logger.info(f"🔍 锤速与延时Z-Score散点图点击回调被触发 - source_plot_id: {source_plot_id}, clickData: {scatter_clickData is not None}")
        
        # 验证点击数据
        if 'points' not in scatter_clickData or len(scatter_clickData['points']) == 0:
            logger.warning("[WARNING] 锤速与延时Z-Score散点图点击回调 - scatter_clickData无效或没有points")
            return current_style, [], no_update, no_update
        
        point = scatter_clickData['points'][0]
        
        if not point.get('customdata'):
            logger.warning("[WARNING] 锤速与延时Z-Score散点图点击 - 点没有customdata")
            return current_style, [], no_update, no_update
        
        # 提取customdata - 锤速与延时Z-Score散点图格式: [delay_ms, original_velocity, record_idx, replay_idx, algorithm_name, key_id]
        raw_customdata = point['customdata']
        
        if isinstance(raw_customdata, list) and len(raw_customdata) > 0:
            customdata = raw_customdata[0] if isinstance(raw_customdata[0], list) else raw_customdata
        else:
            customdata = raw_customdata
        
        if not isinstance(customdata, list) or len(customdata) < 6:
            logger.warning(f"[WARNING] 锤速与延时Z-Score散点图点击 - customdata无效: {customdata}")
            return current_style, [], no_update, no_update
        
        # 解析锤速与延时Z-Score散点图的customdata格式: [delay_ms, original_velocity, record_idx, replay_idx, algorithm_name, key_id]
        delay_ms = customdata[0]
        original_velocity = customdata[1]
        record_index = customdata[2]
        replay_index = customdata[3]
        algorithm_name = customdata[4]
        key_id = customdata[5]
        
        logger.info(f"🖱️ 锤速与延时Z-Score散点图点击: 算法={algorithm_name}, 按键={key_id}, record_index={record_index}, replay_index={replay_index}")
        
        # 转换为按键延时格式并处理
        key_delay_click_data = {
            'points': [{
                'customdata': [record_index, replay_index, key_id, delay_ms, algorithm_name]
            }]
        }
        
        result = self._handle_key_delay_plot_click(key_delay_click_data, session_id, current_style, source_plot_id)
        
        # 如果成功，更新点信息以包含锤速相关信息
        if result[0].get('display') == 'block' and len(result) > 2 and isinstance(result[2], dict):
            result[2]['锤速'] = f"{original_velocity:.0f}"
            result[2]['延时'] = f"{delay_ms:.2f}ms"
            result[2]['Z-Score延时'] = f"{delay_ms:.2f}ms"
        
        return result
    
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
            modal_style, graph_component, point_info_response = self._create_modal_response(detail_figure_combined, point_info)
            return modal_style, graph_component, point_info_response
        else:
            logger.warning("[WARNING] 按键与相对延时散点图点击回调 - 图表生成失败，部分图表为None")
            return current_style, [], no_update, no_update
    
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
    
    def _create_modal_response(self, detail_figure_combined: Any, point_info: Dict[str, Any]) -> Tuple[Dict[str, Any], Any, Dict[str, Any]]:
        """创建模态框响应"""
        from dash import dcc
        
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
        
        logger.info("[OK] 散点图点击回调 - 返回模态框和图表")
        return modal_style, dcc.Graph(figure=detail_figure_combined, style={'height': '600px'}), point_info
