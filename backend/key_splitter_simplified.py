#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
按键拆分模块

核心逻辑：
1. 硬约束：分割点必须在 [录制keyoff, 下一个锤击点) 之间
2. 必须是拐点：前降后升
3. 选择标准：在所有拐点中选择触后值最小的
"""

from typing import List, Tuple, Optional, Dict
import logging

logger = logging.getLogger(__name__)


class KeySplitter:
    """按键拆分器 - 简化版"""
    
    def analyze_split_possibility(self, short_note, long_note,
                                  short_duration: float,
                                  long_duration: float) -> Optional[Dict]:
        """
        分析是否需要拆分以及候选分割点
        
        Args:
            short_note: 短数据（参考数据）
            long_note: 长数据（要拆分的合并数据）
            short_duration: 短数据持续时间
            long_duration: 长数据持续时间
            
        Returns:
            Dict or None: 分析结果，包含best_candidate等信息
        """
        try:
            # 提取数据
            short_times, short_values = self._extract_aftertouch(short_note)
            long_times, long_values = self._extract_aftertouch(long_note)
            
            if not short_times or not long_times:
                logger.warning("数据提取失败")
                return None
            
            # 关键时间点
            short_keyoff = short_times[-1]  # 短数据的keyoff
            long_hammer_times = self._extract_hammer_times(long_note)
            
            # 检查是否有足够的锤击点
            if not long_hammer_times or len(long_hammer_times) < 2:
                logger.info(f"长数据锤击点不足2个（当前{len(long_hammer_times) if long_hammer_times else 0}个），无法使用拆分")
                return None
            
            # 找到在短数据keyoff之后的第一个hammer（这才是真正的"下一个锤击"）
            next_hammer = None
            for hammer_time in long_hammer_times:
                if hammer_time > short_keyoff:
                    next_hammer = hammer_time
                    break
            
            # 如果没有找到在keyoff之后的hammer，说明无法拆分
            if next_hammer is None:
                logger.warning(f"未找到在短数据keyoff({short_keyoff:.1f}ms)之后的锤击点")
                return None
            
            logger.info(f"拆分分析: 短数据keyoff={short_keyoff:.1f}ms, "
                       f"长数据下一个锤击={next_hammer:.1f}ms")
            
            # 搜索范围已经确定为 (short_keyoff, next_hammer)
            # 由于next_hammer是通过 > short_keyoff筛选出来的，所以范围必然有效
            
            # 在硬约束范围内查找候选点（在长数据中查找）
            candidates = self._find_candidates(
                long_times, long_values, 
                short_keyoff, next_hammer
            )
            
            if not candidates:
                logger.info("未找到合适的分割点")
                return None
            
            return {
                'short_duration': short_duration,
                'long_duration': long_duration,
                'short_keyoff': short_keyoff,
                'next_hammer': next_hammer,
                'long_hammer_times': long_hammer_times,
                'candidates': candidates,
                'best_candidate': candidates[0] if candidates else None
            }
            
        except Exception as e:
            logger.error(f"分析拆分可能性失败: {e}", exc_info=True)
            return None
    
    def _find_candidates(self, times: List[float], values: List[float],
                        min_time: float, max_time: float) -> List[Dict]:
        """
        在硬约束范围内查找候选分割点
        
        选择逻辑：在时间范围内的所有拐点中，选择触后值最小的点
        
        Args:
            times: 时间序列(ms)
            values: 触后值序列
            min_time: 最小时间（录制keyoff）
            max_time: 最大时间（下一个锤击点）
            
        Returns:
            List[Dict]: 候选点列表（所有拐点），按触后值大小排序
        """
        # 找到范围内的索引
        search_indices = [i for i, t in enumerate(times) if min_time < t < max_time]
        
        if not search_indices:
            logger.warning(f"范围内无数据点: {min_time:.1f}ms ~ {max_time:.1f}ms")
            return []
        
        logger.info(f"搜索范围: [{min_time:.1f}ms, {max_time:.1f}ms], "
                   f"共{len(search_indices)}个点")
        
        # 检测拐点（前降后升）
        turning_points = self._detect_turning_points(times, values)
        logger.info(f"检测到 {len(turning_points)} 个拐点")
        
        # 筛选候选点：范围内的所有拐点
        candidates = []
        for idx in search_indices:
            # 必须是拐点
            if idx not in turning_points:
                continue
            
            candidates.append({
                'index': idx,
                'time': times[idx],
                'value': values[idx],
                'is_turning': True,
                'reasons': [f"是拐点(前降后升)"]
            })
        
        if not candidates:
            # 退而求其次：没有拐点时，选择触后值最小的点
            logger.warning("在搜索范围内未找到拐点，退而求其次选择触后值最小的点")
            
            # 从搜索范围内选择触后值最小的点
            fallback_candidates = []
            for idx in search_indices:
                fallback_candidates.append({
                    'index': idx,
                    'time': times[idx],
                    'value': values[idx],
                    'is_turning': False,  # 标记为非拐点
                    'reasons': [f"退而求其次: 触后值最小"]
                })
            
            if not fallback_candidates:
                logger.warning("搜索范围内无任何点")
                return []
            
            # 按触后值排序，选择触后值最小的
            fallback_candidates.sort(key=lambda x: x['value'])
            
            logger.info(f"使用后备策略，选择触后值最小的点: "
                       f"时间={fallback_candidates[0]['time']:.1f}ms, "
                       f"触后值={fallback_candidates[0]['value']:.1f}")
            
            return fallback_candidates
        
        # 有拐点：按触后值排序，选择触后值最小的拐点
        candidates.sort(key=lambda x: x['value'])
        
        logger.info(f"找到 {len(candidates)} 个拐点候选（完全满足条件），"
                   f"最佳: 时间={candidates[0]['time']:.1f}ms, "
                   f"触后值={candidates[0]['value']:.1f}")
        
        return candidates
    
    def _detect_turning_points(self, times: List[float], 
                               values: List[float]) -> List[int]:
        """
        检测拐点（前一直下降→后一直上升）
        
        拐点定义：
        - 前面窗口的平均斜率必须 < 0（下降）
        - 后面窗口的平均斜率必须 > 0（上升）
        - 如果存在平滑区间，选择平滑区间的最后一个点
        
        Args:
            times: 时间序列
            values: 值序列
            
        Returns:
            List[int]: 拐点索引列表
        """
        if len(values) < 10:
            return []
        
        # 计算斜率
        slopes = []
        for i in range(len(values) - 1):
            dt = times[i+1] - times[i]
            dv = values[i+1] - values[i]
            slopes.append(dv / dt if dt > 0 else 0)
        
        turning_points = []
        window = 4  # 检查窗口大小
        
        for i in range(window, len(slopes) - window):
            # 前面窗口的平均斜率
            prev_slopes = slopes[i-window:i]
            prev_avg = sum(prev_slopes) / len(prev_slopes)
            
            # 后面窗口的平均斜率（考虑可能的平滑区）
            # 先找到平滑区的结束位置
            plateau_end = i
            for j in range(i, min(i + window, len(slopes))):
                if abs(slopes[j]) < 0.2:  # 平滑阈值
                    plateau_end = j + 1  # 记录平滑区的下一个位置
                else:
                    break
            
            # 从平滑区结束后开始检查上升趋势
            next_start = plateau_end
            if next_start + window > len(slopes):
                continue
            
            next_slopes = slopes[next_start:next_start + window]
            next_avg = sum(next_slopes) / len(next_slopes)
            
            # 判断：前面下降 且 后面上升
            if prev_avg < -0.2 and next_avg > 0.2:
                # 选择平滑区的最后一个点（如果有平滑区）
                turning_point = plateau_end - 1 if plateau_end > i else i
                turning_points.append(turning_point)

        return turning_points
    
    def _extract_hammer_times(self, note) -> Optional[List[float]]:
        """提取锤击时间点（只提取锤速>0的点）"""
        try:
            if note.hammers is None or len(note.hammers) == 0:
                return None
            
            hammer_times = []
            for i in range(len(note.hammers)):
                if note.hammers.values[i] > 0:
                    time_ms = (note.hammers.index[i] + note.offset) / 10.0
                    hammer_times.append(time_ms)
            
            hammer_times.sort()
            return hammer_times if hammer_times else None
            
        except Exception as e:
            logger.error(f"提取锤击时间失败: {e}")
            return None
    
    def _extract_aftertouch(self, note) -> Tuple[List[float], List[float]]:
        """提取aftertouch数据"""
        try:
            if not hasattr(note, 'after_touch') or note.after_touch is None or len(note.after_touch) == 0:
                return [], []
            
            times = [(t + note.offset) / 10.0 for t in note.after_touch.index]
            values = note.after_touch.values.tolist()
            return times, values
            
        except Exception as e:
            logger.error(f"提取aftertouch失败: {e}")
            return [], []

