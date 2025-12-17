"""
匹配质量评级统计详情回调函数
"""
import traceback
import logging
import dash
import json
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dash import Input, Output, State, html, no_update, dash_table, dcc
from dash.exceptions import PreventUpdate
from typing import Dict, List, Optional, Tuple, Any, Union
from backend.session_manager import SessionManager

# 获取logger
logger = logging.getLogger(__name__)


def _calculate_note_keyon_time(note) -> float:
    """
    计算音符的按键开始时间

    Args:
        note: Note对象

    Returns:
        float: keyon时间（0.1ms单位）
    """
    try:
        if hasattr(note, 'after_touch') and note.after_touch is not None and len(note.after_touch.index) > 0:
            return note.after_touch.index[0] + getattr(note, 'offset', 0)
        elif hasattr(note, 'hammers') and note.hammers is not None and len(note.hammers.index) > 0:
            # 如果没有after_touch，使用第一个锤子的时间作为keyon
            return note.hammers.index[0] + getattr(note, 'offset', 0)
        else:
            return 0.0
    except (IndexError, AttributeError, TypeError):
        return 0.0

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


def _add_curve_trace(fig, note, times, color, name):
    """添加触后曲线到图表"""
    if len(note.after_touch) == 0 or times is None:
        return

    fig.add_trace(
        go.Scatter(
            x=times,
            y=note.after_touch.values,
            mode='lines',
            name=name,
            line=dict(color=color, width=2),
            showlegend=True
        )
    )


def _add_hammer_marker(fig, note, after_touch_times, color, name_prefix):
    """添加锤击时间点到图表"""
    if len(note.hammers) == 0 or len(note.hammers.values) == 0:
        return

    first_hammer_value = note.hammers.values[0]
    hammer_time = (note.hammers.index[0] + note.offset) / 10.0  # 转换为ms

    # 计算在触后曲线上的对应位置
    if len(note.after_touch) > 0 and after_touch_times is not None:
        time_diffs = abs(after_touch_times - hammer_time)
        closest_idx = time_diffs.argmin()
        after_touch_value = note.after_touch.iloc[closest_idx]
        hover_text = f'{name_prefix}锤击时间<br>时间: %{{x:.2f}} ms<br>触后值: %{{y}}<br>锤速: {first_hammer_value}<extra></extra>'
    else:
        after_touch_value = 0
        hover_text = f'{name_prefix}锤击时间<br>时间: %{{x:.2f}} ms<br>触后值: N/A<br>锤速: {first_hammer_value}<extra></extra>'

    fig.add_trace(
        go.Scatter(
            x=[hammer_time],
            y=[after_touch_value],
            mode='markers',
            name=f'{name_prefix}锤击时间',
            marker=dict(color=color, size=10, symbol='diamond'),
            showlegend=True,
            hovertemplate=hover_text
        )
    )


def _add_hammer_marker_subplot(fig, note, after_touch_times, color, name_prefix, row, col):
    """添加锤击时间点到指定的子图"""
    if len(note.hammers) == 0 or len(note.hammers.values) == 0:
        return

    first_hammer_value = note.hammers.values[0]
    hammer_time = (note.hammers.index[0] + note.offset) / 10.0  # 转换为ms

    # 计算在触后曲线上的对应位置
    if len(note.after_touch) > 0 and after_touch_times is not None:
        time_diffs = abs(after_touch_times - hammer_time)
        closest_idx = time_diffs.argmin()
        after_touch_value = note.after_touch.iloc[closest_idx]
        hover_text = f'{name_prefix}锤击时间<br>时间: %{{x:.2f}} ms<br>触后值: %{{y}}<br>锤速: {first_hammer_value}<extra></extra>'
    else:
        after_touch_value = 0
        hover_text = f'{name_prefix}锤击时间<br>时间: %{{x:.2f}} ms<br>触后值: N/A<br>锤速: {first_hammer_value}<extra></extra>'

    fig.add_trace(
        go.Scatter(
            x=[hammer_time],
            y=[after_touch_value],
            mode='markers',
            name=f'{name_prefix}锤击时间',
            marker=dict(color=color, size=10, symbol='diamond'),
            showlegend=True,  # 在子图中显示图例
            hovertemplate=hover_text
        ),
        row=row, col=col
    )


def _add_hammer_marker_subplot_offset(fig, note, after_touch_times, color, name_prefix, row, col, offset_ms):
    """添加偏移后的锤击时间点到指定的子图"""
    if len(note.hammers) == 0 or len(note.hammers.values) == 0:
        return

    first_hammer_value = note.hammers.values[0]
    hammer_time = (note.hammers.index[0] + note.offset) / 10.0  # 转换为ms
    hammer_time_offset = hammer_time - offset_ms  # 应用偏移

    # 计算在触后曲线上的对应位置
    if len(note.after_touch) > 0 and after_touch_times is not None:
        time_diffs = abs(after_touch_times - hammer_time_offset)
        closest_idx = time_diffs.argmin()
        after_touch_value = note.after_touch.iloc[closest_idx]
        hover_text = f'{name_prefix}锤击时间 (偏移后)<br>原始时间: {hammer_time:.2f} ms<br>偏移后时间: %{{x:.2f}} ms<br>偏移量: {offset_ms:.2f} ms<br>触后值: %{{y}}<br>锤速: {first_hammer_value}<extra></extra>'
    else:
        after_touch_value = 0
        hover_text = f'{name_prefix}锤击时间 (偏移后)<br>原始时间: {hammer_time:.2f} ms<br>偏移后时间: %{{x:.2f}} ms<br>偏移量: {offset_ms:.2f} ms<br>触后值: N/A<br>锤速: {first_hammer_value}<extra></extra>'

    fig.add_trace(
        go.Scatter(
            x=[hammer_time_offset],
            y=[after_touch_value],
            mode='markers',
            name=f'{name_prefix}锤击时间 (偏移后)',
            marker=dict(color=color, size=10, symbol='diamond'),
            showlegend=False,  # 第二行不显示图例，避免重复
            hovertemplate=hover_text
        ),
        row=row, col=col
    )


def _add_curve_to_subplot(fig, note, times, color, name, row, col, show_legend=True):
    """添加触后曲线到指定的子图"""
    if len(note.after_touch) == 0 or times is None:
        return

    fig.add_trace(
        go.Scatter(
            x=times,
            y=note.after_touch.values,
            mode='lines',
            name=name,
            line=dict(color=color, width=2),
            showlegend=show_legend
        ),
        row=row, col=col
    )


def _get_average_delay(backend, algorithm_name):
    """获取平均延时"""
    try:
        if algorithm_name and algorithm_name != 'single':
            # 多算法模式
            active_algorithms = backend.get_active_algorithms() if hasattr(backend, 'get_active_algorithms') else []
            target_algorithm = next((alg for alg in active_algorithms if alg.metadata.algorithm_name == algorithm_name), None)
            if target_algorithm and target_algorithm.analyzer and hasattr(target_algorithm.analyzer, 'get_global_average_delay'):
                average_delay_0_1ms = target_algorithm.analyzer.get_global_average_delay()
            else:
                average_delay_0_1ms = 0.0
        else:
            # 单算法模式
            average_delay_0_1ms = backend.get_global_average_delay()

        average_delay_ms = average_delay_0_1ms / 10.0
        print(f"[DEBUG] 获取平均延时: {average_delay_ms:.2f}ms (算法: {algorithm_name})")
        return average_delay_ms
    except Exception as e:
        print(f"[WARNING] 获取平均延时失败: {e}")
        return 0.0


def _create_curves_subplot(backend, key_id, algorithm_name, matched_result):
    """创建曲线对比子图"""
    # 获取数据
    note_matcher = get_note_matcher_from_backend(backend, algorithm_name)
    if not note_matcher:
        return None

    record_note = note_matcher._record_data[matched_result.record_index]
    replay_note = note_matcher._replay_data[matched_result.replay_index]

    # 时间转换
    record_after_touch_times = (record_note.after_touch.index + record_note.offset) / 10.0 if len(record_note.after_touch) > 0 else None
    replay_after_touch_times = (replay_note.after_touch.index + replay_note.offset) / 10.0 if len(replay_note.after_touch) > 0 else None

    # 获取平均延时并计算偏移
    average_delay_ms = _get_average_delay(backend, algorithm_name)
    replay_after_touch_times_offset = replay_after_touch_times - average_delay_ms if replay_after_touch_times is not None else None

    # 创建子图
    fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=(
            '原始触后曲线对比',
            f'偏移后触后曲线对比 (平均延时: {average_delay_ms:.2f}ms)'
        ),
        vertical_spacing=0.2,
        row_heights=[0.5, 0.5]
    )

    # 添加第一行曲线和锤击点
    _add_curve_to_subplot(fig, record_note, record_after_touch_times, 'blue', '录制触后', 1, 1, True)
    _add_curve_to_subplot(fig, replay_note, replay_after_touch_times, 'red', '播放触后', 1, 1, True)
    _add_hammer_marker_subplot(fig, record_note, record_after_touch_times, 'blue', '录制', 1, 1)
    _add_hammer_marker_subplot(fig, replay_note, replay_after_touch_times, 'red', '播放', 1, 1)

    # 添加第二行曲线和锤击点
    _add_curve_to_subplot(fig, record_note, record_after_touch_times, 'blue', '录制触后 (偏移后)', 2, 1, False)
    _add_curve_to_subplot(fig, replay_note, replay_after_touch_times_offset, 'red', '播放触后 (偏移后)', 2, 1, False)
    _add_hammer_marker_subplot_offset(fig, record_note, record_after_touch_times, 'blue', '录制', 2, 1, 0)
    _add_hammer_marker_subplot_offset(fig, replay_note, replay_after_touch_times_offset, 'red', '播放', 2, 1, average_delay_ms)

    return fig


def _configure_figure_layout(fig, key_id, algorithm_name):
    """配置图表布局"""
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


def _create_modal_style(display='block'):
    """创建模态框样式"""
    return {
        'display': display,
        'position': 'fixed',
        'zIndex': '9999',
        'left': '0',
        'top': '0',
        'width': '100%',
        'height': '100%',
        'backgroundColor': 'rgba(0,0,0,0.6)',
        'backdropFilter': 'blur(5px)'
    }


def _handle_close_button():
    """处理关闭按钮点击"""
    return _create_modal_style('none'), [], no_update


def _parse_table_trigger(trigger_id):
    """解析表格点击的触发信息"""
    try:
        id_part = trigger_id.split('.')[0]
        table_props = json.loads(id_part)
        table_index = table_props.get('index')
        return table_index
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def _extract_active_cell(active_cells):
    """从active_cells列表中提取激活的单元格"""
    for cell in active_cells:
        if cell and isinstance(cell, dict) and 'row' in cell:
            return cell
    return None


def _get_table_data(table_data_list, table_index):
    """根据表格索引获取对应的数据"""
    if isinstance(table_data_list, list) and len(table_data_list) > 0:
        # 在多算法模式下，我们需要根据 table_index 找到对应的表格数据
        # 由于回调使用了 dash.ALL，table_data_list 包含所有表格的数据
        # 我们可以通过 table_index 在列表中查找匹配的数据

        # 由于 dash.ALL 返回的数据顺序通常与组件定义顺序一致
        # 我们可以尝试通过索引位置来匹配，或者通过数据内容来匹配

        # 更简单的方法：由于表格数据通常按算法顺序创建
        # 我们可以根据 table_index 的值来选择对应的数据
        if table_index and isinstance(table_index, str):
            # 尝试通过某种启发式方法匹配数据
            # 例如，如果 table_index 是算法名称，我们可以检查数据中是否包含该算法的信息
            for table_data in table_data_list:
                if table_data and isinstance(table_data, list) and len(table_data) > 0:
                    # 检查第一行数据是否包含算法信息
                    first_row = table_data[0] if table_data else {}
                    if isinstance(first_row, dict) and 'algorithm_name' in first_row:
                        if first_row.get('algorithm_name') == table_index:
                            return table_data

        # 如果没有找到匹配的数据，返回第一个非空数据
        for table_data in table_data_list:
            if table_data and isinstance(table_data, list) and len(table_data) > 0:
                return table_data

        # 默认返回第一个表格的数据（向后兼容）
        return table_data_list[0]
    return None


def _get_table_data_by_index(table_data_list, triggered_index):
    """根据触发的索引获取对应的表格数据"""
    if isinstance(table_data_list, list) and len(table_data_list) > 0:
        # 在多算法模式下，尝试根据triggered_index找到对应的数据

        # 方法1：检查数据内容是否包含匹配的算法信息
        for table_data in table_data_list:
            if table_data and isinstance(table_data, list) and len(table_data) > 0:
                # 检查第一行数据是否包含算法信息
                first_row = table_data[0] if table_data else {}
                if isinstance(first_row, dict) and 'algorithm_name' in first_row:
                    if first_row.get('algorithm_name') == triggered_index:
                        return table_data

        # 方法2：如果没有找到匹配的，根据数据的位置关系返回
        # 通常第一个数据对应第一个算法，第二个对应第二个算法
        # 这里简化处理，返回第一个非空数据
        for table_data in table_data_list:
            if table_data and isinstance(table_data, list) and len(table_data) > 0:
                return table_data

        # 默认返回第一个
        return table_data_list[0]
    return None


def _extract_row_data(table_data, active_cell):
    """从表格数据中提取点击行的数据"""
    if not table_data or not active_cell:
        return None

    row_idx = active_cell.get('row')
    if row_idx is None or row_idx >= len(table_data):
        return None

    return table_data[row_idx]


def _process_note_data(session_manager, session_id, row_data, table_index, active_cell=None):
    """处理音符数据并生成图表"""
    if not row_data:
        return _create_modal_style(), [html.Div("无法获取行数据", className="text-danger text-center")], no_update

    key_id = row_data.get('keyId')
    global_index = row_data.get('global_index')
    data_type = row_data.get('data_type')

    if not key_id:
        return _create_modal_style(), [html.Div("无法获取按键ID", className="text-danger text-center")], no_update

    try:
        key_id = int(key_id)
    except (ValueError, TypeError):
        return _create_modal_style(), [html.Div("按键ID格式错误", className="text-danger text-center")], no_update

    # 获取后端实例
    backend = session_manager.get_backend(session_id)
    if not backend:
        return _create_modal_style(), [html.Div("无法获取后端实例", className="text-danger text-center")], no_update

    # 获取note_matcher
    note_matcher = get_note_matcher_from_backend(backend, table_index)
    if not note_matcher:
        return _create_modal_style(), [html.Div("无法获取匹配器", className="text-danger text-center")], no_update

    # 查找匹配结果
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
        return _create_modal_style(), [html.Div(f"未找到按键ID {key_id} 的匹配数据", className="text-muted text-center")], no_update

    # 生成图表
    try:
        comparison_content = generate_single_key_curves_comparison(
            backend, key_id, table_index, session_id, matched_result
        )

        # 准备跳转到瀑布图的信息
        clicked_info = {
            'key_id': key_id,
            'algorithm_name': table_index,
            'data_type': data_type,
            'global_index': global_index,
            'record_idx': matched_result.record_index if hasattr(matched_result, 'record_index') else None,
            'replay_idx': matched_result.replay_index if hasattr(matched_result, 'replay_index') else None,
            'source_plot_id': 'grade-detail-curves-modal',  # 标识来源是评级统计曲线对比
            'table_index': table_index,  # 保存表格索引
            'row_index': active_cell.get('row') if active_cell else None  # 保存点击的行索引
        }

        return _create_modal_style(), comparison_content, clicked_info

    except Exception as e:
        return _create_modal_style(), [html.Div(f"生成曲线对比图失败: {str(e)}", className="text-danger text-center")], no_update


def generate_single_key_curves_comparison(backend, key_id: int, algorithm_name: str, session_id: str, matched_result):
    """生成单个按键的曲线对比图"""
    try:
        # 创建曲线对比子图
        fig = _create_curves_subplot(backend, key_id, algorithm_name, matched_result)
        if fig is None:
            return [html.Div([html.P("无法获取匹配器", className="text-danger text-center")])]

        # 配置图表布局
        fig.update_layout(
            height=700,  # 增大高度以提供更多间距
            title_text=f"按键 {key_id} 曲线对比 - {algorithm_name}",
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            ),
            hovermode='x unified',
            margin=dict(t=80, b=50, l=50, r=50)  # 增加边距
        )

        # 更新坐标轴标签
        fig.update_xaxes(title_text="时间 (ms)", row=1, col=1)
        fig.update_xaxes(title_text="时间 (ms)", row=2, col=1)

        fig.update_yaxes(title_text="触后值", row=1, col=1)
        fig.update_yaxes(title_text="触后值", row=2, col=1)

        # 添加网格线，便于对比
        for row in [1, 2]:
            fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='lightgray', row=row, col=1)
            fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='lightgray', row=row, col=1)

        return [
            dcc.Graph(figure=fig),
            html.Div([
                html.Button(
                    "跳转到瀑布图",
                    id="jump-to-waterfall-btn-from-grade-detail",
                    className="btn btn-success",
                    style={
                        'backgroundColor': '#28a745',
                        'border': 'none',
                        'color': 'white',
                        'padding': '8px 16px',
                        'borderRadius': '4px',
                        'cursor': 'pointer',
                        'marginTop': '10px'
                    }
                )
            ], style={'textAlign': 'center', 'marginTop': '10px'})
        ]

    except Exception as e:
        print(f"[ERROR] 生成单按键曲线对比图失败: {e}")
        
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

        # 处理关闭按钮
        if trigger_id == 'close-grade-detail-curves-modal.n_clicks':
            return _handle_close_button()

        # 处理表格点击
        if 'grade-detail-datatable' in trigger_id and 'active_cell' in trigger_id:
            # 解析表格信息 - 获取触发表格的索引
            table_index = _parse_table_trigger(trigger_id)
            if not table_index:
                return current_style, [], no_update

            # 根据表格索引找到对应的active_cell和table_data
            # 由于dash.ALL的返回顺序与组件定义顺序一致，我们需要找到匹配的索引
            active_cell = None
            table_data = None

            # 解析触发源的完整ID来获取索引位置
            try:
                # trigger_id 格式类似: '{"index":"algorithm_name","type":"grade-detail-datatable"}.active_cell'
                id_part = trigger_id.split('.')[0]
                table_props = json.loads(id_part)
                triggered_index = table_props.get('index')

                # 在多算法模式下，我们需要找到对应索引的数据
                # 由于回调参数的顺序与组件定义顺序一致，我们可以尝试匹配
                if triggered_index:
                    # 简化处理：假设第一个匹配的数据就是正确的
                    # 在实际应用中，可能需要更复杂的匹配逻辑
                    active_cell = _extract_active_cell(active_cells)
                    table_data = _get_table_data_by_index(table_data_list, triggered_index)
                else:
                    # 单算法模式或默认处理
                    active_cell = _extract_active_cell(active_cells)
                    table_data = _get_table_data(table_data_list, table_index)

            except (json.JSONDecodeError, KeyError):
                # 回退到原来的逻辑
                active_cell = _extract_active_cell(active_cells)
                table_data = _get_table_data(table_data_list, table_index)

            if not active_cell or not table_data:
                return current_style, [], no_update

            # 提取行数据
            row_data = _extract_row_data(table_data, active_cell)
            if not row_data:
                return current_style, [], no_update

            # 处理音符数据并生成图表
            return _process_note_data(session_manager, session_id, row_data, table_index, active_cell)

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

        # 数据类型映射
        data_type_map = {
            'record': ('录制', '_record_data'),
            'replay': ('播放', '_replay_data')
        }

        # 一次遍历处理所有失败匹配
        for (data_type, index), reason in failure_reasons.items():
            if data_type in data_type_map:
                display_type, data_attr = data_type_map[data_type]

                # 获取对应的数据列表
                data_list = getattr(note_matcher, data_attr, [])
                if index < len(data_list):
                    note = data_list[index]
                    row = create_failed_match_row(note, index, display_type, reason, algorithm_name)
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


def register_grade_detail_jump_callbacks(app, session_manager: SessionManager):
    """注册评级统计跳转回调函数"""

    # 评级统计曲线对比跳转到瀑布图按钮回调
    @app.callback(
        [Output('main-plot', 'figure', allow_duplicate=True),
         Output('main-tabs', 'value', allow_duplicate=True),
         Output('grade-detail-curves-modal', 'style', allow_duplicate=True),
         Output('jump-source-plot-id', 'data', allow_duplicate=True)],
        [Input('jump-to-waterfall-btn-from-grade-detail', 'n_clicks')],
        [State('session-id', 'data'),
         State('current-clicked-point-info', 'data')],
        prevent_initial_call=True
    )
    def handle_jump_to_waterfall_from_grade_detail(n_clicks, session_id, point_info):
        """处理评级统计曲线对比跳转到瀑布图按钮点击"""
        from dash import callback_context

        ctx = callback_context
        if not ctx.triggered:
            return no_update, no_update, no_update, no_update

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        if trigger_id != 'jump-to-waterfall-btn-from-grade-detail':
            return no_update, no_update, no_update, no_update

        if not n_clicks or n_clicks == 0:
            return no_update, no_update, no_update, no_update

        if not point_info:
            logger.warning("[WARNING] 评级统计: 没有存储的数据点信息，无法跳转")
            return no_update, no_update, no_update, no_update

        # 获取来源图表ID
        source_plot_id = point_info.get('source_plot_id', 'grade-detail-curves-modal')

        backend = session_manager.get_backend(session_id)
        if not backend:
            logger.warning("[WARNING] 评级统计: 没有找到backend")
            return no_update, no_update, no_update, no_update

        try:
            algorithm_name = point_info.get('algorithm_name')
            record_idx = point_info.get('record_idx')
            replay_idx = point_info.get('replay_idx')
            key_id = point_info.get('key_id')
            available_data = point_info.get('available_data')  # 检查是否有单侧数据标记

            # 对于评级统计，至少需要一个索引；对于错误表格，允许单侧数据
            if record_idx is None and replay_idx is None:
                logger.warning(f"[WARNING] 数据点信息不完整: {point_info}")
                return no_update, no_update, no_update, no_update

            logger.info(f"[PROCESS] 评级统计跳转到瀑布图: 算法={algorithm_name}, record_idx={record_idx}, replay_idx={replay_idx}, 按键={key_id}")

            # 计算跳转点的时间信息 - 基于瀑布图中实际显示的数据点位置
            center_time_ms = None
            target_y_position = None

            # 根据数据源类型查找音符数据
            if point_info.get('source_plot_id', '').startswith('error-table'):
                # 来自错误表格（丢锤/多锤）
                available_data = point_info.get('available_data', 'record')
                global_index = point_info.get('global_index')

                if algorithm_name == 'single':
                    # 单算法模式
                    if available_data == 'record':
                        valid_data = getattr(backend.analyzer, 'valid_record_data', [])
                    else:
                        valid_data = getattr(backend.analyzer, 'valid_replay_data', [])

                    if valid_data and global_index < len(valid_data):
                        note_data = valid_data[global_index]
                        if hasattr(note_data, 'hammers') and note_data.hammers is not None and len(note_data.hammers.index) > 0:
                            hammer_time = note_data.hammers.index[0] + getattr(note_data, 'offset', 0)
                            center_time_ms = hammer_time / 10.0  # 转换为ms
                            target_y_position = float(key_id)  # 基础Y位置
                            logger.info(f"🔍 错误表格单算法: hammer_time={hammer_time}, center_time_ms={center_time_ms}")
                else:
                    # 多算法模式
                    if backend.multi_algorithm_mode and backend.multi_algorithm_manager:
                        algorithm = backend.multi_algorithm_manager.get_algorithm(algorithm_name)
                        if algorithm and algorithm.analyzer:
                            if available_data == 'record':
                                valid_data = getattr(algorithm.analyzer, 'valid_record_data', [])
                            else:
                                valid_data = getattr(algorithm.analyzer, 'valid_replay_data', [])

                            if valid_data and global_index < len(valid_data):
                                note_data = valid_data[global_index]
                                if hasattr(note_data, 'hammers') and note_data.hammers is not None and len(note_data.hammers.index) > 0:
                                    hammer_time = note_data.hammers.index[0] + getattr(note_data, 'offset', 0)
                                    center_time_ms = hammer_time / 10.0  # 转换为ms
                                    target_y_position = float(key_id)  # 基础Y位置
                                    logger.info(f"🔍 错误表格多算法: hammer_time={hammer_time}, center_time_ms={center_time_ms}")
            else:
                # 来自评级统计表格（匹配对）
                if algorithm_name:
                    # 多算法模式
                    if backend.multi_algorithm_mode and backend.multi_algorithm_manager:
                        algorithm = backend.multi_algorithm_manager.get_algorithm(algorithm_name)
                        if algorithm and algorithm.analyzer and algorithm.analyzer.note_matcher:
                            matched_pairs = algorithm.analyzer.matched_pairs
                            logger.info(f"🔍 多算法模式: 找到 {len(matched_pairs)} 个匹配对")

                            # 查找对应的匹配对
                            for record_idx_in_pair, replay_idx_in_pair, record_note, replay_note in matched_pairs:
                                if record_idx_in_pair == record_idx and replay_idx_in_pair == replay_idx:
                                    # 计算瀑布图中实际显示的数据点时间位置
                                    # 取录制音符第一个锤子的时间作为标注位置
                                    if hasattr(record_note, 'hammers') and record_note.hammers is not None and len(record_note.hammers.index) > 0:
                                        record_hammer_time = record_note.hammers.index[0] + getattr(record_note, 'offset', 0)
                                        center_time_ms = record_hammer_time / 10.0  # 转换为ms
                                        target_y_position = float(key_id)  # 基础Y位置
                                        logger.info(f"🔍 找到匹配对: record_hammer_time={record_hammer_time}, center_time_ms={center_time_ms}")
                                    break
                else:
                    # 单算法模式
                    if backend.analyzer and backend.analyzer.note_matcher:
                        matched_pairs = backend.analyzer.note_matcher.matched_pairs
                        logger.info(f"🔍 单算法模式: 找到 {len(matched_pairs)} 个匹配对")

                        # 查找对应的匹配对
                        for record_idx_in_pair, replay_idx_in_pair, record_note, replay_note in matched_pairs:
                            if record_idx_in_pair == record_idx and replay_idx_in_pair == replay_idx:
                                # 计算瀑布图中实际显示的数据点时间位置
                                # 取录制音符第一个锤子的时间作为标注位置
                                if hasattr(record_note, 'hammers') and record_note.hammers is not None and len(record_note.hammers.index) > 0:
                                    record_hammer_time = record_note.hammers.index[0] + getattr(record_note, 'offset', 0)
                                    center_time_ms = record_hammer_time / 10.0  # 转换为ms
                                    target_y_position = float(key_id)  # 基础Y位置
                                    logger.info(f"🔍 找到匹配对: record_hammer_time={record_hammer_time}, center_time_ms={center_time_ms}")
                                break

            # 生成新的瀑布图
            waterfall_fig = backend.generate_waterfall_plot()
            if not waterfall_fig:
                logger.warning(f"[WARNING] 评级统计: 瀑布图生成失败")
                return no_update, no_update, no_update, no_update

            # 在瀑布图中添加高亮标记（如果有时间信息）
            if center_time_ms is not None and target_y_position is not None:
                # 计算标记的y位置（使用预先计算的target_y_position，如果是多算法模式需要考虑偏移）
                marker_y = target_y_position
                if algorithm_name and backend.multi_algorithm_mode and backend.multi_algorithm_manager:
                    # 多算法模式：需要找到该算法对应的y偏移
                    active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()
                    algorithm_y_range = 100  # 与瀑布图生成器保持一致
                    algorithm_y_offset = 0
                    for idx, alg in enumerate(active_algorithms):
                        if alg.metadata.algorithm_name == algorithm_name:
                            algorithm_y_offset = idx * algorithm_y_range
                            break
                    marker_y = target_y_position + algorithm_y_offset

                # 添加垂直参考线标记跳转的数据点（贯穿整个y轴）
                waterfall_fig.add_vline(
                    x=center_time_ms,
                    line_dash="dash",
                    line_color="red",
                    line_width=4,
                    opacity=0.9,
                    annotation_text=f"跳转点: 按键 {key_id}" + (f" (算法: {algorithm_name})" if algorithm_name else ""),
                    annotation_position="top",
                    annotation=dict(
                        font=dict(size=16, color="red", family="Arial Black"),
                        bgcolor="rgba(255, 255, 255, 0.9)",
                        bordercolor="red",
                        borderwidth=2,
                        borderpad=4
                    )
                )

                # 在按键位置添加一个醒目的标记点
                waterfall_fig.add_trace(go.Scatter(
                    x=[center_time_ms],
                    y=[marker_y],
                    mode='markers+text',
                    marker=dict(
                        symbol='star',
                        size=20,
                        color='red',
                        line=dict(width=3, color='darkred')
                    ),
                    text=[f"按键 {key_id}"],
                    textposition="top center",
                    textfont=dict(size=16, color="red", family="Arial Black", weight="bold"),
                    name='跳转标记',
                    showlegend=False,
                    hovertemplate=f'<b>[TARGET] 跳转点</b><br>按键: {key_id}<br>时间: {center_time_ms:.1f}ms' + (f'<br>算法: {algorithm_name}' if algorithm_name else '') + '<extra></extra>'
                ))

                logger.info(f"[OK] 已在瀑布图中添加跳转标记: 按键={key_id}, 时间={center_time_ms:.1f}ms, y位置={marker_y:.1f}")
            else:
                if center_time_ms is None:
                    logger.error(f"[ERROR] 无法计算 center_time_ms: record_idx={record_idx}, replay_idx={replay_idx}, algorithm_name={algorithm_name}")
                if key_id is None:
                    logger.error(f"[ERROR] key_id 为 None: point_info={point_info}")

            # 切换到瀑布图标签页
            return waterfall_fig, "waterfall-tab", {'display': 'none'}, 'grade-detail-curves-modal'

        except Exception as e:
            logger.error(f"[ERROR] 评级统计跳转到瀑布图失败: {e}")
            logger.error(traceback.format_exc())
            return no_update, no_update, no_update, no_update


def register_grade_detail_return_callbacks(app, session_manager: SessionManager):
    """注册评级统计返回回调函数"""

    # 控制返回评级统计按钮显示/隐藏
    @app.callback(
        Output('btn-return-to-grade-detail', 'style'),
        [Input('jump-source-plot-id', 'data')],
        prevent_initial_call=True
    )
    def control_return_button_visibility(source_plot_id):
        """控制返回评级统计按钮的显示/隐藏"""
        if source_plot_id == 'grade-detail-curves-modal':
            # 从评级统计跳转过来，显示返回按钮
            return {'display': 'inline-block'}
        else:
            # 其他情况，隐藏返回按钮
            return {'display': 'none'}

    # 返回评级统计模态框按钮回调
    @app.callback(
        [Output('grade-detail-curves-modal', 'style', allow_duplicate=True),
         Output('main-tabs', 'value', allow_duplicate=True),
         Output('grade-detail-return-scroll-trigger', 'data'),
         Output('grade-detail-section-scroll-trigger', 'data')],
        [Input('btn-return-to-grade-detail', 'n_clicks')],
        [State('current-clicked-point-info', 'data')],
        prevent_initial_call=True
    )
    def handle_return_to_grade_detail(n_clicks, point_info):
        """处理返回评级统计模态框按钮点击"""
        if n_clicks and n_clicks > 0:
            logger.info(f"[PROCESS] 返回评级统计模态框")

            # 准备滚动触发数据
            scroll_data = None
            section_scroll_data = {'scroll_to': 'grade_detail_section'}
            if point_info and 'table_index' in point_info and 'row_index' in point_info:
                scroll_data = {
                    'table_index': point_info['table_index'],
                    'row_index': point_info['row_index']
                }
                logger.info(f"[PROCESS] 准备滚动到表格 {point_info['table_index']} 的行 {point_info['row_index']}")

            # 显示模态框，切换到报告标签页
            return ({'display': 'block', 'position': 'fixed', 'top': '50%', 'left': '50%',
                   'transform': 'translate(-50%, -50%)', 'zIndex': '1050', 'width': '90%',
                   'maxWidth': '1200px', 'maxHeight': '90vh', 'overflowY': 'auto'},
                   "report-tab",
                   scroll_data,
                   section_scroll_data)

        return no_update, no_update, None, None


# 在主注册函数中调用跳转回调注册
def register_all_callbacks(app, session_manager: SessionManager):
    """注册所有回调函数"""
    register_grade_detail_callbacks(app, session_manager)
    register_grade_detail_jump_callbacks(app, session_manager)