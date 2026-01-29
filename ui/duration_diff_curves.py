#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
持续时间差异匹配对曲线绘制模块

负责绘制持续时间差异显著的匹配对的原始曲线，包括：
- aftertouch 曲线
- hammers 锤击时间点标记
"""

import plotly.graph_objs as go
from plotly.subplots import make_subplots
from typing import Optional, Tuple, Dict
import logging

logger = logging.getLogger(__name__)


from backend.key_splitter_simplified import KeySplitter



class DurationDiffCurvePlotter:
    """持续时间差异曲线绘制器（通用版本，支持录制和播放数据的任意组合）"""
    
    def __init__(self):
        """初始化绘制器"""
        self.key_splitter = KeySplitter() 
    
    def create_comparison_figure(self, note_a, note_b, key_id: int,
                                 duration_a: float, duration_b: float,
                                 duration_ratio: float,
                                 label_a: str = '数据A', label_b: str = '数据B',
                                 force_draw_split_point: bool = False):
        """
        创建两个音符数据的曲线对比图（单图显示）
        
        Args:
            note_a: 第一个音符数据
            note_b: 第二个音符数据
            key_id: 按键ID
            duration_a: 第一个数据持续时间(ms)
            duration_b: 第二个数据持续时间(ms)
            duration_ratio: 持续时间比值
            label_a: 第一个数据的标签（默认'数据A'）
            label_b: 第二个数据的标签（默认'数据B'）
            
        Returns:
            Tuple[go.Figure, Optional[Dict]]: (对比图, 分割分析结果)
        """
        try:
            # 创建单个图表
            fig = go.Figure()
            
            # 绘制第一个数据（蓝色）
            self._add_note_curve_to_figure(fig, note_a, color='blue', name=label_a)
            
            # 绘制第二个数据（红色）
            self._add_note_curve_to_figure(fig, note_b, color='red', name=label_b)
            
            # 分析并绘制候选分割点（如果持续时间差异显著或强制绘制）
            split_analysis = None
            if self.key_splitter and (duration_ratio >= 2.0 or force_draw_split_point):
                split_analysis = self._analyze_and_draw_split_points(
                    fig, note_a, note_b, 
                    duration_a, duration_b,
                    label_a, label_b
                )
            
            # 更新布局
            title_text = f'按键 {key_id} - 持续时间差异对比 ({label_a}: {duration_a:.1f}ms, {label_b}: {duration_b:.1f}ms, 比值: {duration_ratio:.2f})'
            if split_analysis and split_analysis.get('best_candidate'):
                best = split_analysis['best_candidate']
                title_text += f'<br><sub>建议分割点: {best["time"]:.1f}ms (触后值: {best["value"]:.1f})</sub>'
            
            fig.update_layout(
                title=title_text,
                xaxis_title="时间 (ms)",
                yaxis_title="触后值",
                height=600,
                showlegend=True,
                hovermode='closest',
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                )
            )
            
            return fig, split_analysis
            
        except Exception as e:
            logger.error(f"创建持续时间差异对比图失败: {e}")
            return self._create_error_figure(str(e)), None
    
    def _add_note_curve_to_figure(self, fig, note, color: str, name: str):
        """
        添加单个音符的曲线和锤击点到图表
        
        Args:
            fig: plotly figure对象
            note: 音符数据
            color: 曲线颜色
            name: 曲线名称前缀
        """
        # 提取aftertouch数据
        after_touch_times, after_touch_values = self._extract_aftertouch_data(note)
        
        if after_touch_times is None or len(after_touch_times) == 0:
            # 添加无数据提示
            fig.add_annotation(
                text=f"{name}数据：无aftertouch数据",
                xref="paper",
                yref="paper",
                x=0.5, y=0.5,
                showarrow=False,
                font=dict(size=14, color='gray')
            )
            return
        
        # 添加aftertouch曲线
        fig.add_trace(
            go.Scatter(
                x=after_touch_times,
                y=after_touch_values,
                mode='lines',
                name=f'{name}-触后曲线',
                line=dict(color=color, width=2),
                showlegend=True,
                hovertemplate=f'{name}<br>时间: %{{x:.2f}}ms<br>触后值: %{{y}}<extra></extra>'
            )
        )
        
        # 添加锤击时间点标记
        self._add_hammer_markers_to_figure(fig, note, after_touch_times, after_touch_values, 
                                          color, name)
    
    def _extract_aftertouch_data(self, note) -> Tuple[Optional[list], Optional[list]]:
        """
        提取aftertouch数据
        
        Args:
            note: 音符数据
            
        Returns:
            Tuple[时间列表(ms), 值列表]
        """
        try:
            if not hasattr(note, 'after_touch') or note.after_touch is None:
                return None, None
            
            if len(note.after_touch) == 0:
                return None, None
            
            # 转换时间为毫秒 (原始单位为0.1ms)
            times_ms = [(t + note.offset) / 10.0 for t in note.after_touch.index]
            values = note.after_touch.values.tolist()
            
            return times_ms, values
            
        except Exception as e:
            logger.error(f"提取aftertouch数据失败: {e}")
            return None, None
    
    def _add_hammer_markers_to_figure(self, fig, note, after_touch_times, after_touch_values,
                                      color: str, name: str):
        """
        添加锤击时间点标记到图表
        
        Args:
            fig: plotly figure对象
            note: 音符数据
            after_touch_times: aftertouch时间列表
            after_touch_values: aftertouch值列表
            color: 标记颜色
            name: 标记名称前缀
        """
        try:
            if not hasattr(note, 'hammers') or note.hammers is None:
                return
            
            if len(note.hammers) == 0 or len(note.hammers.values) == 0:
                return
            
            # 提取所有锤击时间点
            hammer_times = []
            hammer_values = []
            hammer_velocities = []
            
            for i in range(len(note.hammers)):
                hammer_velocity = note.hammers.values[i]

                # 过滤掉锤速为0的锤击点
                if hammer_velocity == 0:
                    continue

                hammer_time_ms = (note.hammers.index[i] + note.offset) / 10.0

                # 在aftertouch曲线上找到对应的值
                after_touch_value = self._find_closest_aftertouch_value(
                    hammer_time_ms, after_touch_times, after_touch_values
                )

                hammer_times.append(hammer_time_ms)
                hammer_values.append(after_touch_value)
                hammer_velocities.append(hammer_velocity)
            
            # 添加锤击点标记
            hover_texts = [
                f'{name}-锤击点<br>时间: {t:.2f}ms<br>触后值: {v}<br>锤速: {vel}'
                for t, v, vel in zip(hammer_times, hammer_values, hammer_velocities)
            ]
            
            fig.add_trace(
                go.Scatter(
                    x=hammer_times,
                    y=hammer_values,
                    mode='markers',
                    name=f'{name}-锤击点',
                    marker=dict(
                        color=color,
                        size=10,
                        symbol='diamond',
                        line=dict(color='white', width=1)
                    ),
                    showlegend=True,
                    hovertemplate='%{text}<extra></extra>',
                    text=hover_texts
                )
            )
            
        except Exception as e:
            logger.error(f"添加锤击点标记失败: {e}")
    
    def _find_closest_aftertouch_value(self, hammer_time: float, 
                                       after_touch_times: list, 
                                       after_touch_values: list) -> float:
        """
        在aftertouch曲线上找到最接近锤击时间的触后值
        
        Args:
            hammer_time: 锤击时间(ms)
            after_touch_times: aftertouch时间列表(ms)
            after_touch_values: aftertouch值列表
            
        Returns:
            最接近的触后值
        """
        if not after_touch_times or not after_touch_values:
            return 0
        
        # 找到最接近的时间点索引
        min_diff = float('inf')
        closest_idx = 0
        
        for i, time in enumerate(after_touch_times):
            diff = abs(time - hammer_time)
            if diff < min_diff:
                min_diff = diff
                closest_idx = i
        
        return after_touch_values[closest_idx]
    
    def _analyze_and_draw_split_points(self, fig, note_a, note_b,
                                       duration_a: float, duration_b: float,
                                       label_a: str = '数据A', label_b: str = '数据B') -> Optional[Dict]:
        """
        分析并绘制候选分割点
        
        Args:
            fig: plotly figure对象
            note_a: 第一个音符数据
            note_b: 第二个音符数据
            duration_a: 第一个数据持续时间
            duration_b: 第二个数据持续时间
            label_a: 第一个数据的标签
            label_b: 第二个数据的标签
            
        Returns:
            Dict or None: 分析结果
        """
        try:
            # 确定哪个是短数据，哪个是长数据
            if duration_a <= duration_b:
                short_note = note_a
                long_note = note_b
                short_duration = duration_a
                long_duration = duration_b
                short_data_type = label_a
                long_data_type = label_b
            else:
                short_note = note_b
                long_note = note_a
                short_duration = duration_b
                long_duration = duration_a
                short_data_type = label_b
                long_data_type = label_a
            
            # 执行拆分分析（使用新的通用接口）
            analysis = self.key_splitter.analyze_split_possibility(
                short_note=short_note,
                long_note=long_note,
                short_duration=short_duration,
                long_duration=long_duration
            )
            
            if not analysis or not analysis.get('candidates'):
                logger.info("未找到候选分割点")
                return None
            
            # 提取长数据用于绘制
            long_times, long_values = self._extract_aftertouch_data(long_note)
            if not long_times:
                return None
            
            # 绘制关键时间线和范围
            short_keyoff = analysis.get('short_keyoff')
            next_hammer = analysis.get('next_hammer')
            long_hammer_times = analysis.get('long_hammer_times')
            
            if short_keyoff:
                self._draw_reference_time_line(fig, short_keyoff, long_values, f"短数据({short_data_type})keyoff")
            
            if next_hammer:
                self._draw_reference_time_line(fig, next_hammer, long_values, "下一个锤击点")
            
            # 绘制搜索范围
            if short_keyoff and next_hammer:
                fig.add_vrect(
                    x0=short_keyoff,
                    x1=next_hammer,
                    fillcolor='rgba(0, 128, 0, 0.1)',
                    layer='below',
                    line_width=0,
                    annotation_text="搜索范围",
                    annotation_position="top left"
                )
            
            # 绘制候选分割点
            self._draw_split_point_candidates(
                fig, analysis['candidates'], long_times, long_values
            )
            
            return analysis
            
        except Exception as e:
            logger.error(f"分析和绘制分割点失败: {e}", exc_info=True)
            return None
    
    def _draw_reference_time_line(self, fig, reference_time: float, values: list, label: str = "参考时间"):
        """
        绘制参考时间线（录制数据的keyoff）
        
        Args:
            fig: plotly figure对象
            reference_time: 参考时间(ms)
            values: 值列表（用于确定y轴范围）
        """
        if not values:
            return
        
        y_min = min(values)
        y_max = max(values)
        
        color = 'green' if 'keyoff' in label else 'purple'
        fig.add_trace(
            go.Scatter(
                x=[reference_time, reference_time],
                y=[y_min, y_max],
                mode='lines',
                name=label,
                line=dict(
                    color=color,
                    width=2,
                    dash='dash'
                ),
                showlegend=True,
                hovertemplate=f'{label}: {reference_time:.2f}ms<extra></extra>'
            )
        )
    
    def _draw_split_point_candidates(self, fig, candidates: list,
                                     times: list, values: list):
        """
        绘制最佳分割点

        Args:
            fig: plotly figure对象
            candidates: 候选点列表
            times: 时间列表
            values: 值列表
        """
        if not candidates:
            return

        # 只绘制最佳分割点
        best = candidates[0]
        self._draw_single_split_point(
            fig, best, times, values,
            color='red',
            size=15,
            symbol='star-triangle-up',
            name='最佳分割点'
        )
    
    def _draw_single_split_point(self, fig, candidate: Dict,
                                 times: list, values: list,
                                 color: str, size: int, symbol: str, name: str):
        """
        绘制单个分割点
        
        Args:
            fig: plotly figure对象
            candidate: 候选点信息
            times: 时间列表
            values: 值列表
            color: 标记颜色
            size: 标记大小
            symbol: 标记符号
            name: 标记名称
        """
        idx = candidate['index']
        
        # 构建hover文本
        hover_text = f"{name}<br>" \
                    f"时间: {candidate['time']:.2f}ms<br>" \
                    f"触后值: {candidate['value']:.1f}<br>"
        
        if 'reasons' in candidate and candidate['reasons']:
            hover_text += "原因:<br>"
            for reason in candidate['reasons']:
                hover_text += f"  • {reason}<br>"
        
        fig.add_trace(
            go.Scatter(
                x=[times[idx]],
                y=[values[idx]],
                mode='markers',
                name=name,
                marker=dict(
                    color=color,
                    size=size,
                    symbol=symbol,
                    line=dict(color='white', width=2)
                ),
                showlegend=True,
                hovertemplate=hover_text + '<extra></extra>'
            )
        )
    
    def _create_error_figure(self, error_msg: str) -> go.Figure:
        """
        创建错误提示图
        
        Args:
            error_msg: 错误信息
            
        Returns:
            包含错误信息的空图
        """
        fig = go.Figure()
        fig.add_annotation(
            text=f"生成曲线失败: {error_msg}",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=16, color='red')
        )
        fig.update_layout(
            title="错误",
            height=600
        )
        return fig


def get_duration_diff_pairs_from_backend(backend, active_algorithms) -> list:
    """
    从后端获取持续时间差异数据
    
    Args:
        backend: 后端实例
        active_algorithms: 活动算法列表
        
    Returns:
        持续时间差异匹配对列表
    """
    try:
        duration_diff_pairs = []
        
        # 从算法中获取持续时间差异数据
        if active_algorithms:
            # 多算法模式
            for algorithm in active_algorithms:
                if hasattr(algorithm.analyzer, "note_matcher") and \
                   hasattr(algorithm.analyzer.note_matcher, "duration_diff_pairs"):
                    diff_pairs = algorithm.analyzer.note_matcher.duration_diff_pairs
                    if diff_pairs:
                        duration_diff_pairs.extend(diff_pairs)
        elif backend and hasattr(backend, "_get_current_analyzer"):
            # 单算法模式
            analyzer = backend._get_current_analyzer()
            if analyzer and hasattr(analyzer, "note_matcher") and \
               hasattr(analyzer.note_matcher, "duration_diff_pairs"):
                diff_pairs = analyzer.note_matcher.duration_diff_pairs
                if diff_pairs:
                    duration_diff_pairs.extend(diff_pairs)
        
        return duration_diff_pairs
        
    except Exception as e:
        logger.error(f"获取持续时间差异数据失败: {e}")
        return []

