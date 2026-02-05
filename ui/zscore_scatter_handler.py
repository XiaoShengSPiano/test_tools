"""
Z-Score散点图处理器 - 处理Z-Score标准化散点图的生成和交互
"""

import traceback
from typing import Optional, Tuple, List, Any, Union, Dict, TypedDict

from dash import dcc, no_update
from dash._callback import NoUpdate
from dash._callback_context import callback_context

from backend.piano_analysis_backend import PianoAnalysisBackend
from backend.session_manager import SessionManager
from ui.scatter_handler_base import ScatterHandlerBase
from utils.logger import Logger


logger = Logger.get_logger()


# Type definition
class ZScoreClickData(TypedDict):
    """Z-Score散点图点击数据的类型定义"""
    record_index: int
    replay_index: int
    key_id: Optional[int]
    algorithm_name: str


class ZScoreScatterHandler(ScatterHandlerBase):
    """
    Z-Score散点图处理器
    
    负责处理Z-Score标准化散点图的生成、点击交互和数据管理
    """
    
    def generate_zscore_scatter_plot(self, session_id: str) -> Union[Any, NoUpdate]:
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
    
    def handle_zscore_scatter_click(self, zscore_scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理Z-Score标准化散点图点击，显示曲线对比（悬浮窗）"""
        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            logger.debug("[WARNING] Z-Score散点图点击回调：没有触发源")
            return no_update, no_update, no_update, no_update
        
        trigger_id_raw = ctx.triggered[0]['prop_id'].split('.')[0]
        
        # 1. 解析 Plot ID (支持字符串和模式匹配字典)
        plot_id = trigger_id_raw
        if trigger_id_raw.startswith('{'):
            try:
                import json
                plot_id = json.loads(trigger_id_raw).get('id', trigger_id_raw)
            except Exception:
                pass
        
        # 如果点击了关闭按钮，只有当模态框是由本回调打开时才处理
        if plot_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            if current_style and current_style.get('display') == 'block' and zscore_scatter_clickData is not None:
                return self._handle_zscore_modal_close()
            else:
                return no_update, no_update, no_update, no_update
        
        # 如果是Z-Score散点图点击
        if plot_id == 'key-delay-zscore-scatter-plot':
            if not zscore_scatter_clickData or 'points' not in zscore_scatter_clickData:
                logger.warning("[WARNING] Z-Score标准化散点图点击 - clickData无效")
                return no_update, no_update, no_update, no_update
            
            return self._handle_zscore_plot_click(zscore_scatter_clickData, session_id, current_style)
        
        # 其他情况，保持当前状态
        return no_update, no_update, no_update, no_update
    
    # ==================== 私有方法 ====================
    
    def _extract_zscore_customdata(self, raw_customdata: Any) -> Optional[ZScoreClickData]:
        """
        提取和验证Z-Score散点图的customdata
        
        Args:
            raw_customdata: 原始customdata
            
        Returns:
            Optional[ZScoreClickData]: 提取的点击数据，失败返回None
        """
        if isinstance(raw_customdata, list) and len(raw_customdata) > 0:
            customdata = raw_customdata[0] if isinstance(raw_customdata[0], list) else raw_customdata
        else:
            customdata = raw_customdata
        
        if not isinstance(customdata, list):
            logger.warning(f"[WARNING] Z-Score标准化散点图点击 - customdata不是列表类型: {type(customdata)}, 值: {customdata}")
            return None
        
        if len(customdata) < 5:
            logger.warning(f"[WARNING] Z-Score标准化散点图点击 - customdata长度不足: {len(customdata)}")
            return None
        
        # Z-Score散点图的customdata格式: [record_index, replay_index, key_id_int, delay_ms, algorithm_name]
        # 单算法模式: [record_index, replay_index, key_id_int, delay_ms] (4个元素)
        # 多算法模式: [record_index, replay_index, key_id_int, delay_ms, algorithm_name] (5个元素)
        record_index = customdata[0]
        replay_index = customdata[1]
        key_id = customdata[2] if len(customdata) > 2 else None
        algorithm_name = customdata[4] if len(customdata) > 4 else None
        
        return {
            'record_index': record_index,
            'replay_index': replay_index,
            'key_id': key_id,
            'algorithm_name': algorithm_name
        }
    
    def _calculate_zscore_center_time(self, backend: PianoAnalysisBackend, click_data: ZScoreClickData) -> Optional[float]:
        """
        计算Z-Score散点图点击点的中心时间
        
        Args:
            backend: 后端实例
            click_data: 点击数据
            
        Returns:
            Optional[float]: 中心时间（毫秒），计算失败返回None
        """
        try:
            # 获取分析器
            analyzer = self._get_analyzer_for_algorithm(backend, click_data['algorithm_name'])
            if not analyzer or not analyzer.note_matcher:
                return None
            
            record_index = click_data['record_index']
            replay_index = click_data['replay_index']
            
            # 从预计算的 offset_data 中获取时间信息
            keyon_times = self._get_time_from_offset_data(analyzer.note_matcher, record_index, replay_index)
            if keyon_times:
                record_keyon, replay_keyon = keyon_times
                return self._calculate_center_time_ms(record_keyon, replay_keyon)
            
            return None
            
        except Exception as e:
            logger.warning(f"[WARNING] 计算时间信息失败: {e}")
            return None
    
    def _get_time_from_offset_data(self, note_matcher: Any, record_index: int, replay_index: int) -> Optional[Tuple[float, float]]:
        """
        从预计算的offset_data中获取时间信息
        
        Args:
            note_matcher: 音符匹配器实例
            record_index: 录制音符索引
            replay_index: 播放音符索引
            
        Returns:
            Optional[Tuple[float, float]]: (record_keyon, replay_keyon)，获取失败返回None
        """
        try:
            offset_data = note_matcher.get_precision_offset_alignment_data()
            if not offset_data:
                return None
            
            for item in offset_data:
                if item.get('record_index') == record_index and item.get('replay_index') == replay_index:
                    record_keyon = item.get('record_keyon', 0)
                    replay_keyon = item.get('replay_keyon', 0)
                    if record_keyon and replay_keyon:
                        return record_keyon, replay_keyon
            return None
        except Exception as e:
            logger.warning(f"[WARNING] 从offset_data获取时间信息失败 (record_index={record_index}, replay_index={replay_index}): {e}")
            return None
    
    def _create_zscore_modal_response(self, detail_figure_combined: Any, point_info: Dict[str, Any]) -> Tuple[Dict[str, Any], Any, Dict[str, Any]]:
        """
        创建Z-Score模态框响应
        
        Args:
            detail_figure_combined: 组合详细图表
            point_info: 点信息
            
        Returns:
            Tuple[Dict[str, Any], Any, Dict[str, Any]]: (模态框样式, 图表组件, 点信息)
        """
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
        
        logger.info("[OK] Z-Score标准化散点图点击回调 - 返回模态框和图表")
        return modal_style, dcc.Graph(figure=detail_figure_combined, style={'height': '600px'}), point_info
    
    def _handle_zscore_modal_close(self) -> Tuple[Dict[str, Any], List[Any], NoUpdate, NoUpdate]:
        """处理Z-Score模态框关闭逻辑"""
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
    
    def _handle_zscore_plot_click(self, zscore_scatter_clickData: Optional[Dict[str, Any]], session_id: str, current_style: Dict[str, Any], source_plot_id: str = 'key-delay-zscore-scatter-plot') -> Tuple[Dict[str, Any], List[Any], Union[Dict[str, Any], NoUpdate]]:
        """处理Z-Score散点图点击的主要逻辑"""
        logger.info(f"🔍 散点图点击回调被触发 - source_plot_id: {source_plot_id}, clickData: {zscore_scatter_clickData is not None}")
        
        backend = self.session_manager.get_backend(session_id)
        if not backend:
            logger.warning("[WARNING] 没有找到backend")
            return current_style, [], no_update, no_update
        
        # 验证点击数据 - Z-Score图表需要至少5个元素的customdata
        parsed_data = self._parse_plot_click_data(zscore_scatter_clickData, "Z-Score标准化散点图", 5)
        if not parsed_data:
            return current_style, [], no_update, no_update
        
        # 提取customdata
        click_data = self._extract_zscore_customdata(parsed_data['raw_customdata'])
        if not click_data:
            return current_style, [], no_update, no_update
        
        # 计算中心时间
        center_time_ms = self._calculate_zscore_center_time(backend, click_data)
        
        # 存储当前点击的数据点信息，用于跳转按钮
        point_info = {
            'algorithm_name': click_data['algorithm_name'],
            'record_idx': click_data['record_index'],
            'replay_idx': click_data['replay_index'],
            'key_id': click_data['key_id'],
            'source_plot_id': source_plot_id,  # 记录来源图表ID
            'center_time_ms': center_time_ms  # 预先计算的时间信息
        }
        
        # 生成详细曲线图
        detail_figure1, detail_figure2, detail_figure_combined = self._generate_key_delay_detail_plots(backend, click_data)
        
        # 检查图表生成是否成功
        if detail_figure1 and detail_figure2 and detail_figure_combined:
            modal_style, graph_component, point_info_response = self._create_zscore_modal_response(detail_figure_combined, point_info)
            return modal_style, graph_component, no_update, point_info_response, None
        else:
            logger.warning("[WARNING] Z-Score标准化散点图点击回调 - 图表生成失败，部分图表为None")
            return current_style, [], no_update, no_update, no_update
    
    def _generate_key_delay_detail_plots(self, backend: PianoAnalysisBackend, click_data: Dict[str, Any]) -> Tuple[Any, Any, Any]:
        """
        生成按键延时图的详细曲线图
        """
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
    
    def _validate_zscore_plot(self, fig):
        """验证Z-Score图表是否正确生成"""
        if not fig or not hasattr(fig, 'data') or not fig.data:
            return False
        return True
