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
    Args:
        record: 录制数据
        play: 播放数据  
        time_range: 时间范围元组 (start_time, end_time)，用于设置x轴范围
    """
    if record is None or play is None:
        logger.warning("DataFrames are not available.")
        return None
    offsets = {
        'record': 0.0,
        'play': 0.2,
        # 'pwm': -0.2
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
    
    fig.update_layout(
        title='Piano Key/Pedal Events Waterfall (Bar = KeyOn~KeyOff, Color=Value)',
        xaxis=xaxis_config,
        yaxis_title='Key ID (1-88: keys, 89-90: pedals)',
        yaxis=dict(tickmode='array', tickvals=list(range(1, 91))),
        height=None,
        width=None,
        template='simple_white',
        autosize=True,
        margin=dict(l=60, r=60, t=100, b=60),
        showlegend=False,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(size=12)
    )
    return fig

import plotly.graph_objects as go
import numpy as np

def plot_note_comparison_plotly(record_note, play_note):
    """
    使用 Plotly 绘制音符的触后数据和锤子数据对比图（在同一图中）
    
    参数:
    record_note: 录制音轨数据，如果为None则不绘制录制数据
    play_note: 回放音轨数据，如果为None则不绘制回放数据
    """
    
    # 创建图表
    fig = go.Figure()
    
    # 检查并绘制录制触后数据（线条）
    if record_note is not None and not record_note.after_touch.empty:
        fig.add_trace(
            go.Scatter(
                x=record_note.after_touch.index,
                y=record_note.after_touch.values,
                mode='lines',
                name='录制触后',
                line=dict(color='blue', width=3),
                showlegend=True
            )
        )
    
    # 检查并绘制回放触后数据（线条）
    if play_note is not None and not play_note.after_touch.empty:
        fig.add_trace(
            go.Scatter(
                x=play_note.after_touch.index,
                y=play_note.after_touch.values,
                mode='lines',
                name='回放触后',
                line=dict(color='red', width=3),
                showlegend=True
            )
        )
    
    # 检查并绘制录制锤子数据（点）
    if record_note is not None and not record_note.hammers.empty:
        fig.add_trace(
            go.Scatter(
                x=record_note.hammers.index,
                y=record_note.hammers.values,
                mode='markers',
                name='录制锤子',
                marker=dict(color='blue', size=8, symbol='circle'),
                showlegend=True
            )
        )
    
    # 检查并绘制回放锤子数据（点）
    if play_note is not None and not play_note.hammers.empty:
        fig.add_trace(
            go.Scatter(
                x=play_note.hammers.index,
                y=play_note.hammers.values,
                mode='markers',
                name='回放锤子',
                marker=dict(color='red', size=8, symbol='circle'),
                showlegend=True
            )
        )
    
    # 生成标题
    title_parts = []
    if record_note is not None:
        title_parts.append(f"录制音符ID: {record_note.id}")
    if play_note is not None:
        title_parts.append(f"回放音符ID: {play_note.id}")
    
    title = "音符数据对比分析"
    if title_parts:
        title += f" ({', '.join(title_parts)})"
    
    # 更新布局
    fig.update_layout(
        title=title,
        xaxis_title='时间 (ms)',
        yaxis_title='数值',
        height=500,
        width=800,
        template='simple_white',
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        hovermode='x unified'  # 统一悬停模式
    )
    
    return fig

# 使用示例：
# fig = plot_note_comparison_plotly(record, play, note_index=0)
# fig.show()




if __name__=="__main__":
    pass