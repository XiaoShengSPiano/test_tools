#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
表格数据生成模块
纯粹的数据转换工具类，负责将领域对象转换为UI表格格式
"""

from typing import List, Dict, Any, Optional
from utils.logger import Logger

logger = Logger.get_logger()


class TableDataGenerator:
    """
    表格数据生成器 - 负责生成各类UI表格数据
    
    职责：
    1. 生成摘要信息表格
    2. 生成错误音符表格（丢锤/多锤）
    3. 生成无效音符统计表格/详情
    """
    
    def __init__(self, backend):
        """
        初始化表格数据生成器
        
        Args:
            backend: PianoAnalysisBackend实例
        """
        self.backend = backend
    
    def get_summary_info(self) -> Dict[str, Any]:
        """获取摘要信息"""
        analyzer = self.backend._get_current_analyzer()
        if not analyzer:
            return self._generate_empty_summary()
        
        # 获取统计数据 (直接使用 analyzer 提供的统计信息)
        stats = getattr(analyzer, 'get_analysis_stats', lambda: {})()
        
        return {
            'total_notes': max(stats.get('total_record_notes', 0) + stats.get('record_invalid_notes', 0),
                              stats.get('total_replay_notes', 0) + stats.get('replay_invalid_notes', 0)),
            'valid_notes': stats.get('matched_pairs', 0),
            'invalid_notes': stats.get('record_invalid_notes', 0) + stats.get('replay_invalid_notes', 0),
            'multi_hammers': stats.get('multi_hammers', 0),
            'drop_hammers': stats.get('drop_hammers', 0),
            'total_errors': stats.get('drop_hammers', 0) + stats.get('multi_hammers', 0),
            'data_source': {
                'total_valid_record': stats.get('total_record_notes', 0),
                'total_valid_replay': stats.get('total_replay_notes', 0),
                'total_valid_record_with_splits': stats.get('total_record_notes', 0), # 拆分后数据现已统一
                'total_valid_replay_with_splits': stats.get('total_replay_notes', 0)
            },
            'error_analysis': {
                'drop_hammers': stats.get('drop_hammers', 0),
                'multi_hammers': stats.get('multi_hammers', 0),
                'total_errors': stats.get('drop_hammers', 0) + stats.get('multi_hammers', 0)
            },
            'matching_analysis': {
                'matched_pairs': stats.get('matched_pairs', 0)
            },
            'invalid_notes_detail': {
                'invalid_record': stats.get('record_invalid_notes', 0),
                'invalid_replay': stats.get('replay_invalid_notes', 0),
                'total_invalid': stats.get('record_invalid_notes', 0) + stats.get('replay_invalid_notes', 0)
            }
        }
    
    def get_invalid_notes_table_data(self) -> List[Dict[str, Any]]:
        """获取无效音符统计表格数据"""
        active_algorithms = self.backend.get_active_algorithms()
        table_data = []
        
        for algorithm in active_algorithms:
            if not algorithm.analyzer or not algorithm.analyzer.invalid_statistics:
                table_data.extend(self._generate_empty_invalid_notes_data(algorithm.metadata.algorithm_name))
                continue
            
            try:
                table_data.extend(algorithm.analyzer.invalid_statistics.to_table_data(
                    algorithm_name=algorithm.metadata.algorithm_name
                ))
            except Exception as e:
                logger.error(f"获取算法 {algorithm.metadata.algorithm_name}统计失败: {e}")
        
        return table_data
    
    def get_invalid_notes_detail_table_data(self, data_type: str) -> List[Dict[str, Any]]:
        """获取无效音符详细列表数据"""
        active_algorithms = self.backend.get_active_algorithms()
        table_data = []
        
        for algorithm in active_algorithms:
            if not algorithm.analyzer or not algorithm.analyzer.invalid_statistics:
                continue
            
            try:
                detail_data = algorithm.analyzer.invalid_statistics.get_detailed_table_data(data_type)
                # 在每一行注入算法名称，用于多算法模式下的筛选
                for row in detail_data:
                    row['algorithm_name'] = algorithm.metadata.algorithm_name
                table_data.extend(detail_data)
            except Exception as e:
                logger.error(f"获取算法详细无效数据失败: {e}")
        
        return table_data
    
    def get_error_table_data(self, error_type: str) -> List[Dict[str, Any]]:
        """获取错误表格数据（丢锤/多锤）"""
        active_algorithms = self.backend.get_active_algorithms()
        table_data = []

        for algorithm in active_algorithms:
            analyzer = algorithm.analyzer
            if not analyzer:
                continue
            
            error_notes = analyzer.drop_hammers if error_type == '丢锤' else analyzer.multi_hammers
            reason = f'{error_type}（{"录制有，播放无" if error_type == "丢锤" else "播放有，录制无"}）'
            data_type = 'record' if error_type == '丢锤' else 'play'

            for note in error_notes:
                if not note: continue
                
                velocity = note.first_hammer_velocity
                table_data.append({
                    'algorithm_name': algorithm.metadata.algorithm_name,
                    'data_type': data_type,
                    'keyId': note.id,
                    'keyOn': f"{note.key_on_ms:.2f}" if note.key_on_ms is not None else 'N/A',
                    'keyOff': f"{note.key_off_ms:.2f}" if note.key_off_ms is not None else 'N/A',
                    'duration': f"{note.duration_ms:.2f}" if note.duration_ms is not None else 'N/A',
                    'velocity': int(velocity) if velocity is not None else 'N/A',
                    'index': note.uuid,
                    'analysis_reason': reason
                })
        
        return table_data
    
    def _generate_empty_summary(self) -> Dict[str, Any]:
        """工厂方法：生成空的摘要"""
        return {
            'total_notes': 0, 'valid_notes': 0, 'invalid_notes': 0,
            'multi_hammers': 0, 'drop_hammers': 0, 'total_errors': 0,
            'data_source': {'total_valid_record': 0, 'total_valid_replay': 0},
            'error_analysis': {'drop_hammers': 0, 'multi_hammers': 0, 'total_errors': 0},
            'matching_analysis': {'matched_pairs': 0},
            'invalid_notes_detail': {'invalid_record': 0, 'invalid_replay': 0, 'total_invalid': 0}
        }
    
    def _generate_empty_invalid_notes_data(self, algorithm_name: str) -> List[Dict[str, Any]]:
        """生成空的统计行示例"""
        return [{
            'algorithm_name': algorithm_name,
            'data_type': dt,
            'total_notes': 0, 'valid_notes': 0, 'invalid_notes': 0,
            'low_after_value': 0, 'short_duration': 0, 'empty_data': 0, 'other_errors': 0
        } for dt in ['录制数据', '回放数据']]

