import pandas as pd
import numpy as np
import dtw
import matplotlib.pyplot as plt
import os
from utils.logger import Logger

import plotly.io as pio
# pio.renderers.default = "browser"

logger = Logger.get_logger()

def offset_stats(df1, df2):
    """    对两个DataFrame中的Hammer事件进行对齐和偏移量统计 """
    key_stats = []
    all_offsets = []

    for key_id in range(1, 89):
        ts1 = df1[(df1['type'] == 'Hammer') & (df1['key_id'] == key_id)]['timestamp'].values
        ts2 = df2[(df2['type'] == 'Hammer') & (df2['key_id'] == key_id)]['timestamp'].values
        if len(ts1) == 0 or len(ts2) == 0:
            continue  # 跳过没有数据的键
        
        alignment = dtw(ts1.reshape(-1, 1),
               ts2.reshape(-1, 1),
               keep_internals=True)  # 现在这个参数有效了

        offsets = [ts2[idx2] - ts1[idx1] for idx1, idx2 in zip(alignment.index1, alignment.index2)]
        all_offsets.extend(offsets)
        key_stats.append({
            'key_id': key_id,
            'count': len(offsets),
            'median': np.median(offsets) if offsets else np.nan,
            'mean': np.mean(offsets) if offsets else np.nan,
            'std': np.std(offsets) if offsets else np.nan
        })

    # 转为DataFrame输出
    df_stats = pd.DataFrame(key_stats)
    # 总体统计
    all_offsets = np.array(all_offsets)
    logger.info(f"录制歌曲的锤子总数: {len(df1[df1['type'] == 'Hammer'])}")
    logger.info(f"回放歌曲的按键总数: {len(df2[df2['type'] == 'Hammer'])}")
    logger.info(f"总共配对数: {len(all_offsets)}")
    logger.info(f"所有按键偏移量中位数: {np.median(all_offsets):.2f} ms")
    logger.info(f"所有按键偏移量均值: {np.mean(all_offsets):.2f} ms")
    logger.info(f"所有按键偏移量标准差: {np.std(all_offsets):.2f} ms")
    return np.median(all_offsets)


def get_bar_segments(df):
    # 只处理Hammer事件
    hammer_df = df[df['type'] == 'Hammer'].copy()
    keyon_df = df[df['type'] == 'KeyOn']
    keyoff_df = df[df['type'] == 'KeyOff']
    bar_segments = []
    for idx, row in hammer_df.iterrows():
        key_id = row['key_id']
        t_hammer = row['timestamp']
        # 找到该key_id下，且时间小于hammer的最近一次KeyOn
        keyon = keyon_df[(keyon_df['key_id'] == key_id) & (keyon_df['timestamp'] <= t_hammer)]
        if keyon.empty:
            continue
        t_on = keyon['timestamp'].max()
        # 找到该key_id下，且时间大于hammer的最近一次KeyOff
        keyoff = keyoff_df[(keyoff_df['key_id'] == key_id) & (keyoff_df['timestamp'] >= t_hammer)]
        if keyoff.empty:
            continue
        t_off = keyoff['timestamp'].min()
        bar_segments.append((t_hammer, t_off, key_id, row['value']))
    return bar_segments



def offset_two_df(df_record, df_play):
    offset_play = offset_stats(df_record, df_play)
    df_play['timestamp'] = df_play['timestamp'] - offset_play  # 修正第二个序列的时间

    return df_record, df_play


def offset_third_df(record, pid, pwm):
    """    对三个 parqute 中的Hammer事件进行对齐和偏移量统计 """
    try:
        df_record = pd.read_parquet(record)
        df_pid = pd.read_parquet(pid)
        offset_pid = offset_stats(df_record, df_pid)
        df_pid['timestamp'] = df_pid['timestamp'] - offset_pid  # 修正第二个序列的时间
        df_pwm = pd.read_parquet(pwm)
        offset_pwm = offset_stats(df_record, df_pwm)
        df_pwm['timestamp'] = df_pwm['timestamp'] - offset_pwm
    except:
        df_record = None
        df_pid = None
        df_pwm = None
    return df_record, df_pid, df_pwm

