#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
表格数据生成模块
负责错误表格、摘要信息、偏移对齐数据等表格数据的生成
"""

from typing import List, Dict, Any, Optional
from utils.logger import Logger

logger = Logger.get_logger()


class TableDataGenerator:
    """表格数据生成器 - 负责各种表格数据的生成"""
    
    def __init__(self):
        """初始化表格数据生成器"""
        # 只保留最终有效数据，移除原始数据
        self.valid_record_data = None
        self.valid_replay_data = None
        self.multi_hammers = []
        self.drop_hammers = []
        self.silent_hammers = []
        self.all_error_notes = []
        self.invalid_notes_table_data = {}
        self.matched_pairs = []
        self.analyzer = None  # SPMIDAnalyzer实例
    
    def set_data(self, valid_record_data=None, valid_replay_data=None,
                 multi_hammers=None, drop_hammers=None, silent_hammers=None, all_error_notes=None,
                 invalid_notes_table_data=None, matched_pairs=None, analyzer=None):
        self.valid_record_data = valid_record_data
        self.valid_replay_data = valid_replay_data
        self.multi_hammers = multi_hammers or []
        self.drop_hammers = drop_hammers or []
        self.silent_hammers = silent_hammers or []
        self.all_error_notes = all_error_notes or []
        self.invalid_notes_table_data = invalid_notes_table_data or {}
        self.matched_pairs = matched_pairs or []
        self.analyzer = analyzer
    
    
    def _build_error_table_rows(self, target_error_type: str) -> List[Dict[str, Any]]:
        """
        构建错误表格行数据
        
        Args:
            target_error_type: 目标错误类型 ('丢锤' 或 '多锤')
            
        Returns:
            List[Dict[str, Any]]: 表格行数据列表
        """
        table_data = []
        
        # 筛选目标错误类型
        target_errors = []
        if target_error_type == '丢锤':
            target_errors = self.drop_hammers
        elif target_error_type == '多锤':
            target_errors = self.multi_hammers
        
        # 获取note_matcher的匹配失败原因（用于更详细的分析）
        failure_reasons = {}
        if self.analyzer and hasattr(self.analyzer, 'note_matcher'):
            failure_reasons = getattr(self.analyzer.note_matcher, 'failure_reasons', {})
        
        for error_note in target_errors:
            # 根据错误类型决定显示逻辑
            if target_error_type == '丢锤':
                # 丢锤：录制有，播放没有
                if len(error_note.infos) > 0:
                    rec = error_note.infos[0]
                    
                # 获取详细的匹配失败原因
                # 优先使用ErrorNote中的reason字段，如果没有则从failure_reasons中获取
                analysis_reason = getattr(error_note, 'reason', None)
                # 如果reason是None或空字符串，尝试从failure_reasons中获取
                if not analysis_reason:
                    if ('record', rec.index) in failure_reasons:
                        analysis_reason = failure_reasons[('record', rec.index)]
                    else:
                        analysis_reason = ''  # 没有原因就保持为空
                
                table_data.append({
                    'global_index': error_note.global_index,
                    'problem_type': error_note.error_type,
                    'data_type': 'record',
                    'keyId': rec.keyId,
                    'keyOn': f"{rec.keyOn/10:.2f}ms",
                    'keyOff': f"{rec.keyOff/10:.2f}ms",
                    'index': rec.index,
                    'analysis_reason': analysis_reason
                })
                # 播放行显示"无匹配"
                table_data.append({
                    'global_index': error_note.global_index,
                    'problem_type': '',
                    'data_type': 'play',
                    'keyId': '无匹配',
                    'keyOn': '无匹配',
                    'keyOff': '无匹配',
                    'index': '无匹配',
                    'analysis_reason': ''
                })
            
            elif target_error_type == '多锤':
                # 多锤：播放有，录制没有
                if len(error_note.infos) > 0:
                    play = error_note.infos[0]
                    
                # 多锤的分析原因
                # 优先使用ErrorNote中的reason字段，如果没有则从failure_reasons中获取
                analysis_reason = getattr(error_note, 'reason', None)
                # 如果reason是None或空字符串，尝试从failure_reasons中获取
                # 注意：播放数据的失败原因可能不存在，因为匹配是以录制数据为基准的
                if not analysis_reason:
                    # 注意：现在所有匹配都在matched_pairs中
                    analysis_reason = ''
                
                # 录制行显示"无匹配"
                table_data.append({
                    'global_index': error_note.global_index,
                    'problem_type': error_note.error_type,
                    'data_type': 'record',
                    'keyId': '无匹配',
                    'keyOn': '无匹配',
                    'keyOff': '无匹配',
                    'index': '无匹配',
                    'analysis_reason': ''
                })
                # 播放行显示实际数据
                table_data.append({
                    'global_index': error_note.global_index,
                    'problem_type': '',
                    'data_type': 'play',
                    'keyId': play.keyId,
                    'keyOn': f"{play.keyOn/10:.2f}ms",
                    'keyOff': f"{play.keyOff/10:.2f}ms",
                    'index': play.index,
                    'analysis_reason': analysis_reason
                })
        
        return table_data
    
    def get_error_table_data(self, error_type: str) -> List[Dict[str, Any]]:
        """
        获取错误表格数据
        
        Args:
            error_type: 错误类型 ('丢锤' 或 '多锤')
            
        Returns:
            List[Dict[str, Any]]: 错误表格数据
        """
        try:
            return self._build_error_table_rows(error_type)
        except Exception as e:
            logger.error(f"获取错误表格数据失败: {e}")
            return []
    
    def get_summary_info(self) -> Dict[str, Any]:
        """
        获取摘要信息 - 基于最终有效数据
        
        Returns:
            Dict[str, Any]: 摘要信息
        """
        try:
            # 计算统计数据 - 使用初始有效数据（第一次过滤后）
            initial_valid_record = getattr(self.analyzer, 'initial_valid_record_data', None) if self.analyzer else None
            initial_valid_replay = getattr(self.analyzer, 'initial_valid_replay_data', None) if self.analyzer else None
            
            total_valid_record = len(initial_valid_record) if initial_valid_record else 0
            total_valid_replay = len(initial_valid_replay) if initial_valid_replay else 0
            
            # 错误统计
            drop_hammer_count = len(self.drop_hammers)
            multi_hammer_count = len(self.multi_hammers)
            silent_hammer_count = len(self.silent_hammers)
            total_errors = drop_hammer_count + multi_hammer_count + silent_hammer_count
            
            # 匹配统计
            matched_pairs_count = len(self.matched_pairs)
            
            # 无效音符统计
            invalid_record_count = 0
            invalid_replay_count = 0
            if self.invalid_notes_table_data:
                record_stats = self.invalid_notes_table_data.get('record_data', {})
                replay_stats = self.invalid_notes_table_data.get('replay_data', {})
                invalid_record_count = record_stats.get('invalid_notes', 0)
                invalid_replay_count = replay_stats.get('invalid_notes', 0)
            
            # 计算统计数据
            # 总音符数 = 原始数据总数（录制和播放中的较大值）
            total_record_notes = total_valid_record + invalid_record_count
            total_replay_notes = total_valid_replay + invalid_replay_count
            total_notes = max(total_record_notes, total_replay_notes)
            
            # 无效音符数 = 被数据过滤器过滤掉的音符总数
            total_invalid_notes = invalid_record_count + invalid_replay_count
            
            # 获取所有已配对的数据（包括宽松匹配）
            total_matched_pairs = matched_pairs_count

            # 加上宽松匹配对
            if self.analyzer and hasattr(self.analyzer, 'note_matcher'):
                note_matcher = self.analyzer.note_matcher
                loose_matched_pairs = getattr(note_matcher, 'loose_matched_pairs', [])
                if loose_matched_pairs:
                    total_matched_pairs += len(loose_matched_pairs)

            # 分子：所有已配对按键数 * 2（因为每个配对包含录制和播放各一个按键）
            matched_keys_count = total_matched_pairs * 2

            # 分母：所有有效数据的按键总和
            total_effective_keys = total_valid_record + total_valid_replay

            # 计算准确率
            accuracy = (matched_keys_count / max(total_effective_keys, 1)) * 100 if total_effective_keys > 0 else 0

            # 调试信息
            print(f"[DEBUG] 准确率计算: 配对按键数={matched_keys_count}, 总有效按键={total_effective_keys}, 准确率={accuracy:.2f}%")
            print(f"[DEBUG] 多锤数={multi_hammer_count}, 丢锤数={drop_hammer_count}")
            
            return {
                'total_notes': total_notes,
                'valid_notes': total_matched_pairs,  # 所有已配对的音符对数量
                'invalid_notes': total_invalid_notes,  # 直接返回数字
                'multi_hammers': multi_hammer_count,
                'drop_hammers': drop_hammer_count,
                'silent_hammers': silent_hammer_count,
                'accuracy': accuracy,
                'total_errors': total_errors,
                'data_source': {
                    'total_valid_record': total_valid_record,
                    'total_valid_replay': total_valid_replay
                },
                'error_analysis': {
                    'drop_hammers': drop_hammer_count,
                    'multi_hammers': multi_hammer_count,
                    'silent_hammers': silent_hammer_count,
                    'total_errors': total_errors
                },
                'matching_analysis': {
                    'matched_pairs': matched_pairs_count,
                    'match_rate': (matched_pairs_count / max(total_valid_record, 1)) * 100
                },
                'invalid_notes_detail': {  # 保留详细信息的字段名
                    'invalid_record': invalid_record_count,
                    'invalid_replay': invalid_replay_count,
                    'total_invalid': invalid_record_count + invalid_replay_count
                }
            }
            
        except Exception as e:
            logger.error(f"获取摘要信息失败: {e}")
            return {
                'total_notes': 0,
                'valid_notes': 0,
                'invalid_notes': 0,
                'multi_hammers': 0,
                'drop_hammers': 0,
                'silent_hammers': 0,
                'accuracy': 0,
                'total_errors': 0,
                'data_source': {
                    'total_valid_record': 0,
                    'total_valid_replay': 0
                },
                'error_analysis': {
                    'drop_hammers': 0,
                    'multi_hammers': 0,
                    'silent_hammers': 0,
                    'total_errors': 0
                },
                'matching_analysis': {
                    'matched_pairs': 0,
                    'match_rate': 0.0
                },
                'invalid_notes_detail': {
                    'invalid_record': 0,
                    'invalid_replay': 0,
                    'total_invalid': 0
                },
                'error': f'获取摘要信息失败: {str(e)}'
            }
    
    def get_invalid_notes_table_data(self) -> List[Dict[str, Any]]:
        """
        获取无效音符表格数据 - 转换为DataTable格式
        
        Returns:
            List[Dict[str, Any]]: 适合DataTable显示的表格数据
        """
        try:
            if not self.invalid_notes_table_data:
                # 返回默认的空数据
                return [
                    {
                        'data_type': '录制数据',
                        'total_notes': 0,
                        'valid_notes': 0,
                        'invalid_notes': 0,
                        'duration_too_short': 0,
                        'empty_data': 0,
                        'silent_notes': 0,
                        'other_errors': 0
                    },
                    {
                        'data_type': '回放数据',
                        'total_notes': 0,
                        'valid_notes': 0,
                        'invalid_notes': 0,
                        'duration_too_short': 0,
                        'empty_data': 0,
                        'silent_notes': 0,
                        'other_errors': 0
                    }
                ]
            
            # 转换为DataTable格式
            table_data = []
            
            # 处理录制数据
            record_data = self.invalid_notes_table_data.get('record_data', {})
            invalid_reasons = record_data.get('invalid_reasons', {})
            table_data.append({
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
            replay_data = self.invalid_notes_table_data.get('replay_data', {})
            replay_invalid_reasons = replay_data.get('invalid_reasons', {})
            table_data.append({
                'data_type': '回放数据',
                'total_notes': replay_data.get('total_notes', 0),
                'valid_notes': replay_data.get('valid_notes', 0),
                'invalid_notes': replay_data.get('invalid_notes', 0),
                'duration_too_short': replay_invalid_reasons.get('duration_too_short', 0),
                'empty_data': replay_invalid_reasons.get('empty_data', 0),
                'silent_notes': replay_invalid_reasons.get('silent_notes', 0),
                'other_errors': replay_invalid_reasons.get('other_errors', 0)
            })
            
            return table_data
            
        except Exception as e:
            logger.error(f"获取无效音符表格数据失败: {e}")
            return [
                {
                    'data_type': '录制数据',
                    'total_notes': 0,
                    'valid_notes': 0,
                    'invalid_notes': 0,
                    'duration_too_short': 0,
                    'empty_data': 0,
                    'silent_notes': 0,
                    'other_errors': 0
                },
                {
                    'data_type': '回放数据',
                    'total_notes': 0,
                    'valid_notes': 0,
                    'invalid_notes': 0,
                    'duration_too_short': 0,
                    'empty_data': 0,
                    'silent_notes': 0,
                    'other_errors': 0
                }
            ]
    
