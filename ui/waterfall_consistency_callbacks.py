from dash import Input, Output, State, callback_context, no_update, html
import dash_bootstrap_components as dbc
from utils.logger import Logger
from backend.consistency_plotter import ConsistencyPlotter
import json

logger = Logger.get_logger()

def register_callbacks(app, session_manager):
    """
    注册瀑布图页面波形一致性分析的回调函数
    """
    
    # 1. 更新按键下拉框选项
    @app.callback(
        Output('track-comparison-consistency-key-dropdown', 'options'),
        [Input('session-id', 'data'),
         Input('active-algorithm-store', 'data'),
         Input('algorithm-management-trigger', 'data')]
    )
    def update_key_options(session_id, active_algorithm_name, management_trigger):
        return _handle_update_key_options(session_id, active_algorithm_name, session_manager)


    # 2. 更新Slider范围和文本 (基于第一个播放音轨)
    @app.callback(
        [Output('track-comparison-consistency-index-slider', 'max'),
         Output('track-comparison-consistency-index-slider', 'value'),
         Output('track-comparison-consistency-index-slider', 'marks'),
         Output('track-comparison-consistency-curve-count-label', 'children')],
        [Input('track-comparison-consistency-key-dropdown', 'value')],
        [State('session-id', 'data'),
         State('active-algorithm-store', 'data')]
    )
    def update_slider_range(key_id, session_id, active_algorithm_name):
        return _handle_update_slider_range(key_id, session_id, active_algorithm_name, session_manager)


    # 3. 更新波形一致性图表 (仅绘制播放音轨)
    @app.callback(
        [Output('track-comparison-consistency-waveform-graph', 'figure'),
         Output('track-comparison-consistency-curve-count-label', 'children', allow_duplicate=True)],
        [Input('track-comparison-consistency-index-slider', 'value'),
         Input('track-comparison-consistency-key-dropdown', 'value')],
        [State('session-id', 'data'),
         State('active-algorithm-store', 'data')],
        prevent_initial_call=True
    )
    def update_consistency_graph(slider_value, key_id, session_id, active_algorithm_name):
        return _handle_update_consistency_graph(slider_value, key_id, session_id, active_algorithm_name, session_manager)


def _handle_update_key_options(session_id, active_algorithm_name, session_manager):
    if not session_id:
        return []
        
    backend = session_manager.get_backend(session_id)
    if not backend:
        return []
        
    # 获取所有活跃算法，收集所有 Key ID
    active_algorithms = backend.get_active_algorithms()
    if not active_algorithms:
        return []
        
    keys = set()
    for alg in active_algorithms:
        analyzer = alg.analyzer
        if not analyzer: continue
        
        # 仅收集播放音轨 (Replay) 的 Key ID，因为此界面只显示播放音轨
        rep_data = analyzer.get_initial_valid_replay_data() or []
        for note in rep_data: keys.add(note.id)
            
    # 排序并生成选项
    sorted_keys = sorted(list(keys))
    options = [{'label': f"Key {k}", 'value': k} for k in sorted_keys]
    
    return options

def _handle_update_slider_range(key_id, session_id, active_algorithm_name, session_manager):
    if key_id is None or not session_id:
        return 0, [0, 0], None, ""
        
    backend = session_manager.get_backend(session_id)
    if not backend:
        return 0, [0, 0], None, ""
        
    active_algorithms = backend.get_active_algorithms()
    if not active_algorithms:
        return 0, [0, 0], None, ""
        
    # 取第一个算法作为基准进行范围切片
    base_analyzer = active_algorithms[0].analyzer
    if not base_analyzer:
        return 0, [0, 0], None, ""
        
    # 注意：瀑布图界面以播放音轨 (Replay) 为准
    replay_data = base_analyzer.get_initial_valid_replay_data() or []
    key_replay_notes = sorted([n for n in replay_data if n.id == key_id], key=lambda x: x.offset)
    count = len(key_replay_notes)
    
    if count == 0:
         return 0, [0, 0], None, "该按键无播放数据"
    
    max_val = max(0, count - 1)
    marks = {}
    
    def format_time(idx):
        if 0 <= idx < count:
            note = key_replay_notes[idx]
            if note.key_on_ms is not None:
                return f"{note.key_on_ms/1000:.1f}s"
            return f"{note.offset/10000:.1f}s"
        return str(idx)

    if count <= 20:
        marks = {i: format_time(i) for i in range(count)}
    else:
        marks[0] = format_time(0)
        marks[max_val] = format_time(max_val)
        num_ticks = 8
        step = count / (num_ticks + 1)
        for i in range(1, num_ticks + 1):
            idx = int(i * step)
            if idx < max_val: marks[idx] = format_time(idx)

    start_time = format_time(0)
    end_time = format_time(max_val)
    label_text = f"总计 {count} 组播放曲线，时间范围: {start_time} - {end_time}"
    
    return max_val, [0, max_val], marks, label_text

def _handle_update_consistency_graph(slider_value, key_id, session_id, active_algorithm_name, session_manager):
    if key_id is None or not session_id:
        return no_update, no_update
        
    backend = session_manager.get_backend(session_id)
    if not backend:
        return no_update, no_update
        
    active_algorithms = backend.get_active_algorithms()
    if not active_algorithms:
        return no_update, no_update
        
    # 1. 提取基准 Replay 数据用于范围切片
    base_analyzer = active_algorithms[0].analyzer
    full_replay_data = base_analyzer.get_initial_valid_replay_data() or []
    full_key_replay_notes = sorted([n for n in full_replay_data if n.id == key_id], key=lambda x: x.offset)
    
    total_count = len(full_key_replay_notes)
    if total_count == 0:
        return no_update, "无播放数据"
        
    # 解析范围
    start_idx = 0
    end_idx = total_count - 1
    if isinstance(slider_value, list) and len(slider_value) == 2:
        start_idx = max(0, slider_value[0])
        end_idx = min(total_count - 1, slider_value[1])
    
    sliced_base_notes = full_key_replay_notes[start_idx : end_idx + 1]
    
    # 2. 提取所有算法的 Replay 数据并统计
    data_sources = []
    stats_list = []
    
    # 确定时间范围
    min_ts = sliced_base_notes[0].key_on_ms if sliced_base_notes and sliced_base_notes[0].key_on_ms else -1
    max_ts = sliced_base_notes[-1].key_on_ms if sliced_base_notes and sliced_base_notes[-1].key_on_ms else float('inf')

    for alg in active_algorithms:
        alg_name = alg.metadata.algorithm_name
        display_name = alg.metadata.display_name or alg_name
        analyzer = alg.analyzer
        
        alg_replay_data = analyzer.get_initial_valid_replay_data() or []
        alg_key_replay = sorted([n for n in alg_replay_data if n.id == key_id], key=lambda x: x.offset)
        
        # 统计该按键的总播放数
        total_alg_key_count = len(alg_key_replay)
        
        # 按时间范围切片 Replay
        sliced_replay_notes = [
             n for n in alg_key_replay 
             if n.key_on_ms is not None and (min_ts - 500 <= n.key_on_ms <= max_ts + 500)
        ]
        
        data_sources.append({
            'name': display_name,
            'record_notes': [], # 不显示录制音轨
            'replay_notes': sliced_replay_notes
        })
        
        stats_list.append(f"{alg_name}: {total_alg_key_count}")

    # 3. 生成图表
    fig = ConsistencyPlotter.generate_key_waveform_consistency_plot(
        data_sources=data_sources,
        key_id=key_id,
        title_suffix=" (仅播放音轨对比)"
    )
    
    # 修正标题，因为没有 Record
    fig.update_layout(
        title=f'Key {key_id} 音轨对比一致性分析 (仅播放音轨对比)'
    )
    
    # 4. 计算显示标签
    current_count = len(sliced_base_notes)
    start_str = "N/A"
    end_str = "N/A"
    if sliced_base_notes:
        n1 = sliced_base_notes[0]
        n2 = sliced_base_notes[-1]
        if n1.key_on_ms: start_str = f"{n1.key_on_ms/1000:.1f}s"
        if n2.key_on_ms: end_str = f"{n2.key_on_ms/1000:.1f}s"
        
    stats_str = " | ".join(stats_list)
    label_text = html.Div([
        html.Div(f"显示范围: {start_idx + 1} - {end_idx + 1} (共 {current_count} 组播放曲线, 时间: {start_str} - {end_str})"),
        html.Div([
            html.B("各音轨总按键数统计: "),
            html.Span(stats_str, className="text-info")
        ], className="mt-1")
    ])
    
    return fig, label_text
