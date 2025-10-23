#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SPMID时序对齐器

负责SPMID数据的时序对齐，包括：
- 动态时间窗口DTW
- 简单全局DTW
- 时间偏移量计算
"""

from .spmid_reader import Note
from typing import List, Optional
from utils.logger import Logger

import numpy as np
from dtw import dtw

logger = Logger.get_logger()


class TimeAligner:
    """SPMID时序对齐器类"""
    
    def __init__(self):
        """初始化时序对齐器"""
        self.global_time_offset: float = 0.0
    
    def calculate_global_time_offset(self, record_data: List[Note], replay_data: List[Note]) -> float:
        """
        计算全局时间偏移量
        
        Args:
            record_data: 录制数据
            replay_data: 播放数据
            
        Returns:
            float: 全局时间偏移量
        """
        logger.info("⏰ 开始计算全局时间偏移量")
        
        # 收集时间戳
        record_times = self._extract_hammer_times(record_data)
        replay_times = self._extract_hammer_times(replay_data)
        
        if not record_times or not replay_times:
            raise RuntimeError("录制或播放数据中没有有效的锤子时间戳，无法进行时序对齐")
        
        # 对时间戳进行排序 TODO
        record_times.sort()
        replay_times.sort()
        
        # 根据数据量选择DTW策略
        total_notes = len(record_times) + len(replay_times)
        # TODO 阈值需要根据数据量动态调整
        DTW_THRESHOLD = 200  # 阈值：200个音符
        
        if total_notes < DTW_THRESHOLD:
            # 小数据集：使用简单的全局DTW
            logger.debug(f"数据量较小（{total_notes}个音符），使用简单的全局DTW对齐")
            self.global_time_offset = self._calculate_simple_dtw_offset(record_times, replay_times)
        else:
            # 大数据集：使用动态时间窗口DTW
            logger.debug(f"数据量较大（{total_notes}个音符），使用动态时间窗口DTW对齐")
            self.global_time_offset = self._calculate_dynamic_window_offset(record_times, replay_times)
        
        return self.global_time_offset
    
    def _extract_hammer_times(self, notes: List[Note]) -> List[float]:
        """
        提取音符的第一个锤子时间戳
        
        Args:
            notes: 音符列表
            
        Returns:
            List[float]: 时间戳列表
        """
        times = []
        for note in notes:
            if len(note.hammers) > 0:
                first_hammer_time = note.hammers.index[0] + note.offset
                times.append(first_hammer_time)
        return times
    
    def _calculate_simple_dtw_offset(self, record_times: List[float], replay_times: List[float]) -> float:
        """
        使用简单的全局DTW算法计算时间偏移量
        
        Args:
            record_times: 录制时间戳列表
            replay_times: 播放时间戳列表
            
        Returns:
            float: 时间偏移量
        """
        logger.debug(f"使用简单全局DTW对齐：录制{len(record_times)}个音符, 播放{len(replay_times)}个音符")
        return self._calculate_dtw_offset(record_times, replay_times, "简单DTW")
    
    def _calculate_dynamic_window_offset(self, record_times: List[float], replay_times: List[float]) -> float:
        """
        使用动态时间窗口DTW算法计算时间偏移量
        
        Args:
            record_times: 录制时间戳列表
            replay_times: 播放时间戳列表
            
        Returns:
            float: 时间偏移量
        """
        try:
            # 将数据分成多个时间段
            num_segments = min(5, len(record_times) // 2)
            if num_segments < 1:
                num_segments = 1
            
            logger.debug(f"使用动态时间窗口对齐，分为{num_segments}个时间段")
            
            # 计算每个时间段的偏移量
            segment_offsets = []
            
            for i in range(num_segments):
                # 计算当前时间段的录制数据
                start_idx = i * len(record_times) // num_segments
                end_idx = (i + 1) * len(record_times) // num_segments
                segment_record = record_times[start_idx:end_idx]
                
                if len(segment_record) < 2:
                    continue
                    
                # 计算当前时间段的时间范围
                segment_start = segment_record[0]
                segment_end = segment_record[-1]
                segment_duration = segment_end - segment_start
                
                # 定义时间窗口
                window_size = segment_duration * 2
                window_start = segment_start - window_size
                window_end = segment_end + window_size
                
                # 在播放数据中找到对应时间窗口的数据
                segment_replay = [t for t in replay_times if window_start <= t <= window_end]
                
                if len(segment_replay) >= 2:
                    # 对当前时间段进行DTW对齐
                    try:
                        offset = self._calculate_dtw_offset(segment_record, segment_replay)
                        if offset is not None:
                            segment_offsets.append(offset)
                            logger.debug(f"时间段{i+1}: 录制{len(segment_record)}个音符, 播放{len(segment_replay)}个音符, 偏移量={offset:.2f}")
                    except Exception as e:
                        logger.debug(f"时间段{i+1}的DTW对齐失败: {e}")
                        continue
                else:
                    logger.debug(f"时间段{i+1}: 播放数据不足，跳过对齐")
            
            # 返回所有时间段偏移量的中位数
            if segment_offsets:
                global_offset = np.median(segment_offsets)
                logger.debug(f"动态时间窗口对齐完成，{len(segment_offsets)}个有效时间段，全局偏移量={global_offset:.2f}")
                return global_offset
            else:
                error_msg = "所有时间段的DTW对齐都失败，无法计算全局时间偏移量"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
                
        except Exception as e:
            error_msg = f"动态时间窗口对齐失败: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
    
    def _calculate_dtw_offset(self, record_times: List[float], replay_times: List[float], algorithm_type: str = "DTW") -> float:
        """
        使用DTW算法计算时间偏移量（通用版本）
        
        Args:
            record_times: 录制时间戳列表
            replay_times: 播放时间戳列表
            algorithm_type: 算法类型标识，用于日志记录（如"简单DTW"、"DTW"等）
            
        Returns:
            float: 时间偏移量
        """
        try:
            # 转换为numpy数组并重塑为列向量
            record_array = np.array(record_times).reshape(-1, 1)
            replay_array = np.array(replay_times).reshape(-1, 1)
            
            # 执行DTW对齐
            alignment = dtw(record_array, replay_array, keep_internals=True)
            
            # 计算偏移量
            offsets = []
            for i, j in zip(alignment.index1, alignment.index2):
                if i < len(record_times) and j < len(replay_times):
                    offset = replay_times[j] - record_times[i]
                    offsets.append(offset)
            
            if not offsets:
                raise RuntimeError(f"{algorithm_type}对齐未产生有效的偏移量数据")
            
            # 使用中位数作为全局偏移量
            global_offset = np.median(offsets)
            logger.debug(f"{algorithm_type}对齐完成，计算偏移量: 中位数={global_offset:.2f}, 均值={np.mean(offsets):.2f}, 标准差={np.std(offsets):.2f}")
            return global_offset

        except Exception as e:
            error_msg = f"{algorithm_type}时间对齐算法执行失败: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
    
    def get_global_time_offset(self) -> float:
        """
        获取全局时间偏移量
        
        Returns:
            float: 全局时间偏移量
        """
        return self.global_time_offset
