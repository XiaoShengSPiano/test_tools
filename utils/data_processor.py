"""
数据处理模块 - 处理SPMID文件上传和分析的核心逻辑
"""
import base64
from dash import dcc, html, no_update
import dash_bootstrap_components as dbc
from ui.layout_components import create_report_layout
from utils.logger import Logger
logger = Logger.get_logger()



def process_file_upload(contents, filename, backend, history_manager):
    """
    处理文件上传 - 清理状态并加载新数据，解决数据源切换问题
    
    Args:
        contents: 上传文件的内容（base64编码）
        filename: 上传文件的文件名
        backend: 后端实例，用于数据加载和分析
        history_manager: 历史记录管理器，用于保存分析结果
        
    Returns:
        tuple: (info_content, error_content, error_msg)
               - info_content: 成功时的信息内容
               - error_content: 失败时的错误内容
               - error_msg: 错误信息
    """
    try:
        logger.info(f"新文件上传: {filename}")
        
        # 初始化上传状态
        _initialize_upload_state(backend, filename)
        
        # 解码文件内容
        decoded_bytes = _decode_file_contents(contents)
        
        # 加载并分析SPMID数据
        success, error_msg = _load_and_analyze_spmid_data(backend, decoded_bytes)
        
        if success:
            # 处理上传成功的情况
            return _handle_upload_success(filename, backend, history_manager)
        else:
            # 处理上传失败的情况
            return _handle_upload_failure(filename, error_msg)

    except Exception as e:
        logger.error(f"❌ 文件处理错误: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return _create_general_error_content(str(e))

def _initialize_upload_state(backend, filename):
    """初始化文件上传状态"""
    backend.clear_data_state()
    backend.set_upload_data_source(filename)

def _decode_file_contents(contents):
    """解码文件内容"""
    content_type, content_string = contents.split(',')
    return base64.b64decode(content_string)

def _load_and_analyze_spmid_data(backend, decoded_bytes):
    """加载并分析SPMID数据"""
    success = False
    error_msg = None
    
    try:
        success = backend.load_spmid_data(decoded_bytes)
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ 文件处理错误: {error_msg}")
        import traceback
        logger.error(traceback.format_exc())
    
    return success, error_msg

def _handle_upload_success(filename, backend, history_manager):
    """处理文件上传成功的情况"""
    # 保存分析结果到历史记录
    history_id = history_manager.save_analysis_result(filename, backend)
    
    # 记录成功信息
    _log_upload_success(filename, backend, history_id)
    
    # 创建成功信息内容
    info_content = _create_success_content(filename, backend, history_id)
    
    return info_content, None, None

def _handle_upload_failure(filename, error_msg):
    """处理文件上传失败的情况"""
    error_content = _create_specific_error_content(filename, error_msg)
    return None, error_content, error_msg

def _log_upload_success(filename, backend, history_id):
    """记录文件上传成功信息"""
    logger.info(f"✅ 文件上传处理完成 - {filename}")
    logger.info(f"📊 当前数据源: 文件上传 ({filename})")
    logger.info(f"🔢 异常统计: 多锤 {len(backend.multi_hammers)} 个, 丢锤 {len(backend.drop_hammers)} 个")
    logger.info(f"💾 已保存到数据库，记录ID: {history_id}")

def _create_success_content(filename, backend, history_id):
    """创建文件上传成功的内容"""
    return html.Div([
        html.H4("文件上传成功", className="text-center mb-4 text-success"),
        dbc.Card([
            dbc.CardBody([
                html.Div([
                    html.I(className="fas fa-file-upload", style={'fontSize': '48px', 'color': '#28a745', 'marginBottom': '16px'}),
                    html.H5(f"📁 {filename}", className="mb-3"),
                    html.P(f"📊 检测到异常: 多锤 {len(backend.multi_hammers)} 个, 丢锤 {len(backend.drop_hammers)} 个",
                           className="text-muted mb-3"),
                    html.P(f"💾 已保存到数据库，记录ID: {history_id}", className="text-success small mb-3"),
                    html.Hr(),
                    html.P("点击右上角的 '生成瀑布图' 或 '生成分析报告' 按钮来查看详细分析结果",
                           className="text-info text-center"),
                ], className="text-center")
            ])
        ], className="shadow-sm")
    ], className="p-4")

def _create_specific_error_content(filename, error_msg):
    """根据错误类型创建特定的错误内容"""
    if _is_track_count_error(error_msg):
        return _create_track_count_error_content(filename)
    elif _is_file_format_error(error_msg):
        return _create_file_format_error_content(filename)
    else:
        return _create_general_upload_error_content(filename, error_msg)

def _is_track_count_error(error_msg):
    """判断是否为轨道数量错误"""
    return error_msg and ("轨道" in error_msg or "track" in error_msg.lower())

def _is_file_format_error(error_msg):
    """判断是否为文件格式错误"""
    return error_msg and ("Invalid file format" in error_msg or "SPID" in error_msg or "file format" in error_msg)

def _create_track_count_error_content(filename):
    """创建轨道数量不足的错误内容"""
    return html.Div([
        html.H4("❌ SPMID文件只包含 1 个轨道，需要至少2个轨道（录制+播放）才能进行分析", className="text-center text-danger"),
        html.Div([
            html.I(className="fas fa-exclamation-triangle", style={'fontSize': '48px', 'color': '#dc3545', 'marginBottom': '16px'}),
            html.P(f"文件 {filename} 只包含单个轨道，无法进行分析。", className="text-center text-danger mb-3"),
            html.P("SPMID 文件需要包含至少2个轨道（录制轨道+播放轨道）才能进行对比分析。", className="text-center text-muted small"),
            html.P("请检查文件是否为完整的钢琴录制数据。", className="text-center text-muted small"),
        ], className="text-center")
    ], className="p-4")

def _create_file_format_error_content(filename):
    """创建文件格式错误的错误内容"""
    return html.Div([
        html.H4("文件格式错误", className="text-center text-danger"),
        html.Div([
            html.I(className="fas fa-exclamation-triangle", style={'fontSize': '48px', 'color': '#dc3545', 'marginBottom': '16px'}),
            html.P(f"文件 {filename} 格式错误，请上传正确的 SPMID 文件。", className="text-center text-danger mb-3"),
            html.P("SPMID 文件应以 .spmid 为后缀，且内容为钢琴数据专用格式。", className="text-center text-muted small"),
        ], className="text-center")
    ], className="p-4")

def _create_general_upload_error_content(filename, error_msg):
    """创建一般上传错误的错误内容"""
    return html.Div([
        html.H4("文件处理失败", className="text-center text-danger"),
        html.Div([
            html.I(className="fas fa-exclamation-triangle", style={'fontSize': '48px', 'color': '#dc3545', 'marginBottom': '16px'}),
            html.P("请检查文件格式是否正确或联系管理员。", className="text-center text-danger mb-3"),
            html.P(f"错误信息: {error_msg if error_msg else '未知错误'}", className="text-center text-muted small"),
        ], className="text-center")
    ], className="p-4")

def _create_general_error_content(error_msg):
    """创建一般错误内容"""
    return html.Div([
        html.H4("文件处理错误", className="text-center text-danger"),
        html.P(f"错误信息: {error_msg}", className="text-center")
    ])


def process_history_selection(history_id, history_manager, backend):
    """
    处理历史记录选择 - 清理状态并从数据库重新加载，解决数据源切换问题
    
    Args:
        history_id: 历史记录ID
        history_manager: 历史记录管理器
        backend: 后端实例，用于数据加载和分析
        
    Returns:
        tuple: (waterfall_fig, report_content)
               - waterfall_fig: 瀑布图对象
               - report_content: 报告内容
    """
    try:
        logger.info(f"📚 用户选择历史记录 ID: {history_id}")
        
        # 获取历史记录详情
        record_details = _get_history_record_details(history_id, history_manager)
        if not record_details:
            return _create_record_not_found_error()

        # 解析历史记录信息
        main_record, file_content, filename = _parse_history_record(record_details)
        
        # 初始化历史记录状态
        _initialize_history_state(backend, history_id, filename)
        
        # 处理历史记录内容
        if file_content:
            return _handle_history_with_file_content(backend, filename, history_id, main_record, file_content)
        else:
            return _handle_history_without_file_content(filename, main_record)

    except Exception as e:
        logger.error(f"❌ 历史记录处理错误: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return _create_history_processing_error(str(e))

def _get_history_record_details(history_id, history_manager):
    """获取历史记录详情"""
    return history_manager.get_record_details(history_id)

def _create_record_not_found_error():
    """创建历史记录不存在的错误"""
    empty_fig = _create_empty_figure("历史记录不存在")
    err_content = _create_error_content("历史记录不存在", "请选择其他历史记录")
    return empty_fig, err_content

def _parse_history_record(record_details):
    """解析历史记录信息"""
    main_record = record_details['main_record']
    file_content = record_details.get('file_content')
    filename = main_record[1]
    
    logger.info(f"📋 开始加载历史记录: {filename} (ID: {main_record[0]})")
    
    return main_record, file_content, filename

def _initialize_history_state(backend, history_id, filename):
    """初始化历史记录状态"""
    # 关键修复：无论之前的状态如何，都强制清理并设置为历史记录数据源
    backend.clear_data_state()
    backend.set_history_data_source(history_id, filename)

def _handle_history_with_file_content(backend, filename, history_id, main_record, file_content):
    """处理有文件内容的历史记录"""
    logger.info("🔄 从数据库重新分析历史文件...")
    
    # 使用存储的文件内容重新进行完整的SPMID分析
    success = backend.load_spmid_data(file_content)
    
    if success:
        return _generate_history_analysis_results(backend, filename, history_id, main_record)
    else:
        return _create_history_analysis_failure_error()

def _handle_history_without_file_content(filename, main_record):
    """处理没有文件内容的历史记录"""
    logger.warning("⚠️ 历史记录中没有文件内容，只显示基本信息")
    
    # 创建空图表
    empty_fig = _create_empty_figure(f"历史记录 - {filename}")
    
    # 创建基本信息内容
    empty_content = _create_history_basic_info_content(filename, main_record)
    
    return empty_fig, empty_content


def _generate_history_analysis_results(backend, filename, history_id, main_record):
    """生成历史记录分析结果"""
    # 记录成功信息
    _log_history_analysis_success(filename, history_id, backend)
    
    # 生成瀑布图
    waterfall_fig = _generate_history_waterfall(backend, filename, main_record)
    
    # 生成报告内容
    report_content = _generate_history_report(backend, filename, history_id)
    
    return waterfall_fig, report_content

def _log_history_analysis_success(filename, history_id, backend):
    """记录历史记录分析成功信息"""
    logger.info(f"✅ 历史记录重新分析完成")
    logger.info(f"📊 当前数据源: 历史记录 ({filename}, ID: {history_id})")
    logger.info(f"🔢 异常统计: 多锤 {len(backend.multi_hammers)} 个, 丢锤 {len(backend.drop_hammers)} 个")

def _generate_history_waterfall(backend, filename, main_record):
    """生成历史记录瀑布图"""
    try:
        waterfall_fig = backend.generate_waterfall_plot()
        # 更新图表标题包含历史记录信息
        waterfall_fig.update_layout(
            title=f"历史记录瀑布图 - {filename}<br><sub>📊 多锤:{len(backend.multi_hammers)} 丢锤:{len(backend.drop_hammers)} | 🕒 {main_record[2]}</sub>"
        )
        return waterfall_fig
    except Exception as fig_error:
        logger.warning(f"⚠️ 历史记录瀑布图生成失败: {fig_error}")
        # 生成失败时，创建包含错误信息的空图表
        return _create_fallback_waterfall(filename, backend, main_record[2], str(fig_error))

def _generate_history_report(backend, filename, history_id):
    """生成历史记录报告"""
    try:
        report_content = create_report_layout(backend)
        logger.info("✅ 历史记录分析报告生成成功")
        return report_content
    except Exception as report_error:
        logger.warning(f"⚠️ 历史记录分析报告生成失败: {report_error}")
        return _create_fallback_report(filename, backend, history_id, str(report_error))

def _create_history_analysis_failure_error():
    """创建历史记录分析失败错误"""
    empty_fig = _create_empty_figure("历史文件分析失败")
    err_content = _create_error_content("历史文件分析失败", "无法从数据库读取的文件内容进行分析")
    return empty_fig, err_content

def _create_history_basic_info_content(filename, main_record):
    """创建历史记录基本信息内容"""
    return html.Div([
        html.H4(f"历史记录 - {filename}", className="text-center mb-3"),
        html.Div([
            html.P(f"📁 文件名: {filename}", className="text-center text-muted mb-2"),
            html.P(f"📊 分析结果: 多锤 {main_record[3]} 个, 丢锤 {main_record[4]} 个, 总计 {main_record[3] + main_record[4]} 个异常", className="text-center mb-3"),
            html.P(f"🕒 历史记录时间: {main_record[2]}", className="text-center text-info small"),
            html.Hr(),
            html.P("⚠️ 此历史记录没有保存原始文件内容，无法重新生成详细分析", className="text-center text-warning")
        ])
    ], className="text-center")

def _create_history_processing_error(error_msg):
    """创建历史记录处理错误"""
    empty_fig = _create_empty_figure("历史记录处理错误")
    err_content = _create_error_content("历史记录处理错误", error_msg)
    return empty_fig, err_content


def _create_fallback_waterfall(filename, backend, timestamp, error_msg):
    """创建瀑布图生成失败时的备用内容 - 返回一个包含错误信息的空 figure"""
    import plotly.graph_objects as go

    fig = go.Figure()

    # 添加错误信息作为注释
    fig.add_annotation(
        x=0.5,
        y=0.7,
        xref="paper",
        yref="paper",
        text=f"瀑布图生成失败<br>文件: {filename}<br>时间: {timestamp}",
        showarrow=False,
        font=dict(size=16, color="red"),
        align="center"
    )

    fig.add_annotation(
        x=0.5,
        y=0.3,
        xref="paper",
        yref="paper",
        text=f"错误信息: {error_msg}",
        showarrow=False,
        font=dict(size=12, color="darkred"),
        align="center"
    )

    fig.update_layout(
        title=f"历史记录瀑布图 - {filename}",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        height=600,
        template='plotly_white'
    )

    return fig


def _create_fallback_report(filename, backend, record_id, error_msg):
    """创建分析报告生成失败时的备用内容"""
    return html.Div([
        html.H4(f"分析报告 - {filename}", className="text-center text-danger"),
        html.P(f"记录ID: {record_id}", className="text-center text-muted"),
        html.P("分析报告生成失败", className="text-center text-warning"),
        html.P(f"错误信息: {error_msg}", className="text-center text-danger small")
    ])


def _create_error_content(title, message):
    """创建错误内容"""
    return html.Div([
        html.H4(title, className="text-center text-danger"),
        html.P(message, className="text-center")
    ])


def _create_empty_figure(title):
    """创建空的Plotly figure对象"""
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
