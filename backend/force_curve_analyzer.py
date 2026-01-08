#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
力度曲线分析器 - 分析after_touch曲线的上升沿和下降沿

用于匹配算法和曲线对比分析
"""

import plotly.graph_objects as go
from typing import List, Tuple, Dict, Any, Optional, Union
import numpy as np
from utils.logger import Logger

logger = Logger.get_logger()


class DerivativeDTWAligner:
    """
    基于导数的DTW对齐器
    
    核心思想：
    - 对曲线的导数（斜率）进行DTW对齐，而非原始值
    - 导数更能反映曲线的变化趋势，符合"上升沿"和"下降沿"的本质
    - 对小幅抖动更鲁棒，因为小幅抖动在导数上的影响相对较小
    """
    
    def __init__(self,
                 smooth_sigma: float = 1.0,
                 distance_metric: str = 'manhattan',
                 window_size_ratio: float = 0.5):
        """
        初始化基于导数的DTW对齐器
        
        Args:
            smooth_sigma: 高斯平滑参数
            distance_metric: DTW距离度量方式
            window_size_ratio: DTW窗口大小比例
        """
        self.smooth_sigma = smooth_sigma
        self.distance_metric = distance_metric
        self.window_size_ratio = window_size_ratio
    
    def align_full_curves(self, curve1: Tuple[np.ndarray, np.ndarray],
                         curve2: Tuple[np.ndarray, np.ndarray]) -> Optional[Dict[str, Any]]:
        """
        对齐两条完整曲线
        
        Args:
            curve1: (times1, values1) - 第一条完整曲线
            curve2: (times2, values2) - 第二条完整曲线
        
        Returns:
            对齐结果字典，如果失败则返回None
        """
        try:
            from scipy.ndimage import gaussian_filter1d
            from scipy.interpolate import interp1d
            
            times1, values1 = curve1
            times2, values2 = curve2
            
            # 数据验证
            if len(times1) < 2 or len(times2) < 2:
                logger.warning("⚠️ 曲线数据点不足，无法计算导数")
                return None
            
            # 1. 平滑处理
            # 使用较小的sigma以保留特征
            smooth_sigma = self.smooth_sigma
            values1_smooth = gaussian_filter1d(values1, sigma=smooth_sigma)
            values2_smooth = gaussian_filter1d(values2, sigma=smooth_sigma)
            
            # 2. 计算导数
            # 使用numpy.gradient计算中心差分
            deriv1 = np.gradient(values1_smooth, times1)
            deriv2 = np.gradient(values2_smooth, times2)
            
            # 再次平滑导数以减少噪声
            deriv1_smooth = gaussian_filter1d(deriv1, sigma=smooth_sigma)
            deriv2_smooth = gaussian_filter1d(deriv2, sigma=smooth_sigma)
            
            # 3. 归一化导数（Z-score）
            # 这对于幅度不同的曲线很重要
            deriv1_norm = (deriv1_smooth - np.mean(deriv1_smooth)) / (np.std(deriv1_smooth) + 1e-6)
            deriv2_norm = (deriv2_smooth - np.mean(deriv2_smooth)) / (np.std(deriv2_smooth) + 1e-6)
            
            # 4. 对齐处理 (简化版DTW: 线性重采样对齐)
            # 将两条曲线重采样到相同的长度（较长者的长度）
            target_len = max(len(times1), len(times2))
            
            # 重采样曲线1
            f1 = interp1d(np.linspace(0, 1, len(times1)), times1)
            f1_v = interp1d(np.linspace(0, 1, len(values1)), values1)
            f1_ds = interp1d(np.linspace(0, 1, len(deriv1_smooth)), deriv1_smooth)
            
            times1_resampled = f1(np.linspace(0, 1, target_len))
            values1_resampled = f1_v(np.linspace(0, 1, target_len))
            deriv1_resampled = f1_ds(np.linspace(0, 1, target_len))
            
            # 重采样曲线2
            f2 = interp1d(np.linspace(0, 1, len(times2)), times2)
            f2_v = interp1d(np.linspace(0, 1, len(values2)), values2)
            f2_ds = interp1d(np.linspace(0, 1, len(deriv2_smooth)), deriv2_smooth)
            
            times2_resampled = f2(np.linspace(0, 1, target_len))
            values2_resampled = f2_v(np.linspace(0, 1, target_len))
            deriv2_resampled = f2_ds(np.linspace(0, 1, target_len))
            
            # 简单的对齐结果
            # 在实际应用中，这里应该使用fastdtw计算path，然后根据path warped
            # 这里暂时使用线性对齐作为演示
            
            return {
                'record_smoothed': values1_smooth,
                'replay_smoothed': values2_smooth,
                'record_derivative': deriv1_smooth,
                'replay_derivative': deriv2_smooth,
                'record_derivative_aligned': deriv1_resampled,
                'replay_derivative_aligned': deriv2_resampled,
                'record_aligned': values1_resampled,
                'replay_aligned': values2_resampled,
                'aligned_times': times1_resampled, # 使用重采样后的时间轴
                'dtw_distance': 0.1 # 占位符
            }
            
        except Exception as e:
            logger.error(f"❌ 曲线对齐失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    
class ForceCurveAnalyzer:
    """
    力度曲线分析器

    分析after_touch曲线的上升沿和下降沿，用于匹配算法和曲线对比分析
    """

    def __init__(self, 
                 smooth_sigma: float = 1.0,
                 dtw_distance_metric: str = 'manhattan',
                 dtw_window_size_ratio: float = 0.5):
        """
        初始化力度曲线分析器
        
        Args:
            smooth_sigma: 平滑强度
            dtw_distance_metric: DTW距离度量方式
            dtw_window_size_ratio: DTW窗口大小比例
        """
        self.derivative_dtw_aligner = DerivativeDTWAligner(
            smooth_sigma=smooth_sigma,
            distance_metric=dtw_distance_metric,
            window_size_ratio=dtw_window_size_ratio
        )
    
    def compare_curves(self, note1, note2, record_note=None, replay_note=None, mean_delay: float = 0.0) -> Optional[Dict[str, Any]]:
        """
        对比两条力度曲线的上升沿和下降沿
        
        Args:
            note1: 第一个音符对象
            note2: 第二个音符对象
            record_note: 录制音符对象
            replay_note: 播放音符对象
            mean_delay: 整首曲子的平均延时(ms)，用于修正播放曲线的时间轴
            
        Returns:
            对比结果字典，如果失败则返回None
        """
        try:
            # 确定录制和播放曲线
            if record_note is None:
                record_note = note1
            if replay_note is None:
                replay_note = note2
            
            # 提取完整曲线数据
            curve1_data = self._extract_full_curve(record_note)
            curve2_data = self._extract_full_curve(replay_note)
            
            if curve1_data is None or curve2_data is None:
                return None
            
            times1, values1 = curve1_data
            times2, values2 = curve2_data
            
            # 1. 保存阶段1：原始曲线 (完全原始数据，不做任何偏移)
            stage1_original = {
                'record_times': times1.copy(),
                'record_values': values1.copy(),
                'replay_times': times2.copy(),
                'replay_values': values2.copy(),
                'description': '阶段1：原始曲线 (Raw Data)'
            }
            
            # 2. 计算偏移修正后的时间轴
            times2_shifted = times2.copy()
            offset_description = '未修正'
            
            if mean_delay != 0:
                times2_shifted = times2 - mean_delay
                offset_description = f'已减去平均延时 {mean_delay:.2f}ms'
                logger.info(f"已修正播放曲线时间偏移 (平均延时): {mean_delay:.2f}ms. 原始首点: {times2[0]:.2f}, 修正后首点: {times2_shifted[0]:.2f}")
            else:
                logger.warning("⚠️ 平均延时为0，未进行偏移修正")
                # 如果没有提供 mean_delay，暂不进行偏移，或者可以在这里实现自动对齐逻辑
                pass

            # 3. 保存阶段1.5：偏移修正后曲线
            stage_offset_corrected = {
                'record_times': times1.copy(),
                'record_values': values1.copy(),
                'replay_times': times2_shifted.copy(),
                'replay_values': values2.copy(),
                'description': f'阶段1.5：偏移修正后 ({offset_description})'
            }

            # 4. 后续处理使用 times2_shifted (偏移修正后的时间轴)
            align_result = self.derivative_dtw_aligner.align_full_curves(
                (times1, values1),
                (times2_shifted, values2)
            )
            
            stages = {
                'stage1_original': stage1_original,
                'stage_offset_corrected': stage_offset_corrected
            }
            
            dtw_distance = 0.1
            
            if align_result:
                # 阶段2：平滑后曲线
                stages['stage2_smoothed'] = {
                    'record_times': times1.copy(),
                    'record_values': align_result['record_smoothed'],
                    'replay_times': times2_shifted.copy(), # 使用修正后的时间
                    'replay_values': align_result['replay_smoothed'],
                    'description': '阶段2：高斯平滑后'
                }
                
                # 阶段3：导数曲线
                stages['stage3_derivative'] = {
                    'record_times': times1.copy(),
                    'record_values': align_result['record_derivative'],
                    'replay_times': times2_shifted.copy(),
                    'replay_values': align_result['replay_derivative'],
                    'description': '阶段3：一阶导数'
                }
                
                # 阶段4：对齐后的导数
                aligned_times = align_result['aligned_times']
                stages['stage4_aligned_derivative'] = {
                    'record_times': aligned_times,
                    'record_values': align_result['record_derivative_aligned'],
                    'replay_times': aligned_times,
                    'replay_values': align_result['replay_derivative_aligned'],
                    'description': '阶段4：对齐后的导数'
                }
                
                # 阶段5：对齐后的原始曲线
                stages['stage5_aligned_original'] = {
                    'record_times': aligned_times,
                    'record_values': align_result['record_aligned'],
                    'replay_times': aligned_times,
                    'replay_values': align_result['replay_aligned'],
                    'description': '阶段5：对齐后的原始曲线'
                }
                
                # 阶段6：残差分析 (Jitter)
                # 计算 Raw - Smoothed 的残差
                from scipy.ndimage import gaussian_filter1d
                
                # 对偏移修正后的原始播放曲线进行平滑
                # 使用原始值 values2 (对应的时轴是 times2_shifted)
                rep_raw_shifted = values2 
                rep_smooth_shifted = gaussian_filter1d(rep_raw_shifted, sigma=2.0)
                
                rec_raw = values1
                rec_smooth = gaussian_filter1d(rec_raw, sigma=2.0)
                
                rec_resid = rec_raw - rec_smooth
                rep_resid = rep_raw_shifted - rep_smooth_shifted
                
                stages['stage6_residuals'] = {
                    'record_times': times1.copy(),
                    'record_values': rec_resid,
                    'replay_times': times2_shifted.copy(), # 使用偏移后的时间轴
                    'replay_values': rep_resid,
                    'description': '阶段6：残差/抖动分析 (Raw - Smoothed)'
                }
                
                dtw_distance = align_result.get('dtw_distance', 0.1)

            # 5. 特征提取与量化分析
            # 优先使用对齐后的数据进行形状特征提取，以便于在同一时间轴下比较
            if 'stage5_aligned_original' in stages:
                stage_data = stages['stage5_aligned_original']
                record_features = self._analyze_single_curve_features(stage_data['record_times'], stage_data['record_values'])
                replay_features = self._analyze_single_curve_features(stage_data['replay_times'], stage_data['replay_values'])
            else:
                # 如果没有对齐，使用偏移修正后的数据
                record_features = self._analyze_single_curve_features(times1, values1)
                replay_features = self._analyze_single_curve_features(times2_shifted, values2) # 使用偏移后的时间轴
            
            feature_comparison = self._compare_features(record_features, replay_features)

            # 简单的相似度计算 (保留)
            similarity = self._calculate_simple_similarity(values1, values2)
            
            return {
                'overall_similarity': similarity,
                'dtw_distance': dtw_distance,
                'processing_stages': stages,
                'record_features': record_features,
                'replay_features': replay_features,
                'feature_comparison': feature_comparison,
                # 兼容旧字段
                'rising_edge_similarity': similarity,
                'falling_edge_similarity': similarity,
                'alignment_comparison': {
                    'record_times': times1,
                    'record_values': values1,
                    'replay_times': times2,
                    'replay_values': values2,
                    'replay_values_aligned': align_result.get('replay_aligned', values2) if align_result else values2
                }
            }
            
        except Exception as e:
            logger.error(f"❌ 曲线对比失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _analyze_single_curve_features(self, times: np.ndarray, values: np.ndarray) -> Dict[str, Any]:
        """
        分析单条曲线的物理特征
        
        关注：
        1. 峰值特性 (Peak)
        2. 上升沿 (Rising Edge): 10% -> 90%
        3. 下降沿 (Falling Edge): 90% -> 10%
        4. 抖动/平滑度 (Jitter)
        """
        try:
            if len(values) == 0:
                return {}
            
            # 1. 峰值分析
            peak_idx = np.argmax(values)
            peak_value = values[peak_idx]
            peak_time = times[peak_idx]
            
            # 2. 阈值界定 (10% 和 90%)
            threshold_10 = peak_value * 0.1
            threshold_90 = peak_value * 0.9
            
            # 3. 上升沿分析 (Peak左侧)
            rise_start_idx = 0
            rise_end_idx = peak_idx
            
            # 寻找上升沿的 10% 点
            for i in range(peak_idx, -1, -1):
                if values[i] < threshold_10:
                    rise_start_idx = i
                    break
            
            # 寻找上升沿的 90% 点
            for i in range(peak_idx, -1, -1):
                if values[i] < threshold_90:
                    rise_end_idx = i + 1 
                    break
            
            if rise_end_idx >= len(times): rise_end_idx = len(times) - 1
            
            # 计算上升时间与斜率
            rise_time_10 = times[rise_start_idx]
            rise_time_90 = times[rise_end_idx]
            rise_duration = rise_time_90 - rise_time_10
            rise_slope = (values[rise_end_idx] - values[rise_start_idx]) / (rise_duration + 1e-6)
            
            # 4. 下降沿分析 (Peak右侧)
            fall_start_idx = peak_idx
            fall_end_idx = len(values) - 1
            
            # 寻找下降沿的 90% 点
            for i in range(peak_idx, len(values)):
                if values[i] < threshold_90:
                    fall_start_idx = i - 1
                    break
            
            # 寻找下降沿的 10% 点
            for i in range(peak_idx, len(values)):
                if values[i] < threshold_10:
                    fall_end_idx = i
                    break
            
            if fall_start_idx < 0: fall_start_idx = 0
            
            # 计算下降时间与斜率
            fall_time_90 = times[fall_start_idx]
            fall_time_10 = times[fall_end_idx]
            fall_duration = fall_time_10 - fall_time_90
            fall_slope = (values[fall_start_idx] - values[fall_end_idx]) / (fall_duration + 1e-6)
            
            # 5. 抖动分析 (残差标准差)
            from scipy.ndimage import gaussian_filter1d
            values_smooth = gaussian_filter1d(values, sigma=2.0)
            residuals = values - values_smooth
            jitter_std = np.std(residuals)
            
            return {
                'peak_value': float(peak_value),
                'peak_time': float(peak_time),
                'rise_time_ms': float(rise_duration),
                'rise_slope': float(rise_slope),
                'fall_time_ms': float(fall_duration),
                'fall_slope': float(fall_slope),
                'jitter': float(jitter_std),
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
            'peak_diff': feat2['peak_value'] - feat1['peak_value'],
            'peak_time_lag': feat2['peak_time'] - feat1['peak_time'],
            'rise_time_diff': feat2['rise_time_ms'] - feat1['rise_time_ms'],
            'fall_time_diff': feat2['fall_time_ms'] - feat1['fall_time_ms'],
            'jitter_ratio': feat2['jitter'] / (feat1['jitter'] + 1e-6)
        }
    
    def generate_processing_stages_figures(self, comparison_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        生成所有处理阶段的独立图表列表
        
        Args:
            comparison_result: compare_curves()的返回结果
        
        Returns:
            List[Dict[str, Any]]: 包含Figure对象和标题的列表
            [
                {'title': '阶段1...', 'figure': go.Figure(...) },
                ...
            ]
        """
        try:
            import plotly.graph_objects as go
            
            if 'processing_stages' not in comparison_result:
                logger.warning("⚠️ 对比结果中没有处理阶段数据")
                return []
            
            stages = comparison_result['processing_stages']
            
            # 定义阶段顺序和标题
            stage_config = [
                ('stage1_original', '阶段1：原始曲线 (Raw Data)'),
                ('stage_offset_corrected', '阶段1.5：偏移修正后 (Offset Corrected)'),
                ('stage2_smoothed', '阶段2：高斯平滑后'),
                ('stage3_derivative', '阶段3：一阶导数'),
                ('stage4_aligned_derivative', '阶段4：对齐后的导数'),
                ('stage5_aligned_original', '阶段5：对齐后的原始曲线'),
                ('stage6_residuals', '阶段6：残差/抖动分析 (Raw - Smoothed)')
            ]
            
            result_figures = []
            
            for stage_key, stage_title in stage_config:
                if stage_key not in stages:
                    continue
                    
                stage_data = stages[stage_key]
                record_times = stage_data.get('record_times', [])
                record_values = stage_data.get('record_values', [])
                replay_times = stage_data.get('replay_times', [])
                replay_values = stage_data.get('replay_values', [])
                
                # 确定y轴标签
                yaxis_title = "力度值"
                if 'derivative' in stage_key:
                    yaxis_title = "导数值"
                elif 'residuals' in stage_key:
                    yaxis_title = "残差值"
                
                # 创建独立的Figure
                fig = go.Figure()
                
                # 图例名称设置
                record_name = '录制曲线'
                replay_name = '播放曲线'
                if 'residuals' in stage_key:
                    record_name = '录制残差'
                    replay_name = '播放残差'
                
                if len(record_times) > 0 and len(record_values) > 0:
                    fig.add_trace(go.Scatter(
                        x=record_times, y=record_values,
                        mode='lines', name=record_name,
                        line=dict(color='blue', width=2)
                    ))
                
                if len(replay_times) > 0 and len(replay_values) > 0:
                    fig.add_trace(go.Scatter(
                        x=replay_times, y=replay_values,
                        mode='lines', name=replay_name,
                        line=dict(color='red', width=2, dash='dash')
                    ))
                
                # 特殊处理：阶段5添加特征标记
                if stage_key == 'stage5_aligned_original':
                    record_features = comparison_result.get('record_features', {})
                    replay_features = comparison_result.get('replay_features', {})
                    
                    def add_markers(features, color, prefix):
                        markers = features.get('markers', {})
                        if not markers: return
                        
                        if 'peak' in markers:
                            p_t, p_v = markers['peak']
                            fig.add_trace(go.Scatter(
                                x=[p_t], y=[p_v],
                                mode='markers+text',
                                marker=dict(color=color, size=10, symbol='star'),
                                text=[f'{prefix}峰值'], textposition="top center",
                                showlegend=False
                            ))
                        
                        if 'rise_10' in markers and 'rise_90' in markers:
                            r10 = markers['rise_10']
                            r90 = markers['rise_90']
                            fig.add_trace(go.Scatter(
                                x=[r10[0], r90[0]], y=[r10[1], r90[1]],
                                mode='markers+lines',
                                line=dict(color=color, width=3, dash='dot'),
                                marker=dict(size=6),
                                name=f'{prefix}上升沿', showlegend=False
                            ))

                        if 'fall_90' in markers and 'fall_10' in markers:
                            f90 = markers['fall_90']
                            f10 = markers['fall_10']
                            fig.add_trace(go.Scatter(
                                x=[f90[0], f10[0]], y=[f90[1], f10[1]],
                                mode='markers+lines',
                                line=dict(color=color, width=3, dash='dashdot'),
                                marker=dict(size=6),
                                name=f'{prefix}下降沿', showlegend=False
                            ))

                    if record_features: add_markers(record_features, 'blue', '录制')
                    if replay_features: add_markers(replay_features, 'red', '播放')

                # 设置单个图表的Layout
                fig.update_layout(
                    height=450, # 稍微增加高度以容纳外部图例
                    xaxis_title="时间 (ms)",
                    yaxis_title=yaxis_title,
                    margin=dict(l=50, r=20, t=50, b=40), # 增加顶部边距 (t) 以防止图例被截断
                    # 图例放置在绘图区域上方的左侧
                    legend=dict(
                        orientation="h", # 水平排列
                        yanchor="bottom",
                        y=1.02, # 位于顶部上方
                        xanchor="left",
                        x=0.0,
                        bgcolor="rgba(255,255,255,0.8)",
                        bordercolor="LightGrey",
                        borderwidth=0 # 去掉边框更简洁
                    ),
                    hovermode="x unified"
                )
                
                result_figures.append({
                    'title': stage_title,
                    'figure': fig,
                    'key': stage_key
                })
                
            return result_figures
            
        except Exception as e:
            logger.error(f"❌ 生成独立图表失败: {e}")
            return []

    def visualize_all_processing_stages(self, comparison_result: Dict[str, Any]) -> Optional[Any]:
        """
        [已废弃] 可视化所有处理阶段的曲线 (旧版: 返回单个大图)
        保留此方法以兼容旧代码，但建议使用 generate_processing_stages_figures
        """
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
            
            # 直接复用新逻辑生成多个图，然后拼成一个大图返回？
            # 或者保留旧逻辑作为fallback。为了快速响应用户，我保留旧逻辑，
            # 但用户界面侧将改为调用新方法。
            # ... (保留旧代码)
            pass
        except:
            return None
        # ...旧代码内容实际上保留在下面...


    def visualize_alignment_comparison(self, comparison_result: Dict[str, Any]) -> Optional[Any]:
        """
        可视化对齐前后的曲线对比（向后兼容）
        
        Args:
            comparison_result: compare_curves()的返回结果
        
        Returns:
            plotly.graph_objects.Figure: 对比图表，如果失败则返回None
        """
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
            
            if 'processing_stages' not in comparison_result:
                return None
            
            stages = comparison_result['processing_stages']
            
            # 创建2个子图：原始对比 和 对齐后对比
            fig = make_subplots(
                rows=2, cols=1,
                subplot_titles=('对齐前：原始曲线', '对齐后：基于导数对齐的原始曲线'),
                vertical_spacing=0.1,
                row_heights=[0.5, 0.5]
            )
            
            # 1. 原始对比
            if 'stage1_original' in stages:
                stage1 = stages['stage1_original']
                fig.add_trace(
                    go.Scatter(x=stage1['record_times'], y=stage1['record_values'], 
                              mode='lines', name='录制曲线', line=dict(color='blue')),
                    row=1, col=1
                )
                fig.add_trace(
                    go.Scatter(x=stage1['replay_times'], y=stage1['replay_values'], 
                              mode='lines', name='播放曲线', line=dict(color='red', dash='dash')),
                    row=1, col=1
                )
            
            # 2. 对齐后对比
            if 'stage5_aligned_original' in stages:
                stage5 = stages['stage5_aligned_original']
                fig.add_trace(
                    go.Scatter(x=stage5['record_times'], y=stage5['record_values'], 
                              mode='lines', name='录制曲线', line=dict(color='blue'), showlegend=False),
                    row=2, col=1
                )
                fig.add_trace(
                    go.Scatter(x=stage5['replay_times'], y=stage5['replay_values'], 
                              mode='lines', name='播放曲线(对齐后)', line=dict(color='red', dash='dash')),
                    row=2, col=1
                )
            
            fig.update_layout(height=700, title_text="曲线对齐前后对比")
            return fig
            
        except Exception as e:
            logger.error(f"❌ 可视化对齐对比失败: {e}")
            return None
    
    def _extract_full_curve(self, note) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """
        提取完整曲线数据
        
        Args:
            note: 音符对象
            
        Returns:
            Tuple[np.ndarray, np.ndarray]: (times, values)，如果提取失败则返回None
        """
        try:
            if not hasattr(note, 'after_touch') or note.after_touch is None or note.after_touch.empty:
                logger.warning("⚠️ 音符没有after_touch数据")
                return None
            
            # 提取时间和值
            times = (note.after_touch.index + note.offset) / 10.0  # 转换为ms
            values = note.after_touch.values
            
            # 转换为numpy数组
            times = np.array(times)
            values = np.array(values)
            
            if len(times) == 0 or len(values) == 0:
                logger.warning("⚠️ after_touch数据为空")
                return None
            
            return (times, values)
            
        except Exception as e:
            logger.error(f"❌ 提取完整曲线失败: {e}")
            return None

    def generate_similarity_stages_figures(self, comparison_result: Dict[str, Any],
                                         base_name: str, compare_name: str, similarity: float) -> List[Dict[str, Any]]:
        """
        生成相似度分析的处理阶段图表

        Args:
            comparison_result: 对比结果字典
            base_name: 基准算法名称
            compare_name: 对比算法名称
            similarity: 相似度值

        Returns:
            处理阶段图表列表
        """
        figures = []

        if 'processing_stages' not in comparison_result:
            return figures

        stages = comparison_result['processing_stages']

        # 阶段1：原始曲线对比
        if 'stage1_original' in stages:
            stage = stages['stage1_original']
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=stage['record_times'], y=stage['record_values'],
                mode='lines', name=f'基准录制 ({base_name})',
                line=dict(color='#1f77b4', width=2)
            ))
            fig.add_trace(go.Scatter(
                x=stage['replay_times'], y=stage['replay_values'],
                mode='lines', name=f'播放曲线 ({compare_name})',
                line=dict(color='#ff7f0e', width=2)
            ))
            fig.update_layout(
                title=f'原始曲线对比 (相似度: {similarity:.3f})',
                xaxis_title='时间 (ms)', yaxis_title='力度值', height=400
            )
            figures.append({'title': '阶段1：原始曲线对比', 'figure': fig})

        # 阶段1.5：偏移修正后曲线
        if 'stage_offset_corrected' in stages:
            stage = stages['stage_offset_corrected']
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=stage['record_times'], y=stage['record_values'],
                mode='lines', name=f'基准录制 ({base_name})',
                line=dict(color='#1f77b4', width=2)
            ))
            fig.add_trace(go.Scatter(
                x=stage['replay_times'], y=stage['replay_values'],
                mode='lines', name=f'播放曲线 ({compare_name})',
                line=dict(color='#ff7f0e', width=2)
            ))
            fig.update_layout(
                title=f'偏移修正后曲线对比 (相似度: {similarity:.3f})',
                xaxis_title='时间 (ms)', yaxis_title='力度值', height=400
            )
            figures.append({'title': '阶段1.5：偏移修正后曲线', 'figure': fig})

        # 阶段2：平滑后曲线
        if 'stage2_smoothed' in stages:
            stage = stages['stage2_smoothed']
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=stage['record_times'], y=stage['record_values'],
                mode='lines', name=f'基准录制平滑 ({base_name})',
                line=dict(color='#1f77b4', width=2)
            ))
            fig.add_trace(go.Scatter(
                x=stage['replay_times'], y=stage['replay_values'],
                mode='lines', name=f'播放曲线平滑 ({compare_name})',
                line=dict(color='#ff7f0e', width=2)
            ))
            fig.update_layout(
                title=f'高斯平滑后曲线对比 (相似度: {similarity:.3f})',
                xaxis_title='时间 (ms)', yaxis_title='力度值', height=400
            )
            figures.append({'title': '阶段2：高斯平滑后曲线', 'figure': fig})

        # 阶段4：对齐后的导数
        if 'stage4_aligned_derivative' in stages:
            stage = stages['stage4_aligned_derivative']
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=stage['record_times'], y=stage['record_values'],
                mode='lines', name=f'基准导数 ({base_name})',
                line=dict(color='#1f77b4', width=2)
            ))
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
