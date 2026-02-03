#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
完整输出SPMID文件中的所有数据
包括所有轨道的所有OptimizedNote的详细信息
"""

import sys
import os
from spmid.spmid_reader import OptimizedSPMidReader

def dump_spmid_data(spmid_file: str, output_file: str = None):
    """
    完整输出SPMID文件的所有数据
    
    Args:
        spmid_file: SPMID文件路径
        output_file: 输出文件路径（默认为输入文件名_full_dump.txt）
    """
    if output_file is None:
        output_file = f"{os.path.splitext(spmid_file)[0]}_full_dump.txt"
    
    print(f"正在读取SPMID文件: {spmid_file}")
    
    try:
        reader = OptimizedSPMidReader(spmid_file)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("=" * 100 + "\n")
            f.write(f"SPMID文件完整数据输出: {spmid_file}\n")
            f.write("=" * 100 + "\n\n")
            
            # 文件级别统计
            f.write(f"轨道数量: {len(reader.tracks)}\n")
            for track_idx, track in enumerate(reader.tracks):
                track_name = "录制轨道" if track_idx == 0 else "播放轨道" if track_idx == 1 else f"轨道{track_idx}"
                f.write(f"  {track_name}: {len(track)} 个音符\n")
            f.write("\n")
            
            # 遍历每个轨道
            for track_idx, track in enumerate(reader.tracks):
                track_name = "录制轨道 (Record)" if track_idx == 0 else "播放轨道 (Replay)" if track_idx == 1 else f"轨道 {track_idx}"
                
                f.write("\n" + "=" * 100 + "\n")
                f.write(f"{track_name} - 共 {len(track)} 个音符\n")
                f.write("=" * 100 + "\n\n")
                
                # 统计信息
                has_hammer = sum(1 for note in track if note.hammers_val.size > 0)
                no_hammer = len(track) - has_hammer
                has_after = sum(1 for note in track if note.after_val.size > 0)
                
                f.write(f"统计信息:\n")
                f.write(f"  有hammer数据: {has_hammer}/{len(track)} ({has_hammer/len(track)*100:.1f}%)\n")
                f.write(f"  无hammer数据: {no_hammer}/{len(track)} ({no_hammer/len(track)*100:.1f}%)\n")
                f.write(f"  有after touch数据: {has_after}/{len(track)} ({has_after/len(track)*100:.1f}%)\n")
                
                if has_hammer > 0:
                    first_zero = sum(1 for note in track if note.hammers_val.size > 0 and note.hammers_val[0] == 0)
                    first_nonzero = has_hammer - first_zero
                    f.write(f"  第一个hammer值为0: {first_zero}/{has_hammer}\n")
                    f.write(f"  第一个hammer值非0: {first_nonzero}/{has_hammer}\n")
                
                f.write("\n")
                
                # 详细列出每个音符
                for note_idx, note in enumerate(track):
                    f.write(f"\n{'─' * 100}\n")
                    f.write(f"[{track_name} - 音符 {note_idx}]\n")
                    f.write(f"{'─' * 100}\n")
                    
                    # 基本信息
                    f.write(f"ID:       {note.id}\n")
                    f.write(f"Offset:   {note.offset}\n")
                    f.write(f"Finger:   {note.finger}\n")
                    f.write(f"Velocity: {note.velocity}\n")
                    f.write(f"UUID:     {note.uuid}\n")
                    
                    # Hammer数据
                    f.write(f"\nHammer数据:\n")
                    if note.hammers_val.size > 0:
                        f.write(f"  数据点数: {note.hammers_val.size}\n")
                        f.write(f"  第一个hammer值: {note.hammers_val[0]}\n")
                        f.write(f"  所有hammer值: {note.hammers_val.tolist()}\n")
                        f.write(f"  时间戳: {note.hammers_ts.tolist()}\n")
                        
                        # 详细列出每个hammer数据点
                        f.write(f"  详细数据:\n")
                        for i, (ts, val) in enumerate(zip(note.hammers_ts, note.hammers_val)):
                            f.write(f"    [{i}] 时间={ts:6d} ms, 值={val:3d}")
                            if val == 0:
                                f.write(" <-- 零值")
                            f.write("\n")
                        
                        # 统计
                        zero_count = sum(1 for v in note.hammers_val if v == 0)
                        nonzero_count = note.hammers_val.size - zero_count
                        f.write(f"  零值数量: {zero_count}\n")
                        f.write(f"  非零值数量: {nonzero_count}\n")
                        if note.hammers_val.size > 0:
                            f.write(f"  最小值: {note.hammers_val.min()}\n")
                            f.write(f"  最大值: {note.hammers_val.max()}\n")
                            f.write(f"  平均值: {note.hammers_val.mean():.2f}\n")
                    else:
                        f.write(f"  无hammer数据 (hammers_val数组为空)\n")
                    
                    # After Touch数据
                    f.write(f"\nAfter Touch数据:\n")
                    if note.after_val.size > 0:
                        f.write(f"  数据点数: {note.after_val.size}\n")
                        f.write(f"  时间范围: {note.after_ts[0]} ms ~ {note.after_ts[-1]} ms\n")
                        f.write(f"  值范围: {note.after_val.min()} ~ {note.after_val.max()}\n")
                        f.write(f"  平均值: {note.after_val.mean():.2f}\n")
                        
                        # 只显示前5个和后5个数据点（如果数据太多）
                        if note.after_val.size <= 10:
                            f.write(f"  所有数据点:\n")
                            for i, (ts, val) in enumerate(zip(note.after_ts, note.after_val)):
                                f.write(f"    [{i}] 时间={ts:6d} ms, 值={val:3d}\n")
                        else:
                            f.write(f"  前5个数据点:\n")
                            for i in range(5):
                                f.write(f"    [{i}] 时间={note.after_ts[i]:6d} ms, 值={note.after_val[i]:3d}\n")
                            f.write(f"  ... (省略 {note.after_val.size - 10} 个数据点)\n")
                            f.write(f"  后5个数据点:\n")
                            for i in range(note.after_val.size - 5, note.after_val.size):
                                f.write(f"    [{i}] 时间={note.after_ts[i]:6d} ms, 值={note.after_val[i]:3d}\n")
                    else:
                        f.write(f"  无after touch数据 (after_val数组为空)\n")
                    
                    f.write("\n")
            
            # 文件末尾总结
            f.write("\n" + "=" * 100 + "\n")
            f.write("输出完成\n")
            f.write("=" * 100 + "\n")
        
        print(f"\n输出完成！数据已保存到: {output_file}")
        print(f"\n摘要:")
        print(f"  总轨道数: {len(reader.tracks)}")
        for track_idx, track in enumerate(reader.tracks):
            track_name = "录制轨道" if track_idx == 0 else "播放轨道" if track_idx == 1 else f"轨道{track_idx}"
            has_hammer = sum(1 for note in track if note.hammers_val.size > 0)
            print(f"  {track_name}: {len(track)} 个音符, {has_hammer} 个有hammer数据")
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python dump_spmid_data.py <spmid文件路径> [输出文件路径]")
        print("\n示例:")
        print("  python dump_spmid_data.py data.spmid")
        print("  python dump_spmid_data.py data.spmid full_output.txt")
        sys.exit(1)
    
    spmid_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not os.path.exists(spmid_file):
        print(f"错误: 文件不存在: {spmid_file}")
        sys.exit(1)
    
    dump_spmid_data(spmid_file, output_file)


if __name__ == '__main__':
    main()
