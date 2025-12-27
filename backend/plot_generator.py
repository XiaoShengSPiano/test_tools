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

# 绘图相关导入
import spmid
import plotly.graph_objects as go

# 导入新的瀑布图生成器
from .waterfall_plot_generator import WaterfallPlotGenerator

logger = Logger.get_logger()


class PlotGenerator:
    """绘图生成器 - 负责各种图表的生成"""
    
    def __init__(self, data_filter=None):
        """初始化绘图生成器"""
        self.valid_record_data = None
        self.valid_replay_data = None
        self.matched_pairs = None
        self.analyzer = None  # SPMIDAnalyzer实例
        self.data_filter = data_filter  # DataFilter实例

        # 初始化新的瀑布图生成器
        self.waterfall_generator = WaterfallPlotGenerator()

        self._setup_chinese_font()
    
    def set_data(self, valid_record_data=None, valid_replay_data=None, matched_pairs=None, analyzer=None):
        self.valid_record_data = valid_record_data
        self.valid_replay_data = valid_replay_data
        self.matched_pairs = matched_pairs
        self.analyzer = analyzer
    
    def _setup_chinese_font(self) -> None:
        """设置中文字体"""
        try:
            # 获取系统字体候选列表
            font_candidates = self._get_system_font_candidates()
            
            # 查找可用字体
            available_font = self._find_available_font(font_candidates)
            
            if available_font:
                # 设置matplotlib字体
                plt.rcParams['font.sans-serif'] = [available_font]
                plt.rcParams['axes.unicode_minus'] = False
                logger.info(f"✅ 中文字体设置成功: {available_font}")
            else:
                logger.warning("⚠️ 未找到可用的中文字体，可能影响中文显示")
                
        except Exception as e:
            logger.error(f"中文字体设置失败: {e}")
    
    def _get_system_font_candidates(self) -> list:
        """获取系统字体候选列表"""
        return [
            'Microsoft YaHei',  # 微软雅黑
            'SimHei',           # 黑体
            'SimSun',           # 宋体
            'KaiTi',            # 楷体
            'FangSong',         # 仿宋
            'Arial Unicode MS', # Arial Unicode MS
            'DejaVu Sans'       # DejaVu Sans
        ]
    
    def _find_available_font(self, font_candidates: list) -> Optional[str]:
        """查找可用的字体"""
        available_fonts = [f.name for f in fm.fontManager.ttflist]
        
        for font in font_candidates:
            if font in available_fonts:
                logger.info(f"✅ 找到可用字体: {font}")
                return font
        
        logger.warning("⚠️ 未找到候选字体，使用系统默认字体")
        return None
    
    def _is_font_available(self, font_name: str) -> bool:
        """检查字体是否可用"""
        try:
            available_fonts = [f.name for f in fm.fontManager.ttflist]
            return font_name in available_fonts
        except Exception as e:
            logger.debug(f"⚠️ 字体检查失败: {font_name}, 错误: {e}")
            return False
    
    # TODO
    def generate_waterfall_plot(self, time_filter=None, include_all_data=True) -> Any:
        """
        生成瀑布图 - 基于匹配等级划分的数据

        Args:
            time_filter: 时间过滤器实例，用于过滤数据
            include_all_data: 兼容性参数（已废弃），现在总是使用基于匹配等级的模式

        Returns:
            Any: 瀑布图对象
        """
        try:
            # 检查是否有analyzer（包含note_matcher）
            if not self.analyzer or not hasattr(self.analyzer, 'note_matcher'):
                logger.error("没有可用的分析器或音符匹配器，无法生成瀑布图")
                return self._create_empty_plot("数据源不存在")

            # 使用基于匹配等级划分的瀑布图生成器
            logger.info("🎨 使用基于匹配等级划分的瀑布图生成器")

            fig = self.waterfall_generator.generate_comprehensive_waterfall_plot(
                self.analyzer,  # 传递完整的analyzer，包含note_matcher和错误数据
                time_filter,
                self.data_filter.key_filter if self.data_filter else None
            )

            logger.info("✅ 瀑布图生成成功")
            return fig

        except Exception as e:
            logger.error(f"瀑布图生成失败: {e}")
            logger.error(traceback.format_exc())
            return self._create_empty_plot(f"生成瀑布图失败: {str(e)}")
    
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
    
    def get_note_image_base64(self, global_index: int) -> str:
        """
        获取音符图像Base64编码
        
        Args:
            global_index: 全局索引
            
        Returns:
            str: Base64编码的图像
        """
        try:
            # 这里需要根据global_index找到对应的错误音符
            # 暂时返回空字符串，具体实现需要根据数据结构调整
            return ""
        except Exception as e:
            logger.error(f"获取音符图像失败: {e}")
            return ""
    
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
    
    # 已移除：EDA抖动点图及其数据准备与统计方法，改用现有散点图方案
    
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
        
        # 创建算法控制图注（按键用下拉菜单选择）
        self._create_algorithm_control_legends(fig, algo_info['display_names'], algorithm_colors)
        # 不再需要按键控制图注，改用UI中的下拉菜单
        
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
    
    def _handle_single_algorithm_plot(self, fig, analysis_result):
        """处理单算法模式的图表绘制"""
        interaction_plot_data = analysis_result.get('interaction_plot_data', {})
        key_data = interaction_plot_data.get('key_data', {})
        
        if not key_data:
            return
        
        # 生成按键颜色
        key_colors = self._generate_key_colors(len(key_data))
        
        # 添加数据散点
        self._add_single_algorithm_data_traces(fig, key_data, key_colors)
    
    def _configure_plot_layout(self, fig, analysis_result, is_multi_algorithm, algorithm_results):
        """配置图表布局（横轴、纵轴、图注等）"""
        # 收集所有播放锤速用于生成横轴刻度
        all_velocities = self._collect_all_velocities(analysis_result, is_multi_algorithm, algorithm_results)

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
            height=600,
            hovermode='closest',
            legend=dict(
                orientation='v',
                yanchor='top',
                y=1,
                xanchor='left',
                x=1.02,
                font=dict(size=11, color='rgba(0,0,0,1.0)')
            ),
            uirevision='key-force-interaction'
        )

    def _generate_adaptive_y_axis_config(self, delays):
        """生成Y轴配置 - 针对相对延时数据使用固定5ms刻度"""
        # 相对延时一般都在0ms附近，使用固定的5ms刻度间隔
        # 范围设置为±50ms，适合大多数相对延时数据
        return {
            'range': [-50, 50],
            'dtick': 5,  # 固定5ms刻度间隔
            'tickformat': '.1f'
        }

    def _collect_all_velocities(self, analysis_result, is_multi_algorithm, algorithm_results):
        """收集所有播放锤速"""
        all_velocities = []
        
        if is_multi_algorithm and algorithm_results:
            for alg_result in algorithm_results.values():
                interaction_data = alg_result.get('interaction_plot_data', {})
                key_data = interaction_data.get('key_data', {})
                for data in key_data.values():
                    velocities = data.get('forces', [])  # 这里的forces实际是播放锤速
                    all_velocities.extend([v for v in velocities if v > 0])
        else:
            interaction_data = analysis_result.get('interaction_plot_data', {})
            key_data = interaction_data.get('key_data', {})
            for data in key_data.values():
                velocities = data.get('forces', [])
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
    
    def _create_algorithm_control_legends(self, fig, algorithm_names, algorithm_colors):
        """创建算法控制图注（独立的图例组）"""
        
        for alg_idx, algorithm_name in enumerate(algorithm_names):
            algorithm_color = algorithm_colors[alg_idx % len(algorithm_colors)]
            
            # 控制图注：空数据，只在图例中显示
            fig.add_trace(go.Scatter(
                x=[],  # 空数组，不绘制任何点
                y=[],
                mode='markers',
                name=algorithm_name,  # 算法名称
                marker=dict(
                    size=12,
                    color=algorithm_color,
                    symbol='circle',
                    opacity=0.6
                ),
                legendgroup='algorithm_control',
                visible=True,
                showlegend=True,
                hoverinfo='skip'
            ))
    
    def _add_multi_algorithm_data_traces(self, fig, algorithm_results, algo_info, key_stats, algorithm_colors, key_colors):
        """为多算法模式添加数据散点
        
        数据源：已配对的按键数据
        横轴：log₁₀(播放锤速)
        纵轴：锤速差值（播放锤速 - 录制锤速）
        """
        internal_names = algo_info['internal_names']
        display_names = algo_info['display_names']
        all_keys = key_stats['all_keys']
        
        # 为每个算法的每个按键创建散点trace
        for alg_idx, alg_internal_name in enumerate(internal_names):
            alg_result = algorithm_results[alg_internal_name]
            alg_display_name = display_names[alg_idx]
            alg_color = algorithm_colors[alg_idx % len(algorithm_colors)]
            
            interaction_data = alg_result.get('interaction_plot_data', {})
            key_data = interaction_data.get('key_data', {})
            
            for key_idx, key_id in enumerate(all_keys):
                if key_id not in key_data:
                    continue
                
                # 提取数据并添加trace
                self._add_single_trace(
                    fig, key_data[key_id], key_id,
                    alg_display_name, alg_color,
                    key_idx, key_colors
                )
    
    def _add_single_algorithm_data_traces(self, fig, key_data, key_colors):
        """为单算法模式添加数据散点"""
        key_ids = sorted(key_data.keys())
        
        for idx, key_id in enumerate(key_ids):
            data = key_data[key_id]
            color = key_colors[idx % len(key_colors)]
            
            # 使用统一的trace添加函数
            self._add_single_trace(
                fig, data, key_id,
                algorithm_name=None,  # 单算法模式无需算法名
                algorithm_color=None,
                key_idx=idx,
                key_colors=key_colors
            )
    
    def _add_single_trace(self, fig, data, key_id, algorithm_name, algorithm_color, key_idx, key_colors):
        """添加单个散点trace
        
        Args:
            fig: Plotly图表对象
            data: 按键数据字典（forces=播放锤速, delays=锤速差值）
            key_id: 按键ID
            algorithm_name: 算法名称（多算法模式）
            algorithm_color: 算法颜色（多算法模式）
            key_idx: 按键索引
            key_colors: 按键颜色列表
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
        
        # 构建customdata: [key_id, replay_velocity, relative_delay, absolute_delay, algorithm_name, mean_delay]
        customdata = [[key_id, rv, rd, ad, algorithm_name if algorithm_name else '', mean_delay] 
                     for rv, rd, ad in zip(replay_vels, rel_delays, abs_delays)]
        
        # 确定颜色和图例
        if algorithm_name:  # 多算法模式
            color = algorithm_color
            showlegend = False
            legendgroup = f'data_{algorithm_name}_key_{key_id}'
            hover_prefix = f'<b>{algorithm_name}</b><br>'
        else:  # 单算法模式
            color = key_colors[key_idx % len(key_colors)]
            showlegend = True
            legendgroup = f'key_{key_id}'
            hover_prefix = ''
        
        fig.add_trace(go.Scatter(
            x=log10_vels,
            y=rel_delays,
            mode='markers',
            name=f'按键 {key_id}' if not algorithm_name else None,
            marker=dict(
                size=8 if algorithm_name else 10,
                color=color,
                opacity=0.8,
                line=dict(width=1, color='white')
            ),
            legendgroup=legendgroup,
            showlegend=showlegend,
            customdata=customdata,
            visible=True if algorithm_name else 'legendonly',
            hovertemplate=hover_prefix +
                         f'<b>按键 {key_id}</b><br>' +
                         '<b>log₁₀(播放锤速)</b>: %{x:.2f}<br>' +
                         '<b>播放锤速</b>: %{customdata[1]:.0f}<br>' +
                         '<b>相对延时</b>: %{y:.2f}ms<br>' +
                         '<b>原始延时</b>: %{customdata[3]:.2f}ms<br>' +
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
            
            # 检查是否是多算法模式
            is_multi_algorithm = analysis_result.get('multi_algorithm_mode', False)
            algorithm_results = analysis_result.get('algorithm_results', {})
            
            fig = go.Figure()
            
            # 定义算法颜色
            algorithm_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', 
                              '#9467bd', '#8c564b', '#e377c2', '#7f7f7f']
            
            if is_multi_algorithm and algorithm_results:
                # 多算法模式
                self._handle_multi_algorithm_plot(fig, algorithm_results, algorithm_colors)
            else:
                # 单算法模式
                self._handle_single_algorithm_plot(fig, analysis_result)
            
            # 配置图表布局
            self._configure_plot_layout(fig, analysis_result, is_multi_algorithm, algorithm_results)
            
            return fig
            
        except Exception as e:
            logger.error(f"生成交互效应图失败: {e}")
            logger.error(traceback.format_exc())
            return self._create_empty_plot(f"生成交互效应图失败: {str(e)}")