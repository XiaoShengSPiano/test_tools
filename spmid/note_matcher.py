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
   └── 第三阶段：应用扩展阈值过滤 (≤300ms)

【匹配分类 - 六等级系统】
- 优秀匹配 (≤20ms)：高质量匹配
- 良好匹配 (20-30ms)：较高质量匹配
- 一般匹配 (30-50ms)：可接受匹配
- 较差匹配 (50-100ms)：需要改进的匹配
- 严重匹配 (100-200ms)：质量极差但找到的匹配
- 失败匹配 (>200ms)：误差过大，标记为丢锤/多锤异常

【搜索策略 - 三阶段分层搜索】
- 第一阶段：精确搜索 (≤50ms) - 寻找优秀/良好/一般匹配
- 第二阶段：较差搜索 (50-100ms) - 寻找较差匹配
- 第三阶段：严重搜索 (100-200ms) - 寻找严重误差匹配

【阈值体系 - 六等级精确分类】
- 优秀阈值：≤20ms
- 良好阈值：20-30ms
- 一般阈值：30-50ms
- 较差阈值：50-100ms
- 严重阈值：100-200ms
- 失败阈值：>200ms

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
import heapq
import time

logger = Logger.get_logger()

# 匹配阈值常量 (0.1ms单位) - 六等级匹配系统
# 优秀匹配：≤20ms
EXCELLENT_THRESHOLD = 200.0
# 良好匹配：20-30ms
GOOD_THRESHOLD = 300.0
# 一般匹配：30-50ms
FAIR_THRESHOLD = 500.0
# 较差匹配：50-100ms
POOR_THRESHOLD = 1000.0
# 严重匹配：100-200ms
SEVERE_THRESHOLD = 2000.0
# 失败匹配：>200ms

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
        self.poor_matches = 0         # 较差匹配 (50-100ms)
        self.severe_matches = 0       # 严重误差 (100-200ms)
        self.failed_matches = 0       # 失败匹配 (>200ms或无候选)

        # 兼容性字段 - 保持向后兼容
        self.precision_matches = 0    # 精确匹配总数 (≤50ms)
        self.approximate_matches = 0  # 较差匹配总数 (50-100ms)
        self.large_error_matches = 0  # 严重误差匹配总数 (100-200ms)

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

        # 持续时间差异检测结果
        # (record_idx, replay_idx, record_note, replay_note, 
        #  record_duration, replay_duration, duration_ratio,
        #  record_keyon, record_keyoff, replay_keyon, replay_keyoff)
        self.duration_diff_pairs: List[Tuple[int, int, Note, Note, float, float, float, float, float, float, float]] = []

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
    
        # 拆分索引起始值（使用大数字避免与原始索引冲突）
        self._split_index_offset = 1000000
        self._split_counter = 0  # 全局拆分计数器，确保跨key_group的唯一索引
    
    def find_all_matched_pairs_legacy(self, record_data: List[Note], replay_data: List[Note]) -> List[Tuple[int, int, Note, Note]]:
        """
        【旧版算法 - 已弃用】查找所有匹配对：按键分组贪心匹配

        注意：此方法已被新算法替代，保留仅用于兼容性测试。
        新算法使用基于堆的keyon优先匹配，支持双向拆分。

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
        import time
        matching_start_time = time.time()

        # 初始化状态
        self._initialize_matching_state()

        logger.info(f"开始按键分组贪心匹配: 录制数据{len(record_data)}个音符, 回放数据{len(replay_data)}个音符")

        # 保存原始数据引用（用于失败匹配详情）
        self._record_data = record_data
        self._replay_data = replay_data

        # 1. 按按键ID分组数据
        record_by_key = self._group_notes_by_key(record_data)
        replay_by_key = self._group_notes_by_key(replay_data)

        logger.info(f"按键分组完成: 录制数据{len(record_by_key)}个按键, 播放数据{len(replay_by_key)}个按键")

        # 2. 对每个按键分别进行贪心匹配
        all_matched_pairs = []

        for key_id in record_by_key.keys():
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

            logger.debug(f"按键{key_id}匹配完成: 录制{record_count}个, 播放{replay_count}个, 匹配{matched_count}个")

        # 保存所有匹配对
        self.matched_pairs = all_matched_pairs

        # 3. 基于匹配结果计算按键统计信息
        self._calculate_key_statistics_from_matches(record_by_key, replay_by_key)

        # 记录按键级别的匹配统计
        self._log_key_matching_statistics()

        # 匹配完成后计算并缓存平均误差
        self._mean_error_cached = self._calculate_mean_error()

        # 计算并记录性能统计
        matching_end_time = time.time()
        matching_duration = matching_end_time - matching_start_time

        # 打印匹配统计信息
        logger.info(f"按键匹配性能统计: 耗时{matching_duration:.3f}秒")
        logger.info(f"匹配结果: 精确{self.match_statistics.precision_matches} | 近似{self.match_statistics.approximate_matches} | 大误差{self.match_statistics.large_error_matches} | 失败{self.match_statistics.failed_matches} | 总数{len(all_matched_pairs)}")

        # 输出持续时间差异统计
        duration_diff_count = len(self.duration_diff_pairs)
        if duration_diff_count > 0:
            logger.info(f"持续时间差异检测: 发现{duration_diff_count}个持续时间差异显著的匹配对")
        else:
            logger.info("持续时间差异检测: 未发现持续时间差异显著的匹配对")

        # 性能详情输出到控制台
        print(f"[匹配统计] 精确匹配: {self.match_statistics.precision_matches} 个")
        print(f"[匹配统计] 较差匹配: {self.match_statistics.approximate_matches} 个")
        print(f"[匹配统计] 严重误差: {self.match_statistics.large_error_matches} 个")
        print(f"[匹配统计] 失败匹配: {self.match_statistics.failed_matches} 个")
        print(f"[匹配统计] 总匹配对: {len(all_matched_pairs)} 个 (准确率分子)")
        print(f"[持续时间差异] 检测到: {duration_diff_count} 个持续时间差异显著的匹配对")
        print(f"[性能统计] 按键匹配耗时: {matching_duration:.3f} 秒")

        return all_matched_pairs

    # ========== 主算法：基于堆的keyon优先匹配（支持拆分） ==========
    # 注意：旧算法已重命名为 find_all_matched_pairs_legacy
    
    def find_all_matched_pairs(self, record_data: List[Note], replay_data: List[Note]) -> List[Tuple[int, int, Note, Note]]:
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
        
        算法优势：
        - 解决了旧算法无法处理双向合并的问题
        - 严格按keyon时间排序，避免匹配错误
        - 支持智能拆分（拐点优先，触后值最小后备）
        
        Args:
            record_data: 录制数据
            replay_data: 播放数据
            
        Returns:
            List[Tuple[int, int, Note, Note]]: 匹配对列表 (record_index, replay_index, record_note, replay_note)
        """
        matching_start_time = time.time()
        
        # 初始化状态
        self._initialize_matching_state()
        
        logger.info(f"🚀 开始新算法匹配（基于堆的keyon优先）: 录制{len(record_data)}个音符, 播放{len(replay_data)}个音符")
        
        # 保存原始数据引用
        self._record_data = record_data
        self._replay_data = replay_data
        
        # 1. 按key_id分组
        record_by_key = self._group_notes_by_key(record_data)
        replay_by_key = self._group_notes_by_key(replay_data)
        
        logger.info(f"按键分组完成: 录制{len(record_by_key)}个按键, 播放{len(replay_by_key)}个按键")
        
        # 2. 对每个按键分别进行堆匹配
        all_matched_pairs = []
        
        for key_id in sorted(record_by_key.keys()):
            key_record_notes = record_by_key[key_id]
            key_replay_notes = replay_by_key.get(key_id, [])
            
            logger.info(f"📌 处理按键{key_id}: 录制{len(key_record_notes)}个, 播放{len(key_replay_notes)}个")
            
            # 对该按键进行堆匹配
            key_matched_pairs = self._match_single_key_with_heap(
                key_id, key_record_notes, key_replay_notes
            )
            
            all_matched_pairs.extend(key_matched_pairs)
            
            logger.info(f"✅ 按键{key_id}匹配完成: 匹配{len(key_matched_pairs)}对")
        
        # 保存匹配对
        self.matched_pairs = all_matched_pairs
        
        # 3. 计算统计信息
        self._calculate_key_statistics_from_matches(record_by_key, replay_by_key)
        
        # 缓存平均误差
        self._mean_error_cached = self._calculate_mean_error()
        
        # 性能统计
        matching_end_time = time.time()
        matching_duration = matching_end_time - matching_start_time
        
        # 输出统计信息
        logger.info(f"🎯 新算法匹配完成: 总匹配对{len(all_matched_pairs)}个, 耗时{matching_duration:.3f}秒")
        logger.info(f"质量分布: 优秀{self.match_statistics.precision_matches} | "
                   f"近似{self.match_statistics.approximate_matches} | "
                   f"大误差{self.match_statistics.large_error_matches} | "
                   f"失败{self.match_statistics.failed_matches}")
        
        duration_diff_count = len(self.duration_diff_pairs)
        if duration_diff_count > 0:
            logger.info(f"持续时间差异: 检测到{duration_diff_count}个（拆分处理后）")
        
        # 控制台输出
        print(f"\n{'='*60}")
        print(f"[新算法] 匹配完成")
        print(f"{'='*60}")
        print(f"[匹配统计] 总匹配对: {len(all_matched_pairs)} 个")
        print(f"[质量分布] 优秀: {self.match_statistics.precision_matches} 个")
        print(f"[质量分布] 近似: {self.match_statistics.approximate_matches} 个")
        print(f"[质量分布] 大误差: {self.match_statistics.large_error_matches} 个")
        print(f"[质量分布] 失败: {self.match_statistics.failed_matches} 个")
        print(f"[持续时间差异] 检测到: {duration_diff_count} 个")
        print(f"[性能统计] 匹配耗时: {matching_duration:.3f} 秒")
        print(f"{'='*60}\n")
        
        return all_matched_pairs
    
    def _match_single_key_with_heap(self, key_id: int, 
                                     record_notes: List[Tuple[int, Note]], 
                                     replay_notes: List[Tuple[int, Note]]) -> List[Tuple[int, int, Note, Note]]:
        """
        使用最小堆对单个按键进行匹配（支持拆分）
        
        Args:
            key_id: 按键ID
            record_notes: 该按键的录制音符列表 [(原始索引, Note), ...]
            replay_notes: 该按键的播放音符列表 [(原始索引, Note), ...]
            
        Returns:
            List[Tuple[int, int, Note, Note]]: 该按键的匹配对列表
        """
        logger.debug(f"  🔧 初始化按键{key_id}的堆结构...")
        
        # 构建最小堆
        record_heap, replay_heap = self._build_matching_heaps(key_id, record_notes, replay_notes)
        
        # 初始化状态
        matched_pairs = []
        used_replay_indices = set()
        skipped_replay_indices = set()  # 跳过的播放数据索引（可疑的多锤）
        
        logger.debug(f"  🔄 开始主循环匹配...")
        
        # 主循环：处理所有录制数据
        match_count, failed_count = self._process_record_notes(
            key_id, record_heap, replay_heap, used_replay_indices, 
            skipped_replay_indices, matched_pairs
        )
        
        # 处理跳过的播放数据（多锤）
        extra_hammer_count = self._process_skipped_replays(
            key_id, skipped_replay_indices, replay_notes
        )
        
        logger.debug(f"  ✅ 按键{key_id}匹配完成: 成功{match_count}个, 失败{failed_count}个, 多锤{extra_hammer_count}个")
        
        return matched_pairs
    
    def _build_matching_heaps(self, key_id: int, 
                               record_notes: List[Tuple[int, Note]], 
                               replay_notes: List[Tuple[int, Note]]) -> Tuple[List, List]:
        """
        构建录制和播放的最小堆
        
        Args:
            key_id: 按键ID
            record_notes: 录制音符列表
            replay_notes: 播放音符列表
            
        Returns:
            Tuple[List, List]: (record_heap, replay_heap)
        """
        # 堆元素格式: (keyon_time, parent_index, note_object, split_seq)
        # split_seq: None=原始数据, 0/1/2...=拆分序号
        
        # 录制堆
        record_heap = []
        for orig_idx, note in record_notes:
            if note.key_on_ms is not None:
                heapq.heappush(record_heap, (note.key_on_ms, orig_idx, note, None))
            else:
                logger.warning(f"  ⚠️ 按键{key_id}的录制音符索引{orig_idx}没有key_on_ms，跳过")
        
        # 播放堆
        replay_heap = []
        for orig_idx, note in replay_notes:
            if note.key_on_ms is not None:
                heapq.heappush(replay_heap, (note.key_on_ms, orig_idx, note, None))
            else:
                logger.warning(f"  ⚠️ 按键{key_id}的播放音符索引{orig_idx}没有key_on_ms，跳过")
        
        logger.debug(f"  📊 堆构建完成: 录制堆{len(record_heap)}个, 播放堆{len(replay_heap)}个")
        
        return record_heap, replay_heap
    
    def _process_record_notes(self, key_id: int, record_heap: List, replay_heap: List,
                               used_replay_indices: set, skipped_replay_indices: set,
                               matched_pairs: List) -> Tuple[int, int]:
        """
        处理所有录制数据的主循环
        
        Args:
            key_id: 按键ID
            record_heap: 录制堆
            replay_heap: 播放堆
            used_replay_indices: 已使用的播放索引集合
            skipped_replay_indices: 跳过的播放索引集合（可疑的多锤）
            matched_pairs: 匹配对列表（输出）
            
        Returns:
            Tuple[int, int]: (成功匹配数, 失败匹配数)
        """
        match_count = 0
        failed_count = 0
        
        while record_heap:
            # 取出录制数据
            rec_keyon, rec_idx, rec_note, rec_split_seq = heapq.heappop(record_heap)
            self._log_processing_record(rec_idx, rec_note, rec_keyon)
            
            # 清理已使用的播放数据
            self._clean_used_replay_notes(replay_heap, used_replay_indices)
            
            # 查找播放候选（支持跳过可疑的多锤）
            replay_candidate = self._find_replay_candidate(
                key_id, replay_heap, rec_keyon, skipped_replay_indices
            )
            
            if replay_candidate is None:
                # 无可用候选 → 失败
                self._create_failed_match(rec_idx, None, "无可用播放数据")
                failed_count += 1
                continue
            
            rep_keyon, rep_idx, rep_note, rep_split_seq, keyon_error_ms = replay_candidate
            
            # 检查误差阈值
            if not self._check_error_threshold(keyon_error_ms, rec_idx, rep_idx, rep_split_seq):
                # 超出阈值 → 失败
                failed_count += 1
                continue
            
            # 创建成功匹配（支持拆分，在pop播放数据之前检查是否需要拆分）
            success, split_type = self._create_successful_match(
                rec_idx, rec_note, rec_split_seq,
                rep_idx, rep_note, rep_split_seq,
                keyon_error_ms, matched_pairs, used_replay_indices,
                record_heap, replay_heap
            )
            
            if success:
                # 匹配成功：消费播放数据
                heapq.heappop(replay_heap)
                match_count += 1
        
        return match_count, failed_count
    
    def _log_processing_record(self, rec_idx: int, rec_note: Note, rec_keyon: float):
        """记录当前处理的录制数据"""
        if rec_note.is_split:
            parent_idx = rec_note.split_parent_idx if rec_note.split_parent_idx is not None else rec_idx
            split_seq = rec_note.split_seq if rec_note.split_seq is not None else 0
            logger.debug(f"    处理录制[{parent_idx}:拆分{split_seq}] keyon={rec_keyon:.1f}ms")
        else:
            logger.debug(f"    处理录制[{rec_idx}] keyon={rec_keyon:.1f}ms")
    
    def _clean_used_replay_notes(self, replay_heap: List, used_replay_indices: set):
        """清理播放堆顶的已使用数据（惰性删除）"""
        while replay_heap:
            rep_keyon, rep_idx, rep_note, rep_split_seq = replay_heap[0]
            
            if rep_idx in used_replay_indices:
                heapq.heappop(replay_heap)
                logger.debug(f"      清理已使用的播放[{rep_idx}]")
                continue
            else:
                break
    
    def _find_replay_candidate(self, key_id: int, replay_heap: List, rec_keyon: float,
                                skipped_replay_indices: set) -> Optional[Tuple]:
        """
        使用Lookahead窗口查找最佳播放候选
        
        策略：
        1. 先跳过提前超过200ms的候选（ADVANCE_THRESHOLD检测）
        2. Peek前N个候选进行综合评分
        3. 选择得分最低的候选
        4. 跳过前面的次优候选
        
        Args:
            key_id: 按键ID
            replay_heap: 播放堆
            rec_keyon: 录制keyon时间（ms）
            skipped_replay_indices: 跳过的播放索引集合（输出）
            
        Returns:
            Optional[Tuple]: (rep_keyon, rep_idx, rep_note, rep_split_seq, error_ms) 或 None
        """
        if not replay_heap:
            logger.debug(f"      ✗ 无可用播放数据 → 失败")
            return None
        
        # 【第一道防线】循环跳过"提前过多"的播放数据（>200ms，极端情况）
        while replay_heap:
            rep_keyon, rep_idx, rep_note, rep_split_seq = replay_heap[0]
            
            # 检查：播放是否"提前"过多？
            if rep_keyon < rec_keyon - ADVANCE_THRESHOLD:
                # 播放明显提前录制，可能是多锤
                advance_ms = rec_keyon - rep_keyon
                
                # 日志
                if rep_note.is_split:
                    parent_idx = rep_note.split_parent_idx if rep_note.split_parent_idx is not None else rep_idx
                    split_seq = rep_note.split_seq if rep_note.split_seq is not None else 0
                    logger.debug(f"      ⚠️ [防线1] 跳过极端多锤 播放[{parent_idx}:拆分{split_seq}] "
                               f"keyon={rep_keyon:.1f}ms 提前录制{advance_ms:.1f}ms > 阈值{ADVANCE_THRESHOLD:.1f}ms")
                else:
                    logger.debug(f"      ⚠️ [防线1] 跳过极端多锤 播放[{rep_idx}] "
                               f"keyon={rep_keyon:.1f}ms 提前录制{advance_ms:.1f}ms > 阈值{ADVANCE_THRESHOLD:.1f}ms")
                
                # 移除并记录
                heapq.heappop(replay_heap)
                skipped_replay_indices.add((rep_idx, rep_note.key_on_ms, rep_split_seq, rep_note.is_split))
                continue
            else:
                break
        
        # 检查是否还有可用候选
        if not replay_heap:
            logger.debug(f"      ✗ 跳过多锤后无可用播放数据 → 失败")
            return None
        
        # 【第二道防线】Lookahead窗口评分，选择最佳候选
        best_candidate = self._select_best_candidate_with_lookahead(
            replay_heap, rec_keyon, skipped_replay_indices
        )
        
        if best_candidate is None:
            logger.debug(f"      ✗ Lookahead评分后无可接受候选 → 失败")
            return None
        
        return best_candidate
    
    def _select_best_candidate_with_lookahead(self, replay_heap: List, rec_keyon: float,
                                               skipped_replay_indices: set) -> Optional[Tuple]:
        """
        使用Lookahead窗口评分并选择最佳候选
        
        Args:
            replay_heap: 播放堆
            rec_keyon: 录制keyon时间（ms）
            skipped_replay_indices: 跳过的播放索引集合（输出）
            
        Returns:
            Optional[Tuple]: (rep_keyon, rep_idx, rep_note, rep_split_seq, error_ms) 或 None
        """
        # 1. Peek前N个候选
        window_size = min(LOOKAHEAD_WINDOW_SIZE, len(replay_heap))
        candidates = []
        
        for i in range(window_size):
            rep_keyon, rep_idx, rep_note, rep_split_seq = replay_heap[i]
            candidates.append({
                'heap_index': i,
                'keyon': rep_keyon,
                'idx': rep_idx,
                'note': rep_note,
                'split_seq': rep_split_seq
            })
        
        # 2. 评分每个候选
        logger.debug(f"      📊 [Lookahead] 评估前{window_size}个候选:")
        
        scored_candidates = []
        for candidate in candidates:
            score_result = self._calculate_candidate_score(candidate, rec_keyon)
            scored_candidates.append(score_result)
            
            # 详细日志
            c = score_result['candidate']
            idx_str = self._format_note_index(c['idx'], c['note'], c['split_seq'])
            logger.debug(f"        播放{idx_str} "
                        f"keyon={score_result['keyon']:.1f}ms "
                        f"误差={score_result['error']:.1f}ms "
                        f"偏向={score_result['bias']:+.1f}ms "
                        f"惩罚={score_result['penalty']:.1f} "
                        f"→ 总分={score_result['score']:.1f}")
        
        # 3. 选择得分最低的
        scored_candidates.sort(key=lambda x: x['score'])
        best = scored_candidates[0]
        best_index = best['candidate']['heap_index']
        
        # 日志：选择结果
        best_c = best['candidate']
        best_idx_str = self._format_note_index(best_c['idx'], best_c['note'], best_c['split_seq'])
        logger.debug(f"      ✓ [Lookahead] 选择播放{best_idx_str} keyon={best['keyon']:.1f}ms (总分={best['score']:.1f})")
        
        # 4. 跳过前面的次优候选
        if best_index > 0:
            logger.debug(f"      ⚠️ [Lookahead] 跳过前{best_index}个次优候选:")
            for i in range(best_index):
                rep_keyon, rep_idx, rep_note, rep_split_seq = heapq.heappop(replay_heap)
                skipped_replay_indices.add((rep_idx, rep_keyon, rep_split_seq, rep_note.is_split))
                
                idx_str = self._format_note_index(rep_idx, rep_note, rep_split_seq)
                logger.debug(f"        播放{idx_str} keyon={rep_keyon:.1f}ms (综合得分不如后续候选)")
        
        # 5. 返回最佳候选（现在在堆顶）
        rep_keyon, rep_idx, rep_note, rep_split_seq = replay_heap[0]
        keyon_error_ms = best['error']
        
        return (rep_keyon, rep_idx, rep_note, rep_split_seq, keyon_error_ms)
    
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
    
    def _format_note_index(self, idx: int, note: Note, split_seq: Optional[int]) -> str:
        """
        格式化音符索引显示
        
        Args:
            idx: 音符索引
            note: Note对象
            split_seq: 拆分序号
            
        Returns:
            str: 格式化的索引字符串
        """
        if note.is_split and split_seq is not None:
            parent_idx = note.split_parent_idx if note.split_parent_idx is not None else idx
            return f"[{parent_idx}:拆分{split_seq}]"
        else:
            return f"[{idx}]"
    
    def _check_error_threshold(self, keyon_error_ms: float, rec_idx: int, 
                                rep_idx: int, rep_split_seq: Optional[int]) -> bool:
        """
        检查误差是否在阈值内（≤200ms）
        
        Returns:
            bool: True=在阈值内, False=超出阈值
        """
        keyon_error_units = keyon_error_ms * 10.0
        
        if keyon_error_units > SEVERE_THRESHOLD:
            logger.debug(f"      ✗ 误差{keyon_error_ms:.1f}ms超出阈值{SEVERE_THRESHOLD/10:.1f}ms → 失败")
            
            self._create_failed_match(
                rec_idx, keyon_error_ms,
                f"所有候选误差超过阈值（{keyon_error_ms:.1f}ms > {SEVERE_THRESHOLD/10:.1f}ms）"
            )
            return False
        
        return True
    
    def _process_skipped_replays(self, key_id: int, skipped_replay_indices: set,
                                  replay_notes: List[Tuple[int, Note]]) -> int:
        """
        处理跳过的播放数据，标记为多锤
        
        Args:
            key_id: 按键ID
            skipped_replay_indices: 跳过的播放数据集合 {(idx, keyon_ms, split_seq, is_split), ...}
            replay_notes: 原始播放音符列表（用于统计）
            
        Returns:
            int: 多锤数量
        """
        if not skipped_replay_indices:
            return 0
        
        logger.debug(f"  📋 处理按键{key_id}跳过的播放数据: {len(skipped_replay_indices)}个")
        
        # 统计多锤
        for rep_idx, keyon_ms, rep_split_seq, is_split in skipped_replay_indices:
            # 日志
            if is_split and rep_split_seq is not None:
                logger.info(f"  🔨 确认多锤: 按键{key_id} 播放[{rep_idx}:拆分{rep_split_seq}] "
                           f"keyon={keyon_ms:.1f}ms（提前过多，无对应录制数据）")
            else:
                logger.info(f"  🔨 确认多锤: 按键{key_id} 播放[{rep_idx}] "
                           f"keyon={keyon_ms:.1f}ms（提前过多，无对应录制数据）")
        
        return len(skipped_replay_indices)
    
    def _create_failed_match(self, rec_idx: int, error_ms: Optional[float], reason: str):
        """创建失败匹配结果"""
        match_result = MatchResult(
            match_type=MatchType.FAILED,
            record_index=rec_idx,
            replay_index=None,
            error_ms=error_ms,
            pair=None,
            reason=reason
        )
        self.match_results.append(match_result)
        self.match_statistics.add_result(match_result)
    
    def _create_successful_match(self, rec_idx: int, rec_note: Note, rec_split_seq: Optional[int],
                                  rep_idx: int, rep_note: Note, rep_split_seq: Optional[int],
                                  keyon_error_ms: float, matched_pairs: List,
                                  used_replay_indices: set, record_heap: List, replay_heap: List) -> Tuple[bool, str]:
        """
        创建成功匹配（支持拆分）
        
        Returns:
            Tuple[bool, str]: (是否成功, 拆分类型: 'none'/'record'/'replay')
        """
        # 评判质量
        match_type = self._evaluate_match_quality(keyon_error_ms)
        
        # 检查持续时间差异并尝试拆分
        rec_duration = rec_note.duration_ms if rec_note.duration_ms else 0
        rep_duration = rep_note.duration_ms if rep_note.duration_ms else 0
        
        if rec_duration > 0 and rep_duration > 0:
            duration_ratio = max(rec_duration, rep_duration) / min(rec_duration, rep_duration)
            
            should_split = False
            trigger_reason = ""
            force_record = False
            
            # 主要条件：持续时间差异显著（>= 2.0倍）
            if duration_ratio >= 2.0:
                should_split = True
                trigger_reason = "主要条件"
                logger.debug(f"      ⚠️ 【主要条件】持续时间差异显著: {duration_ratio:.2f}倍，尝试拆分...")
            
            # 次要条件：持续时间相差不大，但短数据keyoff之后还有hammer和after_touch
            elif rec_duration != rep_duration:  # 确保有长短之分
                long_note = rec_note if rec_duration > rep_duration else rep_note
                short_note = rep_note if rec_duration > rep_duration else rec_note
                
                if self._check_hammer_after_shorter_keyoff(long_note, short_note):
                    should_split = True
                    trigger_reason = "次要条件"
                    force_record = True  # 次要条件触发时需要强制记录
                    logger.debug(f"      ⚠️ 【次要条件】持续时间相差不大({duration_ratio:.2f}倍)，"
                               f"但检测到短数据keyoff后仍有锤击和after_touch，尝试拆分...")
            
            # 如果满足任一条件，进行拆分
            if should_split:
                # 重要：在拆分之前先记录原始数据到持续时间差异列表
                # 这样可以在UI中看到拆分前的原始曲线
                self._check_duration_difference(rec_note, rep_note, rec_idx, rep_idx, force_record=force_record)
                logger.debug(f"      📝 已记录拆分前的原始数据（触发原因：{trigger_reason}）")
                
                # 尝试拆分并立即匹配第一部分
                split_result = self._try_split_and_match_first(
                    rec_idx, rec_note, rec_split_seq,
                    rep_idx, rep_note, rep_split_seq,
                    record_heap, replay_heap, used_replay_indices,
                    rec_duration, rep_duration
                )
                
                if split_result is not None:
                    # 拆分成功，返回用于匹配的Note（第一部分）
                    split_type, match_rec_note, match_rep_note = split_result
                    logger.debug(f"      ↺ 拆分成功（拆分{split_type}数据），立即匹配第一部分")
                    # 更新rec_note和rep_note为拆分后的第一部分
                    rec_note = match_rec_note
                    rep_note = match_rep_note
                    # 继续下面的匹配逻辑
                else:
                    logger.debug(f"      ⚠️ 拆分失败，按原匹配处理")
        
        # 创建匹配对（使用父索引）
        final_rec_idx = rec_note.split_parent_idx if rec_note.is_split else rec_idx
        final_rep_idx = rep_note.split_parent_idx if rep_note.is_split else rep_idx
        matched_pairs.append((final_rec_idx, final_rep_idx, rec_note, rep_note))
        
        # 创建匹配结果（使用父索引）
        match_result = MatchResult(
            match_type=match_type,
            record_index=final_rec_idx,
            replay_index=final_rep_idx,
            error_ms=keyon_error_ms,
            pair=(rec_note, rep_note),
            reason=""
        )
        self.match_results.append(match_result)
        self.match_statistics.add_result(match_result)
        
        # 标记为已使用
        used_replay_indices.add(rep_idx)
        
        # 日志
        rec_display = f"[{rec_note.split_parent_idx}:拆分{rec_note.split_seq}]" if rec_note.is_split else f"[{rec_idx}]"
        rep_display = f"[{rep_note.split_parent_idx}:拆分{rep_note.split_seq}]" if rep_note.is_split else f"[{rep_idx}]"
        logger.debug(f"      ✓ 匹配成功: 录制{rec_display} ↔ 播放{rep_display} ({match_type.value}, {keyon_error_ms:.1f}ms)")
        
        return (True, 'none')  # 成功创建，无拆分
    
    def _try_split_and_match_first(self, rec_idx: int, rec_note: Note, rec_split_seq: Optional[int],
                                     rep_idx: int, rep_note: Note, rep_split_seq: Optional[int],
                                     record_heap: List, replay_heap: List, used_replay_indices: set,
                                     rec_duration: float, rep_duration: float) -> Optional[Tuple[str, Note, Note]]:
        """
        尝试拆分并返回第一部分用于立即匹配
        
        Returns:
            Optional[Tuple[str, Note, Note]]: (拆分类型, 匹配用的rec_note, 匹配用的rep_note) 或 None
        """
        from backend.key_splitter_simplified import KeySplitter
        
        # 判断拆分方向
        if rec_duration > rep_duration:
            # 录制数据更长 → 拆分录制数据
            logger.debug(f"        拆分录制数据（录制{rec_duration:.1f}ms > 播放{rep_duration:.1f}ms）")
            result = self._split_record_note_and_return_first(
                rec_idx, rec_note, rep_note, record_heap,
                rec_duration, rep_duration
            )
            if result:
                rec_note_a, rec_note_b = result
                # rec_note_a用于匹配，rec_note_b已加入堆
                return ('record', rec_note_a, rep_note)
            return None
        else:
            # 播放数据更长 → 拆分播放数据
            logger.debug(f"        拆分播放数据（播放{rep_duration:.1f}ms > 录制{rec_duration:.1f}ms）")
            result = self._split_replay_note_and_return_first(
                rep_idx, rep_note, rec_note, replay_heap, used_replay_indices,
                rec_duration, rep_duration
            )
            if result:
                rep_note_a, rep_note_b = result
                # rep_note_a用于匹配，rep_note_b已加入堆
                return ('replay', rec_note, rep_note_a)
            return None
    
    def _split_note_and_return_first(self, long_note: Note, long_idx: int, short_note: Note,
                                     target_heap: List,
                                     rec_duration: float, rep_duration: float,
                                     data_type: str, used_indices: Optional[set] = None) -> Optional[Tuple[Note, Note]]:
        """
        拆分Note并返回两个Note对象（通用方法）
        
        Args:
            long_note: 长数据（要拆分的）
            long_idx: 长数据的索引
            short_note: 短数据
            target_heap: 目标堆（将note_b加入）
            split_counter: 拆分计数器
            rec_duration: 录制数据持续时间
            rep_duration: 播放数据持续时间
            data_type: 数据类型标识（"录制"或"播放"），用于日志
            used_indices: 可选的已使用索引集合
        
        Returns:
            Optional[Tuple[Note, Note]]: (note_a用于匹配, note_b已加入堆) 或 None
        """
        # 提取hammers（只考虑velocity > 0的）
        hammer_times_ms = []
        for i in range(len(long_note.hammers)):
            if long_note.hammers.values[i] > 0:
                time_ms = (long_note.hammers.index[i] + long_note.offset) / 10.0
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
            parent_idx=long_idx,
            split_seq_a=0,  # 第一部分
            split_seq_b=1   # 第二部分
        )
        
        # 生成拆分数据的唯一索引（使用大偏移量避免与原始索引冲突）
        split_idx_b = self._split_index_offset + self._split_counter * 2 + 1
        self._split_counter += 1
        
        # 设置拆分元数据（实际上_split_note_at_time已经设置了，这里是冗余的）
        note_a.split_parent_idx = long_idx
        note_a.split_seq = 0
        note_a.is_split = True
        
        note_b.split_parent_idx = long_idx
        note_b.split_seq = 1
        note_b.is_split = True
        
        # 标记原数据为已使用（如果提供了used_indices）
        if used_indices is not None:
            used_indices.add(long_idx)
        
        # 只将note_b（第二部分）加入堆，note_a用于立即匹配
        if note_b.key_on_ms is not None:
            heapq.heappush(target_heap, (note_b.key_on_ms, split_idx_b, note_b, 1))
            logger.debug(f"        ↺ {data_type}数据拆分: note_a立即匹配, note_b({note_b.key_on_ms:.1f}ms)加入堆")
        else:
            logger.warning(f"        ⚠️ 拆分后的{data_type}数据B没有key_on_ms，跳过")
        
        # 返回两个Note对象
        return (note_a, note_b)
    
    def _split_replay_note_and_return_first(self, rep_idx: int, rep_note: Note, rec_note: Note,
                                              replay_heap: List, used_replay_indices: set,
                                              rec_duration: float, rep_duration: float) -> Optional[Tuple[Note, Note]]:
        """拆分播放数据（简化wrapper）"""
        return self._split_note_and_return_first(
            long_note=rep_note, long_idx=rep_idx, short_note=rec_note,
            target_heap=replay_heap,
            rec_duration=rec_duration, rep_duration=rep_duration,
            data_type="播放", used_indices=used_replay_indices
        )
    
    def _split_record_note_and_return_first(self, rec_idx: int, rec_note: Note, rep_note: Note,
                                              record_heap: List,
                                              rec_duration: float, rep_duration: float) -> Optional[Tuple[Note, Note]]:
        """拆分录制数据（简化wrapper）"""
        return self._split_note_and_return_first(
            long_note=rec_note, long_idx=rec_idx, short_note=rep_note,
            target_heap=record_heap,
            rec_duration=rec_duration, rep_duration=rep_duration,
            data_type="录制", used_indices=None
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
            - short_note: 短数据（参考数据）
            - long_note: 长数据（要拆分的合并数据）
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
                    time_ms = (long_note.hammers.index[i] + long_note.offset) / 10.0
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
                           parent_idx: int, split_seq_a: int, split_seq_b: int) -> Tuple[Note, Note]:
        """
        在指定时间点拆分Note
        
        Args:
            note: 要拆分的Note对象
            split_time_ms: 拆分点的绝对时间（ms）
            parent_idx: 父索引（原始数据的索引）
            split_seq_a: 前半段的拆分序号
            split_seq_b: 后半段的拆分序号
        
        Returns:
            Tuple[Note, Note]: (前半段, 后半段)
        """
        import pandas as pd
        from dataclasses import replace
        
        # 将split_time_ms（绝对时间）转换为相对于offset的索引（0.1ms单位）
        # split_time_ms是绝对时间，after_touch.index是相对于offset的索引
        # 所以：relative_index = absolute_time * 10 - offset
        split_time_units = int(split_time_ms * 10) - note.offset
        
        logger.debug(f"        拆分参数: split_time={split_time_ms:.1f}ms (绝对时间), "
                    f"offset={note.offset}, split_units={split_time_units} (相对索引)")
        
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
        note_a = Note(
            offset=note.offset,
            id=note.id,
            finger=note.finger,
            hammers=hammers_a,
            uuid=f"{note.uuid}_split_{split_seq_a}",
            velocity=note.velocity,
            after_touch=after_touch_a,
            split_parent_idx=parent_idx,
            split_seq=split_seq_a,
            is_split=True
        )
        
        note_b = Note(
            offset=note.offset,  # offset保持不变
            id=note.id,
            finger=note.finger,
            hammers=hammers_b,
            uuid=f"{note.uuid}_split_{split_seq_b}",
            velocity=note.velocity,
            after_touch=after_touch_b,
            split_parent_idx=parent_idx,
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
        # 获取短数据的keyoff（绝对时间，0.1ms单位）
        short_keyoff_ms = short_note.key_off_ms
        if short_keyoff_ms is None:
            return False
        
        short_keyoff_units = int(short_keyoff_ms * 10)
        
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
    
    def _check_duration_difference(self, record_note: Note, replay_note: Note, record_idx: int, replay_idx: int, force_record: bool = False):
        """
        检查匹配对的持续时间差异，如果差异显著则记录

        Args:
            record_note: 录制音符
            replay_note: 播放音符
            record_idx: 录制音符原始索引
            replay_idx: 播放音符原始索引
            force_record: 是否强制记录（即使不满足主要条件）
        """
        # 获取持续时间
        record_duration = getattr(record_note, 'duration_ms', None)
        replay_duration = getattr(replay_note, 'duration_ms', None)

        # 检查是否有有效的持续时间数据
        if record_duration is None or replay_duration is None or record_duration <= 0 or replay_duration <= 0:
            return

        # 计算持续时间比例
        duration_ratio = max(record_duration, replay_duration) / min(record_duration, replay_duration)

        # 如果持续时间差异显著（大约2倍以上）或强制记录，记录下来
        if duration_ratio >= 2.0 or force_record:
            # 获取keyon和keyoff时间
            record_keyon = getattr(record_note, 'key_on_ms', None)
            record_keyoff = getattr(record_note, 'key_off_ms', None)
            replay_keyon = getattr(replay_note, 'key_on_ms', None)
            replay_keyoff = getattr(replay_note, 'key_off_ms', None)
            
            # 记录差异匹配对（包含keyon和keyoff）
            self.duration_diff_pairs.append((
                record_idx,
                replay_idx,
                record_note,
                replay_note,
                record_duration,
                replay_duration,
                duration_ratio,
                record_keyon,
                record_keyoff,
                replay_keyon,
                replay_keyoff
            ))

            # 输出日志
            logger.info(f"🔍 发现持续时间差异显著的匹配对: 按键{record_note.id} "
                       f"录制[{record_keyon:.1f}-{record_keyoff:.1f}ms, {record_duration:.1f}ms], "
                       f"播放[{replay_keyon:.1f}-{replay_keyoff:.1f}ms, {replay_duration:.1f}ms], "
                       f"比例={duration_ratio:.2f}")

    def _match_notes_for_single_key_group(self, key_id: int,
                                        record_notes_with_indices: List[Tuple[int, Note]],
                                        replay_notes_with_indices: List[Tuple[int, Note]]) -> Tuple[List[Tuple[int, int, Note, Note]], int]:
        """
        对单个按键组进行贪心匹配

        匹配策略：
        1. 精确匹配 (≤50ms)
        2. 较差匹配 (50ms-100ms)
        3. 严重误差匹配 (100ms-200ms) - 理论上应该匹配所有剩余按键

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
            ("approximate", "较差匹配", [MatchType.POOR]),
            ("severe", "严重误差匹配", [MatchType.SEVERE])
        ]

        # 获取待匹配的录制音符列表（未匹配的）
        unmatched_record_notes = [(idx, note) for idx, note in record_notes_with_indices]

        # 按等级顺序进行匹配
        for strategy_name, strategy_desc, allowed_types in match_strategies:
            if not unmatched_record_notes:
                break

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

                # 只有成功的匹配才记录到全局统计中
                # 失败的匹配会在所有策略尝试完后，由 _analyze_key_group_hammer_status 统一处理

                # 处理匹配结果
                if match_result.is_success and match_result.match_type in allowed_types:
                    # 更新全局统计信息（只记录成功的匹配）
                    self.match_statistics.add_result(match_result)
                    self.match_results.append(match_result)
                    # 从MatchResult中直接获取播放音符索引
                    matched_replay_orig_idx = match_result.replay_index
                    matched_replay_note = match_result.pair[1]

                    key_matched_pairs.append((
                        record_orig_idx,
                        matched_replay_orig_idx,
                        record_note,
                        matched_replay_note
                    ))

                    # 检查持续时间差异
                    self._check_duration_difference(record_note, matched_replay_note, record_orig_idx, matched_replay_orig_idx)

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
            ("approximate", self.approximate_matched_pairs), # 第二优先级: 较差搜索 (50ms-100ms)
            ("severe", self.severe_matched_pairs),          # 第三优先级: 严重误差搜索 (100ms-200ms)
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
            # 获取录制音符（从match_result.pair，支持拆分数据）
            if match_result.pair is None:
                # 失败匹配，从原始数据获取
                # 检查是否是拆分索引（>= 1000000）或无效索引
                if match_result.record_index >= 1000000 or \
                   match_result.record_index < 0 or \
                   match_result.record_index >= len(self._record_data):
                    continue  # 拆分索引或无效索引，跳过
                record_note = self._record_data[match_result.record_index]
            else:
                # 成功匹配，从pair获取（支持拆分）
                record_note = match_result.pair[0]
            
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
            # 较差搜索：当精确搜索失败时，寻找可接受的匹配 (50ms-100ms)
            # 避免与precision模式重叠，确保评级逻辑不受影响
            filtered = [c for c in candidates if FAIR_THRESHOLD < c.total_error <= POOR_THRESHOLD]
            if not filtered:
                return [], f"无较差候选(阈值:{FAIR_THRESHOLD/10:.1f}-{POOR_THRESHOLD/10:.1f}ms)"
        elif search_mode == "severe":
            # 严重误差搜索：只接受误差很大的匹配 (100ms-200ms)
            # 这些匹配会被评为SEVERE类型
            filtered = [c for c in candidates if POOR_THRESHOLD < c.total_error <= SEVERE_THRESHOLD]
            if not filtered:
                return [], f"无严重误差候选(阈值:{POOR_THRESHOLD/10:.1f}-{SEVERE_THRESHOLD/10:.1f}ms)"
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
        elif error_units <= SEVERE_THRESHOLD:
            return MatchType.SEVERE
        else:
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


    def _initialize_matching_state(self) -> None:
        """初始化匹配状态"""
        self.failure_reasons.clear()
        self._clear_mean_error_cache()
        self._split_counter = 0  # 重置全局拆分计数器

    def _perform_single_note_matching(self, record_note: Note, record_index: int,
                                     replay_data: List[Note], used_replay_indices: set) -> MatchResult:
        """
        执行单个音符的匹配过程

        按优先级顺序尝试不同类型的匹配：
        1. 精确匹配 (≤50ms)
        2. 较差匹配 (50ms-100ms)
        3. 严重误差匹配 (100ms-200ms)
        4. 失败 (>200ms)

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
            ("approximate", self.approximate_matched_pairs), # 第二优先级: 较差搜索 (50ms-100ms)
            ("severe", self.severe_matched_pairs),          # 第三优先级: 严重误差搜索 (100ms-200ms)
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
        获取较差匹配对的偏移数据 (50-100ms)

        Returns:
            List[Dict]: 较差匹配对的偏移数据
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
            logger.warning(f"总体方差为负数: {variance}，返回0")
            return 0.0
        std = variance ** 0.5
        logger.info(f"[后端] 总体标准差: {std/10:.2f}ms ({std:.1f}单位，基于精确匹配数据)")
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
            logger.info(f"[后端] 平均绝对误差 MAE: {mae/10:.2f}ms ({mae:.1f}单位，基于{len(abs_errors)}个精确匹配对)")
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
