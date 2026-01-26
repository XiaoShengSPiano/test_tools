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
from utils.logger import Logger

logger = Logger.get_logger()


class ForceCurveAnalyzer:
    """
    力度曲线分析器
    
    使用标准DTW算法计算两条曲线的相似度
    """

    def __init__(self, 
                 smooth_sigma: float = 1.0,
                 dtw_distance_metric: str = 'euclidean',
                 dtw_window_size_ratio: float = 0.5):
        """
        初始化力度曲线分析器
        
        Args:
            smooth_sigma: 平滑强度 (保留参数用于兼容，实际可能仅用于特征提取)
            dtw_distance_metric: DTW距离度量方式 ('euclidean' or 'manhattan')
            dtw_window_size_ratio: DTW窗口大小比例
        """
        self.smooth_sigma = smooth_sigma
        self.dtw_distance_metric = dtw_distance_metric
        self.dtw_window_size_ratio = dtw_window_size_ratio
    
    def compare_curves(self, note1, note2, record_note=None, replay_note=None, mean_delay: float = 0.0) -> Optional[Dict[str, Any]]:
        """
        对比两条力度曲线
        
        Args:
            note1: 第一个音符对象
            note2: 第二个音符对象
            record_note: 录制音符对象
            replay_note: 播放音符对象
            mean_delay: 平均延时(ms)
            
        Returns:
            对比结果字典，如果失败则返回None
        """
        try:
            # 确定录制和播放曲线
            if record_note is None: record_note = note1
            if replay_note is None: replay_note = note2
            
            # 提取完整曲线数据
            curve1_data = self._extract_full_curve(record_note)
            curve2_data = self._extract_full_curve(replay_note)
            
            if curve1_data is None or curve2_data is None:
                return None
            
            times1, values1 = curve1_data
            times2, values2 = curve2_data
            
            # 1. 偏移修正
            times2_shifted = times2.copy()
            if mean_delay != 0:
                times2_shifted = times2 - mean_delay
            # 1.5. 强制起始点对齐 (Visual Shape Comparison)
            # 将两条曲线的起始时间对齐，用于纯粹的形状对比
            time_shift_start = times1[0] - times2[0]
            times2_start_aligned = times2 + time_shift_start
            
            # 2. 预处理：归一化 (Min-Max Scaling)
            # DTW对幅度敏感，必须归一化到 0-1 范围才能只比较"形状"
            v1_norm = self._normalize(values1)
            v2_norm = self._normalize(values2)
            
            # 3. DTW 计算 (Shape Similarity)
            # 计算窗口大小
            window_size = int(max(len(v1_norm), len(v2_norm)) * self.dtw_window_size_ratio)
            window_args = {'window_size': window_size} if self.dtw_window_size_ratio > 0 else {}
            
            alignment = dtw(
                v1_norm, 
                v2_norm, 
                dist_method=self.dtw_distance_metric,
                step_pattern='symmetric2',
                window_type='slantedband' if self.dtw_window_size_ratio > 0 else 'none',
                window_args=window_args,
                keep_internals=True
            )
            
            dtw_distance = alignment.distance
            # 形状相似度 (Shape Score)
            shape_similarity = 1.0 / (1.0 + dtw_distance)

            # 4. 幅度相似度 (Amplitude Assessment)
            max_v1 = np.max(values1) if len(values1) > 0 else 0
            max_v2 = np.max(values2) if len(values2) > 0 else 0
            
            # 避免除以零
            max_val = max(max_v1, max_v2)
            if max_val > 0:
                amplitude_diff_ratio = abs(max_v1 - max_v2) / max_val
                amplitude_similarity = 1.0 - amplitude_diff_ratio
            else:
                amplitude_similarity = 1.0 # 都是0，完全匹配

            # 5. 综合评分 (Weighted Combination)
            # 权重可调：形状60%，幅度40%
            w_shape = 0.6
            w_amplitude = 0.4
            
            overall_similarity = (w_shape * shape_similarity) + (w_amplitude * amplitude_similarity)
            
            # 6. 构建对齐后的数据用于展示
            stages = {}
            
            # 阶段1：原始曲线
            stages['stage1_original'] = {
                'record_times': times1,
                'record_values': values1,
                'replay_times': times2,
                'replay_values': values2,
                'description': '原始曲线'
            }
            
            # 阶段2：起始点对齐 (Start Aligned) - 用户主要关注这个
            stages['stage_start_aligned'] = {
                'record_times': times1,
                'record_values': values1,
                'replay_times': times2_start_aligned,
                'replay_values': values2,
                'description': '起始点对齐 (形状对比)'
            }
            
            # 阶段3：偏移修正 (Mean Delay Corrected)
            stages['stage_offset_corrected'] = {
                'record_times': times1,
                'record_values': values1,
                'replay_times': times2_shifted,
                'replay_values': values2,
                'description': '平均延时修正后'
            }
            
            # 阶段4：归一化后 (用于Debug DTW输入)
            stages['stage_normalized'] = {
                'record_times': times1,
                'record_values': v1_norm,
                'replay_times': times2_start_aligned, # 归一化图使用对齐后的时间轴展示
                'replay_values': v2_norm,
                'description': '归一化 (DTW输入)'
            }
            
            # 特征提取 (保留原有逻辑)
            record_features = self._analyze_single_curve_features(times1, values1)
            replay_features = self._analyze_single_curve_features(times2_start_aligned, values2) # 使用对齐后的时间用于特征比较（如Peak Time相对位置）
            feature_comparison = self._compare_features(record_features, replay_features)
            
            return {
                'match_found': True,
                'overall_similarity': overall_similarity,
                'shape_similarity': shape_similarity,
                'amplitude_similarity': amplitude_similarity,
                'dtw_distance': dtw_distance,
                'max_record': max_v1,
                'max_replay': max_v2,
                'processing_stages': stages,
                'record_features': record_features,
                'replay_features': replay_features,
                'feature_comparison': feature_comparison,
                # 兼容旧UI字段
                'rising_edge_similarity': overall_similarity, # Use overall_similarity for compatibility
                'falling_edge_similarity': overall_similarity, # Use overall_similarity for compatibility
                'alignment_comparison': {
                    'record_times': times1,
                    'record_values': values1,
                    'replay_times': times2_shifted,
                    'replay_values': values2
                }
            }
            
        except Exception as e:
            logger.error(f"❌ DTW曲线对比失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _normalize(self, values: np.ndarray) -> np.ndarray:
        """归一化到 0-1 范围"""
        if len(values) == 0: return values
        if np.all(values == values[0]): return np.zeros_like(values) # 常数数组
        
        min_val = np.min(values)
        max_val = np.max(values)
        if max_val - min_val < 1e-9:
            return np.zeros_like(values)
            
        return (values - min_val) / (max_val - min_val)

    def _analyze_single_curve_features(self, times: np.ndarray, values: np.ndarray) -> Dict[str, Any]:
        """
        分析单条曲线的物理特征
        """
        try:
            if len(values) == 0:
                return {}
            
            peak_idx = np.argmax(values)
            peak_value = values[peak_idx]
            peak_time = times[peak_idx]
            
            threshold_10 = peak_value * 0.1
            threshold_90 = peak_value * 0.9
            
            # 上升沿
            rise_start_idx = 0
            rise_end_idx = peak_idx
            
            for i in range(peak_idx, -1, -1):
                if values[i] < threshold_10:
                    rise_start_idx = i
                    break
            
            for i in range(peak_idx, -1, -1):
                if values[i] < threshold_90:
                    rise_end_idx = i + 1 
                    break
            
            if rise_end_idx >= len(times): rise_end_idx = len(times) - 1
            
            rise_time = times[rise_end_idx] - times[rise_start_idx]
            rise_slope = (values[rise_end_idx] - values[rise_start_idx]) / (rise_time + 1e-6) if rise_time > 0 else 0
            
            # 下降沿
            fall_start_idx = peak_idx
            fall_end_idx = len(values) - 1
            
            for i in range(peak_idx, len(values)):
                if values[i] < threshold_90:
                    fall_start_idx = i - 1
                    break
            
            for i in range(peak_idx, len(values)):
                if values[i] < threshold_10:
                    fall_end_idx = i
                    break
            
            if fall_start_idx < 0: fall_start_idx = 0
            
            fall_time = times[fall_end_idx] - times[fall_start_idx]
            fall_slope = (values[fall_start_idx] - values[fall_end_idx]) / (fall_time + 1e-6) if fall_time > 0 else 0
            
            # 抖动
            from scipy.ndimage import gaussian_filter1d
            values_smooth = gaussian_filter1d(values, sigma=2.0)
            jitter = np.std(values - values_smooth)
            
            return {
                'peak_value': float(peak_value),
                'peak_time': float(peak_time),
                'rise_time_ms': float(rise_time),
                'rise_slope': float(rise_slope),
                'fall_time_ms': float(fall_time),
                'fall_slope': float(fall_slope),
                'jitter': float(jitter),
                'markers': {
                    'peak': (peak_time, peak_value),
                    'rise_10': (times[rise_start_idx], values[rise_start_idx]),
                    'rise_90': (times[rise_end_idx], values[rise_end_idx]),
                    'fall_90': (times[fall_start_idx], values[fall_start_idx]),
                    'fall_10': (times[fall_end_idx], values[fall_end_idx])
                }
            }
        except Exception as e:
            logger.error(f"特征提取失败: {e}")
            return {}

    def _compare_features(self, feat1: Dict, feat2: Dict) -> Dict[str, Any]:
        """对比两组特征"""
        if not feat1 or not feat2:
            return {}
            
        return {
            'peak_diff': feat2.get('peak_value', 0) - feat1.get('peak_value', 0),
            'peak_time_lag': feat2.get('peak_time', 0) - feat1.get('peak_time', 0),
            'rise_time_diff': feat2.get('rise_time_ms', 0) - feat1.get('rise_time_ms', 0),
            'fall_time_diff': feat2.get('fall_time_ms', 0) - feat1.get('fall_time_ms', 0),
            'jitter_ratio': feat2.get('jitter', 0) / (feat1.get('jitter', 0) + 1e-6)
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
            
            # 定义要展示的阶段
            stage_configs = [
                ('stage_start_aligned', '起始点对齐 (形状对比)', '力度值'),
                ('stage_normalized', '归一化形状对比 (DTW输入)', '归一化值'),
                ('stage1_original', '原始曲线对比', '力度值')
            ]
            
            for key, title, yaxis in stage_configs:
                if key not in stages: continue
                
                data = stages[key]
                fig = go.Figure()
                
                fig.add_trace(go.Scatter(
                    x=data['record_times'], y=data['record_values'],
                    mode='lines', name='录制', line=dict(color='blue')
                ))
                
                fig.add_trace(go.Scatter(
                    x=data['replay_times'], y=data['replay_values'],
                    mode='lines', name='播放', line=dict(color='red', dash='dash')
                ))
                
                # 如果是修正后，添加特征标记
                if key == 'stage_offset_corrected':
                    self._add_markers_to_fig(fig, comparison_result.get('record_features'), 'blue', '录制')
                    self._add_markers_to_fig(fig, comparison_result.get('replay_features'), 'red', '播放')
                
                fig.update_layout(
                    title=title,
                    xaxis_title='时间 (ms)',
                    yaxis_title=yaxis,
                    height=400,
                    margin=dict(l=20, r=20, t=40, b=20),
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
        """辅助方法：添加特征标记"""
        if not features or 'markers' not in features: return
        markers = features['markers']
        
        # 峰值
        if 'peak' in markers:
            fig.add_trace(go.Scatter(
                x=[markers['peak'][0]], y=[markers['peak'][1]],
                mode='markers', marker=dict(symbol='star', size=10, color=color),
                name=f'{prefix}峰值', showlegend=False
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
            fig.add_trace(go.Scatter(x=data['record_times'], y=data['record_values'], name='录制', line=dict(color='blue')))
            fig.add_trace(go.Scatter(x=data['replay_times'], y=data['replay_values'], name='播放', line=dict(color='red', dash='dash')))
            fig.update_layout(title="曲线对比 (时间修正后)")
            return fig
        except:
            return None

    def generate_similarity_stages_figures(self, comparison_result: Dict[str, Any],
                                         base_name: str, compare_name: str, similarity: float) -> List[Dict[str, Any]]:
        """兼容性包装器"""
        return self.generate_processing_stages_figures(comparison_result)

    def _extract_full_curve(self, note) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """提取完整曲线数据"""
        try:
            # 尝试多种属性访问方式以兼容不同Note对象结构 (Mock vs Real)
            times = None
            values = None
            
            # 1. 真实Note对象的结构: note.after_touch (Series)
            if hasattr(note, 'after_touch') and hasattr(note.after_touch, 'values'):
                values = note.after_touch.values
                if hasattr(note.after_touch, 'index'):
                    # 真实数据的index通常是基于0的，需要加上offset并转ms
                    offset = getattr(note, 'offset', 0)
                    times = (np.array(note.after_touch.index) + offset) / 10.0
                elif hasattr(note, 'key_on_ms'):
                     times = note.key_on_ms
            
            # 2. 备用/Mock结构
            if values is None and hasattr(note, 'values'):
                values = note.values
            if times is None and hasattr(note, 'times'):
                times = note.times

            if times is None or values is None:
                return None
                
            times = np.array(times)
            values = np.array(values)
            
            if len(times) == 0: return None
            
            return times, values
            
        except Exception as e:
            logger.error(f"提取曲线失败: {e}")
            return None

            fig.add_trace(go.Scatter(
                x=stage['replay_times'], y=stage['replay_values'],
                mode='lines', name=f'播放导数 ({compare_name})',
                line=dict(color='#ff7f0e', width=2)
            ))
            fig.update_layout(
                title=f'对齐后导数曲线对比 (相似度: {similarity:.3f})',
                xaxis_title='时间 (ms)', yaxis_title='导数值', height=400
            )
            figures.append({'title': '阶段4：对齐后导数曲线', 'figure': fig})

        return figures
    
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
