#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
重构后的钢琴分析后端API
使用模块化架构，将原来的大类拆分为多个专门的模块
"""

import os
import tempfile
import traceback
import hashlib
import json
import pandas as pd
import numpy as np
from typing import Optional, Tuple, Dict, Any, List, Union
from collections import defaultdict
from plotly.graph_objects import Figure
from utils.logger import Logger

# Dash UI imports for report generation
import dash_bootstrap_components as dbc
from dash import html

# SPMID相关导入
import spmid
from spmid.spmid_analyzer import SPMIDAnalyzer
import spmid.spmid_plot as spmid

# 导入各个模块
from .data_manager import DataManager
from .plot_generator import PlotGenerator
from .data_filter import DataFilter
from .time_filter import TimeFilter
from .table_data_generator import TableDataGenerator
from .history_manager import HistoryManager
from .delay_analysis import DelayAnalysis
from .multi_algorithm_manager import MultiAlgorithmManager, AlgorithmDataset, AlgorithmStatus
from .force_curve_analyzer import ForceCurveAnalyzer

logger = Logger.get_logger()


# 统一统计服务类
class AlgorithmStatistics:
    """算法统计服务 - 统一处理准确率和错误计算"""

    def __init__(self, algorithm):
        self.algorithm = algorithm
        self._cache = {}  # 计算结果缓存

    def get_accuracy_info(self) -> dict:
        """获取准确率相关信息"""
        # 检查数据是否已经准备好（是否有匹配结果）
        note_matcher = getattr(getattr(self.algorithm, 'analyzer', None), 'note_matcher', None)
        has_match_data = (note_matcher and
                hasattr(note_matcher, 'match_results') and
                len(getattr(note_matcher, 'match_results', [])) > 0)

        if not has_match_data:
            # 数据还没有准备好，清除缓存并返回空数据
            self._cache.pop('accuracy_info', None)
            return {
                'accuracy': 0.0,
                'matched_count': 0,
                'total_effective_keys': 0,
                'precision_matches': 0,
                'approximate_matches': 0
            }

        if 'accuracy_info' not in self._cache:
            self._cache['accuracy_info'] = self._calculate_accuracy_info()
        return self._cache['accuracy_info']

    def get_error_info(self) -> dict:
        """获取错误统计信息"""
        # 检查数据是否已经准备好
        note_matcher = getattr(getattr(self.algorithm, 'analyzer', None), 'note_matcher', None)
        has_match_data = (note_matcher and
                         hasattr(note_matcher, 'match_results') and
                         len(getattr(note_matcher, 'match_results', [])) > 0)

        if not has_match_data:
            # 数据还没有准备好，清除缓存并返回空数据
            self._cache.pop('error_info', None)
            return {
                'drop_count': 0,
                'multi_count': 0,
                'silent_count': 0
            }

        if 'error_info' not in self._cache:
            self._cache['error_info'] = self._calculate_error_info()
        return self._cache['error_info']

    def get_full_statistics(self) -> dict:
        """获取完整的统计信息"""
        accuracy_info = self.get_accuracy_info()
        error_info = self.get_error_info()

        return {
            **accuracy_info,
            **error_info,
            'total_errors': error_info['drop_count'] + error_info['multi_count']
        }

    def _calculate_accuracy_info(self) -> dict:
        """计算准确率相关信息"""
        # 分母：总有效按键数
        total_effective_keys = self._get_total_effective_keys()

        if total_effective_keys == 0:
            return {
                'accuracy': 0.0,
                'matched_count': 0,
                'total_effective_keys': 0,
                'precision_matches': 0,
                'approximate_matches': 0
            }

        # 使用匹配质量评级统计中的总匹配对数，确保数据源一致
        note_matcher = getattr(self.algorithm.analyzer, 'note_matcher', None)
        if note_matcher and hasattr(note_matcher, 'get_graded_error_stats'):
            graded_stats = note_matcher.get_graded_error_stats()
            total_matched_count = graded_stats.get('total_successful_matches', 0)
        else:
            total_matched_count = 0

        # 分子：匹配的音符总数（每个匹配对包含2个音符）
        # 注意：只计算成功匹配的音符，不包括失败匹配
        matched_keys_count = total_matched_count * 2

        # 准确率计算
        # 准确率 = (成功匹配的音符数 / 总有效音符数) * 100
        # 每个匹配对包含2个音符（1个录制 + 1个播放）
        accuracy = (matched_keys_count / total_effective_keys) * 100 if total_effective_keys > 0 else 0.0

        # 调试信息
        logger.debug(f"准确率计算: matched_keys_count={matched_keys_count}, total_effective_keys={total_effective_keys}, accuracy={accuracy:.2f}%")
        logger.debug(f"total_matched_count={total_matched_count}, matched_keys_count={matched_keys_count}")

        # 获取匹配统计信息（用于其他用途）
        # 注意：现在stats不再包含failed_matches，所以我们从match_statistics获取兼容字段
        match_stats = self.algorithm.analyzer.match_statistics
        precision_matches = getattr(match_stats, 'precision_matches', 0)
        approximate_matches = getattr(match_stats, 'approximate_matches', 0)

        return {
            'accuracy': accuracy,
            'matched_count': total_matched_count,  # 返回总匹配对数
            'total_effective_keys': total_effective_keys,
            'precision_matches': precision_matches,
            'approximate_matches': approximate_matches
        }

    def _format_error_note_time(self, error_info, data_list, data_type: str) -> str:
        """格式化错误音符的时间信息

        Args:
            error_info: 错误信息对象
            data_list: 原始数据列表
            data_type: 数据类型 ('record' 或 'replay')

        Returns:
            str: 格式化的时间信息
        """
        # 基础时间信息
        time_info = f"keyOn={error_info.keyOn/10:.2f}ms, keyOff={error_info.keyOff/10:.2f}ms"

        # 如果有原始数据，计算更精确的时间
        if error_info.index < len(data_list):
            note = data_list[error_info.index]
            if hasattr(note, 'after_touch') and note.after_touch is not None and len(note.after_touch.index) > 0:
                key_on = (note.after_touch.index[0] + note.offset) / 10.0
                key_off = (note.after_touch.index[-1] + note.offset) / 10.0
                time_info = f"按下={key_on:.2f}ms, 释放={key_off:.2f}ms"

        return time_info

    def _log_error_details(self, error_notes, error_type: str, data_list, data_type: str):
        """记录错误详情信息

        Args:
            error_notes: 错误音符列表
            error_type: 错误类型 ('丢锤' 或 '多锤')
            data_list: 原始数据列表
            data_type: 数据类型 ('record' 或 'replay')
        """
        if not error_notes:
            return

        logger.info(f"{error_type}按键详细信息:")
        for i, error_note in enumerate(error_notes):
            if len(error_note.infos) > 0:
                error_info = error_note.infos[0]
                time_info = self._format_error_note_time(error_info, data_list, data_type)
                logger.info(f"{error_type}{i+1}: 按键ID={error_info.keyId}, 索引={error_info.index}, {time_info}")

    def _calculate_error_info(self) -> dict:
        """计算错误统计信息"""
        # 直接使用analyzer中已计算的错误数据，保持与表格显示一致
        drop_hammers = getattr(self.algorithm.analyzer, 'drop_hammers', [])
        multi_hammers = getattr(self.algorithm.analyzer, 'multi_hammers', [])

        logger.info(f"统计数据源检查: analyzer.drop_hammers={len(drop_hammers)}, analyzer.multi_hammers={len(multi_hammers)}")

        # 获取原始数据用于详细信息显示
        initial_valid_record_data = getattr(self.algorithm.analyzer, 'initial_valid_record_data', [])
        initial_valid_replay_data = getattr(self.algorithm.analyzer, 'initial_valid_replay_data', [])

        # 详细记录错误信息
        self._log_error_details(drop_hammers, "丢锤", initial_valid_record_data, "record")
        self._log_error_details(multi_hammers, "多锤", initial_valid_replay_data, "replay")

        logger.info(f"统计概览: 丢锤={len(drop_hammers)}个, 多锤={len(multi_hammers)}个")

        return {
            'drop_hammers': drop_hammers,
            'multi_hammers': multi_hammers,
            'drop_count': len(drop_hammers),
            'multi_count': len(multi_hammers)
        }

    def _get_total_effective_keys(self) -> int:
        """获取总有效按键数"""
        initial_valid_record = getattr(self.algorithm.analyzer, 'initial_valid_record_data', None)
        initial_valid_replay = getattr(self.algorithm.analyzer, 'initial_valid_replay_data', None)

        total_valid_record = len(initial_valid_record) if initial_valid_record else 0
        total_valid_replay = len(initial_valid_replay) if initial_valid_replay else 0

        total_keys = total_valid_record + total_valid_replay
        logger.debug(f"总有效按键数: record={total_valid_record}, replay={total_valid_replay}, total={total_keys}")
        return total_keys


class PianoAnalysisBackend:
    """钢琴分析后端主类 - 统一管理单算法和多算法分析流程"""

    # 常用错误消息常量
    ERROR_NO_ANALYZER = "没有分析器"
    ERROR_NO_MATCHER = "没有分析器或匹配器"
    ERROR_NO_DATA = "没有数据"
    ERROR_NO_PRECISION_DATA = "无精确匹配数据（≤50ms）"
    ERROR_ANALYSIS_FAILED = "分析失败"

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
        self.data_filter = DataFilter()
        self.plot_generator = PlotGenerator(self.data_filter)
        self.time_filter = TimeFilter()
        self.table_generator = TableDataGenerator()

        # 初始化多算法图表生成器（复用实例，避免重复初始化）
        from backend.multi_algorithm_plot_generator import MultiAlgorithmPlotGenerator
        self.multi_algorithm_plot_generator = MultiAlgorithmPlotGenerator(self.data_filter)

        # 初始化力度曲线分析器
        self.force_curve_analyzer = ForceCurveAnalyzer()
        
        # 使用全局的历史管理器实例
        self.history_manager = history_manager
        
        # 初始化延时分析器（延迟初始化，因为需要analyzer）
        self.delay_analysis = None
        
        # ==================== 多算法管理器 ====================
        # 多算法管理器（延迟初始化，用于管理多个算法的数据）
        self.multi_algorithm_manager: Optional[MultiAlgorithmManager] = None
        
        logger.info(f"PianoAnalysisBackend初始化完成 (Session: {session_id})")


    # ==================== 数据管理相关方法 ====================
    
    def clear_data_state(self) -> None:
        """清理所有数据状态"""
        self.data_manager.clear_data_state()
        self.plot_generator.set_data()
        self.data_filter.set_data(None, None)
        self.table_generator.set_data()
        
        # 清理多算法管理器
        if self.multi_algorithm_manager:
            self.multi_algorithm_manager.clear_all()

        # 清除上传状态，允许重新上传同一文件
        self._last_upload_content = None
        self._last_upload_time = None
        self._last_selected_history_id = None
        self._last_history_time = None

        logger.info("✅ 所有数据状态已清理")
    
    def _get_algorithms_to_analyze(self) -> List[Any]:
        """
        获取需要分析的算法列表

        Returns:
            List[AlgorithmDataset]: 需要分析的算法列表
        """
        # 获取激活的算法，如果没有则创建单算法数据集
        if self.multi_algorithm_manager:
            active_algorithms = self.multi_algorithm_manager.get_active_algorithms() if self.multi_algorithm_manager else []
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
        # 确保multi_algorithm_manager存在
        self._ensure_multi_algorithm_manager()

        # 查找现有的单算法
        active_algorithms = self.multi_algorithm_manager.get_active_algorithms()
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

            # 创建分析器
            from spmid.spmid_analyzer import SPMIDAnalyzer
            analyzer = SPMIDAnalyzer()

            # 执行分析
            success = analyzer.analyze(record_data, replay_data)

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
            active_algorithms = self.multi_algorithm_manager.get_active_algorithms()
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

    def process_file_upload(self, contents, filename):
        """
        处理文件上传 - 统一的文件上传入口

        Args:
            contents: 上传文件的内容（base64编码）
            filename: 上传文件的文件名

        Returns:
            tuple: (info_content, error_content, error_msg)
        """
        # 使用统一的上传管理器处理
        from backend.upload_manager import UploadManager
        upload_manager = UploadManager(self)
        return upload_manager.process_upload(contents, filename)

    def process_spmid_upload(self, contents, filename):
        """
        处理SPMID文件上传并执行完整分析流程

        Args:
            contents: 文件内容（二进制数据）
            filename: 文件名

        Returns:
            tuple: (success, result_data, error_msg)
        """
        try:
            # 使用上传管理器处理文件
            from backend.upload_manager import UploadManager
            upload_manager = UploadManager(self)
            success, result_data, error_msg = upload_manager.process_upload(contents, filename)

            if not success:
                return success, result_data, error_msg

            # 执行数据分析
            self.analyze_data()

            return True, result_data, None

        except Exception as e:
            logger.error(f"SPMID文件处理异常: {e}")
            return False, None, f"处理异常: {str(e)}"

    def analyze_data(self) -> bool:
        """
        执行完整的数据分析流程（统一单算法和多算法模式）

        Returns:
            bool: 分析是否成功
        """
        try:
            logger.info("开始数据分析流程")

            # 获取需要分析的算法列表
            algorithms_to_analyze = self._get_algorithms_to_analyze()

            if not algorithms_to_analyze:
                logger.error("没有需要分析的算法")
                return False

            # 对每个算法执行分析
            success_count = 0
            for algorithm in algorithms_to_analyze:
                if self._analyze_single_algorithm(algorithm):
                    success_count += 1
                    logger.info(f"算法 '{algorithm.metadata.algorithm_name}' 分析成功")
                else:
                    logger.error(f"算法 '{algorithm.metadata.algorithm_name}' 分析失败")

            if success_count == len(algorithms_to_analyze):
                logger.info(f"数据分析完成，共分析 {success_count} 个算法")
                return True
            else:
                logger.error(f"数据分析部分失败，成功 {success_count}/{len(algorithms_to_analyze)} 个算法")
                return False

        except Exception as e:
            logger.error(f"数据分析异常: {e}")
            logger.error(traceback.format_exc())
            return False

    def generate_report_content(self):
        """
        生成报告内容（用于单算法模式）

        Returns:
            html.Div: 报告内容
        """
        try:
            from ui.layout_components import create_report_layout
            return create_report_layout(self)
        except Exception as e:
            logger.error(f"生成报告内容失败: {e}")
            logger.error(traceback.format_exc())
            return html.Div([
                dbc.Alert(f"报告生成失败: {str(e)}", color="danger")
            ])


    def process_history_selection(self, history_id):
        """
        处理历史记录选择 - 统一的历史记录入口
        
        Args:
            history_id: 历史记录ID
            
        Returns:
            tuple: (success, result_data, error_msg)
        """
        return self.history_manager.process_history_selection(history_id, self)
    
    def load_spmid_data(self, spmid_bytes: bytes) -> bool:
        """
        加载SPMID数据
        
        Args:
            spmid_bytes: SPMID文件字节数据
            
        Returns:
            bool: 是否加载成功
        """
        try:
            # 使用数据管理器加载数据
            success = self.data_manager.load_spmid_data(spmid_bytes)
            
            if success:
                # 同步数据到各个模块
                self._sync_data_to_modules()
                logger.info("SPMID数据加载成功")
            else:
                logger.error("SPMID数据加载失败")
            
            return success
            
        except Exception as e:
            logger.error(f"SPMID数据加载异常: {e}")
            return False
            
    def _sync_data_to_modules(self) -> None:
        """同步数据到各个模块"""
        # 获取有效数据
        valid_record_data = self.data_manager.get_valid_record_data()
        valid_replay_data = self.data_manager.get_valid_replay_data()
        
        # 同步到各个模块
        current_analyzer = self._get_current_analyzer()
        self.plot_generator.set_data(valid_record_data, valid_replay_data, analyzer=current_analyzer)
        self.data_filter.set_data(valid_record_data, valid_replay_data)
        self.time_filter.set_data(valid_record_data, valid_replay_data)
        
        # 同步分析结果到各个模块
        self._sync_analysis_results()
    
    def _extract_analysis_results(self, analyzer) -> Dict[str, Any]:
        """提取分析结果数据"""
        # 获取分析结果
        multi_hammers = getattr(analyzer, 'multi_hammers', [])
        drop_hammers = getattr(analyzer, 'drop_hammers', [])
        silent_hammers = getattr(analyzer, 'silent_hammers', [])
        invalid_notes_table_data = getattr(analyzer, 'invalid_notes_table_data', {})
        matched_pairs = getattr(analyzer, 'matched_pairs', [])

        # 合并所有错误音符
        all_error_notes = multi_hammers + drop_hammers + silent_hammers

        return {
            'multi_hammers': multi_hammers,
            'drop_hammers': drop_hammers,
            'silent_hammers': silent_hammers,
            'invalid_notes_table_data': invalid_notes_table_data,
            'matched_pairs': matched_pairs,
            'all_error_notes': all_error_notes
        }

    def _prepare_error_data(self, analyzer, analysis_data: Dict[str, Any]) -> None:
        """准备错误数据，确保analyzer对象有必要的属性"""
        multi_hammers = analysis_data['multi_hammers']
        drop_hammers = analysis_data['drop_hammers']
        silent_hammers = analysis_data['silent_hammers']
        all_error_notes = analysis_data['all_error_notes']

        # 确保analyzer对象有这些属性（供瀑布图生成器使用）
        analyzer.drop_hammers = drop_hammers
        analyzer.multi_hammers = multi_hammers
        analyzer.silent_hammers = silent_hammers
        logger.info(f"设置analyzer错误数据: 丢锤={len(drop_hammers)}, 多锤={len(multi_hammers)}")

        # 设置all_error_notes属性供UI层使用
        self.all_error_notes = all_error_notes

    def _sync_analysis_data_to_modules(self, analysis_data: Dict[str, Any]) -> None:
        """同步分析数据到各个模块"""
        multi_hammers = analysis_data['multi_hammers']
        drop_hammers = analysis_data['drop_hammers']
        silent_hammers = analysis_data['silent_hammers']
        invalid_notes_table_data = analysis_data['invalid_notes_table_data']
        matched_pairs = analysis_data['matched_pairs']
        all_error_notes = analysis_data['all_error_notes']

        # 获取有效数据
        valid_record_data = self.data_manager.get_valid_record_data()
        valid_replay_data = self.data_manager.get_valid_replay_data()

        # 同步到各个模块
        self.data_filter.set_data(valid_record_data, valid_replay_data)
        self.plot_generator.set_data(valid_record_data, valid_replay_data, matched_pairs, analyzer=self._get_current_analyzer())
        self.time_filter.set_data(valid_record_data, valid_replay_data)

        logger.info(f"同步错误数据到table_generator: 丢锤={len(drop_hammers)}, 多锤={len(multi_hammers)}")

        self.table_generator.set_data(
            valid_record_data=valid_record_data,
            valid_replay_data=valid_replay_data,
            multi_hammers=multi_hammers,
            drop_hammers=drop_hammers,
            silent_hammers=silent_hammers,
            all_error_notes=all_error_notes,
            invalid_notes_table_data=invalid_notes_table_data,
            matched_pairs=matched_pairs,
            analyzer=self._get_current_analyzer()
        )

    def _validate_sync(self, analyzer) -> bool:
        """验证数据同步是否成功"""
        if hasattr(analyzer, 'drop_hammers'):
            drop_hammers_count = len(analyzer.drop_hammers)
            multi_hammers_count = len(getattr(analyzer, 'multi_hammers', []))
            logger.info(f"analyzer错误数据同步验证: 丢锤={drop_hammers_count}, 多锤={multi_hammers_count}")
            return True
        else:
            logger.warning("analyzer错误数据同步失败：drop_hammers属性不存在")
            return False

    def _log_sync_details(self, analyzer) -> None:
        """记录同步统计信息"""
        drop_hammers_count = len(getattr(analyzer, 'drop_hammers', []))
        multi_hammers_count = len(getattr(analyzer, 'multi_hammers', []))
        silent_hammers_count = len(getattr(analyzer, 'silent_hammers', []))

        # 输出简洁的错误统计汇总
        total_errors = drop_hammers_count + multi_hammers_count + silent_hammers_count
        if total_errors > 0:
            logger.info(f"错误统计: 丢锤={drop_hammers_count}, 多锤={multi_hammers_count}, 静音={silent_hammers_count}, 总计={total_errors}")

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
            if self._validate_sync(analyzer):
                # 记录同步详情
                self._log_sync_details(analyzer)

            logger.info("分析结果同步完成")

        except Exception as e:
            logger.error(f"同步分析结果失败: {e}")
    
    def get_global_average_delay(self) -> float:
        """
        获取整首曲子的平均时延（基于已配对数据）

        Returns:
            float: 平均时延（0.1ms单位）
        """
        analyzer = self._get_current_analyzer()
        if not analyzer:
            return 0.0

        # 保持内部单位为0.1ms，由UI层负责显示时换算为ms
        average_delay_0_1ms = analyzer.get_global_average_delay()
        return average_delay_0_1ms
    
    def get_variance(self) -> float:
        """
        获取已配对按键的总体方差

        Returns:
            float: 总体方差（(0.1ms)²单位）
        """
        analyzer = self._get_current_analyzer()
        if not analyzer:
            return 0.0

        variance_0_1ms_squared = analyzer.get_variance()
        return variance_0_1ms_squared
    
    def get_standard_deviation(self) -> float:
        """
        获取已配对按键的总体标准差

        Returns:
            float: 总体标准差（0.1ms单位）
        """
        analyzer = self._get_current_analyzer()
        if not analyzer:
            return 0.0

        std_0_1ms = analyzer.get_standard_deviation()
        return std_0_1ms
    
    def get_mean_absolute_error(self) -> float:
        """
        获取已配对按键的平均绝对误差（MAE）

        Returns:
            float: 平均绝对误差（0.1ms单位）
        """
        analyzer = self._get_current_analyzer()
        if not analyzer:
            return 0.0

        mae_0_1ms = analyzer.get_mean_absolute_error()
        return mae_0_1ms
    
    def get_mean_squared_error(self) -> float:
        """
        获取已配对按键的均方误差（MSE）

        Returns:
            float: 均方误差（(0.1ms)²单位）
        """
        analyzer = self._get_current_analyzer()
        if not analyzer:
            return 0.0

        mse_0_1ms_squared = analyzer.get_mean_squared_error()
        return mse_0_1ms_squared

    def get_root_mean_squared_error(self) -> float:
        """
        获取已配对按键的均方根误差（RMSE）

        Returns:
            float: 均方根误差（0.1ms单位）
        """
        analyzer = self._get_current_analyzer()
        if not analyzer:
            return 0.0

        rmse_0_1ms = analyzer.get_root_mean_squared_error()
        return rmse_0_1ms

    def get_mean_error(self) -> float:
        """
        获取已匹配按键对的平均误差（ME）

        Returns:
            float: 平均误差ME（0.1ms单位）
        """
        analyzer = self._get_current_analyzer()
        if not analyzer:
            return 0.0

        me_0_1ms = analyzer.get_mean_error()
        return me_0_1ms

    def get_coefficient_of_variation(self) -> float:
        """
        获取已配对按键的变异系数（Coefficient of Variation, CV）

        Returns:
            float: 变异系数（百分比，例如 15.5 表示 15.5%）
        """
        analyzer = self._get_current_analyzer()
        if not analyzer:
            return 0.0

        cv = analyzer.get_coefficient_of_variation()
        return cv
    
    def _get_delay_time_series_raw_data(self) -> Optional[List[Dict[str, Any]]]:
        """
        获取延时时间序列图的原始数据

        Returns:
            Optional[List[Dict[str, Any]]]: 精确匹配数据列表，如果获取失败返回None
        """
        try:
            analyzer = self._get_current_analyzer()
            if not analyzer or not analyzer.note_matcher:
                logger.warning("[WARNING] 没有分析器或音符匹配器，无法获取数据")
                return None

            offset_data = analyzer.note_matcher.get_precision_offset_alignment_data()
            logger.info(f"[DEBUG] 获取到精确匹配数据: {len(offset_data)} 条记录")

            if not offset_data:
                logger.warning("[WARNING] 无精确匹配数据（≤50ms）")
                return None

            return offset_data

        except Exception as e:
            logger.error(f"[ERROR] 获取延时时间序列原始数据失败: {e}")
            return None

    def _process_delay_time_series_data(self, offset_data: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        """
        处理和过滤延时时间序列数据

        Args:
            offset_data: 原始偏移数据

        Returns:
            Optional[List[Dict[str, Any]]]: 处理后的数据点列表，按时间排序
        """
        data_points = []  # 存储所有数据点，用于排序
        skipped_count = 0

        for i, item in enumerate(offset_data):
            record_keyon = item.get('record_keyon')  # 单位：0.1ms
            keyon_offset = item.get('keyon_offset')  # 单位：0.1ms
            key_id = item.get('key_id')
            record_index = item.get('record_index')
            replay_index = item.get('replay_index')
            record_velocity = item.get('record_velocity')
            replay_velocity = item.get('replay_velocity')
            velocity_diff = item.get('velocity_diff')
            relative_delay = item.get('relative_delay')

            # 检查必要字段是否存在且不为None
            if record_keyon is None or keyon_offset is None:
                logger.debug(f"[DEBUG] 跳过第{i}条记录: record_keyon或keyon_offset为None")
                skipped_count += 1
                continue

            # 检查时间和偏移量是否有效（为有效数字）
            if not isinstance(record_keyon, (int, float)):
                logger.debug(f"[DEBUG] 跳过第{i}条记录: record_keyon无效 ({record_keyon})")
                skipped_count += 1
                continue
            if not isinstance(keyon_offset, (int, float)):
                logger.debug(f"[DEBUG] 跳过第{i}条记录: keyon_offset无效 ({keyon_offset})")
                skipped_count += 1
                continue

            # 转换为ms单位
            time_ms = record_keyon / 10.0
            delay_ms = keyon_offset / 10.0

            data_points.append({
                'time': time_ms,
                'delay': delay_ms,
                'relative_delay': relative_delay,
                'record_velocity': record_velocity,
                'replay_velocity': replay_velocity,
                'velocity_diff': velocity_diff,
                'key_id': key_id if key_id is not None else 'N/A',
                'record_index': record_index,
                'replay_index': replay_index
            })

        logger.info(f"[DEBUG] 数据处理完成: 原始数据 {len(offset_data)} 条, 有效数据点 {len(data_points)} 条, 跳过 {skipped_count} 条")

        if not data_points:
            logger.warning("[WARNING] 无有效时间序列数据")
            return None

        # 按时间排序，确保按时间顺序显示
        data_points.sort(key=lambda x: x['time'])
        return data_points

    def _calculate_relative_delays(self, data_points: List[Dict[str, Any]]) -> Tuple[List[float], float]:
        """
        计算相对延时数据

        Args:
            data_points: 排序后的数据点列表

        Returns:
            Tuple[List[float], float]: (相对延时列表, 平均延时ms)
        """
        # 计算平均延时（用于计算相对延时）
        me_0_1ms = self.get_mean_error()  # 平均延时（0.1ms单位，带符号）
        mean_delay = me_0_1ms / 10.0  # 平均延时（ms，带符号）

        # 计算相对延时：每个点的延时减去平均延时
        # 标准公式：相对延时 = 延时 - 平均延时（对所有点统一适用）
        relative_delays_ms = []
        for point in data_points:
            delay_ms = point['delay']
            relative_delay = delay_ms - mean_delay
            relative_delays_ms.append(relative_delay)

        return relative_delays_ms, mean_delay

    def _prepare_time_series_plot_data(self, data_points: List[Dict[str, Any]], mean_delay: float) -> Tuple[List[float], List[float], List[List[Any]]]:
        """
        准备图表绘制所需的数据格式

        Args:
            data_points: 排序后的数据点列表
            mean_delay: 平均延时（ms）

        Returns:
            Tuple[List[float], List[float], List[List[Any]]]: (时间列表, 延时列表, 自定义数据列表)
        """
        # 提取排序后的数据
        times_ms = [point['time'] for point in data_points]
        delays_ms = [point['delay'] for point in data_points]  # 保留原始延时用于hover显示
        # customdata 包含 [key_id, record_index, replay_index, 原始延时, 相对延时, 平均延时, 录制锤速, 播放锤速, 锤速差值]
        customdata_list = [[
            point['key_id'],
            point['record_index'],
            point['replay_index'],
            point['delay'],              # 原始延时
            point.get('relative_delay', 0),  # 相对延时
            mean_delay,                  # 平均延时
            point.get('record_velocity'),    # 录制锤速
            point.get('replay_velocity'),    # 播放锤速
            point.get('velocity_diff')       # 锤速差值
        ] for point in data_points]

        return times_ms, delays_ms, customdata_list

    def _configure_delay_plot_axes(self, delays_ms: List[float], is_relative: bool = False) -> Tuple[float, float, float]:
        """
        配置延时图表的Y轴参数

        Args:
            delays_ms: 延时数据列表
            is_relative: 是否为相对延时图

        Returns:
            Tuple[float, float, float]: (y_axis_min, y_axis_max, dtick)
        """
        if not delays_ms:
            # 默认配置
            return (-50, 50, 10) if not is_relative else (-15, 15, 3)

        y_min = min(delays_ms)
        y_max = max(delays_ms)

        # 使用已有的统计信息来确定合适的Y轴范围
        mean_delay_0_1ms = self.get_mean_error()  # 平均延时（0.1ms单位）
        std_dev_0_1ms = self.get_standard_deviation()  # 标准差（0.1ms单位）

        # 转换为ms单位
        mean_delay_ms = mean_delay_0_1ms / 10.0
        std_dev_ms = std_dev_0_1ms / 10.0

        if is_relative:
            # 相对延时通常集中在0附近，基于标准差设置合理的对称范围
            if std_dev_ms <= 2:  # 数据高度集中
                y_half_range = 8  # ±8ms
                dtick = 2
            elif std_dev_ms <= 5:  # 中等集中
                y_half_range = 12  # ±12ms
                dtick = 3
            elif std_dev_ms <= 10:  # 适中离散
                y_half_range = 20  # ±20ms
                dtick = 4
            elif std_dev_ms <= 25:  # 较大离散
                y_half_range = 40  # ±40ms
                dtick = 8
            else:  # 超大离散
                y_half_range = max(40, std_dev_ms * 1.5)  # 至少±40ms，或1.5倍标准差
                dtick = 10

            # 以0为中心对称显示（相对延时的特点）
            # 但确保能显示所有实际数据点
            y_axis_min = min(y_min - 1, -y_half_range)  # 显示实际最小值，或对称范围的最小值
            y_axis_max = max(y_max + 1, y_half_range)   # 显示实际最大值，或对称范围的最大值

            # 确保最小范围为±5ms
            if y_axis_max - y_axis_min < 10:
                y_axis_min = -5
                y_axis_max = 5
                dtick = 1
        else:
            # 原始延时：根据数据分布智能选择Y轴范围和刻度
            # 使用3倍标准差作为合理的显示范围
            suggested_half_range = max(15, std_dev_ms * 3)  # 至少显示±15ms，或3倍标准差

            if std_dev_ms <= 5:  # 数据集中分布
                dtick = 2
            elif std_dev_ms <= 20:  # 中等离散度
                dtick = 5
            elif std_dev_ms <= 100:  # 大离散度
                dtick = 10
            else:  # 超大离散度
                dtick = 20

            # 以平均值为中心设置Y轴范围，但确保显示所有数据点
            y_center = mean_delay_ms
            y_axis_min = min(y_min - 2, y_center - suggested_half_range)
            y_axis_max = max(y_max + 2, y_center + suggested_half_range)

        return y_axis_min, y_axis_max, dtick

    def _create_raw_delay_plot(self, times_ms: List[float], delays_ms: List[float], customdata_list: List[List[Any]]) -> Any:
        """
        创建原始延时时间序列图

        Args:
            times_ms: 时间数据（ms）
            delays_ms: 原始延时数据（ms）
            customdata_list: 自定义数据列表

        Returns:
            Any: Plotly图表对象
        """
        import plotly.graph_objects as go

        # 创建偏移之前的时间序列图
        raw_delay_fig = go.Figure()
        raw_delay_fig.add_trace(go.Scatter(
            x=times_ms,  # X轴使用录制时间
            y=delays_ms,  # Y轴使用原始延时
            mode='markers+lines',  # 显示数据点并按时间顺序连接
            name='原始延时时间序列',
            marker=dict(
                size=6,
                color='#FF9800',  # 橙色
                symbol='circle'  # 实心圆点
            ),
            line=dict(color='#FF9800', width=1.5),
            hovertemplate='<b>录制时间</b>: %{x:.2f}ms<br>' +
                         '<b>原始延时</b>: %{y:.2f}ms<br>' +
                         '<b>相对延时</b>: %{customdata[4]:.2f}ms<br>' +
                         '<b>平均延时</b>: %{customdata[5]:.2f}ms<br>' +
                         '<b>录制锤速</b>: %{customdata[6]}<br>' +
                         '<b>播放锤速</b>: %{customdata[7]}<br>' +
                         '<b>锤速差值</b>: %{customdata[8]}<br>' +
                         '<b>按键ID</b>: %{customdata[0]}<br>' +
                         '<extra></extra>',
            customdata=customdata_list
        ))

        # 配置Y轴
        y_axis_min, y_axis_max, dtick = self._configure_delay_plot_axes(delays_ms, is_relative=False)

        # 配置偏移前图表的布局
        raw_delay_fig.update_layout(
            xaxis_title='录制时间 (ms)',
            yaxis_title='原始延时 (ms)',
            showlegend=True,
            template='plotly_white',
            height=400,
            hovermode='closest'
        )

        # 根据数据动态设置Y轴刻度和范围
        raw_delay_fig.update_yaxes(
            range=[y_axis_min, y_axis_max],
            dtick=dtick,
            tickformat='.1f'  # 显示1位小数
        )

        return raw_delay_fig

    def _create_relative_delay_plot(self, times_ms: List[float], relative_delays_ms: List[float],
                                   customdata_list: List[List[Any]], mean_delay: float) -> Any:
        """
        创建相对延时时间序列图

        Args:
            times_ms: 时间数据（ms）
            relative_delays_ms: 相对延时数据（ms）
            customdata_list: 自定义数据列表
            mean_delay: 平均延时（ms）

        Returns:
            Any: Plotly图表对象
        """
        import plotly.graph_objects as go

        # 创建偏移之后的时间序列图
        relative_delay_fig = go.Figure()
        relative_delay_fig.add_trace(go.Scatter(
            x=times_ms,
            y=relative_delays_ms,
            mode='markers+lines',  # 显示数据点并按时间顺序连接
            name=f'相对延时时间序列 (平均延时: {mean_delay:.2f}ms)',
            marker=dict(
                size=6,
                color='#2196F3',  # 蓝色
                line=dict(width=0.5, color='#1976D2')
            ),
            line=dict(color='#2196F3', width=1.5),
            hovertemplate='<b>录制时间</b>: %{x:.2f}ms<br>' +
                         '<b>相对延时</b>: %{y:.2f}ms<br>' +
                         '<b>原始延时</b>: %{customdata[3]:.2f}ms<br>' +
                         '<b>平均延时</b>: %{customdata[4]:.2f}ms<br>' +
                         '<b>按键ID</b>: %{customdata[0]}<br>' +
                         '<extra></extra>',
            customdata=customdata_list
        ))

        # 配置Y轴
        y_axis_min, y_axis_max, dtick = self._configure_delay_plot_axes(relative_delays_ms, is_relative=True)

        # 配置偏移后图表的布局
        relative_delay_fig.update_layout(
            xaxis_title='录制时间 (ms)',
            yaxis_title='相对延时 (ms)',
            showlegend=True,
            template='plotly_white',
            height=400,
            hovermode='closest'
        )

        # 根据数据动态设置Y轴刻度和范围
        relative_delay_fig.update_yaxes(
            range=[y_axis_min, y_axis_max],
            dtick=dtick,
            tickformat='.1f'  # 显示1位小数
        )

        # 为相对延时图添加参考线
        if relative_delays_ms:
            std_0_1ms = self.get_standard_deviation()  # 标准差（0.1ms单位）
            std_delay = std_0_1ms / 10.0  # 标准差（ms）

            # 添加零线参考线（相对延时的均值应该为0）
            relative_delay_fig.add_trace(go.Scatter(
                x=[times_ms[0], times_ms[-1]] if times_ms else [0, 1],
                y=[0, 0],
                mode='lines',
                name='平均延时（零线）',
                line=dict(dash='dash', color='red', width=2),
                hovertemplate='<b>平均延时（零线）</b>: 0.00ms<extra></extra>',
                showlegend=False
            ))

            # 添加±3σ参考线（相对延时的±3σ，以0为中心）
            if std_delay > 0:
                relative_delay_fig.add_trace(go.Scatter(
                    x=[times_ms[0], times_ms[-1]] if times_ms else [0, 1],
                    y=[3 * std_delay, 3 * std_delay],
                    mode='lines',
                    name='+3σ',
                    line=dict(dash='dot', color='orange', width=1.5),
                    hovertemplate=f'<b>+3σ</b>: {3 * std_delay:.2f}ms<extra></extra>',
                    showlegend=False
                ))
                relative_delay_fig.add_trace(go.Scatter(
                    x=[times_ms[0], times_ms[-1]] if times_ms else [0, 1],
                    y=[-3 * std_delay, -3 * std_delay],
                    mode='lines',
                    name='-3σ',
                    line=dict(dash='dot', color='orange', width=1.5),
                    hovertemplate=f'<b>-3σ</b>: {-3 * std_delay:.2f}ms<extra></extra>',
                    showlegend=False
                ))

        return relative_delay_fig

    def generate_delay_time_series_plot(self) -> Any:
        """
        生成延时时间序列图（支持单算法和多算法模式）
        x轴：时间（record_keyon，转换为ms）
        y轴：延时（keyon_offset，转换为ms）
        数据来源：所有已匹配的按键对，按时间顺序排列
        """
        # 获取激活的算法并生成图表
        active_algorithms = self.multi_algorithm_manager.get_active_algorithms() if self.multi_algorithm_manager else []

        if not active_algorithms:
            logger.debug("没有激活的算法，返回空图表")
            return {
                'raw_delay_plot': self.plot_generator._create_empty_plot("没有激活的算法"),
                'relative_delay_plot': self.plot_generator._create_empty_plot("没有激活的算法")
            }

        # 直接使用多算法图表生成器，它会自动处理单算法和多算法的情况
        logger.info(f"处理 {len(active_algorithms)} 个激活算法")
        return self.multi_algorithm_plot_generator.generate_multi_algorithm_delay_time_series_plot(
            active_algorithms
        )
    

    def generate_delay_histogram_plot(self) -> Any:
        """
        生成延时分布直方图，并叠加正态拟合曲线（基于绝对时延）。

        数据筛选：只使用误差≤50ms的按键数据
        绝对时延 = keyon_offset（直接测量值）
        - 反映算法的实际延时表现
        - 包含整体偏移信息
        - 延时有正有负，正值表示延迟，负值表示提前

        x轴：绝对延时 (ms)，y轴：概率密度（支持单算法和多算法模式）
        """
        # 获取激活的算法并生成图表
        active_algorithms = self.multi_algorithm_manager.get_active_algorithms() if self.multi_algorithm_manager else []

        if not active_algorithms:
            logger.debug("没有激活的算法，返回空图表")
            return self.plot_generator._create_empty_plot("没有激活的算法")

        # 直接使用多算法图表生成器，它会自动处理单算法和多算法的情况
        logger.info(f"处理 {len(active_algorithms)} 个激活算法")
        return self.multi_algorithm_plot_generator.generate_multi_algorithm_delay_histogram_plot(
            active_algorithms
        )
    def generate_offset_alignment_plot(self) -> Any:
        """生成偏移对齐分析柱状图 - 键位为横坐标，中位数、均值、标准差为纵坐标，分4个子图显示（支持单算法和多算法模式）"""
        # 获取激活的算法并生成图表
        active_algorithms = self.multi_algorithm_manager.get_active_algorithms() if self.multi_algorithm_manager else []

        if not active_algorithms:
            logger.debug("没有激活的算法，返回空图表")
            return self.plot_generator._create_empty_plot("没有激活的算法")

        # 直接使用多算法图表生成器，它会自动处理单算法和多算法的情况
        logger.info(f"处理 {len(active_algorithms)} 个激活算法")
        return self.multi_algorithm_plot_generator.generate_multi_algorithm_offset_alignment_plot(
                active_algorithms
            )

    def generate_key_delay_zscore_scatter_plot(self) -> Any:
        """
        生成按键与延时Z-Score标准化散点图（支持单算法和多算法模式）
        x轴：按键ID（key_id）
        y轴：Z-Score标准化延时值，z = (x_i - μ) / σ
        """
        # 获取激活的算法并生成图表
        active_algorithms = self.multi_algorithm_manager.get_active_algorithms() if self.multi_algorithm_manager else []

        if not active_algorithms:
            logger.debug("没有激活的算法，返回空图表")
            return self.plot_generator._create_empty_plot("没有激活的算法")

        # 直接使用多算法图表生成器，它会自动处理单算法和多算法的情况
        logger.info(f"处理 {len(active_algorithms)} 个激活算法")
        return self.multi_algorithm_plot_generator.generate_multi_algorithm_key_delay_zscore_scatter_plot(
                active_algorithms
            )
    
    def generate_single_key_delay_comparison_plot(self, key_id: int) -> Any:
        """
        生成单键多曲延时对比图
        
        Args:
            key_id: 按键ID
            
        Returns:
            Any: Plotly图表对象
        """
        # 获取激活的算法并生成图表
        active_algorithms = self.multi_algorithm_manager.get_active_algorithms() if self.multi_algorithm_manager else []

        if not active_algorithms:
            logger.debug("没有激活的算法，返回空图表")
            return self.plot_generator._create_empty_plot("没有激活的算法")
            
        # 直接使用多算法图表生成器，它会自动处理单算法和多算法的情况
        logger.info(f"处理 {len(active_algorithms)} 个激活算法")
        return self.multi_algorithm_plot_generator.generate_single_key_delay_comparison_plot(
                active_algorithms, key_id
            )

    def generate_hammer_velocity_delay_scatter_plot(self) -> Any:
        """
        生成锤速与延时的散点图（支持单算法和多算法模式）
        x轴：锤速（播放锤速）
        y轴：延时（keyon_offset，转换为ms）
        数据来源：所有已匹配的按键对
        """
        # 获取激活的算法并生成图表
        active_algorithms = self.multi_algorithm_manager.get_active_algorithms() if self.multi_algorithm_manager else []

        if not active_algorithms:
            logger.debug("没有激活的算法，返回空图表")
            return self.plot_generator._create_empty_plot("没有激活的算法")

        # 直接使用多算法图表生成器，它会自动处理单算法和多算法的情况
        logger.info(f"处理 {len(active_algorithms)} 个激活算法")
        return self.multi_algorithm_plot_generator.generate_multi_algorithm_hammer_velocity_delay_scatter_plot(
                active_algorithms
            )
        
    def generate_hammer_velocity_relative_delay_scatter_plot(self) -> Any:
        """
        生成锤速与相对延时的散点图（支持单算法和多算法模式）
        x轴：log₁₀(锤速)（播放锤速的对数值）
        y轴：相对延时（keyon_offset - μ，转换为ms）
        数据来源：精确匹配对（≤50ms）
        """
        # 获取激活的算法并生成图表
        active_algorithms = self.multi_algorithm_manager.get_active_algorithms() if self.multi_algorithm_manager else []

        if not active_algorithms:
            logger.debug("没有激活的算法，返回空图表")
            return self.plot_generator._create_empty_plot("没有激活的算法")

        # 直接使用多算法图表生成器，它会自动处理单算法和多算法的情况
        logger.info(f"处理 {len(active_algorithms)} 个激活算法")
        return self.multi_algorithm_plot_generator.generate_multi_algorithm_hammer_velocity_relative_delay_scatter_plot(
                active_algorithms
            )
    
    def generate_key_hammer_velocity_scatter_plot(self) -> Any:
        """
        生成按键与锤速的散点图，颜色表示延时（支持单算法和多算法模式）
        x轴：按键ID（key_id）
        y轴：锤速（播放锤速）
        颜色：延时（keyon_offset，转换为ms，使用颜色映射）
        数据来源：所有已匹配的按键对
        """
        # 获取激活的算法并生成图表
        active_algorithms = self.multi_algorithm_manager.get_active_algorithms() if self.multi_algorithm_manager else []

        if not active_algorithms:
            logger.debug("没有激活的算法，返回空图表")
            return self.plot_generator._create_empty_plot("没有激活的算法")

        # 直接使用多算法图表生成器，它会自动处理单算法和多算法的情况
        logger.info(f"处理 {len(active_algorithms)} 个激活算法")
        return self.multi_algorithm_plot_generator.generate_multi_algorithm_key_hammer_velocity_scatter_plot(
                active_algorithms
            )
    
    def generate_waterfall_plot(self) -> Any:
        """生成瀑布图（统一单算法和多算法模式）"""

        # 获取激活的算法并生成图表
        active_algorithms = self.multi_algorithm_manager.get_active_algorithms() if self.multi_algorithm_manager else []

        if not active_algorithms:
            logger.debug("没有激活的算法，返回空图表")
            return self.plot_generator._create_empty_plot("没有激活的算法")

        # 准备数据
        analyzers = [alg.analyzer for alg in active_algorithms if alg.analyzer]
        algorithm_names = [alg.metadata.algorithm_name for alg in active_algorithms]
        is_multi_algorithm = len(active_algorithms) > 1

        # 对于单算法模式，确保数据已同步
        if not is_multi_algorithm:
            analyzer = analyzers[0] if analyzers else None
            if analyzer and (not self.plot_generator.valid_record_data or not self.plot_generator.valid_replay_data):
                logger.info("同步数据到PlotGenerator")
                self._sync_analysis_results()

        # 使用统一的瀑布图生成器，它会自动处理单算法和多算法的情况
        logger.info(f"处理 {len(active_algorithms)} 个激活算法")
        return self.multi_algorithm_plot_generator.generate_unified_waterfall_plot(
            self,                # 后端实例
            analyzers,           # 分析器列表
            algorithm_names,     # 算法名称列表
            is_multi_algorithm,  # 是否多算法模式
            self.time_filter,    # 时间过滤器
            self.data_filter.key_filter if self.data_filter else None  # 按键过滤器
        )
    
    def generate_watefall_conbine_plot(self, key_on: float, key_off: float, key_id: int) -> Tuple[Any, Any, Any]:
        """生成瀑布图对比图"""
        return self.plot_generator.generate_watefall_conbine_plot(key_on, key_off, key_id)
    
    def generate_watefall_conbine_plot_by_index(self, index: int, is_record: bool) -> Tuple[Any, Any, Any]:
        """根据索引生成瀑布图对比图"""
        return self.plot_generator.generate_watefall_conbine_plot_by_index(index, is_record)
    
    #  TODO
    def get_notes_by_delay_type(self, algorithm_name: str, delay_type: str) -> Optional[Tuple[Any, Any, int, int]]:
        """
        根据延迟类型（最大/最小）获取对应的音符
        
        Args:
            algorithm_name: 算法名称
            delay_type: 延迟类型，'max' 或 'min'
        
        Returns:
            Tuple[Note, Note]: (record_note, replay_note)，如果失败则返回None
        """
        try:
            if not self.multi_algorithm_manager:
                logger.warning("多算法管理器不存在")
                return None
            
            active_algorithms = self.multi_algorithm_manager.get_active_algorithms()
            algorithm = None
            for alg in active_algorithms:
                if alg.metadata.algorithm_name == algorithm_name:
                    algorithm = alg
                    break
            
            if not algorithm:
                logger.warning(f"未找到算法: {algorithm_name}")
                return None
            
            if not algorithm.analyzer or not algorithm.analyzer.note_matcher:
                logger.warning(f"算法 '{algorithm_name}' 的分析器或匹配器不存在")
                return None
            
            note_matcher = algorithm.analyzer.note_matcher
            
            # 获取偏移数据
            offset_data = note_matcher.get_offset_alignment_data()
            if not offset_data:
                logger.warning("没有匹配数据")
                return None
            
            # 找到最大或最小延迟对应的数据项
            target_item = None
            if delay_type == 'max':
                # 找到所有具有最大延迟的数据项
                max_delay = max(item.get('keyon_offset', 0) for item in offset_data)
                max_delay_items = [item for item in offset_data if item.get('keyon_offset', 0) == max_delay]
                if max_delay_items:
                    # 如果有多个，选择第一个（也可以选择其他策略，比如按时间排序）
                    target_item = max_delay_items[0]
                    logger.info(f"🔍 最大延迟: {max_delay/10.0:.2f}ms, 找到{len(max_delay_items)}个匹配项, 选择record_index={target_item.get('record_index')}, replay_index={target_item.get('replay_index')}")
                    if len(max_delay_items) > 1:
                        logger.warning(f"找到{len(max_delay_items)}个具有最大延迟({max_delay/10.0:.2f}ms)的数据项，选择第一个")
                else:
                    logger.warning(f"⚠️ 未找到最大延迟对应的数据项")
            elif delay_type == 'min':
                # 找到所有具有最小延迟的数据项
                # 注意：这里使用带符号的keyon_offset，与UI显示保持一致
                all_delays = [item.get('keyon_offset', 0) for item in offset_data]
                min_delay = min(all_delays)
                min_delay_ms = min_delay / 10.0
                
                # 使用与UI相同的逻辑：遍历所有数据项，找到最后一个匹配的（与UI保持一致）
                # UI中的逻辑：if min_delay_item is None or item_delay_ms == min_delay_ms: min_delay_item = item
                # 这意味着如果有多个匹配项，UI会保存最后一个
                target_item = None
                for item in offset_data:
                    item_delay_ms = item.get('keyon_offset', 0) / 10.0
                    if target_item is None or item_delay_ms == min_delay_ms:
                        target_item = item
                
                # 验证：检查是否真的找到了最小值
                logger.info(f"🔍 所有延迟值范围: [{min(all_delays)/10.0:.2f}ms, {max(all_delays)/10.0:.2f}ms]")
                logger.info(f"🔍 最小延迟值: {min_delay_ms:.2f}ms")
                
                if target_item:
                    # 统计有多少个匹配项
                    min_delay_items = [item for item in offset_data if abs(item.get('keyon_offset', 0) / 10.0 - min_delay_ms) < 0.001]
                    logger.info(f"🔍 找到{len(min_delay_items)}个具有最小延迟({min_delay_ms:.2f}ms)的数据项")
                    logger.info(f"🔍 选择的数据项（与UI逻辑一致，最后一个匹配项）: record_index={target_item.get('record_index')}, replay_index={target_item.get('replay_index')}, keyon_offset={target_item.get('keyon_offset', 0)/10.0:.2f}ms")
                    if len(min_delay_items) > 1:
                        logger.warning(f"⚠️ 找到{len(min_delay_items)}个具有最小延迟({min_delay_ms:.2f}ms)的数据项，选择最后一个（与UI逻辑一致）")
                        # 列出所有匹配项的信息
                        for idx, item in enumerate(min_delay_items):
                            logger.info(f"  匹配项{idx+1}: record_index={item.get('record_index')}, replay_index={item.get('replay_index')}")
                else:
                    logger.warning(f"⚠️ 未找到最小延迟对应的数据项")
            else:
                logger.warning(f"⚠️ 无效的延迟类型: {delay_type}")
                return None
            
            if not target_item:
                logger.warning(f"⚠️ 未找到{delay_type}延迟对应的数据项")
                return None
            
            record_index = target_item.get('record_index')
            replay_index = target_item.get('replay_index')
            
            if record_index is None or replay_index is None:
                logger.warning(f"⚠️ 数据项缺少索引信息")
                return None
            
            # 从matched_pairs中查找对应的Note对象
            matched_pairs = note_matcher.get_matched_pairs()
            record_note = None
            replay_note = None
            
            for r_idx, p_idx, r_note, p_note in matched_pairs:
                if r_idx == record_index and p_idx == replay_index:
                    record_note = r_note
                    replay_note = p_note
                    break
            
            if record_note is None or replay_note is None:
                logger.warning(f"⚠️ 未找到匹配对: record_index={record_index}, replay_index={replay_index}")
                return None
            
            delay_ms = target_item.get('keyon_offset', 0) / 10.0
            # 从音符对象获取正确的按键ID，而不是从offset_data中获取
            key_id = getattr(record_note, 'id', 'N/A') if record_note else 'N/A'
            delay_type_name = "最大" if delay_type == 'max' else "最小"
            logger.info(f"✅ 找到{delay_type_name}延迟对应的音符: 算法={algorithm_name}, 按键ID={key_id}, record_index={record_index}, replay_index={replay_index}, delay={delay_ms:.2f}ms")
            return (record_note, replay_note, record_index, replay_index)
            
        except Exception as e:
            logger.error(f"❌ 获取{delay_type}延迟对应的音符失败: {e}")
            
            logger.error(traceback.format_exc())
            return None
    
    def get_first_data_point_notes(self) -> Optional[Tuple[Any, Any]]:
        """
        获取延时时间序列图的第一个数据点对应的音符
        
        支持单算法模式和多算法模式：
        - 单算法模式：使用 multi_algorithm_manager 中的算法
        - 多算法模式：使用指定的算法
        
        Returns:
            Tuple[Note, Note]: (record_note, replay_note)，如果失败则返回None
        """
        try:
            # 获取激活的算法（统一处理单算法和多算法模式）
            active_algorithms = self.multi_algorithm_manager.get_active_algorithms() if self.multi_algorithm_manager else []

            if not active_algorithms:
                logger.debug("没有激活的算法")
                return None
                
            # 使用第一个激活的算法（无论单算法还是多算法模式）
            algorithm = active_algorithms[0]
            if not algorithm.analyzer or not algorithm.analyzer.note_matcher:
                logger.warning(f"算法 '{algorithm.metadata.algorithm_name}' 的分析器或匹配器不存在")
                return None

            analyzer = algorithm.analyzer
            note_matcher = analyzer.note_matcher
            
            # 获取偏移数据
            offset_data = note_matcher.get_offset_alignment_data()
            if not offset_data:
                logger.warning("没有匹配数据")
                return None
            
            # 提取数据点并排序
            data_points = []
            for item in offset_data:
                record_keyon = item.get('record_keyon', 0)
                record_index = item.get('record_index')
                replay_index = item.get('replay_index')
                
                if record_keyon is None or record_index is None or replay_index is None:
                    continue
                
                data_points.append({
                    'time': record_keyon / 10.0,  # 转换为ms
                    'record_index': record_index,
                    'replay_index': replay_index
                })
            
            if not data_points:
                logger.warning("没有有效数据点")
                return None
            
            # 按时间排序，获取第一个数据点
            data_points.sort(key=lambda x: x['time'])
            first_point = data_points[0]
            
            record_index = first_point['record_index']
            replay_index = first_point['replay_index']
            
            # 从matched_pairs中查找对应的Note对象
            matched_pairs = note_matcher.get_matched_pairs()
            record_note = None
            replay_note = None
            
            for r_idx, p_idx, r_note, p_note in matched_pairs:
                if r_idx == record_index and p_idx == replay_index:
                    record_note = r_note
                    replay_note = p_note
                    break
            
            if record_note is None or replay_note is None:
                logger.warning(f"未找到匹配对: record_index={record_index}, replay_index={replay_index}")
                return None
            
            logger.info(f"找到第一个数据点: record_index={record_index}, replay_index={replay_index}")
            return (record_note, replay_note)
            
        except Exception as e:
            logger.error(f"获取第一个数据点失败: {e}")
            logger.error(traceback.format_exc())
            return None
    
    def test_curve_alignment(self) -> Optional[Dict[str, Any]]:
        """
        测试曲线对齐功能，使用延时时间序列图的第一个数据点
        
        Returns:
            Dict[str, Any]: 测试结果，包含对齐前后的对比图和相似度
        """
        try:
            from backend.force_curve_analyzer import ForceCurveAnalyzer
            
            # 获取第一个数据点的音符
            notes = self.get_first_data_point_notes()
            if notes is None:
                return {
                    'status': 'error',
                    'message': '无法获取第一个数据点的音符'
                }
            
            record_note, replay_note = notes
            
            # 计算平均延时（统一处理单算法和多算法模式）
            mean_delay = 0.0
            
                # 获取第一个激活的算法（与get_first_data_point_notes逻辑一致）
            active_algorithms = self.multi_algorithm_manager.get_active_algorithms() if self.multi_algorithm_manager else []
            if active_algorithms:
                algorithm = active_algorithms[0]
                if algorithm.analyzer:
                    mean_error_0_1ms = algorithm.analyzer.get_mean_error()
                    if mean_error_0_1ms is not None:
                        mean_delay = mean_error_0_1ms / 10.0
            
            logger.info(f"测试曲线对齐 - 获取平均延时: {mean_delay}ms")
            
            # 创建曲线分析器
            # 减少平滑强度，保持波峰和波谷特征
            analyzer = ForceCurveAnalyzer(
                smooth_sigma=0.3,  # 大幅减小平滑强度，从1.0改为0.3，更好地保持波峰和波谷
                dtw_distance_metric='manhattan',
                dtw_window_size_ratio=0.3  # 适中的窗口大小，平衡对齐效果和形状保持
            )
            
            # 对比曲线（播放曲线对齐到录制曲线）
            result = analyzer.compare_curves(
                record_note, 
                replay_note,
                record_note=record_note,
                replay_note=replay_note,
                mean_delay=mean_delay  # 传入平均延时
            )
            
            if result is None:
                return {
                    'status': 'error',
                    'message': '曲线对比失败'
                }
            
            # 生成所有处理阶段的对比图 (大图)
            all_stages_fig = None
            # 生成独立的处理阶段图表列表
            individual_stage_figures = []
            
            if 'processing_stages' in result:
                # 兼容旧的大图逻辑
                all_stages_fig = analyzer.visualize_all_processing_stages(result)
                # 生成新的独立图表列表
                individual_stage_figures = analyzer.generate_processing_stages_figures(result)
            
            # 生成对齐前后对比图（保持向后兼容）
            comparison_fig = None
            if 'alignment_comparison' in result:
                comparison_fig = analyzer.visualize_alignment_comparison(result)
            
            return {
                'status': 'success',
                'result': result,
                'comparison_figure': comparison_fig,
                'all_stages_figure': all_stages_fig, # 保留以兼容
                'individual_stage_figures': individual_stage_figures, # 新增字段
                'record_index': record_note.id if hasattr(record_note, 'id') else 'N/A',
                'replay_index': replay_note.id if hasattr(replay_note, 'id') else 'N/A'
            }
            
        except Exception as e:
            logger.error(f"测试曲线对齐失败: {e}")
            
            logger.error(traceback.format_exc())
            return {
                'status': 'error',
                'message': f'测试失败: {str(e)}'
            }
    
    def generate_scatter_detail_plot_by_indices(self, record_index: int, replay_index: int) -> Tuple[Any, Any, Any]:
        """
        根据record_index和replay_index生成散点图点击的详细曲线图

        Args:
            record_index: 录制音符索引
            replay_index: 播放音符索引

        Returns:
            Tuple[Any, Any, Any]: (录制音符图, 播放音符图, 对比图)
        """
        analyzer = self._get_current_analyzer()
        if not analyzer or not analyzer.note_matcher:
            logger.warning("分析器或匹配器不存在，无法生成详细曲线图")
            return None, None, None
        
        # 从precision_matched_pairs中查找对应的Note对象（确保只使用精确匹配对）
        precision_matched_pairs = analyzer.note_matcher.precision_matched_pairs
        record_note = None
        play_note = None
        
        for r_idx, p_idx, r_note, p_note in precision_matched_pairs:
            if r_idx == record_index and p_idx == replay_index:
                record_note = r_note
                play_note = p_note
                break
        
        if record_note is None or play_note is None:
            logger.warning(f"未找到匹配对: record_index={record_index}, replay_index={replay_index}")
            return None, None, None

        # 计算平均延时
        mean_delays = {}
        mean_delay_val = 0.0
        analyzer = self._get_current_analyzer()
        if analyzer:
            mean_error_0_1ms = analyzer.get_mean_error()
            mean_delay_val = mean_error_0_1ms / 10.0  # 转换为毫秒
            mean_delays['default'] = mean_delay_val
        else:
            logger.warning("无法获取单算法模式的平均延时")

        # 使用spmid模块生成详细图表
        detail_figure1 = spmid.plot_note_comparison_plotly(record_note, None, mean_delays=mean_delays)
        detail_figure2 = spmid.plot_note_comparison_plotly(None, play_note, mean_delays=mean_delays)
        detail_figure_combined = spmid.plot_note_comparison_plotly(record_note, play_note, mean_delays=mean_delays)
        
        # 生成全过程处理图
        processing_stages_figure = None
        if self.force_curve_analyzer:
            try:
                comparison_result = self.force_curve_analyzer.compare_curves(
                    record_note, 
                    play_note,
                    mean_delay=mean_delay_val  # 传入平均延时
                )
                if comparison_result:
                    processing_stages_figure = self.force_curve_analyzer.visualize_all_processing_stages(comparison_result)
            except Exception as e:
                logger.error(f"生成全过程处理图失败: {e}")

        logger.info(f"生成散点图点击的详细曲线图，record_index={record_index}, replay_index={replay_index}")
        return detail_figure1, detail_figure2, detail_figure_combined
    
    def generate_multi_algorithm_scatter_detail_plot_by_indices(
        self,
        algorithm_name: str,
        record_index: int,
        replay_index: int
    ) -> Tuple[Any, Any, Any]:
        """
        根据算法名称、record_index和replay_index生成多算法散点图点击的详细曲线图

        Args:
            algorithm_name: 算法名称
            record_index: 录制音符索引
            replay_index: 播放音符索引

        Returns:
            Tuple[Any, Any, Any]: (录制音符图, 播放音符图, 对比图)
        """
        if not self.multi_algorithm_manager:
            logger.warning("⚠️ 多算法管理器不存在，无法生成详细曲线图")
            return None, None, None
        
        # 根据 display_name 查找算法
        logger.info(f"🔍 generate_multi_algorithm_scatter_detail_plot_by_indices: 查找算法 display_name='{algorithm_name}'")
        algorithm = None
        for alg in self.multi_algorithm_manager.get_all_algorithms():
            logger.debug(f"🔍 检查算法: display_name='{alg.metadata.display_name}', algorithm_name='{alg.metadata.algorithm_name}'")
            if alg.metadata.display_name == algorithm_name:
                algorithm = alg
                logger.info(f"✅ 找到匹配算法: {alg.metadata.display_name}")
                break

        if not algorithm or not algorithm.analyzer or not algorithm.analyzer.note_matcher:
            logger.warning(f"⚠️ 算法 '{algorithm_name}' 不存在或没有分析器，无法生成详细曲线图")
            # 调试：列出所有可用算法
            all_algs = self.multi_algorithm_manager.get_all_algorithms()
            logger.warning(f"⚠️ 可用算法列表: {[f'{alg.metadata.display_name}({alg.metadata.algorithm_name})' for alg in all_algs]}")
            return None, None, None
        
        # 从precision_matched_pairs中查找对应的Note对象（锤速对比图使用precision数据）
        precision_matched_pairs = algorithm.analyzer.note_matcher.precision_matched_pairs
        record_note = None
        play_note = None
        
        for r_idx, p_idx, r_note, p_note in precision_matched_pairs:
            if r_idx == record_index and p_idx == replay_index:
                record_note = r_note
                play_note = p_note
                break
        
        if record_note is None or play_note is None:
            logger.warning(f"⚠️ 未找到匹配对: 算法={algorithm_name}, record_index={record_index}, replay_index={replay_index}")
            logger.warning(f"⚠️ precision_matched_pairs 数量: {len(precision_matched_pairs)}")
            for i, (r_idx, p_idx, r_note, p_note) in enumerate(precision_matched_pairs[:5]):  # 只显示前5个
                logger.warning(f"⚠️ 匹配对 {i}: record_idx={r_idx}, replay_idx={p_idx}, has_notes={r_note is not None and p_note is not None}")
            return None, None, None

        # 计算平均延时
        mean_delays = {}
        if algorithm.analyzer:
            mean_error_0_1ms = algorithm.analyzer.get_mean_error()
            mean_delays[algorithm_name] = mean_error_0_1ms / 10.0  # 转换为毫秒
        else:
            logger.warning(f"⚠️ 无法获取算法 '{algorithm_name}' 的平均延时")

        # 使用spmid模块生成详细图表
        detail_figure1 = spmid.plot_note_comparison_plotly(record_note, None, algorithm_name=algorithm_name, mean_delays=mean_delays)
        detail_figure2 = spmid.plot_note_comparison_plotly(None, play_note, algorithm_name=algorithm_name, mean_delays=mean_delays)
        detail_figure_combined = spmid.plot_note_comparison_plotly(record_note, play_note, algorithm_name=algorithm_name, mean_delays=mean_delays)
        
        # 生成全过程处理图
        processing_stages_figure = None
        if self.force_curve_analyzer:
            try:
                comparison_result = self.force_curve_analyzer.compare_curves(record_note, play_note)
                if comparison_result:
                    processing_stages_figure = self.force_curve_analyzer.visualize_all_processing_stages(comparison_result)
            except Exception as e:
                logger.error(f"❌ 生成全过程处理图失败: {e}")
        
        logger.info(f"✅ 生成多算法散点图点击的详细曲线图，算法={algorithm_name}, record_index={record_index}, replay_index={replay_index}")
        return detail_figure1, detail_figure2, detail_figure_combined

    def get_note_time_range_for_waterfall(self, algorithm_name: Optional[str], record_index: int, replay_index: int, margin_ms: float = 500.0) -> Optional[Tuple[float, float]]:
        """
        根据record_index和replay_index获取音符的时间范围，用于调整瀑布图显示
        
        Args:
            algorithm_name: 算法名称（多算法模式需要，单算法模式为None）
            record_index: 录制音符索引
            replay_index: 播放音符索引
            margin_ms: 时间范围的前后边距（毫秒），默认500ms
        
        Returns:
            Optional[Tuple[float, float]]: (start_time_ms, end_time_ms) 或 None
        """
        try:
            if algorithm_name:
                # 多算法模式
                if not self.multi_algorithm_manager:
                    logger.warning("⚠️ 多算法管理器不存在，无法获取音符时间范围")
                    return None
                
                # 根据 display_name 查找算法
                algorithm = None
                for alg in self.multi_algorithm_manager.get_all_algorithms():
                    if alg.metadata.display_name == algorithm_name:
                        algorithm = alg
                        break

                if not algorithm or not algorithm.analyzer or not algorithm.analyzer.note_matcher:
                    logger.warning(f"⚠️ 算法 '{algorithm_name}' 不存在或没有分析器")
                    return None
                
                matched_pairs = algorithm.analyzer.matched_pairs
            else:
                # 单算法模式
                analyzer = self._get_current_analyzer()
                if not analyzer or not analyzer.note_matcher:
                    logger.warning("⚠️ 分析器或匹配器不存在，无法获取音符时间范围")
                    return None
                
                matched_pairs = analyzer.matched_pairs
            
            # 从matched_pairs中查找对应的Note对象
            record_note = None
            replay_note = None
            
            for r_idx, p_idx, r_note, p_note in matched_pairs:
                if r_idx == record_index and p_idx == replay_index:
                    record_note = r_note
                    replay_note = p_note
                    break
            
            if record_note is None or replay_note is None:
                logger.warning(f"⚠️ 未找到匹配对: record_index={record_index}, replay_index={replay_index}")
                return None
            
            # 计算音符的时间（单位：0.1ms）
            # 使用keyon时间作为中心点
            record_keyon = record_note.after_touch.index[0] + record_note.offset if hasattr(record_note, 'after_touch') and not record_note.after_touch.empty else record_note.offset
            replay_keyon = replay_note.after_touch.index[0] + replay_note.offset if hasattr(replay_note, 'after_touch') and not replay_note.after_touch.empty else replay_note.offset
            
            # 转换为毫秒
            record_keyon_ms = record_keyon / 10.0
            replay_keyon_ms = replay_keyon / 10.0
            
            # 计算按键持续时间（keyoff - keyon）
            record_keyoff = record_note.after_touch.index[-1] + record_note.offset if hasattr(record_note, 'after_touch') and not record_note.after_touch.empty else record_note.offset
            replay_keyoff = replay_note.after_touch.index[-1] + replay_note.offset if hasattr(replay_note, 'after_touch') and not replay_note.after_touch.empty else replay_note.offset
            
            record_keyoff_ms = record_keyoff / 10.0
            replay_keyoff_ms = replay_keyoff / 10.0
            
            # 计算按键持续时间（取两个按键中较长的）
            record_duration = record_keyoff_ms - record_keyon_ms
            replay_duration = replay_keyoff_ms - replay_keyon_ms
            note_duration = max(record_duration, replay_duration)
            
            # 计算中心时间（取两个音符keyon时间的中间值）
            center_time_ms = (record_keyon_ms + replay_keyon_ms) / 2.0
            
            # 动态调整时间范围：确保能看到按键本身以及周围的数据点
            # 基础边距 + 按键持续时间的倍数，确保能看到按键前后多个按键
            # 最小边距为margin_ms，如果按键持续时间较长，则增加边距（按键持续时间的3倍）
            # 这样即使按键很长，也能看到前后足够的上下文
            dynamic_margin = max(margin_ms, note_duration * 3.0)
            
            # 计算时间范围
            start_time_ms = max(0, center_time_ms - dynamic_margin)
            end_time_ms = center_time_ms + dynamic_margin
            
            logger.info(f"✅ 计算音符时间范围: center={center_time_ms:.1f}ms, range=[{start_time_ms:.1f}, {end_time_ms:.1f}]ms")
            return (start_time_ms, end_time_ms)
            
        except Exception as e:
            logger.error(f"❌ 获取音符时间范围失败: {e}")
            return None
    

    def generate_multi_algorithm_detail_plot_by_index(
        self,
        algorithm_name: str,
        index: int,
        is_record: bool
    ) -> Tuple[Figure, Figure, Figure]:
        """
        多算法模式下，根据算法名称和索引生成详细图表

        Args:
            algorithm_name: 算法名称
            index: 音符索引
            is_record: 是否为录制数据

        Returns:
            Tuple[Figure, Figure, Figure]: (录制音符图, 播放音符图, 对比图)
        """
        if not self.multi_algorithm_manager:
            self._ensure_multi_algorithm_manager()
        
        # 获取对应的算法数据集
        algorithm = self.multi_algorithm_manager.get_algorithm(algorithm_name)
        if not algorithm or not algorithm.is_ready():
            logger.error(f"算法 '{algorithm_name}' 不存在或未就绪")
            return None, None, None
        
        # 从算法的analyzer中获取数据
        if not algorithm.analyzer:
            logger.error(f"算法 '{algorithm_name}' 没有分析器")
            return None, None, None
        
        # 获取算法的有效数据
        valid_record_data = algorithm.analyzer.valid_record_data if hasattr(algorithm.analyzer, 'valid_record_data') else []
        valid_replay_data = algorithm.analyzer.valid_replay_data if hasattr(algorithm.analyzer, 'valid_replay_data') else []
        matched_pairs = algorithm.analyzer.matched_pairs if hasattr(algorithm.analyzer, 'matched_pairs') else []
        
        record_note = None
        play_note = None
        
        if is_record:
            if index < 0 or index >= len(valid_record_data):
                logger.error(f"录制数据索引 {index} 超出范围 [0, {len(valid_record_data)-1}]")
                return None, None, None
            record_note = valid_record_data[index]
            
            # 从matched_pairs中查找匹配的播放音符
            if matched_pairs:
                for record_index, replay_index, r_note, p_note in matched_pairs:
                    if record_index == index:
                        play_note = p_note
                        break
        else:
            if index < 0 or index >= len(valid_replay_data):
                logger.error(f"播放数据索引 {index} 超出范围 [0, {len(valid_replay_data)-1}]")
                return None, None, None
            play_note = valid_replay_data[index]
            
            # 从matched_pairs中查找匹配的录制音符
            if matched_pairs:
                for record_index, replay_index, r_note, p_note in matched_pairs:
                    if replay_index == index:
                        record_note = r_note
                        break
        
        # 计算平均延时
        mean_delays = {}
        if algorithm.analyzer:
            mean_error_0_1ms = algorithm.analyzer.get_mean_error()
            mean_delays[algorithm_name] = mean_error_0_1ms / 10.0  # 转换为毫秒

        # 使用spmid模块生成详细图表
        detail_figure1 = spmid.plot_note_comparison_plotly(record_note, None, algorithm_name=algorithm_name, mean_delays=mean_delays)
        detail_figure2 = spmid.plot_note_comparison_plotly(None, play_note, algorithm_name=algorithm_name, mean_delays=mean_delays)
        detail_figure_combined = spmid.plot_note_comparison_plotly(record_note, play_note, algorithm_name=algorithm_name, mean_delays=mean_delays)
        
        # 生成全过程处理图
        processing_stages_figure = None
        if self.force_curve_analyzer and record_note and play_note:
            try:
                comparison_result = self.force_curve_analyzer.compare_curves(record_note, play_note)
                if comparison_result:
                    processing_stages_figure = self.force_curve_analyzer.visualize_all_processing_stages(comparison_result)
            except Exception as e:
                logger.error(f"❌ 生成全过程处理图失败: {e}")
        
        logger.info(f"✅ 生成算法 '{algorithm_name}' 的详细图表，索引={index}, 类型={'record' if is_record else 'play'}")
        return detail_figure1, detail_figure2, detail_figure_combined
    
    def generate_multi_algorithm_error_detail_plot_by_index(
        self,
        algorithm_name: str,
        index: int,
        error_type: str,  # 'drop' 或 'multi'
        expected_key_id=None  # 期望的keyId，用于验证
    ) -> Tuple[Any, Any, Any]:
        """
        多算法模式下，根据算法名称和索引生成错误音符（丢锤/多锤）的详细图表
        
        Args:
            algorithm_name: 算法名称
            index: 音符索引（在initial_valid_record_data或initial_valid_replay_data中的索引）
            error_type: 错误类型，'drop'表示丢锤（录制有，播放无），'multi'表示多锤（播放有，录制无）
            
        Returns:
            Tuple[Any, Any, Any]: (录制音符图, 播放音符图, 对比图)
        """
        if not self.multi_algorithm_manager:
            self._ensure_multi_algorithm_manager()
        
        # 获取对应的算法数据集
        algorithm = self.multi_algorithm_manager.get_algorithm(algorithm_name)
        if not algorithm or not algorithm.is_ready():
            logger.error(f"算法 '{algorithm_name}' 不存在或未就绪")
            return None, None, None
        
        # 从算法的analyzer中获取数据
        if not algorithm.analyzer:
            logger.error(f"算法 '{algorithm_name}' 没有分析器")
            return None, None, None
        
        # 获取初始有效数据（第一次过滤后的数据，包含所有有效音符）
        initial_valid_record_data = getattr(algorithm.analyzer, 'initial_valid_record_data', None)
        initial_valid_replay_data = getattr(algorithm.analyzer, 'initial_valid_replay_data', None)
        
        if initial_valid_record_data is None or initial_valid_replay_data is None:
            logger.error(f"算法 '{algorithm_name}' 没有初始有效数据")
            return None, None, None
        
        # 获取匹配对列表，尝试查找是否有匹配的音符对
        # 注意：现在所有成功的匹配都在matched_pairs中，包括扩展候选匹配
        matched_pairs = getattr(algorithm.analyzer, 'matched_pairs', [])
        note_matcher = getattr(algorithm.analyzer, 'note_matcher', None)
        
        record_note = None
        play_note = None
        
        if error_type == 'drop':
            # 丢锤：录制有，播放可能无也可能有（如果超过阈值但能匹配到）
            if index < 0 or index >= len(initial_valid_record_data):
                logger.error(f"录制数据索引 {index} 超出范围 [0, {len(initial_valid_record_data)-1}]")
                return None, None, None
            record_note = initial_valid_record_data[index]
            
            # 验证NoteID：从表格数据中获取的keyId应该与音符的id一致
            if expected_key_id is not None:
                if str(record_note.id) != str(expected_key_id):
                    logger.error(f"❌ NoteID不匹配: 表格中的keyId={expected_key_id}, 音符的id={record_note.id}, 算法={algorithm_name}, index={index}")
                    return None, None, None
                logger.info(f"✅ NoteID验证通过: keyId={expected_key_id}, 音符id={record_note.id}")
            
            # 尝试从matched_pairs中查找匹配的播放音符
            play_note = None
            # 检查matched_pairs（现在包含所有成功的匹配）
            if matched_pairs:
                for record_index, replay_index, r_note, p_note in matched_pairs:
                    if record_index == index:
                        play_note = p_note
                        logger.info(f"🔍 丢锤数据在matched_pairs中找到匹配的播放音符: replay_index={replay_index}")
                        break
            # 如果没找到，再检查超过阈值的匹配对
            # 注意：现在所有匹配都在matched_pairs中，不需要额外检查
            
            if play_note is None:
                logger.info(f"✅ 生成丢锤详细曲线图（无匹配播放数据），算法={algorithm_name}, index={index}")
            else:
                logger.info(f"✅ 生成丢锤详细曲线图（有匹配播放数据，显示对比图），算法={algorithm_name}, index={index}")
                
        elif error_type == 'multi':
            # 多锤：播放有，录制可能无也可能有（如果超过阈值但能匹配到）
            if index < 0 or index >= len(initial_valid_replay_data):
                logger.error(f"播放数据索引 {index} 超出范围 [0, {len(initial_valid_replay_data)-1}]")
                return None, None, None
            play_note = initial_valid_replay_data[index]
            
            # 验证NoteID：从表格数据中获取的keyId应该与音符的id一致
            if expected_key_id is not None:
                if str(play_note.id) != str(expected_key_id):
                    logger.error(f"❌ NoteID不匹配: 表格中的keyId={expected_key_id}, 音符的id={play_note.id}, 算法={algorithm_name}, index={index}")
                    return None, None, None
                logger.info(f"✅ NoteID验证通过: keyId={expected_key_id}, 音符id={play_note.id}")
            
            # 尝试从matched_pairs中查找匹配的录制音符
            record_note = None
            # 检查matched_pairs（现在包含所有成功的匹配）
            if matched_pairs:
                for record_index, replay_index, r_note, p_note in matched_pairs:
                    if replay_index == index:
                        record_note = r_note
                        logger.info(f"🔍 多锤数据在matched_pairs中找到匹配的录制音符: record_index={record_index}")
                        break
            # 如果没找到，再检查超过阈值的匹配对
            # 注意：现在所有匹配都在matched_pairs中，不需要额外检查
            
            if record_note is None:
                logger.info(f"✅ 生成多锤详细曲线图（无匹配录制数据），算法={algorithm_name}, index={index}")
            else:
                logger.info(f"✅ 生成多锤详细曲线图（有匹配录制数据，显示对比图），算法={algorithm_name}, index={index}")
        else:
            logger.error(f"未知的错误类型: {error_type}")
            return None, None, None
        
        # 生成图表

        try:
            # 验证 Note 对象是否有效
            if error_type == 'drop' and record_note:
                logger.info(f"🔍 丢锤 - record_note ID={record_note.id}, after_touch长度={len(record_note.after_touch) if hasattr(record_note, 'after_touch') and record_note.after_touch is not None else 0}, hammers长度={len(record_note.hammers) if hasattr(record_note, 'hammers') and record_note.hammers is not None else 0}")
            elif error_type == 'multi' and play_note:
                logger.info(f"🔍 多锤 - play_note ID={play_note.id}, after_touch长度={len(play_note.after_touch) if hasattr(play_note, 'after_touch') and play_note.after_touch is not None else 0}, hammers长度={len(play_note.hammers) if hasattr(play_note, 'hammers') and play_note.hammers is not None else 0}")
            
            # 计算平均延时
            mean_delays = {}
            if algorithm and algorithm.analyzer:
                mean_error_0_1ms = algorithm.analyzer.get_mean_error()
                mean_delays[algorithm_name] = mean_error_0_1ms / 10.0  # 转换为毫秒

            detail_figure1 = spmid.plot_note_comparison_plotly(record_note, None, algorithm_name=algorithm_name, mean_delays=mean_delays)
            detail_figure2 = spmid.plot_note_comparison_plotly(None, play_note, algorithm_name=algorithm_name, mean_delays=mean_delays)
            detail_figure_combined = spmid.plot_note_comparison_plotly(record_note, play_note, algorithm_name=algorithm_name, mean_delays=mean_delays)
            
            # 验证图表是否有效
            if detail_figure1 is None or detail_figure2 is None or detail_figure_combined is None:
                logger.error(f"❌ 图表生成失败，部分图表为None")
                return None, None, None
            
            logger.info(f"✅ 图表生成成功: figure1数据点={len(detail_figure1.data)}, figure2数据点={len(detail_figure2.data)}, figure_combined数据点={len(detail_figure_combined.data)}")
            
            return detail_figure1, detail_figure2, detail_figure_combined
        except Exception as e:
            logger.error(f"❌ 生成图表时出错: {e}")
            
            logger.error(traceback.format_exc())
            return None, None, None
    
    # ==================== 数据过滤相关方法 ====================
    
    def apply_key_filter(self, key_ids: Optional[List[int]]) -> None:
        """应用按键过滤

        Args:
            key_ids: 要过滤的按键ID列表，None表示清除过滤
        """
        if key_ids is None:
            # 清除按键过滤
            self.data_filter.set_key_filter([])
        else:
            self.data_filter.set_key_filter(key_ids)

    def get_filter_info(self) -> Dict[str, Any]:
        """获取所有过滤器的状态信息

        Returns:
            Dict包含：
            - key_filter: 按键过滤状态
            - available_keys: 可用按键列表
            - time_filter: 时间过滤状态
            - time_range: 时间范围信息
            - display_time_range: 显示时间范围
        """
        return {
            'key_filter': self.data_filter.get_key_filter_status(),
            'available_keys': self.data_filter.get_available_keys(),
            'time_filter': self.time_filter.get_time_filter_status(),
            'time_range': self.time_filter.get_time_range(),
            'display_time_range': self.time_filter.get_display_time_range(),
            'time_range_info': self.time_filter.get_time_range_info()
        }
    
    def apply_time_filter(self, time_range: Optional[Tuple[float, float]]) -> None:
        """应用时间范围过滤

        Args:
            time_range: 时间范围元组 (start_time, end_time)，None表示清除过滤
        """
        self.time_filter.set_time_filter(time_range)

    def update_time_filter_from_input(self, start_time: float, end_time: float) -> Tuple[bool, str]:
        """从用户输入更新时间范围过滤

        Args:
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        success = self.time_filter.update_time_range_from_input(start_time, end_time)
        if success:
            return True, "时间范围更新成功"
        else:
            return False, "时间范围更新失败"

    def reset_time_filter(self) -> None:
        """重置时间范围过滤"""
        self.time_filter.reset_display_time_range()
    
    def get_filtered_data(self) -> Dict[str, Any]:
        """获取过滤后的数据"""
        return self.data_filter.get_filtered_data()
    
    # ==================== 表格数据相关方法 ====================
    
    def get_summary_info(self) -> Dict[str, Any]:
        """获取摘要信息"""
        return self.table_generator.get_summary_info()

    def calculate_accuracy_for_algorithm(self, algorithm) -> float:
        """
        为指定的算法计算准确率 - 重构版本

        使用统一的AlgorithmStatistics服务进行计算，确保前后端数据一致性

        Args:
            algorithm: 算法对象（具有analyzer属性）

        Returns:
            float: 准确率百分比
        """
        try:
            if not hasattr(algorithm, 'analyzer') or not algorithm.analyzer:
                return 0.0

            # 使用统一的统计服务
            stats_service = AlgorithmStatistics(algorithm)
            accuracy_info = stats_service.get_accuracy_info()

            # 输出调试信息
            algorithm_name = getattr(getattr(algorithm, 'metadata', None), 'algorithm_name', 'unknown')
            print(f"[DEBUG] 准确率计算 - 算法: {algorithm_name}")
            print(f"[DEBUG]   精确匹配: {accuracy_info['precision_matches']} 对")
            print(f"[DEBUG]   近似匹配: {accuracy_info['approximate_matches']} 对")
            print(f"[DEBUG]   总匹配对: {accuracy_info['matched_count']} 对")
            print(f"[DEBUG]   分子（匹配按键数）: {accuracy_info['matched_count'] * 2}")
            print(f"[DEBUG]   分母（总有效按键数）: {accuracy_info['total_effective_keys']}")
            print(f"[DEBUG]   准确率: {accuracy_info['accuracy']:.2f}%")

            return accuracy_info['accuracy']

        except Exception as e:
            logger.error(f"计算算法准确率失败: {e}")
            return 0.0

    def get_algorithm_statistics(self, algorithm) -> dict:
        """
        获取算法的完整统计信息 - 统一接口

        Args:
            algorithm: 算法对象

        Returns:
            dict: 包含准确率和错误统计的完整信息
        """
        try:
            if not hasattr(algorithm, 'analyzer') or not algorithm.analyzer:
                return {
                    'accuracy': 0.0,
                    'matched_count': 0,
                    'total_effective_keys': 0,
                    'precision_matches': 0,
                    'approximate_matches': 0,
                    'drop_count': 0,
                    'multi_count': 0,
                    'total_errors': 0
                }

            # 使用统一的统计服务
            stats_service = AlgorithmStatistics(algorithm)
            return stats_service.get_full_statistics()

        except Exception as e:
            logger.error(f"获取算法统计信息失败: {e}")
            return {
                'accuracy': 0.0,
                'matched_count': 0,
                'total_effective_keys': 0,
                'precision_matches': 0,
                'approximate_matches': 0,
                'drop_count': 0,
                'multi_count': 0,
                'total_errors': 0
            }
    
    def get_invalid_notes_table_data(self) -> List[Dict[str, Any]]:
        """
        获取无效音符表格数据（支持单算法和多算法模式）
        
        Returns:
            List[Dict[str, Any]]: 无效音符统计表格数据
        """
        # 获取激活的算法并生成数据
        active_algorithms = self.multi_algorithm_manager.get_active_algorithms() if self.multi_algorithm_manager else []
            
        if not active_algorithms:
            return []
            
        table_data = []
            
        for algorithm in active_algorithms:
            algorithm_name = algorithm.metadata.algorithm_name
            
            if not algorithm.analyzer:
                continue
            
            try:
                # 获取算法的无效音符统计数据
                invalid_notes_table_data = getattr(algorithm.analyzer, 'invalid_notes_table_data', {})
                
                if not invalid_notes_table_data:
                    # 如果没有数据，添加默认的空数据
                    table_data.append({
                        'algorithm_name': algorithm_name,
                        'data_type': '录制数据',
                        'total_notes': 0,
                        'valid_notes': 0,
                        'invalid_notes': 0,
                        'duration_too_short': 0,
                        'empty_data': 0,
                        'silent_notes': 0,
                        'other_errors': 0
                    })
                    table_data.append({
                        'algorithm_name': algorithm_name,
                        'data_type': '回放数据',
                        'total_notes': 0,
                        'valid_notes': 0,
                        'invalid_notes': 0,
                        'duration_too_short': 0,
                        'empty_data': 0,
                        'silent_notes': 0,
                        'other_errors': 0
                    })
                    continue
                
                # 处理录制数据
                record_data = invalid_notes_table_data.get('record_data', {})
                invalid_reasons = record_data.get('invalid_reasons', {})
                table_data.append({
                    'algorithm_name': algorithm_name,
                    'data_type': '录制数据',
                    'total_notes': record_data.get('total_notes', 0),
                    'valid_notes': record_data.get('valid_notes', 0),
                    'invalid_notes': record_data.get('invalid_notes', 0),
                    'duration_too_short': invalid_reasons.get('duration_too_short', 0),
                    'empty_data': invalid_reasons.get('empty_data', 0),
                    'silent_notes': invalid_reasons.get('silent_notes', 0),
                    'other_errors': invalid_reasons.get('other_errors', 0)
                })
                
                # 处理回放数据
                replay_data = invalid_notes_table_data.get('replay_data', {})
                replay_invalid_reasons = replay_data.get('invalid_reasons', {})
                table_data.append({
                    'algorithm_name': algorithm_name,
                    'data_type': '回放数据',
                    'total_notes': replay_data.get('total_notes', 0),
                    'valid_notes': replay_data.get('valid_notes', 0),
                    'invalid_notes': replay_data.get('invalid_notes', 0),
                    'duration_too_short': replay_invalid_reasons.get('duration_too_short', 0),
                    'empty_data': replay_invalid_reasons.get('empty_data', 0),
                    'silent_notes': replay_invalid_reasons.get('silent_notes', 0),
                    'other_errors': replay_invalid_reasons.get('other_errors', 0)
                })
                
            except Exception as e:
                logger.error(f"获取算法 '{algorithm_name}' 的无效音符统计数据失败: {e}")
                
                logger.error(traceback.format_exc())
                continue
        
        return table_data

    # TODO
    def get_error_table_data(self, error_type: str) -> List[Dict[str, Any]]:
        """获取错误表格数据（支持单算法和多算法模式）"""
        # 获取激活的算法并生成数据
        active_algorithms = self.multi_algorithm_manager.get_active_algorithms() if self.multi_algorithm_manager else []

        if not active_algorithms:
            return []
            
        table_data = []
        is_multi_algorithm = len(active_algorithms) > 1

        for algorithm in active_algorithms:
            algorithm_name = algorithm.metadata.algorithm_name
            
            if not algorithm.analyzer:
                continue
            
            # 获取该算法的错误数据
            if error_type == '丢锤':
                error_notes = algorithm.analyzer.drop_hammers if hasattr(algorithm.analyzer, 'drop_hammers') else []
            elif error_type == '多锤':
                error_notes = algorithm.analyzer.multi_hammers if hasattr(algorithm.analyzer, 'multi_hammers') else []
            else:
                continue
            # 记录该算法的错误数据详情
            if error_notes:
                logger.info(f"算法 '{algorithm_name}' {error_type}数据详情 ({len(error_notes)}个):")
                for i, note in enumerate(error_notes[:3]):  # 只显示前3个
                    if len(note.infos) > 0:
                        info = note.infos[0]
                        logger.info(f"  {error_type}{i+1}: 按键ID={info.keyId}, 索引={info.index}, keyOn={info.keyOn/10:.2f}ms")
                if len(error_notes) > 3:
                    logger.info(f"  ...还有{len(error_notes)-3}个{error_type}按键")
            # 转换为表格数据格式
            for note in error_notes:
                row = {
                    'data_type': 'record' if error_type == '丢锤' else 'play',
                    'keyId': note.keyId if hasattr(note, 'keyId') else 'N/A',
                }
                # 多算法模式时添加算法名称列
                if is_multi_algorithm:
                    row['algorithm_name'] = algorithm_name
                # 添加时间和索引信息
                if error_type == '丢锤':
                    row.update({
                        'keyOn': f"{note.keyOn/10:.2f}" if hasattr(note, 'keyOn') else 'N/A',
                        'keyOff': f"{note.keyOff/10:.2f}" if hasattr(note, 'keyOff') else 'N/A',
                        'index': note.index if hasattr(note, 'index') else 'N/A',
                        'analysis_reason': '丢锤（录制有，播放无）'
                    })
                else:  # 多锤
                    row.update({
                        'keyOn': f"{note.keyOn/10:.2f}" if hasattr(note, 'keyOn') else 'N/A',
                        'keyOff': f"{note.keyOff/10:.2f}" if hasattr(note, 'keyOff') else 'N/A',
                        'index': note.index if hasattr(note, 'index') else 'N/A',
                        'analysis_reason': '多锤（播放有，录制无）'
                    })
                table_data.append(row)

        return table_data
    
    
    # ==================== 延时关系分析相关方法 ====================
    def get_force_delay_by_key_analysis(self) -> Dict[str, Any]:
        """
        获取每个按键的力度与延时关系分析结果

        按按键ID分组，对每个按键分析其内部的力度（锤速）与延时的统计关系。
        包括：相关性分析、回归分析、描述性统计等。

        注意：每个按键至少需要2个样本才能进行相关性和回归分析。

        统一处理单算法和多算法模式：通过multi_algorithm_manager获取激活算法并生成分析结果。

        Returns:
            Dict[str, Any]: 分析结果，包含：
                单算法模式：
                - key_analysis: 每个按键的分析结果列表
                - overall_summary: 整体摘要统计
                - scatter_data: 散点图数据（按按键分组）
                - status: 状态标识

                多算法模式：
                - status: 状态标识
                - multi_algorithm_mode: True
                - algorithm_results: 各算法的完整结果字典
                - key_analysis: 第一个算法的结果（向后兼容）
                - overall_summary: 第一个算法的结果（向后兼容）
                - scatter_data: 第一个算法的结果（向后兼容）
        """
        try:
            # 获取激活的算法并生成数据
            active_algorithms = self.multi_algorithm_manager.get_active_algorithms() if self.multi_algorithm_manager else []

            if not active_algorithms:
                logger.warning("没有激活的算法，无法进行按键力度-延时分析")
                return {
                    'status': 'error',
                    'message': '没有激活的算法'
                }
                
            is_multi_algorithm = len(active_algorithms) > 1

            # 为每个算法生成分析结果
            algorithm_results = {}
            for algorithm in active_algorithms:
                if not algorithm.analyzer:
                    logger.warning(f"算法 '{algorithm.metadata.algorithm_name}' 没有分析器，跳过")
                    continue
                
                algorithm_name = algorithm.metadata.algorithm_name
                delay_analysis = DelayAnalysis(algorithm.analyzer)
                result = delay_analysis.analyze_force_delay_by_key()
                
                if result.get('status') == 'success':
                    algorithm_results[algorithm_name] = result
                    logger.info(f"算法 '{algorithm_name}' 的按键力度-延时分析完成")
            
            if not algorithm_results:
                logger.warning("没有成功分析的算法")
                return {
                    'status': 'error',
                    'message': '没有成功分析的算法'
                }
            
            # 返回结果
            if is_multi_algorithm:
                # 多算法模式：返回所有算法结果
                return {
                    'status': 'success',
                    'multi_algorithm_mode': True,
                    'algorithm_results': algorithm_results,
                    # 为了向后兼容，也包含第一个算法的结果
                    'key_analysis': list(algorithm_results.values())[0].get('key_analysis', []),
                    'overall_summary': list(algorithm_results.values())[0].get('overall_summary', {}),
                    'scatter_data': list(algorithm_results.values())[0].get('scatter_data', {}),
                }
            else:
                # 单算法模式：直接返回第一个（也是唯一的）算法结果
                single_result = list(algorithm_results.values())[0]
                logger.info("按键力度-延时分析完成")
                return single_result
            
        except Exception as e:
            logger.error(f"按键力度-延时分析失败: {e}")
            logger.error(traceback.format_exc())
            return {
                'status': 'error',
                'message': f'分析失败: {str(e)}'
            }
    
    def get_key_force_interaction_analysis(self) -> Dict[str, Any]:
        """
        获取按键与力度的交互效应图数据

        生成按键-力度交互效应图所需的数据，用于可视化分析按键和力度对延时的联合影响。

        统一处理单算法和多算法模式：通过multi_algorithm_manager获取激活算法并生成分析结果。

        Returns:
            Dict[str, Any]: 分析结果，包含：
                单算法模式：
                - interaction_plot_data: 交互效应图数据
                - status: 状态标识

                多算法模式：
                - status: 状态标识
                - multi_algorithm_mode: True
                - algorithm_results: 各算法的完整结果字典
                - interaction_plot_data: 第一个算法的结果（向后兼容）
        """
        try:
            # 获取激活的算法并生成数据
            active_algorithms = self.multi_algorithm_manager.get_active_algorithms() if self.multi_algorithm_manager else []

            if not active_algorithms:
                logger.warning("没有激活的算法，无法进行按键-力度交互分析")
                return {
                    'status': 'error',
                    'message': '没有激活的算法'
                }
                
            is_multi_algorithm = len(active_algorithms) > 1

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
                
            # 返回结果
            if is_multi_algorithm:
                # 多算法模式：返回所有算法结果
                return {
                    'status': 'success',
                    'multi_algorithm_mode': True,
                    'algorithm_results': algorithm_results,
                    # 为了向后兼容，也包含第一个算法的结果（用于交互效应强度等统计信息）
                    'two_way_anova': list(algorithm_results.values())[0].get('two_way_anova', {}),
                    'interaction_effect': list(algorithm_results.values())[0].get('interaction_effect', {}),
                    'stratified_regression': list(algorithm_results.values())[0].get('stratified_regression', {}),
                }
            else:
                # 单算法模式：直接返回第一个（也是唯一的）算法结果
                single_result = list(algorithm_results.values())[0]
                logger.info("按键-力度交互分析完成")
                return single_result
        
        except Exception as e:
            logger.error(f"按键-力度交互分析失败: {e}")
            
            logger.error(traceback.format_exc())
            return {
                'status': 'error',
                'message': f'分析失败: {str(e)}'
            }
    
    
    def generate_key_force_interaction_plot(self) -> Any:
        """
        生成按键-力度交互效应图
        
        Returns:
            Any: Plotly图表对象
        """
        try:
            analysis_result = self.get_key_force_interaction_analysis()
            
            if analysis_result.get('status') != 'success':
                return self.plot_generator._create_empty_plot("分析失败")
            
            return self.plot_generator.generate_key_force_interaction_plot(analysis_result)
            
        except Exception as e:
            logger.error(f"生成交互效应图失败: {e}")
            
            logger.error(traceback.format_exc())
            return self.plot_generator._create_empty_plot(f"生成失败: {str(e)}")
    
    # ==================== 多算法对比模式相关方法 ====================
    
    def _ensure_multi_algorithm_manager(self, max_algorithms: Optional[int] = None) -> None:
        """
        确保multi_algorithm_manager已初始化（多算法模式始终启用）

        Args:
            max_algorithms: 最大算法数量（None表示无限制）
        """
        if self.multi_algorithm_manager is None:
            self.multi_algorithm_manager = MultiAlgorithmManager(max_algorithms=max_algorithms)
            limit_text = "无限制" if max_algorithms is None else str(max_algorithms)
            logger.info(f"✅ 初始化多算法管理器 (最大算法数: {limit_text})")
    
    def enable_multi_algorithm_mode(self, max_algorithms: Optional[int] = None) -> Tuple[bool, bool, Optional[str]]:
        """
        启用多算法对比模式（向后兼容方法，现在只是确保管理器已初始化）
        
        Args:
            max_algorithms: 最大算法数量（None表示无限制）
            
        Returns:
            Tuple[bool, bool, Optional[str]]: (是否成功, 是否有现有数据需要迁移, 文件名)
        """
        try:
            self._ensure_multi_algorithm_manager(max_algorithms)
            
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
            logger.error(f"❌ 初始化多算法管理器失败: {e}")
            return False, False, None
    
    def migrate_existing_data_to_algorithm(self, algorithm_name: str) -> Tuple[bool, str]:
        """
        将现有的单算法分析数据迁移到多算法模式
        
        Args:
            algorithm_name: 用户指定的算法名称
            
        Returns:
            Tuple[bool, str]: (是否成功, 错误信息)
        """
        if not self.multi_algorithm_manager:
            self._ensure_multi_algorithm_manager()
        
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

            # 确保错误数据也同步到analyzer对象
            # 从table_generator获取当前的错误数据并同步
            if hasattr(self, 'table_generator') and self.table_generator:
                analyzer = self.table_generator.analyzer
                if analyzer and hasattr(analyzer, 'drop_hammers') and hasattr(analyzer, 'multi_hammers'):
                    algorithm.analyzer.drop_hammers = analyzer.drop_hammers
                    algorithm.analyzer.multi_hammers = analyzer.multi_hammers
                    algorithm.analyzer.silent_hammers = getattr(analyzer, 'silent_hammers', [])
                    logger.info(f"迁移时同步错误数据: 丢锤={len(algorithm.analyzer.drop_hammers)}, 多锤={len(algorithm.analyzer.multi_hammers)}")

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
            active_algorithms = self.multi_algorithm_manager.get_active_algorithms()

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
            active_algorithms = self.multi_algorithm_manager.get_active_algorithms()
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
        if not self.multi_algorithm_manager:
            self._ensure_multi_algorithm_manager()
        
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
    
    def get_same_algorithm_relative_delay_analysis(self) -> Dict[str, Any]:
        """
        分析同种算法不同曲子的相对延时分布
        
        识别逻辑：
        - display_name 相同：表示同种算法
        - algorithm_name 不同：表示不同曲子（因为文件名不同）
        
        Returns:
            Dict[str, Any]: 分析结果，包含：
                - status: 状态标识
                - algorithm_groups: 按算法分组的相对延时数据
                - overall_relative_delays: 所有曲子合并后的相对延时列表
                - statistics: 统计信息
        """
        try:
            if not self.multi_algorithm_manager:
                return {
                    'status': 'error',
                    'message': '多算法管理器不存在'
                }
            
            all_algorithms = self.multi_algorithm_manager.get_all_algorithms()
            if not all_algorithms:
                return {
                    'status': 'error',
                    'message': '没有算法数据'
                }
            
            # 按display_name分组，识别同种算法
            from collections import defaultdict
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
            all_relative_delays = []  # 合并所有曲子的相对延时
            
            for display_name, algorithms in same_algorithm_groups.items():
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
                        all_relative_delays.extend(relative_delays)
                        
                        # 从algorithm_name中提取文件名部分
                        filename_display = algorithm.metadata.filename
                        if '_' in algorithm.metadata.algorithm_name:
                            parts = algorithm.metadata.algorithm_name.rsplit('_', 1)
                            if len(parts) == 2:
                                filename_display = parts[1]
                        
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
                
                if group_relative_delays:
                    result_groups[display_name] = {
                        'relative_delays': group_relative_delays,  # 合并后的相对延时
                        'algorithms': group_info,  # 算法信息
                        'song_data': song_data  # 按曲子分组的数据
                    }
            
            if not all_relative_delays:
                return {
                    'status': 'error',
                    'message': '没有有效的相对延时数据'
                }
            
            # 计算统计信息
            relative_delays_array = np.array(all_relative_delays)
            
            statistics = {
                'mean': float(np.mean(relative_delays_array)),
                'std': float(np.std(relative_delays_array)),
                'median': float(np.median(relative_delays_array)),
                'min': float(np.min(relative_delays_array)),
                'max': float(np.max(relative_delays_array)),
                'q25': float(np.percentile(relative_delays_array, 25)),
                'q75': float(np.percentile(relative_delays_array, 75)),
                'iqr': float(np.percentile(relative_delays_array, 75) - np.percentile(relative_delays_array, 25)),
                'count': len(all_relative_delays),
                'cv': float(np.std(relative_delays_array) / abs(np.mean(relative_delays_array))) if np.mean(relative_delays_array) != 0 else float('inf')
            }
            
            # 计算±1σ、±2σ、±3σ范围内的数据占比
            std = statistics['std']
            mean = statistics['mean']
            within_1sigma = np.sum(np.abs(relative_delays_array - mean) <= std) / len(relative_delays_array) * 100
            within_2sigma = np.sum(np.abs(relative_delays_array - mean) <= 2 * std) / len(relative_delays_array) * 100
            within_3sigma = np.sum(np.abs(relative_delays_array - mean) <= 3 * std) / len(relative_delays_array) * 100
            
            statistics['within_1sigma_percent'] = float(within_1sigma)
            statistics['within_2sigma_percent'] = float(within_2sigma)
            statistics['within_3sigma_percent'] = float(within_3sigma)
            
            logger.info(f"同种算法相对延时分析完成，共 {len(same_algorithm_groups)} 个算法组，{len(all_relative_delays)} 个数据点")
            
            return {
                'status': 'success',
                'algorithm_groups': result_groups,
                'overall_relative_delays': all_relative_delays,
                'statistics': statistics
            }
            
        except Exception as e:
            logger.error(f"分析同种算法相对延时分布失败: {e}")
            
            logger.error(traceback.format_exc())
            return {
                'status': 'error',
                'message': f'分析失败: {str(e)}'
            }
    
    def get_relative_delay_range_data_points_by_subplot(
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
            if not self.multi_algorithm_manager:
                return []
            
            all_algorithms = self.multi_algorithm_manager.get_all_algorithms()
            filtered_data = []
            
            for algorithm in all_algorithms:
                if not algorithm.is_ready():
                    continue
                
                # 检查算法是否属于指定的display_name组
                if algorithm.metadata.display_name != display_name:
                    continue
                
                # 如果是汇总图，包含该组所有算法；否则只包含指定文件名的算法
                if filename_display != '汇总':
                    # 从algorithm_name中提取文件名部分
                    algorithm_filename = algorithm.metadata.filename
                    if '_' in algorithm.metadata.algorithm_name:
                        parts = algorithm.metadata.algorithm_name.rsplit('_', 1)
                        if len(parts) == 2:
                            algorithm_filename = parts[1]
                    
                    if algorithm_filename != filename_display:
                        continue
                
                if not algorithm.analyzer or not algorithm.analyzer.note_matcher:
                    continue
                
                # 获取偏移数据
                offset_data = algorithm.analyzer.get_offset_alignment_data()
                if not offset_data:
                    continue
                
                algorithm_name = algorithm.metadata.algorithm_name
                
                # 计算该算法的平均延时（用于计算相对延时）
                absolute_delays_ms = [item.get('keyon_offset', 0.0) / 10.0 for item in offset_data]
                if not absolute_delays_ms:
                    continue
                
                mean_delay_ms = sum(absolute_delays_ms) / len(absolute_delays_ms)
                
                # 筛选出指定相对延时范围内的数据点
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
            
        except Exception as e:
            logger.error(f"获取相对延时范围数据点失败: {e}")
            
            logger.error(traceback.format_exc())
            return []
    
    def generate_relative_delay_distribution_plot(self) -> Any:
        """
        生成同种算法不同曲子的相对延时分布图
        
        Returns:
            Any: Plotly图表对象
        """
        try:
            analysis_result = self.get_same_algorithm_relative_delay_analysis()
            
            if analysis_result.get('status') != 'success':
                return self.plot_generator._create_empty_plot(
                    analysis_result.get('message', '分析失败')
                )
            
            # 使用多算法图表生成器
            return self.multi_algorithm_plot_generator.generate_relative_delay_distribution_plot(analysis_result)
            
        except Exception as e:
            logger.error(f"生成相对延时分布图失败: {e}")
            logger.error(traceback.format_exc())
            return self.plot_generator._create_empty_plot(f"生成失败: {str(e)}")


    def get_graded_error_stats(self, algorithm=None) -> Dict[str, Any]:
        """
        获取分级误差统计数据

        Args:
            algorithm: 指定算法（用于多算法模式下的单算法查询）

        Returns:
            Dict[str, Any]: 包含各级别误差统计的数据
        """
        try:
            # 如果指定了算法，使用该算法的数据
            if algorithm:
                if algorithm.analyzer and algorithm.analyzer.note_matcher:
                    return algorithm.analyzer.note_matcher.get_graded_error_stats()
                else:
                    return {'error': f'算法 {algorithm} 没有有效的分析器'}

            # 获取激活的算法并生成数据
            active_algorithms = self.multi_algorithm_manager.get_active_algorithms() if self.multi_algorithm_manager else []

            if not active_algorithms:
                return {'error': '没有激活的算法'}

            is_multi_algorithm = len(active_algorithms) > 1

            # 多算法模式：汇总所有激活算法的评级统计
            if is_multi_algorithm:
                total_stats = {
                    'correct': {'count': 0, 'percent': 0.0},
                    'minor': {'count': 0, 'percent': 0.0},
                    'moderate': {'count': 0, 'percent': 0.0},
                    'large': {'count': 0, 'percent': 0.0},
                    'severe': {'count': 0, 'percent': 0.0}
                }

                total_count = 0
                for algorithm in active_algorithms:
                    if algorithm.analyzer and algorithm.analyzer.note_matcher:
                        alg_stats = algorithm.analyzer.note_matcher.get_graded_error_stats()
                        if alg_stats and 'error' not in alg_stats:
                            for level in ['correct', 'minor', 'moderate', 'large', 'severe']:
                                if level in alg_stats:
                                    total_stats[level]['count'] += alg_stats[level].get('count', 0)
                                    total_count += alg_stats[level].get('count', 0)

                # 计算百分比，确保总和为100%（保留4位小数）
                if total_count > 0:
                    # 先计算原始百分比
                    raw_percentages = {}
                    for level in ['correct', 'minor', 'moderate', 'large', 'severe']:
                        raw_percentages[level] = (total_stats[level]['count'] / total_count) * 100.0

                    # 保留4位小数并四舍五入
                    rounded_percentages = {}
                    for level in ['correct', 'minor', 'moderate', 'large', 'severe']:
                        rounded_percentages[level] = round(raw_percentages[level], 4)

                    # 调整最后一个百分比以确保总和为100%
                    total_rounded = sum(rounded_percentages.values())
                    if total_rounded != 100.0:
                        # 找出最大的百分比进行调整
                        max_level = max(rounded_percentages.keys(), key=lambda x: rounded_percentages[x])
                        rounded_percentages[max_level] += (100.0 - total_rounded)

                    # 设置最终百分比
                    for level in ['correct', 'minor', 'moderate', 'large', 'severe']:
                        total_stats[level]['percent'] = rounded_percentages[level]

                return total_stats

            # 单算法模式
            else:
                single_algorithm = active_algorithms[0]
                if not single_algorithm.analyzer or not single_algorithm.analyzer.note_matcher:
                    return {'error': '算法没有有效的分析器或音符匹配器'}

                stats = single_algorithm.analyzer.note_matcher.get_graded_error_stats()
            return stats

        except Exception as e:
            logger.error(f"获取分级误差统计失败: {e}")
            return {'error': str(e)}

