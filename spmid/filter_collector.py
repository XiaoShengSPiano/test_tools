#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据过滤收集器模块

职责：
1. 在数据加载阶段收集被过滤的音符信息
2. 记录过滤原因和详细信息
3. 提供查询接口供统计使用

设计原则：
- 单一职责：只负责过滤信息的收集
- 轻量级：不处理复杂的业务逻辑
- 清晰的接口：便于集成到现有系统
"""

from typing import List
from dataclasses import dataclass
import numpy as np
from .spmid_reader import OptimizedNote, Note
from utils.logger import Logger

logger = Logger.get_logger()


@dataclass
class FilteredNoteInfo:
    """
    被过滤音符的信息
    
    Attributes:
        note: 被过滤的音符对象（OptimizedNote或Note）
        index: 音符在原始列表中的索引
        reason: 过滤原因代码
        detail: 过滤详情（可选）
    """
    note: any  # OptimizedNote 或 Note
    index: int
    reason: str  # 'low_after_value' | 'short_duration' | 'empty_data'
    detail: str = ""  # 详细说明


class FilterCollector:
    """
    过滤信息收集器
    
    在数据加载阶段收集被过滤的音符信息，记录：
    - 被过滤的音符对象
    - 过滤原因
    - 详细信息（如具体的数值）
    
    Usage:
        collector = FilterCollector()
        
        for i, note in enumerate(notes):
            if should_filter(note):
                collector.add_filtered_note(note, i, reason, detail)
        
        # 获取过滤统计
        stats = collector.get_statistics()
    """
    
    def __init__(self):
        """初始化收集器"""
        self.record_filtered: List[FilteredNoteInfo] = []
        self.replay_filtered: List[FilteredNoteInfo] = []
        self._current_data_type = None  # 'record' or 'replay'
    
    def set_data_type(self, data_type: str) -> None:
        """
        设置当前处理的数据类型
        
        Args:
            data_type: 'record' 或 'replay'
        """
        if data_type not in ['record', 'replay']:
            raise ValueError(f"Invalid data_type: {data_type}")
        self._current_data_type = data_type
    
    def add_filtered_note(self, note: any, index: int, reason: str, detail: str = "") -> None:
        """
        添加一个被过滤的音符
        
        Args:
            note: 被过滤的音符对象
            index: 音符在原始列表中的索引
            reason: 过滤原因代码
                - 'low_after_value': 压感值过低（after_touch最大值<500）
                - 'short_duration': 持续时间过短（<30ms）
                - 'empty_data': 数据为空
            detail: 详细说明（可选）
        """
        if self._current_data_type is None:
            raise RuntimeError("必须先调用set_data_type设置数据类型")
        
        info = FilteredNoteInfo(
            note=note,
            index=index,
            reason=reason,
            detail=detail
        )
        
        if self._current_data_type == 'record':
            self.record_filtered.append(info)
        else:
            self.replay_filtered.append(info)
    
    def get_filtered_count(self, data_type: str = None) -> int:
        """
        获取被过滤的音符数量
        
        Args:
            data_type: 'record', 'replay', 或 None（返回总数）
        
        Returns:
            int: 被过滤的音符数量
        """
        if data_type == 'record':
            return len(self.record_filtered)
        elif data_type == 'replay':
            return len(self.replay_filtered)
        else:
            return len(self.record_filtered) + len(self.replay_filtered)
    
    def get_filtered_notes(self, data_type: str) -> List[FilteredNoteInfo]:
        """
        获取指定类型的被过滤音符列表
        
        Args:
            data_type: 'record' 或 'replay'
        
        Returns:
            List[FilteredNoteInfo]: 被过滤的音符列表
        """
        if data_type == 'record':
            return self.record_filtered.copy()
        elif data_type == 'replay':
            return self.replay_filtered.copy()
        else:
            raise ValueError(f"Invalid data_type: {data_type}")
    
    def get_statistics(self) -> dict:
        """
        获取过滤统计信息
        
        Returns:
            dict: 统计信息
                {
                    'record': {
                        'total_filtered': 总数,
                        'low_after_value': 数量,
                        'short_duration': 数量,
                        'empty_data': 数量
                    },
                    'replay': {...}
                }
        """
        def count_by_reason(filtered_list):
            counts = {
                'low_after_value': 0,
                'short_duration': 0,
                'empty_data': 0
            }
            for info in filtered_list:
                if info.reason in counts:
                    counts[info.reason] += 1
            return counts
        
        return {
            'record': {
                'total_filtered': len(self.record_filtered),
                **count_by_reason(self.record_filtered)
            },
            'replay': {
                'total_filtered': len(self.replay_filtered),
                **count_by_reason(self.replay_filtered)
            }
        }
    
    def clear(self) -> None:
        """清空收集的数据"""
        self.record_filtered.clear()
        self.replay_filtered.clear()
        self._current_data_type = None
    
    def __str__(self) -> str:
        """字符串表示"""
        stats = self.get_statistics()
        return (
            f"FilterCollector(\n"
            f"  录制: 过滤 {stats['record']['total_filtered']} 个音符\n"
            f"  播放: 过滤 {stats['replay']['total_filtered']} 个音符\n"
            f")"
        )
