#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
绘图和图像生成模块
负责瀑布图生成、音符对比图、错误音符图像等
"""

import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import base64
import io
import math
import traceback
import numpy as np
from typing import Optional, Tuple, Any, Dict
from utils.logger import Logger
from utils.colors import ALGORITHM_COLOR_PALETTE

# 绘图相关导入
import spmid
import plotly.graph_objects as go

logger = Logger.get_logger()


class PlotGenerator:
    """绘图生成器 - 负责各种图表的生成"""
    
    def __init__(self, key_filter=None):
        """初始化绘图生成器"""
        self.valid_record_data = None
        self.valid_replay_data = None
        self.matched_pairs = None
        self.analyzer = None  # SPMIDAnalyzer实例
        self.key_filter = key_filter  # KeyFilter实例
    
    def set_data(self, valid_record_data=None, valid_replay_data=None, matched_pairs=None, analyzer=None):
        self.valid_record_data = valid_record_data
        self.valid_replay_data = valid_replay_data
        self.matched_pairs = matched_pairs
        self.analyzer = analyzer
        
    def _apply_key_filter(self, notes_data, key_filter: set):
        """
        应用按键过滤
        
        Args:
            notes_data: 音符数据列表
            key_filter: 要保留的按键ID集合
            
        Returns:
            过滤后的音符数据列表
        """
        if not notes_data or not key_filter:
            return notes_data
        
        filtered_notes = []
        for note in notes_data:
            if hasattr(note, 'id') and note.id in key_filter:
                filtered_notes.append(note)
        
        return filtered_notes
    
    def generate_watefall_conbine_plot(self, key_on: float, key_off: float, key_id: int) -> Tuple[Any, Any, Any]:
        """
        生成瀑布图对比图，使用已匹配的数据
        
        Args:
            key_on: 按键开始时间
            key_off: 按键结束时间
            key_id: 键ID
            
        Returns:
            Tuple[Any, Any, Any]: (录制音符图, 播放音符图, 对比图)
        """
        # 从matched_pairs中查找匹配的音符对
        record_note = None
        replay_note = None
        
        if hasattr(self, 'matched_pairs') and self.matched_pairs:
            for record_index, replay_index, r_note, p_note in self.matched_pairs:
                if r_note.id == key_id:
                    # 检查时间是否匹配
                    r_keyon = r_note.hammers.index[0] + r_note.offset
                    r_keyoff = r_note.after_touch.index[-1] + r_note.offset if len(r_note.after_touch) > 0 else r_note.hammers.index[0] + r_note.offset
                    
                    if abs(r_keyon - key_on) < 1000 and abs(r_keyoff - key_off) < 1000:  # 1秒容差
                        record_note = r_note
                        replay_note = p_note
                        break
        
        # 计算平均延时
        mean_delays = {}
        if hasattr(self, 'get_mean_error'):
            mean_error_0_1ms = self.get_mean_error()
            mean_delays['default'] = mean_error_0_1ms / 10.0  # 转换为毫秒

        detail_figure1 = spmid.plot_note_comparison_plotly(record_note, None, mean_delays=mean_delays)
        detail_figure2 = spmid.plot_note_comparison_plotly(None, replay_note, mean_delays=mean_delays)
        detail_figure_combined = spmid.plot_note_comparison_plotly(record_note, replay_note, mean_delays=mean_delays)

        return detail_figure1, detail_figure2, detail_figure_combined
    
    def generate_watefall_conbine_plot_by_index(self, index: int, is_record: bool) -> Tuple[Any, Any, Any]:
        """
        根据索引生成瀑布图对比图，使用已匹配的数据
        
        Args:
            index: 音符索引
            is_record: 是否为录制数据
            
        Returns:
            Tuple[Any, Any, Any]: (录制音符图, 播放音符图, 对比图)
        """
        record_note = None
        play_note = None
        
        if is_record:
            if index < 0 or index >= len(self.valid_record_data):
                return None, None, None
            record_note = self.valid_record_data[index]
            
            # 从matched_pairs中查找匹配的播放音符
            if hasattr(self, 'matched_pairs') and self.matched_pairs:
                for record_index, replay_index, r_note, p_note in self.matched_pairs:
                    if record_index == index:
                        play_note = p_note
                        break

        else:
            if index < 0 or index >= len(self.valid_replay_data):
                return None, None, None
            play_note = self.valid_replay_data[index]
            
            # 从matched_pairs中查找匹配的录制音符
            if hasattr(self, 'matched_pairs') and self.matched_pairs:
                for record_index, replay_index, r_note, p_note in self.matched_pairs:
                    if replay_index == index:
                        record_note = r_note
                        break
        
        # 计算平均延时
        mean_delays = {}
        if hasattr(self, 'get_mean_error'):
            mean_error_0_1ms = self.get_mean_error()
            mean_delays['default'] = mean_error_0_1ms / 10.0  # 转换为毫秒

        detail_figure1 = spmid.plot_note_comparison_plotly(record_note, None, mean_delays=mean_delays)
        detail_figure2 = spmid.plot_note_comparison_plotly(None, play_note, mean_delays=mean_delays)
        detail_figure_combined = spmid.plot_note_comparison_plotly(record_note, play_note, mean_delays=mean_delays)

        return detail_figure1, detail_figure2, detail_figure_combined
    
    def _create_empty_plot(self, message: str) -> Any:
        """
        创建空图表
        
        Args:
            message: 显示消息
            
        Returns:
            Any: 空图表对象
        """
        try:
            fig = go.Figure()
            fig.add_annotation(
                text=message,
                xref="paper", yref="paper",
                x=0.5, y=0.5, xanchor='center', yanchor='middle',
                showarrow=False, font_size=16
            )
            fig.update_layout(
                title="图表生成失败",
                xaxis=dict(visible=False),
                yaxis=dict(visible=False),
                plot_bgcolor='white'
            )
            return fig
        except Exception as e:
            logger.error(f"创建空图表失败: {e}")
            return None
    
    def _convert_plot_to_base64(self) -> str:
        """
        将matplotlib图表转换为Base64编码
        
        Returns:
            str: Base64编码的图像
        """
        try:
            # 将当前图表保存到内存缓冲区
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
            buffer.seek(0)
            
            # 转换为Base64
            image_base64 = base64.b64encode(buffer.getvalue()).decode()
            buffer.close()
            
            return image_base64
        except Exception as e:
            logger.error(f"图表转换Base64失败: {e}")
            return ""
    
    def _create_error_image(self, error_msg: str) -> str:
        """
        创建错误图像
        
        Args:
            error_msg: 错误消息
            
        Returns:
            str: Base64编码的错误图像
        """
        try:
            fig, ax = plt.subplots(figsize=(8, 6))
            ax.text(0.5, 0.5, f"错误: {error_msg}", 
                   ha='center', va='center', fontsize=14, 
                   bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral"))
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis('off')
            ax.set_title("图像生成失败", fontsize=16, color='red')
            
            return self._convert_plot_to_base64()
        except Exception as e:
            logger.error(f"创建错误图像失败: {e}")
            return ""
    
    
    def generate_delay_by_key_barplot(self, analysis_result: Dict[str, Any]) -> Any:
        """
        生成延时与按键关系的条形图（显示均值和标准差）
        
        Args:
            analysis_result: 延时与按键分析结果
            
        Returns:
            Any: Plotly图表对象
        """
        try:
            descriptive_stats = analysis_result.get('descriptive_stats', [])
            if not descriptive_stats:
                return self._create_empty_plot("没有描述性统计数据")
            
            # 按按键ID排序
            descriptive_stats.sort(key=lambda x: x['key_id'])
            
            key_ids = [s['key_id'] for s in descriptive_stats]
            means = [s['mean'] for s in descriptive_stats]
            stds = [s['std'] for s in descriptive_stats]
            
            # 创建条形图
            fig = go.Figure()
            
            # 添加条形图（带误差线）
            fig.add_trace(go.Bar(
                x=[str(k) for k in key_ids],
                y=means,
                error_y=dict(
                    type='data',
                    array=stds,
                    visible=True,
                    symmetric=True,
                    thickness=2,
                    width=0  # 隐藏误差线顶部的横线（T型标记）
                ),
                name='平均延时',
                marker_color='#1976d2',
                text=[f"{m:.2f}ms" for m in means],
                textposition='auto',
                hovertemplate='按键ID: %{x}<br>平均延时: %{y:.2f}ms<br>标准差: %{customdata:.2f}ms<extra></extra>',
                customdata=stds
            ))
            
            # 添加总体均值线
            overall_stats = analysis_result.get('overall_stats', {})
            overall_mean = overall_stats.get('overall_mean', 0.0)
            fig.add_hline(
                y=overall_mean,
                line_dash="dash",
                line_color="red",
                annotation_text=f"总体均值: {overall_mean:.2f}ms",
                annotation_position="right"
            )
            
            # 高亮异常按键
            anomaly_keys = analysis_result.get('anomaly_keys', [])
            if anomaly_keys:
                anomaly_key_ids = [ak['key_id'] for ak in anomaly_keys]
                for i, key_id in enumerate(key_ids):
                    if key_id in anomaly_key_ids:
                        # 添加异常按键标记
                        fig.add_annotation(
                            x=str(key_id),
                            y=means[i] + stds[i] + 1,
                            text="⚠️",
                            showarrow=True,
                            arrowhead=2,
                            arrowcolor="red",
                            font=dict(size=16, color="red")
                        )
            
            fig.update_layout(
                title={
                    'text': '各按键平均延时对比（带标准差）',
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 18, 'color': '#1976d2'}
                },
                xaxis_title='按键ID',
                yaxis_title='延时 (ms)',
                showlegend=False,
                template='plotly_white',
                height=500,
                hovermode='closest'
            )
            
            return fig
            
        except Exception as e:
            logger.error(f"生成条形图失败: {e}")
            logger.error(traceback.format_exc())
            return self._create_empty_plot(f"生成条形图失败: {str(e)}")
    
    
    
    def _handle_multi_algorithm_plot(self, fig, algorithm_results, algorithm_colors):
        """处理多算法模式的图表绘制"""
        # 获取算法名称和显示名称
        algo_info = self._prepare_algorithm_info(algorithm_results)
        
        # 收集按键统计信息
        key_stats = self._collect_key_statistics(algorithm_results, algo_info['display_names'])
        
        # 生成按键颜色
        key_colors = self._generate_key_colors(len(key_stats['all_keys']))
        
        # 添加数据散点
        self._add_multi_algorithm_data_traces(fig, algorithm_results, algo_info, key_stats, algorithm_colors, key_colors)
    
    def _prepare_algorithm_info(self, algorithm_results):
        """准备算法信息（内部名称和显示名称）"""
        internal_names = sorted(algorithm_results.keys())
        display_names = []
        display_name_count = {}
        
        for alg_name in internal_names:
            alg_result = algorithm_results[alg_name]
            display_name = alg_result.get('display_name', alg_name)
            
            # 统计重名情况
            if display_name not in display_name_count:
                display_name_count[display_name] = 0
            display_name_count[display_name] += 1
            
            # 如果重名，添加文件名后缀
            if display_name_count[display_name] > 1:
                parts = alg_name.rsplit('_', 1)
                if len(parts) == 2:
                    display_name = f"{display_name} ({parts[1]})"
            
            display_names.append(display_name)
        
        return {
            'internal_names': internal_names,
            'display_names': display_names
        }
    
    def _collect_key_statistics(self, algorithm_results, display_names):
        """收集所有按键ID和每个按键在每个曲子中的出现次数"""
        all_key_ids = set()
        key_piece_stats = {}  # {key_id: {piece_name: count}}
        
        for idx, (alg_name, alg_result) in enumerate(algorithm_results.items()):
            piece_name = display_names[idx]
            interaction_data = alg_result.get('interaction_plot_data', {})
            key_data = interaction_data.get('key_data', {})
            
            for key_id, data in key_data.items():
                all_key_ids.add(key_id)
                if key_id not in key_piece_stats:
                    key_piece_stats[key_id] = {}
                # 统计该按键在该曲子中的出现次数
                sample_count = len(data.get('forces', []))
                if sample_count > 0:
                    key_piece_stats[key_id][piece_name] = sample_count
        
        return {
            'all_keys': sorted(all_key_ids),
            'piece_stats': key_piece_stats
        }
    
    def _generate_key_colors(self, n_keys):
        """为按键生成颜色"""
        import matplotlib.cm as cm
        import matplotlib.colors as mcolors
        
        if n_keys <= 20:
            colors = cm.get_cmap('tab20')(np.linspace(0, 1, n_keys))
        else:
            colors = cm.get_cmap('viridis')(np.linspace(0, 1, n_keys))
        
        return [mcolors.rgb2hex(c[:3]) for c in colors]
    
    def _configure_plot_layout(self, fig, analysis_result, algorithm_results):
        """配置图表布局（横轴、纵轴、图注等）"""
        # 收集所有播放锤速用于生成横轴刻度
        all_velocities = self._collect_all_velocities(analysis_result, algorithm_results)

        # 生成横轴刻度
        tick_positions, tick_texts = self._generate_log_ticks(all_velocities)

        # 生成Y轴配置（相对延时使用固定配置）
        y_axis_config = self._generate_adaptive_y_axis_config(None)

        fig.update_layout(
            xaxis_title='log₁₀(播放锤速)',
            yaxis_title='相对延时 (ms)',
            xaxis=dict(
                type='linear',  # 线性轴显示log10值
                showgrid=True,
                gridcolor='lightgray',
                tickmode='array' if tick_positions else 'auto',
                tickvals=tick_positions if tick_positions else None,
                ticktext=tick_texts if tick_texts else None
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor='lightgray',
                zeroline=True,  # 显示y=0的参考线
                zerolinecolor='red',
                zerolinewidth=1.5,
                **y_axis_config  # 使用动态配置
            ),
            showlegend=True,
            template='plotly_white',
            height=800,  # 增加高度，与其他散点图保持一致
            hovermode='closest',
            legend=dict(
                x=0.01,  # 更靠左
                y=1.02,  # 移到图表上方
                xanchor='left',
                yanchor='bottom',  # 从图注底部定位，这样会完全在图表上方
                bgcolor='rgba(255,255,255,0.95)',
                bordercolor='gray',
                borderwidth=1,
                font=dict(size=10),
                orientation='h'  # 水平排列图注
            ),
            uirevision='key-force-interaction'
        )

    def _generate_adaptive_y_axis_config(self, delays):
        """生成Y轴配置 - 相对延时使用合理的固定范围"""
        # 相对延时一般都在0附近，使用 ±10ms 范围，比原来的 ±50ms 更合理
        return {
            'range': [-10, 10],
            'dtick': 2,  # 2ms刻度间隔
            'tickformat': '.1f'
        }

    def _collect_all_velocities(self, analysis_result, algorithm_results):
        """收集所有播放锤速"""
        all_velocities = []
        
        if algorithm_results:
            for alg_result in algorithm_results.values():
                interaction_data = alg_result.get('interaction_plot_data', {})
                key_data = interaction_data.get('key_data', {})
                for data in key_data.values():
                    velocities = data.get('forces', [])  # 这里的forces实际是播放锤速
                all_velocities.extend([v for v in velocities if v > 0])
        
        return all_velocities
    
    def _generate_log_ticks(self, velocities):
        """生成对数刻度的刻度点"""
        if not velocities:
            return [], []

        min_vel = min(velocities)
        max_vel = max(velocities)

        if min_vel <= 0 or max_vel <= 0:
            return [], []

        min_log = math.floor(math.log10(min_vel))
        max_log = math.ceil(math.log10(max_vel))

        # 生成更密集的刻度，每0.2个单位一个刻度
        tick_positions = []
        tick_texts = []

        current = min_log
        while current <= max_log:
            tick_positions.append(current)
            # 显示log10值本身
            tick_texts.append(f"{current:.1f}")
            current += 0.2  # 每0.2个log10单位一个刻度

        return tick_positions, tick_texts
    
    
    def _add_multi_algorithm_data_traces(self, fig, algorithm_results, algo_info, key_stats, algorithm_colors, key_colors):
        """为多算法模式添加数据散点
        
        数据源：已配对的按键数据
        横轴：log₁₀(播放锤速)
        纵轴：锤速差值（播放锤速 - 录制锤速）
        """
        internal_names = algo_info['internal_names']
        display_names = algo_info['display_names']
        all_keys = key_stats['all_keys']

        # 跟踪已添加图注的算法，避免重复显示
        legend_added_algorithms = set()
        
        # 为每个算法的每个按键创建散点trace
        for alg_idx, alg_internal_name in enumerate(internal_names):
            alg_result = algorithm_results[alg_internal_name]
            alg_display_name = display_names[alg_idx]
            alg_color = algorithm_colors[alg_idx % len(algorithm_colors)]
            
            interaction_data = alg_result.get('interaction_plot_data', {})
            key_data = interaction_data.get('key_data', {})
            
            # 决定是否为此算法显示图注（每个算法只显示一次）
            show_legend_for_algorithm = alg_display_name not in legend_added_algorithms
            if show_legend_for_algorithm:
                legend_added_algorithms.add(alg_display_name)

            for key_idx, key_id in enumerate(all_keys):
                if key_id not in key_data:
                    continue
                
                # 提取数据并添加trace（传入内部名称用于customdata）
                self._add_single_trace(
                    fig, key_data[key_id], key_id,
                    alg_internal_name, alg_color,
                    key_idx, key_colors,
                    show_legend_for_algorithm if key_idx == 0 else False,  # 只为每个算法的第一个按键显示图注
                    alg_display_name  # 传入显示名称用于图例
            )
    
    def _add_single_trace(self, fig, data, key_id, algorithm_name, algorithm_color, key_idx, key_colors, show_legend=None, display_name=None):
        """添加单个散点trace
        
        Args:
            fig: Plotly图表对象
            data: 按键数据字典（forces=播放锤速, delays=锤速差值）
            key_id: 按键ID
            algorithm_name: 算法的唯一标识（用于customdata）
            algorithm_color: 算法颜色
            key_idx: 按键索引
            key_colors: 按键颜色列表（未使用，保留用于兼容）
            show_legend: 是否显示图例
            display_name: 显示名称（用于图例和hover，如果为None则使用algorithm_name）
        """
        # 提取数据
        replay_velocities = data.get('forces', [])  # 播放锤速
        relative_delays = data.get('delays', [])  # 相对延时
        absolute_delays = data.get('absolute_delays', relative_delays)  # 原始延时
        mean_delay = data.get('mean_delay', 0)  # 整体平均延时
        
        if not replay_velocities or not relative_delays:
            return
        
        # 过滤有效数据
        valid_data = [(rv, rd, ad) for rv, rd, ad in zip(replay_velocities, relative_delays, absolute_delays) if rv > 0]
        if not valid_data:
            return
        
        replay_vels, rel_delays, abs_delays = zip(*valid_data)
        
        # 计算log10锤速
        log10_vels = [math.log10(v) for v in replay_vels]
        
        # 构建customdata: [key_id, algorithm_name, replay_velocity, relative_delay, absolute_delay, record_index, replay_index]
        # 从数据中提取索引信息
        record_indices = data.get('record_indices', [])
        replay_indices = data.get('replay_indices', [])

        if len(record_indices) == len(replay_vels) and len(replay_indices) == len(replay_vels):
            # 如果有对应的索引信息，使用它
            customdata = [[key_id, algorithm_name if algorithm_name else '', rv, rd, ad, record_indices[i], replay_indices[i]]
                         for i, (rv, rd, ad) in enumerate(zip(replay_vels, rel_delays, abs_delays))]
        else:
            # 如果没有索引信息，填充None
            logger.warning(f"⚠️ 按键 {key_id} 缺少索引信息: record_indices={len(record_indices)}, replay_indices={len(replay_indices)}, data_points={len(replay_vels)}")
            customdata = [[key_id, algorithm_name if algorithm_name else '', rv, rd, ad, None, None]
                     for rv, rd, ad in zip(replay_vels, rel_delays, abs_delays)]
        
        # 确定颜色和图例
        color = algorithm_color
        showlegend = show_legend if show_legend is not None else True
        # 使用algorithm_name作为legendgroup（唯一标识），使用display_name作为显示名称
        legendgroup = f'algorithm_{algorithm_name}'
        legend_display_name = display_name if display_name else algorithm_name
        name = legend_display_name  # 使用显示名称作为图注
        hover_prefix = f'<b>{legend_display_name}</b><br>'
        marker_size = 8
        
        fig.add_trace(go.Scatter(
            x=log10_vels,
            y=rel_delays,
            mode='markers',
            name=name,
            marker=dict(
                size=marker_size,
                color=color,
                opacity=0.8,
                line=dict(width=1, color='white')
            ),
            legendgroup=legendgroup,
            showlegend=showlegend,
            customdata=customdata,
            visible=True,  # 统一默认显示
            hovertemplate=hover_prefix +
                         f'<b>按键 {key_id}</b><br>' +
                         '<b>log₁₀(播放锤速)</b>: %{x:.2f}<br>' +
                         '<b>播放锤速</b>: %{customdata[2]:.0f}<br>' +
                         '<b>相对延时</b>: %{y:.2f}ms<br>' +
                         '<b>原始延时</b>: %{customdata[4]:.2f}ms<br>' +
                         f'<i>平均延时: {mean_delay:.2f}ms</i><extra></extra>'
        ))
    
    def generate_key_force_interaction_plot(self, analysis_result: Dict[str, Any]) -> Any:
        """
        生成按键-力度交互效应图
        横轴：log₁₀(播放锤速)
        纵轴：锤速差值（播放锤速 - 录制锤速）
        
        Args:
            analysis_result: analyze_key_force_interaction()的返回结果
            
        Returns:
            Any: Plotly图表对象
        """
        try:
            import matplotlib.cm as cm
            import matplotlib.colors as mcolors
            
            if analysis_result.get('status') != 'success':
                return self._create_empty_plot("分析失败或数据不足")
            
            # 统一使用多算法模式处理
            algorithm_results = analysis_result.get('algorithm_results', {})
            
            if not algorithm_results:
                return self._create_empty_plot("没有可用的算法结果")
            
            fig = go.Figure()
            
            # 使用全局算法颜色方案
            algorithm_colors = ALGORITHM_COLOR_PALETTE
            
            # 统一使用多算法模式处理（即使只有1个算法）
            self._handle_multi_algorithm_plot(fig, algorithm_results, algorithm_colors)
            
            # 配置图表布局
            self._configure_plot_layout(fig, analysis_result, algorithm_results)
            
            return fig
            
        except Exception as e:
            logger.error(f"生成交互效应图失败: {e}")
            logger.error(traceback.format_exc())
            return self._create_empty_plot(f"生成交互效应图失败: {str(e)}")
    
    # ==================== 音符对比图相关方法 ====================
    
    def _has_valid_data(self, note, data_type):
        """检查音符是否有有效的触后或锤子数据"""
        if note is None:
            return False
        data = getattr(note, data_type, None)
        return data is not None and not data.empty
    
    def _calculate_time_data(self, note, data_type, mean_delay_ms=0.0):
        """计算音符数据的时间轴（毫秒）"""
        data = getattr(note, data_type)
        time_actual = (data.index + note.offset) / 10.0
        time_adjusted = time_actual - mean_delay_ms
        return time_actual, time_adjusted, data.values
    
    def _add_after_touch_trace(self, fig, note, color, name, legend_name, legendgroup, 
                               row, mean_delay_ms=0.0, is_adjusted=False, algorithm_name=None):
        """添加触后曲线轨迹"""
        if not self._has_valid_data(note, 'after_touch'):
            return
        
        time_actual, time_adjusted, values = self._calculate_time_data(note, 'after_touch', mean_delay_ms)
        x_data = time_adjusted if is_adjusted else time_actual
        
        # 构建hover模板
        if algorithm_name:
            hover_parts = [f'算法: {algorithm_name}', f'实际播放时间: %{{customdata:.2f}} ms']
            if is_adjusted:
                hover_parts.extend([f'平均延时: {mean_delay_ms:.2f} ms', '调整后时间: %{x:.2f} ms', '类型: 调整后曲线'])
            else:
                hover_parts.append('类型: 原始曲线')
            hover_parts.append('触后压力: %{y}')
            hovertemplate = '<br>'.join(hover_parts) + '<extra></extra>'
        else:
            hovertemplate = f'{name}时间: %{{x:.2f}} ms<br>触后压力: %{{y}}<extra></extra>'
        
        fig.add_trace(
            go.Scatter(
                x=x_data, y=values, mode='lines', name=name,
                line=dict(color=color, width=3 if '录制' in name or '回放' in name else 2, 
                         dash='solid' if '录制' in name or not is_adjusted else 'dash'),
                showlegend=True, legend=legend_name, legendgroup=legendgroup,
                customdata=time_actual, hovertemplate=hovertemplate
            ),
            row=row, col=1
        )
    
    def _add_hammer_trace(self, fig, note, color, name, legend_name, legendgroup,
                         row, symbol='circle', size=8, algorithm_name=None):
        """添加锤子数据点轨迹"""
        if not self._has_valid_data(note, 'hammers'):
            return

        time_actual, _, values = self._calculate_time_data(note, 'hammers')

        # 过滤掉锤速为0的锤击时间点
        valid_indices = [i for i, velocity in enumerate(values) if velocity != 0]
        if not valid_indices:
            # 如果没有有效的锤击点，直接返回
            return

        filtered_time = [time_actual[i] for i in valid_indices]
        filtered_values = [values[i] for i in valid_indices]

        first_hammer_time = filtered_time[0] if len(filtered_time) > 0 else 0.0

        # 构建hover模板
        if algorithm_name:
            hovertemplate = f'算法: {algorithm_name}<br>锤子时间: %{{customdata:.2f}} ms<br>锤子速度: %{{y}}<extra></extra>'
        else:
            hover_parts = [f'{name}时间: %{{x:.2f}} ms', f'锤子速度: %{{y}}']
            if '录制' in name:
                hover_parts.append(f'第一个锤子时间: {first_hammer_time:.2f} ms')
            hovertemplate = '<br>'.join(hover_parts) + '<extra></extra>'

        fig.add_trace(
            go.Scatter(
                x=filtered_time, y=filtered_values, mode='markers', name=name,
                marker=dict(color=color, size=size, symbol=symbol),
                showlegend=True, legend=legend_name, legendgroup=legendgroup,
                customdata=filtered_time, hovertemplate=hovertemplate
            ),
            row=row, col=1
        )
    
    def _add_record_traces(self, fig, record_note):
        """添加录制数据轨迹（触后+锤子，在两个子图）"""
        if record_note is None:
            return
        
        try:
            for row in [1, 2]:
                legend_name = "legend" if row == 1 else "legend2"
                self._add_after_touch_trace(fig, record_note, 'blue', '录制触后', 
                                           legend_name, 'record', row)
                self._add_hammer_trace(fig, record_note, 'blue', '录制锤子', 
                                      legend_name, 'record', row)
        except Exception as e:
            logger.warning(f"⚠️ 绘制录制数据时出错: {e}")
    
    def _add_play_traces(self, fig, play_note, algorithm_name, mean_delays, 
                        show_other_algorithms):
        """添加回放数据轨迹（触后+锤子，上子图原始曲线，下子图调整曲线）"""
        if play_note is None:
            return
        
        try:
            mean_delay_ms = mean_delays.get(algorithm_name, 0.0) if algorithm_name else 0.0
            alg_prefix = f"{algorithm_name} - " if algorithm_name and show_other_algorithms else ""
            alg_group = f'algorithm_{algorithm_name}' if algorithm_name else 'algorithm_default'
            
            # 上子图：原始曲线（不偏移）
            self._add_after_touch_trace(fig, play_note, 'red', f'{alg_prefix}回放触后(原始)', 
                                        'legend', alg_group, 1, 0.0, False, 
                                        algorithm_name if algorithm_name else None)
            
            # 下子图：调整后曲线（偏移）
            self._add_after_touch_trace(fig, play_note, 'red', f'{alg_prefix}回放触后(调整后)', 
                                        'legend2', alg_group, 2, mean_delay_ms, True, 
                                        algorithm_name if algorithm_name else None)
            
            # 锤子数据在两个子图（不偏移）
            for row in [1, 2]:
                legend_name = "legend" if row == 1 else "legend2"
                self._add_hammer_trace(fig, play_note, 'red', f'{alg_prefix}回放锤子', 
                                      legend_name, alg_group, row, 'circle', 8, 
                                      algorithm_name if algorithm_name else None)
        except Exception as e:
            logger.warning(f"⚠️ 绘制回放数据时出错: {e}")
    
    def _add_other_algorithm_traces(self, fig, other_algorithm_notes, mean_delays):
        """添加其他算法的播放曲线（在上下两个子图都显示）"""
        colors = ['green', 'orange', 'purple', 'brown', 'pink', 'gray', 'olive', 'cyan']
        
        for idx, (alg_name, play_note) in enumerate(other_algorithm_notes):
            if play_note is None:
                continue
            
            color = colors[idx % len(colors)]
            mean_delay_ms = mean_delays.get(alg_name, 0.0)
            alg_group = f'algorithm_{alg_name}'
            
            try:
                # 上子图：显示原始曲线（不偏移）
                self._add_after_touch_trace(fig, play_note, color, f'{alg_name} - 回放触后(原始)',
                                           'legend', alg_group, 1, 0.0, False, alg_name)
                self._add_hammer_trace(fig, play_note, color, f'{alg_name} - 回放锤子',
                                      'legend', alg_group, 1, 'square', 6, alg_name)
                
                # 下子图：显示调整后曲线（偏移）
                self._add_after_touch_trace(fig, play_note, color, f'{alg_name} - 回放触后(调整后)',
                                           'legend2', alg_group, 2, mean_delay_ms, True, alg_name)
                self._add_hammer_trace(fig, play_note, color, f'{alg_name} - 回放锤子',
                                      'legend2', alg_group, 2, 'square', 6, alg_name)
            except Exception as e:
                logger.warning(f"⚠️ 绘制算法 '{alg_name}' 的回放数据时出错: {e}")
    
    def _configure_note_comparison_layout(self, fig, record_note, play_note, algorithm_name):
        """配置音符对比图的布局"""
        # 生成标题
        title_parts = []
        if algorithm_name:
            title_parts.append(f"算法: {algorithm_name}")
        if record_note:
            title_parts.append(f"录制音符ID: {record_note.id}")
        if play_note:
            title_parts.append(f"回放音符ID: {play_note.id}")
        
        title = "音符数据对比分析"
        if title_parts:
            title += f" ({', '.join(title_parts)})"
        
        # 无数据提示
        if len(fig.data) == 0:
            fig.add_annotation(
                text="无数据可显示", xref="paper", yref="paper",
                x=0.5, y=0.5, xanchor='center', yanchor='middle',
                showarrow=False, font_size=16
            )
        
        # 轴配置（复用配置）
        axis_config = dict(
            title=dict(text='时间 (ms)', font=dict(size=12)),
            showgrid=True, showline=True, linewidth=1, 
            linecolor='black', mirror=True
        )
        yaxis_config = dict(
            title=dict(text='数值（触后压力/锤子速度）', font=dict(size=12)),
            showgrid=True, showline=True, linewidth=1,
            linecolor='black', mirror=True
        )
        
        # 图例配置（复用配置）
        legend_config_base = dict(
            orientation="h", yanchor="bottom", xanchor="left", x=0.0,
            traceorder='grouped', tracegroupgap=10, itemwidth=30,
            font=dict(size=9), bgcolor='rgba(255,255,255,0.95)',
            entrywidthmode='pixels', entrywidth=240,
            groupclick='toggleitem', itemsizing='trace', itemclick='toggle'
        )
        
        fig.update_layout(
            title=dict(text=title, x=0.5, xanchor='center', y=0.95, 
                      yanchor='top', font=dict(size=16, weight='bold')),
            xaxis=axis_config, yaxis=yaxis_config,
            xaxis2=axis_config, yaxis2=yaxis_config,
            height=900, width=1200, template='simple_white',
            legend=dict(**legend_config_base, y=1.05, bordercolor='blue', borderwidth=1),
            legend2=dict(**legend_config_base, y=0.40, bordercolor='red', borderwidth=1),
            hovermode='x unified',
            margin=dict(l=80, r=60, t=160, b=100)
        )
    
    def generate_note_comparison_plot(self, record_note, play_note, algorithm_name=None, other_algorithm_notes=None, mean_delays=None):
        """
        生成音符详细对比图（触后数据和锤子数据对比）

        Args:
            record_note: 录制音符数据，如果为None则不绘制录制数据
            play_note: 回放音符数据，如果为None则不绘制回放数据
            algorithm_name: 算法名称（可选），用于在标题中显示
            other_algorithm_notes: 其他算法的播放音符列表，格式为 [(algorithm_name, play_note), ...]
            mean_delays: 各算法的平均延时字典，格式为 {algorithm_name: mean_delay_ms}，用于调整播放曲线的时间轴

        Returns:
            go.Figure: Plotly图表对象
        """
        other_algorithm_notes = other_algorithm_notes or []
        mean_delays = mean_delays or {}

        # 创建子图：上方显示偏移前曲线，下方显示偏移后曲线
        from plotly.subplots import make_subplots
        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=('偏移前曲线对比', '偏移后曲线对比'),
            shared_xaxes=False,
            vertical_spacing=0.3,
            row_heights=[0.5, 0.5]
        )
        
        # 添加各类轨迹
        self._add_record_traces(fig, record_note)
        self._add_play_traces(fig, play_note, algorithm_name, mean_delays, bool(other_algorithm_notes))
        self._add_other_algorithm_traces(fig, other_algorithm_notes, mean_delays)
        
        # 配置布局
        self._configure_note_comparison_layout(fig, record_note, play_note, algorithm_name)
        
        return fig