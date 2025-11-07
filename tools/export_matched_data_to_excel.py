#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
导出匹配后的按键数据（锤速与时延）到Excel表格

使用方法:
    python tools/export_matched_data_to_excel.py <spmid_file_path> [output_excel_path]

示例:
    python tools/export_matched_data_to_excel.py data/example.spmid output.xlsx
"""

import sys
import os
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from spmid.spmid_reader import SPMidReader, Note
from spmid.spmid_analyzer import SPMIDAnalyzer
from utils.logger import Logger

logger = Logger.get_logger()


def iter_hammer_rows(pair_id: int, key_id: int, data_type: str, note: Note) -> List[Dict[str, Any]]:
    """
    生成某个音符的第一个锤速行（通过阈值检查的锤速）
    
    注意：匹配对中的音符对象来自过滤后的有效数据，这些音符的第一个锤速已经通过了阈值检查
    （PWM值 >= 阈值）。因此，这里导出的锤速值就是用于阈值检查并通过检查的那个锤速值。

    Args:
        pair_id: 匹配对序号（从1开始）
        key_id: 键ID
        data_type: 'record' 或 'replay'
        note: 音符对象（来自过滤后的有效数据，已通过阈值检查）

    Returns:
        List[Dict[str, Any]]: 只包含第一个锤速的一行数据（该锤速已通过阈值检查）
    """
    rows: List[Dict[str, Any]] = []
    if note is None or note.hammers is None or len(note.hammers) == 0:
        return rows
    
    # 获取时间上最早的锤速值（第一个锤速）
    # 注意：hammers Series的index是时间戳，需要找到最小时间戳对应的锤速值
    # 这个锤速值是在数据过滤阶段用于阈值检查的锤速，并且已经通过了阈值检查
    min_timestamp = note.hammers.index.min()
    first_hammer_velocity_raw = note.hammers.loc[min_timestamp]
    # 如果返回Series（多个相同时间戳），取第一个值
    if isinstance(first_hammer_velocity_raw, pd.Series):
        first_hammer_velocity = first_hammer_velocity_raw.iloc[0]
    else:
        first_hammer_velocity = first_hammer_velocity_raw
    
    # 导出第一个锤速值（该值已经通过阈值检查，匹配对中的音符来自过滤后的有效数据）
    # 理论上锤速不应该为0（因为已经通过过滤），但为了安全起见，仍然检查
    if first_hammer_velocity != 0:
        rows.append({
            '匹配对序号': pair_id,
            '键ID': key_id,
            '数据类型': '录制' if data_type == 'record' else '播放',
            '锤速值': int(first_hammer_velocity)  # 这是通过阈值检查的锤速值
        })
    
    return rows


def calculate_note_times(note: Note) -> tuple:
    """
    计算音符的按键开始和结束时间
    
    Args:
        note: 音符对象
        
    Returns:
        tuple: (keyon_time, keyoff_time) 单位：0.1ms
    """
    if note.after_touch is None or len(note.after_touch) == 0:
        return 0.0, 0.0
    
    keyon_time = note.after_touch.index[0] + note.offset
    keyoff_time = note.after_touch.index[-1] + note.offset
    
    return keyon_time, keyoff_time


def export_matched_data_to_excel(spmid_file_path: str, output_excel_path: str = None) -> str:
    """
    导出匹配后的按键数据（锤速与时延）到Excel表格
    
    Args:
        spmid_file_path: SPMID文件路径
        output_excel_path: 输出Excel文件路径（可选，默认自动生成）
        
    Returns:
        str: 输出Excel文件路径
    """
    # 检查文件是否存在
    if not os.path.exists(spmid_file_path):
        raise FileNotFoundError(f"SPMID文件不存在: {spmid_file_path}")
    
    logger.info(f"📂 开始处理SPMID文件: {spmid_file_path}")
    
    # 1. 加载SPMID文件
    reader = SPMidReader.from_file(spmid_file_path, verbose=False)
    
    if reader.get_track_count < 2:
        raise ValueError("SPMID文件必须包含至少2个轨道")
    
    # 获取录制和播放数据
    record_data = reader.get_track(0)  # 录制数据（实际演奏）
    replay_data = reader.get_track(1)  # 播放数据（MIDI回放）
    
    logger.info(f"📊 加载数据: 录制数据{len(record_data)}个音符, 播放数据{len(replay_data)}个音符")
    
    # 2. 执行分析
    analyzer = SPMIDAnalyzer()
    analyzer.analyze(record_data, replay_data)
    
    # 3. 获取匹配对
    matched_pairs = analyzer.note_matcher.get_matched_pairs()
    logger.info(f"✅ 成功匹配 {len(matched_pairs)} 对按键")
    
    if len(matched_pairs) == 0:
        logger.warning("⚠️ 没有匹配的按键对，无法导出数据")
        return None
    
    # 4. 提取数据
    # 表1：每个匹配对的第一个锤速值（通过阈值检查的锤速）
    # 注意：matched_pairs中的音符对象来自过滤后的有效数据（valid_record_data和valid_replay_data），
    # 这些音符的第一个锤速已经通过了阈值检查（PWM值 >= 阈值），因此导出的锤速值就是通过阈值检查的那个锤速
    hammer_rows: List[Dict[str, Any]] = []
    
    for pair_idx, (record_idx, replay_idx, record_note, replay_note) in enumerate(matched_pairs, 1):
        # 提取录制和播放音符的第一个锤速值（该值已经通过阈值检查）
        hammer_rows.extend(iter_hammer_rows(pair_idx, record_note.id, 'record', record_note))
        hammer_rows.extend(iter_hammer_rows(pair_idx, record_note.id, 'replay', replay_note))
    
    # 5. 获取偏移对齐数据并按按键ID分组统计（计算方差而不是标准差）
    offset_data = analyzer.note_matcher.get_offset_alignment_data()
    
    # 按按键ID分组有效匹配的偏移数据（只使用keyon_offset的绝对值）
    from collections import defaultdict
    import numpy as np
    
    key_groups = defaultdict(list)
    for item in offset_data:
        key_id = item.get('key_id', 'N/A')
        keyon_offset_abs = abs(item.get('keyon_offset', 0))  # 只使用keyon_offset的绝对值
        key_groups[key_id].append(keyon_offset_abs)
    
    # 转换为偏移对齐分析表格格式（标准差改为方差）
    alignment_stats_rows: List[Dict[str, Any]] = []
    
    for key_id, offsets in key_groups.items():
        if offsets:
            median_val = np.median(offsets) / 10.0  # 转换为ms
            mean_val = np.mean(offsets) / 10.0  # 转换为ms
            # 计算总体方差（分母n，ddof=0），不是标准差
            variance_val = np.var(offsets, ddof=0) / 100.0  # 转换为ms²（(0.1ms)² -> ms²）
            
            alignment_stats_rows.append({
                '键位ID': key_id,
                '配对数': len(offsets),
                '中位数(ms)': round(median_val, 2),
                '均值(ms)': round(mean_val, 2),
                '方差(ms²)': round(variance_val, 2),
                '状态': 'matched'
            })
    
    # 6. 创建DataFrame
    hammer_df = pd.DataFrame(hammer_rows)
    alignment_stats_df = pd.DataFrame(alignment_stats_rows)
    
    # 7. 生成输出文件路径
    if output_excel_path is None:
        # 自动生成文件名：原文件名_匹配数据_时间戳.xlsx
        base_name = Path(spmid_file_path).stem
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_excel_path = f"{base_name}_匹配数据_{timestamp}.xlsx"
    
    # 确保输出目录存在
    output_dir = Path(output_excel_path).parent
    if output_dir and not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
    
    # 8. 导出到Excel（两个工作表：第一个锤速数据、偏移对齐分析）
    with pd.ExcelWriter(output_excel_path, engine='openpyxl') as writer:
        hammer_df.to_excel(writer, sheet_name='第一个锤速数据', index=False)
        alignment_stats_df.to_excel(writer, sheet_name='偏移对齐分析', index=False)
    
    logger.info(f"✅ 数据已成功导出到: {output_excel_path}")
    logger.info(f"📊 共导出 {len(matched_pairs)} 个匹配对的数据")
    logger.info(f"📊 第一个锤速数据总数: {len(hammer_rows)}")
    
    return output_excel_path


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python tools/export_matched_data_to_excel.py <spmid_file_path> [output_excel_path]")
        print("\n示例:")
        print("  python tools/export_matched_data_to_excel.py data/example.spmid")
        print("  python tools/export_matched_data_to_excel.py data/example.spmid output.xlsx")
        sys.exit(1)
    
    spmid_file_path = sys.argv[1]
    output_excel_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    try:
        output_path = export_matched_data_to_excel(spmid_file_path, output_excel_path)
        if output_path:
            print(f"\n✅ 成功！数据已导出到: {output_path}")
        else:
            print("\n⚠️ 警告：没有匹配的按键对，无法导出数据")
    except Exception as e:
        logger.error(f"❌ 导出失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        print(f"\n❌ 错误: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

