#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
条形统计图生成器模块

专门用于生成各种条形统计图，包括按键延时分析条形图等。
"""

import logging
import traceback
import numpy as np
import plotly.graph_objects as go
from collections import defaultdict
from typing import List, Dict, Any, Tuple


logger = logging.getLogger(__name__)


class BarChartGenerator:
    """条形统计图生成器类"""

    def __init__(self):
        """初始化条形图生成器"""
        pass

    def generate_single_algorithm_offset_alignment_plots(self, single_algorithm, piano_analysis_backend) -> List[Dict[str, Any]]:
        """
        生成单算法模式的偏移对齐分析条形图

        Args:
            single_algorithm: 单个算法数据集
            piano_analysis_backend: PianoAnalysisBackend实例，用于访问辅助方法

        Returns:
            List[Dict[str, Any]]: 包含4个独立图表的字典列表
        """
        try:
            # 数据预处理（基于精确匹配对数据）
            processed_data = self._preprocess_key_stats_data(None, single_algorithm, piano_analysis_backend)

            if not processed_data['key_ids']:
                logger.warning("没有有效的精确匹配对数据，无法生成柱状图")
                empty_fig = piano_analysis_backend.plot_generator._create_empty_plot("没有有效的精确匹配对数据")
                return [{'title': title, 'figure': empty_fig} for title in
                       ['中位数偏移', '均值偏移', '标准差', '方差']]

            # 生成图表
            plots = self._create_offset_alignment_plots(processed_data, piano_analysis_backend)

            logger.info(f"单算法偏移对齐分析条形图生成成功，包含 {len(processed_data['key_ids'])} 个键位")
            return plots

        except Exception as e:
            logger.error(f"单算法偏移对齐分析条形图生成失败: {e}")
            logger.error(traceback.format_exc())
            empty_fig = piano_analysis_backend.plot_generator._create_empty_plot(f"生成失败: {str(e)}")
            return [{'title': title, 'figure': empty_fig} for title in
                   ['中位数偏移', '均值偏移', '标准差', '方差']]

    def _preprocess_key_stats_data(self, unused_param, single_algorithm, piano_analysis_backend) -> Dict[str, Any]:
        """
        预处理按键统计数据（基于精确匹配对数据）

        Args:
            unused_param: 未使用的参数（保持接口兼容性）
            single_algorithm: 单个算法数据集
            piano_analysis_backend: PianoAnalysisBackend实例

        Returns:
            Dict[str, Any]: 处理后的数据
        """
        # 获取精确匹配对数据
        precision_offset_data = self._get_precision_offset_data(single_algorithm)
        if not precision_offset_data:
            return self._create_empty_chart_data()

        # 按键位分组数据
        key_groups = self._group_data_by_key_id(precision_offset_data)

        # 计算各键位统计信息
        key_stats = self._calculate_key_statistics(key_groups)

        # 计算总体统计信息
        overall_stats = self._calculate_overall_statistics(single_algorithm, piano_analysis_backend)

        # 准备图表数据
        return self._prepare_chart_data(key_stats, overall_stats)

    def _create_offset_alignment_plots(self, data: Dict[str, Any], piano_analysis_backend) -> List[Dict[str, Any]]:
        """
        创建偏移对齐分析的4个独立图表

        Args:
            data: 预处理后的数据
            piano_analysis_backend: PianoAnalysisBackend实例

        Returns:
            List[Dict[str, Any]]: 包含4个独立图表的字典列表
        """
        if not data.get('matched_indices'):
            return []

        # 提取匹配数据
        matched_data = self._extract_matched_data(data)

        # 定义图表配置
        chart_configs = [
            ('中位数偏移', matched_data['median'], '#1f77b4', '中位数偏移 (ms)'),
            ('均值偏移', matched_data['mean'], '#ff7f0e', '均值偏移 (ms)'),
            ('标准差', matched_data['std'], '#2ca02c', '标准差 (ms)'),
            ('方差', matched_data['variance'], '#9467bd', '方差 (ms²)')
        ]

        # 创建图表
        plots = []
        for title, values, color, y_title in chart_configs:
            fig = self._create_single_bar_chart(
                matched_data['key_ids'], values, f'匹配-{title.split()[0]}',
                color, y_title
            )
            plots.append({'title': title, 'figure': fig})

        # 添加未匹配数据
        if data.get('unmatched_indices'):
            self._add_unmatched_data_to_plots(
                plots, data['key_ids'], data['median_values'], data['mean_values'],
                data['std_values'], data['variance_values'], data['unmatched_indices']
            )

        # 统一设置图表布局
        self._apply_chart_layout(plots, data['min_key_id'], data['max_key_id'])

        return plots

    def _extract_matched_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """提取匹配的数据"""
        matched_indices = data['matched_indices']
        key_ids = data['key_ids']
        median_values = data['median_values']
        mean_values = data['mean_values']
        std_values = data['std_values']
        variance_values = data['variance_values']

        return {
            'key_ids': [key_ids[i] for i in matched_indices],
            'median': [median_values[i] for i in matched_indices],
            'mean': [mean_values[i] for i in matched_indices],
            'std': [std_values[i] for i in matched_indices],
            'variance': [variance_values[i] for i in matched_indices]
        }

    def _apply_chart_layout(self, plots: List[Dict[str, Any]], min_key_id: int, max_key_id: int):
        """统一应用图表布局"""
        for plot in plots:
            fig = plot['figure']
            fig.update_layout(
                height=600,
                showlegend=False,
                margin=dict(l=100, r=150, t=80, b=80)
            )
            fig.update_xaxes(
                title_text="键位ID",
                range=[min_key_id - 1, max_key_id + 1]
            )

    def _create_single_bar_chart(self, x_data: List[int], y_data: List[float], name: str,
                                color: str, y_title: str) -> go.Figure:
        """
        创建单个条形图

        Args:
            x_data: x轴数据（键位ID）
            y_data: y轴数据（统计值）
            name: 图例名称
            color: 条形颜色
            y_title: y轴标题

        Returns:
            go.Figure: Plotly图表对象
        """
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=x_data,
            y=y_data,
            name=name,
            marker_color=color,
            opacity=0.8,
            width=1.0,
            text=[f'{val:.2f}' for val in y_data],
            textposition='outside',
            textfont=dict(size=10),
            hovertemplate=f'键位: %{{x}}<br>{y_title.split()[0]}: %{{y:.2f}}{y_title.split()[-1]}<br>状态: 匹配<extra></extra>',
            showlegend=False
        ))

        fig.update_yaxes(title_text=y_title)
        return fig

    def _add_unmatched_data_to_plots(self, plots: List[Dict[str, Any]], key_ids: List[int],
                                    median_values: List[float], mean_values: List[float],
                                    std_values: List[float], variance_values: List[float],
                                    unmatched_indices: List[int]):
        """
        将未匹配数据添加到所有图表中

        Args:
            plots: 图表列表
            key_ids: 键位ID列表
            median_values: 中位数列表
            mean_values: 均值列表
            std_values: 标准差列表
            variance_values: 方差列表
            unmatched_indices: 未匹配数据的索引
        """
        unmatched_key_ids = [key_ids[i] for i in unmatched_indices]
        unmatched_median = [median_values[i] for i in unmatched_indices]
        unmatched_mean = [mean_values[i] for i in unmatched_indices]
        unmatched_std = [std_values[i] for i in unmatched_indices]
        unmatched_variance = [variance_values[i] for i in unmatched_indices]

        # 将未匹配数据添加到对应的图表中
        plot_data = [
            (plots[0]['figure'], unmatched_median, '未匹配-中位数', '#d62728'),
            (plots[1]['figure'], unmatched_mean, '未匹配-均值', '#9467bd'),
            (plots[2]['figure'], unmatched_std, '未匹配-标准差', '#8c564b'),
            (plots[3]['figure'], unmatched_variance, '未匹配-方差', '#bcbd22')
        ]

        for fig, y_data, name, color in plot_data:
            fig.add_trace(go.Bar(
                x=unmatched_key_ids,
                y=y_data,
                name=name,
                marker_color=color,
                opacity=0.8,
                width=1.0,
                text=[f'{val:.2f}' for val in y_data],
                textposition='outside',
                textfont=dict(size=10),
                hovertemplate=f'键位: %{{x}}<br>{name.split("-")[1]}: %{{y:.2f}}ms<br>状态: 未匹配<extra></extra>',
                showlegend=False
            ))

    def _get_precision_offset_data(self, single_algorithm) -> List[Dict[str, Any]]:
        """获取精确匹配对数据"""
        try:
            return single_algorithm.analyzer.get_precision_offset_alignment_data()
        except Exception as e:
            logger.warning(f"获取精确匹配对数据失败: {e}")
            return []

    def _create_empty_chart_data(self) -> Dict[str, Any]:
        """创建空的图表数据"""
        return {
            'key_ids': [],
            'median_values': [],
            'mean_values': [],
            'std_values': [],
            'variance_values': [],
            'status_list': [],
            'matched_indices': [],
            'unmatched_indices': [],
            'min_key_id': 1,
            'max_key_id': 90,
            'overall_mean': 0,
            'overall_std': 0,
            'overall_variance': 0
        }

    def _group_data_by_key_id(self, precision_offset_data: List[Dict[str, Any]]) -> Dict[int, List[float]]:
        """按键位ID分组数据"""
        from collections import defaultdict

        key_groups = defaultdict(list)
        for item in precision_offset_data:
            key_id = item.get('key_id')
            if key_id is None:
                continue
            corrected_offset = item.get('corrected_offset', 0)
            # 将0.1ms单位转换为ms
            delay_ms = corrected_offset / 10.0
            key_groups[key_id].append(delay_ms)

        return key_groups

    def _calculate_key_statistics(self, key_groups: Dict[int, List[float]]) -> Dict[str, Any]:
        """计算各键位的统计信息"""
        key_ids = []
        median_values = []
        mean_values = []
        std_values = []
        variance_values = []
        status_list = []

        for key_id in sorted(key_groups.keys()):
            delays = key_groups[key_id]
            if not delays:
                continue

            key_ids.append(key_id)
            median_values.append(float(np.median(delays)))
            mean_values.append(float(np.mean(delays)))
            std_values.append(float(np.std(delays)))
            variance_values.append(float(np.var(delays)))
            status_list.append('matched')

        if not key_ids:
            raise ValueError("没有有效的偏移对齐数据")

        # 计算键位范围（按键ID从1开始）
        min_key_id = min(key_ids) if key_ids else 1
        max_key_id = max(key_ids) if key_ids else 90

        # 计算匹配索引（当前所有数据都是匹配的）
        matched_indices = list(range(len(key_ids)))
        unmatched_indices = []

        return {
            'key_ids': key_ids,
            'median_values': median_values,
            'mean_values': mean_values,
            'std_values': std_values,
            'variance_values': variance_values,
            'status_list': status_list,
            'matched_indices': matched_indices,
            'unmatched_indices': unmatched_indices,
            'min_key_id': min_key_id,
            'max_key_id': max_key_id
        }

    def _calculate_overall_statistics(self, single_algorithm, piano_analysis_backend) -> Dict[str, float]:
        """计算总体统计信息"""
        overall_mean = 0.0
        overall_std = 0.0
        overall_variance = 0.0

        if piano_analysis_backend and hasattr(single_algorithm, 'metadata') and hasattr(single_algorithm.metadata, 'filename'):
            try:
                overall_mean_0_1ms = piano_analysis_backend.get_mean_absolute_error(single_algorithm.metadata.filename)  # 单位：0.1ms
                overall_mean = overall_mean_0_1ms / 10.0  # 转换为ms

                overall_std_0_1ms = piano_analysis_backend.get_standard_deviation(single_algorithm.metadata.filename)  # 单位：0.1ms
                overall_std = overall_std_0_1ms / 10.0  # 转换为ms

                overall_variance_0_1ms_squared = piano_analysis_backend.get_variance(single_algorithm.metadata.filename)  # 单位：(0.1ms)²
                overall_variance = overall_variance_0_1ms_squared / 100.0  # 转换为ms²
            except Exception as e:
                logger.warning(f"无法计算总体统计信息: {e}，使用默认值0")

        return {
            'overall_mean': overall_mean,
            'overall_std': overall_std,
            'overall_variance': overall_variance
        }

    def _prepare_chart_data(self, key_stats: Dict[str, Any], overall_stats: Dict[str, float]) -> Dict[str, Any]:
        """准备图表数据"""
        return {
            **key_stats,
            **overall_stats
        }
