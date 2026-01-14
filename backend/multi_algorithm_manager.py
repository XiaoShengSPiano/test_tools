#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
多算法对比管理器

负责管理多个算法的数据集，支持算法对比分析。
使用面向对象设计，支持并发处理。
"""

from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field
from enum import Enum
import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import time
from utils.logger import Logger
from utils.colors import ALGORITHM_COLOR_PALETTE
from spmid.spmid_analyzer import SPMIDAnalyzer
from spmid.spmid_reader import Note

logger = Logger.get_logger()


class AlgorithmStatus(Enum):
    """算法状态枚举"""
    PENDING = "pending"  # 等待加载
    LOADING = "loading"  # 正在加载
    READY = "ready"  # 已就绪
    ERROR = "error"  # 加载失败


@dataclass
class AlgorithmMetadata:
    """算法元数据"""
    algorithm_name: str  # 算法名称（内部唯一标识：算法名_文件名（无扩展名））
    display_name: str  # 显示名称（用户输入的原始算法名称）
    filename: str  # 原始文件名
    upload_time: float  # 上传时间戳
    status: AlgorithmStatus = AlgorithmStatus.PENDING
    error_message: Optional[str] = None


class AlgorithmDataset:
    """
    单个算法的数据集类
    
    封装单个算法的所有数据、分析结果和统计信息。
    每个算法实例独立管理自己的分析器。
    """
    
    def __init__(self, algorithm_name: str, display_name: str, filename: str, color_index: int = 0):
        """
        初始化算法数据集
        
        Args:
            algorithm_name: 算法名称（内部唯一标识：算法名_文件名（无扩展名））
            display_name: 显示名称（用户输入的原始算法名称）
            filename: 原始文件名
            color_index: 颜色索引（用于分配图表颜色）
        """
        self.metadata = AlgorithmMetadata(
            algorithm_name=algorithm_name,
            display_name=display_name,
            filename=filename,
            upload_time=0.0
        )
        
        # 分析器实例
        self.analyzer: Optional[SPMIDAnalyzer] = None
        
        # 显示控制
        self.color = ALGORITHM_COLOR_PALETTE[color_index % len(ALGORITHM_COLOR_PALETTE)]
        self.is_active: bool = True  # 是否在对比中显示
        
        # 原始数据（用于重新分析）
        self.record_data: Optional[List[Note]] = None
        self.replay_data: Optional[List[Note]] = None
        
        logger.info(f"✅ AlgorithmDataset初始化: {algorithm_name} (文件: {filename})")
    
    def load_data(self, record_data: List[Note], replay_data: List[Note], filter_collector=None) -> bool:
        """
        加载并分析数据
        
        Args:
            record_data: 录制数据
            replay_data: 播放数据
            filter_collector: 可选的过滤信息收集器（包含加载阶段的过滤信息）
            
        Returns:
            bool: 是否成功
        """
        try:
            perf_load_start = time.time()
            self.metadata.status = AlgorithmStatus.LOADING
            logger.info(f"                📊 [Dataset] 开始加载数据...")

            # ============ 保存原始数据 ============
            perf_save_start = time.time()
            self.record_data = record_data
            self.replay_data = replay_data
            perf_save_end = time.time()
            logger.info(f"                ⏱️  [性能] Dataset-保存数据: {(perf_save_end - perf_save_start)*1000:.2f}ms")

            # ============ 创建分析器并执行分析 ============
            perf_analyze_start = time.time()
            logger.info(f"                🔬 开始执行SPMIDAnalyzer分析...")
            self.analyzer = SPMIDAnalyzer()
            self.analyzer.analyze(record_data, replay_data, filter_collector)
            perf_analyze_end = time.time()
            analyze_time_ms = (perf_analyze_end - perf_analyze_start) * 1000
            logger.info(f"                ⏱️  [性能] Dataset-SPMIDAnalyzer分析: {analyze_time_ms:.2f}ms")

            self.metadata.status = AlgorithmStatus.READY
            
            perf_load_end = time.time()
            total_time_ms = (perf_load_end - perf_load_start) * 1000
            logger.info(f"                🏁 [Dataset] 数据加载完成，总耗时: {total_time_ms:.2f}ms")
            return True
            
        except Exception as e:
            self.metadata.status = AlgorithmStatus.ERROR
            self.metadata.error_message = str(e)
            logger.error(f"                ❌ 算法 {self.metadata.algorithm_name} 数据加载失败: {e}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            Dict[str, Any]: 统计信息字典
        """
        if not self.analyzer:
            return {}
        
        return {
            'algorithm_name': self.metadata.algorithm_name,  # 内部唯一标识
            'display_name': self.metadata.display_name,  # 显示名称
            'filename': self.metadata.filename,
            'offset_statistics': self.analyzer.get_offset_statistics() if self.analyzer.note_matcher else {},
            'global_average_delay': self.analyzer.get_global_average_delay() if self.analyzer.note_matcher else 0.0,
            'mean_error': self.analyzer.get_mean_error() if self.analyzer.note_matcher else 0.0,
            'matched_pairs_count': len(self.analyzer.matched_pairs) if hasattr(self.analyzer, 'matched_pairs') else 0,
        }
    
    def get_offset_alignment_data(self) -> List[Dict[str, Union[int, float]]]:
        """
        获取偏移对齐数据
        
        Returns:
            List[Dict[str, Any]]: 偏移对齐数据列表
        """
        if not self.analyzer or not self.analyzer.note_matcher:
            return []
        
        return self.analyzer.note_matcher.get_offset_alignment_data()
    
    def get_key_statistics_table_data(self) -> List[Dict[str, Union[int, float, str]]]:
        """
        获取按键统计表格数据
        
        Returns:
            List[Dict[str, Any]]: 按键统计数据列表，每行包含一个按键的统计信息
        """
        if not self.analyzer or not self.analyzer.note_matcher:
            return []
        
        # 获取基础统计数据
        data = self.analyzer.note_matcher.get_key_statistics_for_bar_chart()
        
        # 为每行添加算法名称（格式：算法名_文件名）
        algorithm_display = f"{self.metadata.display_name}_{self.metadata.filename}"
        for row in data:
            row['algorithm_name'] = algorithm_display
        
        return data
    
    def is_ready(self) -> bool:
        """检查算法是否已就绪"""
        return self.metadata.status == AlgorithmStatus.READY and self.analyzer is not None



class MultiAlgorithmManager:
    """
    多算法对比管理器类
    
    负责管理多个算法数据集，支持：
    - 添加/删除算法
    - 并发加载多个算法
    - 算法状态管理
    - 算法显示控制
    """
    
    def __init__(self, max_algorithms: Optional[int] = None):
        """
        初始化多算法管理器
        
        Args:
            max_algorithms: 最大算法数量（None表示无限制）
        """
        self.algorithms: Dict[str, AlgorithmDataset] = {}  # algorithm_name -> AlgorithmDataset
        self.max_algorithms = max_algorithms
        # 线程池用于并发处理，如果无限制则使用默认值10
        executor_workers = max_algorithms if max_algorithms is not None else 10
        self.executor = ThreadPoolExecutor(max_workers=executor_workers)
        
        limit_text = "无限制" if max_algorithms is None else str(max_algorithms)
        logger.info(f"MultiAlgorithmManager初始化完成 (最大算法数: {limit_text})")
    
    def get_algorithm_count(self) -> int:
        """获取当前算法数量"""
        return len(self.algorithms)
    
    def can_add_algorithm(self) -> bool:
        """检查是否可以添加新算法"""
        if self.max_algorithms is None:
            return True  # 无限制
        return self.get_algorithm_count() < self.max_algorithms
    
    def validate_algorithm_name(self, algorithm_name: str) -> Tuple[bool, str]:
        """
        验证算法名称是否有效
        
        Args:
            algorithm_name: 算法名称
            
        Returns:
            Tuple[bool, str]: (是否有效, 错误信息)
        """
        if not algorithm_name or not algorithm_name.strip():
            return False, "算法名称不能为空"
        
        algorithm_name = algorithm_name.strip()
        
        if algorithm_name in self.algorithms:
            return False, f"算法名称 '{algorithm_name}' 已存在"
        
        return True, ""
    
    def _generate_unique_algorithm_name(self, algorithm_name: str, filename: str) -> str:
        """
        生成唯一的算法名称（算法名_文件名（无扩展名））
        
        Args:
            algorithm_name: 用户输入的算法名称
            filename: 文件名
            
        Returns:
            str: 唯一的算法名称
        """
        import os
        # 去掉路径和扩展名，只保留文件名（无扩展名）
        basename = os.path.basename(filename)
        filename_without_ext = os.path.splitext(basename)[0]
        # 生成组合名称：算法名_文件名
        unique_name = f"{algorithm_name}_{filename_without_ext}"
        return unique_name
    
    async def add_algorithm_async(self, algorithm_name: str, filename: str,
                                  record_data: List[Note], replay_data: List[Note],
                                  filter_collector=None) -> Tuple[bool, str]:
        """
        异步添加算法（支持并发处理）
        
        使用 ThreadPoolExecutor 进行并发处理，因为数据分析是 CPU 密集型任务。
        自动通过"算法名_文件名（无扩展名）"生成唯一标识，区分同种算法的不同曲子。
        
        Args:
            algorithm_name: 算法名称（用户输入的原始名称）
            filename: 文件名
            record_data: 录制数据
            replay_data: 播放数据
            filter_collector: 可选的过滤信息收集器（包含加载阶段的过滤信息）
            
        Returns:
            Tuple[bool, str]: (是否成功, 唯一算法名或错误信息)
                - 成功时返回: (True, unique_algorithm_name)
                - 失败时返回: (False, error_message)
        """
        perf_manager_start = time.time()
        logger.info(f"            🔧 [Manager] 开始添加算法...")
        
        # ============ 生成唯一算法名 ============
        perf_name_start = time.time()
        unique_algorithm_name = self._generate_unique_algorithm_name(algorithm_name, filename)
        perf_name_end = time.time()
        logger.info(f"            ⏱️  [性能] Manager-生成唯一名: {(perf_name_end - perf_name_start)*1000:.2f}ms")
        
        # ============ 验证算法名 ============
        is_valid, error_msg = self.validate_algorithm_name(unique_algorithm_name)
        if not is_valid:
            return False, error_msg
        
        # 检查是否超过最大数量
        if not self.can_add_algorithm():
            limit_text = str(self.max_algorithms) if self.max_algorithms is not None else "无限制"
            return False, f"已达到最大算法数量限制 ({limit_text})"
        
        # ============ 创建算法数据集 ============
        perf_create_start = time.time()
        color_index = len(self.algorithms)
        algorithm = AlgorithmDataset(unique_algorithm_name, algorithm_name, filename, color_index)
        perf_create_end = time.time()
        logger.info(f"            ⏱️  [性能] Manager-创建数据集: {(perf_create_end - perf_create_start)*1000:.2f}ms")
        
        # ============ 执行数据分析（线程池） ============
        perf_analysis_start = time.time()
        logger.info(f"            🔄 执行数据分析（线程池）...")
        
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(
            self.executor,
            algorithm.load_data,
            record_data,
            replay_data,
            filter_collector
        )
        
        perf_analysis_end = time.time()
        analysis_time_ms = (perf_analysis_end - perf_analysis_start) * 1000
        logger.info(f"            ⏱️  [性能] Manager-数据分析: {analysis_time_ms:.2f}ms")
        
        if success:
            self.algorithms[unique_algorithm_name] = algorithm
            
            perf_manager_end = time.time()
            total_time_ms = (perf_manager_end - perf_manager_start) * 1000
            logger.info(f"            🏁 [Manager] 算法添加完成，总耗时: {total_time_ms:.2f}ms")
            logger.info(f"            ✅ 算法 '{algorithm_name}' (文件: {filename}) 添加成功，唯一标识: {unique_algorithm_name}")
            return True, unique_algorithm_name  # 返回唯一标识符
        else:
            error_msg = algorithm.metadata.error_message or "未知错误"
            logger.error(f"            ❌ 算法 '{algorithm_name}' (文件: {filename}) 添加失败: {error_msg}")
            return False, error_msg
    
    def remove_algorithm(self, algorithm_name: str) -> bool:
        """
        移除算法
        
        Args:
            algorithm_name: 算法名称
            
        Returns:
            bool: 是否成功
        """
        if algorithm_name not in self.algorithms:
            return False
        
        del self.algorithms[algorithm_name]
        logger.info(f"算法 '{algorithm_name}' 已移除")
        return True
    
    def get_algorithm(self, algorithm_name: str) -> Optional[AlgorithmDataset]:
        """获取指定算法"""
        return self.algorithms.get(algorithm_name)
    
    def get_all_algorithms(self) -> List[AlgorithmDataset]:
        """获取所有算法列表"""
        return list(self.algorithms.values())
    
    def get_active_algorithms(self) -> List[AlgorithmDataset]:
        """获取激活的算法列表（用于对比显示）"""
        return [alg for alg in self.algorithms.values() if alg.is_active and alg.is_ready()]
    
    def toggle_algorithm(self, algorithm_name: str) -> bool:
        """
        切换算法的显示/隐藏状态
        
        Args:
            algorithm_name: 算法名称
            
        Returns:
            bool: 是否成功
        """
        if algorithm_name not in self.algorithms:
            return False
        
        algorithm = self.algorithms[algorithm_name]
        algorithm.is_active = not algorithm.is_active
        logger.info(f"算法 '{algorithm_name}' 显示状态: {'显示' if algorithm.is_active else '隐藏'}")
        return True
    
    def clear_all(self) -> None:
        """清空所有算法"""
        self.algorithms.clear()
        logger.info("所有算法已清空")
    
    def get_comparison_statistics(self) -> Dict[str, Any]:
        """
        获取所有算法的对比统计信息
        
        Returns:
            Dict[str, Any]: 对比统计信息
        """
        active_algorithms = self.get_active_algorithms()
        
        if not active_algorithms:
            return {}
        
        comparison_data = {}
        for algorithm in active_algorithms:
            comparison_data[algorithm.metadata.algorithm_name] = algorithm.get_statistics()
        
        return comparison_data

