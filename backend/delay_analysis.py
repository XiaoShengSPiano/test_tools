"""
延时关系分析模块
负责分析延时与按键、延时与锤速之间的关系
"""

import math
import traceback
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Any, Optional
from collections import defaultdict
from scipy import stats
from scipy.stats import f_oneway
from statsmodels.stats.multicomp import pairwise_tukeyhsd
from utils.logger import Logger

logger = Logger.get_logger()


class DelayAnalysis:
    """延时关系分析器 - 分析延时与按键、延时与锤速之间的关系"""
    
    def __init__(self, analyzer=None):
        """
        初始化延时分析器
        
        Args:
            analyzer: SPMIDAnalyzer实例
        """
        self.analyzer = analyzer
    
    def analyze_key_force_interaction(self) -> Dict[str, Any]:
        """
        生成按键与力度的交互效应图数据

        生成按键-力度交互效应图所需的数据，用于可视化分析按键和力度对延时的联合影响。

        Returns:
            Dict[str, Any]: 分析结果，包含：
                - interaction_plot_data: 交互效应图数据
                - status: 状态标识
        """
        try:
            if not self.analyzer or not self.analyzer.note_matcher:
                logger.warning("分析器或匹配器不存在，无法进行按键-力度交互分析")
                return self._create_empty_interaction_result("分析器不存在")

            matched_pairs = self.analyzer.note_matcher.get_matched_pairs()
            offset_data = self.analyzer.note_matcher.get_offset_alignment_data()
            
            if not matched_pairs or not offset_data:
                logger.warning("⚠️ 没有匹配数据，无法进行分析")
                return self._create_empty_interaction_result("没有匹配数据")
            
            # 提取数据：按键ID、锤速、延时、索引
            key_force_delay_data = self._extract_key_force_delay_data(matched_pairs, offset_data)
            
            if not key_force_delay_data:
                logger.warning("⚠️ 没有有效的按键-力度-延时数据")
                return self._create_empty_interaction_result("没有有效数据")
            
            # 准备数据列表
            # item格式: (key_id, replay_velocity, delay_ms, record_idx, replay_idx)
            key_ids_list = [item[0] for item in key_force_delay_data]
            replay_velocities_list = [item[1] for item in key_force_delay_data]
            delays_list = [item[2] for item in key_force_delay_data]
            record_indices_list = [item[3] for item in key_force_delay_data]
            replay_indices_list = [item[4] for item in key_force_delay_data]
            
            # 生成交互效应图数据（包含索引信息）
            interaction_plot_data = self._generate_interaction_plot_data(
                key_ids_list, replay_velocities_list, delays_list,
                record_indices_list, replay_indices_list
            )
            
            logger.info("按键-力度交互分析完成")
            
            return {
                'interaction_plot_data': interaction_plot_data,
                'status': 'success'
            }
            
        except Exception as e:
            logger.error(f"按键-力度交互分析失败: {e}")
            logger.error(traceback.format_exc())
            return self._create_empty_interaction_result(f"分析失败: {str(e)}")
    
    def _extract_key_force_delay_data(self, matched_pairs: List[Tuple], 
                                      offset_data: List[Dict[str, Any]]) -> List[Tuple[int, float, float, int, int]]:
        """
        从匹配对和偏移数据中提取按键ID、力度（锤速）、延时数据
        
        Args:
            matched_pairs: 匹配对列表
            offset_data: 偏移对齐数据列表
            
        Returns:
            List[Tuple]: [(key_id, replay_velocity, delay_ms, record_idx, replay_idx), ...]
                - key_id: 按键ID
                - replay_velocity: 播放锤速值
                - delay_ms: 延时（单位：ms，带符号）
                - record_idx: 录制音符索引
                - replay_idx: 回放音符索引
        """
        # 创建匹配对索引到偏移数据的映射
        offset_map = {}
        for item in offset_data:
            record_idx = item.get('record_index')
            replay_idx = item.get('replay_index')
            if record_idx is not None and replay_idx is not None:
                offset_map[(record_idx, replay_idx)] = item
        
        result = []
        
        for record_note, replay_note in matched_pairs:
            # Lookup needs offsets because NoteMatcher.get_offset_alignment_data uses offsets
            lookup_record_idx = record_note.offset
            lookup_replay_idx = replay_note.offset
            
            # Result needs UUIDs as per user request
            record_uuid = record_note.uuid
            replay_uuid = replay_note.uuid

            # 获取按键ID
            key_id = record_note.id
            
            # 提取播放音符的锤速（第一个锤速值）
            replay_velocity = replay_note.first_hammer_velocity
            
            if replay_velocity is None or replay_velocity <= 0:
                continue
            
            # 获取延时
            keyon_offset = None
            if (lookup_record_idx, lookup_replay_idx) in offset_map:
                keyon_offset = offset_map[(lookup_record_idx, lookup_replay_idx)].get('keyon_offset', 0)
            else:
                # 备用方案：直接计算
                try:
                    record_keyon, _ = self.analyzer.note_matcher._calculate_note_times(record_note)
                    replay_keyon, _ = self.analyzer.note_matcher._calculate_note_times(replay_note)
                    keyon_offset = replay_keyon - record_keyon
                except:
                    continue
            
            if keyon_offset is not None:
                # 转换为ms单位（带符号）
                delay_ms = keyon_offset / 10.0
                result.append((key_id, float(replay_velocity), delay_ms, record_uuid, replay_uuid))
        
        return result
    
    def _generate_interaction_plot_data(self, key_ids: List[int], replay_velocities: List[float], 
                                       delays: List[float], record_indices: List[int] = None,
                                       replay_indices: List[int] = None) -> Dict[str, Any]:
        """
        生成按键-力度交互效应图数据（使用相对延时）

        横轴：log₁₀(播放锤速)（用于分析）
        纵轴：相对延时（延时 - 平均延时）
        
        Args:
            key_ids: 按键ID列表
            replay_velocities: 播放锤速列表
            delays: 延时列表（单位：ms）
            record_indices: 录制音符索引列表（可选）
            replay_indices: 回放音符索引列表（可选）
            
        Returns:
            Dict[str, Any]: 交互效应图数据，包含每个按键的数据
        """
        try:
            from collections import defaultdict

            # 使用预计算的整体平均延时（避免重复计算）
            if hasattr(self, 'analyzer') and self.analyzer and hasattr(self.analyzer, 'get_mean_error'):
                mean_delay_0_1ms = self.analyzer.get_mean_error()
                mean_delay = mean_delay_0_1ms / 10.0  # 转换为毫秒
            else:
                # 备用计算（如果预计算不可用）
                mean_delay = np.mean(delays) if delays else 0
            logger.info(f"📊 整体平均延时: {mean_delay:.2f}ms")
            
            # 计算相对延时（延时 - 平均延时）
            relative_delays = [delay - mean_delay for delay in delays]
            
            # 按按键分组
            key_groups = defaultdict(lambda: {'forces': [], 'delays': [], 'absolute_delays': [],
                                               'record_indices': [], 'replay_indices': []})
            for i, (key_id, replay_vel, rel_delay, abs_delay) in enumerate(zip(key_ids, replay_velocities, relative_delays, delays)):
                # 'forces'存储播放锤速
                # 'delays'存储相对延时
                # 'absolute_delays'存储原始延时
                key_groups[key_id]['forces'].append(replay_vel)
                key_groups[key_id]['delays'].append(rel_delay)
                key_groups[key_id]['absolute_delays'].append(abs_delay)
                if record_indices and i < len(record_indices):
                    key_groups[key_id]['record_indices'].append(record_indices[i])
                if replay_indices and i < len(replay_indices):
                    key_groups[key_id]['replay_indices'].append(replay_indices[i])
            
            interaction_data = {}
            
            for key_id in sorted(key_groups.keys()):
                replay_vels_key = key_groups[key_id]['forces']
                relative_delays_key = key_groups[key_id]['delays']  # 相对延时
                absolute_delays_key = key_groups[key_id]['absolute_delays']  # 原始延时
                record_indices_key = key_groups[key_id].get('record_indices', [])
                replay_indices_key = key_groups[key_id].get('replay_indices', [])
                
                if len(replay_vels_key) < 1:
                    continue
                
                # 初始化回归数据为默认值
                slope = 0.0
                intercept = 0.0
                r_value = 0.0
                p_value = 1.0 # Default to 1.0 if no regression
                
                interaction_data[key_id] = {
                    'forces': replay_vels_key,
                    'delays': relative_delays_key,  # 相对延时
                    'absolute_delays': absolute_delays_key,  # 原始延时
                    'record_indices': record_indices_key,
                    'replay_indices': replay_indices_key,
                    'mean_delay': float(mean_delay),  # 整体平均延时
                    'regression_line': {
                        'force': [],
                        'delay': [],
                        'slope': float(slope),
                        'intercept': float(intercept),
                        'r_value': float(r_value)
                    },
                    'r_squared': float(r_value ** 2), # Calculate r_squared from r_value
                    'p_value': float(p_value),
                    'sample_count': len(replay_vels_key)
                }
            
            return {
                'key_data': interaction_data,
                'mean_delay': float(mean_delay),
                'message': f'生成 {len(interaction_data)} 个按键的交互效应图数据（使用相对延时）'
            }
            
        except Exception as e:
            logger.error(f"生成交互效应图数据失败: {e}")
            return {
                'key_data': {},
                'message': f'生成交互效应图数据失败: {str(e)}'
            }
    
    def _create_empty_interaction_result(self, message: str) -> Dict[str, Any]:
        """创建空的交互效应分析结果"""
        return {
            'status': 'error',
            'message': message,
            'interaction_plot_data': {}
        }