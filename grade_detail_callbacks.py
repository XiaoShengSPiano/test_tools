"""
匹配质量评级统计详情回调控制逻辑
"""
import json
import logging
import traceback
from typing import Dict, List, Optional, Any

import dash
import plotly.graph_objects as go
from dash import Input, Output, State, html, no_update, dcc

from backend.session_manager import SessionManager
from spmid.note_matcher import MatchType
from spmid.spmid_reader import Note
from utils.constants import GRADE_RANGE_CONFIG
from backend.force_curve_analyzer import ForceCurveAnalyzer

# 日志记录器
logger = logging.getLogger(__name__)

# ==========================================
# 1. 数据工具函数 (Utilities)
# ==========================================

def get_note_matcher_from_backend(backend, algorithm_name: Optional[str] = None) -> Optional[Any]:
    """获取指定算法的 NoteMatcher 实例"""
    if algorithm_name:
        active_algorithms = backend.get_active_algorithms()
        target = next((alg for alg in active_algorithms if alg.metadata.algorithm_name == algorithm_name), None)
        return target.analyzer.note_matcher if target and target.analyzer else None
    return backend.analyzer.note_matcher if backend and backend.analyzer else None

def format_hammer_time(note: Note) -> str:
    """格式化锤击时间点（首个锤头时间 + Offset）"""
    if note and not note.hammers.empty:
        return f"{note.get_first_hammer_time():.2f}"
    return "N/A"

def format_hammer_velocity(note: Note) -> str:
    """格式化首个锤击速度"""
    if note and not note.hammers.empty:
        return f"{note.get_first_hammer_velocity():.2f}"
    return "N/A"

# ==========================================
# 2. 核心数据获取层 (Data Layer)
# ==========================================

def get_grade_detail_data(backend, grade_key: str, algorithm_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    流式获取指定匹配等级的行数据
    包含：录制/播放对比对、关键时间差计算
    """
    try:
        matcher = get_note_matcher_from_backend(backend, algorithm_name)
        if not matcher: return []
        
        matched_pairs = matcher.get_matched_pairs_with_grade()
        if not matched_pairs: return []
        
        # 建立评级映射
        match_map = {
            'correct': MatchType.EXCELLENT, 'minor': MatchType.GOOD,
            'moderate': MatchType.FAIR, 'large': MatchType.POOR, 'severe': MatchType.SEVERE
        }
        target_type = match_map.get(grade_key)
        
        detail_data = []
        for rec_note, rep_note, m_type, err_ms in matched_pairs:
            if m_type != target_type: continue
            
            # 计算差异指标 (播放相对于录制)
            k_diff = rep_note.key_on_ms - rec_note.key_on_ms
            d_diff = rep_note.duration_ms - rec_note.duration_ms

            # 计算锤击时间差和锤速差
            rec_hammer_time = rec_note.get_first_hammer_time() 
            rep_hammer_time = rep_note.get_first_hammer_time()
            hammer_time_diff = rep_hammer_time - rec_hammer_time if rec_hammer_time and rep_hammer_time else 0

            rec_hammer_velocity = rec_note.get_first_hammer_velocity()
            rep_hammer_velocity = rep_note.get_first_hammer_velocity()
            hammer_velocity_diff = rep_hammer_velocity - rec_hammer_velocity if rec_hammer_velocity and rep_hammer_velocity else 0
            
            # 基础行 (录制) - 添加配对信息以便查找
            record_row = {
                'data_type': '录制', 'global_index': rec_note.uuid, 'keyId': rec_note.id,
                'keyOn': f"{rec_note.key_on_ms:.2f}", 'keyOff': f"{rec_note.key_off_ms:.2f}",
                'hammer_times': format_hammer_time(rec_note), 'hammer_velocities': format_hammer_velocity(rec_note),
                'duration': f"{rec_note.duration_ms:.2f}", 'row_type': 'record',
                'match_status': f"误差: {err_ms:.2f}ms", 'keyon_diff': '', 'duration_diff': '', 'hammer_time_diff': '', 'hammer_velocity_diff': '',
                'record_uuid': rec_note.uuid, 'replay_uuid': rep_note.uuid  # 添加配对信息
            }
            # 对比行 (播放) - 添加配对信息以便查找
            replay_row = {
                'data_type': '播放', 'global_index': rep_note.uuid, 'keyId': rep_note.id,
                'keyOn': f"{rep_note.key_on_ms:.2f}", 'keyOff': f"{rep_note.key_off_ms:.2f}",
                'hammer_times': format_hammer_time(rep_note), 'hammer_velocities': format_hammer_velocity(rep_note),
                'duration': f"{rep_note.duration_ms:.2f}", 'row_type': 'replay',
                'keyon_diff': f"{k_diff:+.2f}ms", 'duration_diff': f"{d_diff:+.2f}ms",
                'hammer_time_diff': f"{hammer_time_diff:+.2f}ms" if hammer_time_diff else '',
                'hammer_velocity_diff': f"{hammer_velocity_diff:+.2f}" if hammer_velocity_diff else '',
                'match_status': f"误差: {err_ms:.2f}ms",
                'record_uuid': rec_note.uuid, 'replay_uuid': rep_note.uuid  # 添加配对信息
            }
            
            if algorithm_name:
                record_row['algorithm_name'] = algorithm_name
                replay_row['algorithm_name'] = algorithm_name
                
            detail_data.extend([record_row, replay_row])
        return detail_data
    except Exception as e:
        logger.error(f"Error fetching grade detail: {e}")
        return []

def get_failed_matches_detail_data(matcher, algorithm_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """获取无法匹配（Major 异常）的音符详情"""
    try:
        failure_reasons = getattr(matcher, 'failure_reasons', {})
        if not failure_reasons: return []
        
        detail_data = []
        for (data_type, index), reason in failure_reasons.items():
            attr = '_record_data' if data_type == 'record' else '_replay_data'
            notes = getattr(matcher, attr, [])
            if index < len(notes):
                note = notes[index]
                row = {
                    'row_type': '录制' if data_type == 'record' else '播放',
                    'index': index, 'key_id': note.id, 'reason': reason,
                    'keyon': f"{note.key_on_ms:.2f}", 'keyoff': f"{note.key_off_ms:.2f}",
                    'duration': f"{note.duration_ms:.2f}", 'hammer_time': format_hammer_time(note),
                    'hammer_velocity': format_hammer_velocity(note)
                }
                if algorithm_name: row['algorithm_name'] = algorithm_name
                detail_data.append(row)
        return detail_data
    except: return []

def show_single_grade_detail(button_index, session_id, session_manager):
    """根据点击属性派发具体数据及列定义"""
    backend = session_manager.get_backend(session_id)
    if not backend: return None
    
    try:
        # 解析按钮索引
        if '_' in button_index:
            alg_name, grade_key = button_index.rsplit('_', 1)
        else:
            alg_name, grade_key = None, button_index
            
        # 根据评级类型抓取数据
        if grade_key == 'major':
            matcher = get_note_matcher_from_backend(backend, alg_name)
            data = get_failed_matches_detail_data(matcher, alg_name)
            cols = [{"name": n, "id": i} for n, i in [
                ("类型", "row_type"), ("索引", "index"), ("按键ID", "key_id"), 
                ("按键时间(ms)", "keyon"), ("释放时间(ms)", "keyoff"), 
                ("按键时长(ms)", "duration"), ("失败原因", "reason")
            ]]
        else:
            data = get_grade_detail_data(backend, grade_key, alg_name)
            cols = [
                {"name": "类型", "id": "data_type"},
                {"name": "按键ID", "id": "keyId"},
                {"name": "按键时间\n(ms)", "id": "keyOn"},
                {"name": "释放时间\n(ms)", "id": "keyOff"},
                {"name": "锤击时间\n(ms)", "id": "hammer_times"},
                {"name": "锤速", "id": "hammer_velocities"},
                {"name": "按键开始差\n(ms)", "id": "keyon_diff"},
                {"name": "持续时间差\n(ms)", "id": "duration_diff"},
                {"name": "锤击时间差\n(ms)", "id": "hammer_time_diff"},
                {"name": "锤速差", "id": "hammer_velocity_diff"},
                {"name": "匹配状态", "id": "match_status"}
            ]
            
        if alg_name: cols.insert(0, {"name": "算法名称", "id": "algorithm_name"})
        return {'display': 'block', 'marginTop': '20px'}, cols, data
    except Exception as e:
        logger.error(f"Detailed view dispatch error: {e}")
        return None

# ==========================================
# 3. 绘图与跳转层 (Viz & Navigation)
# ==========================================

def _create_modal_style(show=True):
    return {
        'display': 'block' if show else 'none',
        'position': 'fixed', 'zIndex': '9999', 'left': '0', 'top': '0',
        'width': '100%', 'height': '100%', 'backgroundColor': 'rgba(0,0,0,0.6)',
        'backdropFilter': 'blur(5px)'
    }

def _process_note_data(session_manager, session_id, row_data, table_index, active_cell=None):
    """基于行数据提取并生成曲线对比模态框内容"""
    try:
        key_id = int(row_data.get('keyId') or row_data.get('key_id'))
        global_idx = row_data.get('global_index') or row_data.get('index')
        data_type = row_data.get('data_type') or row_data.get('row_type')
        
        backend = session_manager.get_backend(session_id)
        matcher = get_note_matcher_from_backend(backend, table_index)
        
        # 优先使用表格数据中的配对信息（更可靠）
        record_uuid = row_data.get('record_uuid')
        replay_uuid = row_data.get('replay_uuid')
        
        matched = None
        if record_uuid and replay_uuid:
            # 使用配对信息直接查找匹配对
            matched = matcher.find_matched_pair_by_uuid(str(record_uuid), str(replay_uuid))
            if matched:
                logger.info(f"通过配对信息找到匹配对: record_uuid={record_uuid}, replay_uuid={replay_uuid}")
        
        if not matched: 
            logger.warning(f"未找到匹配曲线: key_id={key_id}, global_idx={global_idx}, data_type={data_type}, table_index={table_index}")
            return _create_modal_style(True), [html.Div("未找到匹配曲线")], no_update
        
        # 从matched中解包出正确的note对象
        rec_note, rep_note, match_type, error_ms = matched
        
        # 验证找到的note对象是否正确
        validation_errors = []
        if data_type == '录制':
            if str(rec_note.uuid) != str(global_idx):
                error_msg = f"UUID不匹配: 期望={global_idx}, 实际rec_note.uuid={rec_note.uuid}"
                logger.error(error_msg)
                validation_errors.append(error_msg)
        elif data_type == '播放':
            if str(rep_note.uuid) != str(global_idx):
                error_msg = f"UUID不匹配: 期望={global_idx}, 实际rep_note.uuid={rep_note.uuid}"
                logger.error(error_msg)
                validation_errors.append(error_msg)
        
        # 验证key_id是否匹配
        if rec_note.id != key_id:
            error_msg = f"录制按键ID不匹配: 期望={key_id}, 实际={rec_note.id}"
            logger.warning(error_msg)
            validation_errors.append(error_msg)
        if rep_note.id != key_id:
            error_msg = f"播放按键ID不匹配: 期望={key_id}, 实际={rep_note.id}"
            logger.warning(error_msg)
            validation_errors.append(error_msg)
        
        # 如果有严重错误，返回错误信息
        if validation_errors:
            error_content = html.Div([
                html.H5("数据验证失败", className="text-danger"),
                html.Ul([html.Li(err) for err in validation_errors])
            ])
            return _create_modal_style(True), [error_content], no_update
        
        # 构建图表
        fig_original, fig_aligned = _create_curves_subplot(backend, key_id, table_index, matched)
        jump_info = {
            'key_id': key_id, 'algorithm_name': table_index, 'record_uuid': rec_note.uuid,
            'replay_uuid': rep_note.uuid, 'source_plot_id': 'grade-detail-curves-modal',
            'table_index': table_index, 'row_index': active_cell.get('row') if active_cell else None
        }

        # Tab 1: 原始对比
        tab1_content = [
            dcc.Graph(figure=fig_original, style={'marginBottom': '20px'}),
            dcc.Graph(figure=fig_aligned, style={'marginBottom': '20px'}),
        ]

        # Tab 2: 相似度分析
        tab2_content = _create_similarity_content(rec_note, rep_note, backend)

        content = [
            dcc.Tabs([
                dcc.Tab(label='曲线对比', children=html.Div(tab1_content, style={'padding': '20px'})),
                dcc.Tab(label='相似度分析', children=html.Div(tab2_content, style={'padding': '20px'}))
            ]),
            html.Div(html.Button("跳转到瀑布图", id="jump-to-waterfall-btn-from-grade-detail", className="btn btn-success"),
                     style={'textAlign': 'center', 'marginTop': '10px'})
        ]
        return _create_modal_style(True), content, jump_info
    except Exception as e:
        logger.error(f"生成模态框内容失败: {e}")
        logger.error(traceback.format_exc())
        return _create_modal_style(True), [html.Div(f"生成失败: {e}")], no_update

def _create_similarity_content(rec_note, rep_note, backend) -> List[Any]:
    """创建相似度分析Tab内容"""
    try:
        # 获取全局平均延时
        mean_delay = backend.get_global_average_delay() if backend else 0.0
        
        # 调用分析器
        analyzer = ForceCurveAnalyzer()
        result = analyzer.compare_curves(rec_note, rep_note, 
                                       record_note=rec_note, replay_note=rep_note,
                                       mean_delay=mean_delay)
        
        if not result:
            return [html.Div("无法计算相似度", className="alert alert-warning")]
            
        # 提取结果
        similarity = result.get('overall_similarity', 0.0)
        shape_score = result.get('shape_similarity', 0.0)
        amp_score = result.get('amplitude_similarity', 0.0)
        dtw_distance = result.get('dtw_distance', 0.0)
        
        # 生成图表
        figures = analyzer.generate_processing_stages_figures(result)
        
        # 构建UI
        ui_elements = [
            html.Div([
                html.H4(f"综合相似度: {similarity:.3f}", className="text-primary"),
                html.Div([
                    html.Span(f"形状相似度(60%): {shape_score:.3f}", className="badge bg-info me-2", style={'fontSize': '14px'}),
                    html.Span(f"幅度还原度(40%): {amp_score:.3f}", className="badge bg-success", style={'fontSize': '14px'})
                ], className="mb-2"),
                html.P(f"DTW距离: {dtw_distance:.3f}", className="text-muted small"),
                html.Hr()
            ], style={'textAlign': 'center', 'marginBottom': '20px'})
        ]
        
        # 添加所有阶段的图表
        for fig_item in figures:
            ui_elements.append(dcc.Graph(
                figure=fig_item['figure'],
                style={'marginBottom': '20px', 'height': '350px'}
            ))
            
        return ui_elements
        
    except Exception as e:
        logger.error(f"创建相似度内容失败: {e}")
        return [html.Div(f"相似度分析出错: {e}", className="alert alert-danger")]

def _add_hammer_markers(fig, note, label, color, time_offset=0.0):
    """向图表添加锤击点标记（过滤掉锤速为0的点）
    
    锤击点的数据完全来自hammers，不依赖after_touch：
    - X坐标：时间（hammers.index + offset）
    - Y坐标：锤速值（hammers.values）
    
    Args:
        fig: Plotly图表对象
        note: Note对象（包含hammers数据）
        label: 标签名称（如'录制'或'播放'）
        color: 标记颜色
        time_offset: 时间偏移量（用于对齐）
    """
    if note.hammers.empty:
        return
    
    # 过滤掉锤速为0的点
    valid_mask = note.hammers.values > 0
    if not any(valid_mask):
        return
    
    # 从hammers数据中获取时间和锤速
    hammer_times = (note.hammers.index[valid_mask] + note.offset) / 10.0 - time_offset
    hammer_velocities = note.hammers.values[valid_mask]
    
    # 直接使用锤速值作为Y坐标
    fig.add_trace(go.Scatter(
        x=hammer_times.tolist() if hasattr(hammer_times, 'tolist') else list(hammer_times),
        y=hammer_velocities.tolist() if hasattr(hammer_velocities, 'tolist') else list(hammer_velocities),
        mode='markers',
        name=f'{label}锤击',
        marker=dict(symbol='diamond', size=10, color=color),
        hovertemplate=f'<b>{label}锤击</b><br>时间: %{{x:.2f}}ms<br>锤速: %{{y}}<extra></extra>'
    ))

def _add_after_touch_traces(fig, rec_note, rep_note, delay=0.0):
    """向图表添加触后曲线"""
    rec_x = (rec_note.after_touch.index + rec_note.offset) / 10.0
    rep_x = (rep_note.after_touch.index + rep_note.offset) / 10.0 - delay
    
    fig.add_trace(go.Scatter(x=rec_x, y=rec_note.after_touch.values, name='录制', line=dict(color='blue')))
    fig.add_trace(go.Scatter(x=rep_x, y=rep_note.after_touch.values, name='播放', line=dict(color='red')))

def _create_curves_subplot(backend, key_id, algorithm_name, matched_pair):
    """构建对比曲线 Dash 组件 - 返回两个独立的图表"""
    rec_note, rep_note, match_type, error_ms = matched_pair

    # 获取平均延时用于对齐
    delay = (backend.get_global_average_delay() if not algorithm_name else
             next(alg.analyzer.get_global_average_delay() for alg in backend.get_active_algorithms() 
                  if alg.metadata.algorithm_name == algorithm_name)) / 10.0

    # 创建原始对比图（偏移前）
    fig_original = go.Figure()
    _add_after_touch_traces(fig_original, rec_note, rep_note, delay=0.0)
    _add_hammer_markers(fig_original, rec_note, '录制', 'blue', time_offset=0.0)
    _add_hammer_markers(fig_original, rep_note, '播放', 'red', time_offset=0.0)
    
    fig_original.update_layout(
        height=300,
        title=f"按键 {key_id} - 原始对比",
        margin=dict(t=50, b=50),
        xaxis_title="时间 (ms)",
        yaxis_title="触后值 / 锤速"
    )

    # 创建对齐对比图（偏移后）
    fig_aligned = go.Figure()
    _add_after_touch_traces(fig_aligned, rec_note, rep_note, delay=delay)
    _add_hammer_markers(fig_aligned, rec_note, '录制', 'blue', time_offset=0.0)
    _add_hammer_markers(fig_aligned, rep_note, '播放', 'red', time_offset=delay)
    
    fig_aligned.update_layout(
        height=300,
        title=f"按键 {key_id} - 对齐对比 (偏移: {delay:.1f}ms)",
        margin=dict(t=50, b=50),
        xaxis_title="时间 (ms)",
        yaxis_title="触后值 / 锤速"
    )

    return fig_original, fig_aligned

# ==========================================
# 4. 回调函数中心 (Interaction Control)
# ==========================================

def register_grade_detail_callbacks(app, session_manager: SessionManager):
    """注册等级统计主交互逻辑"""
    
    # 表格单元格点击 -> 显示对比图
    @app.callback(
        [Output('grade-detail-curves-modal', 'style'),
         Output('grade-detail-curves-comparison-container', 'children'),
         Output('current-clicked-point-info', 'data')],
        [Input({'type': 'grade-detail-datatable', 'index': dash.ALL}, 'active_cell'),
         Input('close-grade-detail-curves-modal', 'n_clicks')],
        [State({'type': 'grade-detail-datatable', 'index': dash.ALL}, 'data'),
         State('session-id', 'data'),
         State('grade-detail-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_click(cells, n_clicks, table_data_list, session_id, current_style):
        ctx = dash.callback_context
        triggered = ctx.triggered[0]['prop_id']
        
        if 'close-grade-detail-curves-modal' in triggered:
            return _create_modal_style(False), [], no_update
            
        if 'active_cell' in triggered:
            # 提取具体的触发槽
            target_idx = json.loads(triggered.split('.')[0])['index']
            active_cell = next((c for c in cells if c), None)
            
            # 找到对应的数据块
            if target_idx == 'single':
                data = table_data_list[0] if table_data_list else []
            else:
                # 简单匹配策略：取第一个非空
                data = next((d for d in table_data_list if d), [])
                
            if active_cell and data:
                row = data[active_cell['row']]
                return _process_note_data(session_manager, session_id, row, target_idx, active_cell)
        return current_style, [], no_update

    # 按钮点击 -> 展开/切换评级详情
    # 注意：为了避免 Output 重叠冲突，此回调不再直接输出 'data'，
    # 而是通过更新 'state_store' 间接触发下方的渲染逻辑。
    @app.callback(
        Output({'type': 'grade-detail-table', 'index': dash.ALL}, 'style'),
        Output({'type': 'grade-detail-datatable', 'index': dash.ALL}, 'columns'),
        Output({'type': 'grade-detail-key-filter', 'index': dash.ALL}, 'options'),
        Output({'type': 'grade-detail-key-filter', 'index': dash.ALL}, 'value'),
        Output({'type': 'grade-detail-state-store', 'index': dash.ALL}, 'data'),
        Input({'type': 'grade-detail-btn', 'index': dash.ALL}, 'n_clicks'),
        State('session-id', 'data'),
        prevent_initial_call=True
    )
    def switch_grade(n_clicks_list, session_id):
        ctx = dash.callback_context
        if not ctx.triggered: return [no_update] * 5
        
        btn_index = json.loads(ctx.triggered[0]['prop_id'].split('.')[0])['index']
        # 解析算法和评级
        if '_' in btn_index:
            alg_name, actual_grade = btn_index.rsplit('_', 1)
        else:
            alg_name, actual_grade = None, btn_index
            
        backend = session_manager.get_backend(session_id)
        if not backend: return [no_update] * 5
        
        # 确定后端活跃算法数
        active_algs = backend.get_active_algorithms()
        num_slots = len(active_algs) if active_algs else 1
        
        # 获取底层数据结果 (用于项提取)
        result = show_single_grade_detail(btn_index, session_id, session_manager)
        if not result: return [no_update] * 5
        style, cols, all_data = result
        
        # 解析可用的按键下拉选项
        key_ids = sorted(list(set(r.get('keyId') or r.get('key_id') for r in all_data if (r.get('keyId') or r.get('key_id')) is not None)))
        opts = [{'label': '请选择按键...', 'value': ''}, {'label': '全部按键', 'value': 'all'}] + \
               [{'label': f"按键 {k}", 'value': str(k)} for k in key_ids]
        
        # 初始化扇区容器
        out_styles, out_cols = [no_update] * num_slots, [no_update] * num_slots
        out_opts, out_vals = [no_update] * num_slots, [no_update] * num_slots
        out_states = [no_update] * num_slots
        
        # 定位目标 Slot
        target = 0
        if alg_name:
            for i, alg in enumerate(active_algs):
                if alg.metadata.algorithm_name == alg_name: target = i; break
        
        out_styles[target] = style
        out_cols[target] = cols
        out_opts[target] = opts
        out_vals[target] = 'all'
        out_states[target] = {'grade_key': actual_grade, 'nonce': dash.callback_context.triggered[0]['value']}
        
        return out_styles, out_cols, out_opts, out_vals, out_states

def register_grade_detail_jump_callbacks(app, session_manager: SessionManager):
    """跳转逻辑"""
    @app.callback(
        [Output('url', 'pathname'),
         Output('grade-detail-curves-modal', 'style', allow_duplicate=True),
         Output('jump-source-plot-id', 'data', allow_duplicate=True)],
        [Input('jump-to-waterfall-btn-from-grade-detail', 'n_clicks')],
        [State('session-id', 'data'),
         State('current-clicked-point-info', 'data'),
         State('url', 'pathname')],
        prevent_initial_call=True
    )
    def jump_to_waterfall(n_clicks, session_id, info, current_pathname):
        if not n_clicks or not info: return no_update, no_update, no_update

        # 如果已经在waterfall页面，直接返回不做操作
        if current_pathname == '/waterfall':
            return no_update, {'display': 'none'}, 'grade-detail-curves-modal'

        # 跳转到waterfall页面
        return '/waterfall', {'display': 'none'}, 'grade-detail-curves-modal'

def register_grade_detail_return_callbacks(app, session_manager: SessionManager):
    """返回逻辑"""
    @app.callback(
        Output('btn-return-to-grade-detail', 'style'),
        Input('jump-source-plot-id', 'data'),
        prevent_initial_call=True
    )
    def update_btn(source):
        return {'display': 'inline-block'} if source == 'grade-detail-curves-modal' else {'display': 'none'}

    @app.callback(
        [Output('grade-detail-curves-modal', 'style', allow_duplicate=True),
         Output('main-tabs', 'value', allow_duplicate=True),
         Output('grade-detail-return-scroll-trigger', 'data'),
         Output('grade-detail-section-scroll-trigger', 'data')],
        Input('btn-return-to-grade-detail', 'n_clicks'),
        State('current-clicked-point-info', 'data'),
        prevent_initial_call=True
    )
    def back(n, info):
        if not n: return no_update, no_update, None, None
        return _create_modal_style(True), "report-tab", info, {'scroll_to': 'grade_detail_section'}

def register_all_callbacks(app, session_manager: SessionManager):
    """聚合注册所有评级详情相关的交互"""
    register_grade_detail_callbacks(app, session_manager)
    register_grade_detail_jump_callbacks(app, session_manager)
    register_grade_detail_return_callbacks(app, session_manager)
    
    # 【核心：数据渲染与过滤逻辑】
    # 使用 MATCH 模式，监听下拉框 value 和 状态 Store，输出到对应的表格 data
    @app.callback(
        Output({'type': 'grade-detail-datatable', 'index': dash.MATCH}, 'data'),
        [Input({'type': 'grade-detail-key-filter', 'index': dash.MATCH}, 'value'),
         Input({'type': 'grade-detail-state-store', 'index': dash.MATCH}, 'data')],
        State('session-id', 'data'),
        prevent_initial_call=True
    )
    def filter_by_key(key_filter, state, sid):
        if not state or not state.get('grade_key'): return no_update
        
        grade_key = state['grade_key']
        # 确定索引 (多算法 vs 单算法)
        trigger_id = dash.callback_context.triggered[0]['prop_id']
        target_idx = json.loads(trigger_id.split('.')[0])['index']
        alg = None if target_idx == 'single' else target_idx
        
        backend = session_manager.get_backend(sid)
        if not backend: return no_update

        # 获取完整结果数据
        if grade_key == 'major':
            matcher = get_note_matcher_from_backend(backend, alg)
            all_data = get_failed_matches_detail_data(matcher, alg)
            filter_field = 'key_id'
        else:
            all_data = get_grade_detail_data(backend, grade_key, alg)
            filter_field = 'keyId'
        
        # 执行过滤
        if key_filter and key_filter != 'all' and key_filter != '':
            return [r for r in all_data if str(r.get(filter_field)) == str(key_filter)]
        return all_data