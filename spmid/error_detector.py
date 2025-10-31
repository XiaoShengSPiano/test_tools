#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SPMID异常检测器

负责SPMID数据的异常检测，包括：
- 多锤检测
- 丢锤检测
- 不发声检测
- 异常音符创建
"""

from .spmid_reader import Note
from .types import ErrorNote
from typing import List, Tuple, Dict
from utils.logger import Logger

logger = Logger.get_logger()


class ErrorDetector:
    """SPMID异常检测器类"""
    
    def __init__(self, global_time_offset: float = 0.0):
        """
        初始化异常检测器
        
        Args:
            global_time_offset: 全局时间偏移量（已废弃，固定为0）
        """
        self.global_time_offset = 0.0  # 固定为0，不再使用全局偏移
        self.multi_hammers: List[ErrorNote] = []
        self.drop_hammers: List[ErrorNote] = []
        self.silent_hammers: List[ErrorNote] = []
    
    def analyze_hammer_issues(self, record_data: List[Note], replay_data: List[Note], 
                            matched_pairs: List[Tuple[int, int, Note, Note]]) -> Tuple[List[ErrorNote], List[ErrorNote]]:
        """
        分析多锤和丢锤问题
        
        Args:
            record_data: 录制数据
            replay_data: 播放数据
            matched_pairs: 匹配对列表
            
        Returns:
            Tuple[List[ErrorNote], List[ErrorNote]]: (drop_hammers, multi_hammers)
        """
        # 分析未匹配的音符
        self._analyze_unmatched_notes(record_data, replay_data, matched_pairs)
        
        return self.drop_hammers, self.multi_hammers
    
    def _analyze_unmatched_notes(self, record_data: List[Note], replay_data: List[Note], 
                               matched_pairs: List[Tuple[int, int, Note, Note]]) -> None:
        """
        分析未匹配的音符，识别丢锤和多锤异常
        
        Args:
            record_data: 录制数据
            replay_data: 播放数据
            matched_pairs: 匹配对列表
        """
        # 获取已匹配的索引
        matched_record_indices = {pair[0] for pair in matched_pairs}
        matched_replay_indices = {pair[1] for pair in matched_pairs}
        
        # 分析录制数据中未匹配的音符（丢锤）
        for i, record_note in enumerate(record_data):
            if i not in matched_record_indices:
                self._handle_drop_hammer_case(record_note, i)
        
        # 分析播放数据中未匹配的音符（多锤）
        for i, replay_note in enumerate(replay_data):
            if i not in matched_replay_indices:
                self._handle_multi_hammer_case(replay_note, i)
    
    def _handle_drop_hammer_case(self, note: Note, index: int) -> None:
        """
        处理丢锤情况
        
        Args:
            note: 音符对象
            index: 音符索引
        """
        note_info = self._extract_note_info(note, index)
        error_note = self._create_error_note_with_stats(note, note_info, "丢锤")
        self.drop_hammers.append(error_note)
    
    def _handle_multi_hammer_case(self, note: Note, index: int) -> None:
        """
        处理多锤情况
        
        Args:
            note: 音符对象
            index: 音符索引
        """
        note_info = self._extract_note_info(note, index)
        error_note = self._create_error_note_with_stats(note, note_info, "多锤")
        self.multi_hammers.append(error_note)
    
    def _extract_note_info(self, note: Note, index: int) -> Dict:
        """
        提取音符基本信息
        
        Args:
            note: 音符对象
            index: 音符索引
            
        Returns:
            Dict: 音符信息字典
        """
        # 计算绝对时间戳，考虑全局时间偏移
        absolute_keyon = note.after_touch.index[0] + note.offset + self.global_time_offset
        absolute_keyoff = note.after_touch.index[-1] + note.offset + self.global_time_offset
        
        return {
            'keyon': absolute_keyon,
            'keyoff': absolute_keyoff,
            'key_id': note.id,
            'index': index,
            'relative_keyon': note.after_touch.index[0] + note.offset,
            'relative_keyoff': note.after_touch.index[-1] + note.offset
        }
    
    def _create_error_note_with_stats(self, note: Note, note_info: Dict, error_type: str) -> ErrorNote:
        """
        创建错误音符对象并添加统计信息
        
        Args:
            note: 音符对象
            note_info: 音符信息字典
            error_type: 错误类型
            
        Returns:
            ErrorNote: 错误音符对象
        """
        from .types import NoteInfo
        
        return ErrorNote(
            infos=[NoteInfo(
                index=note_info['index'],
                keyId=note_info['key_id'],
                keyOn=note_info['keyon'],
                keyOff=note_info['keyoff']
            )],
            diffs=[],
            error_type=error_type,
            global_index=note_info['index']
        )
    
    def get_drop_hammers(self) -> List[ErrorNote]:
        """
        获取丢锤列表
        
        Returns:
            List[ErrorNote]: 丢锤列表
        """
        return self.drop_hammers.copy()
    
    def get_multi_hammers(self) -> List[ErrorNote]:
        """
        获取多锤列表
        
        Returns:
            List[ErrorNote]: 多锤列表
        """
        return self.multi_hammers.copy()
    
    def get_silent_hammers(self) -> List[ErrorNote]:
        """
        获取不发声锤子列表
        
        Returns:
            List[ErrorNote]: 不发声锤子列表
        """
        return self.silent_hammers.copy()
    
