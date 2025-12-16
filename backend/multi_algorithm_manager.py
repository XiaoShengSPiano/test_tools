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
from utils.logger import Logger
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
    
    # 预定义颜色方案（用于图表显示）
    COLOR_PALETTE = [
        '#1f77b4',  # 蓝色
        '#ff7f0e',  # 橙色
        '#2ca02c',  # 绿色
        '#d62728',  # 红色
        '#9467bd',  # 紫色
        '#8c564b',  # 棕色
        '#e377c2',  # 粉色
        '#7f7f7f',  # 灰色
    ]
    
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
        self.color = self.COLOR_PALETTE[color_index % len(self.COLOR_PALETTE)]
        self.is_active: bool = True  # 是否在对比中显示
        
        # 原始数据（用于重新分析）
        self.record_data: Optional[List[Note]] = None
        self.replay_data: Optional[List[Note]] = None
        
        logger.info(f"✅ AlgorithmDataset初始化: {algorithm_name} (文件: {filename})")
    
    def load_data(self, record_data: List[Note], replay_data: List[Note]) -> bool:
        """
        加载并分析数据
        
        Args:
            record_data: 录制数据
            replay_data: 播放数据
            
        Returns:
            bool: 是否成功
        """
        try:
            self.metadata.status = AlgorithmStatus.LOADING

            # 清除之前的一致性验证状态，确保重新验证
            self._last_algorithm_hash = None
            self._last_overview_metrics = None

            # 保存原始数据
            self.record_data = record_data
            self.replay_data = replay_data
            
            # 创建分析器并执行分析
            self.analyzer = SPMIDAnalyzer()
            self.analyzer.analyze(record_data, replay_data)

            # 验证数据一致性
            self._verify_algorithm_consistency()

            self.metadata.status = AlgorithmStatus.READY
            logger.info(f"✅ 算法 {self.metadata.algorithm_name} 数据加载完成")
            return True
            
        except Exception as e:
            self.metadata.status = AlgorithmStatus.ERROR
            self.metadata.error_message = str(e)
            logger.error(f"❌ 算法 {self.metadata.algorithm_name} 数据加载失败: {e}")
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
    
    def is_ready(self) -> bool:
        """检查算法是否已就绪"""
        return self.metadata.status == AlgorithmStatus.READY and self.analyzer is not None

    def _verify_algorithm_consistency(self) -> None:
        """
        验证算法数据一致性，包括数据概览指标的具体对比

        计算分析结果的哈希值，用于检测相同输入是否产生相同输出。
        """
        try:
            import hashlib
            import json

            # 计算当前分析结果的哈希值
            current_hash = self._calculate_algorithm_hash()
            current_metrics = self._calculate_overview_metrics()

            # 获取之前保存的哈希值和指标
            previous_hash = getattr(self, '_last_algorithm_hash', None)
            previous_metrics = getattr(self, '_last_overview_metrics', None)

            if previous_hash is not None and previous_metrics is not None:
                if current_hash == previous_hash:
                    logger.info(f"✅ 算法 {self.metadata.algorithm_name} 数据一致性验证通过")
                    logger.info(f"📊 数据概览指标验证: 准确率={current_metrics.get('accuracy_percent', 'N/A')}%, "
                              f"丢锤数={current_metrics.get('drop_hammers_count', 'N/A')}, "
                              f"多锤数={current_metrics.get('multi_hammers_count', 'N/A')}, "
                              f"已配对数={current_metrics.get('matched_pairs_count', 'N/A')}")
                else:
                    logger.warning(f"⚠️ 算法 {self.metadata.algorithm_name} 数据一致性警告：相同输入产生了不同输出！")
                    logger.warning(f"  之前的哈希值: {previous_hash}")
                    logger.warning(f"  当前的哈希值: {current_hash}")

                    # 对比具体指标
                    self._log_metrics_comparison(previous_metrics, current_metrics)
            else:
                logger.info(f"📝 算法 {self.metadata.algorithm_name} 首次分析，记录数据哈希值: {current_hash}")
                logger.info(f"📊 记录数据概览指标: 准确率={current_metrics.get('accuracy_percent', 'N/A')}%, "
                          f"丢锤数={current_metrics.get('drop_hammers_count', 'N/A')}, "
                          f"多锤数={current_metrics.get('multi_hammers_count', 'N/A')}, "
                          f"已配对数={current_metrics.get('matched_pairs_count', 'N/A')}")

                # 输出详细的丢锤按键信息
                drop_hammers_count = current_metrics.get('drop_hammers_count', 0)
                if drop_hammers_count > 0:
                    logger.info(f"🔍 算法 {self.metadata.algorithm_name} 丢锤按键详情:")
                    drop_hammers = getattr(self.analyzer, 'drop_hammers', [])
                    for i, error_note in enumerate(drop_hammers):
                        if len(error_note.infos) > 0:
                            rec = error_note.infos[0]
                            logger.info(f"  🪓 丢锤{i+1}: 按键ID={rec.keyId}, 索引={rec.index}")

                # 输出详细的多锤按键信息
                multi_hammers_count = current_metrics.get('multi_hammers_count', 0)
                if multi_hammers_count > 0:
                    logger.info(f"🔍 算法 {self.metadata.algorithm_name} 多锤按键详情:")
                    multi_hammers = getattr(self.analyzer, 'multi_hammers', [])
                    for i, error_note in enumerate(multi_hammers):
                        if len(error_note.infos) > 0:
                            play = error_note.infos[0]
                            logger.info(f"  🔨 多锤{i+1}: 按键ID={play.keyId}, 索引={play.index}")

            # 保存当前哈希值和指标供下次比较
            self._last_algorithm_hash = current_hash
            self._last_overview_metrics = current_metrics

        except Exception as e:
            logger.warning(f"⚠️ 算法 {self.metadata.algorithm_name} 一致性验证失败: {e}")

    def _log_metrics_comparison(self, previous_metrics: Dict[str, Any], current_metrics: Dict[str, Any]) -> None:
        """
        记录指标对比信息，用于调试不一致问题

        Args:
            previous_metrics: 之前的指标数据
            current_metrics: 当前的指标数据
        """
        try:
            logger.warning("🔍 数据概览指标对比:")

            metrics_to_compare = [
                ('accuracy_percent', '准确率(%)'),
                ('drop_hammers_count', '丢锤数'),
                ('multi_hammers_count', '多锤数'),
                ('matched_pairs_count', '已配对音符数'),
                ('total_valid_record', '有效录制音符数'),
                ('total_valid_replay', '有效播放音符数'),
                ('total_valid_combined', '总有效音符数')
            ]

            for key, name in metrics_to_compare:
                prev_val = previous_metrics.get(key, 'N/A')
                curr_val = current_metrics.get(key, 'N/A')
                if prev_val != curr_val:
                    logger.warning(f"  ❌ {name}: {prev_val} → {curr_val} (不一致！)")
                else:
                    logger.info(f"  ✅ {name}: {curr_val} (一致)")

        except Exception as e:
            logger.warning(f"记录指标对比失败: {e}")

    def _calculate_algorithm_hash(self) -> str:
        """
        计算算法分析结果的哈希值，包括数据概览指标

        Returns:
            str: 分析结果的SHA256哈希值
        """
        try:
            # 获取数据概览指标的具体数值
            overview_metrics = self._calculate_overview_metrics()

            hash_data = {
                'overview_metrics': overview_metrics,
                'matched_pairs_count': len(getattr(self.analyzer, 'matched_pairs', [])),
                'valid_record_count': len(getattr(self.analyzer, 'valid_record_data', [])),
                'valid_replay_count': len(getattr(self.analyzer, 'valid_replay_data', [])),
                'multi_hammers_count': len(getattr(self.analyzer, 'multi_hammers', [])),
                'drop_hammers_count': len(getattr(self.analyzer, 'drop_hammers', [])),
                'silent_hammers_count': len(getattr(self.analyzer, 'silent_hammers', [])),
            }

            # 记录丢锤详细信息
            drop_hammers = getattr(self.analyzer, 'drop_hammers', [])
            if drop_hammers:
                drop_info = []
                for i, error_note in enumerate(drop_hammers[:10]):  # 只记录前10个
                    if len(error_note.infos) > 0:
                        rec = error_note.infos[0]
                        drop_info.append({
                            'index': i+1,
                            'key_id': rec.keyId,
                            'note_index': rec.index,
                            'key_on': rec.keyOn / 10.0,
                            'key_off': rec.keyOff / 10.0
                        })
                hash_data['drop_hammers_detail'] = drop_info

            # 记录多锤详细信息
            multi_hammers = getattr(self.analyzer, 'multi_hammers', [])
            if multi_hammers:
                multi_info = []
                for i, error_note in enumerate(multi_hammers[:10]):  # 只记录前10个
                    if len(error_note.infos) > 0:
                        play = error_note.infos[0]
                        multi_info.append({
                            'index': i+1,
                            'key_id': play.keyId,
                            'note_index': play.index,
                            'key_on': play.keyOn / 10.0,
                            'key_off': play.keyOff / 10.0
                        })
                hash_data['multi_hammers_detail'] = multi_info

            # 添加matched_pairs的详细信息
            if hasattr(self.analyzer, 'matched_pairs') and self.analyzer.matched_pairs:
                pairs_info = []
                for i, (r_idx, p_idx, r_note, p_note) in enumerate(self.analyzer.matched_pairs[:5]):
                    pairs_info.append({
                        'record_index': r_idx,
                        'replay_index': p_idx,
                        'record_note_id': getattr(r_note, 'id', None),
                        'replay_note_id': getattr(p_note, 'id', None)
                    })
                hash_data['matched_pairs_sample'] = pairs_info

            # 转换为JSON字符串并计算哈希
            hash_string = json.dumps(hash_data, sort_keys=True, default=str)
            return hashlib.sha256(hash_string.encode('utf-8')).hexdigest()

        except Exception as e:
            logger.warning(f"计算算法哈希失败: {e}")
            return "hash_calculation_failed"

    def _calculate_overview_metrics(self) -> Dict[str, Any]:
        """
        计算数据概览中的关键指标，用于一致性验证

        Returns:
            Dict[str, Any]: 包含数据概览指标的字典
        """
        try:
            # 使用与UI相同的计算逻辑
            initial_valid_record = getattr(self.analyzer, 'initial_valid_record_data', None)
            initial_valid_replay = getattr(self.analyzer, 'initial_valid_replay_data', None)

            total_valid_record = len(initial_valid_record) if initial_valid_record else 0
            total_valid_replay = len(initial_valid_replay) if initial_valid_replay else 0

            matched_pairs = getattr(self.analyzer, 'matched_pairs', [])
            drop_hammers = getattr(self.analyzer, 'drop_hammers', [])
            multi_hammers = getattr(self.analyzer, 'multi_hammers', [])

            matched_count = len(matched_pairs)
            total_valid = total_valid_record + total_valid_replay
            accuracy = (matched_count * 2 / total_valid * 100) if total_valid > 0 else 0.0

            return {
                'accuracy_percent': round(accuracy, 1),
                'drop_hammers_count': len(drop_hammers),
                'multi_hammers_count': len(multi_hammers),
                'matched_pairs_count': matched_count,
                'total_valid_record': total_valid_record,
                'total_valid_replay': total_valid_replay,
                'total_valid_combined': total_valid
            }

        except Exception as e:
            logger.warning(f"计算概览指标失败: {e}")
            return {'error': str(e)}


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
        logger.info(f"✅ MultiAlgorithmManager初始化完成 (最大算法数: {limit_text})")
    
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
                                  record_data: List[Note], replay_data: List[Note]) -> Tuple[bool, str]:
        """
        异步添加算法（支持并发处理）
        
        使用 ThreadPoolExecutor 进行并发处理，因为数据分析是 CPU 密集型任务。
        自动通过"算法名_文件名（无扩展名）"生成唯一标识，区分同种算法的不同曲子。
        
        Args:
            algorithm_name: 算法名称（用户输入的原始名称）
            filename: 文件名
            record_data: 录制数据
            replay_data: 播放数据
            
        Returns:
            Tuple[bool, str]: (是否成功, 错误信息)
        """
        # 生成唯一的算法名称（算法名_文件名（无扩展名））
        unique_algorithm_name = self._generate_unique_algorithm_name(algorithm_name, filename)
        
        # 验证唯一算法名称
        is_valid, error_msg = self.validate_algorithm_name(unique_algorithm_name)
        if not is_valid:
            return False, error_msg
        
        # 检查是否超过最大数量
        if not self.can_add_algorithm():
            limit_text = str(self.max_algorithms) if self.max_algorithms is not None else "无限制"
            return False, f"已达到最大算法数量限制 ({limit_text})"
        
        # 创建算法数据集（使用唯一名称作为内部标识，原始名称作为显示名称）
        color_index = len(self.algorithms)
        algorithm = AlgorithmDataset(unique_algorithm_name, algorithm_name, filename, color_index)
        
        # 在线程池中执行数据加载（CPU密集型任务，使用线程池更高效）
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(
            self.executor,
            algorithm.load_data,
            record_data,
            replay_data
        )
        
        if success:
            self.algorithms[unique_algorithm_name] = algorithm
            logger.info(f"✅ 算法 '{algorithm_name}' (文件: {filename}) 添加成功，内部标识: '{unique_algorithm_name}'")
            return True, ""
        else:
            error_msg = algorithm.metadata.error_message or "未知错误"
            logger.error(f"❌ 算法 '{algorithm_name}' (文件: {filename}) 添加失败: {error_msg}")
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
        logger.info(f"✅ 算法 '{algorithm_name}' 已移除")
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
        logger.info(f"✅ 算法 '{algorithm_name}' 显示状态: {'显示' if algorithm.is_active else '隐藏'}")
        return True
    
    def rename_algorithm(self, old_name: str, new_name: str) -> bool:
        """
        重命名算法
        
        Args:
            old_name: 旧名称
            new_name: 新名称
            
        Returns:
            bool: 是否成功
        """
        if old_name not in self.algorithms:
            return False
        
        if new_name in self.algorithms:
            return False  # 新名称已存在
        
        algorithm = self.algorithms.pop(old_name)
        algorithm.metadata.algorithm_name = new_name
        self.algorithms[new_name] = algorithm
        
        logger.info(f"✅ 算法重命名: '{old_name}' -> '{new_name}'")
        return True
    
    def clear_all(self) -> None:
        """清空所有算法"""
        self.algorithms.clear()
        logger.info("✅ 所有算法已清空")
    
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

