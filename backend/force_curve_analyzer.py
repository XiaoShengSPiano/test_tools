#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
力度曲线分析器 - 使用标准DTW算法分析曲线相似度
"""
import traceback
import plotly.graph_objects as go
from typing import List, Tuple, Dict, Any, Optional, Union
import numpy as np
from dtw import dtw
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks
from utils.logger import Logger

logger = Logger.get_logger()

# TODO：需要优化 ？
class ForceCurveAnalyzer:
    """
    力度曲线分析器
    
    使用标准DTW算法计算两条曲线的相似度
    """

    def __init__(self,
                 dtw_distance_metric: str = 'euclidean',
                 dtw_window_size_ratio: float = 0.15):
        """
        初始化力度曲线分析器

        Args:
            dtw_distance_metric: DTW距离度量方式 ('euclidean' or 'manhattan')
            dtw_window_size_ratio: DTW窗口大小比例
        """
        self.dtw_distance_metric = dtw_distance_metric
        self.dtw_window_size_ratio = dtw_window_size_ratio

    def _calculate_action_fidelity(self, s1: Dict, s2: Dict) -> float:
        """计算两个动作段落之间的保真度"""
        if s1['type'] != s2['type']: return 0.0
        max_v = max(abs(s1['end_v']), abs(s2['end_v']), 1.0)
        v_sim = np.exp(-5.0 * (abs(s1['end_v'] - s2['end_v']) / max_v))
        max_slp = max(abs(s1['avg_slope']), abs(s2['avg_slope']), 0.1)
        slp_sim = np.exp(-5.0 * (abs(s1['avg_slope'] - s2['avg_slope']) / max_slp))
        return v_sim * slp_sim

    def _get_structural_alignment(self, sigs1: List[Dict], sigs2: List[Dict]) -> Tuple[float, List[Tuple[int, int]]]:
        """使用带权 LCS 算法对齐物理动作序列"""
        if not sigs1 and not sigs2: return 1.0, []
        if not sigs1 or not sigs2: return 0.2, []
        
        # 提取非 Stable 的动作序列
        seq1 = [(i, s) for i, s in enumerate(sigs1) if s['type'] != 'Stable']
        seq2 = [(i, s) for i, s in enumerate(sigs2) if s['type'] != 'Stable']
        
        if not seq1 or not seq2: return 0.2, []

        n, m = len(seq1), len(seq2)
        dp = np.zeros((n + 1, m + 1))
        
        for i in range(1, n + 1):
            for j in range(1, m + 1):
                if seq1[i-1][1]['type'] == seq2[j-1][1]['type']:
                    weight = self._calculate_action_fidelity(seq1[i-1][1], seq2[j-1][1])
                    dp[i, j] = dp[i-1, j-1] + weight
                else:
                    dp[i, j] = max(dp[i-1, j], dp[i, j-1])
        
        matches = []
        i, j = n, m
        while i > 0 and j > 0:
            if seq1[i-1][1]['type'] == seq2[j-1][1]['type'] and dp[i, j] > max(dp[i-1, j], dp[i, j-1]):
                matches.append((seq1[i-1][0], seq2[j-1][0]))
                i -= 1
                j -= 1
            elif dp[i-1, j] >= dp[i, j-1]:
                i -= 1
            else:
                j -= 1
        
        match_weight_sum = dp[n, m]
        score = (match_weight_sum / max(n, m)) ** 1.2
        return max(0.1, min(1.0, score)), matches[::-1]

    def compare_curves(self, note1, note2, record_note=None, replay_note=None, mean_delay: float = 0.0) -> Optional[Dict[str, Any]]:
        """对比两条力度曲线"""
        try:
            if record_note is None: record_note = note1
            if replay_note is None: replay_note = note2
            
            # 1. 提取并采样曲线 (0.1ms 硬件级精度)
            curve1_raw = self._extract_full_curve(record_note, use_offset=False)
            curve2_raw = self._extract_full_curve(replay_note, use_offset=False)
            if not curve1_raw or not curve2_raw: return None
            
            target_dt = 0.1
            t1, v1 = self._resample_curves(curve1_raw[0] - curve1_raw[0][0], curve1_raw[1], target_dt)
            t2, v2 = self._resample_curves(curve2_raw[0] - curve2_raw[0][0], curve2_raw[1], target_dt)

            # 2. 归一化特征
            v1_norm, v2_norm = self._normalize(v1), self._normalize(v2)

            # 3. 物理特征提取与结构化对齐
            rec_features = self._analyze_single_curve_features(t1, v1)
            rep_features = self._analyze_single_curve_features(t2, v2)
            
            rec_sigs, rep_sigs = rec_features.get('segments', []), rep_features.get('segments', [])
            structural_score, aligned_segment_pairs = self._get_structural_alignment(rec_sigs, rep_sigs)

            # 4. 细节还原度计算 (仅针对对齐成功的物理段落)
            fidelity_scores = []
            amp_sims = []
            for (idx1, idx2) in aligned_segment_pairs:
                s1, s2 = rec_sigs[idx1], rep_sigs[idx2]
                f_score = self._calculate_action_fidelity(s1, s2)
                fidelity_scores.append(f_score)
                max_v = max(abs(s1['end_v']), abs(s2['end_v']), 1.0)
                amp_sims.append(np.exp(-5.0 * (abs(s1['end_v'] - s2['end_v']) / max_v)))
            
            avg_fidelity = np.mean(fidelity_scores) if fidelity_scores else 0.0
            amp_similarity = np.mean(amp_sims) if amp_sims else 0.0
            
            # 5. 边沿相似度聚合
            rise_pairs = [f for f, (idx1, _) in zip(fidelity_scores, aligned_segment_pairs) if rec_sigs[idx1]['type'] == 'Rise']
            fall_pairs = [f for f, (idx1, _) in zip(fidelity_scores, aligned_segment_pairs) if rec_sigs[idx1]['type'] == 'Fall']
            rising_sim = np.mean(rise_pairs) if rise_pairs else 0.0
            falling_sim = np.mean(fall_pairs) if fall_pairs else 0.0
            
            # 6. 形状相似度 (DTW + Pearson)
            window_size = int(max(len(v1_norm), len(v2_norm)) * self.dtw_window_size_ratio)
            alignment = dtw(v1_norm, v2_norm, dist_method=self.dtw_distance_metric, step_pattern='symmetric2',
                            window_type='slantedband' if self.dtw_window_size_ratio > 0 else 'none',
                            window_args={'window_size': window_size} if self.dtw_window_size_ratio > 0 else {})
            
            dtw_sim = np.exp(-15.0 * (alignment.distance / (len(v1_norm) + len(v2_norm))))
            pearson_sim = self._calculate_pearson(v1_norm, v2_norm)
            shape_similarity = 0.7 * dtw_sim + 0.3 * pearson_sim

            # 7. 综合判定 (4:6 加权)
            physical_similarity = structural_score * (0.3 + 0.7 * avg_fidelity)
            overall_similarity = 0.4 * physical_similarity + 0.6 * shape_similarity
            
            # 兼容性修正逻辑
            if physical_similarity < 0.6:
                overall_similarity *= (0.5 + 0.5 * (physical_similarity / 0.6))

            return {
                'match_found': True,
                'overall_similarity': float(np.clip(overall_similarity, 0, 1)),
                'shape_similarity': float(shape_similarity),
                'amplitude_similarity': float(amp_similarity),
                'physical_similarity': float(np.clip(physical_similarity, 0, 1)),
                'pearson_correlation': float(pearson_sim),
                'dtw_distance': float(alignment.distance),
                'processing_stages': {
                    'stage_start_aligned': {'record_times': t1, 'record_values': v1, 'replay_times': t2, 'replay_values': v2, 'description': '时间轴对齐'},
                    'stage_normalized': {'record_times': t1, 'record_values': v1_norm, 'replay_times': t2, 'replay_values': v2_norm, 'description': '特征归一化'}
                },
                'record_features': rec_features,
                'replay_features': rep_features,
                'feature_comparison': self._compare_features(rec_features, rep_features),
                'rising_edge_similarity': float(rising_sim),
                'falling_edge_similarity': float(falling_sim),
                'alignment_comparison': {'record_times': t1, 'record_values': v1, 'replay_times': t2, 'replay_values': v2}
            }
        except Exception as e:
            logger.error(f"❌ 曲线对比失败: {e}\n{traceback.format_exc()}")
            return None

    def _normalize(self, values: np.ndarray) -> np.ndarray:
        """归一化到 0-1 范围 (带小信号保护)"""
        if len(values) == 0: return values
        
        v_min, v_max = np.min(values), np.max(values)
        if v_max - v_min < 1e-9:
            return np.zeros_like(values)
            
        return (values - v_min) / (v_max - v_min)

    def _resample_curves(self, times: np.ndarray, values: np.ndarray, target_dt: float = 0.1) -> Tuple[np.ndarray, np.ndarray]:
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
            
            # 状态判定阈值 (动态调整：基于峰值力度的 1%)
            # 确保轻触和重压都能获得合理的段落分解
            peak_val = np.max(values)
            threshold = max(0.5, peak_val * 0.01)
            
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
        """对齐后的核心物理特征差异对比"""
        if not feat1 or not feat2: return {}
        return {
            'peak_diff': float(feat2.get('peak_value', 0) - feat1.get('peak_value', 0)),
            'peak_count_diff': int(feat2.get('peak_count', 1) - feat1.get('peak_count', 1)),
            'rise_time_diff': float(feat2.get('rise_time_ms', 0) - feat1.get('rise_time_ms', 0))
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
    

