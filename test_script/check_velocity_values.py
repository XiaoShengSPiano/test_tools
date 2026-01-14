#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查SPMID文件中velocity字段的值
"""

import sys
from pathlib import Path
from collections import Counter
from spmid.spmid_reader import OptimizedSPMidReader

def check_velocity_values(spmid_file_path):
    """检查SPMID文件中所有Note的velocity值"""
    
    print(f"正在读取SPMID文件: {spmid_file_path}")
    print("=" * 80)
    
    try:
        # 读取SPMID文件（使用OptimizedNote）
        reader = OptimizedSPMidReader(spmid_file_path)
        
        # 获取所有轨道的notes
        all_notes = []
        for track_idx in range(reader.track_count):
            track_notes = reader.get_track(track_idx)
            all_notes.extend(track_notes)
        
        notes = all_notes
        
        print(f"✓ 文件包含 {reader.track_count} 个轨道")
        
        if not notes:
            print("❌ 文件中没有找到任何Note")
            return
        
        print(f"✓ 成功读取 {len(notes)} 个Note\n")
        
        # 收集所有velocity值
        velocity_values = [note.velocity for note in notes]
        
        # 统计
        velocity_counter = Counter(velocity_values)
        unique_values = sorted(velocity_counter.keys())
        
        print("=" * 80)
        print("Velocity 值统计:")
        print("=" * 80)
        
        print(f"\n总Note数: {len(notes)}")
        print(f"不同velocity值的数量: {len(unique_values)}")
        print(f"Velocity值范围: {min(velocity_values)} ~ {max(velocity_values)}")
        
        print("\n各velocity值的分布:")
        print("-" * 80)
        for value in unique_values:
            count = velocity_counter[value]
            percentage = (count / len(notes)) * 100
            print(f"  velocity = {value:4d}  |  出现次数: {count:4d}  |  占比: {percentage:5.1f}%")
        
        # 显示前10个Note的详细信息
        print("\n" + "=" * 80)
        print("前10个Note的详细信息:")
        print("=" * 80)
        for i, note in enumerate(notes[:10]):
            print(f"\nNote #{i+1}:")
            print(f"  id: {note.id}")
            print(f"  velocity: {note.velocity}")
            print(f"  finger: {note.finger}")
            print(f"  offset: {note.offset}")
            print(f"  hammers数量: {len(note.hammers_val)}")
            if len(note.hammers_val) > 0:
                print(f"  hammers值示例: {note.hammers_val[:5].tolist() if len(note.hammers_val) >= 5 else note.hammers_val.tolist()}")
        
        # 判断是否为固定值
        print("\n" + "=" * 80)
        print("结论:")
        print("=" * 80)
        if len(unique_values) == 1:
            print(f"✓ velocity字段是固定值: {unique_values[0]}")
            print(f"  所有 {len(notes)} 个Note的velocity都是 {unique_values[0]}")
        else:
            print(f"✗ velocity字段不是固定值")
            print(f"  有 {len(unique_values)} 个不同的值: {unique_values}")
        
        # 检查hammers值
        print("\n检查hammers值（真正的锤速）:")
        print("-" * 80)
        hammer_values = []
        for note in notes:
            if len(note.hammers_val) > 0:
                hammer_values.append(note.hammers_val[0])
        
        if hammer_values:
            print(f"收集到 {len(hammer_values)} 个有效的hammer值")
            print(f"hammer值范围: {min(hammer_values)} ~ {max(hammer_values)}")
            print(f"hammer值示例（前20个）: {hammer_values[:20]}")
            
            # 统计hammer值分布
            hammer_counter = Counter(hammer_values)
            print(f"\n不同hammer值的数量: {len(hammer_counter)}")
            if len(hammer_counter) <= 20:
                print("hammer值分布:")
                for value in sorted(hammer_counter.keys()):
                    count = hammer_counter[value]
                    print(f"  hammer = {value:4d}  |  出现次数: {count:4d}")
        
    except FileNotFoundError:
        print(f"❌ 错误: 找不到文件 {spmid_file_path}")
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 默认查找当前目录下的SPMID文件
    if len(sys.argv) > 1:
        spmid_path = sys.argv[1]
    else:
        # 在当前目录查找第一个.spmid文件
        spmid_files = list(Path('.').glob('*.spmid'))
        if spmid_files:
            spmid_path = str(spmid_files[0])
            print(f"自动选择文件: {spmid_path}\n")
        else:
            print("用法: python check_velocity_values.py <spmid文件路径>")
            print("\n或将.spmid文件放在当前目录下")
            sys.exit(1)
    
    check_velocity_values(spmid_path)
