#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SPMID数据分析器

主协调器类，负责协调各个专门的分析组件：
- DataFilter: 数据过滤
- TimeAligner: 时序对齐
- NoteMatcher: 按键匹配
- ErrorDetector: 异常检测
"""

from matplotlib import figure
from .spmid_reader import Note
from .types import ErrorNote
from .data_filter import DataFilter
from .invalid_notes_statistics import InvalidNotesStatistics
from .note_matcher import NoteMatcher, MatchType
from .filter_collector import FilterCollector
from .filter_integrator import FilterIntegrator
from typing import List, Tuple, Optional, Dict, Any, Union, TYPE_CHECKING
from utils.logger import Logger

import pandas as pd
import matplotlib.pyplot as plt
import os
import numpy as np

logger = Logger.get_logger()


class SPMIDAnalyzer:
    """
    SPMID数据分析器类
    
    主协调器，负责协调各个专门的分析组件完成完整的SPMID数据分析流程
    """
    
    def __init__(self):
        """初始化分析器"""
        # 初始化各个组件
        self.data_filter: DataFilter()
        self.note_matcher: NoteMatcher()
        
        # 分析结果（现在直接从NoteMatcher获取）
        self.multi_hammers: List[ErrorNote] = []
        self.drop_hammers: List[ErrorNote] = []
        self.abnormal_matches: List[ErrorNote] = []  # 异常匹配对
        self.valid_record_data: List[Note] = []
        self.valid_replay_data: List[Note] = []
        self.invalid_statistics: InvalidNotesStatistics()  # 使用统计对象
        self.matched_pairs: List[Tuple[Note, Note, MatchType, float]] = []  # (record_note, replay_note, match_type, keyon_error_ms)
        
        # 统计信息
        self.analysis_stats: Dict[str, Any] = {}
    
    def analyze(
        self, 
        record_data: List[Note], 
        replay_data: List[Note],
        filter_collector: FilterCollector = None
    ) -> Tuple[List[ErrorNote], List[ErrorNote], List[ErrorNote], List[Note], List[Note], InvalidNotesStatistics, List[Tuple[int, int, Note, Note]]]:
        """
        执行完整的SPMID数据分析

        分析流程：
        1. 初始化各个分析组件
        2. 整合加载阶段的过滤信息（如果提供）
        3. 执行按键匹配（使用原始数据，不预先过滤）
        4. 分析异常（多锤、丢锤，使用原始数据和匹配结果）
        5. 数据过滤（用于分类统计技术性无效数据，如不发声）
        6. 提取正常匹配的音符对
        7. 生成统计报告
        
        注意：匹配和错误检测在过滤之前，确保多锤/丢锤的准确识别

        Args:
            record_data: 录制数据（已经过滤的有效数据）
            replay_data: 播放数据（已经过滤的有效数据）
            filter_collector: 可选的过滤信息收集器（包含在加载阶段被过滤的音符信息）

        Returns:
            tuple: (multi_hammers, drop_hammers, matched_record_data, matched_replay_data, invalid_statistics, matched_pairs)
        """
        import time
        total_start_time = time.time()
        logger.info("开始SPMID数据分析")

        # 步骤1：初始化各个分析组件
        self._initialize_components()
        
        # 步骤2：整合加载阶段的过滤信息
        if filter_collector is not None:
            self.invalid_statistics = FilterIntegrator.integrate_filter_data(
                filter_collector, record_data, replay_data
            )
            logger.debug(f"[DEBUG] 已整合加载阶段的过滤信息: {self.invalid_statistics}")
        else:
            # 如果没有提供过滤器，创建空的统计对象
            self.invalid_statistics = InvalidNotesStatistics()
            self.invalid_statistics.record_total = len(record_data)
            self.invalid_statistics.record_valid = len(record_data)
            self.invalid_statistics.replay_total = len(replay_data)
            self.invalid_statistics.replay_valid = len(replay_data)
        
        # 直接使用初次过滤后的数据（来自 SPMIDLoader）
        # initial_valid_xxx_data 用于一致性分析波形展示
        self.initial_valid_record_data = record_data
        self.initial_valid_replay_data = replay_data

        # 步骤3：执行按键匹配 (使用初次过滤后的数据)
        matching_start_time = time.time()
        
        # NoteMatcher现在在匹配过程中直接进行错误检测和分类
        self.note_matcher.find_all_matched_pairs(record_data, replay_data)
        # matched_pairs 已在匹配过程中被正确填充
        self.matched_pairs = self.note_matcher.matched_pairs

        matching_end_time = time.time()
        matching_duration = matching_end_time - matching_start_time
        
        # 保存匹配统计信息
        self.match_statistics = self.note_matcher.match_statistics
        
        # 步骤4：从NoteMatcher获取错误检测结果

        self.drop_hammers = self.note_matcher.drop_hammers
        self.multi_hammers = self.note_matcher.multi_hammers
        self.abnormal_matches = self.note_matcher.abnormal_matches
        
        logger.debug(f"[DEBUG]    ✅ 匹配与错误检测完成: 耗时{matching_duration:.3f}秒")
        logger.debug(f"[DEBUG]       - 精确匹配对: {len(self.matched_pairs)}个")
        logger.debug(f"[DEBUG]       - 丢锤: {len(self.drop_hammers)}个")
        logger.debug(f"[DEBUG]       - 多锤: {len(self.multi_hammers)}个")
        logger.debug(f"[DEBUG]       - 异常匹配对: {len(self.abnormal_matches)}个")

        
        # 步骤5：从精确匹配对中提取音符数据（用于后续分析）
        # matched_pairs 是 List[Tuple[Note, Note, MatchType, float]]，提取前两个元素即可
        if self.matched_pairs:
            self.valid_record_data = [rec_note for rec_note, _, _, _ in self.matched_pairs]
            self.valid_replay_data = [rep_note for _, rep_note, _, _ in self.matched_pairs]
        else:
            self.valid_record_data = []
            self.valid_replay_data = []

        # 步骤6：记录统计信息
        self._log_invalid_notes_statistics(record_data, replay_data)
        
        # 步骤8：生成分析统计
        self._generate_analysis_stats()

        # 计算总耗时并输出性能统计
        total_end_time = time.time()
        total_duration = total_end_time - total_start_time
        logger.info(f"🎉 SPMID数据分析完成: 总耗时{total_duration:.3f}秒")

        
        return (self.multi_hammers, self.drop_hammers,
                self.valid_record_data, self.valid_replay_data,
                self.invalid_statistics, self.matched_pairs)
    
    def _initialize_components(self):
        """初始化各个分析组件"""
        
        # 初始化各个组件
        self.data_filter = DataFilter()
        self.note_matcher = NoteMatcher()
        
        logger.debug("所有分析组件初始化完成")
    
    def _log_invalid_notes_statistics(self, record_data: List[Note], replay_data: List[Note]):
        """记录无效音符统计信息"""
        if self.invalid_statistics is None:
            logger.warning("无效音符统计对象未初始化，跳过统计日志")
            return
        
        summary = self.invalid_statistics.get_summary()
        logger.info("📊 音符过滤统计:")
        logger.info(
            f"  录制数据: 总计 {len(record_data)} 个音符, "
            f"有效 {summary['record']['valid']} 个, "
            f"无效 {summary['record']['invalid']} 个"
        )
        logger.info(
            f"  回放数据: 总计 {len(replay_data)} 个音符, "
            f"有效 {summary['replay']['valid']} 个, "
            f"无效 {summary['replay']['invalid']} 个"
        )
    
    def _generate_analysis_stats(self):
        """生成分析统计信息"""
        # 获取无效音符数
        record_invalid = self.invalid_statistics.record_invalid_count if self.invalid_statistics else 0
        replay_invalid = self.invalid_statistics.replay_invalid_count if self.invalid_statistics else 0
        
        # 使用初始有效数据的长度，而不是匹配后的数据长度
        # initial_valid_xxx_data 包含所有通过过滤的有效音符（1-88号按键）
        total_record_valid = len(self.initial_valid_record_data) if self.initial_valid_record_data else 0
        total_replay_valid = len(self.initial_valid_replay_data) if self.initial_valid_replay_data else 0
        
        self.analysis_stats = {
            'total_record_notes': total_record_valid,  # 录制有效音符总数（不仅仅是匹配的）
            'total_replay_notes': total_replay_valid,  # 播放有效音符总数（不仅仅是匹配的）
            'matched_pairs': len(self.matched_pairs),
            'drop_hammers': len(self.drop_hammers),
            'multi_hammers': len(self.multi_hammers),
            'record_invalid_notes': record_invalid,
            'replay_invalid_notes': replay_invalid,
        }
    
    def get_analysis_stats(self) -> Dict[str, Any]:
        """获取分析统计信息"""
        return self.analysis_stats.copy()
    
    def get_matched_pairs(self) -> List[Tuple[Note, Note]]:
        """获取匹配对信息 (仅返回 Record Note 和 Replay Note)"""
        if self.note_matcher:
            return self.note_matcher.get_matched_pairs()
        return []
    
    
    def get_data_filter(self) -> Optional[DataFilter]:
        """获取数据过滤器实例"""
        return self.data_filter

    
    def get_note_matcher(self) -> Optional[NoteMatcher]:
        """获取音符匹配器实例"""
        return self.note_matcher
    
    
    def get_valid_record_data(self) -> Optional[List[Note]]:
        """
        获取有效录制数据
        
        Returns:
            Optional[List[Note]]: 有效录制数据列表
        """
        return self.valid_record_data
    
    def get_valid_replay_data(self) -> Optional[List[Note]]:
        """
        获取有效播放数据
        
        Returns:
            Optional[List[Note]]: 有效播放数据列表
        """
        return self.valid_replay_data
    
    def get_initial_valid_record_data(self) -> Optional[List[Note]]:
        """
        获取初始有效录制数据（第一次过滤后）
        
        Returns:
            Optional[List[Note]]: 初始有效录制数据列表
        """
        return getattr(self, 'initial_valid_record_data', None)
    
    def get_initial_valid_replay_data(self) -> Optional[List[Note]]:
        """
        获取初始有效播放数据（第一次过滤后）
        
        Returns:
            Optional[List[Note]]: 初始有效播放数据列表
        """
        return getattr(self, 'initial_valid_replay_data', None)
    
    def get_offset_alignment_data(self) -> List[Dict[str, Union[int, float]]]:
        """
        获取偏移对齐数据

        Returns:
            List[Dict[str, Any]]: 偏移对齐数据列表
        """
        if self.note_matcher:
            return self.note_matcher.get_offset_alignment_data()
        return []

    def get_precision_offset_alignment_data(self) -> List[Dict[str, Union[int, float]]]:
        """
        获取精确匹配的偏移对齐数据（误差 ≤ 50ms）

        Returns:
            List[Dict[str, Any]]: 精确匹配的偏移对齐数据列表
        """
        if self.note_matcher:
            return self.note_matcher.get_precision_offset_alignment_data()
        return []
    
    def get_grouped_precision_match_data(self) -> Dict[int, List[float]]:
        """
        获取按按键ID分组的精确匹配延时数据（误差 ≤ 50ms）

        Returns:
            Dict[int, List[float]]: key_id -> [keyon_offset_ms, ...]
        """
        if self.note_matcher:
            return self.note_matcher.get_grouped_precision_match_data()
        return {}
    
    def get_key_statistics_table_data(self) -> List[Dict[str, Union[int, float, str]]]:
        """
        获取按键统计表格数据
        
        Returns:
            List[Dict[str, Any]]: 按键统计数据列表，每行包含一个按键的统计信息
        """
        if self.note_matcher:
            return self.note_matcher.get_key_statistics_for_bar_chart()
        return []
    
    def get_invalid_notes_offset_analysis(self) -> List[Dict[str, Any]]:
        """
        获取无效音符的偏移对齐分析
        
        Returns:
            List[Dict[str, Any]]: 无效音符偏移分析数据
        """
        if self.note_matcher and self.valid_record_data and self.valid_replay_data:
            return self.note_matcher.get_invalid_notes_offset_analysis(
                self.valid_record_data, self.valid_replay_data
            )
        return []
    
    def get_global_average_delay(self) -> float:
        """
        获取整首曲子的平均时延（基于已配对数据）
        
        Returns:
            float: 平均时延（0.1ms单位）
        """
        if self.note_matcher:
            return self.note_matcher.get_global_average_delay()
        return 0.0
    
    def get_variance(self) -> float:
        """
        获取已配对按键的总体方差
        
        Returns:
            float: 总体方差（(0.1ms)²单位）
        """
        if self.note_matcher:
            return self.note_matcher.get_variance()
        return 0.0
    
    def get_standard_deviation(self) -> float:
        """
        获取已配对按键的总体标准差
        
        Returns:
            float: 总体标准差（0.1ms单位）
        """
        if self.note_matcher:
            return self.note_matcher.get_standard_deviation()
        return 0.0
    
    def get_mean_absolute_error(self) -> float:
        """
        获取已配对按键的平均绝对误差（MAE）
        
        Returns:
            float: 平均绝对误差（0.1ms单位）
        """
        if self.note_matcher:
            return self.note_matcher.get_mean_absolute_error()
        return 0.0
    
    def get_mean_squared_error(self) -> float:
        """
        获取已配对按键的均方误差（MSE）
        
        Returns:
            float: 均方误差（(0.1ms)²单位）
        """
        if self.note_matcher:
            return self.note_matcher.get_mean_squared_error()
        return 0.0

    def get_root_mean_squared_error(self) -> float:
        """
        获取已配对按键的均方根误差（RMSE）
        
        Returns:
            float: 均方根误差（0.1ms单位）
        """
        if self.note_matcher:
            return self.note_matcher.get_root_mean_squared_error()
        return 0.0
    
    def get_mean_error(self) -> float:
        """
        获取已匹配按键对的平均误差（ME）
        
        Returns:
            float: 平均误差ME（0.1ms单位）
        """
        if self.note_matcher:
            return self.note_matcher.get_mean_error()
        return 0.0
    
    def get_coefficient_of_variation(self) -> float:
        """
        获取已配对按键的变异系数（Coefficient of Variation, CV）
        
        Returns:
            float: 变异系数（百分比，例如 15.5 表示 15.5%）
        """
        if self.note_matcher:
            return self.note_matcher.get_coefficient_of_variation()
        return 0.0

    
    def get_offset_statistics(self) -> Dict[str, Any]:
        """
        获取偏移统计信息
        
        Returns:
            Dict[str, Any]: 偏移统计信息
        """
        if self.note_matcher:
            return self.note_matcher.get_offset_statistics()



def get_figure_by_index(record_data: List[Note], replay_data: List[Note], record_index: int, replay_index: int) -> figure:
    """按索引获取对比图"""
    # 确保index是有效的非负索引
    if record_index < 0 or record_index >= len(record_data):
        raise IndexError(f"record_index {record_index} 超出范围 [0, {len(record_data)-1}]")
    if replay_index < 0 or replay_index >= len(replay_data):
        raise IndexError(f"replay_index {replay_index} 超出范围 [0, {len(replay_data)-1}]")
    
    record_note = record_data[record_index]
    replay_note = replay_data[replay_index]
    record_note.after_touch.plot(label='record after_touch', color='blue')
    plt.scatter(x=record_note.hammers.index, y=record_note.hammers.values, color='blue', label='record hammers')
    replay_note.after_touch.plot(label='play after_touch', color='red')
    plt.scatter(x=replay_note.hammers.index, y=replay_note.hammers.values, color='red', label='play hammers')
    plt.xlabel('Time (100us)') 
    plt.legend()
    return plt.gcf()
