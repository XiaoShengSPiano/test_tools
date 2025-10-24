#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SPMID音符匹配器

负责SPMID数据的按键匹配，包括：
- 音符匹配算法
- 匹配对生成
- 匹配结果管理
"""

from .spmid_reader import Note
from typing import List, Tuple, Dict, Any
from utils.logger import Logger

logger = Logger.get_logger()

class NoteMatcher:
    """SPMID音符匹配器类"""
    
    def __init__(self, global_time_offset: float = 0.0):
        """
        初始化音符匹配器
        
        Args:
            global_time_offset: 全局时间偏移量
        """
        self.global_time_offset = global_time_offset
        self.matched_pairs: List[Tuple[int, int, Note, Note]] = []
    
    def find_all_matched_pairs(self, record_data: List[Note], replay_data: List[Note]) -> List[Tuple[int, int, Note, Note]]:
        """
        以录制数据为基准，在播放数据中寻找匹配的音符对
        
        Args:
            record_data: 录制数据
            replay_data: 播放数据
            
        Returns:
            List[Tuple[int, int, Note, Note]]: 匹配对列表
        """
        matched_pairs = []
        used_replay_indices = set()
        
        # 录制数据在播放数据中匹配
        for i, record_note in enumerate(record_data):
            note_info = self._extract_note_info(record_note, i)
            index = find_best_matching_notes(replay_data, note_info["keyon"], note_info["keyoff"], note_info["key_id"])
            
            # 确保index是有效的非负索引
            if index >= 0 and index < len(replay_data) and index not in used_replay_indices:
                matched_pairs.append((i, index, record_note, replay_data[index]))
                used_replay_indices.add(index)
        
        self.matched_pairs = matched_pairs
        return matched_pairs
    
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
    
    def extract_normal_matched_pairs(self, matched_pairs: List[Tuple[int, int, Note, Note]], 
                                   multi_hammers: List, drop_hammers: List) -> Tuple[List[Note], List[Note]]:
        """
        从匹配对中提取正常匹配的音符对
        
        Args:
            matched_pairs: 匹配对列表
            multi_hammers: 多锤列表
            drop_hammers: 丢锤列表
            
        Returns:
            Tuple[List[Note], List[Note]]: (matched_record_data, matched_replay_data)
        """
        matched_record_data = []
        matched_replay_data = []
        
        for record_index, replay_index, record_note, replay_note in matched_pairs:
            matched_record_data.append(record_note)
            matched_replay_data.append(replay_note)
        
        return matched_record_data, matched_replay_data
    
    def get_matched_pairs(self) -> List[Tuple[int, int, Note, Note]]:
        """
        获取匹配对列表
        
        Returns:
            List[Tuple[int, int, Note, Note]]: 匹配对列表
        """
        return self.matched_pairs.copy()
    
    def update_global_time_offset(self, global_time_offset: float) -> None:
        """
        更新全局时间偏移量
        
        Args:
            global_time_offset: 新的全局时间偏移量
        """
        self.global_time_offset = global_time_offset
    
    def get_offset_alignment_data(self) -> List[Dict[str, Any]]:
        """
        获取偏移对齐数据 - 计算每个匹配对的时间偏移
        
        Returns:
            List[Dict[str, Any]]: 偏移对齐数据列表
        """
        offset_data = []
        
        for record_idx, replay_idx, record_note, replay_note in self.matched_pairs:
            # 计算按键开始时间偏移
            record_keyon = record_note.after_touch.index[0] + record_note.offset if len(record_note.after_touch) > 0 else record_note.hammers.index[0] + record_note.offset
            replay_keyon = replay_note.after_touch.index[0] + replay_note.offset if len(replay_note.after_touch) > 0 else replay_note.hammers.index[0] + replay_note.offset
            keyon_offset = replay_keyon - record_keyon
            
            # 计算按键结束时间偏移
            record_keyoff = record_note.after_touch.index[-1] + record_note.offset if len(record_note.after_touch) > 0 else record_note.hammers.index[0] + record_note.offset
            replay_keyoff = replay_note.after_touch.index[-1] + replay_note.offset if len(replay_note.after_touch) > 0 else replay_note.hammers.index[0] + replay_note.offset
            keyoff_offset = replay_keyoff - record_keyoff
            
            # 计算平均偏移
            avg_offset = (keyon_offset + keyoff_offset) / 2
            
            offset_data.append({
                'record_index': record_idx,
                'replay_index': replay_idx,
                'key_id': record_note.id,
                'record_keyon': record_keyon,
                'replay_keyon': replay_keyon,
                'keyon_offset': keyon_offset,
                'record_keyoff': record_keyoff,
                'replay_keyoff': replay_keyoff,
                'keyoff_offset': keyoff_offset,
                'average_offset': avg_offset,
                'record_duration': record_keyoff - record_keyon,
                'replay_duration': replay_keyoff - replay_keyon,
                'duration_diff': (replay_keyoff - replay_keyon) - (record_keyoff - record_keyon)
            })
        
        return offset_data
    
    def get_invalid_notes_offset_analysis(self, record_data: List[Note], replay_data: List[Note]) -> List[Dict[str, Any]]:
        """
        获取无效音符的偏移对齐分析
        
        Args:
            record_data: 录制数据
            replay_data: 播放数据
            
        Returns:
            List[Dict[str, Any]]: 无效音符偏移分析数据
        """
        invalid_offset_data = []
        
        # 获取已匹配的音符索引
        matched_record_indices = set(pair[0] for pair in self.matched_pairs)
        matched_replay_indices = set(pair[1] for pair in self.matched_pairs)
        
        # 分析录制数据中的无效音符（未匹配的音符）
        for i, note in enumerate(record_data):
            if i not in matched_record_indices:  # 未匹配的音符
                try:
                    keyon_time = note.after_touch.index[0] + note.offset if len(note.after_touch) > 0 else note.hammers.index[0] + note.offset
                    keyoff_time = note.after_touch.index[-1] + note.offset if len(note.after_touch) > 0 else note.hammers.index[0] + note.offset
                    
                    invalid_offset_data.append({
                        'data_type': 'record',
                        'note_index': i,
                        'key_id': note.id,
                        'keyon_time': keyon_time,
                        'keyoff_time': keyoff_time,
                        'offset': note.offset,
                        'status': 'unmatched'
                    })
                except (IndexError, AttributeError) as e:
                    # 处理数据异常的情况
                    invalid_offset_data.append({
                        'data_type': 'record',
                        'note_index': i,
                        'key_id': note.id,
                        'keyon_time': 0.0,
                        'keyoff_time': 0.0,
                        'offset': note.offset,
                        'status': 'data_error'
                    })
        
        # 分析播放数据中的无效音符（未匹配的音符）
        for i, note in enumerate(replay_data):
            if i not in matched_replay_indices:  # 未匹配的音符
                try:
                    keyon_time = note.after_touch.index[0] + note.offset if len(note.after_touch) > 0 else note.hammers.index[0] + note.offset
                    keyoff_time = note.after_touch.index[-1] + note.offset if len(note.after_touch) > 0 else note.hammers.index[0] + note.offset
                    
                    invalid_offset_data.append({
                        'data_type': 'replay',
                        'note_index': i,
                        'key_id': note.id,
                        'keyon_time': keyon_time,
                        'keyoff_time': keyoff_time,
                        'offset': note.offset,
                        'status': 'unmatched'
                    })
                except (IndexError, AttributeError) as e:
                    # 处理数据异常的情况
                    invalid_offset_data.append({
                        'data_type': 'replay',
                        'note_index': i,
                        'key_id': note.id,
                        'keyon_time': 0.0,
                        'keyoff_time': 0.0,
                        'offset': note.offset,
                        'status': 'data_error'
                    })
        
        return invalid_offset_data
    
    def get_offset_statistics(self) -> Dict[str, Any]:
        """
        获取偏移统计信息
        
        Returns:
            Dict[str, Any]: 偏移统计信息
        """
        if not self.matched_pairs:
            return {
                'total_pairs': 0,
                'keyon_offset_stats': {'average': 0.0, 'max': 0.0, 'min': 0.0, 'std': 0.0},
                'keyoff_offset_stats': {'average': 0.0, 'max': 0.0, 'min': 0.0, 'std': 0.0},
                'overall_offset_stats': {'average': 0.0, 'max': 0.0, 'min': 0.0, 'std': 0.0}
            }
        
        # 获取偏移数据
        offset_data = self.get_offset_alignment_data()
        
        # 提取偏移值
        keyon_offsets = [item['keyon_offset'] for item in offset_data]
        keyoff_offsets = [item['keyoff_offset'] for item in offset_data]
        all_offsets = keyon_offsets + keyoff_offsets
        
        return {
            'total_pairs': len(self.matched_pairs),
            'keyon_offset_stats': self._calculate_offset_stats(keyon_offsets),
            'keyoff_offset_stats': self._calculate_offset_stats(keyoff_offsets),
            'overall_offset_stats': self._calculate_offset_stats(all_offsets)
        }
    
    def _calculate_offset_stats(self, offsets: List[float]) -> Dict[str, float]:
        """
        计算偏移统计信息
        
        Args:
            offsets: 偏移值列表
            
        Returns:
            Dict[str, float]: 统计信息
        """
        if not offsets:
            return {'average': 0.0, 'max': 0.0, 'min': 0.0, 'std': 0.0}
        
        average = sum(offsets) / len(offsets)
        max_val = max(offsets)
        min_val = min(offsets)
        
        # 计算标准差
        if len(offsets) <= 1:
            std = 0.0
        else:
            variance = sum((x - average) ** 2 for x in offsets) / (len(offsets) - 1)
            std = variance ** 0.5
        
        return {
            'average': average,
            'max': max_val,
            'min': min_val,
            'std': std
        }


def find_best_matching_notes(notes_list: List[Note], target_keyon: float, target_keyoff: float, target_key_id: int) -> int:
    """
    在音符列表中查找与目标音符最匹配的音符
    
    算法说明：
    1. 首先筛选出所有相同键ID的音符
    2. 对每个候选音符，计算与目标音符的时间误差
    3. 使用加权误差计算（按键开始时间权重更高）
    4. 返回误差最小的音符索引，如果误差超过阈值则返回-1
    
    参数详解：
    - notes_list: List[Note] - 候选音符列表，从中寻找匹配的音符
    - target_keyon: float - 目标音符的按键开始时间（毫秒，绝对时间戳，已对齐）
    - target_keyoff: float - 目标音符的按键结束时间（毫秒，绝对时间戳，已对齐）
    - target_key_id: int - 目标音符的键ID（1-88，对应钢琴的88个键）
    
    返回值：
    - int: 匹配音符在notes_list中的索引，如果未找到匹配则返回-1
    
    时间戳说明：
    - target_keyon/target_keyoff: 已经过全局时间对齐的绝对时间戳（毫秒）
    - 候选音符的时间戳: note.after_touch.index[0] + note.offset（毫秒，绝对时间戳）
    - 两者在同一时间坐标系下进行比较
    
    匹配策略：
    - 只使用第一个锤子数据，避免锤子抖动影响
    - 优先使用after_touch数据计算音符持续时间
    - 按键开始时间误差权重为2.0，结束时间误差权重为1.0
    - 动态阈值：基础阈值1000ms，根据音符持续时间调整（实际范围500-2000ms）
    
    异常情况：
    - notes_list为空：返回-1
    - 没有匹配键ID的音符：返回-1
    - 所有候选音符都没有有效锤子数据：返回-1
    - 最佳匹配的误差超过阈值：返回-1
    """
    if not notes_list:
        return -1
    
    # 第1步：筛选出所有相同键ID的音符
    # matching_notes: List[Tuple[int, Note]] - 存储(索引, 音符对象)的元组列表
    matching_notes = []
    for i, note in enumerate(notes_list):
        if note.id == target_key_id:  # 键ID匹配
            matching_notes.append((i, note))
    
    if not matching_notes:
        logger.debug(f"没有找到匹配键ID {target_key_id} 的音符")
        return -1
    
    # 第2步：对每个匹配的音符计算时间误差
    # candidates: List[Dict] - 存储候选音符的详细信息
    candidates = []
    for i, note in matching_notes:
        if note.hammers.empty:  # 跳过没有锤子数据的音符
            continue
            
        # 计算候选音符的绝对时间戳
        # first_hammer_time: float - 第一个锤子的绝对时间戳
        first_hammer_time = note.hammers.index[0] + note.offset
        
        # 计算音符的按键开始和结束时间
        # current_keyon: float - 候选音符的按键开始时间（绝对时间戳）
        # current_keyoff: float - 候选音符的按键结束时间（绝对时间戳）
        if len(note.after_touch) > 0:
            # 优先使用after_touch数据，更准确反映按键持续时间
            current_keyon = note.after_touch.index[0] + note.offset
            current_keyoff = note.after_touch.index[-1] + note.offset
        else:
            # 如果没有after_touch数据，使用第一个锤子时间作为备选
            current_keyon = first_hammer_time
            current_keyoff = first_hammer_time
        
        # 第3步：计算与目标音符的时间误差
        # keyon_error: float - 按键开始时间误差（毫秒）
        # keyoff_error: float - 按键结束时间误差（毫秒）
        keyon_error = abs(current_keyon - target_keyon)
        keyoff_error = abs(current_keyoff - target_keyoff)
        
        # 第4步：计算加权总误差
        # total_error: float - 加权总误差，按键开始时间权重更高
        total_error = keyon_error * 2.0 + keyoff_error * 1.0
        
        # 存储候选音符的详细信息
        candidates.append({
            'index': i,                    # 音符在notes_list中的索引
            'keyon': current_keyon,        # 候选音符的按键开始时间
            'keyoff': current_keyoff,      # 候选音符的按键结束时间
            'keyon_error': keyon_error,    # 按键开始时间误差
            'keyoff_error': keyoff_error,  # 按键结束时间误差
            'total_error': total_error     # 加权总误差
        })
        
        logger.debug(f"候选音符 {i}: keyon={current_keyon}, keyoff={current_keyoff}, 总误差={total_error}")

    if not candidates:
        logger.debug("没有有效的候选音符")
        return -1
    
    # 第5步：找到误差最小的候选音符
    # best_candidate: Dict - 最佳匹配音符的详细信息
    best_candidate = min(candidates, key=lambda x: x['total_error'])
    logger.debug(f"最佳候选: 索引={best_candidate['index']}, 总误差={best_candidate['total_error']}")


    # TODO 短音符的阈值可以调整到更小的阈值
    # 第6步：动态阈值检查
    # 基础阈值：1000ms（1秒）- 更符合钢琴演奏实际情况
    base_threshold = 1000
    
    # 根据目标音符的持续时间调整阈值
    # duration: float - 目标音符的持续时间（毫秒）
    duration = target_keyoff - target_keyon
    
    # duration_factor: float - 持续时间因子，范围[0.5, 2.0]
    # 短音符（<500ms）使用较小阈值，长音符（>500ms）使用较大阈值
    duration_factor = min(2.0, max(0.5, duration / 500))
    
    # max_allowed_error: float - 最大允许误差（毫秒）
    # 实际范围：500ms - 2000ms，更符合钢琴演奏的精度要求
    max_allowed_error = base_threshold * duration_factor
    
    # 第7步：误差阈值检查
    if best_candidate['total_error'] > max_allowed_error:
        logger.debug(f"误差 {best_candidate['total_error']} 超过阈值 {max_allowed_error}")
        return -1
    
    # 第8步：返回最佳匹配音符的索引
    return best_candidate['index']
