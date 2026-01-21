#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
播放音轨对比页面的回调函数
"""

import json
import traceback
import time
import dash
import dash_bootstrap_components as dbc
from dash import dcc, Input, Output, State, html, no_update, ctx, dash_table
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
                # 处理未匹配数据，使其可序列化
                serializable_baseline_unmatched = []
                for note in comp['unmatched_baseline']:
                    serializable_baseline_unmatched.append({
                        'id': note.id,
                        'uuid': getattr(note, 'uuid', None),
                        'key_on_ms': getattr(note, 'key_on_ms', None),
                        'key_off_ms': getattr(note, 'key_off_ms', None),
                        'duration_ms': getattr(note, 'duration_ms', None),
                        'first_hammer_time': note.get_first_hammer_time(),
                        'first_hammer_velocity': note.get_first_hammer_velocity()
                    })

                serializable_compare_unmatched = []
                for note in comp['unmatched_compare']:
                    serializable_compare_unmatched.append({
                        'id': note.id,
                        'uuid': getattr(note, 'uuid', None),
                        'key_on_ms': getattr(note, 'key_on_ms', None),
                        'key_off_ms': getattr(note, 'key_off_ms', None),
                        'duration_ms': getattr(note, 'duration_ms', None),
                        'first_hammer_time': note.get_first_hammer_time(),
                        'first_hammer_velocity': note.get_first_hammer_velocity()
                    })

                serializable_comp = {
                    'compare_name': comp['compare_name'],
                    'baseline_name': comp['baseline_name'],
                    'total_matches': comp['total_matches'],
                    'matched_pairs': comp['matched_pairs'],  # 已经是字典列表，可序列化
                    'unmatched_baseline': serializable_baseline_unmatched,  # 保存可序列化的未匹配数据
                    'unmatched_compare': serializable_compare_unmatched,    # 保存可序列化的未匹配数据
                    'grade_counts': comp['grade_counts'],
                    'grade_percentages': comp['grade_percentages'],
                    # 保存未匹配的数量（向后兼容）
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


def _get_unmatched_table_columns():
    """获取未匹配数据表格的列定义"""
    return [
        {'name': '序号', 'id': '序号', 'type': 'numeric'},
        {'name': 'UUID', 'id': 'uuid', 'type': 'text'},
        {'name': '按键ID', 'id': 'key_id', 'type': 'numeric'},
        {'name': '按键开始时间', 'id': 'key_on_ms', 'type': 'text'},
        {'name': '按键结束时间', 'id': 'key_off_ms', 'type': 'text'},
        {'name': '持续时间', 'id': 'duration_ms', 'type': 'text'},
        {'name': '锤击时间', 'id': 'hammer_time', 'type': 'text'},
        {'name': '锤速', 'id': 'hammer_velocity', 'type': 'text'}
    ]


def _process_unmatched_notes(notes_list):
    """处理未匹配音符列表，返回表格数据（按按键ID分组并分配序号）"""
    from collections import defaultdict

    # 按按键ID分组
    notes_by_key = defaultdict(list)
    for note in notes_list:
        key_id = note['id']
        notes_by_key[key_id].append(note)

    result = []

    # 对每个按键ID的音符按时间排序并分配序号
    for key_id in sorted(notes_by_key.keys()):
        key_notes = notes_by_key[key_id]
        # 按时间排序
        key_notes.sort(key=lambda n: n.get('key_on_ms', 0) or 0)

        # 为每个音符分配按键内部序号
        for seq_idx, note in enumerate(key_notes):
            result.append({
                'uuid': note.get('uuid', 'N/A'),
                'key_id': note['id'],
                '序号': seq_idx + 1,  # 按键内部序号，从1开始
                'key_on_ms': f"{note.get('key_on_ms', 'N/A'):.2f}ms" if note.get('key_on_ms') is not None else 'N/A',
                'key_off_ms': f"{note.get('key_off_ms', 'N/A'):.2f}ms" if note.get('key_off_ms') is not None else 'N/A',
                'duration_ms': f"{note.get('duration_ms', 'N/A'):.2f}ms" if note.get('duration_ms') is not None else 'N/A',
                'hammer_time': f"{note.get('first_hammer_time', 'N/A'):.2f}ms" if note.get('first_hammer_time') is not None else 'N/A',
                'hammer_velocity': f"{note.get('first_hammer_velocity', 'N/A')}" if note.get('first_hammer_velocity') is not None else 'N/A'
            })

    return result


def _get_unmatched_data(target_comparison):
    """获取未匹配数据的完整表格数据"""
    baseline_unmatched_data = []
    compare_unmatched_data = []

    if 'unmatched_baseline' in target_comparison:
        baseline_raw = target_comparison['unmatched_baseline']
        baseline_unmatched_data = _process_unmatched_notes(baseline_raw)

    if 'unmatched_compare' in target_comparison:
        compare_raw = target_comparison['unmatched_compare']
        compare_unmatched_data = _process_unmatched_notes(compare_raw)

    return baseline_unmatched_data, compare_unmatched_data


def _generate_anomaly_table_data(anomaly_pairs, compare_name, baseline_track, grade_key):
    """生成异常匹配数据表格（分行显示，与详细对比表格保持一致的风格）"""
    table_data = []

    for pair in anomaly_pairs:
        baseline_key_id = pair.get('key_id')  # 数据中存储的是 key_id
        compare_key_id = pair.get('key_id')   # 两个音轨的key_id应该相同
        baseline_key_on = pair.get('baseline_keyon', 0)  # 数据中的字段名
        compare_key_on = pair.get('compare_keyon', 0)
        baseline_duration = pair.get('baseline_duration', 0)
        compare_duration = pair.get('compare_duration', 0)
        baseline_hammer_time = pair.get('baseline_hammer_time', 0)
        compare_hammer_time = pair.get('compare_hammer_time', 0)
        baseline_velocity = pair.get('baseline_hammer_velocity', 0)
        compare_velocity = pair.get('compare_hammer_velocity', 0)  # 修正字段名
        hammer_time_diff = pair.get('hammer_time_diff_ms', 0)  # 数据中的字段名

        # 计算锤速还原百分比：(对比锤速 / 标准锤速) * 100%
        velocity_percentage = 0.0
        if baseline_velocity and baseline_velocity != 0:
            velocity_percentage = (compare_velocity / baseline_velocity) * 100

        # 计算差值：对比数据 - 标准数据
        keyon_diff = compare_key_on - baseline_key_on
        hammer_time_diff = compare_hammer_time - baseline_hammer_time
        duration_diff = compare_duration - baseline_duration
        velocity_diff = compare_velocity - baseline_velocity

        # 第一行：标准音轨的数据（差值列为空）
        table_data.append({
            'SPMID文件': baseline_track,
            '数据类型': '标准',
            '琴键编号': baseline_key_id,
            '序号': pair.get('sequence', 0),
            '时间': f"{baseline_key_on:.2f}ms" if baseline_key_on else 'N/A',
            '锤击时间': f"{baseline_hammer_time:.2f}ms" if baseline_hammer_time else 'N/A',
            '锤速': int(baseline_velocity),
            '持续时间': f"{baseline_duration:.2f}ms" if baseline_duration else 'N/A',
            'keyon时间差': '',
            '锤击时间差': '',
            '持续时间差': '',
            '锤速差': '',
            '锤速还原百分比': '',
            '评级': grade_key
        })

        # 第二行：对比音轨的数据（差值列显示差值）
        table_data.append({
            'SPMID文件': compare_name,
            '数据类型': '对比',
            '琴键编号': compare_key_id,
            '序号': pair.get('sequence', 0),
            '时间': f"{compare_key_on:.2f}ms" if compare_key_on else 'N/A',
            '锤击时间': f"{compare_hammer_time:.2f}ms" if compare_hammer_time else 'N/A',
            '锤速': int(compare_velocity),
            '持续时间': f"{compare_duration:.2f}ms" if compare_duration else 'N/A',
            'keyon时间差': f"{keyon_diff:+.2f}ms",
            '锤击时间差': f"{hammer_time_diff:+.2f}ms",
            '持续时间差': f"{duration_diff:+.2f}ms",
            '锤速差': f"{velocity_diff:+d}",
            '锤速还原百分比': f"{velocity_percentage:.1f}%" if velocity_percentage else 'N/A',
            '评级': grade_key
        })

    # 使用与详细对比表格相同的列定义
    columns = [
        {'name': 'SPMID文件', 'id': 'SPMID文件'},
        {'name': '数据类型', 'id': '数据类型'},
        {'name': '琴键编号', 'id': '琴键编号', 'type': 'numeric'},
        {'name': '序号', 'id': '序号', 'type': 'numeric'},
        {'name': '时间', 'id': '时间', 'type': 'text'},
        {'name': '锤击时间', 'id': '锤击时间', 'type': 'text'},
        {'name': '锤速', 'id': '锤速', 'type': 'numeric'},
        {'name': '持续时间', 'id': '持续时间', 'type': 'text'},
        {'name': 'keyon时间差', 'id': 'keyon时间差', 'type': 'text'},
        {'name': '锤击时间差', 'id': '锤击时间差', 'type': 'text'},
        {'name': '持续时间差', 'id': '持续时间差', 'type': 'text'},
        {'name': '锤速差', 'id': '锤速差', 'type': 'text'},
        {'name': '锤速还原百分比', 'id': '锤速还原百分比', 'type': 'text'},
        {'name': '评级', 'id': '评级', 'type': 'text'}
    ]

    return table_data, columns

# ==================== Callback Registration ====================

def update_table_visibility_handler(grade_btn_clicks, hide_btn_clicks):
    """
    处理表格显示/隐藏的回调逻辑

    Args:
        grade_btn_clicks: 评级按钮点击次数列表
        hide_btn_clicks: 隐藏按钮点击次数

    Returns:
        (表格区域样式, 筛选器区域样式, 状态JSON)
    """
    ctx = dash.callback_context
    if not ctx.triggered:
        return {'display': 'none'}, {'display': 'none'}, json.dumps({'compare_name': None, 'grade_key': None})

    trigger_id = ctx.triggered[0]['prop_id']

    # 如果是隐藏按钮触发，隐藏所有区域
    if 'hide-track-comparison-detail-table' in trigger_id:
        return {'display': 'none'}, {'display': 'none'}, json.dumps({'compare_name': None, 'grade_key': None})

    # 如果是评级按钮触发，显示区域并设置状态
    if 'track-comparison-grade-btn' in trigger_id:
        try:
            id_part = trigger_id.split('.')[0]
            id_dict = json.loads(id_part)
            button_index = id_dict['index']
            compare_name, grade_key = button_index.rsplit('_', 1)
            updated_state = json.dumps({'compare_name': compare_name, 'grade_key': grade_key})
            return {'display': 'block', 'marginTop': '20px'}, {'display': 'block'}, updated_state
        except Exception as e:
            logger.error(f"解析评级按钮失败: {e}")
            return {'display': 'none'}, {'display': 'none'}, json.dumps({'compare_name': None, 'grade_key': None})

    return {'display': 'none'}, {'display': 'none'}, json.dumps({'compare_name': None, 'grade_key': None})


def update_key_filter_options_handler(current_state_json, store_data):
    """
    处理按键筛选器选项更新的回调逻辑

    Args:
        current_state_json: 当前表格状态JSON
        store_data: 存储的对比结果数据

    Returns:
        (筛选器选项, 筛选器值)
    """
    try:
        current_state = json.loads(current_state_json) if current_state_json else {}
        compare_name = current_state.get('compare_name')
        grade_key = current_state.get('grade_key')
    except json.JSONDecodeError:
        return [], None

    if not compare_name or not grade_key or not store_data:
        return [], None

    # 从存储中获取数据
    results = store_data.get('results', {})
    comparisons = results.get('comparisons', [])

    # 找到对应的对比数据
    target_comparison = None
    for comparison in comparisons:
        if comparison['compare_name'] == compare_name:
            target_comparison = comparison
            break

    if not target_comparison:
        return [], None

    # 获取当前评级的匹配对
    matched_pairs = target_comparison.get('matched_pairs', [])
    grade_pairs = [pair for pair in matched_pairs if pair.get('grade') == grade_key]

    if not grade_pairs:
        return [], None

    # 提取当前评级的所有按键ID
    key_ids = set()
    for pair in grade_pairs:
        key_id = pair.get('key_id')
        if key_id is not None:
            key_ids.add(key_id)

    # 生成筛选器选项
    key_filter_options = [
        {'label': '请选择按键...', 'value': ''},
        {'label': '全部按键', 'value': 'all'}
    ]

    # 为每个按键ID添加选项
    for key_id in sorted(key_ids):
        key_filter_options.append({
            'label': f'按键 {key_id}',
            'value': str(key_id)
        })

    return key_filter_options, ''


def update_unmatched_area_visibility_handler(current_state_json, key_filter_value, store_data):
    """
    处理未匹配区域显示的回调逻辑

    Args:
        current_state_json: 当前表格状态JSON
        key_filter_value: 按键筛选器值
        store_data: 存储的对比结果数据

    Returns:
        未匹配区域样式
    """
    try:
        current_state = json.loads(current_state_json) if current_state_json else {}
        compare_name = current_state.get('compare_name')
        grade_key = current_state.get('grade_key')
    except json.JSONDecodeError:
        return {'display': 'none'}

    if not compare_name or not grade_key:
        return {'display': 'none'}

    # 检查是否有有效的筛选值
    if key_filter_value:
        return {'display': 'block', 'marginTop': '30px', 'marginBottom': '30px'}

    return {'display': 'none'}


def update_detail_table_handler(current_state_json, key_filter_value, store_data):
    """
    处理详细对比表格更新的回调逻辑

    Args:
        current_state_json: 当前表格状态JSON
        key_filter_value: 按键筛选器值
        store_data: 存储的对比结果数据

    Returns:
        (表格数据, 表格列)
    """
    try:
        current_state = json.loads(current_state_json) if current_state_json else {}
        compare_name = current_state.get('compare_name')
        grade_key = current_state.get('grade_key')
    except json.JSONDecodeError:
        return [], []

    if not compare_name or not grade_key or not store_data:
        return [], []

    # 从存储中获取数据
    results = store_data.get('results', {})
    baseline_track = results.get('baseline_track', '标准音轨')
    comparisons = results.get('comparisons', [])

    # 找到对应的对比数据
    target_comparison = None
    for comparison in comparisons:
        if comparison['compare_name'] == compare_name:
            target_comparison = comparison
            break

    if not target_comparison:
        return [], []

    # 获取当前评级的匹配对
    matched_pairs = target_comparison['matched_pairs']
    grade_pairs = [pair for pair in matched_pairs if pair['grade'] == grade_key]

    # 根据按键筛选器进一步过滤
    if key_filter_value == 'all' or not key_filter_value:
        filtered_pairs = grade_pairs  # 显示当前评级的所有数据
    else:
        # 只显示选定按键的数据
        selected_key_id = int(key_filter_value)
        filtered_pairs = [pair for pair in grade_pairs if pair['key_id'] == selected_key_id]

    if not filtered_pairs:
        return [], []

    # 创建表格数据 - 标准与对比数据分行显示
    table_data = []
    for pair in filtered_pairs:
        # 计算差值：对比数据 - 标准数据
        keyon_diff = pair['compare_keyon'] - pair['baseline_keyon']
        hammer_time_diff = pair['compare_hammer_time'] - pair['baseline_hammer_time']
        duration_diff = pair['compare_duration'] - pair['baseline_duration']
        velocity_diff = pair['compare_hammer_velocity'] - pair['baseline_hammer_velocity']

        # 计算锤速还原百分比：(对比锤速 / 标准锤速) * 100%
        velocity_percentage = 0.0
        if pair['baseline_hammer_velocity'] and pair['baseline_hammer_velocity'] != 0:
            velocity_percentage = (pair['compare_hammer_velocity'] / pair['baseline_hammer_velocity']) * 100

        # 第一行：标准音轨的数据（差值列为空）
        table_data.append({
            'SPMID文件': baseline_track,
            '数据类型': '标准',
            '琴键编号': pair['key_id'],
            '序号': pair['sequence'],
            '时间': f"{pair['baseline_keyon']:.2f}ms",
            '锤击时间': f"{pair['baseline_hammer_time']:.2f}ms",
            '锤速': int(pair['baseline_hammer_velocity']),
            '持续时间': f"{pair['baseline_duration']:.2f}ms",
            'keyon时间差': '',
            '锤击时间差': '',
            '持续时间差': '',
            '锤速差': '',
            '锤速还原百分比': '',
            '评级': grade_key
        })

        # 第二行：对比音轨的数据（差值列显示差值）
        table_data.append({
            'SPMID文件': compare_name,
            '数据类型': '对比',
            '琴键编号': pair['key_id'],
            '序号': pair['sequence'],
            '时间': f"{pair['compare_keyon']:.2f}ms",
            '锤击时间': f"{pair['compare_hammer_time']:.2f}ms",
            '锤速': int(pair['compare_hammer_velocity']),
            '持续时间': f"{pair['compare_duration']:.2f}ms",
            'keyon时间差': f"{keyon_diff:+.2f}ms",
            '锤击时间差': f"{hammer_time_diff:+.2f}ms",
            '持续时间差': f"{duration_diff:+.2f}ms",
            '锤速差': f"{velocity_diff:+d}",
            '锤速还原百分比': f"{velocity_percentage:.1f}%" if velocity_percentage else 'N/A',
            '评级': grade_key
        })

    # 定义表格列
    columns = [
        {'name': 'SPMID文件', 'id': 'SPMID文件'},
        {'name': '数据类型', 'id': '数据类型'},
        {'name': '琴键编号', 'id': '琴键编号', 'type': 'numeric'},
        {'name': '序号', 'id': '序号', 'type': 'numeric'},
        {'name': '时间', 'id': '时间', 'type': 'text'},
        {'name': '锤击时间', 'id': '锤击时间', 'type': 'text'},
        {'name': '锤速', 'id': '锤速', 'type': 'numeric'},
        {'name': '持续时间', 'id': '持续时间', 'type': 'text'},
        {'name': 'keyon时间差', 'id': 'keyon时间差', 'type': 'text'},
        {'name': '锤击时间差', 'id': '锤击时间差', 'type': 'text'},
        {'name': '持续时间差', 'id': '持续时间差', 'type': 'text'},
        {'name': '锤速差', 'id': '锤速差', 'type': 'text'},
        {'name': '锤速还原百分比', 'id': '锤速还原百分比', 'type': 'text'},
        {'name': '评级', 'id': '评级', 'type': 'text'}
    ]

    return table_data, columns


def update_anomaly_table_handler(current_state_json, key_filter_value, store_data):
    """
    处理异常匹配表格更新的回调逻辑

    Args:
        current_state_json: 当前表格状态JSON
        key_filter_value: 按键筛选器值
        store_data: 存储的对比结果数据

    Returns:
        (异常区域样式, 异常空消息样式, 异常表格样式, 异常表格数据, 异常表格列)
    """
    try:
        current_state = json.loads(current_state_json) if current_state_json else {}
        compare_name = current_state.get('compare_name')
        grade_key = current_state.get('grade_key')
    except json.JSONDecodeError:
        return {'display': 'none'}, {'display': 'none'}, {'display': 'none'}, [], []

    if not compare_name or not grade_key or not store_data:
        return {'display': 'none'}, {'display': 'none'}, {'display': 'none'}, [], []

    # 从存储中获取数据
    results = store_data.get('results', {})
    baseline_track = results.get('baseline_track', '标准音轨')
    comparisons = results.get('comparisons', [])

    # 找到对应的对比数据
    target_comparison = None
    for comparison in comparisons:
        if comparison['compare_name'] == compare_name:
            target_comparison = comparison
            break

    if not target_comparison:
        return {'display': 'none'}, {'display': 'none'}, {'display': 'none'}, [], []

    # 获取当前评级的匹配对
    matched_pairs = target_comparison['matched_pairs']
    grade_pairs = [pair for pair in matched_pairs if pair['grade'] == grade_key]

    # 生成异常匹配数据
    anomaly_pairs = []
    for pair in grade_pairs:
        baseline_velocity = pair.get('baseline_hammer_velocity', 0)
        compare_velocity = pair.get('compare_hammer_velocity', 0)
        if (baseline_velocity == 0 and compare_velocity != 0) or (baseline_velocity != 0 and compare_velocity == 0):
            anomaly_pairs.append(pair)

    if anomaly_pairs:
        # 有异常数据，显示表格
        anomaly_table_data, anomaly_columns = _generate_anomaly_table_data(anomaly_pairs, compare_name, baseline_track, grade_key)
        return ({'display': 'block', 'marginTop': '20px', 'marginBottom': '20px'},
                {'display': 'none'},
                {'display': 'block'},
                anomaly_table_data,
                anomaly_columns)
    else:
        # 没有异常数据，显示空消息
        return ({'display': 'block', 'marginTop': '20px', 'marginBottom': '20px'},
                {'display': 'block'},
                {'display': 'none'},
                [],
                [])


def update_unmatched_tables_handler(current_state_json, store_data):
    """
    处理未匹配数据表格更新的回调逻辑

    Args:
        current_state_json: 当前表格状态JSON
        store_data: 存储的对比结果数据

    Returns:
        (空状态样式, 标准区域样式, 对比区域样式, 标准数据, 标准列, 对比数据, 对比列)
    """
    try:
        current_state = json.loads(current_state_json) if current_state_json else {}
        compare_name = current_state.get('compare_name')
    except json.JSONDecodeError:
        return ({'display': 'block'}, {'display': 'none'}, {'display': 'none'},
                [], [], [], [])

    if not compare_name or not store_data:
        return ({'display': 'block'}, {'display': 'none'}, {'display': 'none'},
                [], [], [], [])

    # 从存储中获取数据
    results = store_data.get('results', {})
    comparisons = results.get('comparisons', [])

    # 找到对应的对比数据
    target_comparison = None
    for comparison in comparisons:
        if comparison['compare_name'] == compare_name:
            target_comparison = comparison
            break

    if not target_comparison:
        return ({'display': 'block'}, {'display': 'none'}, {'display': 'none'},
                [], [], [], [])

    # 获取未匹配数据
    unmatched_columns = _get_unmatched_table_columns()
    baseline_unmatched_data, compare_unmatched_data = _get_unmatched_data(target_comparison)

    # 检查是否有数据
    has_baseline_data = len(baseline_unmatched_data) > 0
    has_compare_data = len(compare_unmatched_data) > 0
    has_any_data = has_baseline_data or has_compare_data

    if not has_any_data:
        # 没有数据，显示空状态
        return ({'display': 'block'}, {'display': 'none'}, {'display': 'none'},
                [], [], [], [])
    else:
        # 有数据，显示相应的表格
        baseline_area_style = {'display': 'block', 'marginBottom': '30px'} if has_baseline_data else {'display': 'none'}
        compare_area_style = {'display': 'block'} if has_compare_data else {'display': 'none'}

        return ({'display': 'none'}, baseline_area_style, compare_area_style,
                baseline_unmatched_data, unmatched_columns,
                compare_unmatched_data, unmatched_columns)


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
        Output('track-comparison-key-filter-area', 'style'),
        Output('current-table-state', 'children'),
        Input({'type': 'track-comparison-grade-btn', 'index': dash.ALL}, 'n_clicks'),
        Input('hide-track-comparison-detail-table', 'n_clicks'),
        prevent_initial_call=True
    )
    def update_table_visibility(grade_btn_clicks, hide_btn_clicks):
        ctx = dash.callback_context
        if not ctx.triggered:
            return {'display': 'none'}, {'display': 'none'}, json.dumps({'compare_name': None, 'grade_key': None})

        trigger_id = ctx.triggered[0]['prop_id']

        # 如果是隐藏按钮触发，隐藏所有区域
        if 'hide-track-comparison-detail-table' in trigger_id:
            return {'display': 'none'}, {'display': 'none'}, json.dumps({'compare_name': None, 'grade_key': None})

        # 如果是评级按钮触发，显示区域并设置状态
        if 'track-comparison-grade-btn' in trigger_id:
            try:
                id_part = trigger_id.split('.')[0]
                id_dict = json.loads(id_part)
                button_index = id_dict['index']
                compare_name, grade_key = button_index.rsplit('_', 1)
                updated_state = json.dumps({'compare_name': compare_name, 'grade_key': grade_key})
                return {'display': 'block', 'marginTop': '20px'}, {'display': 'block'}, updated_state
            except Exception as e:
                logger.error(f"解析评级按钮失败: {e}")
                return {'display': 'none'}, {'display': 'none'}, json.dumps({'compare_name': None, 'grade_key': None})

        return {'display': 'none'}, {'display': 'none'}, json.dumps({'compare_name': None, 'grade_key': None})

    @app.callback(
        Output('track-comparison-key-filter', 'options'),
        Output('track-comparison-key-filter', 'value'),
        Input('current-table-state', 'children'),
        State('track-comparison-store', 'data'),
        prevent_initial_call=True
    )
    def update_key_filter_options(current_state_json, store_data):
        try:
            current_state = json.loads(current_state_json) if current_state_json else {}
            compare_name = current_state.get('compare_name')
            grade_key = current_state.get('grade_key')
        except json.JSONDecodeError:
            return [], None

        if not compare_name or not grade_key or not store_data:
            return [], None

        # 从存储中获取数据
        results = store_data.get('results', {})
        comparisons = results.get('comparisons', [])

        # 找到对应的对比数据
        target_comparison = None
        for comparison in comparisons:
            if comparison['compare_name'] == compare_name:
                target_comparison = comparison
                break

        if not target_comparison:
            return [], None

        # 获取当前评级的匹配对
        matched_pairs = target_comparison.get('matched_pairs', [])
        grade_pairs = [pair for pair in matched_pairs if pair.get('grade') == grade_key]

        if not grade_pairs:
            return [], None

        # 提取当前评级的所有按键ID
        key_ids = set()
        for pair in grade_pairs:
            key_id = pair.get('key_id')
            if key_id is not None:
                key_ids.add(key_id)

        # 生成筛选器选项
        key_filter_options = [
            {'label': '请选择按键...', 'value': ''},
            {'label': '全部按键', 'value': 'all'}
        ]

        # 为每个按键ID添加选项
        for key_id in sorted(key_ids):
            key_filter_options.append({
                'label': f'按键 {key_id}',
                'value': str(key_id)
            })

        return key_filter_options, ''

    @app.callback(
        Output('track-comparison-unmatched-area', 'style'),
        Input('track-comparison-key-filter', 'value'),
        Input('current-table-state', 'children'),
        State('track-comparison-store', 'data'),
        prevent_initial_call=True
    )
    def update_unmatched_area_visibility(key_filter_value, current_state_json, store_data):
        try:
            current_state = json.loads(current_state_json) if current_state_json else {}
            compare_name = current_state.get('compare_name')
            grade_key = current_state.get('grade_key')
        except json.JSONDecodeError:
            return {'display': 'none'}

        if not compare_name or not grade_key:
            return {'display': 'none'}

        # 检查是否有有效的筛选值
        if key_filter_value:
            return {'display': 'block', 'marginTop': '30px', 'marginBottom': '30px'}

        return {'display': 'none'}

    @app.callback(
        Output('track-comparison-detail-datatable', 'data'),
        Output('track-comparison-detail-datatable', 'columns'),
        Input('current-table-state', 'children'),
        Input('track-comparison-key-filter', 'value'),
        State('track-comparison-store', 'data'),
        prevent_initial_call=True
    )
    def update_unmatched_area_visibility(current_state_json, key_filter_value, store_data):
        try:
            current_state = json.loads(current_state_json) if current_state_json else {}
            compare_name = current_state.get('compare_name')
            grade_key = current_state.get('grade_key')
        except json.JSONDecodeError:
            return [], []

        if not compare_name or not grade_key or not store_data:
            return [], []

        # 从存储中获取数据
        results = store_data.get('results', {})
        baseline_track = results.get('baseline_track', '标准音轨')
        comparisons = results.get('comparisons', [])

        # 找到对应的对比数据
        target_comparison = None
        for comparison in comparisons:
            if comparison['compare_name'] == compare_name:
                target_comparison = comparison
                break

        if not target_comparison:
            return [], []

        # 获取当前评级的匹配对
        matched_pairs = target_comparison['matched_pairs']
        grade_pairs = [pair for pair in matched_pairs if pair['grade'] == grade_key]

        # 根据按键筛选器进一步过滤
        if key_filter_value == 'all' or not key_filter_value:
            filtered_pairs = grade_pairs  # 显示当前评级的所有数据
        else:
            # 只显示选定按键的数据
            selected_key_id = int(key_filter_value)
            filtered_pairs = [pair for pair in grade_pairs if pair['key_id'] == selected_key_id]

        if not filtered_pairs:
            return [], []

        # 创建表格数据 - 标准与对比数据分行显示
        table_data = []
        for pair in filtered_pairs:
            # 计算差值：对比数据 - 标准数据
            keyon_diff = pair['compare_keyon'] - pair['baseline_keyon']
            hammer_time_diff = pair['compare_hammer_time'] - pair['baseline_hammer_time']
            duration_diff = pair['compare_duration'] - pair['baseline_duration']
            velocity_diff = pair['compare_hammer_velocity'] - pair['baseline_hammer_velocity']

            # 第一行：标准音轨的数据（差值列为空）
            table_data.append({
                'SPMID文件': baseline_track,
                '数据类型': '标准',
                '琴键编号': pair['key_id'],
                '序号': pair['sequence'],
                '时间': f"{pair['baseline_keyon']:.2f}ms",
                '锤击时间': f"{pair['baseline_hammer_time']:.2f}ms",
                '锤速': int(pair['baseline_hammer_velocity']),
                '持续时间': f"{pair['baseline_duration']:.2f}ms",
                'keyon时间差': '',
                '锤击时间差': '',
                '持续时间差': '',
                '锤速差': '',
                '评级': grade_key
            })

            # 第二行：对比音轨的数据（差值列显示差值）
            table_data.append({
                'SPMID文件': compare_name,
                '数据类型': '对比',
                '琴键编号': pair['key_id'],
                '序号': pair['sequence'],
                '时间': f"{pair['compare_keyon']:.2f}ms",
                '锤击时间': f"{pair['compare_hammer_time']:.2f}ms",
                '锤速': int(pair['compare_hammer_velocity']),
                '持续时间': f"{pair['compare_duration']:.2f}ms",
                'keyon时间差': f"{keyon_diff:+.2f}ms",
                '锤击时间差': f"{hammer_time_diff:+.2f}ms",
                '持续时间差': f"{duration_diff:+.2f}ms",
                '锤速差': f"{velocity_diff:+d}",
                '评级': grade_key
            })

        # 定义表格列
        columns = [
            {'name': 'SPMID文件', 'id': 'SPMID文件'},
            {'name': '数据类型', 'id': '数据类型'},
            {'name': '琴键编号', 'id': '琴键编号', 'type': 'numeric'},
            {'name': '序号', 'id': '序号', 'type': 'numeric'},
            {'name': '时间', 'id': '时间', 'type': 'text'},
            {'name': '锤击时间', 'id': '锤击时间', 'type': 'text'},
            {'name': '锤速', 'id': '锤速', 'type': 'numeric'},
            {'name': '持续时间', 'id': '持续时间', 'type': 'text'},
            {'name': 'keyon时间差', 'id': 'keyon时间差', 'type': 'text'},
            {'name': '锤击时间差', 'id': '锤击时间差', 'type': 'text'},
            {'name': '持续时间差', 'id': '持续时间差', 'type': 'text'},
            {'name': '锤速差', 'id': '锤速差', 'type': 'text'},
            {'name': '评级', 'id': '评级', 'type': 'text'}
        ]

        return table_data, columns

    @app.callback(
        Output('track-comparison-anomaly-area', 'style'),
        Output('track-comparison-anomaly-empty', 'style'),
        Output('track-comparison-anomaly-table', 'style'),
        Output('track-comparison-anomaly-table', 'data'),
        Output('track-comparison-anomaly-table', 'columns'),
        Input('current-table-state', 'children'),
        Input('track-comparison-key-filter', 'value'),
        State('track-comparison-store', 'data'),
        prevent_initial_call=True
    )
    def update_anomaly_table(current_state_json, key_filter_value, store_data):
        try:
            current_state = json.loads(current_state_json) if current_state_json else {}
            compare_name = current_state.get('compare_name')
            grade_key = current_state.get('grade_key')
        except json.JSONDecodeError:
            return {'display': 'none'}, {'display': 'none'}, {'display': 'none'}, [], []

        if not compare_name or not grade_key or not store_data:
            return {'display': 'none'}, {'display': 'none'}, {'display': 'none'}, [], []

        # 从存储中获取数据
        results = store_data.get('results', {})
        baseline_track = results.get('baseline_track', '标准音轨')
        comparisons = results.get('comparisons', [])

        # 找到对应的对比数据
        target_comparison = None
        for comparison in comparisons:
            if comparison['compare_name'] == compare_name:
                target_comparison = comparison
                break

        if not target_comparison:
            return {'display': 'none'}, {'display': 'none'}, {'display': 'none'}, [], []

        # 获取当前评级的匹配对
        matched_pairs = target_comparison['matched_pairs']
        grade_pairs = [pair for pair in matched_pairs if pair['grade'] == grade_key]

        # 生成异常匹配数据
        anomaly_pairs = []
        for pair in grade_pairs:
            baseline_velocity = pair.get('baseline_hammer_velocity', 0)
            compare_velocity = pair.get('compare_hammer_velocity', 0)
            if (baseline_velocity == 0 and compare_velocity != 0) or (baseline_velocity != 0 and compare_velocity == 0):
                anomaly_pairs.append(pair)

        if anomaly_pairs:
            # 有异常数据，显示表格
            anomaly_table_data, anomaly_columns = _generate_anomaly_table_data(anomaly_pairs, compare_name, baseline_track, grade_key)
            return ({'display': 'block', 'marginTop': '20px', 'marginBottom': '20px'},
                    {'display': 'none'},
                    {'display': 'block'},
                    anomaly_table_data,
                    anomaly_columns)
        else:
            # 没有异常数据，显示空消息
            return ({'display': 'block', 'marginTop': '20px', 'marginBottom': '20px'},
                    {'display': 'block'},
                    {'display': 'none'},
                    [],
                    [])

    @app.callback(
        Output('track-comparison-unmatched-baseline-table', 'data'),
        Output('track-comparison-unmatched-baseline-table', 'columns'),
        Output('track-comparison-unmatched-compare-table', 'data'),
        Output('track-comparison-unmatched-compare-table', 'columns'),
        Input('current-table-state', 'children'),
        State('track-comparison-store', 'data'),
        prevent_initial_call=True
    )
    def update_unmatched_tables(current_state_json, store_data):
        try:
            current_state = json.loads(current_state_json) if current_state_json else {}
            compare_name = current_state.get('compare_name')
        except json.JSONDecodeError:
            return [], [], [], []

        if not compare_name or not store_data:
            return [], [], [], []

        # 从存储中获取数据
        results = store_data.get('results', {})
        comparisons = results.get('comparisons', [])

        # 找到对应的对比数据
        target_comparison = None
        for comparison in comparisons:
            if comparison['compare_name'] == compare_name:
                target_comparison = comparison
                break

        if not target_comparison:
            return [], [], [], []

        # 获取未匹配数据
        unmatched_columns = _get_unmatched_table_columns()
        baseline_unmatched_data, compare_unmatched_data = _get_unmatched_data(target_comparison)

        return (baseline_unmatched_data, unmatched_columns,
                compare_unmatched_data, unmatched_columns)


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
            hammer_time_diff = c_hammer_time - b_hammer_time if b_hammer_time is not None and c_hammer_time is not None else 0

            duration_diff = (c_note.duration_ms - b_note.duration_ms) if hasattr(b_note, 'duration_ms') and hasattr(c_note, 'duration_ms') else 0

            b_velocity = b_note.get_first_hammer_velocity() if hasattr(b_note, 'get_first_hammer_velocity') else None
            c_velocity = c_note.get_first_hammer_velocity() if hasattr(c_note, 'get_first_hammer_velocity') else None
            hammer_velocity_diff = c_velocity - b_velocity if b_velocity is not None and c_velocity is not None else 0

            matched_pairs.append({
                'key_id': key_id,
                'sequence': i,
                'baseline_uuid': getattr(b_note, 'uuid', 'N/A'),
                'compare_uuid': getattr(c_note, 'uuid', 'N/A'),
                'baseline_keyon': b_note.key_on_ms,
                'compare_keyon': c_note.key_on_ms,
                'keyon_diff_ms': keyon_diff,
                'keyon_diff_abs': keyon_diff_abs,
                'grade': grade,
                # 标准音轨的额外信息
                'baseline_hammer_velocity': b_note.get_first_hammer_velocity() or 0,
                'baseline_hammer_time': b_note.get_first_hammer_time() or 0,  # 已经是ms单位
                'baseline_duration': getattr(b_note, 'duration_ms', None) or 0,
                # 对比音轨的额外信息
                'compare_hammer_velocity': c_note.get_first_hammer_velocity() or 0,
                'compare_hammer_time': c_note.get_first_hammer_time() or 0,  # 已经是ms单位
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
        'available_keys': sorted(all_key_ids),  # 可用的按键ID列表
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
                            disabled=False,  # 总是允许点击，即使count为0
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
        Input('url', 'pathname'),
        Input('algorithm-list-trigger', 'data'),
        State('session-id', 'data')
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
        Output('track-comparison-key-filter-area', 'style'),
        Output('current-table-state', 'children'),
        Input({'type': 'track-comparison-grade-btn', 'index': dash.ALL}, 'n_clicks'),
        Input('hide-track-comparison-detail-table', 'n_clicks'),
        prevent_initial_call=True
    )
    def update_table_visibility(grade_btn_clicks, hide_btn_clicks):
        return update_table_visibility_handler(grade_btn_clicks, hide_btn_clicks)

    @app.callback(
        Output('track-comparison-key-filter', 'options'),
        Output('track-comparison-key-filter', 'value'),
        Input('current-table-state', 'children'),
        State('track-comparison-store', 'data'),
        prevent_initial_call=True
    )
    def update_key_filter_options(current_state_json, store_data):
        return update_key_filter_options_handler(current_state_json, store_data)

    @app.callback(
        Output('track-comparison-unmatched-area', 'style'),
        Input('track-comparison-key-filter', 'value'),
        Input('current-table-state', 'children'),
        State('track-comparison-store', 'data'),
        prevent_initial_call=True
    )
    def update_unmatched_area_visibility(key_filter_value, current_state_json, store_data):
        return update_unmatched_area_visibility_handler(current_state_json, key_filter_value, store_data)

    @app.callback(
        Output('track-comparison-detail-datatable', 'data'),
        Output('track-comparison-detail-datatable', 'columns'),
        Input('current-table-state', 'children'),
        Input('track-comparison-key-filter', 'value'),
        State('track-comparison-store', 'data'),
        prevent_initial_call=True
    )
    def update_detail_table(current_state_json, key_filter_value, store_data):
        return update_detail_table_handler(current_state_json, key_filter_value, store_data)

    @app.callback(
        Output('track-comparison-anomaly-area', 'style'),
        Output('track-comparison-anomaly-empty', 'style'),
        Output('track-comparison-anomaly-table', 'style'),
        Output('track-comparison-anomaly-table', 'data'),
        Output('track-comparison-anomaly-table', 'columns'),
        Input('current-table-state', 'children'),
        Input('track-comparison-key-filter', 'value'),
        State('track-comparison-store', 'data'),
        prevent_initial_call=True
    )
    def update_anomaly_table(current_state_json, key_filter_value, store_data):
        return update_anomaly_table_handler(current_state_json, key_filter_value, store_data)

    @app.callback(
        Output('track-comparison-unmatched-empty', 'style'),
        Output('track-comparison-unmatched-baseline-area', 'style'),
        Output('track-comparison-unmatched-compare-area', 'style'),
        Output('track-comparison-unmatched-baseline-table', 'data'),
        Output('track-comparison-unmatched-baseline-table', 'columns'),
        Output('track-comparison-unmatched-compare-table', 'data'),
        Output('track-comparison-unmatched-compare-table', 'columns'),
        Input('current-table-state', 'children'),
        State('track-comparison-store', 'data'),
        prevent_initial_call=True
    )
    def update_unmatched_tables(current_state_json, store_data):
        return update_unmatched_tables_handler(current_state_json, store_data)

    @app.callback(
        Output({'type': 'baseline-radio', 'index': dash.ALL}, 'value'),
        Input({'type': 'baseline-radio', 'index': dash.ALL}, 'value'),
        State({'type': 'baseline-radio', 'index': dash.ALL}, 'id'),
        prevent_initial_call=True
    )
    def enforce_baseline_radio_mutual_exclusion(current_values, current_ids):
        """
        确保标准音轨RadioItems的互斥性 - 只能选择其中一个

        Args:
            current_values: 当前所有RadioItems的值列表
            current_ids: 当前所有RadioItems的ID列表

        Returns:
            更新后的值列表，确保只有一个被选中
        """
        # 找出哪些RadioItems有值（被选中）
        selected_indices = []
        selected_values = []

        for idx, (value, id_dict) in enumerate(zip(current_values, current_ids)):
            if value is not None:
                selected_indices.append(idx)
                selected_values.append(value)

        # 如果没有选中任何项，返回当前状态
        if not selected_indices:
            return current_values

        # 如果只选中了一个，保持现状
        if len(selected_indices) == 1:
            return current_values

        # 如果选中了多个，保留最后一个选中的，取消其他选择
        # Dash的回调上下文可以帮助我们确定哪个触发了变化
        ctx = dash.callback_context
        if ctx.triggered:
            # 找出触发变化的输入
            triggered_prop = ctx.triggered[0]['prop_id']
            if 'baseline-radio' in triggered_prop:
                # 解析触发者的ID
                try:
                    # 从prop_id中提取index
                    # 格式类似：'{"index":"alg1","type":"baseline-radio"}.value'
                    import json
                    id_str = triggered_prop.split('.')[0]
                    id_dict = json.loads(id_str)
                    triggered_index = id_dict['index']

                    # 只保留触发者的选择，取消其他所有选择
                    result_values = [None] * len(current_values)
                    for idx, id_dict in enumerate(current_ids):
                        if id_dict['index'] == triggered_index:
                            result_values[idx] = triggered_index
                            break

                    return result_values
                except (json.JSONDecodeError, KeyError):
                    pass

        # 备用逻辑：保留第一个选中的，取消其他
        result_values = [None] * len(current_values)
        if selected_indices:
            result_values[selected_indices[0]] = selected_values[0]

        return result_values