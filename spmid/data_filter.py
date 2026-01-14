#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SPMID数据过滤器

负责SPMID数据的过滤和验证，包括：
- 音符有效性检查
- 音符数据验证（持续时间、锤速、数据完整性）

重构后职责更清晰：
- 只负责验证音符的有效性
- 统计信息由 InvalidNotesStatistics 类管理
"""

from .spmid_reader import Note
from .invalid_notes_statistics import InvalidNotesStatistics
from typing import List, Tuple
from utils.logger import Logger

logger = Logger.get_logger()


class DataFilter:
    """
    SPMID数据过滤器类
    
    职责：对音符进行有效性检查和过滤
    """
    
    def filter_notes(
        self, 
        record_data: List[Note], 
        replay_data: List[Note]
    ) -> Tuple[List[Note], List[Note], InvalidNotesStatistics]:
        """
        过滤音符数据
        
        对录制和播放数据进行有效性检查，过滤掉无效的音符。
        使用 InvalidNotesStatistics 对象管理统计信息，提供更清晰的接口。
        
        Args:
            record_data: 录制数据，包含所有录制的音符
            replay_data: 播放数据，包含所有播放的音符
            
        Returns:
            Tuple[List[Note], List[Note], InvalidNotesStatistics]:
                - valid_record_data: 过滤后的有效录制音符列表
                - valid_replay_data: 过滤后的有效播放音符列表  
                - statistics: 无效音符统计信息对象
        """
        # 创建统计对象
        statistics = InvalidNotesStatistics()
        
        # 过滤录制数据
        valid_record_data = self._filter_single_track(
            record_data, '录制', statistics
        )
        
        # 过滤播放数据
        valid_replay_data = self._filter_single_track(
            replay_data, '播放', statistics
        )
        
        # 记录日志
        summary = statistics.get_summary()
        logger.info(
            f"数据过滤完成: "
            f"录制 {summary['record']['valid']}/{summary['record']['total']}, "
            f"播放 {summary['replay']['valid']}/{summary['replay']['total']}"
        )
        
        return valid_record_data, valid_replay_data, statistics
    
    def _filter_single_track(
        self, 
        notes: List[Note], 
        data_type: str,
        statistics: InvalidNotesStatistics
    ) -> List[Note]:
        """
        过滤单个轨道的音符
        
        对单个数据源（录制或播放）的音符进行有效性检查。
        有效的音符返回，无效的音符记录到统计对象中。
        
        Args:
            notes: 待过滤的音符列表
            data_type: 数据类型标识（"录制" 或 "播放"）
            statistics: 统计信息对象，用于记录无效音符
            
        Returns:
            List[Note]: 通过有效性检查的音符列表
        """
        valid_notes = []
        
        # 设置总数
        if data_type == '录制':
            statistics.record_total = len(notes)
        else:
            statistics.replay_total = len(notes)
        
        # 逐个检查音符
        for i, note in enumerate(notes):
            is_valid, reason = self._validate_note(note)
            if is_valid:
                valid_notes.append(note)
            else:
                # 记录无效音符到统计对象
                statistics.add_invalid_note(note, i, reason, data_type)
        
        # 设置有效数
        if data_type == '录制':
            statistics.record_valid = len(valid_notes)
        else:
            statistics.replay_valid = len(valid_notes)
        
        return valid_notes
    
    def _validate_note(self, note: Note) -> Tuple[bool, str]:
        """
        验证单个音符的有效性
        
        对单个音符进行全面的有效性检查，包括数据完整性、锤速、持续时间等条件。
        
        Args:
            note: 待检查的音符对象
            
        Returns:
            Tuple[bool, str]: (是否有效, 无效原因代码)
                无效原因代码：
                - 'empty_data': 数据为空
                - 'silent_notes': 不发声（锤速为0）
                - 'duration_too_short': 持续时间过短
                - 'other_errors': 其他错误
                - 'valid': 有效
        """
        try:
            # 1. 检查数据完整性
            if len(note.after_touch) == 0 or len(note.hammers) == 0:
                return False, 'empty_data'
            
            # 2. 检查锤速（第一个锤击的速度）
            # 获取时间上最早的锤速值
            min_timestamp = note.hammers.index.min()
            first_hammer_velocity = note.hammers.loc[min_timestamp]
            
            if first_hammer_velocity == 0:
                return False, 'silent_notes'
            
            # 3. 检查持续时间
            try:
                duration_ms = note.key_off_ms - note.key_on_ms
                if duration_ms < 10:  # 最短持续时间：10ms
                    return False, 'duration_too_short'
            except (AttributeError, TypeError) as e:
                raise ValueError(f"音符ID {note.id} 的时间数据无效: {e}") from e
            
            # 所有检查通过
            return True, 'valid'
            
        except Exception as e:
            # 未预期的错误
            logger.debug(f"验证音符 {note.id} 时发生错误: {e}")
            return False, 'other_errors'
