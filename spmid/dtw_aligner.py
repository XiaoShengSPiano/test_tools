#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DTW时间对齐器

基于已匹配的按键对，使用DTW算法进行全局时间对齐。
用于识别整首曲子的固定延迟和时间扭曲。
"""

from typing import List, Dict, Any, Tuple, Optional
import numpy as np
from dtw import dtw
from utils.logger import Logger

logger = Logger.get_logger()


class DTWAligner:
    """
    DTW时间对齐器类
    
    基于已匹配的按键对，使用DTW算法进行时间对齐。
    主要用于识别固定延迟和时间扭曲。
    """
    
    def __init__(self, window_size: Optional[int] = None, step_pattern: str = "symmetric2"):
        """
        初始化DTW对齐器
        
        Args:
            window_size: DTW窗口大小，None表示无限制。用于限制对齐范围，避免过度扭曲
            step_pattern: DTW步进模式，默认为"symmetric2"（对称模式）
        """
        self.window_size = window_size
        self.step_pattern = step_pattern
        self.alignment_result: Optional[Dict[str, Any]] = None
        
    def align(self, offset_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        基于已匹配的按键对进行DTW时间对齐
        
        Args:
            offset_data: 偏移对齐数据列表，来自 note_matcher.get_offset_alignment_data()
                每个元素包含：
                - record_keyon: 录制按键按下时间（0.1ms单位）
                - replay_keyon: 播放按键按下时间（0.1ms单位）
                - record_index: 录制索引
                - replay_index: 播放索引
                - key_id: 按键ID
                等其他字段
        
        Returns:
            Dict[str, Any]: DTW对齐结果，包含：
                - alignment_path: DTW对齐路径 [(i, j), ...]
                - record_times: 录制时间序列（ms单位）
                - replay_times: 播放时间序列（ms单位）
                - aligned_record_times: 对齐后的录制时间序列（ms单位）
                - aligned_replay_times: 对齐后的播放时间序列（ms单位）
                - dtw_distance: DTW距离
                - time_mapping: 时间映射函数（录制时间 -> 播放时间）
                - fixed_delay: 固定延迟估计（ms）
                - time_warping: 时间扭曲系数
        """
        if not offset_data:
            logger.warning("⚠️ 偏移对齐数据为空，无法进行DTW对齐")
            return self._create_empty_result()
        
        try:
            # 提取时间序列
            record_times, replay_times = self._extract_time_sequences(offset_data)
            
            if len(record_times) < 2 or len(replay_times) < 2:
                logger.warning("⚠️ 时间序列数据点不足，无法进行DTW对齐")
                return self._create_empty_result()
            
            # 执行DTW对齐
            alignment_result = self._perform_dtw_alignment(record_times, replay_times)
            
            # 计算时间映射
            time_mapping = self._calculate_time_mapping(
                record_times, replay_times, alignment_result['alignment_path']
            )
            
            # 计算固定延迟和时间扭曲
            fixed_delay, time_warping = self._analyze_delay_and_warping(
                record_times, replay_times, alignment_result['alignment_path']
            )
            
            # 构建完整结果
            self.alignment_result = {
                'alignment_path': alignment_result['alignment_path'],
                'record_times': record_times,
                'replay_times': replay_times,
                'aligned_record_times': alignment_result['aligned_record_times'],
                'aligned_replay_times': alignment_result['aligned_replay_times'],
                'dtw_distance': alignment_result['dtw_distance'],
                'time_mapping': time_mapping,
                'fixed_delay': fixed_delay,
                'time_warping': time_warping,
                'num_points': len(record_times),
                'offset_data': offset_data  # 保留原始数据引用
            }
            
            logger.info(f"✅ DTW对齐完成: {len(record_times)}个匹配点, DTW距离={alignment_result['dtw_distance']:.2f}, "
                       f"固定延迟={fixed_delay:.2f}ms, 时间扭曲={time_warping:.4f}")
            
            return self.alignment_result
            
        except Exception as e:
            logger.error(f"❌ DTW对齐失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._create_empty_result()
    
    def _extract_time_sequences(self, offset_data: List[Dict[str, Any]]) -> Tuple[List[float], List[float]]:
        """
        从偏移对齐数据中提取时间序列
        
        Args:
            offset_data: 偏移对齐数据列表
        
        Returns:
            Tuple[List[float], List[float]]: (录制时间序列, 播放时间序列)，单位：ms
        """
        # 按录制时间排序，确保时间顺序
        sorted_data = sorted(offset_data, key=lambda x: x.get('record_keyon', 0))
        
        record_times = []
        replay_times = []
        
        for item in sorted_data:
            record_keyon = item.get('record_keyon')
            replay_keyon = item.get('replay_keyon')
            
            if record_keyon is not None and replay_keyon is not None:
                # 转换为ms单位
                record_times.append(record_keyon / 10.0)
                replay_times.append(replay_keyon / 10.0)
        
        return record_times, replay_times
    
    def _perform_dtw_alignment(
        self, 
        record_times: List[float], 
        replay_times: List[float]
    ) -> Dict[str, Any]:
        """
        执行DTW对齐
        
        Args:
            record_times: 录制时间序列（ms单位）
            replay_times: 播放时间序列（ms单位）
        
        Returns:
            Dict[str, Any]: DTW对齐结果
        """
        # 转换为numpy数组并重塑为列向量（DTW库要求）
        record_array = np.array(record_times).reshape(-1, 1)
        replay_array = np.array(replay_times).reshape(-1, 1)
        
        # 配置DTW参数
        dtw_kwargs = {
            'keep_internals': True,
            'step_pattern': self.step_pattern
        }
        
        # 如果设置了窗口大小，添加窗口约束
        if self.window_size is not None:
            dtw_kwargs['window_type'] = 'sakoechiba'
            dtw_kwargs['window_size'] = self.window_size
        
        # 执行DTW对齐
        alignment = dtw(record_array, replay_array, **dtw_kwargs)
        
        # 提取对齐路径
        alignment_path = list(zip(alignment.index1, alignment.index2))
        
        # 计算对齐后的时间序列
        aligned_record_times = [record_times[i] for i in alignment.index1]
        aligned_replay_times = [replay_times[j] for j in alignment.index2]
        
        return {
            'alignment_path': alignment_path,
            'aligned_record_times': aligned_record_times,
            'aligned_replay_times': aligned_replay_times,
            'dtw_distance': alignment.distance
        }
    
    def _calculate_time_mapping(
        self,
        record_times: List[float],
        replay_times: List[float],
        alignment_path: List[Tuple[int, int]]
    ) -> List[Tuple[float, float]]:
        """
        计算时间映射函数（录制时间 -> 播放时间）
        
        Args:
            record_times: 录制时间序列（ms单位）
            replay_times: 播放时间序列（ms单位）
            alignment_path: DTW对齐路径
        
        Returns:
            List[Tuple[float, float]]: 时间映射点列表 [(record_time, replay_time), ...]
        """
        time_mapping = []
        for i, j in alignment_path:
            if i < len(record_times) and j < len(replay_times):
                time_mapping.append((record_times[i], replay_times[j]))
        
        return time_mapping
    
    def _analyze_delay_and_warping(
        self,
        record_times: List[float],
        replay_times: List[float],
        alignment_path: List[Tuple[int, int]]
    ) -> Tuple[float, float]:
        """
        分析固定延迟和时间扭曲
        
        Args:
            record_times: 录制时间序列（ms单位）
            replay_times: 播放时间序列（ms单位）
            alignment_path: DTW对齐路径
        
        Returns:
            Tuple[float, float]: (固定延迟, 时间扭曲系数)
                固定延迟：ms单位，表示系统固有延迟
                时间扭曲系数：无单位，1.0表示无扭曲，>1.0表示加速，<1.0表示减速
        """
        if not alignment_path:
            return 0.0, 1.0
        
        # 计算对齐后的延迟
        delays = []
        for i, j in alignment_path:
            if i < len(record_times) and j < len(replay_times):
                delay = replay_times[j] - record_times[i]
                delays.append(delay)
        
        if not delays:
            return 0.0, 1.0
        
        # 固定延迟：使用中位数（更鲁棒）
        fixed_delay = float(np.median(delays))
        
        # 时间扭曲：使用线性回归计算斜率
        # 如果时间扭曲系数接近1.0，表示无扭曲
        record_aligned = [record_times[i] for i, _ in alignment_path if i < len(record_times)]
        replay_aligned = [replay_times[j] for _, j in alignment_path if j < len(replay_times)]
        
        if len(record_aligned) < 2 or len(replay_aligned) < 2:
            time_warping = 1.0
        else:
            # 线性回归：replay_time = a * record_time + b
            # 时间扭曲系数 = a
            record_array = np.array(record_aligned)
            replay_array = np.array(replay_aligned)
            
            # 使用最小二乘法计算斜率
            # 为了避免固定延迟的影响，先减去均值
            record_mean = np.mean(record_array)
            replay_mean = np.mean(replay_array)
            
            record_centered = record_array - record_mean
            replay_centered = replay_array - replay_mean
            
            # 计算斜率
            if np.sum(record_centered ** 2) > 1e-10:
                slope = np.sum(record_centered * replay_centered) / np.sum(record_centered ** 2)
                time_warping = float(slope)
            else:
                time_warping = 1.0
        
        return fixed_delay, time_warping
    
    def _create_empty_result(self) -> Dict[str, Any]:
        """创建空的对齐结果"""
        return {
            'alignment_path': [],
            'record_times': [],
            'replay_times': [],
            'aligned_record_times': [],
            'aligned_replay_times': [],
            'dtw_distance': 0.0,
            'time_mapping': [],
            'fixed_delay': 0.0,
            'time_warping': 1.0,
            'num_points': 0,
            'offset_data': []
        }
    
    def get_alignment_result(self) -> Optional[Dict[str, Any]]:
        """
        获取对齐结果
        
        Returns:
            Optional[Dict[str, Any]]: 对齐结果，如果未执行对齐则返回None
        """
        return self.alignment_result
    
    def get_fixed_delay(self) -> float:
        """
        获取固定延迟估计
        
        Returns:
            float: 固定延迟（ms），如果未执行对齐则返回0.0
        """
        if self.alignment_result:
            return self.alignment_result.get('fixed_delay', 0.0)
        return 0.0
    
    def get_time_warping(self) -> float:
        """
        获取时间扭曲系数
        
        Returns:
            float: 时间扭曲系数，如果未执行对齐则返回1.0
        """
        if self.alignment_result:
            return self.alignment_result.get('time_warping', 1.0)
        return 1.0
    
    def get_dtw_distance(self) -> float:
        """
        获取DTW距离
        
        Returns:
            float: DTW距离，如果未执行对齐则返回0.0
        """
        if self.alignment_result:
            return self.alignment_result.get('dtw_distance', 0.0)
        return 0.0

