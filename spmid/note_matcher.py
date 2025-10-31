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
            global_time_offset: 全局时间偏移量（已废弃，固定为0）
        """
        self.global_time_offset = 0.0  # 固定为0，不再使用全局偏移
        self.matched_pairs: List[Tuple[int, int, Note, Note]] = []
        # 记录匹配失败原因：key=(data_type, index)，value=str
        self.failure_reasons: Dict[Tuple[str, int], str] = {}
    
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
        # 清空上一轮失败原因
        self.failure_reasons.clear()
        
        logger.info(f"🎯 开始音符匹配: 录制数据{len(record_data)}个音符, 回放数据{len(replay_data)}个音符")
        
        # 录制数据在播放数据中匹配
        for i, record_note in enumerate(record_data):
            note_info = self._extract_note_info(record_note, i)

            # 生成候选列表（按总误差升序），仅保留在动态阈值内的候选
            candidates, threshold, reason_if_empty = self._generate_sorted_candidates_within_threshold(
                replay_data,
                target_keyon=note_info["keyon"],
                target_keyoff=note_info["keyoff"],
                target_key_id=note_info["key_id"]
            )

            if not candidates:
                # 无任何在阈值内的候选，直接判定失败
                logger.info(f"❌ 匹配失败: 键ID={note_info['key_id']}, 录制索引={i}, "
                           f"录制时间=({note_info['keyon']/10:.2f}ms, {note_info['keyoff']/10:.2f}ms), "
                           f"原因: {reason_if_empty}")
                self.failure_reasons[("record", i)] = reason_if_empty
                continue

            # 从候选中选择第一个未被占用的重放索引
            chosen = None
            for cand in candidates:
                cand_index = cand['index']
                if cand_index not in used_replay_indices:
                    chosen = cand
                    break

            if chosen is not None:
                replay_index = chosen['index']
                matched_pairs.append((i, replay_index, record_note, replay_data[replay_index]))
                used_replay_indices.add(replay_index)
                
                # 记录匹配成功的详细信息
                replay_note = replay_data[replay_index]
                record_keyon, record_keyoff = self._calculate_note_times(record_note)
                replay_keyon, replay_keyoff = self._calculate_note_times(replay_note)
                keyon_offset = replay_keyon - record_keyon
                keyoff_offset = replay_keyoff - record_keyoff
                
                logger.info(f"✅ 匹配成功: 键ID={note_info['key_id']}, "
                           f"录制索引={i}, 回放索引={replay_index}, "
                           f"录制时间=({record_keyon/10:.2f}ms, {record_keyoff/10:.2f}ms), "
                           f"回放时间=({replay_keyon/10:.2f}ms, {replay_keyoff/10:.2f}ms), "
                           f"偏移=({keyon_offset/10:.2f}ms, {keyoff_offset/10:.2f}ms), "
                           f"总误差={chosen['total_error']/10:.2f}ms, "
                           f"阈值={threshold/10:.2f}ms")
            else:
                # 所有阈值内候选都被占用
                reason = f"所有候选已被占用(候选数:{len(candidates)}, 阈值:{threshold:.1f}ms)"
                logger.info(f"❌ 匹配失败: 键ID={note_info['key_id']}, 录制索引={i}, "
                           f"录制时间=({note_info['keyon']/10:.2f}ms, {note_info['keyoff']/10:.2f}ms), "
                           f"原因: {reason}")
                
                # 记录被占用的候选详细信息
                for j, cand in enumerate(candidates[:3]):  # 只记录前3个候选
                    cand_note = replay_data[cand['index']]
                    cand_keyon, cand_keyoff = self._calculate_note_times(cand_note)
                    logger.info(f"   候选{j+1}: 回放索引={cand['index']}, "
                               f"回放时间=({cand_keyon/10:.2f}ms, {cand_keyoff/10:.2f}ms), "
                               f"总误差={cand['total_error']/10:.2f}ms")
                
                self.failure_reasons[("record", i)] = reason
        
        self.matched_pairs = matched_pairs
        
        # 记录匹配结果统计
        success_count = len(matched_pairs)
        failure_count = len(record_data) - success_count
        logger.info(f"🎯 音符匹配完成: 成功匹配{success_count}对, 失败{failure_count}个, "
                   f"成功率{success_count/len(record_data)*100:.1f}%")
        
        return matched_pairs

    def _generate_sorted_candidates_within_threshold(self, notes_list: List[Note], target_keyon: float, target_keyoff: float, target_key_id: int) -> Tuple[List[Dict[str, float]], float, str]:
        """
        生成在动态阈值内的候选列表（按总误差升序）。

        参数单位：
            - target_keyon/target_keyoff：0.1ms（绝对时间 = after_touch.index + offset）
            - 误差/阈值：0.1ms（内部统一单位）

        Returns:
            (candidates, max_allowed_error, reason_if_empty)
        """
        # 1) 过滤同键ID
        matching = []
        for idx, note in enumerate(notes_list):
            if getattr(note, 'id', None) == target_key_id:
                matching.append((idx, note))

        if not matching:
            return [], 0.0, f"没有找到键ID {target_key_id} 的音符"

        # 2) 构建候选并计算误差
        # 注意：此时所有音符都已通过数据过滤，保证有hammers和after_touch数据
        candidates: List[Dict[str, float]] = []
        for idx, note in matching:
            # 计算按键开始和结束时间
            current_keyon = note.after_touch.index[0] + note.offset
            current_keyoff = note.after_touch.index[-1] + note.offset

            # 只使用keyon_offset计算误差
            keyon_offset = current_keyon - target_keyon

            # 评分：只使用 |keyon_offset| （单位：0.1ms）
            total_error = abs(keyon_offset)

            candidates.append({
                'index': idx,
                'total_error': total_error,
                'keyon_error': abs(keyon_offset)
            })

        # 由于数据已过滤，理论上不会出现空候选列表（除非没有相同键ID）
        # 但保留此检查以防万一
        if not candidates:
            return [], 0.0, f"没有找到键ID {target_key_id} 的候选音符"

        # 3) 动态阈值（单位：0.1ms；base_threshold=500→50ms；范围约30–50ms）
        base_threshold = 500.0
        duration = (target_keyoff - target_keyon)
        # 持续时间必须大于0，否则视为异常音符（索引或数据异常）
        # TODO
        if duration <= 0:
            return [], 0.0, "无效持续时间(≤0)，疑似异常音符"
        duration_factor = min(1.0, max(0.6, duration / 500.0))
        max_allowed_error = base_threshold * duration_factor

        # 4) 过滤出在阈值内的候选并排序
        within = [c for c in candidates if c['total_error'] <= max_allowed_error]
        within.sort(key=lambda x: x['total_error'])

        if not within:
            # 即使有候选，但全部超阈值
            # 选出最小误差用于提示
            best_total = min(c['total_error'] for c in candidates)
            # 日志/原因字符串以ms显示（内部0.1ms需/10）
            return [], max_allowed_error, (
                f"时间误差过大(误差:{best_total/10:.1f}ms, 阈值:{max_allowed_error/10:.1f}ms)"
            )

        return within, max_allowed_error, ""
    
    def _extract_note_info(self, note: Note, index: int) -> Dict:
        """
        提取音符基本信息
        
        Args:
            note: 音符对象
            index: 音符索引
            
        Returns:
            Dict: 音符信息字典
        """
        # 计算绝对时间戳
        absolute_keyon = note.after_touch.index[0] + note.offset
        absolute_keyoff = note.after_touch.index[-1] + note.offset
        
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
    
    # TODO
    def get_offset_alignment_data(self) -> List[Dict[str, Any]]:
        """
        获取偏移对齐数据 - 计算每个匹配对的时间偏移
        
        Returns:
            List[Dict[str, Any]]: 偏移对齐数据列表
        """
        offset_data = []
        
        for record_idx, replay_idx, record_note, replay_note in self.matched_pairs:
            # 计算录制和播放音符的时间
            record_keyon, record_keyoff = self._calculate_note_times(record_note)
            replay_keyon, replay_keyoff = self._calculate_note_times(replay_note)
            
            # 计算偏移量：只使用keyon_offset
            keyon_offset = replay_keyon - record_keyon
            record_duration = record_keyoff - record_keyon
            replay_duration = replay_keyoff - replay_keyon
            duration_diff = replay_duration - record_duration
            duration_offset = duration_diff
            # 只使用keyon_offset计算average_offset
            avg_offset = abs(keyon_offset)
    
            
            offset_data.append({
                'record_index': record_idx,
                'replay_index': replay_idx,
                'key_id': record_note.id,
                'record_keyon': record_keyon,
                'replay_keyon': replay_keyon,
                'keyon_offset': keyon_offset,
                'record_keyoff': record_keyoff,
                'replay_keyoff': replay_keyoff,
                'duration_offset': duration_offset,
                'average_offset': avg_offset,  
                'record_duration': record_duration,
                'replay_duration': replay_duration,
                'duration_diff': duration_diff
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
        invalid_offset_data.extend(
            self._analyze_invalid_notes(record_data, matched_record_indices, 'record', replay_data)
        )
        
        # 分析播放数据中的无效音符（未匹配的音符）
        invalid_offset_data.extend(
            self._analyze_invalid_notes(replay_data, matched_replay_indices, 'replay', record_data)
        )
        
        return invalid_offset_data
    
    def _analyze_invalid_notes(self, notes_data: List[Note], matched_indices: set, data_type: str, 
                              other_notes_data: List[Note] = None) -> List[Dict[str, Any]]:
        """
        分析无效音符的通用方法
        
        Args:
            notes_data: 音符数据列表
            matched_indices: 已匹配的音符索引集合
            data_type: 数据类型 ('record' 或 'replay')
            other_notes_data: 另一个数据类型的音符列表，用于分析匹配失败原因
            
        Returns:
            List[Dict[str, Any]]: 无效音符分析数据
        """
        invalid_notes = []
        
        for i, note in enumerate(notes_data):
            if i not in matched_indices:  # 未匹配的音符
                try:
                    keyon_time, keyoff_time = self._calculate_note_times(note)
                    
                    # 优先使用匹配阶段记录的真实失败原因（仅record侧有）
                    analysis_reason = None
                    if data_type == 'record' and (data_type, i) in self.failure_reasons:
                        analysis_reason = self.failure_reasons[(data_type, i)]
                    else:
                        # 回放侧或无记录时，再做推断分析
                        analysis_reason = self._get_actual_unmatch_reason(note, data_type, i, other_notes_data)
                    
                    invalid_notes.append({
                        'data_type': data_type,
                        'note_index': i,
                        'key_id': note.id,
                        'keyon_time': keyon_time,
                        'keyoff_time': keyoff_time,
                        'status': 'unmatched',
                        'analysis_reason': analysis_reason
                    })
                except (IndexError, AttributeError) as e:
                    # 处理数据异常的情况
                    invalid_notes.append({
                        'data_type': data_type,
                        'note_index': i,
                        'key_id': note.id,
                        'keyon_time': 0.0,
                        'keyoff_time': 0.0,
                        'status': 'data_error',
                        'analysis_reason': f'数据异常: {str(e)}'
                    })
        
        return invalid_notes
    
    def _get_actual_unmatch_reason(self, note: Note, data_type: str, note_index: int, 
                                  other_notes_data: List[Note] = None) -> str:
        """
        分析未匹配音符的实际失败原因
        
        Args:
            note: 音符对象
            data_type: 数据类型 ('record' 或 'replay')
            note_index: 音符索引
            other_notes_data: 另一个数据类型的音符列表
            
        Returns:
            str: 匹配失败原因
        """
        if other_notes_data is None:
            return "无法分析匹配失败原因(缺少对比数据)"
        
        try:
            # 提取当前音符信息
            note_info = self._extract_note_info(note, note_index)
            
            # 分析匹配失败的具体原因
            return self._analyze_match_failure_reason(note_info, other_notes_data, data_type)
            
        except Exception as e:
            return f"分析匹配失败原因时出错: {str(e)}"
    
    def _analyze_match_failure_reason(self, note_info: Dict, other_notes_data: List[Note], data_type: str) -> str:
        """
        分析匹配失败的具体原因（回放侧推断用）
        
        注意：录制侧已在匹配阶段记录真实原因，此方法主要用于回放侧推断
        
        Args:
            note_info: 音符信息字典
            other_notes_data: 另一个数据类型的音符列表
            data_type: 数据类型
            
        Returns:
            str: 匹配失败原因
        """
        target_key_id = note_info["key_id"]
        target_keyon = note_info["keyon"]
        target_keyoff = note_info["keyoff"]
        
        # 调用相同的候选生成逻辑（确保与匹配阶段一致）
        candidates, threshold, reason_if_empty = self._generate_sorted_candidates_within_threshold(
            other_notes_data,
            target_keyon=target_keyon,
            target_keyoff=target_keyoff,
            target_key_id=target_key_id
        )
        
        if not candidates:
            return reason_if_empty
        
        # 有在阈值内的候选，但未被匹配 -> 可能全被占用（回放侧无法得知占用情况）
        return f"可能所有候选已被占用(候选数:{len(candidates)}, 阈值:{threshold:.1f}ms)"
    
    def _calculate_note_times(self, note: Note) -> Tuple[float, float]:
        """
        计算音符的按键开始和结束时间
        
        Args:
            note: 音符对象
            
        Returns:
            Tuple[float, float]: (keyon_time, keyoff_time)
        """

        keyon_time = note.after_touch.index[0] + note.offset
        keyoff_time = note.after_touch.index[-1] + note.offset
        
        return keyon_time, keyoff_time
    
    # TODO  
    def get_global_average_delay(self) -> float:
        """
        计算整首曲子的平均时延（基于已配对数据）
        
        只使用 keyon_offset 计算：全局平均时延 = mean(|keyon_offset|)
        
        Returns:
            float: 平均时延（0.1ms单位）
        """
        if not self.matched_pairs:
            return 0.0
        
        # 获取偏移数据
        offset_data = self.get_offset_alignment_data()
        
        # 只使用keyon_offset的绝对值
        keyon_errors = [abs(item.get('keyon_offset', 0)) for item in offset_data if item.get('keyon_offset') is not None]
        
        if not keyon_errors:
            return 0.0
        
        # 计算平均值（0.1ms单位）
        average_delay = sum(keyon_errors) / len(keyon_errors)
        
        logger.info(f"📊 整首曲子平均时延(keyon): {average_delay/10:.2f}ms (基于{len(keyon_errors)}个匹配对)")
        
        return average_delay
    
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
                'duration_offset_stats': {'average': 0.0, 'max': 0.0, 'min': 0.0, 'std': 0.0},
                'overall_offset_stats': {'average': 0.0, 'max': 0.0, 'min': 0.0, 'std': 0.0}
            }
        
        # 获取偏移数据
        offset_data = self.get_offset_alignment_data()
        
        # 提取偏移值（只使用keyon_offset）
        keyon_offsets = [item['keyon_offset'] for item in offset_data]
        duration_offsets = [item.get('duration_offset', 0.0) for item in offset_data]
        # 整体统计只使用keyon_offset的绝对值
        overall_offsets = [abs(item.get('keyon_offset', 0)) for item in offset_data if item.get('keyon_offset') is not None]
        
        return {
            'total_pairs': len(self.matched_pairs),
            'keyon_offset_stats': self._calculate_offset_stats(keyon_offsets),
            'duration_offset_stats': self._calculate_offset_stats(duration_offsets),
            'overall_offset_stats': self._calculate_offset_stats(overall_offsets)  # 只使用keyon_offset
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
