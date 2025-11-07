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
import dash_bootstrap_components as dbc
from ui.layout_components import create_report_layout, empty_figure
from backend.piano_analysis_backend import PianoAnalysisBackend
from backend.data_manager import DataManager
from ui.ui_processor import UIProcessor
from utils.pdf_generator import PDFReportGenerator
from utils.logger import Logger

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


def register_callbacks(app, backends, history_manager):
    """注册所有回调函数"""

    @app.callback(
        Output('session-id', 'data'),
        Input('session-id', 'data'),
        prevent_initial_call=True
    )
    def init_session(session_data):
        """初始化会话ID"""
        if session_data is None:
            return str(uuid.uuid4())
        return session_data

    # 主要的数据处理回调
    @app.callback(
        [Output('main-plot', 'figure'),
         Output('report-content', 'children'),
         Output('history-dropdown', 'options'),
         Output('key-filter-dropdown', 'options'),
         Output('key-filter-status', 'children'),
         Output('key-filter-dropdown', 'value'),
         Output('time-filter-slider', 'min'),
         Output('time-filter-slider', 'max'),
         Output('time-filter-slider', 'value'),
         Output('time-filter-status', 'children')],
        [Input('upload-spmid-data', 'contents'),
         Input('history-dropdown', 'value'),
         Input('key-filter-dropdown', 'value'),
         Input('btn-show-all-keys', 'n_clicks')],
        [State('upload-spmid-data', 'filename'),
         State('session-id', 'data')],
        prevent_initial_call=True
    )
    def process_data(contents, history_id, key_filter, show_all_keys, filename, session_id):
        """处理数据的主要回调函数"""

        # 获取触发上下文
        ctx = callback_context

        # 初始化后端实例
        if session_id not in backends:
            backends[session_id] = PianoAnalysisBackend(session_id, history_manager)
        backend = backends[session_id]

        try:
            # 检测触发源
            trigger_source = _detect_trigger_source(ctx, backend, contents, filename, history_id)
            
            if trigger_source == 'skip':
                return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update

            # 根据触发源分发处理
            if trigger_source == 'upload' and contents and filename:
                return _handle_file_upload(contents, filename, backend, key_filter)
                
            elif trigger_source == 'history' and history_id:
                return _handle_history_selection(history_id, backend)
                
            else:
                # 兜底逻辑
                return _handle_fallback_logic(contents, filename, history_id, backend)

        except Exception as e:
            logger.error(f"❌ 处理数据失败: {e}")
            import traceback
            logger.error(traceback.format_exc())

            # 返回错误状态的figure和内容
            error_fig = _create_empty_figure_for_callback(f"处理失败: {str(e)}")
            error_content = html.Div([
                html.H4("处理失败", className="text-center text-danger"),
                html.P(f"错误信息: {str(e)}", className="text-center")
            ])
            return error_fig, error_content, no_update, [], "显示全部键位", [], 0, 1000, [0, 1000], "显示全部时间范围", no_update


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
        if not session_id or session_id not in backends:
            return no_update, no_update, no_update, no_update
        
        backend = backends[session_id]
        
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
        Output('detail-plot', 'figure'),
        Output('detail-plot2', 'figure'),
        Output('detail-plot-combined', 'figure')],
        [Input('main-plot', 'clickData'),
        Input('close-modal', 'n_clicks'),
        Input('close-modal-btn', 'n_clicks')],
        [State('detail-modal', 'style'),
        State('session-id', 'data')]
        )
    def update_plot(clickData, close_clicks, close_btn_clicks, current_style, session_id):
        """更新详细图表 - 支持多用户会话"""
        from dash import no_update

        # if session_id is None:
        if session_id not in backends:
            return current_style, no_update, no_update, no_update

        # 获取用户会话数据
        backend = backends[session_id]
        if backend is None:
            return current_style, no_update, no_update, no_update

        ctx = callback_context
        if not ctx.triggered:
            return current_style, no_update, no_update, no_update

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if trigger_id == 'main-plot' and clickData:
            # 从会话中获取数据
            # 检查数据是否已加载

            # 获取点击的点数据
            if 'points' in clickData and len(clickData['points']) > 0:
                point = clickData['points'][0]
                # logger.debug(f"点击点: {point}")

                if point.get('customdata') is None:
                    return current_style, no_update, no_update, no_update
                print(point['customdata'])
                key_id = point['customdata'][2]
                key_on = point['customdata'][0]
                key_off = point['customdata'][1]
                data_type = point['customdata'][4]
                index = point['customdata'][5]

                # todo
                detail_figure1, detail_figure2, detail_figure_combined = backend.generate_watefall_conbine_plot_by_index(index=index, is_record=(data_type=='record'))

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
                return modal_style, detail_figure1, detail_figure2, detail_figure_combined
            else:
                logger.warning("点击数据格式不正确")
                return current_style, no_update, no_update, no_update

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
            return modal_style, no_update, no_update, no_update

        else:
            return current_style, no_update, no_update, no_update


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
        说明：旧版要求存在 all_error_notes 才允许导出，导致“无异常时无法导出概览”。
        现在放宽条件：只要存在有效数据（任一轨或有匹配对）即可生成PDF（概览页+可选异常页）。
        """
        if not n_clicks:
            return no_update

        # 检查会话和后端实例
        if not session_id or session_id not in backends:
            return dbc.Alert("❌ 会话已过期，请刷新页面", color="warning", duration=3000)

        backend = backends[session_id]
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
        if not session_id or session_id not in backends:
            return no_update

        backend = backends[session_id]
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
        if not session_id or session_id not in backends:
            return [no_update]

        backend = backends[session_id]
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
        if not session_id or session_id not in backends:
            return no_update, no_update, no_update, no_update
        
        backend = backends[session_id]
        
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
        if not session_id or session_id not in backends:
            return no_update, no_update, no_update
        
        backend = backends[session_id]
        
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
        
        if not session_id or session_id not in backends:
            logger.warning("⚠️ 无效的会话ID")
            return no_update, "无效的会话ID", no_update, no_update, no_update, no_update
        
        if start_time is None or end_time is None:
            logger.warning("⚠️ 时间范围输入为空")
            return no_update, "请输入有效的时间范围", no_update, no_update, no_update, no_update
        
        backend = backends[session_id]
        
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
        
        if not session_id or session_id not in backends:
            logger.warning("⚠️ 无效的会话ID")
            return no_update, "无效的会话ID", no_update, no_update, no_update, no_update
        
        backend = backends[session_id]
        
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
        if not session_id or session_id not in backends:
            return no_update, no_update

        backend = backends[session_id]

        try:
            if not backend.analyzer:
                logger.warning("⚠️ 没有分析器，无法生成偏移对齐分析")
                empty = backend.plot_generator._create_empty_plot("没有分析器")
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
        Output('key-delay-scatter-plot', 'figure'),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_generate_scatter_plot(report_content, session_id):
        """处理按键与延时散点图自动生成 - 当报告内容更新时触发"""
        if not session_id or session_id not in backends:
            return no_update
        
        backend = backends[session_id]
        
        try:
            # 检查是否有分析数据
            if not backend.analyzer:
                logger.warning("⚠️ 没有分析器，无法生成散点图")
                return backend.plot_generator._create_empty_plot("没有分析器")
            
            # 生成按键与延时散点图
            fig = backend.generate_key_delay_scatter_plot()
            
            logger.info("✅ 按键与延时散点图生成成功")
            return fig
            
        except Exception as e:
            logger.error(f"❌ 生成散点图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            return backend.plot_generator._create_empty_plot(f"生成散点图失败: {str(e)}")

    # 锤速与延时散点图自动生成回调函数 - 当报告内容加载时自动生成
    @app.callback(
        Output('hammer-velocity-delay-scatter-plot', 'figure'),
        [Input('report-content', 'children')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def handle_generate_hammer_velocity_scatter_plot(report_content, session_id):
        """处理锤速与延时散点图自动生成 - 当报告内容更新时触发"""
        if not session_id or session_id not in backends:
            return no_update
        
        backend = backends[session_id]
        
        try:
            # 检查是否有分析数据
            if not backend.analyzer:
                logger.warning("⚠️ 没有分析器，无法生成散点图")
                return backend.plot_generator._create_empty_plot("没有分析器")
            
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
        if not session_id or session_id not in backends:
            return no_update
        
        backend = backends[session_id]
        
        try:
            # 检查是否有分析数据
            if not backend.analyzer:
                logger.warning("⚠️ 没有分析器，无法生成散点图")
                return backend.plot_generator._create_empty_plot("没有分析器")
            
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
        if not session_id or session_id not in backends:
            return no_update
        backend = backends[session_id]
        try:
            fig = backend.generate_delay_histogram_plot()
            return fig
        except Exception as e:
            logger.error(f"❌ 生成延时直方图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return backend.plot_generator._create_empty_plot(f"生成直方图失败: {str(e)}")

