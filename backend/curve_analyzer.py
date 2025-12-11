
"""
曲线分析器 - 使用DTW算法对齐after_touch曲线

面向对象设计，专注于DTW对齐算法
"""
import traceback
from typing import List, Tuple, Dict, Any, Optional, Callable
import numpy as np
from scipy.interpolate import interp1d
from scipy.ndimage import gaussian_filter1d
from dtw import dtw
from utils.logger import Logger

logger = Logger.get_logger()


class DTWCurveAligner:
    """
    DTW曲线对齐器 - 使用DTW算法对齐两条after_touch曲线
    
    对齐流程：
    1. 提取after_touch数据（时间和深度值）
    2. 归一化和对数变换
    3. 使用DTW找到对齐路径
    4. 根据对齐路径重新采样曲线，使两条曲线对齐
    5. 自动处理初始抖动和局部时间扭曲
    """
    
    def __init__(self, 
                 sampling_rate_ms: float = 1.0,
                 time_range_threshold_ms: float = 1000.0,
                 window_size_ratio: float = 0.5,
                 distance_metric: str = 'manhattan',
                 smooth_sigma: float = 1.0):
        """
        初始化DTW曲线对齐器
        
        Args:
            sampling_rate_ms: 重采样时间间隔（毫秒），默认1ms
            time_range_threshold_ms: 时间范围差异阈值（毫秒），超过此值认为不匹配
            window_size_ratio: DTW窗口大小比例（相对于最大持续时间），默认0.5（50%）
            distance_metric: 距离度量方式，可选：
                - 'euclidean': 欧式距离（默认，对抖动敏感）
                - 'manhattan': 曼哈顿距离（L1距离，对抖动更鲁棒）
                - 'chebyshev': 切比雪夫距离（关注最大差异）
                - 'gradient': 基于梯度的距离（关注变化趋势，对抖动最鲁棒）
            smooth_sigma: 高斯平滑参数（标准差），用于减少抖动影响，0表示不平滑
        """
        self.sampling_rate_ms = sampling_rate_ms
        self.time_range_threshold_ms = time_range_threshold_ms
        self.window_size_ratio = window_size_ratio
        self.distance_metric = distance_metric
        self.smooth_sigma = smooth_sigma
    
    def align_curves(self, 
                    record_note, 
                    replay_note) -> Optional[Dict[str, Any]]:
        """
        对齐两条after_touch曲线
        
        Args:
            record_note: 录制音符对象
            replay_note: 播放音符对象
        
        Returns:
            Dict[str, Any]: 对齐结果，包含：
                - time_points: 对齐后的时间点数组（ms）
                - record_curve: 对齐后的录制曲线值
                - replay_curve: 对齐后的播放曲线值
                - alignment_path: DTW对齐路径 [(i, j), ...]
                - alignment_method: 对齐方法（'dtw'）
                - before_alignment: 对齐前的数据（用于对比）
                如果对齐失败则返回None
        """
        try:
            # 1. 提取after_touch数据
            record_data = self._extract_curve_data(record_note)
            replay_data = self._extract_curve_data(replay_note)
            
            if record_data is None or replay_data is None:
                return None
            
            record_times, record_values = record_data
            replay_times, replay_values = replay_data
            
            # 2. 检查数据有效性
            if not self._validate_curve_data(record_times, record_values, replay_times, replay_values):
                return None
            
            # 3. 保存对齐前的数据（用于对比）
            before_alignment = {
                'record_times': record_times.copy(),
                'record_values': record_values.copy(),
                'replay_times': replay_times.copy(),
                'replay_values': replay_values.copy()
            }
            
            # 4. 预处理：归一化和对数变换
            record_values_processed = self._preprocess_curve(record_values)
            replay_values_processed = self._preprocess_curve(replay_values)
            
            # 5. 平滑处理（减少抖动影响）
            if self.smooth_sigma > 0:
                record_values_processed = self._smooth_curve(record_values_processed)
                replay_values_processed = self._smooth_curve(replay_values_processed)
            
            # 6. 使用DTW找到对齐路径
            alignment_result = self._perform_dtw_alignment(
                record_times, record_values_processed,
                replay_times, replay_values_processed
            )
            
            if alignment_result is None:
                logger.warning("⚠️ DTW对齐失败")
                return None
            
            alignment_path = alignment_result['alignment_path']
            dtw_distance = alignment_result['dtw_distance']
            
            # 7. 根据对齐路径重新采样曲线，使两条曲线对齐
            aligned_result = self._resample_by_alignment_path(
                record_times, record_values_processed,
                replay_times, replay_values_processed,
                alignment_path
            )
            
            if aligned_result is None:
                logger.warning("⚠️ 根据对齐路径重新采样失败")
                return None
            
            return {
                'time_points': aligned_result['time_points'],
                'record_curve': aligned_result['record_curve'],
                'replay_curve': aligned_result['replay_curve'],
                'alignment_path': alignment_path,
                'dtw_distance': dtw_distance,
                'alignment_method': 'dtw',
                'before_alignment': before_alignment
            }
            
        except Exception as e:
            logger.error(f"❌ 曲线对齐失败: {e}")
            logger.error(traceback.format_exc())
            return None
    
    def _extract_curve_data(self, note) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """
        提取after_touch曲线数据
        
        Args:
            note: 音符对象
        
        Returns:
            Tuple[np.ndarray, np.ndarray]: (时间数组, 值数组)，单位：ms
            如果提取失败则返回None
        """
        try:
            if not hasattr(note, 'after_touch') or note.after_touch is None or note.after_touch.empty:
                logger.warning("⚠️ 音符没有after_touch数据")
                return None
            
            # 提取时间和值
            # after_touch.index是相对时间（0.1ms单位），note.offset是绝对偏移（0.1ms单位）
            times = (note.after_touch.index + note.offset) / 10.0  # 转换为ms
            values = note.after_touch.values
            
            # 转换为numpy数组
            times = np.array(times)
            values = np.array(values)
            
            # 检查数据有效性
            if len(times) == 0 or len(values) == 0:
                logger.warning("⚠️ after_touch数据为空")
                return None
            
            if len(times) != len(values):
                logger.warning(f"⚠️ 时间和值数组长度不匹配: times={len(times)}, values={len(values)}")
                return None
            
            return times, values
            
        except Exception as e:
            logger.error(f"❌ 提取曲线数据失败: {e}")
            return None
    
    def _validate_curve_data(self,
                             record_times: np.ndarray,
                             record_values: np.ndarray,
                             replay_times: np.ndarray,
                             replay_values: np.ndarray) -> bool:
        """
        验证曲线数据有效性
        
        Args:
            record_times: 录制时间数组
            record_values: 录制值数组
            replay_times: 播放时间数组
            replay_values: 播放值数组
        
        Returns:
            bool: 数据是否有效
        """
        # 检查数据点数量
        if len(record_times) < 2 or len(replay_times) < 2:
            logger.warning("⚠️ 曲线数据点不足（少于2个点）")
            return False
        
        # 检查时间范围差异
        record_duration = record_times[-1] - record_times[0]
        replay_duration = replay_times[-1] - replay_times[0]
        max_duration = max(record_duration, replay_duration)
        
        if max_duration <= 0:
            logger.warning("⚠️ 曲线持续时间无效")
            return False
        
        time_diff = abs(record_duration - replay_duration)
        threshold = max(self.time_range_threshold_ms, max_duration * 0.5)
        
        if time_diff > threshold:
            logger.warning(f"⚠️ 时间范围差异过大: 录制={record_duration:.1f}ms, 播放={replay_duration:.1f}ms, 差异={time_diff:.1f}ms, 阈值={threshold:.1f}ms")
            return False
        
        # 检查NaN和Inf
        if np.any(~np.isfinite(record_times)) or np.any(~np.isfinite(record_values)):
            logger.warning("⚠️ 录制曲线包含NaN或Inf值")
            return False
        
        if np.any(~np.isfinite(replay_times)) or np.any(~np.isfinite(replay_values)):
            logger.warning("⚠️ 播放曲线包含NaN或Inf值")
            return False
        
        return True
    
    def _preprocess_curve(self, values: np.ndarray) -> np.ndarray:
        """
        预处理曲线：归一化和对数变换
        
        Args:
            values: 原始曲线值
        
        Returns:
            np.ndarray: 预处理后的曲线值（0-1范围）
        """
        # 1. 归一化到0-1范围
        normalized = self._normalize_values(values)
        
        # 2. 应用对数变换（log1p = log(1+x)）
        log_values = np.log1p(normalized)
        
        # 3. 重新归一化到0-1范围
        normalized_log = self._normalize_values(log_values)
        
        return normalized_log
    
    def _normalize_values(self, values: np.ndarray) -> np.ndarray:
        """
        归一化值到0-1范围
        
        Args:
            values: 原始值数组
        
        Returns:
            np.ndarray: 归一化后的值数组（0-1范围）
        """
        if len(values) == 0:
            return values
        
        values = np.array(values)
        min_val = np.min(values)
        max_val = np.max(values)
        
        if max_val > min_val:
            normalized = (values - min_val) / (max_val - min_val)
        else:
            # 所有值相同，归一化为0
            normalized = np.zeros_like(values)
        
        # 处理NaN和Inf
        normalized = np.nan_to_num(normalized, nan=0.0, posinf=1.0, neginf=0.0)
        
        return normalized
    
    def _smooth_curve(self, values: np.ndarray) -> np.ndarray:
        """
        使用高斯滤波平滑曲线，减少抖动影响
        
        Args:
            values: 曲线值数组
        
        Returns:
            np.ndarray: 平滑后的曲线值
        """
        if len(values) < 3 or self.smooth_sigma <= 0:
            return values
        
        try:
            smoothed = gaussian_filter1d(values, sigma=self.smooth_sigma)
            # 处理NaN和Inf
            smoothed = np.nan_to_num(smoothed, nan=0.0, posinf=1.0, neginf=0.0)
            return smoothed
        except Exception as e:
            logger.warning(f"⚠️ 曲线平滑失败: {e}，使用原始值")
            return values
    
    def _perform_dtw_alignment(self,
                               record_times: np.ndarray,
                               record_values: np.ndarray,
                               replay_times: np.ndarray,
                               replay_values: np.ndarray) -> Optional[Dict[str, Any]]:
        """
        执行DTW对齐，找到对齐路径
        
        注意：DTW对齐只使用值维度（曲线深度值），时间对齐由DTW路径本身处理。
        这样可以避免时间维度在距离计算中占主导地位。
        
        Args:
            record_times: 录制时间点（ms）- 仅用于记录，不参与距离计算
            record_values: 录制曲线值（已预处理）
            replay_times: 播放时间点（ms）- 仅用于记录，不参与距离计算
            replay_values: 播放曲线值（已预处理）
        
        Returns:
            Dict[str, Any]: DTW对齐结果，包含：
                - alignment_path: 对齐路径 [(i, j), ...]
                - dtw_distance: DTW距离
            如果对齐失败则返回None
        """
        try:
            # 根据距离度量类型准备数据
            if self.distance_metric == 'gradient':
                # 基于梯度的距离：使用一阶差分（变化趋势）
                record_features = self._compute_gradient(record_values)
                replay_features = self._compute_gradient(replay_values)
            else:
                # 其他距离度量：直接使用值
                record_features = record_values
                replay_features = replay_values
            
            # 将值重塑为列向量（DTW库要求）
            record_features_2d = record_features.reshape(-1, 1)
            replay_features_2d = replay_features.reshape(-1, 1)
            
            # 获取距离度量字符串（dtw库支持：'euclidean', 'manhattan', 'squared_euclidean'等）
            dist_method_str = self._get_distance_method_string()
            
            # 先尝试无窗口约束的DTW（更灵活，能处理更大的时间扭曲）
            try:
                alignment = dtw(
                    record_features_2d, 
                    replay_features_2d, 
                    keep_internals=True,
                    distance_only=False,
                    dist_method=dist_method_str
                )
                alignment_path = list(zip(alignment.index1, alignment.index2))
                dtw_distance = alignment.distance
                
                logger.debug(f"✅ DTW对齐成功（无窗口，{self.distance_metric}距离）: 路径长度={len(alignment_path)}, 距离={dtw_distance:.2f}")
                
                return {
                    'alignment_path': alignment_path,
                    'dtw_distance': dtw_distance
                }
                
            except Exception as e1:
                logger.warning(f"⚠️ DTW对齐失败（无窗口）: {e1}")
                
                # 尝试使用窗口约束（限制对齐范围，避免过度扭曲）
                try:
                    max_duration = max(
                        record_times[-1] - record_times[0],
                        replay_times[-1] - replay_times[0]
                    )
                    window_size = min(int(max_duration * self.window_size_ratio), 500)  # 最大500ms
                    
                    alignment = dtw(
                        record_features_2d,
                        replay_features_2d,
                        keep_internals=True,
                        distance_only=False,
                        dist_method=dist_method_str,
                        window_type='sakoechiba',
                        window_args={'window_size': window_size}
                    )
                    alignment_path = list(zip(alignment.index1, alignment.index2))
                    dtw_distance = alignment.distance
                    
                    logger.debug(f"✅ DTW对齐成功（窗口={window_size}ms，{self.distance_metric}距离）: 路径长度={len(alignment_path)}, 距离={dtw_distance:.2f}")
                    
                    return {
                        'alignment_path': alignment_path,
                        'dtw_distance': dtw_distance
                    }
                    
                except Exception as e2:
                    logger.warning(f"⚠️ DTW对齐失败（有窗口）: {e2}")
                    return None
                    
        except Exception as e:
            logger.error(f"❌ DTW对齐执行失败: {e}")
            logger.error(traceback.format_exc())
            return None
    
    def _compute_gradient(self, values: np.ndarray) -> np.ndarray:
        """
        计算曲线的一阶差分（梯度），用于基于变化趋势的距离度量
        
        Args:
            values: 曲线值数组
        
        Returns:
            np.ndarray: 梯度数组（长度减1）
        """
        if len(values) < 2:
            return np.array([0.0])
        
        # 计算一阶差分
        gradient = np.diff(values)
        
        # 归一化梯度（避免量纲问题）
        if np.max(np.abs(gradient)) > 1e-10:
            gradient = gradient / np.max(np.abs(gradient))
        
        # 处理边界：在两端补0，保持长度一致
        gradient_padded = np.concatenate([[0.0], gradient, [0.0]])
        
        return gradient_padded
    
    def _get_distance_method_string(self) -> str:
        """
        根据距离度量类型返回dtw库支持的距离度量字符串
        
        dtw库支持的距离度量：
        - 'euclidean': 欧式距离（L2）
        - 'manhattan': 曼哈顿距离（L1）
        - 'squared_euclidean': 平方欧式距离
        
        注意：对于'gradient'和'chebyshev'，我们通过数据预处理来实现
        （gradient在数据准备阶段已处理，chebyshev使用manhattan作为近似）
        
        Returns:
            str: dtw库支持的距离度量字符串
        """
        if self.distance_metric == 'manhattan':
            return 'manhattan'
        elif self.distance_metric == 'gradient':
            # 梯度距离：数据已经转换为梯度，使用manhattan距离计算梯度差异
            return 'manhattan'
        elif self.distance_metric == 'chebyshev':
            # 切比雪夫距离：dtw库不支持，使用manhattan作为近似（对抖动也较鲁棒）
            return 'manhattan'
        else:
            # 默认：欧式距离
            return 'euclidean'
    
    def _resample_by_alignment_path(self,
                                    record_times: np.ndarray,
                                    record_values: np.ndarray,
                                    replay_times: np.ndarray,
                                    replay_values: np.ndarray,
                                    alignment_path: List[Tuple[int, int]]) -> Optional[Dict[str, Any]]:
        """
        根据DTW对齐路径重新采样曲线，使两条曲线对齐
        
        对齐策略：
        1. 根据对齐路径，找到对齐后的时间点
        2. 对每条曲线进行插值，得到对齐后的值
        3. 自动处理初始抖动和局部时间扭曲
        
        Args:
            record_times: 录制时间点（ms）
            record_values: 录制曲线值（已预处理）
            replay_times: 播放时间点（ms）
            replay_values: 播放曲线值（已预处理）
            alignment_path: DTW对齐路径 [(i, j), ...]
        
        Returns:
            Dict[str, Any]: 对齐后的结果，包含：
                - time_points: 对齐后的时间点数组（ms）
                - record_curve: 对齐后的录制曲线值
                - replay_curve: 对齐后的播放曲线值
            如果重新采样失败则返回None
        """
        try:
            if not alignment_path:
                logger.warning("⚠️ 对齐路径为空")
                return None
            
            # 1. 根据对齐路径构建对齐后的时间点
            # 策略：使用对齐路径中对应的时间点，取平均值或使用统一采样
            aligned_time_points = []
            aligned_record_values = []
            aligned_replay_values = []
            
            for i, j in alignment_path:
                if i < len(record_times) and j < len(replay_times):
                    # 使用对齐路径中对应的时间点
                    # 可以取平均值，或者使用录制时间作为基准
                    # 这里使用录制时间作为基准，因为录制是参考标准
                    aligned_time = record_times[i]
                    aligned_time_points.append(aligned_time)
                    aligned_record_values.append(record_values[i])
                    aligned_replay_values.append(replay_values[j])
            
            if len(aligned_time_points) < 2:
                logger.warning("⚠️ 对齐后的时间点不足")
                return None
            
            # 转换为numpy数组
            aligned_time_points = np.array(aligned_time_points)
            aligned_record_values = np.array(aligned_record_values)
            aligned_replay_values = np.array(aligned_replay_values)
            
            # 2. 创建统一的时间采样点（用于最终输出）
            # 使用对齐后的时间范围，按采样率重新采样
            min_time = np.min(aligned_time_points)
            max_time = np.max(aligned_time_points)
            uniform_time_points = np.arange(
                min_time,
                max_time + self.sampling_rate_ms,
                self.sampling_rate_ms
            )
            
            # 3. 插值到统一时间点
            # 由于对齐路径可能不是严格单调的，需要先处理重复时间点
            record_curve = self._interpolate_to_uniform_time(
                aligned_time_points, aligned_record_values, uniform_time_points
            )
            replay_curve = self._interpolate_to_uniform_time(
                aligned_time_points, aligned_replay_values, uniform_time_points
            )
            
            return {
                'time_points': uniform_time_points,
                'record_curve': record_curve,
                'replay_curve': replay_curve
            }
            
        except Exception as e:
            logger.error(f"❌ 根据对齐路径重新采样失败: {e}")
            logger.error(traceback.format_exc())
            return None
    
    def _interpolate_to_uniform_time(self,
                                     original_times: np.ndarray,
                                     original_values: np.ndarray,
                                     target_times: np.ndarray) -> np.ndarray:
        """
        插值曲线到统一时间点
        
        Args:
            original_times: 原始时间点（可能不单调）
            original_values: 原始值
            target_times: 目标时间点（均匀采样）
        
        Returns:
            np.ndarray: 插值后的值数组
        """
        try:
            # 处理重复时间点：取平均值
            unique_times = []
            unique_values = []
            
            # 按时间排序
            sort_idx = np.argsort(original_times)
            sorted_times = original_times[sort_idx]
            sorted_values = original_values[sort_idx]
            
            # 合并相同时间点的值（取平均值）
            i = 0
            while i < len(sorted_times):
                current_time = sorted_times[i]
                time_group = [sorted_values[i]]
                
                # 收集相同时间点的所有值
                j = i + 1
                while j < len(sorted_times) and abs(sorted_times[j] - current_time) < 1e-6:
                    time_group.append(sorted_values[j])
                    j += 1
                
                # 取平均值
                unique_times.append(current_time)
                unique_values.append(np.mean(time_group))
                
                i = j
            
            unique_times = np.array(unique_times)
            unique_values = np.array(unique_values)
            
            if len(unique_times) < 2:
                # 数据点不足，返回零数组
                return np.zeros_like(target_times)
            
            # 检查NaN和Inf
            valid_mask = np.isfinite(unique_times) & np.isfinite(unique_values)
            if not np.all(valid_mask):
                unique_times = unique_times[valid_mask]
                unique_values = unique_values[valid_mask]
            
            if len(unique_times) < 2:
                return np.zeros_like(target_times)
            
            # 线性插值
            interp_func = interp1d(
                unique_times,
                unique_values,
                kind='linear',
                fill_value=0.0,
                bounds_error=False,
                assume_sorted=True
            )
            
            interpolated = interp_func(target_times)
            
            # 处理NaN和Inf
            interpolated = np.nan_to_num(interpolated, nan=0.0, posinf=1.0, neginf=0.0)
            
            return interpolated
            
        except Exception as e:
            logger.error(f"❌ 曲线插值失败: {e}")
            return np.zeros_like(target_times)


class CurvePair:
    """
    曲线对类 - 封装一对录制和播放曲线的对齐结果
    """
    
    def __init__(self, record_note, replay_note, record_idx: int, replay_idx: int):
        """
        初始化曲线对
        
        Args:
            record_note: 录制音符对象
            replay_note: 播放音符对象
            record_idx: 录制索引
            replay_idx: 播放索引
        """
        self.record_note = record_note
        self.replay_note = replay_note
        self.record_idx = record_idx
        self.replay_idx = replay_idx
        self.key_id = record_note.id if record_note else None
        
        # 对齐结果
        self.alignment_result: Optional[Dict[str, Any]] = None
        self.alignment_status: str = "pending"  # pending, success, failed
    
    def get_alignment_result(self) -> Optional[Dict[str, Any]]:
        """获取对齐结果"""
        return self.alignment_result
    
    def get_result_dict(self) -> Dict[str, Any]:
        """获取结果字典（用于序列化）"""
        return {
            'record_idx': self.record_idx,
            'replay_idx': self.replay_idx,
            'key_id': self.key_id,
            'status': self.alignment_status,
            'alignment_result': self.alignment_result
        }


class CurveAnalyzer:
    """
    曲线分析器 - 主类，协调曲线对齐
    """
    
    def __init__(self,
                 sampling_rate_ms: float = 1.0,
                 time_range_threshold_ms: float = 1000.0):
        """
        初始化曲线分析器
        
        Args:
            sampling_rate_ms: 重采样时间间隔（毫秒）
            time_range_threshold_ms: 时间范围差异阈值（毫秒）
        """
        self.aligner = DTWCurveAligner(
            sampling_rate_ms=sampling_rate_ms,
            time_range_threshold_ms=time_range_threshold_ms
        )
    
    def align_pairs(self,
                   matched_pairs: List[Tuple[int, int, Any, Any]]) -> List[CurvePair]:
        """
        对齐匹配对列表
        
        Args:
            matched_pairs: 匹配对列表，格式为 [(record_idx, replay_idx, record_note, replay_note), ...]
        
        Returns:
            List[CurvePair]: 对齐结果列表
        """
        results = []
        
        logger.info(f"🔄 开始对齐 {len(matched_pairs)} 对曲线...")
        
        success_count = 0
        for record_idx, replay_idx, record_note, replay_note in matched_pairs:
            pair = CurvePair(record_note, replay_note, record_idx, replay_idx)
            
            try:
                # 执行对齐
                alignment_result = self.aligner.align_curves(record_note, replay_note)
                
                if alignment_result is None:
                    pair.alignment_status = "failed"
                    logger.debug(f"⚠️ 对齐失败: record_idx={record_idx}, replay_idx={replay_idx}")
                else:
                    pair.alignment_result = alignment_result
                    pair.alignment_status = "success"
                    success_count += 1
                    
            except Exception as e:
                logger.error(f"❌ 对齐配对失败 (record_idx={record_idx}, replay_idx={replay_idx}): {e}")
                pair.alignment_status = "failed"
            
            results.append(pair)
        
        logger.info(f"✅ 对齐完成: 成功={success_count}/{len(matched_pairs)}, 失败={len(matched_pairs) - success_count}")
        
        return results
    
    def get_alignment_statistics(self, curve_pairs: List[CurvePair]) -> Dict[str, Any]:
        """
        获取对齐统计信息
        
        Args:
            curve_pairs: 曲线对列表
        
        Returns:
            Dict[str, Any]: 统计结果
        """
        successful_pairs = [p for p in curve_pairs if p.alignment_status == "success"]
        
        if not successful_pairs:
            return {
                'total_pairs': len(curve_pairs),
                'successful_pairs': 0,
                'failed_pairs': len(curve_pairs),
                'success_rate': 0.0
            }
        
        # 计算平均DTW距离
        dtw_distances = []
        for pair in successful_pairs:
            if pair.alignment_result and 'dtw_distance' in pair.alignment_result:
                dtw_distances.append(pair.alignment_result['dtw_distance'])
        
        avg_dtw_distance = float(np.mean(dtw_distances)) if dtw_distances else 0.0
        
        return {
            'total_pairs': len(curve_pairs),
            'successful_pairs': len(successful_pairs),
            'failed_pairs': len(curve_pairs) - len(successful_pairs),
            'success_rate': len(successful_pairs) / len(curve_pairs) * 100.0,
            'average_dtw_distance': avg_dtw_distance
        }

