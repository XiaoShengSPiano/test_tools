#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SPMID音符匹配器

负责SPMID数据的按键匹配，包括：
- 音符匹配算法
- 匹配对生成
- 匹配结果管理

匹配逻辑架构：
==========================================

【核心策略】
- 贪心匹配：每个录制音符只匹配一个最佳的播放音符
- 三阶段搜索：精确搜索(≤50ms) → 较差搜索(50ms-100ms) → 严重搜索(100ms-200ms)
- 六等级阈值：按误差范围精确分类 (20ms, 30ms, 50ms, 100ms, 200ms)

【匹配流程】
1. find_all_matched_pairs() - 主入口
   ├── 初始化匹配状态
   ├── 对每个录制音符调用 _find_match_for_single_note()
   └── 统计匹配结果

2. _find_match_for_single_note() - 单音符匹配
   ├── 提取音符信息 (_extract_note_info)
   ├── 生成候选列表 (_generate_candidates_for_note)
   ├── 选择最佳候选 (_select_best_candidate)
   └── 处理匹配结果 (精确匹配/近似匹配/失败)

3. _generate_candidates_for_note() - 候选生成
   ├── 第一阶段：阈值内候选 (_generate_sorted_candidates_within_threshold)
   ├── 第二阶段：如无候选则扩展到全局 (_generate_all_candidates_sorted)
   └── 第三阶段：应用扩展阈值过滤 (≤200ms)



"""

import pandas as pd
import numpy as np
from .spmid_reader import Note
from .delay_metrics import DelayMetrics
from typing import List, Tuple, Dict, Union, Optional, Any
from utils.logger import Logger
from enum import Enum
from collections import defaultdict
import heapq
import statistics

logger = Logger.get_logger()

from utils.constants import GRADE_THRESHOLDS, get_grade_by_delay

# 匹配阈值常量 (0.1ms单位) - 统一从 utils.constants 获取
EXCELLENT_THRESHOLD = GRADE_THRESHOLDS['excellent'] * 10.0
GOOD_THRESHOLD = GRADE_THRESHOLDS['good'] * 10.0
FAIR_THRESHOLD = GRADE_THRESHOLDS['fair'] * 10.0
POOR_THRESHOLD = GRADE_THRESHOLDS['poor'] * 10.0
SEVERE_THRESHOLD = GRADE_THRESHOLDS['severe'] * 10.0
# 失败匹配：> SEVERE_THRESHOLD (200ms)

# 多锤检测阈值 (ms) - 播放提前录制的阈值
# 如果播放keyon < 录制keyon - ADVANCE_THRESHOLD，认为是可疑的多锤
ADVANCE_THRESHOLD = 200.0  # 200ms

# Lookahead窗口配置 - 前瞻检查优化
# 查看堆顶前N个候选，选择综合得分最优的
LOOKAHEAD_WINDOW_SIZE = 3  # 窗口大小：查看前3个候选
# 播放提前录制时的惩罚系数
# score = error + (advance_time * BIAS_PENALTY_FACTOR)
BIAS_PENALTY_FACTOR = 2.0  # 提前惩罚系数：2倍

# 兼容性常量 (向后兼容)
PRECISION_THRESHOLD = FAIR_THRESHOLD      # 50ms - 精确匹配上限
APPROXIMATE_THRESHOLD = POOR_THRESHOLD    # 100ms - 较差匹配上限

# 匹配类型枚举 - 按误差等级细分
class MatchType(Enum):
    """匹配结果类型 - 按误差等级分类"""
    EXCELLENT = "excellent"      # 优秀匹配 (误差 ≤ 20ms)
    GOOD = "good"               # 良好匹配 (20ms < 误差 ≤ 30ms)
    FAIR = "fair"               # 一般匹配 (30ms < 误差 ≤ 50ms)
    POOR = "poor"               # 较差匹配 (50ms < 误差 ≤ 100ms)
    SEVERE = "severe"           # 严重匹配 (100ms < 误差 ≤ 200ms)
    FAILED = "failed"           # 失败匹配 (误差 > 200ms 或无候选)

# 匹配结果类
class MatchResult:
    """匹配结果封装类"""
    def __init__(self, match_type: MatchType, record_index: int,
                 replay_index: Optional[int] = None, error_ms: float = 0.0,
                 pair: Optional[Tuple[Note, Note]] = None, reason: str = ""):
        self.match_type = match_type
        self.record_index = record_index
        self.replay_index = replay_index
        self.error_ms = error_ms  # 误差(毫秒)
        self.pair = pair  # 匹配对 (record_note, replay_note)
        self.reason = reason  # 失败原因

    @property
    def is_success(self) -> bool:
        """是否匹配成功"""
        return self.match_type != MatchType.FAILED

# 候选信息类
class Candidate:
    """候选匹配信息"""
    def __init__(self, total_error: float, note: Note):
        self.total_error = total_error
        self.note = note

    @property
    def error_ms(self) -> float:
        """误差转换为毫秒"""
        return self.total_error / 10.0

    def add_match_result(self, match_result: MatchResult, corrected_offset_ms: float):
        """添加匹配结果"""
        if match_result.is_success:
            self.matched_count += 1
            self.offsets_ms.append(corrected_offset_ms)

            # 统计匹配质量
            if match_result.match_type == MatchType.EXCELLENT:
                self.excellent_count += 1
            elif match_result.match_type == MatchType.GOOD:
                self.good_count += 1
            elif match_result.match_type == MatchType.FAIR:
                self.fair_count += 1
            elif match_result.match_type == MatchType.POOR:
                self.poor_count += 1
            elif match_result.match_type == MatchType.SEVERE:
                self.severe_count += 1
        else:
            self.failed_count += 1

    def calculate_statistics(self):
        """计算统计信息"""
        if self.offsets_ms:
            self.median_offset = statistics.median(self.offsets_ms)
            self.mean_offset = statistics.mean(self.offsets_ms)
            self.min_offset = min(self.offsets_ms)
            self.max_offset = max(self.offsets_ms)
            self.range_offset = self.max_offset - self.min_offset

            if len(self.offsets_ms) > 1:
                self.std_offset = statistics.stdev(self.offsets_ms)
                self.variance_offset = statistics.variance(self.offsets_ms)
            else:
                self.std_offset = 0.0
                self.variance_offset = 0.0

    def __str__(self):
        return f"按键{self.key_id}: 录制{self.total_record_notes}, 播放{self.total_replay_notes}, 匹配{self.matched_count}, 失败{self.failed_count}, 均值{self.mean_offset:.2f}ms"

# 匹配统计类
class MatchStatistics:
    """匹配统计信息 - 六等级系统"""

    def __init__(self):
        # 六等级匹配统计 (使用统一 key)
        self.excellent_matches = 0    # 优秀匹配 (≤20ms)
        self.good_matches = 0         # 良好匹配 (20-30ms)
        self.fair_matches = 0         # 一般匹配 (30-50ms)
        self.poor_matches = 0         # 较差匹配 (50-100ms)
        self.severe_matches = 0       # 严重误差 (100-200ms)
        self.failed_matches = 0       # 失败匹配 (>200ms或无候选)

    def __str__(self):
        return f"优秀:{self.excellent_matches}, 良好:{self.good_matches}, 一般:{self.fair_matches}, 较差:{self.poor_matches}, 严重:{self.severe_matches}, 失败:{self.failed_matches}"

class NoteMatcher:
    """SPMID音符匹配器类"""
    
    def __init__(self):
        """
        初始化音符匹配器
        """
        # 匹配结果分类存储
        # 精确匹配对：(record_note, replay_note, match_type, keyon_error_ms)
        self.matched_pairs: List[Tuple[Note, Note, MatchType, float]] = []
        self.drop_hammers: List[Note] = []                   # 丢锤音符
        self.multi_hammers: List[Note] = []                  # 多锤音符
        self.abnormal_matches: List[Tuple[Note, Note]] = []  # 异常匹配对 (record_note, replay_note)
        self.duration_diff_pairs: List[Tuple[Note, Note, float]] = []  # 持续时间差异对 (rec_note, rep_note, ratio)

        # 匹配统计
        self.match_statistics = MatchStatistics()

        # 延时指标计算器（延迟初始化）
        self._delay_metrics: Optional[DelayMetrics] = None
    
    
    def find_all_matched_pairs(self, record_data: List[Note], replay_data: List[Note]) -> List[Tuple[Note, Note]]:
        """
        查找所有匹配对：基于最小堆的keyon优先匹配（支持双向拆分）
        
        核心特性：
        1. 按keyon时间顺序处理（最小堆）
        2. 贪心策略：keyon最小（在阈值内）
        3. 支持双向拆分（录制/播放都可拆分）
        4. 保留6等级质量评判
        5. 动态重新匹配
        
        匹配流程：
        1. 按key_id分组
        2. 对每个按键构建最小堆（按keyon排序）
        3. 按keyon顺序匹配，检测持续时间差异并拆分
        4. 拆分后的数据重新加入堆
        
        
        Args:
            record_data: 录制数据
            replay_data: 播放数据

        Returns:
            List[Tuple[Note, Note]]: 精确匹配对列表 (record_note, replay_note)
        """
        # 按key_id分组
        record_by_key = self._group_notes_by_key(record_data)
        replay_by_key = self._group_notes_by_key(replay_data)

        # 对每个按键进行匹配
        all_matched_pairs = []
        for key_id in sorted(record_by_key.keys()):
            key_record_notes = record_by_key[key_id]
            key_replay_notes = replay_by_key.get(key_id, [])

            key_matched_pairs = self._match_single_key_with_heap(
                key_id, key_record_notes, key_replay_notes
            )
            all_matched_pairs.extend(key_matched_pairs)

        
        # 输出最终统计信息
        logger.info(f"📊 匹配完成统计:")
        logger.info(f"   ✅ 正常匹配对 (matched_pairs): {len(self.matched_pairs)}")
        logger.debug(f"   [DEBUG] all_matched_pairs长度: {len(all_matched_pairs)}")
        logger.info(f"   ⚠️ 异常匹配对 (abnormal_matches): {len(self.abnormal_matches)}")
        logger.info(f"   ⚠️ 丢锤 (drop_hammers): {len(self.drop_hammers)}")
        logger.info(f"   ⚠️ 多锤 (multi_hammers): {len(self.multi_hammers)}")
        logger.info(f"   评级统计:")
        logger.info(f"      - excellent (≤20ms): {self.match_statistics.excellent_matches}")
        logger.info(f"      - good (20-30ms): {self.match_statistics.good_matches}")
        logger.info(f"      - fair (30-50ms): {self.match_statistics.fair_matches}")
        logger.info(f"      - poor (50-100ms): {self.match_statistics.poor_matches}")
        logger.info(f"      - severe (100-200ms): {self.match_statistics.severe_matches}")
        
        return all_matched_pairs
    
    def _match_single_key_with_heap(self, key_id: int,
                                     record_notes: List[Note],
                                     replay_notes: List[Note]) -> List[Tuple[Note, Note]]:
        """
        使用最小堆对单个按键进行匹配（支持拆分）

        Args:
            key_id: 按键ID
            record_notes: 该按键的录制音符列表
            replay_notes: 该按键的播放音符列表

        Returns:
            List[Tuple[Note, Note]]: 该按键的匹配对列表 (record_note, replay_note)
        """
        
        # 构建最小堆
        record_heap, replay_heap = self._build_matching_heaps(key_id, record_notes, replay_notes)
        
        # 初始化状态
        matched_pairs = []
        used_replay_uuids = set()  # 已使用的播放音符UUID
        skipped_replay_uuids = set()  # 跳过的播放音符UUID（可疑的多锤）
        
        
        # 主循环：处理所有录制数据
        match_count, failed_count = self._process_record_notes(
            key_id, record_heap, replay_heap, used_replay_uuids,
            skipped_replay_uuids, matched_pairs
        )
        
        logger.debug(f"按键{key_id}匹配完成: 成功{match_count}个, 失败{failed_count}个")
        
        return matched_pairs
    
    def _build_matching_heaps(self, key_id: int,
                               record_notes: List[Note],
                               replay_notes: List[Note]) -> Tuple[List, List]:
        """
        构建录制和播放的最小堆
        
        Args:
            key_id: 按键ID
            record_notes: 录制音符列表
            replay_notes: 播放音符列表
            
        Returns:
            Tuple[List, List]: (record_heap, replay_heap)
        """
        # 堆元素格式: (key_on_ms, uuid, note_object, split_seq)
        # key_on_ms: 用于堆排序
        # uuid: 唯一识别号，防止同时间点时比较Note对象（会导致Pandas Series比较错误）
        # split_seq: None=原始数据, 0/1/2...=拆分序号

        # 录制堆
        record_heap = []
        for note in record_notes:
            heapq.heappush(record_heap, (note.key_on_ms, note.uuid, note, None))

        # 播放堆
        replay_heap = []
        for note in replay_notes:
            heapq.heappush(replay_heap, (note.key_on_ms, note.uuid, note, None))

        
        return record_heap, replay_heap
    
    def _process_record_notes(self, key_id: int, record_heap: List, replay_heap: List,
                                used_replay_uuids: set, skipped_replay_uuids: set,
                                matched_pairs: List) -> Tuple[int, int]:
        """
        处理所有录制数据的主循环

        Args:
            key_id: 按键ID
            record_heap: 录制堆
            replay_heap: 播放堆
            used_replay_uuids: 已使用的播放音符UUID集合
            skipped_replay_uuids: 跳过的播放音符UUID集合（可疑的多锤）
            matched_pairs: 匹配对列表（输出）

        Returns:
            Tuple[int, int]: (成功匹配数, 失败匹配数)
        """
        match_count = 0
        failed_count = 0
        
        while record_heap:
            # 取出录制数据
            rec_keyon, rec_uuid, rec_note, rec_split_seq = heapq.heappop(record_heap)
            
            logger.debug(f"    处理录制Note: UUID={rec_note.uuid[:8]}..., key_on={rec_note.key_on_ms:.2f}ms, split_seq={rec_split_seq}")
            
            # 清理已使用的播放数据
            self._clean_used_replay_notes(replay_heap, used_replay_uuids)
            
            # 查找播放候选（支持跳过可疑的多锤）
            replay_candidate = self._find_replay_candidate(
                replay_heap, rec_note, skipped_replay_uuids
            )
            
            if replay_candidate is None:
                # 无可用候选 → 失败
                failed_count += 1
                continue
            
            rep_note, keyon_error_ms = replay_candidate
            
            # 检查误差阈值
            if not self._check_error_threshold(keyon_error_ms):
                # 超出阈值 → 失败
                failed_count += 1
                continue
            
            # 创建成功匹配（支持拆分，在pop播放数据之前检查是否需要拆分）
            success, split_type = self._create_successful_match(
                rec_note, rep_note,
                keyon_error_ms, matched_pairs, used_replay_uuids,
                record_heap, replay_heap
            )
            
            if success:
                # 匹配成功：消费播放数据
                heapq.heappop(replay_heap)
                match_count += 1
                logger.debug(f"    ✓ 匹配成功 (match_count={match_count})")
            else:
                logger.debug(f"    ✗ 匹配失败")
        
        return match_count, failed_count
    
    def _clean_used_replay_notes(self, replay_heap: List, used_replay_uuids: set):
        """清理播放堆顶的已使用数据（惰性删除）"""
        while replay_heap:
            _, _, rep_note, _ = replay_heap[0]  # 堆元素: (key_on_ms, uuid, note, split_seq)

            if rep_note.uuid in used_replay_uuids:
                heapq.heappop(replay_heap)
                continue
            else:
                break
    
    def _find_replay_candidate(self, replay_heap: List, rec_note: Note,
                                skipped_replay_uuids: set) -> Optional[Tuple[Note, float]]:
        """
        使用Lookahead窗口查找最佳播放候选
        
        策略：
        1. 先跳过提前超过200ms的候选（ADVANCE_THRESHOLD检测）
        2. Peek前N个候选进行综合评分
        3. 选择得分最低的候选
        4. 跳过前面的次优候选
        
        Args:
            replay_heap: 播放堆 (key_on_ms, note, split_seq)
            rec_note: 录制Note对象
            skipped_replay_uuids: 跳过的播放音符UUID集合（输出）
            
        Returns:
            Optional[Tuple[Note, float]]: (rep_note, error_ms) 或 None
        """
        if not replay_heap:
            logger.debug(f"      ✗ 无可用播放数据 → 失败")
            return None
        
        rec_keyon = rec_note.key_on_ms
        
        # 【第一道防线】循环跳过"提前过多"的播放数据（>200ms，极端情况）+ 锤速异常检测
        while replay_heap:
            _, _, rep_note, _ = replay_heap[0]
            rep_keyon = rep_note.key_on_ms
            
            # 检查条件1：播放是否"提前"过多？
            if rep_keyon < rec_keyon - ADVANCE_THRESHOLD:
                # 播放明显提前录制，可能是多锤
                heapq.heappop(replay_heap)
                skipped_replay_uuids.add(rep_note.uuid)
                continue

            # 检查条件2：锤速异常检测（录制无锤速但播放有锤速 = 多锤）
            if self._is_multi_hammer_by_velocity(rec_note, rep_note):
                # 录制数据无锤速，播放数据有锤速，判定为多锤
                heapq.heappop(replay_heap)
                skipped_replay_uuids.add(rep_note.uuid)
                continue
            
            # 两个条件都不满足，跳出循环
            break
        
        # 检查是否还有可用候选
        if not replay_heap:
            logger.debug(f"      ✗ 跳过多锤后无可用播放数据 → 失败")
            return None
        
        # 【第二道防线】Lookahead窗口评分，选择最佳候选
        best_candidate = self._select_best_candidate_with_lookahead(
            replay_heap, rec_keyon, skipped_replay_uuids
        )
        
        if best_candidate is None:
            logger.debug(f"      ✗ Lookahead评分后无可接受候选 → 失败")
            return None
        
        return best_candidate
    
    def _select_best_candidate_with_lookahead(self, replay_heap: List, rec_keyon: float,
                                               skipped_replay_uuids: set) -> Optional[Tuple[Note, float]]:
        """
        使用Lookahead窗口评分并选择最佳候选
        
        Args:
            replay_heap: 播放堆 (key_on_ms, note, split_seq)
            rec_keyon: 录制keyon时间（ms）
            skipped_replay_uuids: 跳过的播放音符UUID集合（输出）
            
        Returns:
            Optional[Tuple[Note, float]]: (rep_note, error_ms) 或 None
        """
        # 1. Peek前N个候选
        window_size = min(LOOKAHEAD_WINDOW_SIZE, len(replay_heap))
        candidates = []
        
        for i in range(window_size):
            rep_keyon, rep_uuid, rep_note, rep_split_seq = replay_heap[i]
            candidates.append({
                'heap_index': i,
                'keyon': rep_keyon,
                'note': rep_note
            })
        
        # 2. 对候选进行评分
        scored_candidates = []
        for candidate in candidates:
            score_result = self._calculate_candidate_score(candidate, rec_keyon)
            scored_candidates.append(score_result)
        
        # 3. 选择得分最低的
        scored_candidates.sort(key=lambda x: x['score'])
        best = scored_candidates[0]
        best_index = best['candidate']['heap_index']
        
        # 4. 跳过前面的次优候选
        if best_index > 0:
            for i in range(best_index):
                _, _, rep_note, _ = heapq.heappop(replay_heap)
                skipped_replay_uuids.add(rep_note.uuid)

        # 5. 返回最佳候选（现在在堆顶）
        _, _, rep_note, _ = replay_heap[0]
        keyon_error_ms = best['error']

        return (rep_note, keyon_error_ms)
    
    def _is_multi_hammer_by_velocity(self, rec_note: Note, rep_note: Note) -> bool:
        """
        通过锤速检测是否为多锤
        
        判定条件：录制无锤速或锤速=0，但播放有锤速>0
        """
        rec_hammer = rec_note.get_first_hammer_velocity()
        rep_hammer = rep_note.get_first_hammer_velocity()
        
        rec_no_hammer = (rec_hammer is None or rec_hammer == 0)
        rep_has_hammer = (rep_hammer is not None and rep_hammer > 0)
        
        return rec_no_hammer and rep_has_hammer

    def _calculate_candidate_score(self, candidate: dict, rec_keyon: float) -> dict:
        """
        计算候选的综合得分
        
        评分公式：score = error + bias_penalty
        - error: 绝对误差
        - bias_penalty: 偏向惩罚（提前时加倍惩罚）
        
        Args:
            candidate: 候选信息字典
            rec_keyon: 录制keyon时间（ms）
            
        Returns:
            dict: 评分结果
        """
        replay_keyon = candidate['keyon']
        
        # 1. 基础误差
        error = abs(replay_keyon - rec_keyon)
        
        # 2. 计算偏向（正数=滞后，负数=提前）
        bias = replay_keyon - rec_keyon
        
        # 3. 计算偏向惩罚
        if bias >= 0:  # 滞后（正常现象）
            penalty = 0  # 不惩罚
        else:  # 提前（可疑）
            advance = abs(bias)
            penalty = advance * BIAS_PENALTY_FACTOR  # 提前惩罚
        
        # 4. 综合得分
        total_score = error + penalty
        
        return {
            'candidate': candidate,
            'keyon': replay_keyon,
            'score': total_score,
            'error': error,
            'bias': bias,
            'penalty': penalty
        }

    
    def _check_error_threshold(self, keyon_error_ms: float) -> bool:
        """
        检查误差是否在阈值内（≤200ms）
        
        Args:
            keyon_error_ms: keyon误差（毫秒）
        
        Returns:
            bool: True=在阈值内, False=超出阈值
        """
        keyon_error_units = keyon_error_ms * 10.0
        
        if keyon_error_units > SEVERE_THRESHOLD:
            return False
        
        return True
    

    
    def _create_successful_match(self, rec_note: Note, rep_note: Note,
                                  keyon_error_ms: float, matched_pairs: List,
                                  used_replay_uuids: set, record_heap: List, replay_heap: List) -> Tuple[bool, str]:
        """
        创建成功匹配（支持拆分）
        
        Args:
            rec_note: 录制Note对象（包含split_seq属性）
            rep_note: 播放Note对象（包含split_seq属性）
            keyon_error_ms: keyon误差（毫秒）
            matched_pairs: 匹配对列表
            used_replay_uuids: 已使用的播放UUID集合
            record_heap: 录制堆
            replay_heap: 播放堆
        
        Returns:
            Tuple[bool, str]: (是否成功, 拆分类型: 'none'/'record'/'replay')
        """
        # 步骤1: 先检查持续时间差异并尝试拆分
        rec_duration = rec_note.duration_ms 
        rep_duration = rep_note.duration_ms
        
        if rec_duration > 0 and rep_duration > 0:
            duration_ratio = max(rec_duration, rep_duration) / min(rec_duration, rep_duration)
            
            should_split = False
            force_record = False
            
            # 主要条件：持续时间差异显著（>= 2.0倍）
            if duration_ratio >= 2.0:
                should_split = True

            # 次要条件：持续时间相差不大，但短数据keyoff之后还有hammer和after_touch
            elif rec_duration != rep_duration:  # 确保有长短之分
                long_note = rec_note if rec_duration > rep_duration else rep_note
                short_note = rep_note if rec_duration > rep_duration else rec_note
                
                if self._check_hammer_after_shorter_keyoff(long_note, short_note):
                    should_split = True
                    force_record = True  # 次要条件触发时需要强制记录

            # 如果满足任一条件，进行拆分
            if should_split:
                # 重要：在拆分之前先记录原始数据到持续时间差异列表
                # 这样可以在UI中看到拆分前的原始曲线
                self._check_duration_difference(rec_note, rep_note, force_record=force_record)

                # 尝试拆分并立即匹配第一部分
                split_result = self._try_split_and_match_first(
                    rec_note,
                    rep_note,
                    record_heap, replay_heap, used_replay_uuids,
                    rec_duration, rep_duration
                )
                
                if split_result is not None:
                    # 拆分成功，更新为拆分后的Note对象（第一部分）
                    split_type, match_rec_note, match_rep_note = split_result
                    rec_note = match_rec_note
                    rep_note = match_rep_note
                else:
                    logger.warning(f"      ⚠️ 拆分失败，按原匹配处理")
        
        # 步骤2: 用最终的Note对象（拆分后的或原始的）计算误差和评级
        final_keyon_error_ms = abs(rep_note.key_on_ms - rec_note.key_on_ms)
        match_type = self._evaluate_match_quality(final_keyon_error_ms)
        
        # 步骤3: 根据hammer数据分类匹配对
        rec_hammer = rec_note.get_first_hammer_velocity() or 0
        rep_hammer = rep_note.get_first_hammer_velocity() or 0

        # 分类逻辑（按优先级）
        if rec_hammer <= 0 and rep_hammer <= 0:
            # 情况1：双方都无hammer → 异常匹配对
            self.abnormal_matches.append((rec_note, rep_note))
        elif rec_hammer > 0 and rep_hammer <= 0:
            # 情况2：录制有hammer，播放无hammer → 丢锤
            self.drop_hammers.append(rec_note)
        elif rep_hammer > 0 and rec_hammer <= 0:
            # 情况3：播放有hammer，录制无hammer → 多锤
            self.multi_hammers.append(rep_note)
        else:
            # 情况4：双方都有hammer → 精确匹配对
            # 保存匹配对，包含评级信息和误差
            self.matched_pairs.append((rec_note, rep_note, match_type, final_keyon_error_ms))

            # 根据误差等级统计
            if match_type == MatchType.EXCELLENT:
                self.match_statistics.excellent_matches += 1
            elif match_type == MatchType.GOOD:
                self.match_statistics.good_matches += 1
            elif match_type == MatchType.FAIR:
                self.match_statistics.fair_matches += 1
            elif match_type == MatchType.POOR:
                self.match_statistics.poor_matches += 1
            elif match_type == MatchType.SEVERE:
                self.match_statistics.severe_matches += 1
        
        # 标记为已使用
        used_replay_uuids.add(rep_note.uuid)
        
        return (True, 'none')  # 成功创建，无拆分
    
    def _try_split_and_match_first(self, rec_note: Note,
                                     rep_note: Note,
                                     record_heap: List, replay_heap: List, used_replay_uuids: set,
                                     rec_duration: float, rep_duration: float) -> Optional[Tuple[str, Note, Note]]:
        """
        尝试拆分并返回第一部分用于立即匹配
        
        Args:
            rec_note: 录制音符
            rep_note: 播放音符
            record_heap: 录制堆
            replay_heap: 播放堆
            used_replay_uuids: 已使用的播放音符集合
            rec_duration: 录制持续时间
            rep_duration: 播放持续时间
        
        Returns:
            Optional[Tuple[str, Note, Note]]: (拆分类型, 匹配用的rec_note, 匹配用的rep_note) 或 None
        """
        from backend.key_splitter_simplified import KeySplitter
        
        # 判断拆分方向
        if rec_duration > rep_duration:
            # 录制数据更长 → 拆分录制数据
            logger.debug(f"        拆分录制数据（录制{rec_duration:.1f}ms > 播放{rep_duration:.1f}ms）")
            result = self._split_record_note_and_return_first(
                rec_note, rep_note, record_heap,
                rec_duration, rep_duration
            )
            if result:
                rec_note_a, rec_note_b = result
                # rec_note_a用于匹配，rec_note_b已加入堆
                return ('record', rec_note_a, rep_note)
            return None
        else:
            # 播放数据更长 → 拆分播放数据
            result = self._split_replay_note_and_return_first(
                rep_note, rec_note, replay_heap, used_replay_uuids,
                rec_duration, rep_duration
            )
            if result:
                rep_note_a, rep_note_b = result
                # rep_note_a用于匹配，rep_note_b已加入堆
                return ('replay', rec_note, rep_note_a)
            return None
    
    def _split_note_and_return_first(self, long_note: Note, short_note: Note,
                                     target_heap: List,
                                     rec_duration: float, rep_duration: float,
                                     data_type: str) -> Optional[Tuple[Note, Note]]:
        """
        拆分Note并返回两个Note对象（通用方法）
        
        Args:
            long_note: 长数据（要拆分的）
            short_note: 短数据
            target_heap: 目标堆（将note_b加入）
            rec_duration: 录制数据持续时间
            rep_duration: 播放数据持续时间
            data_type: 数据类型标识（"录制"或"播放"），用于日志
        
        Returns:
            Optional[Tuple[Note, Note]]: (note_a用于匹配, note_b已加入堆) 或 None
        """
        # 提取hammers（只考虑velocity > 0的）
        hammer_times_ms = []
        for i in range(len(long_note.hammers)):
            if long_note.hammers.values[i] > 0:
                time_ms = long_note.hammers.values[i]
                hammer_times_ms.append(time_ms)
        
        hammer_times_ms.sort()
        
        # 检查是否有足够的hammer（至少2个）
        if len(hammer_times_ms) < 2:
            logger.debug(f"        ✗ {data_type}数据hammer不足2个，无法拆分")
            return None
        
        # 使用精细的拆分点查找算法
        split_time_ms = self._find_best_split_point(
            long_note=long_note,
            short_note=short_note,
            rec_duration=rec_duration,
            rep_duration=rep_duration
        )
        
        if split_time_ms is None:
            logger.debug(f"        ✗ 未找到合适的拆分点")
            return None
        
        # 执行拆分
        note_a, note_b = self._split_note_at_time(
            long_note, split_time_ms,
            split_seq_a=0,  # 第一部分
            split_seq_b=1   # 第二部分
        )
        
        # 将note_b加入堆（note_a用于立即匹配）
        heapq.heappush(target_heap, (note_b.key_on_ms, note_b.uuid, note_b, note_b.split_seq if note_b.split_seq is not None else 0))
        
        # ⚠️ 重要：不要将 note_b 标记为 used_uuids！
        # note_b 是拆分后的第二部分，需要在后续循环中重新匹配
        # 如果标记为 used，它会在 _clean_used_replay_notes 中被删除
        
        logger.debug(f"[DEBUG]        ✓ 拆分成功，note_b (UUID={note_b.uuid[:8]}...) 已加入堆，等待重新匹配")
        
        return (note_a, note_b)
    
    def _split_replay_note_and_return_first(self, rep_note: Note, rec_note: Note,
                                              replay_heap: List, used_replay_uuids: set,
                                              rec_duration: float, rep_duration: float) -> Optional[Tuple[Note, Note]]:
        """拆分播放数据（简化wrapper）
        
        注意：used_replay_uuids 参数保留是为了兼容调用接口，但不会在拆分时使用。
        拆分后的 note_b 会被加入堆，在后续循环中重新匹配时才会被标记为 used。
        """
        return self._split_note_and_return_first(
            long_note=rep_note, short_note=rec_note,
            target_heap=replay_heap,
            rec_duration=rec_duration, rep_duration=rep_duration,
            data_type="播放"
        )
    
    def _split_record_note_and_return_first(self, rec_note: Note, rep_note: Note,
                                              record_heap: List,
                                              rec_duration: float, rep_duration: float) -> Optional[Tuple[Note, Note]]:
        """拆分录制数据（简化wrapper）
        
        拆分后的 note_b 会被加入录制堆，在后续循环中重新匹配。
        """
        return self._split_note_and_return_first(
            long_note=rec_note, short_note=rep_note,
            target_heap=record_heap,
            rec_duration=rec_duration, rep_duration=rep_duration,
            data_type="录制"
        )
    
    def _find_best_split_point(self, long_note: Note, short_note: Note, 
                              rec_duration: float, rep_duration: float) -> Optional[float]:
        """
        查找最佳拆分点
        
        Args:
            long_note: 较长的Note对象（要拆分的合并数据）
            short_note: 较短的Note对象（提供keyoff作为搜索起点）
            rec_duration: 录制数据持续时间
            rep_duration: 播放数据持续时间
        
        Returns:
            Optional[float]: 最佳拆分点的绝对时间（ms），如果未找到则返回None
            
        Note:
            KeySplitter使用通用的参数命名：
            - short_note: 短数据 (参考数据)
            - long_note: 长数据 (要拆分的合并数据)
            这适用于录制和播放数据的任意组合
        """
        try:
            from backend.key_splitter_simplified import KeySplitter
            
            # 创建KeySplitter实例
            splitter = KeySplitter()
            
            # 调试信息：输出要拆分的数据
            logger.debug(f"        🔍 拆分点查找参数:")
            logger.debug(f"          短数据: keyon={short_note.key_on_ms:.1f}ms, keyoff={short_note.key_off_ms:.1f}ms")
            logger.debug(f"          长数据: keyon={long_note.key_on_ms:.1f}ms, keyoff={long_note.key_off_ms:.1f}ms")
            
            # 提取长数据的hammers（检查是否足够）
            long_hammers = []
            for i in range(len(long_note.hammers)):
                if long_note.hammers.values[i] > 0:
                    time_ms = long_note.hammers.values[i]
                    long_hammers.append(time_ms)
            long_hammers.sort()
            logger.debug(f"          长数据hammers(>0): {[f'{h:.1f}ms' for h in long_hammers]}")
            
            # 调用KeySplitter（使用通用接口）
            result = splitter.analyze_split_possibility(
                short_note=short_note,        # 短数据（参考数据）
                long_note=long_note,          # 长数据（要拆分的）
                short_duration=min(rec_duration, rep_duration),
                long_duration=max(rec_duration, rep_duration)
            )
            
            # 检查是否找到最佳分割点
            if result and result.get('best_candidate'):
                best = result['best_candidate']
                split_time_ms = best['time']  # 注意：键名是'time'不是'time_ms'
                
                # 日志输出
                if best.get('is_turning', False):  # 注意：键名是'is_turning'不是'is_turning_point'
                    logger.debug(f"        ✓ 找到最佳拆分点（拐点）: {split_time_ms:.1f}ms, "
                               f"触后值={best.get('value', 0):.1f}")
                else:
                    logger.debug(f"        ⚠️ 使用后备策略（触后值最小点）: {split_time_ms:.1f}ms, "
                               f"触后值={best.get('value', 0):.1f}")
                
                return split_time_ms
            else:
                if result:
                    logger.debug(f"        ⚠️ KeySplitter返回结果但无best_candidate: {list(result.keys())}")
                else:
                    logger.debug(f"        ⚠️ KeySplitter返回None（可能原因：hammer不足2个或范围无效）")
                return None
                
        except Exception as e:
            logger.error(f"        ✗ 拆分点查找失败: {e}")
            return None
    
    def _split_note_at_time(self, note: Note, split_time_ms: float, 
                           split_seq_a: int, split_seq_b: int) -> Tuple[Note, Note]:
        """
        在指定时间点拆分Note
        
        Args:
            note: 要拆分的Note对象
            split_time_ms: 拆分点的绝对时间（ms）
            split_seq_a: 前半段的拆分序号
            split_seq_b: 后半段的拆分序号
        
        Returns:
            Tuple[Note, Note]: (前半段, 后半段)
        """

        # 将split_time_ms（绝对时间）转换为相对于offset的索引（0.1ms单位）
        # split_time_ms是绝对时间，after_touch.index是相对于offset的索引
        # 所以：relative_index = absolute_time * 10 - offset
        split_time_units = split_time_ms * 10 - note.offset
        
        # logger.debug(f"        拆分参数: split_time={split_time_ms:.1f}ms (绝对时间), "
        #             f"offset={note.offset}, split_units={split_time_units} (相对索引)")
        
        # 拆分aftertouch：拆分点同时出现在note_a的末尾和note_b的开头
        # note_a: <= split_time（包含拆分点作为结束点）
        # note_b: >= split_time（包含拆分点作为起始点）
        mask1 = note.after_touch.index <= split_time_units
        mask2 = note.after_touch.index >= split_time_units
        
        after_touch_a = note.after_touch[mask1].copy()
        after_touch_b = note.after_touch[mask2].copy()
        
        # 如果拆分点不在原始after_touch中，需要插入
        if split_time_units not in note.after_touch.index:
            # 插值计算拆分点的触后值
            if not after_touch_a.empty and not after_touch_b.empty:
                # 使用线性插值
                prev_idx = after_touch_a.index[-1]
                next_idx = after_touch_b.index[0]
                prev_val = after_touch_a.iloc[-1]
                next_val = after_touch_b.iloc[0]
                
                if next_idx > prev_idx:
                    ratio = (split_time_units - prev_idx) / (next_idx - prev_idx)
                    split_val = prev_val + ratio * (next_val - prev_val)
                else:
                    split_val = prev_val
                
                # 插入拆分点到after_touch_a和after_touch_b
                after_touch_a = pd.concat([after_touch_a, pd.Series([split_val], index=[split_time_units])]).sort_index()
                after_touch_b = pd.concat([pd.Series([split_val], index=[split_time_units]), after_touch_b]).sort_index()
                logger.debug(f"        ℹ️ 在拆分点{split_time_units}插值after_touch={split_val:.1f}")
        
        # 拆分hammers：第一个按键只包含第一个hammer，第二个按键包含后续hammers
        # note_a: < split_time（不包含拆分点的hammer）
        # note_b: >= split_time（包含拆分点及之后的hammers）
        hammers_a = note.hammers[note.hammers.index < split_time_units].copy()
        hammers_b = note.hammers[note.hammers.index >= split_time_units].copy()
        
        # 确保note_b的key_on就是拆分点：
        # 如果hammers_b为空或第一个hammer不在拆分点，在拆分点插入hammer
        if hammers_b.empty or hammers_b.index[0] != split_time_units:
            if not after_touch_b.empty:
                # 在拆分点创建hammer（velocity=0表示虚拟hammer）
                split_hammer = pd.Series([0], index=[split_time_units])
                if hammers_b.empty:
                    hammers_b = split_hammer
                    logger.debug(f"        ℹ️ note_b无hammer，在拆分点{split_time_units}创建虚拟hammer")
                else:
                    # 合并拆分点hammer和后续hammers
                    hammers_b = pd.concat([split_hammer, hammers_b])
                    logger.debug(f"        ℹ️ 在拆分点{split_time_units}插入hammer，确保key_on=拆分点")
        
        # 创建新的Note对象（设置split元数据）
        # note_a（第一个note）保持原有UUID，note_b（第二个note）分配新UUID
        # 
        # UUID分配策略：
        # - note_a: 保持原UUID（如果原note已经是拆分的，保持其原UUID）
        # - note_b: 基于原UUID + 拆分序号生成新UUID
        #   如果原note的UUID已经包含"_split_"，需要追加新的序号
        
        # 生成note_b的UUID
        if "_split_" in note.uuid:
            # 已经是拆分后的Note，追加新的拆分序号
            note_b_uuid = f"{note.uuid}_{split_seq_b}"
        else:
            # 第一次拆分，使用标准格式
            note_b_uuid = f"{note.uuid}_split_{split_seq_b}"
        
        note_a = Note(
            offset=note.offset,
            id=note.id,
            finger=note.finger,
            hammers=hammers_a,
            uuid=note.uuid,  # 第一个note保持原有UUID
            velocity=note.velocity,
            after_touch=after_touch_a,
            split_parent_idx=None,  # 不再需要索引
            split_seq=split_seq_a,
            is_split=True
        )

        note_b = Note(
            offset=note.offset,  # offset保持不变
            id=note.id,
            finger=note.finger,
            hammers=hammers_b,
            uuid=note_b_uuid,  # 使用生成的UUID，避免冲突
            velocity=note.velocity,
            after_touch=after_touch_b,
            split_parent_idx=None,  # 不再需要索引
            split_seq=split_seq_b,
            is_split=True
        )
        
        logger.debug(f"        ✓ note_a: key_on={note_a.key_on_ms:.1f}ms, key_off={note_a.key_off_ms:.1f}ms, "
                    f"duration={note_a.duration_ms:.1f}ms")
        logger.debug(f"        ✓ note_b: key_on={note_b.key_on_ms:.1f}ms, key_off={note_b.key_off_ms:.1f}ms, "
                    f"duration={note_b.duration_ms:.1f}ms")
        
        return note_a, note_b
    
    def _check_hammer_after_shorter_keyoff(self, long_note: Note, short_note: Note) -> bool:
        """
        检查在较短数据的keyoff之后，较长数据是否还有有效的锤击和aftertouch
        
        Args:
            long_note: 较长的Note对象
            short_note: 较短的Note对象
        
        Returns:
            bool: 如果在短数据keyoff之后还有hammer（velocity>0）且after_touch不为空，返回True
        """

        short_keyoff_ms = short_note.key_off_ms
        if short_keyoff_ms is None:
            return False
        
        short_keyoff_units = short_keyoff_ms * 10
        
        # 检查长数据在此时间之后是否还有hammer（velocity > 0）
        has_hammer_after = False
        for i in range(len(long_note.hammers)):
            hammer_time_units = long_note.hammers.index[i] + long_note.offset
            hammer_velocity = long_note.hammers.values[i]
            
            if hammer_time_units > short_keyoff_units and hammer_velocity > 0:
                has_hammer_after = True
                logger.debug(f"        🔨 检测到短数据keyoff({short_keyoff_ms:.1f}ms)之后的锤击: "
                           f"{hammer_time_units/10:.1f}ms, velocity={hammer_velocity}")
                break
        
        if not has_hammer_after:
            return False
        
        # 检查长数据在此时间之后是否还有after_touch数据
        has_aftertouch_after = False
        for at_time_units in long_note.after_touch.index:
            absolute_time_units = at_time_units + long_note.offset
            if absolute_time_units > short_keyoff_units:
                has_aftertouch_after = True
                logger.debug(f"        📊 检测到短数据keyoff之后的after_touch数据")
                break
        
        return has_hammer_after and has_aftertouch_after
    
    def _check_duration_difference(self, record_note: Note, replay_note: Note, force_record: bool = False):
        """
        检查匹配对的持续时间差异，如果差异显著则记录

        Args:
            record_note: 录制音符
            replay_note: 播放音符
            force_record: 是否强制记录（即使不满足主要条件）
        """
        # 获取持续时间
        record_duration = record_note.duration_ms
        replay_duration = replay_note.duration_ms

        # 检查是否有有效的持续时间数据
        if record_duration is None or replay_duration is None or record_duration <= 0 or replay_duration <= 0:
            return

        # 计算持续时间比例
        duration_ratio = max(record_duration, replay_duration) / min(record_duration, replay_duration)

        # 如果持续时间差异显著（大约2倍以上）或强制记录，记录下来
        if duration_ratio >= 2.0 or force_record:
            # 记录差异匹配对（包含keyon和keyoff）
            self.duration_diff_pairs.append((
                record_note,
                replay_note,
                duration_ratio,
            ))

            # 输出日志
            logger.debug(f"🔍 发现持续时间差异显著的匹配对: 按键{record_note.uuid} "
                       f"录制[{record_note.key_on_ms:.2f}-{record_note.key_off_ms:.2f}ms, {record_note.duration_ms:.2f}ms], "
                       f"播放[{replay_note.key_on_ms:.2f}-{replay_note.key_off_ms:.2f}ms, {replay_note.duration_ms:.2f}ms], "
                        f"比例={duration_ratio:.2f}")


    def _group_notes_by_key(self, notes: List[Note]) -> Dict[int, List[Note]]:
        """
        按按键ID分组音符数据

        Args:
            notes: 音符列表

        Returns:
            Dict[int, List[Note]]: key=按键ID, value=音符对象列表
        """
        grouped = defaultdict(list)
        for note in notes:
            grouped[note.id].append(note)
        return dict(grouped)

    def get_key_statistics_for_bar_chart(self) -> List[Dict[str, Union[int, float]]]:
        """
        获取按键统计信息用于条形统计图

        直接使用预计算的按键统计信息，避免重复计算

        Returns:
            List[Dict[str, Union[int, float]]]: 按键统计数据列表，每个元素包含:
            - key_id: 按键ID
            - median: 中位数偏移 (ms)
            - mean: 均值偏移 (ms)
            - std: 标准差 (ms)
            - variance: 方差 (ms²)
            - count: 该按键成功匹配对数量
        """
        result = []

        for key_id, key_stats in self.key_statistics.items():
            # 只包含有匹配数据的按键
            if key_stats.matched_count > 0 and key_stats.offsets_ms:
                result.append({
                    'key_id': key_id,
                    'count': key_stats.matched_count,
                    'median': round(key_stats.median_offset, 3),
                    'mean': round(key_stats.mean_offset, 3),
                    'std': round(key_stats.std_offset, 3),
                    'variance': round(key_stats.variance_offset, 3),
                    'min': round(key_stats.min_offset, 3),
                    'max': round(key_stats.max_offset, 3),
                    'range': round(key_stats.range_offset, 3),
                    'status': 'matched'
                })

        # 按按键ID排序
        result.sort(key=lambda x: x['key_id'])

        logger.debug(f"📊 条形统计图数据: {len(result)}个按键有统计信息")
        return result


    def _evaluate_match_quality(self, error_ms: float) -> MatchType:
        """
        根据误差评估匹配质量 - 统一六等级标准
        """
        grade_key = get_grade_by_delay(error_ms)
        # 将 constants 中的 key 映射到 MatchType 枚举值
        try:
            return MatchType(grade_key)
        except ValueError:
            return MatchType.FAILED

    def _create_match_result(self, match_type: MatchType, record_index: int,
                           replay_index: Optional[int] = None, candidate: Optional[Candidate] = None,
                           record_note: Optional[Note] = None, replay_note: Optional[Note] = None,
                           reason: str = "") -> MatchResult:
        """
        创建匹配结果对象

        Args:
            match_type: 匹配类型
            record_index: 录制音符索引
            replay_index: 播放音符索引
            candidate: 候选对象
            record_note: 录制音符
            replay_note: 播放音符
            reason: 失败原因

        Returns:
            MatchResult: 匹配结果对象
        """
        error_ms = candidate.error_ms if candidate else 0.0
        pair = (record_note, replay_note) if record_note and replay_note else None

        return MatchResult(
            match_type=match_type,
            record_index=record_index,
            replay_index=replay_index,
            error_ms=error_ms,
            pair=pair,
            reason=reason
        )

    
    def get_matched_pairs(self) -> List[Tuple[Note, Note]]:
        """
        获取精确匹配对列表（双方都有hammer）- 仅返回Note对

        Returns:
            List[Tuple[Note, Note]]: 精确匹配对列表
        """
        return [(rec_note, rep_note) for rec_note, rep_note, _, _ in self.matched_pairs]
    
    def get_matched_pairs_with_grade(self) -> List[Tuple[Note, Note, MatchType, float]]:
        """
        获取精确匹配对列表（包含评级信息）

        Returns:
            List[Tuple[Note, Note, MatchType, float]]:
                (record_note, replay_note, match_type, keyon_error_ms)
        """
        return self.matched_pairs.copy()

    def find_matched_pair_by_uuid(self, record_uuid: str, replay_uuid: str) -> Tuple[Note, Note, MatchType, float]:
        """
        通过UUID查找匹配对

        Args:
            record_uuid: 录制音符的UUID
            replay_uuid: 播放音符的UUID

        Returns:
            Tuple[Note, Note, MatchType, float]: 匹配对信息，如果未找到返回None
        """
        for rec_note, rep_note, match_type, error_ms in self.matched_pairs:
            if str(rec_note.uuid) == str(record_uuid) and str(rep_note.uuid) == str(replay_uuid):
                return (rec_note, rep_note, match_type, error_ms)
        return None

    def get_failed_matches_count(self) -> int:
        """获取失败匹配数量"""
        return self.match_statistics.failed_matches

    def get_match_quality_counts(self) -> Dict[str, int]:
        """获取各等级匹配质量统计"""
        return {
            'excellent': self.match_statistics.excellent_matches,
            'good': self.match_statistics.good_matches,
            'fair': self.match_statistics.fair_matches,
            'poor': self.match_statistics.poor_matches,
            'severe': self.match_statistics.severe_matches,
            'failed': self.match_statistics.failed_matches
        }

    def get_error_counts(self) -> Dict[str, int]:
        """获取各种错误类型的统计"""
        return {
            'drop_hammers': len(self.drop_hammers),
            'multi_hammers': len(self.multi_hammers),
            'abnormal_matches': len(self.abnormal_matches)
        }
    
    # ==================== 错误记录方法（原ErrorDetector职责） ====================
    
    def _analyze_unmatched_notes(self, record_data: List[Note], replay_data: List[Note]) -> None:
        """
        分析未匹配的音符，判断是否为丢锤/多锤
        
        使用UUID标识已匹配的音符，只有未匹配且有hammer（>0）的音符才判定为丢锤/多锤
        
        Args:
            record_data: 录制数据
            replay_data: 播放数据
        """
        # 1. 获取已匹配的UUID集合（包括：精确匹配、异常匹配、已判定为丢锤/多锤的音符）
        matched_record_uuids = set()
        matched_replay_uuids = set()
        
        # 从精确匹配对中获取UUID
        for rec_note, rep_note, _, _ in self.matched_pairs:
            matched_record_uuids.add(rec_note.uuid)
            matched_replay_uuids.add(rep_note.uuid)
        
        # 从已记录的异常匹配对、丢锤、多锤中获取UUID
        for rec_note, rep_note in self.abnormal_matches:
            matched_record_uuids.add(rec_note.uuid)
            matched_replay_uuids.add(rep_note.uuid)

        for note in self.drop_hammers:
            matched_record_uuids.add(note.uuid)

        for note in self.multi_hammers:
            matched_replay_uuids.add(note.uuid)
        
        # 2. 分析未匹配的录制音符（丢锤）
        for record_note in record_data:
            if record_note.uuid not in matched_record_uuids:
                hammer_velocity = record_note.get_first_hammer_velocity()
                if hammer_velocity and hammer_velocity > 0:
                    self.drop_hammers.append(record_note)

        # 3. 分析未匹配的播放音符（多锤）
        for replay_note in replay_data:
            if replay_note.uuid not in matched_replay_uuids:
                hammer_velocity = replay_note.get_first_hammer_velocity()
                if hammer_velocity and hammer_velocity > 0:
                    self.multi_hammers.append(replay_note)
                    
    def get_offset_alignment_data(self) -> List[Dict[str, Union[int, float]]]:
        """
        获取所有匹配对的偏移对齐数据 - 包含所有成功匹配
        
        Returns:
            List[Dict[str, Union[int, float]]]: 偏移对齐数据列表
        """
        offset_data = []
        for rec_note, rep_note, match_type, keyon_error_ms in self.matched_pairs:
            record_note = rec_note
            replay_note = rep_note
            
            # 计算录制和播放音符的时间
            record_keyon, record_keyoff = self._calculate_note_times(record_note)
            replay_keyon, replay_keyoff = self._calculate_note_times(replay_note)

            # 获取锤速信息
            record_velocity = self._get_velocity_from_note(record_note)
            replay_velocity = self._get_velocity_from_note(replay_note)

            # 计算原始偏移量
            keyon_offset = replay_keyon - record_keyon
            
            record_duration = record_keyoff - record_keyon
            replay_duration = replay_keyoff - replay_keyon
            duration_diff = replay_duration - record_duration
            
            # 计算相对延时 (需要在外部计算，这里先给原始值)
            # 在DelayAnalysis中会重新计算相对延时，这里只需提供原始数据
            # 为保持格式一致，先给一个占位值
            relative_delay = keyon_offset / 10.0
            
            # 计算持续时间偏移
            duration_offset = replay_duration - record_duration

            offset_data.append({
                'record_index': record_note.offset,  # 这里的index其实是offset
                'replay_index': replay_note.offset,
                'record_uuid': record_note.uuid,      # 增加UUID以供精确查找
                'replay_uuid': replay_note.uuid,
                'record_id': record_note.id,
                'replay_id': replay_note.id,
                'record_keyon': record_keyon,
                'replay_keyon': replay_keyon,
                'record_velocity': record_velocity,
                'replay_velocity': replay_velocity,
                'velocity_diff': (replay_velocity - record_velocity) if record_velocity is not None and replay_velocity is not None else None,
                'keyon_offset': keyon_offset,
                'corrected_offset': keyon_offset,
                'relative_delay': relative_delay,
                'record_keyoff': record_keyoff,
                'replay_keyoff': replay_keyoff,
                'duration_offset': duration_offset,
                'average_offset': abs(keyon_offset),
                'record_duration': record_duration,
                'replay_duration': replay_duration,
                'duration_diff': duration_diff
            })

        return offset_data


    def get_precision_offset_alignment_data(self) -> List[Dict[str, Union[int, float]]]:
        """
        获取精确匹配对的偏移对齐数据 - 包含优秀/良好/一般匹配（误差 ≤ 50ms）

        精确匹配：EXCELLENT (≤20ms) + GOOD (20-30ms) + FAIR (30-50ms)
        用于计算延时误差统计指标，确保只使用相对高质量的匹配数据。

        Returns:
            List[Dict[str, Union[int, float]]]: 精确匹配对的偏移对齐数据列表
        """
        # 从matched_pairs中筛选精确匹配（EXCELLENT, GOOD, FAIR）
        offset_data = []
        for rec_note, rep_note, match_type, keyon_error_ms in self.matched_pairs:
            # 只处理精确匹配（≤50ms）
            if match_type not in [MatchType.EXCELLENT, MatchType.GOOD, MatchType.FAIR]:
                continue
            
            # 计算录制和播放音符的时间
            record_keyon, record_keyoff = self._calculate_note_times(rec_note)
            replay_keyon, replay_keyoff = self._calculate_note_times(rep_note)

            # 获取锤速信息
            record_velocity = self._get_velocity_from_note(rec_note)
            replay_velocity = self._get_velocity_from_note(rep_note)

            # 计算原始偏移量
            keyon_offset = replay_keyon - record_keyon

            record_duration = record_keyoff - record_keyon
            replay_duration = replay_keyoff - replay_keyon
            duration_diff = replay_duration - record_duration
            
            # 计算相对延时（用于悬停显示，单位：ms）
            relative_delay = keyon_offset / 10.0

            offset_data.append({
                'record_index': rec_note.uuid,
                'replay_index': rep_note.uuid,
                'key_id': rec_note.id,
                'record_keyon': record_keyon,
                'replay_keyon': replay_keyon,
                'record_velocity': record_velocity,
                'replay_velocity': replay_velocity,
                'velocity_diff': (replay_velocity - record_velocity) if record_velocity is not None and replay_velocity is not None else None,
                'keyon_offset': keyon_offset,
                'corrected_offset': keyon_offset,
                'relative_delay': relative_delay,
                'record_keyoff': record_keyoff,
                'replay_keyoff': replay_keyoff,
                'duration_offset': duration_diff,
                'average_offset': abs(keyon_offset),
                'record_duration': record_duration,
                'replay_duration': replay_duration,
                'duration_diff': duration_diff
            })

        return offset_data

    def get_grouped_precision_match_data(self) -> Dict[int, List[float]]:
        """
        获取按按键ID分组的精确匹配延时数据（误差 ≤ 50ms）
        直接利用 NoteMatcher 的匹配结果，避免在外部进行二次遍历和分组。

        Returns:
            Dict[int, List[float]]: key_id -> [keyon_offset_ms, ...]
        """
        grouped_data = defaultdict(list)
        for rec_note, rep_note, match_type, _ in self.matched_pairs:
            if match_type in [MatchType.EXCELLENT, MatchType.GOOD, MatchType.FAIR]:
                # 计算延时 (ms)
                offset_ms = (rep_note.key_on_ms - rec_note.key_on_ms)
                grouped_data[rec_note.id].append(offset_ms)
        return grouped_data

    def _get_velocity_from_note(self, note) -> Optional[float]:
        """从音符中获取锤速"""
        try:
            if not note:
                return None

            # 只从hammers数据中获取锤速
            if note.hammers is not None:
                if  len(note.hammers.values) > 0:
                    hammer_velocity = note.hammers.values[0]
                    if hammer_velocity is not None and not pd.isna(hammer_velocity):
                        return float(hammer_velocity)
                elif len(note.hammers) > 0:
                    hammer_velocity = note.hammers.iloc[0]
                    if hammer_velocity is not None and not pd.isna(hammer_velocity):
                        return float(hammer_velocity)

            return None

        except Exception as e:
            logger.warning(f"[WARNING] 从音符提取锤速失败: {e}")
            return None


    def get_graded_error_stats(self) -> Dict[str, Dict[str, Union[int, float]]]:
        """
        获取分级误差统计 - 成功匹配质量评级

        只统计成功匹配对的质量分布（不包括失败匹配）：
        - excellent: 优秀 (误差 ≤ 20ms)
        - good: 良好 (20ms < 误差 ≤ 30ms)
        - fair: 一般 (30ms < 误差 ≤ 50ms)
        - poor: 较差 (50ms < 误差 ≤ 100ms)
        - severe: 严重 (100ms < 误差 ≤ 200ms)

        Returns:
            Dict: 包含各级别的计数和百分比
        """
        # 直接从 match_statistics 获取统计数据 (使用统一 key)
        stats = {
            'excellent': self.match_statistics.excellent_matches,
            'good': self.match_statistics.good_matches,
            'fair': self.match_statistics.fair_matches,
            'poor': self.match_statistics.poor_matches,
            'severe': self.match_statistics.severe_matches,
        }

        # 成功匹配总数（精确匹配对数量）
        total_successful_matches = len(self.matched_pairs)
        
        # 计算百分比（基于成功的匹配对总数）
        result = {}
        for key, count in stats.items():
            result[key] = {
                'count': count,
                'percent': (count / total_successful_matches * 100) if total_successful_matches > 0 else 0.0
            }

        result['total_successful_matches'] = total_successful_matches

        logger.debug(f"📊 [后端] 匹配质量评级统计: 成功配对数={total_successful_matches}")

        return result

    def get_invalid_notes_offset_analysis(self, record_data: List[Note], replay_data: List[Note]) -> List[Dict[str, Union[int, float, str]]]:
        """
        获取无效音符的偏移对齐分析
        
        Args:
            record_data: 录制数据
            replay_data: 播放数据
            
        Returns:
            List[Dict[str, Union[int, float, str]]]: 无效音符偏移分析数据
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
                              other_notes_data: List[Note] = None) -> List[Dict[str, Union[int, float, str]]]:
        """
        分析无效音符的通用方法
        
        Args:
            notes_data: 音符数据列表
            matched_indices: 已匹配的音符索引集合
            data_type: 数据类型 ('record' 或 'replay')
            other_notes_data: 另一个数据类型的音符列表，用于分析匹配失败原因
            
        Returns:
            List[Dict[str, Union[int, float, str]]]: 无效音符分析数据
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
    
    def _get_delay_metrics(self) -> DelayMetrics:
        """
        获取延时指标计算器（延迟初始化）
        
        Returns:
            DelayMetrics: 延时指标计算器实例
        """
        if self._delay_metrics is None:
            # 从matched_pairs中提取精确匹配对（EXCELLENT + GOOD + FAIR）
            # DelayMetrics需要的格式：[(record_idx, replay_idx, record_note, replay_note), ...]
            precision_pairs = []
            for rec_note, rep_note, match_type, _ in self.matched_pairs:
                if match_type in [MatchType.EXCELLENT, MatchType.GOOD, MatchType.FAIR]:
                    # DelayMetrics实际上不使用index，只使用Note对象
                    precision_pairs.append((0, 0, rec_note, rep_note))
            
            self._delay_metrics = DelayMetrics(precision_pairs)
        return self._delay_metrics
    
    def _calculate_note_times(self, note: Note) -> Tuple[float, float]:
        """
        获取音符的按键开始和结束时间
        
        Args:
            note: 音符对象
            
        Returns:
            Tuple[float, float]: (keyon_time, keyoff_time) 单位：0.1ms
        """
        # 直接使用Note对象的预计算属性（已经是ms），转换为0.1ms单位
        if note.key_on_ms is not None and note.key_off_ms is not None:
            keyon_time = note.key_on_ms * 10.0
            keyoff_time = note.key_off_ms * 10.0
        else:
            logger.waring(f"音符ID {note.id} 的时间属性未初始化")
        
        return keyon_time, keyoff_time

    
    def get_standard_deviation(self) -> float:
        """
        计算已配对按键的总体标准差（Population Standard Deviation）
        
        Returns:
            float: 总体标准差（单位：0.1ms）
        """
        return self._get_delay_metrics().get_standard_deviation()
    
    def get_mean_absolute_error(self) -> float:
        """
        计算已配对按键的平均绝对误差（MAE）
        
        Returns:
            float: 平均绝对误差（单位：0.1ms）
        """
        return self._get_delay_metrics().get_mean_absolute_error()
    
    def get_coefficient_of_variation(self) -> float:
        """
        计算已配对按键的变异系数（CV）
        
        Returns:
            float: 变异系数（百分比，例如 15.5 表示 15.5%）
        """
        return self._get_delay_metrics().get_coefficient_of_variation()

    def get_root_mean_squared_error(self) -> float:
        """
        计算已配对按键的均方根误差（RMSE）
        
        Returns:
            float: 均方根误差（单位：0.1ms）
        """
        return self._get_delay_metrics().get_root_mean_squared_error()
    
    def get_mean_error(self) -> float:
        """
        获取已匹配按键对的平均误差（ME，带符号）

        Returns:
            float: 平均误差ME（单位：0.1ms）
        """
        return self._get_delay_metrics().get_mean_error()

    def get_global_average_delay(self) -> float:
        """获取整首曲子的平均时延（兼容性接口）"""
        return self.get_mean_error()

    def get_variance(self) -> float:
        """获取已配对按键的总体方差"""
        return self._get_delay_metrics().get_variance()

    def get_all_display_data(self) -> Dict[str, List[MatchResult]]:
        """
        获取所有用于显示的数据（统一接口，使用 MatchResult 对象）

        提供统一的瀑布图显示数据访问接口，避免表现层处理复杂的元组解包。

        Returns:
            Dict[str, List[MatchResult]]: 包含所有显示相关结果的字典
                - matched_pairs: 正常匹配对
                - drop_hammers: 丢锤错误
                - multi_hammers: 多锤错误
                - abnormal_matches: 异常匹配对（无锤速）
        """
        # 1. 正常匹配对
        normal_matches = [
            MatchResult(match_type=mt, record_index=0, replay_index=0, error_ms=err, pair=(rec, rep))
            for rec, rep, mt, err in self.matched_pairs
        ]

        # 2. 丢锤数据
        drop_hammers = [
            MatchResult(match_type=MatchType.FAILED, record_index=0, pair=(note, None), reason="丢锤 (播放数据缺失)")
            for note in self.drop_hammers
        ]

        # 3. 多锤数据
        multi_hammers = [
            MatchResult(match_type=MatchType.FAILED, record_index=0, pair=(None, note), reason="多锤 (录制数据缺失)")
            for note in self.multi_hammers
        ]

        # 4. 异常匹配对
        abnormal_matches = [
            MatchResult(match_type=MatchType.FAILED, record_index=0, replay_index=0, 
                        error_ms=abs(rep.key_on_ms - rec.key_on_ms), pair=(rec, rep), reason="异常匹配 (均无有效锤速)")
            for rec, rep in self.abnormal_matches
        ]

        return {
            'matched_pairs': normal_matches,
            'drop_hammers': drop_hammers,
            'multi_hammers': multi_hammers,
            'abnormal_matches': abnormal_matches
        }

