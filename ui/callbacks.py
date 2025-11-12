"""
回调函数模块 - 处理Dash应用的所有回调逻辑
包含文件上传、历史记录表格交互等回调函数
"""
import uuid
import base64
import os
import time
from datetime import datetime
from dash import Input, Output, State, callback_context, no_update, html, dcc
import dash.dependencies
import dash_bootstrap_components as dbc
from ui.layout_components import create_report_layout, empty_figure, create_multi_algorithm_upload_area, create_multi_algorithm_management_area
from backend.piano_analysis_backend import PianoAnalysisBackend
from backend.data_manager import DataManager
from backend.session_manager import SessionManager
from ui.ui_processor import UIProcessor
from ui.multi_file_upload_handler import MultiFileUploadHandler
from utils.pdf_generator import PDFReportGenerator
from utils.logger import Logger
import plotly.graph_objects as go

logger = Logger.get_logger()


def _create_delay_by_key_stats_html(analysis_result):
    """创建延时与按键分析的统计结果HTML"""
    from typing import Dict, Any
    
    if analysis_result.get('status') != 'success':
        return [html.P("分析失败或数据不足", className="text-danger")]
    
    children = []
    
    # ANOVA结果
    anova_result = analysis_result.get('anova_result', {})
    if anova_result:
        f_stat = anova_result.get('f_statistic')
        p_value = anova_result.get('p_value')
        significant = anova_result.get('significant', False)
        
        if f_stat is not None and p_value is not None:
            status_text = "存在显著差异" if significant else "不存在显著差异"
            status_color = "success" if not significant else "warning"
            
            children.append(
                dbc.Alert([
                    html.H6("ANOVA检验结果", className="mb-2"),
                    html.P(f"F统计量: {f_stat:.4f}", className="mb-1"),
                    html.P(f"p值: {p_value:.4f}", className="mb-1"),
                    html.P(f"结论: {status_text}", className="mb-0", style={'fontWeight': 'bold'})
                ], color=status_color, className="mb-3")
            )
    
    # 异常按键
    anomaly_keys = analysis_result.get('anomaly_keys', [])
    if anomaly_keys:
        children.append(
            html.Div([
                html.H6("异常按键列表", className="mb-2"),
                html.Ul([
                    html.Li(f"按键ID {ak['key_id']}: 平均延时 {ak['mean_delay']:.2f}ms ({ak['anomaly_type']}), "
                           f"偏差 {ak['deviation']:.2f}ms ({ak['deviation_std']:.2f}倍标准差)")
                    for ak in anomaly_keys[:10]  # 只显示前10个
                ])
            ], className="mb-3")
        )
    
    # 事后检验结果 - 已注释
    # posthoc_result = analysis_result.get('posthoc_result')
    # if posthoc_result and posthoc_result.get('significant_pairs'):
    #     pairs = posthoc_result['significant_pairs']
    #     if pairs:
    #         # 先构建字符串列表，避免在f-string中使用反斜杠
    #         pair_strings = [f'按键{int(p["key1"])}-按键{int(p["key2"])}' for p in pairs[:5]]
    #         pair_text = ', '.join(pair_strings)
    #         children.append(
    #             html.Div([
    #                 html.H6(f"显著差异按键对 ({len(pairs)}对)", className="mb-2"),
    #                 html.P(f"前5对: {pair_text}")
    #             ], className="mb-3")
    #         )
    
    # 整体统计 - 已注释
    # overall_stats = analysis_result.get('overall_stats', {})
    # if overall_stats:
    #     children.append(
    #         dbc.Card([
    #             dbc.CardBody([
    #                 html.H6("整体统计信息", className="mb-2"),
    #                 html.P(f"总体平均延时: {overall_stats.get('overall_mean', 0):.2f}ms", className="mb-1"),
    #                 html.P(f"总体标准差: {overall_stats.get('overall_std', 0):.2f}ms", className="mb-1"),
    #                 html.P(f"按键间平均延时极差: {overall_stats.get('key_mean_range_diff', 0):.2f}ms", className="mb-0")
    #             ])
    #         ], className="mb-3")
    #     )
    
    return children if children else [html.P("暂无统计结果", className="text-muted")]


def _create_delay_by_velocity_stats_html(analysis_result):
    """创建延时与锤速分析的统计结果HTML"""
    from typing import Dict, Any
    
    if analysis_result.get('status') != 'success':
        return [html.P("分析失败或数据不足", className="text-danger")]
    
    children = []
    
    # 相关性分析
    correlation_result = analysis_result.get('correlation_result', {})
    if correlation_result:
        pearson_r = correlation_result.get('pearson_r')
        pearson_p = correlation_result.get('pearson_p')
        pearson_significant = correlation_result.get('pearson_significant', False)
        pearson_strength = correlation_result.get('pearson_strength', '')
        
        spearman_r = correlation_result.get('spearman_r')
        spearman_p = correlation_result.get('spearman_p')
        
        if pearson_r is not None:
            status_color = "success" if pearson_significant else "secondary"
            children.append(
                dbc.Alert([
                    html.H6("相关性分析结果", className="mb-2"),
                    html.P(f"皮尔逊相关系数: r = {pearson_r:.4f}, p = {pearson_p:.4f} ({pearson_strength})", className="mb-1"),
                    html.P(f"斯皮尔曼相关系数: r = {spearman_r:.4f}, p = {spearman_p:.4f}" if spearman_r is not None else "", className="mb-0")
                ], color=status_color, className="mb-3")
            )
    
    # 回归分析
    regression_result = analysis_result.get('regression_result', {})
    linear_reg = regression_result.get('linear', {})
    if linear_reg:
        r_squared = linear_reg.get('r_squared', 0)
        p_value = linear_reg.get('p_value', 1)
        slope = linear_reg.get('slope', 0)
        intercept = linear_reg.get('intercept', 0)
        
        children.append(
            dbc.Card([
                dbc.CardBody([
                    html.H6("回归分析结果", className="mb-2"),
                    html.P(f"线性回归方程: y = {slope:.4f}x + {intercept:.4f}", className="mb-1"),
                    html.P(f"R² = {r_squared:.4f}, p = {p_value:.4f}", className="mb-0")
                ])
            ], className="mb-3")
        )
    
    # 分组分析
    grouped_analysis = analysis_result.get('grouped_analysis', {})
    groups = grouped_analysis.get('groups', [])
    if groups:
        children.append(
            html.Div([
                html.H6("按锤速区间分组统计", className="mb-2"),
                dbc.Table([
                    html.Thead([
                        html.Tr([
                            html.Th("锤速区间"),
                            html.Th("样本数"),
                            html.Th("平均延时(ms)"),
                            html.Th("标准差(ms)")
                        ])
                    ]),
                    html.Tbody([
                        html.Tr([
                            html.Td(group.get('range_label', '')),
                            html.Td(group.get('count', 0)),
                            html.Td(f"{group.get('mean_delay', 0):.2f}"),
                            html.Td(f"{group.get('std_delay', 0):.2f}")
                        ])
                        for group in groups
                    ])
                ], bordered=True, hover=True, className="mb-3")
            ])
        )
    
    return children if children else [html.P("暂无统计结果", className="text-muted")]


def _create_empty_figure_for_callback(title):
    """创建用于回调的空Plotly figure对象"""
    import plotly.graph_objects as go

    fig = go.Figure()
    fig.add_annotation(
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        text=title,
        showarrow=False,
        font=dict(size=16, color="gray"),
        align="center"
    )

    fig.update_layout(
        title=title,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        height=600,
        template='plotly_white',
        showlegend=False
    )

    return fig


def _detect_trigger_source(ctx, backend, contents, filename, history_id):
    """
    检测用户操作的触发源，确定需要执行的处理逻辑
    
    触发源优先级（从高到低）：
    1. 新文件上传 - 最高优先级，会重新加载数据
    2. 历史记录选择 - 中等优先级，会切换数据源
    3. 按钮点击 - 最低优先级，基于当前数据生成视图
    
    Args:
        ctx: Dash回调上下文，包含触发信息
        backend: 后端实例，用于状态管理
        contents: 上传文件的内容（base64编码）
        filename: 上传文件的文件名
        history_id: 选择的历史记录ID
        
    Returns:
        str: 触发源类型 ('upload', 'history', 'waterfall', 'report', 'skip')
             - 'upload': 新文件上传
             - 'history': 历史记录选择
             - 'waterfall': 瀑布图按钮点击
             - 'report': 报告按钮点击
             - 'skip': 跳过处理（重复操作）
    """
    # 获取当前状态信息
    current_time = time.time()
    current_state = _get_current_state(contents, filename, history_id)
    previous_state = _get_previous_state(backend)
    
    # 从回调上下文检测触发源
    trigger_source = _detect_trigger_from_context(ctx, current_state, previous_state, backend, current_time)
    
    # 如果无法从上下文确定，则基于状态变化智能判断
    if not trigger_source:
        trigger_source = _detect_trigger_from_state_change(current_state, previous_state, backend, current_time)
    
    # 记录最终结果
    data_source = getattr(backend, '_data_source', 'none') if backend else 'none'
    logger.info(f"🔍 最终确定触发源: {trigger_source}, 当前数据源: {data_source}")
    return trigger_source

def _get_current_state(contents, filename, history_id):
    """获取当前状态信息"""
    return {
        'has_upload': contents and filename,
        'has_history': history_id is not None,
        'upload_content': contents,
        'filename': filename,
        'history_id': history_id
    }

def _get_previous_state(backend):
    """获取上次的状态信息"""
    if not backend:
        return {
            'last_upload_content': None,
            'last_history_id': None
        }
    
    return {
        'last_upload_content': getattr(backend, '_last_upload_content', None),
        'last_history_id': getattr(backend, '_last_selected_history_id', None)
    }

def _detect_trigger_from_context(ctx, current_state, previous_state, backend, current_time):
    """从回调上下文检测触发源"""
    if not ctx.triggered:
        return None
    
    recent_trigger = ctx.triggered[0]['prop_id']
    
    # 检查文件上传触发
    if 'upload-spmid-data' in recent_trigger:
        return _handle_upload_trigger(current_state, previous_state, backend, current_time)
    
    # 检查历史记录选择触发
    elif 'history-dropdown' in recent_trigger:
        return _handle_history_trigger(current_state, previous_state, backend, current_time)
    
    # 移除瀑布图和报告按钮，改为自动生成
    
    return None

def _handle_upload_trigger(current_state, previous_state, backend, current_time):
    """处理文件上传触发"""
    if not current_state['has_upload']:
        return None
    
    # 检查文件内容是否发生变化
    if current_state['upload_content'] != previous_state['last_upload_content']:
        _update_upload_state(backend, current_state['upload_content'], current_time)
        logger.info(f"🔄 检测到新文件上传: {current_state['filename']}")
        return 'upload'
    else:
        logger.warning("⚠️ 文件内容未变化，跳过重复处理")
        return 'skip'

def _handle_history_trigger(current_state, previous_state, backend, current_time):
    """处理历史记录选择触发"""
    if not current_state['has_history']:
        return None
    
    # 检查历史记录选择是否发生变化
    if current_state['history_id'] != previous_state['last_history_id']:
        _update_history_state(backend, current_state['history_id'], current_time)
        logger.info(f"🔄 检测到历史记录选择变化: {current_state['history_id']}")
        return 'history'
    else:
        logger.warning("⚠️ 历史记录选择未变化，跳过重复处理")
        return 'skip'

def _detect_trigger_from_state_change(current_state, previous_state, backend, current_time):
    """基于状态变化智能检测触发源"""
    # 检查是否有新的文件上传
    if (current_state['has_upload'] and 
        current_state['upload_content'] != previous_state['last_upload_content']):
        _update_upload_state(backend, current_state['upload_content'], current_time)
        logger.info(f"🔄 智能检测到新文件上传: {current_state['filename']}")
        return 'upload'
    
    # 检查是否有新的历史记录选择
    elif (current_state['has_history'] and 
          current_state['history_id'] != previous_state['last_history_id']):
        _update_history_state(backend, current_state['history_id'], current_time)
        logger.info(f"🔄 智能检测到历史记录选择: {current_state['history_id']}")
        return 'history'
    
    return None

def _update_upload_state(backend, upload_content, current_time):
    """更新文件上传状态"""
    backend._last_upload_content = upload_content
    backend._last_upload_time = current_time
    backend._data_source = 'upload'

def _update_history_state(backend, history_id, current_time):
    """更新历史记录选择状态"""
    backend._last_selected_history_id = history_id
    backend._last_history_time = current_time
    backend._data_source = 'history'


def _handle_file_upload(contents, filename, backend, key_filter):
    """处理文件上传操作"""
    logger.info(f"🔄 处理文件上传: {filename}")
    
    # 使用backend中的DataManager处理文件上传
    success, result_data, error_msg = backend.process_file_upload(contents, filename)
    
    if success:
        # 使用UIProcessor生成成功内容
        ui_processor = UIProcessor()
        info_content = ui_processor.create_upload_success_content(result_data)
        error_content = None
    else:
        # 使用UIProcessor生成错误内容
        ui_processor = UIProcessor()
        info_content = None
        error_content = ui_processor.create_upload_error_content(filename, error_msg)
    
    if info_content and not error_content:
        # 执行数据分析
        backend._perform_error_analysis()
        
        # 设置键ID筛选
        if key_filter:
            backend.set_key_filter(key_filter)
        else:
            backend.set_key_filter(None)
        
        # 自动生成瀑布图和报告
        fig = backend.generate_waterfall_plot()
        report_content = create_report_layout(backend)
        
        # 不在这里更新历史记录选项，避免与初始化回调冲突
        # 历史记录选项由专门的初始化和搜索回调管理
        
        # 获取键ID和时间筛选相关数据
        available_keys = backend.get_available_keys()
        key_options = [{'label': f'键位 {key_id}', 'value': key_id} for key_id in available_keys]
        key_status = backend.get_key_filter_status()
        
        # 将key_status转换为可渲染的字符串
        if key_status['enabled']:
            key_status_text = f"已筛选 {len(key_status['filtered_keys'])} 个键位 (共 {key_status['total_available_keys']} 个)"
        else:
            key_status_text = f"显示全部 {key_status['total_available_keys']} 个键位"
        
        # 完全避免更新滑块属性，防止无限递归
        time_status = backend.get_time_filter_status()
        
        # 将time_status转换为可渲染的字符串
        if time_status['enabled']:
            time_status_text = f"时间范围: {time_status['start_time']:.2f}s - {time_status['end_time']:.2f}s (时长: {time_status['duration']:.2f}s)"
        else:
            time_status_text = "显示全部时间范围"
        
        logger.info("✅ 文件上传处理完成，清空历史记录选择，显示新文件数据")
        current_value = key_filter if key_filter else []
        return fig, report_content, no_update, key_options, key_status_text, current_value, no_update, no_update, no_update, time_status_text
    else:
        # 处理上传错误
        if error_content:
            if error_msg and ("轨道" in error_msg or "track" in error_msg.lower() or "SPMID文件只包含" in error_msg):
                fig = _create_empty_figure_for_callback("❌ SPMID文件只包含 1 个轨道，需要至少2个轨道（录制+播放）才能进行分析")
            else:
                fig = _create_empty_figure_for_callback("文件类型不符")
            # 顺序: fig, report, history_options, key_options, key_status, key_value, time_min, time_max, time_value, time_status
            return fig, error_content, no_update, [], "显示全部键位", [], 0, 1000, [0, 1000], "显示全部时间范围"
        else:
            fig = _create_empty_figure_for_callback("文件上传失败")
            error_div = html.Div([
                html.H4("文件上传失败", className="text-center text-danger"),
                html.P("请检查文件格式或联系管理员。", className="text-center")
            ])
            return fig, error_div, no_update, [], "显示全部键位", [], 0, 1000, [0, 1000], "显示全部时间范围"


def _handle_history_selection(history_id, backend):
    """处理历史记录选择操作"""
    logger.info(f"🔄 加载历史记录: {history_id}")
    
    # 使用HistoryManager处理历史记录选择（包含状态初始化）
    success, result_data, error_msg = backend.history_manager.process_history_selection(history_id, backend)
    
    # 使用UIProcessor生成UI内容
    ui_processor = UIProcessor()

    if success:
        if result_data['has_file_content']:
            # 执行数据分析
            backend._perform_error_analysis()
            
            # 自动生成瀑布图和报告
            waterfall_fig = backend.generate_waterfall_plot()
            report_content = ui_processor.generate_history_report(backend, result_data['filename'], result_data['history_id'])
        else:
            # 没有文件内容，只显示基本信息
            waterfall_fig = ui_processor.create_empty_figure("历史记录无文件内容")
            report_content = ui_processor.create_history_basic_info_content(result_data)
    else:
        waterfall_fig = ui_processor.create_empty_figure("历史记录加载失败")
        report_content = ui_processor.create_error_content("历史记录加载失败", error_msg)
    
    if waterfall_fig and report_content:
        logger.info("✅ 历史记录加载完成，返回瀑布图和报告")
        
        # 获取键ID筛选相关数据
        available_keys = backend.get_available_keys()
        key_options = [{'label': f'键位 {key_id}', 'value': key_id} for key_id in available_keys]
        key_status = backend.get_key_filter_status()
        
        # 将key_status转换为可渲染的字符串
        if key_status['enabled']:
            key_status_text = f"已筛选 {len(key_status['filtered_keys'])} 个键位 (共 {key_status['total_available_keys']} 个)"
        else:
            key_status_text = f"显示全部 {key_status['total_available_keys']} 个键位"
        
        # 完全避免更新滑块属性，防止无限递归
        time_status = backend.get_time_filter_status()
        
        # 将time_status转换为可渲染的字符串
        if time_status['enabled']:
            time_status_text = f"时间范围: {time_status['start_time']:.2f}s - {time_status['end_time']:.2f}s (时长: {time_status['duration']:.2f}s)"
        else:
            time_status_text = "显示全部时间范围"
        
        # 历史记录情况下，当前筛选值取后端已设置的filtered_keys
        kstatus = backend.get_key_filter_status()
        current_value = kstatus.get('filtered_keys', []) if kstatus else []
        return waterfall_fig, report_content, no_update, key_options, key_status_text, current_value, no_update, no_update, no_update, time_status_text
    else:
        logger.error("❌ 历史记录加载失败")
        empty_fig = _create_empty_figure_for_callback("历史记录加载失败")
        error_content = html.Div([
            html.H4("历史记录加载失败", className="text-center text-danger"),
            html.P("请尝试选择其他历史记录", className="text-center")
        ])
        return empty_fig, error_content, no_update, [], "显示全部键位", 0, 1000, [0, 1000], "显示全部时间范围", no_update


def _handle_waterfall_button(backend):
    """处理瀑布图按钮点击"""
    current_data_source = getattr(backend, '_data_source', 'none') if backend else 'none'
    logger.info(f"🔄 生成瀑布图（数据源: {current_data_source}）")
    
    # 检查是否有已加载的数据 - 改为检查更基本的数据状态
    has_data = (backend.analyzer and 
                (backend.plot_generator.valid_record_data or backend.plot_generator.valid_replay_data or
                 (hasattr(backend.analyzer, 'valid_record_data') and backend.analyzer.valid_record_data) or
                 (hasattr(backend.analyzer, 'valid_replay_data') and backend.analyzer.valid_replay_data)))
    
    if has_data:
        fig = backend.generate_waterfall_plot()
        
        # 获取实际的时间范围并更新滑动条
        try:
            time_range = backend.get_time_range()
            time_min, time_max = time_range
            
            # 确保时间范围是有效的
            if isinstance(time_min, (int, float)) and isinstance(time_max, (int, float)) and time_min < time_max:
                # 创建合理的标记点
                range_size = time_max - time_min
                if range_size <= 1000:
                    step = max(1, range_size // 5)
                elif range_size <= 10000:
                    step = max(10, range_size // 10)
                else:
                    step = max(100, range_size // 20)
                
                marks = {}
                for i in range(int(time_min), int(time_max) + 1, step):
                    if i == time_min or i == time_max or (i - time_min) % (step * 2) == 0:
                        marks[i] = str(i)
                
                logger.info(f"⏰ 瀑布图按钮更新滑动条: min={time_min}, max={time_max}, 范围={range_size}")
                # key_value 不在此回调中更新
                return fig, no_update, no_update, [], "显示全部键位", no_update, time_min, time_max, [time_min, time_max], "显示全部时间范围"
            else:
                logger.warning(f"⚠️ 时间范围无效: {time_range}")
                return fig, no_update, no_update, [], "显示全部键位", no_update, 0, 1000, [0, 1000], "显示全部时间范围"
        except Exception as e:
            logger.error(f"❌ 获取时间范围失败: {e}")
            return fig, no_update, no_update, [], "显示全部键位", 0, 1000, [0, 1000], "显示全部时间范围", no_update
    else:
        if current_data_source == 'history':
            empty_fig = _create_empty_figure_for_callback("请选择历史记录或上传新文件")
        else:
            empty_fig = _create_empty_figure_for_callback("请先上传SPMID文件")
            return empty_fig, no_update, no_update, [], "显示全部键位", no_update, 0, 1000, [0, 1000], "显示全部时间范围"


def _handle_report_button(backend):
    """处理报告按钮点击"""
    current_data_source = getattr(backend, '_data_source', 'none') if backend else 'none'
    logger.info(f"🔄 生成分析报告（数据源: {current_data_source}）")
    
    # 检查是否有已加载的数据
    if hasattr(backend, 'all_error_notes') and backend.all_error_notes:
        report_content = create_report_layout(backend)
        return no_update, report_content, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update
    else:
        if current_data_source == 'history':
            error_content = html.Div([
                html.H4("请选择历史记录或上传新文件", className="text-center text-warning"),
                html.P("需要先选择历史记录或上传SPMID文件才能生成报告", className="text-center")
            ])
        else:
            error_content = html.Div([
                html.H4("请先上传SPMID文件", className="text-center text-warning"),
                html.P("需要先上传并分析SPMID文件才能生成报告", className="text-center")
            ])
        return no_update, error_content, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update


def _handle_fallback_logic(contents, filename, history_id, backend):
    """兜底逻辑：基于现有状态判断"""
    if contents and filename and not history_id:
        logger.info(f"🔄 兜底处理文件上传: {filename}")
        
        # 使用backend中的DataManager处理文件上传
        success, result_data, error_msg = backend.process_file_upload(contents, filename)
        fig = backend.generate_waterfall_plot()
        report_content = create_report_layout(backend)
        
        # 不在这里更新历史记录选项，避免循环调用
        return fig, report_content, no_update, [], "显示全部键位", [], 0, 1000, [0, 1000], "显示全部时间范围"
        
    elif history_id:
        logger.info(f"🔄 兜底处理历史记录: {history_id}")
        
        # 使用UIProcessor生成UI内容
        ui_processor = UIProcessor()
        # 使用HistoryManager处理历史记录选择（包含状态初始化）
        success, result_data, error_msg = backend.history_manager.process_history_selection(history_id, backend)
        
        if success:
            if result_data['has_file_content']:
                # 有文件内容，生成瀑布图和报告
                waterfall_fig = ui_processor.generate_history_waterfall(backend, result_data['filename'], result_data['main_record'])
                report_content = ui_processor.generate_history_report(backend, result_data['filename'], result_data['history_id'])
            else:
                # 没有文件内容，只显示基本信息
                waterfall_fig = ui_processor.create_empty_figure("历史记录无文件内容")
                report_content = ui_processor.create_history_basic_info_content(result_data)
        else:
            waterfall_fig = ui_processor.create_empty_figure("历史记录加载失败")
            report_content = ui_processor.create_error_content("历史记录加载失败", error_msg)
        if waterfall_fig and report_content:
            return waterfall_fig, report_content, no_update, [], "显示全部键位", [], 0, 1000, [0, 1000], "显示全部时间范围"
        else:
            empty_fig = _create_empty_figure_for_callback("历史记录加载失败")
            error_content = html.Div([
                html.H4("历史记录加载失败", className="text-center text-danger"),
                html.P("请尝试选择其他历史记录", className="text-center")
            ])
            return empty_fig, error_content, no_update, [], "显示全部键位", 0, 1000, [0, 1000], "显示全部时间范围", no_update

    # 最终兜底：无上传、无历史选择、无触发
    placeholder_fig = _create_empty_figure_for_callback("等待操作：请上传文件或选择历史记录")
    return placeholder_fig, no_update, no_update, [], "显示全部键位", [], 0, 1000, [0, 1000], "显示全部时间范围"


def register_callbacks(app, session_manager: SessionManager, history_manager):
    """注册所有回调函数"""

    # 初始化回调：自动启用多算法模式
    @app.callback(
        Output('session-id', 'data'),
        Input('session-id', 'data'),
        prevent_initial_call=False
    )
    def init_session_and_enable_multi_algorithm(session_data):
        """初始化会话ID并自动启用多算法模式"""
        if session_data is None:
            session_id = str(uuid.uuid4())
        else:
            session_id = session_data
        
        # 多算法模式始终启用
        session_id, backend = session_manager.get_or_create_backend(session_id)
        if backend:
            # 确保multi_algorithm_manager已初始化
            if not backend.multi_algorithm_manager:
                backend._ensure_multi_algorithm_manager()
            logger.info("✅ 多算法模式已就绪")
        
        return session_id

    # 单算法模式的数据处理回调已移除 - 现在只使用多算法模式


    # 表格选择回调和相关辅助函数已删除 - 因为已删除对比分析图和详细数据信息的UI组件，且表格已禁用行选择
    # 原回调用于处理表格选择并更新对比分析图和详细数据信息，现已不再需要


    # 添加时间滑块初始化回调 - 当数据加载完成后自动设置合理的时间范围
    @app.callback(
        [Output('time-filter-slider', 'min', allow_duplicate=True),
         Output('time-filter-slider', 'max', allow_duplicate=True),
         Output('time-filter-slider', 'value', allow_duplicate=True),
         Output('time-filter-slider', 'marks', allow_duplicate=True)],
        Input('report-content', 'children'),
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def initialize_time_slider_on_data_load(report_content, session_id):
        """当数据加载完成后初始化时间滑块"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update, no_update, no_update, no_update
        
        # 只有当有分析数据时才更新滑块
        if not hasattr(backend, 'all_error_notes') or not backend.all_error_notes:
            return no_update, no_update, no_update, no_update
        
        try:
            # 获取实际的时间范围
            time_range = backend.get_time_range()
            time_min, time_max = time_range
            
            # 确保时间范围是有效的
            if not isinstance(time_min, (int, float)) or not isinstance(time_max, (int, float)):
                return no_update, no_update, no_update, no_update
            
            if time_min >= time_max:
                return no_update, no_update, no_update, no_update
            
            # 转换为整数，避免滑块精度问题
            time_min, time_max = int(time_min), int(time_max)
            
            # 创建合理的标记点
            range_size = time_max - time_min
            if range_size <= 1000:
                step = max(1, range_size // 5)
            elif range_size <= 10000:
                step = max(10, range_size // 10)
            else:
                step = max(100, range_size // 20)
            
            marks = {}
            for i in range(time_min, time_max + 1, step):
                if i == time_min or i == time_max or (i - time_min) % (step * 2) == 0:
                    marks[i] = str(i)
            
            logger.info(f"⏰ 初始化时间滑块: min={time_min}, max={time_max}, 范围={range_size}")
            
            return time_min, time_max, [time_min, time_max], marks
            
        except Exception as e:
            logger.warning(f"⚠️ 初始化时间滑块失败: {e}")
            return no_update, no_update, no_update, no_update

    # 添加初始化历史记录下拉菜单的回调 - 只在应用启动时初始化一次
    @app.callback(
        [Output('history-dropdown', 'options', allow_duplicate=True),
         Output('history-dropdown', 'value', allow_duplicate=True)],
        Input('session-id', 'data'),
        prevent_initial_call='initial_duplicate'  # 修复：使用 initial_duplicate 允许初始调用和重复输出
    )
    def initialize_history_dropdown(session_id):
        """初始化历史记录下拉框选项 - 只在会话初始化时调用一次"""
        # 检查是否已经初始化过
        if hasattr(initialize_history_dropdown, '_initialized'):
            return no_update, no_update
        
        try:
            # 获取历史记录列表
            history_list = history_manager.get_history_list(limit=100)

            if not history_list:
                initialize_history_dropdown._initialized = True
                return [], None

            # 转换为下拉框选项格式
            options = []
            for record in history_list:
                label = f"{record['filename']} ({record['timestamp'][:19] if record['timestamp'] else '未知时间'}) - 多锤:{record['multi_hammers']} 丢锤:{record['drop_hammers']}"
                options.append({
                    'label': label,
                    'value': record['id']
                })

            logger.info(f"✅ 初始化历史记录下拉菜单，找到 {len(options)} 条记录")
            initialize_history_dropdown._initialized = True
            return options, None  # 返回选项列表，但不预选任何项

        except Exception as e:
            logger.error(f"❌ 初始化历史记录下拉框失败: {e}")
            initialize_history_dropdown._initialized = True
            return [], None

    @app.callback(
        Output('history-dropdown', 'options', allow_duplicate=True),
        [Input('history-search', 'value'),
         Input('session-id', 'data')],
        prevent_initial_call=True  # 修改为True，防止初始化时重复调用
    )
    def update_history_dropdown_search(search_value, session_id):
        """更新历史记录下拉框选项 - 仅搜索触发"""
        try:
            # 获取历史记录列表
            history_list = history_manager.get_history_list(limit=100)

            if not history_list:
                return []

            # 转换为下拉框选项格式
            options = []
            for record in history_list:
                label = f"{record['filename']} ({record['timestamp'][:19] if record['timestamp'] else '未知时间'}) - 多锤:{record['multi_hammers']} 丢锤:{record['drop_hammers']}"

                # 如果有搜索值，则过滤选项
                if search_value and search_value.lower() not in label.lower():
                    continue

                options.append({
                    'label': label,
                    'value': record['id']
                })

            return options

        except Exception as e:
            logger.error(f"❌ 更新历史记录下拉框失败: {e}")
            return []

    @app.callback(
        Output('spmid-filename', 'children'),
        Input('upload-spmid-data', 'contents'),
        State('upload-spmid-data', 'filename'),
        prevent_initial_call=True
    )
    def update_spmid_filename(contents, filename):
        """更新SPMID文件名显示"""
        if filename:
            return html.Div([
                html.I(className="fas fa-file-audio", style={'marginRight': '8px', 'color': '#28a745'}),
                html.Span(f"已选择: {filename}", style={'color': '#28a745', 'fontWeight': 'bold'})
            ])
        return ""




        # 点击plot的点显示详细图像
    @app.callback(
        [Output('detail-modal', 'style'),
        Output('detail-plot-combined', 'figure')],
        [Input('main-plot', 'clickData'),
        Input('key-delay-scatter-plot', 'clickData'),  # 添加散点图点击输入
        Input('key-delay-zscore-scatter-plot', 'clickData'),  # 添加Z-Score标准化散点图点击输入
        Input('close-modal', 'n_clicks'),
        Input('close-modal-btn', 'n_clicks'),
        Input({'type': 'drop-hammers-table', 'index': dash.dependencies.ALL}, 'active_cell'),  # 丢锤表格点击
        Input({'type': 'multi-hammers-table', 'index': dash.dependencies.ALL}, 'active_cell')],  # 多锤表格点击
        [State('detail-modal', 'style'),
        State('session-id', 'data'),
        State({'type': 'drop-hammers-table', 'index': dash.dependencies.ALL}, 'data'),  # 丢锤表格数据
        State({'type': 'multi-hammers-table', 'index': dash.dependencies.ALL}, 'data')],  # 多锤表格数据
        prevent_initial_call=False
        )
    def update_plot(clickData, scatter_clickData, zscore_scatter_clickData, close_clicks, close_btn_clicks, 
                   drop_hammers_active_cells, multi_hammers_active_cells,
                   current_style, session_id, drop_hammers_table_data, multi_hammers_table_data):
        """更新详细图表 - 支持多用户会话"""
        from dash import no_update

        # if session_id is None:
        # 获取用户会话数据
        backend = session_manager.get_backend(session_id)
        if not backend:
            return current_style, no_update

        ctx = callback_context
        if not ctx.triggered:
            return current_style, no_update

        # 获取触发信息
        triggered_prop_id = ctx.triggered[0]['prop_id']
        trigger_value = ctx.triggered[0].get('value')
        
        # 解析trigger_id
        if triggered_prop_id.startswith('{'):
            # Pattern matching ID
            import json
            try:
                trigger_id_dict = json.loads(triggered_prop_id.split('.')[0])
                trigger_id = f"{trigger_id_dict.get('type', 'unknown')}-{trigger_id_dict.get('index', 'unknown')}"
            except:
                trigger_id = triggered_prop_id.split('.')[0]
        else:
            trigger_id = triggered_prop_id.split('.')[0]
        
        logger.info(f"🔍 回调触发: trigger_id={trigger_id}, trigger_value={trigger_value}, triggered_prop_id={triggered_prop_id}")

        # 处理瀑布图点击
        if trigger_id == 'main-plot' and clickData:
            # 从会话中获取数据
            # 检查数据是否已加载

            # 获取点击的点数据
            if 'points' in clickData and len(clickData['points']) > 0:
                point = clickData['points'][0]
                # logger.debug(f"点击点: {point}")

                if point.get('customdata') is None:
                    return current_style, no_update
                
                customdata = point['customdata'][0] if isinstance(point['customdata'], list) and len(point['customdata']) > 0 else point['customdata']
                
                # 多算法模式：从customdata中提取算法名称
                if len(customdata) >= 7:
                    algorithm_name = customdata[6] if len(customdata) > 6 else None
                    key_id = customdata[2]
                    key_on = customdata[0]
                    key_off = customdata[1]
                    data_type = customdata[4]
                    index = customdata[5]
                    
                    logger.info(f"🖱️ 多算法模式点击: 算法={algorithm_name}, 索引={index}, 类型={data_type}")
                    
                    # 从对应的算法数据中生成详细图表
                    detail_figure1, detail_figure2, detail_figure_combined = backend.generate_multi_algorithm_detail_plot_by_index(
                        algorithm_name=algorithm_name,
                        index=index,
                        is_record=(data_type=='record')
                    )
                else:
                    logger.warning(f"⚠️ customdata格式不正确，长度={len(customdata)}")
                    return current_style, no_update

                # 更新模态框样式为显示状态
                modal_style = {
                    'display': 'block',
                    'position': 'fixed',
                    'zIndex': '1000',
                    'left': '0',
                    'top': '0',
                    'width': '100%',
                    'height': '100%',
                    'backgroundColor': 'rgba(0,0,0,0.6)',
                    'backdropFilter': 'blur(5px)'
                }

                logger.info("🔄 显示详细分析模态框")
                return modal_style, detail_figure_combined
            else:
                logger.warning("点击数据格式不正确")
                return current_style, no_update
        
        # 处理散点图点击（点击超过阈值的点时显示曲线图）
        elif trigger_id == 'key-delay-scatter-plot' and scatter_clickData:
            logger.info(f"🔍 散点图点击回调被触发 - scatter_clickData: {scatter_clickData is not None}")
            
            if 'points' not in scatter_clickData or len(scatter_clickData['points']) == 0:
                logger.warning("⚠️ 散点图点击回调 - scatter_clickData无效或没有points")
                return current_style, no_update
            
            point = scatter_clickData['points'][0]
            logger.info(f"🔍 散点图点击 - 点击点数据: {point}")
            
            if not point.get('customdata'):
                logger.warning("⚠️ 散点图点击 - 点没有customdata")
                return current_style, no_update
            
            # 安全地提取customdata
            raw_customdata = point['customdata']
            logger.info(f"🔍 散点图点击 - raw_customdata类型: {type(raw_customdata)}, 值: {raw_customdata}")
            
            if isinstance(raw_customdata, list) and len(raw_customdata) > 0:
                customdata = raw_customdata[0] if isinstance(raw_customdata[0], list) else raw_customdata
            else:
                customdata = raw_customdata
            
            # 确保customdata是列表类型
            if not isinstance(customdata, list):
                logger.warning(f"⚠️ customdata不是列表类型: {type(customdata)}, 值: {customdata}")
                return current_style, no_update
            
            logger.info(f"🔍 散点图点击 - customdata: {customdata}, 长度: {len(customdata)}")
            
            # 提取延时值
            delay_ms = point.get('y')
            if delay_ms is None:
                return current_style, no_update
            
            # 多算法模式
            if len(customdata) >= 5:
                record_index = customdata[0]
                replay_index = customdata[1]
                algorithm_name = customdata[4]
                
                # 获取该算法的阈值
                algorithm = backend.multi_algorithm_manager.get_algorithm(algorithm_name)
                if algorithm and algorithm.analyzer:
                    me_0_1ms = algorithm.analyzer.get_mean_error()
                    std_0_1ms = algorithm.analyzer.get_standard_deviation()
                    mu = me_0_1ms / 10.0
                    sigma = std_0_1ms / 10.0
                    upper_threshold = mu + 3 * sigma
                    lower_threshold = mu - 3 * sigma
                    
                    # 检查是否超过阈值
                    if delay_ms > upper_threshold or delay_ms < lower_threshold:
                        logger.info(f"🖱️ 散点图点击（超过阈值）: 算法={algorithm_name}, record_index={record_index}, replay_index={replay_index}, delay={delay_ms:.2f}ms")
                        detail_figure1, detail_figure2, detail_figure_combined = backend.generate_multi_algorithm_scatter_detail_plot_by_indices(
                            algorithm_name=algorithm_name,
                            record_index=record_index,
                            replay_index=replay_index
                        )
                        
                        logger.info(f"🔍 散点图点击回调 - 图表生成结果: figure1={detail_figure1 is not None}, figure2={detail_figure2 is not None}, figure_combined={detail_figure_combined is not None}")
                        
                        if detail_figure1 and detail_figure2 and detail_figure_combined:
                            modal_style = {
                                'display': 'block',
                                'position': 'fixed',
                                'zIndex': '1000',
                                'left': '0',
                                'top': '0',
                                'width': '100%',
                                'height': '100%',
                                'backgroundColor': 'rgba(0,0,0,0.6)',
                                'backdropFilter': 'blur(5px)'
                            }
                            logger.info("✅ 散点图点击回调 - 返回模态框和图表")
                            return modal_style, detail_figure_combined
                        else:
                            logger.warning(f"⚠️ 散点图点击回调 - 图表生成失败，部分图表为None")
                    else:
                        logger.info(f"ℹ️ 散点图点击 - 点未超过阈值: delay={delay_ms:.2f}ms, 阈值范围=[{lower_threshold:.2f}, {upper_threshold:.2f}]")
            
            return current_style, no_update
        
        # 处理Z-Score标准化散点图点击（点击任意点时显示曲线图）
        elif trigger_id == 'key-delay-zscore-scatter-plot' and zscore_scatter_clickData:
            logger.info(f"🔍 Z-Score标准化散点图点击回调被触发 - zscore_scatter_clickData: {zscore_scatter_clickData is not None}")
            
            if 'points' not in zscore_scatter_clickData or len(zscore_scatter_clickData['points']) == 0:
                logger.warning("⚠️ Z-Score标准化散点图点击回调 - zscore_scatter_clickData无效或没有points")
                return current_style, no_update
            
            point = zscore_scatter_clickData['points'][0]
            logger.info(f"🔍 Z-Score标准化散点图点击 - 点击点数据: {point}")
            
            if not point.get('customdata'):
                logger.warning("⚠️ Z-Score标准化散点图点击 - 点没有customdata")
                return current_style, no_update
            
            # 安全地提取customdata
            raw_customdata = point['customdata']
            logger.info(f"🔍 Z-Score标准化散点图点击 - raw_customdata类型: {type(raw_customdata)}, 值: {raw_customdata}")
            
            if isinstance(raw_customdata, list) and len(raw_customdata) > 0:
                customdata = raw_customdata[0] if isinstance(raw_customdata[0], list) else raw_customdata
            else:
                customdata = raw_customdata
            
            # 确保customdata是列表类型
            if not isinstance(customdata, list):
                logger.warning(f"⚠️ Z-Score标准化散点图点击 - customdata不是列表类型: {type(customdata)}, 值: {customdata}")
                return current_style, no_update
            
            logger.info(f"🔍 Z-Score标准化散点图点击 - customdata: {customdata}, 长度: {len(customdata)}")
            
            # 多算法模式：从customdata中提取算法名称和索引
            if len(customdata) >= 5:
                record_index = customdata[0]
                replay_index = customdata[1]
                algorithm_name = customdata[4]  # Z-Score散点图的customdata格式: [record_index, replay_index, key_id_int, delay_ms, algorithm_name]
                
                logger.info(f"🖱️ Z-Score标准化散点图点击: 算法={algorithm_name}, record_index={record_index}, replay_index={replay_index}")
                
                # 生成详细曲线图
                detail_figure1, detail_figure2, detail_figure_combined = backend.generate_multi_algorithm_scatter_detail_plot_by_indices(
                    algorithm_name=algorithm_name,
                    record_index=record_index,
                    replay_index=replay_index
                )
                
                logger.info(f"🔍 Z-Score标准化散点图点击回调 - 图表生成结果: figure1={detail_figure1 is not None}, figure2={detail_figure2 is not None}, figure_combined={detail_figure_combined is not None}")
                
                if detail_figure1 and detail_figure2 and detail_figure_combined:
                    modal_style = {
                        'display': 'block',
                        'position': 'fixed',
                        'zIndex': '1000',
                        'left': '0',
                        'top': '0',
                        'width': '100%',
                        'height': '100%',
                        'backgroundColor': 'rgba(0,0,0,0.6)',
                        'backdropFilter': 'blur(5px)'
                    }
                    logger.info("✅ Z-Score标准化散点图点击回调 - 返回模态框和图表")
                    return modal_style, detail_figure_combined
                else:
                    logger.warning(f"⚠️ Z-Score标准化散点图点击回调 - 图表生成失败，部分图表为None")
            else:
                logger.warning(f"⚠️ Z-Score标准化散点图点击 - customdata长度不足: {len(customdata)}")
            
            return current_style, no_update

        # 处理丢锤表格点击
        elif 'drop-hammers-table' in str(trigger_id):
            import json
            try:
                logger.info(f"🔍 丢锤表格点击 - 开始处理")
                logger.info(f"🔍 trigger_value={trigger_value}, active_cells={drop_hammers_active_cells}")
                
                # 解析表格ID获取算法名称和表格索引
                triggered_prop = ctx.triggered[0]['prop_id']
                table_id_str = triggered_prop.split('.')[0]
                table_id = json.loads(table_id_str)
                algorithm_name = table_id.get('index')
                
                if not algorithm_name:
                    logger.warning(f"⚠️ 无法获取算法名称")
                    return current_style, no_update
                
                logger.info(f"🔍 算法名称: {algorithm_name}, triggered_prop={triggered_prop}")
                
                # 找到被点击的表格在列表中的索引
                # 需要从后端获取算法列表，确保表格数据与算法对应
                active_algorithms = backend.multi_algorithm_manager.get_active_algorithms() if backend.multi_algorithm_manager else []
                algorithm_names = [alg.metadata.algorithm_name for alg in active_algorithms]
                
                # 找到当前算法在列表中的索引
                if algorithm_name not in algorithm_names:
                    logger.warning(f"⚠️ 算法 '{algorithm_name}' 不在激活算法列表中")
                    return current_style, no_update
                
                algorithm_idx = algorithm_names.index(algorithm_name)
                logger.info(f"🔍 算法索引: {algorithm_idx}, 算法名称: {algorithm_name}")
                
                # 从对应表格的active_cells中获取active_cell
                active_cell = None
                if algorithm_idx < len(drop_hammers_active_cells):
                    active_cell = drop_hammers_active_cells[algorithm_idx]
                    logger.info(f"🔍 从active_cells[{algorithm_idx}]获取: {active_cell}")
                
                # 如果active_cells中没有，尝试使用trigger_value（但需要验证是否来自正确的表格）
                if not active_cell and trigger_value and isinstance(trigger_value, dict) and 'row' in trigger_value:
                    # 验证trigger_value是否来自当前表格
                    # 由于无法直接验证，我们假设它来自当前表格
                    active_cell = trigger_value
                    logger.info(f"🔍 使用trigger_value: {active_cell}")
                
                if not active_cell:
                    logger.warning(f"⚠️ 未找到active_cell, algorithm_idx={algorithm_idx}, active_cells={drop_hammers_active_cells}")
                    return current_style, no_update
                
                row_idx = active_cell.get('row')
                if row_idx is None:
                    logger.warning(f"⚠️ active_cell中没有row索引")
                    return current_style, no_update
                
                logger.info(f"🔍 row_idx={row_idx}, algorithm_idx={algorithm_idx}")
                
                # 找到对应的表格数据 - 使用已经计算好的algorithm_idx
                
                # 通过算法索引获取对应的表格数据
                if algorithm_idx >= len(drop_hammers_table_data):
                    logger.warning(f"⚠️ 算法索引 {algorithm_idx} 超出表格数据范围")
                    return current_style, no_update
                
                data_list = drop_hammers_table_data[algorithm_idx]
                if not data_list or row_idx >= len(data_list):
                    logger.warning(f"⚠️ 表格数据为空或行索引超出范围: algorithm_idx={algorithm_idx}, row_idx={row_idx}, data_list长度={len(data_list) if data_list else 0}")
                    return current_style, no_update
                
                table_data = data_list[row_idx]
                logger.info(f"🔍 找到表格数据: algorithm={algorithm_name}, algorithm_idx={algorithm_idx}, row_idx={row_idx}, data={table_data}")
                
                row_index = table_data.get('index')
                data_type = table_data.get('data_type')
                
                logger.info(f"🔍 表格数据: row_index={row_index}, data_type={data_type}")
                
                # 只处理record类型的行
                if data_type != 'record' or row_index == '无匹配' or row_index is None:
                    logger.info(f"ℹ️ 跳过该行: data_type={data_type}, row_index={row_index}")
                    return current_style, no_update
                
                # 获取表格数据中的keyId，用于验证
                table_key_id = table_data.get('keyId')
                
                # 生成图表
                index = int(row_index)
                logger.info(f"🔍 生成图表: algorithm={algorithm_name}, index={index}, table_keyId={table_key_id}")
                
                detail_figure1, detail_figure2, detail_figure_combined = backend.generate_multi_algorithm_error_detail_plot_by_index(
                    algorithm_name=algorithm_name,
                    index=index,
                    error_type='drop',
                    expected_key_id=table_key_id  # 传递期望的keyId用于验证
                )
                
                if not detail_figure1 or not detail_figure2 or not detail_figure_combined:
                    logger.warning(f"⚠️ 图表生成失败")
                    return current_style, no_update
                
                # 返回结果 - 确保样式正确
                modal_style = {
                    'display': 'block',
                    'position': 'fixed',
                    'zIndex': '1000',
                    'left': '0',
                    'top': '0',
                    'width': '100%',
                    'height': '100%',
                    'backgroundColor': 'rgba(0,0,0,0.6)',
                    'backdropFilter': 'blur(5px)'
                }
                
                logger.info(f"✅ 丢锤表格 - 返回模态框和图表, modal_style={modal_style}")
                logger.info(f"🔍 图表类型: figure_combined={type(detail_figure_combined)}")
                return modal_style, detail_figure_combined
                
            except Exception as e:
                logger.error(f"❌ 丢锤表格点击处理失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return current_style, no_update
        
        # 处理多锤表格点击
        elif 'multi-hammers-table' in str(trigger_id):
            import json
            try:
                logger.info(f"🔍 多锤表格点击 - 开始处理")
                
                # 解析表格ID获取算法名称和表格索引
                triggered_prop = ctx.triggered[0]['prop_id']
                table_id_str = triggered_prop.split('.')[0]
                table_id = json.loads(table_id_str)
                algorithm_name = table_id.get('index')
                
                if not algorithm_name:
                    logger.warning(f"⚠️ 无法获取算法名称")
                    return current_style, no_update
                
                logger.info(f"🔍 算法名称: {algorithm_name}, triggered_prop={triggered_prop}")
                
                # 找到被点击的表格在列表中的索引
                # 需要从后端获取算法列表，确保表格数据与算法对应
                active_algorithms = backend.multi_algorithm_manager.get_active_algorithms() if backend.multi_algorithm_manager else []
                algorithm_names = [alg.metadata.algorithm_name for alg in active_algorithms]
                
                # 找到当前算法在列表中的索引
                if algorithm_name not in algorithm_names:
                    logger.warning(f"⚠️ 算法 '{algorithm_name}' 不在激活算法列表中")
                    return current_style, no_update
                
                algorithm_idx = algorithm_names.index(algorithm_name)
                logger.info(f"🔍 算法索引: {algorithm_idx}, 算法名称: {algorithm_name}")
                
                # 从对应表格的active_cells中获取active_cell
                active_cell = None
                if algorithm_idx < len(multi_hammers_active_cells):
                    active_cell = multi_hammers_active_cells[algorithm_idx]
                    logger.info(f"🔍 从active_cells[{algorithm_idx}]获取: {active_cell}")
                
                # 如果active_cells中没有，尝试使用trigger_value（但需要验证是否来自正确的表格）
                if not active_cell and trigger_value and isinstance(trigger_value, dict) and 'row' in trigger_value:
                    # 验证trigger_value是否来自当前表格
                    # 由于无法直接验证，我们假设它来自当前表格
                    active_cell = trigger_value
                    logger.info(f"🔍 使用trigger_value: {active_cell}")
                
                if not active_cell:
                    logger.warning(f"⚠️ 未找到active_cell, algorithm_idx={algorithm_idx}, active_cells={multi_hammers_active_cells}")
                    return current_style, no_update
                
                row_idx = active_cell.get('row')
                if row_idx is None:
                    logger.warning(f"⚠️ active_cell中没有row索引")
                    return current_style, no_update
                
                logger.info(f"🔍 row_idx={row_idx}, algorithm_idx={algorithm_idx}")
                
                # 找到对应的表格数据 - 使用已经计算好的algorithm_idx
                
                # 通过算法索引获取对应的表格数据
                if algorithm_idx >= len(multi_hammers_table_data):
                    logger.warning(f"⚠️ 算法索引 {algorithm_idx} 超出表格数据范围")
                    return current_style, no_update
                
                data_list = multi_hammers_table_data[algorithm_idx]
                if not data_list or row_idx >= len(data_list):
                    logger.warning(f"⚠️ 表格数据为空或行索引超出范围: algorithm_idx={algorithm_idx}, row_idx={row_idx}, data_list长度={len(data_list) if data_list else 0}")
                    return current_style, no_update
                
                table_data = data_list[row_idx]
                logger.info(f"🔍 找到表格数据: algorithm={algorithm_name}, algorithm_idx={algorithm_idx}, row_idx={row_idx}, data={table_data}")
                
                row_index = table_data.get('index')
                data_type = table_data.get('data_type')
                
                # 只处理play类型的行
                if data_type != 'play' or row_index == '无匹配' or row_index is None:
                    logger.info(f"ℹ️ 跳过该行: data_type={data_type}, row_index={row_index}")
                    return current_style, no_update
                
                # 获取表格数据中的keyId，用于验证
                table_key_id = table_data.get('keyId')
                
                # 生成图表
                index = int(row_index)
                logger.info(f"🔍 生成图表: algorithm={algorithm_name}, index={index}, table_keyId={table_key_id}")
                
                detail_figure1, detail_figure2, detail_figure_combined = backend.generate_multi_algorithm_error_detail_plot_by_index(
                    algorithm_name=algorithm_name,
                    index=index,
                    error_type='multi',
                    expected_key_id=table_key_id  # 传递期望的keyId用于验证
                )
                
                if not detail_figure1 or not detail_figure2 or not detail_figure_combined:
                    logger.warning(f"⚠️ 图表生成失败")
                    return current_style, no_update
                
                # 返回结果
                modal_style = {
                    'display': 'block',
                    'position': 'fixed',
                    'zIndex': '1000',
                    'left': '0',
                    'top': '0',
                    'width': '100%',
                    'height': '100%',
                    'backgroundColor': 'rgba(0,0,0,0.6)',
                    'backdropFilter': 'blur(5px)'
                }
                
                logger.info(f"✅ 多锤表格 - 返回模态框和图表")
                return modal_style, detail_figure_combined
                
            except Exception as e:
                logger.error(f"❌ 多锤表格点击处理失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return current_style, no_update

        elif trigger_id in ['close-modal', 'close-modal-btn']:
            # 关闭模态框
            modal_style = {
                'display': 'none',
                'position': 'fixed',
                'zIndex': '1000',
                'left': '0',
                'top': '0',
                'width': '100%',
                'height': '100%',
                'backgroundColor': 'rgba(0,0,0,0.6)',
                'backdropFilter': 'blur(5px)'
            }
            return modal_style, no_update

        else:
            return current_style, no_update


    # 修复PDF导出回调，添加加载动画和异常处理
    # PDF导出 - 第一步：显示加载动画
    @app.callback(
        Output('pdf-status', 'children'),
        [Input('btn-export-pdf', 'n_clicks')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def show_pdf_loading(n_clicks, session_id):
        """第一步：立即显示PDF生成加载动画
        说明：旧版要求存在 all_error_notes 才允许导出，导致"无异常时无法导出概览"。
        现在放宽条件：只要存在有效数据（任一轨或有匹配对）即可生成PDF（概览页+可选异常页）。
        """
        if not n_clicks:
            return no_update

        # 检查会话和后端实例
        backend = session_manager.get_backend(session_id)
        if not backend:
            return dbc.Alert("❌ 会话已过期，请刷新页面", color="warning", duration=3000)
        # 放宽校验：存在任一数据或匹配结果即可导出
        has_data = False
        try:
            dm = getattr(backend, 'data_manager', None)
            record = dm.get_record_data() if dm else None
            replay = dm.get_replay_data() if dm else None
            has_pairs = bool(getattr(backend.analyzer, 'matched_pairs', [])) if hasattr(backend, 'analyzer') else False
            has_data = bool(record) or bool(replay) or has_pairs
        except Exception:
            has_data = False
        if not has_data:
            return dbc.Alert("❌ 没有可导出的数据，请先上传SPMID文件并完成分析", color="warning", duration=4000)

        # 显示加载动画
        return dcc.Loading(
            children=[
                dbc.Alert([
                    html.I(className="fas fa-file-pdf", style={'marginRight': '8px'}),
                    f"正在生成PDF报告，包含 {len(backend.all_error_notes)} 个异常的完整分析，请稍候..."
                ], color="info", style={'margin': '0'})
            ],
            type="dot",
            color="#dc3545",
            style={'textAlign': 'center'}
        )

    # PDF导出 - 第二步：实际生成PDF
    @app.callback(
        Output('download-pdf', 'data'),
        [Input('pdf-status', 'children')],
        [State('session-id', 'data'),
         State('btn-export-pdf', 'n_clicks')],
        prevent_initial_call=True
    )
    def generate_pdf_after_loading(pdf_status, session_id, n_clicks):
        """第二步：在显示加载动画后实际生成PDF
        说明：不再依赖 all_error_notes 存在与否；若无异常，仅输出概览页。
        """
        # 只有当状态显示为加载中时才执行
        if not pdf_status or not n_clicks:
            return no_update

        # 检查是否是加载状态
        try:
            if isinstance(pdf_status, dict) and 'props' in pdf_status:
                # 这是一个Loading组件，表示正在加载
                pass
            else:
                # 不是加载状态，不执行
                return no_update
        except:
            return no_update

        # 检查会话和后端实例
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update

        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update
        # 只要有有效数据即可生成（概览为主，异常页可为空）
        try:
            dm = getattr(backend, 'data_manager', None)
            record = dm.get_record_data() if dm else None
            replay = dm.get_replay_data() if dm else None
            has_pairs = bool(getattr(backend.analyzer, 'matched_pairs', [])) if hasattr(backend, 'analyzer') else False
            has_data = bool(record) or bool(replay) or has_pairs
        except Exception:
            has_data = False
        if not has_data:
            return no_update

        try:
            # 添加延迟确保加载动画显示
            time.sleep(0.3)

            # 生成PDF报告
            source_info = backend.get_data_source_info() 
            current_filename = source_info.get('filename') or "未知文件"
            pdf_generator = PDFReportGenerator(backend)
            pdf_data = pdf_generator.generate_pdf_report(current_filename)

            if not pdf_data:
                return no_update

            # 生成安全的文件名
            import re
            safe_filename = re.sub(r'[<>:"/\\|?*]', '_', current_filename or "未知文件")
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"SPMID_完整分析报告_{safe_filename}_{timestamp}.pdf"

            # 确保PDF数据是base64编码的字符串
            if isinstance(pdf_data, bytes):
                pdf_data_b64 = base64.b64encode(pdf_data).decode('utf-8')
            else:
                pdf_data_b64 = pdf_data

            # 构建下载数据
            download_data = {
                'content': pdf_data_b64,
                'filename': filename,
                'type': 'application/pdf',
                'base64': True
            }

            return download_data

        except Exception as e:
            logger.error(f"PDF生成失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return no_update

    # PDF导出 - 第三步：显示完成状态
    @app.callback(
        [Output('pdf-status', 'children', allow_duplicate=True)],
        [Input('download-pdf', 'data')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def show_pdf_completion(download_data, session_id):
        """第三步：显示PDF生成完成状态"""
        if not download_data:
            return [no_update]

        # 检查会话
        backend = session_manager.get_backend(session_id)
        if not backend:
            return [no_update]

        # 显示成功状态
        success_alert = dbc.Alert([
            html.I(className="fas fa-check-circle", style={'marginRight': '8px'}),
            # 成功提示说明：根据实际异常数量提示；若为0则提示生成概览
            f"✅ PDF报告生成成功！异常条目: {len(getattr(backend, 'all_error_notes', []) or [])}，已开始下载（如无异常则仅包含概览）"
        ], color="success", duration=5000)

        return [success_alert]

    # 键ID筛选回调函数
    @app.callback(
        [Output('main-plot', 'figure', allow_duplicate=True),
         Output('key-filter-status', 'children', allow_duplicate=True),
         Output('key-filter-dropdown', 'options', allow_duplicate=True),
         Output('key-filter-dropdown', 'value', allow_duplicate=True)],
        [Input('key-filter-dropdown', 'value'),
         Input('btn-show-all-keys', 'n_clicks')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_key_filter(key_filter, show_all_clicks, session_id):
        """处理键ID筛选"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update, no_update, no_update, no_update
        
        # 检查是否有数据（通过DataManager的getter）
        if not backend.data_manager.get_record_data() and not backend.data_manager.get_replay_data():
            return no_update, no_update, no_update, no_update
        
        # 获取触发上下文
        ctx = callback_context
        if not ctx.triggered:
            return no_update, no_update, no_update, no_update
        
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        
        # 处理"显示全部键位"按钮
        if trigger_id == 'btn-show-all-keys' and show_all_clicks and show_all_clicks > 0:
            backend.set_key_filter(None)
            key_filter = None
            logger.info("🔍 重置键ID筛选")
        # 处理键ID下拉框选择
        elif trigger_id == 'key-filter-dropdown':
            if key_filter:
                backend.set_key_filter(key_filter)
                logger.info(f"🔍 应用键ID筛选: {key_filter}")
            else:
                backend.set_key_filter(None)
                logger.info("🔍 清除键ID筛选")
        else:
            return no_update, no_update, no_update, no_update
        
        # 重新生成瀑布图
        fig = backend.generate_waterfall_plot()
        key_status = backend.get_key_filter_status()
        
        # 将key_status转换为可渲染的字符串
        if key_status['enabled']:
            key_status_text = f"已筛选 {len(key_status['filtered_keys'])} 个键位 (共 {key_status['total_available_keys']} 个)"
        else:
            key_status_text = f"显示全部 {key_status['total_available_keys']} 个键位"
        
        logger.info(f"🔍 键ID筛选状态: {key_status}")
        
        # 获取键ID选项并转换为Dash Dropdown格式
        available_keys = backend.get_available_keys()
        key_options = [{'label': f'键位 {key_id}', 'value': key_id} for key_id in available_keys]
        
        # 返回当前选中的value，确保UI回显
        return fig, key_status_text, key_options, (key_filter or [])

    # 时间轴筛选回调函数
    @app.callback(
        [Output('main-plot', 'figure', allow_duplicate=True),
         Output('time-filter-status', 'children', allow_duplicate=True),
         Output('time-filter-slider', 'value', allow_duplicate=True)],
        [Input('btn-apply-time-filter', 'n_clicks'),
         Input('btn-reset-time-filter', 'n_clicks')],
        [State('session-id', 'data'),
         State('time-filter-slider', 'value')],
        prevent_initial_call=True
    )
    def handle_time_filter(apply_clicks, reset_clicks, session_id, time_range):
        """处理时间轴筛选"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update, no_update, no_update
        
        # 检查是否有数据
        if not hasattr(backend, 'all_error_notes') or not backend.all_error_notes:
            logger.warning("⚠️ 没有分析数据，无法应用时间筛选")
            return no_update, no_update, no_update
        
        # 获取触发上下文
        ctx = callback_context
        if not ctx.triggered:
            return no_update, no_update, no_update
        
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        logger.info(f"⏰ 时间筛选触发器: {trigger_id}")
        
        # 获取原始时间范围（用于重置）
        original_time_range = backend.get_time_range()
        original_min, original_max = original_time_range
        slider_value = no_update
        
        # 处理"重置时间范围"按钮
        if trigger_id == 'btn-reset-time-filter' and reset_clicks and reset_clicks > 0:
            backend.set_time_filter(None)
            logger.info("⏰ 重置时间范围筛选")
            # 重置滑块到原始范围
            slider_value = [int(original_min), int(original_max)]
            logger.info(f"⏰ 重置滑块到原始范围: {slider_value}")
            
        # 处理"应用时间筛选"按钮
        elif trigger_id == 'btn-apply-time-filter' and apply_clicks and apply_clicks > 0:
            if time_range and len(time_range) == 2 and time_range[0] != time_range[1]:
                # 验证时间范围的合理性
                start_time, end_time = time_range
                if start_time < end_time:
                    backend.set_time_filter(time_range)
                    logger.info(f"⏰ 应用时间轴筛选: {time_range}")
                    # 保持当前滑块值
                    slider_value = no_update
                else:
                    logger.warning(f"⚠️ 时间范围无效: {time_range}")
                    backend.set_time_filter(None)
                    # 重置滑块到原始范围
                    slider_value = [int(original_min), int(original_max)]
            else:
                backend.set_time_filter(None)
                logger.info("⏰ 清除时间轴筛选（无效范围）")
                # 重置滑块到原始范围
                slider_value = [int(original_min), int(original_max)]
        else:
            logger.warning(f"⚠️ 未识别的时间筛选触发器: {trigger_id}")
            return no_update, no_update, no_update
        
        try:
            # 重新生成瀑布图
            fig = backend.generate_waterfall_plot()
            time_status = backend.get_time_filter_status()
            
            # 将time_status转换为可渲染的字符串
            if time_status['enabled']:
                time_status_text = f"时间范围: {time_status['start_time']:.2f}s - {time_status['end_time']:.2f}s (时长: {time_status['duration']:.2f}s)"
            else:
                time_status_text = "显示全部时间范围"
            
            logger.info(f"⏰ 时间轴筛选状态: {time_status}")
            
            return fig, time_status_text, slider_value
        except Exception as e:
            logger.error(f"❌ 时间筛选后生成瀑布图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # 返回错误提示图
            error_fig = _create_empty_figure_for_callback(f"时间筛选失败: {str(e)}")
            return error_fig, "时间筛选出错，请重试", no_update


    # 时间范围输入确认回调函数
    @app.callback(
        [Output('main-plot', 'figure', allow_duplicate=True),
         Output('time-range-input-status', 'children', allow_duplicate=True),
         Output('time-filter-slider', 'min', allow_duplicate=True),
         Output('time-filter-slider', 'max', allow_duplicate=True),
         Output('time-filter-slider', 'value', allow_duplicate=True),
         Output('time-filter-slider', 'marks', allow_duplicate=True)],
        [Input('btn-confirm-time-range', 'n_clicks')],
        [State('session-id', 'data'),
         State('time-range-start-input', 'value'),
         State('time-range-end-input', 'value')],
        prevent_initial_call=True
    )
    def handle_time_range_input_confirmation(n_clicks, session_id, start_time, end_time):
        """处理时间范围输入确认"""
        logger.info(f"🔄 时间范围输入确认回调被触发: n_clicks={n_clicks}, start_time={start_time}, end_time={end_time}")
        
        if not n_clicks or n_clicks <= 0:
            logger.info("⚠️ 按钮未点击，跳过处理")
            return no_update, no_update, no_update, no_update, no_update, no_update
        
        backend = session_manager.get_backend(session_id)
        if not backend:
            logger.warning("⚠️ 无效的会话ID")
            return no_update, "无效的会话ID", no_update, no_update, no_update, no_update
        
        if start_time is None or end_time is None:
            logger.warning("⚠️ 时间范围输入为空")
            return no_update, "请输入有效的时间范围", no_update, no_update, no_update, no_update
        
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update
        
        try:
            logger.info(f"🔄 调用后端更新时间范围: start_time={start_time}, end_time={end_time}")
            # 调用后端方法更新时间范围
            success, message = backend.update_time_range_from_input(start_time, end_time)
            
            if success:
                logger.info(f"✅ 后端时间范围更新成功: {message}")
                # 重新生成瀑布图（使用新的时间范围）
                fig = backend.generate_waterfall_plot()
                
                # 更新滑动条的范围和当前值
                new_min = int(start_time)
                new_max = int(end_time)
                new_value = [new_min, new_max]
                
                # 创建新的标记点
                range_size = new_max - new_min
                if range_size <= 1000:
                    step = max(1, range_size // 5)
                elif range_size <= 10000:
                    step = max(10, range_size // 10)
                else:
                    step = max(100, range_size // 20)
                
                new_marks = {}
                for i in range(new_min, new_max + 1, step):
                    if i == new_min or i == new_max or (i - new_min) % (step * 2) == 0:
                        new_marks[i] = str(i)
                
                logger.info(f"✅ 时间范围更新成功: {message}")
                logger.info(f"⏰ 更新滑动条范围: min={new_min}, max={new_max}, value={new_value}")
                logger.info(f"⏰ 新标记点: {new_marks}")
                status_message = f"✅ {message}"
                status_style = {'color': '#28a745', 'fontWeight': 'bold'}
                
                return fig, html.Span(status_message, style=status_style), new_min, new_max, new_value, new_marks
            else:
                logger.warning(f"⚠️ 时间范围更新失败: {message}")
                status_message = f"❌ {message}"
                status_style = {'color': '#dc3545', 'fontWeight': 'bold'}
                
                return no_update, html.Span(status_message, style=status_style), no_update, no_update, no_update, no_update
                
        except Exception as e:
            logger.error(f"❌ 时间范围输入确认失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            error_message = f"❌ 时间范围更新失败: {str(e)}"
            error_style = {'color': '#dc3545', 'fontWeight': 'bold'}
            
            return no_update, html.Span(error_message, style=error_style), no_update, no_update, no_update, no_update


    # 重置显示时间范围回调函数
    @app.callback(
        [Output('main-plot', 'figure', allow_duplicate=True),
         Output('time-range-input-status', 'children', allow_duplicate=True),
         Output('time-filter-slider', 'min', allow_duplicate=True),
         Output('time-filter-slider', 'max', allow_duplicate=True),
         Output('time-filter-slider', 'value', allow_duplicate=True),
         Output('time-filter-slider', 'marks', allow_duplicate=True)],
        [Input('btn-reset-display-time-range', 'n_clicks')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_reset_display_time_range(n_clicks, session_id):
        """处理重置显示时间范围"""
        if not n_clicks or n_clicks <= 0:
            return no_update, no_update, no_update, no_update, no_update, no_update
        
        backend = session_manager.get_backend(session_id)
        if not backend:
            logger.warning("⚠️ 无效的会话ID")
            return no_update, "无效的会话ID", no_update, no_update, no_update, no_update
        
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update
        
        try:
            # 重置显示时间范围
            backend.reset_display_time_range()
            
            # 重新生成瀑布图
            fig = backend.generate_waterfall_plot()
            
            # 获取原始数据时间范围并重置滑动条到原始范围
            original_min, original_max = backend.get_time_range()
            new_value = [int(original_min), int(original_max)]
            
            logger.info("✅ 显示时间范围重置成功")
            status_message = "✅ 显示时间范围已重置到原始数据范围"
            status_style = {'color': '#28a745', 'fontWeight': 'bold'}
            
            return fig, html.Span(status_message, style=status_style), no_update, no_update, new_value, no_update
                
        except Exception as e:
            logger.error(f"❌ 重置显示时间范围失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            error_message = f"❌ 重置显示时间范围失败: {str(e)}"
            error_style = {'color': '#dc3545', 'fontWeight': 'bold'}
            
            return no_update, html.Span(error_message, style=error_style), no_update, no_update, no_update, no_update


    # 已移除全局延迟统计图表相关回调（使用数据统计概览中的平均时延替代）

    # 偏移对齐分析 - 页面加载时自动生成（无需点击按钮）
    @app.callback(
        Output('offset-alignment-plot', 'figure', allow_duplicate=True),
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
                logger.warning("⚠️ 没有激活的算法，无法生成偏移对齐分析")
                empty = backend.plot_generator._create_empty_plot("没有激活的算法")
                return empty, []
            
            fig = backend.generate_offset_alignment_plot()
            table_data = backend.get_offset_alignment_data()
            logger.info("✅ 偏移对齐分析（自动）生成成功")
            return fig, table_data
            
        except Exception as e:
            logger.error(f"❌ 自动生成偏移对齐分析失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            empty = backend.plot_generator._create_empty_plot(f"生成失败: {str(e)}")
            return empty, no_update

    # 按键与延时散点图自动生成回调函数 - 当报告内容加载时自动生成
    @app.callback(
        [Output('key-delay-scatter-plot', 'figure'),
         Output('key-delay-zscore-scatter-plot', 'figure')],
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_generate_scatter_plot(report_content, session_id):
        """处理按键与延时散点图自动生成 - 当报告内容更新时触发"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update, no_update
        
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update, no_update
        
        try:
            # 检查是否有分析数据
            if not backend.analyzer and not (hasattr(backend, 'multi_algorithm_mode') and backend.multi_algorithm_mode):
                logger.warning("⚠️ 没有分析器，无法生成散点图")
                empty = backend.plot_generator._create_empty_plot("没有分析器")
                return empty, empty
            
            # 生成按键与延时散点图
            fig = backend.generate_key_delay_scatter_plot()
            
            # 生成Z-Score标准化散点图
            zscore_fig = backend.generate_key_delay_zscore_scatter_plot()
            
            # 验证Z-Score图表是否正确生成
            if zscore_fig and hasattr(zscore_fig, 'data') and len(zscore_fig.data) > 0:
                # 检查第一个数据点的y值是否是Z-Score（应该在-3到3之间，而不是原始的延时值）
                first_trace = zscore_fig.data[0]
                if hasattr(first_trace, 'y') and len(first_trace.y) > 0:
                    first_y = first_trace.y[0] if hasattr(first_trace.y, '__getitem__') else first_trace.y
                    logger.info(f"🔍 Z-Score图表验证: 第一个数据点的y值={first_y} (应该是Z-Score值，通常在-3到3之间)")
            
            logger.info("✅ 按键与延时散点图和Z-Score标准化散点图生成成功")
            return fig, zscore_fig
            
        except Exception as e:
            logger.error(f"❌ 生成散点图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            empty = backend.plot_generator._create_empty_plot(f"生成失败: {str(e)}")
            return empty, empty

    # 锤速与延时散点图自动生成回调函数 - 当报告内容加载时自动生成
    @app.callback(
        Output('hammer-velocity-delay-scatter-plot', 'figure'),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_generate_hammer_velocity_scatter_plot(report_content, session_id):
        """处理锤速与延时散点图自动生成 - 当报告内容更新时触发"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update
        
        try:
            # 检查是否有激活的算法
            active_algorithms = backend.get_active_algorithms()
            if not active_algorithms:
                logger.warning("⚠️ 没有激活的算法，无法生成散点图")
                return backend.plot_generator._create_empty_plot("没有激活的算法")
            
            # 生成锤速与延时散点图
            fig = backend.generate_hammer_velocity_delay_scatter_plot()
            
            logger.info("✅ 锤速与延时散点图生成成功")
            return fig
            
        except Exception as e:
            logger.error(f"❌ 生成散点图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            return backend.plot_generator._create_empty_plot(f"生成散点图失败: {str(e)}")

    # 延时与按键分析图表自动生成回调函数 - 已注释，因为箱线图与柱状图的均值子图重复
    # @app.callback(
    #     [Output('delay-by-key-boxplot', 'figure'),
    #      Output('delay-by-key-analysis-stats', 'children')],
    #     [Input('report-content', 'children')],
    #     [State('session-id', 'data')],
    #     prevent_initial_call=True
    # )
    # def handle_generate_delay_by_key_analysis(report_content, session_id):
    #     """处理延时与按键关系分析图表生成"""
    #     if not session_id or session_id not in backends:
    #         return no_update, []
    #     
    #     backend = backends[session_id]
    #     
    #     try:
    #         if not backend.analyzer:
    #             logger.warning("⚠️ 没有分析器，无法生成分析图表")
    #             empty_fig = backend.plot_generator._create_empty_plot("没有分析器")
    #             return empty_fig, []
    #         
    #         # 生成图表和分析结果
    #         plots_result = backend.generate_delay_by_key_analysis_plots()
    #         analysis_result = plots_result.get('analysis_result', {})
    #         
    #         # 生成统计结果表格
    #         stats_html = _create_delay_by_key_stats_html(analysis_result)
    #         
    #         logger.info("✅ 延时与按键关系分析图表生成成功")
    #         return plots_result.get('boxplot', {}), stats_html
    #         
    #     except Exception as e:
    #         logger.error(f"❌ 生成延时与按键分析图表失败: {e}")
    #         import traceback
    #         logger.error(traceback.format_exc())
    #         empty_fig = backend.plot_generator._create_empty_plot(f"生成失败: {str(e)}")
    #         return empty_fig, []

    # 延时与锤速分析图表自动生成回调函数 - 已注释
    # @app.callback(
    #     [Output('delay-by-velocity-analysis-plot', 'figure'),
    #      Output('delay-by-velocity-analysis-stats', 'children')],
    #     [Input('report-content', 'children')],
    #     [State('session-id', 'data')],
    #     prevent_initial_call=True
    # )
    # def handle_generate_delay_by_velocity_analysis(report_content, session_id):
    #     """处理延时与锤速关系分析图表生成"""
    #     if not session_id or session_id not in backends:
    #         return no_update, []
    #     
    #     backend = backends[session_id]
    #     
    #     try:
    #         if not backend.analyzer:
    #             logger.warning("⚠️ 没有分析器，无法生成分析图表")
    #             empty_fig = backend.plot_generator._create_empty_plot("没有分析器")
    #             return empty_fig, []
    #         
    #         # 生成图表
    #         fig = backend.generate_delay_by_velocity_analysis_plot()
    #         
    #         # 获取分析结果并生成统计结果表格
    #         analysis_result = backend.get_delay_by_velocity_analysis()
    #         stats_html = _create_delay_by_velocity_stats_html(analysis_result)
    #         
    #         logger.info("✅ 延时与锤速关系分析图表生成成功")
    #         return fig, stats_html
    #         
    #     except Exception as e:
    #         logger.error(f"❌ 生成延时与锤速分析图表失败: {e}")
    #         import traceback
    #         logger.error(traceback.format_exc())
    #         empty_fig = backend.plot_generator._create_empty_plot(f"生成失败: {str(e)}")
    #         return empty_fig, []

    # 按键与锤速散点图自动生成回调函数（颜色表示延时）- 当报告内容加载时自动生成
    @app.callback(
        Output('key-hammer-velocity-scatter-plot', 'figure'),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_generate_key_hammer_velocity_scatter_plot(report_content, session_id):
        """处理按键与锤速散点图自动生成（颜色表示延时）- 当报告内容更新时触发"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update
        
        try:
            # 检查是否在多算法模式
            # 检查是否有激活的算法
            active_algorithms = backend.get_active_algorithms()
            if not active_algorithms:
                logger.warning("⚠️ 没有激活的算法，无法生成散点图")
                return backend.plot_generator._create_empty_plot("没有激活的算法")
            
            # 生成按键与锤速散点图（颜色表示延时）
            fig = backend.generate_key_hammer_velocity_scatter_plot()
            
            logger.info("✅ 按键与锤速散点图生成成功")
            return fig
            
        except Exception as e:
            logger.error(f"❌ 生成散点图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            return backend.plot_generator._create_empty_plot(f"生成散点图失败: {str(e)}")

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
                logger.warning("⚠️ 没有激活的算法，无法生成延时直方图")
                return backend.plot_generator._create_empty_plot("没有激活的算法")
            
            fig = backend.generate_delay_histogram_plot()
            logger.info("✅ 延时直方图生成成功")
            return fig
        except Exception as e:
            logger.error(f"❌ 生成延时直方图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return backend.plot_generator._create_empty_plot(f"生成直方图失败: {str(e)}")

    # ==================== 多算法对比模式回调 ====================
    
    # 多算法模式初始化回调 - 在会话初始化时自动触发
    @app.callback(
        [Output('multi-algorithm-upload-area', 'style'),
         Output('multi-algorithm-upload-area', 'children'),
         Output('multi-algorithm-management-area', 'style'),
         Output('multi-algorithm-management-area', 'children'),
         Output('main-plot', 'figure', allow_duplicate=True),
         Output('report-content', 'children', allow_duplicate=True)],
        [Input('session-id', 'data')],
        prevent_initial_call='initial_duplicate',
        prevent_duplicate=True
    )
    def initialize_multi_algorithm_mode(session_id):
        """初始化多算法模式 - 确保上传区域和管理区域显示"""
        logger.info(f"🔄 初始化多算法模式: session_id={session_id}")
        
        if not session_id:
            return no_update, no_update, no_update, no_update, no_update, no_update
        
        session_id, backend = session_manager.get_or_create_backend(session_id)
        if not backend:
            logger.warning("⚠️ 无法获取backend实例")
            return no_update, no_update, no_update, no_update, no_update, no_update
        
        try:
            # 多算法模式始终启用
            # 确保multi_algorithm_manager已初始化
            if not backend.multi_algorithm_manager:
                backend._ensure_multi_algorithm_manager()
            has_existing_data = False
            existing_filename = None
            logger.info("✅ 多算法模式已就绪")
            
            success = True
            if success:
                upload_style = {'display': 'block'}
                try:
                    upload_area = create_multi_algorithm_upload_area()
                    logger.info("✅ 创建多算法上传区域成功")
                except Exception as e:
                    logger.error(f"❌ 创建多算法上传区域失败: {e}")
                    upload_area = html.Div("上传区域创建失败", style={'color': '#dc3545'})
                
                management_style = {'display': 'block'}
                try:
                    management_area = create_multi_algorithm_management_area()
                    logger.info("✅ 创建多算法管理区域成功")
                except Exception as e:
                    logger.error(f"❌ 创建多算法管理区域失败: {e}")
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
            if active_algorithms:
                try:
                    logger.info(f"🔄 更新瀑布图，共 {len(active_algorithms)} 个激活算法")
                    plot_fig = backend.generate_waterfall_plot()
                    report_content = create_report_layout(backend)
                except Exception as e:
                    logger.error(f"❌ 更新瀑布图失败: {e}")
                    plot_fig = _create_empty_figure_for_callback(f"更新失败: {str(e)}")
                    # 使用 create_report_layout 确保包含所有必需的组件
                    try:
                        report_content = create_report_layout(backend)
                    except:
                        # 如果 create_report_layout 也失败，返回包含必需组件的错误布局
                        empty_fig = {}
                        report_content = html.Div([
                            html.H4("更新失败", className="text-center text-danger"),
                            html.P(f"错误信息: {str(e)}", className="text-center"),
                            # 包含所有必需的图表组件（隐藏），确保回调函数不会报错
                            dcc.Graph(id='key-delay-scatter-plot', figure=empty_fig, style={'display': 'none'}),
                            dcc.Graph(id='key-delay-zscore-scatter-plot', figure=empty_fig, style={'display': 'none'}),
                            dcc.Graph(id='hammer-velocity-delay-scatter-plot', figure=empty_fig, style={'display': 'none'}),
                            dcc.Graph(id='key-hammer-velocity-scatter-plot', figure=empty_fig, style={'display': 'none'}),
                            dcc.Graph(id='offset-alignment-plot', figure=empty_fig, style={'display': 'none'}),
                            html.Div([
                                dash_table.DataTable(
                                    id='offset-alignment-table',
                                    data=[],
                                    columns=[]
                                )
                            ], style={'display': 'none'})
                        ])
            
            logger.info(f"✅ 多算法模式初始化完成")
            return upload_style, upload_area, management_style, management_area, plot_fig, report_content
            
        except Exception as e:
            logger.error(f"❌ 初始化多算法模式失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return (
                {'display': 'block'}, 
                html.Div("初始化失败", style={'color': '#dc3545'}), 
                {'display': 'block'}, 
                html.Div("初始化失败", style={'color': '#dc3545'}), 
                no_update, 
                no_update
            )
    
    @app.callback(
        [Output('multi-algorithm-upload-area', 'style', allow_duplicate=True),
         Output('multi-algorithm-management-area', 'style', allow_duplicate=True),
         Output('multi-algorithm-file-list', 'children'),
         Output('multi-algorithm-upload-status', 'children'),
         Output('multi-algorithm-files-store', 'data')],
        [Input('upload-multi-algorithm-data', 'contents')],
        [State('upload-multi-algorithm-data', 'filename'),
         State('session-id', 'data'),
         State('multi-algorithm-files-store', 'data')],
        prevent_initial_call=True,
        prevent_duplicate=True
    )
    def handle_multi_file_upload(contents_list, filename_list, session_id, store_data):
        """处理多文件上传，显示文件列表供用户输入算法名称"""
        # 获取后端实例
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update, no_update, no_update, no_update, no_update
        
        # 确保多算法模式已启用
        # 确保multi_algorithm_manager已初始化
        if not backend.multi_algorithm_manager:
            backend._ensure_multi_algorithm_manager()
        
        # 确保上传区域和管理区域始终显示
        upload_style = {'display': 'block'}
        management_style = {'display': 'block'}
        
        # 使用MultiFileUploadHandler处理文件上传
        upload_handler = MultiFileUploadHandler()
        file_list, status_text, new_store_data = upload_handler.process_uploaded_files(contents_list, filename_list, store_data)
        
        return upload_style, management_style, file_list, status_text, new_store_data
    
    @app.callback(
        Output({'type': 'algorithm-status', 'index': dash.dependencies.MATCH}, 'children'),
        [Input({'type': 'confirm-algorithm-btn', 'index': dash.dependencies.MATCH}, 'n_clicks')],
        [State({'type': 'algorithm-name-input', 'index': dash.dependencies.MATCH}, 'value'),
         State({'type': 'confirm-algorithm-btn', 'index': dash.dependencies.MATCH}, 'id'),
         State('multi-algorithm-files-store', 'data'),
         State('session-id', 'data')],
        prevent_initial_call=True
    )
    def confirm_add_algorithm(n_clicks, algorithm_name, button_id, store_data, session_id):
        """确认添加算法"""
        if not n_clicks or not algorithm_name or not algorithm_name.strip():
            return html.Span("请输入算法名称", style={'color': '#ffc107'})
        
        # 获取后端实例
        backend = session_manager.get_backend(session_id)
        if not backend:
            return html.Span("会话无效", style={'color': '#dc3545'})
        
        # 确保多算法模式已启用
        # 确保multi_algorithm_manager已初始化
        if not backend.multi_algorithm_manager:
            backend._ensure_multi_algorithm_manager()
        
        if not store_data or 'contents' not in store_data or 'filenames' not in store_data:
            return html.Span("文件数据丢失，请重新上传", style={'color': '#dc3545'})
        
        try:
            # 使用MultiFileUploadHandler获取文件数据
            upload_handler = MultiFileUploadHandler()
            file_id = button_id['index']
            file_data = upload_handler.get_file_data_by_id(file_id, store_data)
            
            if not file_data:
                return html.Span("文件数据无效", style={'color': '#dc3545'})
            
            content, filename = file_data
            algorithm_name = algorithm_name.strip()
            
            # 异步添加算法
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success, error_msg = loop.run_until_complete(
                backend.add_algorithm(algorithm_name, filename, content)
            )
            loop.close()
            
            if success:
                # 确保新添加的算法默认显示（is_active 应该已经是 True，但确保一下）
                algorithm = backend.multi_algorithm_manager.get_algorithm(algorithm_name) if hasattr(backend, 'multi_algorithm_manager') else None
                if algorithm:
                    algorithm.is_active = True
                    logger.info(f"✅ 确保算法 '{algorithm_name}' 默认显示: is_active={algorithm.is_active}")
                logger.info(f"✅ 算法 '{algorithm_name}' 添加成功")
                return html.Span("✅ 添加成功", style={'color': '#28a745', 'fontWeight': 'bold'})
            else:
                return html.Span(f"❌ {error_msg}", style={'color': '#dc3545'})
            
        except Exception as e:
            logger.error(f"❌ 添加算法失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return html.Span(f"添加失败: {str(e)}", style={'color': '#dc3545'})
    
    @app.callback(
        Output('algorithm-list-trigger', 'data'),
        [Input({'type': 'algorithm-status', 'index': dash.dependencies.ALL}, 'children'),
         Input('confirm-migrate-existing-data-btn', 'n_clicks')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def trigger_algorithm_list_update(status_children, migrate_clicks, session_id):
        """当算法状态改变时触发算法列表更新"""
        import time
        # 当算法状态改变或迁移按钮被点击时，触发列表更新
        # 这会在算法添加成功后自动触发，因为 algorithm-status 会更新
        # status_children 可能是 None 或空列表（当没有算法时），需要处理
        if status_children is None:
            status_children = []
        trigger_value = time.time()
        logger.info(f"🔄 触发算法列表更新: trigger_value={trigger_value}, status_children数量={len(status_children) if status_children else 0}")
        return trigger_value
    
    @app.callback(
        [Output('main-plot', 'figure', allow_duplicate=True),
         Output('report-content', 'children', allow_duplicate=True)],
        [Input('algorithm-list-trigger', 'data'),
         Input({'type': 'algorithm-toggle', 'index': dash.dependencies.ALL}, 'value')],
        [State('session-id', 'data')],
        prevent_duplicate=True,
        prevent_initial_call=True
    )
    def update_plot_on_algorithm_change(trigger_data, toggle_values, session_id):
        """当算法添加/删除/切换时，自动更新瀑布图和报告"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update, no_update
        
        # 确保多算法模式已启用
        # 确保multi_algorithm_manager已初始化
        if not backend.multi_algorithm_manager:
            backend._ensure_multi_algorithm_manager()
        
        # 检查是否有激活的算法
        active_algorithms = backend.get_active_algorithms()
        if not active_algorithms:
            # 没有激活的算法，显示空图表
            empty_fig = _create_empty_figure_for_callback("请至少激活一个算法以查看瀑布图")
            # 使用 create_report_layout 确保包含所有必需的组件
            empty_report = create_report_layout(backend)
            return empty_fig, empty_report
        
        try:
            # 生成多算法瀑布图
            logger.info(f"🔄 更新多算法瀑布图，共 {len(active_algorithms)} 个激活算法")
            fig = backend.generate_waterfall_plot()
            
            # 生成报告内容（多算法模式下的报告）
            report_content = create_report_layout(backend)
            
            logger.info("✅ 多算法瀑布图和报告更新完成")
            return fig, report_content
            
        except Exception as e:
            logger.error(f"❌ 更新多算法瀑布图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            error_fig = _create_empty_figure_for_callback(f"更新失败: {str(e)}")
            # 使用 create_report_layout 确保包含所有必需的组件
            try:
                error_report = create_report_layout(backend)
            except:
                # 如果 create_report_layout 也失败，返回包含必需组件的错误布局
                empty_fig = {}
                error_report = html.Div([
                    html.H4("更新失败", className="text-center text-danger"),
                    html.P(f"错误信息: {str(e)}", className="text-center"),
                    # 包含所有必需的图表组件（隐藏），确保回调函数不会报错
                    dcc.Graph(id='key-delay-scatter-plot', figure=empty_fig, style={'display': 'none'}),
                    dcc.Graph(id='key-delay-zscore-scatter-plot', figure=empty_fig, style={'display': 'none'}),
                    dcc.Graph(id='hammer-velocity-delay-scatter-plot', figure=empty_fig, style={'display': 'none'}),
                    dcc.Graph(id='key-hammer-velocity-scatter-plot', figure=empty_fig, style={'display': 'none'}),
                    dcc.Graph(id='offset-alignment-plot', figure=empty_fig, style={'display': 'none'}),
                    html.Div([
                        dash_table.DataTable(
                            id='offset-alignment-table',
                            data=[],
                            columns=[]
                        )
                    ], style={'display': 'none'})
                ])
            return error_fig, error_report
    
    @app.callback(
        [Output('existing-data-migration-area', 'style'),
         Output('existing-data-migration-area', 'children')],
        [Input('session-id', 'data'),
         Input('confirm-migrate-existing-data-btn', 'n_clicks')],
        [State('existing-data-algorithm-name-input', 'value')],
        prevent_initial_call=True
    )
    def handle_existing_data_migration(session_id_trigger, migrate_clicks, algorithm_name):
        """处理现有数据迁移区域的显示和迁移操作"""
        logger.info(f"🔄 handle_existing_data_migration: migrate_clicks={migrate_clicks}")
        
        # 从 session_id_trigger 获取 session_id（它可能是 None 或实际值）
        session_id = session_id_trigger if session_id_trigger else None
        
        backend = session_manager.get_backend(session_id)
        if not backend:
            logger.warning("⚠️ 无法获取backend实例（handle_existing_data_migration）")
            return {'display': 'none'}, None
        
        ctx = callback_context
        if not ctx.triggered:
            return {'display': 'none'}, None
        
        trigger_id = ctx.triggered[0]['prop_id']
        logger.info(f"🔍 触发源: {trigger_id}")
        
        try:
            # 如果是会话初始化触发
            if 'session-id' in trigger_id:
                # 多算法模式始终启用
                logger.info("ℹ️ 多算法模式始终启用")
                
                # 检查是否有现有分析数据
                has_existing_data = False
                existing_filename = None
                
                try:
                    if backend.analyzer and backend.analyzer.note_matcher and hasattr(backend.analyzer, 'matched_pairs') and len(backend.analyzer.matched_pairs) > 0:
                        has_existing_data = True
                        data_source_info = backend.get_data_source_info()
                        existing_filename = data_source_info.get('filename', '未知文件')
                        logger.info(f"✅ 检测到现有分析数据: {existing_filename}")
                except Exception as e:
                    logger.warning(f"⚠️ 检查现有数据时出错: {e}")
                    has_existing_data = False
                
                if has_existing_data:
                    # 显示迁移提示（按钮和输入框在布局中已定义，通过显示它们）
                    migration_area = dbc.Alert([
                        html.H6("检测到现有分析数据", className="mb-2", style={'fontWeight': 'bold'}),
                        html.P(f"文件: {existing_filename}", style={'fontSize': '14px', 'marginBottom': '10px'}),
                        html.P("请为这个算法输入名称，以便在多算法模式下进行对比：", style={'fontSize': '14px', 'marginBottom': '10px'}),
                        html.Div(id='migration-components-placeholder', children=[
                            html.P("请在下方输入算法名称并点击确认迁移按钮", style={'fontSize': '12px', 'color': '#6c757d'})
                        ])
                    ], color='info', className='mb-3')
                    logger.info("✅ 显示迁移提示区域")
                    return {'display': 'block'}, migration_area
                else:
                    logger.info("ℹ️ 没有现有数据需要迁移")
                    return {'display': 'none'}, None
            
            # 如果是迁移按钮触发
            elif 'confirm-migrate-existing-data-btn' in trigger_id:
                if not migrate_clicks or not algorithm_name or not algorithm_name.strip():
                    return no_update, no_update
                
                try:
                    # 确保multi_algorithm_manager已初始化
                    if not backend.multi_algorithm_manager:
                        backend._ensure_multi_algorithm_manager()
                    
                    algorithm_name = algorithm_name.strip()
                    logger.info(f"📤 开始迁移现有数据到算法: {algorithm_name}")
                    success, error_msg = backend.migrate_existing_data_to_algorithm(algorithm_name)
                    
                    if success:
                        # 隐藏迁移区域
                        logger.info("✅ 数据迁移成功")
                        return {'display': 'none'}, None
                    else:
                        # 显示错误信息
                        logger.error(f"❌ 数据迁移失败: {error_msg}")
                        error_alert = dbc.Alert([
                            html.H6("迁移失败", className="mb-2", style={'fontWeight': 'bold', 'color': '#dc3545'}),
                            html.P(f"错误: {error_msg}", style={'fontSize': '14px'})
                        ], color='danger', className='mb-3')
                        return no_update, error_alert
                except Exception as e:
                    logger.error(f"❌ 迁移数据时发生异常: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    error_alert = dbc.Alert([
                        html.H6("迁移失败", className="mb-2", style={'fontWeight': 'bold', 'color': '#dc3545'}),
                        html.P(f"异常: {str(e)}", style={'fontSize': '14px'})
                    ], color='danger', className='mb-3')
                    return no_update, error_alert
            else:
                # 未知触发源
                logger.warning(f"⚠️ 未知触发源: {trigger_id}")
                return {'display': 'none'}, None
                
        except Exception as e:
            logger.error(f"❌ handle_existing_data_migration 发生异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {'display': 'none'}, None
        
        return {'display': 'none'}, None
    
    @app.callback(
        [Output('algorithm-list', 'children'),
         Output('algorithm-management-status', 'children')],
        [Input('algorithm-list-trigger', 'data')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def update_algorithm_list(trigger_data, session_id):
        """更新算法列表显示"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return [], ""
        
        backend = session_manager.get_backend(session_id)
        if not backend:
            return [], ""
        
        # 确保多算法模式已启用
        # 确保multi_algorithm_manager已初始化
        if not backend.multi_algorithm_manager:
            backend._ensure_multi_algorithm_manager()
        
        try:
            algorithms = backend.get_all_algorithms()
            
            if not algorithms:
                return [], html.Span("暂无算法，请上传文件", style={'color': '#6c757d'})
            
            algorithm_items = []
            for alg_info in algorithms:
                alg_name = alg_info['algorithm_name']
                filename = alg_info['filename']
                status = alg_info['status']
                # 获取is_active，如果未设置或为None，则默认为True（新上传的文件应该默认显示）
                is_active = alg_info.get('is_active')
                if is_active is None:
                    is_active = True
                    # 如果is_active为None，确保算法对象中的is_active也被设置为True
                    algorithm = backend.multi_algorithm_manager.get_algorithm(alg_name) if hasattr(backend, 'multi_algorithm_manager') else None
                    if algorithm:
                        algorithm.is_active = True
                        logger.info(f"✅ 确保算法 '{alg_name}' 默认显示: is_active={is_active}")
                color = alg_info['color']
                is_ready = alg_info['is_ready']
                
                # 状态图标
                if status == 'ready' and is_ready:
                    status_icon = html.I(className="fas fa-check-circle", style={'color': '#28a745', 'marginRight': '5px'})
                    status_text = "就绪"
                elif status == 'loading':
                    status_icon = html.I(className="fas fa-spinner fa-spin", style={'color': '#17a2b8', 'marginRight': '5px'})
                    status_text = "加载中"
                elif status == 'error':
                    status_icon = html.I(className="fas fa-exclamation-circle", style={'color': '#dc3545', 'marginRight': '5px'})
                    status_text = "错误"
                else:
                    status_icon = html.I(className="fas fa-clock", style={'color': '#ffc107', 'marginRight': '5px'})
                    status_text = "等待中"
                
                # 显示/隐藏开关
                toggle_switch = dbc.Switch(
                    id={'type': 'algorithm-toggle', 'index': alg_name},
                    label='显示',
                    value=is_active,
                    style={'fontSize': '12px'}
                )
                
                algorithm_items.append(
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.Div([
                                    html.Span(alg_name, style={'fontWeight': 'bold', 'fontSize': '14px', 'color': color}),
                                    html.Br(),
                                    html.Small(filename, style={'color': '#6c757d', 'fontSize': '11px'}),
                                    html.Br(),
                                    html.Small([status_icon, status_text], style={'fontSize': '11px'})
                                ], style={'flex': '1'}),
                                html.Div([
                                    toggle_switch,
                                    dbc.Button("删除", 
                                             id={'type': 'algorithm-delete-btn', 'index': alg_name},
                                             color='danger',
                                             size='sm',
                                             n_clicks=0,
                                             style={'marginTop': '5px', 'width': '100%'})
                                ], style={'marginLeft': '10px'})
                            ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center'})
                        ])
                    ], className='mb-2', style={'border': f'2px solid {color}', 'borderRadius': '5px'})
                )
            
            # 创建算法列表（使用列表而不是Div，保持一致性）
            algorithm_list = algorithm_items  # 直接返回列表，Dash会自动处理
            status_text = html.Span(f"共 {len(algorithms)} 个算法", style={'color': '#6c757d'})
            
            return algorithm_list, status_text
            
        except Exception as e:
            logger.error(f"❌ 更新算法列表失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return [], html.Span(f"更新失败: {str(e)}", style={'color': '#dc3545'})
    
    @app.callback(
        [Output('algorithm-list', 'children', allow_duplicate=True),
         Output('algorithm-management-status', 'children', allow_duplicate=True),
         Output('algorithm-list-trigger', 'data', allow_duplicate=True),
         Output('multi-algorithm-file-list', 'children', allow_duplicate=True),
         Output('multi-algorithm-files-store', 'data', allow_duplicate=True)],
        [Input({'type': 'algorithm-toggle', 'index': dash.dependencies.ALL}, 'value'),
         Input({'type': 'algorithm-delete-btn', 'index': dash.dependencies.ALL}, 'n_clicks')],
        [State({'type': 'algorithm-toggle', 'index': dash.dependencies.ALL}, 'id'),
         State({'type': 'algorithm-delete-btn', 'index': dash.dependencies.ALL}, 'id'),
         State('session-id', 'data'),
         State('multi-algorithm-files-store', 'data')],
        prevent_duplicate=True,
        prevent_initial_call=True
    )
    def handle_algorithm_management(toggle_values, delete_clicks_list, toggle_ids, delete_ids, session_id, store_data):
        """处理算法管理操作（显示/隐藏、删除）"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update, no_update, no_update, no_update, no_update
        
        # 确保多算法模式已启用
        # 确保multi_algorithm_manager已初始化
        if not backend.multi_algorithm_manager:
            backend._ensure_multi_algorithm_manager()
        
        ctx = callback_context
        if not ctx.triggered:
            return no_update, no_update, no_update, no_update, no_update
        
        trigger_id = ctx.triggered[0]['prop_id']
        
        # 标记是否删除了算法，用于更新文件列表
        algorithm_deleted = False
        deleted_algorithm_filename = None
        
        try:
            # 解析 trigger_id，格式通常是 '{"type":"...","index":"..."}.property'
            import json
            trigger_prop_id = trigger_id.split('.')[0]
            try:
                trigger_data = json.loads(trigger_prop_id)
                algorithm_name = trigger_data.get('index', '')
            except (json.JSONDecodeError, KeyError):
                logger.error(f"无法解析 trigger_id: {trigger_id}")
                return no_update, no_update, no_update, no_update, no_update
            
            if 'algorithm-toggle' in trigger_id:
                # 根据开关的新值设置显示/隐藏状态（而不是切换）
                # 找到对应的开关索引和值
                if toggle_values and toggle_ids:
                    for i, toggle_id in enumerate(toggle_ids):
                        if toggle_id and toggle_id.get('index') == algorithm_name:
                            new_value = toggle_values[i] if i < len(toggle_values) else None
                            if new_value is not None:
                                # 获取算法对象
                                algorithm = backend.multi_algorithm_manager.get_algorithm(algorithm_name) if hasattr(backend, 'multi_algorithm_manager') else None
                                if algorithm:
                                    # 直接设置为新值，而不是切换
                                    if algorithm.is_active != new_value:
                                        algorithm.is_active = new_value
                                        logger.info(f"✅ 算法 '{algorithm_name}' 显示状态设置为: {'显示' if new_value else '隐藏'}")
                                    else:
                                        logger.debug(f"ℹ️ 算法 '{algorithm_name}' 显示状态未变化: {new_value}")
                            break
                else:
                    # 如果找不到对应的开关，使用切换方式（向后兼容）
                    backend.toggle_algorithm(algorithm_name)
            elif 'algorithm-delete-btn' in trigger_id:
                # 删除算法
                # 检查是否有点击（n_clicks > 0）
                if delete_clicks_list:
                    # 找到对应的按钮索引
                    for i, delete_id in enumerate(delete_ids):
                        if delete_id and delete_id.get('index') == algorithm_name:
                            if delete_clicks_list[i] and delete_clicks_list[i] > 0:
                                # 在删除前获取算法信息，以便从文件列表中移除
                                algorithms_before = backend.get_all_algorithms()
                                for alg_info in algorithms_before:
                                    if alg_info['algorithm_name'] == algorithm_name:
                                        deleted_algorithm_filename = alg_info.get('filename', '')
                                        break
                                
                                backend.remove_algorithm(algorithm_name)
                                algorithm_deleted = True
                                break
                    else:
                        return no_update, no_update, no_update, no_update, no_update
                else:
                    return no_update, no_update, no_update, no_update, no_update
            else:
                return no_update, no_update, no_update, no_update, no_update
            
            # 重新获取算法列表
            algorithms = backend.get_all_algorithms()
            
            # 更新文件列表：如果删除了算法，从文件列表中移除对应的文件
            file_list_children = no_update
            updated_store_data = no_update
            
            if algorithm_deleted and store_data and deleted_algorithm_filename:
                # 获取所有已添加算法的文件名
                added_filenames = set()
                for alg_info in algorithms:
                    added_filenames.add(alg_info.get('filename', ''))
                
                # 从store_data中获取文件列表
                if 'contents' in store_data and 'filenames' in store_data:
                    contents_list = store_data.get('contents', [])
                    filenames_list = store_data.get('filenames', [])
                    file_ids = store_data.get('file_ids', [])
                    
                    # 过滤出未添加的文件
                    filtered_contents = []
                    filtered_filenames = []
                    filtered_file_ids = []
                    
                    for i, filename in enumerate(filenames_list):
                        if filename not in added_filenames:
                            if i < len(contents_list):
                                filtered_contents.append(contents_list[i])
                            filtered_filenames.append(filename)
                            if i < len(file_ids):
                                filtered_file_ids.append(file_ids[i])
                    
                    # 更新store_data
                    updated_store_data = {
                        'contents': filtered_contents,
                        'filenames': filtered_filenames,
                        'file_ids': filtered_file_ids
                    }
                    
                    # 重新生成文件列表UI
                    if filtered_contents and filtered_filenames:
                        from ui.multi_file_upload_handler import MultiFileUploadHandler
                        upload_handler = MultiFileUploadHandler()
                        file_list_children, _, _ = upload_handler.process_uploaded_files(
                            filtered_contents, 
                            filtered_filenames, 
                            updated_store_data
                        )
                    else:
                        # 如果没有文件了，返回空列表
                        file_list_children = []
                        updated_store_data = {'contents': [], 'filenames': [], 'file_ids': []}
            
            if not algorithms:
                # 返回空列表和状态文本，以及触发更新
                import time
                empty_list = []  # 空列表，而不是 Div
                status_text = html.Span("暂无算法，请上传文件", style={'color': '#6c757d'})
                # 如果没有算法了，也清空文件列表
                if file_list_children == no_update:
                    file_list_children = []
                if updated_store_data == no_update:
                    updated_store_data = {'contents': [], 'filenames': [], 'file_ids': []}
                return empty_list, status_text, time.time(), file_list_children, updated_store_data
            
            algorithm_items = []
            for alg_info in algorithms:
                alg_name = alg_info['algorithm_name']
                filename = alg_info['filename']
                status = alg_info['status']
                is_active = alg_info['is_active']
                color = alg_info['color']
                is_ready = alg_info['is_ready']
                
                if status == 'ready' and is_ready:
                    status_icon = html.I(className="fas fa-check-circle", style={'color': '#28a745', 'marginRight': '5px'})
                    status_text = "就绪"
                elif status == 'loading':
                    status_icon = html.I(className="fas fa-spinner fa-spin", style={'color': '#17a2b8', 'marginRight': '5px'})
                    status_text = "加载中"
                elif status == 'error':
                    status_icon = html.I(className="fas fa-exclamation-circle", style={'color': '#dc3545', 'marginRight': '5px'})
                    status_text = "错误"
                else:
                    status_icon = html.I(className="fas fa-clock", style={'color': '#ffc107', 'marginRight': '5px'})
                    status_text = "等待中"
                
                toggle_switch = dbc.Switch(
                    id={'type': 'algorithm-toggle', 'index': alg_name},
                    label='显示',
                    value=is_active,
                    style={'fontSize': '12px'}
                )
                
                algorithm_items.append(
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.Div([
                                    html.Span(alg_name, style={'fontWeight': 'bold', 'fontSize': '14px', 'color': color}),
                                    html.Br(),
                                    html.Small(filename, style={'color': '#6c757d', 'fontSize': '11px'}),
                                    html.Br(),
                                    html.Small([status_icon, status_text], style={'fontSize': '11px'})
                                ], style={'flex': '1'}),
                                html.Div([
                                    toggle_switch,
                                    dbc.Button("删除", 
                                             id={'type': 'algorithm-delete-btn', 'index': alg_name},
                                             color='danger',
                                             size='sm',
                                             n_clicks=0,
                                             style={'marginTop': '5px', 'width': '100%'})
                                ], style={'marginLeft': '10px'})
                            ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center'})
                        ])
                    ], className='mb-2', style={'border': f'2px solid {color}', 'borderRadius': '5px'})
                )
            
            # 创建算法列表（使用列表而不是Div，保持一致性）
            algorithm_list = algorithm_items  # 直接返回列表，Dash会自动处理
            status_text = html.Span(f"共 {len(algorithms)} 个算法", style={'color': '#6c757d'})
            
            # 更新触发 Store，以便触发算法列表更新
            import time
            return algorithm_list, status_text, time.time(), file_list_children, updated_store_data
            
        except Exception as e:
            logger.error(f"❌ 处理算法管理操作失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return no_update, no_update, no_update, no_update, no_update
    
    # 按键延时分析表格点击回调 - 显示按键曲线对比（悬浮窗）
    @app.callback(
        [Output('key-curves-modal', 'style'),
         Output('key-curves-comparison-container', 'children')],
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
        from dash import callback_context
        
        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            logger.debug("⚠️ 按键表格点击回调：没有触发源")
            return current_style, []
        
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        logger.info(f"🔄 按键表格点击回调触发：trigger_id={trigger_id}")
        
        # 如果点击了关闭按钮，隐藏模态框
        if trigger_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            logger.info("✅ 关闭按键曲线对比模态框")
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
        
        # 如果是表格点击
        if trigger_id == 'offset-alignment-table':
            logger.info(f"🔄 表格点击：active_cell={active_cell}, table_data长度={len(table_data) if table_data else 0}")
            backend = session_manager.get_backend(session_id)
            if not backend:
                logger.warning("⚠️ 没有找到backend")
                return current_style, []
            if not active_cell or not table_data:
                logger.warning("⚠️ active_cell或table_data为空")
                return current_style, []
            
            try:
                # 获取点击的行数据
                row_idx = active_cell.get('row')
                if row_idx is None or row_idx >= len(table_data):
                    return current_style, []
                
                row_data = table_data[row_idx]
                algorithm_name = row_data.get('algorithm_name')
                key_id_str = row_data.get('key_id')
                
                # 跳过汇总行
                if key_id_str in ['总体', '汇总'] or not algorithm_name:
                    return current_style, []
                
                # 转换按键ID
                try:
                    key_id = int(key_id_str)
                except (ValueError, TypeError):
                    return current_style, []
                
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
                    ])]
                
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
                    ])]
                
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
                import spmid
                import plotly.graph_objects as go
                from plotly.subplots import make_subplots
                
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
                            fig.add_trace(go.Scatter(x=x_at, y=y_at, mode='lines', name='录制触后', 
                                                    line=dict(color='blue', width=2), showlegend=False), row=1, col=1)
                        if record_note1 and hasattr(record_note1, 'hammers') and not record_note1.hammers.empty:
                            x_hm = (record_note1.hammers.index + record_note1.offset) / 10.0
                            y_hm = record_note1.hammers.values
                            fig.add_trace(go.Scatter(x=x_hm, y=y_hm, mode='markers', name='录制锤子',
                                                    marker=dict(color='blue', size=6), showlegend=False), row=1, col=1)
                        if replay_note1 and hasattr(replay_note1, 'after_touch') and not replay_note1.after_touch.empty:
                            x_at = (replay_note1.after_touch.index + replay_note1.offset) / 10.0
                            y_at = replay_note1.after_touch.values
                            fig.add_trace(go.Scatter(x=x_at, y=y_at, mode='lines', name='回放触后',
                                                    line=dict(color='red', width=2), showlegend=False), row=1, col=1)
                        if replay_note1 and hasattr(replay_note1, 'hammers') and not replay_note1.hammers.empty:
                            x_hm = (replay_note1.hammers.index + replay_note1.offset) / 10.0
                            y_hm = replay_note1.hammers.values
                            fig.add_trace(go.Scatter(x=x_hm, y=y_hm, mode='markers', name='回放锤子',
                                                    marker=dict(color='red', size=6), showlegend=False), row=1, col=1)
                    
                    # 右侧：算法2的曲线
                    if alg2_pair:
                        _, _, record_note2, replay_note2, _ = alg2_pair
                        if record_note2 and hasattr(record_note2, 'after_touch') and not record_note2.after_touch.empty:
                            x_at = (record_note2.after_touch.index + record_note2.offset) / 10.0
                            y_at = record_note2.after_touch.values
                            fig.add_trace(go.Scatter(x=x_at, y=y_at, mode='lines', name='录制触后',
                                                    line=dict(color='blue', width=2), showlegend=False), row=1, col=2)
                        if record_note2 and hasattr(record_note2, 'hammers') and not record_note2.hammers.empty:
                            x_hm = (record_note2.hammers.index + record_note2.offset) / 10.0
                            y_hm = record_note2.hammers.values
                            fig.add_trace(go.Scatter(x=x_hm, y=y_hm, mode='markers', name='录制锤子',
                                                    marker=dict(color='blue', size=6), showlegend=False), row=1, col=2)
                        if replay_note2 and hasattr(replay_note2, 'after_touch') and not replay_note2.after_touch.empty:
                            x_at = (replay_note2.after_touch.index + replay_note2.offset) / 10.0
                            y_at = replay_note2.after_touch.values
                            fig.add_trace(go.Scatter(x=x_at, y=y_at, mode='lines', name='回放触后',
                                                    line=dict(color='red', width=2), showlegend=False), row=1, col=2)
                        if replay_note2 and hasattr(replay_note2, 'hammers') and not replay_note2.hammers.empty:
                            x_hm = (replay_note2.hammers.index + replay_note2.offset) / 10.0
                            y_hm = replay_note2.hammers.values
                            fig.add_trace(go.Scatter(x=x_hm, y=y_hm, mode='markers', name='回放锤子',
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
                    ])]
                
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
                
                return modal_style, rendered_rows
                
            except Exception as e:
                logger.error(f"❌ 生成按键曲线对比失败: {e}")
                import traceback
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
                ])]
        
        # 其他情况，保持当前状态
        return current_style, []
    
    # 锤速与延时散点图点击回调 - 显示曲线对比（悬浮窗）
    @app.callback(
        [Output('key-curves-modal', 'style', allow_duplicate=True),
         Output('key-curves-comparison-container', 'children', allow_duplicate=True)],
        [Input('hammer-velocity-delay-scatter-plot', 'clickData'),
         Input('close-key-curves-modal', 'n_clicks'),
         Input('close-key-curves-modal-btn', 'n_clicks')],
        [State('session-id', 'data'),
         State('key-curves-modal', 'style')],
        prevent_initial_call=True,
        prevent_duplicate=True
    )
    def handle_hammer_velocity_scatter_click(click_data, close_modal_clicks, close_btn_clicks, session_id, current_style):
        """处理锤速与延时散点图点击，显示曲线对比（悬浮窗）- 参考按键与延时Z-Score标准化散点图的逻辑"""
        from dash import callback_context
        
        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            logger.debug("⚠️ 散点图点击回调：没有触发源")
            return current_style, []
        
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        logger.info(f"🔄 散点图点击回调触发：trigger_id={trigger_id}")
        
        # 如果点击了关闭按钮，隐藏模态框
        if trigger_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            logger.info("✅ 关闭按键曲线对比模态框")
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
        
        # 如果是散点图点击
        if trigger_id == 'hammer-velocity-delay-scatter-plot':
            logger.info(f"🔄 散点图点击：click_data={click_data}")
            backend = session_manager.get_backend(session_id)
            if not backend:
                logger.warning("⚠️ 没有找到backend")
                return current_style, []
            
            if not click_data or 'points' not in click_data or not click_data['points']:
                logger.warning("⚠️ click_data为空或没有points")
                return current_style, []
            
            try:
                # 获取点击的数据点
                point = click_data['points'][0]
                logger.info(f"🔍 散点图点击 - 点击点数据: {point}")
                
                if not point.get('customdata'):
                    logger.warning("⚠️ 散点图点击 - 点没有customdata")
                    return current_style, []
                
                # 安全地提取customdata（参考Z-Score散点图的逻辑）
                raw_customdata = point['customdata']
                logger.info(f"🔍 散点图点击 - raw_customdata类型: {type(raw_customdata)}, 值: {raw_customdata}")
                
                if isinstance(raw_customdata, list) and len(raw_customdata) > 0:
                    customdata = raw_customdata[0] if isinstance(raw_customdata[0], list) else raw_customdata
                else:
                    customdata = raw_customdata
                
                # 确保customdata是列表类型
                if not isinstance(customdata, list):
                    logger.warning(f"⚠️ 散点图点击 - customdata不是列表类型: {type(customdata)}, 值: {customdata}")
                    return current_style, []
                
                logger.info(f"🔍 散点图点击 - customdata: {customdata}, 长度: {len(customdata)}")
                
                # 解析customdata
                # 单算法模式: [delay_ms, record_idx, replay_idx]
                # 多算法模式: [delay_ms, record_idx, replay_idx, algorithm_name]
                if len(customdata) < 3:
                    logger.warning(f"⚠️ customdata长度不足：{len(customdata)}")
                    return current_style, []
                
                delay_ms = customdata[0]
                record_idx = customdata[1]
                replay_idx = customdata[2]
                algorithm_name = customdata[3] if len(customdata) > 3 else None
                
                logger.info(f"🖱️ 散点图点击: 算法={algorithm_name}, record_idx={record_idx}, replay_idx={replay_idx}")
                
                # 如果是多算法模式且有算法名称，使用generate_multi_algorithm_scatter_detail_plot_by_indices
                if algorithm_name:
                    # 多算法模式：使用与Z-Score散点图相同的方法
                    detail_figure1, detail_figure2, detail_figure_combined = backend.generate_multi_algorithm_scatter_detail_plot_by_indices(
                        algorithm_name=algorithm_name,
                        record_index=record_idx,
                        replay_index=replay_idx
                    )
                    
                    logger.info(f"🔍 散点图点击回调 - 图表生成结果: figure1={detail_figure1 is not None}, figure2={detail_figure2 is not None}, figure_combined={detail_figure_combined is not None}")
                    
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
                        logger.info("✅ 散点图点击回调 - 返回模态框和图表")
                        # 将Plotly figure对象包装在dcc.Graph组件中
                        return modal_style, dcc.Graph(figure=detail_figure_combined, style={'height': '600px'})
                    else:
                        logger.warning(f"⚠️ 散点图点击回调 - 图表生成失败，部分图表为None")
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
                            html.P("图表生成失败", className="text-danger text-center")
                        ])]
                else:
                    # 单算法模式：使用generate_scatter_detail_plot_by_indices
                    detail_figure1, detail_figure2, detail_figure_combined = backend.generate_scatter_detail_plot_by_indices(
                        record_index=record_idx,
                        replay_index=replay_idx
                    )
                    
                    logger.info(f"🔍 散点图点击回调（单算法） - 图表生成结果: figure1={detail_figure1 is not None}, figure2={detail_figure2 is not None}, figure_combined={detail_figure_combined is not None}")
                    
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
                        logger.info("✅ 散点图点击回调（单算法） - 返回模态框和图表")
                        # 将Plotly figure对象包装在dcc.Graph组件中
                        return modal_style, dcc.Graph(figure=detail_figure_combined, style={'height': '600px'})
                    else:
                        logger.warning(f"⚠️ 散点图点击回调（单算法） - 图表生成失败，部分图表为None")
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
                            html.P("图表生成失败", className="text-danger text-center")
                        ])]
                
            except Exception as e:
                logger.error(f"❌ 生成曲线对比失败: {e}")
                import traceback
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
                ])]
        
        # 其他情况，保持当前状态
        return current_style, []

