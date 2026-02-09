#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
表格数据生成模块
纯粹的数据转换工具类，负责将领域对象转换为UI表格格式
"""
import traceback
from typing import List, Dict, Any, Optional
from utils.logger import Logger

logger = Logger.get_logger()


class TableDataGenerator:
    """
    表格数据生成器 - 负责生成各类UI表格数据
    
    职责：
    1. 生成摘要信息表格
    2. 生成错误音符表格（丢锤/多锤）
    3. 生成无效音符统计表格
    4. 生成无效音符详细列表表格
    """
    
    def __init__(self, backend):
        """
        初始化表格数据生成器
        
        Args:
            backend: PianoAnalysisBackend实例（用于获取算法数据）
        """
        self.backend = backend
    
    def get_summary_info(self) -> Dict[str, Any]:
        """
        获取摘要信息
        
        Returns:
            Dict[str, Any]: 摘要信息字典
        """
        analyzer = self.backend._get_current_analyzer()
        if not analyzer:
            return self._generate_empty_summary()
        
        # 从 analyzer 获取所需数据
        return self.generate_summary_info(
            invalid_statistics=analyzer.invalid_statistics,
            multi_hammers=analyzer.multi_hammers,
            drop_hammers=analyzer.drop_hammers,
            matched_pairs=analyzer.matched_pairs,
            initial_valid_record_data=analyzer.initial_valid_record_data,
            initial_valid_replay_data=analyzer.initial_valid_replay_data,
            note_matcher=analyzer.note_matcher
        )
    
    def get_invalid_notes_table_data(self) -> List[Dict[str, Any]]:
        """
        获取无效音符表格数据（支持单算法和多算法模式）
        
        Returns:
            List[Dict[str, Any]]: 无效音符统计表格数据
        """
        active_algorithms = self.backend.get_active_algorithms()
        
        if not active_algorithms:
            return []
        
        table_data = []
        
        for algorithm in active_algorithms:
            algorithm_name = algorithm.metadata.algorithm_name
            
            if not algorithm.analyzer:
                continue
            
            try:
                invalid_statistics = algorithm.analyzer.invalid_statistics
                
                if invalid_statistics is None:
                    # 添加默认的空数据
                    table_data.extend(self._generate_empty_invalid_notes_data(algorithm_name))
                    continue
                
                # 直接调用统计对象的方法生成表格数据
                algorithm_table_data = invalid_statistics.to_table_data(algorithm_name=algorithm_name)
                table_data.extend(algorithm_table_data)
                
            except Exception as e:
                logger.error(f"获取算法 '{algorithm_name}' 的无效音符统计数据失败: {e}")
                logger.error(traceback.format_exc())
                continue
        
        return table_data
    
    def get_invalid_notes_detail_table_data(self, data_type: str) -> List[Dict[str, Any]]:
        """
        获取无效音符详细列表数据（支持单算法和多算法模式）
        
        Args:
            data_type: 数据类型（'录制' 或 '播放'）
        
        Returns:
            List[Dict[str, Any]]: 详细表格数据
        """
        active_algorithms = self.backend.get_active_algorithms()
        
        if not active_algorithms:
            return []
        
        table_data = []
        
        for algorithm in active_algorithms:
            algorithm_name = algorithm.metadata.algorithm_name
            
            if not algorithm.analyzer:
                continue
            
            try:
                invalid_statistics = algorithm.analyzer.invalid_statistics
                
                if invalid_statistics is None:
                    continue
                
                # 调用统计对象的方法获取详细数据
                detail_data = invalid_statistics.get_detailed_table_data(data_type)
                table_data.extend(detail_data)
                
            except Exception as e:
                logger.error(f"获取算法 '{algorithm_name}' 的无效音符详细数据失败: {e}")
                logger.error(traceback.format_exc())
                continue
        
        return table_data
    
    def get_error_table_data(self, error_type: str) -> List[Dict[str, Any]]:
        """
        获取错误表格数据（支持单算法和多算法模式）
        
        Args:
            error_type: 错误类型（'丢锤' 或 '多锤'）
        
        Returns:
            List[Dict[str, Any]]: 错误表格数据
        """
        active_algorithms = self.backend.get_active_algorithms()
        
        if not active_algorithms:
            logger.error("[ERROR] 没有活跃算法")
            return []
        
        table_data = []

        
        for algorithm in active_algorithms:
            algorithm_name = algorithm.metadata.algorithm_name
            
            if not algorithm.analyzer:
                continue
            
            # 获取该算法的错误数据
            if error_type == '丢锤':
                error_notes = algorithm.analyzer.drop_hammers
            elif error_type == '多锤':
                error_notes = algorithm.analyzer.multi_hammers
            else:
                continue

            # 确定错误原因描述和数据类型
            if error_type == '丢锤':
                analysis_reason = '丢锤（录制有，播放无）'
                data_type = 'record'  # 丢锤显示录制轨道数据
            else:  # 多锤
                analysis_reason = '多锤（播放有，录制无）'
                data_type = 'play'  # 多锤显示播放轨道数据

            # 转换为表格数据格式
            for error_note in error_notes:
                if not error_note:
                    continue

                note = error_note
                # 获取锤速数据
                hammer_velocity = note.get_first_hammer_velocity()

                # 显示锤速：有值显示值，无值显示N/A
                if hammer_velocity is not None and hammer_velocity != 0:
                    velocity_display = hammer_velocity
                elif hammer_velocity == 0:
                    velocity_display = 0
                else:
                    # hammer_velocity is None，表示没有hammer数据
                    velocity_display = 'N/A'

                row = {
                    'data_type': data_type,
                    'keyId': note.id,
                    'keyOn': f"{note.key_on_ms:.2f}" if note.key_on_ms is not None else 'N/A',
                    'keyOff': f"{note.key_off_ms:.2f}" if note.key_off_ms is not None else 'N/A',
                    'duration': f"{note.duration_ms:.2f}" if note.duration_ms is not None else 'N/A',
                    'velocity': velocity_display,
                    'index': error_note.uuid,
                    'analysis_reason': analysis_reason
                }

                row['algorithm_name'] = algorithm_name

                table_data.append(row)
        
        return table_data
    
    def _generate_empty_summary(self) -> Dict[str, Any]:
        """生成空的摘要信息"""
        return self.generate_summary_info(
            invalid_statistics=None,
            multi_hammers=[],
            drop_hammers=[],
            matched_pairs=[],
            initial_valid_record_data=[],
            initial_valid_replay_data=[],
            note_matcher=None
        )
    
    def _generate_empty_invalid_notes_data(self, algorithm_name: str) -> List[Dict[str, Any]]:
        """生成空的无效音符数据"""
        return [
            {
                'algorithm_name': algorithm_name,
                'data_type': '录制数据',
                'total_notes': 0,
                'valid_notes': 0,
                'invalid_notes': 0,
                'low_after_value': 0,
                'short_duration': 0,
                'empty_data': 0,
                'other_errors': 0
            },
            {
                'algorithm_name': algorithm_name,
                'data_type': '回放数据',
                'total_notes': 0,
                'valid_notes': 0,
                'invalid_notes': 0,
                'low_after_value': 0,
                'short_duration': 0,
                'empty_data': 0,
                'other_errors': 0
            }
        ]
    

    @staticmethod
    def generate_summary_info(
        invalid_statistics: Optional[Any],
        multi_hammers: List[Any],
        drop_hammers: List[Any],
        matched_pairs: List[Any],
        initial_valid_record_data: Optional[List[Any]] = None,
        initial_valid_replay_data: Optional[List[Any]] = None,
        note_matcher: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        生成摘要信息
        
        Args:
            invalid_statistics: 无效音符统计对象
            multi_hammers: 多锤列表
            drop_hammers: 丢锤列表
            matched_pairs: 匹配对列表
            initial_valid_record_data: 初始有效录制数据
            initial_valid_replay_data: 初始有效播放数据
            note_matcher: 音符匹配器对象
            
        Returns:
            Dict[str, Any]: 摘要信息字典
        """
        try:
            # 计算统计数据
            initial_valid_record_data = initial_valid_record_data or []
            initial_valid_replay_data = initial_valid_replay_data or []
            
            total_valid_record = len(initial_valid_record_data)
            total_valid_replay = len(initial_valid_replay_data)
            
            # 获取拆分统计
            split_stats = {
                'split_count': 0, 
                'additional_notes': 0,
                'record_split_count': 0,
                'replay_split_count': 0,
                'additional_record_notes': 0,
                'additional_replay_notes': 0
            }
            if note_matcher and hasattr(note_matcher, 'get_split_statistics'):
                split_stats = note_matcher.get_split_statistics()
            
            # 调整有效按键数量（加上拆分产生的额外按键）
            total_valid_record_with_splits = total_valid_record + split_stats['additional_record_notes']
            total_valid_replay_with_splits = total_valid_replay + split_stats['additional_replay_notes']
            
            # 错误统计
            drop_hammer_count = len(drop_hammers)
            multi_hammer_count = len(multi_hammers)
            total_errors = drop_hammer_count + multi_hammer_count
            
            # 匹配统计
            matched_pairs_count = len(matched_pairs)
            
            # 无效音符统计
            invalid_record_count = 0
            invalid_replay_count = 0
            if invalid_statistics:
                summary = invalid_statistics.get_summary()
                invalid_record_count = summary['record']['invalid']
                invalid_replay_count = summary['replay']['invalid']
            
            # 计算总音符数
            total_record_notes = total_valid_record + invalid_record_count
            total_replay_notes = total_valid_replay + invalid_replay_count
            total_notes = max(total_record_notes, total_replay_notes)
            
            # 无效音符数
            total_invalid_notes = invalid_record_count + invalid_replay_count
            
            # 获取所有已配对的数据（包括宽松匹配）
            total_matched_pairs = matched_pairs_count
            if note_matcher:
                loose_matched_pairs = getattr(note_matcher, 'loose_matched_pairs', [])
                if loose_matched_pairs:
                    total_matched_pairs += len(loose_matched_pairs)
            
            
            return {
                'total_notes': total_notes,
                'valid_notes': total_matched_pairs,
                'invalid_notes': total_invalid_notes,
                'multi_hammers': multi_hammer_count,
                'drop_hammers': drop_hammer_count,
                'total_errors': total_errors,
                'data_source': {
                    'total_valid_record': total_valid_record,
                    'total_valid_replay': total_valid_replay,
                    'total_valid_record_with_splits': total_valid_record_with_splits,
                    'total_valid_replay_with_splits': total_valid_replay_with_splits,
                    'split_count': split_stats['split_count'],
                    'record_split_count': split_stats['record_split_count'],
                    'replay_split_count': split_stats['replay_split_count'],
                    'additional_record_notes': split_stats['additional_record_notes'],
                    'additional_replay_notes': split_stats['additional_replay_notes']
                },
                'error_analysis': {
                    'drop_hammers': drop_hammer_count,
                    'multi_hammers': multi_hammer_count,
                    'total_errors': total_errors
                },
                'matching_analysis': {
                    'matched_pairs': matched_pairs_count
                },
                'invalid_notes_detail': {
                    'invalid_record': invalid_record_count,
                    'invalid_replay': invalid_replay_count,
                    'total_invalid': invalid_record_count + invalid_replay_count
                }
            }
            
        except Exception as e:
            logger.error(f"生成摘要信息失败: {e}")
            return {
                'total_notes': 0,
                'valid_notes': 0,
                'invalid_notes': 0,
                'multi_hammers': 0,
                'drop_hammers': 0,
                'total_errors': 0,
                'data_source': {
                    'total_valid_record': 0,
                    'total_valid_replay': 0
                },
                'error_analysis': {
                    'drop_hammers': 0,
                    'multi_hammers': 0,
                    'total_errors': 0
                },
                'matching_analysis': {
                    'matched_pairs': 0
                },
                'invalid_notes_detail': {
                    'invalid_record': 0,
                    'invalid_replay': 0,
                    'total_invalid': 0
                },
                'error': f'生成摘要信息失败: {str(e)}'
            }

