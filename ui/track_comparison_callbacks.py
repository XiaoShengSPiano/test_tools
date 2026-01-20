#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
播放音轨对比页面的回调函数
"""


import traceback
import time
import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, html, no_update, ctx, dash_table
from dash.exceptions import PreventUpdate
from typing import List, Dict, Any

from utils.logger import Logger

logger = Logger.get_logger()


# ==================== Handler Functions ====================

def update_track_selection_handler(pathname, trigger, session_id, session_manager):
    """
    从全局文件管理中获取已上传文件，生成音轨选择界面

    Args:
        pathname: 当前页面路径
        trigger: 全局文件列表更新触发器
        session_id: 会话ID
        session_manager: SessionManager实例

    Returns:
        (提示区域样式, 音轨选择UI, 设置区域样式)
    """
    # 只在音轨对比页面才更新
    if pathname != '/track-comparison':
        print(f"   ❌ 不在音轨对比页面，跳过")
        raise PreventUpdate

    print(f"   ✅ 在音轨对比页面，继续执行")

    # 从全局获取已上传的文件
    try:
        # 首先尝试从当前session获取backend
        backend = None
        if session_id:
            backend = session_manager.get_backend(session_id)

        # 如果当前session没有backend，或者backend中没有文件，尝试从所有backend中找
        if not backend or (backend and len(backend.get_active_algorithms()) == 0):
            # 遍历所有backend，找到有文件的那个
            for sid, b in session_manager.backends.items():
                if b and len(b.get_active_algorithms()) > 0:
                    backend = b
                    break

        if not backend:
            return (
                {'display': 'block'},
                create_empty_selection_ui(),
                {'display': 'none'}
            )



        # 获取激活的算法（已上传的文件）
        active_algorithms = backend.get_active_algorithms()
        logger.info(f"获取到 {len(active_algorithms)} 个激活的算法")

        if len(active_algorithms) < 2:
            return (
                {'display': 'block'},
                create_empty_selection_ui(len(active_algorithms)),
                {'display': 'none'}
            )

        # 生成音轨选择UI
        selection_ui = create_track_selection_ui(active_algorithms)

        return (
            {'display': 'none'},
            selection_ui,
            {'display': 'block'}
        )

    except Exception as e:
        logger.error(f"更新音轨选择失败: {e}")
        traceback.print_exc()
        return (
            {'display': 'block'},
            create_empty_selection_ui(),
            {'display': 'none'}
        )

def update_comparison_settings_handler(baseline_values, pathname):
        """
        更新对比设置区域（显示开始对比按钮）
        
        Args:
            baseline_values: 标准音轨选择
            pathname: 当前页面
        
        Returns:
            对比设置UI
        """
        if pathname != '/track-comparison':
            raise PreventUpdate
        
        return html.Div([
            dbc.Button(
                [
                    html.I(className="bi bi-play-circle-fill me-2"),
                    "开始对比分析"
                ],
                id='start-comparison-btn',
                color="primary",
                size="lg",
                className="w-100"
            )
        ])


def perform_comparison_handler(n_clicks, checkbox_values, checkbox_ids, baseline_values, session_id, session_manager):
        """
        执行音轨对比分析
        
        Args:
            n_clicks: 按钮点击次数
            checkbox_values: 选中状态列表
            checkbox_ids: checkbox ID列表
            baseline_values: 标准音轨选择
            session_id: 会话ID
        
        Returns:
            (结果UI, 显示样式)
        """
        if not n_clicks:
            raise PreventUpdate
        
        logger.info("🎯 开始执行音轨对比分析")
        
        try:
            # 获取backend
            backend = session_manager.get_backend(session_id)
            if not backend:
                # 尝试从其他session找
                for sid, b in session_manager.backends.items():
                    if b and len(b.get_active_algorithms()) > 0:
                        backend = b
                        break
            
            if not backend:
                return (
                    dbc.Alert("无法获取backend实例", color="danger"),
                    {'display': 'block'},
                    no_update
                )
            
            # 获取选中的音轨名称
            selected_tracks = []
            for idx, (value, id_dict) in enumerate(zip(checkbox_values, checkbox_ids)):
                if value:  # checkbox被选中
                    selected_tracks.append(id_dict['index'])
            
            # 获取标准音轨
            baseline_track = None
            for value in baseline_values:
                if value:
                    baseline_track = value
                    break
            
            logger.info(f"选中的音轨: {selected_tracks}")
            logger.info(f"标准音轨: {baseline_track}")
            
            if not baseline_track:
                return (
                    dbc.Alert("请先选择标准音轨", color="warning"),
                    {'display': 'block'},
                    no_update
                )

            if len(selected_tracks) < 2:
                return (
                    dbc.Alert("请至少选择2个音轨进行对比", color="warning"),
                    {'display': 'block'},
                    no_update
                )
            
            # 执行对比
            comparison_results = perform_track_comparison(
                backend, selected_tracks, baseline_track
            )

            # 生成结果UI
            results_ui = create_comparison_results_ui(comparison_results)

            # 准备可序列化的存储数据（移除 Note 对象）
            serializable_results = {
                'baseline_track': comparison_results['baseline_track'],
                'comparisons': []
            }
            
            for comp in comparison_results['comparisons']:
                # 只保留可序列化的数据，移除 Note 对象
                serializable_comp = {
                    'compare_name': comp['compare_name'],
                    'baseline_name': comp['baseline_name'],
                    'total_matches': comp['total_matches'],
                    'matched_pairs': comp['matched_pairs'],  # 已经是字典列表，可序列化
                    'grade_counts': comp['grade_counts'],
                    'grade_percentages': comp['grade_percentages'],
                    # 保存未匹配的数量
                    'unmatched_baseline_count': len(comp['unmatched_baseline']),
                    'unmatched_compare_count': len(comp['unmatched_compare'])
                }
                serializable_results['comparisons'].append(serializable_comp)
            
            store_data = {
                'results': serializable_results,
                'timestamp': time.time()
            }

            return (results_ui, {'display': 'block'}, store_data)

        except Exception as e:
            logger.error(f"音轨对比失败: {e}")
            traceback.print_exc()
            return (
                dbc.Alert(f"对比失败: {str(e)}", color="danger"),
                {'display': 'block'},
                no_update
            )


def toggle_comparison_detail_table_handler(grade_btn_clicks, hide_btn_clicks, store_data):
    """
    显示或隐藏音轨对比详细表格

    Args:
        grade_btn_clicks: 评级按钮点击次数列表
        hide_btn_clicks: 隐藏按钮点击次数
        store_data: 存储的对比结果数据

    Returns:
        (表格区域样式, 表格数据, 表格列)
    """
    ctx = dash.callback_context
    if not ctx.triggered:
        return {'display': 'none'}, [], []

    # 获取触发源
    trigger_id = ctx.triggered[0]['prop_id']
    
    # 如果是隐藏按钮触发，直接返回隐藏状态
    if 'hide-track-comparison-detail-table' in trigger_id:
        return {'display': 'none'}, [], []

    # 否则是评级按钮触发，显示对应等级的数据
    button_index = eval(trigger_id.split('.')[0])['index']  # "音轨A_EXCELLENT"

    # 解析按钮索引
    compare_name, grade_key = button_index.rsplit('_', 1)

    logger.info(f"显示详细表格: {compare_name}, 等级: {grade_key}")

    # 从存储中获取数据
    if not store_data or 'results' not in store_data:
        return {'display': 'none'}, [], []

    results = store_data['results']
    baseline_track = results.get('baseline_track', '未知')
    comparisons = results.get('comparisons', [])

    # 找到对应的对比数据
    target_comparison = None
    for comp in comparisons:
        if comp['compare_name'] == compare_name:
            target_comparison = comp
            break

    if not target_comparison:
        return {'display': 'none'}, [], []

    # 过滤指定等级的匹配对
    matched_pairs = target_comparison['matched_pairs']
    filtered_pairs = [pair for pair in matched_pairs if pair['grade'] == grade_key]

    if not filtered_pairs:
        return {'display': 'none'}, [], []

    # 创建表格数据 - 交替显示标准音轨和对比音轨的数据
    table_data = []
    for pair in filtered_pairs:
        # 第一行：标准音轨的数据
        table_data.append({
            'row_type': baseline_track,  # 标准音轨文件名
            '数据类型': '标准',
            '琴键编号': pair['key_id'],
            '序号': pair['sequence'],
            '时间': f"{pair['baseline_keyon']:.2f}ms",
            '锤击时间': f"{pair['baseline_hammer_time']:.2f}ms",
            '锤速': f"{int(pair['baseline_hammer_velocity'])}",
            '持续时间': f"{pair['baseline_duration']:.2f}ms",
            'keyon时间差': '',  # 标准行不需要显示差异
            '锤击时间差': '',
            '持续时间差': '',
            '锤速差': '',
            '评级': grade_key
        })

        # 第二行：对比音轨的数据
        table_data.append({
            'row_type': compare_name,  # 对比音轨文件名
            '数据类型': '对比',
            '琴键编号': pair['key_id'],
            '序号': pair['sequence'],
            '时间': f"{pair['compare_keyon']:.2f}ms",
            '锤击时间': f"{pair['compare_hammer_time']:.2f}ms",
            '锤速': f"{int(pair['compare_hammer_velocity'])}",
            '持续时间': f"{pair['compare_duration']:.2f}ms",
            'keyon时间差': f"{pair['keyon_diff_ms']:+.2f}ms",
            '锤击时间差': f"{pair['hammer_time_diff_ms']:+.2f}ms",
            '持续时间差': f"{pair['duration_diff_ms']:+.2f}ms",
            '锤速差': f"{pair['hammer_velocity_diff']}" if isinstance(pair['hammer_velocity_diff'], str) else f"{int(pair['hammer_velocity_diff'])}",
            '评级': grade_key
        })

    # 定义表格列
    columns = [
        {'name': 'SPMID文件', 'id': 'row_type'},  # SPMID文件名
        {'name': '数据类型', 'id': '数据类型'},  # 标准/对比
        {'name': '琴键编号', 'id': '琴键编号', 'type': 'numeric'},
        {'name': '序号', 'id': '序号', 'type': 'numeric'},
        {'name': '时间', 'id': '时间', 'type': 'text'},
        {'name': '锤击时间', 'id': '锤击时间', 'type': 'text'},
        {'name': '锤速', 'id': '锤速', 'type': 'text'},
        {'name': '持续时间', 'id': '持续时间', 'type': 'text'},
        {'name': 'keyon时间差', 'id': 'keyon时间差', 'type': 'text'},
        {'name': '锤击时间差', 'id': '锤击时间差', 'type': 'text'},
        {'name': '持续时间差', 'id': '持续时间差', 'type': 'text'},
        {'name': '锤速差', 'id': '锤速差', 'type': 'text'},
        {'name': '评级', 'id': '评级', 'type': 'text'}
    ]

    logger.info(f"更新表格: {len(table_data)} 行数据")
    return {'display': 'block'}, table_data, columns


# ==================== Callback Registration ====================

def register_callbacks(app, session_manager):
    """
    注册音轨对比页面的回调

    Args:
        app: Dash应用实例
        session_manager: SessionManager实例
    """

    @app.callback(
        Output('track-comparison-file-prompt', 'style'),
        Output('track-selection-content', 'children'),
        Output('comparison-settings-area', 'style'),
        Input('url', 'pathname'),  # 监听页面变化
        Input('algorithm-list-trigger', 'data'),  # 监听全局文件列表变化
        State('session-id', 'data'),  # 获取session ID
    )
    def update_track_selection(pathname, trigger, session_id):
        return update_track_selection_handler(pathname, trigger, session_id, session_manager)

    @app.callback(
        Output('comparison-settings-content', 'children'),
        Input({'type': 'baseline-radio', 'index': dash.ALL}, 'value'),
        State('url', 'pathname'),
        prevent_initial_call=True
    )
    def update_comparison_settings(baseline_values, pathname):
        return update_comparison_settings_handler(baseline_values, pathname)

    @app.callback(
        Output('comparison-results-area', 'children'),
        Output('comparison-results-area', 'style'),
        Output('track-comparison-store', 'data'),
        Input('start-comparison-btn', 'n_clicks'),
        State({'type': 'track-select-checkbox', 'index': dash.ALL}, 'value'),
        State({'type': 'track-select-checkbox', 'index': dash.ALL}, 'id'),
        State({'type': 'baseline-radio', 'index': dash.ALL}, 'value'),
        State('session-id', 'data'),
        prevent_initial_call=True
    )
    def perform_comparison(n_clicks, checkbox_values, checkbox_ids, baseline_values, session_id):
        return perform_comparison_handler(n_clicks, checkbox_values, checkbox_ids, baseline_values, session_id, session_manager)

    @app.callback(
        Output('track-comparison-detail-table-area', 'style'),
        Output('track-comparison-detail-datatable', 'data'),
        Output('track-comparison-detail-datatable', 'columns'),
        Input({'type': 'track-comparison-grade-btn', 'index': dash.ALL}, 'n_clicks'),
        Input('hide-track-comparison-detail-table', 'n_clicks'),
        State('track-comparison-store', 'data'),
        prevent_initial_call=True
    )
    def toggle_comparison_detail_table(grade_btn_clicks, hide_btn_clicks, store_data):
        return toggle_comparison_detail_table_handler(grade_btn_clicks, hide_btn_clicks, store_data)


def perform_track_comparison(backend, selected_tracks, baseline_track):
    """
    执行音轨对比分析
    
    Args:
        backend: PianoAnalysisBackend实例
        selected_tracks: 选中的音轨名称列表
        baseline_track: 标准音轨名称
    
    Returns:
        dict: 对比结果
    """
    logger.info(f"🔍 执行对比分析，标准音轨: {baseline_track}")
    
    # 获取所有算法
    algorithms = backend.get_active_algorithms()
    alg_dict = {alg.metadata.algorithm_name: alg for alg in algorithms}
    
    # 获取标准音轨数据
    baseline_alg = alg_dict.get(baseline_track)
    if not baseline_alg or not baseline_alg.analyzer:
        raise ValueError(f"标准音轨 {baseline_track} 数据无效")
    
    # 从标准音轨的analyzer中获取播放音符数据（使用初始的有效数据，而非匹配后的数据）
    baseline_notes = baseline_alg.analyzer.initial_valid_replay_data
    if not baseline_notes:
        raise ValueError(f"标准音轨 {baseline_track} 没有有效的播放音符")
    
    logger.info(f"📊 标准音轨有 {len(baseline_notes)} 个音符")
    
    # 对比结果
    results = {
        'baseline_track': baseline_track,
        'comparisons': []
    }
    
    # 对每个非标准音轨进行对比
    for track_name in selected_tracks:
        if track_name == baseline_track:
            continue
        
        compare_alg = alg_dict.get(track_name)
        if not compare_alg or not compare_alg.analyzer:
            logger.warning(f"跳过无效音轨: {track_name}")
            continue
        
        compare_notes = compare_alg.analyzer.initial_valid_replay_data
        if not compare_notes:
            logger.warning(f"跳过空音轨: {track_name}")
            continue
        
        logger.info(f"🔄 对比 {track_name}，有 {len(compare_notes)} 个音符")
        
        # 执行严格按序号匹配
        comparison = compare_tracks_strict_sequence(
            baseline_notes, compare_notes, baseline_track, track_name
        )
        
        results['comparisons'].append(comparison)
    
    return results


def classify_keyon_error(error_abs_ms: float) -> str:
    """
    根据 Key-On 时间差的绝对值分级
    
    Args:
        error_abs_ms: 时间差绝对值（毫秒）
    
    Returns:
        str: 等级名称
    """
    if error_abs_ms <= 20:
        return 'EXCELLENT'
    elif error_abs_ms <= 30:
        return 'GOOD'
    elif error_abs_ms <= 50:
        return 'FAIR'
    elif error_abs_ms <= 100:
        return 'POOR'
    elif error_abs_ms <= 200:
        return 'SEVERE'
    else:
        return 'FAILED'


def compare_tracks_strict_sequence(baseline_notes, compare_notes, baseline_name, compare_name):
    """
    严格按序号匹配两个音轨，并进行分等级统计
    
    Args:
        baseline_notes: 标准音轨的Note列表
        compare_notes: 对比音轨的Note列表
        baseline_name: 标准音轨名称
        compare_name: 对比音轨名称
    
    Returns:
        dict: 对比结果
    """
    from collections import defaultdict
    
    logger.info(f"开始严格序号匹配: {compare_name} vs {baseline_name}")
    
    # 按琴键编号(note.id)分组
    baseline_by_key = defaultdict(list)
    compare_by_key = defaultdict(list)
    
    for note in baseline_notes:
        baseline_by_key[note.id].append(note)
    
    for note in compare_notes:
        compare_by_key[note.id].append(note)
    
    # 对每个琴键按时间排序
    for key_id in baseline_by_key:
        baseline_by_key[key_id].sort(key=lambda n: n.key_on_ms)
    
    for key_id in compare_by_key:
        compare_by_key[key_id].sort(key=lambda n: n.key_on_ms)
    
    # 匹配结果
    matched_pairs = []
    unmatched_baseline = []
    unmatched_compare = []
    
    # 初始化等级计数器
    grade_counts = {
        'EXCELLENT': 0,
        'GOOD': 0,
        'FAIR': 0,
        'POOR': 0,
        'SEVERE': 0,
        'FAILED': 0,
    }
    
    # 对每个琴键进行严格序号匹配
    all_key_ids = set(baseline_by_key.keys()) | set(compare_by_key.keys())
    
    for key_id in sorted(all_key_ids):
        baseline_group = baseline_by_key.get(key_id, [])
        compare_group = compare_by_key.get(key_id, [])
        
        # 严格按序号匹配
        min_len = min(len(baseline_group), len(compare_group))
        
        for i in range(min_len):
            b_note = baseline_group[i]
            c_note = compare_group[i]
            
            # 计算 Key-On 时间差
            keyon_diff = c_note.key_on_ms - b_note.key_on_ms
            keyon_diff_abs = abs(keyon_diff)
            
            # 分级
            grade = classify_keyon_error(keyon_diff_abs)
            grade_counts[grade] += 1
            
            # 计算各种时间差
            b_hammer_time = b_note.get_first_hammer_time() if hasattr(b_note, 'get_first_hammer_time') else None
            c_hammer_time = c_note.get_first_hammer_time() if hasattr(c_note, 'get_first_hammer_time') else None
            hammer_time_diff = (c_hammer_time * 10) - (b_hammer_time * 10) if b_hammer_time is not None and c_hammer_time is not None else 0

            duration_diff = (c_note.duration_ms - b_note.duration_ms) if hasattr(b_note, 'duration_ms') and hasattr(c_note, 'duration_ms') else 0

            b_velocity = b_note.get_first_hammer_velocity() if hasattr(b_note, 'get_first_hammer_velocity') else None
            c_velocity = c_note.get_first_hammer_velocity() if hasattr(c_note, 'get_first_hammer_velocity') else None
            hammer_velocity_diff = c_velocity - b_velocity if b_velocity is not None and c_velocity is not None else 0

            matched_pairs.append({
                'key_id': key_id,
                'sequence': i,
                'baseline_keyon': b_note.key_on_ms,
                'compare_keyon': c_note.key_on_ms,
                'keyon_diff_ms': keyon_diff,
                'keyon_diff_abs': keyon_diff_abs,
                'grade': grade,
                # 标准音轨的额外信息
                'baseline_hammer_velocity': b_note.get_first_hammer_velocity() if hasattr(b_note, 'get_first_hammer_velocity') and b_note.get_first_hammer_velocity() is not None else 0,
                'baseline_hammer_time': (b_note.get_first_hammer_time() * 10) if hasattr(b_note, 'get_first_hammer_time') and b_note.get_first_hammer_time() is not None else 0,  # 转换为0.1ms到ms
                'baseline_duration': b_note.duration_ms if hasattr(b_note, 'duration_ms') else 0,
                # 对比音轨的额外信息
                'compare_hammer_velocity': c_note.get_first_hammer_velocity() if hasattr(c_note, 'get_first_hammer_velocity') and c_note.get_first_hammer_velocity() is not None else 0,
                'compare_hammer_time': (c_note.get_first_hammer_time() * 10) if hasattr(c_note, 'get_first_hammer_time') and c_note.get_first_hammer_time() is not None else 0,  # 转换为0.1ms到ms
                'compare_duration': c_note.duration_ms if hasattr(c_note, 'duration_ms') else 0,
                # 各种差异
                'hammer_time_diff_ms': hammer_time_diff,
                'duration_diff_ms': duration_diff,
                'hammer_velocity_diff': hammer_velocity_diff,
            })
        
        # 记录未匹配的音符
        if len(baseline_group) > min_len:
            unmatched_baseline.extend(baseline_group[min_len:])
        if len(compare_group) > min_len:
            unmatched_compare.extend(compare_group[min_len:])
    
    total_matches = len(matched_pairs)
    logger.info(f"匹配完成: {total_matches} 对匹配，{len(unmatched_baseline)} 个标准未匹配，{len(unmatched_compare)} 个对比未匹配")
    
    # 计算百分比
    grade_percentages = {}
    if total_matches > 0:
        for grade, count in grade_counts.items():
            grade_percentages[grade] = (count / total_matches) * 100
    else:
        for grade in grade_counts.keys():
            grade_percentages[grade] = 0.0
    
    logger.info(f"等级分布: {grade_counts}")
    
    return {
        'compare_name': compare_name,
        'baseline_name': baseline_name,
        'total_matches': total_matches,
        'matched_pairs': matched_pairs,
        'unmatched_baseline': unmatched_baseline,
        'unmatched_compare': unmatched_compare,
        'grade_counts': grade_counts,
        'grade_percentages': grade_percentages,
    }


def create_comparison_results_ui(results):
    """
    创建对比结果UI（匹配质量评估风格）

    Args:
        results: 对比结果字典

    Returns:
        html.Div: 结果UI组件
    """
    baseline_track = results['baseline_track']
    comparisons = results['comparisons']

    if not comparisons:
        return dbc.Alert("没有可对比的结果", color="info")

    result_cards = []

    # 等级配置（匹配质量评估的风格）
    grade_configs = [
        ('EXCELLENT', '优秀 (≤20ms)', 'success'),
        ('GOOD', '良好 (20-30ms)', 'info'),
        ('FAIR', '一般 (30-50ms)', 'primary'),
        ('POOR', '较差 (50-100ms)', 'warning'),
        ('SEVERE', '严重 (100-200ms)', 'danger'),
        ('FAILED', '失败 (>200ms)', 'dark'),
    ]

    for comp in comparisons:
        grade_counts = comp['grade_counts']
        grade_percentages = comp['grade_percentages']
        total_matches = comp['total_matches']

        # 创建评级统计按钮行（匹配质量评估风格）
        grade_cols = []
        for grade_key, grade_name, color_class in grade_configs:
            count = grade_counts[grade_key]
            percentage = grade_percentages[grade_key]

            grade_cols.append(
                dbc.Col([
                    html.Div([
                        dbc.Button(
                            f"{count}",
                            id={'type': 'track-comparison-grade-btn', 'index': f"{comp['compare_name']}_{grade_key}"},
                            color=color_class,
                            size='lg',
                            className="mb-1",
                            disabled=(count == 0),
                            style={'fontSize': '24px', 'fontWeight': 'bold', 'width': '100%'}
                        ),
                        html.P(f"{grade_name}", className="text-muted mb-0"),
                        html.Small(f"{percentage:.1f}%", className="text-muted", style={'fontSize': '10px'})
                    ], className="text-center")
                ], width='auto', className="px-2")
            )

        # 计算总匹配对数
        total_count = total_matches

        # 创建统计卡片
        card = dbc.Card([
            dbc.CardHeader([
                html.I(className="bi bi-bar-chart-line me-2"),
                html.Strong(f"{comp['compare_name']} vs {baseline_track}")
            ]),
            dbc.CardBody([
                # 总体统计行
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            html.H3(f"{total_count}", className="text-info mb-1"),
                            html.P("总匹配对数", className="text-muted mb-0"),
                            html.Small(f"{comp['compare_name']} vs {baseline_track}", className="text-muted", style={'fontSize': '10px'})
                        ], className="text-center")
                    ], width=12)
                ], className="mb-3"),

                # 评级统计按钮行
                dbc.Row(grade_cols, className="mb-3 justify-content-center"),

                # 额外统计信息
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            html.Strong("标准未匹配: ", className="text-muted"),
                            html.Span(f"{comp.get('unmatched_baseline_count', len(comp.get('unmatched_baseline', [])))}", className="fs-6 text-warning fw-bold")
                        ])
                    ], width=6),
                    dbc.Col([
                        html.Div([
                            html.Strong("对比未匹配: ", className="text-muted"),
                            html.Span(f"{comp.get('unmatched_compare_count', len(comp.get('unmatched_compare', [])))}", className="fs-6 text-warning fw-bold")
                        ])
                    ], width=6)
                ], className="text-center text-muted")
            ])
        ], className="mb-3")

        result_cards.append(card)

    return html.Div([
        html.H4([
            html.I(className="bi bi-check-circle-fill text-success me-2"),
            "音轨对比分析结果"
        ], className="mb-4"),
        html.Div(result_cards)
    ])


def create_empty_selection_ui(file_count: int = 0) -> html.Div:
    """
    创建空的选择UI（没有足够文件时）
    
    Args:
        file_count: 当前文件数量
    
    Returns:
        UI组件
    """
    if file_count == 0:
        message = "当前没有已上传的SPMID文件"
    elif file_count == 1:
        message = f"当前只有1个文件，需要至少2个文件才能进行对比"
    else:
        message = "正在加载文件..."
    
    return html.Div([
        html.P([
            html.I(className="bi bi-inbox me-2"),
            message
        ], className="text-muted text-center py-4")
    ])


def create_track_selection_ui(algorithms) -> html.Div:
    """
    创建音轨选择UI
    
    Args:
        algorithms: 已上传的算法列表
    
    Returns:
        UI组件
    """
    print(f"   🎨 [create_track_selection_ui] 开始创建UI，算法数量: {len(algorithms)}")
    logger.info(f"创建音轨选择UI，共 {len(algorithms)} 个算法")
    
    track_options = []
    
    for idx, alg in enumerate(algorithms):
        try:
            algorithm_name = alg.metadata.algorithm_name
            
            # 尝试获取音符数量（使用初始播放音符数据）
            note_count = "未知"
            try:
                if alg.analyzer:
                    if alg.analyzer.initial_valid_replay_data:
                        note_count = len(alg.analyzer.initial_valid_replay_data)
                    elif alg.analyzer.valid_replay_data:
                        note_count = len(alg.analyzer.valid_replay_data)
                    elif hasattr(alg.analyzer, 'matched_pairs'):
                        note_count = len(alg.analyzer.matched_pairs)
            except Exception as e:
                logger.debug(f"获取音符数量失败: {e}")
            
            is_first = (idx == 0)  # 第一个默认设为标准
            
            track_options.append(
                dbc.Card([
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.Div([
                                    dbc.Checkbox(
                                        id={'type': 'track-select-checkbox', 'index': algorithm_name},
                                        value=True,  # 默认选中
                                        className="me-2"
                                    ),
                                    html.Span(algorithm_name, className="fw-bold"),
                                    html.Small(
                                        f" · {note_count} 音符" if isinstance(note_count, int) else f" · {note_count}",
                                        className="text-muted ms-2"
                                    )
                                ], className="d-flex align-items-center")
                            ], width=8),
                            dbc.Col([
                                html.Div([
                                    dbc.RadioItems(
                                        id={'type': 'baseline-radio', 'index': algorithm_name},
                                        options=[{'label': '标准', 'value': algorithm_name}],
                                        value=algorithm_name if is_first else None,
                                        inline=True,
                                        className="text-end"
                                    )
                                ], className="text-end")
                            ], width=4)
                        ])
                    ], style={'padding': '12px'})
                ], className="mb-2")
            )
            
            logger.debug(f"添加音轨选项: {algorithm_name}, 音符数: {note_count}")
            
        except Exception as e:
            logger.error(f"创建音轨选项失败: {e}")
            continue
    
    if not track_options:
        return create_empty_selection_ui()
    
    return html.Div([
        html.P([
            html.I(className="bi bi-info-circle me-2"),
            f"找到 {len(track_options)} 个播放音轨，请勾选要对比的音轨，并选择其中一个作为标准"
        ], className="text-muted mb-3"),
        html.Div(track_options),
        html.Hr(className="my-3"),
        html.Small([
            html.I(className="bi bi-lightbulb me-1"),
            "提示：标准音轨将作为对比的基准，其他音轨的差异将相对于标准音轨计算"
        ], className="text-muted")
    ])


