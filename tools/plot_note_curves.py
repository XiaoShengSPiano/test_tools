#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
可视化单个音符的 after_touch 与 hammers 曲线：
- after_touch：时间戳(0.1ms) vs 按键深度
- hammers：时间戳(0.1ms) vs 锤速

使用方法：
python tools/plot_note_curves.py --file your_file.spmid --track 0 --index 0
或按键ID查找：
python tools/plot_note_curves.py --file your_file.spmid --track 0 --key-id 60

可选择保存图片：
python tools/plot_note_curves.py --file your_file.spmid --index 0 --save out.png
"""

import argparse
import sys
import os
from typing import Optional

import matplotlib.pyplot as plt

# 确保可从任意工作目录运行：将项目根目录加入 sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from spmid.spmid_reader import SPMidReader, Note


def find_note_by_key_id(notes, key_id: int) -> Optional[int]:
    for i, n in enumerate(notes):
        if getattr(n, 'id', None) == key_id:
            return i
    return None


def plot_note_series(note: Note, title_prefix: str = "") -> plt.Figure:
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)

    # x 轴统一转为 ms 显示（内部单位为 0.1ms）
    at_x_ms = [t / 10.0 for t in note.after_touch.index.tolist()]
    at_y = note.after_touch.values.tolist()

    hm_x_ms = [t / 10.0 for t in note.hammers.index.tolist()]
    hm_y = note.hammers.values.tolist()

    # after_touch curve
    axes[0].plot(at_x_ms, at_y, color='tab:blue', linewidth=1.5)
    axes[0].set_ylabel('After Touch Depth')
    axes[0].set_title(f"{title_prefix}after_touch: Time(ms) vs Key Depth")
    axes[0].grid(True, linestyle='--', alpha=0.4)

    # hammers curve
    axes[1].plot(hm_x_ms, hm_y, color='tab:orange', linewidth=1.5)
    axes[1].set_xlabel('Time (ms)')
    axes[1].set_ylabel('Hammer Velocity')
    axes[1].set_title(f"{title_prefix}hammers: Time(ms) vs Hammer Velocity")
    axes[1].grid(True, linestyle='--', alpha=0.4)

    plt.tight_layout()
    return fig


def main():
    parser = argparse.ArgumentParser(description='Visualize after_touch and hammers curves for a single note')
    parser.add_argument('--file', required=True, help='SPMID file path')
    parser.add_argument('--track', type=int, default=0, help='Track index (default: 0)')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--index', type=int, help='Note index')
    group.add_argument('--key-id', type=int, help='Key ID (e.g., 60)')
    parser.add_argument('--save', help='Save image to specified path (e.g., out.png)')
    args = parser.parse_args()

    try:
        reader = SPMidReader.from_file(args.file, verbose=False)
        notes = reader.get_track(args.track)
    except Exception as e:
        print(f"Failed to read file: {e}")
        sys.exit(1)

    note_idx: Optional[int] = args.index
    if note_idx is None and args.key_id is not None:
        note_idx = find_note_by_key_id(notes, args.key_id)
        if note_idx is None:
            print(f"Note with KeyID={args.key_id} not found")
            sys.exit(2)

    if note_idx is None or note_idx < 0 or note_idx >= len(notes):
        print(f"Note index out of range: {note_idx} (total {len(notes)} notes)")
        sys.exit(3)

    note = notes[note_idx]
    title_prefix = f"Track {args.track}, Index {note_idx}, KeyID {getattr(note, 'id', 'N/A')}: "
    fig = plot_note_series(note, title_prefix)

    if args.save:
        fig.savefig(args.save, dpi=150)
        print(f"Saved: {args.save}")
    else:
        plt.show()


if __name__ == '__main__':
    main()


