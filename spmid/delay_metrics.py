#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
延时误差统计指标计算模块

负责计算各种延时误差统计指标，所有计算基于匹配对的原始 keyon_offset。
不再使用已废弃的 global_time_offset 概念。
"""

from typing import List, Dict
from utils.logger import Logger
import math

logger = Logger.get_logger()


class DelayMetrics:
    """延时误差统计指标计算器"""
    
    def __init__(self, precision_matched_pairs: List[tuple]):
        """
        初始化延时指标计算器
        
        Args:
            precision_matched_pairs: 精确匹配对列表 [(record_idx, replay_idx, record_note, replay_note), ...]
        """
        self.precision_matched_pairs = precision_matched_pairs
        self._offsets_cache = None
    
    def _calculate_note_times(self, note) -> tuple:
        """
        获取音符的keyon和keyoff时间
        
        Args:
            note: Note对象
            
        Returns:
            tuple: (keyon_time, keyoff_time) 单位：0.1ms
        """
        # 直接使用Note对象的预计算属性（已经是ms），转换为0.1ms单位
        keyon = note.key_on_ms * 10.0 if note.key_on_ms is not None else note.offset
        keyoff = note.key_off_ms * 10.0 if note.key_off_ms is not None else note.offset
        return keyon, keyoff
    
    def _get_keyon_offsets(self) -> List[float]:
        """
        获取所有精确匹配对的 keyon_offset（原始值，不校准）
        
        Returns:
            List[float]: keyon_offset 列表（单位：0.1ms）
        """
        if self._offsets_cache is not None:
            return self._offsets_cache
        
        offsets = []
        for record_idx, replay_idx, record_note, replay_note in self.precision_matched_pairs:
            record_keyon, _ = self._calculate_note_times(record_note)
            replay_keyon, _ = self._calculate_note_times(replay_note)
            
            # 原始偏移：replay_keyon - record_keyon
            keyon_offset = replay_keyon - record_keyon
            offsets.append(keyon_offset)
        
        self._offsets_cache = offsets
        return offsets
    
    def get_mean_error(self) -> float:
        """
        计算平均误差（ME，带符号）
        
        ME = mean(keyon_offset)
        正值表示播放延迟，负值表示播放提前
        
        Returns:
            float: 平均误差（单位：0.1ms）
        """
        offsets = self._get_keyon_offsets()
        if not offsets:
            return 0.0
        
        me = sum(offsets) / len(offsets)
        logger.debug(f"📊 平均误差 ME: {me/10:.2f}ms (基于{len(offsets)}个精确匹配对)")
        return me
    
    def get_mean_absolute_error(self) -> float:
        """
        计算平均绝对误差（MAE）
        
        MAE = mean(|keyon_offset|)
        反映平均延时幅度，不考虑方向
        
        Returns:
            float: 平均绝对误差（单位：0.1ms）
        """
        offsets = self._get_keyon_offsets()
        if not offsets:
            return 0.0
        
        mae = sum(abs(offset) for offset in offsets) / len(offsets)
        logger.info(f"📊 平均绝对误差 MAE: {mae/10:.2f}ms (基于{len(offsets)}个精确匹配对)")
        return mae
    
    def get_standard_deviation(self) -> float:
        """
        计算总体标准差（Population Standard Deviation）
        
        使用带符号的 keyon_offset 计算，反映延时的波动程度
        σ = sqrt(mean((x_i - μ)²))
        
        Returns:
            float: 总体标准差（单位：0.1ms）
        """
        offsets = self._get_keyon_offsets()
        if len(offsets) <= 1:
            return 0.0
        
        # 计算均值
        mean = sum(offsets) / len(offsets)
        
        # 计算方差
        variance = sum((offset - mean) ** 2 for offset in offsets) / len(offsets)
        
        # 计算标准差
        std = math.sqrt(variance)
        logger.info(f"📊 总体标准差: {std/10:.2f}ms (基于{len(offsets)}个精确匹配对)")
        return std
    
    def get_root_mean_squared_error(self) -> float:
        """
        计算均方根误差（RMSE）
        
        RMSE = sqrt(mean(keyon_offset²))
        反映延时的整体误差水平
        
        Returns:
            float: 均方根误差（单位：0.1ms）
        """
        offsets = self._get_keyon_offsets()
        if not offsets:
            return 0.0
        
        # 计算均方误差
        mse = sum(offset ** 2 for offset in offsets) / len(offsets)
        
        # 计算均方根误差
        rmse = math.sqrt(mse)
        logger.info(f"📊 均方根误差 RMSE: {rmse/10:.2f}ms (基于{len(offsets)}个精确匹配对)")
        return rmse
    
    def get_coefficient_of_variation(self) -> float:
        """
        计算变异系数（CV）
        
        CV = (σ / |μ|) × 100%
        反映延时的相对波动程度
        
        Returns:
            float: 变异系数（百分比，例如 15.5 表示 15.5%）
        """
        offsets = self._get_keyon_offsets()
        if not offsets:
            return 0.0
        
        # 计算均值和标准差
        mean = sum(offsets) / len(offsets)
        if abs(mean) < 1e-6:  # 均值接近0，无法计算CV
            logger.warning("平均误差接近0，无法计算变异系数")
            return 0.0
        
        std = self.get_standard_deviation()
        if std == 0:
            return 0.0
        
        # 计算变异系数
        cv = (std / abs(mean)) * 100.0
        logger.info(f"📊 变异系数 CV: {cv:.2f}% (基于{len(offsets)}个精确匹配对)")
        return cv
    
    def get_variance(self) -> float:
        """
        计算方差

        Returns:
            float: 方差（单位：0.1ms²）
        """
        offsets = self._get_keyon_offsets()
        if len(offsets) < 2:
            return 0.0

        mean = sum(offsets) / len(offsets)
        variance = sum((x - mean) ** 2 for x in offsets) / len(offsets)
        logger.info(f"📊 方差: {variance/100:.2f}ms² (基于{len(offsets)}个精确匹配对)")
        return variance

    def get_max_error(self) -> float:
        """
        计算最大偏差

        Returns:
            float: 最大偏差（单位：0.1ms）
        """
        offsets = self._get_keyon_offsets()
        if not offsets:
            return 0.0

        max_error = max(offsets)
        logger.info(f"📊 最大偏差: {max_error/10:.2f}ms (基于{len(offsets)}个精确匹配对)")
        return max_error

    def get_min_error(self) -> float:
        """
        计算最小偏差

        Returns:
            float: 最小偏差（单位：0.1ms）
        """
        offsets = self._get_keyon_offsets()
        if not offsets:
            return 0.0

        min_error = min(offsets)
        logger.info(f"📊 最小偏差: {min_error/10:.2f}ms (基于{len(offsets)}个精确匹配对)")
        return min_error

    def get_all_metrics(self) -> Dict[str, float]:
        """
        一次性获取所有延时统计指标

        Returns:
            dict: 包含所有延时指标的字典
        """
        return {
            'mean_error': self.get_mean_error(),  # 平均延时
            'mae': self.get_mean_absolute_error(),  # 平均绝对误差
            'std_deviation': self.get_standard_deviation(),  # 标准差
            'variance': self.get_variance(),  # 方差
            'rmse': self.get_root_mean_squared_error(),  # 均方根误差
            'cv': self.get_coefficient_of_variation(),  # 变异系数
            'max_error': self.get_max_error(),  # 最大偏差
            'min_error': self.get_min_error(),  # 最小偏差
            'sample_count': len(self._get_keyon_offsets())  # 样本数量
        }
