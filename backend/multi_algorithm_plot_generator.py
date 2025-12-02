#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
多算法图表生成器

负责生成支持多算法对比的图表，使用面向对象设计。
"""

from typing import List, Optional, Any, Dict, Tuple
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
                # 关键修改：只使用匹配对的数据，与延时时间序列图保持一致
                if not algorithm.analyzer:
                    logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有分析器，跳过")
                    continue
                
                # 关键：使用 matched_pairs 和 offset_data，确保与延时时间序列图完全一致
                # 延时时间序列图只显示已匹配的音符对，所以瀑布图也应该只显示匹配的音符
                if not hasattr(algorithm.analyzer, 'note_matcher') or not algorithm.analyzer.note_matcher:
                    logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有匹配器，跳过")
                    continue
                
                matched_pairs = algorithm.analyzer.note_matcher.get_matched_pairs()
                offset_data = algorithm.analyzer.note_matcher.get_offset_alignment_data()
                
                if not matched_pairs or not offset_data:
                    logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有匹配数据，跳过")
                    continue
                
                logger.info(f"📊 算法 '{algorithm_name}': 使用 matched_pairs 生成瀑布图，共 {len(matched_pairs)} 个匹配对")
                
                # 计算当前算法的y_offset（每个算法偏移100个单位，确保范围明确）
                current_y_offset = alg_idx * algorithm_y_range
                
                # 收集当前算法的数据点
                # 直接从 offset_data 遍历，确保与延时时间序列图使用相同的数据
                algorithm_bars = []
                
                for item in offset_data:
                    record_index = item.get('record_index')
                    replay_index = item.get('replay_index')
                    record_keyon = item.get('record_keyon', 0)  # 单位：0.1ms
                    record_keyoff = item.get('record_keyoff', 0)  # 单位：0.1ms
                    replay_keyon = item.get('replay_keyon', 0)  # 单位：0.1ms
                    replay_keyoff = item.get('replay_keyoff', 0)  # 单位：0.1ms
                    key_id = item.get('key_id')
                    
                    if record_index is None or replay_index is None:
                        continue
                    
                    # 从 matched_pairs 中查找对应的 Note 对象（用于获取力度值）
                    record_note = None
                    replay_note = None
                    for r_idx, p_idx, r_note, p_note in matched_pairs:
                        if r_idx == record_index and p_idx == replay_index:
                            record_note = r_note
                            replay_note = p_note
                            break
                    
                    if record_note is None or replay_note is None:
                        continue
                    
                    # 处理录制数据
                    y_offset_record = base_offsets['record'] + current_y_offset
                    if len(record_note.hammers) > 0:
                        v_hammer_record = record_note.hammers.values[0]
                    else:
                        v_hammer_record = 0
                    
                    algorithm_bars.append({
                        't_on': record_keyon,  # 单位：0.1ms，与延时时间序列图完全一致
                        't_off': record_keyoff,
                        'key_id': key_id + y_offset_record,
                        'value': v_hammer_record,
                        'label': 'record',
                        'index': record_index,
                        'algorithm_name': algorithm_name,
                        'original_key_id': key_id
                    })
                    all_values.append(v_hammer_record)
                    
                    # 处理播放数据
                    y_offset_play = base_offsets['play'] + current_y_offset
                    if len(replay_note.hammers) > 0:
                        v_hammer_play = replay_note.hammers.values[0]
                    else:
                        v_hammer_play = 0
                    
                    algorithm_bars.append({
                        't_on': replay_keyon,  # 单位：0.1ms
                        't_off': replay_keyoff,
                        'key_id': key_id + y_offset_play,
                        'value': v_hammer_play,
                        'label': 'play',
                        'index': replay_index,
                        'algorithm_name': algorithm_name,
                        'original_key_id': key_id
                    })
                    all_values.append(v_hammer_play)
                
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
                            f'按键按下: {bar["t_on"]/10:.2f}ms<br>'
                            f'按键释放: {bar["t_off"]/10:.2f}ms<br>'
                            f'索引: {bar["index"]}<br>'
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
                # 删除title，因为UI区域已有标题
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
            
            # 创建5个子图（添加相对延时图）
            fig = make_subplots(
                rows=5, cols=1,
                subplot_titles=('中位数偏移', '均值偏移', '标准差', '方差', '相对延时（减去各自曲子的平均延时）'),
                vertical_spacing=0.05,
                row_heights=[0.20, 0.20, 0.20, 0.20, 0.20]
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
                    
                    # 计算该算法的平均延时（用于计算相对延时）
                    me_0_1ms = algorithm.analyzer.get_mean_error() if hasattr(algorithm.analyzer, 'get_mean_error') else 0.0
                    mean_delay = me_0_1ms / 10.0  # 平均延时（ms，带符号）
                    
                    # 按按键ID分组有效匹配的偏移数据（只使用keyon_offset）
                    key_groups = defaultdict(list)
                    key_groups_relative = defaultdict(list)  # 用于存储相对延时
                    for item in offset_data:
                        key_id = item.get('key_id', 'N/A')
                        keyon_offset = item.get('keyon_offset', 0)  # 原始延时（0.1ms单位，带符号）
                        keyon_offset_abs = abs(keyon_offset)  # 绝对值用于其他统计
                        keyon_offset_ms = keyon_offset / 10.0  # 转换为ms
                        relative_delay = keyon_offset_ms - mean_delay  # 相对延时
                        key_groups[key_id].append(keyon_offset_abs)
                        key_groups_relative[key_id].append(relative_delay)
                    
                    # 提取数据
                    algorithm_key_ids = []
                    algorithm_median = []
                    algorithm_mean = []
                    algorithm_std = []
                    algorithm_variance = []
                    algorithm_relative_mean = []  # 相对延时的均值
                    
                    for key_id, offsets in key_groups.items():
                        if offsets:
                            try:
                                key_id_int = int(key_id)
                                algorithm_key_ids.append(key_id_int)
                                algorithm_median.append(np.median(offsets) / 10.0)  # 转换为ms
                                algorithm_mean.append(np.mean(offsets) / 10.0)  # 转换为ms
                                algorithm_std.append(np.std(offsets) / 10.0)  # 转换为ms
                                algorithm_variance.append(np.var(offsets) / 100.0)  # 转换为ms²
                                
                                # 计算相对延时的均值
                                if key_id in key_groups_relative:
                                    relative_delays = key_groups_relative[key_id]
                                    algorithm_relative_mean.append(np.mean(relative_delays))
                                else:
                                    algorithm_relative_mean.append(0.0)
                            except (ValueError, TypeError):
                                continue
                    
                    if algorithm_key_ids:
                        all_algorithms_data.append({
                            'name': algorithm_name,
                            'display_name': algorithm.metadata.display_name,  # 显示名称
                            'key_ids': algorithm_key_ids,
                            'median': algorithm_median,
                            'mean': algorithm_mean,
                            'std': algorithm_std,
                            'variance': algorithm_variance,
                            'relative_mean': algorithm_relative_mean,  # 相对延时的均值
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
                display_name = alg_data.get('display_name', algorithm_name)  # 使用显示名称
                color = alg_data['color']
                
                # 计算x轴位置（每个算法偏移一定距离）
                x_positions = []
                median_values = []
                mean_values = []
                std_values = []
                variance_values = []
                relative_mean_values = []
                
                # 创建键位到值的映射
                key_to_median = dict(zip(alg_data['key_ids'], alg_data['median']))
                key_to_mean = dict(zip(alg_data['key_ids'], alg_data['mean']))
                key_to_std = dict(zip(alg_data['key_ids'], alg_data['std']))
                key_to_variance = dict(zip(alg_data['key_ids'], alg_data['variance']))
                key_to_relative_mean = dict(zip(alg_data['key_ids'], alg_data['relative_mean']))
                
                for key_id in all_key_ids:
                    if key_id in alg_data['key_ids']:
                        x_positions.append(key_id + (alg_idx - num_algorithms / 2 + 0.5) * bar_width)
                        median_values.append(key_to_median[key_id])
                        mean_values.append(key_to_mean[key_id])
                        std_values.append(key_to_std[key_id])
                        variance_values.append(key_to_variance[key_id])
                        relative_mean_values.append(key_to_relative_mean[key_id])
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
                        name=display_name,
                        marker_color=color,
                        opacity=0.8,
                        width=bar_width,
                        text=[f'{val:.2f}' for val in median_values],
                        textposition='outside',
                        textfont=dict(size=8),
                        showlegend=True,
                        legendgroup=algorithm_name,
                        hovertemplate=f'算法: {display_name}<br>键位: %{{x:.0f}}<br>中位数: %{{y:.2f}}ms<extra></extra>'
                    ),
                    row=1, col=1
                )
                
                # 添加均值柱状图（带数值标注）
                fig.add_trace(
                    go.Bar(
                        x=x_positions,
                        y=mean_values,
                        name=display_name,
                        marker_color=color,
                        opacity=0.8,
                        width=bar_width,
                        text=[f'{val:.2f}' for val in mean_values],
                        textposition='outside',
                        textfont=dict(size=8),
                        showlegend=False,  # 只在第一个子图显示图例
                        legendgroup=algorithm_name,
                        hovertemplate=f'算法: {display_name}<br>键位: %{{x:.0f}}<br>均值: %{{y:.2f}}ms<extra></extra>'
                    ),
                    row=2, col=1
                )
                
                # 添加标准差柱状图（带数值标注）
                fig.add_trace(
                    go.Bar(
                        x=x_positions,
                        y=std_values,
                        name=display_name,
                        marker_color=color,
                        opacity=0.8,
                        width=bar_width,
                        text=[f'{val:.2f}' for val in std_values],
                        textposition='outside',
                        textfont=dict(size=8),
                        showlegend=False,
                        legendgroup=algorithm_name,
                        hovertemplate=f'算法: {display_name}<br>键位: %{{x:.0f}}<br>标准差: %{{y:.2f}}ms<extra></extra>'
                    ),
                    row=3, col=1
                )
                
                # 添加方差柱状图（带数值标注）
                fig.add_trace(
                    go.Bar(
                        x=x_positions,
                        y=variance_values,
                        name=display_name,
                        marker_color=color,
                        opacity=0.8,
                        width=bar_width,
                        text=[f'{val:.2f}' for val in variance_values],
                        textposition='outside',
                        textfont=dict(size=8),
                        showlegend=False,
                        legendgroup=algorithm_name,
                        hovertemplate=f'算法: {display_name}<br>键位: %{{x:.0f}}<br>方差: %{{y:.2f}}ms²<extra></extra>'
                    ),
                    row=4, col=1
                )
                
                # 添加相对延时柱状图（带数值标注）
                fig.add_trace(
                    go.Bar(
                        x=x_positions,
                        y=relative_mean_values,
                        name=display_name,
                        marker_color=color,
                        opacity=0.8,
                        width=bar_width,
                        text=[f'{val:.2f}' for val in relative_mean_values],
                        textposition='outside',
                        textfont=dict(size=8),
                        showlegend=False,
                        legendgroup=algorithm_name,
                        hovertemplate=f'算法: {display_name}<br>键位: %{{x:.0f}}<br>相对延时: %{{y:.2f}}ms<extra></extra>'
                    ),
                    row=5, col=1
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
            fig.update_xaxes(
                tickmode='linear',
                tick0=min_key_id,
                dtick=1,
                title_text='键位ID',
                range=[min_key_id - 1, max_key_id + 1],
                row=5, col=1
            )
            
            # 设置y轴标题
            fig.update_yaxes(title_text='中位数偏移 (ms)', row=1, col=1)
            fig.update_yaxes(title_text='均值偏移 (ms)', row=2, col=1)
            fig.update_yaxes(title_text='标准差 (ms)', row=3, col=1)
            fig.update_yaxes(title_text='方差 (ms²)', row=4, col=1)
            fig.update_yaxes(title_text='相对延时 (ms)', row=5, col=1)
            
            # 设置布局（删除title，因为UI区域已有标题）
            fig.update_layout(
                height=2750,  # 增加高度以容纳5个子图（2200 * 5/4 ≈ 2750）
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
        
        使用相对时延（原始时延 - 平均时延）：
        - 消除整体偏移，更公平地比较不同算法的稳定性
        - 均值接近0，标准差保持不变
        
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
                    
                    # 步骤1：提取原始延时数据（带符号的keyon_offset）
                    absolute_delays_ms = [item.get('keyon_offset', 0.0) / 10.0 for item in offset_data]
                    
                    if not absolute_delays_ms:
                        logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有有效延时数据，跳过")
                        continue
                    
                    # 步骤2：计算该算法的平均延时（用于计算相对延时）
                    n = len(absolute_delays_ms)
                    mean_delay_ms = sum(absolute_delays_ms) / n
                    
                    # 步骤3：计算相对延时（消除整体偏移）
                    # 相对延时 = 原始延时 - 平均延时
                    # 这样均值接近0，标准差保持不变，更适合评估稳定性
                    delays_ms = [delay - mean_delay_ms for delay in absolute_delays_ms]
                    
                    all_delays.extend(delays_ms)
                    
                    # 步骤4：计算统计量（基于相对延时）
                    # 注意：相对延时的均值应该接近0（理论上为0，但由于浮点运算可能有微小偏差）
                    mean_val = sum(delays_ms) / n  # 均值 ≈ 0
                    if n > 1:
                        # 样本方差：相对延时的方差和标准差与原始延时相同（因为减去常数不改变方差）
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
                        opacity=0.85,  # 增加不透明度，使颜色更明显
                        marker_line_color=color,  # 添加边框颜色，使用相同颜色但更深的边框
                        marker_line_width=0.5,
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
            
            # 设置布局（删除title，因为UI区域已有标题）
            fig.update_layout(
                xaxis_title='相对延时 (ms)',
                yaxis_title='概率密度',
                bargap=0.05,
                plot_bgcolor='white',
                paper_bgcolor='white',
                font=dict(size=12),
                height=500,
                clickmode='event+select',  # 启用点击和选择事件
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
                # 删除title，因为UI区域已有标题
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
                    
                    # 获取matched_pairs以便查找时间信息
                    matched_pairs = algorithm.analyzer.matched_pairs
                    record_note_dict = {r_idx: r_note for r_idx, _, r_note, _ in matched_pairs}
                    replay_note_dict = {p_idx: p_note for _, p_idx, _, p_note in matched_pairs}

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
                            
                            # 获取录制和播放按键的时间信息
                            record_hammer_time_ms = 0.0
                            replay_hammer_time_ms = 0.0

                            # 获取录制音符的锤子时间
                            if record_index in record_note_dict:
                                record_note = record_note_dict[record_index]
                                if hasattr(record_note, 'hammers') and record_note.hammers is not None and not record_note.hammers.empty:
                                    record_hammer_time_ms = (record_note.hammers.index[0] + record_note.offset) / 10.0

                            # 获取播放音符的锤子时间
                            if replay_index in replay_note_dict:
                                replay_note = replay_note_dict[replay_index]
                                if hasattr(replay_note, 'hammers') and replay_note.hammers is not None and not replay_note.hammers.empty:
                                    replay_hammer_time_ms = (replay_note.hammers.index[0] + replay_note.offset) / 10.0

                            key_ids.append(key_id_int)
                            delays_ms.append(delay_ms)
                            customdata_list.append([
                                record_index,
                                replay_index,
                                key_id_int,
                                delay_ms,
                                algorithm_name,
                                record_hammer_time_ms,
                                replay_hammer_time_ms
                            ])
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
                        hovertemplate=f"算法: {algorithm_name}<br>键位: %{{x}}<br>延时: %{{customdata[3]:.2f}}ms<br>Z-Score: %{{y:.2f}}<br>录制锤子时间: %{{customdata[5]:.2f}}ms<br>播放锤子时间: %{{customdata[6]:.2f}}ms<extra></extra>"
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
                # 删除title，因为UI区域已有标题
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
                        
                        # 跳过锤速为0或负数的数据点（对数无法处理）
                        if hammer_velocity <= 0:
                            continue
                        
                        # 获取按键ID
                        key_id = record_note.id if hasattr(record_note, 'id') else None
                        
                        hammer_velocities.append(hammer_velocity)
                        delays_ms.append(delay_ms)
                        # 存储record_idx、replay_idx、algorithm_name和key_id，用于点击事件识别和显示
                        scatter_customdata.append([record_idx, replay_idx, algorithm_name, key_id])
                    
                    if not hammer_velocities:
                        logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有有效的散点图数据，跳过")
                        continue
                    
                    # 计算Z-Score（与按键与延时Z-Score散点图相同的计算方式）
                    import numpy as np
                    import math
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
                    
                    # 将锤速转换为对数形式（类似分贝）：log10(velocity)
                    log_velocities = [math.log10(v) for v in hammer_velocities]
                    
                    color = colors[alg_idx % len(colors)]
                    
                    # 添加散点图数据（x轴使用对数形式的锤速，y轴使用Z-Score值）
                    # customdata格式: [delay_ms, original_velocity, record_idx, replay_idx, algorithm_name, key_id]
                    # 第一个元素用于hover显示延时，第二个元素用于hover显示原始锤速，后四个用于点击事件识别和显示
                    combined_customdata = [[delay_ms, orig_vel, record_idx, replay_idx, alg_name, key_id] 
                                          for delay_ms, orig_vel, (record_idx, replay_idx, alg_name, key_id) 
                                          in zip(delays_ms, hammer_velocities, scatter_customdata)]
                    
                    fig.add_trace(go.Scatter(
                        x=log_velocities,
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
                        hovertemplate=f'算法: {algorithm_name}<br>按键: %{{customdata[5]}}<br>锤速: %{{customdata[1]:.0f}} (log: %{{x:.2f}})<br>延时: %{{customdata[0]:.2f}}ms<br>Z-Score: %{{y:.2f}}<extra></extra>',
                        customdata=combined_customdata
                    ))
                    
                    # 添加Z-Score参考线（与按键与延时Z-Score散点图相同）
                    if len(log_velocities) > 0:
                        # 获取x轴范围（使用所有算法的对数范围）
                        all_log_velocities = []
                        for alg in ready_algorithms:
                            try:
                                matched_pairs = alg.analyzer.note_matcher.get_matched_pairs()
                                for record_idx, replay_idx, record_note, replay_note in matched_pairs:
                                    if len(replay_note.hammers) > 0 and len(replay_note.hammers.values) > 0:
                                        vel = replay_note.hammers.values[0]
                                        if vel > 0:
                                            all_log_velocities.append(math.log10(vel))
                            except:
                                continue
                        
                        # 对数形式
                        x_min = min(all_log_velocities) if all_log_velocities else 0
                        x_max = max(all_log_velocities) if all_log_velocities else 2
                        
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
                # 删除title，因为UI区域已有标题
                xaxis_title='锤速（log₁₀）',
                yaxis_title='Z-Score（标准化延时）',
                xaxis=dict(
                    showgrid=True,
                    gridcolor='lightgray',
                    gridwidth=1,
                    # 使用线性刻度，让Plotly自动处理，但设置合适的范围
                    autorange=True,
                    # 设置刻度格式
                    tickformat='.1f',  # 显示1位小数
                    dtick=0.2  # 每0.2个单位一个刻度
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
                # 删除title，因为UI区域已有标题
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
    
    def _extract_song_identifier(self, filename: str) -> str:
        """
        从文件名中提取曲子标识（用于判断是否是同一首曲子）
        
        Args:
            filename: 原始文件名
            
        Returns:
            str: 曲子标识（去掉路径和扩展名）
        """
        import os
        # 去掉路径，只保留文件名
        basename = os.path.basename(filename)
        # 去掉扩展名
        song_id = os.path.splitext(basename)[0]
        return song_id
    
    def _should_generate_time_series_plot(self, algorithms: List[AlgorithmDataset]) -> Tuple[bool, str]:
        """
        判断是否应该生成延时时间序列图
        
        条件：
        1. 至少有2个算法
        2. 如果算法名称（display_name）不同，直接允许生成（不同算法的同首曲子）
        3. 如果算法名称相同，需要检查文件名，确保是同一首曲子（同种算法的不同曲子不绘制）
        
        Args:
            algorithms: 算法数据集列表
            
        Returns:
            Tuple[bool, str]: (是否应该生成, 原因说明)
        """
        if not algorithms or len(algorithms) < 2:
            return False, "需要至少2个算法才能进行对比"
        
        # 检查算法名称（display_name）
        display_names = set(alg.metadata.display_name for alg in algorithms)
        
        # 如果算法名称不同，说明是不同算法的同首曲子，直接允许生成（不需要检查文件名）
        if len(display_names) >= 2:
            return True, ""
        
        # 如果算法名称相同，需要检查文件名，确保是同一首曲子
        # 如果文件名不同，说明是同种算法的不同曲子，不应该绘制
        song_identifiers = set(self._extract_song_identifier(alg.metadata.filename) for alg in algorithms)
        if len(song_identifiers) > 1:
            return False, f"检测到同种算法的不同曲子（{len(song_identifiers)}首），延时时间序列图仅支持同一首曲子的不同算法对比"
        
        # 算法名称相同且文件名相同（这种情况理论上不应该出现，因为内部标识是唯一的）
        # 但为了安全，返回False
        return False, "所有算法名称和文件名都相同，无法进行算法对比"
    
    def generate_multi_algorithm_delay_time_series_plot(
        self,
        algorithms: List[AlgorithmDataset]
    ) -> Any:
        """
        生成多算法延时时间序列图（叠加显示，不同颜色，图例控制）
        
        注意：仅当存在不同算法且是同一首曲子时才绘制
        
        Args:
            algorithms: 激活的算法数据集列表
            
        Returns:
            go.Figure: Plotly图表对象
        """
        if not algorithms:
            logger.warning("⚠️ 没有激活的算法，无法生成多算法延时时间序列图")
            return self._create_empty_plot("没有激活的算法")
        
        try:
            # 过滤出就绪的算法
            ready_algorithms = [alg for alg in algorithms if alg.is_ready()]
            if not ready_algorithms:
                logger.warning("⚠️ 没有就绪的算法，无法生成多算法延时时间序列图")
                return self._create_empty_plot("没有就绪的算法")
            
            # 检查是否应该生成图表
            should_generate, reason = self._should_generate_time_series_plot(ready_algorithms)
            if not should_generate:
                logger.info(f"ℹ️ 跳过延时时间序列图生成: {reason}")
                return self._create_empty_plot(reason)
            
            logger.info(f"📊 开始生成多算法延时时间序列图，共 {len(ready_algorithms)} 个算法")
            
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
            
            # 收集所有算法的数据，用于计算全局统计量
            all_delays = []
            
            # 不绘制录制音轨，直接绘制各算法的播放音轨
            for alg_idx, algorithm in enumerate(ready_algorithms):
                algorithm_name = algorithm.metadata.algorithm_name  # 内部唯一标识
                display_name = algorithm.metadata.display_name  # 显示名称
                
                if not algorithm.analyzer or not algorithm.analyzer.note_matcher:
                    logger.warning(f"⚠️ 算法 '{display_name}' 没有分析器或匹配器，跳过")
                    continue
                
                try:
                    offset_data = algorithm.analyzer.get_offset_alignment_data()
                    
                    if not offset_data:
                        logger.warning(f"⚠️ 算法 '{display_name}' 没有匹配数据，跳过")
                        continue
                    
                    # 提取时间和延时数据
                    data_points = []
                    
                    for item in offset_data:
                        record_keyon = item.get('record_keyon', 0)  # 单位：0.1ms
                        keyon_offset = item.get('keyon_offset', 0.0)  # 单位：0.1ms
                        key_id = item.get('key_id')
                        record_index = item.get('record_index')
                        replay_index = item.get('replay_index')
                        
                        if record_keyon is None or keyon_offset is None:
                            continue
                        
                        # 转换为ms单位
                        time_ms = record_keyon / 10.0
                        delay_ms = keyon_offset / 10.0
                        
                        data_points.append({
                            'time': time_ms,
                            'delay': delay_ms,
                            'key_id': key_id if key_id is not None else 'N/A',
                            'record_index': record_index,
                            'replay_index': replay_index
                        })
                    
                    if not data_points:
                        logger.warning(f"⚠️ 算法 '{display_name}' 没有有效时间序列数据，跳过")
                        continue
                    
                    # 按时间排序，确保按时间顺序显示
                    data_points.sort(key=lambda x: x['time'])
                    
                    # 计算该算法的平均延时（用于计算相对延时）
                    me_0_1ms = algorithm.analyzer.get_mean_error() if hasattr(algorithm.analyzer, 'get_mean_error') else 0.0
                    mean_delay = me_0_1ms / 10.0  # 平均延时（ms，带符号）
                    
                    # 计算相对延时：每个点的延时减去该算法的平均延时
                    # 标准公式：相对延时 = 延时 - 平均延时（对所有点统一适用）
                    relative_delays_ms = []
                    for point in data_points:
                        delay_ms = point['delay']
                        relative_delay = delay_ms - mean_delay
                        relative_delays_ms.append(relative_delay)
                    
                    # 提取排序后的数据
                    times_ms = [point['time'] for point in data_points]  # 录制时间
                    delays_ms = [point['delay'] for point in data_points]  # 保留原始延时用于hover显示
                    # 计算播放时间 = 录制时间 + 延时
                    replay_times_ms = [point['time'] + point['delay'] for point in data_points]
                    # X轴使用偏移后的播放时间：播放时间 - 平均延时 = 录制时间 + 相对延时
                    replay_times_offset_ms = [replay_time - mean_delay for replay_time in replay_times_ms]
                    # customdata 包含 [key_id, record_index, replay_index, algorithm_name, 原始延时, 平均延时, 播放时间, 录制时间]，用于点击时查找匹配对和显示原始值
                    customdata_list = [[point['key_id'], point['record_index'], point['replay_index'], algorithm_name, point['delay'], mean_delay, replay_time, point['time']] 
                                      for point, replay_time in zip(data_points, replay_times_ms)]
                    
                    all_delays.extend(relative_delays_ms)  # 使用相对延时用于统计
                    color = colors[alg_idx % len(colors)]
                    
                    # 添加播放音轨散点图（X轴=偏移后的播放时间，Y轴=相对延时）
                    fig.add_trace(go.Scatter(
                        x=replay_times_offset_ms,  # X轴使用偏移后的播放时间（播放时间 - 平均延时）
                        y=relative_delays_ms,  # Y轴使用相对延时
                        mode='markers+lines',
                        name=f'{display_name} (平均延时: {mean_delay:.2f}ms)',
                        marker=dict(
                            size=5,
                            color=color,
                            line=dict(width=0.5, color=color)
                        ),
                        line=dict(color=color, width=1.5),
                        legendgroup=algorithm_name,
                        showlegend=True,
                        hovertemplate='<b>算法</b>: ' + display_name + '<br>' +
                                     '<b>偏移后播放时间（X轴）</b>: %{x:.2f}ms<br>' +
                                     '<b>相对延时（Y轴）</b>: %{y:.2f}ms<br>' +
                                     '<b>实际播放时间</b>: %{customdata[6]:.2f}ms<br>' +
                                     '<b>录制时间</b>: %{customdata[7]:.2f}ms<br>' +
                                     '<b>原始延时</b>: %{customdata[4]:.2f}ms<br>' +
                                     '<b>按键ID</b>: %{customdata[0]}<br>' +
                                     '<extra></extra>',
                        customdata=customdata_list
                    ))
                    
                    # 为每个算法计算独立的统计量，添加独立的参考线
                    if delays_ms and len(delays_ms) > 0:
                        # 使用该算法自己的数据计算标准差
                        std_0_1ms = algorithm.analyzer.get_standard_deviation() if hasattr(algorithm.analyzer, 'get_standard_deviation') else 0.0
                        
                        # 转换为ms单位
                        std_delay = std_0_1ms / 10.0
                        
                        # 获取该算法的偏移后播放时间范围（用于参考线）
                        replay_time_offset_min = min(replay_times_offset_ms) if replay_times_offset_ms else 0
                        replay_time_offset_max = max(replay_times_offset_ms) if replay_times_offset_ms else 1
                        
                        # 添加该算法的零线参考线（相对延时的均值应该为0）
                        fig.add_trace(go.Scatter(
                            x=[replay_time_offset_min, replay_time_offset_max],
                            y=[0, 0],
                            mode='lines',
                            name=f'{display_name} - 零线',
                            line=dict(dash='dash', color=color, width=1.5),
                            hovertemplate=f'<b>{display_name} 零线</b>: 0.00ms<extra></extra>',
                            showlegend=False,
                            legendgroup=algorithm_name
                        ))
                        
                        # 添加该算法的±3σ参考线（相对延时的±3σ，以0为中心）
                        if std_delay > 0:
                            fig.add_trace(go.Scatter(
                                x=[replay_time_offset_min, replay_time_offset_max],
                                y=[3 * std_delay, 3 * std_delay],
                                mode='lines',
                                name=f'{display_name} - +3σ',
                                line=dict(dash='dot', color=color, width=1),
                                hovertemplate=f'<b>{display_name} +3σ</b>: {3 * std_delay:.2f}ms<extra></extra>',
                                showlegend=False,
                                legendgroup=algorithm_name
                            ))
                            fig.add_trace(go.Scatter(
                                x=[replay_time_offset_min, replay_time_offset_max],
                                y=[-3 * std_delay, -3 * std_delay],
                                mode='lines',
                                name=f'{display_name} - -3σ',
                                line=dict(dash='dot', color=color, width=1),
                                hovertemplate=f'<b>{display_name} -3σ</b>: {-3 * std_delay:.2f}ms<extra></extra>',
                                showlegend=False,
                                legendgroup=algorithm_name
                            ))
                    
                except Exception as e:
                    logger.warning(f"⚠️ 获取算法 '{display_name}' 的时间序列数据失败: {e}")
                    continue
            
            if not all_delays:
                logger.warning("⚠️ 没有有效的时间序列数据，无法生成图表")
                return self._create_empty_plot("没有有效的时间序列数据")
            
            # 设置布局
            fig.update_layout(
                # 删除title，因为UI区域已有标题
                xaxis_title='偏移后播放时间 (播放时间 - 平均延时) (ms)',
                yaxis_title='相对延时 (ms)',
                plot_bgcolor='white',
                paper_bgcolor='white',
                font=dict(size=12),
                height=500,
                hovermode='closest',
                legend=dict(
                    orientation='h',
                    yanchor='bottom',
                    y=1.05,
                    xanchor='left',
                    x=0.0,
                    bgcolor='rgba(255, 255, 255, 0.9)',
                    bordercolor='gray',
                    borderwidth=1
                ),
                margin=dict(t=100, b=60, l=60, r=60)
            )
            
            logger.info(f"✅ 多算法延时时间序列图生成成功，共 {len(ready_algorithms)} 个算法")
            return fig
            
        except Exception as e:
            logger.error(f"❌ 生成多算法延时时间序列图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._create_empty_plot(f"生成失败: {str(e)}")
    
    def generate_relative_delay_distribution_plot(self, analysis_result: Dict[str, Any]) -> Any:
        """
        生成相对延时分布直方图 + 密度曲线
        
        每个曲子单独一个子图，最后是汇总图
        
        Args:
            analysis_result: get_same_algorithm_relative_delay_analysis()的返回结果
            
        Returns:
            go.Figure: Plotly图表对象（包含多个子图）
        """
        try:
            if analysis_result.get('status') != 'success':
                return self._create_empty_plot(analysis_result.get('message', '分析失败'))
            
            algorithm_groups = analysis_result.get('algorithm_groups', {})
            overall_relative_delays = analysis_result.get('overall_relative_delays', [])
            statistics = analysis_result.get('statistics', {})
            
            if not overall_relative_delays:
                return self._create_empty_plot("没有有效的相对延时数据")
            
            import numpy as np
            from scipy import stats
            
            # 收集所有需要绘制的曲子信息
            all_songs = []  # [(display_name, filename_display, relative_delays, group_relative_delays), ...]
            for display_name, group_data in algorithm_groups.items():
                song_data = group_data.get('song_data', [])
                group_relative_delays = group_data.get('relative_delays', [])
                
                if not group_relative_delays:
                    continue
                
                # 添加每个曲子
                for song_info in song_data:
                    song_relative_delays = song_info.get('relative_delays', [])
                    if song_relative_delays:
                        filename_display = song_info.get('filename_display', song_info.get('filename', '未知文件'))
                        all_songs.append((display_name, filename_display, song_relative_delays, None))
                
                # 添加汇总（每个算法组一个汇总）
                all_songs.append((display_name, '汇总', None, group_relative_delays))
            
            if not all_songs:
                return self._create_empty_plot("没有有效的相对延时数据")
            
            # 创建子图：每个曲子一个子图 + 每个算法组一个汇总子图
            num_subplots = len(all_songs)
            subplot_titles = []
            for display_name, filename_display, _, _ in all_songs:
                if filename_display == '汇总':
                    subplot_titles.append(f'{display_name} (汇总)')
                else:
                    subplot_titles.append(f'{display_name} - {filename_display}')
            
            # 创建子图
            fig = make_subplots(
                rows=num_subplots,
                cols=1,
                subplot_titles=subplot_titles,
                vertical_spacing=0.06,  # 减小子图之间的间距
                row_heights=[1.0] * num_subplots  # 每个子图高度相等
            )
            
            # 颜色方案
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
            
            # 为每个子图绘制数据
            algorithm_color_map = {}  # 记录每个算法使用的颜色
            color_idx = 0
            
            for subplot_idx, (display_name, filename_display, song_relative_delays, group_relative_delays) in enumerate(all_songs, 1):
                # 确定使用的数据
                if filename_display == '汇总':
                    # 汇总图：使用合并后的数据
                    delays_array = np.array(group_relative_delays)
                else:
                    # 单个曲子：使用该曲子的数据
                    delays_array = np.array(song_relative_delays)
                
                # 获取或分配颜色
                if display_name not in algorithm_color_map:
                    algorithm_color_map[display_name] = colors[color_idx % len(colors)]
                    color_idx += 1
                base_color = algorithm_color_map[display_name]
                r = int(base_color[1:3], 16)
                g = int(base_color[3:5], 16)
                b = int(base_color[5:7], 16)
                
                # 计算直方图数据
                hist, bin_edges = np.histogram(delays_array, bins=50, density=False)
                bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
                
                # 为每个bin创建customdata，包含子图信息
                customdata_list = []
                for i, bin_center in enumerate(bin_centers):
                    bin_left = bin_edges[i]
                    bin_right = bin_edges[i + 1]
                    customdata_list.append([
                        subplot_idx,  # 子图索引
                        display_name,  # 算法显示名称
                        filename_display,  # 文件名显示
                        bin_center,  # bin中心值
                        bin_left,  # bin左边界
                        bin_right  # bin右边界
                    ])
                
                # 计算密度曲线（KDE）
                kde = stats.gaussian_kde(delays_array)
                x_density = np.linspace(delays_array.min(), delays_array.max(), 200)
                y_density = kde(x_density) * len(delays_array)  # 转换为频数
                
                # 添加直方图
                fig.add_trace(
                    go.Bar(
                        x=bin_centers,
                        y=hist,
                        name='相对延时分布',
                        marker=dict(
                            color=f'rgba({r}, {g}, {b}, 0.6)',
                            line=dict(color=base_color, width=1.5 if filename_display == '汇总' else 1)
                        ),
                        opacity=0.7,
                        showlegend=False,  # 不在图注中显示，因为每个子图独立
                        hovertemplate=f'相对延时: %{{x:.2f}} ms<br>频数: %{{y}}<extra></extra>',
                        customdata=customdata_list  # 添加customdata用于点击回调
                    ),
                    row=subplot_idx,
                    col=1
                )
                
                # 添加密度曲线
                fig.add_trace(
                    go.Scatter(
                        x=x_density,
                        y=y_density,
                        mode='lines',
                        name='密度曲线',
                        line=dict(
                            color=base_color,
                            width=3 if filename_display == '汇总' else 2,
                            dash='dash' if filename_display == '汇总' else 'solid'
                        ),
                        showlegend=False,  # 不在图注中显示
                        hovertemplate=f'相对延时: %{{x:.2f}} ms<br>密度: %{{y:.2f}}<extra></extra>'
                    ),
                    row=subplot_idx,
                    col=1
                )
            
            # 为每个子图添加统计量标注和布局设置
            for subplot_idx, (display_name, filename_display, song_relative_delays, group_relative_delays) in enumerate(all_songs, 1):
                # 确定使用的数据
                if filename_display == '汇总':
                    delays_array = np.array(group_relative_delays)
                else:
                    delays_array = np.array(song_relative_delays)
                
                # 计算统计量
                mean = np.mean(delays_array)
                std = np.std(delays_array)
                median = np.median(delays_array)
                count = len(delays_array)
                
                # 计算±1σ、±2σ、±3σ的百分比
                within_1sigma = np.sum(np.abs(delays_array - mean) <= std) / count * 100
                within_2sigma = np.sum(np.abs(delays_array - mean) <= 2 * std) / count * 100
                within_3sigma = np.sum(np.abs(delays_array - mean) <= 3 * std) / count * 100
                
                # 添加±1σ、±2σ、±3σ区间（简洁显示：只显示背景色区域，不显示文字标注）
                for sigma, color in [(1, 'rgba(255, 0, 0, 0.08)'),   # ±1σ：浅红色，透明度低
                                     (2, 'rgba(255, 0, 0, 0.12)'),   # ±2σ：稍深红色
                                     (3, 'rgba(255, 0, 0, 0.15)')]:  # ±3σ：更深红色
                    fig.add_vrect(
                        x0=mean - sigma * std,
                        x1=mean + sigma * std,
                        fillcolor=color,
                        layer="below",
                        line_width=0,
                        row=subplot_idx,
                        col=1
                    )
                
                # 添加均值线（简化：只显示线条，不显示文字标注）
                fig.add_vline(
                    x=mean,
                    line_dash="dash",
                    line_color="green",
                    line_width=1.5,
                    row=subplot_idx,
                    col=1
                )
                
                # 添加中位数线（简化：只显示线条，不显示文字标注）
                fig.add_vline(
                    x=median,
                    line_dash="dot",
                    line_color="orange",
                    line_width=1.5,
                    row=subplot_idx,
                    col=1
                )
                
                # 添加统计信息文本标注（只在最后一个子图添加整体统计信息）
                if subplot_idx == len(all_songs):
                    # 使用整体统计信息
                    overall_mean = statistics.get('mean', 0)
                    overall_std = statistics.get('std', 0)
                    overall_median = statistics.get('median', 0)
                    overall_count = statistics.get('count', 0)
                    overall_1sigma = statistics.get('within_1sigma_percent', 0)
                    overall_2sigma = statistics.get('within_2sigma_percent', 0)
                    overall_3sigma = statistics.get('within_3sigma_percent', 0)
                    
                    fig.add_annotation(
                        x=0.02,
                        y=0.98,
                        xref=f'x{subplot_idx} domain',
                        yref=f'y{subplot_idx} domain',
                        text=f"整体统计:<br>均值: {overall_mean:.2f} ms<br>标准差: {overall_std:.2f} ms<br>中位数: {overall_median:.2f} ms<br>数据点数: {overall_count}<br>±1σ: {overall_1sigma:.1f}%<br>±2σ: {overall_2sigma:.1f}%<br>±3σ: {overall_3sigma:.1f}%",
                        showarrow=False,
                        align='left',
                        bgcolor='rgba(255, 255, 255, 0.8)',
                        bordercolor='rgba(0, 0, 0, 0.3)',
                        borderwidth=1,
                        font=dict(size=9)
                    )
                
                # 更新每个子图的坐标轴
                fig.update_xaxes(title_text='相对延时 (ms)', row=subplot_idx, col=1)
                fig.update_yaxes(title_text='频数', row=subplot_idx, col=1)
            
            # 根据子图数量调整图表高度（增加每个子图的高度，避免挤压）
            base_height_per_subplot = 500  # 增加每个子图的高度
            total_height = base_height_per_subplot * num_subplots
            
            # 更新整体布局
            fig.update_layout(
                title='',
                height=total_height,
                hovermode='x unified',
                template='plotly_white',
                showlegend=False,  # 不使用图注，因为每个子图独立
                margin=dict(l=80, r=60, t=60, b=80)  # 增加上下边距
            )
            
            logger.info(f"✅ 相对延时分布图生成成功，共 {len(overall_relative_delays)} 个数据点")
            return fig
            
        except Exception as e:
            logger.error(f"❌ 生成相对延时分布图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._create_empty_plot(f"生成失败: {str(e)}")

