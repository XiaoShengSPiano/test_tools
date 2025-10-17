
import pandas as pd
import matplotlib.pyplot as plt
from backend.hammer_analysis import get_bar_segments
from utils.logger import Logger

import plotly.graph_objects as go
from plotly.subplots import make_subplots

logger = Logger.get_logger()


def plot_bar_plotly(df_record, df_play):
    # df_record = df_record
    # df_play = df_play

    if df_record is None or df_play is None:
        logger.warning("DataFrames are not available.")
        return None
    
    # 检测是否为单个按键筛选（通过检查键位数量）
    record_keys = set(df_record['key_id'].unique()) if not df_record.empty else set()
    play_keys = set(df_play['key_id'].unique()) if not df_play.empty else set()
    all_keys = record_keys.union(play_keys)
    
    # 如果是单个按键或少量按键，使用更小的偏移量便于对比
    if len(all_keys) <= 3:
        offsets = {
            'record': -0.02,  # 录制数据稍微向下偏移
            'play': 0.02,     # 播放数据稍微向上偏移
        }
    else:
        # 多个按键时使用稍大的偏移量
        offsets = {
            'record': -0.05,  # 录制数据稍微向下偏移
            'play': 0.05,     # 播放数据稍微向上偏移
        }

    all_bars = []
    for df, label in [
        (df_record, 'record'),
        (df_play, 'play'),
        # (df_pwm, 'pwm')
    ]:
        if df is None:
            continue
        bars = get_bar_segments(df)
        y_offset = offsets[label]
        for t_on, t_off, key_id, value in bars:
            all_bars.append({
                't_on': t_on,
                't_off': t_off,
                'key_id': key_id + y_offset,
                'value': value,
                'label': label
            })

    # 归一化力度到0-1
    values = [b['value'] for b in all_bars]
    vmin, vmax = min(values), max(values)
    norm = lambda v: (v - vmin) / (vmax - vmin) if vmax > vmin else 0.5

    # 选用plotly自带的colormap
    from matplotlib import cm
    cmap = cm.get_cmap('tab20b')

    fig = go.Figure()

    # 为录制和播放数据使用不同的颜色方案
    record_color_base = (0, 100, 200)  # 蓝色系
    play_color_base = (200, 50, 50)    # 红色系
    
    for b in all_bars:
        # 根据数据类型选择基础颜色
        if b['label'] == 'record':
            base_color = record_color_base
            line_style = 'solid'
        else:  # play
            base_color = play_color_base
            line_style = 'dash'
        
        # 根据力度值调整颜色透明度
        alpha = 0.3 + 0.7 * norm(b['value'])  # 透明度从0.3到1.0
        color = f'rgba({base_color[0]}, {base_color[1]}, {base_color[2]}, {alpha})'
        
        fig.add_trace(go.Scatter(
            x=[b['t_on'], b['t_off']],
            y=[b['key_id'], b['key_id']],
            mode='lines',
            line=dict(color=color, width=4, dash=line_style),
            name=b['label'],
            showlegend=True,
            hoverinfo='text',
            text=f'键位: {int(b["key_id"])}<br>力度: {b["value"]}<br>类型: {"录制" if b["label"] == "record" else "播放"}<br>时间: {b["t_on"]:.1f} - {b["t_off"]:.1f}ms',
            customdata=[[b['t_on'], b['t_off'], int(b['key_id']), b['value'], b['label']]]
        ))

    # 添加色条
    import numpy as np
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

    # 动态生成标题
    key_count = len(all_keys)
    if key_count <= 3:
        title = f'钢琴按键对比分析 - 选中 {key_count} 个键位 (蓝色实线=录制, 红色虚线=播放)'
    else:
        title = f'钢琴按键事件瀑布图 - 共 {key_count} 个键位 (蓝色实线=录制, 红色虚线=播放)'
    
    fig.update_layout(
        title=title,
        xaxis_title='时间 (ms)',
        yaxis_title='键位ID (1-88: 钢琴键, 89-90: 踏板)',
        yaxis=dict(tickmode='array', tickvals=list(range(1, 91))),
        height=None,
        width=None,
        template='plotly_white',
        autosize=True,
        margin=dict(l=60, r=60, t=120, b=60),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor="rgba(255,255,255,0.8)"
        ),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(size=12)
    )
    # fig.show()
    return fig


def get_sample_rate_plot_plotly(keyOn_t, keyOff_t, keyId, df):
    """使用plotly绘制力度曲线，自动查找最匹配的keyon/keyoff时间戳"""
    df_key = df[df['key_id'] == keyId]
    
    # 查找最匹配的keyon和keyoff时间戳（粗匹配）
    best_keyon, best_keyoff = find_best_matching_timestamps_coarse(df_key, keyOn_t, keyOff_t)
    
    if best_keyon is None or best_keyoff is None:
        # 如果没有找到匹配的时间戳，创建一个空的图形
        fig = go.Figure()
        fig.add_annotation(
            text=f"No matching data found for Key ID: {keyId}",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=16)
        )
        fig.update_layout(
            title=f'Key ID: {keyId} - No Matching Data',
            xaxis_title='Time (100us)',
            yaxis_title='Value',
            height=400
        )
        return fig
    
    # 使用找到的最佳时间戳来筛选数据
    df_at = df_key[(df_key['type'] == 'AfterTouch') & 
                   (df_key['timestamp'] >= best_keyon) & 
                   (df_key['timestamp'] <= best_keyoff)]
    df_hammer = df_key[(df_key['type'] == 'Hammer') & 
                       (df_key['timestamp'] >= best_keyon) & 
                       (df_key['timestamp'] <= best_keyoff)]
    
    if df_at.empty and df_hammer.empty:
        # 如果没有数据，创建一个空的图形
        fig = go.Figure()
        fig.add_annotation(
            text=f"No AfterTouch/Hammer data for Key ID: {keyId}",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=16)
        )
        fig.update_layout(
            title=f'Key ID: {keyId} - No Data Available',
            xaxis_title='Time (100us)',
            yaxis_title='Value',
            height=400
        )
        return fig
    
    fig = go.Figure()
    
    # 绘制AfterTouch数据
    if not df_at.empty:
        fig.add_trace(go.Scatter(
            x=df_at['timestamp'] - best_keyon,
            y=df_at['value'],
            mode='lines',
            name='AfterTouch',
            line=dict(color='blue', width=2)
        ))
    
    # 绘制Hammer数据点
    if not df_hammer.empty:
        fig.add_trace(go.Scatter(
            x=df_hammer['timestamp'] - best_keyon,
            y=df_hammer['value'],
            mode='markers',
            name='Hammer',
            marker=dict(color='red', size=8)
        ))
    
    # 添加KeyOn/KeyOff垂直线
    fig.add_vline(x=0, line_dash="dash", line_color="green", annotation_text="KeyOn")
    fig.add_vline(x=best_keyoff - best_keyon, line_dash="dash", line_color="green", annotation_text="KeyOff")
    
    # 添加时间戳信息到标题
    time_diff = abs(best_keyon - keyOn_t) + abs(best_keyoff - keyOff_t)
    title_suffix = f" (粗匹配误差: {time_diff:.2f}ms)" if time_diff > 0 else " (精确匹配)"
    
    fig.update_layout(
        title=f'Key ID: {keyId} - Force Curve (KeyOn: {best_keyon:.2f}, KeyOff: {best_keyoff:.2f}){title_suffix}',
        xaxis_title='Time (100us)',
        yaxis_title='Value',
        height=400,
        template='simple_white'
    )
    
    return fig


def get_sample_rate_plot_plotly_original(keyOn_t, keyOff_t, keyId, df):
    """使用plotly绘制力度曲线（原算法）"""
    df_key = df[df['key_id'] == keyId]
    df_at = df_key[(df_key['type'] == 'AfterTouch') & (df_key['timestamp'] >= keyOn_t) & (df_key['timestamp'] <= keyOff_t)]
    df_hammer = df_key[(df_key['type'] == 'Hammer') & (df_key['timestamp'] >= keyOn_t) & (df_key['timestamp'] <= keyOff_t)]
    
    if df_at.empty:
        # 如果没有AfterTouch数据，创建一个空的图形
        fig = go.Figure()
        fig.add_annotation(
            text=f"No AfterTouch data for Key ID: {keyId}",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=16)
        )
        fig.update_layout(
            title=f'Key ID: {keyId} - No Data Available',
            xaxis_title='Time (100us)',
            yaxis_title='Value',
            height=400
        )
        return fig
    
    fig = go.Figure()
    
    # 绘制AfterTouch数据
    fig.add_trace(go.Scatter(
        x=df_at['timestamp'] - keyOn_t,
        y=df_at['value'],
        mode='lines',
        name='AfterTouch',
        line=dict(color='blue', width=2)
    ))
    
    # 绘制Hammer数据点
    fig.add_trace(go.Scatter(
        x=df_hammer['timestamp'] - keyOn_t,
        y=df_hammer['value'],
        mode='markers',
        name='Hammer',
        marker=dict(color='red', size=8)
    ))
    
    # 添加KeyOn/KeyOff垂直线
    fig.add_vline(x=0, line_dash="dash", line_color="green", annotation_text="KeyOn")
    fig.add_vline(x=keyOff_t - keyOn_t, line_dash="dash", line_color="green", annotation_text="KeyOff")
    
    fig.update_layout(
        title=f'Key ID: {keyId} - Force Curve (KeyOn: {keyOn_t:.2f}, KeyOff: {keyOff_t:.2f})',
        xaxis_title='Time (100us)',
        yaxis_title='Value',
        height=400,
        template='simple_white'
    )
    
    return fig


def get_sample_rate_plot_plotly_combined(keyOn_t, keyOff_t, keyId, df_record, df_play):
    """
    使用plotly绘制两个DataFrame的力度曲线对比图
    
    Args:
        keyOn_t: 目标keyon时间戳
        keyOff_t: 目标keyoff时间戳
        keyId: 键位ID
        df_record: 录制数据DataFrame
        df_play: 回放数据DataFrame
    
    Returns:
        plotly.graph_objects.Figure: 合并的力度曲线图
    """
    # 获取两个DataFrame中对应key_id的数据
    df_record_key = df_record[df_record['key_id'] == keyId]
    df_play_key = df_play[df_play['key_id'] == keyId]
    
    # 查找最匹配的时间戳（粗匹配）
    best_record_keyon, best_record_keyoff = find_best_matching_timestamps_coarse(df_record_key, keyOn_t, keyOff_t)
    best_play_keyon, best_play_keyoff = find_best_matching_timestamps_coarse(df_play_key, keyOn_t, keyOff_t)
    
    # 创建图形
    fig = go.Figure()
    
    # 处理录制数据
    if best_record_keyon is not None and best_record_keyoff is not None:
        # 筛选录制数据
        df_record_at = df_record_key[(df_record_key['type'] == 'AfterTouch') & 
                                    (df_record_key['timestamp'] >= best_record_keyon) & 
                                    (df_record_key['timestamp'] <= best_record_keyoff)]
        df_record_hammer = df_record_key[(df_record_key['type'] == 'Hammer') & 
                                        (df_record_key['timestamp'] >= best_record_keyon) & 
                                        (df_record_key['timestamp'] <= best_record_keyoff)]
        
        # 绘制录制数据的AfterTouch
        if not df_record_at.empty:
            fig.add_trace(go.Scatter(
                x=df_record_at['timestamp'] - best_record_keyon,
                y=df_record_at['value'],
                mode='lines',
                name='录制-AfterTouch',
                line=dict(color='blue', width=2),
                opacity=0.8
            ))
        
        # 绘制录制数据的Hammer
        if not df_record_hammer.empty:
            fig.add_trace(go.Scatter(
                x=df_record_hammer['timestamp'] - best_record_keyon,
                y=df_record_hammer['value'],
                mode='markers',
                name='录制-Hammer',
                marker=dict(color='blue', size=8, symbol='circle'),
                opacity=0.8
            ))
    
    # 处理回放数据
    if best_play_keyon is not None and best_play_keyoff is not None:
        # 筛选回放数据
        df_play_at = df_play_key[(df_play_key['type'] == 'AfterTouch') & 
                                (df_play_key['timestamp'] >= best_play_keyon) & 
                                (df_play_key['timestamp'] <= best_play_keyoff)]
        df_play_hammer = df_play_key[(df_play_key['type'] == 'Hammer') & 
                                    (df_play_key['timestamp'] >= best_play_keyon) & 
                                    (df_play_key['timestamp'] <= best_play_keyoff)]
        
        # 绘制回放数据的AfterTouch
        if not df_play_at.empty:
            fig.add_trace(go.Scatter(
                x=df_play_at['timestamp'] - best_play_keyon,
                y=df_play_at['value'],
                mode='lines',
                name='回放-AfterTouch',
                line=dict(color='red', width=2),
                opacity=0.8
            ))
        
        # 绘制回放数据的Hammer
        if not df_play_hammer.empty:
            fig.add_trace(go.Scatter(
                x=df_play_hammer['timestamp'] - best_play_keyon,
                y=df_play_hammer['value'],
                mode='markers',
                name='回放-Hammer',
                marker=dict(color='red', size=8, symbol='diamond'),
                opacity=0.8
            ))
    
    # 检查是否有数据
    if len(fig.data) == 0:
        fig.add_annotation(
            text=f"No data found for Key ID: {keyId}",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=16)
        )
        fig.update_layout(
            title=f'Key ID: {keyId} - No Data Available',
            xaxis_title='Time (100us)',
            yaxis_title='Value',
            height=400
        )
        return fig
    
    # 添加KeyOn/KeyOff垂直线（使用录制数据的时间作为基准）
    if best_record_keyon is not None:
        fig.add_vline(x=0, line_dash="dash", line_color="green", annotation_text="KeyOn")
        if best_record_keyoff is not None:
            fig.add_vline(x=best_record_keyoff - best_record_keyon, line_dash="dash", line_color="green", annotation_text="KeyOff")
    
    # 计算匹配误差信息
    record_error = 0
    play_error = 0
    if best_record_keyon is not None:
        record_error = abs(best_record_keyon - keyOn_t) + abs(best_record_keyoff - keyOff_t)
    if best_play_keyon is not None:
        play_error = abs(best_play_keyon - keyOn_t) + abs(best_play_keyoff - keyOff_t)
    
    # 更新布局
    title_parts = [f'Key ID: {keyId} - 力度曲线对比']
    if best_record_keyon is not None:
        title_parts.append(f'录制(误差:{record_error:.2f}ms)')
    if best_play_keyon is not None:
        title_parts.append(f'回放(误差:{play_error:.2f}ms)')
    
    fig.update_layout(
        title=' | '.join(title_parts),
        xaxis_title='Time (100us)',
        yaxis_title='Value',
        height=400,
        template='simple_white',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        hovermode='x unified'
    )
    
    return fig


def find_best_matching_timestamps_coarse(df_key, target_keyon, target_keyoff):
    """
    在DataFrame中查找最匹配的keyon和keyoff时间戳（粗匹配算法）
    
    Args:
        df_key: 包含特定key_id数据的DataFrame
        target_keyon: 目标keyon时间戳
        target_keyoff: 目标keyoff时间戳
    
    Returns:
        tuple: (best_keyon, best_keyoff) 最匹配的时间戳对
    """
    # 获取所有KeyOn和KeyOff事件
    keyon_events = df_key[df_key['type'] == 'KeyOn']['timestamp'].values
    keyoff_events = df_key[df_key['type'] == 'KeyOff']['timestamp'].values
    
    if len(keyon_events) == 0 or len(keyoff_events) == 0:
        return None, None
    
    best_keyon = None
    best_keyoff = None
    min_total_error = float('inf')
    
    # 计算目标持续时间
    target_duration = target_keyoff - target_keyon
    
    # 粗匹配：只考虑时间戳误差，不考虑持续时间
    for keyon in keyon_events:
        for keyoff in keyoff_events:
            # 确保keyoff在keyon之后
            if keyoff > keyon:
                # 只计算时间戳误差（粗匹配）
                keyon_error = abs(keyon - target_keyon)
                keyoff_error = abs(keyoff - target_keyoff)
                total_error = keyon_error + keyoff_error
                
                # 如果这个组合的误差更小，更新最佳匹配
                if total_error < min_total_error:
                    min_total_error = total_error
                    best_keyon = keyon
                    best_keyoff = keyoff
    
    # 粗匹配的误差阈值更宽松
    max_allowed_error = max(2000, target_duration * 1.0)  # 至少2000ms或持续时间的100%
    
    # 如果找到的误差太大，认为没有找到匹配
    if min_total_error > max_allowed_error:
        return None, None
    
    return best_keyon, best_keyoff


def find_best_matching_timestamps(df_key, target_keyon, target_keyoff):
    """
    在DataFrame中查找最匹配的keyon和keyoff时间戳（精确匹配算法）
    
    Args:
        df_key: 包含特定key_id数据的DataFrame
        target_keyon: 目标keyon时间戳
        target_keyoff: 目标keyoff时间戳
    
    Returns:
        tuple: (best_keyon, best_keyoff) 最匹配的时间戳对
    """
    # 获取所有KeyOn和KeyOff事件
    keyon_events = df_key[df_key['type'] == 'KeyOn']['timestamp'].values
    keyoff_events = df_key[df_key['type'] == 'KeyOff']['timestamp'].values
    
    if len(keyon_events) == 0 or len(keyoff_events) == 0:
        return None, None
    
    best_keyon = None
    best_keyoff = None
    min_total_error = float('inf')
    
    # 计算目标持续时间
    target_duration = target_keyoff - target_keyon
    
    # 精确匹配：综合考虑时间戳误差和持续时间误差
    for keyon in keyon_events:
        for keyoff in keyoff_events:
            # 确保keyoff在keyon之后
            if keyoff > keyon:
                # 计算与目标时间戳的误差
                keyon_error = abs(keyon - target_keyon)
                keyoff_error = abs(keyoff - target_keyoff)
                
                # 计算持续时间的误差
                duration = keyoff - keyon
                duration_error = abs(duration - target_duration)
                
                # 综合误差计算（给持续时间误差更高的权重）
                total_error = keyon_error + keyoff_error + duration_error * 2
                
                # 如果这个组合的误差更小，更新最佳匹配
                if total_error < min_total_error:
                    min_total_error = total_error
                    best_keyon = keyon
                    best_keyoff = keyoff
    
    # 精确匹配的误差阈值更严格
    max_allowed_error = max(500, target_duration * 0.3)  # 至少500ms或持续时间的30%
    
    # 如果找到的误差太大，认为没有找到匹配
    if min_total_error > max_allowed_error:
        return None, None
    
    return best_keyon, best_keyoff


def debug_matching_process(df_key, target_keyon, target_keyoff, match_type="coarse"):
    """
    调试匹配过程，显示所有可能的匹配选项
    
    Args:
        df_key: 包含特定key_id数据的DataFrame
        target_keyon: 目标keyon时间戳
        target_keyoff: 目标keyoff时间戳
        match_type: 匹配类型 ("coarse" 或 "precise")
    """
    keyon_events = df_key[df_key['type'] == 'KeyOn']['timestamp'].values
    keyoff_events = df_key[df_key['type'] == 'KeyOff']['timestamp'].values
    
    logger.debug(f"目标时间戳: KeyOn={target_keyon:.2f}, KeyOff={target_keyoff:.2f}")
    logger.debug(f"匹配类型: {match_type}")
    logger.debug(f"可用KeyOn事件: {len(keyon_events)}个")
    logger.debug(f"可用KeyOff事件: {len(keyoff_events)}个")
    
    if len(keyon_events) > 0:
        logger.debug(f"KeyOn事件时间戳: {keyon_events[:5]}...")  # 只显示前5个
    if len(keyoff_events) > 0:
        logger.debug(f"KeyOff事件时间戳: {keyoff_events[:5]}...")  # 只显示前5个
    
    # 根据匹配类型选择算法
    if match_type == "coarse":
        best_keyon, best_keyoff = find_best_matching_timestamps_coarse(df_key, target_keyon, target_keyoff)
        logger.debug("使用粗匹配算法")
    else:
        best_keyon, best_keyoff = find_best_matching_timestamps(df_key, target_keyon, target_keyoff)
        logger.debug("使用精确匹配算法")
    
    if best_keyon is not None:
        logger.debug(f"最佳匹配: KeyOn={best_keyon:.2f}, KeyOff={best_keyoff:.2f}")
        logger.debug(f"误差: KeyOn误差={abs(best_keyon - target_keyon):.2f}, KeyOff误差={abs(best_keyoff - target_keyoff):.2f}")
        logger.debug(f"总误差: {abs(best_keyon - target_keyon) + abs(best_keyoff - target_keyoff):.2f}")
    else:
        logger.debug("未找到匹配的时间戳")


def get_sample_rate_plot(keyOn_t, keyOff_t,keyId,df):
 # 取区间内的AfterTouch事件
    # df = pd.read_parquet(os.path.join('parquet', row['filename']))
    df_key = df[df['key_id'] == keyId]
    df_at = df_key[(df_key['type'] == 'AfterTouch') & (df_key['timestamp'] >= keyOn_t) & (df_key['timestamp'] <= keyOff_t)]
    df_hammer = df_key[(df_key['type'] == 'Hammer') & (df_key['timestamp'] >= keyOn_t) & (df_key['timestamp'] <= keyOff_t)]
    if df_at.empty:
        logger.warning(f"No AfterTouch data for Key ID: {keyId} in file data")
        # continue
        return
    plt.figure(figsize=(10, 5))
    plt.plot(df_at['timestamp'] - keyOn_t, df_at['value'], label='AfterTouch', color='blue')
    plt.scatter(df_hammer['timestamp'] - keyOn_t, df_hammer['value'], color='red', label='Hammer')
    plt.vlines([0, keyOff_t - keyOn_t], ymin=0, ymax=1024, color='green', linestyle='--', label='KeyOn/KeyOff')
    # plt.title(f"file_name:{row['filename']} Key ID: {key_id}, On: {t_on}, Off: {t_off},\n mean:{row['mean']}, std: {row['std']}, min:{row['min']}, max:{row['max']}", fontdict={'fontsize': 10, 'font':'SimSun'})
    plt.xlabel('Time (100us)')
    plt.legend()
    plt.tight_layout()
    # plt.savefig(os.path.join(folder, f"{row['filename']}_{key_id}_{t_on}.png"), dpi=300)
    plt.show()


def get_clicked_data(clickData, df_record, df_play):
    """从点击事件中提取数据"""
    if not clickData or 'points' not in clickData:
        return None, None, None, None, None
    
    point = clickData['points'][0]
    customdata = point.get('customdata', [])
    
    if len(customdata) >= 5:
        t_on = customdata[0]
        t_off = customdata[1]
        key_id = customdata[2]
        value = customdata[3]
        label = customdata[4]
        
        # 根据label选择对应的DataFrame
        if label == 'record':
            df = df_record
        elif label == 'play':
            df = df_play
        else:
            df = None
            
        return t_on, t_off, key_id, value, df
    
    return None, None, None, None, None

