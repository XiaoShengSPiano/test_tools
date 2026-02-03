#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试播放轨道的hammer数据
检查播放轨道（Track 1）的OptimizedNote是否有hammers_val数据
"""

import sys
from spmid.spmid_reader import OptimizedSPMidReader

def test_replay_hammer_data(spmid_file: str):
    """测试播放轨道的hammer数据"""
    print(f"正在读取SPMID文件: {spmid_file}")
    
    reader = OptimizedSPMidReader(spmid_file)
    
    if len(reader.tracks) < 2:
        print("错误: SPMID文件应该至少有2个track（录制和播放）")
        return
    
    record_track = reader.tracks[0]
    replay_track = reader.tracks[1]
    
    print(f"\n录制轨道 (Track 0): {len(record_track)} 个音符")
    print(f"播放轨道 (Track 1): {len(replay_track)} 个音符")
    
    # 检查播放轨道的前10个音符
    print("\n播放轨道前10个音符的hammer数据:")
    print("=" * 80)
    
    for i, note in enumerate(replay_track[:10]):
        print(f"\n音符 {i}:")
        print(f"  ID: {note.id}")
        print(f"  Offset: {note.offset}")
        print(f"  Velocity: {note.velocity}")
        print(f"  hammers_val数组长度: {note.hammers_val.size}")
        
        if note.hammers_val.size > 0:
            first_hammer = note.hammers_val[0]
            print(f"  第一个hammer值: {first_hammer}")
            print(f"  所有hammer值: {note.hammers_val.tolist()}")
        else:
            print(f"  第一个hammer值: None (没有hammer数据)")
            print(f"  所有hammer值: []")
    
    # 统计播放轨道中有hammer数据的音符数量
    has_hammer_count = sum(1 for note in replay_track if note.hammers_val.size > 0)
    no_hammer_count = len(replay_track) - has_hammer_count
    
    print(f"\n播放轨道统计:")
    print(f"  有hammer数据的音符: {has_hammer_count}/{len(replay_track)} ({has_hammer_count/len(replay_track)*100:.1f}%)")
    print(f"  无hammer数据的音符: {no_hammer_count}/{len(replay_track)} ({no_hammer_count/len(replay_track)*100:.1f}%)")
    
    if has_hammer_count > 0:
        # 统计第一个hammer值为0的音符
        first_zero_count = sum(1 for note in replay_track 
                               if note.hammers_val.size > 0 and note.hammers_val[0] == 0)
        print(f"  第一个hammer值为0的音符: {first_zero_count}/{has_hammer_count}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python test_replay_hammer_data.py <spmid文件路径>")
        sys.exit(1)
    
    test_replay_hammer_data(sys.argv[1])
