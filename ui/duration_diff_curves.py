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
    """按键曲线对比绘图器
    
    提供统一的 Note 对比绘图逻辑，包括：
    1. Aftertouch 曲线绘制
    2. 锤击点标记（支持多锤击显示）
    3. 自动计算时间对齐
    4. 可视化 KeySplitter 的拆分建议
    """
    
    def __init__(self):
        self.key_splitter = KeySplitter() 
    
    def add_note_traces(self, fig, note, label, color, time_offset=0.0, show_all_hammers=True):
        """向现有图表添加音符追踪（Aftertouch 和 Hammers）"""
        if note.after_touch is not None and not note.after_touch.empty:
            times = [(t + note.offset) / 10.0 - time_offset for t in note.after_touch.index]
            values = note.after_touch.values.tolist()
            fig.add_trace(go.Scattergl(
                x=times, y=values, name=label, 
                line=dict(color=color, width=2),
                hovertemplate=f'{label}<br>时间: %{{x:.2f}}ms<br>触后值: %{{y}}<extra></extra>'
            ))
            
            # 添加锤击点
            if hasattr(note, 'hammers') and note.hammers is not None and not note.hammers.empty:
                h_times = []
                h_vels = []
                
                # 是否显示所有锤击点
                indices = range(len(note.hammers)) if show_all_hammers else [0]
                for i in indices:
                    vel = note.hammers.values[i]
                    if vel > 0:
                        t = (note.hammers.index[i] + note.offset) / 10.0 - time_offset
                        h_times.append(t)
                        h_vels.append(vel)
                
                if h_times:
                    fig.add_trace(go.Scattergl(
                        x=h_times, y=h_vels, mode='markers',
                        name=f'{label}锤击',
                        marker=dict(symbol='diamond', size=10, color=color, line=dict(color='white', width=1)),
                        hovertemplate=f'<b>{label}锤击</b><br>时间: %{{x:.2f}}ms<br>锤速: %{{y}}<extra></extra>'
                    ))

    def draw_split_analysis(self, fig, matched_pair, label_a='录制', label_b='播放'):
        """如果匹配对存在重大的持续时间差异，绘制拆分分析建议"""
        rec_note, rep_note, match_type, _ = matched_pair
        
        # 只有在持续时间差异显著时才尝试分析（比值 > 1.8）
        ratio = max(rec_note.duration_ms / rep_note.duration_ms, rep_note.duration_ms / rec_note.duration_ms)
        if ratio < 1.8:
            return None
            
        # 确定长短音符
        if rec_note.duration_ms <= rep_note.duration_ms:
            short, long = rec_note, rep_note
            label_long = label_b
        else:
            short, long = rep_note, rec_note
            label_long = label_a
            
        analysis = self.key_splitter.analyze_split_possibility(
            short_note=short, long_note=long,
            short_duration=short.duration_ms, long_duration=long.duration_ms
        )
        
        if analysis and analysis.get('best_candidate'):
            best = analysis['best_candidate']
            # 在长音符所属的曲线上绘制分割点
            fig.add_trace(go.Scatter(
                x=[best['time']], y=[best['value']],
                mode='markers', name='建议分割点',
                marker=dict(symbol='star-triangle-up', size=15, color='green', line=dict(color='white', width=2)),
                hovertemplate=f"建议分割位置<br>时间: {best['time']:.2f}ms<br>原因: {best['reasons'][0]}<extra></extra>"
            ))
            return analysis
        return None

    def create_comparison_figure(self, matched_pair, delay_ms=0.0):
        """创建完整的对比图（包含原始和对齐追踪）"""
        rec_note, rep_note, _, _ = matched_pair
        fig = go.Figure()
        
        # 绘制
        self.add_note_traces(fig, rec_note, '录制', 'blue')
        self.add_note_traces(fig, rep_note, '播放', 'red', time_offset=delay_ms)
        
        # 尝试添加拆分分析
        self.draw_split_analysis(fig, matched_pair)
        
        fig.update_layout(
            xaxis_title="时间 (ms)", yaxis_title="触后值 / 锤速",
            hovermode='closest', height=450,
            margin=dict(l=40, r=40, t=40, b=40)
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

