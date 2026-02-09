#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
力度曲线分析器 - 使用标准DTW算法分析曲线相似度

简化版：移除复杂的导数DTW，直接比较归一化后的曲线形状
"""

import plotly.graph_objects as go
from typing import List, Tuple, Dict, Any, Optional, Union
import numpy as np
from dtw import dtw
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks
from utils.logger import Logger

logger = Logger.get_logger()

# TODO
class ForceCurveAnalyzer:
    """
    力度曲线分析器
    
    使用标准DTW算法计算两条曲线的相似度
    """

    def __init__(self,
                 dtw_distance_metric: str = 'euclidean',
                 dtw_window_size_ratio: float = 0.5):
        """
        初始化力度曲线分析器

        Args:
            dtw_distance_metric: DTW距离度量方式 ('euclidean' or 'manhattan')
            dtw_window_size_ratio: DTW窗口大小比例
        """
        self.dtw_distance_metric = dtw_distance_metric
        self.dtw_window_size_ratio = dtw_window_size_ratio
    
    def compare_curves(self, note1, note2, record_note=None, replay_note=None, mean_delay: float = 0.0) -> Optional[Dict[str, Any]]:
        """
        对比两条力度曲线
        """
        try:
            if record_note is None: record_note = note1
            if replay_note is None: replay_note = note2
            
            # 提取原始曲线 (不加 offset)
            curve1_raw = self._extract_full_curve(record_note, use_offset=False)
            curve2_raw = self._extract_full_curve(replay_note, use_offset=False)
            
            if curve1_raw is None or curve2_raw is None:
                return None
            
            t1_raw, v1_raw = curve1_raw
            t2_raw, v2_raw = curve2_raw
            
            # 归一化时间轴：采用相对时间 (从0开始)
            # 这样对比将纯粹专注于波形形状，而不受其在全局序列中位置的影响
            t1_rel = t1_raw - t1_raw[0] if len(t1_raw) > 0 else t1_raw
            t2_rel = t2_raw - t2_raw[0] if len(t2_raw) > 0 else t2_raw

            # 1. 重采样 (建立统一的时间基准)
            # 使用 0.5ms 作为均衡步长
            target_dt = 0.5 
            t1, v1 = self._resample_curves(t1_rel, v1_raw, target_dt)
            t2, v2 = self._resample_curves(t2_rel, v2_raw, target_dt)

            # 2. 对齐策略 (由于已经相对化，此处对齐更加纯粹)
            # 在相对时间轴下，直接比较形状
            t2_aligned = t2 # 已经对齐到起始点 0

            # 3. 归一化 (用于形状对比)
            v1_norm = self._normalize(v1)
            v2_norm = self._normalize(v2)

            # 4.1 提取动作签名序列 (Action Signature)
            # 将曲线转化为一系列有序的物理动作 [Rise, Fall, Rise...]
            rec_features = self._analyze_single_curve_features(t1, v1)
            rep_features = self._analyze_single_curve_features(t2_aligned, v2)
            
            rec_sigs = rec_features.get('segments', [])
            rep_sigs = rep_features.get('segments', [])
            
            # --- 深度对比逻辑：统一特征签名匹配 ---
            
            # 1. 结构一致性 (Structural Integrity)
            def get_structural_score(sigs1, sigs2):
                if not sigs1 and not sigs2: return 1.0
                if not sigs1 or not sigs2: return 0.2 # 彻底结构缺失重罚
                
                type_seq1 = [s['type'] for s in sigs1 if s['type'] != 'Stable']
                type_seq2 = [s['type'] for s in sigs2 if s['type'] != 'Stable']
                
                if type_seq1 == type_seq2:
                    return 1.0
                else:
                    # 序列不一致惩罚 (基于编辑距离的思想，简单化处理)
                    common_len = min(len(type_seq1), len(type_seq2))
                    matches = sum(1 for i in range(common_len) if type_seq1[i] == type_seq2[i])
                    base_score = matches / max(len(type_seq1), len(type_seq2))
                    return base_score ** 2 # 非线性重罚

            structural_score = get_structural_score(rec_sigs, rep_sigs)

            # 2. 细节还原度 (Signature Fidelity) - 幅度与斜率的一体化对比
            def compare_action_fidelity(s1, s2):
                # 对比端点幅度 (End Value)
                # 使用指数惩罚，偏差 15% 以上分数迅速跌落
                max_v = max(abs(s1['end_v']), abs(s2['end_v']), 1.0)
                v_diff = abs(s1['end_v'] - s2['end_v']) / max_v
                v_sim = np.exp(-12.0 * v_diff)
                
                # 对比斜率 (Slope)
                max_slp = max(abs(s1['avg_slope']), abs(s2['avg_slope']), 0.1)
                slp_diff = abs(s1['avg_slope'] - s2['avg_slope']) / max_slp
                slp_sim = np.exp(-10.0 * slp_diff)
                
                # 动作还原度 = 幅度与斜率的联合判定（任何一个不行都不行）
                return v_sim * slp_sim 

            fidelity_scores = []
            amp_sims = []
            min_len = min(len(rec_sigs), len(rep_sigs))
            for i in range(min_len):
                if rec_sigs[i]['type'] == rep_sigs[i]['type']:
                    # 单独计算幅度分用于显示 (端点值对比)
                    max_v = max(abs(rec_sigs[i]['end_v']), abs(rep_sigs[i]['end_v']), 1.0)
                    v_sim = np.exp(-12.0 * (abs(rec_sigs[i]['end_v'] - rep_sigs[i]['end_v']) / max_v))
                    amp_sims.append(v_sim)
                    
                    fidelity_scores.append(compare_action_fidelity(rec_sigs[i], rep_sigs[i]))
                else:
                    fidelity_scores.append(0.0)
                    amp_sims.append(0.0)
            
            avg_fidelity = np.mean(fidelity_scores) if fidelity_scores else structural_score
            amp_similarity = np.mean(amp_sims) if amp_sims else structural_score
            
            # 物理结构分 (Strict Physical) - 50%
            physical_similarity = structural_score * (0.3 + 0.7 * avg_fidelity)
            # 确保在范围 0-1
            physical_similarity = max(0.0, min(1.0, physical_similarity))
            amp_similarity = max(0.0, min(1.0, amp_similarity))

            # 4.2 形状与相关性评分 (Shape & Correlation) - 50%
            # 调高 DTW 敏感度至极高 (映射系数 20)
            window_size = int(max(len(v1_norm), len(v2_norm)) * self.dtw_window_size_ratio)
            alignment = dtw(
                v1_norm, v2_norm, 
                dist_method=self.dtw_distance_metric,
                step_pattern='symmetric2',
                window_type='slantedband' if self.dtw_window_size_ratio > 0 else 'none',
                window_args={'window_size': window_size} if self.dtw_window_size_ratio > 0 else {}
            )
            norm_dist = alignment.distance / (len(v1_norm) + len(v2_norm))
            dtw_sim = np.exp(-20.0 * norm_dist) 
            
            pearson_sim = self._calculate_pearson(v1_norm, v2_norm)
            shape_similarity = 0.4 * dtw_sim + 0.6 * pearson_sim

            # 5. 综合总分：采用几何平均思想 (Anti-inflation)
            # 任何一个维度（物理结构或形状相关性）极低，都会导致总分极低
            overall_similarity = np.sqrt(physical_similarity * shape_similarity)
            overall_similarity = max(0.0, min(1.0, overall_similarity))

            # 如果视觉差异大，分数必须低。
            # 这里强制阈值：如果物理结构分低于 0.6，总分直接锁定在及格线以下
            if physical_similarity < 0.6:
                overall_similarity = min(overall_similarity, physical_similarity)

            # 6. 构建结果
            stages = {
                'stage_start_aligned': {'record_times': t1, 'record_values': v1, 'replay_times': t2_aligned, 'replay_values': v2, 'description': '相对时间对齐'},
                'stage_normalized': {'record_times': t1, 'record_values': v1_norm, 'replay_times': t2_aligned, 'replay_values': v2_norm, 'description': '归一化特征'}
            }
            
            return {
                'match_found': True,
                'overall_similarity': float(overall_similarity),
                'shape_similarity': float(shape_similarity),
                'amplitude_similarity': float(amp_similarity),
                'physical_similarity': float(physical_similarity),
                'pearson_correlation': float(pearson_sim),
                'dtw_distance': float(alignment.distance),
                'max_record': rec_features.get('peak_value', 0.0),
                'max_replay': rep_features.get('peak_value', 0.0),
                'processing_stages': stages,
                'record_features': rec_features,
                'replay_features': rep_features,
                'feature_comparison': self._compare_features(rec_features, rep_features),
                'rising_edge_similarity': float(physical_similarity),
                'falling_edge_similarity': float(physical_similarity),
                'alignment_comparison': {'record_times': t1, 'record_values': v1, 'replay_times': t2_aligned, 'replay_values': v2}
            }
            
        except Exception as e:
            logger.error(f"❌ DTW曲线对比失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _normalize(self, values: np.ndarray) -> np.ndarray:
        """归一化到 0-1 范围 (带小信号保护)"""
        if len(values) == 0: return values
        
        v_min, v_max = np.min(values), np.max(values)
        if v_max - v_min < 1e-9:
            return np.zeros_like(values)
            
        return (values - v_min) / (v_max - v_min)

    def _resample_curves(self, times: np.ndarray, values: np.ndarray, target_dt: float = 0.5) -> Tuple[np.ndarray, np.ndarray]:
        """
        重采样曲线到固定的时间间隔 (ms)
        针对 100us (0.1ms) 采样单位进行统一插值
        """
        if len(times) < 2:
            return times, values
            
        t_start, t_end = times[0], times[-1]
        # 创建新的统一时间轴
        new_times = np.arange(t_start, t_end + target_dt/2, target_dt)
        # 线性插值
        new_values = np.interp(new_times, times, values)
        
        return new_times, new_values

    def _calculate_impulse(self, times: np.ndarray, values: np.ndarray) -> float:
        """
        使用梯形法则计算冲量 (积分面积)
        针对非均匀采样 (间隔 1, 2, 3) 具有鲁棒性
        """
        if len(times) < 2:
            return 0.0
        # numpy.trapz(y, x) 使用梯形法则
        return float(np.trapz(values, times))

    def _calculate_pearson(self, v1: np.ndarray, v2: np.ndarray) -> float:
        """计算皮尔逊相关系数"""
        if len(v1) < 2 or len(v2) < 2:
            return 0.0
        
        # 长度对齐 (插值较短的到较长的长度)
        if len(v1) != len(v2):
            indices = np.linspace(0, len(v1)-1, len(v2))
            v1_aligned = np.interp(indices, np.arange(len(v1)), v1)
            v2_aligned = v2
        else:
            v1_aligned, v2_aligned = v1, v2
            
        correlation = np.corrcoef(v1_aligned, v2_aligned)[0, 1]
        return float(max(0.0, correlation)) if np.isfinite(correlation) else 0.0

    def _analyze_single_curve_features(self, times: np.ndarray, values: np.ndarray) -> Dict[str, Any]:
        """
        分析单条曲线的物理特征 (增强版：支持多段分解)
        """
        try:
            if len(values) == 0:
                return {}
            
            # 1. 基础极值
            peak_idx = np.argmax(values)
            peak_value = values[peak_idx]
            peak_time = times[peak_idx]
            
            # 2. 多波峰与波谷检测
            prominence = peak_value * 0.1
            peaks, _ = find_peaks(values, height=prominence, distance=10)
            # 波谷检测：对原始值取反求峰值
            valleys, _ = find_peaks(-values, distance=10)
            
            peak_count = len(peaks) if len(peaks) > 0 else 1
            
            # 3. 结构化段落分解 (Rising / Falling / Stable)
            segments = self._decompose_segments(times, values)
            
            # 4. 上升沿分析 (到第一个显著波峰)
            threshold_10 = peak_value * 0.1
            threshold_90 = peak_value * 0.9
            first_peak_90_idx = np.where(values >= threshold_90)[0][0] if any(values >= threshold_90) else peak_idx
            rise_start_idx = 0
            for i in range(first_peak_90_idx, -1, -1):
                if values[i] < threshold_10:
                    rise_start_idx = i
                    break
            rise_time = times[first_peak_90_idx] - times[rise_start_idx]
            
            # 5. 波动率
            values_smooth = gaussian_filter1d(values, sigma=2.0)
            volatility = np.std(values - values_smooth)
            
            return {
                'peak_value': float(peak_value),
                'peak_time': float(peak_time),
                'peak_count': int(peak_count),
                'peak_heights': [float(values[p]) for p in peaks] if len(peaks) > 0 else [float(peak_value)],
                'valley_heights': [float(values[v]) for v in valleys],
                'segments': segments,
                'rise_time_ms': float(rise_time),
                'volatility': float(volatility),
                'markers': {
                    'peak': (peak_time, peak_value),
                    'peaks': [(times[p], values[p]) for p in peaks],
                    'valleys': [(times[v], values[v]) for v in valleys],
                    'rise_10': (times[rise_start_idx], values[rise_start_idx]),
                    'rise_90': (times[first_peak_90_idx], values[first_peak_90_idx])
                }
            }
        except Exception as e:
            logger.error(f"特征提取失败: {e}")
            return {}

    def _decompose_segments(self, times: np.ndarray, values: np.ndarray) -> List[Dict[str, Any]]:
        """
        利用导数将曲线分解为上升段和下降段
        """
        try:
            if len(values) < 3: return []
            
            # 平滑处理以获得更准确的导数
            v_smooth = gaussian_filter1d(values, sigma=1.5)
            # 计算一阶导数 (速度)
            dv = np.gradient(v_smooth, times)
            
            # 状态判定阈值 (力度单位/ms)
            threshold = 1.0 
            
            segments = []
            curr_type = None
            start_idx = 0
            
            for i in range(len(dv)):
                # 判定当前点的状态
                if dv[i] > threshold:
                    stype = 'Rise'
                elif dv[i] < -threshold:
                    stype = 'Fall'
                else:
                    stype = 'Stable'
                
                if stype != curr_type:
                    if curr_type in ['Rise', 'Fall']:
                        # 记录之前的段落
                        duration = times[i-1] - times[start_idx]
                        if duration > 1.0: # 忽略极短的抖动 (1ms)
                            change = values[i-1] - values[start_idx]
                            segments.append({
                                'type': curr_type,
                                'start_idx': start_idx,
                                'end_idx': i-1,
                                'start_v': float(values[start_idx]),
                                'end_v': float(values[i-1]),
                                'duration': float(duration),
                                'avg_slope': float(change / duration)
                            })
                    curr_type = stype
                    start_idx = i
            
            # 处理最后一段
            if curr_type in ['Rise', 'Fall']:
                duration = times[-1] - times[start_idx]
                if duration > 1.0:
                    change = values[-1] - values[start_idx]
                    segments.append({
                        'type': curr_type,
                        'start_idx': start_idx,
                        'end_idx': len(times)-1,
                        'start_v': float(values[start_idx]),
                        'end_v': float(values[-1]),
                        'duration': float(duration),
                        'avg_slope': float(change / duration)
                    })
                    
            return segments
        except Exception as e:
            logger.error(f"分解段落失败: {e}")
            return []

    def _compare_features(self, feat1: Dict, feat2: Dict) -> Dict[str, Any]:
        """对比两组特征 (增强版)"""
        if not feat1 or not feat2:
            return {}
            
        return {
            'peak_diff': feat2.get('peak_value', 0) - feat1.get('peak_value', 0),
            'peak_count_diff': feat2.get('peak_count', 1) - feat1.get('peak_count', 1),
            'rise_time_diff': feat2.get('rise_time_ms', 0) - feat1.get('rise_time_ms', 0),
            'volatility_ratio': feat2.get('volatility', 0) / (feat1.get('volatility', 0) + 1e-6),
            'impulse_diff': feat2.get('impulse', 0) - feat1.get('impulse', 0)
        }
    
    def generate_processing_stages_figures(self, comparison_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        生成处理阶段图表
        """
        try:
            if 'processing_stages' not in comparison_result:
                return []
            
            stages = comparison_result['processing_stages']
            result_figures = []
            
            # 定义要展示的阶段 (移除原始曲线对比，精简UI)
            stage_configs = [
                ('stage_start_aligned', '起始点对齐 (形状对比)', '力度值'),
                ('stage_normalized', '归一化形状对比 (DTW输入)', '归一化值')
            ]
            
            for key, title, yaxis in stage_configs:
                if key not in stages: continue
                
                data = stages[key]
                fig = go.Figure()
                
                fig.add_trace(go.Scattergl(
                    x=data['record_times'], y=data['record_values'],
                    mode='lines', name='录制', line=dict(color='blue')
                ))
                
                fig.add_trace(go.Scattergl(
                    x=data['replay_times'], y=data['replay_values'],
                    mode='lines', name='播放', line=dict(color='red', dash='dash')
                ))
                
                # 如果是修正后，添加特征标记
                if key == 'stage_offset_corrected':
                    self._add_markers_to_fig(fig, comparison_result.get('record_features'), 'blue', '录制')
                    self._add_markers_to_fig(fig, comparison_result.get('replay_features'), 'red', '播放')
                
                fig.update_layout(
                    # title=title,  # UI中已有Markdown标题，此处移除避免重复
                    xaxis_title='时间 (ms)',
                    yaxis_title=yaxis,
                    height=400,
                    margin=dict(l=20, r=20, t=20, b=20),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                
                result_figures.append({
                    'title': title,
                    'figure': fig,
                    'key': key
                })
                
            return result_figures
            
        except Exception as e:
            logger.error(f"生成图表失败: {e}")
            return []

    def _add_markers_to_fig(self, fig, features, color, prefix):
        """辅助方法：添加特征标记 (支持多波峰展示)"""
        if not features or 'markers' not in features: return
        markers = features['markers']
        
        # 主峰值
        if 'peak' in markers:
            fig.add_trace(go.Scattergl(
                x=[markers['peak'][0]], y=[markers['peak'][1]],
                mode='markers', marker=dict(symbol='star', size=12, color=color),
                name=f'{prefix}主峰', showlegend=True
            ))
            
        # 所有检测到的波峰
        if 'peaks' in markers and len(markers['peaks']) > 1:
            pk_times = [p[0] for p in markers['peaks']]
            pk_vals = [p[1] for p in markers['peaks']]
            fig.add_trace(go.Scattergl(
                x=pk_times, y=pk_vals,
                mode='markers', marker=dict(symbol='circle-open', size=8, color=color),
                name=f'{prefix}各波峰', showlegend=False
            ))
            
        # 所有检测到的波谷
        if 'valleys' in markers and len(markers['valleys']) > 0:
            v_times = [p[0] for p in markers['valleys']]
            v_vals = [p[1] for p in markers['valleys']]
            fig.add_trace(go.Scattergl(
                x=v_times, y=v_vals,
                mode='markers', marker=dict(symbol='triangle-down', size=8, color=color),
                name=f'{prefix}各波谷', showlegend=False
            ))

    def visualize_all_processing_stages(self, comparison_result: Dict[str, Any]) -> Optional[Any]:
        """兼容性包装器"""
        return None

    def visualize_alignment_comparison(self, comparison_result: Dict[str, Any]) -> Optional[Any]:
        """兼容性包装器 - 返回修正后的对比图"""
        try:
            if 'processing_stages' not in comparison_result: return None
            stages = comparison_result['processing_stages']
            if 'stage_offset_corrected' not in stages: return None
            
            data = stages['stage_offset_corrected']
            fig = go.Figure()
            fig.add_trace(go.Scattergl(x=data['record_times'], y=data['record_values'], name='录制', line=dict(color='blue')))
            fig.add_trace(go.Scattergl(x=data['replay_times'], y=data['replay_values'], name='播放', line=dict(color='red', dash='dash')))
            fig.update_layout(title="曲线对比 (时间修正后)")
            return fig
        except:
            return None

    def generate_similarity_stages_figures(self, comparison_result: Dict[str, Any],
                                         base_name: str, compare_name: str, similarity: float) -> List[Dict[str, Any]]:
        """兼容性包装器"""
        return self.generate_processing_stages_figures(comparison_result)

    def _extract_full_curve(self, note, use_offset=True) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """从 Note 的 after_touch 提取完整曲线 (times, values)。"""
        try:
            if not hasattr(note, 'after_touch') or not hasattr(note.after_touch, 'values'):
                return None

            values = note.after_touch.values
            if hasattr(note.after_touch, 'index'):
                offset = getattr(note, 'offset', 0) if use_offset else 0
                times = (np.array(note.after_touch.index) + offset) / 10.0
            elif hasattr(note, 'key_on_ms'):
                times = note.key_on_ms
            else:
                return None

            times = np.array(times)
            values = np.array(values)
            if len(times) == 0:
                return None
            return times, values
            
        except Exception as e:
            logger.error(f"提取曲线失败: {e}")
            return None
    
    def _calculate_simple_similarity(self, values1: np.ndarray, values2: np.ndarray) -> float:
        """
        计算简单的相似度

        Args:
            values1: 第一组值
            values2: 第二组值

        Returns:
            相似度 (0-1)
        """
        try:
            # 处理不同长度的数组 - 插值到相同长度
            len1, len2 = len(values1), len(values2)
            if len1 != len2:
                # 取较短的长度作为基准，插值较长的数组
                min_len = min(len1, len2)
                if len1 > len2:
                    # values1 较长，对 values2 插值
                    indices = np.linspace(0, len2-1, min_len)
                    values2_aligned = np.interp(indices, np.arange(len2), values2)
                    values1_aligned = values1[:min_len]
                else:
                    # values2 较长，对 values1 插值
                    indices = np.linspace(0, len1-1, min_len)
                    values1_aligned = np.interp(indices, np.arange(len1), values1)
                    values2_aligned = values2[:min_len]
            else:
                values1_aligned = values1
                values2_aligned = values2

            # 简单的均方根误差归一化相似度
            mse = np.mean((values1_aligned - values2_aligned) ** 2)
            max_possible_error = np.var(values1_aligned) + np.var(values2_aligned)
            if max_possible_error == 0:
                return 1.0

            similarity = 1.0 - (mse / max_possible_error)
            return max(0.0, min(1.0, similarity))

        except Exception as e:
            logger.error(f"❌ 计算相似度失败: {e}")
            return 0.5
