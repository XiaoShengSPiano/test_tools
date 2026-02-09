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
import json
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
from ui.delay_time_series_handler import DelayTimeSeriesHandler


logger = Logger.get_logger()


def register_scatter_callbacks(app, session_mgr: SessionManager):
    """注册散点图相关的回调函数"""
    # 创建所有处理器实例
    zscore_handler = ZScoreScatterHandler(session_mgr)
    hammer_velocity_handler = HammerVelocityScatterHandler(session_mgr)
    key_delay_handler = KeyDelayScatterHandler(session_mgr)
    velocity_comparison_handler = VelocityComparisonHandler(session_mgr)
    key_force_handler = KeyForceInteractionHandler(session_mgr)
    delay_time_series_handler = DelayTimeSeriesHandler(session_mgr)
    
    # ==================== Z-Score散点图回调 ====================
    
    @app.callback(
        Output({'type': 'scatter-plot', 'id': 'key-delay-zscore-scatter-plot'}, 'figure'),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_generate_zscore_scatter_plot(report_content, session_id):
        """处理按键与延时Z-Score标准化散点图自动生成 - 当报告内容更新时触发"""
        return zscore_handler.generate_zscore_scatter_plot(session_id)
    
    # ==================== 统一散点图点击回调 (Pattern Matching) ====================
    
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True),
         Output({'type': 'scatter-plot', 'id': ALL}, 'clickData')],
        [Input({'type': 'scatter-plot', 'id': ALL}, 'clickData'),
         Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State('session-id', 'data'),
         State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_any_scatter_click(all_click_data, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理所有散点图点击"""
        ctx = callback_context
        if not ctx.triggered:
            return no_update
        
        trigger_id_raw = ctx.triggered[0]['prop_id'].split('.')[0]
        
        # 1. 弹窗关闭逻辑
        if trigger_id_raw in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            new_style = current_style.copy()
            new_style['display'] = 'none'
            return new_style, [], no_update, [None] * len(all_click_data)

        # 2. 提取 Plot ID
        if trigger_id_raw.startswith('{'):
            plot_id = json.loads(trigger_id_raw).get('id')
        else:
            plot_id = trigger_id_raw

        # 3. 查找点击数据
        click_data = next((d for d in all_click_data if d), None)
        if not click_data:
            return no_update

        # 4. 根据 ID 分发到处理器
        style, children, point_info = no_update, no_update, no_update
        
        if plot_id == 'key-delay-zscore-scatter-plot':
            style, children, point_info = zscore_handler.handle_zscore_scatter_click(click_data, session_id, current_style)
        
        elif plot_id == 'hammer-velocity-delay-scatter-plot':
            style, children, point_info = hammer_velocity_handler.handle_hammer_velocity_scatter_click(click_data, session_id, current_style)
            
        elif plot_id in ['hammer-velocity-relative-delay-scatter-plot', 'relative-delay-distribution-plot']:
            style, children, point_info = hammer_velocity_handler.handle_hammer_velocity_scatter_click(click_data, session_id, current_style)
            
        elif plot_id == 'key-delay-scatter-plot':
            style, children, point_info = key_delay_handler.handle_key_delay_scatter_click(click_data, session_id, current_style)
            
        elif plot_id == 'hammer-velocity-comparison-plot':
            style, children, point_info = velocity_comparison_handler.handle_hammer_velocity_comparison_click(click_data, session_id, current_style)
            
        elif plot_id == 'key-force-interaction-plot':
            style, children, point_info = key_force_handler.handle_key_force_interaction_plot_click(click_data, session_id, current_style)
            
        elif plot_id in ['raw-delay-time-series-plot', 'relative-delay-time-series-plot']:
            raw_data = click_data if plot_id == 'raw-delay-time-series-plot' else None
            rel_data = click_data if plot_id == 'relative-delay-time-series-plot' else None
            # 注意：DelayTimeSeriesHandler 暂未重构，保持原样或在此一并简化
            res = delay_time_series_handler.handle_delay_time_series_click_multi(raw_data, rel_data, None, None, session_id, current_style)
            style, children, point_info = res[0], res[1], res[2]

        return style, children, point_info, [None] * len(all_click_data)
    
    @app.callback(
        Output({'type': 'scatter-plot', 'id': 'relative-delay-distribution-plot'}, 'figure'),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_generate_relative_delay_distribution_plot(report_content, session_id):
        backend = session_mgr.get_backend(session_id)
        return backend.generate_relative_delay_distribution_plot() if backend else no_update

    @app.callback(
        Output({'type': 'scatter-plot', 'id': 'key-delay-scatter-plot'}, 'figure'),
        [Input('report-content', 'children'),
         Input({'type': 'key-delay-scatter-common-keys-only', 'index': ALL}, 'value'),
         Input({'type': 'key-delay-scatter-algorithm-selector', 'index': ALL}, 'value')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_key_delay_scatter_plot_unified(report_content, common_keys_filter_values, algorithm_selector_values, session_id):
        """直接实现按键延时散点图逻辑"""
        backend = session_mgr.get_backend(session_id)
        if not backend: return no_update
        
        # 参数提取
        common_keys_filter = common_keys_filter_values[0] if common_keys_filter_values else False
        algorithm_selector = algorithm_selector_values[0] if algorithm_selector_values else []
        
        ctx = callback_context
        if not ctx.triggered: return no_update
        
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        has_analyzer = backend._get_current_analyzer() is not None
        active_algorithms = backend.multi_algorithm_manager.get_active_algorithms() if backend.multi_algorithm_manager else []
        is_multi_mode = len(active_algorithms) > 1
        
        # 生成图表
        if not is_multi_mode and has_analyzer:
            if trigger_id != 'report-content': return no_update
            return backend.generate_key_delay_scatter_plot(only_common_keys=False, selected_algorithm_names=[])
        
        if is_multi_mode:
            return backend.generate_key_delay_scatter_plot(
                only_common_keys=bool(common_keys_filter),
                selected_algorithm_names=algorithm_selector or []
            )
        
        return no_update
    
    # ==================== 锤速对比图回调 ====================
    
    @app.callback(
        Output({'type': 'scatter-plot', 'id': 'hammer-velocity-comparison-plot'}, 'figure'),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def callback_generate_hammer_velocity_comparison_plot(report_content, session_id):
        """处理锤速对比图自动生成 - 当报告内容更新时触发"""
        return velocity_comparison_handler.handle_generate_hammer_velocity_comparison_plot(report_content, session_id)
    
    
    # 注册按键-力度交互效应图回调
    register_key_force_interaction_callbacks(app, session_mgr)
    


# ==================== 按键-力度交互效应图相关处理 ====================

def register_key_force_interaction_callbacks(app, session_manager: SessionManager):
    """注册按键-力度交互效应图相关的回调函数 - 实现全部内联"""
    
    @app.callback(
        Output('key-force-interaction-key-selector', 'options'),
        [Input({'type': 'scatter-plot', 'id': 'key-force-interaction-plot'}, 'figure')],
        prevent_initial_call=False
    )
    def callback_update_key_selector_options(figure):
        """内联提取按键选项逻辑"""
        if not figure or 'data' not in figure: return []
        
        key_ids = set()
        for trace in figure['data']:
            customdata = trace.get('customdata')
            if customdata and isinstance(customdata, list) and len(customdata) > 0:
                try:
                    first_point = customdata[0]
                    if isinstance(first_point, list) and len(first_point) >= 3:
                        key_ids.add(int(first_point[2]))
                except (IndexError, TypeError, ValueError): pass
            
            meta = trace.get('meta')
            if meta and isinstance(meta, dict) and 'key_id' in meta:
                key_ids.add(meta['key_id'])
        
        return [{'label': f'按键 {kid}', 'value': kid} for kid in sorted(key_ids)]
    
    @app.callback(
        Output('key-force-interaction-selected-keys', 'data'),
        [Input('key-force-interaction-key-selector', 'value')],
        prevent_initial_call=True
    )
    def callback_update_selected_keys_from_dropdown(selected_key):
        return [selected_key] if selected_key is not None else []
    
    @app.callback(
        Output({'type': 'scatter-plot', 'id': 'key-force-interaction-plot'}, 'figure'),
        [Input('report-content', 'children'),
         Input('key-force-interaction-selected-keys', 'data')],
        [State('session-id', 'data'),
         State({'type': 'scatter-plot', 'id': 'key-force-interaction-plot'}, 'figure')],
        prevent_initial_call=True
    )
    def callback_handle_generate_key_force_interaction_plot(report_content, selected_keys, session_id, current_figure):
        """直接实现交互效应图生成与可见性过滤"""
        backend = session_manager.get_backend(session_id)
        if not backend: return no_update
        
        ctx = callback_context
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else 'report-content'
        
        # 1. 获取图表
        if trigger_id == 'report-content':
            active_algorithms = backend.get_active_algorithms()
            if not active_algorithms: return backend.plot_generator._create_empty_plot("没有激活的算法")
            fig = backend.generate_key_force_interaction_plot()
        else:
            if not current_figure: return no_update
            fig = go.Figure(current_figure)
            if fig.data and isinstance(fig.data[0], dict):
                fig.data = [go.Scattergl(t) if t.get('type') == 'scatter' else t for t in fig.data]

        # 2. 过滤可见性 (内联逻辑)
        selected_keys = selected_keys or []
        for trace in fig.data:
            key_id = None
            if hasattr(trace, 'customdata') and trace.customdata:
                try:
                    if len(trace.customdata[0]) >= 3: key_id = int(trace.customdata[0][2])
                except Exception: pass
            if key_id is None and hasattr(trace, 'meta') and isinstance(trace.meta, dict):
                key_id = trace.meta.get('key_id')

            is_legend = getattr(trace, 'showlegend', False) and getattr(trace, 'legendgroup', '').startswith('algorithm_')
            trace.visible = True if (is_legend or not selected_keys or key_id in selected_keys) else 'legendonly'
        
        return fig
