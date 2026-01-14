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
            offset_data = self.analyzer.note_matcher.get_precision_offset_alignment_data()
            
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
        
        for record_idx, replay_idx, record_note, replay_note in matched_pairs:
            # 获取按键ID
            key_id = record_note.id
            
            # 提取播放音符的锤速（第一个锤速值）
            replay_velocity = self._extract_first_hammer_velocity(replay_note)
            
            if replay_velocity is None or replay_velocity <= 0:
                continue
            
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
                result.append((key_id, float(replay_velocity), delay_ms, record_idx, replay_idx))
        
        return result
    
    def _extract_first_hammer_velocity(self, note) -> Optional[float]:
        """
        提取音符的第一个锤速值
        
        Args:
            note: 音符对象
            
        Returns:
            Optional[float]: 第一个锤速值，如果提取失败则返回None
        """
        try:
            if not hasattr(note, 'hammers') or note.hammers is None:
                return None
            
            if hasattr(note.hammers, 'empty') and note.hammers.empty:
                return None
            
            if len(note.hammers) == 0:
                return None
            
            # 获取时间上最早的锤速值
            min_timestamp = note.hammers.index.min()
            first_velocity_raw = note.hammers.loc[min_timestamp]
            
            if isinstance(first_velocity_raw, pd.Series):
                return first_velocity_raw.iloc[0]
            else:
                return first_velocity_raw
                
        except Exception as e:
            return None
    
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
                
                if len(replay_vels_key) < 2:
                    continue
                
                # 进行线性回归（播放锤速 vs 相对延时）
                slope, intercept, r_value, p_value, std_err = stats.linregress(replay_vels_key, relative_delays_key)
                
                # 生成回归线的x和y值（用于绘图）
                vel_min = min(replay_vels_key)
                vel_max = max(replay_vels_key)
                vel_range = vel_max - vel_min
                
                # 生成10个点用于绘制回归线
                vel_line = np.linspace(vel_min - vel_range * 0.1, 
                                      vel_max + vel_range * 0.1, 10)
                delay_line = slope * vel_line + intercept
                
                interaction_data[key_id] = {
                    'forces': replay_vels_key,
                    'delays': relative_delays_key,  # 相对延时
                    'absolute_delays': absolute_delays_key,  # 原始延时
                    'record_indices': record_indices_key,
                    'replay_indices': replay_indices_key,
                    'mean_delay': float(mean_delay),  # 整体平均延时
                    'regression_line': {
                        'force': [float(v) for v in vel_line],
                        'delay': [float(d) for d in delay_line]
                    },
                    'slope': float(slope),
                    'intercept': float(intercept),
                    'r_squared': float(r_value ** 2),
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