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
        
        self.global_time_offset = 0.0
        
        logger.info(f"✅ 全局时间偏移量设为0 (按键匹配算法已有动态阈值容错，无需额外偏移)")
        
        
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
    
    
    def get_global_time_offset(self) -> float:
        """
        获取全局时间偏移量
        
        Returns:
            float: 全局时间偏移量
        """
        return self.global_time_offset
