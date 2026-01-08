#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试拆分后note_b的key_on等于拆分点
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')

from spmid.spmid_reader import Note
from spmid.note_matcher import NoteMatcher
import pandas as pd

def create_mock_note_with_offset(note_id, offset, relative_keyon, duration, hammer_times, 
                                 create_realistic_curve=False):
    """创建带offset的模拟Note对象
    
    Args:
        note_id: 按键ID
        offset: 起始偏移（0.1ms单位）
        relative_keyon: 相对于offset的keyon时间索引（0.1ms单位）
        duration: 持续时间索引（0.1ms单位）
        hammer_times: hammer的相对时间索引列表（0.1ms单位）
        create_realistic_curve: 是否创建真实的触后值曲线（上升-平稳-下降）
    """
    # after_touch: 从relative_keyon开始，每10个单位（1ms）采样一次
    times = list(range(relative_keyon, relative_keyon + duration, 10))
    if not times:
        times = [relative_keyon]
    
    if create_realistic_curve and len(times) > 10:
        # 创建真实的按键曲线：起始值100 → 上升到150 → 保持 → 下降回100
        values = []
        for i, t in enumerate(times):
            progress = i / len(times)
            if progress < 0.2:  # 前20%：上升
                values.append(100 + int(50 * (progress / 0.2)))
            elif progress < 0.7:  # 中间50%：保持高值
                values.append(150)
            else:  # 后30%：下降
                values.append(150 - int(50 * ((progress - 0.7) / 0.3)))
    else:
        values = [100] * len(times)
    
    after_touch = pd.Series(values, index=times)
    
    # hammers
    hammers = pd.Series([100] * len(hammer_times), index=hammer_times)
    
    return Note(
        offset=offset,
        id=note_id,
        finger=0,
        hammers=hammers,
        uuid=f"note_{note_id}_{offset}_{relative_keyon}",
        velocity=100,
        after_touch=after_touch
    )

def test_split_keyon_equals_split_point():
    """测试拆分后note_b的key_on等于拆分点"""
    print("=" * 70)
    print("测试: 拆分点 = note_b的key_on")
    print("=" * 70)
    
    # 场景1：offset=1000，两个按键合并
    # 第1个按键：相对keyon=0（绝对时间=100ms），持续3000单位（300ms）
    # 第2个按键：相对keyon=7700（绝对时间=870ms），持续2000单位（200ms）
    offset = 1000  # 100ms
    
    print("\n原始数据:")
    print(f"  offset = {offset} ({offset/10}ms)")
    print(f"  合并数据: 相对index [0, 10, ..., 7700, 7710, ...]")
    print(f"  hammers: [0, 7700]")
    print(f"  第1个hammer绝对时间 = (0 + {offset}) / 10 = {(0+offset)/10}ms")
    print(f"  第2个hammer绝对时间 = (7700 + {offset}) / 10 = {(7700+offset)/10}ms")
    
    record_data = [
        create_mock_note_with_offset(60, offset, 0, 3000, [0], create_realistic_curve=True),        # R1
        create_mock_note_with_offset(60, offset, 7700, 2000, [7700], create_realistic_curve=True),  # R2
    ]
    
    # 合并数据：第一个按键的曲线 + 第二个按键的曲线
    # 创建一个完整的合并after_touch曲线
    times1 = list(range(0, 3000, 10))
    times2 = list(range(3000, 9700, 10))
    
    # 第一段：上升-平稳-下降（到100）
    values1 = []
    for i, t in enumerate(times1):
        progress = i / len(times1)
        if progress < 0.2:
            values1.append(100 + int(50 * (progress / 0.2)))
        elif progress < 0.7:
            values1.append(150)
        else:
            values1.append(150 - int(50 * ((progress - 0.7) / 0.3)))
    
    # 第二段：从100开始，再次上升-平稳-下降
    values2 = []
    for i, t in enumerate(times2):
        progress = i / len(times2)
        if progress < 0.2:
            values2.append(100 + int(50 * (progress / 0.2)))
        elif progress < 0.7:
            values2.append(150)
        else:
            values2.append(150 - int(50 * ((progress - 0.7) / 0.3)))
    
    merged_after_touch = pd.Series(values1 + values2, index=times1 + times2)
    merged_hammers = pd.Series([100, 100], index=[0, 7700])
    
    replay_data = [
        Note(
            offset=offset,
            id=60,
            finger=0,
            hammers=merged_hammers,
            uuid="merged_note",
            velocity=100,
            after_touch=merged_after_touch
        )
    ]
    
    print(f"\n录制数据:")
    for i, note in enumerate(record_data):
        print(f"  R{i+1}: key_on={(note.after_touch.index[0] + note.offset)/10}ms, "
              f"duration={note.duration_ms}ms")
    
    print(f"\n播放数据（合并）:")
    for i, note in enumerate(replay_data):
        print(f"  P{i+1}: key_on={(note.after_touch.index[0] + note.offset)/10}ms, "
              f"duration={note.duration_ms}ms, "
              f"hammers={list(note.hammers.index)}")
    
    print("\n" + "=" * 70)
    print("执行匹配算法...")
    print("=" * 70)
    
    matcher = NoteMatcher()
    matched_pairs = matcher.find_all_matched_pairs(record_data, replay_data)
    
    print(f"\n匹配结果: {len(matched_pairs)}对")
    print("-" * 70)
    
    for rec_idx, rep_idx, rec_note, rep_note in matched_pairs:
        rec_info = f"[{rec_idx}]"
        if rec_note.is_split:
            rec_info = f"[{rec_note.split_parent_idx}:拆分{rec_note.split_seq}]"
        
        rep_info = f"[{rep_idx}]"
        if rep_note.is_split:
            rep_info = f"[{rep_note.split_parent_idx}:拆分{rep_note.split_seq}]"
        
        print(f"  录制{rec_info} (key_on={rec_note.key_on_ms:.1f}ms) ↔ "
              f"播放{rep_info} (key_on={rep_note.key_on_ms:.1f}ms)")
        
        # 验证拆分的note_b
        if rep_note.is_split and rep_note.split_seq == 1:
            print(f"    → note_b的key_on={rep_note.key_on_ms:.1f}ms")
            print(f"    → note_b的第一个after_touch索引={rep_note.after_touch.index[0]}")
            print(f"    → 计算: ({rep_note.after_touch.index[0]} + {rep_note.offset}) / 10 = {rep_note.key_on_ms:.1f}ms")
            
            # 关键验证：拆分点应该是下一个hammer的位置
            expected_split_keyon = (7700 + offset) / 10  # 870ms
            assert abs(rep_note.key_on_ms - expected_split_keyon) < 0.1, \
                f"note_b的key_on应该是{expected_split_keyon}ms，实际是{rep_note.key_on_ms}ms"
            print(f"    ✓ 验证成功: note_b的key_on = {expected_split_keyon}ms (拆分点)")
    
    assert len(matched_pairs) == 2, f"期望2个匹配对，实际{len(matched_pairs)}"
    
    print("\n" + "=" * 70)
    print("✓ 所有测试通过：拆分点 = note_b的key_on")
    print("=" * 70)
    
    return True

if __name__ == "__main__":
    success = test_split_keyon_equals_split_point()
    sys.exit(0 if success else 1)

