"""
回调函数模块 - 处理Dash应用的所有回调逻辑
包含文件上传、历史记录表格交互等回调函数
"""
import json
import time
import traceback
import uuid
import math

from typing import Dict, Optional, Union, TypedDict, Tuple, List, Any
from collections import defaultdict

import pandas as pd
import numpy as np

# SPMID导入
from spmid.spmid_analyzer import SPMIDAnalyzer
import spmid



from dash import html, no_update
from dash._callback import NoUpdate
            
import dash
import dash.dependencies
import dash.dcc as dcc
import dash_bootstrap_components as dbc
from dash import Input, Output, State, ALL, callback_context, dcc, dash_table
from dash._callback_context import CallbackContext
from datetime import datetime

import plotly.graph_objects as go
from plotly.graph_objects import Figure
from plotly.subplots import make_subplots

from scipy import stats
from ui.layout_components import empty_figure, create_multi_algorithm_upload_area, create_multi_algorithm_management_area
from backend.session_manager import SessionManager
from utils.ui_helpers import create_empty_figure
from ui.delay_time_series_handler import DelayTimeSeriesHandler
from ui.relative_delay_distribution_handler import RelativeDelayDistributionHandler
from ui.delay_value_click_handler import DelayValueClickHandler
from ui.duration_diff_click_handler import DurationDiffClickHandler
from grade_detail_callbacks import register_all_callbacks
from utils.logger import Logger
# 后端类型导入
from backend.piano_analysis_backend import PianoAnalysisBackend



logger = Logger.get_logger()

# 自定义类型定义

class AlgorithmMetadata:
    """算法元数据的类型定义"""
    algorithm_name: str
    display_name: str
    filename: str

class OffsetAlignmentDataItem(TypedDict):
    """偏移对齐数据项的类型定义"""
    record_index: int
    replay_index: int
    key_id: int
    record_keyon: float
    replay_keyon: float
    keyon_offset: float
    record_keyoff: float
    replay_keyoff: float
    duration_offset: float
    average_offset: float
    record_duration: float
    replay_duration: float
    duration_diff: float

class OffsetAlignmentTableItem(TypedDict):
    """偏移对齐表格数据项的类型定义"""
    algorithm_name: str
    key_id: Union[int, str]
    count: int
    median: Union[float, str]
    mean: Union[float, str]
    std: Union[float, str]
    variance: Union[float, str]
    min: Union[float, str]
    max: Union[float, str]
    range: Union[float, str]
    status: str

class SPMIDNote:
    """SPMID音符对象的类型定义"""
    id: int
    hammers: pd.Series  # 锤击数据，pandas Series对象，索引为时间戳

class AlgorithmInstance:
    """算法实例的类型定义"""
    metadata: AlgorithmMetadata
    analyzer: Optional[SPMIDAnalyzer]  # SPMID分析器实例

    def is_ready(self) -> bool:
        """检查算法是否就绪"""
        pass

# 状态字典类型定义
class StateDict(TypedDict, total=False):
    """状态字典类型定义"""
    has_upload: bool
    upload_content: Optional[str]
    filename: Optional[str]
    has_history: bool
    history_id: Optional[str]
    last_upload_content: Optional[str]
    last_history_id: Optional[str]

# 文件上传结果数据类型定义
class UploadResultData(TypedDict):
    """文件上传成功时的结果数据字典"""
    filename: str
    record_count: int
    replay_count: int
    history_id: str


def _create_history_basic_info_content(result_data):
    """创建历史记录基本信息内容"""
    main_record = result_data['main_record']
    record_id = main_record[0] if len(main_record) > 0 else '未知'
    upload_time = main_record[2] if len(main_record) > 2 else '未知'
    
    return html.Div([
        html.H4("📋 历史记录基本信息", className="text-center"),
        html.P(f"文件名: {result_data['filename']}", className="text-center"),
        html.P(f"创建时间: {upload_time}", className="text-center"),
        html.P(f"记录ID: {record_id}", className="text-center"),
        html.P("⚠️ 该历史记录没有保存文件内容，无法重新分析", className="text-center text-warning")
    ])


def _create_error_content(title, message):
    """创建错误内容"""
    return html.Div([
        html.H4(f"❌ {title}", className="text-center text-danger"),
        html.P(message, className="text-center"),
        html.P("请检查数据或联系管理员", className="text-center text-muted")
    ])
    
def register_callbacks(app, session_manager: SessionManager, history_manager):
    """
    注册所有回调函数
    
    注意：多页面重构后，只注册核心回调：
    - 会话管理
    - 文件上传
    - 算法管理
    
    散点图等详细分析回调将在各自页面中实现
    """

    # 导入回调模块
    from ui.session_callbacks import register_session_callbacks
    from ui.file_upload_callbacks import register_file_upload_callbacks
    from ui.algorithm_callbacks import register_algorithm_callbacks
    from ui.track_comparison_callbacks import register_callbacks as register_track_comparison_callbacks
    # from ui.scatter_callbacks import register_scatter_callbacks  # 暂时禁用，将在散点图页面重新实现

    # 注册会话和初始化管理回调
    register_session_callbacks(app, session_manager, history_manager)
    
    # 注册音轨对比回调
    register_track_comparison_callbacks(app, session_manager)

    # 注册文件上传回调
    register_file_upload_callbacks(app, session_manager)

    # 注册算法管理回调
    register_algorithm_callbacks(app, session_manager)

    # 注册评级详情核心回调 (包含按键筛选、对比模态框、跳转跳转等)
    register_all_callbacks(app, session_manager)

    # 注册散点图回调 - 暂时禁用
    # register_scatter_callbacks(app, session_manager)

    # 多页面架构：禁用所有依赖旧UI的内联回调
    # 这些回调都引用了 main-plot, report-content 等旧组件
    # 新架构中，功能将在各自的页面中重新实现
    return

    # ==================== 以下是旧架构的内联回调（已禁用） ====================

    # 创建延时时间序列图处理器实例
    delay_time_series_handler = DelayTimeSeriesHandler(session_manager)

    # 创建相对延时分布图处理器实例
    relative_delay_distribution_handler = RelativeDelayDistributionHandler(session_manager)

    # 创建延迟值点击处理器实例
    delay_value_click_handler = DelayValueClickHandler(session_manager)

    # TODO
    # 偏移对齐分析 - 页面加载时自动生成
    @app.callback(
        Output('offset-alignment-plot', 'children', allow_duplicate=True),
        Output('offset-alignment-table', 'data', allow_duplicate=True),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def auto_generate_alignment_on_load(report_content, session_id):
        """报告内容加载时，自动生成偏移对齐柱状图与表格"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update, no_update
        
        try:
            # 检查是否有激活的算法
            active_algorithms = backend.get_active_algorithms()
            if not active_algorithms:
                logger.debug("[DEBUG] 没有激活的算法，跳过偏移对齐分析生成")
                empty = backend.plot_generator._create_empty_plot("没有激活的算法")
                return [dcc.Graph(figure=empty)], []
            
            result = backend.generate_offset_alignment_plot()
            # 获取第一个激活算法的按键统计表格数据
            table_data = active_algorithms[0].get_key_statistics_table_data() if active_algorithms else []
            
            children = []
            if isinstance(result, list):
                # 多图模式：返回多个独立的图表
                for item in result:
                    fig = item.get('figure')
                    
                    # 创建单个图表的容器
                    children.append(html.Div([
                        dcc.Graph(
                            figure=fig,
                            style={'height': '500px'},
                            config={'displayModeBar': True}
                        )
                    ], className="mb-4", style={'border': '1px solid #eee', 'padding': '10px', 'borderRadius': '5px', 'backgroundColor': 'white', 'boxShadow': '0 1px 3px rgba(0,0,0,0.1)'}))
            else:
                # 单图模式 (Legacy)：返回单个图表
                children.append(dcc.Graph(
                    figure=result,
                    style={'height': '800px'}
                ))
            
            logger.info("[OK] 偏移对齐分析（自动）生成成功")
            return children, table_data
            
        except Exception as e:
            logger.error(f"[ERROR] 自动生成偏移对齐分析失败: {e}")
            logger.error(traceback.format_exc())
            empty = backend.plot_generator._create_empty_plot(f"生成失败: {str(e)}")
            return [dcc.Graph(figure=empty)], no_update

    # 更新按键与相对延时散点图的曲子选择器选项
    @app.callback(
        [Output({'type': 'key-delay-scatter-algorithm-selector', 'index': ALL}, 'options'),
         Output({'type': 'key-delay-scatter-algorithm-selector', 'index': ALL}, 'value')],
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def update_key_delay_scatter_algorithm_selector(report_content, session_id):
        backend = session_manager.get_backend(session_id)
        if not backend or not hasattr(backend, 'multi_algorithm_manager'):
            return [], []
            
        try:
            active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()
            if not active_algorithms:
                return [], []
            
            options = []
            values = []
            for alg in active_algorithms:
                unique_name = alg.metadata.algorithm_name  # unique_algorithm_name
                display_name = alg.metadata.display_name    # 用户输入的算法名
                filename = alg.metadata.filename            # 原始文件名

                # 创建更具描述性的标签：算法名 (文件名)
                # 例如：pid (11-21-音阶测试pid.spmid)
                descriptive_label = f"{display_name} ({filename})"
                options.append({'label': descriptive_label, 'value': unique_name})
                values.append(unique_name)
            
            # 返回列表以匹配 Pattern Matching Output
            return [options], [values]
            
        except Exception as e:
            logger.error(f"[ERROR] 更新曲子选择器失败: {e}")
            return [], []

    def _validate_multi_algorithm_analysis(backend):
        """验证多算法模式并获取分析结果"""
        # 使用统一的模式检查方法
        mode, algorithm_count = backend.get_current_analysis_mode()

        if mode != "multi":
            logger.warning(f"[WARNING] 当前为{mode}模式，无法生成相对延时分布图（需要多算法模式）")
            return None, html.Div([
                dbc.Alert("需要多算法模式才能生成相对延时分布图", color="warning")
            ])

        # 获取分析结果
        analysis_result = backend.get_same_algorithm_relative_delay_analysis()
        if analysis_result.get('status') != 'success':
            return None, html.Div([
                dbc.Alert(analysis_result.get('message', '分析失败'), color="danger")
            ])

        algorithm_groups = analysis_result.get('algorithm_groups', {})
        if not algorithm_groups:
            return None, html.Div([
                dbc.Alert("没有算法组数据", color="warning")
            ])

        return analysis_result, None

    def _collect_songs_data(algorithm_groups):
        """收集所有需要绘制的曲子信息"""
        all_songs = []
        for display_name, group_data in algorithm_groups.items():
            song_data = group_data.get('song_data', [])
            group_relative_delays = group_data.get('relative_delays', [])

            if not group_relative_delays:
                continue

            # 添加每个曲子
            for song_info in song_data:
                song_relative_delays = song_info.get('relative_delays', [])
                if song_relative_delays:
                    filename_display = song_info.get('filename_display', song_info.get('filename', '未知文件'))
                    all_songs.append((display_name, filename_display, song_relative_delays, None, song_info))


        return all_songs


    def _create_subplot_figure(subplot_idx, display_name, filename_display, delays_array, base_color):
        """为单个子图创建图表"""
        # 生成子图标题
        subplot_title = f'{display_name} - {filename_display}'

        # 计算直方图数据
        hist, bin_edges = np.histogram(delays_array, bins=50, density=False)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

        # 为每个bin创建customdata
        customdata_list = []
        for i, bin_center in enumerate(bin_centers):
            bin_left = bin_edges[i]
            bin_right = bin_edges[i + 1]
            customdata_list.append([
                subplot_idx,
                display_name,
                filename_display,
                bin_center,
                bin_left,
                bin_right
            ])

        # 计算密度曲线
        bin_width = bin_edges[1] - bin_edges[0]
        try:
            if len(delays_array) < 2 or np.std(delays_array) == 0:
                raise ValueError("Insufficient data or zero variance")
                
            kde = stats.gaussian_kde(delays_array)
            x_density = np.linspace(delays_array.min(), delays_array.max(), 200)
            # 修正：乘以bin_width
            y_density = kde(x_density) * len(delays_array) * bin_width
        except:
            # KDE计算失败（如数据点太少或全相同），不绘制曲线
            y_density = []
            x_density = []

        # 创建独立的图表
        fig = go.Figure()

        # 添加直方图
        fig.add_trace(
            go.Bar(
                x=bin_centers,
                y=hist,
                name='相对延时分布',
                marker=dict(
                    color=f'rgba({int(base_color[1:3], 16)}, {int(base_color[3:5], 16)}, {int(base_color[5:7], 16)}, 0.6)',
                    line=dict(color=base_color, width=1)
                ),
                opacity=0.7,
                showlegend=False,
                hovertemplate=f'相对延时: %{{x:.2f}} ms<br>频数: %{{y}}<extra></extra>',
                customdata=customdata_list
            )
        )

        # 添加密度曲线
        fig.add_trace(
            go.Scattergl(
                x=x_density,
                y=y_density,
                mode='lines',
                name='密度曲线',
                line=dict(
                    color=base_color,
                    width=2,
                    dash='solid'
                ),
                showlegend=False,
                hovertemplate=f'相对延时: %{{x:.2f}} ms<br>密度: %{{y:.2f}}<extra></extra>'
            )
        )

        # 计算统计量
        mean = np.mean(delays_array)
        std = np.std(delays_array)
        median = np.median(delays_array)

        # 添加±1σ、±2σ、±3σ区间
        for sigma, color in [(1, 'rgba(255, 0, 0, 0.08)'), (2, 'rgba(255, 0, 0, 0.12)'), (3, 'rgba(255, 0, 0, 0.15)')]:
            fig.add_vrect(
                x0=mean - sigma * std,
                x1=mean + sigma * std,
                fillcolor=color,
                layer="below",
                line_width=0
            )

        # 添加均值线
        fig.add_vline(
            x=mean,
            line_dash="dash",
            line_color="green",
            line_width=1.5
        )

        # 添加中位数线
        fig.add_vline(
            x=median,
            line_dash="dot",
            line_color="orange",
            line_width=1.5
        )

        # 更新布局
        fig.update_layout(
            title=subplot_title,
            xaxis_title='相对延时 (ms)',
            yaxis_title='频数',
            height=500,
            template='plotly_white',
            showlegend=False
        )

        return fig


    def _create_subplot_container(subplot_idx, fig, display_name, filename_display):
        """创建完整的子图容器"""
        # 创建图表和表格容器（使用字典形式的ID以支持Pattern Matching Callbacks）
        plot_id = {'type': 'relative-delay-distribution-plot', 'index': subplot_idx}
        table_id = {'type': 'relative-delay-distribution-table', 'index': subplot_idx}
        title_id = {'type': 'relative-delay-distribution-title', 'index': subplot_idx}
        info_id = {'type': 'relative-delay-distribution-info', 'index': subplot_idx}
        container_id = {'type': 'relative-delay-distribution-container', 'index': subplot_idx}

        # 添加相对延时分布图
        plot_elements = [
            dcc.Graph(
                id=plot_id,
                figure=fig,
                style={'height': '500px'}
            )
        ]

        return html.Div([
            *plot_elements,
            html.P("💡 提示：点击直方图中的柱状图区域，可查看该相对延时范围内的数据点详情",
                   className="text-muted",
                   style={'fontSize': '12px', 'marginTop': '10px', 'marginBottom': '10px'}),
            html.Div([
                html.Div(id=title_id,
                        style={'marginTop': '15px', 'marginBottom': '10px',
                               'fontSize': '16px', 'fontWeight': 'bold',
                               'color': '#9c27b0', 'padding': '8px 12px',
                               'backgroundColor': '#f3e5f5', 'borderRadius': '4px',
                               'borderLeft': '4px solid #9c27b0', 'display': 'none'}),
                html.Div(id=info_id,
                        style={'marginBottom': '10px', 'fontSize': '14px', 'fontWeight': 'bold', 'color': '#2c3e50', 'display': 'none'}),
                dash_table.DataTable(
                    id=table_id,
                    columns=[
                        {"name": "算法名称", "id": "algorithm_name"},
                        {"name": "按键ID", "id": "key_id"},
                        {"name": "相对延时(ms)", "id": "relative_delay_ms", "type": "numeric", "format": {"specifier": ".2f"}},
                        {"name": "绝对延时(ms)", "id": "absolute_delay_ms", "type": "numeric", "format": {"specifier": ".2f"}},
                        {"name": "录制索引", "id": "record_index"},
                        {"name": "播放索引", "id": "replay_index"},
                        {"name": "录制开始(0.1ms)", "id": "record_keyon"},
                        {"name": "播放开始(0.1ms)", "id": "replay_keyon"},
                        {"name": "持续时间差(0.1ms)", "id": "duration_offset"},
                    ],
                    data=[],
                    page_action='none',
                    style_cell={
                        'textAlign': 'center',
                        'fontSize': '12px',
                        'fontFamily': 'Arial, sans-serif',
                        'padding': '8px',
                        'overflow': 'hidden',
                        'textOverflow': 'ellipsis',
                    },
                    style_header={
                        'backgroundColor': '#f8f9fa',
                        'fontWeight': 'bold',
                        'border': '1px solid #dee2e6',
                        'position': 'sticky',
                        'top': 0,
                        'zIndex': 1
                    },
                    style_data={
                        'whiteSpace': 'normal',
                        'height': 'auto',
                    },
                    style_table={
                        'overflowX': 'auto',
                        'overflowY': 'auto',
                        'maxHeight': '600px',
                    }
                )
            ], style={'display': 'none'}, id=container_id)
        ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'})

    # 锤速对比图控制面板回调
    @app.callback(
        Output('overall-hammer-velocity-comparison-plot', 'figure'),
        [Input('velocity-plot-legend-control', 'value')],
        [State('overall-hammer-velocity-comparison-plot', 'figure')],
        prevent_initial_call=True
    )
    def update_velocity_plot_visibility(selected_algorithms, current_figure):
        """根据控制面板的选择更新锤速对比图的可见性"""
        if not current_figure or not current_figure.data:
            return current_figure

        # 更新每个trace的可见性
        for i, trace in enumerate(current_figure.data):
            algorithm_filename = trace.name
            trace.visible = algorithm_filename in selected_algorithms

        return current_figure


    # 同种算法相对延时分布图回调 - 报告内容加载时自动生成
    @app.callback(
        Output('relative-delay-distribution-container', 'children'),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_generate_relative_delay_distribution_plot(report_content, session_id):
        """处理同种算法相对延时分布图自动生成 - 当报告内容更新时触发，为每个子图创建独立的图表和表格区域"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update

        try:
            # 验证多算法模式和获取分析结果
            analysis_result, error_div = _validate_multi_algorithm_analysis(backend)
            if error_div:
                return error_div

            algorithm_groups = analysis_result.get('algorithm_groups', {})

            # 收集所有需要绘制的曲子信息
            all_songs = _collect_songs_data(algorithm_groups)

            if not all_songs:
                return html.Div([
                    dbc.Alert("没有有效的相对延时数据", color="warning")
                ])
            
            # 生成整体锤速对比图
            # 为每个子图创建独立的图表和表格区域
            children = []
            algorithm_color_map = {}
            color_idx = 0

            # 使用全局算法颜色方案
            from utils.colors import ALGORITHM_COLOR_PALETTE
            colors = ALGORITHM_COLOR_PALETTE

            for subplot_idx, (display_name, filename_display, song_relative_delays, group_relative_delays, song_info) in enumerate(all_songs, 1):
                # 确定使用的数据
                delays_array = np.array(song_relative_delays)

                if len(delays_array) == 0:
                    continue

                # 获取或分配颜色
                if display_name not in algorithm_color_map:
                    algorithm_color_map[display_name] = colors[color_idx % len(colors)]
                    color_idx += 1
                base_color = algorithm_color_map[display_name]

                # 生成子图标题
                subplot_title = f'{display_name} - {filename_display}'

                # 创建子图图表
                fig = _create_subplot_figure(subplot_idx, display_name, filename_display, delays_array, base_color)

                # 创建完整的子图容器（只包含延时分布图）
                subplot_container = _create_subplot_container(subplot_idx, fig, display_name, filename_display)
                children.append(subplot_container)
            
            logger.info("[OK] 同种算法相对延时分布图生成成功")
            return children
            
        except Exception as e:
            logger.error(f"[ERROR] 生成相对延时分布图失败: {e}")
            logger.error(traceback.format_exc())
            return html.Div([
                dbc.Alert(f"生成失败: {str(e)}", color="danger")
            ])
    
    # 同种算法相对延时分布图点击回调 - 显示指定相对延时范围内的数据点详情
    # 使用Pattern Matching Callbacks处理动态生成的图表点击
    @app.callback(
        [Output({'type': 'relative-delay-distribution-table', 'index': dash.dependencies.MATCH}, 'data'),
         Output({'type': 'relative-delay-distribution-table', 'index': dash.dependencies.MATCH}, 'style_table'),
         Output({'type': 'relative-delay-distribution-info', 'index': dash.dependencies.MATCH}, 'children'),
         Output({'type': 'relative-delay-distribution-container', 'index': dash.dependencies.MATCH}, 'style'),
         Output({'type': 'relative-delay-distribution-title', 'index': dash.dependencies.MATCH}, 'children')],
        [Input({'type': 'relative-delay-distribution-plot', 'index': dash.dependencies.MATCH}, 'clickData')],
        [State('session-id', 'data'),
         State({'type': 'relative-delay-distribution-plot', 'index': dash.dependencies.MATCH}, 'id')],
        prevent_initial_call=True
    )
    def handle_relative_delay_distribution_click(click_data, session_id, plot_id):
        """处理同种算法相对延时分布图点击事件，显示该相对延时范围内的数据点详情"""
        return relative_delay_distribution_handler.handle_click(click_data, session_id, plot_id)
    
    def _find_algorithm_by_indices(algorithms, record_index, replay_index, log_prefix=""):
        """[Helper] 在算法列表中通过匹配对索引查找算法实例"""
        for alg in algorithms:
            if alg.analyzer and hasattr(alg.analyzer, 'matched_pairs'):
                for r_idx, p_idx, _, _ in alg.analyzer.matched_pairs:
                    if r_idx == record_index and p_idx == replay_index:
                        logger.info(f"{log_prefix} 通过匹配对找到算法实例: {alg.metadata.algorithm_name}")
                        return alg
        return None
    
    def _find_target_algorithm_instance(backend, algorithm_name, record_index, replay_index):
        """[Helper] 在多算法模式下查找目标算法实例"""
        if not backend.multi_algorithm_manager:
            return None
            
        all_algorithms = backend.multi_algorithm_manager.get_all_algorithms()
        
        # 1. 首先尝试精确匹配算法名称
        candidate_algorithms = [alg for alg in all_algorithms if alg.metadata.algorithm_name == algorithm_name]
        logger.info(f"🔍 找到 {len(candidate_algorithms)} 个匹配算法名称的算法实例: {algorithm_name}")
        
        # 2. 在候选算法中通过匹配对查找
        if candidate_algorithms:
            target_alg = _find_algorithm_by_indices(
                candidate_algorithms, record_index, replay_index,
                "[OK] 在候选算法中"
            )
            if target_alg:
                return target_alg

            # 如果只有一个候选但未找到匹配对，则勉强使用
            if len(candidate_algorithms) == 1:
                logger.warning(f"[WARNING] 只有一个候选算法但未找到明确匹配对，尝试使用: {algorithm_name}")
                return candidate_algorithms[0]

        # 3. 如果精确匹配失败，在所有算法中全局查找
        logger.info(f"[WARNING] 算法名称匹配失败，尝试全局查找")
        return _find_algorithm_by_indices(
            all_algorithms, record_index, replay_index,
            "[OK] 全局查找"
        )

    def _get_notes_and_center_time(target_algorithm, record_index, replay_index, key_id):
        """[Helper] 获取录制/播放音符对象及中心时间"""
        if not target_algorithm or not target_algorithm.analyzer:
            return None, None, None

        # 从 matched_pairs 获取匹配的音符对
        matched_pairs = getattr(target_algorithm.analyzer, 'matched_pairs', [])
        
        for r_idx, p_idx, r_note, p_note in matched_pairs:
            if r_idx == record_index and p_idx == replay_index:
                # 如果指定了key_id，进行额外验证
                if key_id is not None and r_note.id != key_id:
                    continue
                        
            # 计算中心时间（keyon时间）
            r_offset = r_note.after_touch.index[0] + r_note.offset if hasattr(r_note, 'after_touch') and not r_note.after_touch.empty else r_note.offset
            p_offset = p_note.after_touch.index[0] + p_note.offset if hasattr(p_note, 'after_touch') and not p_note.after_touch.empty else p_note.offset
            center_time_ms = ((r_offset + p_offset) / 2.0) / 10.0

        return r_note, p_note, center_time_ms

        # 如果在 matched_pairs 中找不到匹配的音符对，直接返回None
        return None, None, None
    
    # 同种算法相对延时分布图详情表格点击回调 - 显示录制与播放对比曲线
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True)],
        [Input({'type': 'relative-delay-distribution-table', 'index': dash.dependencies.ALL}, 'active_cell'),
         Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State({'type': 'relative-delay-distribution-table', 'index': dash.dependencies.ALL}, 'data'),
         State('session-id', 'data'),
         State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_relative_delay_distribution_table_click(active_cells, close_modal_clicks, close_btn_clicks, table_data_list, session_id, current_style):
        """处理同种算法相对延时分布图详情表格点击，显示录制与播放对比曲线（悬浮窗）"""
        return relative_delay_distribution_handler.handle_table_click(
            active_cells, close_modal_clicks, close_btn_clicks,
            table_data_list, session_id, current_style
        )

    # 延时时间序列图回调 - 报告内容加载时自动生成
    @app.callback(
        [Output('raw-delay-time-series-plot', 'figure'),
         Output('relative-delay-time-series-plot', 'figure')],
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_generate_delay_time_series(report_content, session_id):
        """处理延时时间序列图自动生成 - 当报告内容更新时触发"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return [no_update, no_update]

        try:
            # 检查是否在多算法模式
            # 检查是否有激活的算法
            active_algorithms = backend.get_active_algorithms()
            if not active_algorithms:
                logger.debug("[DEBUG] 没有激活的算法，跳过延时时间序列图生成")
                empty_plot = backend.plot_generator._create_empty_plot("没有激活的算法")
                return [empty_plot, empty_plot]

            result = backend.generate_delay_time_series_plot()

            # 检查返回的是否是字典（两个图表）还是单个图表
            if isinstance(result, dict) and 'raw_delay_plot' in result and 'relative_delay_plot' in result:
                logger.info("[OK] 延时时间序列图生成成功（分离模式）")
                return [result['raw_delay_plot'], result['relative_delay_plot']]
            else:
                # 单算法模式 - 两个图表都显示相同的内容
                logger.info("[OK] 延时时间序列图生成成功（单算法模式）")
                return [result, result]

        except Exception as e:
            logger.error(f"[ERROR] 生成延时时间序列图失败: {e}")
            logger.error(traceback.format_exc())
            empty_plot = backend.plot_generator._create_empty_plot(f"生成时间序列图失败: {str(e)}")
            return [empty_plot, empty_plot]
    
    # 延时时间序列图点击回调 - 只处理关闭按钮（单算法模式）
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True)],
        [Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_delay_time_series_click(close_modal_clicks, close_btn_clicks, current_style):
        """处理延时时间序列图点击，显示音符分析曲线（悬浮窗）"""
        """处理延时时间序列图模态框的关闭按钮（单算法模式）"""
        logger.info("[START] handle_delay_time_series_click 关闭按钮回调被触发")

        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            return current_style, [], no_update

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        logger.info(f"🔍 触发ID: {trigger_id}")

        # 如果点击了关闭按钮，隐藏模态框
        if trigger_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
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
            return modal_style, [], no_update

        return current_style, [], no_update
                    
    # 延时时间序列图点击回调 - 多算法模式（监听所有时间序列图）
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True),
         Output('raw-delay-time-series-plot', 'clickData', allow_duplicate=True),
         Output('relative-delay-time-series-plot', 'clickData', allow_duplicate=True)],
        [Input('raw-delay-time-series-plot', 'clickData'),
         Input('relative-delay-time-series-plot', 'clickData'),
         Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State('session-id', 'data'),
         State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_delay_time_series_click_multi(raw_click_data, relative_click_data, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理延时时间序列图点击（多算法模式），显示音符分析曲线（悬浮窗）"""
        return delay_time_series_handler.handle_delay_time_series_click_multi(
            raw_click_data, relative_click_data, close_modal_clicks, close_btn_clicks, session_id, current_style
        )

    # 最大/最小延迟字段点击回调 - 显示对应按键的曲线对比图
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True)],
        [Input({'type': 'max-delay-value', 'algorithm': dash.ALL}, 'n_clicks'),
         Input({'type': 'min-delay-value', 'algorithm': dash.ALL}, 'n_clicks'),
         Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State({'type': 'max-delay-value', 'algorithm': dash.ALL}, 'id'),
         State({'type': 'min-delay-value', 'algorithm': dash.ALL}, 'id'),
         State('session-id', 'data'),
         State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_delay_value_click(max_clicks_list, min_clicks_list, close_modal_clicks, close_btn_clicks, 
                                  max_ids_list, min_ids_list, session_id, current_style):
        """处理最大/最小延迟字段点击，显示对应按键的曲线对比图"""
        return delay_value_click_handler.handle_delay_value_click(
            max_clicks_list, min_clicks_list, close_modal_clicks, close_btn_clicks,
            max_ids_list, min_ids_list, session_id, current_style
        )
    
    # 延时分布直方图回调 - 报告内容加载时自动生成
    @app.callback(
        Output('delay-histogram-plot', 'figure'),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_generate_delay_histogram(report_content, session_id):
        """处理延时直方图自动生成 - 当报告内容更新时触发"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update
        
        try:
            # 检查是否在多算法模式
            # 检查是否有激活的算法
            active_algorithms = backend.get_active_algorithms()
            if not active_algorithms:
                logger.debug("[DEBUG] 没有激活的算法，跳过延时直方图生成")
                return backend.plot_generator._create_empty_plot("没有激活的算法")
            
            fig = backend.generate_delay_histogram_plot()
            logger.info("[OK] 延时直方图生成成功")
            return fig
        except Exception as e:
            logger.error(f"[ERROR] 生成延时直方图失败: {e}")
            logger.error(traceback.format_exc())
            return backend.plot_generator._create_empty_plot(f"生成直方图失败: {str(e)}")

    # ==================== 多算法对比模式回调 ====================
    
    # 多算法模式初始化回调 - 在会话初始化时自动触发
    @app.callback(
        [Output('multi-algorithm-upload-area', 'style', allow_duplicate=True),
         Output('multi-algorithm-upload-area', 'children'),
         Output('multi-algorithm-management-area', 'style', allow_duplicate=True),
         Output('multi-algorithm-management-area', 'children'),
         Output('main-plot', 'figure', allow_duplicate=True),
         Output('report-content', 'children', allow_duplicate=True)],
        [Input('session-id', 'data')],
        prevent_initial_call='initial_duplicate',
        prevent_duplicate=True
    )
    def initialize_multi_algorithm_mode(session_id):
        """初始化多算法模式 - 确保上传区域和管理区域显示"""
        logger.info(f"[PROCESS] 初始化多算法模式: session_id={session_id}")
        
        if not session_id:
            return no_update, no_update, no_update, no_update, no_update, no_update
        
        session_id, backend = session_manager.get_or_create_backend(session_id)
        if not backend:
            logger.warning("[WARNING] 无法获取backend实例")
            return no_update, no_update, no_update, no_update, no_update, no_update
        
        try:
            # 多算法模式始终启用（在初始化时已创建）
            has_existing_data = False
            existing_filename = None
            logger.info("[OK] 多算法模式已就绪")
            
            success = True
            if success:
                upload_style = {'display': 'block'}
                try:
                    upload_area = create_multi_algorithm_upload_area()
                    logger.info("[OK] 创建多算法上传区域成功")
                except Exception as e:
                    logger.error(f"[ERROR] 创建多算法上传区域失败: {e}")
                    upload_area = html.Div("上传区域创建失败", style={'color': '#dc3545'})
                
                management_style = {'display': 'block'}
                try:
                    management_area = create_multi_algorithm_management_area()
                    logger.info("[OK] 创建多算法管理区域成功")
                except Exception as e:
                    logger.error(f"[ERROR] 创建多算法管理区域失败: {e}")
                    management_area = html.Div("管理区域创建失败", style={'color': '#dc3545'})
            else:
                upload_style = {'display': 'block'}  # 即使失败也显示，让用户知道有问题
                upload_area = html.Div("多算法模式启用失败", style={'color': '#dc3545'})
                management_style = {'display': 'block'}
                management_area = html.Div("多算法模式启用失败", style={'color': '#dc3545'})
            
            # 检查是否有激活的算法，更新瀑布图
            plot_fig = no_update
            report_content = no_update
            
            active_algorithms = backend.get_active_algorithms()
            # 进一步检查：只有算法真正有数据（analyzer存在且有matched_pairs）才生成图形
            algorithms_with_data = []
            for alg in active_algorithms:
                if alg.analyzer and hasattr(alg.analyzer, 'matched_pairs') and alg.analyzer.matched_pairs:
                    algorithms_with_data.append(alg)
            
            if algorithms_with_data:
                try:
                    logger.info(f"[PROCESS] 更新瀑布图，共 {len(algorithms_with_data)} 个有数据的激活算法")
                    plot_fig = backend.generate_waterfall_plot()
                    # 报告内容已迁移到 pages/report.py，由其内部回调处理刷新
                    report_content = html.Div(id='report-update-signal', style={'display': 'none'})
                except Exception as e:
                    logger.error(f"[ERROR] 更新瀑布图失败: {e}")
                    plot_fig = create_empty_figure(f"更新失败: {str(e)}")
                    # 使用 create_report_layout 确保包含所有必需的组件
                    try:
                        report_content = html.Div(id='report-update-signal', style={'display': 'none'})
                    except:
                        # 错误情况下的备选方案
                        empty_fig = {}
                        report_content = html.Div([
                            html.H4("更新失败", className="text-center text-danger"),
                            html.P(f"错误信息: {str(e)}", className="text-center"),
                            # 包含所有必需的图表组件（隐藏），确保回调函数不会报错
                            dcc.Graph(id='key-delay-scatter-plot', figure=empty_fig, style={'display': 'none'}),
                            dcc.Graph(id='key-delay-zscore-scatter-plot', figure=empty_fig, style={'display': 'none'}),
                            dcc.Graph(id='hammer-velocity-delay-scatter-plot', figure=empty_fig, style={'display': 'none'}),
                            html.Div(id='offset-alignment-plot', style={'display': 'none'}),
                            html.Div([
                                dash_table.DataTable(
                                    id='offset-alignment-table',
                                    data=[],
                                    columns=[]
                                )
                            ], style={'display': 'none'})
                        ])
            else:
                # 没有激活的算法时，不调用 create_report_layout，直接返回空布局
                # 避免在没有数据时执行不必要的操作
                logger.info("[INFO] 没有激活的算法，跳过图形生成，返回空布局")
                empty_fig = {}
                report_content = html.Div([
                        html.H4("暂无数据", className="text-center text-muted"),
                        html.P("请至少激活一个算法以查看分析报告", className="text-center text-muted"),
                        # 包含所有必需的图表组件（隐藏），确保回调函数不会报错
                        dcc.Graph(id='key-delay-scatter-plot', figure=empty_fig, style={'display': 'none'}),
                        dcc.Graph(id='key-delay-zscore-scatter-plot', figure=empty_fig, style={'display': 'none'}),
                        dcc.Graph(id='hammer-velocity-delay-scatter-plot', figure=empty_fig, style={'display': 'none'}),
                        # key-hammer-velocity-scatter-plot 已删除（功能与按键-力度交互效应图重复）
                        dcc.Graph(id='key-force-interaction-plot', figure=empty_fig, style={'display': 'none'}),
                        dcc.Graph(id='relative-delay-distribution-plot', figure=empty_fig, style={'display': 'none'}),
                        html.Div(id='offset-alignment-plot', style={'display': 'none'}),
                        dcc.Graph(id='delay-time-series-plot', figure=empty_fig, style={'display': 'none'}),
                        dcc.Graph(id='delay-histogram-plot', figure=empty_fig, style={'display': 'none'}),
                        html.Div([
                            dash_table.DataTable(
                                id='offset-alignment-table',
                                data=[],
                                columns=[]
                            )
                        ], style={'display': 'none'}),
                        html.Div(id='delay-histogram-selection-info', style={'display': 'none'})
                        ])
            
            logger.info(f"[OK] 多算法模式初始化完成")
            return upload_style, upload_area, management_style, management_area, plot_fig, report_content
            
        except Exception as e:
            logger.error(f"[ERROR] 初始化多算法模式失败: {e}")
            logger.error(traceback.format_exc())
            return (
                {'display': 'block'}, 
                html.Div("初始化失败", style={'color': '#dc3545'}), 
                {'display': 'block'}, 
                html.Div("初始化失败", style={'color': '#dc3545'}), 
                no_update, 
                no_update
            )
    
    # 更新单键选择器的选项
    @app.callback(
        Output('single-key-selector', 'options'),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def update_single_key_selector_options(report_content, session_id):
        backend = session_manager.get_backend(session_id)
        if not backend or not hasattr(backend, 'multi_algorithm_manager'):
            return []
            
        try:
            active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()
            if not active_algorithms:
                return []
                
            all_keys = set()
            for alg in active_algorithms:
                if alg.analyzer and alg.analyzer.note_matcher:
                    offset_data = alg.analyzer.note_matcher.get_offset_alignment_data()
                    if offset_data:
                        for item in offset_data:
                            if item.get('key_id') is not None:
                                all_keys.add(item.get('key_id'))
                                
            sorted_keys = sorted(list(all_keys))
            return [{'label': f'Key {k}', 'value': k} for k in sorted_keys]
            
        except Exception as e:
            logger.error(f"[ERROR] 更新单键选择器失败: {e}")
            return []

    # 单键多曲延时对比图自动生成回调
    @app.callback(
        Output('single-key-delay-comparison-plot', 'figure'),
        [Input('single-key-selector', 'value'),
         Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_generate_single_key_comparison_plot(key_id, report_content, session_id):
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update

        if not key_id:
            # 返回空图表提示
            return {
                "layout": {
                    "xaxis": {"visible": False},
                    "yaxis": {"visible": False},
                    "annotations": [
                        {
                            "text": "请选择一个按键进行分析",
                            "xref": "paper",
                            "yref": "paper",
                            "showarrow": False,
                            "font": {"size": 20},
                            "x": 0.5,
                            "y": 0.5
                        }
                    ]
                }
            }
            
        try:
            fig = backend.generate_single_key_delay_comparison_plot(key_id)
            return fig
        except Exception as e:
            logger.error(f"[ERROR] 生成单键对比图失败: {e}")
            return backend.plot_generator._create_empty_plot(f"生成失败: {str(e)}")

    # 按键延时分析表格点击回调 - 显示按键曲线对比（悬浮窗）
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True)],
        [Input('offset-alignment-table', 'active_cell'),
         Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State('offset-alignment-table', 'data'),
         State('session-id', 'data'),
         State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_key_table_click(active_cell, close_modal_clicks, close_btn_clicks, table_data, session_id, current_style):
        """处理按键延时分析表格点击，显示按键曲线对比（悬浮窗）"""
        
        
        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            logger.debug("[WARNING] 按键表格点击回调：没有触发源")
            return current_style, [], no_update
        
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        logger.debug(f"[DEBUG] 按键表格点击回调触发：trigger_id={trigger_id}")
        
        # 如果点击了关闭按钮，隐藏模态框
        if trigger_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
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
            return modal_style, [], no_update
        
        # 如果是表格点击
        if trigger_id == 'offset-alignment-table':
            logger.info(f"[PROCESS] 表格点击：active_cell={active_cell}, table_data长度={len(table_data) if table_data else 0}")
            backend = session_manager.get_backend(session_id)
            if not backend:
                logger.warning("[WARNING] 没有找到backend")
                return current_style, [], no_update
            if not active_cell or not table_data:
                logger.warning("[WARNING] active_cell或table_data为空")
                return current_style, [], no_update
            
            try:
                # 获取点击的行数据
                row_idx = active_cell.get('row')
                if row_idx is None or row_idx >= len(table_data):
                    return current_style, [], no_update
                
                row_data = table_data[row_idx]
                algorithm_name = row_data.get('algorithm_name')
                key_id_str = row_data.get('key_id')
                
                # 跳过汇总行
                if key_id_str in ['总体', '汇总'] or not algorithm_name:
                    return current_style, [], no_update
                
                # 转换按键ID
                try:
                    key_id = int(key_id_str)
                except (ValueError, TypeError):
                    return current_style, [], no_update
                
                # 检查是否在多算法模式
                active_algorithms = backend.multi_algorithm_manager.get_active_algorithms() if backend.multi_algorithm_manager else []
                if len(active_algorithms) <= 1:
                    logger.info("[INFO] 不在多算法模式，不显示曲线对比图")
                    return current_style, [], no_update
                
                # 获取激活的算法列表
                active_algorithms = backend.get_active_algorithms()
                if len(active_algorithms) < 2:
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
                        html.P("需要至少2个激活的算法才能进行对比", className="text-muted text-center")
                    ])], no_update
                
                # 获取所有激活算法的匹配对
                algorithm_pairs_dict = {}
                all_timestamps = set()
                
                for alg in active_algorithms:
                    alg_name = alg.metadata.algorithm_name
                    pairs = backend.get_key_matched_pairs_by_algorithm(alg_name, key_id)
                    if pairs:
                        algorithm_pairs_dict[alg_name] = pairs
                        for _, _, _, _, timestamp in pairs:
                            all_timestamps.add(timestamp)
                
                if not algorithm_pairs_dict:
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
                        html.P(f"按键ID {key_id} 在所有激活算法中都没有匹配数据", className="text-muted text-center")
                    ])], no_update
                
                # 选择前两个有数据的算法进行对比
                alg_names = list(algorithm_pairs_dict.keys())[:2]
                if len(alg_names) < 2:
                    # 如果只有一个算法有数据，选择前两个激活的算法（即使第二个没有数据）
                    alg_names = [alg.metadata.algorithm_name for alg in active_algorithms[:2]]
                    if alg_names[0] not in algorithm_pairs_dict:
                        alg_names[0] = list(algorithm_pairs_dict.keys())[0]
                
                alg1_name = alg_names[0]
                alg2_name = alg_names[1]
                
                alg1_pairs = algorithm_pairs_dict.get(alg1_name, [])
                alg2_pairs = algorithm_pairs_dict.get(alg2_name, [])
                
                # 生成对比曲线图
                comparison_rows = []
                
                # 使用双指针按时间戳对齐
                # 注意：两个算法处理的是完全不同的SPMID文件，各自有独立的录制数据和播放数据
                # - 算法A：SPMID文件1的录制数据1 vs 播放数据1
                # - 算法B：SPMID文件2的录制数据2 vs 播放数据2
                # 它们之间没有任何关联，record_index和record_keyon都是各自文件内的
                # 步骤：
                # - 提取两个算法的时间戳序列（单位：0.1ms，record_keyon是各自文件内录制按键开始时间）
                # - 使用两个指针在合并时间线上前进，尽量将时间临近的配对，否则单侧显示
                ALIGN_WINDOW_01MS = 200  # 对齐窗口：200(0.1ms) = 20ms
                
                alg1_pairs_sorted = sorted(alg1_pairs, key=lambda p: p[4])
                alg2_pairs_sorted = sorted(alg2_pairs, key=lambda p: p[4])
                i, j = 0, 0
                while i < len(alg1_pairs_sorted) or j < len(alg2_pairs_sorted):
                    if i < len(alg1_pairs_sorted) and j < len(alg2_pairs_sorted):
                        t1 = alg1_pairs_sorted[i][4]
                        t2 = alg2_pairs_sorted[j][4]
                        diff = abs(t1 - t2)
                        if diff <= ALIGN_WINDOW_01MS:
                            # 配对显示
                            comparison_rows.append((alg1_pairs_sorted[i], alg2_pairs_sorted[j], t1, t2))
                            i += 1
                            j += 1
                        elif t1 < t2:
                            # 左侧单独显示
                            comparison_rows.append((alg1_pairs_sorted[i], None, t1, None))
                            i += 1
                        else:
                            # 右侧单独显示
                            comparison_rows.append((None, alg2_pairs_sorted[j], None, t2))
                            j += 1
                    elif i < len(alg1_pairs_sorted):
                        t1 = alg1_pairs_sorted[i][4]
                        comparison_rows.append((alg1_pairs_sorted[i], None, t1, None))
                        i += 1
                    else:
                        t2 = alg2_pairs_sorted[j][4]
                        comparison_rows.append((None, alg2_pairs_sorted[j], None, t2))
                        j += 1
                
                # 为每个对齐项创建对比图
                rendered_rows = []
                for alg1_pair, alg2_pair, t1, t2 in comparison_rows:
                    if not alg1_pair and not alg2_pair:
                        continue
                    
                    # 创建左右对比的子图，标题显示各自时间
                    # record_keyon：各自SPMID文件内录制按键开始时间（两个文件独立，时间戳无关联）
                    if alg1_pair and t1 is not None:
                        title1 = f"{alg1_name}<br>录制按键开始: {t1/10:.2f}ms"
                    else:
                        title1 = f"{alg1_name} (无数据)"
                    
                    if alg2_pair and t2 is not None:
                        title2 = f"{alg2_name}<br>录制按键开始: {t2/10:.2f}ms"
                    else:
                        title2 = f"{alg2_name} (无数据)"
                    
                    fig = make_subplots(
                        rows=1, cols=2,
                        subplot_titles=(title1, title2),
                        horizontal_spacing=0.15
                    )
                    
                    # 左侧：算法1的曲线
                    if alg1_pair:
                        _, _, record_note1, replay_note1, _ = alg1_pair
                        if record_note1 and hasattr(record_note1, 'after_touch') and not record_note1.after_touch.empty:
                            x_at = (record_note1.after_touch.index + record_note1.offset) / 10.0
                            y_at = record_note1.after_touch.values
                            fig.add_trace(go.Scattergl(x=x_at, y=y_at, mode='lines', name='录制触后', 
                                                    line=dict(color='blue', width=2), showlegend=False), row=1, col=1)
                        if record_note1 and hasattr(record_note1, 'hammers') and not record_note1.hammers.empty:
                            # 过滤锤速为0的锤击点
                            hammer_mask = record_note1.hammers.values > 0
                            if hammer_mask.any():
                                x_hm = (record_note1.hammers.index[hammer_mask] + record_note1.offset) / 10.0
                                y_hm = record_note1.hammers.values[hammer_mask]
                                fig.add_trace(go.Scattergl(x=x_hm, y=y_hm, mode='markers', name='录制锤子',
                                                        marker=dict(color='blue', size=6), showlegend=False), row=1, col=1)
                        if replay_note1 and hasattr(replay_note1, 'after_touch') and not replay_note1.after_touch.empty:
                            x_at = (replay_note1.after_touch.index + replay_note1.offset) / 10.0
                            y_at = replay_note1.after_touch.values
                            fig.add_trace(go.Scattergl(x=x_at, y=y_at, mode='lines', name='回放触后',
                                                    line=dict(color='red', width=2), showlegend=False), row=1, col=1)
                        if replay_note1 and hasattr(replay_note1, 'hammers') and not replay_note1.hammers.empty:
                            x_hm = (replay_note1.hammers.index + replay_note1.offset) / 10.0
                            y_hm = replay_note1.hammers.values
                            fig.add_trace(go.Scattergl(x=x_hm, y=y_hm, mode='markers', name='回放锤子',
                                                    marker=dict(color='red', size=6), showlegend=False), row=1, col=1)
                    
                    # 右侧：算法2的曲线
                    if alg2_pair:
                        _, _, record_note2, replay_note2, _ = alg2_pair
                        if record_note2 and hasattr(record_note2, 'after_touch') and not record_note2.after_touch.empty:
                            x_at = (record_note2.after_touch.index + record_note2.offset) / 10.0
                            y_at = record_note2.after_touch.values
                            fig.add_trace(go.Scattergl(x=x_at, y=y_at, mode='lines', name='录制触后',
                                                    line=dict(color='blue', width=2), showlegend=False), row=1, col=2)
                        if record_note2 and hasattr(record_note2, 'hammers') and not record_note2.hammers.empty:
                            # 过滤锤速为0的锤击点
                            hammer_mask = record_note2.hammers.values > 0
                            if hammer_mask.any():
                                x_hm = (record_note2.hammers.index[hammer_mask] + record_note2.offset) / 10.0
                                y_hm = record_note2.hammers.values[hammer_mask]
                                fig.add_trace(go.Scattergl(x=x_hm, y=y_hm, mode='markers', name='录制锤子',
                                                        marker=dict(color='blue', size=6), showlegend=False), row=1, col=2)
                        if replay_note2 and hasattr(replay_note2, 'after_touch') and not replay_note2.after_touch.empty:
                            x_at = (replay_note2.after_touch.index + replay_note2.offset) / 10.0
                            y_at = replay_note2.after_touch.values
                            fig.add_trace(go.Scattergl(x=x_at, y=y_at, mode='lines', name='回放触后',
                                                    line=dict(color='red', width=2), showlegend=False), row=1, col=2)
                        if replay_note2 and hasattr(replay_note2, 'hammers') and not replay_note2.hammers.empty:
                            x_hm = (replay_note2.hammers.index + replay_note2.offset) / 10.0
                            y_hm = replay_note2.hammers.values
                            fig.add_trace(go.Scattergl(x=x_hm, y=y_hm, mode='markers', name='回放锤子',
                                                    marker=dict(color='red', size=6), showlegend=False), row=1, col=2)
                    
                    # 主标题
                    title_text = f"按键ID {key_id} 曲线对比"
                    
                    fig.update_layout(
                        title=title_text,
                        height=400,
                        showlegend=False
                    )
                    fig.update_xaxes(title_text="时间 (ms)", row=1, col=1)
                    fig.update_xaxes(title_text="时间 (ms)", row=1, col=2)
                    fig.update_yaxes(title_text="值", row=1, col=1)
                    fig.update_yaxes(title_text="值", row=1, col=2)
                    
                    rendered_rows.append(
                        dbc.Row([
                            dbc.Col([
                                dcc.Graph(figure=fig, style={'height': '400px'})
                            ], width=12)
                        ], className="mb-3")
                    )
                
                if not rendered_rows:
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
                        html.P(f"按键ID {key_id} 没有可显示的对比数据", className="text-muted text-center")
                    ])], no_update
                
                # 计算时间信息，用于跳转时直接使用
                center_time_ms = None
                record_idx = None
                replay_idx = None
                first_algorithm_name = None
                
                try:
                    # 获取第一个匹配对用于跳转
                    if alg1_pairs:
                        first_pair = alg1_pairs[0]
                        record_idx, replay_idx, record_note, replay_note, _ = first_pair
                        first_algorithm_name = alg1_name
                        
                        if record_note and replay_note:
                            try:
                                # 计算keyon时间
                                record_keyon = record_note.after_touch.index[0] + record_note.offset if hasattr(record_note, 'after_touch') and not record_note.after_touch.empty else record_note.offset
                                replay_keyon = replay_note.after_touch.index[0] + replay_note.offset if hasattr(replay_note, 'after_touch') and not replay_note.after_touch.empty else replay_note.offset
                                center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0  # 转换为ms
                                logger.info(f"[OK] 计算得到center_time_ms: {center_time_ms}ms")
                            except Exception as e:
                                logger.warning(f"[WARNING] 计算时间信息失败: {e}")
                                # 备用方案：从 offset_data 获取
                                try:
                                    algorithm = backend.multi_algorithm_manager.get_algorithm(alg1_name)
                                    if algorithm and algorithm.analyzer and algorithm.analyzer.note_matcher:
                                        offset_data = algorithm.analyzer.note_matcher.get_offset_alignment_data()
                                        if offset_data:
                                            for item in offset_data:
                                                if item.get('record_index') == record_idx and item.get('replay_index') == replay_idx:
                                                    record_keyon = item.get('record_keyon', 0)
                                                    replay_keyon = item.get('replay_keyon', 0)
                                                    if record_keyon and replay_keyon:
                                                        center_time_ms = ((record_keyon + replay_keyon) / 2.0) / 10.0
                                                        logger.info(f"[OK] 从offset_data获取center_time_ms: {center_time_ms}ms")
                                                        break
                                except Exception as e2:
                                    logger.warning(f"[WARNING] 从offset_data获取时间信息失败: {e2}")
                except Exception as e:
                    logger.warning(f"[WARNING] 获取跳转信息失败: {e}")
                
                # 存储当前点击的数据点信息，用于跳转按钮
                point_info = {
                    'algorithm_name': first_algorithm_name,
                    'record_idx': record_idx,
                    'replay_idx': replay_idx,
                    'key_id': key_id,
                    'source_plot_id': 'offset-alignment-table',  # 记录来源表格ID
                    'center_time_ms': center_time_ms  # 预先计算的时间信息
                }
                
                # 显示模态框
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
                
                return modal_style, rendered_rows, point_info
                
            except Exception as e:
                logger.error(f"[ERROR] 生成按键曲线对比失败: {e}")
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
                    html.P(f"生成对比图失败: {str(e)}", className="text-danger text-center")
                ])], no_update
        
        # 其他情况，保持当前状态
        return current_style, [], no_update

    # 按键曲线对比TAB切换回调 - 处理相似度分析
    @app.callback(
        [Output('similarity-loading-indicator', 'style'),
         Output('similarity-analysis-results', 'children')],
        Input('key-curves-comparison-tabs', 'value'),
        State('current-clicked-point-info', 'data'),
        State('session-id', 'data'),
        prevent_initial_call=True
    )
    def handle_key_curves_tab_switch(tab_value, clicked_point_info, session_id):
        """处理按键曲线对比TAB切换，执行相似度分析"""
        if tab_value != 'similarity-tab':
            return {'display': 'none'}, []

        # 显示加载指示器
        loading_style = {'display': 'block'}

        if not clicked_point_info:
            return loading_style, [html.Div("没有点击信息", className="text-muted text-center", style={'padding': '20px'})]

        backend = session_manager.get_backend(session_id)
        if not backend:
            return loading_style, [html.Div("无法获取后端服务", className="text-danger text-center", style={'padding': '20px'})]

        try:
            key_id = clicked_point_info.get('key_id')
            if key_id is None:
                return {'display': 'none'}, [html.Div("缺少按键ID信息", className="text-warning text-center", style={'padding': '20px'})]

            # 执行相似度分析
            result = backend.analyze_curve_similarity(key_id)

            if result.get('status') != 'success':
                error_msg = result.get('error', '相似度分析失败')
                return {'display': 'none'}, [html.Div([
                    dbc.Alert([
                        html.I(className="fas fa-exclamation-triangle me-2"),
                        html.Strong("分析失败: "),
                        html.Span(error_msg)
                    ], color="danger")
                ])]

            # 构建相似度分析结果UI
            children = []

            # 基准信息
            reference_alg = result.get('reference_algorithm_display', '未知')
            children.append(html.Div([
                html.H6("相似度分析结果", className="mb-3", style={'color': '#2c3e50', 'fontWeight': 'bold'}),
                html.P([
                    html.Strong("基准录制曲线: "),
                    html.Span(f"{reference_alg} (按键ID: {key_id})", style={'color': '#007bff'})
                ], className="mb-3")
            ]))

            # 显示处理过程图表
            processing_stages = result.get('processing_stages', [])
            if processing_stages:
                children.append(html.Div([
                    html.H6("相似度分析处理过程", className="mb-3", style={'color': '#2c3e50', 'fontWeight': 'bold'})
                ]))

                for fig_info in processing_stages:
                    title = fig_info.get('title', '未知阶段')
                    fig = fig_info.get('figure')

                    if fig:
                        children.append(html.Div([
                            html.H6(title, className="mt-4 mb-2", style={'fontSize': '14px', 'fontWeight': 'bold', 'color': '#555'}),
                            dcc.Graph(
                                figure=fig,
                                config={'displayModeBar': True}
                            )
                        ], className="mb-3"))

            similarity_results = result.get('similarity_results', [])

            if not similarity_results:
                children.append(html.Div([
                    dbc.Alert([
                        html.I(className="fas fa-info-circle me-2"),
                        "没有找到可分析的播放曲线数据"
                    ], color="info")
                ]))
                return {'display': 'none'}, children

            # 相似度结果表格
            table_rows = []
            for i, alg_result in enumerate(similarity_results, 1):
                table_rows.append(html.Tr([
                    html.Td(str(i), style={'textAlign': 'center', 'width': '60px'}),
                    html.Td(alg_result['algorithm_display_name'], style={'fontWeight': 'bold'}),
                    html.Td(f"{alg_result['match_count']}", style={'textAlign': 'center'}),
                    html.Td([
                        html.Span(f"{alg_result['average_similarity']:.3f}",
                                 style={'fontWeight': 'bold', 'color': _get_similarity_color(alg_result['average_similarity'])})
                    ], style={'textAlign': 'center'}),
                    html.Td([
                        html.Button("详情",
                                   id={'type': 'similarity-detail-btn', 'index': f"{alg_result['algorithm_name']}_{key_id}"},
                                   className="btn btn-sm btn-outline-primary",
                                   style={'fontSize': '12px'})
                    ], style={'textAlign': 'center'})
                ]))

            children.append(html.Div([
                html.H6("各SPMID文件相似度排名", className="mb-3"),
                dbc.Table([
                    html.Thead(html.Tr([
                        html.Th("#", style={'width': '60px'}),
                        html.Th("SPMID文件"),
                        html.Th("匹配次数", style={'width': '100px'}),
                        html.Th("平均相似度", style={'width': '120px'}),
                        html.Th("操作", style={'width': '80px'})
                    ])),
                    html.Tbody(table_rows)
                ], bordered=True, hover=True, responsive=True, className="mb-3")
            ]))

            # 相似度分布图表
            if len(similarity_results) > 1:
                import plotly.graph_objects as go

                algorithms = [r['algorithm_display_name'] for r in similarity_results]
                similarities = [r['average_similarity'] for r in similarity_results]

                fig = go.Figure(data=[
                    go.Bar(
                        x=algorithms,
                        y=similarities,
                        marker_color=[_get_similarity_color(s) for s in similarities],
                        text=[f'{s:.3f}' for s in similarities],
                        textposition='auto'
                    )
                ])

                fig.update_layout(
                    title="各SPMID文件相似度对比",
                    xaxis_title="SPMID文件",
                    yaxis_title="相似度",
                    yaxis_range=[0, 1],
                    height=400
                )

                children.append(html.Div([
                    html.H6("相似度对比柱状图", className="mb-3"),
                    dcc.Graph(figure=fig, style={'height': '400px'})
                ]))

            return {'display': 'none'}, children

        except Exception as e:
            logger.error(f"[ERROR] 相似度分析回调失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {'display': 'none'}, [html.Div([
                dbc.Alert([
                    html.I(className="fas fa-exclamation-triangle me-2"),
                    html.Strong("分析过程中发生错误: "),
                    html.Span(str(e))
                ], color="danger")
            ])]

    def _get_similarity_color(similarity: float) -> str:
        """根据相似度值返回颜色"""
        if similarity >= 0.8:
            return '#28a745'  # 绿色 - 优秀
        elif similarity >= 0.6:
            return '#ffc107'  # 黄色 - 良好
        elif similarity >= 0.4:
            return '#fd7e14'  # 橙色 - 一般
        else:
            return '#dc3545'  # 红色 - 较差

    # 相似度详情模态框回调
    @app.callback(
        [Output('similarity-detail-modal', 'style'),
         Output('similarity-detail-content', 'children')],
        [Input({'type': 'similarity-detail-btn', 'index': ALL}, 'n_clicks'),
         Input('close-similarity-detail-modal', 'n_clicks'),
         Input('close-similarity-detail-modal-btn', 'n_clicks')],
        [State('session-id', 'data'),
         State('similarity-detail-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_similarity_detail_modal(detail_clicks, close_clicks, close_btn_clicks, session_id, current_style):
        """处理相似度详情模态框"""
        ctx = callback_context
        if not ctx.triggered:
            return current_style, []

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

        # 如果点击关闭按钮，隐藏模态框
        if trigger_id in ['close-similarity-detail-modal', 'close-similarity-detail-modal-btn']:
            modal_style = {
                'display': 'none',
                'position': 'fixed',
                'zIndex': '10000',
                'left': '0',
                'top': '0',
                'width': '100%',
                'height': '100%',
                'backgroundColor': 'rgba(0,0,0,0.7)',
                'backdropFilter': 'blur(5px)'
            }
            return modal_style, []

        # 如果点击详情按钮
        if 'similarity-detail-btn' in trigger_id:
            backend = session_manager.get_backend(session_id)
            if not backend:
                return current_style, [html.Div("无法获取后端服务", className="text-danger")]

            try:
                # 解析按钮ID，格式为: algorithm_name_key_id
                button_info = json.loads(trigger_id)
                button_index = button_info.get('index', '')
                parts = button_index.split('_', 1)
                if len(parts) != 2:
                    return current_style, [html.Div("无效的按钮索引", className="text-warning")]

                algorithm_name = parts[0]
                key_id_str = parts[1]

                try:
                    key_id = int(key_id_str)
                except ValueError:
                    return current_style, [html.Div("无效的按键ID", className="text-warning")]

                # 获取相似度分析结果
                full_result = backend.analyze_curve_similarity(key_id)

                if full_result.get('status') != 'success':
                    return current_style, [html.Div([
                        dbc.Alert(f"获取相似度数据失败: {full_result.get('error', '未知错误')}", color="danger")
                    ])]

                # 查找指定算法的结果
                similarity_results = full_result.get('similarity_results', [])
                target_result = None
                for result in similarity_results:
                    if result['algorithm_name'] == algorithm_name:
                        target_result = result
                        break

                if not target_result:
                    return current_style, [html.Div(f"未找到算法 {algorithm_name} 的相似度数据", className="text-warning")]

                # 构建详情内容
                children = []

                # 标题信息
                children.append(html.Div([
                    html.H5(f"{target_result['algorithm_display_name']} - 相似度详情", className="mb-3"),
                    html.P([
                        html.Strong("按键ID: "),
                        html.Span(str(key_id)),
                        html.Br(),
                        html.Strong("基准录制曲线: "),
                        html.Span(full_result.get('reference_algorithm_display', '未知')),
                        html.Br(),
                        html.Strong("平均相似度: "),
                        html.Span(f"{target_result['average_similarity']:.3f}",
                                 style={'color': _get_similarity_color(target_result['average_similarity']),
                                       'fontWeight': 'bold'})
                    ], className="mb-4")
                ]))

                # 详细相似度表格
                individual_similarities = target_result.get('individual_similarities', [])
                if individual_similarities:
                    table_rows = []
                    for i, sim in enumerate(individual_similarities, 1):
                        table_rows.append(html.Tr([
                            html.Td(str(i), style={'textAlign': 'center'}),
                            html.Td(f"{sim['timestamp']:.1f}ms", style={'textAlign': 'center'}),
                            html.Td([
                                html.Span(f"{sim['similarity']:.3f}",
                                         style={'color': _get_similarity_color(sim['similarity']),
                                               'fontWeight': 'bold'})
                            ], style={'textAlign': 'center'})
                        ]))

                    children.append(html.Div([
                        html.H6("各匹配对相似度详情", className="mb-3"),
                        dbc.Table([
                            html.Thead(html.Tr([
                                html.Th("#", style={'width': '60px'}),
                                html.Th("时间戳", style={'width': '120px'}),
                                html.Th("相似度")
                            ])),
                            html.Tbody(table_rows)
                        ], bordered=True, hover=True, responsive=True, className="mb-3")
                    ]))

                    # 相似度分布直方图
                    import plotly.graph_objects as go

                    similarities = [s['similarity'] for s in individual_similarities]

                    fig = go.Figure(data=[
                        go.Histogram(
                            x=similarities,
                            nbinsx=20,
                            marker_color='#1f77b4',
                            opacity=0.7
                        )
                    ])

                    fig.update_layout(
                        title="相似度分布",
                        xaxis_title="相似度",
                        yaxis_title="频次",
                        xaxis_range=[0, 1],
                        height=300
                    )

                    children.append(html.Div([
                        html.H6("相似度分布直方图", className="mb-3"),
                        dcc.Graph(figure=fig, style={'height': '300px'})
                    ]))

                # 显示模态框
                modal_style = {
                    'display': 'block',
                    'position': 'fixed',
                    'zIndex': '10000',
                    'left': '0',
                    'top': '0',
                    'width': '100%',
                    'height': '100%',
                    'backgroundColor': 'rgba(0,0,0,0.7)',
                    'backdropFilter': 'blur(5px)'
                }

                return modal_style, children

            except Exception as e:
                logger.error(f"[ERROR] 相似度详情模态框处理失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return current_style, [html.Div([
                    dbc.Alert(f"处理详情时发生错误: {str(e)}", color="danger")
                ])]

        # 其他情况，保持当前状态
        return current_style, []

    # 瀑布图点击回调 - 显示曲线对比（悬浮窗）
    @app.callback(
        [Output('waterfall-curves-modal', 'style'),
         Output('waterfall-curves-comparison-container', 'children')],
        [Input('main-plot', 'clickData'),
         Input('close-waterfall-curves-modal', 'n_clicks'),
         Input('close-waterfall-curves-modal-btn', 'n_clicks')],
        [State('session-id', 'data'),
         State('waterfall-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_waterfall_click(click_data, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理瀑布图点击，显示曲线对比（悬浮窗）"""
    
        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            print("[ERROR] 没有触发源")
            return current_style, []
        
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        print(f"🔍 触发ID: {trigger_id}")
        
        # 如果点击了关闭按钮，隐藏模态框
        if trigger_id in ['close-waterfall-curves-modal', 'close-waterfall-curves-modal-btn']:
            print("[OK] 关闭瀑布图曲线模态框")
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
            return modal_style, []
        
        # 如果是瀑布图点击
        if trigger_id == 'main-plot' and click_data:
            print("[TARGET] 检测到瀑布图点击！")
            
            backend = session_manager.get_backend(session_id)
            if not backend:
                print("[ERROR] backend为空")
                return current_style, []
            
            try:
                if 'points' not in click_data or len(click_data['points']) == 0:
                    print("[ERROR] clickData中没有points")
                    return current_style, []
                
                point = click_data['points'][0]
                
                # 优先从customdata获取信息，如果没有则从坐标获取
                algorithm_name = None
                key_id = None
                data_type = None
                index = None
                
                if point.get('customdata'):
                    # 有customdata：点击到了起始时间
                    raw_customdata = point['customdata']
                    customdata = raw_customdata[0] if isinstance(raw_customdata, list) and len(raw_customdata) > 0 and isinstance(raw_customdata[0], list) else raw_customdata
                else:
                    # 没有customdata，设置为空
                    customdata = None
                
                print(f"[DATA] customdata: {customdata}")

                if isinstance(customdata, list) and len(customdata) >= 7:
                    # 从customdata提取信息：[t_on/10, t_off/10, original_key_id, value, label, index, algorithm_name]
                    algorithm_name = customdata[6]
                    key_id = int(customdata[2])
                    data_type = customdata[4]  # 'record' 或 'play'
                    index = int(customdata[5])
                    print(f"[STATS] 从customdata提取: algorithm_name={algorithm_name}, key_id={key_id}, data_type={data_type}, index={index}")
                
                # 如果没有customdata，从点击坐标查找对应的音符
                if not algorithm_name or key_id is None or index is None:
                    # 获取点击的坐标
                    click_x = point.get('x')  # 时间（ms）
                    click_y = point.get('y')  # 按键ID
                    
                    if click_x is None or click_y is None:
                        print("[ERROR] 无法从坐标获取点击位置")
                        return current_style, []
                    
                    print(f"[LOCATION] 从坐标获取: x={click_x}ms, y={click_y}")
                    
                    # 在多算法模式下，需要根据y坐标判断是哪个算法
                    active_algorithms = backend.multi_algorithm_manager.get_active_algorithms() if backend.multi_algorithm_manager else []
                    if len(active_algorithms) > 1:
                        active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()
                        algorithm_y_range = 100  # 每个算法偏移100个单位
                        
                        # 根据y坐标找到对应的算法和实际按键ID
                        for alg_idx, alg in enumerate(active_algorithms):
                            alg_y_offset = alg_idx * algorithm_y_range
                            if alg_y_offset <= click_y < alg_y_offset + algorithm_y_range:
                                algorithm_name = alg.metadata.algorithm_name
                                key_id = int(click_y - alg_y_offset)
                                print(f"[OK] 找到算法: {algorithm_name}, 实际按键ID: {key_id}")
                                break
                    else:
                        # 单算法模式
                        key_id = int(click_y)
                        algorithm_name = None
                    
                    if not algorithm_name and len(active_algorithms) > 1:
                        print("[ERROR] 无法确定算法")
                        return current_style, []
                    
                    # 根据时间和按键ID查找对应的音符
                # 获取算法对象（multi_algorithm_manager 在初始化时已创建）
                    
                    if algorithm_name:
                        algorithm = backend.multi_algorithm_manager.get_algorithm(algorithm_name)
                    else:
                        # 单算法模式
                        algorithm = None
                        analyzer = backend._get_current_analyzer()
                        if analyzer:
                            # 使用offset_data查找
                            if analyzer.note_matcher:
                                offset_data = analyzer.note_matcher.get_offset_alignment_data()
                                if offset_data:
                                    # 查找时间范围内的音符
                                    click_time_01ms = click_x * 10  # 转换为0.1ms单位
                                    for item in offset_data:
                                        item_key_id = item.get('key_id')
                                        # 确保key_id类型一致
                                        try:
                                            item_key_id = int(item_key_id) if item_key_id is not None else None
                                        except (ValueError, TypeError):
                                            continue
                                        
                                        record_keyon = item.get('record_keyon', 0)
                                        record_keyoff = item.get('record_keyoff', 0)
                                        # 如果没有record_keyoff，使用record_keyon + record_duration
                                        if record_keyoff == 0:
                                            record_duration = item.get('record_duration', 0)
                                            record_keyoff = record_keyon + record_duration
                                        
                                        if item_key_id == key_id and record_keyon <= click_time_01ms <= record_keyoff:
                                            index = item.get('record_index')
                                            data_type = 'record'
                                            print(f"[OK] 单算法模式: 找到音符 index={index}, data_type={data_type}, 时间范围: {record_keyon/10:.1f}ms - {record_keyoff/10:.1f}ms, 点击时间: {click_time_01ms/10:.1f}ms")
                                            break
                            
                            # 如果在offset_data中没有找到，尝试从丢锤/多锤数据中查找
                            if key_id is not None and index is None:
                                print(f"[INFO] 单算法模式: 在offset_data中未找到，尝试从丢锤/多锤数据中查找")
                                
                                drop_hammers = getattr(analyzer, 'drop_hammers', [])
                                multi_hammers = getattr(analyzer, 'multi_hammers', [])
                                initial_valid_record_data = getattr(analyzer, 'initial_valid_record_data', [])
                                initial_valid_replay_data = getattr(analyzer, 'initial_valid_replay_data', [])
                                
                                click_time_01ms = click_x * 10  # 转换为0.1ms单位
                                
                                # 检查丢锤数据
                                for error_note in drop_hammers:
                                    if hasattr(error_note, 'global_index') and error_note.global_index >= 0:
                                        if error_note.global_index < len(initial_valid_record_data):
                                            note = initial_valid_record_data[error_note.global_index]
                                            if hasattr(note, 'id') and note.id == key_id:
                                                # 检查时间范围
                                                note_keyon = note.offset
                                                note_keyoff = note.offset + (note.after_touch.index[-1] if hasattr(note, 'after_touch') and len(note.after_touch) > 0 else 0)
                                                if note_keyon <= click_time_01ms <= note_keyoff:
                                                    index = error_note.global_index
                                                    data_type = 'record'
                                                    print(f"[OK] 单算法模式: 从丢锤数据中找到音符: index={index}, key_id={key_id}")
                                                    break
                                
                                # 如果还没找到，检查多锤数据
                                if index is None:
                                    for error_note in multi_hammers:
                                        if hasattr(error_note, 'global_index') and error_note.global_index >= 0:
                                            if error_note.global_index < len(initial_valid_replay_data):
                                                note = initial_valid_replay_data[error_note.global_index]
                                                if hasattr(note, 'id') and note.id == key_id:
                                                    # 检查时间范围
                                                    note_keyon = note.offset
                                                    note_keyoff = note.offset + (note.after_touch.index[-1] if hasattr(note, 'after_touch') and len(note.after_touch) > 0 else 0)
                                                    if note_keyon <= click_time_01ms <= note_keyoff:
                                                        index = error_note.global_index
                                                        data_type = 'play'
                                                        print(f"[OK] 单算法模式: 从多锤数据中找到音符: index={index}, key_id={key_id}")
                                                        break
                    
                    if algorithm_name and not algorithm:
                        print("[ERROR] 无法获取算法对象")
                        return current_style, []
                    
                    # 多算法模式：从offset_data查找
                    if algorithm_name and algorithm and algorithm.analyzer and algorithm.analyzer.note_matcher:
                        offset_data = algorithm.analyzer.note_matcher.get_offset_alignment_data()
                        if offset_data:
                            click_time_01ms = click_x * 10  # 转换为0.1ms单位
                            for item in offset_data:
                                item_key_id = item.get('key_id')
                                # 确保key_id类型一致
                                try:
                                    item_key_id = int(item_key_id) if item_key_id is not None else None
                                except (ValueError, TypeError):
                                    continue
                                
                                record_keyon = item.get('record_keyon', 0)
                                record_keyoff = item.get('record_keyoff', 0)
                                # 如果没有record_keyoff，使用record_keyon + record_duration
                                if record_keyoff == 0:
                                    record_duration = item.get('record_duration', 0)
                                    record_keyoff = record_keyon + record_duration
                                
                                if item_key_id == key_id and record_keyon <= click_time_01ms <= record_keyoff:
                                    index = item.get('record_index')
                                    data_type = 'record'
                                    print(f"[OK] 多算法模式: 找到音符 index={index}, data_type={data_type}, 时间范围: {record_keyon/10:.1f}ms - {record_keyoff/10:.1f}ms, 点击时间: {click_time_01ms/10:.1f}ms")
                                    break
                
                # 如果在offset_data中没有找到，尝试从丢锤/多锤数据中查找
                if (key_id is not None and index is None):
                    print(f"[INFO] 在offset_data中未找到，尝试从丢锤/多锤数据中查找")
                    
                    # 获取当前analyzer
                    current_analyzer = algorithm.analyzer if (algorithm_name and algorithm) else backend._get_current_analyzer()
                    
                    if current_analyzer:
                        drop_hammers = getattr(current_analyzer, 'drop_hammers', [])
                        multi_hammers = getattr(current_analyzer, 'multi_hammers', [])
                        initial_valid_record_data = getattr(current_analyzer, 'initial_valid_record_data', [])
                        initial_valid_replay_data = getattr(current_analyzer, 'initial_valid_replay_data', [])
                        
                        click_time_01ms = click_x * 10  # 转换为0.1ms单位
                        
                        # 检查丢锤数据
                        for error_note in drop_hammers:
                            if hasattr(error_note, 'global_index') and error_note.global_index >= 0:
                                if error_note.global_index < len(initial_valid_record_data):
                                    note = initial_valid_record_data[error_note.global_index]
                                    if hasattr(note, 'id') and note.id == key_id:
                                        # 检查时间范围
                                        note_keyon = note.offset
                                        note_keyoff = note.offset + (note.after_touch.index[-1] if hasattr(note, 'after_touch') and len(note.after_touch) > 0 else 0)
                                        if note_keyon <= click_time_01ms <= note_keyoff:
                                            index = error_note.global_index
                                            data_type = 'record'
                                            print(f"[OK] 从丢锤数据中找到音符: index={index}, key_id={key_id}")
                                            break
                        
                        # 如果还没找到，检查多锤数据
                        if index is None:
                            for error_note in multi_hammers:
                                if hasattr(error_note, 'global_index') and error_note.global_index >= 0:
                                    if error_note.global_index < len(initial_valid_replay_data):
                                        note = initial_valid_replay_data[error_note.global_index]
                                        if hasattr(note, 'id') and note.id == key_id:
                                            # 检查时间范围
                                            note_keyon = note.offset
                                            note_keyoff = note.offset + (note.after_touch.index[-1] if hasattr(note, 'after_touch') and len(note.after_touch) > 0 else 0)
                                            if note_keyon <= click_time_01ms <= note_keyoff:
                                                index = error_note.global_index
                                                data_type = 'play'
                                                print(f"[OK] 从多锤数据中找到音符: index={index}, key_id={key_id}")
                                                break
                
                if key_id is None or index is None:
                    print(f"[ERROR] 无法确定按键信息: key_id={key_id}, index={index}")
                    print(f"🔍 调试信息: click_x={point.get('x')}, click_y={point.get('y')}, algorithm_name={algorithm_name}")
                    if not point.get('customdata'):
                        print(f"[WARNING] 没有customdata，尝试从坐标查找失败")
                    return current_style, []
                
                print(f"[STATS] 最终提取的数据: algorithm_name={algorithm_name}, key_id={key_id}, data_type={data_type}, index={index}")
                
                # 获取算法对象
                algorithm = None
                active_algorithms = backend.multi_algorithm_manager.get_active_algorithms() if backend.multi_algorithm_manager else []
                if len(active_algorithms) > 1:
                    if not algorithm_name:
                        print("[ERROR] 多算法模式下无法确定算法名称")
                        return current_style, []
                # multi_algorithm_manager 在初始化时已创建
                algorithm = None
                if backend.multi_algorithm_manager:
                    algorithm = backend.multi_algorithm_manager.get_algorithm(algorithm_name)
                    print(f"[DEBUG] 查找算法: algorithm_name='{algorithm_name}', algorithm={algorithm is not None}")
                    if algorithm:
                        print(f"[DEBUG] 算法状态: is_active={algorithm.is_active}, is_ready={algorithm.is_ready()}, analyzer={algorithm.analyzer is not None}")
                    if not algorithm or not algorithm.analyzer:
                        print(f"[ERROR] 算法对象或analyzer为空: algorithm={algorithm is not None}, analyzer={algorithm.analyzer is not None if algorithm else None}")

                        # 调试：列出所有可用算法
                        all_algorithms = backend.multi_algorithm_manager.get_all_algorithms()
                        print(f"[DEBUG] 所有可用算法: {[alg.metadata.algorithm_name for alg in all_algorithms]}")

                        # 如果是多算法模式但找不到算法，尝试单算法模式
                        analyzer = backend._get_current_analyzer()
                        if analyzer:
                            print("[INFO] 尝试使用单算法模式")
                            algorithm = None  # 标记为单算法模式
                        else:
                            return current_style, []
                else:
                    # 单算法模式
                    analyzer = backend._get_current_analyzer()
                    if not analyzer:
                        print("[ERROR] analyzer为空")
                        return current_style, []
                    algorithm = None  # 单算法模式下不需要algorithm对象
                
                # 获取matched_pairs（已保存的配对数据）
                if algorithm is not None:
                    # 多算法模式
                    matched_pairs = algorithm.analyzer.matched_pairs if hasattr(algorithm.analyzer, 'matched_pairs') else []
                    valid_record_data = algorithm.analyzer.valid_record_data if hasattr(algorithm.analyzer, 'valid_record_data') else []
                    valid_replay_data = algorithm.analyzer.valid_replay_data if hasattr(algorithm.analyzer, 'valid_replay_data') else []
                else:
                    # 单算法模式
                    matched_pairs = analyzer.matched_pairs if hasattr(analyzer, 'matched_pairs') else []
                    valid_record_data = analyzer.valid_record_data if hasattr(analyzer, 'valid_record_data') else []
                    valid_replay_data = analyzer.valid_replay_data if hasattr(analyzer, 'valid_replay_data') else []
                
                # 步骤1：先判断这个按键ID（通过index）是否在matched_pairs中有匹配对
                has_matched_pair = False
                record_note = None
                replay_note = None
                
                print(f"🔍 开始查找匹配对: key_id={key_id}, data_type={data_type}, index={index}")
                print(f"[STATS] matched_pairs数量: {len(matched_pairs)}")
                
                # 根据data_type和index在matched_pairs中查找
                if data_type == 'record':
                    # 点击的是录制线，查找r_idx == index的匹配对
                    print(f"🔍 在matched_pairs中查找: r_idx == {index}")
                    for r_idx, p_idx, r_note, p_note in matched_pairs:
                        if r_idx == index and r_note.id == key_id:
                            # 找到匹配对
                            has_matched_pair = True
                            record_note = r_note
                            replay_note = p_note
                            print(f"[OK] 找到完整匹配对！")
                            break
                else:
                    # 点击的是播放线，查找p_idx == index的匹配对
                    print(f"🔍 在matched_pairs中查找: p_idx == {index}")
                    for r_idx, p_idx, r_note, p_note in matched_pairs:
                        if p_idx == index and p_note.id == key_id:
                            # 找到匹配对
                            has_matched_pair = True
                            record_note = r_note
                            replay_note = p_note
                            print(f"[OK] 找到完整匹配对！")
                            break
                
                print(f"[TARGET] 匹配结果: has_matched_pair={has_matched_pair}")
                
                # 步骤2：根据匹配结果生成曲线
                if has_matched_pair:
                    # 获取当前算法的display_name，用于判断是否是同种算法的不同曲子
                    current_display_name = None
                    if algorithm and algorithm.metadata:
                        current_display_name = algorithm.metadata.display_name

                    # 在多算法模式下，查找所有算法中匹配到同一个录制音符的播放音符
                    # 但是，对于同种算法的不同曲子（相同display_name），不添加其他算法的曲线
                    other_algorithm_notes = []  # [(algorithm_name, play_note), ...]
                    active_algorithms = backend.multi_algorithm_manager.get_active_algorithms() if backend.multi_algorithm_manager else []
                    if len(active_algorithms) > 1:
                        active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()
                        for alg in active_algorithms:
                            if alg.metadata.algorithm_name == algorithm_name:
                                continue  # 跳过当前算法（已经绘制）

                            # 如果是同种算法的不同曲子（相同display_name），跳过
                            if current_display_name and alg.metadata.display_name == current_display_name:
                                logger.info(f"[SKIP] 跳过同种算法的不同曲子: {alg.metadata.algorithm_name} (display_name={alg.metadata.display_name})")
                                continue

                            if not alg.analyzer or not hasattr(alg.analyzer, 'matched_pairs'):
                                continue

                            alg_matched_pairs = alg.analyzer.matched_pairs
                            # 查找匹配到同一个record_index的播放音符
                            for r_idx, p_idx, r_note, p_note in alg_matched_pairs:
                                if r_idx == index and r_note.id == key_id:
                                    other_algorithm_notes.append((alg.metadata.algorithm_name, p_note))
                                    logger.info(f"[OK] 找到算法 '{alg.metadata.algorithm_name}' 的匹配播放音符")
                                    break

                    # 有匹配对：绘制录制+播放对比曲线
                    # 对于同种算法的不同曲子，other_algorithm_notes为空，只显示录制和播放曲线

                    # 计算各算法的平均延时
                    mean_delays = {}
                    if not algorithm or not algorithm.analyzer:
                        print(f"[ERROR] 算法对象或分析器为空，无法计算平均延时")
                        return current_style, []

                    mean_error_0_1ms = algorithm.analyzer.get_mean_error()
                    mean_delays[algorithm_name] = mean_error_0_1ms / 10.0  # 转换为毫秒

                    # 为其他算法也计算平均延时
                    for other_alg_name, _ in other_algorithm_notes:
                        if len(active_algorithms) > 1:
                            other_alg = None
                            for alg in backend.multi_algorithm_manager.get_active_algorithms():
                                if alg.metadata.algorithm_name == other_alg_name:
                                    other_alg = alg
                                    break
                            if other_alg and other_alg.analyzer:
                                other_mean_error_0_1ms = other_alg.analyzer.get_mean_error()
                                mean_delays[other_alg_name] = other_mean_error_0_1ms / 10.0  # 转换为毫秒
                            else:
                                print(f"[ERROR] 其他算法 '{other_alg_name}' 对象或分析器为空")
                                return current_style, []

                    detail_figure_combined = backend.plot_generator.generate_note_comparison_plot(
                        record_note,
                        replay_note,
                        algorithm_name=algorithm_name,
                        other_algorithm_notes=other_algorithm_notes,  # 对于同种算法的不同曲子，这是空列表
                        mean_delays=mean_delays
                    )
                    print(f"[OK] 按键ID {key_id} 有匹配对，绘制录制+播放对比曲线（同种算法不同曲子时不显示其他算法曲线）")
                else:
                    # 没有匹配对：只绘制这个数据点的数据（可能是录制，也可能是播放）
                    # 对于匹配失败的音符，需要从原始数据中查找正确的音符对象
                    print(f"[INFO] 未找到匹配对，尝试查找匹配失败的音符数据")

                    # 首先尝试直接索引
                    found_note = False
                    if data_type == 'record' and index >= 0 and index < len(valid_record_data):
                        record_note = valid_record_data[index]
                        replay_note = None
                        # 验证按键ID是否匹配
                        if hasattr(record_note, 'id') and record_note.id == key_id:
                            found_note = True
                            print(f"[OK] 通过直接索引找到录制音符: index={index}, key_id={key_id}")
                        else:
                            record_note = None
                            print(f"[WARNING] 直接索引的录制音符key_id不匹配: 期望{key_id}, 实际{record_note.id if record_note else 'N/A'}")

                    elif data_type == 'play' and index >= 0 and index < len(valid_replay_data):
                        record_note = None
                        replay_note = valid_replay_data[index]
                        # 验证按键ID是否匹配
                        if hasattr(replay_note, 'id') and replay_note.id == key_id:
                            found_note = True
                            print(f"[OK] 通过直接索引找到播放音符: index={index}, key_id={key_id}")
                        else:
                            replay_note = None
                            print(f"[WARNING] 直接索引的播放音符key_id不匹配: 期望{key_id}, 实际{replay_note.id if replay_note else 'N/A'}")

                    # 如果直接索引失败，尝试通过key_id遍历查找
                    if not found_note:
                        print(f"[INFO] 直接索引失败，尝试通过key_id遍历查找")
                        if data_type == 'record':
                            for i, note in enumerate(valid_record_data):
                                if hasattr(note, 'id') and note.id == key_id:
                                    record_note = note
                                    replay_note = None
                                    found_note = True
                                    print(f"[OK] 通过遍历找到录制音符: array_index={i}, key_id={key_id}")
                                    break
                        elif data_type == 'play':
                            for i, note in enumerate(valid_replay_data):
                                if hasattr(note, 'id') and note.id == key_id:
                                    record_note = None
                                    replay_note = note
                                    found_note = True
                                    print(f"[OK] 通过遍历找到播放音符: array_index={i}, key_id={key_id}")
                                    break

                    # 如果仍然找不到，尝试从错误数据中查找（丢锤、多锤）
                    if not found_note:
                        print(f"[INFO] 在有效数据中未找到，尝试从错误数据中查找")
                        # 获取错误数据和初始有效数据
                        current_analyzer = algorithm.analyzer if algorithm else backend._get_current_analyzer()
                        drop_hammers = getattr(current_analyzer, 'drop_hammers', []) if current_analyzer else []
                        multi_hammers = getattr(current_analyzer, 'multi_hammers', []) if current_analyzer else []
                        initial_valid_record_data = getattr(current_analyzer, 'initial_valid_record_data', []) if current_analyzer else []
                        initial_valid_replay_data = getattr(current_analyzer, 'initial_valid_replay_data', []) if current_analyzer else []

                        # 检查丢锤数据
                        for error_note in drop_hammers:
                            if hasattr(error_note, 'notes') and error_note.notes:
                                for note_obj in error_note.notes:
                                    if hasattr(note_obj, 'id') and note_obj.id == key_id:
                                        # 对于丢锤，只显示录制数据
                                        if data_type == 'record':
                                            # 使用 index 直接从 initial_valid_record_data 中获取
                                            if 0 <= index < len(initial_valid_record_data):
                                                candidate_note = initial_valid_record_data[index]
                                                if hasattr(candidate_note, 'id') and candidate_note.id == key_id:
                                                    record_note = candidate_note
                                                    replay_note = None
                                                    found_note = True
                                                    print(f"[OK] 从丢锤数据中找到录制音符: index={index}, key_id={key_id}")
                                                    break
                                            
                                            # 如果索引不匹配，尝试遍历查找
                                            if not found_note:
                                                for note in initial_valid_record_data:
                                                    if hasattr(note, 'id') and note.id == key_id:
                                                        record_note = note
                                                        replay_note = None
                                                        found_note = True
                                                        print(f"[OK] 从丢锤数据中通过遍历找到录制音符: key_id={key_id}")
                                                        break
                                        break
                            if found_note:
                                break

                        # 如果还没找到，检查多锤数据
                        if not found_note:
                            for error_note in multi_hammers:
                                if hasattr(error_note, 'notes') and error_note.notes:
                                    for note_obj in error_note.notes:
                                        if hasattr(note_obj, 'id') and note_obj.id == key_id:
                                            # 对于多锤，只显示播放数据
                                            if data_type == 'play':
                                                # 使用 index 直接从 initial_valid_replay_data 中获取
                                                if 0 <= index < len(initial_valid_replay_data):
                                                    candidate_note = initial_valid_replay_data[index]
                                                    if hasattr(candidate_note, 'id') and candidate_note.id == key_id:
                                                        record_note = None
                                                        replay_note = candidate_note
                                                        found_note = True
                                                        print(f"[OK] 从多锤数据中找到播放音符: index={index}, key_id={key_id}")
                                                        break
                                                
                                                # 如果索引不匹配，尝试遍历查找
                                                if not found_note:
                                                    for note in initial_valid_replay_data:
                                                        if hasattr(note, 'id') and note.id == key_id:
                                                            record_note = None
                                                            replay_note = note
                                                            found_note = True
                                                            print(f"[OK] 从多锤数据中通过遍历找到播放音符: key_id={key_id}")
                                                            break
                                            break
                                if found_note:
                                    break

                    if not found_note:
                        print(f"[ERROR] 无法找到任何匹配的音符数据: key_id={key_id}, data_type={data_type}")
                        return current_style, []

                    # 计算平均延时（对于匹配失败的音符，使用0作为平均延时，不进行偏移）
                    mean_delays = {algorithm_name: 0.0}  # 不进行时间轴偏移

                    detail_figure_combined = backend.plot_generator.generate_note_comparison_plot(
                        record_note, replay_note,
                        algorithm_name=algorithm_name,
                        mean_delays=mean_delays
                    )
                    print(f"[OK] 匹配失败的按键ID {key_id} 找到音符数据，只绘制单侧曲线（无偏移）")
                
                if not detail_figure_combined:
                    print("[ERROR] 曲线生成失败")
                    return current_style, []
                
                # 显示模态框
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
                

                
                # 生成全过程处理图
                processing_stages_figure = None
                if backend.force_curve_analyzer and record_note and replay_note:
                    try:
                        comparison_result = backend.force_curve_analyzer.compare_curves(record_note, replay_note)
                        if comparison_result:
                            processing_stages_figure = backend.force_curve_analyzer.visualize_all_processing_stages(comparison_result)
                    except Exception as e:
                        print(f"[ERROR] 生成全过程处理图失败: {e}")

                # 构建模态框内容：使用Tabs展示对比图和全过程图
                modal_content = [
                    dcc.Tabs([
                        dcc.Tab(label='曲线对比', children=[
                            dcc.Graph(
                                figure=detail_figure_combined, 
                                style={'height': '700px'},
                                config={'scrollZoom': True, 'displayModeBar': True}
                            )
                        ]),
                        dcc.Tab(label='处理全过程', children=[
                            html.Div(
                                style={'height': '85vh', 'overflowY': 'auto', 'padding': '10px'},
                                children=[
                            dcc.Graph(
                                figure=processing_stages_figure if processing_stages_figure else go.Figure(),
                                        style={'height': f"{processing_stages_figure.layout.height}px"} if processing_stages_figure and processing_stages_figure.layout.height else {'height': '2000px'},
                                        config={'scrollZoom': True, 'displayModeBar': True, 'responsive': True}
                            ) if processing_stages_figure else html.Div("无法生成处理全过程图（可能只有单侧数据）", className="text-center p-3 text-muted")
                                ]
                            )
                        ])
                    ])
                ]
                
                rendered_row = html.Div(modal_content)
                
                print("[OK] 显示模态框")
                return modal_style, [rendered_row]
                
            except Exception as e:
                logger.error(f"[ERROR] 瀑布图点击处理失败: {e}")
                logger.error(traceback.format_exc())
                print(traceback.format_exc())
                return current_style, []
        
        # 其他情况，保持当前状态
        return current_style, []
    
    # 返回报告界面按钮回调
    @app.callback(
        [Output('main-tabs', 'value', allow_duplicate=True),
         Output('scroll-to-plot-trigger', 'data', allow_duplicate=True),
         Output('grade-detail-section-scroll-trigger', 'data', allow_duplicate=True)],
        [Input('btn-return-to-report', 'n_clicks')],
        [State('jump-source-plot-id', 'data')],
        prevent_initial_call=True
    )
    def handle_return_to_report(n_clicks, source_plot_id):
        """处理返回报告界面按钮点击，并触发滚动到来源图表"""
        if n_clicks and n_clicks > 0:
            logger.info(f"[PROCESS] 返回报告界面，来源图表: {source_plot_id}")
            
            # 如果是相对延时分布图，需要特殊处理
            if isinstance(source_plot_id, dict):
                # 从point_info中获取子图索引
                # source_plot_id 可能包含子图索引信息
                if source_plot_id.get('type') == 'relative-delay-distribution-plot':
                    subplot_idx = source_plot_id.get('index')
                    if subplot_idx is not None:
                        # 返回包含子图索引的滚动数据
                        scroll_data = {
                            'plot_type': 'relative-delay-distribution',
                            'subplot_index': int(subplot_idx)  # 确保是整数
                        }
                        return 'report-tab', scroll_data, no_update
                # 其他情况，返回原始数据（但需要确保是JSON可序列化的）
                return 'report-tab', source_plot_id, no_update
            elif isinstance(source_plot_id, str) and source_plot_id == 'relative-delay-distribution-plot':
                # 需要从point_info中获取子图索引
                # 但由于这里没有point_info，我们需要通过其他方式获取
                # 暂时返回一个通用的滚动数据，让客户端回调处理
                scroll_data = {
                    'plot_type': 'relative-delay-distribution',
                    'subplot_index': None  # 客户端会尝试找到第一个可见的子图
                }
                return 'report-tab', scroll_data, no_update
            elif source_plot_id == 'grade-detail-curves-modal':
                # 从评级统计模态框跳转回来，滚动到评级统计区域
                section_scroll_data = {'scroll_to': 'grade_detail_section'}
                logger.info("[PROCESS] 从评级统计跳转回来，触发区域滚动")
                return 'report-tab', no_update, section_scroll_data
            elif source_plot_id in ['error-table-drop', 'error-table-multi']:
                # 从错误表格模态框跳转回来，滚动到对应的错误表格区域
                error_table_scroll_data = {'scroll_to': 'error_table_section', 'table_type': source_plot_id.split('-')[-1]}
                logger.info(f"[PROCESS] 从{source_plot_id}跳转回来，触发错误表格区域滚动")
                return 'report-tab', no_update, error_table_scroll_data
            elif source_plot_id in ['raw-delay-time-series-plot', 'relative-delay-time-series-plot']:
                # 从延时时间序列图跳转回来，滚动到对应的时间序列图区域
                time_series_scroll_data = {'scroll_to': 'delay_time_series_section', 'plot_type': source_plot_id}
                logger.info(f"[PROCESS] 从{source_plot_id}跳转回来，触发时间序列图区域滚动")
                return 'report-tab', no_update, time_series_scroll_data
            else:
                # 普通图表，直接返回ID（字符串）
                if source_plot_id:
                    return 'report-tab', str(source_plot_id), no_update
                else:
                    return 'report-tab', None, no_update

            return no_update, no_update, no_update
    
    # 客户端回调：滚动到指定图表
    app.clientside_callback(
        """
        function(scroll_data) {
            if (scroll_data === null || scroll_data === undefined) {
                return window.dash_clientside.no_update;
            }
            
            try {
                // 如果是相对延时分布图的滚动数据（对象格式）
                if (typeof scroll_data === 'object' && scroll_data !== null && scroll_data.plot_type === 'relative-delay-distribution') {
                    const subplotIndex = scroll_data.subplot_index;
                    // 等待一小段时间，确保标签页切换完成
                    setTimeout(function() {
                        try {
                            // 查找所有相对延时分布图的子图容器
                            // 子图容器的结构：每个子图都在一个Div中，包含Graph元素
                            const allContainers = document.querySelectorAll('[id*="relative-delay-distribution"]');
                            let targetElement = null;
                            
                            // 如果指定了子图索引，尝试找到对应的子图
                            if (subplotIndex) {
                                // 查找包含指定索引的子图容器
                                // 由于Pattern Matching Callbacks，ID格式是动态的
                                // 我们需要通过遍历所有容器来找到对应的子图
                                let currentIndex = 1;
                                allContainers.forEach(function(container) {
                                    // 检查是否是图表容器（包含Graph元素）
                                    const graphElement = container.querySelector('.js-plotly-plot');
                                    if (graphElement && currentIndex === subplotIndex) {
                                        targetElement = container;
                                    }
                                    if (graphElement) {
                                        currentIndex++;
                                    }
                                });
                            }
                            
                            // 如果找到了目标元素，滚动到它
                            if (targetElement) {
                                const elementPosition = targetElement.getBoundingClientRect().top + window.pageYOffset;
                                const offsetPosition = elementPosition - 100;
                                window.scrollTo({
                                    top: offsetPosition,
                                    behavior: 'smooth'
                                });
                            } else if (allContainers.length > 0) {
                                // 如果找不到，滚动到第一个可见的相对延时分布图子图
                                const firstContainer = allContainers[0];
                                const elementPosition = firstContainer.getBoundingClientRect().top + window.pageYOffset;
                                const offsetPosition = elementPosition - 100;
                                window.scrollTo({
                                    top: offsetPosition,
                                    behavior: 'smooth'
                                });
                            }
                        } catch (e) {
                            console.error('滚动到相对延时分布图失败:', e);
                        }
                    }, 300);
                    return window.dash_clientside.no_update;
                }
                
                // 普通图表ID（字符串）
                if (typeof scroll_data === 'string') {
                    const plot_id = scroll_data;
                    // 等待一小段时间，确保标签页切换完成
                    setTimeout(function() {
                        try {
                            // 查找对应的图表元素
                            const plotElement = document.getElementById(plot_id);
                            if (plotElement) {
                                // 滚动到图表位置，并添加一些偏移量（向上偏移100px，避免被顶部导航栏遮挡）
                                const elementPosition = plotElement.getBoundingClientRect().top + window.pageYOffset;
                                const offsetPosition = elementPosition - 100;
                                
                                window.scrollTo({
                                    top: offsetPosition,
                                    behavior: 'smooth'  // 平滑滚动
                                });
                            }
                        } catch (e) {
                            console.error('滚动到图表失败:', e);
                        }
                    }, 300);  // 延迟300ms，确保DOM更新完成
                }
            } catch (e) {
                console.error('客户端回调错误:', e);
            }
            
            return window.dash_clientside.no_update;
        }
        """,
        Output('scroll-to-plot-trigger', 'data', allow_duplicate=True),
        Input('scroll-to-plot-trigger', 'data'),
        prevent_initial_call=True
    )
    
    # 客户端回调：滚动到相对延时分布图的对应子图位置
    app.clientside_callback(
        """
        function(scroll_data) {
            if (!scroll_data || !scroll_data.subplot_index) {
                return window.dash_clientside.no_update;
            }
            
            const subplotIndex = scroll_data.subplot_index;
            const graphElement = document.getElementById('relative-delay-distribution-plot');
            if (!graphElement) {
                return window.dash_clientside.no_update;
            }
            
            // 计算子图的位置（每个子图高度约500px）
            const baseHeightPerSubplot = 500;
            const subplotTop = (subplotIndex - 1) * baseHeightPerSubplot;
            
            // 获取图表元素的位置
            setTimeout(function() {
                const graphRect = graphElement.getBoundingClientRect();
                const absoluteGraphTop = graphRect.top + window.pageYOffset;
                const targetScrollTop = absoluteGraphTop + subplotTop;
                
                // 滚动到对应子图位置
                window.scrollTo({
                    top: targetScrollTop,
                    behavior: 'smooth'
                });
                
                // 延迟后滚动到表格位置
                setTimeout(function() {
                    const tableContainer = document.getElementById('relative-delay-distribution-table-container');
                    if (tableContainer) {
                        const tableRect = tableContainer.getBoundingClientRect();
                        const absoluteTableTop = tableRect.top + window.pageYOffset;
                        const offset = 100;
                        window.scrollTo({
                            top: absoluteTableTop - offset,
                            behavior: 'smooth'
                        });
                    }
                }, 500);
            }, 300);
            
            return window.dash_clientside.no_update;
        }
        """,
        Output('relative-delay-distribution-scroll-trigger', 'data', allow_duplicate=True),
        Input('relative-delay-distribution-scroll-trigger', 'data'),
        prevent_initial_call=True
    )

    # 客户端回调：评级统计返回时滚动到对应行
    app.clientside_callback(
        """
        function(scroll_data) {
            if (!scroll_data || !scroll_data.table_index || scroll_data.row_index === undefined) {
                return window.dash_clientside.no_update;
            }

            const tableIndex = scroll_data.table_index;
            const rowIndex = scroll_data.row_index;

            // 查找对应的表格
            const tableSelector = `[data-dash-component-id*="grade-detail-datatable"][data-dash-component-id*="${tableIndex}"]`;
            const tableElement = document.querySelector(tableSelector);

            if (!tableElement) {
                console.warn('Grade detail table not found:', tableSelector);
                return window.dash_clientside.no_update;
            }

            // 模拟点击对应行来激活它
            setTimeout(function() {
                try {
                    // 构造表格行的选择器
                    // Dash表格的行通常有特定的类名和结构
                    const tableBody = tableElement.querySelector('.dash-table-body');
                    if (tableBody) {
                        const rows = tableBody.querySelectorAll('.dash-table-row');
                        if (rows && rows.length > rowIndex) {
                            const targetRow = rows[rowIndex];

                            // 滚动到目标行
                            targetRow.scrollIntoView({
                                behavior: 'smooth',
                                block: 'center'
                            });

                            // 触发行的点击事件来激活它
                            // 注意：这可能需要根据Dash表格的具体实现进行调整
                            setTimeout(function() {
                                // 尝试设置active_cell（如果可能的话）
                                // 这是一个简化的实现，实际可能需要更复杂的逻辑
                                console.log('Scrolled to grade detail table row:', rowIndex);
                            }, 300);
                        } else {
                            console.warn('Target row not found in grade detail table:', rowIndex);
                        }
                    }
                } catch (error) {
                    console.error('Error scrolling to grade detail table row:', error);
                }
            }, 500);  // 等待模态框显示后再滚动

            return window.dash_clientside.no_update;
        }
        """,
        Output('grade-detail-return-scroll-trigger', 'data', allow_duplicate=True),
        Input('grade-detail-return-scroll-trigger', 'data'),
        prevent_initial_call=True
    )

    # 客户端回调：滚动到评级统计区域
    app.clientside_callback(
        """
        function(scroll_data) {
            if (!scroll_data) {
                return window.dash_clientside.no_update;
            }

            if (scroll_data.scroll_to === 'grade_detail_section') {
                // 查找评级统计区域
                // 优先查找有特定ID的卡片
                let targetElement = document.getElementById('grade-statistics-card');

                if (!targetElement) {
                    // 如果没找到特定ID，查找所有卡片，寻找包含"匹配质量评级统计"的标题
                    const allCards = document.querySelectorAll('.card');
                    for (let card of allCards) {
                        const header = card.querySelector('h4');
                        if (header && header.textContent && header.textContent.includes('匹配质量评级统计')) {
                            targetElement = card;
                            console.log('Found grade detail card by title:', header.textContent);
                            break;
                        }
                    }
                }

                // 如果还是没找到，尝试查找包含grade-detail的元素
                if (!targetElement) {
                    const gradeDetailElements = document.querySelectorAll('[id*="grade-detail"]');
                    if (gradeDetailElements.length > 0) {
                        // 向上查找最近的卡片容器
                        targetElement = gradeDetailElements[0].closest('.card') || gradeDetailElements[0];
                        console.log('Found grade detail element by fallback');
                    }
                }

                if (targetElement) {
                    setTimeout(function() {
                        try {
                            // 滚动到评级统计区域
                            targetElement.scrollIntoView({
                                behavior: 'smooth',
                                block: 'start',
                                inline: 'nearest'
                            });

                            console.log('Scrolled to grade detail section successfully');
                        } catch (error) {
                            console.error('Error scrolling to grade detail section:', error);
                        }
                    }, 500);  // 等待更长时间让页面完全加载
                } else {
                    console.warn('Grade detail section not found. Available cards:');
                    const cards = document.querySelectorAll('.card');
                    for (let card of cards) {
                        const header = card.querySelector('h4');
                        if (header) {
                            console.warn('Card header:', header.textContent);
                        }
                    }
                }
            } else if (scroll_data.scroll_to === 'error_table_section') {
                // 查找错误表格区域
                const tableType = scroll_data.table_type; // 'drop' 或 'multi'
                let targetElement = null;

                if (tableType === 'drop') {
                    // 查找丢锤表格
                    const dropTables = document.querySelectorAll('[id*="drop-hammers-table"]');
                    if (dropTables.length > 0) {
                        targetElement = dropTables[0].closest('.card') || dropTables[0];
                        console.log('Found drop hammers table');
                    }
                } else if (tableType === 'multi') {
                    // 查找多锤表格
                    const multiTables = document.querySelectorAll('[id*="multi-hammers-table"]');
                    if (multiTables.length > 0) {
                        targetElement = multiTables[0].closest('.card') || multiTables[0];
                        console.log('Found multi hammers table');
                    }
                }

                if (targetElement) {
                    setTimeout(function() {
                        try {
                            // 滚动到错误表格区域
                            targetElement.scrollIntoView({
                                behavior: 'smooth',
                                block: 'start',
                                inline: 'nearest'
                            });

                            console.log(`Scrolled to ${tableType} hammers table section successfully`);
                        } catch (error) {
                            console.error(`Error scrolling to ${tableType} hammers table section:`, error);
                        }
                    }, 500);
                } else {
                    console.warn(`${tableType} hammers table section not found`);
                }
            } else if (scroll_data.scroll_to === 'delay_time_series_section') {
                // 查找延时时间序列图区域
                const plotType = scroll_data.plot_type; // 'raw-delay-time-series-plot' 或 'relative-delay-time-series-plot'
                let targetElement = null;

                // 根据图表类型查找对应的图表
                if (plotType === 'raw-delay-time-series-plot') {
                    // 查找原始延时时间序列图
                    targetElement = document.getElementById('raw-delay-time-series-plot');
                    if (targetElement) {
                        // 向上查找最近的卡片容器
                        targetElement = targetElement.closest('.card') || targetElement;
                        console.log('Found raw delay time series plot');
                    }
                } else if (plotType === 'relative-delay-time-series-plot') {
                    // 查找相对延时时间序列图
                    targetElement = document.getElementById('relative-delay-time-series-plot');
                    if (targetElement) {
                        // 向上查找最近的卡片容器
                        targetElement = targetElement.closest('.card') || targetElement;
                        console.log('Found relative delay time series plot');
                    }
                }

                // 如果没找到特定图表，尝试查找包含时间序列图标题的卡片
                if (!targetElement) {
                    const allCards = document.querySelectorAll('.card');
                    for (let card of allCards) {
                        const header = card.querySelector('h6');
                        if (header && header.textContent) {
                            if (plotType === 'raw-delay-time-series-plot' &&
                                header.textContent.includes('原始延时时间序列图')) {
                                targetElement = card;
                                console.log('Found raw delay time series card by title');
                                break;
                            } else if (plotType === 'relative-delay-time-series-plot' &&
                                     header.textContent.includes('相对延时时间序列图')) {
                                targetElement = card;
                                console.log('Found relative delay time series card by title');
                                break;
                            }
                        }
                    }
                }

                if (targetElement) {
                    setTimeout(function() {
                        try {
                            // 滚动到时间序列图区域
                            targetElement.scrollIntoView({
                                behavior: 'smooth',
                                block: 'start',
                                inline: 'nearest'
                            });

                            console.log(`Scrolled to ${plotType} successfully`);
                        } catch (error) {
                            console.error(`Error scrolling to ${plotType}:`, error);
                        }
                    }, 500);  // 等待页面完全加载
                } else {
                    console.warn(`${plotType} not found. Available cards:`);
                    const cards = document.querySelectorAll('.card');
                    for (let card of cards) {
                        const header = card.querySelector('h6');
                        if (header) {
                            console.warn('Card header:', header.textContent);
                        }
                    }
                }
            }

            return window.dash_clientside.no_update;
        }
        """,
        Output('grade-detail-section-scroll-trigger', 'data', allow_duplicate=True),
        Input('grade-detail-section-scroll-trigger', 'data'),
        prevent_initial_call=True
    )



    # TODO
    # 丢锤和多锤表格点击回调 - 显示曲线对比（悬浮窗）
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True)],
        [Input({'type': 'drop-hammers-table', 'index': dash.ALL}, 'active_cell'),
         Input({'type': 'multi-hammers-table', 'index': dash.ALL}, 'active_cell'),
         Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State({'type': 'drop-hammers-table', 'index': dash.ALL}, 'data'),
         State({'type': 'multi-hammers-table', 'index': dash.ALL}, 'data'),
         State('session-id', 'data'),
         State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_error_tables_click(active_cells_multi_drop, active_cells_multi_multi, close_modal_clicks, close_btn_clicks,
                                 data_multi_drop, data_multi_multi, session_id, current_style):
        """处理丢锤和多锤表格点击，显示曲线对比（悬浮窗）"""
        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            return current_style, [], no_update

        trigger_id = ctx.triggered[0]['prop_id']
        trigger_value = ctx.triggered[0].get('value')

        # 如果点击了关闭按钮，隐藏模态框
        if trigger_id in ['close-key-curves-modal.n_clicks', 'close-key-curves-modal-btn.n_clicks']:
            return {'display': 'none'}, [], no_update

        # 处理表格点击
        table_type = None
        active_cell = None
        table_data = None
        algorithm_name = None

        # 解析触发源
        if 'drop-hammers-table' in trigger_id:
            table_type = 'drop'
        elif 'multi-hammers-table' in trigger_id:
            table_type = 'multi'

        if not table_type:
            return current_style, [], no_update

        # 获取对应的数据和active_cell
        try:
            # 解析ID
            id_parts = json.loads(trigger_id.split('.')[0])
            algorithm_name = id_parts.get('index', 'single')  # 默认单算法模式

            # 根据表格类型获取对应的数据
            if table_type == 'drop':
                # 找到对应的active_cell和data
                table_index = None
                for i, cell in enumerate(active_cells_multi_drop):
                    if cell is not None:
                        table_index = i
                        active_cell = cell
                        table_data = data_multi_drop[i] if i < len(data_multi_drop) else None
                        break
            else:  # multi
                # 找到对应的active_cell和data
                table_index = None
                for i, cell in enumerate(active_cells_multi_multi):
                    if cell is not None:
                        table_index = i
                        active_cell = cell
                        table_data = data_multi_multi[i] if i < len(data_multi_multi) else None
                        break

        except (json.JSONDecodeError, KeyError, IndexError):
            return current_style, [], no_update

        if not active_cell or not table_data:
            return current_style, [], no_update

        # 获取后端实例
        backend = session_manager.get_backend(session_id)
        if not backend:
            return current_style, [], no_update

        try:
            # 获取点击的行数据
            row_idx = active_cell.get('row')
            if row_idx is None or row_idx >= len(table_data):
                return current_style, [], no_update

            row_data = table_data[row_idx]

            # 获取音符信息
            data_type = row_data.get('data_type')
            key_id_str = row_data.get('keyId')
            global_index = row_data.get('index')

            if key_id_str == '无匹配':
                # 这是没有数据的行，跳过
                return current_style, [], no_update
            
            # 转换key_id为整数
            try:
                key_id = int(key_id_str) if isinstance(key_id_str, (int, float, str)) and str(key_id_str).isdigit() else None
                if key_id is None:
                    logger.warning(f"[WARNING] 无法转换keyId为整数: {key_id_str}")
                    return current_style, [], no_update
            except (ValueError, TypeError):
                logger.warning(f"[WARNING] keyId转换失败: {key_id_str}")
                return current_style, [], no_update

            # 根据表格类型确定数据类型
            if table_type == 'drop':
                # 丢锤：只有录制数据
                available_data = 'record'
                data_label = '录制'
            else:  # multi
                # 多锤：只有播放数据
                available_data = 'replay'
                data_label = '播放'

            # 查找对应的音符数据
            # 对于丢锤/多锤，应该使用initial_valid_record_data/initial_valid_replay_data
            # 并且使用global_index（即表格中的index字段）作为数组索引
            note_data = None
            
            # 确保global_index是整数类型
            try:
                if isinstance(global_index, str):
                    # 如果是字符串，尝试转换
                    if global_index == '无匹配':
                        return current_style, [], no_update
                    global_index = int(global_index)
            except (ValueError, TypeError):
                logger.warning(f"[WARNING] 无法转换global_index: {global_index}")
                return current_style, [], no_update
            
            if algorithm_name == 'single':
                # 单算法模式
                analyzer = backend._get_current_analyzer()
                if available_data == 'record':
                    # 丢锤：使用initial_valid_record_data
                    initial_data = getattr(analyzer, 'initial_valid_record_data', None) if analyzer else None
                else:
                    # 多锤：使用initial_valid_replay_data
                    initial_data = getattr(analyzer, 'initial_valid_replay_data', None) if analyzer else None

                if initial_data:
                    # 优先通过key_id查找音符数据，确保与表格显示一致
                    logger.info(f"[DEBUG] 单算法模式通过key_id查找音符数据: {key_id}")
                    for i, note in enumerate(initial_data):
                        if getattr(note, 'id', None) == key_id:
                            note_data = note
                            logger.info(f"[DEBUG] 单算法模式通过key_id查找成功: 索引{i}, key_id={key_id}")
                            break

                    # 如果通过key_id没找到，降级使用索引查找（向后兼容）
                    if not note_data and 0 <= global_index < len(initial_data):
                        candidate_note = initial_data[global_index]
                        candidate_key_id = getattr(candidate_note, 'id', None)
                        if candidate_key_id == key_id:
                            # 索引查找成功且key_id匹配
                            note_data = candidate_note
                            logger.info(f"[DEBUG] 单算法模式索引查找成功且key_id匹配: global_index={global_index}, key_id={key_id}")
                        else:
                            logger.warning(f"[WARNING] 单算法模式索引位置的key_id不匹配: 期望{key_id}, 实际{candidate_key_id}, 跳过绘制")
            else:
                # 多算法模式
                active_algorithms = backend.get_active_algorithms()
                logger.info(f"[DEBUG] 多算法模式查找 - 算法名称: {algorithm_name}, 活动算法数量: {len(active_algorithms)}")
                logger.info(f"[DEBUG] 活动算法列表: {[f'{alg.metadata.algorithm_name}(active={alg.is_active}, ready={alg.is_ready()})' for alg in active_algorithms]}")

                # 首先尝试在活动算法中查找
                target_algorithm = next((alg for alg in active_algorithms if alg.metadata.algorithm_name == algorithm_name), None)

                # 如果在活动算法中没找到，尝试在所有算法中查找（可能有未激活的算法）
                if not target_algorithm:
                    all_algorithms = backend.multi_algorithm_manager.algorithms.values() if backend.multi_algorithm_manager else []
                    target_algorithm = next((alg for alg in all_algorithms if alg.metadata.algorithm_name == algorithm_name), None)
                    if target_algorithm:
                        logger.warning(f"[WARNING] 在非活动算法中找到目标算法: {algorithm_name}, 激活状态: {target_algorithm.is_active}")
                    else:
                        logger.error(f"[ERROR] 在所有算法中都未找到目标算法: {algorithm_name}")
                        all_names = [alg.metadata.algorithm_name for alg in all_algorithms] if all_algorithms else []
                        logger.error(f"[ERROR] 所有可用算法: {all_names}")

                if not target_algorithm:
                    logger.error(f"[ERROR] 未找到匹配的算法实例: {algorithm_name}")
                    logger.error(f"[ERROR] 可用算法: {[alg.metadata.algorithm_name for alg in active_algorithms]}")
                    return current_style, [], no_update

                if not target_algorithm.analyzer:
                    logger.error(f"[ERROR] 目标算法没有分析器: {algorithm_name}")
                    return current_style, [], no_update

                logger.info(f"[DEBUG] 找到目标算法: {target_algorithm.metadata.algorithm_name}")

                # 尝试通过索引直接查找音符数据
                note_data = None
                initial_data = None

                if available_data == 'record':
                    # 丢锤：使用initial_valid_record_data
                    initial_data = getattr(target_algorithm.analyzer, 'initial_valid_record_data', None)
                    data_type_name = "initial_valid_record_data"
                else:
                    # 多锤：使用initial_valid_replay_data
                    initial_data = getattr(target_algorithm.analyzer, 'initial_valid_replay_data', None)
                    data_type_name = "initial_valid_replay_data"

                logger.info(f"[DEBUG] {data_type_name} - 数据长度: {len(initial_data) if initial_data else 0}, 索引: {global_index}")

                if initial_data:
                    # 优先通过key_id查找音符数据，确保与表格显示一致
                    logger.info(f"[DEBUG] 通过key_id查找音符数据: {key_id}")
                    for i, note in enumerate(initial_data):
                        if getattr(note, 'id', None) == key_id:
                            note_data = note
                            logger.info(f"[DEBUG] 通过key_id查找成功: 索引{i}, key_id={key_id}")
                            break

                    # 如果通过key_id没找到，降级使用索引查找（向后兼容）
                    if not note_data and 0 <= global_index < len(initial_data):
                        candidate_note = initial_data[global_index]
                        candidate_key_id = getattr(candidate_note, 'id', None)
                        if candidate_key_id == key_id:
                            # 索引查找成功且key_id匹配
                            note_data = candidate_note
                            logger.info(f"[DEBUG] 索引查找成功且key_id匹配: global_index={global_index}, key_id={key_id}")
                        else:
                            logger.warning(f"[WARNING] 索引位置的key_id不匹配: 期望{key_id}, 实际{candidate_key_id}, 跳过绘制")

                    if not note_data:
                        logger.error(f"[ERROR] 无法找到匹配的音符数据: key_id={key_id}, 索引={global_index}, 数据长度={len(initial_data)}")
                        return current_style, [], no_update
                else:
                    logger.error(f"[ERROR] 没有找到{data_type_name}数据")
                    return current_style, [], no_update

            if not note_data:
                return current_style, [], no_update

            # 确保key_id与note_data中的id一致
            actual_key_id = getattr(note_data, 'id', key_id)
            if actual_key_id != key_id:
                logger.info(f"🔍 key_id不一致: 表格中={key_id}, note_data中={actual_key_id}, 使用note_data中的值")
                key_id = actual_key_id

            # 生成曲线图（只显示有数据的部分）
            fig = _create_single_data_curve_figure(note_data, key_id, data_label, algorithm_name)

            # 计算时间信息
            center_time_ms = None
            record_idx = None
            replay_idx = None
            
            try:
                # 对于丢锤：只有录制数据，record_idx就是global_index（在initial_valid_record_data中的索引）
                # 对于多锤：只有播放数据，replay_idx就是global_index（在initial_valid_replay_data中的索引）
                if table_type == 'drop':
                    # 丢锤：只有录制数据
                    record_idx = global_index  # 在initial_valid_record_data中的索引
                    replay_idx = None  # 丢锤没有播放数据
                    
                    # 从表格数据中获取keyOn时间（已经是ms单位）
                    try:
                        key_on_str = row_data.get('keyOn', '')
                        if key_on_str and key_on_str != '无匹配':
                            center_time_ms = float(key_on_str)
                        else:
                            # 备用方案：从note_data计算
                            if note_data and hasattr(note_data, 'key_on_ms') and note_data.key_on_ms is not None:
                                center_time_ms = note_data.key_on_ms
                            elif note_data and hasattr(note_data, 'after_touch') and not note_data.after_touch.empty:
                                center_time_ms = (note_data.after_touch.index[0] + note_data.offset) / 10.0
                            elif note_data and hasattr(note_data, 'hammers') and not note_data.hammers.empty:
                                center_time_ms = (note_data.hammers.index[0] + note_data.offset) / 10.0
                            elif note_data and hasattr(note_data, 'offset'):
                                center_time_ms = note_data.offset / 10.0
                    except (ValueError, TypeError):
                        # 如果转换失败，使用备用方案
                        if note_data and hasattr(note_data, 'key_on_ms') and note_data.key_on_ms is not None:
                            center_time_ms = note_data.key_on_ms
                        elif note_data and hasattr(note_data, 'key_on_ms') and note_data.key_on_ms is not None:
                            center_time_ms = note_data.key_on_ms
                        elif note_data and hasattr(note_data, 'after_touch') and not note_data.after_touch.empty:
                            center_time_ms = (note_data.after_touch.index[0] + note_data.offset) / 10.0
                        elif note_data and hasattr(note_data, 'hammers') and not note_data.hammers.empty:
                            center_time_ms = (note_data.hammers.index[0] + note_data.offset) / 10.0
                        elif note_data and hasattr(note_data, 'offset'):
                            center_time_ms = note_data.offset / 10.0
                else:  # multi
                    # 多锤：只有播放数据
                    record_idx = None  # 多锤没有录制数据
                    replay_idx = global_index  # 在initial_valid_replay_data中的索引
                    
                    # 从表格数据中获取keyOn时间（已经是ms单位）
                    try:
                        key_on_str = row_data.get('keyOn', '')
                        if key_on_str and key_on_str != '无匹配':
                            center_time_ms = float(key_on_str)
                        else:
                            # 备用方案：从note_data计算
                            if note_data and hasattr(note_data, 'key_on_ms') and note_data.key_on_ms is not None:
                                center_time_ms = note_data.key_on_ms
                            elif note_data and hasattr(note_data, 'after_touch') and not note_data.after_touch.empty:
                                center_time_ms = (note_data.after_touch.index[0] + note_data.offset) / 10.0
                            elif note_data and hasattr(note_data, 'hammers') and not note_data.hammers.empty:
                                center_time_ms = (note_data.hammers.index[0] + note_data.offset) / 10.0
                            elif note_data and hasattr(note_data, 'offset'):
                                center_time_ms = note_data.offset / 10.0
                    except (ValueError, TypeError):
                        # 如果转换失败，使用备用方案
                        if note_data and hasattr(note_data, 'key_on_ms') and note_data.key_on_ms is not None:
                            center_time_ms = note_data.key_on_ms
                        elif note_data and hasattr(note_data, 'key_on_ms') and note_data.key_on_ms is not None:
                            center_time_ms = note_data.key_on_ms
                        elif note_data and hasattr(note_data, 'after_touch') and not note_data.after_touch.empty:
                            center_time_ms = (note_data.after_touch.index[0] + note_data.offset) / 10.0
                        elif note_data and hasattr(note_data, 'hammers') and not note_data.hammers.empty:
                            center_time_ms = (note_data.hammers.index[0] + note_data.offset) / 10.0
                        elif note_data and hasattr(note_data, 'offset'):
                            center_time_ms = note_data.offset / 10.0
            except Exception as e:
                logger.warning(f"[WARNING] 计算时间信息失败: {e}")
                logger.error(traceback.format_exc())

            # 准备跳转信息
            clicked_info = {
                'key_id': key_id,
                'algorithm_name': algorithm_name,
                'data_type': data_type,
                'global_index': global_index,
                'available_data': available_data,  # 标记有哪些数据可用
                'source_plot_id': f'error-table-{table_type}',  # 标识来源是错误表格
                'record_idx': record_idx,  # 录制数据索引
                'replay_idx': replay_idx,  # 播放数据索引
                'center_time_ms': center_time_ms  # 预先计算的时间信息
            }

            # 显示模态框 - 使用与其他回调函数一致的样式，避免嵌套
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

            # 直接返回图形，不添加额外的容器包裹，避免多余的框
            return modal_style, [dcc.Graph(figure=fig, style={'height': '500px'})], clicked_info

        except Exception as e:
            logger.error(f"[ERROR] 处理错误表格点击失败: {e}")
            return current_style, [], no_update

    def _create_single_data_curve_figure(note_data, key_id, data_label, algorithm_name):
        """创建只显示单侧数据的曲线图"""

        try:
            logger.info(f"[DEBUG] 创建单侧数据曲线图: key_id={key_id}, data_label={data_label}, algorithm_name={algorithm_name}")
            logger.info(f"[DEBUG] note_data类型: {type(note_data)}")

            # 创建子图
            fig = make_subplots(
                rows=1, cols=1,
                subplot_titles=[f'按键 {key_id} - {data_label}数据曲线 ({algorithm_name})']
            )

            # 提取数据
            note_offset = getattr(note_data, 'offset', 0)  # 获取偏移量
            logger.info(f"[DEBUG] note_offset: {note_offset}")
            has_data = False
            
            # 1. 绘制 after_touch 曲线
            if hasattr(note_data, 'after_touch') and note_data.after_touch is not None and not note_data.after_touch.empty:
                logger.info(f"[DEBUG] 找到after_touch数据，长度: {len(note_data.after_touch)}")
                # after_touch 是 pandas Series，直接使用 index 和 values
                at_time_data = note_data.after_touch.index.tolist()
                at_value_data = note_data.after_touch.values.tolist()
                logger.info(f"[DEBUG] after_touch时间范围: {min(at_time_data)} - {max(at_time_data)}")
                logger.info(f"[DEBUG] after_touch值范围: {min(at_value_data)} - {max(at_value_data)}")

                # 转换为毫秒，加上offset
                at_time_ms = [(t + note_offset) / 10.0 for t in at_time_data]

                # 添加after_touch曲线
                fig.add_trace(
                    go.Scatter(
                        x=at_time_ms,
                        y=at_value_data,
                        mode='lines',
                        name=f'{data_label}触后曲线',
                        line=dict(color='blue', width=2),
                        hovertemplate='<b>时间</b>: %{x:.2f}ms<br><b>触后值</b>: %{y}<extra></extra>'
                    ),
                    row=1, col=1
                )
                has_data = True
                logger.info(f"[DEBUG] 已添加after_touch曲线")
            else:
                logger.warning(f"[WARNING] 没有找到有效的after_touch数据")
            
            # 2. 绘制 hammers 锤击点（过滤掉锤速为0的点）
            if hasattr(note_data, 'hammers') and note_data.hammers is not None and not note_data.hammers.empty:
                logger.info(f"[DEBUG] 找到hammers数据，长度: {len(note_data.hammers)}")
                # hammers 是 pandas Series，直接使用 index 和 values
                hm_time_data = note_data.hammers.index.tolist()
                hm_value_data = note_data.hammers.values.tolist()
                logger.info(f"[DEBUG] hammers时间范围: {min(hm_time_data)} - {max(hm_time_data)}")
                logger.info(f"[DEBUG] hammers值范围: {min(hm_value_data)} - {max(hm_value_data)}")

                # 过滤掉锤速为0的点
                hammer_mask = [v > 0 for v in hm_value_data]
                logger.info(f"[DEBUG] 锤击点过滤: 总共{len(hammer_mask)}个点，其中{sum(hammer_mask)}个有效")
                if any(hammer_mask):
                    filtered_time = [t for t, m in zip(hm_time_data, hammer_mask) if m]
                    filtered_value = [v for v, m in zip(hm_value_data, hammer_mask) if m]

                    # 转换为毫秒，加上offset
                    hm_time_ms = [(t + note_offset) / 10.0 for t in filtered_time]

                    # 添加hammers锤击点
                    fig.add_trace(
                        go.Scattergl(
                            x=hm_time_ms,
                            y=filtered_value,
                            mode='markers',
                            name=f'{data_label}锤击点',
                            marker=dict(color='red', size=8, symbol='circle'),
                            hovertemplate='<b>锤击时间</b>: %{x:.2f}ms<br><b>锤速</b>: %{y}<extra></extra>'
                        ),
                        row=1, col=1
                    )
                    has_data = True
                    logger.info(f"[DEBUG] 已添加锤击点")
                else:
                    logger.warning(f"[WARNING] 所有锤击点都被过滤掉了（锤速为0）")
            else:
                logger.warning(f"[WARNING] 没有找到有效的hammers数据")
            
            # 如果没有任何数据
            if not has_data:
                fig.add_annotation(
                    text="无可用数据",
                    xref="paper", yref="paper",
                    x=0.5, y=0.5,
                    showarrow=False
                )
                return fig

            # 更新布局
            fig.update_layout(
                height=400,
                showlegend=True,
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                ),
                hovermode='x unified'
            )

            # 更新坐标轴标签
            fig.update_xaxes(title_text="时间 (ms)", row=1, col=1)
            fig.update_yaxes(title_text="触后值 / 锤速", row=1, col=1)

            return fig

        except Exception as e:
            logger.error(f"[ERROR] 创建单侧数据曲线图失败: {e}")
            # 返回错误图表
            error_fig = go.Figure()
            error_fig.add_annotation(
                text=f"生成曲线图失败: {str(e)}",
                xref="paper", yref="paper",
                x=0.5, y=0.5,
                showarrow=False
            )
            return error_fig

    # 持续时间差异表格点击回调 - 显示曲线对比
    duration_diff_click_handler = DurationDiffClickHandler()
    
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True),
         Output('current-clicked-point-info', 'data', allow_duplicate=True)],
        [Input('duration-diff-table', 'active_cell'),
         Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State('duration-diff-table', 'data'),
         State('session-id', 'data'),
         State('key-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_duration_diff_table_click(active_cell, close_modal_clicks, close_btn_clicks,
                                        table_data, session_id, current_style):
        """处理持续时间差异表格点击，显示原始曲线对比"""
        # 获取后端实例
        backend = session_manager.get_backend(session_id)
        
        # 获取活动算法列表
        active_algorithms = None
        if backend and hasattr(backend, 'active_algorithms'):
            active_algorithms = backend.active_algorithms
        
        # 调用处理器
        return duration_diff_click_handler.handle_table_click(
            active_cell, close_modal_clicks, close_btn_clicks,
            table_data, session_id, current_style, backend, active_algorithms
        )

    # 单算法模式错误表格数据填充回调
    # 注册评级统计详情回调
    register_all_callbacks(app, session_manager)


