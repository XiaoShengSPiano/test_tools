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
    
    def __init__(self):
        """
        初始化异常检测器
        """
        self.multi_hammers: List[ErrorNote] = []
        self.drop_hammers: List[ErrorNote] = []
        self.abnormal_matches: List[ErrorNote] = []  # 异常匹配对（双方都无hammer）
    
    def analyze_hammer_issues(self, record_data: List[Note], replay_data: List[Note],
                            matched_pairs: List[Tuple[int, int, Note, Note]],
                            note_matcher=None) -> Tuple[List[ErrorNote], List[ErrorNote], List[ErrorNote]]:
        """
        分析锤击问题（丢锤、多锤、异常匹配对）

        分析流程：
        1. 验证匹配对的hammer velocity是否合理
        2. 将不合理的匹配对分类：
           - 双方都无hammer → 异常匹配对
           - 录制有播放无 → 丢锤
           - 播放有录制无 → 多锤
        3. 分析未匹配的音符

        Args:
            record_data: 录制数据
            replay_data: 播放数据
            matched_pairs: 匹配对列表（格式：(record_idx, replay_idx, record_note, replay_note)）
            note_matcher: 音符匹配器（可选），用于获取失败原因

        Returns:
            Tuple[List[ErrorNote], List[ErrorNote], List[ErrorNote]]: (drop_hammers, multi_hammers, abnormal_matches)
        """
        # 步骤1：验证匹配对的hammer velocity，直接修改matched_pairs（原地更新）
        self._validate_hammer_velocity_in_matches(matched_pairs)
        
        # 步骤2：基于更新后的匹配对分析未匹配的音符
        self._analyze_unmatched_notes_for_hammer_issues(record_data, replay_data, matched_pairs, note_matcher)

        return self.drop_hammers, self.multi_hammers, self.abnormal_matches
    
    def _validate_hammer_velocity_in_matches(self, matched_pairs: List[Tuple[int, int, Note, Note]]) -> None:
        """
        验证匹配对的hammer velocity是否合理，直接修改matched_pairs列表（原地更新）
        
        验证规则（按优先级检查）：
        1. 如果录制和播放都无hammer（≤0） → 判定为异常匹配对，从匹配对中移除
        2. 如果录制有hammer（>0），但播放无hammer（≤0） → 判定为丢锤，从匹配对中移除
        3. 如果播放有hammer（>0），但录制无hammer（≤0） → 判定为多锤，从匹配对中移除
        
        剩余的匹配对即为精确匹配对（双方都有hammer）
        
        Args:
            matched_pairs: 匹配对列表（会被直接修改）
        """
        # 记录需要移除的索引（倒序遍历以安全删除）
        indices_to_remove = []
        abnormal_count = 0
        drop_hammer_count = 0
        multi_hammer_count = 0
        
        for i, (record_idx, replay_idx, record_note, replay_note) in enumerate(matched_pairs):
            # 获取hammer velocity
            record_hammer = record_note.get_first_hammer_velocity()
            replay_hammer = replay_note.get_first_hammer_velocity()
            
            # 转换为统一格式（None -> 0）
            record_hammer_val = record_hammer if record_hammer is not None else 0
            replay_hammer_val = replay_hammer if replay_hammer is not None else 0
            
            # 规则1：双方都无hammer → 异常匹配对（优先级最高）
            if record_hammer_val <= 0 and replay_hammer_val <= 0:
                reason = f"双方都无hammer速度（录制={record_hammer_val}, 播放={replay_hammer_val}）"
                self._handle_abnormal_match_case(record_note, replay_note, record_idx, replay_idx, reason)
                logger.debug(f"      ⚠️ 匹配对验证: 录制[{record_idx}] hammer={record_hammer_val}, 播放[{replay_idx}] hammer={replay_hammer_val} → 判定为异常匹配对")
                indices_to_remove.append(i)
                abnormal_count += 1
                continue
            
            # 规则2：录制有hammer（>0），播放无hammer（≤0）→ 丢锤
            if record_hammer_val > 0 and replay_hammer_val <= 0:
                reason = f"录制有hammer速度({record_hammer_val})，播放无hammer速度"
                self._handle_drop_hammer_case(record_note, record_idx, reason)
                logger.debug(f"      ⚠️ 匹配对验证: 录制[{record_idx}] hammer={record_hammer_val}, 播放[{replay_idx}] hammer={replay_hammer_val} → 判定为丢锤")
                indices_to_remove.append(i)
                drop_hammer_count += 1
                continue
            
            # 规则3：播放有hammer（>0），录制无hammer（≤0）→ 多锤
            if replay_hammer_val > 0 and record_hammer_val <= 0:
                reason = f"播放有hammer速度({replay_hammer_val})，录制无hammer速度"
                self._handle_multi_hammer_case(replay_note, replay_idx, reason)
                logger.debug(f"      ⚠️ 匹配对验证: 录制[{record_idx}] hammer={record_hammer_val}, 播放[{replay_idx}] hammer={replay_hammer_val} → 判定为多锤")
                indices_to_remove.append(i)
                multi_hammer_count += 1
                continue
        
        # 从后往前删除，避免索引变化
        for i in reversed(indices_to_remove):
            del matched_pairs[i]
        
        # 如果有匹配对被分类，记录日志
        if indices_to_remove:
            logger.debug(f"    🔍 Hammer velocity验证完成:")
            logger.debug(f"       - 异常匹配对: {abnormal_count}个")
            logger.debug(f"       - 丢锤匹配对: {drop_hammer_count}个")
            logger.debug(f"       - 多锤匹配对: {multi_hammer_count}个")
            logger.debug(f"       - 精确匹配对: {len(matched_pairs)}个（剩余）")

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
                # 验证hammer值：只有当第一个hammer值>0时才判定为丢锤
                hammer_velocity = record_note.get_first_hammer_velocity()
                if hammer_velocity is None or hammer_velocity == 0:
                    # hammer值为空或为0，直接剔除，不记录为丢锤
                    logger.debug(f"      ⏭️  跳过录制音符[{i}]: hammer值为{hammer_velocity}，不判定为丢锤")
                    continue
                
                # 这个录制音符没有找到匹配，且有有效hammer值，是丢锤
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
                # 验证hammer值：只有当第一个hammer值>0时才判定为多锤
                hammer_velocity = replay_note.get_first_hammer_velocity()
                if hammer_velocity is None or hammer_velocity == 0:
                    # hammer值为空或为0，直接剔除，不记录为多锤
                    logger.debug(f"      ⏭️  跳过播放音符[{i}]: hammer值为{hammer_velocity}，不判定为多锤")
                    continue
                
                # 这个播放音符没有被任何录制音符匹配，且有有效hammer值，是多锤
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
    
    def _handle_abnormal_match_case(self, record_note: Note, replay_note: Note, 
                                   record_idx: int, replay_idx: int, reason: str = None) -> None:
        """
        处理异常匹配对情况（双方都无hammer）
        
        注意：异常匹配对需要记录双方信息，但在ErrorNote中只能存储一个Note对象，
        这里选择存储录制轨道的音符，并在reason中说明情况
        
        Args:
            record_note: 录制音符对象
            replay_note: 播放音符对象
            record_idx: 录制音符索引
            replay_idx: 播放音符索引
            reason: 失败原因（可选）
        """
        # 提取录制音符信息（作为代表）
        note_info = self._extract_note_info(record_note, record_idx)
        
        # 增强reason信息，包含双方索引
        if reason:
            enhanced_reason = f"{reason} (录制[{record_idx}]↔播放[{replay_idx}])"
        else:
            enhanced_reason = f"异常匹配对：双方都无hammer (录制[{record_idx}]↔播放[{replay_idx}])"
        
        error_note = self._create_error_note_with_stats(record_note, note_info, "异常匹配对", enhanced_reason)
        self.abnormal_matches.append(error_note)
    
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
            absolute_keyon = note.after_touch.index[0] + note.offset
            absolute_keyoff = note.after_touch.index[-1] + note.offset
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
        
        重构后直接使用 Note 对象，保留完整数据，便于后续绘制曲线。
        
        Args:
            note: 音符对象（完整的 Note，包含 hammers, after_touch 等数据）
            note_info: 音符信息字典（现在主要用于索引）
            error_type: 错误类型
            reason: 失败原因（可选）
            
        Returns:
            ErrorNote: 错误音符对象
        """
        # 如果没有提供原因，保持为空字符串
        if reason is None:
            reason = ""
        
        return ErrorNote(
            note=note,  # 直接使用完整的 Note 对象
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
    
    def get_abnormal_matches(self) -> List[ErrorNote]:
        """
        获取异常匹配对列表
        
        Returns:
            List[ErrorNote]: 异常匹配对列表
        """
        return self.abnormal_matches.copy()
    
    
