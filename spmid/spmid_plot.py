from matplotlib import cm
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import matplotlib.pyplot as plt
from .spmid_reader import SPMidReader
from utils.logger import Logger

logger = Logger.get_logger()

def get_bar_segments2(track):
    all_bars = []
    index = 0
    for note in track:
        key_on = note.after_touch.index[0] + note.offset
        
        key_off = note.after_touch.index[len(note.after_touch.index) - 1] + note.offset
        
        key_id = note.id

        for i in range(len(note.hammers)):
            t_hammer = note.hammers.index[i] + note.offset
            v_hammer = note.hammers.values[i]

            all_bars.append(
                (t_hammer, key_off, key_id, v_hammer, index)
            )
        index = index + 1

    return all_bars


def _smart_sample_bars(all_bars, max_points):
    """
    智能采样数据点，按时间窗口分组，保留最有代表性的数据
    
    采样策略：
    1. 按时间窗口（100ms）分组，确保时间分布均匀
    2. 在每个窗口内，优先保留：
       - 持续时间最长的音符（重要性高）
       - 力度值最大/最小的音符（特征明显）
       - 不同键ID的音符（保持键位多样性）
    3. 采样后数据点数量控制在max_points以内
    
    Args:
        all_bars: 所有数据点的列表，每个元素包含t_on, t_off, key_id, value, label, index
        max_points: 最大数据点数
    
    Returns:
        List: 采样后的数据点列表
    """
    if len(all_bars) <= max_points:
        return all_bars
    
    # 计算时间范围（单位：0.1ms，转换为ms）
    all_times = [b['t_on'] / 10.0 for b in all_bars] + [b['t_off'] / 10.0 for b in all_bars]
    min_time = min(all_times)
    max_time = max(all_times)
    time_span = max_time - min_time
    
    # 时间窗口大小（100ms）- 可根据数据量调整
    window_size_ms = 100.0
    num_windows = max(1, int(time_span / window_size_ms) + 1)
    
    # 目标：每个窗口采样多少个点
    points_per_window = max(1, max_points // num_windows)
    
    # 按时间窗口分组
    windows = {}
    for bar in all_bars:
        # 计算音符的中心时间（ms）
        center_time_ms = (bar['t_on'] / 10.0 + bar['t_off'] / 10.0) / 2.0
        window_idx = int((center_time_ms - min_time) / window_size_ms)
        window_key = min(window_idx, num_windows - 1)  # 确保索引不越界
        
        if window_key not in windows:
            windows[window_key] = []
        windows[window_key].append(bar)
    
    # 对每个窗口进行采样
    sampled_bars = []
    for window_key in sorted(windows.keys()):
        window_bars = windows[window_key]
        
        if len(window_bars) <= points_per_window:
            # 窗口内数据点不多，全部保留
            sampled_bars.extend(window_bars)
        else:
            # 窗口内数据点过多，需要采样
            # 策略：按重要性排序后选择前N个
            
            # 计算每个数据点的重要性得分
            # 重要性 = 持续时间权重 + 力度值权重 + 键位多样性权重
            scored_bars = []
            key_ids_seen = set()
            
            for bar in window_bars:
                duration_ms = (bar['t_off'] - bar['t_on']) / 10.0
                value = bar['value']
                
                # 持续时间权重（归一化到0-1）
                max_duration = max(b['t_off'] - b['t_on'] for b in window_bars) / 10.0
                duration_score = duration_ms / max_duration if max_duration > 0 else 0.5
                
                # 力度值权重（归一化到0-1）
                values = [b['value'] for b in window_bars]
                v_min, v_max = min(values), max(values)
                value_score = (value - v_min) / (v_max - v_min) if v_max > v_min else 0.5
                
                # 键位多样性权重（新键位加分）
                key_id = int(bar['key_id'])
                diversity_score = 1.0 if key_id not in key_ids_seen else 0.3
                key_ids_seen.add(key_id)
                
                # 综合得分（可调整权重）
                total_score = (
                    duration_score * 0.4 +      # 持续时间权重40%
                    value_score * 0.3 +          # 力度值权重30%
                    diversity_score * 0.3       # 键位多样性权重30%
                )
                
                scored_bars.append((total_score, bar))
            
            # 按得分降序排序，选择前points_per_window个
            scored_bars.sort(key=lambda x: x[0], reverse=True)
            sampled_bars.extend([bar for _, bar in scored_bars[:points_per_window]])
    
    # 如果采样后仍然超过max_points（边界情况），随机采样
    if len(sampled_bars) > max_points:
        import random
        random.seed(42)  # 固定随机种子，保证结果可复现
        sampled_bars = random.sample(sampled_bars, max_points)
        logger.warning(f"⚠️ 采样后仍超过阈值，进行随机采样到{max_points}个点")
    
    return sampled_bars
        
def plot_bar(record,play):
    fig, ax = plt.subplots(figsize=(16, 8))
    offsets = {
        'record': 0.0,
        'play': 0.5,
    }

    all_bars = []

    for df, label in [
        (record, 'record'),
        (play, 'play'),
    ]:
        if df is None:
            continue
        bars = get_bar_segments2(df)

        y_offset = offsets[label]
        for t_on, t_off, key_id, value, index in bars:
            all_bars.append({
                't_on': t_on,
                't_off': t_off,
                'key_id': key_id + y_offset,
                'value': value,
                'label': label,
                'index': index
            })

    # 归一化力度到0-1
    values = [b['value'] for b in all_bars]
    
    # 检查是否有数据，避免 min() 空序列错误
    if not values:
        logger.warning("⚠️ 筛选后没有数据，返回空图表")
        return None
    
    vmin, vmax = min(values), max(values)
    norm = plt.Normalize(vmin, vmax)
    cmap = plt.cm.tab20b  # 你可以换成其它colormap

    # 画bar
    for b in all_bars:
        ax.hlines(
            y=b['key_id'],
            xmin=b['t_on']/10,
            xmax=b['t_off']/10,
            colors=cmap(norm(b['value'])),
            linewidth=1,
            alpha=0.9,
        )

    # 力度色条
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    fig.colorbar(sm, ax=ax, label='Hammer')

    ax.set_xlabel('Time (ms)')
    ax.set_ylabel('Key ID (1-88: keys, 89-90: pedals)')
    ax.set_title('Piano Key/Pedal Events Waterfall (Bar = KeyOn~KeyOff, Color=Value)')
    ax.grid(True, linestyle='--', alpha=0.5)
    ax.set_yticks(list(range(1, 91)))
    plt.tight_layout()
    plt.show()

def plot_bar_plotly(record, play, time_range=None):
    """
    使用Plotly绘制钢琴按键事件瀑布图
    
    性能优化说明：
    - 当数据点超过阈值（默认5000）时，自动进行智能采样
    - 采样策略：按时间窗口分组，保留每个窗口中最有代表性的数据点
    - 确保采样后仍能准确反映数据的时间分布和特征
    
    Args:
        record: 录制数据
        play: 播放数据  
        time_range: 时间范围元组 (start_time, end_time)，用于设置x轴范围
    
    Returns:
        go.Figure: Plotly图表对象，包含采样状态信息（如果进行了采样）
    """
    if record is None or play is None:
        logger.warning("DataFrames are not available.")
        return None
    
    # 性能优化：设置数据点阈值，超过该值将进行采样
    MAX_DATA_POINTS = 5000  # 最大渲染数据点数，超过此值将触发采样
    
    offsets = {
        'record': 0.0,
        'play': 0.2,
        # 'pwm': -0.2
    }
    all_bars = []

    # 收集所有数据点
    for df, label in [
        (record, 'record'),
        (play, 'play'),
    ]:
        if df is None:
            continue
        bars = get_bar_segments2(df)

        y_offset = offsets[label]
        for t_on, t_off, key_id, value, index in bars:
            all_bars.append({
                't_on': t_on,
                't_off': t_off,
                'key_id': key_id + y_offset,
                'value': value,
                'label': label,
                'index': index
            })
    
    # 性能优化：如果数据点过多，进行智能采样
    original_count = len(all_bars)
    is_sampled = False
    sampled_count = original_count  # 初始化，如果没有采样则等于原始数量
    
    if original_count > MAX_DATA_POINTS:
        logger.info(f"⚠️ 数据点过多（{original_count}个），进行智能采样以减少到{MAX_DATA_POINTS}个以内")
        all_bars = _smart_sample_bars(all_bars, MAX_DATA_POINTS)
        is_sampled = True
        sampled_count = len(all_bars)
        logger.info(f"✅ 采样完成：{original_count} -> {sampled_count} 个数据点（保留率：{sampled_count/original_count*100:.1f}%）")

    # 归一化力度到0-1
    values = [b['value'] for b in all_bars]
    
    # 检查是否有数据，避免 min() 空序列错误
    if not values:
        logger.warning("⚠️ 筛选后没有数据，返回空图表")
        return None
    
    vmin, vmax = min(values), max(values)
    norm = lambda v: (v - vmin) / (vmax - vmin) if vmax > vmin else 0.5
    cmap = plt.colormaps['tab20b']

    fig = go.Figure()

    for b in all_bars:
        color = 'rgba' + str(tuple(int(255*x) for x in cmap(norm(b['value']))[:3]) + (0.9,))
        fig.add_trace(go.Scatter(
            x=[b['t_on']/10, b['t_off']/10],
            y=[b['key_id'], b['key_id']],
            mode='lines',
            line=dict(color=color, width=3),
            name=b['label'],
            showlegend=False,
            hoverinfo='text',
            text=f'Index: {b["index"]}<br>Key: {int(b["key_id"])}<br>Value: {b["value"]}<br>Label: {b["label"]}<br>Key On: {b["t_on"]/10:.1f}ms<br>Key Off: {b["t_off"]/10:.1f}ms',
            customdata=[[b['t_on']/10, b['t_off']/10, int(b['key_id']), b['value'], b['label'],int(b['index'])]]
        ))

    # 添加色条

    colorbar_trace = go.Scatter(
        x=[None], y=[None],
        mode='markers',
        marker=dict(
            colorscale='Viridis',
            cmin=vmin,
            cmax=vmax,
            color=[vmin, vmax],
            colorbar=dict(
                title='Hammer',
                thickness=20,
                len=0.8
            ),
            showscale=True
        ),
        showlegend=False,
        hoverinfo='none'
    )
    fig.add_trace(colorbar_trace)
    
    # 设置x轴范围
    xaxis_config = {
        'title': 'Time (ms)',
        'showgrid': True,
        'gridcolor': 'lightgray',
        'gridwidth': 1
    }
    
    # 如果提供了时间范围，设置x轴范围
    if time_range and len(time_range) == 2:
        start_time, end_time = time_range
        xaxis_config['range'] = [start_time, end_time]
        logger.info(f"⏰ 设置瀑布图x轴范围: {start_time} - {end_time} (ms)")
    
    # 构建图表标题，包含采样状态提示
    title = 'Piano Key/Pedal Events Waterfall (Bar = KeyOn~KeyOff, Color=Value)'
    if is_sampled:
        title += f'<br><span style="font-size:10px; color:#d69e2e;">⚠️ 性能优化：已智能采样（原始{original_count}个数据点 → 显示{sampled_count}个，保留率{sampled_count/original_count*100:.1f}%）</span>'
    
    fig.update_layout(
        title=title,
        xaxis=xaxis_config,
        yaxis_title='Key ID (1-88: keys, 89-90: pedals)',
        yaxis=dict(
            tickmode='array', 
            tickvals=list(range(1, 91)),
            range=[1, 91]  # 设置y轴范围，确保不显示负数（按键ID从1开始）
        ),
        height=1500,  # 固定高度，与布局中的样式保持一致，避免Tab切换时高度变化
        width=2000,  # 设置一个较大的宽度值，实际宽度由CSS样式控制（100%），确保占满容器
        template='simple_white',
        autosize=False,  # 使用固定高度和宽度，宽度由CSS样式控制（通过布局中的width: 100%）
        margin=dict(l=60, r=60, t=100, b=60),
        showlegend=False,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(size=12)
    )
    
    # 将采样信息附加到figure对象，方便后续使用
    if is_sampled:
        fig._sampling_info = {
            'original_count': original_count,
            'sampled_count': sampled_count,
            'sampling_rate': sampled_count / original_count
        }
    
    return fig

import plotly.graph_objects as go
import numpy as np

def plot_note_comparison_plotly(record_note, play_note, algorithm_name=None, other_algorithm_notes=None):
    """
    使用 Plotly 绘制音符的触后数据和锤子数据对比图（在同一图中）
    
    参数:
    record_note: 录制音轨数据，如果为None则不绘制录制数据
    play_note: 回放音轨数据，如果为None则不绘制回放数据
    algorithm_name: 算法名称（可选），用于在标题中显示
    other_algorithm_notes: 其他算法的播放音符列表，格式为 [(algorithm_name, play_note), ...]
    """
    if other_algorithm_notes is None:
        other_algorithm_notes = []
    
    # 创建图表
    fig = go.Figure()
    
    # 检查并绘制录制触后数据（线条）
    # 注意：
    # - after_touch.index 和 hammers.index 是相对时间（相对于音符开始），单位是 0.1ms
    # - note.offset 是绝对时间偏移，单位是 0.1ms
    # - 实际时间 = (相对时间 + offset) / 10.0，转换为 ms
    # - after_touch.values: 触后压力值（力度传感器读数）
    # - hammers.values: 锤子速度值（MIDI 速度）
    if record_note is not None:
        try:
            if hasattr(record_note, 'after_touch') and record_note.after_touch is not None and not record_note.after_touch.empty:
                # 计算绝对时间：相对时间 + offset，然后转换为 ms
                x_after_touch = (record_note.after_touch.index + record_note.offset) / 10.0
                y_after_touch = record_note.after_touch.values  # 触后压力值
                fig.add_trace(
                    go.Scatter(
                        x=x_after_touch,
                        y=y_after_touch,
                        mode='lines',
                        name='录制触后',
                        line=dict(color='blue', width=3),
                        showlegend=True,
                        legendgroup='record',  # 录制数据分组（触后和锤子一组）
                        hovertemplate='时间: %{x:.2f} ms<br>触后压力: %{y}<extra></extra>'
                    )
                )
            
            # 检查并绘制录制锤子数据（点）
            if hasattr(record_note, 'hammers') and record_note.hammers is not None and not record_note.hammers.empty:
                # 计算绝对时间：相对时间 + offset，然后转换为 ms
                x_hammers = (record_note.hammers.index + record_note.offset) / 10.0
                y_hammers = record_note.hammers.values  # 锤子速度值
                fig.add_trace(
                    go.Scatter(
                        x=x_hammers,
                        y=y_hammers,
                        mode='markers',
                        name='录制锤子',
                        marker=dict(color='blue', size=8, symbol='circle'),
                        showlegend=True,
                        legendgroup='record',  # 录制数据分组（触后和锤子一组）
                        hovertemplate='时间: %{x:.2f} ms<br>锤子速度: %{y}<extra></extra>'
                    )
                )
        except Exception as e:
            logger.warning(f"⚠️ 绘制录制数据时出错: {e}")
    
    # 检查并绘制回放触后数据（线条）
    if play_note is not None:
        try:
            if hasattr(play_note, 'after_touch') and play_note.after_touch is not None and not play_note.after_touch.empty:
                # 计算绝对时间：相对时间 + offset，然后转换为 ms
                x_after_touch = (play_note.after_touch.index + play_note.offset) / 10.0
                y_after_touch = play_note.after_touch.values  # 触后压力值
                play_name = f'回放触后 ({algorithm_name})' if algorithm_name else '回放触后'
                # 当前算法的触后和锤子为一组
                alg_group = f'algorithm_{algorithm_name}' if algorithm_name else 'algorithm_default'
                fig.add_trace(
                    go.Scatter(
                        x=x_after_touch,
                        y=y_after_touch,
                        mode='lines',
                        name=play_name,
                        line=dict(color='red', width=3),
                        showlegend=True,
                        legendgroup=alg_group,  # 当前算法的触后和锤子一组
                        hovertemplate='时间: %{x:.2f} ms<br>触后压力: %{y}<extra></extra>'
                    )
                )
            
            # 检查并绘制回放锤子数据（点）
            if hasattr(play_note, 'hammers') and play_note.hammers is not None and not play_note.hammers.empty:
                # 计算绝对时间：相对时间 + offset，然后转换为 ms
                x_hammers = (play_note.hammers.index + play_note.offset) / 10.0
                y_hammers = play_note.hammers.values  # 锤子速度值
                play_name = f'回放锤子 ({algorithm_name})' if algorithm_name else '回放锤子'
                # 当前算法的触后和锤子为一组
                alg_group = f'algorithm_{algorithm_name}' if algorithm_name else 'algorithm_default'
                fig.add_trace(
                    go.Scatter(
                        x=x_hammers,
                        y=y_hammers,
                        mode='markers',
                        name=play_name,
                        marker=dict(color='red', size=8, symbol='circle'),
                        showlegend=True,
                        legendgroup=alg_group,  # 当前算法的触后和锤子一组
                        hovertemplate='时间: %{x:.2f} ms<br>锤子速度: %{y}<extra></extra>'
                    )
                )
        except Exception as e:
            logger.warning(f"⚠️ 绘制回放数据时出错: {e}")
    
    # 绘制其他算法的播放曲线
    # 为不同算法分配不同颜色
    other_colors = ['green', 'orange', 'purple', 'brown', 'pink', 'gray', 'olive', 'cyan']
    for idx, (other_alg_name, other_play_note) in enumerate(other_algorithm_notes):
        if other_play_note is None:
            continue
        
        color = other_colors[idx % len(other_colors)]
        try:
            # 每个算法的触后和锤子为一组
            other_alg_group = f'algorithm_{other_alg_name}'
            
            # 绘制其他算法的触后数据
            if hasattr(other_play_note, 'after_touch') and other_play_note.after_touch is not None and not other_play_note.after_touch.empty:
                x_after_touch = (other_play_note.after_touch.index + other_play_note.offset) / 10.0
                y_after_touch = other_play_note.after_touch.values
                fig.add_trace(
                    go.Scatter(
                        x=x_after_touch,
                        y=y_after_touch,
                        mode='lines',
                        name=f'回放触后 ({other_alg_name})',
                        line=dict(color=color, width=2, dash='dash'),
                        showlegend=True,
                        legendgroup=other_alg_group,  # 该算法的触后和锤子一组
                        hovertemplate=f'算法: {other_alg_name}<br>时间: %{{x:.2f}} ms<br>触后压力: %{{y}}<extra></extra>'
                    )
                )
            
            # 绘制其他算法的锤子数据
            if hasattr(other_play_note, 'hammers') and other_play_note.hammers is not None and not other_play_note.hammers.empty:
                x_hammers = (other_play_note.hammers.index + other_play_note.offset) / 10.0
                y_hammers = other_play_note.hammers.values
                fig.add_trace(
                    go.Scatter(
                        x=x_hammers,
                        y=y_hammers,
                        mode='markers',
                        name=f'回放锤子 ({other_alg_name})',
                        marker=dict(color=color, size=6, symbol='square'),
                        showlegend=True,
                        legendgroup=other_alg_group,  # 该算法的触后和锤子一组
                        hovertemplate=f'算法: {other_alg_name}<br>时间: %{{x:.2f}} ms<br>锤子速度: %{{y}}<extra></extra>'
                    )
                )
        except Exception as e:
            logger.warning(f"⚠️ 绘制算法 '{other_alg_name}' 的回放数据时出错: {e}")
    
    # 生成标题
    title_parts = []
    if algorithm_name:
        title_parts.append(f"算法: {algorithm_name}")
    if record_note is not None:
        title_parts.append(f"录制音符ID: {record_note.id}")
    if play_note is not None:
        title_parts.append(f"回放音符ID: {play_note.id}")
    
    title = "音符数据对比分析"
    if title_parts:
        title += f" ({', '.join(title_parts)})"
    
    # 如果没有任何数据，添加一个提示信息
    if len(fig.data) == 0:
        fig.add_annotation(
            text="无数据可显示",
            xref="paper", yref="paper",
            x=0.5, y=0.5, xanchor='center', yanchor='middle',
            showarrow=False, font_size=16
        )
    
    # 更新布局
    fig.update_layout(
        title=dict(
            text=title,
            x=0.5,  # 标题居中
            xanchor='center',
            font=dict(size=16)
        ),
        xaxis=dict(
            title=dict(text='时间 (ms)', font=dict(size=14)),
            showgrid=True,
            showline=True,
            linewidth=1,
            linecolor='black',
            mirror=True
        ),
        yaxis=dict(
            title=dict(text='数值（触后压力/锤子速度）', font=dict(size=14)),
            showgrid=True,
            showline=True,
            linewidth=1,
            linecolor='black',
            mirror=True
        ),
        height=600,  # 增加高度（往下扩展）
        width=800,  # 增加宽度（往右扩展）
        template='simple_white',
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=1.40,  # 图注在标题下方（标题在y=1.0，图注在y=1.40，留出空间）
            xanchor="center",
            x=0.5,  # 图注居中，与标题对齐
            traceorder='grouped',  # 按组排序（录制、算法1、算法2...分组）
            tracegroupgap=150,  # 组之间的间距（像素），大幅增大间距让不同算法图注分开
            itemwidth=35,  # 每个图注项的宽度
            font=dict(size=11),  # 图注字体大小
            bgcolor='rgba(255,255,255,0.9)',  # 图注背景色（更不透明）
            bordercolor='gray',
            borderwidth=1.5,  # 边框宽度
            entrywidthmode='fraction',  # 使用分数模式控制图注项宽度
            entrywidth=0.20,  # 每个图注项占用的宽度（分数，大幅增大让文字完整显示）
            groupclick='toggleitem'  # 点击时只切换单个item，而不是整个组
        ),
        hovermode='x unified',  # 统一悬停模式
        margin=dict(l=60, r=40, t=250, b=80)  # 增加右边距和下边距，为图表扩展留出空间
    )
    
    return fig

# 使用示例：
# fig = plot_note_comparison_plotly(record, play, note_index=0)
# fig.show()




if __name__=="__main__":
    pass