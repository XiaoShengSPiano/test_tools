#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
多算法图表生成器

负责生成支持多算法对比的图表，使用面向对象设计。
"""

from typing import List, Optional, Any, Dict
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import spmid
from spmid import spmid_plot
from backend.multi_algorithm_manager import AlgorithmDataset
from utils.logger import Logger

logger = Logger.get_logger()


class MultiAlgorithmPlotGenerator:
    """
    多算法图表生成器类
    
    负责生成支持多算法对比的图表，包括：
    - 瀑布图（多算法叠加显示）
    - 偏移对齐分析图（多算法并排柱状图）
    - 延时分布直方图（多算法叠加显示）
    """
    
    def __init__(self, data_filter=None):
        """
        初始化多算法图表生成器
        
        Args:
            data_filter: 数据过滤器实例（可选）
        """
        self.data_filter = data_filter
        logger.info("✅ MultiAlgorithmPlotGenerator初始化完成")
    
    def generate_multi_algorithm_waterfall_plot(
        self,
        algorithms: List[AlgorithmDataset],
        time_filter=None
    ) -> Any:
        """
        生成多算法瀑布图（按照原来的实现方式，叠加显示，不同算法有明确的范围区分）
        
        为每个算法分配不同的y_offset范围，确保即使颜色一样也能明确区分。
        使用原来的颜色映射方式（基于力度值的colormap）。
        
        Args:
            algorithms: 激活的算法数据集列表
            time_filter: 时间过滤器实例（可选）
            
        Returns:
            go.Figure: Plotly图表对象
        """
        if not algorithms:
            logger.warning("⚠️ 没有激活的算法，无法生成多算法瀑布图")
            return self._create_empty_plot("没有激活的算法")
        
        try:
            # 过滤出就绪的算法
            ready_algorithms = [alg for alg in algorithms if alg.is_ready()]
            if not ready_algorithms:
                logger.warning("⚠️ 没有就绪的算法，无法生成多算法瀑布图")
                return self._create_empty_plot("没有就绪的算法")
            
            logger.info(f"📊 开始生成多算法瀑布图，共 {len(ready_algorithms)} 个算法")
            
            # 为每个算法分配y_offset范围（确保明确区分）
            # 基础offset：record=0.0, play=0.2
            # 每个算法分配100的y_offset范围，确保不重叠且范围明确
            base_offsets = {
                'record': 0.0,
                'play': 0.2
            }
            algorithm_y_range = 100  # 每个算法分配的y轴范围（键位ID范围是1-90，所以100足够）
            
            # 收集所有数据点用于全局归一化
            all_values = []
            all_bars_by_algorithm = []
            
            for alg_idx, algorithm in enumerate(ready_algorithms):
                algorithm_name = algorithm.metadata.algorithm_name
                
                # 获取算法的数据
                record_data = algorithm.record_data
                replay_data = algorithm.replay_data
                
                if not record_data or not replay_data:
                    logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有数据，跳过")
                    continue
                
                # 应用时间过滤（如果提供）
                if time_filter:
                    # TODO: 实现时间过滤逻辑
                    pass
                
                # 应用按键过滤（如果提供）
                if self.data_filter and self.data_filter.key_filter:
                    record_data = self._apply_key_filter(record_data, self.data_filter.key_filter)
                    replay_data = self._apply_key_filter(replay_data, self.data_filter.key_filter)
                
                # 计算当前算法的y_offset（每个算法偏移100个单位，确保范围明确）
                current_y_offset = alg_idx * algorithm_y_range
                
                # 收集当前算法的数据点
                algorithm_bars = []
                
                for df, label in [(record_data, 'record'), (replay_data, 'play')]:
                    if df is None:
                        continue
                    
                    # 使用spmid模块获取条形段数据
                    bars = spmid_plot.get_bar_segments2(df)
                    
                    y_offset = base_offsets[label] + current_y_offset
                    
                    for t_on, t_off, key_id, value, index in bars:
                        algorithm_bars.append({
                            't_on': t_on,
                            't_off': t_off,
                            'key_id': key_id + y_offset,
                            'value': value,
                            'label': label,
                            'index': index,
                            'algorithm_name': algorithm_name,
                            'original_key_id': key_id  # 保存原始key_id用于悬停显示
                        })
                        all_values.append(value)
                
                all_bars_by_algorithm.append({
                    'algorithm': algorithm,
                    'bars': algorithm_bars,
                    'y_offset': current_y_offset
                })
            
            if not all_bars_by_algorithm:
                logger.warning("⚠️ 没有有效的数据点，无法生成瀑布图")
                return self._create_empty_plot("没有有效的数据点")
            
            # 全局归一化力度值（用于颜色映射，使用原来的colormap方式）
            if all_values:
                vmin = min(all_values)
                vmax = max(all_values)
            else:
                vmin, vmax = 0, 1
            
            # 使用原来的colormap（tab20b）
            import matplotlib.pyplot as plt
            cmap = plt.colormaps['tab20b']
            norm = lambda v: (v - vmin) / (vmax - vmin) if vmax > vmin else 0.5
            
            # 创建图表
            fig = go.Figure()
            
            # 按照原来的方式为每个条形段添加trace
            for alg_data in all_bars_by_algorithm:
                algorithm = alg_data['algorithm']
                bars = alg_data['bars']
                algorithm_name = algorithm.metadata.algorithm_name
                current_y_offset = alg_data['y_offset']
                
                # 为每个条形段添加trace（按照原来的方式）
                for bar in bars:
                    # 计算颜色（使用原来的colormap方式）
                    color = 'rgba' + str(tuple(int(255*x) for x in cmap(norm(bar['value']))[:3]) + (0.9,))
                    
                    # 创建trace名称（包含算法名称）
                    trace_name = f"{algorithm_name} - {bar['label']}"
                    
                    # 添加水平线段（按照原来的方式）
                    fig.add_trace(go.Scatter(
                        x=[bar['t_on']/10, bar['t_off']/10],
                        y=[bar['key_id'], bar['key_id']],
                        mode='lines',
                        line=dict(color=color, width=3),
                        name=trace_name,
                        showlegend=False,  # 不显示图例（因为trace太多）
                        legendgroup=algorithm_name,  # 同一算法的trace分组
                        hoverinfo='text',
                        text=(
                            f'算法: {algorithm_name}<br>'
                            f'类型: {bar["label"]}<br>'
                            f'键位: {bar["original_key_id"]}<br>'
                            f'力度: {bar["value"]}<br>'
                            f'按下: {bar["t_on"]/10:.1f}ms<br>'
                            f'释放: {bar["t_off"]/10:.1f}ms<br>'
                            f'索引: {bar["index"]}'
                        ),
                        customdata=[[
                            bar['t_on']/10, 
                            bar['t_off']/10, 
                            int(bar['original_key_id']), 
                            bar['value'], 
                            bar['label'],
                            int(bar['index']),
                            algorithm_name
                        ]]
                    ))
            
            # 添加色条（按照原来的方式）
            colorbar_trace = go.Scatter(
                x=[None], y=[None],
                mode='markers',
                marker=dict(
                    colorscale='Viridis',
                    cmin=vmin,
                    cmax=vmax,
                    color=[vmin, vmax],
                    colorbar=dict(
                        title='Hammer',
                        thickness=20,
                        len=0.8
                    ),
                    showscale=True
                ),
                showlegend=False,
                hoverinfo='none'
            )
            fig.add_trace(colorbar_trace)
            
            # 计算y轴范围（包含所有算法的范围）
            max_y = max([max([b['key_id'] for b in alg_data['bars']]) for alg_data in all_bars_by_algorithm]) if all_bars_by_algorithm else 90
            min_y = min([min([b['key_id'] for b in alg_data['bars']]) for alg_data in all_bars_by_algorithm]) if all_bars_by_algorithm else 1
            
            # 确保y轴最小值至少为1（按键ID不可能为负数）
            min_y = max(1, min_y)
            
            # 设置图表布局（按照原来的方式）
            # 根据算法数量动态调整高度，但限制在一屏内（每个算法约300-400px）
            # 确保不需要滚动条就能看到所有算法
            base_height = 1200  # 基础高度
            height_per_algorithm = 350  # 每个算法增加的高度
            calculated_height = base_height + (len(ready_algorithms) - 1) * height_per_algorithm
            # 限制最大高度，避免过高
            max_height = 1800
            final_height = min(calculated_height, max_height)
            
            fig.update_layout(
                title='多算法瀑布图对比（每个算法有独立的y轴范围，滚轮缩放，左键拖动）',
                xaxis_title='Time (ms)',
                yaxis_title='Key ID (每个算法偏移100个单位，确保范围明确)',
                yaxis=dict(
                    showgrid=True,
                    gridcolor='lightgray',
                    gridwidth=1,
                    range=[min_y, max_y + 10]  # 设置y轴范围，确保不显示负数，并留出一些边距
                ),
                height=final_height,  # 适合一屏显示的高度
                width=2000,  # 设置一个较大的宽度值，实际宽度由CSS样式控制（100%），确保占满容器
                template='simple_white',
                autosize=False,  # 使用固定高度和宽度，宽度由CSS样式控制（通过布局中的width: 100%）
                margin=dict(l=60, r=60, t=100, b=60),
                showlegend=False,  # 不显示图例（因为trace太多）
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(size=12),
                # 启用拖动功能（长按左键拖动）
                dragmode='pan'  # 默认启用拖动模式，可以通过工具栏切换到zoom模式
            )
            
            logger.info(f"✅ 多算法瀑布图生成成功，共 {len(ready_algorithms)} 个算法")
            logger.info(f"📊 y轴范围: {min_y:.1f} - {max_y:.1f} (每个算法偏移100个单位)")
            return fig
            
        except Exception as e:
            logger.error(f"❌ 生成多算法瀑布图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._create_empty_plot(f"生成失败: {str(e)}")
    
    def _apply_key_filter(self, data: List, key_filter: set) -> List:
        """应用按键过滤"""
        if not key_filter:
            return data
        return [note for note in data if note.keyId in key_filter]
    
    def _hex_to_rgba(self, hex_color: str, alpha: float) -> str:
        """
        将十六进制颜色转换为rgba格式
        
        Args:
            hex_color: 十六进制颜色（如 '#1f77b4'）
            alpha: 透明度（0-1）
            
        Returns:
            str: rgba颜色字符串（如 'rgba(31, 119, 180, 0.8)'）
        """
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return f'rgba({r}, {g}, {b}, {alpha})'
    
    def generate_multi_algorithm_offset_alignment_plot(
        self,
        algorithms: List[AlgorithmDataset]
    ) -> Any:
        """
        生成多算法偏移对齐分析图（并排柱状图，不同颜色）
        
        为每个算法生成并排的柱状图，使用不同颜色区分，显示4个子图：
        - 中位数偏移
        - 均值偏移
        - 标准差
        - 方差
        
        Args:
            algorithms: 激活的算法数据集列表
            
        Returns:
            go.Figure: Plotly图表对象
        """
        if not algorithms:
            logger.warning("⚠️ 没有激活的算法，无法生成多算法偏移对齐分析图")
            return self._create_empty_plot("没有激活的算法")
        
        try:
            # 过滤出就绪的算法
            ready_algorithms = [alg for alg in algorithms if alg.is_ready()]
            if not ready_algorithms:
                logger.warning("⚠️ 没有就绪的算法，无法生成多算法偏移对齐分析图")
                return self._create_empty_plot("没有就绪的算法")
            
            logger.info(f"📊 开始生成多算法偏移对齐分析图，共 {len(ready_algorithms)} 个算法")
            
            # 为每个算法分配颜色（使用不同的颜色方案）
            colors = [
                '#1f77b4',  # 蓝色
                '#ff7f0e',  # 橙色
                '#2ca02c',  # 绿色
                '#d62728',  # 红色
                '#9467bd',  # 紫色
                '#8c564b',  # 棕色
                '#e377c2',  # 粉色
                '#7f7f7f'   # 灰色
            ]
            
            # 创建4个子图
            fig = make_subplots(
                rows=4, cols=1,
                subplot_titles=('中位数偏移', '均值偏移', '标准差', '方差'),
                vertical_spacing=0.05,
                row_heights=[0.25, 0.25, 0.25, 0.25]
            )
            
            # 收集所有算法的数据
            all_algorithms_data = []
            
            for alg_idx, algorithm in enumerate(ready_algorithms):
                algorithm_name = algorithm.metadata.algorithm_name
                
                if not algorithm.analyzer:
                    logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有分析器，跳过")
                    continue
                
                # 获取偏移对齐数据（需要从analyzer中获取）
                # 由于get_offset_alignment_data是backend的方法，我们需要直接调用analyzer的方法
                try:
                    # 从analyzer获取偏移数据
                    offset_data = algorithm.analyzer.get_offset_alignment_data()
                    invalid_offset_data = algorithm.analyzer.get_invalid_notes_offset_analysis()
                    
                    # 按按键ID分组并计算统计信息
                    from collections import defaultdict
                    import numpy as np
                    
                    # 按按键ID分组有效匹配的偏移数据（只使用keyon_offset）
                    key_groups = defaultdict(list)
                    for item in offset_data:
                        key_id = item.get('key_id', 'N/A')
                        keyon_offset_abs = abs(item.get('keyon_offset', 0))  # 只使用keyon_offset
                        key_groups[key_id].append(keyon_offset_abs)
                    
                    # 提取数据
                    algorithm_key_ids = []
                    algorithm_median = []
                    algorithm_mean = []
                    algorithm_std = []
                    algorithm_variance = []
                    
                    for key_id, offsets in key_groups.items():
                        if offsets:
                            try:
                                key_id_int = int(key_id)
                                algorithm_key_ids.append(key_id_int)
                                algorithm_median.append(np.median(offsets) / 10.0)  # 转换为ms
                                algorithm_mean.append(np.mean(offsets) / 10.0)  # 转换为ms
                                algorithm_std.append(np.std(offsets) / 10.0)  # 转换为ms
                                algorithm_variance.append(np.var(offsets) / 100.0)  # 转换为ms²
                            except (ValueError, TypeError):
                                continue
                    
                    if algorithm_key_ids:
                        all_algorithms_data.append({
                            'name': algorithm_name,
                            'key_ids': algorithm_key_ids,
                            'median': algorithm_median,
                            'mean': algorithm_mean,
                            'std': algorithm_std,
                            'variance': algorithm_variance,
                            'color': colors[alg_idx % len(colors)],
                            'analyzer': algorithm.analyzer
                        })
                except Exception as e:
                    logger.warning(f"⚠️ 获取算法 '{algorithm_name}' 的偏移对齐数据失败: {e}")
                    continue
            
            if not all_algorithms_data:
                logger.warning("⚠️ 没有有效的偏移对齐数据，无法生成柱状图")
                return self._create_empty_plot("没有有效的偏移对齐数据")
            
            # 为每个算法添加柱状图（使用grouped bar chart）
            # 计算每个键位的x轴位置（使用grouped bar chart的方式）
            # 获取所有键位的并集
            all_key_ids = set()
            for alg_data in all_algorithms_data:
                all_key_ids.update(alg_data['key_ids'])
            all_key_ids = sorted(list(all_key_ids))
            
            # 为每个算法计算x轴位置（使用grouped bar chart）
            num_algorithms = len(all_algorithms_data)
            bar_width = 0.8 / num_algorithms  # 每个算法的柱状图宽度
            
            for alg_idx, alg_data in enumerate(all_algorithms_data):
                algorithm_name = alg_data['name']
                color = alg_data['color']
                
                # 计算x轴位置（每个算法偏移一定距离）
                x_positions = []
                median_values = []
                mean_values = []
                std_values = []
                variance_values = []
                
                # 创建键位到值的映射
                key_to_median = dict(zip(alg_data['key_ids'], alg_data['median']))
                key_to_mean = dict(zip(alg_data['key_ids'], alg_data['mean']))
                key_to_std = dict(zip(alg_data['key_ids'], alg_data['std']))
                key_to_variance = dict(zip(alg_data['key_ids'], alg_data['variance']))
                
                for key_id in all_key_ids:
                    if key_id in alg_data['key_ids']:
                        x_positions.append(key_id + (alg_idx - num_algorithms / 2 + 0.5) * bar_width)
                        median_values.append(key_to_median[key_id])
                        mean_values.append(key_to_mean[key_id])
                        std_values.append(key_to_std[key_id])
                        variance_values.append(key_to_variance[key_id])
                    else:
                        # 如果该算法没有这个键位的数据，跳过
                        continue
                
                if not x_positions:
                    continue
                
                # 添加中位数柱状图（带数值标注）
                fig.add_trace(
                    go.Bar(
                        x=x_positions,
                        y=median_values,
                        name=algorithm_name,
                        marker_color=color,
                        opacity=0.8,
                        width=bar_width,
                        text=[f'{val:.2f}' for val in median_values],
                        textposition='outside',
                        textfont=dict(size=8),
                        showlegend=True,
                        legendgroup=algorithm_name,
                        hovertemplate=f'算法: {algorithm_name}<br>键位: %{{x:.0f}}<br>中位数: %{{y:.2f}}ms<extra></extra>'
                    ),
                    row=1, col=1
                )
                
                # 添加均值柱状图（带数值标注）
                fig.add_trace(
                    go.Bar(
                        x=x_positions,
                        y=mean_values,
                        name=algorithm_name,
                        marker_color=color,
                        opacity=0.8,
                        width=bar_width,
                        text=[f'{val:.2f}' for val in mean_values],
                        textposition='outside',
                        textfont=dict(size=8),
                        showlegend=False,  # 只在第一个子图显示图例
                        legendgroup=algorithm_name,
                        hovertemplate=f'算法: {algorithm_name}<br>键位: %{{x:.0f}}<br>均值: %{{y:.2f}}ms<extra></extra>'
                    ),
                    row=2, col=1
                )
                
                # 添加标准差柱状图（带数值标注）
                fig.add_trace(
                    go.Bar(
                        x=x_positions,
                        y=std_values,
                        name=algorithm_name,
                        marker_color=color,
                        opacity=0.8,
                        width=bar_width,
                        text=[f'{val:.2f}' for val in std_values],
                        textposition='outside',
                        textfont=dict(size=8),
                        showlegend=False,
                        legendgroup=algorithm_name,
                        hovertemplate=f'算法: {algorithm_name}<br>键位: %{{x:.0f}}<br>标准差: %{{y:.2f}}ms<extra></extra>'
                    ),
                    row=3, col=1
                )
                
                # 添加方差柱状图（带数值标注）
                fig.add_trace(
                    go.Bar(
                        x=x_positions,
                        y=variance_values,
                        name=algorithm_name,
                        marker_color=color,
                        opacity=0.8,
                        width=bar_width,
                        text=[f'{val:.2f}' for val in variance_values],
                        textposition='outside',
                        textfont=dict(size=8),
                        showlegend=False,
                        legendgroup=algorithm_name,
                        hovertemplate=f'算法: {algorithm_name}<br>键位: %{{x:.0f}}<br>方差: %{{y:.2f}}ms²<extra></extra>'
                    ),
                    row=4, col=1
                )
            
            # 确保key_ids的最小值至少为1（按键ID不可能为负数）
            min_key_id = max(1, min(all_key_ids)) if all_key_ids else 1
            max_key_id = max(all_key_ids) if all_key_ids else 90
            
            # 设置x轴刻度（显示所有键位）和范围（确保不显示负数）
            fig.update_xaxes(
                tickmode='linear',
                tick0=min_key_id,
                dtick=1,
                title_text='键位ID',
                range=[min_key_id - 1, max_key_id + 1],  # 设置x轴范围，确保不显示负数
                row=1, col=1
            )
            fig.update_xaxes(
                tickmode='linear',
                tick0=min_key_id,
                dtick=1,
                title_text='键位ID',
                range=[min_key_id - 1, max_key_id + 1],
                row=2, col=1
            )
            fig.update_xaxes(
                tickmode='linear',
                tick0=min_key_id,
                dtick=1,
                title_text='键位ID',
                range=[min_key_id - 1, max_key_id + 1],
                row=3, col=1
            )
            fig.update_xaxes(
                tickmode='linear',
                tick0=min_key_id,
                dtick=1,
                title_text='键位ID',
                range=[min_key_id - 1, max_key_id + 1],
                row=4, col=1
            )
            
            # 设置y轴标题
            fig.update_yaxes(title_text='中位数偏移 (ms)', row=1, col=1)
            fig.update_yaxes(title_text='均值偏移 (ms)', row=2, col=1)
            fig.update_yaxes(title_text='标准差 (ms)', row=3, col=1)
            fig.update_yaxes(title_text='方差 (ms²)', row=4, col=1)
            
            # 设置布局
            fig.update_layout(
                title='多算法偏移对齐分析对比图',
                height=2200,
                template='simple_white',
                showlegend=True,
                legend=dict(
                    orientation='h',
                    yanchor='bottom',
                    y=1.02,
                    xanchor='right',
                    x=1
                ),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(size=12)
            )
            
            logger.info(f"✅ 多算法偏移对齐分析图生成成功，共 {len(all_algorithms_data)} 个算法")
            return fig
            
        except Exception as e:
            logger.error(f"❌ 生成多算法偏移对齐分析图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._create_empty_plot(f"生成失败: {str(e)}")
    
    def generate_multi_algorithm_delay_histogram_plot(
        self,
        algorithms: List[AlgorithmDataset]
    ) -> Any:
        """
        生成多算法延时分布直方图（叠加显示，不同颜色，图例控制）
        
        为每个算法生成直方图和正态拟合曲线，使用不同颜色区分，叠加显示在同一图表中。
        
        Args:
            algorithms: 激活的算法数据集列表
            
        Returns:
            go.Figure: Plotly图表对象
        """
        if not algorithms:
            logger.warning("⚠️ 没有激活的算法，无法生成多算法延时分布直方图")
            return self._create_empty_plot("没有激活的算法")
        
        try:
            # 过滤出就绪的算法
            ready_algorithms = [alg for alg in algorithms if alg.is_ready()]
            if not ready_algorithms:
                logger.warning("⚠️ 没有就绪的算法，无法生成多算法延时分布直方图")
                return self._create_empty_plot("没有就绪的算法")
            
            logger.info(f"📊 开始生成多算法延时分布直方图，共 {len(ready_algorithms)} 个算法")
            
            # 为每个算法分配颜色（使用不同的颜色方案）
            colors = [
                '#1f77b4',  # 蓝色
                '#ff7f0e',  # 橙色
                '#2ca02c',  # 绿色
                '#d62728',  # 红色
                '#9467bd',  # 紫色
                '#8c564b',  # 棕色
                '#e377c2',  # 粉色
                '#7f7f7f'   # 灰色
            ]
            
            import plotly.graph_objects as go
            import math
            fig = go.Figure()
            
            # 收集所有算法的数据
            all_delays = []  # 用于确定全局范围
            
            for alg_idx, algorithm in enumerate(ready_algorithms):
                algorithm_name = algorithm.metadata.algorithm_name
                
                if not algorithm.analyzer or not algorithm.analyzer.note_matcher:
                    logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有分析器或匹配器，跳过")
                    continue
                
                try:
                    # 从analyzer获取偏移数据
                    offset_data = algorithm.analyzer.get_offset_alignment_data()
                    
                    if not offset_data:
                        logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有匹配数据，跳过")
                        continue
                    
                    # 注意：这里使用带符号的keyon_offset，而非绝对值
                    delays_ms = [item.get('keyon_offset', 0.0) / 10.0 for item in offset_data]
                    
                    if not delays_ms:
                        logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有有效延时数据，跳过")
                        continue
                    
                    all_delays.extend(delays_ms)
                    
                    # 计算统计量
                    n = len(delays_ms)
                    mean_val = sum(delays_ms) / n
                    if n > 1:
                        var = sum((x - mean_val) ** 2 for x in delays_ms) / (n - 1)
                        std_val = var ** 0.5
                    else:
                        std_val = 0.0
                    
                    color = colors[alg_idx % len(colors)]
                    
                    # 添加直方图
                    fig.add_trace(go.Histogram(
                        x=delays_ms,
                        histnorm='probability density',
                        name=f'{algorithm_name} - 延时分布',
                        marker_color=color,
                        opacity=0.6,
                        legendgroup=algorithm_name,
                        showlegend=True
                    ))
                    
                    # 生成正态拟合曲线
                    if std_val > 0:
                        min_x = min(delays_ms)
                        max_x = max(delays_ms)
                        span = max(1e-6, 3 * std_val)
                        x_start = min(mean_val - span, min_x)
                        x_end = max(mean_val + span, max_x)
                        
                        num_pts = 200
                        step = (x_end - x_start) / (num_pts - 1) if num_pts > 1 else 1.0
                        xs = [x_start + i * step for i in range(num_pts)]
                        ys = [(1.0 / (std_val * (2 * math.pi) ** 0.5)) * 
                              math.exp(-0.5 * ((x - mean_val) / std_val) ** 2) 
                              for x in xs]
                        
                        # 添加正态拟合曲线
                        fig.add_trace(go.Scatter(
                            x=xs,
                            y=ys,
                            mode='lines',
                            name=f'{algorithm_name} - 正态拟合 (μ={mean_val:.2f}ms, σ={std_val:.2f}ms)',
                            line=dict(color=color, width=2),
                            legendgroup=algorithm_name,
                            showlegend=True
                        ))
                    
                except Exception as e:
                    logger.warning(f"⚠️ 获取算法 '{algorithm_name}' 的延时数据失败: {e}")
                    continue
            
            if not all_delays:
                logger.warning("⚠️ 没有有效的延时数据，无法生成直方图")
                return self._create_empty_plot("没有有效的延时数据")
            
            # 设置布局
            fig.update_layout(
                title={
                    'text': '多算法延时分布直方图（附正态拟合曲线）',
                    'x': 0.5,
                    'xanchor': 'center',
                    'y': 0.98,  # 稍微下移，避免被图注挤压
                    'yanchor': 'top',
                    'font': {'size': 18, 'color': '#2c3e50'}
                },
                xaxis_title='延时 (ms)',
                yaxis_title='概率密度',
                bargap=0.05,
                plot_bgcolor='white',
                paper_bgcolor='white',
                font=dict(size=12),
                height=500,
                legend=dict(
                    orientation='h',
                    yanchor='bottom',
                    y=1.05,  # 图注更靠上，给标题留出空间
                    xanchor='left',
                    x=0.0,  # 从最左边开始，避免挤压居中标题
                    bgcolor='rgba(255, 255, 255, 0.9)',
                    bordercolor='gray',
                    borderwidth=1
                ),
                margin=dict(t=100, b=60, l=60, r=60)  # 增加顶部边距，给图注和标题更多空间
            )
            
            logger.info(f"✅ 多算法延时分布直方图生成成功，共 {len(ready_algorithms)} 个算法")
            return fig
            
        except Exception as e:
            logger.error(f"❌ 生成多算法延时分布直方图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._create_empty_plot(f"生成失败: {str(e)}")
    
    def generate_multi_algorithm_key_delay_scatter_plot(
        self,
        algorithms: List[AlgorithmDataset]
    ) -> Any:
        """
        生成多算法按键与延时散点图（叠加显示，不同颜色，图例控制）
        
        Args:
            algorithms: 激活的算法数据集列表
            
        Returns:
            go.Figure: Plotly图表对象
        """
        if not algorithms:
            logger.warning("⚠️ 没有激活的算法，无法生成多算法按键与延时散点图")
            return self._create_empty_plot("没有激活的算法")
        
        try:
            # 过滤出激活且就绪的算法（确保只显示用户选择的算法）
            # 记录传入的算法状态，用于调试
            for alg in algorithms:
                logger.debug(f"🔍 算法 '{alg.metadata.algorithm_name}': is_active={alg.is_active}, is_ready={alg.is_ready()}")
            
            ready_algorithms = [alg for alg in algorithms if alg.is_active and alg.is_ready()]
            if not ready_algorithms:
                logger.warning("⚠️ 没有激活且就绪的算法，无法生成多算法按键与延时散点图")
                return self._create_empty_plot("没有激活的算法")
            
            logger.info(f"📊 开始生成多算法按键与延时散点图，共 {len(ready_algorithms)} 个激活算法: {[alg.metadata.algorithm_name for alg in ready_algorithms]}")
            
            # 为每个算法分配颜色
            colors = [
                '#1f77b4',  # 蓝色
                '#ff7f0e',  # 橙色
                '#2ca02c',  # 绿色
                '#d62728',  # 红色
                '#9467bd',  # 紫色
                '#8c564b',  # 棕色
                '#e377c2',  # 粉色
                '#7f7f7f'   # 灰色
            ]
            
            import plotly.graph_objects as go
            import numpy as np
            fig = go.Figure()
            
            # 收集所有激活算法的数据和统计信息
            algorithm_data_list = []
            
            for alg_idx, algorithm in enumerate(ready_algorithms):
                algorithm_name = algorithm.metadata.algorithm_name
                
                if not algorithm.analyzer or not algorithm.analyzer.note_matcher:
                    logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有分析器或匹配器，跳过")
                    continue
                
                try:
                    offset_data = algorithm.analyzer.note_matcher.get_offset_alignment_data()
                    
                    if not offset_data:
                        logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有匹配数据，跳过")
                        continue
                    
                    # 提取按键ID和延时数据（带符号值）
                    key_ids = []
                    delays_ms = []  # 带符号，用于显示和计算阈值
                    customdata_list = []  # 用于存储customdata，包含record_index和replay_index
                    
                    for item in offset_data:
                        key_id = item.get('key_id')
                        keyon_offset = item.get('keyon_offset', 0)  # 单位：0.1ms
                        record_index = item.get('record_index')
                        replay_index = item.get('replay_index')
                        
                        if key_id is None or key_id == 'N/A':
                            continue
                        
                        try:
                            key_id_int = int(key_id)
                            delay_ms = keyon_offset / 10.0  # 带符号，保留原始值
                            
                            key_ids.append(key_id_int)
                            delays_ms.append(delay_ms)
                            # 添加customdata：包含record_index、replay_index、算法名称，用于点击时查找匹配对
                            customdata_list.append([record_index, replay_index, key_id_int, delay_ms, algorithm_name])
                        except (ValueError, TypeError):
                            continue
                    
                    if not key_ids:
                        logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有有效的散点图数据，跳过")
                        continue
                    
                    color = colors[alg_idx % len(colors)]
                    
                    # 直接使用数据概览页面的数据，不重新计算
                    # 使用analyzer的方法，确保与数据概览页面完全一致
                    me_0_1ms = algorithm.analyzer.get_mean_error()  # 总体均值（0.1ms单位，带符号）
                    std_0_1ms = algorithm.analyzer.get_standard_deviation()  # 总体标准差（0.1ms单位，带符号）
                    
                    # 转换为ms单位
                    mu = me_0_1ms / 10.0  # 总体均值（ms，带符号）
                    sigma = std_0_1ms / 10.0  # 总体标准差（ms，带符号）
                    
                    # 计算该算法的阈值
                    upper_threshold = mu + 3 * sigma  # 上阈值：μ + 3σ
                    lower_threshold = mu - 3 * sigma  # 下阈值：μ - 3σ
                    
                    # 保存算法数据，用于后续添加散点图和阈值线
                    algorithm_data_list.append({
                        'name': algorithm_name,
                        'key_ids': key_ids,
                        'delays_ms': delays_ms,
                        'customdata': customdata_list,  # 保存customdata
                        'color': color,
                        'mu': mu,
                        'sigma': sigma,
                        'upper_threshold': upper_threshold,
                        'lower_threshold': lower_threshold
                    })
                    
                except Exception as e:
                    logger.warning(f"⚠️ 获取算法 '{algorithm_name}' 的按键与延时数据失败: {e}")
                    continue
            
            # 添加散点图数据
            for alg_data in algorithm_data_list:
                # 为超过阈值的点使用不同颜色和大小
                marker_colors = []
                marker_sizes = []
                for delay in alg_data['delays_ms']:
                    if delay > alg_data['upper_threshold'] or delay < alg_data['lower_threshold']:
                        # 超过阈值的点使用更深的颜色，更大尺寸
                        marker_colors.append(alg_data['color'])
                        marker_sizes.append(12)
                    else:
                        marker_colors.append(alg_data['color'])
                        marker_sizes.append(8)
                
                fig.add_trace(go.Scatter(
                    x=alg_data['key_ids'],
                    y=alg_data['delays_ms'],
                    mode='markers',
                    name=f"{alg_data['name']} - 匹配对",
                    marker=dict(
                        size=marker_sizes,
                        color=marker_colors,
                        opacity=0.6,
                        line=dict(width=1, color=alg_data['color'])
                    ),
                    customdata=alg_data['customdata'],  # 添加customdata，包含record_index、replay_index和算法名称
                    legendgroup=alg_data['name'],
                    showlegend=True,
                    hovertemplate=f"算法: {alg_data['name']}<br>键位: %{{x}}<br>延时: %{{y:.2f}}ms<extra></extra>"
                ))
            
            # 获取x轴范围，用于确定标注位置
            all_key_ids = []
            for alg_data in algorithm_data_list:
                all_key_ids.extend(alg_data['key_ids'])
            x_max = max(all_key_ids) if all_key_ids else 90
            x_min = min(all_key_ids) if all_key_ids else 1
            
            # 为每个激活的算法添加阈值线（只显示激活算法的阈值）
            # 使用go.Scatter创建水平线，使其能够响应图例点击
            for alg_data in algorithm_data_list:
                # 添加该算法的总体均值参考线（使用算法颜色，虚线）
                # 使用Scatter创建水平线，设置相同的legendgroup，使其与散点图一起响应图例点击
                fig.add_trace(go.Scatter(
                    x=[x_min, x_max],
                    y=[alg_data['mu'], alg_data['mu']],
                    mode='lines',
                    name=f"{alg_data['name']} - μ",
                    line=dict(
                        color=alg_data['color'],
                        width=1.5,
                        dash='dot'
                    ),
                    legendgroup=alg_data['name'],  # 与散点图使用相同的图例组
                    showlegend=True,
                    hovertemplate=f"算法: {alg_data['name']}<br>μ = {alg_data['mu']:.2f}ms<extra></extra>"
                ))
                # 注意：已移除标注，信息通过悬停（hover）显示
                
                # 添加该算法的上阈值线（μ + 3σ，使用算法颜色）
                fig.add_trace(go.Scatter(
                    x=[x_min, x_max],
                    y=[alg_data['upper_threshold'], alg_data['upper_threshold']],
                    mode='lines',
                    name=f"{alg_data['name']} - μ+3σ",
                    line=dict(
                        color=alg_data['color'],
                        width=2,
                        dash='dash'
                    ),
                    legendgroup=alg_data['name'],  # 与散点图使用相同的图例组
                    showlegend=True,
                    hovertemplate=f"算法: {alg_data['name']}<br>μ+3σ = {alg_data['upper_threshold']:.2f}ms<extra></extra>"
                ))
                
                # 添加该算法的下阈值线（μ - 3σ，使用算法颜色）
                fig.add_trace(go.Scatter(
                    x=[x_min, x_max],
                    y=[alg_data['lower_threshold'], alg_data['lower_threshold']],
                    mode='lines',
                    name=f"{alg_data['name']} - μ-3σ",
                    line=dict(
                        color=alg_data['color'],
                        width=2,
                        dash='dash'
                    ),
                    legendgroup=alg_data['name'],  # 与散点图使用相同的图例组
                    showlegend=True,
                    hovertemplate=f"算法: {alg_data['name']}<br>μ-3σ = {alg_data['lower_threshold']:.2f}ms<extra></extra>"
                ))
            
            # 设置布局
            fig.update_layout(
                title={
                    'text': '多算法按键与延时散点图（已匹配按键对）',
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 18, 'color': '#2c3e50'}
                },
                xaxis_title='按键ID',
                yaxis_title='延时 (ms)',
                xaxis=dict(
                    showgrid=True,
                    gridcolor='lightgray',
                    gridwidth=1,
                    dtick=10
                ),
                yaxis=dict(
                    showgrid=True,
                    gridcolor='lightgray',
                    gridwidth=1
                ),
                hovermode='closest',
                plot_bgcolor='white',
                paper_bgcolor='white',
                font=dict(size=12),
                height=500,
                showlegend=True,
                legend=dict(
                    orientation='h',
                    yanchor='bottom',
                    y=1.02,
                    xanchor='left',
                    x=0.0,
                    bgcolor='rgba(255, 255, 255, 0.9)',
                    bordercolor='gray',
                    borderwidth=1
                ),
                margin=dict(t=90, b=60, l=60, r=60)  # 增加顶部边距，为图例和标注留出空间
            )
            
            logger.info(f"✅ 多算法按键与延时散点图生成成功，共 {len(ready_algorithms)} 个算法")
            return fig
            
        except Exception as e:
            logger.error(f"❌ 生成多算法按键与延时散点图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._create_empty_plot(f"生成失败: {str(e)}")
    
    def generate_multi_algorithm_key_delay_zscore_scatter_plot(
        self,
        algorithms: List[AlgorithmDataset]
    ) -> Any:
        """
        生成多算法按键与延时Z-Score标准化散点图
        
        Z-Score标准化公式：z = (x_i - μ) / σ
        - x_i: 每个数据点的延时值
        - μ: 该算法的总体均值
        - σ: 该算法的总体标准差
        
        Args:
            algorithms: 激活的算法数据集列表
            
        Returns:
            go.Figure: Plotly图表对象
        """
        if not algorithms:
            logger.warning("⚠️ 没有激活的算法，无法生成Z-Score标准化散点图")
            return self._create_empty_plot("没有激活的算法")
        
        try:
            # 过滤出激活且就绪的算法
            ready_algorithms = [alg for alg in algorithms if alg.is_active and alg.is_ready()]
            if not ready_algorithms:
                logger.warning("⚠️ 没有激活且就绪的算法，无法生成Z-Score标准化散点图")
                return self._create_empty_plot("没有激活的算法")
            
            logger.info(f"📊 开始生成多算法Z-Score标准化散点图，共 {len(ready_algorithms)} 个激活算法")
            
            # 为每个算法分配颜色
            colors = [
                '#1f77b4',  # 蓝色
                '#ff7f0e',  # 橙色
                '#2ca02c',  # 绿色
                '#d62728',  # 红色
                '#9467bd',  # 紫色
                '#8c564b',  # 棕色
                '#e377c2',  # 粉色
                '#7f7f7f'   # 灰色
            ]
            
            import plotly.graph_objects as go
            import numpy as np
            fig = go.Figure()
            
            # 用于收集所有算法的x轴范围
            all_x_min = None
            all_x_max = None
            
            # 收集所有激活算法的数据
            for alg_idx, algorithm in enumerate(ready_algorithms):
                algorithm_name = algorithm.metadata.algorithm_name
                
                if not algorithm.analyzer or not algorithm.analyzer.note_matcher:
                    logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有分析器或匹配器，跳过")
                    continue
                
                try:
                    offset_data = algorithm.analyzer.note_matcher.get_offset_alignment_data()
                    
                    if not offset_data:
                        logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有匹配数据，跳过")
                        continue
                    
                    # 提取按键ID和延时数据
                    key_ids = []
                    delays_ms = []
                    customdata_list = []
                    
                    for item in offset_data:
                        key_id = item.get('key_id')
                        keyon_offset = item.get('keyon_offset', 0)  # 单位：0.1ms
                        record_index = item.get('record_index')
                        replay_index = item.get('replay_index')
                        
                        if key_id is None or key_id == 'N/A':
                            continue
                        
                        try:
                            key_id_int = int(key_id)
                            delay_ms = keyon_offset / 10.0  # 转换为ms
                            
                            key_ids.append(key_id_int)
                            delays_ms.append(delay_ms)
                            customdata_list.append([record_index, replay_index, key_id_int, delay_ms, algorithm_name])
                        except (ValueError, TypeError):
                            continue
                    
                    if not key_ids:
                        logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有有效的散点图数据，跳过")
                        continue
                    
                    # 获取该算法的总体均值和标准差（用于Z-Score标准化）
                    me_0_1ms = algorithm.analyzer.get_mean_error()  # 总体均值（0.1ms单位，带符号）
                    std_0_1ms = algorithm.analyzer.get_standard_deviation()  # 总体标准差（0.1ms单位，带符号）
                    
                    # 转换为ms单位
                    mu = me_0_1ms / 10.0  # 总体均值（ms，带符号）
                    sigma = std_0_1ms / 10.0  # 总体标准差（ms，带符号）
                    
                    # 计算Z-Score：z = (x_i - μ) / σ
                    delays_array = np.array(delays_ms)
                    if sigma > 0:
                        z_scores_array = (delays_array - mu) / sigma
                        # 转换为列表，确保Plotly正确处理
                        z_scores = z_scores_array.tolist()
                        logger.info(f"🔍 算法 '{algorithm_name}': μ={mu:.2f}ms, σ={sigma:.2f}ms, 原始延时范围=[{delays_array.min():.2f}, {delays_array.max():.2f}]ms, Z-Score范围=[{z_scores_array.min():.2f}, {z_scores_array.max():.2f}]")
                    else:
                        z_scores = [0.0] * len(delays_ms)
                        logger.warning(f"⚠️ 算法 '{algorithm_name}' 的标准差为0，无法进行Z-Score标准化")
                    
                    color = colors[alg_idx % len(colors)]
                    
                    # 添加散点图（使用Z-Score值作为y轴）
                    fig.add_trace(go.Scatter(
                        x=key_ids,
                        y=z_scores,  # 使用Z-Score值，不是原始延时值
                        mode='markers',
                        name=f"{algorithm_name} - Z-Score",
                        marker=dict(
                            size=8,
                            color=color,
                            opacity=0.6,
                            line=dict(width=1, color=color)
                        ),
                        customdata=customdata_list,
                        legendgroup=algorithm_name,
                        showlegend=True,
                        hovertemplate=f"算法: {algorithm_name}<br>键位: %{{x}}<br>延时: %{{customdata[3]:.2f}}ms<br>Z-Score: %{{y:.2f}}<extra></extra>"
                    ))
                    
                    # 收集x轴范围（用于后续添加全局参考线）
                    if key_ids:
                        if all_x_min is None:
                            all_x_min = min(key_ids)
                            all_x_max = max(key_ids)
                        else:
                            all_x_min = min(all_x_min, min(key_ids))
                            all_x_max = max(all_x_max, max(key_ids))
                    
                except Exception as e:
                    logger.warning(f"⚠️ 获取算法 '{algorithm_name}' 的Z-Score数据失败: {e}")
                    continue
            
            # 确定x轴范围
            x_min = all_x_min if all_x_min is not None else 1
            x_max = all_x_max if all_x_max is not None else 90
            
            # 为每个算法添加阈值线（与按键与延时散点图一样的对比曲线）
            # 虽然Z-Score标准化后所有算法的参考线值相同，但为每个算法添加独立的线，
            # 使其能够响应图例点击，与散点图一起显示/隐藏
            for alg_idx, algorithm in enumerate(ready_algorithms):
                algorithm_name = algorithm.metadata.algorithm_name
                color = colors[alg_idx % len(colors)]
                
                # 添加该算法的Z-Score = 0参考线（均值线）
                fig.add_trace(go.Scatter(
                    x=[x_min, x_max],
                    y=[0, 0],
                    mode='lines',
                    name=f"{algorithm_name} - Z=0",
                    line=dict(
                        color=color,
                        width=1.5,
                        dash='dot'
                    ),
                    legendgroup=algorithm_name,  # 与散点图使用相同的图例组
                    showlegend=True,
                    hovertemplate=f"算法: {algorithm_name}<br>Z-Score = 0 (均值线)<extra></extra>"
                ))
                
                # 添加该算法的Z-Score = +3阈值线（上阈值）
                fig.add_trace(go.Scatter(
                    x=[x_min, x_max],
                    y=[3, 3],
                    mode='lines',
                    name=f"{algorithm_name} - Z=+3",
                    line=dict(
                        color=color,
                        width=2,
                        dash='dash'
                    ),
                    legendgroup=algorithm_name,  # 与散点图使用相同的图例组
                    showlegend=True,
                    hovertemplate=f"算法: {algorithm_name}<br>Z-Score = +3 (上阈值)<extra></extra>"
                ))
                
                # 添加该算法的Z-Score = -3阈值线（下阈值）
                fig.add_trace(go.Scatter(
                    x=[x_min, x_max],
                    y=[-3, -3],
                    mode='lines',
                    name=f"{algorithm_name} - Z=-3",
                    line=dict(
                        color=color,
                        width=2,
                        dash='dash'
                    ),
                    legendgroup=algorithm_name,  # 与散点图使用相同的图例组
                    showlegend=True,
                    hovertemplate=f"算法: {algorithm_name}<br>Z-Score = -3 (下阈值)<extra></extra>"
                ))
            
            # 设置布局
            fig.update_layout(
                title={
                    'text': '多算法按键与延时Z-Score标准化散点图',
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 18, 'color': '#2c3e50'}
                },
                xaxis_title='按键ID',
                yaxis_title='Z-Score (标准化延时)',
                xaxis=dict(
                    showgrid=True,
                    gridcolor='lightgray',
                    gridwidth=1,
                    dtick=10
                ),
                yaxis=dict(
                    showgrid=True,
                    gridcolor='lightgray',
                    gridwidth=1
                ),
                hovermode='closest',
                plot_bgcolor='white',
                paper_bgcolor='white',
                font=dict(size=12),
                height=500,
                showlegend=True,
                legend=dict(
                    orientation='h',
                    yanchor='bottom',
                    y=1.02,
                    xanchor='left',
                    x=0.0,
                    bgcolor='rgba(255, 255, 255, 0.9)',
                    bordercolor='gray',
                    borderwidth=1
                ),
                margin=dict(t=90, b=60, l=60, r=60)
            )
            
            logger.info(f"✅ 多算法Z-Score标准化散点图生成成功，共 {len(ready_algorithms)} 个算法")
            return fig
            
        except Exception as e:
            logger.error(f"❌ 生成多算法Z-Score标准化散点图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._create_empty_plot(f"生成Z-Score散点图失败: {str(e)}")
    
    def generate_multi_algorithm_hammer_velocity_delay_scatter_plot(
        self,
        algorithms: List[AlgorithmDataset]
    ) -> Any:
        """
        生成多算法锤速与延时散点图（叠加显示，不同颜色，图例控制）
        
        Args:
            algorithms: 激活的算法数据集列表
            
        Returns:
            go.Figure: Plotly图表对象
        """
        if not algorithms:
            logger.warning("⚠️ 没有激活的算法，无法生成多算法锤速与延时散点图")
            return self._create_empty_plot("没有激活的算法")
        
        try:
            # 过滤出就绪的算法
            ready_algorithms = [alg for alg in algorithms if alg.is_ready()]
            if not ready_algorithms:
                logger.warning("⚠️ 没有就绪的算法，无法生成多算法锤速与延时散点图")
                return self._create_empty_plot("没有就绪的算法")
            
            logger.info(f"📊 开始生成多算法锤速与延时散点图，共 {len(ready_algorithms)} 个算法")
            
            # 为每个算法分配颜色
            colors = [
                '#1f77b4',  # 蓝色
                '#ff7f0e',  # 橙色
                '#2ca02c',  # 绿色
                '#d62728',  # 红色
                '#9467bd',  # 紫色
                '#8c564b',  # 棕色
                '#e377c2',  # 粉色
                '#7f7f7f'   # 灰色
            ]
            
            import plotly.graph_objects as go
            fig = go.Figure()
            
            for alg_idx, algorithm in enumerate(ready_algorithms):
                algorithm_name = algorithm.metadata.algorithm_name
                
                if not algorithm.analyzer or not algorithm.analyzer.note_matcher:
                    logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有分析器或匹配器，跳过")
                    continue
                
                try:
                    matched_pairs = algorithm.analyzer.note_matcher.get_matched_pairs()
                    
                    if not matched_pairs:
                        logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有匹配数据，跳过")
                        continue
                    
                    offset_data = algorithm.analyzer.note_matcher.get_offset_alignment_data()
                    
                    # 提取锤速和延时数据，并计算Z-Score（与按键与延时Z-Score散点图相同）
                    hammer_velocities = []
                    delays_ms = []  # 延时（ms单位，带符号，用于计算Z-Score）
                    scatter_customdata = []  # 存储record_idx、replay_idx和algorithm_name，用于点击事件识别
                    
                    # 创建匹配对索引到偏移数据的映射
                    offset_map = {}
                    for item in offset_data:
                        record_idx = item.get('record_index')
                        replay_idx = item.get('replay_index')
                        if record_idx is not None and replay_idx is not None:
                            offset_map[(record_idx, replay_idx)] = item
                    
                    for record_idx, replay_idx, record_note, replay_note in matched_pairs:
                        # 获取播放音符的锤速（第一个锤速值）
                        if len(replay_note.hammers) > 0 and len(replay_note.hammers.values) > 0:
                            hammer_velocity = replay_note.hammers.values[0]
                        else:
                            continue
                        
                        # 从偏移数据中获取延时
                        keyon_offset = None
                        if (record_idx, replay_idx) in offset_map:
                            keyon_offset = offset_map[(record_idx, replay_idx)].get('keyon_offset', 0)
                        else:
                            try:
                                record_keyon, _ = algorithm.analyzer.note_matcher._calculate_note_times(record_note)
                                replay_keyon, _ = algorithm.analyzer.note_matcher._calculate_note_times(replay_note)
                                keyon_offset = replay_keyon - record_keyon
                            except:
                                continue
                        
                        # 将延时从0.1ms转换为ms（带符号，用于Z-Score计算）
                        delay_ms = keyon_offset / 10.0
                        
                        hammer_velocities.append(hammer_velocity)
                        delays_ms.append(delay_ms)
                        # 存储record_idx、replay_idx和algorithm_name，用于点击事件识别
                        scatter_customdata.append([record_idx, replay_idx, algorithm_name])
                    
                    if not hammer_velocities:
                        logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有有效的散点图数据，跳过")
                        continue
                    
                    # 计算Z-Score（与按键与延时Z-Score散点图相同的计算方式）
                    import numpy as np
                    me_0_1ms = algorithm.analyzer.get_mean_error() if hasattr(algorithm.analyzer, 'get_mean_error') else 0.0
                    std_0_1ms = algorithm.analyzer.get_standard_deviation() if hasattr(algorithm.analyzer, 'get_standard_deviation') else 0.0
                    
                    mu = me_0_1ms / 10.0  # 总体均值（ms，带符号）
                    sigma = std_0_1ms / 10.0  # 总体标准差（ms，带符号）
                    
                    # 计算Z-Score：z = (x_i - μ) / σ
                    delays_array = np.array(delays_ms)
                    if sigma > 0:
                        z_scores = ((delays_array - mu) / sigma).tolist()
                    else:
                        z_scores = [0.0] * len(delays_ms)
                    
                    color = colors[alg_idx % len(colors)]
                    
                    # 添加散点图数据（y轴使用Z-Score值）
                    # customdata格式: [delay_ms, record_idx, replay_idx, algorithm_name]
                    # 第一个元素用于hover显示，后三个用于点击事件识别
                    combined_customdata = [[delay_ms, record_idx, replay_idx, alg_name] 
                                          for delay_ms, (record_idx, replay_idx, alg_name) 
                                          in zip(delays_ms, scatter_customdata)]
                    
                    fig.add_trace(go.Scatter(
                        x=hammer_velocities,
                        y=z_scores,
                        mode='markers',
                        name=f'{algorithm_name} - Z-Score',
                        marker=dict(
                            size=8,
                            color=color,
                            opacity=0.6,
                            line=dict(width=1, color=color)
                        ),
                        legendgroup=algorithm_name,
                        showlegend=True,
                        hovertemplate=f'算法: {algorithm_name}<br>锤速: %{{x}}<br>延时: %{{customdata[0]:.2f}}ms<br>Z-Score: %{{y:.2f}}<extra></extra>',
                        customdata=combined_customdata
                    ))
                    
                    # 添加Z-Score参考线（与按键与延时Z-Score散点图相同）
                    if len(hammer_velocities) > 0:
                        # 获取x轴范围（使用所有算法的范围）
                        all_velocities = []
                        for alg in ready_algorithms:
                            try:
                                matched_pairs = alg.analyzer.note_matcher.get_matched_pairs()
                                for record_idx, replay_idx, record_note, replay_note in matched_pairs:
                                    if len(replay_note.hammers) > 0 and len(replay_note.hammers.values) > 0:
                                        all_velocities.append(replay_note.hammers.values[0])
                            except:
                                continue
                        
                        x_min = min(all_velocities) if all_velocities else 0
                        x_max = max(all_velocities) if all_velocities else 100
                        
                        # 添加Z=0的水平虚线（均值线）
                        fig.add_trace(go.Scatter(
                            x=[x_min, x_max],
                            y=[0, 0],
                            mode='lines',
                            name=f'{algorithm_name} - Z=0',
                            line=dict(
                                color=color,
                                width=1.5,
                                dash='dot'
                            ),
                            legendgroup=algorithm_name,
                            showlegend=True,
                            hovertemplate=f'算法: {algorithm_name}<br>Z-Score = 0 (均值线)<extra></extra>'
                        ))
                        
                        # 添加Z=+3的水平虚线（上阈值）
                        fig.add_trace(go.Scatter(
                            x=[x_min, x_max],
                            y=[3, 3],
                            mode='lines',
                            name=f'{algorithm_name} - Z=+3',
                            line=dict(
                                color=color,
                                width=2,
                                dash='dash'
                            ),
                            legendgroup=algorithm_name,
                            showlegend=True,
                            hovertemplate=f'算法: {algorithm_name}<br>Z-Score = +3 (上阈值)<extra></extra>'
                        ))
                        
                        # 添加Z=-3的水平虚线（下阈值）
                        fig.add_trace(go.Scatter(
                            x=[x_min, x_max],
                            y=[-3, -3],
                            mode='lines',
                            name=f'{algorithm_name} - Z=-3',
                            line=dict(
                                color=color,
                                width=2,
                                dash='dash'
                            ),
                            legendgroup=algorithm_name,
                            showlegend=True,
                            hovertemplate=f'算法: {algorithm_name}<br>Z-Score = -3 (下阈值)<extra></extra>'
                        ))
                    
                except Exception as e:
                    logger.warning(f"⚠️ 获取算法 '{algorithm_name}' 的锤速与延时数据失败: {e}")
                    continue
            
            # 设置布局
            fig.update_layout(
                title={
                    'text': '多算法锤速与延时散点图（已匹配按键对）',
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 18, 'color': '#2c3e50'}
                },
                xaxis_title='锤速',
                yaxis_title='Z-Score（标准化延时）',
                xaxis=dict(
                    showgrid=True,
                    gridcolor='lightgray',
                    gridwidth=1
                ),
                yaxis=dict(
                    showgrid=True,
                    gridcolor='lightgray',
                    gridwidth=1
                ),
                hovermode='closest',
                plot_bgcolor='white',
                paper_bgcolor='white',
                font=dict(size=12),
                height=500,
                showlegend=True,
                legend=dict(
                    orientation='h',
                    yanchor='bottom',
                    y=1.02,
                    xanchor='left',
                    x=0.0,
                    bgcolor='rgba(255, 255, 255, 0.9)',
                    bordercolor='gray',
                    borderwidth=1
                ),
                margin=dict(t=70, b=60, l=60, r=60)
            )
            
            logger.info(f"✅ 多算法锤速与延时散点图生成成功，共 {len(ready_algorithms)} 个算法")
            return fig
            
        except Exception as e:
            logger.error(f"❌ 生成多算法锤速与延时散点图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._create_empty_plot(f"生成失败: {str(e)}")
    
    def generate_multi_algorithm_key_hammer_velocity_scatter_plot(
        self,
        algorithms: List[AlgorithmDataset]
    ) -> Any:
        """
        生成多算法按键与锤速散点图（颜色表示延时，叠加显示，不同标记形状区分算法）
        
        Args:
            algorithms: 激活的算法数据集列表
            
        Returns:
            go.Figure: Plotly图表对象
        """
        if not algorithms:
            logger.warning("⚠️ 没有激活的算法，无法生成多算法按键与锤速散点图")
            return self._create_empty_plot("没有激活的算法")
        
        try:
            # 过滤出就绪的算法
            ready_algorithms = [alg for alg in algorithms if alg.is_ready()]
            if not ready_algorithms:
                logger.warning("⚠️ 没有就绪的算法，无法生成多算法按键与锤速散点图")
                return self._create_empty_plot("没有就绪的算法")
            
            logger.info(f"📊 开始生成多算法按键与锤速散点图，共 {len(ready_algorithms)} 个算法")
            
            # 为每个算法分配不同的标记形状和颜色方案
            marker_symbols = ['circle', 'square', 'diamond', 'triangle-up', 'x', 'star', 'cross', 'pentagon']
            colorscales = ['Viridis', 'Plasma', 'Inferno', 'Magma', 'Cividis', 'Turbo', 'Blues', 'Reds']
            
            import plotly.graph_objects as go
            fig = go.Figure()
            
            # 收集所有算法的延时范围，用于统一颜色条
            all_delays = []
            
            for alg_idx, algorithm in enumerate(ready_algorithms):
                algorithm_name = algorithm.metadata.algorithm_name
                
                if not algorithm.analyzer or not algorithm.analyzer.note_matcher:
                    logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有分析器或匹配器，跳过")
                    continue
                
                try:
                    matched_pairs = algorithm.analyzer.note_matcher.get_matched_pairs()
                    
                    if not matched_pairs:
                        logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有匹配数据，跳过")
                        continue
                    
                    offset_data = algorithm.analyzer.note_matcher.get_offset_alignment_data()
                    
                    # 提取按键ID、锤速和延时数据
                    key_ids = []
                    hammer_velocities = []
                    delays_ms = []
                    
                    # 创建匹配对索引到偏移数据的映射
                    offset_map = {}
                    for item in offset_data:
                        record_idx = item.get('record_index')
                        replay_idx = item.get('replay_index')
                        if record_idx is not None and replay_idx is not None:
                            offset_map[(record_idx, replay_idx)] = item
                    
                    for record_idx, replay_idx, record_note, replay_note in matched_pairs:
                        key_id = record_note.id
                        
                        if len(replay_note.hammers) > 0 and len(replay_note.hammers.values) > 0:
                            hammer_velocity = replay_note.hammers.values[0]
                        else:
                            continue
                        
                        keyon_offset = None
                        if (record_idx, replay_idx) in offset_map:
                            keyon_offset = offset_map[(record_idx, replay_idx)].get('keyon_offset', 0)
                        else:
                            try:
                                record_keyon, _ = algorithm.analyzer.note_matcher._calculate_note_times(record_note)
                                replay_keyon, _ = algorithm.analyzer.note_matcher._calculate_note_times(replay_note)
                                keyon_offset = replay_keyon - record_keyon
                            except:
                                continue
                        
                        delay_ms = abs(keyon_offset) / 10.0
                        
                        try:
                            key_id_int = int(key_id)
                            key_ids.append(key_id_int)
                            hammer_velocities.append(hammer_velocity)
                            delays_ms.append(delay_ms)
                            all_delays.append(delay_ms)
                        except (ValueError, TypeError):
                            continue
                    
                    if not key_ids:
                        logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有有效的散点图数据，跳过")
                        continue
                    
                    marker_symbol = marker_symbols[alg_idx % len(marker_symbols)]
                    colorscale = colorscales[alg_idx % len(colorscales)]
                    
                    # 添加散点图数据，使用不同的标记形状和颜色方案区分算法
                    fig.add_trace(go.Scatter(
                        x=key_ids,
                        y=hammer_velocities,
                        mode='markers',
                        name=f'{algorithm_name}',
                        marker=dict(
                            size=8,
                            color=delays_ms,
                            colorscale=colorscale,
                            colorbar=dict(
                                title=f'{algorithm_name}<br>延时 (ms)',
                                thickness=15,
                                len=0.3,
                                x=1.02 + (alg_idx * 0.08),  # 每个算法的颜色条位置不同
                                y=0.5 - (alg_idx * 0.3 / len(ready_algorithms))
                            ),
                            cmin=min(all_delays) if all_delays else 0,
                            cmax=max(all_delays) if all_delays else 100,
                            symbol=marker_symbol,
                            line=dict(width=1, color='rgba(0,0,0,0.3)')
                        ),
                        legendgroup=algorithm_name,
                        showlegend=True,
                        hovertemplate=f'算法: {algorithm_name}<br>键位: %{{x}}<br>锤速: %{{y}}<br>延时: %{{marker.color:.2f}}ms<extra></extra>'
                    ))
                    
                except Exception as e:
                    logger.warning(f"⚠️ 获取算法 '{algorithm_name}' 的按键与锤速数据失败: {e}")
                    continue
            
            if not all_delays:
                logger.warning("⚠️ 没有有效的散点图数据，无法生成图表")
                return self._create_empty_plot("没有有效的散点图数据")
            
            # 设置布局
            fig.update_layout(
                title={
                    'text': '多算法按键与锤速散点图（颜色表示延时）',
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 18, 'color': '#2c3e50'}
                },
                xaxis_title='按键ID',
                yaxis_title='锤速',
                xaxis=dict(
                    showgrid=True,
                    gridcolor='lightgray',
                    gridwidth=1,
                    dtick=10
                ),
                yaxis=dict(
                    showgrid=True,
                    gridcolor='lightgray',
                    gridwidth=1
                ),
                hovermode='closest',
                plot_bgcolor='white',
                paper_bgcolor='white',
                font=dict(size=12),
                height=500,
                showlegend=True,
                legend=dict(
                    orientation='h',
                    yanchor='bottom',
                    y=1.02,
                    xanchor='left',
                    x=0.0,
                    bgcolor='rgba(255, 255, 255, 0.9)',
                    bordercolor='gray',
                    borderwidth=1
                ),
                margin=dict(t=70, b=60, l=60, r=200)  # 增加右侧边距，为多个颜色条留出空间
            )
            
            logger.info(f"✅ 多算法按键与锤速散点图生成成功，共 {len(ready_algorithms)} 个算法")
            return fig
            
        except Exception as e:
            logger.error(f"❌ 生成多算法按键与锤速散点图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._create_empty_plot(f"生成失败: {str(e)}")
    
    def _create_empty_plot(self, message: str) -> go.Figure:
        """创建空图表（用于错误提示）"""
        fig = go.Figure()
        fig.add_annotation(
            x=0.5,
            y=0.5,
            text=message,
            showarrow=False,
            font=dict(size=16, color='gray'),
            xref='paper',
            yref='paper'
        )
        fig.update_layout(
            xaxis=dict(showgrid=False, showticklabels=False),
            yaxis=dict(showgrid=False, showticklabels=False),
            height=400
        )
        return fig

