"""
匹配质量评级统计详情回调控制逻辑
"""
import json
import traceback
from typing import Dict, List, Optional, Any

import dash
import plotly.graph_objects as go
from dash import Input, Output, State, html, no_update, dcc

from backend.session_manager import SessionManager
from spmid.note_matcher import MatchType
from spmid.spmid_reader import Note
from backend.force_curve_analyzer import ForceCurveAnalyzer

from utils.logger import Logger

# 日志记录器
from ui.duration_diff_curves import DurationDiffCurvePlotter

logger = Logger.get_logger()
plotter = DurationDiffCurvePlotter()

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
        
        # 建立评级映射 (已统一为 excellent, good, fair, poor, severe, failed)
        try:
            target_type = MatchType(grade_key)
        except ValueError:
            logger.warning(f"未知评级 Key: {grade_key}")
            return []
        
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
                    'hammer_velocity': format_hammer_velocity(note),
                    'record_uuid': note.uuid if data_type == 'record' else None,
                    'replay_uuid': note.uuid if data_type == 'replay' else None,
                    'global_index': note.uuid
                }
                if algorithm_name: row['algorithm_name'] = algorithm_name
                detail_data.append(row)
        return detail_data
    except Exception as e:
        logger.error(f"Error in get_failed_matches_detail_data: {e}")
        return []

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
        if grade_key == 'failed':
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
# 3. 绘图层 (Viz)
# ==========================================

def _create_modal_style(show=True):
    return {
        'display': 'flex' if show else 'none',  # 与 app 布局一致：flex 才能居中显示
        'position': 'fixed', 'zIndex': '9999', 'left': '0', 'top': '0',
        'width': '100%', 'height': '100%', 'backgroundColor': 'rgba(0,0,0,0.6)',
        'backdropFilter': 'blur(5px)', 'alignItems': 'center', 'justifyContent': 'center'
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
            matched = matcher.find_matched_pair_by_uuid(str(record_uuid), str(replay_uuid))
        
        # 获取前后邻居匹配对 (即使当前未匹配，也可以根据 UUID 找邻居)
        prev_pair, next_pair = matcher.get_neighbor_matched_pairs(
            str(record_uuid) if record_uuid else None, 
            str(replay_uuid) if replay_uuid else None
        )
        
        logger.info(f"[DEBUG] _process_note_data: matched={matched is not None}, prev={prev_pair is not None}, next={next_pair is not None}")

        if not matched:
            # 处理未匹配音符的情况
            logger.info("_process_note_data: 处于未匹配模式，尝试显示单边曲线和邻居")
            # 查找音符对象
            current_note = None
            note_side = ""
            if record_uuid:
                current_note = next((n for n in getattr(matcher, '_record_data', []) if str(n.uuid) == str(record_uuid)), None)
                note_side = "录制"
            elif replay_uuid:
                current_note = next((n for n in getattr(matcher, '_replay_data', []) if str(n.uuid) == str(replay_uuid)), None)
                note_side = "播放"
            
            if not current_note:
                return _create_modal_style(True), [html.Div("未找到匹配曲线且无法定位原始音符")], no_update
            
            # 创建单边图表
            fig_single = go.Figure()
            plotter.add_note_traces(fig_single, current_note, f"{note_side} (原始)", "blue" if note_side=="录制" else "red")
            fig_single.update_layout(title=f"未匹配音符详情 ({note_side} 按键 {current_note.id})", height=350)
            
            # 构建内容
            tab1_content = []
            
            # 添加邻居 (前)
            if prev_pair:
                fig_p = plotter.create_comparison_figure(prev_pair)
                fig_p.update_layout(title=f"前一匹配对 (按键 {current_note.id})", height=250)
                tab1_content.append(html.H6("⬅️ 前一匹配对", className="text-muted mt-2"))
                tab1_content.append(dcc.Graph(figure=fig_p, style={'marginBottom': '15px'}))
                tab1_content.append(html.Hr())

            # 当前音符
            tab1_content.append(html.H6(f"⚠️ 当前音符 (未匹配 - {note_side})", className="text-warning mt-2"))
            tab1_content.append(dcc.Graph(figure=fig_single, style={'marginBottom': '20px'}))

            # 添加邻居 (后)
            if next_pair:
                tab1_content.append(html.Hr())
                fig_n = plotter.create_comparison_figure(next_pair)
                fig_n.update_layout(title=f"后一匹配对 (按键 {current_note.id})", height=250)
                tab1_content.append(html.H6("➡️ 后一匹配对", className="text-muted mt-2"))
                tab1_content.append(dcc.Graph(figure=fig_n, style={'marginBottom': '15px'}))

            content = [dcc.Tabs([dcc.Tab(label='曲线对比', children=html.Div(tab1_content, style={'padding': '20px'}))])]
            return _create_modal_style(True), content, no_update

        rec_note, rep_note, match_type, error_ms = matched
        validation_errors = []

        if data_type == '录制':
            if str(rec_note.uuid) != str(global_idx):
                validation_errors.append(f"录制UUID不匹配: 表格={global_idx} 找到={rec_note.uuid}")
            if rec_note.id != key_id:
                validation_errors.append(f"录制按键ID不匹配: 表格keyId={key_id} 找到={rec_note.id}")
        elif data_type == '播放':
            if str(rep_note.uuid) != str(global_idx):
                validation_errors.append(f"播放UUID不匹配: 表格={global_idx} 找到={rep_note.uuid}")
            if rep_note.id != key_id:
                validation_errors.append(f"播放按键ID不匹配: 表格keyId={key_id} 找到={rep_note.id}")

        if validation_errors:
            logger.warning("_process_note_data: 验证失败 %s", validation_errors)
            error_content = html.Div([
                html.H5("数据验证失败", className="text-danger"),
                html.Ul([html.Li(err) for err in validation_errors])
            ])
            return _create_modal_style(True), [error_content], no_update
        
        # 以 UUID 查到的 note 为准：图表与 point_info 均用 rec_note.id，与表格一致
        key_id = rec_note.id
        # 构建图表
        fig_original, fig_aligned = _create_curves_subplot(backend, key_id, table_index, matched)
        
        # 构建点信息（用于其他功能，如返回定位）
        point_info = {
            'key_id': key_id, 'algorithm_name': table_index, 'record_uuid': rec_note.uuid,
            'replay_uuid': rep_note.uuid, 'source_plot_id': 'grade-detail-curves-modal',
            'table_index': table_index, 'row_index': active_cell.get('row') if active_cell else None
        }
        
        # Tab 1: 原始对比
        tab1_content = []
        
        # 如果有前一个匹配对，添加图表
        if prev_pair:
            # 获取对应的邻居序号
            key_pairs = matcher.matched_pairs
            # 过滤出当前按键并排序
            this_key_pairs = sorted([p for p in key_pairs if p[0].id == key_id], key=lambda x: x[0].key_on_ms)
            p_seq = -1
            for i, p in enumerate(this_key_pairs):
                if str(p[0].uuid) == str(prev_pair[0].uuid) and str(p[1].uuid) == str(prev_pair[1].uuid):
                    p_seq = i + 1
                    break
            
            p_label = f" (序号 {p_seq})" if p_seq != -1 else ""
            fig_prev = plotter.create_comparison_figure(prev_pair)
            fig_prev.update_layout(title=None, height=250, margin=dict(t=30))
            tab1_content.append(html.H6(f"⬅️ 前一匹配对{p_label}", className="text-muted mt-2"))
            tab1_content.append(dcc.Graph(figure=fig_prev, style={'marginBottom': '15px'}))
            tab1_content.append(html.Hr())
        # 当前匹配对的原始对比 (按照用户要求，删除对齐对比曲线)
        # 获取当前序号
        this_key_pairs = sorted([p for p in matcher.matched_pairs if p[0].id == key_id], key=lambda x: x[0].key_on_ms)
        c_seq = -1
        for i, p in enumerate(this_key_pairs):
            if str(p[0].uuid) == str(rec_note.uuid) and str(p[1].uuid) == str(rep_note.uuid):
                c_seq = i + 1
                break
        c_label = f" (序号 {c_seq})" if c_seq != -1 else ""
        
        fig_original.update_layout(title=None) # 移除内部标题，由 H6 统一承担
        tab1_content.append(html.H6(f"📍 当前匹配对{c_label} - 原始对比", className="text-primary mt-2 font-weight-bold"))
        tab1_content.append(dcc.Graph(figure=fig_original, style={'marginBottom': '20px'}))

        # 如果有下一个匹配对，添加图表
        if next_pair:
            this_key_pairs = sorted([p for p in matcher.matched_pairs if p[0].id == key_id], key=lambda x: x[0].key_on_ms)
            n_seq = -1
            for i, p in enumerate(this_key_pairs):
                if str(p[0].uuid) == str(next_pair[0].uuid) and str(p[1].uuid) == str(next_pair[1].uuid):
                    n_seq = i + 1
                    break
            
            n_label = f" (序号 {n_seq})" if n_seq != -1 else ""
            tab1_content.append(html.Hr())
            fig_next = plotter.create_comparison_figure(next_pair)
            fig_next.update_layout(title=None, height=250, margin=dict(t=30))
            tab1_content.append(html.H6(f"➡️ 后一匹配对{n_label}", className="text-muted mt-2"))
            tab1_content.append(dcc.Graph(figure=fig_next, style={'marginBottom': '15px'}))
        
        # Tab 2: 相似度分析
        tab2_content = _create_similarity_content(rec_note, rep_note, backend)
        
        # 仅保留曲线对比和相似度分析
        content = [
            dcc.Tabs([
                dcc.Tab(label='曲线对比', children=html.Div(tab1_content, style={'padding': '20px'})),
                dcc.Tab(label='相似度分析', children=html.Div(tab2_content, style={'padding': '20px'}))
            ])
        ]
        return _create_modal_style(True), content, point_info
    except Exception as e:
        logger.error(f"生成模态框内容失败: {e}")
        logger.error(traceback.format_exc())
        return _create_modal_style(True), [html.Div(f"生成失败: {e}")], no_update

def _create_similarity_content(rec_note, rep_note, backend) -> List[Any]:
    """创建相似度分析Tab内容 (显示深度重构后的多维评分)"""
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
        impulse_score = result.get('impulse_similarity', 0.0)
        phys_score = result.get('physical_similarity', 0.0)
        
        pearson = result.get('pearson_correlation', 0.0)
        dtw_dist = result.get('dtw_distance', 0.0)
        
        # 生成图表
        figures = analyzer.generate_processing_stages_figures(result)
        
        # 构建UI
        ui_elements = [
            html.Div([
                html.H3(f"综合相似度: {similarity:.1%}", className="text-primary", style={'fontWeight': 'bold', 'marginBottom': '15px'}),
                
                # 评分展示 (50/50 模式)
                html.Div([
                    html.Div([
                        html.Div("形状相关 (50%)", style={'fontSize': '12px', 'color': '#666'}),
                        html.Div(f"{shape_score:.3f}", style={'fontSize': '20px', 'color': '#17a2b8', 'fontWeight': 'bold'}),
                        html.Div(f"DTW/Pearson", style={'fontSize': '10px', 'color': '#999'})
                    ], style={'flex': '1', 'textAlign': 'center', 'borderRight': '1px solid #eee'}),
                    
                    html.Div([
                        html.Div("物理动作还原 (50%)", style={'fontSize': '12px', 'color': '#666'}),
                        html.Div(f"{phys_score:.3f}", style={'fontSize': '20px', 'color': '#6f42c1', 'fontWeight': 'bold'}),
                        html.Div("斜率/高度/序列", style={'fontSize': '10px', 'color': '#999'})
                    ], style={'flex': '1', 'textAlign': 'center'}),
                ], style={'display': 'flex', 'padding': '15px', 'backgroundColor': '#f8f9fa', 'borderRadius': '10px', 'marginBottom': '20px'}),
                
                html.Hr()
            ], style={'textAlign': 'center', 'marginBottom': '20px'})
        ]
        
        # 添加所有阶段的图表
        for fig_item in figures:
            ui_elements.append(html.Div([
                html.H5(fig_item['title'], style={'textAlign': 'left', 'marginLeft': '10px', 'color': '#444'}),
                dcc.Graph(
                    figure=fig_item['figure'],
                    style={'marginBottom': '25px', 'height': '380px'}
                )
            ]))
            
        return ui_elements
        
    except Exception as e:
        logger.error(f"创建相似度内容失败: {e}")
        logger.error(traceback.format_exc())
        return [html.Div(f"相似度分析出错: {e}", className="alert alert-danger")]

def _create_curves_subplot(backend, key_id, algorithm_name, matched_pair):
    """构建对比曲线 Dash 组件 - 返回两个独立的图表"""
    rec_note, rep_note, match_type, error_ms = matched_pair

    # 获取平均延时用于对齐
    delay = 0.0
    try:
        if not algorithm_name or algorithm_name == 'single':
            delay = backend.get_global_average_delay()
        else:
            active_algs = backend.get_active_algorithms()
            target_alg = next((alg for alg in active_algs if alg.metadata.algorithm_name == algorithm_name), None)
            if target_alg and target_alg.analyzer:
                delay = target_alg.analyzer.get_global_average_delay()
            else:
                delay = backend.get_global_average_delay()
    except Exception as e:
        logger.warning(f"获取对齐偏移量失败 (alg={algorithm_name}): {e}")
        delay = 0.0
    
    delay = delay / 10.0

    # 使用统一绘图器创建图表
    fig_original = go.Figure()
    plotter.add_note_traces(fig_original, rec_note, "录制 (原始)", "blue")
    plotter.add_note_traces(fig_original, rep_note, "播放 (原始)", "red")
    fig_original.update_layout(height=300, title=f"按键 {key_id} - 原始对比", margin=dict(t=30, b=30))

    fig_aligned = go.Figure()
    plotter.add_note_traces(fig_aligned, rec_note, "录制 (对齐)", "blue")
    plotter.add_note_traces(fig_aligned, rep_note, "播放 (对齐)", "red", time_offset=delay)
    plotter.draw_split_analysis(fig_aligned, matched_pair)
    fig_aligned.update_layout(height=300, title=f"按键 {key_id} - 对齐对比 (偏移: {delay:.2f}ms)", margin=dict(t=30, b=30))

    return fig_original, fig_aligned

# ==========================================
# 4. 回调函数中心 (Interaction Control)
# ==========================================

def register_grade_detail_callbacks(app, session_manager: SessionManager):
    """注册等级统计主交互逻辑"""
    
    # 表格单元格点击 -> 显示按键曲线模态框。流程见 docs/grade_detail_table_callbacks_flow.md
    @app.callback(
        [Output('grade-detail-curves-modal', 'style'),
         Output('grade-detail-curves-comparison-container', 'children'),
         Output('current-clicked-point-info', 'data')],
        [Input({'type': 'grade-detail-datatable', 'index': dash.ALL}, 'active_cell'),
         Input({'type': 'delay-metric-btn', 'algorithm': dash.ALL, 'metric': dash.ALL}, 'n_clicks'),
         Input('close-grade-detail-curves-modal', 'n_clicks')],
        [State({'type': 'grade-detail-datatable', 'index': dash.ALL}, 'data'),
         State({'type': 'grade-detail-datatable', 'index': dash.ALL}, 'page_current'),
         State({'type': 'grade-detail-datatable', 'index': dash.ALL}, 'page_size'),
         State({'type': 'delay-metric-btn', 'algorithm': dash.ALL, 'metric': dash.ALL}, 'id'),
         State('grade-detail-datatable-indices', 'data'),
         State('session-id', 'data'),
         State('grade-detail-curves-modal', 'style')],
        prevent_initial_call=True
    )
    def handle_click(cells, metric_clicks, n_clicks, table_data_list, page_current_list, page_size_list, metric_ids, indices, session_id, current_style):
        ctx = dash.callback_context
        if not ctx.triggered:
            return current_style, [], no_update

        triggered_id_str = ctx.triggered[0]['prop_id']
        
        # --- 1. 处理弹窗关闭 ---
        if 'close-grade-detail-curves-modal' in triggered_id_str:
            return _create_modal_style(False), [], no_update

        # --- 2. 处理延时误差极值指标点击 ---
        if 'delay-metric-btn' in triggered_id_str:
            try:
                # 解析 ID 信息
                triggered_id = json.loads(triggered_id_str.rsplit('.', 1)[0])
                alg_name = triggered_id['algorithm']
                metric_type = triggered_id['metric'] # 'max' 或 'min'

                # 校验点击值
                click_value = ctx.triggered[0].get('value')
                
                # [补丁] 对于 Pattern-match ID，有时 ctx.triggered 中的 value 为 None
                # 尝试从 Input 列表 (metric_clicks) 中通过 State 列表 (metric_ids) 找回真实值
                if (click_value is None or click_value == 0) and metric_ids:
                    try:
                        if triggered_id in metric_ids:
                            idx = metric_ids.index(triggered_id)
                            click_value = metric_clicks[idx]
                    except Exception:
                        pass
                
                # Dash 某些情况下会触发 value=0 (如组件初始化)，只有真实点击才执行
                if click_value is None or click_value == 0:
                    return current_style, [], no_update

                
                backend = session_manager.get_backend(session_id)
                if not backend: 
                    logger.warning(f" [WARN] Backend not found for session_id: {session_id}")
                    return current_style, [], no_update
                
                # 获取音符数据
                res = backend.get_notes_by_delay_type(alg_name, metric_type)
                if not res:
                    logger.warning(f" [WARN] No notes found for {metric_type} deviation")
                    return _create_modal_style(True), [html.Div(f"未找到 {metric_type} 偏差对应的音符数据")], no_update
                
                rec_note, rep_note, rec_idx, rep_idx = res
                
                # 构建虚拟 row_data 以复用组件渲染逻辑
                row_data = {
                    'keyId': rec_note.id,
                    'data_type': '录制',
                    'global_index': rec_note.uuid,
                    'record_uuid': rec_note.uuid,
                    'replay_uuid': rep_note.uuid,
                }
                
                return _process_note_data(session_manager, session_id, row_data, alg_name)
                
            except Exception as e:
                logger.error(f" [ERROR] Failed to handle delay metric click: {e}")
                logger.error(traceback.format_exc())
                return _create_modal_style(True), [html.Div(f"处理极值点击失败: {e}")], no_update

        # --- 3. 处理详细表格单元格点击 ---
        if 'active_cell' in triggered_id_str:
            try:
                # A. 解析目标表格索引
                target_idx = json.loads(triggered_id_str.rsplit('.', 1)[0])['index']
                active_cell = ctx.triggered[0].get('value')
                
                # B. 数据有效性初步检测与兜底 (解决表格重绘导致的选中丢失)
                if not active_cell or (isinstance(active_cell, dict) and active_cell.get('row') is None):
                    if indices and isinstance(indices, list) and target_idx in indices and cells:
                        pos = indices.index(target_idx)
                        if pos < len(cells) and cells[pos]:
                            active_cell = cells[pos]
                            logger.info(f" [FALLBACK] Using fallback cell for table: {target_idx}")
                
                if not active_cell or (isinstance(active_cell, dict) and active_cell.get('row') is None):
                    return current_style, [], no_update

                # C. 提取行号
                row_val = active_cell.get('row') if active_cell.get('row') is not None else active_cell.get('row_id')
                if row_val is None: return current_style, [], no_update
                page_row = int(row_val)
                
                # D. 校验状态一致性
                if not indices or target_idx not in indices:
                    return _create_modal_style(True), [html.Div("无法定位表格，请刷新")], no_update
                
                pos = indices.index(target_idx)
                if not table_data_list or pos >= len(table_data_list):
                    return _create_modal_style(True), [html.Div("数据未就绪")], no_update
                
                # E. 获取当前页数据并计算全局索引
                data = table_data_list[pos] or []
                page_current = (page_current_list[pos] if page_current_list and pos < len(page_current_list) else 0) or 0
                page_size = (page_size_list[pos] if page_size_list and pos < len(page_size_list) else 50) or 50
                
                if not data: return _create_modal_style(True), [html.Div("暂无数据")], no_update

                global_row_idx = page_current * page_size + page_row
                if global_row_idx < 0 or global_row_idx >= len(data):
                    return _create_modal_style(True), [html.Div("行索引越界")], no_update
                
                row = data[global_row_idx]
                return _process_note_data(session_manager, session_id, row, target_idx, active_cell)
                
            except Exception as e:
                logger.error(f" [ERROR] Table cell click failed: {e}")
                logger.error(traceback.format_exc())
                return _create_modal_style(True), [html.Div(f"处理表格点击失败: {e}")], no_update

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
        Output('grade-detail-datatable-indices', 'data'),
        Input({'type': 'grade-detail-btn', 'index': dash.ALL}, 'n_clicks'),
        State('session-id', 'data'),
        prevent_initial_call=True
    )
    def switch_grade(n_clicks_list, session_id):
        # ALL 型 Output 必须返回 list/tuple，不能返回 no_update；无匹配组件时返回空列表
        def _no_update_all():
            return [], [], [], [], [], no_update

        ctx = dash.callback_context
        if not ctx.triggered:
            return _no_update_all()

        btn_index = json.loads(ctx.triggered[0]['prop_id'].rsplit('.', 1)[0])['index']
        if '_' in btn_index:
            alg_name, actual_grade = btn_index.rsplit('_', 1)
        else:
            alg_name, actual_grade = None, btn_index

        backend = session_manager.get_backend(session_id)
        if not backend:
            return _no_update_all()

        active_algs = backend.get_active_algorithms()
        num_slots = len(active_algs) if active_algs else 1
        # 与布局顺序一致；表格 index 恒为 algorithm_name，不用 'single'
        indices = [a.metadata.algorithm_name for a in active_algs] if active_algs else []

        result = show_single_grade_detail(btn_index, session_id, session_manager)
        if not result:
            return _no_update_all()
        style, cols, all_data = result
        
        key_ids = sorted(list(set(r.get('keyId') or r.get('key_id') for r in all_data if (r.get('keyId') or r.get('key_id')) is not None)))
        opts = [{'label': '请选择按键...', 'value': ''}, {'label': '全部按键', 'value': 'all'}] + \
               [{'label': f"按键 {k}", 'value': str(k)} for k in key_ids]
        
        out_styles, out_cols = [no_update] * num_slots, [no_update] * num_slots
        out_opts, out_vals = [no_update] * num_slots, [no_update] * num_slots
        out_states = [no_update] * num_slots
        
        target = 0
        if alg_name:
            for i, alg in enumerate(active_algs):
                if alg.metadata.algorithm_name == alg_name:
                    target = i
                    break
        
        out_styles[target] = style
        out_cols[target] = cols
        out_opts[target] = opts
        out_vals[target] = 'all'
        out_states[target] = {'grade_key': actual_grade, 'nonce': dash.callback_context.triggered[0]['value']}
        
        return out_styles, out_cols, out_opts, out_vals, out_states, indices

def register_all_callbacks(app, session_manager: SessionManager):
    """聚合注册所有评级详情相关的交互"""
    register_grade_detail_callbacks(app, session_manager)
    
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
        target_idx = json.loads(trigger_id.rsplit('.', 1)[0])['index']
        alg = None if target_idx == 'single' else target_idx
        
        backend = session_manager.get_backend(sid)
        if not backend: return no_update

        # 获取完整结果数据
        if grade_key == 'failed':
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