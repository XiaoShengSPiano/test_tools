import pandas as pd
import numpy as np
import dtw
import matplotlib.pyplot as plt
import os
from utils.logger import Logger

import plotly.io as pio
# pio.renderers.default = "browser"

logger = Logger.get_logger()

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







