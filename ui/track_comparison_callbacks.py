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
        raise PreventUpdate


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
        logger.debug(f"获取到 {len(active_algorithms)} 个激活的算法")

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


def reset_comparison_results_handler(pathname, trigger, session_id, session_manager):
    """
    当文件被删除时，重置对比结果区域到初始状态
    
    Args:
        pathname: 当前页面路径
        trigger: 全局文件列表更新触发器
        session_id: 会话ID
        session_manager: SessionManager实例
    
    Returns:
        (对比结果区域内容, 对比结果区域样式, store数据)
    """
    # 只在音轨对比页面才更新
    if pathname != '/track-comparison':
        raise PreventUpdate
    
    try:
        # 检查是否有文件
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
        
        # 如果没有backend或文件少于2个，重置对比结果
        if not backend or len(backend.get_active_algorithms()) < 2:
            logger.info("检测到文件被删除或文件数量不足，重置对比结果区域")
            return (
                html.Div(),  # 空内容
                {'display': 'none'},  # 隐藏结果区域
                {'selected_tracks': [], 'baseline_id': None}  # 重置store数据
            )
        
        # 有足够的文件，不更新（保持现有结果）
        raise PreventUpdate
        
    except PreventUpdate:
        raise
    except Exception as e:
        logger.error(f"重置对比结果失败: {e}")
        traceback.print_exc()
        # 发生错误时也重置，确保界面不会卡在错误状态
        return (
            html.Div(),
            {'display': 'none'},
            {'selected_tracks': [], 'baseline_id': None}
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
                id={'type': 'start-comparison-btn', 'index': 'main'},
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
        
        logger.debug("[DEBUG]🎯 开始执行音轨对比分析")
        
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
            
            logger.debug(f"[DEBUG] 选中的音轨: {selected_tracks}")
            logger.debug(f"[DEBUG] 标准音轨: {baseline_track}")
            
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
            # 开始计时对比总流程
            total_start_time = time.time()
            
            # 1. 执行算法对比
            compare_start_time = time.time()
            comparison_results = perform_track_comparison(
                backend, selected_tracks, baseline_track
            )
            compare_end_time = time.time()
            logger.info(f"⏱️ [性能统计] 1. 算法对比匹配耗时: {(compare_end_time - compare_start_time)*1000:.2f}ms")

            # 2. 生成结果UI摘要
            ui_start_time = time.time()
            results_ui = create_comparison_results_ui(comparison_results)
            ui_end_time = time.time()
            logger.info(f"⏱️ [性能统计] 2. 结果汇总UI生成耗时: {(ui_end_time - ui_start_time)*1000:.2f}ms")

            # 3. 准备可序列化的存储数据（移除 Note 对象）
            serialize_start_time = time.time()
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
                        'first_hammer_velocity': note.get_first_hammer_velocity(),
                        'group_sequence': getattr(note, 'group_sequence', None)
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
                        'first_hammer_velocity': note.get_first_hammer_velocity(),
                        'group_sequence': getattr(note, 'group_sequence', None)
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
            serialize_end_time = time.time()
            logger.info(f"⏱️ [性能统计] 3. 数据序列化耗时: {(serialize_end_time - serialize_start_time)*1000:.2f}ms")
            
            # ========== 优化1: 预计算所有表格数据 ==========
            precompute_start_time = time.time()
            logger.info("🚀 [优化1] 开始预计算表格数据...")
            precomputed_tables = _precompute_all_table_data(serializable_results)
            precompute_end_time = time.time()
            logger.info(f"✅ [优化1] 预计算完成，共处理 {len(precomputed_tables)} 个对比")
            logger.info(f"⏱️ [性能统计] 4. 表格数据预计算耗时: {(precompute_end_time - precompute_start_time)*1000:.2f}ms")
            
            # ========== 优化3: 创建字典索引 ==========
            index_start_time = time.time()
            logger.info("🚀 [优化3] 创建数据索引缓存...")
            comparisons_dict = {
                comp['compare_name']: comp 
                for comp in serializable_results['comparisons']
            }
            index_end_time = time.time()
            logger.info(f"✅ [优化3] 索引创建完成，共 {len(comparisons_dict)} 个对比")
            logger.info(f"⏱️ [性能统计] 5. 字典索引创建耗时: {(index_end_time - index_start_time)*1000:.2f}ms")
            
            store_data = {
                'results': serializable_results,
                'comparisons_dict': comparisons_dict,  # 新增：字典索引，O(1)查找
                'precomputed_tables': precomputed_tables, # 预计算数据
                'timestamp': time.time()
            }

            total_end_time = time.time()
            logger.info(f"⏱️ [性能统计] 总流程处理耗时: {(total_end_time - total_start_time)*1000:.2f}ms")

            return (results_ui, {'display': 'block'}, store_data)

        except Exception as e:
            logger.error(f"音轨对比失败: {e}")
            traceback.print_exc()
            return (
                dbc.Alert(f"对比失败: {str(e)}", color="danger"),
                {'display': 'block'},
                no_update
            )




def _precompute_all_table_data(serializable_results):
    """
    预计算所有表格数据，避免在回调中实时计算
    
    Args:
        serializable_results: 序列化后的对比结果
    
    Returns:
        dict: 预计算的表格数据，结构为 {compare_name: {grade_key: table_data}}
    """
    precomputed = {}
    baseline_track = serializable_results.get('baseline_track', '标准音轨')
    
    for comp in serializable_results.get('comparisons', []):
        compare_name = comp['compare_name']
        matched_pairs = comp.get('matched_pairs', [])
        
        # 为每个评级预计算表格数据
        grade_tables = {}
        for grade_key in ['EXCELLENT', 'GOOD', 'FAIR', 'POOR', 'SEVERE', 'FAILED']:
            # 过滤当前评级的匹配对
            grade_pairs = [pair for pair in matched_pairs if pair.get('grade') == grade_key]
            
            if not grade_pairs:
                grade_tables[grade_key] = []
                continue
            
            # 生成表格数据
            table_data = []
            for pair in grade_pairs:
                # 计算差值
                keyon_diff = pair['compare_keyon'] - pair['baseline_keyon']
                hammer_time_diff = pair['compare_hammer_time'] - pair['baseline_hammer_time']
                duration_diff = pair['compare_duration'] - pair['baseline_duration']
                baseline_velocity = pair.get('baseline_hammer_velocity') or 0
                compare_velocity = pair.get('compare_hammer_velocity') or 0
                velocity_diff = compare_velocity - baseline_velocity
                
                # 计算锤速还原百分比
                velocity_percentage = 0.0
                if baseline_velocity and baseline_velocity != 0:
                    velocity_percentage = (compare_velocity / baseline_velocity) * 100
                
                # 第一行：标准音轨数据
                table_data.append({
                    'SPMID文件': baseline_track,
                    '数据类型': '标准',
                    '琴键编号': pair['key_id'],
                    '序号': pair['sequence'] + 1,  # 转为 1-indexed 位置
                    'uuid': pair['baseline_uuid'],  # 用于反查数据的唯一标识
                    '时间': f"{pair['baseline_keyon']:.2f}ms",
                    '锤击时间': f"{pair['baseline_hammer_time']:.2f}ms",
                    '锤速': int(pair.get('baseline_hammer_velocity') or 0),
                    '持续时间': f"{pair['baseline_duration']:.2f}ms",
                    'keyon时间差': '',
                    '锤击时间差': '',
                    '持续时间差': '',
                    '锤速差': '',
                    '锤速还原百分比': '',
                    '评级': grade_key
                })
                
                # 第二行：对比音轨数据
                table_data.append({
                    'SPMID文件': compare_name,
                    '数据类型': '对比',
                    '琴键编号': pair['key_id'],
                    '序号': pair['sequence'] + 1,  # 转为 1-indexed 位置
                    'uuid': pair['compare_uuid'],  # 用于反查数据的唯一标识
                    '时间': f"{pair['compare_keyon']:.2f}ms",
                    '锤击时间': f"{pair['compare_hammer_time']:.2f}ms",
                    '锤速': int(pair.get('compare_hammer_velocity') or 0),
                    '持续时间': f"{pair['compare_duration']:.2f}ms",
                    'keyon时间差': f"{keyon_diff:+.2f}ms",
                    '锤击时间差': f"{hammer_time_diff:+.2f}ms",
                    '持续时间差': f"{duration_diff:+.2f}ms",
                    '锤速差': f"{velocity_diff:+d}",
                    '锤速还原百分比': f"{velocity_percentage:.1f}%" if velocity_percentage else 'N/A',
                    '评级': grade_key
                })
            
            grade_tables[grade_key] = table_data
        
        precomputed[compare_name] = grade_tables
    
    return precomputed


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
        # 优先按组内序号排序
        key_notes.sort(key=lambda n: n.get('group_sequence') if n.get('group_sequence') is not None else (n.get('key_on_ms', 0) or 0))

        # 为每个音符分配显示序号
        for seq_idx, note in enumerate(key_notes):
            # 始终使用记录的原始组内序号（1-indexed）
            display_seq = note.get('group_sequence')
            if display_seq is not None:
                display_seq = display_seq + 1
            else:
                display_seq = seq_idx + 1

            result.append({
                'uuid': note.get('uuid', 'N/A'),
                'key_id': note['id'],
                '序号': display_seq,
                'key_on_ms': f"{note.get('key_on_ms', 'N/A'):.2f}ms" if note.get('key_on_ms') is not None else 'N/A',
                'key_off_ms': f"{note.get('key_off_ms', 'N/A'):.2f}ms" if note.get('key_off_ms') is not None else 'N/A',
                'duration_ms': f"{note.get('duration_ms', 'N/A'):.2f}ms" if note.get('duration_ms') is not None else 'N/A',
                'hammer_time': f"{note.get('first_hammer_time', 'N/A'):.2f}ms" if note.get('first_hammer_time') is not None else 'N/A',
                'hammer_velocity': f"{note.get('first_hammer_velocity', 'N/A')}" if note.get('first_hammer_velocity') is not None else 'N/A'
            })

    return result


def _get_unmatched_data(target_comparison, key_filter_value=None):
    """
    获取未匹配数据的完整表格数据
    
    Args:
        target_comparison: 对比结果
        key_filter_value: 按键筛选器值
    """
    # 转换为整数，如果有效
    selected_key_id = None
    if key_filter_value and key_filter_value != 'all' and key_filter_value != '':
        try:
            selected_key_id = int(key_filter_value)
        except: pass

    # 获取未匹配列表
    u_baseline_raw = target_comparison.get('unmatched_baseline', [])
    u_compare_raw = target_comparison.get('unmatched_compare', [])

    # 过滤按键
    if selected_key_id is not None:
        def get_note_key(n):
            if isinstance(n, dict):
                return n.get('id') or n.get('key_id')
            return getattr(n, 'id', None) or getattr(n, 'key_id', None)
        
        u_baseline = [n for n in u_baseline_raw if get_note_key(n) == selected_key_id]
        u_compare = [n for n in u_compare_raw if get_note_key(n) == selected_key_id]
    else:
        u_baseline = u_baseline_raw
        u_compare = u_compare_raw

    baseline_unmatched_data = _process_unmatched_notes(u_baseline)
    compare_unmatched_data = _process_unmatched_notes(u_compare)

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
            '序号': pair.get('sequence', 0) + 1,
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
            '序号': pair.get('sequence', 0) + 1,
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

    # ========== 优化3: 使用字典索引查找 ==========
    comparisons_dict = store_data.get('comparisons_dict', {})
    
    if comparisons_dict and compare_name in comparisons_dict:
        # 使用O(1)字典查找
        target_comparison = comparisons_dict[compare_name]
    else:
        # 降级：使用列表遍历
        results = store_data.get('results', {})
        comparisons = results.get('comparisons', [])
        
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
    处理详细对比表格更新的回调逻辑（优化版：使用预计算数据）

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

    # ========== 优化1: 使用预计算的表格数据 ==========
    precomputed_tables = store_data.get('precomputed_tables', {})
    
    # 如果有预计算数据,直接使用
    if precomputed_tables and compare_name in precomputed_tables:
        all_table_data = precomputed_tables[compare_name].get(grade_key, [])
        
        # 根据按键筛选器过滤数据
        if key_filter_value and key_filter_value != 'all' and key_filter_value != '':
            selected_key_id = int(key_filter_value)
            table_data = [row for row in all_table_data if row.get('琴键编号') == selected_key_id]
        else:
            table_data = all_table_data
    else:
        # 降级方案：如果没有预计算数据,使用原来的实时计算方式
        logger.warning("⚠️ [优化1] 未找到预计算数据,使用降级方案")
        
        # ========== 优化3: 使用字典索引查找 ==========
        comparisons_dict = store_data.get('comparisons_dict', {})
        
        if comparisons_dict and compare_name in comparisons_dict:
            # 使用O(1)字典查找
            target_comparison = comparisons_dict[compare_name]
        else:
            # 最终降级：使用列表遍历
            logger.warning("⚠️ [优化3] 未找到字典索引,使用列表遍历")
            results = store_data.get('results', {})
            comparisons = results.get('comparisons', [])
            
            target_comparison = None
            for comparison in comparisons:
                if comparison['compare_name'] == compare_name:
                    target_comparison = comparison
                    break

        if not target_comparison:
            return [], []

        # 获取baseline_track
        results = store_data.get('results', {})
        baseline_track = results.get('baseline_track', '标准音轨')

        # 获取当前评级的匹配对
        matched_pairs = target_comparison['matched_pairs']
        grade_pairs = [pair for pair in matched_pairs if pair['grade'] == grade_key]

        # 根据按键筛选器进一步过滤
        if key_filter_value == 'all' or not key_filter_value:
            filtered_pairs = grade_pairs
        else:
            selected_key_id = int(key_filter_value)
            filtered_pairs = [pair for pair in grade_pairs if pair['key_id'] == selected_key_id]

        if not filtered_pairs:
            return [], []

        # 实时计算表格数据
        table_data = []
        for pair in filtered_pairs:
            keyon_diff = pair['compare_keyon'] - pair['baseline_keyon']
            hammer_time_diff = pair['compare_hammer_time'] - pair['baseline_hammer_time']
            duration_diff = pair['compare_duration'] - pair['baseline_duration']
            baseline_velocity = pair.get('baseline_hammer_velocity') or 0
            compare_velocity = pair.get('compare_hammer_velocity') or 0
            velocity_diff = compare_velocity - baseline_velocity

            velocity_percentage = 0.0
            if baseline_velocity and baseline_velocity != 0:
                velocity_percentage = (compare_velocity / baseline_velocity) * 100

            table_data.append({
                'SPMID文件': baseline_track,
                '数据类型': '标准',
                '琴键编号': pair['key_id'],
                '序号': pair['sequence'] + 1,
                'uuid': pair['baseline_uuid'],  # 用于反查数据的唯一标识
                '时间': f"{pair['baseline_keyon']:.2f}ms",
                '锤击时间': f"{pair['baseline_hammer_time']:.2f}ms",
                '锤速': int(pair.get('baseline_hammer_velocity') or 0),
                '持续时间': f"{pair['baseline_duration']:.2f}ms",
                'keyon时间差': '',
                '锤击时间差': '',
                '持续时间差': '',
                '锤速差': '',
                '锤速还原百分比': '',
                '评级': grade_key
            })

            table_data.append({
                'SPMID文件': compare_name,
                '数据类型': '对比',
                '琴键编号': pair['key_id'],
                '序号': pair['sequence'] + 1,
                'uuid': pair['compare_uuid'],  # 用于反查数据的唯一标识
                '时间': f"{pair['compare_keyon']:.2f}ms",
                '锤击时间': f"{pair['compare_hammer_time']:.2f}ms",
                '锤速': int(pair.get('compare_hammer_velocity') or 0),
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
        # 按键筛选过滤
        if key_filter_value and key_filter_value != 'all' and key_filter_value != '':
            if pair.get('key_id') != int(key_filter_value):
                continue

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


def update_unmatched_tables_handler(current_state_json, key_filter_value, store_data):
    """
    处理未匹配数据表格更新的回调逻辑
    
    Args:
        current_state_json: 当前表格状态JSON
        key_filter_value: 按键筛选器值
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
    baseline_unmatched_data, compare_unmatched_data = _get_unmatched_data(target_comparison, key_filter_value)

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
        Input({'type': 'start-comparison-btn', 'index': dash.ALL}, 'n_clicks'),
        Input('url', 'pathname'),  # 监听页面变化
        Input('algorithm-list-trigger', 'data'),  # 监听全局文件列表变化
        State({'type': 'track-select-checkbox', 'index': dash.ALL}, 'value'),
        State({'type': 'track-select-checkbox', 'index': dash.ALL}, 'id'),
        State({'type': 'baseline-radio', 'index': dash.ALL}, 'value'),
        State('session-id', 'data'),
        prevent_initial_call=True
    )
    def perform_comparison(n_clicks, pathname, trigger, checkbox_values, checkbox_ids, baseline_values, session_id):
        ctx = dash.callback_context
        if not ctx.triggered:
            raise PreventUpdate
        
        trigger_id = ctx.triggered[0]['prop_id']
        
        # 如果触发源是文件列表变化或页面变化，检查是否需要重置
        if 'algorithm-list-trigger' in trigger_id or 'url' in trigger_id:
            return reset_comparison_results_handler(pathname, trigger, session_id, session_manager)
        
        # 如果是点击开始对比按钮，执行对比
        if 'start-comparison-btn' in trigger_id:
            # 对于 pattern-matching ID，n_clicks 是一个列表
            # 找到 index 为 'main' 的那个按钮的点击次数
            actual_n_clicks = 0
            if isinstance(n_clicks, list) and len(n_clicks) > 0:
                actual_n_clicks = n_clicks[0]
            
            return perform_comparison_handler(actual_n_clicks, checkbox_values, checkbox_ids, baseline_values, session_id, session_manager)
        
        raise PreventUpdate

    # ========== 优化2: 合并回调函数 ==========
    # 将原来的5个级联回调合并为1个,减少回调次数和重复处理
    @app.callback(
        # 所有输出 (19个)
        Output('track-comparison-detail-table-area', 'style'),
        Output('track-comparison-key-filter-area', 'style'),
        Output('current-table-state', 'children'),
        Output('track-comparison-key-filter', 'options'),
        Output('track-comparison-key-filter', 'value'),
        Output('track-comparison-detail-datatable', 'data'),
        Output('track-comparison-detail-datatable', 'columns'),
        Output('track-comparison-anomaly-area', 'style'),
        Output('track-comparison-anomaly-empty', 'style'),
        Output('track-comparison-anomaly-table', 'style'),
        Output('track-comparison-anomaly-table', 'data'),
        Output('track-comparison-anomaly-table', 'columns'),
        Output('track-comparison-unmatched-area', 'style'),
        Output('track-comparison-unmatched-empty', 'style'),
        Output('track-comparison-unmatched-baseline-area', 'style'),
        Output('track-comparison-unmatched-compare-area', 'style'),
        Output('track-comparison-unmatched-baseline-table', 'data'),
        Output('track-comparison-unmatched-baseline-table', 'columns'),
        Output('track-comparison-unmatched-compare-table', 'data'),
        Output('track-comparison-unmatched-compare-table', 'columns'),
        # 输入
        Input({'type': 'track-comparison-grade-btn', 'index': dash.ALL}, 'n_clicks'),
        Input('hide-track-comparison-detail-table', 'n_clicks'),
        Input('track-comparison-key-filter', 'value'),
        State('track-comparison-store', 'data'),
        State('current-table-state', 'children'),
        prevent_initial_call=True
    )
    def update_all_on_grade_selection(grade_btn_clicks, hide_btn_clicks, key_filter_value, store_data, current_state_json):
        """
        合并后的回调函数 - 一次性处理所有更新
        
        原来的5个回调:
        1. update_table_visibility
        2. update_key_filter_options  
        3. update_detail_table
        4. update_anomaly_table
        5. update_unmatched_tables
        """
        ctx = dash.callback_context
        
        # 默认返回值 (隐藏所有)
        default_hidden = (
            {'display': 'none'}, {'display': 'none'},  # 表格区域, 筛选器区域
            json.dumps({'compare_name': None, 'grade_key': None}),  # 状态
            [], None,  # 筛选器选项和值
            [], [],  # 详细表格数据和列
            {'display': 'none'}, {'display': 'none'}, {'display': 'none'},  # 异常区域样式
            [], [],  # 异常表格数据和列
            {'display': 'none'},  # 未匹配区域
            {'display': 'block'}, {'display': 'none'}, {'display': 'none'},  # 未匹配子区域
            [], [], [], []  # 未匹配表格数据和列
        )
        
        if not ctx.triggered:
            return default_hidden
        
        trigger_id = ctx.triggered[0]['prop_id']
        
        # ========== 阶段1: 处理隐藏按钮 ==========
        if 'hide-track-comparison-detail-table' in trigger_id:
            return default_hidden
        
        # ========== 阶段2: 处理评级按钮点击 ==========
        if 'track-comparison-grade-btn' in trigger_id:
            try:
                id_part = trigger_id.split('.')[0]
                id_dict = json.loads(id_part)
                button_index = id_dict['index']
                compare_name, grade_key = button_index.rsplit('_', 1)
                updated_state = json.dumps({'compare_name': compare_name, 'grade_key': grade_key})
            except Exception as e:
                logger.error(f"解析评级按钮失败: {e}")
                return default_hidden
        
        # ========== 阶段3: 处理筛选器变化 ==========
        elif 'track-comparison-key-filter' in trigger_id:
            # 从当前状态获取compare_name和grade_key
            try:
                if not current_state_json:
                    return default_hidden
                current_state = json.loads(current_state_json)
                compare_name = current_state.get('compare_name')
                grade_key = current_state.get('grade_key')
                if not compare_name or not grade_key:
                    return default_hidden
                updated_state = current_state_json
            except:
                return default_hidden
        else:
            return default_hidden
        
        # ========== 阶段4: 获取数据 ==========
        if not store_data:
            logger.warning("⚠️ [DEBUG] store_data 为空")
            return default_hidden
        
        # 使用优化3的字典索引
        comparisons_dict = store_data.get('comparisons_dict', {})
        if not comparisons_dict or compare_name not in comparisons_dict:
            return default_hidden
        
        target_comparison = comparisons_dict[compare_name]
        results = store_data.get('results', {})
        baseline_track = results.get('baseline_track', '标准音轨')
        
        # ========== 阶段5: 生成筛选器选项 ==========
        matched_pairs = target_comparison.get('matched_pairs', [])
        grade_pairs = [pair for pair in matched_pairs if pair.get('grade') == grade_key]
        
        if not grade_pairs:
            # 有状态但没有数据,显示空表格
            return (
                {'display': 'block', 'marginTop': '20px'}, {'display': 'block'},
                updated_state,
                [{'label': '请选择按键...', 'value': ''}], '',
                [], [], 
                {'display': 'none'}, {'display': 'none'}, {'display': 'none'},
                [], [],
                {'display': 'none'},
                {'display': 'block'}, {'display': 'none'}, {'display': 'none'},
                [], [], [], []
            )
        
        # 提取按键ID
        key_ids = set(pair.get('key_id') for pair in grade_pairs if pair.get('key_id') is not None)
        key_filter_options = [
            {'label': '请选择按键...', 'value': ''},
            {'label': '全部按键', 'value': 'all'}
        ]
        for key_id in sorted(key_ids):
            key_filter_options.append({'label': f'按键 {key_id}', 'value': str(key_id)})
        
        # 如果是新点击评级按钮,重置筛选器
        if 'track-comparison-grade-btn' in trigger_id:
            key_filter_value = ''
        
        # ========== 阶段6: 生成详细表格数据 ==========
        detail_data, detail_columns = update_detail_table_handler(
            updated_state, key_filter_value, store_data
        )
        
        # ========== 阶段7: 生成异常表格数据 ==========
        anomaly_area_style, anomaly_empty_style, anomaly_table_style, anomaly_data, anomaly_columns = \
            update_anomaly_table_handler(updated_state, key_filter_value, store_data)
        
        # ========== 阶段8: 生成未匹配表格数据 ==========
        # 只在选择了按键时显示未匹配区域
        if key_filter_value and key_filter_value != '':
            unmatched_area_style = {'display': 'block', 'marginTop': '30px', 'marginBottom': '30px'}
            unmatched_empty_style, baseline_area_style, compare_area_style, \
            baseline_data, baseline_columns, compare_data, compare_columns = \
                update_unmatched_tables_handler(updated_state, key_filter_value, store_data)
        else:
            unmatched_area_style = {'display': 'none'}
            unmatched_empty_style = {'display': 'block'}
            baseline_area_style = {'display': 'none'}
            compare_area_style = {'display': 'none'}
            baseline_data, baseline_columns = [], []
            compare_data, compare_columns = [], []
        
        # ========== 返回所有结果 ==========
        return (
            {'display': 'block', 'marginTop': '20px'},  # 表格区域
            {'display': 'block'},  # 筛选器区域
            updated_state,  # 状态
            key_filter_options, key_filter_value,  # 筛选器
            detail_data, detail_columns,  # 详细表格
            anomaly_area_style, anomaly_empty_style, anomaly_table_style,  # 异常样式
            anomaly_data, anomaly_columns,  # 异常表格
            unmatched_area_style,  # 未匹配区域
            unmatched_empty_style, baseline_area_style, compare_area_style,  # 未匹配子区域
            baseline_data, baseline_columns, compare_data, compare_columns  # 未匹配表格
        )

    # --- 阶段2: 辅助功能 ---
    @app.callback(
        Output({'type': 'baseline-radio', 'index': dash.ALL}, 'value'),
        Input({'type': 'baseline-radio', 'index': dash.ALL}, 'value'),
        State({'type': 'baseline-radio', 'index': dash.ALL}, 'id'),
        prevent_initial_call=True
    )
    def enforce_baseline_radio_mutual_exclusion(current_values, current_ids):
        """确保标准音轨 RadioItems 的互斥性"""
        selected_indices = [idx for idx, val in enumerate(current_values) if val is not None]
        if not selected_indices or len(selected_indices) == 1:
            return current_values
        
        ctx = dash.callback_context
        if ctx.triggered:
            triggered_prop = ctx.triggered[0]['prop_id']
            if 'baseline-radio' in triggered_prop:
                try:
                    id_str = triggered_prop.split('.')[0]
                    id_dict = json.loads(id_str)
                    triggered_index = id_dict['index']
                    result_values = [None] * len(current_values)
                    for idx, id_dict in enumerate(current_ids):
                        if id_dict['index'] == triggered_index:
                            result_values[idx] = triggered_index
                            break
                    return result_values
                except: pass
        return current_values

    # --- 阶段3: 图表查看 (优化 5: 延迟加载) ---
    @app.callback(
        Output('key-curve-modal', 'is_open'),
        Output('key-curve-chart-container', 'children'),
        Input('track-comparison-detail-datatable', 'active_cell'),
        Input('close-curve-modal', 'n_clicks'),
        State('track-comparison-detail-datatable', 'data'),
        State('track-comparison-detail-datatable', 'page_current'),
        State('track-comparison-detail-datatable', 'page_size'),
        State('current-table-state', 'children'),
        State('track-comparison-store', 'data'),
        State('session-id', 'data'),
        prevent_initial_call=True
    )
    def handle_table_click_and_show_curve(active_cell, close_clicks, table_data, page_current, page_size, current_state_json, store_data, session_id):
        """处理表格点击，实时从后端加载曲线数据（按分页计算全局行号）"""
        ctx = dash.callback_context
        if not ctx.triggered:
            return False, no_update
        
        trigger_id = ctx.triggered[0]['prop_id']
        if 'close-curve-modal' in trigger_id:
            return False, no_update
        
        # 检查必要的数据是否存在
        if not active_cell or not table_data or not current_state_json:
            logger.warning("缺少必要的数据：active_cell、table_data 或 current_state_json 为空")
            return False, "无法定位音符数据：缺少必要的数据"
        
        # 按分页计算全局行索引：active_cell['row'] 是当前页内行号 (0..page_size-1)
        try:
            page_row = active_cell.get('row')
            if page_row is None:
                return False, "无法定位音符数据：未获取到行号"
            page_current = page_current if page_current is not None else 0
            page_size = page_size if page_size is not None else 20
            global_row_index = page_current * page_size + page_row
            if global_row_index < 0 or global_row_index >= len(table_data):
                logger.warning(f"行索引越界：global_row_index={global_row_index}, len(table_data)={len(table_data)}, page_current={page_current}, page_size={page_size}, page_row={page_row}")
                return False, "无法定位音符数据：行索引越界"
            row_data = table_data[global_row_index]
            key_id = row_data.get('琴键编号')
            seq_num = row_data.get('序号')  # 表格中的序号（第几对）
            data_type = row_data.get('数据类型')  # '标准' 或 '对比'
            current_uuid = row_data.get('uuid')  # 当前行的UUID
            compare_name = json.loads(current_state_json).get('compare_name')
        except Exception as e:
            logger.error(f"无法定位音符数据: {e}")
            traceback.print_exc()
            return False, "无法定位音符数据"

        if not current_uuid or current_uuid == 'N/A':
            return False, "表格数据中缺少UUID，无法定位音符对象"

        # 找到匹配对 (使用UUID定位，这是最准确的方式)
        matched_pairs = store_data.get('comparisons_dict', {}).get(compare_name, {}).get('matched_pairs', [])
        target_pair = None
        
        # 根据当前行的数据类型，查找匹配对
        if data_type == '标准':
            target_pair = next((p for p in matched_pairs if p.get('baseline_uuid') == current_uuid), None)
        elif data_type == '对比':
            target_pair = next((p for p in matched_pairs if p.get('compare_uuid') == current_uuid), None)
        
        if not target_pair:
            return False, f"未找到UUID {current_uuid} 的匹配信息"

        # 从匹配对中获取两个UUID
        baseline_uuid = target_pair.get('baseline_uuid')
        compare_uuid = target_pair.get('compare_uuid')

        if not baseline_uuid or not compare_uuid:
            return False, "匹配对中缺少UUID信息"

        # 从后端获取曲线数据
        try:
            backend = session_manager.get_backend(session_id)
            if not backend: return False, "Backend 无法访问"
            
            algs = {a.metadata.algorithm_name: a for a in backend.get_active_algorithms()}
            baseline_name = store_data.get('results', {}).get('baseline_track')
            
            b_alg = algs.get(baseline_name)
            c_alg = algs.get(compare_name)
            
            # 辅助函数：根据 UUID 定位 Note 对象
            def find_note_by_uuid(alg, target_uuid):
                """通过UUID查找Note对象"""
                if not alg or not alg.analyzer:
                    return None
                # 获取该算法所有音符
                all_notes = alg.analyzer.initial_valid_replay_data
                # 通过UUID查找
                for note in all_notes:
                    if hasattr(note, 'uuid') and str(note.uuid) == str(target_uuid):
                        return note
                return None

            # 使用UUID查找Note对象，确保数据一致性
            b_note = find_note_by_uuid(b_alg, baseline_uuid)
            c_note = find_note_by_uuid(c_alg, compare_uuid)

            if not b_note or not c_note:
                return True, dbc.Alert("在后端数据中找不到对应的音符对象，可能原始数据已更新。", color="warning")

            # 序列化曲线 (仅对本次点击的一对音符进行)
            import plotly.graph_objects as go
            fig = go.Figure()

            # 绘制曲线逻辑
            for note, label, color in [(b_note, "标准", "blue"), (c_note, "对比", "red")]:
                if hasattr(note, 'after_touch') and note.after_touch is not None and not note.after_touch.empty:
                    times = [(idx + note.offset) / 10.0 for idx in note.after_touch.index]
                    fig.add_trace(go.Scattergl(x=times, y=note.after_touch.values.tolist(), mode='lines', name=f"{label} (after_touch)", line=dict(color=color)))
                
                if hasattr(note, 'hammers') and note.hammers is not None and not note.hammers.empty:
                    # 修复 Bug: 避免直接比较 Series (The truth value of a Series is ambiguous)
                    # 先获取Series
                    s_hammers = note.hammers
                    # 找出大于0的值
                    mask = s_hammers > 0
                    if mask.any():
                        valid_hammers = s_hammers[mask]
                        # 确保索引是唯一的，避免 duplicate index 导致问题
                        if not valid_hammers.index.is_unique:
                             valid_hammers = valid_hammers.groupby(level=0).first() # 取重复时间的第一个值

                        h_times = [(idx + note.offset) / 10.0 for idx in valid_hammers.index]
                        h_vels = valid_hammers.values.tolist()
                        
                        fig.add_trace(go.Scattergl(x=h_times, y=h_vels, mode='markers', name=f"{label} 锤击点", marker=dict(color=color, size=10, symbol='diamond')))

            # 标题同时显示琴键编号与序号
            title = f"琴键 {key_id} 曲线对比 (延迟加载)"
            if seq_num is not None:
                title = f"琴键 {key_id} - 序号 {seq_num} 曲线对比 (延迟加载)"
            fig.update_layout(height=450, title=title, xaxis_title="时间 (ms)", yaxis_title="触后值 / 锤速", margin=dict(l=40, r=40, t=40, b=40))
            
            return True, html.Div([dcc.Graph(figure=fig), html.Small("数据已从后端实时提取", className="text-muted")])

        except Exception as e:
            logger.error(f"延迟加载曲线失败: {e}")
            return True, html.Div(f"图表加载生成失败: {str(e)}", className="alert alert-danger")


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
    
    # 开始计时匹配逻辑
    match_start_time = time.time()
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

    # 统计曲线序列化时间
    curve_serialize_total_time = 0

    for key_id in sorted(all_key_ids):
        baseline_group = baseline_by_key.get(key_id, [])
        compare_group = compare_by_key.get(key_id, [])
        
        # 为两个音轨的所有音符预先分配组内序号（代表在同组按键中的位置）
        for i, note in enumerate(baseline_group):
            note.group_sequence = i
        for i, note in enumerate(compare_group):
            note.group_sequence = i
        
        # 严格按序号匹配
        min_len = min(len(baseline_group), len(compare_group))
        
        for i in range(min_len):
            b_note = baseline_group[i]
            c_note = compare_group[i]
            
            # 计算 Key-On 时间差
            keyon_diff = c_note.key_on_ms - b_note.key_on_ms
            keyon_diff_abs = abs(keyon_diff)
            grade = classify_keyon_error(keyon_diff_abs)
            grade_counts[grade] += 1
            
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
                'baseline_hammer_velocity': b_note.get_first_hammer_velocity() or 0,
                'baseline_hammer_time': b_note.get_first_hammer_time() or 0,
                'baseline_duration': getattr(b_note, 'duration_ms', None) or 0,
                'compare_hammer_velocity': c_note.get_first_hammer_velocity() or 0,
                'compare_hammer_time': c_note.get_first_hammer_time() or 0,
                'compare_duration': c_note.duration_ms if hasattr(c_note, 'duration_ms') else 0,
                'hammer_time_diff_ms': hammer_time_diff,
                'duration_diff_ms': duration_diff,
                'hammer_velocity_diff': hammer_velocity_diff,
                'baseline_after_touch': None,
                'compare_after_touch': None,
                'baseline_hammers': None,
                'compare_hammers': None,
            })
        
        # 记录未匹配的音符并附带组内序号
        if len(baseline_group) > min_len:
            for i in range(min_len, len(baseline_group)):
                note = baseline_group[i]
                note.group_sequence = i
                unmatched_baseline.append(note)
        if len(compare_group) > min_len:
            for i in range(min_len, len(compare_group)):
                note = compare_group[i]
                note.group_sequence = i
                unmatched_compare.append(note)
    
    match_end_time = time.time()
    total_matches = len(matched_pairs)
    logger.info(f"⏱️ [内部性能] 匹配逻辑总耗时: {(match_end_time - match_start_time)*1000:.2f}ms")
    logger.info(f"⏱️ [内部性能] 其中曲线数据序列化耗时: {curve_serialize_total_time*1000:.2f}ms")
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
