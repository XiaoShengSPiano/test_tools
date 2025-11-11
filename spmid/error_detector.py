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
                            matched_pairs: List[Tuple[int, int, Note, Note]],
                            note_matcher=None) -> Tuple[List[ErrorNote], List[ErrorNote]]:
        """
        分析多锤和丢锤问题
        
        Args:
            record_data: 录制数据
            replay_data: 播放数据
            matched_pairs: 匹配对列表（只包含在阈值内的正常匹配对）
            note_matcher: 音符匹配器（可选），用于获取超过阈值的匹配对
            
        Returns:
            Tuple[List[ErrorNote], List[ErrorNote]]: (drop_hammers, multi_hammers)
        """
        # 获取超过阈值的匹配对（如果有）
        exceeds_threshold_matched_pairs = []
        if note_matcher and hasattr(note_matcher, 'exceeds_threshold_matched_pairs'):
            exceeds_threshold_matched_pairs = note_matcher.exceeds_threshold_matched_pairs
        
        # 分析未匹配的音符（没有最佳配对的按键，直接判断为异常）
        self._analyze_unmatched_notes(record_data, replay_data, matched_pairs, exceeds_threshold_matched_pairs, note_matcher)
        
        # 分析超过阈值的匹配对（即使有最佳配对，但超过阈值，仍然标记为异常）
        if exceeds_threshold_matched_pairs:
            self._analyze_exceeds_threshold_pairs(record_data, replay_data, exceeds_threshold_matched_pairs, note_matcher)
        
        return self.drop_hammers, self.multi_hammers
    
    def _analyze_unmatched_notes(self, record_data: List[Note], replay_data: List[Note], 
                               matched_pairs: List[Tuple[int, int, Note, Note]],
                               exceeds_threshold_matched_pairs: List[Tuple[int, int, Note, Note]] = None,
                               note_matcher=None) -> None:
        """
        分析未匹配的音符，识别丢锤和多锤异常
        这些是没有最佳配对的按键（完全没有候选或所有候选都被占用），直接判断为异常
        
        Args:
            record_data: 录制数据
            replay_data: 播放数据
            matched_pairs: 匹配对列表（只包含在阈值内的正常匹配对）
            exceeds_threshold_matched_pairs: 超过阈值但有最佳配对的匹配对列表（可选）
        """
        # 获取已匹配的索引（包括正常匹配和超过阈值的匹配）
        matched_record_indices = {pair[0] for pair in matched_pairs}
        matched_replay_indices = {pair[1] for pair in matched_pairs}
        
        # 如果提供了超过阈值的匹配对，也要排除这些索引（因为它们会在_analyze_exceeds_threshold_pairs中处理）
        if exceeds_threshold_matched_pairs:
            matched_record_indices.update({pair[0] for pair in exceeds_threshold_matched_pairs})
            matched_replay_indices.update({pair[1] for pair in exceeds_threshold_matched_pairs})
        
        # 获取失败原因（从note_matcher中获取，如果有）
        failure_reasons = {}
        if note_matcher and hasattr(note_matcher, 'failure_reasons'):
            failure_reasons = note_matcher.failure_reasons
        
        # 分析录制数据中未匹配的音符（丢锤）
        # 这些是没有最佳配对的按键，直接判断为异常
        for i, record_note in enumerate(record_data):
            if i not in matched_record_indices:
                # 尝试从failure_reasons中获取原因（如果有）
                reason = failure_reasons.get(("record", i), None)
                self._handle_drop_hammer_case(record_note, i, reason)
        
        # 分析播放数据中未匹配的音符（多锤）
        # 这些是没有最佳配对的按键，直接判断为异常
        for i, replay_note in enumerate(replay_data):
            if i not in matched_replay_indices:
                # 尝试从failure_reasons中获取原因（如果有）
                # 注意：播放数据的失败原因可能不存在，因为匹配是以录制数据为基准的
                reason = failure_reasons.get(("replay", i), None)
                self._handle_multi_hammer_case(replay_note, i, reason)
    
    def _analyze_exceeds_threshold_pairs(self, record_data: List[Note], replay_data: List[Note], 
                                        exceeds_threshold_matched_pairs: List[Tuple[int, int, Note, Note]],
                                        note_matcher=None) -> None:
        """
        分析超过阈值的匹配对，将它们标记为异常
        
        Args:
            record_data: 录制数据
            replay_data: 播放数据
            exceeds_threshold_matched_pairs: 超过阈值但有最佳配对的匹配对列表，格式为[(record_index, replay_index, record_note, replay_note), ...]
            note_matcher: 音符匹配器（可选），用于获取失败原因
        """
        for record_index, replay_index, record_note, replay_note in exceeds_threshold_matched_pairs:
            # 获取失败原因（如果有）
            # 注意：匹配是以录制数据为基准的，所以原因存储在 ("record", record_index) 中
            reason = None
            if note_matcher and hasattr(note_matcher, 'failure_reasons'):
                reason = note_matcher.failure_reasons.get(("record", record_index), None)
            
            # 创建错误音符，标记为"超过阈值"
            # 对于录制数据，标记为丢锤（超过阈值）
            self._handle_drop_hammer_case(record_note, record_index, reason)
            # 对于播放数据，标记为多锤（超过阈值）
            # 注意：播放数据也使用相同的reason，因为这是同一个匹配对
            self._handle_multi_hammer_case(replay_note, replay_index, reason)
    
    def _handle_drop_hammer_case(self, note: Note, index: int, reason: str = None) -> None:
        """
        处理丢锤情况
        
        Args:
            note: 音符对象
            index: 音符索引
            reason: 失败原因（可选）
        """
        note_info = self._extract_note_info(note, index)
        error_note = self._create_error_note_with_stats(note, note_info, "丢锤", reason)
        self.drop_hammers.append(error_note)
    
    def _handle_multi_hammer_case(self, note: Note, index: int, reason: str = None) -> None:
        """
        处理多锤情况
        
        Args:
            note: 音符对象
            index: 音符索引
            reason: 失败原因（可选）
        """
        note_info = self._extract_note_info(note, index)
        error_note = self._create_error_note_with_stats(note, note_info, "多锤", reason)
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
    
    def _create_error_note_with_stats(self, note: Note, note_info: Dict, error_type: str, reason: str = None) -> ErrorNote:
        """
        创建错误音符对象并添加统计信息
        
        Args:
            note: 音符对象
            note_info: 音符信息字典
            error_type: 错误类型
            reason: 失败原因（可选）
            
        Returns:
            ErrorNote: 错误音符对象
        """
        from .types import NoteInfo
        
        # 如果没有提供原因，保持为空字符串
        if reason is None:
            reason = ""
        
        return ErrorNote(
            infos=[NoteInfo(
                index=note_info['index'],
                keyId=note_info['key_id'],
                keyOn=note_info['keyon'],
                keyOff=note_info['keyoff']
            )],
            diffs=[],
            error_type=error_type,
            global_index=note_info['index'],
            reason=reason
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
    
