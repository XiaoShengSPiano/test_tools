#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试DTW对齐算法，输出详细的对齐结果
"""

import sys
import numpy as np
from dtw import dtw

# 导入SPMID相关模块
from spmid.spmid_reader import SPMidReader
from spmid.time_aligner import TimeAligner
from utils.logger import Logger

logger = Logger.get_logger()


def read_spmid_file(file_path):
    """读取SPMID文件"""
    try:
        reader = SPMidReader(file_path, verbose=True)
        
        # 获取轨道数量
        track_count = len(reader.tracks)
        logger.info(f"✅ SPMID文件读取成功，共 {track_count} 个轨道")
        
        if track_count < 2:
            logger.error(f"❌ 轨道数量不足：需要至少2个轨道（录制+播放），当前只有 {track_count} 个")
            return None, None
        
        # 获取录制和播放数据
        record_data = reader.get_track(0)
        replay_data = reader.get_track(1)
        
        logger.info(f"📊 录制数据: {len(record_data)} 个音符")
        logger.info(f"📊 播放数据: {len(replay_data)} 个音符")
        
        return record_data, replay_data
        
    except Exception as e:
        logger.error(f"❌ 读取SPMID文件失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None, None


def extract_hammer_times(notes):
    """提取音符的第一个锤子时间戳"""
    times = []
    for note in notes:
        if len(note.hammers) > 0:
            first_hammer_time = note.hammers.index[0] + note.offset
            times.append(first_hammer_time)
    return times


def test_dtw_alignment_detailed(record_data, replay_data):
    """测试DTW对齐，输出详细信息"""
    
    logger.info("="*80)
    logger.info("开始测试DTW对齐算法")
    logger.info("="*80)
    
    # 提取时间戳
    record_times = extract_hammer_times(record_data)
    replay_times = extract_hammer_times(replay_data)
    
    logger.info(f"\n📊 时间戳提取结果:")
    logger.info(f"录制时间戳数量: {len(record_times)}")
    logger.info(f"播放时间戳数量: {len(replay_times)}")
    
    # 输出完整的时间戳序列
    logger.info(f"\n" + "="*80)
    logger.info(f"完整录制时间戳序列 ({len(record_times)}个):")
    logger.info(f"="*80)
    for idx, time in enumerate(record_times):
        logger.info(f"录制[{idx:4d}]: {time:10.2f}ms")
    
    logger.info(f"\n" + "="*80)
    logger.info(f"完整播放时间戳序列 ({len(replay_times)}个):")
    logger.info(f"="*80)
    for idx, time in enumerate(replay_times):
        logger.info(f"播放[{idx:4d}]: {time:10.2f}ms")
    
    # 执行DTW对齐
    logger.info(f"\n🔄 执行DTW对齐...")
    
    record_array = np.array(record_times).reshape(-1, 1)
    replay_array = np.array(replay_times).reshape(-1, 1)
    
    alignment = dtw(record_array, replay_array, keep_internals=True)
    
    # 输出alignment详细信息
    logger.info(f"\n📊 DTW对齐结果详细信息:")
    logger.info(f"="*80)
    
    logger.info(f"\nalignment对象属性:")
    logger.info(f"- distance (总距离): {alignment.distance}")
    if hasattr(alignment, 'normalized_distance'):
        logger.info(f"- normalized_distance (归一化距离): {alignment.normalized_distance}")
    
    logger.info(f"\n对齐路径长度:")
    logger.info(f"- index1 (录制索引序列长度): {len(alignment.index1)}")
    logger.info(f"- index2 (播放索引序列长度): {len(alignment.index2)}")
    
    # 输出完整的对齐序列
    logger.info(f"\n" + "="*80)
    logger.info(f"完整DTW对齐序列 ({len(alignment.index1)}对):")
    logger.info(f"="*80)
    logger.info(f"{'序号':<8} {'录制索引':<10} {'播放索引':<10} {'录制时间(ms)':<15} {'播放时间(ms)':<15} {'时间差(ms)':<12}")
    logger.info(f"-"*90)
    
    for idx in range(len(alignment.index1)):
        i = alignment.index1[idx]
        j = alignment.index2[idx]
        
        if i < len(record_times) and j < len(replay_times):
            record_time = record_times[i]
            replay_time = replay_times[j]
            offset = replay_time - record_time
            
            logger.info(f"{idx:<8} {i:<10} {j:<10} {record_time:<15.2f} {replay_time:<15.2f} {offset:<12.2f}")
    
    # 计算偏移量统计
    logger.info(f"\n📊 偏移量统计:")
    logger.info(f"="*80)
    
    offsets = []
    for i, j in zip(alignment.index1, alignment.index2):
        if i < len(record_times) and j < len(replay_times):
            offset = replay_times[j] - record_times[i]
            offsets.append(offset)
    
    if offsets:
        logger.info(f"总对齐对数: {len(offsets)}")
        logger.info(f"偏移量中位数: {np.median(offsets):.2f}ms")
        logger.info(f"偏移量平均值: {np.mean(offsets):.2f}ms")
        logger.info(f"偏移量标准差: {np.std(offsets):.2f}ms")
        logger.info(f"偏移量最小值: {np.min(offsets):.2f}ms")
        logger.info(f"偏移量最大值: {np.max(offsets):.2f}ms")
        logger.info(f"偏移量范围: {np.max(offsets) - np.min(offsets):.2f}ms")
        
        # 输出偏移量分布
        logger.info(f"\n偏移量分布:")
        bins = [0, 10, 20, 50, 100, 200, 500, 1000, float('inf')]
        bin_labels = ['0-10ms', '10-20ms', '20-50ms', '50-100ms', '100-200ms', '200-500ms', '500-1000ms', '>1000ms']
        
        for i in range(len(bins)-1):
            count = sum(1 for o in offsets if bins[i] <= abs(o) < bins[i+1])
            percentage = count / len(offsets) * 100
            logger.info(f"  {bin_labels[i]:<15}: {count:>5}个 ({percentage:>5.1f}%)")
        
        # 输出全局时间偏移量（中位数）
        global_offset = np.median(offsets)
        logger.info(f"\n✅ 全局时间偏移量 (global_time_offset): {global_offset:.2f}ms")
        logger.info(f"   含义: 播放时间轴整体比录制时间轴{'晚' if global_offset > 0 else '早'} {abs(global_offset):.2f}ms")
    
    return alignment, offsets


def main():
    """主函数"""
    # 检查命令行参数
    if len(sys.argv) < 2:
        logger.error("用法: python test_dtw_alignment.py <spmid文件路径>")
        logger.error("示例: python test_dtw_alignment.py test/2025-08-13C大调音阶.spmid")
        return
    
    file_path = sys.argv[1]
    
    logger.info(f"📂 开始测试DTW对齐，读取SPMID文件: {file_path}")
    
    # 读取SPMID文件
    record_data, replay_data = read_spmid_file(file_path)
    
    if record_data is None or replay_data is None:
        logger.error("❌ 无法读取数据，终止测试")
        return
    
    # 测试DTW对齐
    alignment, offsets = test_dtw_alignment_detailed(record_data, replay_data)
    
    logger.info(f"\n" + "="*80)
    logger.info("测试完成")
    logger.info("="*80)


if __name__ == "__main__":
    main()

