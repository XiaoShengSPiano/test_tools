"""
匹配质量评级统计详情回调函数
"""
import traceback
import dash
from dash import Input, Output, State, html, no_update, dash_table, dcc
from dash.exceptions import PreventUpdate
from typing import Dict, List, Optional, Tuple, Any, Union
from backend.session_manager import SessionManager

# 评级配置常量 - 统一版本
# 基于误差范围进行评级，与评级统计和表格筛选保持一致
GRADE_RANGE_CONFIG: Dict[str, Tuple[float, float]] = {
    'correct': (float('-inf'), 20),    # 优秀: 误差 ≤ 20ms
    'minor': (20, 30),                 # 良好: 20ms < 误差 ≤ 30ms
    'moderate': (30, 50),              # 一般: 30ms < 误差 ≤ 50ms
    'large': (50, 1000),               # 较差: 50ms < 误差 ≤ 1000ms
    'severe': (1000, float('inf')),    # 严重: 误差 > 1000ms
    'major': (float('inf'), float('inf'))  # 失败: 无匹配 (特殊处理)
}


def get_note_matcher_from_backend(backend, algorithm_name: Optional[str] = None) -> Optional[Any]:
    """
    从backend获取note_matcher实例

    Args:
        backend: 后端实例
        algorithm_name: 算法名称（None表示单算法模式）

    Returns:
        note_matcher实例或None
    """
    if algorithm_name:
        # 多算法模式
        active_algorithms = backend.get_active_algorithms() if hasattr(backend, 'get_active_algorithms') else []
        target_algorithm = next((alg for alg in active_algorithms if alg.metadata.algorithm_name == algorithm_name), None)
        if not target_algorithm or not target_algorithm.analyzer or not hasattr(target_algorithm.analyzer, 'note_matcher'):
            return None
        return target_algorithm.analyzer.note_matcher
    else:
        # 单算法模式
        if not backend.analyzer or not hasattr(backend.analyzer, 'note_matcher'):
            return None
        return backend.analyzer.note_matcher


def is_delay_in_grade_range(delay_error: float, grade_key: str) -> bool:
    """
    检查延时误差是否在指定评级的范围内

    Args:
        delay_error: 延时误差（毫秒）
        grade_key: 评级键

    Returns:
        是否在范围内
    """
    if grade_key == 'correct':
        return delay_error <= 25      # 精确匹配优质部分
    elif grade_key == 'minor':
        return 25 < delay_error <= 50  # 精确匹配一般部分
    elif grade_key == 'moderate':
        return 50 < delay_error <= 150 # 近似匹配优质部分
    elif grade_key == 'large':
        return 150 < delay_error <= 300 # 近似匹配一般部分
    elif grade_key == 'major':
        return delay_error > 300       # 失败匹配或误差过大
    else:
        return False


def format_hammer_time(note) -> str:
    """格式化锤击时间（只显示第一个，加offset）"""
    if hasattr(note, 'hammers') and not note.hammers.empty:
        first_time = note.hammers.index[0]
        # 加上offset，与keyOn/keyOff保持一致的时间基准
        if hasattr(note, 'offset'):
            first_time += note.offset
        return f"{first_time/10.0:.2f}"
    return "无"


def format_hammer_velocity(note) -> str:
    """格式化锤速（只显示第一个）"""
    if hasattr(note, 'hammers') and not note.hammers.empty:
        first_velocity = note.hammers.values[0]
        return f"{first_velocity:.2f}"
    return "无"


def create_table_row(item: Dict, note, data_type: str, grade_key: str) -> Dict[str, Any]:
    """
    创建表格行数据

    Args:
        item: 偏移对齐数据项
        note: Note对象
        data_type: 数据类型（'录制'或'播放'）
        grade_key: 评级键

    Returns:
        表格行字典
    """
    delay_error = abs(item['corrected_offset']) / 10.0

    if data_type == '录制':
        key_on = item['record_keyon']
        key_off = item['record_keyoff']
        duration = item['record_duration']
    else:  # 播放
        key_on = item['replay_keyon']
        key_off = item['replay_keyoff']
        duration = item['replay_duration']

    # 根据数据类型显示对应的全局索引
    if data_type == '录制':
        global_index = item['record_index']
    else:  # 播放
        global_index = item['replay_index']

    row = {
        'data_type': data_type,
        'global_index': global_index,
        'keyId': item['key_id'],
        'keyOn': f"{key_on / 10.0:.2f}",
        'keyOff': f"{key_off / 10.0:.2f}",
        'hammer_times': format_hammer_time(note),
        'hammer_velocities': format_hammer_velocity(note),
        'duration': f"{duration / 10.0:.2f}",
        'match_status': f"延时误差: {delay_error:.2f}ms",
        'row_type': 'record' if data_type == '录制' else 'replay'
    }

    return row


def generate_single_key_curves_comparison(backend, key_id: int, algorithm_name: str, session_id: str, matched_result):
    """生成单个按键的曲线对比图"""
    try:
        # 获取note_matcher
        note_matcher = get_note_matcher_from_backend(backend, algorithm_name)
        if not note_matcher:
            return [html.Div([html.P("无法获取匹配器", className="text-danger text-center")])]

        # 获取录制和播放音符
        record_note = note_matcher._record_data[matched_result.record_index]
        replay_note = note_matcher._replay_data[matched_result.replay_index]

        # 为after_touch时间戳加上offset，转换为绝对时间，然后转换为ms
        record_after_touch_times = (record_note.after_touch.index + record_note.offset) / 10.0  # 转换为ms
        replay_after_touch_times = (replay_note.after_touch.index + replay_note.offset) / 10.0  # 转换为ms

        # 生成曲线对比图
        import plotly.graph_objects as go

        # 创建单图布局：触后曲线对比
        fig = go.Figure()

        # 触后曲线 - 录制和播放在同一个图中
        if len(record_note.after_touch) > 0:
            fig.add_trace(
                go.Scatter(
                    x=record_after_touch_times,  # 使用加上offset的绝对时间
                    y=record_note.after_touch.values,
                    mode='lines',
                    name='录制触后',
                    line=dict(color='blue', width=2),
                    showlegend=True
                )
            )

        if len(replay_note.after_touch) > 0:
            fig.add_trace(
                go.Scatter(
                    x=replay_after_touch_times,  # 使用加上offset的绝对时间
                    y=replay_note.after_touch.values,
                    mode='lines',
                    name='播放触后',
                    line=dict(color='red', width=2),
                    showlegend=True
                )
            )

        # 添加锤击时间点 - 使用hammers的第一个锤速数据
        # 录制锤击点
        if len(record_note.hammers) > 0 and len(record_note.hammers.values) > 0:
            first_hammer_value = record_note.hammers.values[0]
            hammer_time = (record_note.hammers.index[0] + record_note.offset) / 10.0  # 转换为ms

            # 计算在触后曲线上的对应位置
            if len(record_note.after_touch) > 0:
                # 找到触后曲线中最接近锤击时间的时间点
                time_diffs = abs(record_after_touch_times - hammer_time)
                closest_idx = time_diffs.argmin()
                after_touch_value = record_note.after_touch.iloc[closest_idx]

                fig.add_trace(
                    go.Scatter(
                        x=[hammer_time],
                        y=[after_touch_value],
                        mode='markers',
                        name='录制锤击时间',
                        marker=dict(color='blue', size=10, symbol='diamond'),
                        showlegend=True,
                        hovertemplate='录制锤击时间<br>时间: %{x:.2f} ms<br>触后值: %{y}<br>锤速: ' + f'{first_hammer_value}<extra></extra>'
                    )
                )
            else:
                # 如果没有触后曲线数据，在y=0的位置显示锤击点
                fig.add_trace(
                    go.Scatter(
                        x=[hammer_time],
                        y=[0],
                        mode='markers',
                        name='录制锤击时间',
                        marker=dict(color='blue', size=10, symbol='diamond'),
                        showlegend=True,
                        hovertemplate='录制锤击时间<br>时间: %{x:.2f} ms<br>触后值: N/A<br>锤速: ' + f'{first_hammer_value}<extra></extra>'
                    )
                )

        # 播放锤击点
        if len(replay_note.hammers) > 0 and len(replay_note.hammers.values) > 0:
            first_hammer_value = replay_note.hammers.values[0]
            hammer_time = (replay_note.hammers.index[0] + replay_note.offset) / 10.0  # 转换为ms

            if len(replay_note.after_touch) > 0:
                time_diffs = abs(replay_after_touch_times - hammer_time)
                closest_idx = time_diffs.argmin()
                after_touch_value = replay_note.after_touch.iloc[closest_idx]

                fig.add_trace(
                    go.Scatter(
                        x=[hammer_time],
                        y=[after_touch_value],
                        mode='markers',
                        name='播放锤击时间',
                        marker=dict(color='red', size=10, symbol='diamond'),
                        showlegend=True,
                        hovertemplate='播放锤击时间<br>时间: %{x:.2f} ms<br>触后值: %{y}<br>锤速: ' + f'{first_hammer_value}<extra></extra>'
                    )
                )
            else:
                # 如果没有触后曲线数据，在y=0的位置显示锤击点
                fig.add_trace(
                    go.Scatter(
                        x=[hammer_time],
                        y=[0],
                        mode='markers',
                        name='播放锤击时间',
                        marker=dict(color='red', size=10, symbol='diamond'),
                        showlegend=True,
                        hovertemplate='播放锤击时间<br>时间: %{x:.2f} ms<br>触后值: N/A<br>锤速: ' + f'{first_hammer_value}<extra></extra>'
                    )
                )

        # 更新布局
        fig.update_layout(
            height=500,
            title_text=f"按键 {key_id} 触后曲线对比 - {algorithm_name}",
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            ),
            hovermode='x unified'
        )

        # 更新坐标轴标签
        fig.update_xaxes(title_text="时间 (ms)")
        fig.update_yaxes(title_text="触后值")

        # 添加网格线，便于对比
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='lightgray')
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='lightgray')

        return [dcc.Graph(figure=fig)]

    except Exception as e:
        print(f"[ERROR] 生成单按键曲线对比图失败: {e}")
        import traceback
        traceback.print_exc()
        return [html.Div([html.P(f"生成曲线对比图失败: {str(e)}", className="text-danger text-center")])]


def register_grade_detail_callbacks(app, session_manager: SessionManager):
    """注册评级统计详情回调函数"""

    # 评级统计表格点击回调 - 显示曲线对比图（使用专用模态框）
    @app.callback(
        [Output('grade-detail-curves-modal', 'style'),
         Output('grade-detail-curves-comparison-container', 'children'),
         Output('current-clicked-point-info', 'data')],
        [Input({'type': 'grade-detail-datatable', 'index': dash.ALL}, 'active_cell'),
         Input('close-grade-detail-curves-modal', 'n_clicks')],
        [State({'type': 'grade-detail-datatable', 'index': dash.ALL}, 'data'),
         State('session-id', 'data'),
         State('grade-detail-curves-modal', 'style')]
    )
    def handle_grade_detail_table_click(active_cells, close_modal_clicks,
                                       table_data_list, session_id, current_style):
        """处理评级统计表格点击，显示按键曲线对比图"""

        # 检测触发源
        ctx = dash.callback_context
        if not ctx.triggered:
            return current_style, [], no_update

        trigger_id = ctx.triggered[0]['prop_id']

        # 如果点击了关闭按钮，隐藏模态框
        if trigger_id == 'close-grade-detail-curves-modal.n_clicks':
            modal_style = {
                'display': 'none',
                'position': 'fixed',
                'zIndex': '9999',
                'left': '0',
                'top': '0',
                'width': '100%',
                'height': '100%',
                'backgroundColor': 'rgba(0,0,0,0.6)',
                'backdropFilter': 'blur(5px)'
            }
            return modal_style, [], no_update


        # 检查是否是表格点击
        if 'grade-detail-datatable' in trigger_id and 'active_cell' in trigger_id:
            # 在Dash中使用ALL时，参数是列表格式，每个元素对应一个表格
            active_cell = None
            table_data = None
            table_index = None

            # 提取被点击的表格ID
            # trigger_id格式: '{"index":"pid_11-21-土耳其进行曲","type":"grade-detail-datatable"}.active_cell'
            try:
                id_part = trigger_id.split('.')[0]  # 获取ID部分
                import json
                table_props = json.loads(id_part)
                table_index = table_props.get('index')

                # active_cells是列表格式，包含所有表格的active_cell
                # 我们需要找到对应的active_cell（通常只有一个表格会被点击）
                if isinstance(active_cells, list):
                    for cell in active_cells:
                        if cell and isinstance(cell, dict) and 'row' in cell:
                            active_cell = cell
                            break

                # table_data_list也是列表格式
                if isinstance(table_data_list, list) and len(table_data_list) > 0:
                    table_data = table_data_list[0]  # 取第一个表格的数据

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                return current_style, [], no_update

            if not active_cell or not table_data:
                return current_style, [], no_update

            # 获取点击的行数据
            row_idx = active_cell.get('row')
            if row_idx is None or row_idx >= len(table_data):
                return current_style, [], no_update

            row_data = table_data[row_idx]

            # 从行数据中提取按键ID和全局索引
            key_id = row_data.get('keyId')
            global_index = row_data.get('global_index')
            data_type = row_data.get('data_type')

            if not key_id:
                return current_style, [], no_update

            # 转换按键ID
            try:
                key_id = int(key_id)
            except (ValueError, TypeError):
                return current_style, [], no_update

            # 获取后端实例
            backend = session_manager.get_backend(session_id)
            if not backend:
                return current_style, [], no_update

            # 获取note_matcher
            note_matcher = get_note_matcher_from_backend(backend, table_index)
            if not note_matcher:
                return current_style, [], no_update

            # 根据点击的行找到对应的匹配对
            matched_result = None
            for result in note_matcher.match_results:
                if result.is_success:
                    if data_type == '录制' and result.record_index == global_index:
                        matched_result = result
                        break
                    elif data_type == '播放' and result.replay_index == global_index:
                        matched_result = result
                        break

            if not matched_result:
                modal_style = {
                    'display': 'block',
                    'position': 'fixed',
                    'zIndex': '9999',
                    'left': '0',
                    'top': '0',
                    'width': '100%',
                    'height': '100%',
                    'backgroundColor': 'rgba(0,0,0,0.6)',
                    'backdropFilter': 'blur(5px)'
                }
                return modal_style, [html.Div([
                    html.P(f"未找到按键ID {key_id} 的匹配数据", className="text-muted text-center")
                ])], no_update

            # 生成曲线对比图
            try:
                comparison_content = generate_single_key_curves_comparison(
                    backend, key_id, table_index, session_id, matched_result
                )

                modal_style = {
                    'display': 'block',
                    'position': 'fixed',
                    'zIndex': '9999',
                    'left': '0',
                    'top': '0',
                    'width': '100%',
                    'height': '100%',
                    'backgroundColor': 'rgba(0,0,0,0.6)',
                    'backdropFilter': 'blur(5px)'
                }

                # 存储点击信息
                clicked_info = {
                    'key_id': key_id,
                    'algorithm_name': table_index,
                    'data_type': data_type,
                    'global_index': global_index
                }

                return modal_style, comparison_content, clicked_info

            except Exception as e:
                modal_style = {
                    'display': 'block',
                    'position': 'fixed',
                    'zIndex': '9999',
                    'left': '0',
                    'top': '0',
                    'width': '100%',
                    'height': '100%',
                    'backgroundColor': 'rgba(0,0,0,0.6)',
                    'backdropFilter': 'blur(5px)'
                }
                return modal_style, [html.Div([
                    html.P(f"生成曲线对比图失败: {str(e)}", className="text-danger text-center")
                ])], no_update

        return current_style, [], no_update


    # 统一的回调处理所有评级按钮点击，避免重叠
    @app.callback(
        Output({'type': 'grade-detail-table', 'index': dash.ALL}, 'style'),
        Output({'type': 'grade-detail-table', 'index': dash.ALL}, 'children'),
        Output({'type': 'grade-detail-datatable', 'index': dash.ALL}, 'columns'),
        Output({'type': 'grade-detail-datatable', 'index': dash.ALL}, 'data'),
        Input({'type': 'grade-detail-btn', 'index': dash.ALL}, 'n_clicks'),
        State('session-id', 'data'),
        prevent_initial_call=True
    )
    def show_grade_detail(n_clicks_list, session_id):
        """统一处理所有评级统计详情显示"""
        ctx = dash.callback_context
        if not ctx.triggered:
            return [no_update], [no_update], [no_update], [no_update]

        # 解析触发的按钮ID
        triggered_id = ctx.triggered[0]['prop_id']
        import json
        try:
            id_part = triggered_id.split('.')[0]
            button_props = json.loads(id_part)
            button_index = button_props['index']
        except (json.JSONDecodeError, KeyError):
            return [no_update], [no_update], [no_update], [no_update]

        print(f"[DEBUG] 评级统计详情回调被触发: button_index={button_index}")

        # 获取后端实例，确定有多少个表格需要更新
        backend = session_manager.get_backend(session_id)
        if not backend:
            return [no_update], [no_update], [no_update], [no_update]

        # 确定输出值的数量和类型
        active_algorithms = backend.get_active_algorithms() if hasattr(backend, 'get_active_algorithms') else []
        has_single_mode = hasattr(backend, 'analyzer') and backend.analyzer is not None

        # 计算表格数量：算法数量 + 单算法模式（如果没有多算法）
        if active_algorithms:
            num_outputs = len(active_algorithms)
        elif has_single_mode:
            num_outputs = 1
        else:
            return [no_update], [no_update], [no_update], [no_update]

        # 获取显示数据
        result = show_single_grade_detail(button_index, session_id, session_manager)

        # 初始化输出值 - 全部设置为no_update
        styles = [no_update] * num_outputs
        children_list = [no_update] * num_outputs
        columns = [no_update] * num_outputs
        data = [no_update] * num_outputs

        # 确定要更新的表格索引
        if '_' in button_index:
            # 多算法模式: "算法名_评级键" -> 更新对应算法的表格
            algorithm_name = button_index.rsplit('_', 1)[0]
            # 找到对应算法在active_algorithms中的索引
            target_index = None
            for i, algorithm in enumerate(active_algorithms):
                if algorithm.metadata.algorithm_name == algorithm_name:
                    target_index = i
                    break

            if target_index is not None:
                styles[target_index] = result[0]
                children_list[target_index] = result[1]
                columns[target_index] = result[2]
                data[target_index] = result[3]
        else:
            # 单算法模式: "评级键" -> 更新single表格（索引0）
            if has_single_mode and not active_algorithms:
                styles[0] = result[0]
                children_list[0] = result[1]
                columns[0] = result[2]
                data[0] = result[3]

        return styles, children_list, columns, data

    # 多算法模式 - 动态处理不同算法的按钮
    # 由于算法名称是动态的，我们需要使用更灵活的方法
    # 这里暂时只处理已知的算法，实际应用中可能需要更复杂的逻辑


def get_grade_detail_data(backend, grade_key: str, algorithm_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    获取评级统计的详细数据

    Args:
        backend: 后端实例
        grade_key: 评级键 ('correct', 'minor', 'moderate', 'large', 'major')
        algorithm_name: 算法名称（None表示单算法模式）

    Returns:
        表格行数据列表
    """
    try:
        # 验证评级键
        if grade_key not in GRADE_RANGE_CONFIG:
            return []

        # 获取note_matcher实例
        note_matcher = get_note_matcher_from_backend(backend, algorithm_name)
        if not note_matcher:
            return []

        # 特殊处理：匹配失败（major评级）
        if grade_key == 'major':
            return get_failed_matches_detail_data(note_matcher, algorithm_name)

        # 获取所有成功匹配对的偏移对齐数据（用于评级统计）
        # 与 get_graded_error_stats 保持完全相同的数据源
        all_matched_data = []
        # 直接从match_results中获取所有成功匹配的数据，与评级统计完全一致
        for result in note_matcher.match_results:
            if result.is_success:
                # 为详情筛选创建数据项，使用与评级统计相同的方法
                item = note_matcher._create_offset_data_item(result)
                all_matched_data.append(item)

        offset_data = all_matched_data
        if not offset_data:
            return []

        # 构建匹配对字典以快速查找Note对象
        # 从match_results中构建，包含所有成功的匹配
        pair_dict = {}
        for result in note_matcher.match_results:
            if result.is_success:
                pair_dict[(result.record_index, result.replay_index)] = (result.pair[0], result.pair[1])

        detail_data: List[Dict[str, Any]] = []
        filtered_count = 0

        # 处理每个偏移数据项
        for item in offset_data:
            error_abs = abs(item['corrected_offset'])
            error_ms = error_abs / 10.0

            # 使用与 get_graded_error_stats 完全一致的评级范围判断逻辑
            in_range = False
            if grade_key == 'correct' and error_ms <= 20:
                in_range = True
            elif grade_key == 'minor' and error_ms > 20 and error_ms <= 30:
                in_range = True
            elif grade_key == 'moderate' and error_ms > 30 and error_ms <= 50:
                in_range = True
            elif grade_key == 'large' and error_ms > 50 and error_ms <= 1000:
                in_range = True
            elif grade_key == 'severe' and error_ms > 1000:
                in_range = True
            # major 评级在其他地方处理 (匹配失败)

            if in_range:
                filtered_count += 1

                # 获取对应的Note对象
                record_idx = item['record_index']
                replay_idx = item['replay_index']
                record_note, replay_note = pair_dict.get((record_idx, replay_idx), (None, None))

                if record_note is None or replay_note is None:
                    continue

                # 创建录制和播放行
                record_row = create_table_row(item, record_note, '录制', grade_key)
                replay_row = create_table_row(item, replay_note, '播放', grade_key)

                # 添加算法名称（如果适用）
                if algorithm_name:
                    record_row['algorithm_name'] = algorithm_name
                    replay_row['algorithm_name'] = algorithm_name

                detail_data.extend([record_row, replay_row])

        # 调试信息
        print(f"[DEBUG] 评级 {grade_key}: 总数据 {len(offset_data)}, 筛选后 {filtered_count}, 表格行 {len(detail_data)}")

        return detail_data

    except Exception as e:
        print(f"获取评级统计详细数据失败: {e}")
        traceback.print_exc()
        return []


def get_failed_matches_detail_data(note_matcher, algorithm_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    获取匹配失败的详细数据

    Args:
        note_matcher: 音符匹配器实例
        algorithm_name: 算法名称

    Returns:
        表格行数据列表
    """
    try:
        # 从failure_reasons中获取失败的音符信息
        failure_reasons = getattr(note_matcher, 'failure_reasons', {})
        if not failure_reasons:
            return []

        detail_data: List[Dict[str, Any]] = []

        # 处理录制数据的失败匹配
        for (data_type, index), reason in failure_reasons.items():
            if data_type == 'record':
                # 获取原始音符数据
                if hasattr(note_matcher, '_record_data') and index < len(note_matcher._record_data):
                    note = note_matcher._record_data[index]
                    row = create_failed_match_row(note, index, '录制', reason, algorithm_name)
                    if row:
                        detail_data.append(row)

        # 处理播放数据的失败匹配
        for (data_type, index), reason in failure_reasons.items():
            if data_type == 'replay':
                # 获取原始音符数据
                if hasattr(note_matcher, '_replay_data') and index < len(note_matcher._replay_data):
                    note = note_matcher._replay_data[index]
                    row = create_failed_match_row(note, index, '播放', reason, algorithm_name)
                    if row:
                        detail_data.append(row)

        return detail_data

    except Exception as e:
        print(f"获取匹配失败详细数据失败: {e}")
        traceback.print_exc()
        return []


def create_failed_match_row(note, index: int, data_type: str, reason: str, algorithm_name: Optional[str] = None) -> Dict[str, Any]:
    """
    创建匹配失败的表格行数据

    Args:
        note: 音符对象
        index: 音符索引
        data_type: 数据类型 ('录制' 或 '播放')
        reason: 失败原因
        algorithm_name: 算法名称

    Returns:
        表格行字典
    """
    try:
        # 基本信息 - 对应新的列定义
        row = {
            'row_type': data_type,  # 显示为"录制"或"播放"
            'index': index,
            'key_id': getattr(note, 'id', 'N/A'),
            'reason': reason
        }

        # 时间信息
        if hasattr(note, 'after_touch') and note.after_touch is not None and not note.after_touch.empty:
            try:
                keyon_time = note.after_touch.index[0]
                keyoff_time = note.after_touch.index[-1] if len(note.after_touch.index) > 1 else keyon_time
                row['keyon'] = f"{keyon_time/10:.1f}ms"
                row['keyoff'] = f"{keyoff_time/10:.1f}ms"
                row['duration'] = f"{(keyoff_time - keyon_time)/10:.1f}ms"
            except:
                row['keyon'] = 'N/A'
                row['keyoff'] = 'N/A'
                row['duration'] = 'N/A'
        else:
            row['keyon'] = 'N/A'
            row['keyoff'] = 'N/A'
            row['duration'] = 'N/A'

        # 锤击信息
        if hasattr(note, 'hammers') and note.hammers is not None and not note.hammers.empty:
            try:
                hammer_time = note.hammers.index[0]
                row['hammer_time'] = f"{hammer_time/10:.1f}ms"
                if len(note.hammers.values) > 0:
                    row['hammer_velocity'] = f"{note.hammers.values[0]:.1f}"
                else:
                    row['hammer_velocity'] = 'N/A'
            except:
                row['hammer_time'] = 'N/A'
                row['hammer_velocity'] = 'N/A'
        else:
            row['hammer_time'] = 'N/A'
            row['hammer_velocity'] = 'N/A'

        # 添加算法名称
        if algorithm_name:
            row['algorithm_name'] = algorithm_name

        return row

    except Exception as e:
        print(f"创建匹配失败行数据失败: {e}")
        return None


def show_single_grade_detail(button_index, session_id, session_manager):
    """处理单个评级统计按钮的点击"""
    print(f"[DEBUG] 处理按钮: {button_index}")

    backend = session_manager.get_backend(session_id)
    if not backend:
        return {'display': 'none'}, no_update, [], []

    try:
        # 解析按钮ID获取评级类型
        grade_key = button_index

        # 检查是否是多算法模式下的按钮（格式：算法名_评级类型）
        if '_' in grade_key:
            algorithm_name, actual_grade_key = grade_key.rsplit('_', 1)
        else:
            algorithm_name = None
            actual_grade_key = grade_key

        print(f"[DEBUG] 算法名称: {algorithm_name}, 评级类型: {actual_grade_key}")

        # 获取详细数据
        detail_data = get_grade_detail_data(backend, actual_grade_key, algorithm_name)
        print(f"[DEBUG] 获取到数据条数: {len(detail_data)}")

        if not detail_data:
            # 没有数据，隐藏表格
            print(f"[DEBUG] 没有数据，隐藏表格")
            return {'display': 'none'}, no_update, [], []

        # 创建表格列定义 - 根据评级类型选择不同的列
        if actual_grade_key == 'major':
            # 匹配失败的列定义
            columns = [
                {"name": "类型", "id": "row_type"},
                {"name": "索引", "id": "index"},
                {"name": "键位ID", "id": "key_id"},
                {"name": "按键时间(ms)", "id": "keyon"},
                {"name": "释放时间(ms)", "id": "keyoff"},
                {"name": "锤击时间(ms)", "id": "hammer_time"},
                {"name": "锤速", "id": "hammer_velocity"},
                {"name": "按键时长(ms)", "id": "duration"},
                {"name": "失败原因", "id": "reason"}
            ]
        else:
            # 普通匹配的列定义 - 分行显示录制和播放信息，包含锤击时间和锤速
            columns = [
                {"name": "类型", "id": "data_type"},
                {"name": "全局索引", "id": "global_index"},
                {"name": "键位ID", "id": "keyId"},
                {"name": "按键时间(ms)", "id": "keyOn"},
                {"name": "释放时间(ms)", "id": "keyOff"},
                {"name": "锤击时间(ms)", "id": "hammer_times"},
                {"name": "锤速", "id": "hammer_velocities"},
                {"name": "按键时长(ms)", "id": "duration"},
                {"name": "匹配状态", "id": "match_status"}
            ]

        if algorithm_name:
            columns.insert(0, {"name": "算法名称", "id": "algorithm_name"})

        # 确定表格的正确index
        if algorithm_name:
            # 多算法模式：使用算法名称作为index
            table_index = algorithm_name
        else:
            # 单算法模式：使用'single'作为index
            table_index = 'single'

        # 创建表格内容
        table_children = [
            html.H5("详细数据", className="mb-3"),
            dash_table.DataTable(
                id={'type': 'grade-detail-datatable', 'index': table_index},
                columns=columns,
                data=detail_data,
                page_action='none',
                fixed_rows={'headers': True},  # 固定表头
                active_cell=None,  # 启用active_cell功能
                style_table={
                    'maxHeight': '400px',
                    'overflowY': 'auto',
                    'overflowX': 'auto'
                },
                style_cell={
                    'textAlign': 'center',
                    'fontSize': '14px',
                    'fontFamily': 'Arial, sans-serif',
                    'padding': '8px',
                    'minWidth': '80px'
                },
                style_header={
                    'backgroundColor': '#f8f9fa',
                    'fontWeight': 'bold',
                    'borderBottom': '2px solid #dee2e6'
                },
                style_data_conditional=[
                    # 录制行样式（默认白色背景）
                    {
                        'if': {'filter_query': '{row_type} = "record"'},
                        'backgroundColor': '#ffffff',
                        'color': '#000000'
                    },
                    # 播放行样式（浅蓝色背景）
                    {
                        'if': {'filter_query': '{row_type} = "replay"'},
                        'backgroundColor': '#e3f2fd',
                        'color': '#000000'
                    },
                    # 不同按键之间的分隔（浅灰色边框）
                    {
                        'if': {'row_index': 'odd'},
                        'borderBottom': '1px solid #e0e0e0'
                    },
                    # 悬停样式 - 提供视觉反馈
                    {
                        'if': {'state': 'active'},
                        'backgroundColor': 'rgba(0, 116, 217, 0.3)',
                        'border': '1px solid rgb(0, 116, 217)'
                    }
                ]
            )
        ]

        print(f"[DEBUG] 返回显示表格")
        return {'display': 'block', 'marginTop': '20px'}, table_children, columns, detail_data

    except Exception as e:
        print(f"[DEBUG] 处理评级统计详情失败: {e}")
        traceback.print_exc()
        return {'display': 'none'}, no_update, [], []