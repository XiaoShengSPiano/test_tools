#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
相对延时分析服务模块

负责分析同种算法不同曲子的相对延时分布
"""

import traceback
from typing import List, Dict, Any, Tuple
from collections import defaultdict
from utils.logger import Logger

logger = Logger.get_logger()


class RelativeDelayAnalyzer:
    """
    相对延时分析器 - 负责分析相对延时分布
    
    职责：
    1. 分析同种算法不同曲子的相对延时分布
    2. 根据相对延时范围筛选数据点
    3. 计算相对延时数据
    """
    
    def __init__(self, backend):
        """
        初始化相对延时分析器
        
        Args:
            backend: PianoAnalysisBackend实例（用于访问算法管理器）
        """
        self.backend = backend
    
    def analyze_same_algorithm_relative_delays(self) -> Dict[str, Any]:
        """
        分析同种算法不同曲子的相对延时分布
        
        识别逻辑：
        - display_name 相同：表示同种算法
        - algorithm_name 不同：表示不同曲子（因为文件名不同）
        
        Returns:
            Dict[str, Any]: 分析结果，包含：
                - status: 状态标识 ('success' 或 'error')
                - algorithm_groups: 按算法分组的相对延时数据
                - message: 错误信息（仅当status为'error'时）
        """
        try:
            if not self.backend.multi_algorithm_manager:
                return {
                    'status': 'error',
                    'message': '多算法管理器不存在'
                }
            
            all_algorithms = self.backend.multi_algorithm_manager.get_all_algorithms()
            if not all_algorithms:
                return {
                    'status': 'error',
                    'message': '没有算法数据'
                }
            
            # 按display_name分组，识别同种算法
            algorithm_groups = defaultdict(list)
            
            for algorithm in all_algorithms:
                if not algorithm.is_ready():
                    continue
                
                display_name = algorithm.metadata.display_name
                algorithm_groups[display_name].append(algorithm)
            
            # 找出有多个曲子的算法（同种算法的不同曲子）
            same_algorithm_groups = {}
            for display_name, algorithms in algorithm_groups.items():
                if len(algorithms) > 1:
                    # 检查是否真的是不同曲子（algorithm_name不同）
                    algorithm_names = set(alg.metadata.algorithm_name for alg in algorithms)
                    if len(algorithm_names) > 1:
                        same_algorithm_groups[display_name] = algorithms
            
            if not same_algorithm_groups:
                return {
                    'status': 'error',
                    'message': '未找到同种算法的不同曲子'
                }
            
            # 分析每个算法的相对延时分布
            result_groups = {}
            
            for display_name, algorithms in same_algorithm_groups.items():
                group_data = self._analyze_algorithm_group(algorithms)
                if group_data:
                    result_groups[display_name] = group_data
            
            if not result_groups:
                return {
                    'status': 'error',
                    'message': '没有有效的相对延时数据'
                }
            
            logger.info(f"同种算法相对延时分析完成，共 {len(same_algorithm_groups)} 个算法组")
            
            return {
                'status': 'success',
                'algorithm_groups': result_groups
            }
            
        except Exception as e:
            logger.error(f"分析同种算法相对延时分布失败: {e}")
            logger.error(traceback.format_exc())
            return {
                'status': 'error',
                'message': f'分析失败: {str(e)}'
            }
    
    def get_data_points_by_range(
        self,
        display_name: str,
        filename_display: str,
        relative_delay_min_ms: float,
        relative_delay_max_ms: float
    ) -> List[Dict[str, Any]]:
        """
        根据子图信息获取指定相对延时范围内的数据点详情
        
        Args:
            display_name: 算法显示名称（用于识别算法组）
            filename_display: 文件名显示（'汇总' 或具体文件名）
            relative_delay_min_ms: 最小相对延时值（ms）
            relative_delay_max_ms: 最大相对延时值（ms）
            
        Returns:
            List[Dict[str, Any]]: 该相对延时范围内的数据点列表
        """
        try:
            if not self.backend.multi_algorithm_manager:
                return []
            
            all_algorithms = self.backend.multi_algorithm_manager.get_all_algorithms()
            filtered_data = []
            
            for algorithm in all_algorithms:
                if not algorithm.is_ready():
                    continue
                
                # 检查算法是否属于指定的display_name组
                if algorithm.metadata.display_name != display_name:
                    continue
                
                # 如果是汇总图，包含该组所有算法；否则只包含指定文件名的算法
                if filename_display != '汇总':
                    algorithm_filename = self._extract_filename_display(algorithm)
                    if algorithm_filename != filename_display:
                        continue
                
                if not algorithm.analyzer or not algorithm.analyzer.note_matcher:
                    continue
                
                # 获取偏移数据
                offset_data = algorithm.analyzer.get_offset_alignment_data()
                if not offset_data:
                    continue
                
                # 筛选指定范围内的数据点
                points = self._filter_data_points_by_range(
                    offset_data,
                    algorithm.metadata.algorithm_name,
                    relative_delay_min_ms,
                    relative_delay_max_ms
                )
                filtered_data.extend(points)
            
            return filtered_data
            
        except Exception as e:
            logger.error(f"获取相对延时范围数据点失败: {e}")
            logger.error(traceback.format_exc())
            return []
    
    def _analyze_algorithm_group(self, algorithms: List[Any]) -> Dict[str, Any]:
        """
        分析一组算法的相对延时数据
        
        Args:
            algorithms: 算法列表
            
        Returns:
            Dict[str, Any]: 包含相对延时数据的字典，如果没有有效数据则返回None
        """
        group_relative_delays = []  # 该算法组所有曲子合并后的相对延时
        group_info = []
        song_data = []  # 按曲子分组的数据
        
        for algorithm in algorithms:
            if not algorithm.analyzer or not algorithm.analyzer.note_matcher:
                continue
            
            # 获取该曲子的精确偏移数据（误差 ≤ 50ms）
            offset_data = algorithm.analyzer.note_matcher.get_precision_offset_alignment_data()
            if not offset_data:
                continue
            
            # 计算该曲子的平均延时（带符号）
            me_0_1ms = algorithm.analyzer.note_matcher.get_mean_error()
            mean_delay_ms = me_0_1ms / 10.0  # 转换为ms
            
            # 计算相对延时
            relative_delays = []
            for item in offset_data:
                keyon_offset_0_1ms = item.get('keyon_offset', 0.0)
                absolute_delay_ms = keyon_offset_0_1ms / 10.0
                relative_delay_ms = absolute_delay_ms - mean_delay_ms
                relative_delays.append(relative_delay_ms)
            
            if relative_delays:
                group_relative_delays.extend(relative_delays)
                
                # 从algorithm_name中提取文件名部分
                filename_display = self._extract_filename_display(algorithm)
                
                group_info.append({
                    'algorithm_name': algorithm.metadata.algorithm_name,
                    'filename': algorithm.metadata.filename,
                    'filename_display': filename_display,
                    'mean_delay_ms': mean_delay_ms,
                    'relative_delay_count': len(relative_delays)
                })
                
                # 保存该曲子的单独数据
                song_data.append({
                    'algorithm_name': algorithm.metadata.algorithm_name,
                    'filename': algorithm.metadata.filename,
                    'filename_display': filename_display,
                    'mean_delay_ms': mean_delay_ms,
                    'relative_delays': relative_delays,  # 该曲子的相对延时列表
                    'relative_delay_count': len(relative_delays)
                })
        
        if not group_relative_delays:
            return None
        
        return {
            'relative_delays': group_relative_delays,  # 合并后的相对延时
            'algorithms': group_info,  # 算法信息
            'song_data': song_data  # 按曲子分组的数据
        }
    
    def _filter_data_points_by_range(
        self,
        offset_data: List[Dict[str, Any]],
        algorithm_name: str,
        relative_delay_min_ms: float,
        relative_delay_max_ms: float
    ) -> List[Dict[str, Any]]:
        """
        筛选指定相对延时范围内的数据点
        
        Args:
            offset_data: 偏移数据列表
            algorithm_name: 算法名称
            relative_delay_min_ms: 最小相对延时值（ms）
            relative_delay_max_ms: 最大相对延时值（ms）
            
        Returns:
            List[Dict[str, Any]]: 筛选后的数据点列表
        """
        # 计算该算法的平均延时（用于计算相对延时）
        absolute_delays_ms = [item.get('keyon_offset', 0.0) / 10.0 for item in offset_data]
        if not absolute_delays_ms:
            return []
        
        mean_delay_ms = sum(absolute_delays_ms) / len(absolute_delays_ms)
        
        # 筛选出指定相对延时范围内的数据点
        filtered_data = []
        for item in offset_data:
            absolute_delay_ms = item.get('keyon_offset', 0.0) / 10.0
            relative_delay_ms = absolute_delay_ms - mean_delay_ms
            
            if relative_delay_min_ms <= relative_delay_ms <= relative_delay_max_ms:
                item_copy = item.copy()
                item_copy['absolute_delay_ms'] = absolute_delay_ms
                item_copy['relative_delay_ms'] = relative_delay_ms
                item_copy['delay_ms'] = relative_delay_ms  # 保持兼容性
                item_copy['algorithm_name'] = algorithm_name
                filtered_data.append(item_copy)
        
        return filtered_data
    
    def _extract_filename_display(self, algorithm: Any) -> str:
        """
        从算法中提取文件名显示
        
        Args:
            algorithm: 算法对象
            
        Returns:
            str: 文件名显示
        """
        filename_display = algorithm.metadata.filename
        if '_' in algorithm.metadata.algorithm_name:
            parts = algorithm.metadata.algorithm_name.rsplit('_', 1)
            if len(parts) == 2:
                filename_display = parts[1]
        return filename_display
