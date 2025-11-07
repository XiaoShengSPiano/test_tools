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
from .types import NoteInfo, Diffs, ErrorNote
from .motor_threshold_checker import MotorThresholdChecker
from .data_filter import DataFilter
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
    SPMID数据分析器类
    
    主协调器，负责协调各个专门的分析组件完成完整的SPMID数据分析流程
    """
    
    def __init__(self):
        """初始化分析器"""
        # 初始化各个组件
        self.data_filter: Optional[DataFilter] = None
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
        
        # 保存第一次过滤后的数据用于准确率计算
        self.initial_valid_record_data = self.valid_record_data.copy()
        self.initial_valid_replay_data = self.valid_replay_data.copy()
        
        # 步骤3：执行按键匹配
        self.matched_pairs = self.note_matcher.find_all_matched_pairs(self.valid_record_data, self.valid_replay_data)
        
        # 步骤4：分析异常
        self.drop_hammers, self.multi_hammers = self.error_detector.analyze_hammer_issues(
            self.valid_record_data, self.valid_replay_data, self.matched_pairs
        )
        
        # 步骤6：提取正常匹配的音符对
        matched_record_data, matched_replay_data = self.note_matcher.extract_normal_matched_pairs(
            self.matched_pairs, self.multi_hammers, self.drop_hammers
        )
        
        # 保存匹配后的数据，但不覆盖初始数据
        self.valid_record_data = matched_record_data
        self.valid_replay_data = matched_replay_data
        
        # 步骤7：记录统计信息
        self._log_invalid_notes_statistics(record_data, replay_data, invalid_counts)
        
        # 步骤8：生成无效音符表格数据
        self.invalid_notes_table_data = self.data_filter.generate_invalid_notes_table_data(invalid_counts)
        
        # 步骤9：从无效音符统计中提取不发声音符详细信息
        self.silent_hammers = self._extract_silent_hammers_from_invalid_counts(invalid_counts)
        
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
        # self.time_aligner = TimeAligner()  # 已删除时序对齐功能
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
    
    def _extract_silent_hammers_from_invalid_counts(self, invalid_counts: Dict[str, Any]) -> List[ErrorNote]:
        """
        从无效音符统计中提取不发声音符的详细信息
        
        Args:
            invalid_counts: 无效音符统计信息
            
        Returns:
            List[ErrorNote]: 不发声音符的ErrorNote列表
        """
        from .types import NoteInfo
        
        silent_hammers = []
        
        # 获取录制和播放数据中的不发声音符详细信息
        record_silent_details = invalid_counts.get('record_data', {}).get('silent_notes_details', [])
        replay_silent_details = invalid_counts.get('replay_data', {}).get('silent_notes_details', [])
        
        # 合并处理所有不发声音符
        for item in record_silent_details + replay_silent_details:
            note = item['note']
            index = item['index']
            
            # 计算时间信息
            keyon_time = note.after_touch.index[0] + note.offset if len(note.after_touch) > 0 else 0
            keyoff_time = note.after_touch.index[-1] + note.offset if len(note.after_touch) > 0 else 0
            
            error_note = ErrorNote(
                infos=[NoteInfo(
                    index=index,
                    keyId=note.id,
                    keyOn=keyon_time,
                    keyOff=keyoff_time
                )],
                diffs=[],
                error_type="不发声",
                global_index=index
            )
            silent_hammers.append(error_note)
        
        logger.info(f"✅ 提取不发声音符: 录制{len(record_silent_details)}个, 播放{len(replay_silent_details)}个, 总计{len(silent_hammers)}个")
        
        return silent_hammers
    
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
            'global_time_offset': 0.0  # 已删除时序对齐功能，固定为0
        }
    
    def get_analysis_stats(self) -> Dict[str, Any]:
        """获取分析统计信息"""
        return self.analysis_stats.copy()
    
    def get_matched_pairs(self) -> List[Tuple[int, int, Note, Note]]:
        """获取匹配对信息"""
        return self.matched_pairs.copy()
    
    # def get_global_time_offset(self) -> float:
    #     """获取全局时间偏移量（已删除时序对齐功能，固定返回0）"""
    #     return 0.0
    
    def get_data_filter(self) -> Optional[DataFilter]:
        """获取数据过滤器实例"""
        return self.data_filter
    
    # def get_time_aligner(self) -> Optional[TimeAligner]:
    #     """获取时序对齐器实例"""
    #     return self.time_aligner
    
    def get_note_matcher(self) -> Optional[NoteMatcher]:
        """获取音符匹配器实例"""
        return self.note_matcher
    
    def get_error_detector(self) -> Optional[ErrorDetector]:
        """获取异常检测器实例"""
        return self.error_detector
    
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
    
    def get_offset_alignment_data(self) -> List[Dict[str, Any]]:
        """
        获取偏移对齐数据
        
        Returns:
            List[Dict[str, Any]]: 偏移对齐数据列表
        """
        if self.note_matcher:
            return self.note_matcher.get_offset_alignment_data()
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

    def get_mean_error(self) -> float:
        """
        获取已匹配按键对的平均误差（ME）
        
        Returns:
            float: 平均误差ME（0.1ms单位）
        """
        if self.note_matcher:
            return self.note_matcher.get_mean_error()
        return 0.0
    

    
    def get_offset_statistics(self) -> Dict[str, Any]:
        """
        获取偏移统计信息
        
        Returns:
            Dict[str, Any]: 偏移统计信息
        """
        if self.note_matcher:
            return self.note_matcher.get_offset_statistics()
            return {
                'total_pairs': 0,
                'keyon_offset_stats': {'average': 0.0, 'max': 0.0, 'min': 0.0, 'std': 0.0},
                'duration_offset_stats': {'average': 0.0, 'max': 0.0, 'min': 0.0, 'std': 0.0},
                'overall_offset_stats': {'average': 0.0, 'max': 0.0, 'min': 0.0, 'std': 0.0}
            }


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
