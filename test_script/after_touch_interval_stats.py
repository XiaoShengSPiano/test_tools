#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
统计每个 Note 的 after_touch 相邻 key 间隔的平均数，输出到文件，并生成频率分布直方图。

- 数据来源：有效播放数据（SPMIDLoader.get_replay_data()）
- 输出文件：间隔平均数列表（文本）、直方图（PNG）
- 直方图：x 轴为间隔平均数，y 轴为频率（具有该平均数的 note 数量）
"""

import sys
import argparse
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

LOG_DIR = _project_root / "logs"
MEANS_FILE = LOG_DIR / "after_touch_interval_means.txt"
HISTOGRAM_FILE = LOG_DIR / "after_touch_interval_histogram.png"


def get_after_touch_keys(note):
    """获取 note.after_touch 的 index 列表。"""
    if not hasattr(note, "after_touch") or note.after_touch is None or note.after_touch.empty:
        return None
    return note.after_touch.index.tolist()


def mean_interval(keys):
    """计算相邻 key 间隔的平均值。至少需要 2 个 key。"""
    if not keys or len(keys) < 2:
        return None
    intervals = [int(keys[i + 1]) - int(keys[i]) for i in range(len(keys) - 1)]
    return sum(intervals) / len(intervals)


def run(spmid_path: str) -> None:
    from backend.spmid_loader import SPMIDLoader
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import os

    path = Path(spmid_path)
    if not path.is_file():
        print("ERROR: 文件不存在: %s" % spmid_path, file=sys.stderr)
        return

    loader = SPMIDLoader()
    with open(path, "rb") as f:
        data = f.read()
    if not loader.load_spmid_data(data):
        print("ERROR: SPMID 加载失败", file=sys.stderr)
        return

    replay_notes = loader.get_replay_data()
    if not replay_notes:
        print("WARNING: 过滤后播放数据为空", file=sys.stderr)
        return

    # 每个 note 的 (note_index, mean_interval)
    results = []
    for idx, note in enumerate(replay_notes):
        keys = get_after_touch_keys(note)
        mu = mean_interval(keys)
        if mu is not None:
            results.append((idx, mu))

    if not results:
        print("WARNING: 没有符合条件的 note（至少 2 个 after_touch key）", file=sys.stderr)
        return

    os.makedirs(LOG_DIR, exist_ok=True)

    # 1. 输出到文件：每行 note_index, mean_interval
    with open(MEANS_FILE, "w", encoding="utf-8") as f:
        f.write("note_index\tmean_interval\n")
        for idx, mu in results:
            f.write("%s\t%s\n" % (idx, mu))
    print("已写入间隔平均数文件: %s" % MEANS_FILE)

    # 2. Frequency distribution: x = mean interval, y = count (frequency)
    means = [r[1] for r in results]
    fig, ax = plt.subplots()
    # Use explicit bins: cover full range, avoid empty or single-bin when data is concentrated
    n_vals = len(means)
    min_m, max_m = min(means), max(means)
    if min_m == max_m:
        # Single value: one bar
        ax.hist(means, bins=[min_m - 0.5, min_m + 0.5], color="steelblue", edgecolor="white", alpha=0.8)
    else:
        # Bin count: Sturges-like, clamped between 5 and 80
        n_bins = max(5, min(80, int(1 + np.log2(n_vals))))
        bins = np.linspace(min_m, max_m, n_bins + 1)
        ax.hist(means, bins=bins, color="steelblue", edgecolor="white", alpha=0.8)
    ax.set_xlabel("Mean interval")
    ax.set_ylabel("Frequency")
    ax.set_title("After-touch interval mean: frequency distribution")
    fig.tight_layout()
    fig.savefig(HISTOGRAM_FILE, dpi=150)
    plt.close(fig)
    print("已生成直方图: %s" % HISTOGRAM_FILE)


def main():
    parser = argparse.ArgumentParser(
        description="统计每个 note 的 after_touch 间隔平均数，输出到文件并绘制频率分布直方图"
    )
    parser.add_argument("spmid_file", type=str, help="SPMID 文件路径")
    args = parser.parse_args()
    run(args.spmid_file)


if __name__ == "__main__":
    main()
