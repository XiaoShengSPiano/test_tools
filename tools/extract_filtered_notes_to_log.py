#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SPMID有效音符数据提取脚本

从SPMID文件中提取经过基本过滤后的有效音符数据，并输出到独立的日志文件，包括：
- 过滤前后的数据统计对比
- 有效音符的详细信息
- 无效音符的过滤原因
- 数据质量分析

使用方法：
python tools/extract_filtered_notes_to_log.py --file your_file.spmid --output filtered_notes.log
"""

import argparse
import sys
import os
from datetime import datetime
from typing import List, Dict, Any

# 确保可从任意工作目录运行：将项目根目录加入 sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from spmid.spmid_reader import SPMidReader, Note
from spmid.data_filter import DataFilter
from spmid.motor_threshold_checker import MotorThresholdChecker


def setup_logger(output_file: str):
    """设置独立的日志记录器"""
    import logging
    
    # 创建logger
    logger = logging.getLogger('filtered_notes_extractor')
    logger.setLevel(logging.INFO)
    
    # 清除已有的handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 创建文件handler
    file_handler = logging.FileHandler(output_file, mode='w', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # 创建格式器
    formatter = logging.Formatter('%(message)s')
    file_handler.setFormatter(formatter)
    
    # 添加handler到logger
    logger.addHandler(file_handler)
    
    return logger


def log_filtering_summary(logger, record_data: List[Note], replay_data: List[Note], 
                         valid_record_data: List[Note], valid_replay_data: List[Note], 
                         invalid_counts: Dict[str, Any]):
    """记录过滤统计信息"""
    logger.info("="*80)
    logger.info("DATA FILTERING SUMMARY")
    logger.info("="*80)
    
    # 原始数据统计
    logger.info("Original Data:")
    logger.info(f"  Record Track: {len(record_data)} notes")
    logger.info(f"  Replay Track: {len(replay_data)} notes")
    logger.info(f"  Total Notes:  {len(record_data) + len(replay_data)} notes")
    
    # 过滤后数据统计
    logger.info("\nFiltered Data:")
    logger.info(f"  Valid Record Notes: {len(valid_record_data)} notes")
    logger.info(f"  Valid Replay Notes: {len(valid_replay_data)} notes")
    logger.info(f"  Total Valid Notes:  {len(valid_record_data) + len(valid_replay_data)} notes")
    
    # 过滤率计算
    total_original = len(record_data) + len(replay_data)
    total_valid = len(valid_record_data) + len(valid_replay_data)
    filter_rate = (total_original - total_valid) / total_original * 100 if total_original > 0 else 0
    
    logger.info(f"\nFiltering Results:")
    logger.info(f"  Filtered Out: {total_original - total_valid} notes ({filter_rate:.1f}%)")
    logger.info(f"  Kept: {total_valid} notes ({100 - filter_rate:.1f}%)")
    
    # 详细过滤原因统计
    logger.info(f"\nDetailed Filtering Reasons:")
    record_invalid = invalid_counts.get('record_data', {})
    replay_invalid = invalid_counts.get('replay_data', {})
    
    # 合并所有无效原因
    all_reasons = {}
    for data_type, reasons in [('Record', record_invalid), ('Replay', replay_invalid)]:
        for reason, count in reasons.items():
            if reason != 'silent_notes_details':  # 跳过详细信息
                key = f"{data_type}: {reason}"
                all_reasons[key] = count
    
    for reason, count in sorted(all_reasons.items()):
        logger.info(f"  {reason}: {count} notes")
    
    logger.info("")


def log_note_detailed_info(logger, note: Note, track_name: str, note_idx: int, is_valid: bool):
    """记录音符详细信息"""
    status = "VALID" if is_valid else "INVALID"
    logger.info(f"  {track_name}[{note_idx:3d}] ({status}): KeyID={note.id:3d}, "
               f"Offset={note.offset:8d}, Finger={note.finger:2d}, "
               f"Velocity={note.velocity:4d}")
    
    # 数据长度信息
    at_length = len(note.after_touch) if note.after_touch is not None else 0
    hm_length = len(note.hammers) if note.hammers is not None else 0
    logger.info(f"         Data: after_touch={at_length:3d} points, hammers={hm_length:3d} points")
    
    # 时间信息
    if note.after_touch is not None and len(note.after_touch) > 0:
        try:
            keyon_time = (note.after_touch.index[0] + note.offset) / 10.0
            keyoff_time = (note.after_touch.index[-1] + note.offset) / 10.0
        except (IndexError, AttributeError) as e:
            raise ValueError(f"音符ID {note.id} 的after_touch数据无效: {e}") from e
        duration = keyoff_time - keyon_time
        logger.info(f"         Time: KeyOn={keyon_time:8.2f}ms, KeyOff={keyoff_time:8.2f}ms, "
                   f"Duration={duration:6.2f}ms")
    
    # 锤速信息
    if note.hammers is not None and len(note.hammers) > 0:
        first_hammer = note.hammers.values[0]
        max_hammer = note.hammers.values.max()
        min_hammer = note.hammers.values.min()
        logger.info(f"         Hammer: First={first_hammer:3d}, Max={max_hammer:3d}, Min={min_hammer:3d}")
    
    logger.info("")


def log_invalid_notes_details(logger, record_data: List[Note], replay_data: List[Note], 
                             valid_record_data: List[Note], valid_replay_data: List[Note],
                             invalid_counts: Dict[str, Any]):
    """记录无效音符的详细信息"""
    logger.info("="*80)
    logger.info("INVALID NOTES DETAILS")
    logger.info("="*80)
    
    # 获取有效音符的索引集合
    valid_record_indices = set()
    valid_replay_indices = set()
    
    # 通过比较找到有效音符的索引
    for valid_note in valid_record_data:
        for i, orig_note in enumerate(record_data):
            if (orig_note.id == valid_note.id and 
                orig_note.offset == valid_note.offset and
                orig_note.velocity == valid_note.velocity):
                valid_record_indices.add(i)
                break
    
    for valid_note in valid_replay_data:
        for i, orig_note in enumerate(replay_data):
            if (orig_note.id == valid_note.id and 
                orig_note.offset == valid_note.offset and
                orig_note.velocity == valid_note.velocity):
                valid_replay_indices.add(i)
                break
    
    # 记录无效的录制音符
    logger.info("Invalid Record Notes:")
    logger.info("-" * 60)
    invalid_record_count = 0
    for i, note in enumerate(record_data):
        if i not in valid_record_indices:
            invalid_record_count += 1
            log_note_detailed_info(logger, note, "Record", i, False)
    
    if invalid_record_count == 0:
        logger.info("  No invalid record notes found.")
    
    # 记录无效的回放音符
    logger.info("\nInvalid Replay Notes:")
    logger.info("-" * 60)
    invalid_replay_count = 0
    for i, note in enumerate(replay_data):
        if i not in valid_replay_indices:
            invalid_replay_count += 1
            log_note_detailed_info(logger, note, "Replay", i, False)
    
    if invalid_replay_count == 0:
        logger.info("  No invalid replay notes found.")
    
    logger.info(f"\nTotal Invalid Notes: {invalid_record_count + invalid_replay_count}")
    logger.info("")


def log_valid_notes_summary(logger, valid_record_data: List[Note], valid_replay_data: List[Note]):
    """记录有效音符的汇总信息"""
    logger.info("="*80)
    logger.info("VALID NOTES SUMMARY")
    logger.info("="*80)
    
    # 录制数据统计
    if valid_record_data:
        record_key_ids = [note.id for note in valid_record_data]
        record_unique_keys = len(set(record_key_ids))
        record_min_key = min(record_key_ids)
        record_max_key = max(record_key_ids)
        
        # 时间范围
        record_times = []
        for note in valid_record_data:
            if note.after_touch is not None and len(note.after_touch) > 0:
                note_times = [(t + note.offset) / 10.0 for t in note.after_touch.index]
                record_times.extend(note_times)
        
        record_time_range = "N/A"
        if record_times:
            record_time_range = f"{min(record_times):.2f}ms - {max(record_times):.2f}ms"
        
        logger.info("Valid Record Notes:")
        logger.info(f"  Count: {len(valid_record_data)} notes")
        logger.info(f"  Key Range: {record_min_key}-{record_max_key} ({record_unique_keys} unique keys)")
        logger.info(f"  Time Range: {record_time_range}")
    
    # 回放数据统计
    if valid_replay_data:
        replay_key_ids = [note.id for note in valid_replay_data]
        replay_unique_keys = len(set(replay_key_ids))
        replay_min_key = min(replay_key_ids)
        replay_max_key = max(replay_key_ids)
        
        # 时间范围
        replay_times = []
        for note in valid_replay_data:
            if note.after_touch is not None and len(note.after_touch) > 0:
                note_times = [(t + note.offset) / 10.0 for t in note.after_touch.index]
                replay_times.extend(note_times)
        
        replay_time_range = "N/A"
        if replay_times:
            replay_time_range = f"{min(replay_times):.2f}ms - {max(replay_times):.2f}ms"
        
        logger.info("\nValid Replay Notes:")
        logger.info(f"  Count: {len(valid_replay_data)} notes")
        logger.info(f"  Key Range: {replay_min_key}-{replay_max_key} ({replay_unique_keys} unique keys)")
        logger.info(f"  Time Range: {replay_time_range}")
    
    logger.info("")


def extract_filtered_notes_to_log(file_path: str, output_file: str):
    """提取过滤后的有效音符数据到日志文件"""
    logger = setup_logger(output_file)
    
    # 记录开始信息
    logger.info("="*80)
    logger.info(f"SPMID Filtered Notes Data Extraction Log")
    logger.info(f"File: {file_path}")
    logger.info(f"Extraction Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*80)
    logger.info("")
    
    try:
        # 读取SPMID文件
        reader = SPMidReader.from_file(file_path, verbose=False)
        track_count = reader.get_track_count
        
        if track_count < 2:
            logger.error(f"❌ Insufficient tracks: {track_count} (need at least 2)")
            return
        
        # 获取原始数据
        record_data = reader.get_track(0)
        replay_data = reader.get_track(1)
        
        logger.info(f"File Information:")
        logger.info(f"  Track Count: {track_count}")
        logger.info(f"  Record Track: {len(record_data)} notes")
        logger.info(f"  Replay Track: {len(replay_data)} notes")
        logger.info("")
        
        # 初始化数据过滤器
        threshold_checker = MotorThresholdChecker()
        data_filter = DataFilter(threshold_checker)
        
        # 执行数据过滤
        logger.info("Executing data filtering...")
        valid_record_data, valid_replay_data, invalid_counts = data_filter.filter_valid_notes_data(
            record_data, replay_data
        )
        logger.info("Data filtering completed.")
        logger.info("")
        
        # 记录过滤统计
        log_filtering_summary(logger, record_data, replay_data, 
                             valid_record_data, valid_replay_data, invalid_counts)
        
        # 记录无效音符详情
        log_invalid_notes_details(logger, record_data, replay_data,
                                 valid_record_data, valid_replay_data, invalid_counts)
        
        # 记录有效音符汇总
        log_valid_notes_summary(logger, valid_record_data, valid_replay_data)
        
        logger.info("="*80)
        logger.info("Filtered notes data extraction completed successfully!")
        logger.info("="*80)
        
        print(f"✅ Filtered notes data extraction completed. Log saved to: {output_file}")
        
    except Exception as e:
        logger.error(f"❌ Error during data extraction: {e}")
        import traceback
        logger.error(traceback.format_exc())
        print(f"❌ Error: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description='Extract filtered valid notes data to log file')
    parser.add_argument('--file', required=True, help='SPMID file path')
    parser.add_argument('--output', default='filtered_notes.log', 
                       help='Output log file path (default: filtered_notes.log)')
    args = parser.parse_args()
    
    if not os.path.exists(args.file):
        print(f"❌ File not found: {args.file}")
        sys.exit(1)
    
    extract_filtered_notes_to_log(args.file, args.output)


if __name__ == '__main__':
    main()

