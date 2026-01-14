#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SPMID 录制音轨数据显示脚本

用于读取SPMID文件并显示录制音轨的详细信息，包括：
- after_touch 数据
- hammers 数据
- 锤速信息
"""

import sys
import os
import argparse
from pathlib import Path
from typing import List, Optional, TextIO
import pandas as pd

# 添加项目路径到Python路径
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from spmid.spmid_reader import SPMidReader, Note


def categorize_notes(track: List[Note]) -> dict:
    """
    将音符按数据类型进行分类

    Args:
        track: 音符列表

    Returns:
        dict: 包含各类音符的字典
    """
    categories = {
        'only_after_touch': [],      # 只有after_touch，没有hammers
        'only_hammers': [],          # 只有hammers，没有after_touch
        'both_with_zero_velocity': [] # 同时有after_touch和hammers，但锤速为0
    }

    for i, note in enumerate(track):
        has_after_touch = not note.after_touch.empty
        has_hammers = not note.hammers.empty
        has_zero_velocity = has_hammers and (note.hammers == 0).any()

        if has_after_touch and not has_hammers:
            # 只有after_touch，没有hammers
            categories['only_after_touch'].append((i, note))
        elif not has_after_touch and has_hammers:
            # 只有hammers，没有after_touch
            categories['only_hammers'].append((i, note))
        elif has_after_touch and has_hammers and has_zero_velocity:
            # 同时有两种数据，但锤速为0
            categories['both_with_zero_velocity'].append((i, note))

    return categories


def find_zero_velocity_notes(track: List[Note]) -> List[tuple]:
    """
    查找同时具有after_touch和hammers数据但锤速为0的音符
    （为了向后兼容保留此函数）

    Args:
        track: 音符列表

    Returns:
        List[tuple]: (note_index, note) 的列表
    """
    categories = categorize_notes(track)
    return categories['both_with_zero_velocity']


def display_note_category(category_name: str, notes: List[tuple], output: TextIO = sys.stdout):
    """
    显示特定类别的音符信息

    Args:
        category_name: 类别名称
        notes: 音符列表 (note_index, note)
        output: 输出流
    """
    print(f"\n{'='*80}", file=output)
    print(f"{category_name}", file=output)
    print(f"{'='*80}", file=output)

    if not notes:
        print(f"未找到{category_name.lower()}的音符", file=output)
        return

    print(f"找到 {len(notes)} 个符合条件的音符:", file=output)

    if "锤速为0" in category_name:
        print("这些音符同时具有after_touch和hammers数据，但至少有一个锤击的锤速为0", file=output)
    elif "只有after_touch" in category_name:
        print("这些音符只有after_touch数据，没有hammers数据", file=output)
    elif "只有hammers" in category_name:
        print("这些音符只有hammers数据，没有after_touch数据", file=output)

    print(file=output)

    for note_index, note in notes:
        print(f"音符 #{note_index} (按键ID: {note.id})", file=output)

        if "锤速为0" in category_name:
            # 显示锤速为0的具体锤击
            zero_velocity_hammers = note.hammers[note.hammers == 0]
            if not zero_velocity_hammers.empty:
                print(f"  锤速为0的锤击数量: {len(zero_velocity_hammers)}", file=output)
                print("  锤速为0的锤击时间戳:", file=output)
                for timestamp in zero_velocity_hammers.index:
                    actual_time = (timestamp + note.offset) / 10.0
                    print(f"    {actual_time:.2f} ms", file=output)

        # 显示数据统计
        if not note.after_touch.empty:
            print(f"  After Touch数据点数: {len(note.after_touch)}", file=output)
        if not note.hammers.empty:
            print(f"  总锤击数量: {len(note.hammers)}", file=output)

        print(file=output)


def display_data_category_analysis(track: List[Note], output_file: str = None):
    """
    分析并显示各类音符数据分布情况

    Args:
        track: 音符列表
        output_file: 输出文件路径，如果为None则输出到标准输出
    """
    categories = categorize_notes(track)

    # 准备输出流
    output = sys.stdout
    if output_file:
        try:
            output = open(output_file, 'w', encoding='utf-8')
        except Exception as e:
            print(f"错误: 无法打开输出文件 '{output_file}': {e}", file=sys.stderr)
            return

    try:
        print("SPMID音符数据分类分析报告", file=output)
        print("=" * 80, file=output)
        print(f"总音符数量: {len(track)}", file=output)

        # 统计信息
        only_after_touch = categories['only_after_touch']
        only_hammers = categories['only_hammers']
        both_with_zero = categories['both_with_zero_velocity']

        print(f"只有after_touch数据的音符: {len(only_after_touch)}", file=output)
        print(f"只有hammers数据的音符: {len(only_hammers)}", file=output)
        print(f"同时有两种数据但锤速为0的音符: {len(both_with_zero)}", file=output)

        # 显示详细分类结果
        display_note_category("只有after_touch数据的音符", only_after_touch, output)
        display_note_category("只有hammers数据的音符", only_hammers, output)
        display_note_category("同时有after_touch和hammers数据但锤速为0的音符", both_with_zero, output)

        print(f"\n{'='*80}", file=output)
        print("分析完成", file=output)
        print(f"{'='*80}", file=output)

    finally:
        if output_file and output != sys.stdout:
            output.close()


def display_zero_velocity_analysis(track: List[Note], output: TextIO = sys.stdout):
    """
    分析并显示锤速为0的音符信息（向后兼容）

    Args:
        track: 音符列表
        output: 输出流，默认为标准输出
    """
    zero_velocity_notes = find_zero_velocity_notes(track)
    display_note_category("同时有after_touch和hammers数据但锤速为0的音符", zero_velocity_notes, output)


def display_note_details(note: Note, note_index: int, output: TextIO = sys.stdout):
    """
    显示单个音符的详细信息

    Args:
        note: Note对象
        note_index: 音符索引
        output: 输出流，默认为标准输出
    """
    print(f"\n{'='*60}", file=output)
    print(f"音符 #{note_index}", file=output)
    print(f"{'='*60}", file=output)

    # 基本信息
    print(f"按键ID: {note.id}", file=output)
    print(f"手指: {note.finger}", file=output)
    print(f"速度: {note.velocity}", file=output)
    print(f"UUID: {note.uuid}", file=output)

    # 时间信息
    print(f"按键开始时间: {note.key_on_ms:.2f} ms" if note.key_on_ms else "按键开始时间: N/A", file=output)
    print(f"按键结束时间: {note.key_off_ms:.2f} ms" if note.key_off_ms else "按键结束时间: N/A", file=output)
    print(f"持续时间: {note.duration_ms:.2f} ms" if note.duration_ms else "持续时间: N/A", file=output)

    # After Touch 数据
    print(f"\nAfter Touch 数据 ({len(note.after_touch)} 个数据点):", file=output)
    if not note.after_touch.empty:
        print("时间戳(ms) | 值", file=output)
        print("-" * 20, file=output)
        for timestamp, value in note.after_touch.items():
            actual_time = (timestamp + note.offset) / 10.0
            print(f"{actual_time:8.2f} | {value}", file=output)
    else:
        print("无After Touch数据", file=output)

    # Hammers 数据（锤击数据）
    print(f"\nHammers 数据 ({len(note.hammers)} 个锤击):", file=output)
    if not note.hammers.empty:
        print("时间戳(ms) | 锤速", file=output)
        print("-" * 20, file=output)
        for timestamp, velocity in note.hammers.items():
            actual_time = (timestamp + note.offset) / 10.0
            print(f"{actual_time:8.2f} | {velocity}", file=output)
    else:
        print("无锤击数据", file=output)


def display_track_summary(track: List[Note], output: TextIO = sys.stdout):
    """
    显示音轨摘要信息

    Args:
        track: 音符列表
        output: 输出流，默认为标准输出
    """
    print(f"\n{'='*80}", file=output)
    print("音轨摘要", file=output)
    print(f"{'='*80}", file=output)
    print(f"总音符数量: {len(track)}", file=output)

    # 统计信息
    notes_with_hammers = sum(1 for note in track if not note.hammers.empty)
    notes_with_after_touch = sum(1 for note in track if not note.after_touch.empty)
    notes_with_both = sum(1 for note in track if not note.hammers.empty and not note.after_touch.empty)

    print(f"包含锤击数据的音符: {notes_with_hammers}", file=output)
    print(f"包含触后数据的音符: {notes_with_after_touch}", file=output)
    print(f"同时包含两种数据的音符: {notes_with_both}", file=output)

    # 按键ID分布
    key_ids = {}
    for note in track:
        key_ids[note.id] = key_ids.get(note.id, 0) + 1

    print(f"\n按键ID分布:", file=output)
    for key_id in sorted(key_ids.keys()):
        print(f"  按键 {key_id}: {key_ids[key_id]} 次", file=output)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="SPMID 录制音轨数据显示脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python display_spmid_track.py data/record.spmid
  python display_spmid_track.py data/record.spmid -o output.txt
  python display_spmid_track.py data/record.spmid --track 1 -o output.txt
  python display_spmid_track.py data/record.spmid --analyze-data-categories --category-output data_categories.txt
        """
    )

    parser.add_argument("file_path", help="SPMID文件路径")
    parser.add_argument("-o", "--output", help="输出文件路径（默认为标准输出）")
    parser.add_argument("-t", "--track", type=int, default=0,
                       help="音轨索引（默认为0，通常为录制音轨）")
    parser.add_argument("--analyze-data-categories", action="store_true",
                       help="分析音符数据分类：只有after_touch、只有hammers、都有但锤速为0")
    parser.add_argument("--category-output", help="数据分类分析结果的输出文件路径")

    args = parser.parse_args()

    file_path = args.file_path
    output_file = args.output
    track_index = args.track
    analyze_data_categories = args.analyze_data_categories
    category_output = args.category_output

    # 检查文件是否存在
    if not os.path.exists(file_path):
        print(f"错误: 文件 '{file_path}' 不存在", file=sys.stderr)
        sys.exit(1)

    # 准备输出流
    output_stream = sys.stdout
    if output_file:
        try:
            output_stream = open(output_file, 'w', encoding='utf-8')
            print(f"输出将写入到文件: {output_file}")
        except Exception as e:
            print(f"错误: 无法打开输出文件 '{output_file}': {e}", file=sys.stderr)
            sys.exit(1)

    try:
        # 读取SPMID文件
        print(f"正在读取文件: {file_path}", file=output_stream)
        reader = SPMidReader(file_path)

        print(f"文件包含 {reader.track_count} 个音轨", file=output_stream)

        if reader.track_count == 0:
            print("错误: 文件不包含任何音轨", file=sys.stderr)
            sys.exit(1)

        if track_index >= reader.track_count:
            print(f"错误: 音轨索引 {track_index} 超出范围 (0-{reader.track_count-1})", file=sys.stderr)
            sys.exit(1)

        print(f"\n读取音轨 #{track_index}...", file=output_stream)

        # 获取标准Note对象
        track = reader.get_track_as_standard_notes(track_index)

        # 如果需要分析数据分类
        if analyze_data_categories:
            print(f"正在分析音符数据分类...")
            display_data_category_analysis(track, category_output)
            if category_output:
                print(f"数据分类分析结果已保存到文件: {category_output}")
            return  # 如果只是分析分类，就不继续输出其他信息

        # 显示音轨摘要
        display_track_summary(track, output_stream)

        # 显示每个音符的详细信息（如果不是只验证模式）
        if not (validate_zero_velocity and output_file is None):
            print("\n详细音符数据:", file=output_stream)
            print("=" * 80, file=output_stream)

            for i, note in enumerate(track):
                display_note_details(note, i, output_stream)

            print(f"\n{'='*80}", file=output_stream)
            print("数据输出完成", file=output_stream)
            print(f"{'='*80}", file=output_stream)

    except Exception as e:
        print(f"错误: 读取文件时发生异常: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # 关闭输出文件（如果打开了的话）
        if output_file and output_stream != sys.stdout:
            output_stream.close()
            print(f"数据已保存到文件: {output_file}")


if __name__ == "__main__":
    main()