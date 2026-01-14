#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查SPMID文件中播放音轨的异常触后数据 (After Touch)

只检查最后一个轨道（播放轨道），查找满足以下条件的Note：
1. after_val中最大值 < 500
2. 或者 after_ts中最后一个值 - after_ts的第一个值小于300

这些数据理论上不会存在，可能表示数据异常。
"""

import sys
from pathlib import Path
import numpy as np
from spmid.spmid_reader import OptimizedSPMidReader

def check_abnormal_after_touch_data(spmid_file_path):
    """检查SPMID文件中播放音轨的异常触后数据"""

    print(f"正在检查SPMID文件播放音轨中的异常触后数据: {spmid_file_path}")
    print("=" * 100)

    try:
        # 读取SPMID文件
        reader = OptimizedSPMidReader(spmid_file_path)

        print(f"✓ 文件包含 {reader.track_count} 个轨道")

        if reader.track_count == 0:
            print("❌ 文件中没有找到任何轨道")
            return

        print(f"🎯 只检查最后一个轨道（播放轨道）")

        # 统计信息
        total_notes = 0
        abnormal_notes = []

        # 只检查最后一个轨道（播放轨道）
        if reader.track_count == 0:
            print("❌ 文件中没有找到任何轨道")
            return

        # 获取最后一个轨道（播放轨道）
        track_idx = reader.track_count - 1
        track_notes = reader.get_track(track_idx)
        track_name = f"轨道{track_idx} (播放轨道)"

        print(f"\n🎵 只检查播放轨道: {track_name}")
        print(f"📊 播放轨道包含: {len(track_notes)} 个Note")

        track_abnormal_count = 0

        # 检查每个Note
        for note_idx, note in enumerate(track_notes):
            total_notes += 1

            # 检查触后数据是否存在
            if note.after_val.size == 0 or note.after_ts.size == 0:
                abnormal_notes.append({
                    'track_idx': track_idx,
                    'track_name': track_name,
                    'note_idx': note_idx,
                    'note_id': note.id,
                    'reason': 'after_touch数据为空',
                    'after_val': note.after_val,
                    'after_ts': note.after_ts
                })
                track_abnormal_count += 1
                continue

            # 检查条件1: after_val中最大值 < 500
            max_after_val = np.max(note.after_val)
            condition1 = max_after_val < 500

            # 检查条件2: after_ts中最后一个值 - after_ts的第一个值小于300
            if note.after_ts.size >= 2:
                time_span = note.after_ts[-1] - note.after_ts[0]
                condition2 = time_span < 300
            else:
                time_span = 0
                condition2 = True  # 只有一个时间点也算异常

            # 如果满足任一条件，记录为异常
            if condition1 or condition2:
                abnormal_notes.append({
                    'track_idx': track_idx,
                    'track_name': track_name,
                    'note_idx': note_idx,
                    'note_id': note.id,
                    'reason': f"{'触后最大值<500' if condition1 else ''}{' & ' if condition1 and condition2 else ''}{f'时间跨度<{300}ms' if condition2 else ''}",
                    'max_after_val': max_after_val,
                    'time_span': time_span,
                    'after_val_size': note.after_val.size,
                    'after_ts_size': note.after_ts.size,
                    'after_val': note.after_val,
                    'after_ts': note.after_ts
                })
                track_abnormal_count += 1

        print(f"📊 播放轨道异常Note统计: {track_abnormal_count} 个")

        # 输出结果
        print(f"\n{'='*100}")
        print("检查结果汇总:")
        print(f"{'='*100}")

        print(f"\n总Note数: {total_notes}")
        print(f"异常Note数: {len(abnormal_notes)}")
        print(".2f")
        if abnormal_notes:
            print("\n🔍 异常Note详细信息:")
            print("-" * 100)

            for i, abnormal_note in enumerate(abnormal_notes[:20], 1):  # 只显示前20个
                print(f"\n异常 {i}:")
                print(f"  轨道: {abnormal_note['track_name']}")
                print(f"  Note索引: {abnormal_note['note_idx']}")
                print(f"  Note ID: {abnormal_note['note_id']}")
                print(f"  异常原因: {abnormal_note['reason']}")

                if 'max_after_val' in abnormal_note:
                    print(f"  触后最大值: {abnormal_note['max_after_val']}")
                if 'time_span' in abnormal_note:
                    print(f"  时间跨度: {abnormal_note['time_span']} ms")
                if 'after_val_size' in abnormal_note:
                    print(f"  触后数据点数: {abnormal_note['after_val_size']}")
                if 'after_ts_size' in abnormal_note:
                    print(f"  时间戳数据点数: {abnormal_note['after_ts_size']}")

                # 显示触后数据（如果数据量不大）
                if 'after_val' in abnormal_note and len(abnormal_note['after_val']) <= 10:
                    print(f"  触后值: {abnormal_note['after_val']}")
                if 'after_ts' in abnormal_note and len(abnormal_note['after_ts']) <= 10:
                    print(f"  时间戳: {abnormal_note['after_ts']}")

            if len(abnormal_notes) > 20:
                print(f"\n... 还有 {len(abnormal_notes) - 20} 个异常Note未显示")

            print(f"\n📈 播放轨道异常统计: {len(abnormal_notes)} 个异常Note")

        else:
            print("\n✅ 未发现任何异常Note！")

    except Exception as e:
        print(f"❌ 处理文件时出错: {e}")
        import traceback
        traceback.print_exc()

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python check_abnormal_hammer_data.py <SPMID文件路径>")
        print("示例: python check_abnormal_hammer_data.py example.spmid")
        sys.exit(1)

    spmid_file_path = sys.argv[1]

    if not Path(spmid_file_path).exists():
        print(f"❌ 文件不存在: {spmid_file_path}")
        sys.exit(1)

    check_abnormal_after_touch_data(spmid_file_path)

if __name__ == "__main__":
    main()