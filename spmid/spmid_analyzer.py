#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SPMID数据分析器（重构版）

主协调器类，负责协调各个专门的分析组件：
- DataFilter: 数据过滤
- TimeAligner: 时序对齐
- NoteMatcher: 按键匹配
- ErrorDetector: 异常检测
"""

from matplotlib import figure
from .spmid_reader import Note
from .note_matcher import find_best_matching_notes
from .types import NoteInfo, Diffs, ErrorNote
from .motor_threshold_checker import MotorThresholdChecker
from .data_filter import DataFilter
from .time_aligner import TimeAligner
from .note_matcher import NoteMatcher
from .error_detector import ErrorDetector
from typing import List, Tuple, Optional, Dict, Any
from utils.logger import Logger

import pandas as pd
import matplotlib.pyplot as plt
import os
import numpy as np

logger = Logger.get_logger()


class SPMIDAnalyzer:
    """
    SPMID数据分析器类（重构版）
    
    主协调器，负责协调各个专门的分析组件完成完整的SPMID数据分析流程
    """
    
    def __init__(self):
        """初始化分析器"""
        # 初始化各个组件
        self.data_filter: Optional[DataFilter] = None
        self.time_aligner: Optional[TimeAligner] = None
        self.note_matcher: Optional[NoteMatcher] = None
        self.error_detector: Optional[ErrorDetector] = None
        
        # 分析结果
        self.multi_hammers: List[ErrorNote] = []
        self.drop_hammers: List[ErrorNote] = []
        self.silent_hammers: List[ErrorNote] = []
        self.valid_record_data: List[Note] = []
        self.valid_replay_data: List[Note] = []
        self.invalid_notes_table_data: Dict[str, Any] = {}
        self.matched_pairs: List[Tuple[int, int, Note, Note]] = []
        
        # 统计信息
        self.analysis_stats: Dict[str, Any] = {}
    
    def analyze(self, record_data: List[Note], replay_data: List[Note]) -> Tuple[List[ErrorNote], List[ErrorNote], List[ErrorNote], List[Note], List[Note], dict, List[Tuple[int, int, Note, Note]]]:
        """
        执行完整的SPMID数据分析
        
        分析流程：
        1. 初始化各个分析组件
        2. 过滤有效音符数据
        3. 计算全局时间偏移量（DTW）
        4. 执行按键匹配
        5. 分析异常（多锤、丢锤、不发声）
        6. 生成统计报告
        
        Args:
            record_data: 录制数据
            replay_data: 播放数据
        
        Returns:
            tuple: (multi_hammers, drop_hammers, silent_hammers, matched_record_data, matched_replay_data, invalid_notes_table_data, matched_pairs)
        """
        logger.info("🎯 开始SPMID数据分析")
        
        # 步骤1：初始化各个分析组件
        self._initialize_components()
        
        # 步骤2：过滤有效音符数据
        self.valid_record_data, self.valid_replay_data, invalid_counts = self.data_filter.filter_valid_notes_data(record_data, replay_data)
        
        # 步骤3：计算全局时间偏移量
        global_offset = self.time_aligner.calculate_global_time_offset(self.valid_record_data, self.valid_replay_data)
        logger.info(f"计算得到的全局时间偏移量: {global_offset}")
        
        # 步骤4：执行按键匹配
        self.note_matcher.update_global_time_offset(global_offset)
        self.matched_pairs = self.note_matcher.find_all_matched_pairs(self.valid_record_data, self.valid_replay_data)
        
        # 步骤5：分析异常
        self.error_detector.update_global_time_offset(global_offset)
        self.drop_hammers, self.multi_hammers = self.error_detector.analyze_hammer_issues(
            self.valid_record_data, self.valid_replay_data, self.matched_pairs
        )
        
        # 步骤6：提取正常匹配的音符对
        self.valid_record_data, self.valid_replay_data = self.note_matcher.extract_normal_matched_pairs(
            self.matched_pairs, self.multi_hammers, self.drop_hammers
        )
        
        # 步骤7：记录统计信息
        self._log_invalid_notes_statistics(record_data, replay_data, invalid_counts)
        
        # 步骤8：生成无效音符表格数据
        self.invalid_notes_table_data = self.data_filter.generate_invalid_notes_table_data(invalid_counts)
        
        # 步骤9：不发声的音符已被过滤掉，返回空列表
        self.silent_hammers = []
        
        # 步骤10：生成分析统计
        self._generate_analysis_stats()
        
        logger.info("✅ SPMID数据分析完成")
        
        return (self.multi_hammers, self.drop_hammers, self.silent_hammers, 
                self.valid_record_data, self.valid_replay_data, 
                self.invalid_notes_table_data, self.matched_pairs)
    
    def _initialize_components(self) -> None:
        """初始化各个分析组件"""
        # 初始化电机阈值检查器
        threshold_checker = self._initialize_threshold_checker()
        
        # 初始化各个组件
        self.data_filter = DataFilter(threshold_checker)
        self.time_aligner = TimeAligner()
        self.note_matcher = NoteMatcher()
        self.error_detector = ErrorDetector()
        
        logger.info("✅ 所有分析组件初始化完成")
    
    def _initialize_threshold_checker(self) -> MotorThresholdChecker:
        """初始化电机阈值检查器"""
        try:
            threshold_checker = MotorThresholdChecker(
                fit_equations_path="spmid/quadratic_fit_formulas.json",
                pwm_thresholds_path="spmid/inflection_pwm_values.json"
            )
            logger.info("✅ 电机阈值检查器初始化成功")
            return threshold_checker
        except Exception as e:
            logger.error(f"初始化电机阈值检查器失败: {e}")
            raise RuntimeError("电机阈值检查器初始化失败，无法进行SPMID数据分析")
    
    def _log_invalid_notes_statistics(self, record_data: List[Note], replay_data: List[Note], invalid_counts: Dict[str, Any]) -> None:
        """记录无效音符统计信息"""
        logger.info("📊 音符过滤统计:")
        logger.info(f"  录制数据: 总计 {len(record_data)} 个音符, 有效 {len(self.valid_record_data)} 个, 无效 {len(record_data) - len(self.valid_record_data)} 个")
        logger.info(f"  回放数据: 总计 {len(replay_data)} 个音符, 有效 {len(self.valid_replay_data)} 个, 无效 {len(replay_data) - len(self.valid_replay_data)} 个")
    
    def _generate_analysis_stats(self) -> None:
        """生成分析统计信息"""
        self.analysis_stats = {
            'total_record_notes': len(self.valid_record_data),
            'total_replay_notes': len(self.valid_replay_data),
            'matched_pairs': len(self.matched_pairs),
            'drop_hammers': len(self.drop_hammers),
            'multi_hammers': len(self.multi_hammers),
            'global_time_offset': self.time_aligner.get_global_time_offset() if self.time_aligner else 0.0
        }
    
    def get_analysis_stats(self) -> Dict[str, Any]:
        """获取分析统计信息"""
        return self.analysis_stats.copy()
    
    def get_matched_pairs(self) -> List[Tuple[int, int, Note, Note]]:
        """获取匹配对信息"""
        return self.matched_pairs.copy()
    
    def get_global_time_offset(self) -> float:
        """获取全局时间偏移量"""
        if self.time_aligner:
            return self.time_aligner.get_global_time_offset()
        return 0.0
    
    def get_data_filter(self) -> Optional[DataFilter]:
        """获取数据过滤器实例"""
        return self.data_filter
    
    def get_time_aligner(self) -> Optional[TimeAligner]:
        """获取时序对齐器实例"""
        return self.time_aligner
    
    def get_note_matcher(self) -> Optional[NoteMatcher]:
        """获取音符匹配器实例"""
        return self.note_matcher
    
    def get_error_detector(self) -> Optional[ErrorDetector]:
        """获取异常检测器实例"""
        return self.error_detector


# 为了保持向后兼容性，提供函数接口
def spmid_analysis(record_data: List[Note], replay_data: List[Note]) -> Tuple[List[ErrorNote], List[ErrorNote], List[ErrorNote], List[Note], List[Note], dict, List[Tuple[int, int, Note, Note]]]:
    """
    向后兼容的函数接口
    
    使用SPMIDAnalyzer类执行分析
    """
    analyzer = SPMIDAnalyzer()
    return analyzer.analyze(record_data, replay_data)


# 其他工具函数保持不变
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
