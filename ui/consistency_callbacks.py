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
         Input('active-algorithm-store', 'data'),
         Input('algorithm-management-trigger', 'data')]
    )
    def update_key_options(session_id, active_algorithm_name, management_trigger):
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

def _get_base_consistency_data(key_id, session_id, session_manager, active_algorithm_name=None):
    """
    获取一致性分析所需的基础数据（算法列表和指定按键的录制数据）
    优先使用 active_algorithm_name 指定的算法作为基准
    """
    if key_id is None or not session_id:
        return None, None
        
    backend = session_manager.get_backend(session_id)
    if not backend:
        return None, None
        
    active_algorithms = backend.get_active_algorithms()
    if not active_algorithms:
        return None, None
        
    # 确定基准算法
    target_alg = active_algorithms[0]
    if active_algorithm_name:
        found = next((a for a in active_algorithms if a.metadata.algorithm_name == active_algorithm_name), None)
        if found:
            target_alg = found
            
    base_analyzer = target_alg.analyzer
    if not base_analyzer:
        return None, None
        
    record_data = base_analyzer.get_initial_valid_record_data() or []
    key_record_notes = sorted([n for n in record_data if n.id == key_id], key=lambda x: x.offset)
    
    return active_algorithms, key_record_notes

def _handle_update_slider_range(key_id, session_id, active_algorithm_name, session_manager):
    active_algorithms, key_record_notes = _get_base_consistency_data(key_id, session_id, session_manager, active_algorithm_name)
    
    if key_record_notes is None:
        return 0, [0, 0], None, ""
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
    # 获取后端
    backend = session_manager.get_backend(session_id)
    if not backend:
        return no_update, no_update
        
    active_algorithms = backend.get_active_algorithms()
    if not active_algorithms:
        return no_update, "无活跃算法"

    logger.debug(f"[DEBUG] ConsistencyPlot: 活跃算法数量: {len(active_algorithms)}")

    # 收集所有数据源
    data_sources = []
    
    # 解析范围（基于索引）
    start_idx = 0
    end_idx = float('inf')
    
    if isinstance(slider_value, list) and len(slider_value) == 2:
        start_idx = max(0, slider_value[0])
        # slider 的值就是索引
        end_idx = slider_value[1]
    
    # [DEBUG] 打印索引范围
    logger.info(f"ConsistencyPlot: 选中索引范围: {start_idx} - {end_idx}")

    # 遍历提取所有算法的数据
    for alg in active_algorithms:
        alg_name = alg.metadata.algorithm_name
        display_name = alg.metadata.display_name or alg_name
        
        analyzer = alg.analyzer
        
        # 1. 提取 Record (Ground Truth)
        # 注意：这里我们使用 get_initial_valid_record_data 获取所有有效数据
        full_rec = analyzer.get_initial_valid_record_data() or []
        key_rec = [n for n in full_rec if n.id == key_id]
        key_rec.sort(key=lambda x: x.offset)
        
        # 2. 提取 Replay
        full_rep = analyzer.get_initial_valid_replay_data() or []
        key_rep = [n for n in full_rep if n.id == key_id]
        key_rep.sort(key=lambda x: x.offset)
        
        # 3. 按索引切片 (独立切片，确保每个算法的对应索引数据都能显示)
        # 无论时间是否对齐，我们都展示该段索引的数据
        curr_rec_len = len(key_rec)
        curr_rep_len = len(key_rep)
        
        rec_end_actual = min(curr_rec_len - 1, int(end_idx))
        rep_end_actual = min(curr_rep_len - 1, int(end_idx))
        
        sliced_rec = []
        if start_idx < curr_rec_len:
             sliced_rec = key_rec[int(start_idx) : rec_end_actual + 1]
             
        sliced_rep = []
        if start_idx < curr_rep_len:
             sliced_rep = key_rep[int(start_idx) : rep_end_actual + 1]
        
        # [DEBUG] 打印该算法的数据统计
        rec_range = f"{sliced_rec[0].key_on_ms:.1f}-{sliced_rec[-1].key_on_ms:.1f}" if sliced_rec else "None"
        logger.info(f"ConsistencyPlot: 算法 {display_name}: Rec总数={len(key_rec)}, 切片后Rec={len(sliced_rec)} (Range:{rec_range}), Rep={len(sliced_rep)}")
        
        data_sources.append({
            'name': display_name,
            'record_notes': sliced_rec,
            'replay_notes': sliced_rep
        })

    # 生成图表
    fig = ConsistencyPlotter.generate_key_waveform_consistency_plot(
        data_sources=data_sources,
        key_id=key_id
    )
    
    return fig, "" # Label text handled by slider callback mostly, or could update here if needed
    if sliced_record_notes:
        n1 = sliced_record_notes[0]
        n2 = sliced_record_notes[-1]
        if n1.key_on_ms: start_str = f"{n1.key_on_ms/1000:.1f}s"
        if n2.key_on_ms: end_str = f"{n2.key_on_ms/1000:.1f}s"
        
    label_text = f"显示范围: {start_idx + 1} - {end_idx + 1} (共 {current_count} 组, 时间: {start_str} - {end_str})"
    
    return fig, label_text
