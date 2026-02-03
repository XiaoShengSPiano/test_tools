#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
导出播放音轨（Replay Track）的详细音符数据
fields: key_id, uuid, key_on, key_off, duration, hammer_time, hammer_velocity
"""

import sys
import os
from spmid.spmid_reader import OptimizedSPMidReader

def dump_replay_notes(spmid_file: str, output_file: str = None):
    if output_file is None:
        output_file = os.path.splitext(spmid_file)[0] + "_replay_notes.txt"
        
    print(f"正在分析文件: {spmid_file}")
    print(f"输出文件: {output_file}")
    
    try:
        reader = OptimizedSPMidReader(spmid_file)
        if len(reader.tracks) < 2:
            print("错误: 文件少于2个音轨，无法找到播放音轨")
            return

        replay_track = reader.tracks[1]
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"文件: {spmid_file}\n")
            f.write(f"播放音轨 (Track 1)，共 {len(replay_track)} 个音符\n")
            f.write("-" * 100 + "\n")
            
            # 打印表头
            header = f"{'KeyID':<6} {'UUID':<36} {'KeyOn(ms)':<10} {'KeyOff(ms)':<10} {'Duration':<10} {'HammerT':<10} {'HammerV':<8}\n"
            f.write(header)
            f.write("-" * 100 + "\n")

            for i, opt_note in enumerate(replay_track):
                # 转换为标准Note以获取计算好的时间属性
                note = opt_note.to_standard_note()
                
                key_id = note.id
                uuid = note.uuid
                key_on = f"{note.key_on_ms:.2f}"
                key_off = f"{note.key_off_ms:.2f}"
                duration = f"{note.duration_ms:.2f}"
                
                hammer_t = f"{note.first_hammer_time:.2f}" if note.first_hammer_velocity > 0 else "N/A"
                hammer_v = f"{note.first_hammer_velocity}" if note.first_hammer_velocity > 0 else "0"
                
                line = f"{key_id:<6} {uuid:<36} {key_on:<10} {key_off:<10} {duration:<10} {hammer_t:<10} {hammer_v:<8}\n"
                f.write(line)
        
        print(f"✅ 输出完成，已保存到: {output_file}")

    except Exception as e:
        print(f"发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python dump_replay_notes.py <spmid_file> [output_file]")
    else:
        spmid_file = sys.argv[1]
        output_file = sys.argv[2] if len(sys.argv) > 2 else None
        dump_replay_notes(spmid_file, output_file)
