#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
延时关系分析模块
负责分析延时与按键、延时与锤速之间的关系
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Any, Optional
from collections import defaultdict
from scipy import stats
from scipy.stats import f_oneway, kruskal
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
    
    def analyze_delay_by_key(self) -> Dict[str, Any]:
        """
        分析延时与按键的关系
        包括：描述性统计、ANOVA检验、事后检验、异常按键识别
        
        Returns:
            Dict[str, Any]: 分析结果，包含：
                - descriptive_stats: 每个按键的描述性统计
                - anova_result: ANOVA检验结果
                - posthoc_result: 事后检验结果
                - anomaly_keys: 异常按键列表
                - overall_stats: 整体统计信息
        """
        try:
            if not self.analyzer or not self.analyzer.note_matcher:
                logger.warning("⚠️ 分析器或匹配器不存在，无法进行延时与按键分析")
                return self._create_empty_result("分析器不存在")
            
            # 获取偏移对齐数据
            offset_data = self.analyzer.note_matcher.get_offset_alignment_data()
            
            if not offset_data:
                logger.warning("⚠️ 没有偏移数据，无法进行分析")
                return self._create_empty_result("没有偏移数据")
            
            # 按按键ID分组延时数据（使用带符号的keyon_offset，保留正负值）
            key_groups = defaultdict(list)
            for item in offset_data:
                key_id = item.get('key_id', 'N/A')
                keyon_offset = item.get('keyon_offset', 0)  # 使用带符号的keyon_offset（正数=延迟，负数=提前）
                key_groups[key_id].append(keyon_offset)
            
            # 1. 描述性统计
            descriptive_stats = self._calculate_descriptive_stats(key_groups)
            
            # 2. 整体统计
            overall_stats = self._calculate_overall_stats(key_groups)
            
            # 3. ANOVA检验
            anova_result = self._perform_anova_test(key_groups)
            
            # 4. 事后检验（如果ANOVA显著）
            posthoc_result = None
            if anova_result.get('significant', False):
                posthoc_result = self._perform_posthoc_test(key_groups)
            
            # 5. 识别异常按键
            anomaly_keys = self._identify_anomaly_keys(key_groups, overall_stats)
            
            # 6. 差异模式分析
            difference_pattern = self._analyze_difference_pattern(descriptive_stats, overall_stats)
            
            # 将原始数据转换为ms单位，用于箱线图
            key_groups_ms = {}
            for key_id, offsets in key_groups.items():
                key_groups_ms[key_id] = [x / 10.0 for x in offsets]  # 转换为ms
            
            return {
                'descriptive_stats': descriptive_stats,
                'overall_stats': overall_stats,
                'anova_result': anova_result,
                'posthoc_result': posthoc_result,
                'anomaly_keys': anomaly_keys,
                'difference_pattern': difference_pattern,
                'key_groups_ms': key_groups_ms,  # 添加原始数据用于箱线图
                'status': 'success'
            }
            
        except Exception as e:
            logger.error(f"❌ 延时与按键分析失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._create_empty_result(f"分析失败: {str(e)}")
    
    def analyze_delay_by_velocity(self) -> Dict[str, Any]:
        """
        分析延时与锤速的关系
        包括：相关性分析、回归分析、分组分析
        
        Returns:
            Dict[str, Any]: 分析结果，包含：
                - correlation_result: 相关性分析结果
                - regression_result: 回归分析结果
                - grouped_analysis: 分组分析结果
                - scatter_data: 散点图数据
        """
        try:
            if not self.analyzer or not self.analyzer.note_matcher:
                logger.warning("⚠️ 分析器或匹配器不存在，无法进行延时与锤速分析")
                return self._create_empty_result("分析器不存在")
            
            matched_pairs = self.analyzer.note_matcher.get_matched_pairs()
            offset_data = self.analyzer.note_matcher.get_offset_alignment_data()
            
            if not matched_pairs or not offset_data:
                logger.warning("⚠️ 没有匹配数据，无法进行分析")
                return self._create_empty_result("没有匹配数据")
            
            # 提取锤速和延时数据
            velocities = []
            delays = []
            key_ids = []
            
            # 创建匹配对索引到偏移数据的映射
            offset_map = {}
            for item in offset_data:
                record_idx = item.get('record_index')
                replay_idx = item.get('replay_index')
                if record_idx is not None and replay_idx is not None:
                    offset_map[(record_idx, replay_idx)] = item
            
            # 提取数据
            for record_idx, replay_idx, record_note, replay_note in matched_pairs:
                # 获取第一个锤速值（用于阈值检查的锤速）
                if len(replay_note.hammers) > 0:
                    min_timestamp = replay_note.hammers.index.min()
                    first_hammer_velocity_raw = replay_note.hammers.loc[min_timestamp]
                    if isinstance(first_hammer_velocity_raw, pd.Series):
                        first_hammer_velocity = first_hammer_velocity_raw.iloc[0]
                    else:
                        first_hammer_velocity = first_hammer_velocity_raw
                    
                    # 获取延时
                    keyon_offset = None
                    if (record_idx, replay_idx) in offset_map:
                        keyon_offset = offset_map[(record_idx, replay_idx)].get('keyon_offset', 0)
                    else:
                        # 备用方案：直接计算
                        try:
                            record_keyon, _ = self.analyzer.note_matcher._calculate_note_times(record_note)
                            replay_keyon, _ = self.analyzer.note_matcher._calculate_note_times(replay_note)
                            keyon_offset = replay_keyon - record_keyon
                        except:
                            continue
                    
                    if first_hammer_velocity > 0 and keyon_offset is not None:
                        velocities.append(first_hammer_velocity)
                        delays.append(abs(keyon_offset) / 10.0)  # 转换为ms
                        key_ids.append(record_note.id)
            
            if not velocities or not delays:
                logger.warning("⚠️ 没有有效的锤速和延时数据")
                return self._create_empty_result("没有有效数据")
            
            # 1. 相关性分析
            correlation_result = self._calculate_correlation(velocities, delays)
            
            # 2. 回归分析
            regression_result = self._perform_regression_analysis(velocities, delays)
            
            # 3. 分组分析（按锤速区间分组）
            grouped_analysis = self._analyze_by_velocity_groups(velocities, delays)
            
            # 4. 散点图数据
            scatter_data = {
                'velocities': velocities,
                'delays': delays,
                'key_ids': key_ids
            }
            
            return {
                'correlation_result': correlation_result,
                'regression_result': regression_result,
                'grouped_analysis': grouped_analysis,
                'scatter_data': scatter_data,
                'status': 'success'
            }
            
        except Exception as e:
            logger.error(f"❌ 延时与锤速分析失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._create_empty_result(f"分析失败: {str(e)}")
    
    def _calculate_descriptive_stats(self, key_groups: Dict[int, List[float]]) -> List[Dict[str, Any]]:
        """计算每个按键的描述性统计"""
        stats_list = []
        
        for key_id in sorted(key_groups.keys()):
            offsets = key_groups[key_id]
            if not offsets:
                continue
            
            offsets_ms = [x / 10.0 for x in offsets]  # 转换为ms
            
            stats_list.append({
                'key_id': key_id,
                'count': len(offsets),
                'mean': np.mean(offsets_ms),
                'median': np.median(offsets_ms),
                'std': np.std(offsets_ms),
                'variance': np.var(offsets_ms),
                'min': np.min(offsets_ms),
                'max': np.max(offsets_ms),
                'q25': np.percentile(offsets_ms, 25),
                'q75': np.percentile(offsets_ms, 75)
            })
        
        return stats_list
    
    def _calculate_overall_stats(self, key_groups: Dict[int, List[float]]) -> Dict[str, Any]:
        """计算整体统计信息"""
        all_offsets = []
        for offsets in key_groups.values():
            all_offsets.extend(offsets)
        
        if not all_offsets:
            return {
                'overall_mean': 0.0,
                'overall_std': 0.0,
                'overall_variance': 0.0,
                'total_count': 0,
                'key_range': (0, 0)
            }
        
        all_offsets_ms = [x / 10.0 for x in all_offsets]
        
        key_ids = sorted(key_groups.keys())
        
        # 计算按键间平均延时的极差
        key_means = []
        for key_id in key_ids:
            offsets = key_groups[key_id]
            if offsets:
                key_means.append(np.mean([x / 10.0 for x in offsets]))
        
        return {
            'overall_mean': np.mean(all_offsets_ms),
            'overall_std': np.std(all_offsets_ms),
            'overall_variance': np.var(all_offsets_ms),
            'total_count': len(all_offsets),
            'key_count': len(key_groups),
            'key_range': (min(key_ids) if key_ids else 0, max(key_ids) if key_ids else 0),
            'key_mean_range': (min(key_means) if key_means else 0.0, max(key_means) if key_means else 0.0),
            'key_mean_range_diff': (max(key_means) - min(key_means)) if key_means else 0.0
        }
    
    def _perform_anova_test(self, key_groups: Dict[int, List[float]]) -> Dict[str, Any]:
        """执行ANOVA检验"""
        try:
            # 准备数据：每个按键的延时列表
            groups = []
            group_labels = []
            
            for key_id in sorted(key_groups.keys()):
                offsets = key_groups[key_id]
                if len(offsets) >= 2:  # 至少需要2个样本
                    groups.append(offsets)
                    group_labels.append(key_id)
            
            if len(groups) < 2:
                return {
                    'significant': False,
                    'f_statistic': None,
                    'p_value': None,
                    'message': '数据不足，无法进行ANOVA检验（至少需要2个按键，每个按键至少2个样本）'
                }
            
            # 执行ANOVA
            f_statistic, p_value = f_oneway(*groups)
            
            # 检查方差齐性（Levene's test）
            try:
                levene_stat, levene_p = stats.levene(*groups)
                variance_homogeneous = levene_p > 0.05
            except:
                variance_homogeneous = None
                levene_stat = None
                levene_p = None
            
            significant = p_value < 0.05
            
            return {
                'significant': significant,
                'f_statistic': float(f_statistic),
                'p_value': float(p_value),
                'variance_homogeneous': variance_homogeneous,
                'levene_statistic': float(levene_stat) if levene_stat is not None else None,
                'levene_p_value': float(levene_p) if levene_p is not None else None,
                'group_count': len(groups),
                'message': f"ANOVA检验: F={f_statistic:.4f}, p={p_value:.4f}, {'存在显著差异' if significant else '不存在显著差异'}"
            }
            
        except Exception as e:
            logger.error(f"ANOVA检验失败: {e}")
            return {
                'significant': False,
                'f_statistic': None,
                'p_value': None,
                'message': f'ANOVA检验失败: {str(e)}'
            }
    
    def _perform_posthoc_test(self, key_groups: Dict[int, List[float]]) -> Dict[str, Any]:
        """执行事后检验（Tukey HSD）"""
        try:
            # 准备数据：将所有延时值和对应的按键ID展平
            data = []
            groups = []
            
            for key_id in sorted(key_groups.keys()):
                offsets = key_groups[key_id]
                if len(offsets) >= 2:  # 至少需要2个样本
                    data.extend(offsets)
                    groups.extend([str(key_id)] * len(offsets))
            
            if len(set(groups)) < 2:
                return {
                    'significant_pairs': [],
                    'message': '数据不足，无法进行事后检验'
                }
            
            # 执行Tukey HSD检验
            tukey_result = pairwise_tukeyhsd(data, groups, alpha=0.05)
            
            # 提取显著差异的按键对
            significant_pairs = []
            
            # tukey_result 是一个 MultipleComparison 对象，包含 _results_table 属性
            # 从结果表中提取显著差异对
            if hasattr(tukey_result, '_results_table'):
                results_table = tukey_result._results_table.data
                # results_table 格式: [group1, group2, meandiff, lower, upper, reject, p-adj]
                for row in results_table[1:]:  # 跳过表头
                    if len(row) >= 7:
                        group1 = row[0]
                        group2 = row[1]
                        meandiff = row[2]
                        p_adj = row[6]
                        reject = row[5]  # True表示显著差异
                        
                        if reject:  # 或者使用 p_adj < 0.05
                            significant_pairs.append({
                                'key1': int(group1),
                                'key2': int(group2),
                                'p_value': float(p_adj),
                                'meandiff': float(meandiff)
                            })
            
            return {
                'significant_pairs': significant_pairs,
                'total_pairs': len(significant_pairs),
                'message': f'事后检验完成，发现{len(significant_pairs)}对按键存在显著差异'
            }
            
        except Exception as e:
            logger.error(f"事后检验失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'significant_pairs': [],
                'message': f'事后检验失败: {str(e)}'
            }
    
    def _identify_anomaly_keys(self, key_groups: Dict[int, List[float]], 
                               overall_stats: Dict[str, Any]) -> List[Dict[str, Any]]:
        """识别异常按键"""
        anomaly_keys = []
        overall_mean = overall_stats.get('overall_mean', 0.0)
        overall_std = overall_stats.get('overall_std', 0.0)
        
        threshold = 2.0  # 2倍标准差阈值
        
        for key_id in sorted(key_groups.keys()):
            offsets = key_groups[key_id]
            if not offsets:
                continue
            
            offsets_ms = [x / 10.0 for x in offsets]
            key_mean = np.mean(offsets_ms)
            key_std = np.std(offsets_ms)
            
            # 判断是否异常
            is_anomaly = False
            anomaly_type = None
            
            if abs(key_mean - overall_mean) > threshold * overall_std:
                is_anomaly = True
                if key_mean > overall_mean:
                    anomaly_type = '延时偏高'
                else:
                    anomaly_type = '延时偏低'
            
            if is_anomaly:
                anomaly_keys.append({
                    'key_id': key_id,
                    'mean_delay': key_mean,
                    'std_delay': key_std,
                    'count': len(offsets),
                    'anomaly_type': anomaly_type,
                    'deviation': key_mean - overall_mean,
                    'deviation_std': (key_mean - overall_mean) / overall_std if overall_std > 0 else 0
                })
        
        # 按偏差大小排序
        anomaly_keys.sort(key=lambda x: abs(x['deviation']), reverse=True)
        
        return anomaly_keys
    
    def _analyze_difference_pattern(self, descriptive_stats: List[Dict[str, Any]], 
                                   overall_stats: Dict[str, Any]) -> Dict[str, Any]:
        """分析差异模式"""
        if not descriptive_stats:
            return {
                'has_pattern': False,
                'pattern_type': None,
                'message': '无数据'
            }
        
        key_ids = [s['key_id'] for s in descriptive_stats]
        key_means = [s['mean'] for s in descriptive_stats]
        
        # 检查是否存在线性趋势
        if len(key_ids) >= 3:
            # 线性回归
            slope, intercept, r_value, p_value, std_err = stats.linregress(key_ids, key_means)
            
            # 判断是否存在规律
            has_linear_trend = abs(r_value) > 0.3 and p_value < 0.05
            
            # 按音域分组分析（假设按键ID范围大致对应音域）
            if key_ids:
                low_keys = [k for k in key_ids if k < 60]  # 低音区
                mid_keys = [k for k in key_ids if 60 <= k < 80]  # 中音区
                high_keys = [k for k in key_ids if k >= 80]  # 高音区
                
                low_means = [s['mean'] for s in descriptive_stats if s['key_id'] in low_keys]
                mid_means = [s['mean'] for s in descriptive_stats if s['key_id'] in mid_keys]
                high_means = [s['mean'] for s in descriptive_stats if s['key_id'] in high_keys]
                
                region_stats = {
                    'low': {
                        'count': len(low_keys),
                        'mean': np.mean(low_means) if low_means else 0.0
                    },
                    'mid': {
                        'count': len(mid_keys),
                        'mean': np.mean(mid_means) if mid_means else 0.0
                    },
                    'high': {
                        'count': len(high_keys),
                        'mean': np.mean(high_means) if high_means else 0.0
                    }
                }
            else:
                region_stats = {}
            
            return {
                'has_pattern': has_linear_trend,
                'pattern_type': 'linear_trend' if has_linear_trend else 'no_trend',
                'linear_slope': slope,
                'linear_r_squared': r_value ** 2,
                'linear_p_value': p_value,
                'region_stats': region_stats,
                'message': f'线性趋势分析: R²={r_value**2:.4f}, p={p_value:.4f}'
            }
        else:
            return {
                'has_pattern': False,
                'pattern_type': None,
                'message': '数据不足，无法分析模式'
            }
    
    def _calculate_correlation(self, velocities: List[float], delays: List[float]) -> Dict[str, Any]:
        """计算相关性"""
        try:
            # 皮尔逊相关系数（线性相关）
            pearson_r, pearson_p = stats.pearsonr(velocities, delays)
            
            # 斯皮尔曼秩相关系数（非线性相关）
            spearman_r, spearman_p = stats.spearmanr(velocities, delays)
            
            # 判断相关强度
            def interpret_correlation(r):
                abs_r = abs(r)
                if abs_r >= 0.7:
                    return '强相关'
                elif abs_r >= 0.3:
                    return '中等相关'
                else:
                    return '弱相关'
            
            return {
                'pearson_r': float(pearson_r),
                'pearson_p': float(pearson_p),
                'spearman_r': float(spearman_r),
                'spearman_p': float(spearman_p),
                'pearson_strength': interpret_correlation(pearson_r),
                'spearman_strength': interpret_correlation(spearman_r),
                'pearson_significant': pearson_p < 0.05,
                'spearman_significant': spearman_p < 0.05,
                'message': f'皮尔逊相关: r={pearson_r:.4f}, p={pearson_p:.4f}; 斯皮尔曼相关: r={spearman_r:.4f}, p={spearman_p:.4f}'
            }
            
        except Exception as e:
            logger.error(f"相关性计算失败: {e}")
            return {
                'pearson_r': None,
                'pearson_p': None,
                'spearman_r': None,
                'spearman_p': None,
                'message': f'相关性计算失败: {str(e)}'
            }
    
    def _perform_regression_analysis(self, velocities: List[float], delays: List[float]) -> Dict[str, Any]:
        """执行回归分析"""
        try:
            # 线性回归
            slope, intercept, r_value, p_value, std_err = stats.linregress(velocities, delays)
            
            # 尝试多项式回归（2次）
            try:
                poly_coeffs = np.polyfit(velocities, delays, 2)
                poly_func = np.poly1d(poly_coeffs)
                poly_r_squared = 1 - (np.sum((delays - poly_func(velocities))**2) / 
                                     np.sum((delays - np.mean(delays))**2))
            except:
                poly_coeffs = None
                poly_r_squared = None
            
            return {
                'linear': {
                    'slope': float(slope),
                    'intercept': float(intercept),
                    'r_squared': float(r_value ** 2),
                    'p_value': float(p_value),
                    'std_err': float(std_err)
                },
                'polynomial': {
                    'coefficients': [float(c) for c in poly_coeffs] if poly_coeffs is not None else None,
                    'r_squared': float(poly_r_squared) if poly_r_squared is not None else None
                },
                'best_fit': 'linear' if poly_r_squared is None or (r_value ** 2) >= poly_r_squared else 'polynomial',
                'message': f'线性回归: R²={r_value**2:.4f}, p={p_value:.4f}'
            }
            
        except Exception as e:
            logger.error(f"回归分析失败: {e}")
            return {
                'linear': None,
                'polynomial': None,
                'message': f'回归分析失败: {str(e)}'
            }
    
    def _analyze_by_velocity_groups(self, velocities: List[float], delays: List[float]) -> Dict[str, Any]:
        """按锤速区间分组分析"""
        try:
            # 定义锤速区间
            velocity_ranges = [
                (0, 100, '低锤速 (0-100)'),
                (100, 200, '中锤速 (100-200)'),
                (200, 300, '高锤速 (200-300)'),
                (300, float('inf'), '超高锤速 (>300)')
            ]
            
            group_stats = []
            
            for v_min, v_max, label in velocity_ranges:
                group_velocities = []
                group_delays = []
                
                for v, d in zip(velocities, delays):
                    if v_min <= v < v_max:
                        group_velocities.append(v)
                        group_delays.append(d)
                
                if group_delays:
                    group_stats.append({
                        'range_label': label,
                        'velocity_min': v_min,
                        'velocity_max': v_max,
                        'count': len(group_delays),
                        'mean_delay': np.mean(group_delays),
                        'std_delay': np.std(group_delays),
                        'mean_velocity': np.mean(group_velocities),
                        'std_velocity': np.std(group_velocities)
                    })
            
            return {
                'groups': group_stats,
                'message': f'按锤速区间分组，共{len(group_stats)}个区间'
            }
            
        except Exception as e:
            logger.error(f"分组分析失败: {e}")
            return {
                'groups': [],
                'message': f'分组分析失败: {str(e)}'
            }
    
    def analyze_force_delay_by_key(self) -> Dict[str, Any]:
        """
        分析每个按键的力度与延时关系
        
        按按键ID分组，对每个按键分析其内部的力度（锤速）与延时的统计关系。
        包括：相关性分析、回归分析、描述性统计等。
        
        Returns:
            Dict[str, Any]: 分析结果，包含：
                - key_analysis: 每个按键的分析结果列表
                - overall_summary: 整体摘要统计
                - scatter_data: 散点图数据（按按键分组）
                - status: 状态标识
        """
        try:
            if not self.analyzer or not self.analyzer.note_matcher:
                logger.warning("⚠️ 分析器或匹配器不存在，无法进行按键力度-延时分析")
                return self._create_empty_force_delay_result("分析器不存在")
            
            matched_pairs = self.analyzer.note_matcher.get_matched_pairs()
            offset_data = self.analyzer.note_matcher.get_offset_alignment_data()
            
            if not matched_pairs or not offset_data:
                logger.warning("⚠️ 没有匹配数据，无法进行分析")
                return self._create_empty_force_delay_result("没有匹配数据")
            
            # 提取数据：按键ID、锤速、延时
            key_force_delay_data = self._extract_key_force_delay_data(matched_pairs, offset_data)
            
            if not key_force_delay_data:
                logger.warning("⚠️ 没有有效的按键-力度-延时数据")
                return self._create_empty_force_delay_result("没有有效数据")
            
            # 计算所有数据的平均延时（用于计算相对延时）
            all_delays = [delay for _, _, delay in key_force_delay_data]
            mean_delay = np.mean(all_delays) if all_delays else 0
            
            # 按按键ID分组，同时存储原始延时和相对延时
            key_groups = defaultdict(lambda: {'forces': [], 'absolute_delays': [], 'relative_delays': []})
            for key_id, force, delay in key_force_delay_data:
                key_groups[key_id]['forces'].append(force)
                key_groups[key_id]['absolute_delays'].append(delay)  # 原始延时
                key_groups[key_id]['relative_delays'].append(delay - mean_delay)  # 相对延时
            
            # 对每个按键进行分析
            key_analysis = []
            scatter_data = {}
            
            for key_id in sorted(key_groups.keys()):
                forces = key_groups[key_id]['forces']
                absolute_delays = key_groups[key_id]['absolute_delays']
                relative_delays = key_groups[key_id]['relative_delays']
                
                if len(forces) < 2:  # 至少需要2个样本才能进行相关性分析
                    continue
                
                # 对单个按键进行力度-延时分析（使用相对延时）
                single_key_result = self._analyze_single_key_force_delay(
                    key_id, forces, relative_delays
                )
                key_analysis.append(single_key_result)
                
                # 保存散点图数据（包含原始延时和相对延时）
                scatter_data[key_id] = {
                    'forces': forces,
                    'delays': relative_delays,  # 用于显示的延时（相对延时）
                    'absolute_delays': absolute_delays,  # 原始延时（用于悬停显示）
                    'mean_delay': mean_delay  # 平均延时（用于说明）
                }
            
            if not key_analysis:
                logger.warning("⚠️ 没有足够的按键数据进行分析（每个按键至少需要2个样本）")
                return self._create_empty_force_delay_result("数据不足")
            
            # 计算整体摘要统计
            overall_summary = self._calculate_force_delay_overall_summary(key_analysis)
            
            logger.info(f"✅ 按键力度-延时分析完成，共分析 {len(key_analysis)} 个按键")
            
            return {
                'key_analysis': key_analysis,
                'overall_summary': overall_summary,
                'scatter_data': scatter_data,
                'status': 'success'
            }
            
        except Exception as e:
            logger.error(f"❌ 按键力度-延时分析失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._create_empty_force_delay_result(f"分析失败: {str(e)}")
    
    def analyze_key_force_interaction(self) -> Dict[str, Any]:
        """
        分析按键与力度的联合统计关系（多因素分析）
        
        使用多因素ANOVA和交互效应分析，评估：
        1. 按键对延时的主效应
        2. 力度对延时的主效应
        3. 按键×力度的交互效应
        
        Returns:
            Dict[str, Any]: 分析结果，包含：
                - two_way_anova: 双因素ANOVA结果
                - interaction_effect: 交互效应分析结果
                - stratified_regression: 分层回归分析结果
                - interaction_plot_data: 交互效应图数据
                - status: 状态标识
        """
        try:
            if not self.analyzer or not self.analyzer.note_matcher:
                logger.warning("⚠️ 分析器或匹配器不存在，无法进行按键-力度交互分析")
                return self._create_empty_interaction_result("分析器不存在")
            
            matched_pairs = self.analyzer.note_matcher.get_matched_pairs()
            offset_data = self.analyzer.note_matcher.get_offset_alignment_data()
            
            if not matched_pairs or not offset_data:
                logger.warning("⚠️ 没有匹配数据，无法进行分析")
                return self._create_empty_interaction_result("没有匹配数据")
            
            # 提取数据：按键ID、锤速、延时
            key_force_delay_data = self._extract_key_force_delay_data(matched_pairs, offset_data)
            
            if not key_force_delay_data:
                logger.warning("⚠️ 没有有效的按键-力度-延时数据")
                return self._create_empty_interaction_result("没有有效数据")
            
            # 准备多因素ANOVA数据
            key_ids_list = [item[0] for item in key_force_delay_data]
            forces_list = [item[1] for item in key_force_delay_data]
            delays_list = [item[2] for item in key_force_delay_data]
            
            # 1. 双因素ANOVA（按键 × 力度）
            two_way_anova = self._perform_two_way_anova(key_ids_list, forces_list, delays_list)
            
            # 2. 交互效应分析
            interaction_effect = self._analyze_interaction_effect(key_ids_list, forces_list, delays_list)
            
            # 3. 分层回归分析
            stratified_regression = self._perform_stratified_regression(key_ids_list, forces_list, delays_list)
            
            # 4. 生成交互效应图数据
            interaction_plot_data = self._generate_interaction_plot_data(key_ids_list, forces_list, delays_list)
            
            logger.info("✅ 按键-力度交互分析完成")
            
            return {
                'two_way_anova': two_way_anova,
                'interaction_effect': interaction_effect,
                'stratified_regression': stratified_regression,
                'interaction_plot_data': interaction_plot_data,
                'status': 'success'
            }
            
        except Exception as e:
            logger.error(f"❌ 按键-力度交互分析失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._create_empty_interaction_result(f"分析失败: {str(e)}")
    
    def _extract_key_force_delay_data(self, matched_pairs: List[Tuple], 
                                      offset_data: List[Dict[str, Any]]) -> List[Tuple[int, float, float]]:
        """
        从匹配对和偏移数据中提取按键ID、力度（锤速）、延时数据
        
        Args:
            matched_pairs: 匹配对列表
            offset_data: 偏移对齐数据列表
            
        Returns:
            List[Tuple[int, float, float]]: [(key_id, force, delay), ...]
                - key_id: 按键ID
                - force: 力度（锤速值，单位：原始单位）
                - delay: 延时（单位：ms，带符号）
        """
        # 创建匹配对索引到偏移数据的映射
        offset_map = {}
        for item in offset_data:
            record_idx = item.get('record_index')
            replay_idx = item.get('replay_index')
            if record_idx is not None and replay_idx is not None:
                offset_map[(record_idx, replay_idx)] = item
        
        result = []
        
        for record_idx, replay_idx, record_note, replay_note in matched_pairs:
            # 获取按键ID
            key_id = record_note.id
            
            # 获取播放音符的锤速（第一个锤速值）
            force = None
            if len(replay_note.hammers) > 0:
                min_timestamp = replay_note.hammers.index.min()
                first_hammer_velocity_raw = replay_note.hammers.loc[min_timestamp]
                if isinstance(first_hammer_velocity_raw, pd.Series):
                    force = first_hammer_velocity_raw.iloc[0]
                else:
                    force = first_hammer_velocity_raw
            
            if force is None or force <= 0:
                continue  # 跳过无效的力度数据
            
            # 获取延时
            keyon_offset = None
            if (record_idx, replay_idx) in offset_map:
                keyon_offset = offset_map[(record_idx, replay_idx)].get('keyon_offset', 0)
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
                result.append((key_id, float(force), delay_ms))
        
        return result
    
    def _analyze_single_key_force_delay(self, key_id: int, forces: List[float], 
                                       delays: List[float]) -> Dict[str, Any]:
        """
        分析单个按键的力度与延时关系
        
        Args:
            key_id: 按键ID
            forces: 力度值列表
            delays: 延时值列表（ms，带符号）
            
        Returns:
            Dict[str, Any]: 单个按键的分析结果，包含：
                - key_id: 按键ID
                - correlation: 相关性分析结果
                - regression: 回归分析结果
                - descriptive_stats: 描述性统计
                - sample_count: 样本数量
        """
        # 1. 相关性分析
        correlation = self._calculate_correlation(forces, delays)
        
        # 2. 回归分析
        regression = self._perform_regression_analysis(forces, delays)
        
        # 3. 描述性统计
        descriptive_stats = {
            'force': {
                'mean': float(np.mean(forces)),
                'std': float(np.std(forces)),
                'min': float(np.min(forces)),
                'max': float(np.max(forces)),
                'median': float(np.median(forces))
            },
            'delay': {
                'mean': float(np.mean(delays)),
                'std': float(np.std(delays)),
                'min': float(np.min(delays)),
                'max': float(np.max(delays)),
                'median': float(np.median(delays))
            }
        }
        
        return {
            'key_id': key_id,
            'correlation': correlation,
            'regression': regression,
            'descriptive_stats': descriptive_stats,
            'sample_count': len(forces)
        }
    
    def _calculate_force_delay_overall_summary(self, key_analysis: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        计算按键力度-延时分析的整体摘要统计
        
        Args:
            key_analysis: 每个按键的分析结果列表
            
        Returns:
            Dict[str, Any]: 整体摘要统计
        """
        if not key_analysis:
            return {}
        
        # 统计显著相关的按键数量
        significant_correlation_count = 0
        positive_correlation_count = 0
        negative_correlation_count = 0
        
        # 统计平均相关系数
        pearson_rs = []
        spearman_rs = []
        
        for analysis in key_analysis:
            corr = analysis.get('correlation', {})
            if corr.get('pearson_significant', False):
                significant_correlation_count += 1
                pearson_r = corr.get('pearson_r', 0)
                if pearson_r > 0:
                    positive_correlation_count += 1
                elif pearson_r < 0:
                    negative_correlation_count += 1
                pearson_rs.append(pearson_r)
            
            if corr.get('spearman_r') is not None:
                spearman_rs.append(corr.get('spearman_r', 0))
        
        return {
            'total_keys_analyzed': len(key_analysis),
            'significant_correlation_count': significant_correlation_count,
            'positive_correlation_count': positive_correlation_count,
            'negative_correlation_count': negative_correlation_count,
            'mean_pearson_r': float(np.mean(pearson_rs)) if pearson_rs else None,
            'mean_spearman_r': float(np.mean(spearman_rs)) if spearman_rs else None,
            'correlation_rate': significant_correlation_count / len(key_analysis) if key_analysis else 0.0
        }
    
    def _perform_two_way_anova(self, key_ids: List[int], forces: List[float], 
                               delays: List[float]) -> Dict[str, Any]:
        """
        执行双因素ANOVA（按键 × 力度）
        
        使用线性模型评估：
        1. 按键对延时的主效应
        2. 力度对延时的主效应
        3. 按键×力度的交互效应
        
        Args:
            key_ids: 按键ID列表
            forces: 力度值列表
            delays: 延时值列表
            
        Returns:
            Dict[str, Any]: 双因素ANOVA结果
        """
        try:
            from statsmodels.formula.api import ols
            from statsmodels.stats.anova import anova_lm
            import pandas as pd
            
            # 准备DataFrame
            df = pd.DataFrame({
                'key_id': key_ids,
                'force': forces,
                'delay': delays
            })
            
            # 将按键ID转换为分类变量（字符串类型，便于模型识别）
            df['key_id'] = df['key_id'].astype(str)
            
            # 构建线性模型：delay ~ key_id + force + key_id:force
            # key_id:force 表示交互项
            model = ols('delay ~ C(key_id) + force + C(key_id):force', data=df).fit()
            
            # 执行ANOVA
            anova_table = anova_lm(model, typ=2)
            
            # 提取结果
            key_effect = anova_table.loc['C(key_id)', :] if 'C(key_id)' in anova_table.index else None
            force_effect = anova_table.loc['force', :] if 'force' in anova_table.index else None
            interaction_effect = anova_table.loc['C(key_id):force', :] if 'C(key_id):force' in anova_table.index else None
            
            result = {
                'key_main_effect': {
                    'f_statistic': float(key_effect['F']) if key_effect is not None else None,
                    'p_value': float(key_effect['PR(>F)']) if key_effect is not None else None,
                    'significant': float(key_effect['PR(>F)']) < 0.05 if key_effect is not None else False
                } if key_effect is not None else None,
                'force_main_effect': {
                    'f_statistic': float(force_effect['F']) if force_effect is not None else None,
                    'p_value': float(force_effect['PR(>F)']) if force_effect is not None else None,
                    'significant': float(force_effect['PR(>F)']) < 0.05 if force_effect is not None else False
                } if force_effect is not None else None,
                'interaction_effect': {
                    'f_statistic': float(interaction_effect['F']) if interaction_effect is not None else None,
                    'p_value': float(interaction_effect['PR(>F)']) if interaction_effect is not None else None,
                    'significant': float(interaction_effect['PR(>F)']) < 0.05 if interaction_effect is not None else False
                } if interaction_effect is not None else None,
                'model_r_squared': float(model.rsquared),
                'model_adj_r_squared': float(model.rsquared_adj)
            }
            
            # 生成解释性消息
            messages = []
            if result['key_main_effect']:
                key_sig = result['key_main_effect']['significant']
                messages.append(f"按键主效应: {'显著' if key_sig else '不显著'} (p={result['key_main_effect']['p_value']:.4f})")
            
            if result['force_main_effect']:
                force_sig = result['force_main_effect']['significant']
                messages.append(f"力度主效应: {'显著' if force_sig else '不显著'} (p={result['force_main_effect']['p_value']:.4f})")
            
            if result['interaction_effect']:
                inter_sig = result['interaction_effect']['significant']
                messages.append(f"交互效应: {'显著' if inter_sig else '不显著'} (p={result['interaction_effect']['p_value']:.4f})")
            
            result['message'] = '; '.join(messages)
            
            return result
            
        except Exception as e:
            logger.error(f"双因素ANOVA失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'key_main_effect': None,
                'force_main_effect': None,
                'interaction_effect': None,
                'message': f'双因素ANOVA失败: {str(e)}'
            }
    
    def _analyze_interaction_effect(self, key_ids: List[int], forces: List[float], 
                                   delays: List[float]) -> Dict[str, Any]:
        """
        分析交互效应的详细模式
        
        评估不同按键下，力度对延时的影响是否不同
        
        Args:
            key_ids: 按键ID列表
            forces: 力度值列表
            delays: 延时值列表
            
        Returns:
            Dict[str, Any]: 交互效应分析结果
        """
        try:
            from collections import defaultdict
            
            # 按按键分组
            key_groups = defaultdict(lambda: {'forces': [], 'delays': []})
            for key_id, force, delay in zip(key_ids, forces, delays):
                key_groups[key_id]['forces'].append(force)
                key_groups[key_id]['delays'].append(delay)
            
            # 对每个按键计算力度-延时的斜率（回归系数）
            key_slopes = {}
            key_intercepts = {}
            key_r_squared = {}
            
            for key_id in sorted(key_groups.keys()):
                forces_key = key_groups[key_id]['forces']
                delays_key = key_groups[key_id]['delays']
                
                if len(forces_key) < 2:
                    continue
                
                # 线性回归
                slope, intercept, r_value, p_value, std_err = stats.linregress(forces_key, delays_key)
                key_slopes[key_id] = slope
                key_intercepts[key_id] = intercept
                key_r_squared[key_id] = r_value ** 2
            
            if not key_slopes:
                return {
                    'key_slopes': {},
                    'slope_variance': None,
                    'message': '数据不足，无法分析交互效应'
                }
            
            # 计算斜率的方差（用于评估交互效应强度）
            slopes_list = list(key_slopes.values())
            slope_mean = np.mean(slopes_list)
            slope_std = np.std(slopes_list)
            slope_variance = np.var(slopes_list)
            
            # 判断交互效应强度
            # 交互效应强度反映不同按键的斜率差异程度
            # 如果斜率的标准差大，说明不同按键的力度-延时关系差异大，交互效应强
            # 如果斜率的标准差小，说明不同按键的力度-延时关系相似，交互效应弱
            
            abs_slope_mean = abs(slope_mean)
            
            # 使用更严格的阈值，避免总是显示"强"
            # 方法1: 如果均值接近0，使用绝对标准差判断
            if abs_slope_mean < 1e-6:
                # 使用更严格的绝对阈值：std > 0.002 为强，> 0.001 为中等，否则为弱
                # 这些阈值基于实际数据的经验值，可能需要根据具体数据调整
                if slope_std > 0.002:
                    interaction_strength = '强'
                elif slope_std > 0.001:
                    interaction_strength = '中等'
                else:
                    interaction_strength = '弱'
            else:
                # 方法2: 使用变异系数（CV = std/mean）来判断
                # CV反映相对变异性，更稳健
                cv = slope_std / abs_slope_mean
                
                # 使用更严格的阈值，同时考虑绝对标准差
                # 如果标准差本身很小（< 0.0005），即使CV大也认为是弱交互
                if slope_std < 0.0005:
                    interaction_strength = '弱'
                elif cv > 1.0:  # CV > 1.0 为强（更严格）
                    interaction_strength = '强'
                elif cv > 0.5:  # CV > 0.5 为中等（更严格）
                    interaction_strength = '中等'
                else:
                    interaction_strength = '弱'
            
            # 记录计算详情，便于调试
            logger.info(f"📊 交互效应强度计算: slope_mean={slope_mean:.6f}, slope_std={slope_std:.6f}, "
                       f"abs_mean={abs_slope_mean:.6f}, CV={slope_std/abs_slope_mean if abs_slope_mean > 1e-6 else 'N/A'}, "
                       f"强度={interaction_strength}")
            
            return {
                'key_slopes': {k: float(v) for k, v in key_slopes.items()},
                'key_intercepts': {k: float(v) for k, v in key_intercepts.items()},
                'key_r_squared': {k: float(v) for k, v in key_r_squared.items()},
                'slope_mean': float(slope_mean),
                'slope_std': float(slope_std),
                'slope_variance': float(slope_variance),
                'interaction_strength': interaction_strength,
                'message': f'交互效应分析: 斜率均值={slope_mean:.6f}, 标准差={slope_std:.6f}, 强度={interaction_strength}'
            }
            
        except Exception as e:
            logger.error(f"交互效应分析失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'key_slopes': {},
                'message': f'交互效应分析失败: {str(e)}'
            }
    
    def _perform_stratified_regression(self, key_ids: List[int], forces: List[float], 
                                      delays: List[float]) -> Dict[str, Any]:
        """
        执行分层回归分析
        
        1. 控制按键后，分析力度对延时的影响
        2. 控制力度后，分析按键对延时的影响
        
        Args:
            key_ids: 按键ID列表
            forces: 力度值列表
            delays: 延时值列表
            
        Returns:
            Dict[str, Any]: 分层回归分析结果
        """
        try:
            from statsmodels.formula.api import ols
            import pandas as pd
            
            df = pd.DataFrame({
                'key_id': key_ids,
                'force': forces,
                'delay': delays
            })
            df['key_id'] = df['key_id'].astype(str)
            
            # 模型1：只包含按键（基准模型）
            model1 = ols('delay ~ C(key_id)', data=df).fit()
            r_squared_key_only = model1.rsquared
            
            # 模型2：按键 + 力度（完整模型）
            model2 = ols('delay ~ C(key_id) + force', data=df).fit()
            r_squared_key_force = model2.rsquared
            
            # 模型3：只包含力度（基准模型）
            model3 = ols('delay ~ force', data=df).fit()
            r_squared_force_only = model3.rsquared
            
            # 模型4：力度 + 按键（完整模型）
            model4 = ols('delay ~ force + C(key_id)', data=df).fit()
            r_squared_force_key = model4.rsquared
            
            # 计算增量R²（控制一个变量后，另一个变量的贡献）
            force_incremental_r2 = r_squared_key_force - r_squared_key_only
            key_incremental_r2 = r_squared_force_key - r_squared_force_only
            
            return {
                'force_effect_controlling_key': {
                    'r_squared_incremental': float(force_incremental_r2),
                    'r_squared_full': float(r_squared_key_force),
                    'r_squared_base': float(r_squared_key_only),
                    'force_coefficient': float(model2.params.get('force', 0)),
                    'force_p_value': float(model2.pvalues.get('force', 1.0))
                },
                'key_effect_controlling_force': {
                    'r_squared_incremental': float(key_incremental_r2),
                    'r_squared_full': float(r_squared_force_key),
                    'r_squared_base': float(r_squared_force_only),
                    'key_f_statistic': float(model4.fvalue) if hasattr(model4, 'fvalue') else None,
                    'key_p_value': float(model4.f_pvalue) if hasattr(model4, 'f_pvalue') else None
                },
                'message': f'分层回归: 控制按键后力度增量R²={force_incremental_r2:.4f}, 控制力度后按键增量R²={key_incremental_r2:.4f}'
            }
            
        except Exception as e:
            logger.error(f"分层回归分析失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'force_effect_controlling_key': None,
                'key_effect_controlling_force': None,
                'message': f'分层回归分析失败: {str(e)}'
            }
    
    def _generate_interaction_plot_data(self, key_ids: List[int], forces: List[float], 
                                       delays: List[float]) -> Dict[str, Any]:
        """
        生成交互效应图数据（使用相对延时）
        
        为每个按键生成力度-延时的回归线数据，用于绘制交互效应图
        延时数据使用相对延时（原始延时减去整体平均延时）
        
        Args:
            key_ids: 按键ID列表
            forces: 力度值列表
            delays: 延时值列表
            
        Returns:
            Dict[str, Any]: 交互效应图数据，包含每个按键的回归线数据
        """
        try:
            from collections import defaultdict
            
            # 计算整体平均延时
            mean_delay = np.mean(delays) if delays else 0
            logger.info(f"📊 整体平均延时: {mean_delay:.2f}ms")
            
            # 计算相对延时（延时 - 平均延时）
            relative_delays = [delay - mean_delay for delay in delays]
            
            # 按按键分组
            key_groups = defaultdict(lambda: {'forces': [], 'relative_delays': [], 'absolute_delays': []})
            for key_id, force, rel_delay, abs_delay in zip(key_ids, forces, relative_delays, delays):
                key_groups[key_id]['forces'].append(force)
                key_groups[key_id]['relative_delays'].append(rel_delay)
                key_groups[key_id]['absolute_delays'].append(abs_delay)
            
            interaction_data = {}
            
            for key_id in sorted(key_groups.keys()):
                forces_key = key_groups[key_id]['forces']
                relative_delays_key = key_groups[key_id]['relative_delays']  # 使用相对延时
                absolute_delays_key = key_groups[key_id]['absolute_delays']  # 保留原始延时用于参考
                
                if len(forces_key) < 2:
                    continue
                
                # 使用相对延时进行线性回归
                slope, intercept, r_value, p_value, std_err = stats.linregress(forces_key, relative_delays_key)
                
                # 生成回归线的x和y值（用于绘图）
                force_min = min(forces_key)
                force_max = max(forces_key)
                force_range = force_max - force_min
                
                # 生成10个点用于绘制回归线
                force_line = np.linspace(force_min - force_range * 0.1, 
                                        force_max + force_range * 0.1, 10)
                delay_line = slope * force_line + intercept  # 相对延时的回归线
                
                interaction_data[key_id] = {
                    'forces': forces_key,
                    'delays': relative_delays_key,  # 使用相对延时
                    'absolute_delays': absolute_delays_key,  # 保留原始延时用于参考
                    'mean_delay': float(mean_delay),  # 整体平均延时
                    'regression_line': {
                        'force': [float(f) for f in force_line],
                        'delay': [float(d) for d in delay_line]
                    },
                    'slope': float(slope),
                    'intercept': float(intercept),
                    'r_squared': float(r_value ** 2),
                    'p_value': float(p_value),
                    'sample_count': len(forces_key)
                }
            
            return {
                'key_data': interaction_data,
                'mean_delay': float(mean_delay),  # 添加整体平均延时到返回结果
                'message': f'生成 {len(interaction_data)} 个按键的交互效应图数据（使用相对延时）'
            }
            
        except Exception as e:
            logger.error(f"生成交互效应图数据失败: {e}")
            return {
                'key_data': {},
                'message': f'生成交互效应图数据失败: {str(e)}'
            }
    
    def _create_empty_force_delay_result(self, message: str) -> Dict[str, Any]:
        """创建空的按键力度-延时分析结果"""
        return {
            'status': 'error',
            'message': message,
            'key_analysis': [],
            'overall_summary': {},
            'scatter_data': {}
        }
    
    def _create_empty_interaction_result(self, message: str) -> Dict[str, Any]:
        """创建空的交互效应分析结果"""
        return {
            'status': 'error',
            'message': message,
            'two_way_anova': {},
            'interaction_effect': {},
            'stratified_regression': {},
            'interaction_plot_data': {}
        }
    
    def _create_empty_result(self, message: str) -> Dict[str, Any]:
        """创建空结果"""
        return {
            'status': 'error',
            'message': message,
            'descriptive_stats': [],
            'overall_stats': {},
            'anova_result': {},
            'posthoc_result': None,
            'anomaly_keys': [],
            'difference_pattern': {}
        }

