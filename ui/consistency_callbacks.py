from dash import Input, Output, State, callback_context, no_update
import dash_bootstrap_components as dbc
from utils.logger import Logger
from backend.consistency_plotter import ConsistencyPlotter
import json

logger = Logger.get_logger()

def register_callbacks(app, session_manager):
    """
    注册波形一致性分析的回调函数
    """
    
    # 1. 更新按键下拉框选项
    @app.callback(
        Output('consistency-key-dropdown', 'options'),
        [Input('session-id', 'data'),
         Input('active-algorithm-store', 'data')]
    )
    def update_key_options(session_id, active_algorithm_name):
        return _handle_update_key_options(session_id, active_algorithm_name, session_manager)


    # 2. 更新Slider范围和文本 (基于主录制音轨)
    @app.callback(
        [Output('consistency-index-slider', 'max'),
         Output('consistency-index-slider', 'value'),
         Output('consistency-index-slider', 'marks'),
         Output('consistency-curve-count-label', 'children')],
        [Input('consistency-key-dropdown', 'value')],
        [State('session-id', 'data'),
         State('active-algorithm-store', 'data')]
    )
    def update_slider_range(key_id, session_id, active_algorithm_name):
        return _handle_update_slider_range(key_id, session_id, active_algorithm_name, session_manager)


    # 3. 更新波形一致性图表 (绘制所有活跃算法的播放音轨)
    @app.callback(
        [Output('consistency-waveform-graph', 'figure'),
         Output('consistency-curve-count-label', 'children', allow_duplicate=True)],
        [Input('consistency-index-slider', 'value'),
         Input('consistency-key-dropdown', 'value')],
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
        
        # 收集 Record 和 Replay 的 Key ID
        rec_data = analyzer.get_initial_valid_record_data() or []
        rep_data = analyzer.get_initial_valid_replay_data() or []
        for note in rec_data: keys.add(note.id)
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
        
    # 取第一个算法作为基准（假设所有文件录制音轨一致）
    base_analyzer = active_algorithms[0].analyzer
    if not base_analyzer:
        return 0, [0, 0], None, ""
        
    record_data = base_analyzer.get_initial_valid_record_data() or []
    key_record_notes = sorted([n for n in record_data if n.id == key_id], key=lambda x: x.offset)
    count = len(key_record_notes)
    
    if count == 0:
         return 0, [0, 0], None, "该按键无录制数据"
    
    max_val = max(0, count - 1)
    marks = {}
    
    def format_time(idx):
        if 0 <= idx < count:
            note = key_record_notes[idx]
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
    label_text = f"总计 {count} 组曲线，时间范围: {start_time} - {end_time}"
    
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
        
    # 1. 提取 Record 数据 (取第一个算法作为基准)
    base_analyzer = active_algorithms[0].analyzer
    full_record_data = base_analyzer.get_initial_valid_record_data() or []
    full_key_record_notes = sorted([n for n in full_record_data if n.id == key_id], key=lambda x: x.offset)
    
    total_record_count = len(full_key_record_notes)
    if total_record_count == 0:
        return no_update, "无录制数据"
        
    # 解析范围
    start_idx = 0
    end_idx = total_record_count - 1
    if isinstance(slider_value, list) and len(slider_value) == 2:
        start_idx = max(0, slider_value[0])
        end_idx = min(total_record_count - 1, slider_value[1])
    
    sliced_record_notes = full_key_record_notes[start_idx : end_idx + 1]
    
    # 2. 提取所有算法的 Replay 数据
    replay_sources = []
    min_ts = sliced_record_notes[0].key_on_ms if sliced_record_notes and sliced_record_notes[0].key_on_ms else -1
    max_ts = sliced_record_notes[-1].key_on_ms if sliced_record_notes and sliced_record_notes[-1].key_on_ms else float('inf')

    for alg in active_algorithms:
        alg_name = alg.metadata.algorithm_name
        analyzer = alg.analyzer
        
        full_replay_data = analyzer.get_initial_valid_replay_data() or []
        key_replay_notes = sorted([n for n in full_replay_data if n.id == key_id], key=lambda x: x.offset)
        
        # 按时间范围切片 Replay
        sliced_replay_notes = [
             n for n in key_replay_notes 
             if n.key_on_ms is not None and (min_ts - 500 <= n.key_on_ms <= max_ts + 500)
        ]
        
        replay_sources.append({
            'label': f"Replay ({alg_name})",
            'notes': sliced_replay_notes
        })

    # 3. 生成图表
    fig = ConsistencyPlotter.generate_key_waveform_consistency_plot(
        record_notes=sliced_record_notes,
        replay_sources=replay_sources,
        key_id=key_id,
        total_record_count=total_record_count
    )
    
    # 4. 计算显示标签
    current_count = len(sliced_record_notes)
    start_str = "N/A"
    end_str = "N/A"
    if sliced_record_notes:
        n1 = sliced_record_notes[0]
        n2 = sliced_record_notes[-1]
        if n1.key_on_ms: start_str = f"{n1.key_on_ms/1000:.1f}s"
        if n2.key_on_ms: end_str = f"{n2.key_on_ms/1000:.1f}s"
        
    label_text = f"显示范围: {start_idx + 1} - {end_idx + 1} (共 {current_count} 组, 时间: {start_str} - {end_str})"
    
    return fig, label_text
