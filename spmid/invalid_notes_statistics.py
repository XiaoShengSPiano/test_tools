#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
无效音符统计模块

负责：
1. 收集和管理无效音符信息
2. 提供统计数据查询接口
3. 转换为不同格式的输出（UI表格、摘要等）
4. 提取特定类型的无效音符（如不发声音符）

设计原则：
- 单一职责：只负责无效音符的统计管理
- 数据封装：使用对象而非字典传递数据
- 类型安全：使用数据类确保类型正确
"""

from typing import List, Dict, Any
from dataclasses import dataclass
from .spmid_reader import Note
from .types import ErrorNote


@dataclass
class InvalidNoteInfo:
    """
    单个无效音符的详细信息
    
    Attributes:
        note: 音符对象
        index: 音符在原始数据中的索引位置
        reason: 无效原因代码
        data_type: 数据类型（'录制' 或 '播放'）
    """
    note: Note
    index: int
    reason: str  # 'low_after_value' | 'short_duration' | 'empty_data' | 'silent_notes' | 'other_errors'
    data_type: str  # '录制' | '播放'


class InvalidNotesStatistics:
    """
    无效音符统计管理类
    
    管理录制和播放数据的无效音符统计信息，提供多种查询和转换接口。
    
    Attributes:
        record_total: 录制数据总音符数
        record_valid: 录制数据有效音符数
        record_invalid_list: 录制数据无效音符详细列表
        replay_total: 播放数据总音符数
        replay_valid: 播放数据有效音符数
        replay_invalid_list: 播放数据无效音符详细列表
    """
    
    def __init__(self):
        """初始化统计对象"""
        # 录制数据统计
        self.record_total = 0
        self.record_valid = 0
        self.record_invalid_list: List[InvalidNoteInfo] = []
        
        # 播放数据统计
        self.replay_total = 0
        self.replay_valid = 0
        self.replay_invalid_list: List[InvalidNoteInfo] = []
    
    @property
    def record_invalid_count(self) -> int:
        """录制数据无效音符数量"""
        return len(self.record_invalid_list)
    
    @property
    def replay_invalid_count(self) -> int:
        """播放数据无效音符数量"""
        return len(self.replay_invalid_list)
    
    @property
    def total_invalid_count(self) -> int:
        """总无效音符数量"""
        return self.record_invalid_count + self.replay_invalid_count
    
    def add_invalid_note(self, note: Note, index: int, reason: str, data_type: str) -> None:
        """
        添加一个无效音符记录
        
        Args:
            note: 无效的音符对象
            index: 音符在原始数据中的索引
            reason: 无效原因代码
                - 'duration_too_short': 持续时间过短
                - 'empty_data': 数据为空
                - 'silent_notes': 不发声（锤速为0）
                - 'other_errors': 其他错误
            data_type: 数据类型（'录制' 或 '播放'）
        """
        info = InvalidNoteInfo(
            note=note,
            index=index,
            reason=reason,
            data_type=data_type
        )
        
        if data_type == '录制':
            self.record_invalid_list.append(info)
        else:
            self.replay_invalid_list.append(info)
    
    def get_reason_counts(self, data_type: str) -> Dict[str, int]:
        """
        获取指定数据类型的各原因统计数量
        
        Args:
            data_type: 数据类型（'录制' 或 '播放'）
        
        Returns:
            Dict[str, int]: 各原因的统计数量
                {
                    'low_after_value': 压感值过低的数量,
                    'short_duration': 持续时间过短的数量,
                    'empty_data': 数据为空的数量,
                    'other_errors': 其他错误的数量
                }
        """
        invalid_list = self.record_invalid_list if data_type == '录制' else self.replay_invalid_list
        
        counts = {
            'low_after_value': 0,
            'short_duration': 0,
            'empty_data': 0,
            'other_errors': 0
        }
        
        for info in invalid_list:
            if info.reason in counts:
                counts[info.reason] += 1
            else:
                # 未知原因归类为其他错误
                counts['other_errors'] += 1
        
        return counts
    
    
    def to_table_data(self, algorithm_name: str = None) -> List[Dict[str, Any]]:
        """
        转换为UI表格数据格式
        
        将统计信息转换为适合 DataTable 显示的格式，包含录制和播放两行数据。
        
        Args:
            algorithm_name: 算法名称（可选，用于多算法模式）
        
        Returns:
            List[Dict[str, Any]]: 表格数据列表
                [
                    {
                        'algorithm_name': '算法1',  # 可选
                        'data_type': '录制数据',
                        'total_notes': 100,
                        'valid_notes': 85,
                        'invalid_notes': 15,
                        'low_after_value': 2,
                        'short_duration': 5,
                        'empty_data': 3,
                        'other_errors': 5
                    },
                    {
                        'algorithm_name': '算法1',  # 可选
                        'data_type': '回放数据',
                        ...
                    }
                ]
        """
        table_data = []
        
        # 录制数据行
        record_reasons = self.get_reason_counts('录制')
        record_row = {
            'data_type': '录制数据',
            'total_notes': self.record_total,
            'valid_notes': self.record_valid,
            'invalid_notes': self.record_invalid_count,
            'low_after_value': record_reasons['low_after_value'],
            'short_duration': record_reasons['short_duration'],
            'empty_data': record_reasons['empty_data'],
            'other_errors': record_reasons['other_errors']
        }
        
        # 如果提供了算法名称，添加到行数据中（多算法模式）
        if algorithm_name:
            record_row['algorithm_name'] = algorithm_name
        
        table_data.append(record_row)
        
        # 播放数据行
        replay_reasons = self.get_reason_counts('播放')
        replay_row = {
            'data_type': '回放数据',
            'total_notes': self.replay_total,
            'valid_notes': self.replay_valid,
            'invalid_notes': self.replay_invalid_count,
            'low_after_value': replay_reasons['low_after_value'],
            'short_duration': replay_reasons['short_duration'],
            'empty_data': replay_reasons['empty_data'],
            'other_errors': replay_reasons['other_errors']
        }
        
        if algorithm_name:
            replay_row['algorithm_name'] = algorithm_name
        
        table_data.append(replay_row)
        
        return table_data
    
    def get_summary(self) -> Dict[str, Any]:
        """
        获取统计摘要信息
        
        返回完整的统计摘要，包含录制和播放数据的所有统计信息。
        
        Returns:
            Dict[str, Any]: 统计摘要
                {
                    'record': {
                        'total': 总数,
                        'valid': 有效数,
                        'invalid': 无效数,
                        'reasons': {各原因统计}
                    },
                    'replay': {
                        'total': 总数,
                        'valid': 有效数,
                        'invalid': 无效数,
                        'reasons': {各原因统计}
                    }
                }
        """
        return {
            'record': {
                'total': self.record_total,
                'valid': self.record_valid,
                'invalid': self.record_invalid_count,
                'reasons': self.get_reason_counts('录制')
            },
            'replay': {
                'total': self.replay_total,
                'valid': self.replay_valid,
                'invalid': self.replay_invalid_count,
                'reasons': self.get_reason_counts('播放')
            }
        }
    
    def get_detailed_table_data(self, data_type: str) -> List[Dict[str, Any]]:
        """
        获取指定数据类型的详细无效音符列表
        
        Args:
            data_type: 数据类型（'录制' 或 '播放'）
        
        Returns:
            List[Dict[str, Any]]: 详细表格数据
                [
                    {
                        'data_type': '录制数据',
                        'key_id': 21,
                        'key_on_ms': '1234.56ms',
                        'key_off_ms': '2345.67ms',
                        'duration_ms': '1111.11ms',
                        'first_hammer_time_ms': '100.50ms',
                        'first_hammer_velocity': '280.50',
                        'invalid_reason': '持续时间过短'
                    },
                    ...
                ]
        """
        # 原因代码到中文描述的映射
        reason_map = {
            'low_after_value': '压感值过低',
            'short_duration': '持续时间过短',
            'empty_data': '数据为空',
            'other_errors': '其他错误'
        }
        
        # 获取对应的无效音符列表
        invalid_list = self.record_invalid_list if data_type == '录制' else self.replay_invalid_list
        
        table_data = []
        for info in invalid_list:
            note = info.note
            
            
            # 获取第一个锤击时间和锤速（如果有 hammers 数据）
            first_hammer_time_ms = None
            first_hammer_velocity = None
            # hammers.index 是时间戳数组（单位是0.1ms）
            first_hammer_time_ms = note.get_first_hammer_time()
            # hammers.values 是速度数组
            first_hammer_velocity = note.get_first_hammer_velocity()


            row = {
                'data_type': f'{data_type}数据',
                'key_id': note.id,
                'key_on_ms': f"{note.key_on_ms:.2f}ms" if note.key_on_ms is not None else 'N/A',
                'key_off_ms': f"{note.key_off_ms:.2f}ms" if note.key_off_ms is not None else 'N/A',
                'duration_ms': f"{note.duration_ms:.2f}ms" if note.duration_ms is not None else 'N/A',
                'first_hammer_time_ms': f"{first_hammer_time_ms:.2f}ms" if first_hammer_time_ms is not None else 'N/A',
                'first_hammer_velocity': f"{int(first_hammer_velocity)}" if first_hammer_velocity is not None else 'N/A',
                'invalid_reason': reason_map.get(info.reason, info.reason)
            }
            
            table_data.append(row)
        
        return table_data
    
    def __str__(self) -> str:
        """字符串表示"""
        summary = self.get_summary()
        return (
            f"InvalidNotesStatistics(\n"
            f"  录制: {summary['record']['valid']}/{summary['record']['total']} 有效, "
            f"{summary['record']['invalid']} 无效\n"
            f"  播放: {summary['replay']['valid']}/{summary['replay']['total']} 有效, "
            f"{summary['replay']['invalid']} 无效\n"
            f")"
        )
    
    def __repr__(self) -> str:
        """开发者表示"""
        return self.__str__()

