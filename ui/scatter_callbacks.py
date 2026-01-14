"""
散点图回调模块 - 处理所有散点图相关的交互逻辑
包含 Z-Score、按键延时、锤速散点图的点击处理

重构后使用专用处理器：
- ZScoreScatterHandler: Z-Score散点图
- HammerVelocityScatterHandler: 锤速散点图
- KeyDelayScatterHandler: 按键延时散点图
- VelocityComparisonHandler: 锤速对比图
- KeyForceInteractionHandler: 按键力度交互效应图
"""

import traceback
from typing import Optional, Tuple, List, Any, Union, Dict

import plotly.graph_objects as go
from plotly.graph_objs import Figure

from dash import html, dcc, no_update
from dash._callback import NoUpdate
from dash import Input, Output, State, ALL
from dash._callback_context import callback_context

from backend.session_manager import SessionManager
from utils.logger import Logger

# 导入新的处理器
from ui.zscore_scatter_handler import ZScoreScatterHandler
from ui.hammer_velocity_scatter_handler import HammerVelocityScatterHandler
from ui.key_delay_scatter_handler import KeyDelayScatterHandler
from ui.velocity_comparison_handler import VelocityComparisonHandler
from ui.key_force_interaction_handler import KeyForceInteractionHandler


logger = Logger.get_logger()


def register_scatter_callbacks(app, session_mgr: SessionManager):
    """注册散点图相关的回调函数"""
    # 创建所有处理器实例
    zscore_handler = ZScoreScatterHandler(session_mgr)
    hammer_velocity_handler = HammerVelocityScatterHandler(session_mgr)
    key_delay_handler = KeyDelayScatterHandler(session_mgr)
    velocity_comparison_handler = VelocityComparisonHandler(session_mgr)
    key_force_handler = KeyForceInteractionHandler(session_mgr)
    
    # ==================== Z-Score散点图回调 ====================
    
    @app.callback(
        Output('key-delay-zscore-scatter-plot', 'figure'),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_generate_zscore_scatter_plot(report_content, session_id):
        """处理按键与延时Z-Score标准化散点图自动生成 - 当报告内容更新时触发"""
        return zscore_handler.generate_zscore_scatter_plot(session_id)
    
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True),
         Output('key-delay-zscore-scatter-plot', 'clickData', allow_duplicate=True)],
        [Input('key-delay-zscore-scatter-plot', 'clickData'),
         Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State('session-id', 'data'),
         State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_zscore_scatter_click(zscore_scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理Z-Score标准化散点图点击，显示曲线对比（专用模态框）"""
        return zscore_handler.handle_zscore_scatter_click(zscore_scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style)
    
    # ==================== 锤速散点图回调 ====================
    
    @app.callback(
        Output('hammer-velocity-delay-scatter-plot', 'figure'),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_generate_hammer_velocity_scatter_plot(report_content, session_id):
        """处理锤速与延时Z-Score标准化散点图自动生成 - 当报告内容更新时触发"""
        return hammer_velocity_handler.generate_hammer_velocity_scatter_plot(session_id)
    
    @app.callback(
        Output('hammer-velocity-relative-delay-scatter-plot', 'figure'),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_generate_hammer_velocity_relative_delay_scatter_plot(report_content, session_id):
        """处理锤速与相对延时散点图自动生成 - 当报告内容更新时触发"""
        return hammer_velocity_handler.generate_hammer_velocity_relative_delay_scatter_plot(session_id)
    
    @app.callback(
        Output('key-curves-modal', 'style', allow_duplicate=True),
        Output('key-curves-comparison-container', 'children', allow_duplicate=True),
        Output('current-clicked-point-info', 'data', allow_duplicate=True),
        Input('hammer-velocity-delay-scatter-plot', 'clickData'),
        Input('close-key-curves-modal', 'n_clicks'),
        Input('close-key-curves-modal-btn', 'n_clicks'),
        State('session-id', 'data'),
        State('key-curves-modal', 'style'),
        prevent_initial_call=True
    )
    def handle_hammer_velocity_scatter_click(scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style):
        return hammer_velocity_handler.handle_hammer_velocity_scatter_click(scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style)
    
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True),
         Output('hammer-velocity-relative-delay-scatter-plot', 'clickData', allow_duplicate=True)],
        [Input('hammer-velocity-relative-delay-scatter-plot', 'clickData'),
         Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State('session-id', 'data'),
         State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_hammer_velocity_relative_delay_scatter_click(scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style):
        return hammer_velocity_handler.handle_hammer_velocity_relative_delay_plot_click(scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style)
    
    # ==================== 按键延时散点图回调 ====================
    
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True),
         Output('key-delay-scatter-plot', 'clickData', allow_duplicate=True)],
        [Input('key-delay-scatter-plot', 'clickData'),
         Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State('session-id', 'data'),
         State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_key_delay_scatter_click(scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理按键与相对延时散点图点击，显示曲线对比（专用模态框）"""
        return key_delay_handler.handle_key_delay_scatter_click(scatter_clickData, close_modal_clicks, close_btn_clicks, session_id, current_style)
    
    @app.callback(
        Output('key-delay-scatter-plot', 'figure'),
        [Input('report-content', 'children'),
         Input({'type': 'key-delay-scatter-common-keys-only', 'index': ALL}, 'value'),
         Input({'type': 'key-delay-scatter-algorithm-selector', 'index': ALL}, 'value')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_key_delay_scatter_plot_unified(report_content, common_keys_filter_values, algorithm_selector_values, session_id):
        """统一的按键与相对延时散点图回调函数 - 根据触发源和当前模式智能响应"""
        # 获取后端实例
        backend = session_mgr.get_backend(session_id)
        if not backend:
            return no_update
        
        # 解析 Pattern Matching Inputs - 简化参数提取
        common_keys_filter = common_keys_filter_values[0] if common_keys_filter_values else False
        algorithm_selector = algorithm_selector_values[0] if algorithm_selector_values else []
        
        # 判断触发源类型 - 简化逻辑
        ctx = callback_context
        if not ctx.triggered:
            return no_update
        
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        is_report_content_trigger = trigger_id == 'report-content'
        is_filter_trigger = 'key-delay-scatter-' in trigger_id
        
        # 提前判断分析模式
        active_algorithms = backend.multi_algorithm_manager.get_active_algorithms() if backend.multi_algorithm_manager else []
        is_multi_mode = len(active_algorithms) > 1
        has_analyzer = backend._get_current_analyzer() is not None
        
        try:
            # 单算法模式：只响应报告内容更新
            if not is_multi_mode and has_analyzer:
                if not is_report_content_trigger:
                    return no_update  # 单算法模式忽略筛选控件变化
                
                fig = backend.generate_key_delay_scatter_plot(
                    only_common_keys=False,
                    selected_algorithm_names=[]
                )
                logger.info("[OK] 单算法模式按键与相对延时散点图生成成功")
                return fig
            
            # 多算法模式：响应所有变化
            if is_multi_mode:
                fig = backend.generate_key_delay_scatter_plot(
                    only_common_keys=bool(common_keys_filter),
                    selected_algorithm_names=algorithm_selector or []
                )
                
                log_msg = "[OK] 多算法模式按键与相对延时散点图数据加载成功" if is_report_content_trigger else "[OK] 多算法模式按键与相对延时散点图筛选更新成功"
                logger.info(log_msg)
                return fig
            
            # 无分析器情况
            logger.warning("[WARNING] 没有有效的分析器，无法生成按键与相对延时散点图")
            return no_update
            
        except Exception as e:
            error_msg = f"按键与相对延时散点图处理失败: {str(e)}"
            logger.error(f"[ERROR] {error_msg}")
            
            return backend.plot_generator._create_empty_plot(error_msg) if backend else no_update
    
    # ==================== 锤速对比图回调 ====================
    
    @app.callback(
        Output('hammer-velocity-comparison-plot', 'figure'),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def callback_generate_hammer_velocity_comparison_plot(report_content, session_id):
        """处理锤速对比图自动生成 - 当报告内容更新时触发"""
        return velocity_comparison_handler.handle_generate_hammer_velocity_comparison_plot(report_content, session_id)
    
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('main-plot', 'figure', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True),
         Output('hammer-velocity-comparison-plot', 'clickData', allow_duplicate=True)],
        [Input('hammer-velocity-comparison-plot', 'clickData'),
         Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State('session-id', 'data'),
         State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def callback_hammer_velocity_comparison_click(
        click_data: Optional[Dict[str, Any]],
        close_modal_clicks: Optional[int],
        close_btn_clicks: Optional[int],
        session_id: str,
        current_style: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[Union[html.Div, dcc.Graph]], Union[Figure, NoUpdate], Dict[str, Any], Optional[Dict[str, Any]]]:
        """处理锤速对比图点击，显示对应按键的曲线对比（悬浮窗）"""
        return velocity_comparison_handler.handle_hammer_velocity_comparison_click(
            click_data, close_modal_clicks, close_btn_clicks, session_id, current_style
        )
    
    # ==================== 按键-力度交互效应图回调 ====================
    
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('main-plot', 'figure', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True),
         Output('key-force-interaction-plot', 'clickData', allow_duplicate=True)],
        [Input('key-force-interaction-plot', 'clickData'),
         Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State('session-id', 'data'),
         State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_key_force_interaction_plot_click_callback(click_data, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理按键-力度交互效应图点击回调"""
        return key_force_handler.handle_key_force_interaction_plot_click(click_data, close_modal_clicks, close_btn_clicks, session_id, current_style)
    
    # 注册按键-力度交互效应图回调
    register_key_force_interaction_callbacks(app, session_mgr)


# ==================== 按键-力度交互效应图相关独立函数 ====================

def _prepare_key_force_interaction_figure(trigger_id: str, backend, current_figure):
    """准备按键-力度交互效应图表对象"""
    # 如果是report-content变化，需要重新生成图表
    if trigger_id == 'report-content':
        # 检查是否有激活的算法
        active_algorithms = backend.get_active_algorithms()
        if not active_algorithms:
            logger.debug("[DEBUG] 没有激活的算法，跳过交互效应图生成")
            return backend.plot_generator._create_empty_plot("没有激活的算法")
        
        # 重新生成图表
        fig = backend.generate_key_force_interaction_plot()
    else:
        # 如果是选择变化，使用当前图表并更新可见性
        if current_figure and isinstance(current_figure, dict) and 'data' in current_figure:
            # 从dict创建Figure，确保所有属性都被正确加载
            fig = go.Figure(current_figure)
            # 确保data是trace对象列表，而不是dict列表
            if fig.data and isinstance(fig.data[0], dict):
                # 如果data是dict列表，需要转换为trace对象
                fig_data = []
                for trace_dict in fig.data:
                    trace_type = trace_dict.get('type', 'scatter')
                    if trace_type == 'scatter':
                        fig_data.append(go.Scatter(trace_dict))
                    else:
                        fig_data.append(trace_dict)
                fig.data = fig_data
        else:
            active_algorithms = backend.get_active_algorithms()
            if not active_algorithms:
                return no_update
            fig = backend.generate_key_force_interaction_plot()
    
    return fig


def _update_data_trace_visibility(data_list: List, selected_keys: List[int]):
    """更新数据trace的可见性 - 只根据按键选择控制"""
    visible_count = 0
    total_data_traces = 0
    
    for trace_idx, trace in enumerate(data_list):
        total_data_traces += 1
        
        # 从trace的customdata中提取按键信息
        key_id = None
        algorithm_name = None
        showlegend = False
        if isinstance(trace, dict):
            customdata = trace.get('customdata')
            legendgroup = trace.get('legendgroup', '')
            showlegend = trace.get('showlegend', False)
        else:
            customdata = trace.customdata if hasattr(trace, 'customdata') else None
            legendgroup = trace.legendgroup if hasattr(trace, 'legendgroup') else ''
            showlegend = trace.showlegend if hasattr(trace, 'showlegend') else False
        
        if customdata:
            try:
                if hasattr(customdata, '__iter__') and not isinstance(customdata, str):
                    if not isinstance(customdata, list):
                        customdata = list(customdata)
                    
                    if len(customdata) > 0:
                        first_point = customdata[0]
                        if hasattr(first_point, '__iter__') and not isinstance(first_point, str):
                            if not isinstance(first_point, list):
                                first_point = list(first_point)
                            
                            # customdata格式: [key_id, algorithm_name, ...]
                            if len(first_point) >= 2:
                                key_id = int(first_point[0])
                                algorithm_name = first_point[1] if first_point[1] else None
            except Exception as e:
                logger.debug(f"[TRACE] 提取按键ID失败: {e}")
        
        # 特殊处理：如果是显示图注的trace，始终保持可见
        # 这样图注始终显示，用户可以通过图注控制整个算法的显示
        is_legend_trace = showlegend and legendgroup.startswith('algorithm_')
        
        # 确定可见性：按键选择是唯一的过滤条件
        if selected_keys:
            # 选择了特定按键：只显示该按键的数据，完全过滤掉其他数据
            target_visible = key_id is not None and key_id in selected_keys
        else:
            # 没有选择按键：显示所有数据（默认行为）
            target_visible = True
        
        # 对图注trace特殊处理：图注始终可见，但不计入数据可见性统计
        if is_legend_trace:
            visible = True  # 图注始终可见
        else:
            visible = target_visible
            if visible:
                visible_count += 1
        
        # 更新可见性
        if isinstance(trace, dict):
            trace['visible'] = True if visible else 'legendonly'
        else:
            trace.visible = True if visible else 'legendonly'
    
    logger.info(f"[INFO] 按键-力度交互效应图可见性更新: {visible_count}/{total_data_traces} traces可见 (selected_keys={selected_keys})")


def handle_generate_key_force_interaction_plot_with_session(session_manager: SessionManager, report_content, selected_keys, session_id, current_figure):
    """处理按键-力度交互效应图自动生成和更新 - 根据选中的按键更新可见性"""
    ctx = callback_context
    if not ctx.triggered:
        return no_update
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    backend = session_manager.get_backend(session_id)
    if not backend:
        return no_update
    
    try:
        # 根据选中的按键更新可见性
        selected_keys = selected_keys or []
        
        # 准备图表对象
        fig = _prepare_key_force_interaction_figure(trigger_id, backend, current_figure)
        if fig is no_update or isinstance(fig, str):  # 如果是空图或错误，直接返回
            return fig
        
        # 将fig.data转换为可修改的list
        data_list = list(fig.data)
        
        # 更新数据trace的可见性
        _update_data_trace_visibility(data_list, selected_keys)
        
        # 将修改后的trace列表赋值回fig.data
        fig.data = data_list
        
        logger.info(f"[OK] 按键-力度交互效应图更新成功 (触发器: {trigger_id})")
        return fig
        
    except Exception as e:
        logger.error(f"[ERROR] 生成/更新按键-力度交互效应图失败: {e}")
        logger.error(traceback.format_exc())
        return backend.plot_generator._create_empty_plot(f"生成交互效应图失败: {str(e)}")


def update_key_selector_options(figure):
    """根据图表数据更新按键选择器的选项"""
    if not figure or 'data' not in figure:
        return []
    
    # 提取所有按键ID
    key_ids = set()
    for trace in figure['data']:
        customdata = trace.get('customdata')
        if customdata:
            try:
                if hasattr(customdata, '__iter__') and not isinstance(customdata, str):
                    if not isinstance(customdata, list):
                        customdata = list(customdata)
                    
                    if len(customdata) > 0:
                        first_point = customdata[0]
                        if hasattr(first_point, '__iter__') and not isinstance(first_point, str):
                            if not isinstance(first_point, list):
                                first_point = list(first_point)
                            
                            # customdata格式: [key_id, algorithm_name, replay_velocity, relative_delay, absolute_delay, record_index, replay_index]
                            if len(first_point) >= 1:
                                key_id = int(first_point[0])
                                key_ids.add(key_id)
            except Exception as e:
                logger.debug(f"[TRACE] 从trace提取按键ID失败: {e}")
    
    # 生成下拉选项
    options = [{'label': f'按键 {key_id}', 'value': key_id} for key_id in sorted(key_ids)]
    return options


def update_selected_keys_from_dropdown(selected_key):
    """当下拉菜单选择改变时，更新selected_keys"""
    if selected_key is None:
        return []
    return [selected_key]


def register_key_force_interaction_callbacks(app, session_manager: SessionManager):
    """注册按键-力度交互效应图相关的回调函数"""
    
    # 更新按键选择器选项
    @app.callback(
        Output('key-force-interaction-key-selector', 'options'),
        [Input('key-force-interaction-plot', 'figure')],
        prevent_initial_call=True
    )
    def callback_update_key_selector_options(figure):
        return update_key_selector_options(figure)
    
    # 当下拉菜单选择改变时，更新selected_keys
    @app.callback(
        Output('key-force-interaction-selected-keys', 'data'),
        [Input('key-force-interaction-key-selector', 'value')],
        prevent_initial_call=True
    )
    def callback_update_selected_keys_from_dropdown(selected_key):
        return update_selected_keys_from_dropdown(selected_key)
    
    # 按键-力度交互效应图自动生成和更新回调函数
    @app.callback(
        Output('key-force-interaction-plot', 'figure'),
        [Input('report-content', 'children'),
         Input('key-force-interaction-selected-keys', 'data')],
        [State('session-id', 'data'),
         State('key-force-interaction-plot', 'figure')],
        prevent_initial_call=True
    )
    def callback_handle_generate_key_force_interaction_plot(report_content, selected_keys, session_id, current_figure):
        return handle_generate_key_force_interaction_plot_with_session(session_manager, report_content, selected_keys, session_id, current_figure)
