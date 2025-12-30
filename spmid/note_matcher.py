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
- 三阶段搜索：精确搜索(≤50ms) → 近似搜索(50ms-1000ms) → 严重搜索(>1000ms)
- 六等级阈值：按误差范围精确分类 (20ms, 30ms, 50ms, 1000ms)

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
   └── 第三阶段：应用扩展阈值过滤 (≤300ms)

【匹配分类 - 六等级系统】
- 优秀匹配 (≤20ms)：高质量匹配
- 良好匹配 (20-30ms)：较高质量匹配
- 一般匹配 (30-50ms)：可接受匹配
- 较差匹配 (50-1000ms)：需要改进的匹配
- 严重匹配 (>1000ms)：质量极差但找到的匹配
- 失败匹配 (无候选)：完全找不到匹配，标记为丢锤/多锤异常

【搜索策略 - 三阶段分层搜索】
- 第一阶段：精确搜索 (≤50ms) - 寻找优秀/良好/一般匹配
- 第二阶段：近似搜索 (50-1000ms) - 寻找较差匹配
- 第三阶段：严重搜索 (>1000ms) - 寻找严重误差匹配

【阈值体系 - 六等级精确分类】
- 优秀阈值：≤20ms
- 良好阈值：20-30ms
- 一般阈值：30-50ms
- 较差阈值：50-1000ms
- 严重阈值：>1000ms
- 失败阈值：无匹配

【错误检测】
- 丢锤：录制数据中未匹配的按键
- 多锤：播放数据中未匹配的按键
- 基于两阶段匹配后的剩余音符直接判断，无需复杂统计
"""

import pandas as pd
import numpy as np
from .spmid_reader import Note
from typing import List, Tuple, Dict, Union, Optional
from utils.logger import Logger
from enum import Enum
from collections import defaultdict

logger = Logger.get_logger()

# 匹配阈值常量 (0.1ms单位) - 五等级匹配系统
# 优秀匹配：≤20ms
EXCELLENT_THRESHOLD = 200.0
# 良好匹配：20-30ms
GOOD_THRESHOLD = 300.0
# 一般匹配：30-50ms
FAIR_THRESHOLD = 500.0
# 较差匹配：50-1000ms
POOR_THRESHOLD = 10000.0
# 严重误差：>1000ms
SEVERE_THRESHOLD = 10000.0
# 失败匹配：无候选

# 兼容性常量 (向后兼容)
PRECISION_THRESHOLD = FAIR_THRESHOLD      # 50ms - 精确匹配上限
APPROXIMATE_THRESHOLD = POOR_THRESHOLD    # 1000ms - 近似匹配上限

# 匹配类型枚举 - 按误差等级细分
class MatchType(Enum):
    """匹配结果类型 - 按误差等级分类"""
    EXCELLENT = "excellent"      # 优秀匹配 (误差 ≤ 20ms)
    GOOD = "good"               # 良好匹配 (20ms < 误差 ≤ 30ms)
    FAIR = "fair"               # 一般匹配 (30ms < 误差 ≤ 50ms)
    POOR = "poor"               # 较差匹配 (50ms < 误差 ≤ 1000ms)
    SEVERE = "severe"           # 严重误差 (误差 > 1000ms)
    FAILED = "failed"           # 失败匹配 (无候选)

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
    def __init__(self, index: int, total_error: float, note: Optional[Note] = None):
        self.index = index
        self.total_error = total_error
        self.note = note

    @property
    def error_ms(self) -> float:
        """误差转换为毫秒"""
        return self.total_error / 10.0

# 按键匹配统计类 - 新增：按键级别的统计信息
class KeyMatchStatistics:
    """单个按键的匹配统计信息"""

    def __init__(self, key_id: int):
        self.key_id = key_id
        self.total_record_notes = 0    # 该按键录制音符总数
        self.total_replay_notes = 0    # 该按键播放音符总数
        self.matched_count = 0         # 成功匹配数
        self.failed_count = 0          # 失败匹配数
        self.extra_hammers = 0         # 多锤数（未使用的播放音符）

        # 误差统计（只统计成功匹配）
        self.offsets_ms: List[float] = []  # 校准后偏移（ms）
        self.median_offset = 0.0
        self.mean_offset = 0.0
        self.std_offset = 0.0
        self.variance_offset = 0.0

        # 匹配质量分布
        self.excellent_count = 0
        self.good_count = 0
        self.fair_count = 0
        self.poor_count = 0
        self.severe_count = 0

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
            import statistics
            self.median_offset = statistics.median(self.offsets_ms)
            self.mean_offset = statistics.mean(self.offsets_ms)

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
        # 六等级匹配统计
        self.excellent_matches = 0    # 优秀匹配 (≤20ms)
        self.good_matches = 0         # 良好匹配 (20-30ms)
        self.fair_matches = 0         # 一般匹配 (30-50ms)
        self.poor_matches = 0         # 较差匹配 (50-1000ms)
        self.severe_matches = 0       # 严重误差 (>1000ms)
        self.failed_matches = 0       # 失败匹配 (无候选)

        # 兼容性字段 - 保持向后兼容
        self.precision_matches = 0    # 精确匹配总数 (≤50ms)
        self.approximate_matches = 0  # 近似匹配总数 (50-1000ms)
        self.large_error_matches = 0  # 大误差匹配总数 (>1000ms)

        self.total_attempts = 0       # 总尝试数

    def add_result(self, result: MatchResult):
        """添加匹配结果到统计"""
        self.total_attempts += 1

        if result.match_type == MatchType.EXCELLENT:
            self.excellent_matches += 1
            self.precision_matches += 1
        elif result.match_type == MatchType.GOOD:
            self.good_matches += 1
            self.precision_matches += 1
        elif result.match_type == MatchType.FAIR:
            self.fair_matches += 1
            self.precision_matches += 1
        elif result.match_type == MatchType.POOR:
            self.poor_matches += 1
            self.approximate_matches += 1
        elif result.match_type == MatchType.SEVERE:
            self.severe_matches += 1
            self.large_error_matches += 1
        elif result.match_type == MatchType.FAILED:
            self.failed_matches += 1

    def __str__(self):
        return f"优秀:{self.excellent_matches}, 良好:{self.good_matches}, 一般:{self.fair_matches}, 较差:{self.poor_matches}, 严重:{self.severe_matches}, 失败:{self.failed_matches}"

class NoteMatcher:
    """SPMID音符匹配器类"""
    
    def __init__(self, global_time_offset: float = 0.0):
        """
        初始化音符匹配器 - 五等级匹配系统

        Args:
            global_time_offset: 初始全局时间偏移量（可选，会在匹配过程中重新计算）
        """
        self.global_time_offset = global_time_offset

        # 核心匹配结果存储
        self.matched_pairs: List[Tuple[int, int, Note, Note]] = []  # 所有成功匹配对 (record_idx, replay_idx, record_note, replay_note)
        self.match_results: List[MatchResult] = []  # 所有匹配结果详情 (包含匹配类型、误差等)

        # 匹配失败信息
        self.failure_reasons: Dict[Tuple[str, int], str] = {}  # key=(data_type, index)，value=str

        # 分类存储 - 按搜索阶段分组（用于数据获取优化）
        self.precision_matched_pairs: List[Tuple[int, int, Note, Note]] = []  # 精确搜索阶段匹配 (≤50ms)
        self.approximate_matched_pairs: List[Tuple[int, int, Note, Note]] = []  # 近似搜索阶段匹配 (50-1000ms)
        self.severe_matched_pairs: List[Tuple[int, int, Note, Note]] = []  # 严重误差搜索阶段匹配 (>1000ms)

        # 按键分组统计信息 - 新增：预计算的按键级别统计数据
        self.key_statistics: Dict[int, KeyMatchStatistics] = {}  # key=key_id, value=该按键的统计信息

        # 统计信息
        self.match_statistics = MatchStatistics()

        # 数据引用缓存
        self._record_data: Optional[List[Note]] = None
        self._replay_data: Optional[List[Note]] = None

        # 计算缓存
        self._mean_error_cached: Optional[float] = None
    
    def find_all_matched_pairs(self, record_data: List[Note], replay_data: List[Note]) -> List[Tuple[int, int, Note, Note]]:
        """
        查找所有匹配对：按键分组贪心匹配

        匹配逻辑：
        1. 按按键ID分组录制和播放数据
        2. 对每个按键分别进行贪心匹配（同按键ID的录制音符 vs 同按键ID的播放音符）
        3. 按键之间完全独立，不允许跨按键配对

        Args:
            record_data: 录制数据
            replay_data: 播放数据

        Returns:
            List[Tuple[int, int, Note, Note]]: 匹配对列表 (record_index, replay_index, record_note, replay_note)
        """
        # 初始化状态
        self._initialize_matching_state()

        logger.info(f"🎯 开始按键分组贪心匹配: 录制数据{len(record_data)}个音符, 回放数据{len(replay_data)}个音符")

        # 保存原始数据引用（用于失败匹配详情）
        self._record_data = record_data
        self._replay_data = replay_data

        # 1. 按按键ID分组数据
        record_by_key = self._group_notes_by_key(record_data)
        replay_by_key = self._group_notes_by_key(replay_data)

        logger.info(f"📊 按键分组完成: 录制数据{len(record_by_key)}个按键, 播放数据{len(replay_by_key)}个按键")

        # 2. 对每个按键分别进行贪心匹配
        all_matched_pairs = []

        for key_id in record_by_key.keys():
            logger.debug(f"🎹 开始匹配按键{key_id}")

            # 获取该按键的所有录制和播放音符
            key_record_notes = record_by_key[key_id]  # [(original_index, note), ...]
            key_replay_notes = replay_by_key.get(key_id, [])  # [(original_index, note), ...]

            # 对该按键进行贪心匹配
            key_matched_pairs, extra_hammers = self._match_notes_for_single_key_group(
                key_id, key_record_notes, key_replay_notes
            )

            all_matched_pairs.extend(key_matched_pairs)

            # 更新按键统计信息中的多锤数量
            if key_id not in self.key_statistics:
                self.key_statistics[key_id] = KeyMatchStatistics(key_id)
                self.key_statistics[key_id].total_record_notes = len(key_record_notes)
                self.key_statistics[key_id].total_replay_notes = len(key_replay_notes)
            self.key_statistics[key_id].extra_hammers = extra_hammers

            matched_count = len(key_matched_pairs)
            record_count = len(key_record_notes)
            replay_count = len(key_replay_notes)

            logger.debug(f"🏁 按键{key_id}匹配完成: 录制{record_count}个, 播放{replay_count}个, 匹配{matched_count}个")

        # 保存所有匹配对
        self.matched_pairs = all_matched_pairs

        # 3. 基于匹配结果计算按键统计信息
        self._calculate_key_statistics_from_matches(record_by_key, replay_by_key)

        # 记录按键级别的匹配统计
        self._log_key_matching_statistics()

        # 匹配完成后计算并缓存平均误差
        self._mean_error_cached = self._calculate_mean_error()

        # 打印匹配统计信息
        print(f"[匹配统计] 精确匹配: {self.match_statistics.precision_matches} 个")
        print(f"[匹配统计] 近似匹配: {self.match_statistics.approximate_matches} 个")
        print(f"[匹配统计] 大误差匹配: {self.match_statistics.large_error_matches} 个")
        print(f"[匹配统计] 失败匹配: {self.match_statistics.failed_matches} 个")
        print(f"[匹配统计] 总匹配对: {len(all_matched_pairs)} 个 (准确率分子)")

        return all_matched_pairs

    def _match_notes_for_single_key_group(self, key_id: int,
                                        record_notes_with_indices: List[Tuple[int, Note]],
                                        replay_notes_with_indices: List[Tuple[int, Note]]) -> Tuple[List[Tuple[int, int, Note, Note]], int]:
        """
        对单个按键组进行贪心匹配

        匹配策略：
        1. 精确匹配 (≤50ms)
        2. 近似匹配 (50ms-1000ms)
        3. 严重误差匹配 (>1000ms) - 理论上应该匹配所有剩余按键

        匹配完成后统一分析：
        - 录制中未匹配的：丢锤
        - 播放中未使用的：多锤

        Args:
            key_id: 按键ID
            record_notes_with_indices: 该按键的录制音符列表 [(original_index, note), ...]
            replay_notes_with_indices: 该按键的播放音符列表 [(original_index, note), ...]

        Returns:
            List[Tuple[int, int, Note, Note]]: 该按键的匹配对列表
        """
        key_matched_pairs = []

        # 初始化状态跟踪 - 使用原始索引作为键，确保唯一性
        record_match_status = {record_idx: False for record_idx, _ in record_notes_with_indices}  # False=未匹配
        replay_match_status = {replay_idx: False for replay_idx, _ in replay_notes_with_indices}  # False=未使用

        logger.debug(f"🎹 开始按键{key_id}贪心匹配: 录制{len(record_notes_with_indices)}个, 播放{len(replay_notes_with_indices)}个")

        # 分等级贪心匹配策略
        match_strategies = [
            ("precision", "精确匹配", [MatchType.EXCELLENT, MatchType.GOOD, MatchType.FAIR]),
            ("approximate", "近似匹配", [MatchType.POOR]),
            ("severe", "严重误差匹配", [MatchType.SEVERE])
        ]

        # 获取待匹配的录制音符列表（未匹配的）
        unmatched_record_notes = [(idx, note) for idx, note in record_notes_with_indices]

        # 按等级顺序进行匹配
        for strategy_name, strategy_desc, allowed_types in match_strategies:
            if not unmatched_record_notes:
                logger.debug(f"🎯 按键{key_id}所有录制音符已匹配完成")
                break

            logger.debug(f"🎪 按键{key_id}开始{strategy_desc}轮: 剩余录制{len(unmatched_record_notes)}个")

            # 本轮成功匹配的录制音符（从列表中移除）
            matched_in_this_round = []

            # 遍历所有未匹配的录制音符，让它们都尝试当前等级的匹配
            for record_orig_idx, record_note in unmatched_record_notes:
                # 获取当前可用的播放音符及其原始索引（未被使用的）
                available_replay_notes_with_indices = []
                for replay_orig_idx, replay_note in replay_notes_with_indices:
                    if not replay_match_status[replay_orig_idx]:  # 未被使用
                        available_replay_notes_with_indices.append((replay_orig_idx, replay_note))

                # 在该按键的可用播放音符中进行指定等级的匹配
                match_result = self._perform_single_note_matching_in_strategy(
                    record_note, record_orig_idx, available_replay_notes_with_indices,
                    strategy_name, len(replay_notes_with_indices) > 0
                )

                # 更新全局统计信息
                self.match_statistics.add_result(match_result)
                self.match_results.append(match_result)

                # 处理匹配结果
                if match_result.is_success and match_result.match_type in allowed_types:
                    # 从MatchResult中直接获取播放音符索引
                    matched_replay_orig_idx = match_result.replay_index
                    matched_replay_note = match_result.pair[1]

                    key_matched_pairs.append((
                        record_orig_idx,
                        matched_replay_orig_idx,
                        record_note,
                        matched_replay_note
                    ))

                    # 更新匹配状态
                    record_match_status[record_orig_idx] = True
                    replay_match_status[matched_replay_orig_idx] = True

                    # 记录按键配对详情日志
                    logger.debug(f"🔗 按键配对: 录制按键{key_id}(索引{record_orig_idx}) ↔ 播放按键{key_id}(索引{matched_replay_orig_idx}), "
                               f"误差={match_result.error_ms:.2f}ms, 类型={match_result.match_type.value}")

                    # 记录到对应的分类列表
                    if match_result.match_type in [MatchType.EXCELLENT, MatchType.GOOD, MatchType.FAIR]:
                        self.precision_matched_pairs.append(key_matched_pairs[-1])
                    elif match_result.match_type == MatchType.POOR:
                        self.approximate_matched_pairs.append(key_matched_pairs[-1])
                    elif match_result.match_type == MatchType.SEVERE:
                        self.severe_matched_pairs.append(key_matched_pairs[-1])

                    # 标记本轮成功匹配
                    matched_in_this_round.append((record_orig_idx, record_note))
                # else: 匹配失败，继续留在未匹配列表中，等待下一轮

            # 从未匹配列表中移除本轮成功匹配的音符
            for matched_record in matched_in_this_round:
                unmatched_record_notes.remove(matched_record)

            logger.debug(f"🏁 按键{key_id}{strategy_desc}轮完成: 本轮匹配{matched_in_this_round.__len__()}个, 剩余{len(unmatched_record_notes)}个")

        # 第二阶段：统一分析丢锤和多锤
        extra_hammers = self._analyze_key_group_hammer_status(key_id, record_match_status, replay_match_status)

        return key_matched_pairs, extra_hammers

    def _analyze_key_group_hammer_status(self, key_id: int,
                                        record_match_status: Dict[int, bool],
                                        replay_match_status: Dict[int, bool]) -> int:
        """
        分析按键组的锤子状态（丢锤和多锤）

        Args:
            key_id: 按键ID
            record_match_status: 录制音符匹配状态 {record_orig_idx: is_matched}
            replay_match_status: 播放音符使用状态 {replay_orig_idx: is_used}

        Returns:
            int: 多锤数量
        """
        # 分析丢锤：录制了但未匹配
        dropped_hammers = [idx for idx, matched in record_match_status.items() if not matched]

        # 分析多锤：播放了但未被使用
        extra_hammers = [idx for idx, matched in replay_match_status.items() if not matched]

        # 记录分析结果
        logger.debug(f"🎯 按键{key_id}匹配完成:")
        logger.debug(f"  📝 录制: {len(record_match_status)}个, 匹配: {sum(record_match_status.values())}个")
        logger.debug(f"  🎵 播放: {len(replay_match_status)}个, 使用: {sum(replay_match_status.values())}个")
        logger.debug(f"  🔨 丢锤: {len(dropped_hammers)}个, 多锤: {len(extra_hammers)}个")

        # 为丢锤创建失败记录
        for record_idx in dropped_hammers:
            match_result = MatchResult(
                MatchType.FAILED,
                record_idx,
                reason=f"按键{key_id}录制音符未匹配(丢锤)"
            )
            self.match_results.append(match_result)
            self.match_statistics.add_result(match_result)

        # 返回多锤数量，用于更新按键统计
        return len(extra_hammers)

    def _perform_single_note_matching_in_strategy(self, record_note: Note, record_index: int,
                                                     replay_notes_with_indices: List[Tuple[int, Note]],
                                                     strategy_name: str,
                                                     has_any_replay_notes: bool = True) -> MatchResult:
        """
        在按键组内部进行单个音符的指定策略匹配

        Args:
            record_note: 录制音符
            record_index: 录制音符的原始索引
            replay_notes_with_indices: 该按键的播放音符列表（已过滤未使用的）[(orig_idx, note), ...]
            strategy_name: 匹配策略名称 ("precision", "approximate", "severe")
            has_any_replay_notes: 是否有播放音符

        Returns:
            MatchResult: 匹配结果
        """
        note_info = self._extract_note_info(record_note, record_index)

        # 只在指定的策略中进行匹配
        replay_notes_only = [note for _, note in replay_notes_with_indices]
        candidates, reason = self._find_candidates_in_key_group(
            replay_notes_only, note_info["keyon"], note_info["keyoff"],
            note_info["key_id"], search_mode=strategy_name
        )

        if candidates:
            # 从候选列表中选择最佳的（第一个，因为已经按误差排序）
            chosen = candidates[0]  # 贪心选择：选择误差最小的一个

            # 构建匹配对
            replay_note = chosen.note
            pair = (record_note, replay_note)

            # 根据实际误差确定匹配类型
            actual_match_type = self._evaluate_match_quality(chosen.error_ms)

            # 从过滤列表中找到对应的原始索引
            replay_orig_idx = replay_notes_with_indices[chosen.index][0]

            return self._create_match_result(
                actual_match_type, record_index, replay_orig_idx, chosen,
                record_note, replay_note
            )

        # 当前策略匹配失败
        return self._create_match_result(
            MatchType.FAILED, record_index, reason=f"{strategy_name}策略无符合候选"
        )

    def _perform_single_note_matching_within_key_group(self, record_note: Note, record_index: int,
                                                     replay_notes_with_indices: List[Tuple[int, Note]],
                                                     has_any_replay_notes: bool = True) -> MatchResult:
        """
        在按键组内部进行单个音符匹配

        Args:
            record_note: 录制音符
            record_index: 录制音符的原始索引
            replay_notes_with_indices: 该按键的播放音符列表（已过滤未使用的）[(orig_idx, note), ...]

        Returns:
            MatchResult: 匹配结果
        """
        note_info = self._extract_note_info(record_note, record_index)

        # 定义匹配策略：分层搜索，确保找到最佳匹配
        match_strategies = [
            ("precision", self.precision_matched_pairs),     # 第一优先级: 精确搜索 (≤50ms)
            ("approximate", self.approximate_matched_pairs), # 第二优先级: 扩展搜索 (50ms-1000ms)
            ("severe", self.severe_matched_pairs),          # 第三优先级: 严重误差搜索 (>1000ms)
        ]

        # 按顺序尝试每种匹配策略
        for search_mode, record_list in match_strategies:
            # 只传入音符列表给 _find_candidates_in_key_group
            replay_notes_only = [note for _, note in replay_notes_with_indices]
            candidates, reason = self._find_candidates_in_key_group(
                replay_notes_only, note_info["keyon"], note_info["keyoff"],
                note_info["key_id"], search_mode=search_mode
            )

            if candidates:
                # 从候选列表中选择最佳的（第一个，因为已经按误差排序）
                chosen = candidates[0]  # 贪心选择：选择误差最小的一个

                # 构建匹配对
                replay_note = chosen.note
                pair = (record_note, replay_note)

                # 根据实际误差确定匹配类型
                actual_match_type = self._evaluate_match_quality(chosen.error_ms)

                # 从过滤列表中找到对应的原始索引
                replay_orig_idx = replay_notes_with_indices[chosen.index][0]

                return self._create_match_result(
                    actual_match_type, record_index, replay_orig_idx, chosen,
                    record_note, replay_note
                )

        # 所有搜索都失败 - 由上级统一分析丢锤多锤
        return self._create_match_result(
            MatchType.FAILED, record_index, reason="无符合误差范围的候选"
        )

    def _find_candidates_in_key_group(self, replay_notes: List[Note], target_keyon: float, target_keyoff: float,
                                    target_key_id: int, search_mode: str = "precision") -> Tuple[List[Candidate], str]:
        """
        在按键组内部寻找候选匹配

        Args:
            replay_notes: 该按键的播放音符列表
            target_keyon: 目标按键开始时间
            target_keyoff: 目标按键结束时间
            target_key_id: 目标按键ID
            search_mode: 搜索模式

        Returns:
            Tuple[List[Candidate], str]: (候选列表, 失败原因)
        """
        candidates = []

        for idx, replay_note in enumerate(replay_notes):
            # 验证按键ID匹配（虽然理论上应该都匹配）
            if getattr(replay_note, 'id', None) != target_key_id:
                continue

            # 计算时间误差（只使用keyon_offset）
            replay_keyon, _ = self._calculate_note_times(replay_note)
            keyon_offset = replay_keyon - target_keyon
            total_error = abs(keyon_offset)

            candidates.append(Candidate(idx, total_error, replay_note))

        # 按误差升序排序
        candidates.sort(key=lambda x: x.total_error)

        # 根据搜索模式应用阈值过滤
        if search_mode == "precision":
            filtered = [c for c in candidates if c.total_error <= FAIR_THRESHOLD]
            if not filtered:
                best_error = min(c.error_ms for c in candidates) if candidates else 0
                return [], f"无精确候选(最佳误差:{best_error:.1f}ms, 阈值:{FAIR_THRESHOLD/10:.1f}ms)"
        elif search_mode == "approximate":
            filtered = [c for c in candidates if FAIR_THRESHOLD < c.total_error <= POOR_THRESHOLD]
            if not filtered:
                return [], f"无近似候选(阈值:{FAIR_THRESHOLD/10:.1f}-{POOR_THRESHOLD/10:.1f}ms)"
        elif search_mode == "severe":
            filtered = [c for c in candidates if c.total_error > POOR_THRESHOLD]
            if not filtered:
                return [], f"无严重误差候选(阈值:>{POOR_THRESHOLD/10:.1f}ms)"
        else:
            filtered = candidates

        return filtered, ""

    def _group_notes_by_key(self, notes: List[Note]) -> Dict[int, List[Tuple[int, Note]]]:
        """
        按按键ID分组音符数据

        Args:
            notes: 音符列表

        Returns:
            Dict[int, List[Tuple[int, Note]]]: key=按键ID, value=(原始索引, 音符)列表
        """
        grouped = defaultdict(list)
        for i, note in enumerate(notes):
            grouped[note.id].append((i, note))
        return dict(grouped)

    def _calculate_global_statistics(self):
        """计算全局统计信息（兼容性方法）"""
        # 这个方法主要用于保持向后兼容性
        # 实际的统计信息已经在_match_notes_for_single_key中计算了
        pass

    def _calculate_key_statistics_from_matches(self, record_by_key: Dict[int, List[Tuple[int, Note]]],
                                             replay_by_key: Dict[int, List[Tuple[int, Note]]]):
        """基于匹配结果计算按键统计信息"""
        logger.info("📊 开始计算按键统计信息...")

        # 初始化所有按键的统计信息
        for key_id in set(record_by_key.keys()) | set(replay_by_key.keys()):
            key_stats = KeyMatchStatistics(key_id)
            key_stats.total_record_notes = len(record_by_key.get(key_id, []))
            key_stats.total_replay_notes = len(replay_by_key.get(key_id, []))
            self.key_statistics[key_id] = key_stats

        # 基于匹配结果更新统计信息
        for match_result in self.match_results:
            # 获取录制音符的按键ID
            record_note = self._record_data[match_result.record_index]
            key_id = record_note.id

            if key_id not in self.key_statistics:
                continue

            key_stats = self.key_statistics[key_id]

            if match_result.is_success:
                # 计算校准后偏移
                record_keyon, _ = self._calculate_note_times(record_note)
                replay_keyon, _ = self._calculate_note_times(match_result.pair[1])
                raw_offset = replay_keyon - record_keyon
                corrected_offset = raw_offset - self.global_time_offset
                corrected_offset_ms = corrected_offset / 10.0

                # 只统计误差≤50ms的匹配对用于条形图
                if abs(corrected_offset_ms) <= 50.0:
                    key_stats.add_match_result(match_result, corrected_offset_ms)
            else:
                # 记录失败匹配
                key_stats.failed_count += 1

        # 计算每个按键的统计值
        for key_stats in self.key_statistics.values():
            if key_stats.matched_count > 0:
                key_stats.calculate_statistics()

    def _log_key_matching_statistics(self):
        """记录按键级别的匹配统计日志"""
        logger.info("📊 按键匹配统计汇总:")

        # 按按键ID排序输出
        for key_id in sorted(self.key_statistics.keys()):
            key_stats = self.key_statistics[key_id]
            match_rate = (key_stats.matched_count / key_stats.total_record_notes * 100) if key_stats.total_record_notes > 0 else 0

            if key_stats.matched_count > 0:
                logger.info(f"🎹 按键{key_id}: 录制{key_stats.total_record_notes} → 匹配{key_stats.matched_count} → "
                           f"失败{key_stats.failed_count} (匹配率: {match_rate:.1f}%, "
                           f"均值: {key_stats.mean_offset:.2f}ms, 标准差: {key_stats.std_offset:.2f}ms)")
            else:
                logger.info(f"🎹 按键{key_id}: 录制{key_stats.total_record_notes} → 匹配{key_stats.matched_count} → "
                           f"失败{key_stats.failed_count} (匹配率: {match_rate:.1f}%)")

        # 总体统计
        total_keys = len(self.key_statistics)
        keys_with_matches = sum(1 for stats in self.key_statistics.values() if stats.matched_count > 0)
        total_record_notes = sum(stats.total_record_notes for stats in self.key_statistics.values())
        total_matched = sum(stats.matched_count for stats in self.key_statistics.values())
        total_failed = sum(stats.failed_count for stats in self.key_statistics.values())

        overall_match_rate = (total_matched / total_record_notes * 100) if total_record_notes > 0 else 0

        logger.info(f"📈 总体统计: {total_keys}个按键, {keys_with_matches}个按键有匹配, "
                   f"总录制音符: {total_record_notes}, 成功匹配: {total_matched}, 失败: {total_failed}, "
                   f"整体匹配率: {overall_match_rate:.1f}%")


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
                    'median': key_stats.median_offset,
                    'mean': key_stats.mean_offset,
                    'std': key_stats.std_offset,
                    'variance': key_stats.variance_offset,
                    'count': key_stats.matched_count,
                    'status': 'matched'
                })

        # 按按键ID排序
        result.sort(key=lambda x: x['key_id'])

        logger.debug(f"📊 条形统计图数据: {len(result)}个按键有统计信息")
        return result

    def _find_candidates(self, notes_list: List[Note], target_keyon: float, target_keyoff: float,
                        target_key_id: int, time_offset: float = 0.0, search_mode: str = "precision") -> Tuple[List[Candidate], str]:
        """
        生成候选列表，支持不同的搜索模式。

        参数单位：
            - target_keyon/target_keyoff：0.1ms（绝对时间 = after_touch.index + offset）
            - 误差：0.1ms（内部统一单位）

        Args:
            notes_list: 音符列表
            target_keyon: 目标按键开始时间
            target_keyoff: 目标按键结束时间
            target_key_id: 目标按键ID
            time_offset: 时间偏移
            search_mode: 搜索模式 ("precision" 或 "approximate")

        Returns:
            (candidates, reason_if_empty)
        """
        # 1) 过滤同键ID的音符
        matching_notes = []
        for idx, note in enumerate(notes_list):
            if getattr(note, 'id', None) == target_key_id:
                matching_notes.append((idx, note))

        if not matching_notes:
            return [], f"没有找到键ID {target_key_id} 的音符"

        # 2) 构建候选并计算误差
        candidates: List[Candidate] = []
        for idx, note in matching_notes:
            # 计算按键开始时间（应用时间偏移）
            try:
                current_keyon = note.after_touch.index[0] + note.offset + time_offset
            except (IndexError, AttributeError) as e:
                raise ValueError(f"音符ID {note.id} 的after_touch数据无效: {e}") from e

            # 只使用keyon_offset计算误差
            keyon_offset = current_keyon - target_keyon
            total_error = abs(keyon_offset)

            candidates.append(Candidate(idx, total_error))

        # 3) 根据搜索模式应用阈值过滤 - 分层搜索策略
        if search_mode == "precision":
            # 精确搜索：优先寻找高质量匹配 (≤ FAIR_THRESHOLD = 50ms)
            # 这个阈值与评级中的fair阈值一致，确保不会影响评级分布
            filtered = [c for c in candidates if c.total_error <= FAIR_THRESHOLD]
            if not filtered:
                # 没有精确候选，返回空列表和原因
                best_error = min(c.error_ms for c in candidates) if candidates else 0
                return [], f"无精确候选(最佳误差:{best_error:.1f}ms, 阈值:{FAIR_THRESHOLD/10:.1f}ms)"
        elif search_mode == "approximate":
            # 近似搜索：当精确搜索失败时，寻找可接受的匹配 (50ms-1000ms)
            # 避免与precision模式重叠，确保评级逻辑不受影响
            filtered = [c for c in candidates if FAIR_THRESHOLD < c.total_error <= POOR_THRESHOLD]
            if not filtered:
                return [], f"无近似候选(阈值:{FAIR_THRESHOLD/10:.1f}-{POOR_THRESHOLD/10:.1f}ms)"
        elif search_mode == "severe":
            # 严重误差搜索：只接受误差很大的匹配 (>1000ms)
            # 这些匹配会被评为SEVERE类型
            filtered = [c for c in candidates if c.total_error > POOR_THRESHOLD]
            if not filtered:
                return [], f"无严重误差候选(阈值:>{POOR_THRESHOLD/10:.1f}ms)"
        else:
            filtered = candidates

        # 按误差升序排序
        filtered.sort(key=lambda x: x.total_error)
        return filtered, ""

    def _evaluate_match_quality(self, error_ms: float) -> MatchType:
        """
        根据误差评估匹配质量 - 六等级标准

        Args:
            error_ms: 误差(毫秒)

        Returns:
            MatchType: 匹配类型
        """
        error_units = error_ms * 10.0  # 转换为内部单位

        if error_units <= EXCELLENT_THRESHOLD:
            return MatchType.EXCELLENT
        elif error_units <= GOOD_THRESHOLD:
            return MatchType.GOOD
        elif error_units <= FAIR_THRESHOLD:
            return MatchType.FAIR
        elif error_units <= POOR_THRESHOLD:
            return MatchType.POOR
        else:
            return MatchType.SEVERE

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

    def _calculate_global_time_offset(self, record_data: List[Note], replay_data: List[Note]) -> float:
        """
        计算全局时间偏移量（系统固定延时）

        目前：暂时禁用DTW算法，直接返回0
        之前的策略（已注释）：
        1. 提取录制和播放的按键时间序列
        2. 使用DTW算法计算序列间的对应关系
        3. 从DTW路径中推导出全局时间偏移

        DTW优点：可以处理复杂的时序对齐，不仅仅是固定偏移
        虽然DTW会产生一对多的情况，但这里只是估算全局偏移，后续匹配会重新处理

        Returns:
            float: 全局时间偏移量（0.1ms单位），目前固定返回0
        """

        # 暂时禁用DTW算法，直接返回0
        logger.info("ℹ️ 全局时间偏移计算已禁用，返回0（DTW算法已注释）")
        return 0.0

        # ==================== DTW算法代码已注释 ====================
        #
        # # 1. 提取时间序列（按键开始时间）
        # record_times = []
        # replay_times = []
        #
        # # 按时间排序录制音符
        # sorted_record = sorted(record_data, key=lambda n: n.after_touch.index[0] + n.offset)
        # for note in sorted_record:
        #     start_time, _ = self._calculate_note_times(note)
        #     record_times.append(start_time)
        #
        # # 按时间排序播放音符
        # sorted_replay = sorted(replay_data, key=lambda n: n.after_touch.index[0] + n.offset)
        # for note in sorted_replay:
        #     start_time, _ = self._calculate_note_times(note)
        #     replay_times.append(start_time)
        #
        #
        # # 2. 计算DTW距离矩阵
        # record_array = np.array(record_times)
        # replay_array = np.array(replay_times)
        #
        # # 归一化时间序列（减去各自的起始时间）
        # record_norm = record_array - record_array[0]
        # replay_norm = replay_array - replay_array[0]
        #
        # # 计算距离矩阵
        # distances = np.abs(record_norm[:, np.newaxis] - replay_norm[np.newaxis, :])
        #
        # # 3. DTW动态规划
        # n, m = len(record_norm), len(replay_norm)
        # dtw_matrix = np.full((n, m), np.inf)
        # dtw_matrix[0, 0] = distances[0, 0]
        #
        # # 填充第一行和第一列
        # for i in range(1, n):
        #     dtw_matrix[i, 0] = dtw_matrix[i-1, 0] + distances[i, 0]
        # for j in range(1, m):
        #     dtw_matrix[0, j] = dtw_matrix[0, j-1] + distances[0, j]
        #
        # # 填充其余部分
        # for i in range(1, n):
        #     for j in range(1, m):
        #         cost = distances[i, j]
        #         dtw_matrix[i, j] = cost + min(
        #             dtw_matrix[i-1, j],    # 上方
        #             dtw_matrix[i, j-1],    # 左方
        #             dtw_matrix[i-1, j-1]   # 对角线
        #         )
        #
        # # 4. 回溯找到最优路径
        # path = []
        # i, j = n-1, m-1
        # path.append((i, j))
        #
        # while i > 0 or j > 0:
        #     if i == 0:
        #         j -= 1
        #     elif j == 0:
        #         i -= 1
        #     else:
        #         min_prev = min(
        #             dtw_matrix[i-1, j],    # 上方
        #             dtw_matrix[i, j-1],    # 左方
        #             dtw_matrix[i-1, j-1]   # 对角线
        #         )
        #         if dtw_matrix[i-1, j-1] == min_prev:
        #             i, j = i-1, j-1
        #         elif dtw_matrix[i-1, j] == min_prev:
        #             i -= 1
        #         else:
        #             j -= 1
        #     path.append((i, j))
        #
        # path.reverse()
        #
        # # 5. 从DTW路径计算时间偏移
        # time_diffs = []
        # for rec_idx, rep_idx in path:
        #     if rec_idx < len(record_times) and rep_idx < len(replay_times):
        #         diff = replay_times[rep_idx] - record_times[rec_idx]
        #         time_diffs.append(diff)
        #
        # if not time_diffs:
        #     logger.warning("⚠️ DTW路径为空，回退到简单方法")
        #     return self._calculate_global_time_offset_simple(record_data, replay_data)
        #
        # # 6. 检查路径质量
        # # 6.2 检查时间差方差是否太大（方差过大表示对齐质量差）
        # # 将时间差转换为ms单位进行方差计算
        # # time_diffs_ms = np.array(time_diffs) / 10.0
        # # variance_ms = float(np.var(time_diffs_ms))
        #
        # # # 方差阈值：如果时间差的标准差超过50ms，认为对齐质量太差
        # # # (50ms)^2 = 2500 ms²
        # # max_variance_threshold = 2500.0
        # # if variance_ms > max_variance_threshold:
        # #     logger.warning(f"⚠️ DTW路径方差太大({variance_ms:.1f} > {max_variance_threshold} ms²)，质量不足，回退到简单方法")
        # #     return self._calculate_global_time_offset_simple(record_data, replay_data)
        #
        # # 6.3 计算加权平均偏移（考虑DTW路径的局部差异）
        # # 使用中位数避免异常值影响
        # median_offset = float(np.median(time_diffs))
        #
        # # 6.4 合理性检查：全局偏移不应超过合理范围
        # # 如果偏移过大，说明DTW对齐可能有问题，回退到简单方法
        # max_reasonable_offset = 5000.0  # 500ms (0.1ms单位)
        # if abs(median_offset) > max_reasonable_offset:
        #     logger.warning(f"⚠️ DTW计算的全局偏移过大({median_offset/10:.2f}ms > {max_reasonable_offset/10:.0f}ms)，"
        #                  f"可能对齐有问题，回退到简单方法")
        #     return self._calculate_global_time_offset_simple(record_data, replay_data)
        #
        # logger.info(f"🎯 DTW计算得到全局时间偏移(Median): {median_offset/10:.2f}ms (基于 {len(time_diffs)} 个路径点)")
        #
        # return median_offset
        #
        # ==================== DTW算法代码已注释结束 ====================

    # def _calculate_global_time_offset_simple(self, record_data: List[Note], replay_data: List[Note]) -> float:
    #     """
    #     简单的全局时间偏移计算方法（当DTW不可用时的回退方案）

    #     策略：
    #     1. 遍历录制音符
    #     2. 在播放数据中寻找相同KeyID且时间最近的音符
    #     3. 收集时间差
    #     4. 取中位数作为全局偏移

    #     Returns:
    #         float: 全局时间偏移量（0.1ms单位）
    #     """
    #     time_diffs = []

    #     # 建立播放数据的快速查找索引：KeyID -> List[Note]
    #     replay_map = {}
    #     for r_note in replay_data:
    #         if r_note.id not in replay_map:
    #             replay_map[r_note.id] = []
    #         replay_map[r_note.id].append(r_note)

    #     for record_note in record_data:
    #         # 寻找相同KeyID的播放音符
    #         if record_note.id not in replay_map:
    #             continue

    #         candidates = replay_map[record_note.id]
    #         if not candidates:
    #             continue

    #         # 计算录制时间
    #         rec_start, _ = self._calculate_note_times(record_note)

    #         # 寻找最近的候选
    #         best_diff = None
    #         min_abs_diff = float('inf')

    #         for replay_note in candidates:
    #             rep_start, _ = self._calculate_note_times(replay_note)
    #             diff = rep_start - rec_start
    #             abs_diff = abs(diff)

    #             # 使用一个较宽的窗口（例如2秒），避免匹配到完全不相关的音符
    #             # 20000 = 2000ms = 2s
    #             if abs_diff < 20000:
    #                 if abs_diff < min_abs_diff:
    #                     min_abs_diff = abs_diff
    #                     best_diff = diff

    #         if best_diff is not None:
    #             time_diffs.append(best_diff)

    #     if not time_diffs:
    #         logger.warning("⚠️ 无法计算全局偏移：没有找到任何匹配的按键对")
    #         return 0.0

    #     # 使用numpy计算中位数（对异常值不敏感）
    #     median_offset = float(np.median(time_diffs))

    #     # 合理性检查：全局偏移不应超过合理范围
    #     max_reasonable_offset = 5000.0  # 500ms (0.1ms单位)
    #     if abs(median_offset) > max_reasonable_offset:
    #         logger.warning(f"⚠️ 简单方法计算的全局偏移过大({median_offset/10:.2f}ms > {max_reasonable_offset/10:.0f}ms)，"
    #                      f"限制为合理范围")
    #         median_offset = max(-max_reasonable_offset, min(max_reasonable_offset, median_offset))

    #     logger.info(f"📊 简单方法计算得到全局时间偏移(Median): {median_offset/10:.2f}ms (基于 {len(time_diffs)} 个样本)")

    #     return median_offset

    def _initialize_matching_state(self) -> None:
        """初始化匹配状态"""
        self.failure_reasons.clear()
        self._clear_mean_error_cache()

    def _perform_single_note_matching(self, record_note: Note, record_index: int,
                                     replay_data: List[Note], used_replay_indices: set) -> MatchResult:
        """
        执行单个音符的匹配过程

        按优先级顺序尝试不同类型的匹配：
        1. 精确匹配 (≤50ms)
        2. 近似匹配 (50ms-300ms)
        3. 大误差匹配 (>300ms)
        4. 失败

        Args:
            record_note: 录制音符
            record_index: 录制音符索引
            replay_data: 播放数据
            used_replay_indices: 已使用的播放音符索引集合

        Returns:
            MatchResult: 匹配结果
        """
        note_info = self._extract_note_info(record_note, record_index)

        # 定义匹配策略：分层搜索，确保找到最佳匹配
        # 搜索策略与评级逻辑解耦，避免阈值影响评级分布
        match_strategies = [
            ("precision", self.precision_matched_pairs),     # 第一优先级: 精确搜索 (≤50ms)
            ("approximate", self.approximate_matched_pairs), # 第二优先级: 扩展搜索 (50ms-1000ms)
            ("severe", self.severe_matched_pairs),          # 第三优先级: 严重误差搜索 (>1000ms)
        ]

        # 按顺序尝试每种匹配策略
        for search_mode, record_list in match_strategies:
            candidates, reason = self._find_candidates(
                replay_data, note_info["keyon"], note_info["keyoff"],
                note_info["key_id"], time_offset=0, search_mode=search_mode
            )

            if candidates:
                chosen = self._select_best_candidate_from_list(candidates, used_replay_indices)
                if chosen:
                    # 匹配成功
                    replay_index = chosen.index
                    replay_note = replay_data[replay_index]

                    # 如果需要记录到特殊列表（如近似匹配或大误差匹配）
                    if record_list is not None:
                        match_pair = (record_index, replay_index, record_note, replay_note)
                        record_list.append(match_pair)

                    used_replay_indices.add(replay_index)

                    # 根据实际误差确定匹配类型
                    actual_match_type = self._evaluate_match_quality(chosen.error_ms)

                    return self._create_match_result(
                        actual_match_type, record_index, replay_index, chosen,
                        record_note, replay_note
                    )

        # 所有搜索都失败
        # 如果有候选但都被过滤掉了，说明误差都不在接受范围内
        # 如果没有候选，说明按键没有可用的播放音符
        if candidates:
            # 有候选但都不满足任何搜索模式，说明误差范围不符合
            failure_reason = reason if reason else f"按键{note_info['key_id']} 无符合误差范围的候选"
        else:
            # 没有候选，说明该按键没有可用的播放音符
            failure_reason = f"按键{note_info['key_id']} 无可用播放音符"

        return self._create_match_result(
            MatchType.FAILED, record_index, reason=failure_reason
        )

    def _select_best_candidate_from_list(self, candidates: List[Candidate], used_indices: set) -> Optional[Candidate]:
        """
        从候选列表中选择最佳的未使用候选

        Args:
            candidates: 候选列表（已按误差排序）
            used_indices: 已使用的索引集合

        Returns:
            Optional[Candidate]: 最佳候选，如果没有则返回None
        """
        for candidate in candidates:
            if candidate.index not in used_indices:
                return candidate
        return None



    def _log_successful_match(self, match_pair: Tuple, expanded_candidates: bool) -> None:
        """
        记录成功的匹配

        Args:
            match_pair: 匹配对
            expanded_candidates: 是否为扩展候选匹配
        """
        record_idx, replay_idx, record_note, replay_note = match_pair

        status = "🔄 匹配成功（扩展候选）" if expanded_candidates else "✅ 匹配成功"

        # 计算时间信息用于日志
        record_keyon, record_keyoff = self._calculate_note_times(record_note)
        replay_keyon, replay_keyoff = self._calculate_note_times(replay_note)

        # logger.info(f"{status}: 键ID={record_note.id}, 录制索引={record_idx}, 回放索引={replay_idx}")

    def _log_failed_match(self, record_index: int, record_note: Note, reason: str,
                         candidates: List[Dict], replay_data: List[Note]) -> None:
        """
        记录失败的匹配

        Args:
            record_index: 录制音符索引
            record_note: 录制音符
            reason: 失败原因
            candidates: 候选列表
            replay_data: 播放数据
        """
        note_info = self._extract_note_info(record_note, record_index)

        logger.info(f"❌ 匹配失败: 键ID={note_info['key_id']}, 录制索引={record_index}, "
                   f"录制时间=({note_info['keyon']/10:.2f}ms, {note_info['keyoff']/10:.2f}ms), "
                   f"原因: {reason}")

        # 记录被占用的候选详细信息
        for j, cand in enumerate(candidates[:3]):
            cand_note = replay_data[cand['index']]
            cand_keyon, cand_keyoff = self._calculate_note_times(cand_note)
            logger.info(f"   候选{j+1}: 回放索引={cand['index']}, "
                       f"回放时间=({cand_keyon/10:.2f}ms, {cand_keyoff/10:.2f}ms), "
                       f"总误差={cand['total_error']/10:.2f}ms")

    def _log_matching_statistics(self, record_data: List[Note], replay_data: List[Note],
                                matched_pairs: List, used_replay_indices: set) -> None:
        """
        记录匹配统计信息

        Args:
            record_data: 录制数据
            replay_data: 播放数据
            matched_pairs: 匹配对列表
            used_replay_indices: 已使用的播放索引
        """
        success_count = len(matched_pairs)
        failure_count = len(record_data) - success_count

        logger.info(f"📊 匹配完成: 成功{success_count}对, 失败{failure_count}对, "
                   f"总计{len(record_data)}个录制音符, 使用{len(used_replay_indices)}/{len(replay_data)}个播放音符")

    
    def _extract_note_info(self, note: Note, index: int) -> Dict:
        """
        提取音符基本信息
        
        Args:
            note: 音符对象
            index: 音符索引
            
        Returns:
            Dict: 音符信息字典，包含绝对时间戳
        """
        # 计算绝对时间戳（after_touch.index + offset）
        # 这是音符在整个时间线上的实际发生时间
        try:
            absolute_keyon = note.after_touch.index[0] + note.offset
            absolute_keyoff = note.after_touch.index[-1] + note.offset
        except (IndexError, AttributeError) as e:
            raise ValueError(f"音符ID {note.id} 的after_touch数据无效: {e}") from e
        
        return {
            'keyon': absolute_keyon,      # 绝对时间戳：按键开始时间
            'keyoff': absolute_keyoff,    # 绝对时间戳：按键结束时间
            'key_id': note.id,            # 按键ID
            'index': index                # 音符在列表中的索引
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
        获取精确匹配对列表（≤50ms）

        只返回精确匹配的配对，用于指标计算和图表显示

        Returns:
            List[Tuple[int, int, Note, Note]]: 精确匹配对列表
        """
        return self.matched_pairs.copy()
    
    # TODO
    def get_offset_alignment_data(self) -> List[Dict[str, Union[int, float]]]:
        """
        获取偏移对齐数据 - 计算每个匹配对的时间偏移（包括超过阈值的匹配对）
        
        Returns:
            List[Dict[str, Union[int, float]]]: 偏移对齐数据列表
        """
        offset_data: List[Dict[str, Union[int, float]]] = []
        
        # 所有匹配对都在 matched_pairs 中
        all_matched_pairs = self.matched_pairs

        for record_idx, replay_idx, record_note, replay_note in all_matched_pairs:
            # 计算录制和播放音符的时间
            record_keyon, record_keyoff = self._calculate_note_times(record_note)
            replay_keyon, replay_keyoff = self._calculate_note_times(replay_note)

            # 计算原始偏移量
            keyon_offset = replay_keyon - record_keyon

            # 计算校准后的偏移（去除全局固定延时）
            # 这反映了音符相对于系统平均延时的"抖动"或"误差"
            corrected_offset = keyon_offset - self.global_time_offset


            record_duration = record_keyoff - record_keyon
            replay_duration = replay_keyoff - replay_keyon
            duration_diff = replay_duration - record_duration
            duration_offset = duration_diff
            # 使用校准后的绝对误差
            avg_offset = abs(corrected_offset)


            offset_data.append({
                'record_index': record_idx,
                'replay_index': replay_idx,
                'key_id': record_note.id,
                'record_keyon': record_keyon,
                'replay_keyon': replay_keyon,
                'keyon_offset': keyon_offset,       # 原始偏移
                'corrected_offset': corrected_offset, # 校准后偏移（用于分析）
                'record_keyoff': record_keyoff,
                'replay_keyoff': replay_keyoff,
                'duration_offset': duration_offset,
                'average_offset': avg_offset,
                'record_duration': record_duration,
                'replay_duration': replay_duration,
                'duration_diff': duration_diff
            })

        return offset_data

    def get_precision_offset_alignment_data(self) -> List[Dict[str, Union[int, float]]]:
        """
        获取精确搜索阶段匹配对的偏移对齐数据 - 包含所有精确搜索阶段的匹配（误差 ≤ 50ms）

        精确搜索阶段：尝试找到误差 ≤ 50ms 的匹配，最终匹配类型可能是优秀/良好/一般
        用于计算延时误差统计指标，确保只使用相对高质量的匹配数据。

        Returns:
            List[Dict[str, Union[int, float]]]: 精确搜索阶段匹配对的偏移对齐数据列表
        """
        # 直接处理precision_matched_pairs中的所有匹配（≤50ms）
        offset_data = []
        for record_idx, replay_idx, record_note, replay_note in self.precision_matched_pairs:
            # 计算录制和播放音符的时间
            record_keyon, record_keyoff = self._calculate_note_times(record_note)
            replay_keyon, replay_keyoff = self._calculate_note_times(replay_note)

            # 获取锤速信息
            record_velocity = self._get_velocity_from_note(record_note)
            replay_velocity = self._get_velocity_from_note(replay_note)

            # 计算原始偏移量
            keyon_offset = replay_keyon - record_keyon

            # 计算校准后的偏移（去除全局固定延时）
            corrected_offset = keyon_offset - self.global_time_offset

            record_duration = record_keyoff - record_keyon
            replay_duration = replay_keyoff - replay_keyon
            duration_diff = replay_duration - record_duration
            duration_offset = duration_diff

            # 计算相对延时（用于悬停显示）
            relative_delay = corrected_offset / 10.0  # 转换为ms

            offset_data.append({
                'record_index': record_idx,
                'replay_index': replay_idx,
                'key_id': record_note.id,
                'record_keyon': record_keyon,
                'replay_keyon': replay_keyon,
                'record_velocity': record_velocity,    # 录制锤速
                'replay_velocity': replay_velocity,    # 播放锤速
                'velocity_diff': (replay_velocity - record_velocity) if record_velocity is not None and replay_velocity is not None else None,  # 锤速差值
                'keyon_offset': keyon_offset,       # 原始偏移
                'corrected_offset': corrected_offset, # 校准后偏移（用于分析）
                'relative_delay': relative_delay,     # 相对延时（ms）
                'record_keyoff': record_keyoff,
                'replay_keyoff': replay_keyoff,
                'duration_offset': duration_offset,
                'average_offset': abs(corrected_offset),
                'record_duration': record_duration,
                'replay_duration': replay_duration,
                'duration_diff': duration_diff
            })

        return offset_data

    def _get_velocity_from_note(self, note) -> Optional[float]:
        """从音符中获取锤速"""
        try:
            if not note:
                return None

            # 只从hammers数据中获取锤速
            if hasattr(note, 'hammers') and note.hammers is not None:
                if hasattr(note.hammers, 'values') and len(note.hammers.values) > 0:
                    hammer_velocity = note.hammers.values[0]
                    if hammer_velocity is not None and not pd.isna(hammer_velocity):
                        return float(hammer_velocity)
                elif hasattr(note.hammers, 'iloc') and len(note.hammers) > 0:
                    hammer_velocity = note.hammers.iloc[0]
                    if hammer_velocity is not None and not pd.isna(hammer_velocity):
                        return float(hammer_velocity)

            return None

        except Exception as e:
            logger.warning(f"[WARNING] 从音符提取锤速失败: {e}")
            return None

    def get_normal_offset_alignment_data(self) -> List[Dict[str, Union[int, float]]]:
        """
        获取正常匹配对的偏移对齐数据 - 只计算在阈值内的匹配对的时间偏移

        注意：这个方法只处理正常匹配对，不包括超过阈值的匹配对。
        用于计算准确的延时指标，避免异常数据影响统计结果。

        Returns:
            List[Dict[str, Union[int, float]]]: 正常匹配对的偏移对齐数据列表
        """
        offset_data: List[Dict[str, Union[int, float]]] = []

        # 只处理正常匹配对（在阈值内的匹配对）
        for record_idx, replay_idx, record_note, replay_note in self.matched_pairs:
            # 计算录制和播放音符的时间
            record_keyon, record_keyoff = self._calculate_note_times(record_note)
            replay_keyon, replay_keyoff = self._calculate_note_times(replay_note)

            # 计算原始偏移量
            keyon_offset = replay_keyon - record_keyon

            # 计算校准后的偏移（去除全局固定延时）
            # 由于DTW已禁用，全局偏移为0，所以corrected_offset = keyon_offset
            corrected_offset = keyon_offset - self.global_time_offset

            # 安全检查：正常匹配对的偏移应该在合理范围内
            # 如果超过1000ms，说明数据或匹配逻辑有严重问题
            max_reasonable_offset = 10000.0  # 1000ms
            if abs(corrected_offset) > max_reasonable_offset:
                logger.error(f"🚨 检测到异常大的校准偏移: {corrected_offset/10:.2f}ms, "
                           f"键ID={record_note.id}, 录制索引={record_idx}, 播放索引={replay_idx}, "
                           f"这表明匹配逻辑或数据有严重问题")
                # 跳过这个异常匹配对，不将其包含在统计中
                continue

            record_duration = record_keyoff - record_keyon
            replay_duration = replay_keyoff - replay_keyon
            duration_diff = replay_duration - record_duration
            duration_offset = duration_diff
            # 使用校准后的绝对误差
            avg_offset = abs(corrected_offset)
    
            
            offset_data.append({
                'record_index': record_idx,
                'replay_index': replay_idx,
                'key_id': record_note.id,
                'record_keyon': record_keyon,
                'replay_keyon': replay_keyon,
                'keyon_offset': keyon_offset,       # 原始偏移
                'corrected_offset': corrected_offset, # 校准后偏移（用于分析）
                'record_keyoff': record_keyoff,
                'replay_keyoff': replay_keyoff,
                'duration_offset': duration_offset,
                'average_offset': avg_offset,  
                'record_duration': record_duration,
                'replay_duration': replay_duration,
                'duration_diff': duration_diff
            })
        
        return offset_data



    def get_graded_error_stats(self) -> Dict[str, Dict[str, Union[int, float]]]:
        """
        获取分级误差统计 - 成功匹配质量评级

        只统计成功匹配对的质量分布（不包括失败匹配）：
        - correct: 优秀 (误差 ≤ 20ms)
        - minor: 良好 (20ms < 误差 ≤ 30ms)
        - moderate: 一般 (30ms < 误差 ≤ 50ms)
        - large: 较差 (50ms < 误差 ≤ 1000ms)
        - severe: 严重 (误差 > 1000ms)

        注意：只统计成功匹配的质量分布，失败匹配不参与评级统计

        Returns:
            Dict: 包含各级别的计数和百分比
        """
        # 获取所有成功的匹配对数据用于评级
        # 直接从match_results中获取所有成功匹配的数据
        all_matched_data = []
        for result in self.match_results:
            if result.is_success:
                # 为评级统计创建数据项
                item = self._create_offset_data_item(result)
                all_matched_data.append(item)

        # 总配对数 = 成功的匹配对数
        total_successful_matches = len(all_matched_data)

        # 初始化统计 - 只统计成功匹配的评级分布
        stats = {
            'correct': 0,      # 优秀 (≤20ms)
            'minor': 0,        # 良好 (20-30ms)
            'moderate': 0,     # 一般 (30-50ms)
            'large': 0,        # 较差 (50-1000ms)
            'severe': 0,       # 严重 (>1000ms)
            # 注意：不再统计失败匹配，因为失败匹配不参与质量评级
        }

        # 基于误差范围对所有成功匹配进行评级
        for item in all_matched_data:
            error_abs = abs(item['corrected_offset'])
            error_ms = error_abs / 10.0

            if error_ms <= 20:
                stats['correct'] += 1      # 优秀
            elif error_ms > 20 and error_ms <= 30:
                stats['minor'] += 1        # 良好
            elif error_ms > 30 and error_ms <= 50:
                stats['moderate'] += 1     # 一般
            elif error_ms > 50 and error_ms <= 1000:
                stats['large'] += 1        # 较差
            else:  # error_ms > 1000
                stats['severe'] += 1       # 严重

        # 计算百分比（基于成功的匹配对总数）
        # 评级统计只反映成功匹配的质量分布，不包括失败匹配
        result = {}
        for key, count in stats.items():
            result[key] = {
                'count': count,
                'percent': (count / total_successful_matches * 100) if total_successful_matches > 0 else 0.0
            }

        result['total_successful_matches'] = total_successful_matches  # 成功匹配总数
        result['global_offset_ms'] = self.global_time_offset / 10.0

        logger.info(f"📊 [后端] 匹配质量评级统计: 成功配对数={total_successful_matches} (只统计成功匹配的质量分布)")

        return result

    def _get_precision_matches_data(self) -> List[Dict[str, Union[int, float]]]:
        """
        获取精确匹配对的偏移数据

        Returns:
            List[Dict]: 精确匹配对的偏移数据
        """
        return self._get_matches_data_by_type(MatchType.PRECISION)

    def _get_approximate_matches_data(self) -> List[Dict[str, Union[int, float]]]:
        """
        获取近似匹配对的偏移数据 (50-1000ms)

        Returns:
            List[Dict]: 近似匹配对的偏移数据
        """
        return self._get_matches_data_by_type(MatchType.POOR)

    def _get_large_error_matches_data(self) -> List[Dict[str, Union[int, float]]]:
        """
        获取大误差匹配对的偏移数据 (>1000ms)

        Returns:
            List[Dict]: 大误差匹配对的偏移数据
        """
        return self._get_matches_data_by_type(MatchType.FAILED)

    def _get_matches_data_by_type(self, match_type: MatchType) -> List[Dict[str, Union[int, float]]]:
        """
        根据匹配类型获取对应的偏移数据

        Args:
            match_type: 匹配类型

        Returns:
            List[Dict]: 该类型匹配对的偏移数据
        """
        offset_data = []

        # 确定数据源和筛选条件 - 基于新的匹配类型
        pairs_source = []
        error_filter = None

        if match_type == MatchType.EXCELLENT:
            # 优秀匹配：从precision_matched_pairs中筛选 ≤20ms 的
            pairs_source = self.precision_matched_pairs
            error_filter = lambda error_ms: error_ms <= 20
        elif match_type == MatchType.GOOD:
            # 良好匹配：从precision_matched_pairs中筛选 20-30ms 的
            pairs_source = self.precision_matched_pairs
            error_filter = lambda error_ms: 20 < error_ms <= 30
        elif match_type == MatchType.FAIR:
            # 一般匹配：从precision_matched_pairs中筛选 30-50ms 的
            pairs_source = self.precision_matched_pairs
            error_filter = lambda error_ms: 30 < error_ms <= 50
        elif match_type == MatchType.POOR:
            # 较差匹配：所有来自loose_matched_pairs的匹配
            pairs_source = self.loose_matched_pairs
            error_filter = lambda error_ms: True  # 不需要额外筛选
        elif match_type == MatchType.SEVERE:
            # 严重误差：所有来自severe_matched_pairs的匹配
            pairs_source = self.severe_matched_pairs
            error_filter = lambda error_ms: True  # 不需要额外筛选
        elif match_type == MatchType.FAILED:
            # 失败匹配：无匹配的情况，不在此处理
            return []
        else:
            return []

        for record_idx, replay_idx, record_note, replay_note in pairs_source:
            # 计算录制和播放音符的时间
            record_keyon, record_keyoff = self._calculate_note_times(record_note)
            replay_keyon, replay_keyoff = self._calculate_note_times(replay_note)

            # 计算原始偏移量
            keyon_offset = replay_keyon - record_keyon

            # 计算校准后的偏移（去除全局固定延时）
            corrected_offset = keyon_offset - self.global_time_offset

            # 计算误差（毫秒）
            error_ms = abs(corrected_offset) / 10.0

            # 根据匹配类型筛选
            if not error_filter(error_ms):
                continue

            record_duration = record_keyoff - record_keyon
            replay_duration = replay_keyoff - replay_keyon
            duration_diff = replay_duration - record_duration
            duration_offset = duration_diff

            offset_data.append({
                'record_index': record_idx,
                'replay_index': replay_idx,
                'key_id': record_note.id,
                'record_keyon': record_keyon,
                'replay_keyon': replay_keyon,
                'keyon_offset': keyon_offset,       # 原始偏移
                'corrected_offset': corrected_offset, # 校准后偏移（用于分析）
                'record_keyoff': record_keyoff,
                'replay_keyoff': replay_keyoff,
                'duration_offset': duration_offset,
                'average_offset': abs(corrected_offset),
                'record_duration': record_duration,
                'replay_duration': replay_duration,
                'duration_diff': duration_diff
            })

        return offset_data
    
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
    
    def _calculate_note_times(self, note: Note) -> Tuple[float, float]:
        """
        计算音符的按键开始和结束时间
        
        Args:
            note: 音符对象
            
        Returns:
            Tuple[float, float]: (keyon_time, keyoff_time)
        """

        try:
            keyon_time = note.after_touch.index[0] + note.offset
            keyoff_time = note.after_touch.index[-1] + note.offset
        except (IndexError, AttributeError) as e:
            raise ValueError(f"音符ID {note.id} 的after_touch数据无效: {e}") from e
        
        return keyon_time, keyoff_time
    
    # TODO  
    def get_global_average_delay(self) -> float:
        """
        计算整首曲子的平均时延（基于已配对数据）
        
        使用带符号的 keyon_offset 计算：全局平均时延 = mean(keyon_offset)
        正值表示 replay 延迟，负值表示 replay 提前
        
        注意：此指标与平均误差（ME，get_mean_error()）在计算和概念上完全相同，
        都是对所有 keyon_offset 求算术平均，反映整体的提前/滞后方向性。
        如果需要不考虑方向的平均延时幅度，应使用平均绝对误差（MAE）。
        
        Returns:
            float: 平均时延（0.1ms单位，带符号）
        """
        if not self.matched_pairs:
            return 0.0

        # 获取偏移数据（只使用精确匹配对，误差 ≤ 50ms）
        offset_data = self.get_precision_offset_alignment_data()

        # 使用带符号的校准后偏移（不取绝对值，去除全局系统延时）
        corrected_offsets = [item.get('corrected_offset', 0) for item in offset_data if item.get('corrected_offset') is not None]
        
        if not corrected_offsets:
            return 0.0

        # 计算平均值（0.1ms单位，带符号）
        average_delay = sum(corrected_offsets) / len(corrected_offsets)

        logger.info(f"📊 [后端] 全局平均延时: {average_delay/10:.2f}ms ({average_delay:.1f}单位，基于{len(corrected_offsets)}个精确匹配对)")
        
        return average_delay
    
    def get_variance(self) -> float:
        """
        计算已匹配按键对的总体方差（Population Variance）
        
        说明：
        - "匹配对"指的是matched_pairs中的每个元素，是一个(record_note, replay_note)的配对
        - 对每个匹配对计算keyon_offset = replay_keyon - record_keyon
        - 使用带符号的keyon_offset计算方差，按照标准总体方差公式
        
        标准数学公式：
        σ² = (1/n) * Σ(x_i - μ)²
        其中 x_i 是带符号的keyon_offset，μ = (1/n) * Σ x_i（总体均值）
        
        Returns:
            float: 总体方差（单位：(0.1ms)²，转换为ms²需要除以100）
        """
        if not self.matched_pairs:
            return 0.0

        # 获取偏移对齐数据（只使用精确匹配对，误差 ≤ 50ms）
        offset_data = self.get_precision_offset_alignment_data()

        # 提取所有带符号的校准后偏移（去除全局系统延时）
        offsets = []
        for item in offset_data:
            corrected_offset = item.get('corrected_offset', 0)
            offsets.append(corrected_offset)  # 使用校准后的偏移值
        
        if len(offsets) <= 1:
            return 0.0
        
        # 计算总体方差（使用标准公式，分母 n）
        # 公式：σ² = (1/n) * Σ(x_i - μ)²
        # 其中 μ = (1/n) * Σ x_i（总体均值）
        mean = sum(offsets) / len(offsets)  # 总体均值（带符号）
        variance = sum((x - mean) ** 2 for x in offsets) / len(offsets)  # 总体方差使用 n
        return variance
    
    def get_standard_deviation(self) -> float:
        """
        计算已配对按键的总体标准差（Population Standard Deviation）
        对所有已匹配按键对的带符号keyon_offset计算总体标准差
        总体标准差 = sqrt(总体方差)
        
        按照标准数学公式：σ = √(σ²) = √((1/n) * Σ(x_i - μ)²)
        其中 x_i 是带符号的keyon_offset，μ = (1/n) * Σ x_i（总体均值）
        
        注意：此方法直接调用 get_variance() 然后开平方根，确保与方差计算的一致性
        由于 get_variance() 使用带符号值计算，此方法也使用带符号值
        
        Returns:
            float: 总体标准差（单位：0.1ms，转换为ms需要除以10）
        """
        variance = self.get_variance()
        if variance < 0:
            # 理论上不应该出现负数，但为了安全起见
            logger.warning(f"⚠️ 总体方差为负数: {variance}，返回0")
            return 0.0
        std = variance ** 0.5
        logger.info(f"📊 [后端] 总体标准差: {std/10:.2f}ms ({std:.1f}单位，基于精确匹配数据)")
        return std
    
    def get_mean_absolute_error(self) -> float:
        """
        计算已配对按键的平均绝对误差（MAE）
        对所有已匹配按键对的延时绝对值求平均
        
        Returns:
            float: 平均绝对误差（单位：0.1ms，转换为ms需要除以10）
        """
        if not self.matched_pairs:
            return 0.0

        # 获取偏移对齐数据（只使用精确匹配对，误差 ≤ 50ms）
        offset_data = self.get_precision_offset_alignment_data()

        # 提取所有校准后延时的绝对值（去除全局系统延时）
        abs_errors = []
        for item in offset_data:
            corrected_offset = item.get('corrected_offset', 0)
            abs_error = abs(corrected_offset)
            abs_errors.append(abs_error)
        
        # 计算平均绝对误差
        if abs_errors:
            mae = sum(abs_errors) / len(abs_errors)
            logger.info(f"📊 [后端] 平均绝对误差 MAE: {mae/10:.2f}ms ({mae:.1f}单位，基于{len(abs_errors)}个精确匹配对)")
            return mae
        else:
            return 0.0
    
    def get_coefficient_of_variation(self) -> float:
        """
        计算已配对按键的变异系数（Coefficient of Variation, CV）
        变异系数 = 总体标准差（σ）/ |总体均值（μ）| × 100%
        
        使用总体标准差（σ）与总体均值（μ）计算，反映相对变异程度
        
        注意：如果总体均值（μ）为0或接近0，变异系数可能无意义或非常大
        
        Returns:
            float: 变异系数（百分比，例如 15.5 表示 15.5%）
        """
        if not self.matched_pairs:
            return 0.0
        
        # 获取总体均值（μ，带符号）
        mean_0_1ms = self.get_mean_error()
        if abs(mean_0_1ms) < 1e-6:  # 如果均值接近0，无法计算CV
            return 0.0
        
        # 获取总体标准差（σ）
        std_0_1ms = self.get_standard_deviation()
        if std_0_1ms == 0:
            return 0.0
        
        # 计算变异系数：CV = (σ / |μ|) × 100%
        cv = (std_0_1ms / abs(mean_0_1ms)) * 100.0
        return cv
    
    def get_mean_squared_error(self) -> float:
        """
        计算已配对按键的均方误差（MSE）
        对所有已匹配按键对的延时的平方求平均
        
        Returns:
            float: 均方误差（单位：(0.1ms)²，转换为ms²需要除以100）
        """
        if not self.matched_pairs:
            return 0.0
        
        # 获取偏移对齐数据（只使用精确匹配对，误差 ≤ 50ms）
        offset_data = self.get_precision_offset_alignment_data()
        
        # 提取所有校准后延时的平方值（去除全局系统延时）
        squared_errors = []
        for item in offset_data:
            corrected_offset = item.get('corrected_offset', 0)
            squared_error = corrected_offset ** 2  # 使用校准后的偏移值
            squared_errors.append(squared_error)
        
        # 计算均方误差
        if squared_errors:
            mse = sum(squared_errors) / len(squared_errors)
            return mse
        else:
            return 0.0

    def get_root_mean_squared_error(self) -> float:
        """
        计算已配对按键的均方根误差（RMSE）
        RMSE = sqrt(MSE) = sqrt(mean((keyon_offset)^2))
        
        Returns:
            float: 均方根误差（单位：0.1ms，转换为ms需要除以10）
        """
        if not self.matched_pairs:
            return 0.0
        
        # 获取MSE
        mse = self.get_mean_squared_error()
        
        # 计算RMSE = sqrt(MSE)
        import math
        rmse = math.sqrt(mse) if mse > 0 else 0.0
        
        return rmse
    
    def get_mean_error(self) -> float:
        """
        获取已匹配按键对的平均误差（ME，带符号的平均偏差）
        对所有匹配对的keyon_offset（replay_keyon - record_keyon）求算术平均。

        Returns:
            float: 平均误差ME（单位：0.1ms，UI显示为ms需除以10）
        """
        # 返回缓存的平均误差，如果没有缓存则计算
        if self._mean_error_cached is None:
            self._mean_error_cached = self._calculate_mean_error()
        return self._mean_error_cached

    def _calculate_mean_error(self) -> float:
        """
        计算已匹配按键对的平均误差（内部方法）

        Returns:
            float: 平均误差ME（单位：0.1ms）
        """
        if not self.matched_pairs:
            return 0.0

        offset_data = self.get_precision_offset_alignment_data()
        offsets = [item.get('corrected_offset', 0) for item in offset_data]
        if not offsets:
            return 0.0
        mean_error = sum(offsets) / len(offsets)
        logger.info(f"📊 [后端] 平均误差 ME: {mean_error/10:.2f}ms ({mean_error:.1f}单位，基于{len(offsets)}个精确匹配对)")
        return mean_error

    def _clear_mean_error_cache(self) -> None:
        """
        清除平均误差缓存
        当匹配对发生变化时调用此方法
        """
        self._mean_error_cached = None
    
    def get_offset_statistics(self) -> Dict[str, Union[int, Dict[str, float]]]:
        """
        获取偏移统计信息
        
        Returns:
            Dict[str, Union[int, Dict[str, float]]]: 偏移统计信息
        """
        if not self.matched_pairs:
            return {
                'total_pairs': 0,
                'keyon_offset_stats': {'average': 0.0, 'max': 0.0, 'min': 0.0, 'std': 0.0},
                'duration_offset_stats': {'average': 0.0, 'max': 0.0, 'min': 0.0, 'std': 0.0},
                'overall_offset_stats': {'average': 0.0, 'max': 0.0, 'min': 0.0, 'std': 0.0}
            }
        
        # 获取偏移数据（只使用精确匹配对，误差 ≤ 50ms）
        offset_data = self.get_precision_offset_alignment_data()
        
        # 提取偏移值（使用校准后的keyon_offset）
        corrected_offsets = [item['corrected_offset'] for item in offset_data]
        duration_offsets = [item.get('duration_offset', 0.0) for item in offset_data]
        # 整体统计只使用校准后偏移的绝对值
        overall_offsets = [abs(item.get('corrected_offset', 0)) for item in offset_data if item.get('corrected_offset') is not None]
        
        return {
            'total_pairs': len(self.matched_pairs),
            'keyon_offset_stats': self._calculate_offset_stats(corrected_offsets),
            'duration_offset_stats': self._calculate_offset_stats(duration_offsets),
            'overall_offset_stats': self._calculate_offset_stats(overall_offsets)  # 使用校准后的偏移
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

    def _create_offset_data_item(self, match_result: MatchResult) -> Dict[str, Union[int, float]]:
        """
        为评级统计创建偏移数据项

        Args:
            match_result: 匹配结果

        Returns:
            Dict: 包含偏移数据的字典
        """
        record_note, replay_note = match_result.pair
        record_keyon, record_keyoff = self._calculate_note_times(record_note)
        replay_keyon, replay_keyoff = self._calculate_note_times(replay_note)

        # 计算原始偏移量
        keyon_offset = replay_keyon - record_keyon

        # 计算校准后的偏移（去除全局固定延时）
        corrected_offset = keyon_offset - self.global_time_offset

        record_duration = record_keyoff - record_keyon
        replay_duration = replay_keyoff - replay_keyon
        duration_diff = replay_duration - record_duration
        duration_offset = duration_diff

        return {
            'record_index': match_result.record_index,
            'replay_index': match_result.replay_index,
            'key_id': record_note.id,
            'record_keyon': record_keyon,
            'replay_keyon': replay_keyon,
            'keyon_offset': keyon_offset,       # 原始偏移
            'corrected_offset': corrected_offset, # 校准后偏移（用于分析）
            'record_keyoff': record_keyoff,
            'replay_keyoff': replay_keyoff,
            'duration_offset': duration_offset,
            'average_offset': abs(corrected_offset),
            'record_duration': record_duration,
            'replay_duration': replay_duration,
            'duration_diff': duration_diff
        }
