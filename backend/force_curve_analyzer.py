#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
力度曲线分析器 - 分析after_touch曲线的上升沿和下降沿

用于匹配算法和曲线对比分析

核心功能：
1. 基于导数的DTW对齐：对曲线的斜率（导数）进行DTW对齐，而非原始值
2. 上升沿和下降沿提取：从峰值点分割曲线
3. 曲线相似度计算：基于对齐后的曲线计算相似度
"""

from typing import List, Tuple, Dict, Any, Optional
import numpy as np
from scipy.interpolate import interp1d
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks
from dtw import dtw
from utils.logger import Logger

logger = Logger.get_logger()


class DerivativeDTWAligner:
    """
    基于导数的DTW对齐器
    
    核心思想：
    - 不直接对齐原始曲线值，而是对齐曲线的导数（斜率）
    - 导数更能反映曲线的变化趋势，符合"上升沿"和"下降沿"的本质
    - 对小幅抖动更鲁棒，因为小幅抖动在导数上的影响相对较小
    
    对齐流程：
    1. 平滑处理：使用高斯滤波去除噪声（避免导数放大噪声）
    2. 计算导数：计算曲线的斜率（变化率）
    3. DTW对齐：对导数序列进行DTW对齐，找到最优对齐路径
    4. 重新采样：根据对齐路径重新采样原始曲线，使两条曲线对齐
    5. 相似度计算：基于对齐后的曲线计算相似度
    """
    
    def __init__(self,
                 smooth_sigma: float = 1.0,
                 distance_metric: str = 'manhattan',
                 window_size_ratio: float = 0.5):
        """
        初始化基于导数的DTW对齐器
        
        Args:
            smooth_sigma: 高斯平滑参数（标准差），用于减少抖动影响
                          - 值越大，平滑程度越高，但可能丢失细节
                          - 0表示不平滑（不推荐，因为导数会放大噪声）
                          - 建议值：1.0-2.0
            distance_metric: DTW距离度量方式
                            - 'euclidean': 欧式距离（默认）
                            - 'manhattan': 曼哈顿距离（L1距离，对抖动更鲁棒，推荐）
                            - 'chebyshev': 切比雪夫距离（关注最大差异）
            window_size_ratio: DTW窗口大小比例（相对于序列长度）
                              - 限制对齐范围，避免过度扭曲
                              - 0.5表示窗口大小为序列长度的50%
                              - 1.0表示无限制（可能导致过度扭曲）
        """
        self.smooth_sigma = smooth_sigma
        self.distance_metric = distance_metric
        self.window_size_ratio = window_size_ratio
    
    def align_full_curves(self,
                         curve1: Tuple[np.ndarray, np.ndarray],
                         curve2: Tuple[np.ndarray, np.ndarray]) -> Optional[Dict[str, Any]]:
        """
        使用基于导数的DTW对齐两条完整曲线
        
        这是改进后的方法：先对齐完整曲线，建立整体对应关系，然后再提取边缘。
        这样可以确保峰值点对应，边缘提取更准确。
        
        Args:
            curve1: (times1, values1) - 第一条完整曲线的时间序列和值序列
            curve2: (times2, values2) - 第二条完整曲线的时间序列和值序列
        
        Returns:
            Dict[str, Any]: 对齐结果，包含：
                - aligned_times: 对齐后的时间点数组（归一化到[0,1]）
                - aligned_values1: 对齐后的第一条曲线的值
                - aligned_values2: 对齐后的第二条曲线的值
                - alignment_path: DTW对齐路径 [(i, j), ...]
                - dtw_distance: DTW距离（越小表示越相似）
                - peak_indices1: 第一条曲线在对齐后的峰值索引
                - peak_indices2: 第二条曲线在对齐后的峰值索引
                如果对齐失败则返回None
        """
        try:
            times1, values1 = curve1
            times2, values2 = curve2
            
            # 1. 数据验证
            if len(times1) < 2 or len(times2) < 2:
                logger.warning("⚠️ 曲线数据点不足（少于2个点），无法计算导数")
                return None
            
            if len(times1) != len(values1) or len(times2) != len(values2):
                logger.warning("⚠️ 时间和值数组长度不匹配")
                return None
            
            # 2. 平滑处理（关键步骤：避免导数放大噪声）
            #    注意：只对用于计算导数的值进行平滑，最终输出使用原始值
            if self.smooth_sigma > 0:
                values1_smooth = gaussian_filter1d(values1, sigma=self.smooth_sigma)
                values2_smooth = gaussian_filter1d(values2, sigma=self.smooth_sigma)
            else:
                values1_smooth = values1.copy()
                values2_smooth = values2.copy()
                logger.warning("⚠️ 未启用平滑，导数可能被噪声放大")
            
            # 3. 计算导数（斜率）- 使用平滑后的值计算导数，但保持原始值用于最终输出
            derivatives1 = self._compute_derivative(times1, values1_smooth)
            derivatives2 = self._compute_derivative(times2, values2_smooth)
            
            if derivatives1 is None or derivatives2 is None:
                logger.warning("⚠️ 计算导数失败")
                return None
            
            # 4. 归一化导数（消除绝对幅度的差异，只关注变化趋势）
            derivatives1_norm = self._normalize_derivative(derivatives1)
            derivatives2_norm = self._normalize_derivative(derivatives2)
            
            # 5. 执行DTW对齐（对导数序列进行对齐）
            dtw_result = self._perform_dtw_on_derivatives(
                derivatives1_norm, derivatives2_norm
            )
            
            if dtw_result is None:
                logger.warning("⚠️ DTW对齐失败")
                return None
            
            alignment_path = dtw_result['alignment_path']
            dtw_distance = dtw_result['dtw_distance']
            
            # 6. 根据对齐路径重新采样原始曲线
            # 使用保守的对齐策略，尽量保持原始曲线形状
            # 重要：使用原始值（values1, values2）而不是平滑后的值，以保持波峰和波谷
            aligned_result = self._resample_by_alignment_path_conservative(
                times1, values1,  # 使用原始值，保持波峰和波谷
                times2, values2,  # 使用原始值，保持波峰和波谷
                alignment_path
            )
            
            if aligned_result is None:
                logger.warning("⚠️ 保守重新采样失败，无法继续分析")
                return None
            
            # 7. 在对齐后的曲线上找到峰值点
            aligned_values1 = aligned_result['aligned_values1']
            aligned_values2 = aligned_result['aligned_values2']
            
            # 找到主要峰值索引（在对齐后的曲线上，支持多个峰值）
            peak_idx1 = self._find_main_peak(aligned_values1)
            peak_idx2 = self._find_main_peak(aligned_values2)
            
            # 归一化原始时间到[0,1]，便于对比
            if times1[-1] != times1[0]:
                norm_times1 = (times1 - times1[0]) / (times1[-1] - times1[0])
            else:
                norm_times1 = np.zeros_like(times1)
            
            if times2[-1] != times2[0]:
                norm_times2 = (times2 - times2[0]) / (times2[-1] - times2[0])
            else:
                norm_times2 = np.zeros_like(times2)
            
            return {
                # 对齐后的数据
                'aligned_times': aligned_result['aligned_times'],
                'aligned_values1': aligned_values1,
                'aligned_values2': aligned_values2,
                
                # 对齐前的数据（归一化时间，便于对比）
                'before_alignment': {
                    'times1': norm_times1,
                    'values1': values1_smooth,
                    'times2': norm_times2,
                    'values2': values2_smooth,
                    'original_times1': times1,  # 原始时间（ms）
                    'original_times2': times2   # 原始时间（ms）
                },
                
                # 对齐信息
                'alignment_path': alignment_path,
                'dtw_distance': dtw_distance,
                
                # 峰值信息
                'peak_indices1': peak_idx1,
                'peak_indices2': peak_idx2,
                'original_peak_idx1': self._find_main_peak(values1),
                'original_peak_idx2': self._find_main_peak(values2),
                'original_peak_time1': times1[self._find_main_peak(values1)],
                'original_peak_time2': times2[self._find_main_peak(values2)],
                
                # 导数信息（用于调试）
                'derivatives1': derivatives1,
                'derivatives2': derivatives2,
                'derivatives1_norm': derivatives1_norm,
                'derivatives2_norm': derivatives2_norm
            }
            
        except Exception as e:
            logger.error(f"❌ 基于导数的完整曲线DTW对齐失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def align_edges(self,
                    edge1: Tuple[np.ndarray, np.ndarray],
                    edge2: Tuple[np.ndarray, np.ndarray]) -> Optional[Dict[str, Any]]:
        """
        使用基于导数的DTW对齐两条边缘（上升沿或下降沿）
        
        Args:
            edge1: (times1, values1) - 第一条边缘的时间序列和值序列
            edge2: (times2, values2) - 第二条边缘的时间序列和值序列
        
        Returns:
            Dict[str, Any]: 对齐结果，包含：
                - aligned_times: 对齐后的时间点数组（归一化到[0,1]）
                - aligned_values1: 对齐后的第一条边缘的值
                - aligned_values2: 对齐后的第二条边缘的值
                - alignment_path: DTW对齐路径 [(i, j), ...]
                - dtw_distance: DTW距离（越小表示越相似）
                - derivatives1: 第一条边缘的导数序列
                - derivatives2: 第二条边缘的导数序列
                如果对齐失败则返回None
        """
        try:
            times1, values1 = edge1
            times2, values2 = edge2
            
            # 1. 数据验证
            if len(times1) < 2 or len(times2) < 2:
                logger.warning("⚠️ 边缘数据点不足（少于2个点），无法计算导数")
                return None
            
            if len(times1) != len(values1) or len(times2) != len(values2):
                logger.warning("⚠️ 时间和值数组长度不匹配")
                return None
            
            # 2. 平滑处理（关键步骤：避免导数放大噪声）
            #    在计算导数之前先平滑，可以减少噪声对导数的影响
            if self.smooth_sigma > 0:
                values1_smooth = gaussian_filter1d(values1, sigma=self.smooth_sigma)
                values2_smooth = gaussian_filter1d(values2, sigma=self.smooth_sigma)
            else:
                values1_smooth = values1.copy()
                values2_smooth = values2.copy()
                logger.warning("⚠️ 未启用平滑，导数可能被噪声放大")
            
            # 3. 计算导数（斜率）
            #    使用np.gradient计算数值导数，它使用中心差分法，比np.diff更准确
            #    导数反映了曲线的变化率，这正是"上升沿"和"下降沿"的本质特征
            derivatives1 = self._compute_derivative(times1, values1_smooth)
            derivatives2 = self._compute_derivative(times2, values2_smooth)
            
            if derivatives1 is None or derivatives2 is None:
                logger.warning("⚠️ 计算导数失败")
                return None
            
            # 4. 归一化导数（消除绝对幅度的差异，只关注变化趋势）
            #    归一化到[-1, 1]范围，使得上升沿和下降沿的导数可以统一处理
            derivatives1_norm = self._normalize_derivative(derivatives1)
            derivatives2_norm = self._normalize_derivative(derivatives2)
            
            # 5. 执行DTW对齐（对导数序列进行对齐）
            dtw_result = self._perform_dtw_on_derivatives(
                derivatives1_norm, derivatives2_norm
            )
            
            if dtw_result is None:
                logger.warning("⚠️ DTW对齐失败")
                return None
            
            alignment_path = dtw_result['alignment_path']
            dtw_distance = dtw_result['dtw_distance']
            
            # 6. 根据对齐路径重新采样原始曲线
            #    使用对齐路径将两条曲线映射到统一的时间轴上
            aligned_result = self._resample_by_alignment_path(
                times1, values1_smooth,
                times2, values2_smooth,
                alignment_path
            )
            
            if aligned_result is None:
                logger.warning("⚠️ 根据对齐路径重新采样失败")
                return None
            
            return {
                'aligned_times': aligned_result['aligned_times'],
                'aligned_values1': aligned_result['aligned_values1'],
                'aligned_values2': aligned_result['aligned_values2'],
                'alignment_path': alignment_path,
                'dtw_distance': dtw_distance,
                'derivatives1': derivatives1,
                'derivatives2': derivatives2,
                'derivatives1_norm': derivatives1_norm,
                'derivatives2_norm': derivatives2_norm
            }
            
        except Exception as e:
            logger.error(f"❌ 基于导数的DTW对齐失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def _compute_derivative(self,
                          times: np.ndarray,
                          values: np.ndarray) -> Optional[np.ndarray]:
        """
        计算曲线的导数（斜率）
        
        使用np.gradient计算数值导数：
        - 对于内部点：使用中心差分法 (f(x+h) - f(x-h)) / (2h)
        - 对于边界点：使用前向/后向差分法
        - 这种方法比np.diff更准确，因为它考虑了时间间隔的不均匀性
        
        Args:
            times: 时间序列（ms）
            values: 值序列
        
        Returns:
            np.ndarray: 导数序列（单位：值/ms），如果计算失败则返回None
        """
        try:
            if len(times) < 2 or len(values) < 2:
                return None
            
            # 使用np.gradient计算导数
            # np.gradient会自动处理时间间隔的不均匀性
            # 返回的导数单位是：值的变化量 / 时间的变化量
            derivatives = np.gradient(values, times)
            
            # 检查是否有无效值
            if np.any(~np.isfinite(derivatives)):
                logger.warning("⚠️ 导数计算产生NaN或Inf值，尝试使用均匀时间间隔")
                # 如果时间间隔不均匀导致问题，使用均匀时间间隔
                dt = (times[-1] - times[0]) / (len(times) - 1) if len(times) > 1 else 1.0
                derivatives = np.gradient(values, dt)
            
            return derivatives
            
        except Exception as e:
            logger.error(f"❌ 计算导数失败: {e}")
            return None
    
    def _normalize_derivative(self, derivatives: np.ndarray) -> np.ndarray:
        """
        归一化导数序列
        
        目的：
        - 消除绝对幅度的差异，只关注变化趋势
        - 将导数归一化到[-1, 1]范围，使得上升沿和下降沿可以统一处理
        
        方法：
        - 如果导数全为0，返回0数组
        - 否则，使用最大绝对值进行归一化：derivative / max(|derivative|)
        
        Args:
            derivatives: 原始导数序列
        
        Returns:
            np.ndarray: 归一化后的导数序列（范围：[-1, 1]）
        """
        max_abs_derivative = np.max(np.abs(derivatives))
        
        if max_abs_derivative == 0:
            # 如果导数全为0（平坦曲线），返回0数组
            return np.zeros_like(derivatives)
        
        # 归一化到[-1, 1]范围
        normalized = derivatives / max_abs_derivative
        
        return normalized
    
    def _perform_dtw_on_derivatives(self,
                                   derivatives1: np.ndarray,
                                   derivatives2: np.ndarray) -> Optional[Dict[str, Any]]:
        """
        对导数序列执行DTW对齐
        
        这是核心步骤：使用DTW算法找到两条导数序列之间的最优对齐路径
        对齐路径告诉我们：derivatives1的第i个点应该与derivatives2的第j个点对齐
        
        Args:
            derivatives1: 第一条边缘的归一化导数序列
            derivatives2: 第二条边缘的归一化导数序列
        
        Returns:
            Dict[str, Any]: DTW对齐结果，包含：
                - alignment_path: 对齐路径 [(i, j), ...]
                - dtw_distance: DTW距离（越小表示越相似）
                如果对齐失败则返回None
        """
        try:
            # 将导数序列重塑为列向量（DTW库要求）
            # 每个导数值作为一个特征维度
            d1_array = derivatives1.reshape(-1, 1)
            d2_array = derivatives2.reshape(-1, 1)
            
            # 计算DTW窗口大小（限制对齐范围，避免过度扭曲）
            max_len = max(len(derivatives1), len(derivatives2))
            window_size = int(max_len * self.window_size_ratio)
            
            # 配置DTW参数
            dtw_kwargs = {
                'keep_internals': True,
                'step_pattern': 'symmetric2'  # 对称步进模式
            }
            
            # 如果设置了窗口大小，添加窗口约束
            # 注意：dtw库使用window_args字典传递窗口参数，而不是直接使用window_size
            if window_size > 0 and window_size < max_len:
                dtw_kwargs['window_type'] = 'sakoechiba'
                dtw_kwargs['window_args'] = {'window_size': window_size}
            
            # 根据距离度量方式选择DTW方法
            # 注意：dtw库默认使用欧式距离，我们需要手动计算距离矩阵
            # 或者使用不同的距离度量方式
            if self.distance_metric == 'manhattan':
                # 曼哈顿距离：对抖动更鲁棒
                # 需要自定义距离函数
                alignment = dtw(d1_array, d2_array, 
                               distance_only=False,
                               **dtw_kwargs)
            elif self.distance_metric == 'chebyshev':
                # 切比雪夫距离：关注最大差异
                alignment = dtw(d1_array, d2_array,
                               distance_only=False,
                               **dtw_kwargs)
            else:
                # 默认：欧式距离
                alignment = dtw(d1_array, d2_array,
                               distance_only=False,
                               **dtw_kwargs)
            
            # 提取对齐路径
            # alignment.index1和alignment.index2是对齐后的索引序列
            # 它们告诉我们：derivatives1的哪个点与derivatives2的哪个点对齐
            alignment_path = list(zip(alignment.index1, alignment.index2))
            
            return {
                'alignment_path': alignment_path,
                'dtw_distance': alignment.distance
            }
            
        except Exception as e:
            logger.error(f"❌ DTW对齐失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def _resample_by_alignment_path(self,
                                   times1: np.ndarray,
                                   values1: np.ndarray,
                                   times2: np.ndarray,
                                   values2: np.ndarray,
                                   alignment_path: List[Tuple[int, int]]) -> Optional[Dict[str, Any]]:
        """
        根据DTW对齐路径重新采样原始曲线
        
        改进方法：使用插值来保持曲线的平滑性，避免直接使用对齐路径导致的不连续
        
        方法：
        1. 从对齐路径中提取对应关系，创建映射
        2. 创建统一的时间轴（基于对齐路径）
        3. 使用插值将原始曲线映射到统一时间轴上，保持平滑性
        
        Args:
            times1: 第一条曲线的时间序列
            values1: 第一条曲线的值序列
            times2: 第二条曲线的时间序列
            values2: 第二条曲线的值序列
            alignment_path: DTW对齐路径 [(i, j), ...]
        
        Returns:
            Dict[str, Any]: 重新采样结果，包含：
                - aligned_times: 对齐后的时间点数组（归一化到[0, 1]）
                - aligned_values1: 对齐后的第一条曲线的值（插值后）
                - aligned_values2: 对齐后的第二条曲线的值（插值后）
                如果重新采样失败则返回None
        """
        try:
            if len(alignment_path) == 0:
                return None
            
            # 1. 从对齐路径中提取对应关系
            #    创建从对齐路径索引到原始索引的映射
            path_indices1 = []
            path_indices2 = []
            
            for i, j in alignment_path:
                # 确保索引在有效范围内
                if i < 0 or i >= len(times1) or j < 0 or j >= len(times2):
                    continue
                path_indices1.append(i)
                path_indices2.append(j)
            
            if len(path_indices1) == 0:
                return None
            
            # 2. 创建统一的时间轴（基于对齐路径的长度）
            #    使用归一化时间[0, 1]，便于对比
            num_aligned_points = len(path_indices1)
            aligned_times_norm = np.linspace(0, 1, num_aligned_points)
            
            # 3. 使用插值将原始曲线映射到统一时间轴上
            #    这样可以保持曲线的平滑性，避免不连续
            
            # 对于曲线1：创建从原始时间到对齐路径的映射
            # 对齐路径告诉我们：原始索引i对应对齐路径中的位置k
            # 我们需要创建一个从对齐路径位置到原始值的映射
            original_times1_mapped = []
            original_values1_mapped = []
            original_times2_mapped = []
            original_values2_mapped = []
            
            for k, (i, j) in enumerate(alignment_path):
                if i < 0 or i >= len(times1) or j < 0 or j >= len(times2):
                    continue
                # 使用归一化时间作为x轴
                norm_time = k / (num_aligned_points - 1) if num_aligned_points > 1 else 0
                original_times1_mapped.append(norm_time)
                original_values1_mapped.append(values1[i])
                original_times2_mapped.append(norm_time)
                original_values2_mapped.append(values2[j])
            
            if len(original_times1_mapped) < 2:
                return None
            
            # 4. 使用插值平滑对齐后的曲线
            #    使用线性插值，对于平滑曲线可以保持平滑性
            from scipy.interpolate import interp1d
            
            # 转换为numpy数组
            original_times1_mapped = np.array(original_times1_mapped)
            original_values1_mapped = np.array(original_values1_mapped)
            original_times2_mapped = np.array(original_times2_mapped)
            original_values2_mapped = np.array(original_values2_mapped)
            
            # 创建插值函数
            # 使用'linear'插值保持平滑性，'cubic'可能过度平滑
            try:
                interp1 = interp1d(original_times1_mapped, original_values1_mapped, 
                                 kind='linear', bounds_error=False, fill_value='extrapolate')
                interp2 = interp1d(original_times2_mapped, original_values2_mapped,
                                 kind='linear', bounds_error=False, fill_value='extrapolate')
                
                # 在统一时间轴上插值
                aligned_values1 = interp1(aligned_times_norm)
                aligned_values2 = interp2(aligned_times_norm)
                
            except Exception as e:
                logger.warning(f"⚠️ 插值失败，使用直接映射: {e}")
                # 如果插值失败，回退到直接使用对齐路径中的值
                aligned_values1 = original_values1_mapped
                aligned_values2 = original_values2_mapped
                aligned_times_norm = original_times1_mapped
            
            return {
                'aligned_times': aligned_times_norm,
                'aligned_values1': aligned_values1,
                'aligned_values2': aligned_values2
            }
            
        except Exception as e:
            logger.error(f"❌ 根据对齐路径重新采样失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def _resample_by_alignment_path_conservative(self,
                                                times1: np.ndarray,
                                                values1: np.ndarray,
                                                times2: np.ndarray,
                                                values2: np.ndarray,
                                                alignment_path: List[Tuple[int, int]]) -> Optional[Dict[str, Any]]:
        """
        保守的重新采样方法：尽量保持原始曲线形状
        
        策略：
        1. 使用录制曲线的时间轴作为基准（不扭曲录制曲线）
        2. 只对播放曲线进行对齐，将其映射到录制曲线的时间轴上
        3. 使用插值将播放曲线映射到录制曲线的时间点
        
        这样可以保持录制曲线不变，只调整播放曲线，减少整体扭曲。
        
        Args:
            times1: 录制曲线的时间序列（作为基准）
            values1: 录制曲线的值序列
            times2: 播放曲线的时间序列
            values2: 播放曲线的值序列
            alignment_path: DTW对齐路径 [(i, j), ...]
        
        Returns:
            Dict[str, Any]: 重新采样结果，包含：
                - aligned_times: 对齐后的时间点数组（归一化到[0, 1]）
                - aligned_values1: 录制曲线的值（保持原样）
                - aligned_values2: 播放曲线的值（对齐后）
                如果重新采样失败则返回None
        """
        try:
            if len(alignment_path) == 0:
                return None
            
            # 1. 归一化录制曲线的时间到[0, 1]作为基准时间轴
            if times1[-1] != times1[0]:
                norm_times1 = (times1 - times1[0]) / (times1[-1] - times1[0])
            else:
                norm_times1 = np.zeros_like(times1)
            
            # 2. 归一化播放曲线的时间到[0, 1]
            if times2[-1] != times2[0]:
                norm_times2 = (times2 - times2[0]) / (times2[-1] - times2[0])
            else:
                norm_times2 = np.zeros_like(times2)
            
            # 3. 根据对齐路径，创建从播放曲线到录制曲线时间轴的映射
            #    对齐路径告诉我们：录制曲线的索引i与播放曲线的索引j对应
            #    我们需要将播放曲线映射到录制曲线的时间轴上
            
            # 策略：使用插值来避免阶梯效应，但使用PchipInterpolator来保持波峰和波谷
            # 创建映射：录制曲线时间 -> 播放曲线值
            record_times_mapped = []
            replay_values_mapped = []
            
            for i, j in alignment_path:
                if i < 0 or i >= len(norm_times1) or j < 0 or j >= len(norm_times2):
                    continue
                # 使用录制曲线的时间点
                record_times_mapped.append(norm_times1[i])
                # 使用播放曲线对应的值
                replay_values_mapped.append(values2[j])
            
            if len(record_times_mapped) < 2:
                return None
            
            # 转换为numpy数组并排序（插值需要排序的数据）
            record_times_mapped = np.array(record_times_mapped)
            replay_values_mapped = np.array(replay_values_mapped)
            
            # 排序
            sort_idx = np.argsort(record_times_mapped)
            record_times_mapped = record_times_mapped[sort_idx]
            replay_values_mapped = replay_values_mapped[sort_idx]
            
            # 去除重复时间点（保留最后一个值，因为可能有多个对齐路径映射到同一时间点）
            unique_times, unique_indices = np.unique(record_times_mapped, return_index=True)
            # 对于重复的时间点，使用最后一个值（更接近对齐路径的末尾）
            unique_values = []
            for i, t in enumerate(unique_times):
                # 找到所有对应这个时间点的值
                mask = record_times_mapped == t
                values_at_t = replay_values_mapped[mask]
                # 使用最后一个值（对齐路径末尾的值通常更准确）
                unique_values.append(values_at_t[-1])
            unique_values = np.array(unique_values)
            
            if len(unique_times) < 2:
                return None
            
            # 4. 使用PchipInterpolator进行插值，既保持平滑又保持波峰和波谷
            from scipy.interpolate import PchipInterpolator, interp1d
            
            try:
                # 使用PchipInterpolator（分段三次Hermite插值）来保持单调性和波峰波谷
                interp_replay = PchipInterpolator(unique_times, unique_values, extrapolate=True)
                
                # 在录制曲线的时间轴上插值播放曲线
                aligned_replay_values = interp_replay(norm_times1)
                
            except Exception as e:
                logger.warning(f"⚠️ PchipInterpolator失败，回退到线性插值: {e}")
                # 如果PchipInterpolator失败，使用线性插值（虽然会稍微改变形状，但至少是平滑的）
                interp_replay = interp1d(unique_times, unique_values,
                                        kind='linear', bounds_error=False, fill_value='extrapolate')
                aligned_replay_values = interp_replay(norm_times1)
            
            return {
                'aligned_times': norm_times1,  # 使用录制曲线的时间轴
                'aligned_values1': values1,    # 录制曲线保持不变
                'aligned_values2': aligned_replay_values  # 播放曲线对齐到录制曲线的时间轴
            }
            
        except Exception as e:
            logger.error(f"❌ 保守重新采样失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def _find_main_peak(self, values: np.ndarray, 
                       min_height_ratio: float = 0.3,
                       min_distance_ratio: float = 0.1) -> int:
        """
        找到曲线中的主要峰值
        
        方法：
        1. 使用find_peaks检测所有局部峰值
        2. 过滤掉高度过低的峰值（相对于最大值）
        3. 如果存在多个峰值，选择最大的峰值作为主峰值
        4. 如果没有找到峰值，回退到全局最大值
        
        Args:
            values: 曲线值数组
            min_height_ratio: 峰值最小高度比例（相对于最大值），默认0.3（30%）
            min_distance_ratio: 峰值之间的最小距离比例（相对于总长度），默认0.1（10%）
        
        Returns:
            int: 主峰值的索引
        """
        try:
            if len(values) < 3:
                # 数据点太少，直接返回最大值索引
                return np.argmax(values)
            
            # 计算峰值检测参数
            max_value = np.max(values)
            min_height = max_value * min_height_ratio
            min_distance = max(1, int(len(values) * min_distance_ratio))
            
            # 使用find_peaks检测所有局部峰值
            peaks, properties = find_peaks(
                values,
                height=min_height,
                distance=min_distance
            )
            
            if len(peaks) == 0:
                # 没有找到峰值，回退到全局最大值
                logger.debug("⚠️ 未找到局部峰值，使用全局最大值")
                return np.argmax(values)
            
            # 如果有多个峰值，选择最大的峰值
            peak_values = values[peaks]
            main_peak_idx_in_peaks = np.argmax(peak_values)
            main_peak_idx = peaks[main_peak_idx_in_peaks]
            
            if len(peaks) > 1:
                logger.debug(f"⚠️ 检测到{len(peaks)}个峰值，选择最大的峰值（索引{main_peak_idx}）")
            
            return main_peak_idx
            
        except Exception as e:
            logger.warning(f"⚠️ 峰值检测失败，使用全局最大值: {e}")
            return np.argmax(values)
    
    
class ForceCurveAnalyzer:
    """
    力度曲线分析器 - 分析after_touch曲线的上升沿和下降沿
    
    功能：
    1. 提取上升沿（从按键开始到峰值）
    2. 提取下降沿（从峰值到按键结束）
    3. 使用基于导数的DTW对齐两条曲线的上升沿和下降沿
    4. 计算曲线相似度（用于匹配）
    5. 对比两条曲线的上升沿和下降沿
    
    核心特性：
    - 使用基于导数的DTW对齐方法
    - 导数更能反映曲线的变化趋势，符合"上升沿"和"下降沿"的本质
    - 对小幅抖动更鲁棒，因为小幅抖动在导数上的影响相对较小
    """
    
    def __init__(self,
                 smooth_sigma: float = 1.0,
                 dtw_distance_metric: str = 'manhattan',
                 dtw_window_size_ratio: float = 0.5):
        """
        初始化力度曲线分析器
        
        Args:
            smooth_sigma: 高斯平滑参数（标准差），用于减少抖动影响
                         - 0表示不平滑（不推荐，因为导数会放大噪声）
                         - 建议值：1.0-2.0
            dtw_distance_metric: DTW距离度量方式
                                - 'manhattan': 曼哈顿距离（L1距离，对抖动更鲁棒，推荐）
                                - 'euclidean': 欧式距离（默认）
                                - 'chebyshev': 切比雪夫距离
            dtw_window_size_ratio: DTW窗口大小比例
                                  - 限制对齐范围，避免过度扭曲
                                  - 0.5表示窗口大小为序列长度的50%（推荐）
        """
        self.smooth_sigma = smooth_sigma
        
        # 初始化基于导数的DTW对齐器
        self.derivative_dtw_aligner = DerivativeDTWAligner(
            smooth_sigma=smooth_sigma,
            distance_metric=dtw_distance_metric,
            window_size_ratio=dtw_window_size_ratio
        )
    
    def extract_curve_edges(self, note) -> Optional[Dict[str, Any]]:
        """
        提取力度曲线的上升沿和下降沿
        
        Args:
            note: 音符对象
            
        Returns:
            Dict[str, Any]: 包含：
                - rising_edge: (times, values) - 上升沿数据
                - falling_edge: (times, values) - 下降沿数据
                - peak_index: 峰值索引
                - peak_time: 峰值时间（ms）
                - peak_value: 峰值
                如果提取失败则返回None
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
            
            # 平滑处理（减少抖动影响）
            if self.smooth_sigma > 0 and len(values) > 1:
                values = gaussian_filter1d(values, sigma=self.smooth_sigma)
            
            # 找到主要峰值（支持多个峰值的情况）
            peak_index = self._find_main_peak(values)
            peak_time = times[peak_index]
            peak_value = values[peak_index]
            
            # 提取上升沿：从开始到峰值
            rising_times = times[:peak_index + 1]
            rising_values = values[:peak_index + 1]
            
            # 提取下降沿：从峰值到结束
            falling_times = times[peak_index:]
            falling_values = values[peak_index:]
            
            return {
                'rising_edge': (rising_times, rising_values),
                'falling_edge': (falling_times, falling_values),
                'peak_index': peak_index,
                'peak_time': peak_time,
                'peak_value': peak_value,
                'full_curve': (times, values)
            }
            
        except Exception as e:
            logger.error(f"❌ 提取曲线边缘失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def _find_main_peak(self, values: np.ndarray, 
                       min_height_ratio: float = 0.3,
                       min_distance_ratio: float = 0.1) -> int:
        """
        找到曲线中的主要峰值
        
        方法：
        1. 使用find_peaks检测所有局部峰值
        2. 过滤掉高度过低的峰值（相对于最大值）
        3. 如果存在多个峰值，选择最大的峰值作为主峰值
        4. 如果没有找到峰值，回退到全局最大值
        
        Args:
            values: 曲线值数组
            min_height_ratio: 峰值最小高度比例（相对于最大值），默认0.3（30%）
            min_distance_ratio: 峰值之间的最小距离比例（相对于总长度），默认0.1（10%）
        
        Returns:
            int: 主峰值的索引
        """
        try:
            if len(values) < 3:
                # 数据点太少，直接返回最大值索引
                return np.argmax(values)
            
            # 计算峰值检测参数
            max_value = np.max(values)
            min_height = max_value * min_height_ratio
            min_distance = max(1, int(len(values) * min_distance_ratio))
            
            # 使用find_peaks检测所有局部峰值
            peaks, properties = find_peaks(
                values,
                height=min_height,
                distance=min_distance
            )
            
            if len(peaks) == 0:
                # 没有找到峰值，回退到全局最大值
                logger.debug("⚠️ 未找到局部峰值，使用全局最大值")
                return np.argmax(values)
            
            # 如果有多个峰值，选择最大的峰值
            peak_values = values[peaks]
            main_peak_idx_in_peaks = np.argmax(peak_values)
            main_peak_idx = peaks[main_peak_idx_in_peaks]
            
            if len(peaks) > 1:
                logger.debug(f"⚠️ 检测到{len(peaks)}个峰值，选择最大的峰值（索引{main_peak_idx}）")
            
            return main_peak_idx
            
        except Exception as e:
            logger.warning(f"⚠️ 峰值检测失败，使用全局最大值: {e}")
            return np.argmax(values)
    
    def compare_curves(self, note1, note2, record_note=None, replay_note=None) -> Optional[Dict[str, Any]]:
        """
        对比两条力度曲线的上升沿和下降沿
        
        改进后的流程：
        1. 先对齐完整曲线，建立整体对应关系
        2. 在对齐后的曲线上提取上升沿和下降沿
        3. 分别计算上升沿和下降沿的相似度
        
        这样确保峰值点对应，边缘提取更准确。
        
        注意：播放曲线对齐到录制曲线（replay对齐到record）
        
        Args:
            note1: 第一个音符对象（通常是录制曲线）
            note2: 第二个音符对象（通常是播放曲线）
            record_note: 录制音符对象（明确指定，用于可视化标签）
            replay_note: 播放音符对象（明确指定，用于可视化标签）
            
        Returns:
            Dict[str, Any]: 对比结果，包含：
                - rising_edge_similarity: 上升沿相似度（0-1，1表示完全相同）
                - falling_edge_similarity: 下降沿相似度（0-1）
                - overall_similarity: 整体相似度（0-1）
                - rising_edge_diff: 上升沿差异统计
                - falling_edge_diff: 下降沿差异统计
                - processing_stages: 各处理阶段的中间数据（用于可视化）
                如果对比失败则返回None
        """
        try:
            # 确定录制和播放曲线
            if record_note is None:
                record_note = note1
            if replay_note is None:
                replay_note = note2
            
            # 步骤1：提取完整曲线数据（原始阶段）
            curve1_data = self._extract_full_curve(record_note)
            curve2_data = self._extract_full_curve(replay_note)
            
            if curve1_data is None or curve2_data is None:
                return None
            
            times1, values1 = curve1_data
            times2, values2 = curve2_data
            
            # 保存阶段1：原始曲线
            stage1_original = {
                'record_times': times1.copy(),
                'record_values': values1.copy(),
                'replay_times': times2.copy(),
                'replay_values': values2.copy(),
                'description': '阶段1：原始曲线（提取后）'
            }
            
            # 步骤2：对齐完整曲线（使用基于导数的DTW）
            alignment_result = self.derivative_dtw_aligner.align_full_curves(
                (times1, values1),
                (times2, values2)
            )
            
            if alignment_result is None:
                logger.warning("⚠️ 完整曲线对齐失败，无法继续分析")
                return None
            
            # 保存阶段2：平滑后的曲线（使用原始时间，不归一化）
            # 重要：必须保持原始时间轴，不能将起始点对齐，否则会丢失延迟信息
            before_alignment = alignment_result.get('before_alignment', {})
            # 获取平滑后的值（从对齐结果中，仅用于可视化对比）
            values1_smooth = before_alignment.get('values1', values1)
            values2_smooth = before_alignment.get('values2', values2)
            # 使用原始时间，不归一化
            stage2_smoothed = {
                'record_times': times1.copy(),  # 原始时间，不归一化
                'record_values': values1_smooth,  # 平滑后的值（仅用于可视化）
                'replay_times': times2.copy(),  # 原始时间，不归一化
                'replay_values': values2_smooth,  # 平滑后的值（仅用于可视化）
                'description': '阶段2：平滑后的曲线（仅用于计算导数，最终输出使用原始值）'
            }
            
            # 保存阶段3：导数曲线（使用原始时间，不归一化）
            derivatives1 = alignment_result.get('derivatives1', None)
            derivatives2 = alignment_result.get('derivatives2', None)
            stage3_derivatives = None
            if derivatives1 is not None and derivatives2 is not None:
                # 使用原始时间轴显示导数，保持原始时间关系
                stage3_derivatives = {
                    'record_times': times1.copy(),  # 原始时间，不归一化
                    'record_derivatives': derivatives1,
                    'replay_times': times2.copy(),  # 原始时间，不归一化
                    'replay_derivatives': derivatives2,
                    'description': '阶段3：导数曲线（用于DTW对齐，保持原始时间轴）'
                }
            
            # 步骤3：在对齐后的曲线上提取上升沿和下降沿
            aligned_times = alignment_result['aligned_times']
            aligned_values1 = alignment_result['aligned_values1']  # 录制曲线（对齐后）
            aligned_values2 = alignment_result['aligned_values2']  # 播放曲线（对齐后）
            peak_idx1 = alignment_result['peak_indices1']
            peak_idx2 = alignment_result['peak_indices2']
            
            # 保存阶段4：DTW对齐后的曲线
            # 同时保存原始曲线（用于对比），确保用户能看到对齐前后的差异
            stage4_aligned = {
                'aligned_times': aligned_times,
                'record_values': aligned_values1,  # 对齐后的录制曲线
                'replay_values': aligned_values2,  # 对齐后的播放曲线
                # 同时保存原始曲线（用于对比）
                'original_record_times': times1.copy(),  # 原始录制曲线时间
                'original_record_values': values1.copy(),  # 原始录制曲线值
                'original_replay_times': times2.copy(),  # 原始播放曲线时间
                'original_replay_values': values2.copy(),  # 原始播放曲线值
                'description': '阶段4：DTW对齐后的曲线（播放对齐到录制）'
            }
            
            # 提取对齐后的上升沿和下降沿
            # 使用两个峰值索引的平均值作为分割点，确保对应关系
            # 如果两个峰值索引差异很大，使用较大的索引作为分割点
            split_idx = max(peak_idx1, peak_idx2)
            
            # 上升沿：从开始到分割点（包含分割点）
            rising_times = aligned_times[:split_idx + 1]
            rising_values1 = aligned_values1[:split_idx + 1]
            rising_values2 = aligned_values2[:split_idx + 1]
            
            # 下降沿：从分割点到结束（包含分割点）
            falling_times = aligned_times[split_idx:]
            falling_values1 = aligned_values1[split_idx:]
            falling_values2 = aligned_values2[split_idx:]
            
            # 保存阶段5：提取上升沿和下降沿后的曲线
            stage5_edges = {
                'rising': {
                    'times': rising_times,
                    'record_values': rising_values1,
                    'replay_values': rising_values2,
                    'description': '阶段5a：上升沿（对齐后）'
                },
                'falling': {
                    'times': falling_times,
                    'record_values': falling_values1,
                    'replay_values': falling_values2,
                    'description': '阶段5b：下降沿（对齐后）'
                }
            }
            
            # 步骤4：分别计算上升沿和下降沿的相似度
            rising_similarity = self._compute_edge_similarity(
                (rising_times, rising_values1),
                (rising_times, rising_values2)
            )
            
            falling_similarity = self._compute_edge_similarity(
                (falling_times, falling_values1),
                (falling_times, falling_values2)
            )
            
            # 步骤5：计算整体相似度
            overall_similarity = (rising_similarity['similarity'] + falling_similarity['similarity']) / 2.0
            
            return {
                'rising_edge_similarity': rising_similarity['similarity'],
                'falling_edge_similarity': falling_similarity['similarity'],
                'overall_similarity': overall_similarity,
                'rising_edge_diff': rising_similarity,
                'falling_edge_diff': falling_similarity,
                'curve1_peak': aligned_values1[peak_idx1],
                'curve2_peak': aligned_values2[peak_idx2],
                'alignment_method': 'full_curve_then_edges',
                'dtw_distance': alignment_result['dtw_distance'],
                
                # 各处理阶段的中间数据（用于可视化）
                'processing_stages': {
                    'stage1_original': stage1_original,
                    'stage2_smoothed': stage2_smoothed,
                    'stage3_derivatives': stage3_derivatives,
                    'stage4_aligned': stage4_aligned,
                    'stage5_edges': stage5_edges
                },
                
                # 对齐前后对比数据（用于可视化，保持向后兼容）
                'alignment_comparison': {
                    'before_alignment': alignment_result.get('before_alignment', {}),
                    'after_alignment': {
                        'times': aligned_times,
                        'values1': aligned_values1,
                        'values2': aligned_values2
                    },
                    'peak_info': {
                        'before': {
                            'peak_idx1': alignment_result.get('original_peak_idx1', -1),
                            'peak_idx2': alignment_result.get('original_peak_idx2', -1),
                            'peak_time1': alignment_result.get('original_peak_time1', 0),
                            'peak_time2': alignment_result.get('original_peak_time2', 0)
                        },
                        'after': {
                            'peak_idx1': peak_idx1,
                            'peak_idx2': peak_idx2,
                            'split_idx': split_idx
                        }
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"❌ 对比曲线失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def visualize_alignment_comparison(self, comparison_result: Dict[str, Any]) -> Optional[Any]:
        """
        可视化对齐前后的对比
        
        生成一个包含两个子图的图表：
        1. 对齐前的曲线（原始时间轴）
        2. 对齐后的曲线（对齐后的时间轴）
        
        Args:
            comparison_result: compare_curves()的返回结果，必须包含alignment_comparison字段
        
        Returns:
            plotly.graph_objects.Figure: 对比图表，如果失败则返回None
        """
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
            
            if 'alignment_comparison' not in comparison_result:
                logger.warning("⚠️ 对比结果中没有对齐对比数据")
                return None
            
            alignment_comp = comparison_result['alignment_comparison']
            before = alignment_comp.get('before_alignment', {})
            after = alignment_comp.get('after_alignment', {})
            
            if not before or not after:
                logger.warning("⚠️ 对齐对比数据不完整")
                return None
            
            # 创建子图：上下排列，对比对齐前后
            fig = make_subplots(
                rows=2, cols=1,
                subplot_titles=('对齐前（原始时间轴）', '对齐后（DTW对齐后的时间轴）'),
                vertical_spacing=0.15,
                row_heights=[0.5, 0.5]
            )
            
            # 子图1：对齐前的曲线
            times1_before = before.get('times1', [])
            values1_before = before.get('values1', [])
            times2_before = before.get('times2', [])
            values2_before = before.get('values2', [])
            
            if len(times1_before) > 0 and len(values1_before) > 0:
                fig.add_trace(
                    go.Scatter(
                        x=times1_before,
                        y=values1_before,
                        mode='lines',
                        name='曲线1（对齐前）',
                        line=dict(color='#1f77b4', width=2),
                        legendgroup='before'
                    ),
                    row=1, col=1
                )
            
            if len(times2_before) > 0 and len(values2_before) > 0:
                fig.add_trace(
                    go.Scatter(
                        x=times2_before,
                        y=values2_before,
                        mode='lines',
                        name='曲线2（对齐前）',
                        line=dict(color='#ff7f0e', width=2),
                        legendgroup='before'
                    ),
                    row=1, col=1
                )
            
            # 标记对齐前的峰值点
            peak_info = alignment_comp.get('peak_info', {}).get('before', {})
            if peak_info:
                peak_idx1 = peak_info.get('peak_idx1', -1)
                peak_idx2 = peak_info.get('peak_idx2', -1)
                
                if peak_idx1 >= 0 and peak_idx1 < len(times1_before) and peak_idx1 < len(values1_before):
                    fig.add_trace(
                        go.Scatter(
                            x=[times1_before[peak_idx1]],
                            y=[values1_before[peak_idx1]],
                            mode='markers',
                            name='曲线1峰值（对齐前）',
                            marker=dict(color='#1f77b4', size=10, symbol='diamond'),
                            legendgroup='before',
                            showlegend=False
                        ),
                        row=1, col=1
                    )
                
                if peak_idx2 >= 0 and peak_idx2 < len(times2_before) and peak_idx2 < len(values2_before):
                    fig.add_trace(
                        go.Scatter(
                            x=[times2_before[peak_idx2]],
                            y=[values2_before[peak_idx2]],
                            mode='markers',
                            name='曲线2峰值（对齐前）',
                            marker=dict(color='#ff7f0e', size=10, symbol='diamond'),
                            legendgroup='before',
                            showlegend=False
                        ),
                        row=1, col=1
                    )
            
            # 子图2：对齐后的曲线
            times_after = after.get('times', [])
            values1_after = after.get('values1', [])
            values2_after = after.get('values2', [])
            
            if len(times_after) > 0 and len(values1_after) > 0:
                fig.add_trace(
                    go.Scatter(
                        x=times_after,
                        y=values1_after,
                        mode='lines',
                        name='曲线1（对齐后）',
                        line=dict(color='#1f77b4', width=2),
                        legendgroup='after'
                    ),
                    row=2, col=1
                )
            
            if len(times_after) > 0 and len(values2_after) > 0:
                fig.add_trace(
                    go.Scatter(
                        x=times_after,
                        y=values2_after,
                        mode='lines',
                        name='曲线2（对齐后）',
                        line=dict(color='#ff7f0e', width=2),
                        legendgroup='after'
                    ),
                    row=2, col=1
                )
            
            # 标记对齐后的峰值点
            peak_info_after = alignment_comp.get('peak_info', {}).get('after', {})
            if peak_info_after:
                peak_idx1 = peak_info_after.get('peak_idx1', -1)
                peak_idx2 = peak_info_after.get('peak_idx2', -1)
                split_idx = peak_info_after.get('split_idx', -1)
                
                if peak_idx1 >= 0 and peak_idx1 < len(times_after) and peak_idx1 < len(values1_after):
                    fig.add_trace(
                        go.Scatter(
                            x=[times_after[peak_idx1]],
                            y=[values1_after[peak_idx1]],
                            mode='markers',
                            name='曲线1峰值（对齐后）',
                            marker=dict(color='#1f77b4', size=10, symbol='diamond'),
                            legendgroup='after',
                            showlegend=False
                        ),
                        row=2, col=1
                    )
                
                if peak_idx2 >= 0 and peak_idx2 < len(times_after) and peak_idx2 < len(values2_after):
                    fig.add_trace(
                        go.Scatter(
                            x=[times_after[peak_idx2]],
                            y=[values2_after[peak_idx2]],
                            mode='markers',
                            name='曲线2峰值（对齐后）',
                            marker=dict(color='#ff7f0e', size=10, symbol='diamond'),
                            legendgroup='after',
                            showlegend=False
                        ),
                        row=2, col=1
                    )
                
                # 标记分割点（用于提取上升沿和下降沿）
                if split_idx >= 0 and split_idx < len(times_after):
                    fig.add_trace(
                        go.Scatter(
                            x=[times_after[split_idx]],
                            y=[(values1_after[split_idx] + values2_after[split_idx]) / 2 if split_idx < len(values1_after) and split_idx < len(values2_after) else 0],
                            mode='markers',
                            name='分割点（上升沿/下降沿）',
                            marker=dict(color='red', size=12, symbol='x', line=dict(width=2)),
                            legendgroup='after',
                            showlegend=True
                        ),
                        row=2, col=1
                    )
            
            # 更新布局
            fig.update_layout(
                title='曲线对齐前后对比',
                height=800,
                showlegend=True,
                legend=dict(
                    orientation='h',
                    yanchor='bottom',
                    y=1.02,
                    xanchor='right',
                    x=1
                )
            )
            
            # 更新x轴和y轴标签
            fig.update_xaxes(title_text='归一化时间 [0, 1]', row=1, col=1)
            fig.update_yaxes(title_text='力度值', row=1, col=1)
            fig.update_xaxes(title_text='对齐后的归一化时间 [0, 1]', row=2, col=1)
            fig.update_yaxes(title_text='力度值', row=2, col=1)
            
            return fig
            
        except Exception as e:
            logger.error(f"❌ 生成对齐对比图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def visualize_all_processing_stages(self, comparison_result: Dict[str, Any]) -> Optional[Any]:
        """
        可视化所有处理阶段的曲线
        
        生成一个包含多个子图的图表，显示：
        1. 阶段1：原始曲线（提取后）
        2. 阶段2：平滑后的曲线
        3. 阶段3：导数曲线（用于DTW对齐）
        4. 阶段4：DTW对齐后的曲线（播放对齐到录制）
        5. 阶段5a：上升沿（对齐后）
        6. 阶段5b：下降沿（对齐后）
        
        注意：播放曲线对齐到录制曲线（replay对齐到record）
        
        Args:
            comparison_result: compare_curves()的返回结果，必须包含processing_stages字段
        
        Returns:
            plotly.graph_objects.Figure: 多阶段对比图表，如果失败则返回None
        """
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
            
            if 'processing_stages' not in comparison_result:
                logger.warning("⚠️ 对比结果中没有处理阶段数据")
                return None
            
            stages = comparison_result['processing_stages']
            
            # 计算子图数量
            num_subplots = 0
            subplot_titles = []
            
            if stages.get('stage1_original'):
                num_subplots += 1
                subplot_titles.append('阶段1：原始曲线')
            if stages.get('stage2_smoothed'):
                num_subplots += 1
                subplot_titles.append('阶段2：平滑后的曲线')
            if stages.get('stage3_derivatives'):
                num_subplots += 1
                subplot_titles.append('阶段3：导数曲线')
            if stages.get('stage4_aligned'):
                num_subplots += 1
                subplot_titles.append('阶段4：DTW对齐后的曲线（播放对齐到录制）')
            if stages.get('stage5_edges'):
                num_subplots += 2  # 上升沿和下降沿
                subplot_titles.append('阶段5a：上升沿')
                subplot_titles.append('阶段5b：下降沿')
            
            if num_subplots == 0:
                logger.warning("⚠️ 没有可用的处理阶段数据")
                return None
            
            # 创建子图
            # 增加子图间距和高度，避免挤在一起
            fig = make_subplots(
                rows=num_subplots, cols=1,
                subplot_titles=subplot_titles,
                vertical_spacing=0.075,  # 子图之间的间距（0.15的一半）
                row_heights=[1.0] * num_subplots  # 每个子图使用相同高度
            )
            
            row = 1
            
            # 阶段1：原始曲线
            if stages.get('stage1_original'):
                stage1 = stages['stage1_original']
                record_times = stage1.get('record_times', [])
                record_values = stage1.get('record_values', [])
                replay_times = stage1.get('replay_times', [])
                replay_values = stage1.get('replay_values', [])
                
                if len(record_times) > 0 and len(record_values) > 0:
                    fig.add_trace(
                        go.Scatter(
                            x=record_times,
                            y=record_values,
                            mode='lines',
                            name='录制曲线',
                            line=dict(color='blue', width=2),
                            legendgroup='record',
                            showlegend=(row == 1)
                        ),
                        row=row, col=1
                    )
                
                if len(replay_times) > 0 and len(replay_values) > 0:
                    fig.add_trace(
                        go.Scatter(
                            x=replay_times,
                            y=replay_values,
                            mode='lines',
                            name='播放曲线',
                            line=dict(color='red', width=2, dash='dash'),
                            legendgroup='replay',
                            showlegend=(row == 1)
                        ),
                        row=row, col=1
                    )
                
                fig.update_xaxes(title_text="时间 (ms)", row=row, col=1)
                fig.update_yaxes(title_text="力度值", row=row, col=1)
                row += 1
            
            # 阶段2：平滑后的曲线
            if stages.get('stage2_smoothed'):
                stage2 = stages['stage2_smoothed']
                record_times = stage2.get('record_times', [])
                record_values = stage2.get('record_values', [])
                replay_times = stage2.get('replay_times', [])
                replay_values = stage2.get('replay_values', [])
                
                if len(record_times) > 0 and len(record_values) > 0:
                    fig.add_trace(
                        go.Scatter(
                            x=record_times,
                            y=record_values,
                            mode='lines',
                            name='录制曲线（平滑后）',
                            line=dict(color='blue', width=2),
                            legendgroup='record',
                            showlegend=False
                        ),
                        row=row, col=1
                    )
                
                if len(replay_times) > 0 and len(replay_values) > 0:
                    fig.add_trace(
                        go.Scatter(
                            x=replay_times,
                            y=replay_values,
                            mode='lines',
                            name='播放曲线（平滑后）',
                            line=dict(color='red', width=2, dash='dash'),
                            legendgroup='replay',
                            showlegend=False
                        ),
                        row=row, col=1
                    )
                
                fig.update_xaxes(title_text="时间 (ms)", row=row, col=1)
                fig.update_yaxes(title_text="力度值", row=row, col=1)
                row += 1
            
            # 阶段3：导数曲线
            if stages.get('stage3_derivatives'):
                stage3 = stages['stage3_derivatives']
                record_times = stage3.get('record_times', [])
                record_derivatives = stage3.get('record_derivatives', [])
                replay_times = stage3.get('replay_times', [])
                replay_derivatives = stage3.get('replay_derivatives', [])
                
                if len(record_times) > 0 and len(record_derivatives) > 0:
                    fig.add_trace(
                        go.Scatter(
                            x=record_times,
                            y=record_derivatives,
                            mode='lines',
                            name='录制曲线导数',
                            line=dict(color='blue', width=2),
                            legendgroup='record',
                            showlegend=False
                        ),
                        row=row, col=1
                    )
                
                if len(replay_times) > 0 and len(replay_derivatives) > 0:
                    fig.add_trace(
                        go.Scatter(
                            x=replay_times,
                            y=replay_derivatives,
                            mode='lines',
                            name='播放曲线导数',
                            line=dict(color='red', width=2, dash='dash'),
                            legendgroup='replay',
                            showlegend=False
                        ),
                        row=row, col=1
                    )
                
                fig.update_xaxes(title_text="时间 (ms)", row=row, col=1)
                fig.update_yaxes(title_text="导数", row=row, col=1)
                row += 1
            
            # 阶段4：DTW对齐后的曲线（同时显示原始曲线进行对比）
            if stages.get('stage4_aligned'):
                stage4 = stages['stage4_aligned']
                aligned_times = stage4.get('aligned_times', [])
                record_values_aligned = stage4.get('record_values', [])
                replay_values_aligned = stage4.get('replay_values', [])
                
                # 获取原始曲线（用于对比）
                original_record_times = stage4.get('original_record_times', [])
                original_record_values = stage4.get('original_record_values', [])
                original_replay_times = stage4.get('original_replay_times', [])
                original_replay_values = stage4.get('original_replay_values', [])
                
                # 先显示原始曲线（使用原始时间，归一化到[0,1]便于对比）
                if len(original_record_times) > 0 and len(original_record_values) > 0:
                    # 归一化原始时间到[0,1]
                    if original_record_times[-1] != original_record_times[0]:
                        norm_original_times1 = (original_record_times - original_record_times[0]) / (original_record_times[-1] - original_record_times[0])
                    else:
                        norm_original_times1 = np.zeros_like(original_record_times)
                    
                    fig.add_trace(
                        go.Scatter(
                            x=norm_original_times1,
                            y=original_record_values,
                            mode='lines',
                            name='录制曲线（原始）',
                            line=dict(color='blue', width=2, dash='dot'),
                            legendgroup='record_original',
                            showlegend=(row == 1)
                        ),
                        row=row, col=1
                    )
                
                if len(original_replay_times) > 0 and len(original_replay_values) > 0:
                    # 归一化原始时间到[0,1]
                    if original_replay_times[-1] != original_replay_times[0]:
                        norm_original_times2 = (original_replay_times - original_replay_times[0]) / (original_replay_times[-1] - original_replay_times[0])
                    else:
                        norm_original_times2 = np.zeros_like(original_replay_times)
                    
                    fig.add_trace(
                        go.Scatter(
                            x=norm_original_times2,
                            y=original_replay_values,
                            mode='lines',
                            name='播放曲线（原始）',
                            line=dict(color='red', width=2, dash='dot'),
                            legendgroup='replay_original',
                            showlegend=(row == 1)
                        ),
                        row=row, col=1
                    )
                
                # 再显示对齐后的曲线（使用不同颜色：绿色和橙色）
                if len(aligned_times) > 0 and len(record_values_aligned) > 0:
                    fig.add_trace(
                        go.Scatter(
                            x=aligned_times,
                            y=record_values_aligned,
                            mode='lines',
                            name='录制曲线（对齐后）',
                            line=dict(color='green', width=2),  # 绿色表示对齐后的录制曲线
                            legendgroup='record_aligned',
                            showlegend=(row == 1)
                        ),
                        row=row, col=1
                    )
                
                if len(aligned_times) > 0 and len(replay_values_aligned) > 0:
                    fig.add_trace(
                        go.Scatter(
                            x=aligned_times,
                            y=replay_values_aligned,
                            mode='lines',
                            name='播放曲线（对齐后）',
                            line=dict(color='orange', width=2, dash='dash'),  # 橙色表示对齐后的播放曲线
                            legendgroup='replay_aligned',
                            showlegend=(row == 1)
                        ),
                        row=row, col=1
                    )
                
                fig.update_xaxes(title_text="归一化时间 [0, 1]", row=row, col=1)
                fig.update_yaxes(title_text="力度值", row=row, col=1)
                row += 1
            
            # 阶段5：上升沿和下降沿
            if stages.get('stage5_edges'):
                stage5 = stages['stage5_edges']
                
                # 上升沿
                if stage5.get('rising'):
                    rising = stage5['rising']
                    rising_times = rising.get('times', [])
                    rising_record = rising.get('record_values', [])
                    rising_replay = rising.get('replay_values', [])
                    
                    if len(rising_times) > 0 and len(rising_record) > 0:
                        fig.add_trace(
                            go.Scatter(
                                x=rising_times,
                                y=rising_record,
                                mode='lines',
                                name='录制曲线上升沿',
                                line=dict(color='blue', width=2),
                                legendgroup='record',
                                showlegend=False
                            ),
                            row=row, col=1
                        )
                    
                    if len(rising_times) > 0 and len(rising_replay) > 0:
                        fig.add_trace(
                            go.Scatter(
                                x=rising_times,
                                y=rising_replay,
                                mode='lines',
                                name='播放曲线上升沿',
                                line=dict(color='red', width=2, dash='dash'),
                                legendgroup='replay',
                                showlegend=False
                            ),
                            row=row, col=1
                        )
                    
                    fig.update_xaxes(title_text="归一化时间", row=row, col=1)
                    fig.update_yaxes(title_text="力度值", row=row, col=1)
                    row += 1
                
                # 下降沿
                if stage5.get('falling'):
                    falling = stage5['falling']
                    falling_times = falling.get('times', [])
                    falling_record = falling.get('record_values', [])
                    falling_replay = falling.get('replay_values', [])
                    
                    if len(falling_times) > 0 and len(falling_record) > 0:
                        fig.add_trace(
                            go.Scatter(
                                x=falling_times,
                                y=falling_record,
                                mode='lines',
                                name='录制曲线下降沿',
                                line=dict(color='blue', width=2),
                                legendgroup='record',
                                showlegend=False
                            ),
                            row=row, col=1
                        )
                    
                    if len(falling_times) > 0 and len(falling_replay) > 0:
                        fig.add_trace(
                            go.Scatter(
                                x=falling_times,
                                y=falling_replay,
                                mode='lines',
                                name='播放曲线下降沿',
                                line=dict(color='red', width=2, dash='dash'),
                                legendgroup='replay',
                                showlegend=False
                            ),
                            row=row, col=1
                        )
                    
                    fig.update_xaxes(title_text="归一化时间", row=row, col=1)
                    fig.update_yaxes(title_text="力度值", row=row, col=1)
            
            # 增加整体图表高度，每个子图约400px，加上间距
            fig.update_layout(
                height=450 * num_subplots,  # 增加每个子图的高度（从300增加到450）
                showlegend=True,
                title_text="曲线处理各阶段对比（播放曲线对齐到录制曲线）",
                hovermode="x unified",
                margin=dict(l=60, r=30, t=80, b=60)  # 增加边距，避免标签被裁剪
            )
            
            return fig
            
        except Exception as e:
            logger.error(f"❌ 可视化所有处理阶段失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def _extract_full_curve(self, note) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """
        提取完整曲线数据（不分割）
        
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
            
            # 注意：不在这里进行平滑处理
            # 平滑处理只在计算导数时使用（在align_full_curves中），
            # 最终输出的曲线应该保持原始特征（包括波峰和波谷）
            # 这样可以确保处理后的曲线与原曲线在波峰和波谷上保持一致
            
            return (times, values)
            
        except Exception as e:
            logger.error(f"❌ 提取完整曲线失败: {e}")
            return None
    
    def _compute_edge_similarity(self,
                                edge1: Tuple[np.ndarray, np.ndarray],
                                edge2: Tuple[np.ndarray, np.ndarray]) -> Dict[str, Any]:
        """
        计算两条边缘的相似度（边缘已经对齐，时间轴相同）
        
        Args:
            edge1: (times, values1) - 第一条边缘（时间轴已对齐）
            edge2: (times, values2) - 第二条边缘（时间轴已对齐）
        
        Returns:
            Dict[str, Any]: 包含相似度和差异统计
        """
        times, values1 = edge1
        _, values2 = edge2
        
        if len(values1) == 0 or len(values2) == 0:
            return {'similarity': 0.0, 'mean_diff': float('inf'), 'max_diff': float('inf')}
        
        # 归一化值到[0, 1]区间，消除绝对力度差异
        if values1.max() != values1.min():
            norm_values1 = (values1 - values1.min()) / (values1.max() - values1.min())
        else:
            norm_values1 = np.ones_like(values1) * 0.5
        
        if values2.max() != values2.min():
            norm_values2 = (values2 - values2.min()) / (values2.max() - values2.min())
        else:
            norm_values2 = np.ones_like(values2) * 0.5
        
        # 计算差异
        diff = np.abs(norm_values1 - norm_values2)
        mean_diff = np.mean(diff)
        max_diff = np.max(diff)
        
        # 计算相似度：1 - 平均差异（差异越小，相似度越高）
        similarity = max(0.0, 1.0 - mean_diff)
        
        return {
            'similarity': similarity,
            'mean_diff': mean_diff,
            'max_diff': max_diff,
            'alignment_method': 'pre_aligned'
        }
    
    def _compare_edges(self, edge1: Tuple[np.ndarray, np.ndarray], 
                      edge2: Tuple[np.ndarray, np.ndarray]) -> Dict[str, Any]:
        """
        使用基于导数的DTW对齐对比两条边缘（上升沿或下降沿）
        
        流程：
        1. 使用DerivativeDTWAligner对齐两条边缘
        2. 基于对齐后的曲线计算相似度
        
        Args:
            edge1: (times1, values1) - 第一条边缘
            edge2: (times2, values2) - 第二条边缘
        
        Returns:
            Dict[str, Any]: 包含相似度和差异统计
        """
        times1, values1 = edge1
        times2, values2 = edge2
        
        if len(times1) == 0 or len(times2) == 0:
            return {'similarity': 0.0, 'mean_diff': float('inf'), 'max_diff': float('inf')}
        
        try:
            # 1. 使用基于导数的DTW对齐
            alignment_result = self.derivative_dtw_aligner.align_edges(edge1, edge2)
            
            if alignment_result is None:
                logger.warning("⚠️ 基于导数的DTW对齐失败")
                return {
                    'similarity': 0.0,
                    'mean_diff': float('inf'),
                    'max_diff': float('inf'),
                    'alignment_method': 'derivative_dtw_failed'
                }
            
            # 2. 提取对齐后的曲线
            aligned_times = alignment_result['aligned_times']
            aligned_values1 = alignment_result['aligned_values1']
            aligned_values2 = alignment_result['aligned_values2']
            
            # 3. 归一化值到[0, 1]区间，消除绝对力度差异
            #    注意：这里是对对齐后的值进行归一化，而不是对齐前的值
            if aligned_values1.max() != aligned_values1.min():
                norm_values1 = (aligned_values1 - aligned_values1.min()) / (aligned_values1.max() - aligned_values1.min())
            else:
                norm_values1 = np.ones_like(aligned_values1) * 0.5
            
            if aligned_values2.max() != aligned_values2.min():
                norm_values2 = (aligned_values2 - aligned_values2.min()) / (aligned_values2.max() - aligned_values2.min())
            else:
                norm_values2 = np.ones_like(aligned_values2) * 0.5
            
            # 4. 计算差异（在对齐后的曲线上）
            diff = np.abs(norm_values1 - norm_values2)
            mean_diff = np.mean(diff)
            max_diff = np.max(diff)
            
            # 5. 计算相似度：1 - 平均差异（差异越小，相似度越高）
            similarity = max(0.0, 1.0 - mean_diff)
            
            # 6. 也可以使用DTW距离作为相似度的参考
            #    DTW距离越小，表示导数序列越相似
            dtw_distance = alignment_result['dtw_distance']
            
            return {
                'similarity': similarity,
                'mean_diff': mean_diff,
                'max_diff': max_diff,
                'dtw_distance': dtw_distance,
                'aligned_times': aligned_times,
                'aligned_values1': norm_values1,
                'aligned_values2': norm_values2,
                'alignment_method': 'derivative_dtw',
                'alignment_path': alignment_result['alignment_path']
            }
            
        except Exception as e:
            logger.error(f"❌ 基于导数的DTW对比失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'similarity': 0.0,
                'mean_diff': float('inf'),
                'max_diff': float('inf'),
                'alignment_method': 'derivative_dtw_error'
            }

