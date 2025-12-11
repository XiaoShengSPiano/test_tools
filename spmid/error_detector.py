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
        分析丢锤和多锤问题

        直接基于匹配结果分析：
        - 丢锤：录制数据中未匹配的音符
        - 多锤：播放数据中未匹配的音符

        Args:
            record_data: 录制数据
            replay_data: 播放数据
            matched_pairs: 匹配对列表（格式：(record_idx, replay_idx, record_note, replay_note)）
            note_matcher: 音符匹配器（可选），用于获取失败原因

        Returns:
            Tuple[List[ErrorNote], List[ErrorNote]]: (drop_hammers, multi_hammers)
        """
        # 简化的逻辑：直接基于匹配结果分析未匹配的音符
        self._analyze_unmatched_notes_for_hammer_issues(record_data, replay_data, matched_pairs, note_matcher)

        # 打印错误统计信息
        print(f"[错误统计] 丢锤数: {len(self.drop_hammers)} 个")
        print(f"[错误统计] 多锤数: {len(self.multi_hammers)} 个")
        print(f"[错误统计] 总错误数: {len(self.drop_hammers) + len(self.multi_hammers)} 个")

        return self.drop_hammers, self.multi_hammers

    def _analyze_unmatched_notes_for_hammer_issues(self, record_data: List[Note], replay_data: List[Note],
                                                  matched_pairs: List[Tuple[int, int, Note, Note]],
                                                  note_matcher=None) -> None:
        """
        基于匹配结果直接分析丢锤和多锤问题

        匹配算法以录制数据为基准，遍历每个录制音符在播放数据中寻找最佳匹配：
        - 丢锤：匹配完成后，录制数据中仍未匹配的音符
        - 多锤：匹配完成后，播放数据中未被任何录制音符匹配的音符

        Args:
            record_data: 录制数据
            replay_data: 播放数据
            matched_pairs: 匹配对列表（格式：(record_idx, replay_idx, record_note, replay_note)）
            note_matcher: 音符匹配器（可选，用于获取详细的失败原因）
        """
        # 1. 获取已匹配的索引集合
        matched_record_indices = {record_idx for record_idx, _, _, _ in matched_pairs}
        matched_replay_indices = {replay_idx for _, replay_idx, _, _ in matched_pairs}

        # 2. 分析丢锤：录制数据中未匹配的音符
        for i, record_note in enumerate(record_data):
            if i not in matched_record_indices:
                # 这个录制音符没有找到匹配，是丢锤
                reason = "录制音符未找到匹配"
                if note_matcher and hasattr(note_matcher, 'failure_reasons'):
                    # 如果有详细的失败原因，使用它
                    failure_key = ('record', i)
                    if failure_key in note_matcher.failure_reasons:
                        reason = note_matcher.failure_reasons[failure_key]

                self._handle_drop_hammer_case(record_note, i, reason)

        # 3. 分析多锤：播放数据中未匹配的音符
        for i, replay_note in enumerate(replay_data):
            if i not in matched_replay_indices:
                # 这个播放音符没有被任何录制音符匹配，是多锤
                reason = "播放音符未被匹配"
                if note_matcher and hasattr(note_matcher, 'failure_reasons'):
                    # 如果有详细的失败原因，使用它
                    failure_key = ('replay', i)
                    if failure_key in note_matcher.failure_reasons:
                        reason = note_matcher.failure_reasons[failure_key]

                self._handle_multi_hammer_case(replay_note, i, reason)


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
        try:
            absolute_keyon = note.after_touch.index[0] + note.offset + self.global_time_offset
            absolute_keyoff = note.after_touch.index[-1] + note.offset + self.global_time_offset
            relative_keyon = note.after_touch.index[0] + note.offset
            relative_keyoff = note.after_touch.index[-1] + note.offset
        except (IndexError, AttributeError) as e:
            raise ValueError(f"音符ID {note.id} 的after_touch数据无效: {e}") from e

        return {
            'keyon': absolute_keyon,
            'keyoff': absolute_keyoff,
            'key_id': note.id,
            'index': index,
            'relative_keyon': relative_keyon,
            'relative_keyoff': relative_keyoff
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
    
