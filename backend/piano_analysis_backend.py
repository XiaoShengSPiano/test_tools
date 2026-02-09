#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import traceback
import pandas as pd
import numpy as np
from typing import Optional, Tuple, Dict, Any, List, Union
from collections import defaultdict
from plotly.graph_objects import Figure
from utils.logger import Logger
from utils.constants import GRADE_LEVELS


import dash_bootstrap_components as dbc
from dash import html

# SPMID相关导入
from spmid.spmid_analyzer import SPMIDAnalyzer
from backend.file_upload_service import FileUploadService

# 导入各个模块
from .data_manager import DataManager
from .plot_generator import PlotGenerator
from .plot_service import PlotService
from .key_filter import KeyFilter
from .table_data_generator import TableDataGenerator
from .delay_analysis import DelayAnalysis
from .multi_algorithm_manager import MultiAlgorithmManager, AlgorithmDataset, AlgorithmStatus
from .force_curve_analyzer import ForceCurveAnalyzer

logger = Logger.get_logger()


class PianoAnalysisBackend:
    """钢琴分析后端主类 - 统一管理单算法和多算法分析流程"""
    def __init__(self, session_id=None, history_manager=None):
        """
        初始化钢琴分析后端
        
        Args:
            session_id: 会话ID，用于标识不同的分析会话
            history_manager: 全局历史管理器实例
        """
        self.session_id = session_id
        
        # 初始化各个模块
        self.data_manager = DataManager()
        self.key_filter = KeyFilter()
        self.plot_generator = PlotGenerator(self.key_filter)

        # 初始化多算法图表生成器（复用实例，避免重复初始化）
        from backend.multi_algorithm_plot_generator import MultiAlgorithmPlotGenerator
        self.multi_algorithm_plot_generator = MultiAlgorithmPlotGenerator(self.key_filter)

        # 初始化力度曲线分析器
        self.force_curve_analyzer = ForceCurveAnalyzer()
        
        # 使用全局的历史管理器实例
        self.history_manager = history_manager
        
        # 初始化延时分析器（延迟初始化，因为需要analyzer）
        self.delay_analysis = None
        
        # ==================== 多算法管理器 ====================
        self.multi_algorithm_manager = MultiAlgorithmManager(max_algorithms=None)
        
        # 初始化文件上传服务（统一的文件上传处理）
        self.file_upload_service = FileUploadService(self.multi_algorithm_manager, self.history_manager)
        
        # 初始化绘图服务（统一管理所有图表生成）
        self.plot_service = PlotService(self)
        
        # 初始化表格数据生成器（统一管理所有表格数据生成）
        self.table_data_generator = TableDataGenerator(self)
        
        # ==================== 临时文件缓存 ====================
        # 用于存储上传的文件二进制数据，减少 dcc.Store 的负载
        self.temp_file_cache: Dict[str, bytes] = {}
        
        logger.debug(f"[DEBUG]PianoAnalysisBackend初始化完成 (Session: {session_id})")


    # ==================== 数据管理相关方法 ====================
    def clear_data_state(self) -> None:
        """清理所有数据状态"""
        self.data_manager.clear_data_state()
        self.plot_generator.set_data()
        self.key_filter.set_data(None, None)
        
        # 清理多算法管理器
        if self.multi_algorithm_manager:
            self.multi_algorithm_manager.clear_all()
        
        # 清理临时文件缓存
        self.clear_temp_cache()

        logger.debug("[DEBUG] 所有数据状态已清理")
    
    def _get_algorithms_to_analyze(self) -> List[Any]:
        """
        获取需要分析的算法列表

        Returns:
            List[AlgorithmDataset]: 需要分析的算法列表
        """
        # 获取激活的算法，如果没有则创建单算法数据集
        if self.multi_algorithm_manager:
            active_algorithms = self.get_active_algorithms()
            if active_algorithms:
                return active_algorithms
            # 如果管理器存在但没有激活算法，则创建单算法
            return [self._get_or_create_single_algorithm()]
        else:
            # 多算法管理器不存在，创建单算法数据集
            return [self._get_or_create_single_algorithm()]

    def _get_or_create_single_algorithm(self) -> Any:
        """
        获取或创建单算法数据集

        Returns:
            AlgorithmDataset: 单算法数据集
        """
        # 查找现有的单算法
        active_algorithms = self.get_active_algorithms()
        for algorithm in active_algorithms:
            if algorithm.metadata.algorithm_name == "single_algorithm":
                return algorithm

        # 如果不存在，创建新的单算法数据集
        from backend.multi_algorithm_manager import AlgorithmMetadata
        algorithm = self.multi_algorithm_manager.create_algorithm(
            AlgorithmMetadata(
                algorithm_name="single_algorithm",
                display_name="单算法分析",
                filename=self.data_manager.get_upload_filename()
            )
        )
        return algorithm

    # ==================== 临时文件缓存方法 ====================
    def cache_temp_file(self, file_id: str, content_bytes: bytes) -> None:
        """缓存临时上传的文件"""
        if file_id and content_bytes:
            self.temp_file_cache[file_id] = content_bytes
            logger.debug(f"已缓存临时文件: {file_id}, 大小: {len(content_bytes)} 字节")
    
    def get_cached_temp_file(self, file_id: str) -> Optional[bytes]:
        """获取缓存的临时文件"""
        return self.temp_file_cache.get(file_id)
    
    def clear_temp_cache(self) -> None:
        """清理临时文件缓存"""
        self.temp_file_cache.clear()
        logger.debug("[DEBUG] 临时文件缓存已清理")

    def _analyze_single_algorithm(self, algorithm) -> bool:
        """
        分析单个算法

        Args:
            algorithm: 算法数据集

        Returns:
            bool: 分析是否成功
        """
        try:
            # 获取该算法的数据
            record_data = self.data_manager.get_record_data()
            replay_data = self.data_manager.get_replay_data()

            if not record_data or not replay_data:
                logger.error(f"算法 '{algorithm.metadata.algorithm_name}' 没有有效的录制或播放数据")
                return False

            analyzer = SPMIDAnalyzer()

            # 获取过滤信息收集器（包含加载阶段被过滤的音符信息）
            filter_collector = self.data_manager.get_filter_collector()

            # 执行分析（传递过滤信息）
            success = analyzer.analyze(record_data, replay_data, filter_collector)

            if success:
                # 将分析器存储到算法实例中
                algorithm.analyzer = analyzer
                algorithm.is_analyzed = True
                return True
            else:
                return False

        except Exception as e:
            logger.error(f"分析算法 '{algorithm.metadata.algorithm_name}' 时发生异常: {e}")
            return False

    def _get_current_analyzer(self, algorithm_name: Optional[str] = None) -> Optional[Any]:
        """
        获取当前上下文的分析器（统一的数据访问层）

        Args:
            algorithm_name: 算法名称（多算法模式时需要）

        Returns:
            分析器实例，如果不存在返回None
        """
        # 获取激活的算法列表
        if self.multi_algorithm_manager:
            active_algorithms = self.get_active_algorithms()
            if active_algorithms:
                # 多算法模式
                if algorithm_name:
                    algorithm = self._find_algorithm_by_name(algorithm_name)
                    return algorithm.analyzer if algorithm else None
                else:
                    # 多算法但未指定算法名，返回第一个算法的分析器
                    return active_algorithms[0].analyzer
            else:
                # 多算法管理器存在但没有激活算法，返回None
                return None
        else:
            # 多算法管理器不存在，返回None
            return None

    def get_data_source_info(self) -> Dict[str, Any]:
        """获取数据源信息"""
        return self.data_manager.get_data_source_info()

    def analyze_data(self) -> bool:
        """
        执行完整的数据分析流程（统一单算法和多算法模式）

        Returns:
            bool: 分析是否成功
        """
        try:
            logger.debug("[DEBUG]开始数据分析流程")

            # 获取需要分析的算法列表
            algorithms_to_analyze = self._get_algorithms_to_analyze()

            if not algorithms_to_analyze:
                logger.error("[ERROR]没有需要分析的算法")
                return False

            # 对每个算法执行分析
            success_count = 0
            for algorithm in algorithms_to_analyze:
                if self._analyze_single_algorithm(algorithm):
                    success_count += 1
                    logger.debug(f"[DEBUG]算法 '{algorithm.metadata.algorithm_name}' 分析成功")
                else:
                    logger.error(f"[ERROR]算法 '{algorithm.metadata.algorithm_name}' 分析失败")

            if success_count == len(algorithms_to_analyze):
                logger.debug(f"[DEBUG]数据分析完成，共分析 {success_count} 个算法")
                return True
            else:
                logger.error(f"数据分析部分失败，成功 {success_count}/{len(algorithms_to_analyze)} 个算法")
                return False

        except Exception as e:
            logger.error(f"数据分析异常: {e}")
            logger.error(traceback.format_exc())
            return False


    def process_history_selection(self, history_id):
        """
        处理历史记录选择 - 统一的历史记录入口
        
        Args:
            history_id: 历史记录ID
            
        Returns:
            tuple: (success, result_data, error_msg)
        """
        return self.history_manager.process_history_selection(history_id, self)
    
    async def load_algorithm_from_history(self, record_id: int) -> Tuple[bool, str]:
        """
        从历史记录加载算法到当前会话
        
        Args:
            record_id: 数据库记录 ID
            
        Returns:
            Tuple[bool, str]: (成功与否, 算法名或错误信息)
        """
        try:
            # 1. 获取记录
            record = self.history_manager.get_record_by_id(record_id)
            if not record:
                return False, f"未找到记录 ID: {record_id}"
            
            # 2. 从 Parquet 加载数据
            from database.history_manager import ParquetDataLoader
            tracks = ParquetDataLoader.load_from_record(record)
            
            if len(tracks) < 2:
                return False, "历史数据音轨不足"
            
            # 3. 转换为 Note 列表并进行二次过滤 (Ensuring quality criteria for historical data)
            # 注意：历史数据存储的是 OptimizedNote
            raw_record_notes = [note.to_standard_note() for note in tracks[0]]
            raw_replay_notes = [note.to_standard_note() for note in tracks[1]]
            
            # 重新应用最新的过滤规则 (User Requirement)
            from spmid.data_filter import DataFilter
            data_filter = DataFilter()
            record_notes, replay_notes, _ = data_filter.filter_notes(raw_record_notes, raw_replay_notes)
            
            logger.debug(f"[DEBUG] 从历史加载并重新过滤: 录制({len(raw_record_notes)}->{len(record_notes)}), 播放({len(raw_replay_notes)}->{len(replay_notes)})")

            # 4. 生成算法名称 (如果用户没给，用文件名+电机/算法标记)
            display_name = f"{record['filename']}_{record['motor_type']}_{record['algorithm']}"
            
            # 5. 添加到管理器
            success, result = await self.multi_algorithm_manager.add_algorithm_async(
                display_name,
                record['filename'],
                record_notes,
                replay_notes,
                filter_collector=None # 历史加载通常不重复展示过滤详细日志
            )
            
            if success:
                # 自动激活
                unique_name = result
                alg = self.multi_algorithm_manager.get_algorithm(unique_name)
                if alg:
                    alg.is_active = True
                return True, unique_name
            else:
                return False, result
                
        except Exception as e:
            logger.error(f"从历史加载失败: {e}")
            logger.error(traceback.format_exc())
            return False, str(e)

            
    def _sync_data_to_modules(self) -> None:
        """同步数据到各个模块"""
        # 获取有效数据
        valid_record_data = self.data_manager.get_valid_record_data()
        valid_replay_data = self.data_manager.get_valid_replay_data()
        
        # 同步到各个模块
        current_analyzer = self._get_current_analyzer()
        self.plot_generator.set_data(valid_record_data, valid_replay_data, analyzer=current_analyzer)
        self.key_filter.set_data(valid_record_data, valid_replay_data)
        
        # 同步分析结果到各个模块
        self._sync_analysis_results()
    
    def _extract_analysis_results(self, analyzer) -> Dict[str, Any]:
        """提取分析结果数据"""
        # 获取分析结果
        multi_hammers = analyzer.multi_hammers
        drop_hammers = analyzer.drop_hammers

        # 统计数据现在由 invalid_statistics 对象管理
        matched_pairs = analyzer.matched_pairs

        # 合并所有错误音符
        all_error_notes = multi_hammers + drop_hammers

        return {
            'multi_hammers': multi_hammers,
            'drop_hammers': drop_hammers,
            'matched_pairs': matched_pairs,
            'all_error_notes': all_error_notes
        }

    def _prepare_error_data(self, analyzer, analysis_data: Dict[str, Any]) -> None:
        """准备错误数据，确保analyzer对象有必要的属性"""
        multi_hammers = analysis_data['multi_hammers']
        drop_hammers = analysis_data['drop_hammers']
        all_error_notes = analysis_data['all_error_notes']

        # 确保analyzer对象有这些属性（供瀑布图生成器使用）
        analyzer.drop_hammers = drop_hammers
        analyzer.multi_hammers = multi_hammers
        logger.info(f"设置analyzer错误数据: 丢锤={len(drop_hammers)}, 多锤={len(multi_hammers)}")

        # 设置all_error_notes属性供UI层使用
        self.all_error_notes = all_error_notes

    def _sync_analysis_data_to_modules(self, analysis_data: Dict[str, Any]) -> None:
        """同步分析数据到各个模块"""
        multi_hammers = analysis_data['multi_hammers']
        drop_hammers = analysis_data['drop_hammers']
        # 不再从 analysis_data 获取 invalid_notes_table_data（已移除）
        matched_pairs = analysis_data['matched_pairs']
        all_error_notes = analysis_data['all_error_notes']

        # 获取有效数据
        valid_record_data = self.data_manager.get_valid_record_data()
        valid_replay_data = self.data_manager.get_valid_replay_data()

        # 同步到各个模块
        self.key_filter.set_data(valid_record_data, valid_replay_data)
        self.plot_generator.set_data(valid_record_data, valid_replay_data, matched_pairs, analyzer=self._get_current_analyzer())

        logger.info(f"错误数据统计: 丢锤={len(drop_hammers)}, 多锤={len(multi_hammers)}")

    def _validate_sync(self, analyzer) -> bool:
        """验证数据同步是否成功"""
        drop_count = len(analyzer.drop_hammers)
        multi_count = len(analyzer.multi_hammers)
        total_errors = drop_count + multi_count
        
        logger.info(f"analyzer错误数据同步验证: 丢锤={drop_count}, 多锤={multi_count}")
        
        if total_errors > 0:
            logger.info(f"错误统计: 丢锤={drop_count}, 多锤={multi_count}, 总计={total_errors}")
        
        return True

    def _sync_analysis_results(self) -> None:
        """同步分析结果到各个模块"""
        analyzer = self._get_current_analyzer()
        if not analyzer:
            return

        try:
            # 提取分析结果
            analysis_data = self._extract_analysis_results(analyzer)

            # 准备错误数据
            self._prepare_error_data(analyzer, analysis_data)

            # 同步数据到各个模块
            self._sync_analysis_data_to_modules(analysis_data)

            # 验证同步结果
            self._validate_sync(analyzer)

            logger.info("分析结果同步完成")

        except Exception as e:
            logger.error(f"同步分析结果失败: {e}")
    
    def get_global_average_delay(self) -> float:
        """
        获取整首曲子的平均时延（基于已配对数据）

        Returns:
            float: 平均时延（0.1ms单位）
        """
        active_algorithms = self.get_active_algorithms()
        if not active_algorithms or not active_algorithms[0].analyzer:
            return 0.0
        return active_algorithms[0].analyzer.get_global_average_delay()
    
    def get_variance(self) -> float:
        """获取已配对按键的总体方差"""
        active_algorithms = self.get_active_algorithms()
        if not active_algorithms or not active_algorithms[0].analyzer:
            return 0.0
        return active_algorithms[0].analyzer.get_variance()
    
    def get_standard_deviation(self) -> float:
        """获取已配对按键的总体标准差"""
        active_algorithms = self.get_active_algorithms()
        if not active_algorithms or not active_algorithms[0].analyzer:
            return 0.0
        return active_algorithms[0].analyzer.get_standard_deviation()
    
    def get_mean_absolute_error(self) -> float:
        """获取已配对按键的平均绝对误差（MAE）"""
        active_algorithms = self.get_active_algorithms()
        if not active_algorithms or not active_algorithms[0].analyzer:
            return 0.0
        return active_algorithms[0].analyzer.get_mean_absolute_error()
    
    def get_mean_squared_error(self) -> float:
        """获取已配对按键的均方误差（MSE）"""
        active_algorithms = self.get_active_algorithms()
        if not active_algorithms or not active_algorithms[0].analyzer:
            return 0.0
        return active_algorithms[0].analyzer.get_mean_squared_error()

    def get_root_mean_squared_error(self) -> float:
        """获取已配对按键的均方根误差（RMSE）"""
        active_algorithms = self.get_active_algorithms()
        if not active_algorithms or not active_algorithms[0].analyzer:
            return 0.0
        return active_algorithms[0].analyzer.get_root_mean_squared_error()

    def get_mean_error(self) -> float:
        """获取已匹配按键对的平均误差（ME）"""
        active_algorithms = self.get_active_algorithms()
        if not active_algorithms or not active_algorithms[0].analyzer:
            return 0.0
        return active_algorithms[0].analyzer.get_mean_error()

    def get_coefficient_of_variation(self) -> float:
        """获取已配对按键的变异系数（CV）"""
        active_algorithms = self.get_active_algorithms()
        if not active_algorithms or not active_algorithms[0].analyzer:
            return 0.0
        return active_algorithms[0].analyzer.get_coefficient_of_variation()

    def generate_delay_time_series_plot(self) -> Any:
        """生成延时时间序列图（委托给PlotService）"""
        return self.plot_service.generate_delay_time_series_plot()
    

    def generate_delay_histogram_plot(self) -> Any:
        """生成延时分布直方图（委托给PlotService）"""
        return self.plot_service.generate_delay_histogram_plot()

    def generate_offset_alignment_plot(self) -> Any:
        """生成偏移对齐分析柱状图（委托给PlotService）"""
        return self.plot_service.generate_offset_alignment_plot()

    def generate_key_delay_zscore_scatter_plot(self) -> Any:
        """生成按键与延时Z-Score标准化散点图（委托给PlotService）"""
        return self.plot_service.generate_key_delay_zscore_scatter_plot()
    
    def generate_single_key_delay_comparison_plot(self, key_id: int) -> Any:
        """生成单键多曲延时对比图（委托给PlotService）"""
        return self.plot_service.generate_single_key_delay_comparison_plot(key_id)
    
    def generate_key_delay_scatter_plot(self, only_common_keys: bool = False, selected_algorithm_names: List[str] = None) -> Any:
        """生成按键与延时的散点图（委托给PlotService）"""
        return self.plot_service.generate_key_delay_scatter_plot(only_common_keys, selected_algorithm_names)

    def generate_hammer_velocity_delay_scatter_plot(self) -> Any:
        """生成锤速与延时的散点图（委托给PlotService）"""
        return self.plot_service.generate_hammer_velocity_delay_scatter_plot()
        
    def generate_hammer_velocity_relative_delay_scatter_plot(self) -> Any:
        """生成锤速与相对延时的散点图（委托给PlotService）"""
        return self.plot_service.generate_hammer_velocity_relative_delay_scatter_plot()
    
    def generate_key_hammer_velocity_scatter_plot(self) -> Any:
        """生成按键与锤速的散点图（委托给PlotService）"""
        return self.plot_service.generate_key_hammer_velocity_scatter_plot()
    
    def generate_waterfall_plot(self, data_types: List[str] = None, key_ids: List[int] = None, key_filter=None) -> Any:
        """生成瀑布图（委托给PlotService）

        Args:
            data_types: 要显示的数据类型列表，默认显示所有类型
            key_ids: 要显示的按键ID列表，默认显示所有按键
            key_filter: 按键筛选条件
        """
        return self.plot_service.generate_waterfall_plot(data_types, key_ids, key_filter)

    def get_waterfall_key_statistics(self, data_types: List[str] = None) -> Dict[str, Any]:
        """获取瀑布图按键统计信息

        Args:
            data_types: 数据类型列表，如果为None则统计所有类型

        Returns:
            Dict[str, Any]: 包含按键统计信息的字典
                - available_keys: List[Dict] 可用按键列表，每个包含key_id, total_count, exception_count等
                - summary: Dict 总体统计信息
        """
        return self.plot_service.get_waterfall_key_statistics(data_types)
    
    
    def _find_algorithm_by_name(self, algorithm_name: str):
        """根据算法名称查找算法"""
        for alg in self.get_active_algorithms():
            if alg.metadata.algorithm_name == algorithm_name:
                return alg
        return None
    
    def _find_extreme_delay_item(self, offset_data: List[Dict], delay_type: str) -> Optional[Dict]:
        """查找极值延迟项"""
        if not offset_data:
            return None
        
        if delay_type == 'max':
            max_delay = max(item.get('keyon_offset', 0) for item in offset_data)
            items = [item for item in offset_data if item.get('keyon_offset', 0) == max_delay]
            return items[0] if items else None
        elif delay_type == 'min':
            # 与UI逻辑一致：找最后一个匹配的最小延迟项
            min_delay = min(item.get('keyon_offset', 0) for item in offset_data)
            target = None
            for item in offset_data:
                if item.get('keyon_offset', 0) == min_delay:
                    target = item
            return target
        return None
    
    def get_notes_by_delay_type(self, algorithm_name: str, delay_type: str) -> Optional[Tuple[Any, Any, int, int]]:
        """
        根据延迟类型（最大/最小）获取对应的音符
        
        Args:
            algorithm_name: 算法名称
            delay_type: 延迟类型，'max' 或 'min'
        
        Returns:
            Tuple[Note, Note, int, int]: (record_note, replay_note, record_index, replay_index) 或 None
        """
        try:
            # 查找算法
            algorithm = self._find_algorithm_by_name(algorithm_name)
            if not algorithm or not algorithm.analyzer or not algorithm.analyzer.note_matcher:
                logger.warning(f"算法 '{algorithm_name}' 不可用")
                return None
            
            note_matcher = algorithm.analyzer.note_matcher
            
            # 获取对齐数据（注意：record_index/replay_index 在此处实际存储的是 UUID）
            offset_data = note_matcher.get_offset_alignment_data()
            if not offset_data:
                logger.warning("没有匹配数据")
                return None
            
            # 查找极值项
            target_item = self._find_extreme_delay_item(offset_data, delay_type)
            if not target_item:
                logger.warning(f"未找到{delay_type}延迟项")
                return None

            # 从对齐数据中提取 UUID
            record_uuid = target_item.get('record_uuid')
            replay_uuid = target_item.get('replay_uuid')
            
            # 兼容性：如果新字段不存在，尝试回退到 record_index
            if not record_uuid: record_uuid = target_item.get('record_index')
            if not replay_uuid: replay_uuid = target_item.get('replay_index')
            
            # 通过 UUID 在匹配器中查找完整的匹配对对象
            matched = note_matcher.find_matched_pair_by_uuid(str(record_uuid), str(replay_uuid))
            if not matched:
                logger.warning(f"未找到匹配对: record_uuid={record_uuid}, replay_uuid={replay_uuid}")
                return None
            
            record_note, rep_note, match_type, error_ms = matched
            
            # 返回 Note 对象及其内部偏移量（整数索引）
            return (record_note, rep_note, record_note.offset, rep_note.offset)
            
        except Exception as e:
            logger.error(f"获取{delay_type}延迟音符失败: {e}")
            logger.error(traceback.format_exc())
            return None
    
    def generate_scatter_detail_plot_by_indices(self, record_index: int, replay_index: int) -> Any:
        """生成散点图点击的详细曲线图（委托给PlotService）"""
        return self.plot_service.generate_scatter_detail_plot_by_indices(record_index, replay_index)
    
    def generate_multi_algorithm_scatter_detail_plot_by_indices(self, algorithm_name: str, record_index: int, replay_index: int) -> Any:
        """多算法模式下生成散点图点击的详细曲线图（委托给PlotService）"""
        return self.plot_service.generate_multi_algorithm_scatter_detail_plot_by_indices(algorithm_name, record_index, replay_index)


    def generate_multi_algorithm_detail_plot_by_index(self, algorithm_name: str, index: int, is_record: bool) -> Any:
        """多算法模式下根据索引生成瀑布图点击的详细曲线图（委托给PlotService）"""
        return self.plot_service.generate_multi_algorithm_detail_plot_by_index(algorithm_name, index, is_record)
    def generate_multi_algorithm_error_detail_plot_by_index(self, algorithm_name: str, index: int, is_record: bool) -> Any:
        """多算法模式下生成错误详情的详细曲线图（委托给PlotService）"""
        return self.plot_service.generate_multi_algorithm_error_detail_plot_by_index(algorithm_name, index, is_record)
    def apply_key_filter(self, key_ids: Optional[List[int]]) -> None:
        """应用按键过滤

        Args:
            key_ids: 要过滤的按键ID列表，None表示清除过滤
        """
        if key_ids is None:
            # 清除按键过滤
            self.key_filter.set_key_filter([])
        else:
            self.key_filter.set_key_filter(key_ids)

    def get_filter_info(self) -> Dict[str, Any]:
        """获取所有过滤器的状态信息

        Returns:
            Dict包含：
            - key_filter: 按键过滤状态
            - available_keys: 可用按键列表
        """
        return {
            'key_filter': self.key_filter.get_key_filter_status(),
            'available_keys': self.key_filter.get_available_keys(),
        }
    
    # ==================== 表格数据相关方法 ====================
    
    def get_summary_info(self) -> Dict[str, Any]:
        """获取摘要信息（委托给TableDataGenerator）"""
        return self.table_data_generator.get_summary_info()
    
    def get_algorithm_statistics(self, algorithm) -> dict:
        """
        获取算法的统计信息（包含所有错误类型）

        Args:
            algorithm: 算法对象

        Returns:
            dict: 包含完整错误统计的信息
                - drop_hammers: 丢锤数
                - multi_hammers: 多锤数
                - invalid_record_notes: 录制无效音符数
                - invalid_replay_notes: 播放无效音符数
                - total_errors: 总错误数（丢锤+多锤+无效音符）
        """
        try:
            if not hasattr(algorithm, 'analyzer') or not algorithm.analyzer:
                return {
                    'drop_hammers': 0,
                    'multi_hammers': 0,
                    'invalid_record_notes': 0,
                    'invalid_replay_notes': 0,
                    'total_errors': 0
                }

            # 直接从analyzer获取错误统计
            analyzer = algorithm.analyzer

            # 锤击错误统计
            drop_hammers = len(analyzer.drop_hammers) 
            multi_hammers = len(analyzer.multi_hammers)

            # 无效音符统计
            analysis_stats = analyzer.get_analysis_stats()
            invalid_record_notes = analysis_stats.get('record_invalid_notes', 0)
            invalid_replay_notes = analysis_stats.get('replay_invalid_notes', 0)

            # 计算总错误数
            total_errors = drop_hammers + multi_hammers + invalid_record_notes + invalid_replay_notes

            result = {
                'drop_hammers': drop_hammers,
                'multi_hammers': multi_hammers,
                'invalid_record_notes': invalid_record_notes,
                'invalid_replay_notes': invalid_replay_notes,
                'total_errors': total_errors
            }
            return result

        except Exception as e:
            logger.error(f"获取算法统计信息失败: {e}")
            return {
                'drop_hammers': 0,
                'multi_hammers': 0,
                'invalid_record_notes': 0,
                'invalid_replay_notes': 0,
                'total_errors': 0
            }
    
    def get_data_overview_statistics(self, algorithm) -> dict:
        """
        获取数据概览统计信息
        
        Args:
            algorithm: 算法对象
        
        Returns:
            dict: 包含音符总数、有效音符数、匹配对数等信息
        """
        try:
            if not hasattr(algorithm, 'analyzer') or not algorithm.analyzer:
                return {
                    'total_notes': 0,
                    'valid_record_notes': 0,
                    'valid_replay_notes': 0,
                    'matched_pairs': 0,
                    'invalid_record_notes': 0,
                    'invalid_replay_notes': 0
                }
            
            # 从analyzer获取统计数据
            analyzer = algorithm.analyzer
            stats = analyzer.get_analysis_stats()
            
            # 计算有效音符数（total_record_notes 就是有效的录制音符数）
            valid_record = stats.get('total_record_notes', 0)
            valid_replay = stats.get('total_replay_notes', 0)
            invalid_record = stats.get('record_invalid_notes', 0)
            invalid_replay = stats.get('replay_invalid_notes', 0)
            
            # 音符总数 = 有效音符 + 无效音符
            total_notes = valid_record + valid_replay + invalid_record + invalid_replay
            
            result = {
                'total_notes': total_notes,
                'valid_record_notes': valid_record,
                'valid_replay_notes': valid_replay,
                'matched_pairs': stats.get('matched_pairs', 0),
                'invalid_record_notes': invalid_record,
                'invalid_replay_notes': invalid_replay
            }
            return result

        except Exception as e:
            logger.error(f"获取数据概览统计信息失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                        'total_notes': 0,
                'valid_record_notes': 0,
                'valid_replay_notes': 0,
                'matched_pairs': 0,
                'invalid_record_notes': 0,
                'invalid_replay_notes': 0
            }
    
    def get_invalid_notes_table_data(self) -> List[Dict[str, Any]]:
        """获取无效音符表格数据（委托给TableDataGenerator）"""
        return self.table_data_generator.get_invalid_notes_table_data()

    def get_invalid_notes_detail_table_data(self, data_type: str) -> List[Dict[str, Any]]:
        """获取无效音符详细列表数据（委托给TableDataGenerator）"""
        return self.table_data_generator.get_invalid_notes_detail_table_data(data_type)

    def _filter_error_data_by_algorithm(self, error_type: str, algorithm_name: str) -> List[Dict[str, Any]]:
        """根据算法名称过滤错误数据（内部辅助函数）
        
        Args:
            error_type: 错误类型 ('丢锤' 或 '多锤')
            algorithm_name: 算法名称
        
        Returns:
            List[Dict[str, Any]]: 过滤后的错误数据
        """
        all_error_data = self.table_data_generator.get_error_table_data(error_type)

        # 过滤出指定算法的数据
        filtered_data = []
        for item in all_error_data:
            if item.get('algorithm_name') == algorithm_name:
                filtered_data.append(item)

        return filtered_data

    def get_drop_hammers_detail_table_data(self, algorithm_name: str) -> List[Dict[str, Any]]:
        """获取指定算法的丢锤详细列表数据"""
        return self._filter_error_data_by_algorithm('丢锤', algorithm_name)

    def get_multi_hammers_detail_table_data(self, algorithm_name: str) -> List[Dict[str, Any]]:
        """获取指定算法的多锤详细列表数据"""
        return self._filter_error_data_by_algorithm('多锤', algorithm_name)

    # TODO
    def get_error_table_data(self, error_type: str) -> List[Dict[str, Any]]:
        """获取错误表格数据（委托给TableDataGenerator）"""
        return self.table_data_generator.get_error_table_data(error_type)
    
    
    # ==================== 延时关系分析相关方法 ====================
    def get_key_force_interaction_analysis(self) -> Dict[str, Any]:
        """
        获取按键与力度的交互效应图数据

        生成按键-力度交互效应图所需的数据，用于可视化分析按键和力度对延时的联合影响。

        统一处理所有算法：通过multi_algorithm_manager获取激活算法并生成分析结果。

        Returns:
            Dict[str, Any]: 分析结果，包含：
                - status: 状态标识
                - multi_algorithm_mode: True（始终为统一格式）
                - algorithm_results: 各算法的完整结果字典
        """
        try:
            # 获取激活的算法并生成数据
            active_algorithms = self.get_active_algorithms()

            if not active_algorithms:
                logger.warning("没有激活的算法，无法进行按键-力度交互分析")
                return {
                    'status': 'error',
                    'message': '没有激活的算法'
                }

            # 为每个算法生成分析结果
            # 使用内部的algorithm_name作为key（唯一标识，包含文件名），避免同种算法不同曲子被覆盖
            algorithm_results = {}
            for algorithm in active_algorithms:
                if not algorithm.analyzer:
                    logger.warning(f"算法 '{algorithm.metadata.algorithm_name}' 没有分析器，跳过")
                    continue
                
                # 使用内部的algorithm_name作为key（唯一标识）
                algorithm_name = algorithm.metadata.algorithm_name
                display_name = algorithm.metadata.display_name
                delay_analysis = DelayAnalysis(algorithm.analyzer)
                result = delay_analysis.analyze_key_force_interaction()
                
                if result.get('status') == 'success':
                    # 在result中添加display_name，用于UI显示
                    result['display_name'] = display_name
                    algorithm_results[algorithm_name] = result
                    logger.info(f"算法 '{display_name}' (内部: {algorithm_name}) 的按键-力度交互分析完成")
            
            if not algorithm_results:
                logger.warning("⚠️ 没有成功分析的算法")
                return {
                    'status': 'error',
                    'message': '没有成功分析的算法'
                }
                
            # 统一返回格式（不再区分单算法/多算法模式）
            logger.info(f"按键-力度交互分析完成，共 {len(algorithm_results)} 个算法")
            return {
                    'status': 'success',
                'multi_algorithm_mode': True,  # 始终使用统一格式
                    'algorithm_results': algorithm_results,
            }
        
        except Exception as e:
            logger.error(f"按键-力度交互分析失败: {e}")
            
            logger.error(traceback.format_exc())
            return {
                'status': 'error',
                'message': f'分析失败: {str(e)}'
            }
    
    
    def generate_key_force_interaction_plot(self) -> Any:
        """生成按键-力度交互效应图（委托给PlotService）"""
        return self.plot_service.generate_key_force_interaction_plot()
    def enable_multi_algorithm_mode(self, max_algorithms: Optional[int] = None) -> Tuple[bool, bool, Optional[str]]:
        """
        启用多算法对比模式（向后兼容方法，统一模式下管理器已在初始化时创建）
        
        Args:
            max_algorithms: 最大算法数量（已废弃，管理器在初始化时已创建）
            
        Returns:
            Tuple[bool, bool, Optional[str]]: (是否成功, 是否有现有数据需要迁移, 文件名)
        """
        try:
            # 注意：multi_algorithm_manager 在 __init__ 中已经初始化
            # max_algorithms 参数在统一模式下被忽略
            
            # 检查是否有现有的分析数据需要迁移
            has_existing_data = False
            existing_filename = None
            
            analyzer = self._get_current_analyzer()
            if analyzer and analyzer.note_matcher and hasattr(analyzer, 'matched_pairs') and len(analyzer.matched_pairs) > 0:
                # 有已分析的数据
                has_existing_data = True
                # 获取文件名
                data_source_info = self.get_data_source_info()
                existing_filename = data_source_info.get('filename', '未知文件')
                logger.info(f"检测到现有分析数据，文件名: {existing_filename}")
            
            return True, has_existing_data, existing_filename
            
        except Exception as e:
            logger.error(f"❌ 检查现有数据失败: {e}")
            return False, False, None
    
    def migrate_existing_data_to_algorithm(self, algorithm_name: str) -> Tuple[bool, str]:
        """
        将现有的单算法分析数据迁移到多算法模式
        
        Args:
            algorithm_name: 用户指定的算法名称
            
        Returns:
            Tuple[bool, str]: (是否成功, 错误信息)
        """
        # multi_algorithm_manager 在初始化时已创建
        
        analyzer = self._get_current_analyzer()
        if not analyzer or not analyzer.note_matcher:
            return False, "没有可迁移的分析数据"
        
        try:
            # 获取原始数据
            record_data = self.data_manager.get_record_data()
            replay_data = self.data_manager.get_replay_data()
            
            if not record_data or not replay_data:
                return False, "原始数据不存在"
            
            # 获取文件名
            data_source_info = self.get_data_source_info()
            filename = data_source_info.get('filename', '未知文件')
            
            # 生成唯一的算法名称（算法名_文件名（无扩展名））
            unique_algorithm_name = self.multi_algorithm_manager._generate_unique_algorithm_name(algorithm_name, filename)
            
            # 创建算法数据集（使用唯一名称作为内部标识，原始名称作为显示名称）
            color_index = 0
            algorithm = AlgorithmDataset(unique_algorithm_name, algorithm_name, filename, color_index)
            
            # 获取当前的分析器
            current_analyzer = self._get_current_analyzer()
            algorithm.analyzer = current_analyzer
            algorithm.record_data = record_data
            algorithm.replay_data = replay_data

            # 错误数据已经在 analyzer 中，无需额外同步
            logger.info(f"迁移算法数据: 丢锤={len(current_analyzer.drop_hammers)}, "
                       f"多锤={len(current_analyzer.multi_hammers)}")

            algorithm.metadata.status = AlgorithmStatus.READY

            # 添加到管理器
            self.multi_algorithm_manager.algorithms[unique_algorithm_name] = algorithm
            
            logger.info(f"现有数据已迁移为算法: {algorithm_name}")
            return True, ""
            
        except Exception as e:
            logger.error(f"迁移现有数据失败: {e}")
            logger.error(traceback.format_exc())
            return False, str(e)


    def get_current_analysis_mode(self) -> Tuple[str, int]:
        """
        获取当前的分析模式和活跃算法数量

        Returns:
            Tuple[str, int]: (模式名称, 活跃算法数量)
                           模式: "multi" (多算法), "single" (单算法), "none" (无数据)
        """
        # 检查活跃的多算法
        active_algorithms = []
        if self.multi_algorithm_manager:
            active_algorithms = self.get_active_algorithms()

        if active_algorithms:
            # 有活跃的多算法
            return "multi", len(active_algorithms)
        else:
            # 检查是否有单算法数据
            analyzer = self._get_current_analyzer()
            if analyzer:
                # 有单算法分析器
                return "single", 1
            else:
                # 两者都没有
                return "none", 0

    def has_active_multi_algorithm_data(self) -> bool:
        """检查是否有活跃的多算法数据"""
        if self.multi_algorithm_manager:
            active_algorithms = self.get_active_algorithms()
            return len(active_algorithms) > 0
        return False

    def has_single_algorithm_data(self) -> bool:
        """检查是否有单算法数据"""
        analyzer = self._get_current_analyzer()
        return analyzer is not None
    
    async def add_algorithm(self, algorithm_name: str, filename: str, 
                           contents: bytes) -> Tuple[bool, str]:
        """
        添加算法到多算法管理器（异步）
        
        Args:
            algorithm_name: 算法名称（用户指定）
            filename: 文件名
            contents: 文件内容（二进制数据）
            
        Returns:
            Tuple[bool, str]: (是否成功, 错误信息)
        """
        # multi_algorithm_manager 在初始化时已创建
        
        try:
            # 加载SPMID数据
            from .spmid_loader import SPMIDLoader
            loader = SPMIDLoader()
            success = loader.load_spmid_data(contents)
            
            if not success:
                return False, "SPMID文件解析失败"
            
            # 获取数据
            record_data = loader.get_record_data()
            replay_data = loader.get_replay_data()
            
            if not record_data or not replay_data:
                return False, "数据为空"
            
            # 异步添加算法
            success, error_msg = await self.multi_algorithm_manager.add_algorithm_async(
                algorithm_name, filename, record_data, replay_data
            )

            return success, error_msg
            
        except Exception as e:
            logger.error(f"添加算法失败: {e}")
            
            logger.error(traceback.format_exc())
            return False, str(e)
    
    def remove_algorithm(self, algorithm_name: str) -> bool:
        """
        从多算法管理器中移除算法

        Args:
            algorithm_name: 算法名称

        Returns:
            bool: 是否成功
        """
        if not self.multi_algorithm_manager:
            return False

        return self.multi_algorithm_manager.remove_algorithm(algorithm_name)
    
    def get_all_algorithms(self) -> List[Dict[str, Any]]:
        """
        获取所有算法的信息列表
        
        Returns:
            List[Dict[str, Any]]: 算法信息列表
        """
        if not self.multi_algorithm_manager:
            return []
        
        algorithms = []
        for alg in self.multi_algorithm_manager.get_all_algorithms():
            # 确保is_active有值，如果为None则默认为True（新上传的文件应该默认显示）
            is_active = alg.is_active if alg.is_active is not None else True
            if alg.is_active is None:
                alg.is_active = True
                logger.info(f"✅ 确保算法 '{alg.metadata.algorithm_name}' 默认显示: is_active={is_active}")
            
            algorithms.append({
                'algorithm_name': alg.metadata.algorithm_name,  # 内部唯一标识（用于查找）
                'display_name': alg.metadata.display_name,  # 显示名称（用于UI显示）
                'filename': alg.metadata.filename,
                'status': alg.metadata.status.value,
                'is_active': is_active,
                'color': alg.color,
                'is_ready': alg.is_ready()
            })
        
        return algorithms
    
    def get_key_matched_pairs_by_algorithm(self, algorithm_name: str, key_id: int) -> List[Tuple[int, int, Any, Any, float]]:
        """
        获取指定算法和按键ID的所有匹配对，按时间戳排序

        Args:
            algorithm_name: 算法名称
            key_id: 按键ID

        Returns:
            List[Tuple[int, int, Note, Note, float]]: 匹配对列表，每个元素为(record_index, replay_index, record_note, replay_note, record_keyon)
        """
        if not self.multi_algorithm_manager:
            return []

        # 根据 display_name 查找算法
        algorithm = None
        for alg in self.multi_algorithm_manager.get_all_algorithms():
            if alg.metadata.display_name == algorithm_name:
                algorithm = alg
                break

        if not algorithm or not algorithm.is_ready() or not algorithm.analyzer:
            return []

        matched_pairs = algorithm.analyzer.matched_pairs if hasattr(algorithm.analyzer, 'matched_pairs') else []
        if not matched_pairs:
            return []

        # 获取偏移对齐数据以获取时间戳
        offset_data = algorithm.analyzer.get_offset_alignment_data()
        offset_map = {}
        for item in offset_data:
            record_idx = item.get('record_index')
            replay_idx = item.get('replay_index')
            if record_idx is not None and replay_idx is not None:
                offset_map[(record_idx, replay_idx)] = item.get('record_keyon', 0)

        # 筛选指定按键ID的匹配对
        key_pairs = []
        for record_idx, replay_idx, record_note, replay_note in matched_pairs:
            if record_note.id == key_id:
                record_keyon = offset_map.get((record_idx, replay_idx), 0)
                key_pairs.append((record_idx, replay_idx, record_note, replay_note, record_keyon))

        # 按时间戳排序
        key_pairs.sort(key=lambda x: x[4])

        return key_pairs
    
    def get_active_algorithms(self) -> List[AlgorithmDataset]:
        """
        获取激活的算法列表（用于对比显示）
        
        Returns:
            List[AlgorithmDataset]: 激活的算法列表
        """
        if not self.multi_algorithm_manager:
            return []
        
        return self.multi_algorithm_manager.get_active_algorithms()
    
    def toggle_algorithm(self, algorithm_name: str) -> bool:
        """
        切换算法的显示/隐藏状态
        
        Args:
            algorithm_name: 算法名称
            
        Returns:
            bool: 是否成功
        """
        if not self.multi_algorithm_manager:
            return False
        
        return self.multi_algorithm_manager.toggle_algorithm(algorithm_name)
    
    def rename_algorithm(self, old_name: str, new_name: str) -> bool:
        """
        重命名算法
        
        Args:
            old_name: 旧名称
            new_name: 新名称
            
        Returns:
            bool: 是否成功
        """
        if not self.multi_algorithm_manager:
            return False
        
        return self.multi_algorithm_manager.rename_algorithm(old_name, new_name)
    
    def get_multi_algorithm_statistics(self) -> Dict[str, Any]:
        """
        获取多算法对比统计信息
        
        Returns:
            Dict[str, Any]: 对比统计信息
        """
        if not self.multi_algorithm_manager:
            return {}
        
        return self.multi_algorithm_manager.get_comparison_statistics()
    
    def generate_relative_delay_distribution_plot(self) -> Any:
        """生成同种算法不同曲子的相对延时分布图（委托给PlotService）"""
        return self.plot_service.generate_relative_delay_distribution_plot()

    def get_delay_metrics(self, algorithm=None) -> Dict[str, Any]:
        """
        获取延时误差统计指标

        Args:
            algorithm: 指定算法（用于多算法模式下的单算法查询）

        Returns:
            Dict[str, Any]: 包含延时误差统计指标的数据
        """
        try:
            # 如果指定了算法，使用该算法的数据
            if algorithm:
                if algorithm.analyzer and algorithm.analyzer.note_matcher:
                    delay_metrics = algorithm.analyzer.note_matcher._get_delay_metrics()
                    return delay_metrics.get_all_metrics()
                else:
                    return {'error': f'算法 {algorithm} 没有有效的分析器'}

            # 单算法模式
            if self.analyzer and self.analyzer.note_matcher:
                delay_metrics = self.analyzer.note_matcher._get_delay_metrics()
                return delay_metrics.get_all_metrics()
            else:
                return {'error': '没有有效的分析器'}

        except Exception as e:
            logger.error(f"获取延时误差统计指标失败: {e}")
            return {'error': str(e)}

    def get_graded_error_stats(self, algorithm=None) -> Dict[str, Any]:
        """
        获取分级误差统计数据

        Args:
            algorithm: 指定算法（用于多算法模式下的单算法查询）

        Returns:
            Dict[str, Any]: 包含各级别误差统计的数据
        """
        from utils.constants import GRADE_LEVELS
        
        try:
            # 如果指定了算法，使用该算法的数据
            if algorithm:
                if algorithm.analyzer and algorithm.analyzer.note_matcher:
                    return algorithm.analyzer.note_matcher.get_graded_error_stats()
                else:
                    return {'error': f'算法 {algorithm} 没有有效的分析器'}

            # 获取激活的算法并生成数据
            active_algorithms = self.get_active_algorithms()

            if not active_algorithms:
                return {'error': '没有激活的算法'}

            is_multi_algorithm = len(active_algorithms) > 1

            # 多算法模式：汇总所有激活算法的评级统计
            if is_multi_algorithm:
                # 动态初始化
                total_stats = {level: {'count': 0, 'percent': 0.0} for level in GRADE_LEVELS}

                total_count = 0
                for algorithm in active_algorithms:
                    if algorithm.analyzer and algorithm.analyzer.note_matcher:
                        alg_stats = algorithm.analyzer.note_matcher.get_graded_error_stats()
                        if alg_stats and 'error' not in alg_stats:
                            for level in GRADE_LEVELS:
                                if level in alg_stats:
                                    total_stats[level]['count'] += alg_stats[level].get('count', 0)
                                    total_count += alg_stats[level].get('count', 0)

                # 计算百分比，确保总和为100%（保留4位小数）
                if total_count > 0:
                    raw_percentages = {}
                    for level in GRADE_LEVELS:
                        raw_percentages[level] = (total_stats[level]['count'] / total_count) * 100.0

                    rounded_percentages = {}
                    for level in GRADE_LEVELS:
                        rounded_percentages[level] = round(raw_percentages[level], 4)

                    total_rounded = sum(rounded_percentages.values())
                    if total_rounded != 100.0:
                        max_level = max(rounded_percentages.keys(), key=lambda x: rounded_percentages[x])
                        rounded_percentages[max_level] += (100.0 - total_rounded)

                    for level in GRADE_LEVELS:
                        total_stats[level]['percent'] = rounded_percentages[level]

                return total_stats

            # 单算法模式
            else:
                single_algorithm = active_algorithms[0]
                if not single_algorithm.analyzer or not single_algorithm.analyzer.note_matcher:
                    return {'error': '算法没有有效的分析器或音符匹配器'}

                return single_algorithm.analyzer.note_matcher.get_graded_error_stats()

        except Exception as e:
            logger.error(f"获取分级误差统计失败: {e}")
            return {'error': str(e)}
