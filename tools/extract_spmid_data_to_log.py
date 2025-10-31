#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SPMID数据提取脚本

从SPMID文件中提取详细数据并输出到独立的日志文件，包括：
- 音符基本信息（键ID、偏移量、手指、UUID等）
- after_touch数据（时间戳与按键深度）
- hammers数据（时间戳与锤速）
- 数据统计信息

使用方法：
python tools/extract_spmid_data_to_log.py --file your_file.spmid --output data_extraction.log
"""

import argparse
import sys
import os
from datetime import datetime
from typing import List

# 确保可从任意工作目录运行：将项目根目录加入 sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from spmid.spmid_reader import SPMidReader, Note


def setup_logger(output_file: str):
    """设置独立的日志记录器"""
    import logging
    
    # 创建logger
    logger = logging.getLogger('spmid_data_extractor')
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


def log_note_basic_info(logger, note: Note, track_idx: int, note_idx: int):
    """记录音符基本信息"""
    logger.info(f"  Note[{note_idx:3d}]: KeyID={note.id:3d}, "
               f"Offset={note.offset:8d}, Finger={note.finger:2d}, "
               f"Velocity={note.velocity:4d}, UUID={note.uuid}")
    
    # 记录数据长度
    at_length = len(note.after_touch) if note.after_touch is not None else 0
    hm_length = len(note.hammers) if note.hammers is not None else 0
    logger.info(f"         Data Length: after_touch={at_length:3d} points, "
               f"hammers={hm_length:3d} points")


def log_after_touch_data(logger, note: Note, track_idx: int, note_idx: int):
    """记录after_touch数据"""
    if note.after_touch is None or len(note.after_touch) == 0:
        logger.info(f"         after_touch: No data")
        return
    
    logger.info(f"         after_touch data ({len(note.after_touch)} points):")
    logger.info(f"           {'Index':<8} {'Time(ms)':<12} {'Depth':<8}")
    logger.info(f"           {'-'*8} {'-'*12} {'-'*8}")
    
    for i, (timestamp, depth) in enumerate(note.after_touch.items()):
        time_ms = timestamp / 10.0  # 转换为ms显示
        logger.info(f"           {i:<8} {time_ms:<12.2f} {depth:<8}")
        
        # 限制输出数量，避免日志过长
        if i >= 49:  # 最多显示50个点
            remaining = len(note.after_touch) - 50
            if remaining > 0:
                logger.info(f"           ... ({remaining} more points)")
            break


def log_hammers_data(logger, note: Note, track_idx: int, note_idx: int):
    """记录hammers数据"""
    if note.hammers is None or len(note.hammers) == 0:
        logger.info(f"         hammers: No data")
        return
    
    logger.info(f"         hammers data ({len(note.hammers)} points):")
    logger.info(f"           {'Index':<8} {'Time(ms)':<12} {'Velocity':<10}")
    logger.info(f"           {'-'*8} {'-'*12} {'-'*10}")
    
    for i, (timestamp, velocity) in enumerate(note.hammers.items()):
        time_ms = timestamp / 10.0  # 转换为ms显示
        logger.info(f"           {i:<8} {time_ms:<12.2f} {velocity:<10}")
        
        # 限制输出数量，避免日志过长
        if i >= 49:  # 最多显示50个点
            remaining = len(note.hammers) - 50
            if remaining > 0:
                logger.info(f"           ... ({remaining} more points)")
            break


def log_track_summary(logger, notes: List[Note], track_idx: int):
    """记录音轨统计信息"""
    total_notes = len(notes)
    total_at_points = sum(len(note.after_touch) for note in notes if note.after_touch is not None)
    total_hm_points = sum(len(note.hammers) for note in notes if note.hammers is not None)
    
    # 统计键ID分布
    key_ids = [note.id for note in notes]
    unique_keys = len(set(key_ids))
    min_key = min(key_ids) if key_ids else 0
    max_key = max(key_ids) if key_ids else 0
    
    # 统计时间范围
    all_times = []
    for note in notes:
        if note.after_touch is not None and len(note.after_touch) > 0:
            note_times = [t + note.offset for t in note.after_touch.index]
            all_times.extend(note_times)
    
    time_range = "N/A"
    if all_times:
        min_time = min(all_times) / 10.0  # 转换为ms
        max_time = max(all_times) / 10.0
        time_range = f"{min_time:.2f}ms - {max_time:.2f}ms"
    
    logger.info(f"Track {track_idx} Summary:")
    logger.info(f"  Total Notes: {total_notes}")
    logger.info(f"  Unique Keys: {unique_keys} (Range: {min_key}-{max_key})")
    logger.info(f"  Total after_touch Points: {total_at_points}")
    logger.info(f"  Total hammers Points: {total_hm_points}")
    logger.info(f"  Time Range: {time_range}")
    logger.info("")


def extract_spmid_data_to_log(file_path: str, output_file: str):
    """提取SPMID数据到日志文件"""
    logger = setup_logger(output_file)
    
    # 记录开始信息
    logger.info("="*80)
    logger.info(f"SPMID Data Extraction Log")
    logger.info(f"File: {file_path}")
    logger.info(f"Extraction Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*80)
    logger.info("")
    
    try:
        # 读取SPMID文件
        reader = SPMidReader.from_file(file_path, verbose=False)
        track_count = reader.get_track_count
        
        logger.info(f"File Information:")
        logger.info(f"  Track Count: {track_count}")
        logger.info("")
        
        # 处理每个音轨
        for track_idx in range(track_count):
            notes = reader.get_track(track_idx)
            
            logger.info(f"Track {track_idx} ({len(notes)} notes):")
            logger.info("-" * 60)
            
            # 记录每个音符的详细信息
            for note_idx, note in enumerate(notes):
                log_note_basic_info(logger, note, track_idx, note_idx)
                log_after_touch_data(logger, note, track_idx, note_idx)
                log_hammers_data(logger, note, track_idx, note_idx)
                logger.info("")  # 空行分隔
            
            # 记录音轨统计
            log_track_summary(logger, notes, track_idx)
        
        logger.info("="*80)
        logger.info("Data extraction completed successfully!")
        logger.info("="*80)
        
        print(f"✅ Data extraction completed. Log saved to: {output_file}")
        
    except Exception as e:
        logger.error(f"❌ Error during data extraction: {e}")
        import traceback
        logger.error(traceback.format_exc())
        print(f"❌ Error: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description='Extract SPMID data to log file')
    parser.add_argument('--file', required=True, help='SPMID file path')
    parser.add_argument('--output', default='spmid_data_extraction.log', 
                       help='Output log file path (default: spmid_data_extraction.log)')
    args = parser.parse_args()
    
    if not os.path.exists(args.file):
        print(f"❌ File not found: {args.file}")
        sys.exit(1)
    
    extract_spmid_data_to_log(args.file, args.output)


if __name__ == '__main__':
    main()

