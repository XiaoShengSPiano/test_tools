#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
时间过滤模块
负责时间范围过滤功能
"""

from typing import List, Dict, Any, Optional, Tuple
from utils.logger import Logger

logger = Logger.get_logger()


class TimeFilter:
    """时间过滤器 - 负责时间范围过滤功能"""
    
    def __init__(self):
        """初始化时间过滤器"""
        self.valid_record_data = None
        self.valid_replay_data = None
        
        # 时间过滤设置
        self.time_range = None   # 时间范围过滤
    
    def set_data(self, valid_record_data=None, valid_replay_data=None):
        """设置有效数据"""
        self.valid_record_data = valid_record_data
        self.valid_replay_data = valid_replay_data
    
    def set_time_filter(self, time_range: Optional[Tuple[float, float]]) -> None:
        """
        设置时间范围过滤
        
        Args:
            time_range: 时间范围 (开始时间, 结束时间)，单位为毫秒
        """
        self.time_range = time_range
        if time_range:
            logger.info(f"✅ 时间过滤已设置: {time_range[0]:.2f}ms - {time_range[1]:.2f}ms")
        else:
            logger.info("✅ 时间过滤已清除")
    
    def get_time_filter_status(self) -> Dict[str, Any]:
        """
        获取时间过滤状态
        
        Returns:
            Dict[str, Any]: 时间过滤状态信息
        """
        if self.time_range:
            return {
                'enabled': True,
                'start_time': self.time_range[0],
                'end_time': self.time_range[1],
                'duration': self.time_range[1] - self.time_range[0]
            }
        else:
            return {
                'enabled': False,
                'start_time': None,
                'end_time': None,
                'duration': None
            }
    
    def _get_time_range_from_notes(self, notes_data) -> Tuple[float, float]:
        """从音符数据中获取时间范围"""
        start_time = float('inf')
        end_time = float('-inf')
        
        if notes_data:
            for note in notes_data:
                if len(note.hammers) > 0:
                    note_start = note.hammers.index[0] + note.offset
                    note_end = note.after_touch.index[-1] + note.offset if len(note.after_touch) > 0 else note.hammers.index[0] + note.offset
                    start_time = min(start_time, note_start)
                    end_time = max(end_time, note_end)
        
        return start_time, end_time
    
    def _get_original_time_range(self) -> Tuple[float, float]:
        """
        获取有效数据的时间范围
        
        Returns:
            Tuple[float, float]: (开始时间, 结束时间)
        """
        # 从有效录制数据中获取时间范围
        record_start, record_end = self._get_time_range_from_notes(self.valid_record_data)
        
        # 从有效播放数据中获取时间范围
        replay_start, replay_end = self._get_time_range_from_notes(self.valid_replay_data)
        
        # 合并两个时间范围
        start_time = min(record_start, replay_start)
        end_time = max(record_end, replay_end)
        
        # 处理空数据情况
        if start_time == float('inf'):
            start_time = 0
        if end_time == float('-inf'):
            end_time = 0
        
        return start_time, end_time
    
    def get_time_range(self) -> Dict[str, Any]:
        """
        获取时间范围信息
        
        Returns:
            Dict[str, Any]: 时间范围信息
        """
        original_start, original_end = self._get_original_time_range()
        
        return {
            'original_start': original_start,
            'original_end': original_end,
            'original_duration': original_end - original_start,
            'filter_start': self.time_range[0] if self.time_range else original_start,
            'filter_end': self.time_range[1] if self.time_range else original_end,
            'filter_duration': (self.time_range[1] - self.time_range[0]) if self.time_range else (original_end - original_start)
        }
    
    def get_display_time_range(self) -> Tuple[float, float]:
        """
        获取显示时间范围
        
        Returns:
            Tuple[float, float]: (开始时间, 结束时间)
        """
        if self.time_range:
            return self.time_range
        else:
            return self._get_original_time_range()
    
    def update_time_range_from_input(self, start_time: float, end_time: float) -> bool:
        """
        从输入更新时间范围
        
        Args:
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            bool: 是否更新成功
        """
        try:
            # 验证时间范围
            if start_time >= end_time:
                logger.error("开始时间必须小于结束时间")
                return False
            
            # 获取原始时间范围
            original_start, original_end = self._get_original_time_range()
            
            # 验证时间范围是否在有效范围内
            if start_time < original_start or end_time > original_end:
                logger.error(f"时间范围超出有效范围: {original_start:.2f}ms - {original_end:.2f}ms")
                return False
            
            # 设置时间过滤
            self.set_time_filter((start_time, end_time))
            return True
            
        except Exception as e:
            logger.error(f"更新时间范围失败: {e}")
            return False
    
    def get_time_range_info(self) -> Dict[str, Any]:
        """
        获取时间范围详细信息
        
        Returns:
            Dict[str, Any]: 时间范围信息
        """
        time_range = self.get_time_range()
        
        return {
            'original_range': {
                'start': time_range['original_start'],
                'end': time_range['original_end'],
                'duration': time_range['original_duration']
            },
            'current_range': {
                'start': time_range['filter_start'],
                'end': time_range['filter_end'],
                'duration': time_range['filter_duration']
            },
            'filter_enabled': self.time_range is not None
        }
    
    def reset_display_time_range(self) -> None:
        """重置显示时间范围"""
        self.time_range = None
        logger.info("✅ 时间范围已重置为原始范围")
    
    def _is_note_in_time_range(self, note) -> bool:
        """
        检查音符是否在时间范围内
        
        Args:
            note: 音符对象
            
        Returns:
            bool: 是否在时间范围内
        """
        if not self.time_range:
            return True
        
        # 获取音符的时间范围
        start_time, end_time = self._get_time_range_from_notes([note])
        if start_time == float('inf') or end_time == float('-inf'):
            return False
        
        filter_start, filter_end = self.time_range
        
        # 检查音符时间范围是否与过滤时间范围有重叠
        return not (end_time < filter_start or start_time > filter_end)
    
    def get_filtered_data(self) -> Tuple[List, List]:
        """
        获取根据时间范围过滤后的有效数据
        
        Returns:
            Tuple[List, List]: (过滤后的录制数据, 过滤后的播放数据)
        """
        if not self.valid_record_data or not self.valid_replay_data:
            logger.warning("⚠️ 有效数据不存在，返回空数据")
            return [], []
        
        # 过滤录制数据
        filtered_record_data = [
            note for note in self.valid_record_data 
            if self._is_note_in_time_range(note)
        ]
        
        # 过滤播放数据
        filtered_replay_data = [
            note for note in self.valid_replay_data 
            if self._is_note_in_time_range(note)
        ]
        
        logger.info(f"✅ 时间范围过滤完成: 录制{len(filtered_record_data)}/{len(self.valid_record_data)}个音符, 播放{len(filtered_replay_data)}/{len(self.valid_replay_data)}个音符")
        
        return filtered_record_data, filtered_replay_data
