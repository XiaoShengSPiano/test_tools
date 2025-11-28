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
    def generate_waterfall_plot(self, time_filter=None) -> Any:
        """
        生成瀑布图 - 调用SPMIDAnalyzer获取有效数据
        
        Args:
            time_filter: 时间过滤器实例，用于获取过滤后的数据
        
        Returns:
            Any: 瀑布图对象
        """
        try:
            # 检查是否有可用的数据源
            has_data = (self.valid_record_data and self.valid_replay_data) or self.analyzer
            if not has_data:
                logger.error("没有可用的数据源，无法生成瀑布图")
                return self._create_empty_plot("数据源不存在")
            
            # 获取数据
            if time_filter:
                # 使用时间过滤后的数据
                filtered_record_data, filtered_replay_data = time_filter.get_filtered_data()
                logger.info(f"⏰ 时间过滤结果: 录制{len(filtered_record_data)}个音符, 播放{len(filtered_replay_data)}个音符")
                
                # 如果时间过滤返回了有效数据，使用过滤后的数据
                if filtered_record_data and filtered_replay_data:
                    valid_record_data = filtered_record_data
                    valid_replay_data = filtered_replay_data
                    logger.info(f"✅ 使用时间过滤后的数据")
                else:
                    # 时间过滤返回空数据，回退到原始数据
                    logger.warning("⚠️ 时间过滤返回空数据，回退到原始数据")
                    if self.valid_record_data and self.valid_replay_data:
                        valid_record_data = self.valid_record_data
                        valid_replay_data = self.valid_replay_data
                        logger.info(f"📊 使用PlotGenerator存储的数据: 录制{len(valid_record_data)}个音符, 播放{len(valid_replay_data)}个音符")
                    elif self.analyzer:
                        valid_record_data = self.analyzer.get_valid_record_data()
                        valid_replay_data = self.analyzer.get_valid_replay_data()
                        logger.info(f"📊 使用Analyzer数据: 录制{len(valid_record_data)}个音符, 播放{len(valid_replay_data)}个音符")
                    else:
                        valid_record_data = None
                        valid_replay_data = None
                        logger.warning("⚠️ 没有可用的数据源")
            else:
                # 优先使用PlotGenerator自己存储的数据
                if self.valid_record_data and self.valid_replay_data:
                    valid_record_data = self.valid_record_data
                    valid_replay_data = self.valid_replay_data
                    logger.info(f"📊 使用PlotGenerator存储的数据: 录制{len(valid_record_data)}个音符, 播放{len(valid_replay_data)}个音符")
                elif self.analyzer:
                    # 备选方案：从analyzer获取数据
                    valid_record_data = self.analyzer.get_valid_record_data()
                    valid_replay_data = self.analyzer.get_valid_replay_data()
                    logger.info(f"📊 使用Analyzer数据: 录制{len(valid_record_data)}个音符, 播放{len(valid_replay_data)}个音符")
                else:
                    valid_record_data = None
                    valid_replay_data = None
                    logger.warning("⚠️ 没有可用的数据源")
            
            if not valid_record_data or not valid_replay_data:
                logger.error("有效数据不存在，无法生成瀑布图")
                return self._create_empty_plot("数据不存在")
            
            # 应用按键过滤
            if self.data_filter and self.data_filter.key_filter:
                logger.info(f"🔍 应用按键过滤: {sorted(list(self.data_filter.key_filter))}")
                valid_record_data = self._apply_key_filter(valid_record_data, self.data_filter.key_filter)
                valid_replay_data = self._apply_key_filter(valid_replay_data, self.data_filter.key_filter)
                logger.info(f"📊 按键过滤后: 录制{len(valid_record_data)}个音符, 播放{len(valid_replay_data)}个音符")
            
            # 使用spmid模块生成瀑布图
            # 注意：time_range 参数在 generate_waterfall_plot 中暂不支持，需要通过 update_layout 设置
            fig = spmid.plot_bar_plotly(valid_record_data, valid_replay_data)
            
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
    
    def generate_delay_by_key_boxplot(self, analysis_result: Dict[str, Any]) -> Any:
        """
        生成延时与按键关系的箱线图
        
        Args:
            analysis_result: analyze_delay_by_key()的返回结果
            
        Returns:
            Any: Plotly图表对象
        """
        try:
            
            descriptive_stats = analysis_result.get('descriptive_stats', [])
            if not descriptive_stats:
                return self._create_empty_plot("没有描述性统计数据")
            
            # 准备数据
            key_ids = [s['key_id'] for s in descriptive_stats]
            means = [s['mean'] for s in descriptive_stats]
            
            # 创建箱线图
            fig = go.Figure()
            
            # 添加箱线图
            fig.add_trace(go.Box(
                y=means,
                x=[str(k) for k in key_ids],
                name='平均延时',
                boxmean='sd',
                marker_color='#1976d2',
                line=dict(color='#0d47a1', width=2)
            ))
            
            # 添加均值线
            overall_stats = analysis_result.get('overall_stats', {})
            overall_mean = overall_stats.get('overall_mean', 0.0)
            fig.add_hline(
                y=overall_mean,
                line_dash="dash",
                line_color="red",
                annotation_text=f"总体均值: {overall_mean:.2f}ms",
                annotation_position="right"
            )
            
            fig.update_layout(
                title={
                    'text': '延时与按键关系分析 - 箱线图',
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 18, 'color': '#1976d2'}
                },
                xaxis_title='按键ID',
                yaxis_title='延时 (ms)',
                showlegend=True,
                template='plotly_white',
                height=500,
                hovermode='closest'
            )
            
            return fig
            
        except Exception as e:
            logger.error(f"生成箱线图失败: {e}")
            logger.error(traceback.format_exc())
            return self._create_empty_plot(f"生成箱线图失败: {str(e)}")
    
    def generate_delay_by_key_barplot(self, analysis_result: Dict[str, Any]) -> Any:
        """
        生成延时与按键关系的条形图（显示均值和标准差）
        
        Args:
            analysis_result: analyze_delay_by_key()的返回结果
            
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
    
    def generate_delay_by_velocity_analysis_plot(self, analysis_result: Dict[str, Any]) -> Any:
        """
        生成延时与锤速关系的分析图表（散点图+分组统计）
        
        Args:
            analysis_result: analyze_delay_by_velocity()的返回结果
            
        Returns:
            Any: Plotly图表对象
        """
        try:
            
            scatter_data = analysis_result.get('scatter_data', {})
            velocities = scatter_data.get('velocities', [])
            delays = scatter_data.get('delays', [])

            if not velocities or not delays:
                return self._create_empty_plot("没有散点图数据")

            # 过滤掉非正值
            valid_data = [(v, d) for v, d in zip(velocities, delays) if v > 0]
            if not valid_data:
                return self._create_empty_plot("没有有效的锤速数据")
            
            velocities_clean = [v for v, d in valid_data]
            delays_clean = [d for v, d in valid_data]
            log10_velocities = [np.log10(v) for v in velocities_clean]


            fig = go.Figure()

            # 添加散点图 - 使用log10(锤速)作为横坐标
            fig.add_trace(go.Scatter(
                x=log10_velocities,
                y=delays_clean,
                mode='markers',
                name='数据点',
                marker=dict(
                    size=6,
                    color='#d32f2f',
                    opacity=0.6,
                    line=dict(width=1, color='#b71c1c')
                ),
                hovertemplate='锤速: %{customdata:.2f}<br>log₁₀(锤速): %{x:.2f}<br>延时: %{y:.2f}ms<extra></extra>',
                customdata=velocities_clean  # 在hover中显示原始锤速值
            ))
            
            # 添加分组统计（按锤速区间）
            grouped_analysis = analysis_result.get('grouped_analysis', {})
            groups = grouped_analysis.get('groups', [])
            if groups:
                for group in groups:
                    v_min = group.get('velocity_min', 0)
                    v_max = group.get('velocity_max', float('inf'))
                    mean_delay = group.get('mean_delay', 0)
                    mean_velocity = group.get('mean_velocity', 0)
                    count = group.get('count', 0)
                    label = group.get('range_label', '')
                    
                    if mean_velocity > 0:
                        fig.add_trace(go.Scatter(
                            x=[np.log10(mean_velocity)],  # 使用log10(平均锤速)值
                            y=[mean_delay],
                            mode='markers',
                            name=label,
                            marker=dict(
                                size=15,
                                symbol='diamond',
                                color='#7b1fa2',
                                line=dict(width=2, color='#4a148c')
                            ),
                            hovertemplate=f'{label}<br>平均锤速: {mean_velocity:.2f}<br>log₁₀(锤速): %{{x:.2f}}<br>平均延时: %{{y:.2f}}ms<br>样本数: {count}<extra></extra>'
                        ))
            
            # 添加相关性信息文本
            correlation_result = analysis_result.get('correlation_result', {})
            pearson_r = correlation_result.get('pearson_r', None)
            pearson_p = correlation_result.get('pearson_p', None)
            pearson_significant = correlation_result.get('pearson_significant', False)
            
            if pearson_r is not None:
                corr_text = f"皮尔逊相关系数: r={pearson_r:.4f}, p={pearson_p:.4f}"
                if pearson_significant:
                    corr_text += " (显著)"
                else:
                    corr_text += " (不显著)"
                
                fig.add_annotation(
                    x=0.02,
                    y=0.98,
                    xref='paper',
                    yref='paper',
                    text=corr_text,
                    showarrow=False,
                    bgcolor='rgba(255,255,255,0.8)',
                    bordercolor='#1976d2',
                    borderwidth=2,
                    font=dict(size=12, color='#2c3e50')
                )
            
            fig.update_layout(
                title={
                    'text': '延时与锤速关系分析',
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 18, 'color': '#d32f2f'}
                },
                xaxis_title='log₁₀(锤速)',
                yaxis_title='延时 (ms)',
                xaxis=dict(
                    showgrid=True,
                    gridcolor='lightgray',
                    gridwidth=1,
                    showticklabels=True,
                    # 手动设置刻度以确保显示合适的范围
                    tickmode='linear',
                    tick0=min(log10_velocities) if log10_velocities else 0,
                    dtick=0.1,  # 每0.1个单位一个刻度
                    range=[min(log10_velocities) - 0.1, max(log10_velocities) + 0.1] if log10_velocities else None
                ),
                showlegend=True,
                template='plotly_white',
                height=500,
                hovermode='closest',
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                )
            )
            
            return fig
            
        except Exception as e:
            logger.error(f"生成延时与锤速分析图失败: {e}")
            logger.error(traceback.format_exc())
            return self._create_empty_plot(f"生成分析图失败: {str(e)}")
    
    
    def _create_algorithm_control_legends(self, fig, algorithm_names, algorithm_colors):
        """创建算法控制图注（独立的图例组）"""
        
        for alg_idx, algorithm_name in enumerate(algorithm_names):
            algorithm_color = algorithm_colors[alg_idx % len(algorithm_colors)]
            
            fig.add_trace(go.Scatter(
                x=[None],  # 使用None，不显示在图表上
                y=[None],
                mode='markers',
                name=algorithm_name,  # 算法名称
                marker=dict(
                    size=12,  # 未选中状态的默认大小
                    color=algorithm_color,
                    symbol='circle',  # 算法用圆形
                    line=dict(width=1, color='rgba(0,0,0,0.3)'),
                    opacity=0.4  # 默认较透明（未选中状态）
                ),
                legendgroup='algorithm_control',  # 算法控制图例组（独立）
                visible=True,  # 图例始终可见
                showlegend=True,
                hovertemplate=f'<b>{algorithm_name}</b><br>点击选择/取消选择此算法<extra></extra>'
            ))
    
    def _create_key_control_legends(self, fig, all_key_ids, key_color_hex, key_piece_stats=None):
        """创建按键控制图注（独立的图例组）
        
        Args:
            fig: Plotly图表对象
            all_key_ids: 所有按键ID列表
            key_color_hex: 按键颜色列表
            key_piece_stats: 每个按键在每个曲子中的出现次数统计（可选）
               格式: {key_id: {piece_name: count}}
        """
        
        for key_idx, key_id in enumerate(all_key_ids):
            key_color = key_color_hex[key_idx % len(key_color_hex)]
            
            # 构建按键名称和hover信息，如果有统计信息则添加
            if key_piece_stats and key_id in key_piece_stats:
                piece_stats = key_piece_stats[key_id]
                # 构建统计文本：例如 "曲子A: 5次, 曲子B: 3次"
                stats_text = ', '.join([f'{piece}: {count}次' for piece, count in sorted(piece_stats.items())])
                # 计算总次数
                total_count = sum(piece_stats.values())
                # 在图例名称中显示统计信息（格式：按键 {key_id} (曲子A:5, 曲子B:3)）
                # 如果统计信息太长，可以只显示总次数
                if len(stats_text) > 40:  # 如果统计文本太长，只显示总次数
                    key_name = f'按键 {key_id} (总计:{total_count}次)'
                else:
                    key_name = f'按键 {key_id} ({stats_text})'
                # 在hover中显示详细统计
                hover_text = f'<b>按键 {key_id}</b><br>统计: {stats_text}<br>总计: {total_count}次<br>点击选择/取消选择此按键<extra></extra>'
            else:
                key_name = f'按键 {key_id}'
                hover_text = f'<b>按键 {key_id}</b><br>点击选择/取消选择此按键<extra></extra>'
            
            fig.add_trace(go.Scatter(
                x=[None],  # 使用None，不显示在图表上
                y=[None],
                mode='markers',
                name=key_name,
                marker=dict(
                    size=14,  # 未选中状态的默认大小
                    color=key_color,
                    symbol='square',  # 按键用方形
                    line=dict(width=1, color='rgba(0,0,0,0.3)'),
                    opacity=0.4  # 默认较透明（未选中状态）
                ),
                legendgroup='key_control',  # 按键控制图例组（独立）
                visible=True,  # 图例始终可见
                showlegend=True,
                hovertemplate=hover_text,
                # 在customdata中存储统计信息，用于后续显示
                customdata=[key_piece_stats.get(key_id, {}) if key_piece_stats else {}]
            ))
    
    def _add_data_traces_multi_algorithm(self, fig, all_key_ids, algorithm_internal_names, algorithm_display_names, algorithm_results, algorithm_colors):
        """
        为多算法模式添加数据traces
        
        Args:
            fig: Plotly图表对象
            all_key_ids: 所有按键ID列表
            algorithm_internal_names: 算法内部名称列表（用于查找数据）
            algorithm_display_names: 算法显示名称列表（用于UI显示）
            algorithm_results: 算法结果字典（key为内部名称）
            algorithm_colors: 算法颜色列表
        """
        
        # 为每个算法的每个按键生成数据trace（只显示散点）
        for key_idx, key_id in enumerate(all_key_ids):
            for alg_idx, algorithm_internal_name in enumerate(algorithm_internal_names):
                # 使用内部名称查找数据
                alg_result = algorithm_results[algorithm_internal_name]
                interaction_plot_data = alg_result.get('interaction_plot_data', {})
                key_data = interaction_plot_data.get('key_data', {})
                
                if key_id not in key_data:
                    continue  # 如果该算法没有这个按键的数据，跳过
                
                # 使用显示名称用于UI显示
                algorithm_display_name = algorithm_display_names[alg_idx]
                
                # 使用算法颜色，而不是按键颜色，便于区分不同算法
                algorithm_color = algorithm_colors[alg_idx % len(algorithm_colors)]
                
                data = key_data[key_id]
                forces = data.get('forces', [])
                delays = data.get('delays', [])  # 相对延时
                absolute_delays = data.get('absolute_delays', delays)  # 原始延时
                mean_delay = data.get('mean_delay', 0)  # 整体平均延时
                record_indices = data.get('record_indices', [])
                replay_indices = data.get('replay_indices', [])
                
                if forces and delays:
                    # 过滤掉非正值
                    valid_data = [(f, d, ad) for f, d, ad in zip(forces, delays, absolute_delays) if f > 0]
                    if not valid_data:
                        continue
                    
                    forces_clean = [f for f, d, ad in valid_data]
                    delays_clean = [d for f, d, ad in valid_data]
                    absolute_delays_clean = [ad for f, d, ad in valid_data]
                    
                    # 构建customdata，包含索引信息用于点击事件
                    # 格式: [key_id, algorithm_display_name, orig_force, abs_delay, rel_delay, log10_force, record_idx, replay_idx]
                    customdata_list = []
                    for i, (orig_force, abs_delay, rel_delay) in enumerate(zip(forces_clean, absolute_delays_clean, delays_clean)):
                        record_idx = record_indices[i] if i < len(record_indices) else None
                        replay_idx = replay_indices[i] if i < len(replay_indices) else None
                        log10_force = math.log10(orig_force) if orig_force > 0 else 0
                        customdata_list.append([
                            key_id, algorithm_display_name, orig_force, abs_delay, rel_delay,
                            log10_force, record_idx, replay_idx
                        ])
                    
                    fig.add_trace(go.Scatter(
                        x=forces_clean,  # 使用原始力度值，Plotly的log轴会自动处理
                        y=delays_clean,
                        mode='markers',
                        name=None,
                        marker=dict(
                            size=8,
                            color=algorithm_color,
                            opacity=0.9,
                            line=dict(width=1, color='white')
                        ),
                        # legendgroup使用显示名称，用于匹配算法控制图注
                        legendgroup=f'data_{algorithm_display_name}_key_{key_id}',
                        showlegend=False,
                        # customdata中存储显示名称、原始力度和索引，用于匹配、显示和点击事件
                        customdata=customdata_list,
                        visible=False,  # 默认不显示，需要选择后才显示
                        hovertemplate=f'<b>{algorithm_display_name}</b><br>' +
                                     f'<b>按键 {key_id}</b><br>' +
                                     '<b>力度</b>: %{x:.0f} (log₁₀: %{customdata[5]:.2f})<br>' +
                                     '<b>相对延时</b>: %{y:.2f}ms<br>' +
                                     '<b>原始延时</b>: %{customdata[3]:.2f}ms<br>' +
                                     f'<i>平均延时: {mean_delay:.2f}ms</i><extra></extra>'
                    ))
    
    def _add_data_traces_single_algorithm(self, fig, key_data, color_hex):
        """为单算法模式添加数据traces"""
        
        key_ids = sorted(key_data.keys())
        
        for idx, key_id in enumerate(key_ids):
            data = key_data[key_id]
            color = color_hex[idx % len(color_hex)]
            
            forces = data.get('forces', [])
            delays = data.get('delays', [])  # 相对延时
            absolute_delays = data.get('absolute_delays', delays)  # 原始延时
            mean_delay = data.get('mean_delay', 0)  # 整体平均延时
            record_indices = data.get('record_indices', [])
            replay_indices = data.get('replay_indices', [])
            
            if forces and delays:
                # 过滤掉非正值
                valid_data = [(f, d, ad) for f, d, ad in zip(forces, delays, absolute_delays) if f > 0]
                if not valid_data:
                    continue
                
                forces_clean = [f for f, d, ad in valid_data]
                delays_clean = [d for f, d, ad in valid_data]
                absolute_delays_clean = [ad for f, d, ad in valid_data]
                
                # 构建customdata，包含索引信息用于点击事件
                # 格式: [key_id, orig_force, abs_delay, rel_delay, log10_force, record_idx, replay_idx]
                customdata_list = []
                for i, (orig_force, abs_delay, rel_delay) in enumerate(zip(forces_clean, absolute_delays_clean, delays_clean)):
                    record_idx = record_indices[i] if i < len(record_indices) else None
                    replay_idx = replay_indices[i] if i < len(replay_indices) else None
                    log10_force = math.log10(orig_force) if orig_force > 0 else 0
                    customdata_list.append([
                        key_id, orig_force, abs_delay, rel_delay,
                        log10_force, record_idx, replay_idx
                    ])
                
                fig.add_trace(go.Scatter(
                    x=forces_clean,  # 使用原始力度值，Plotly的log轴会自动处理
                    y=delays_clean,
                    mode='markers',
                    name=f'按键 {key_id}',
                    marker=dict(
                        size=10,
                        color=color,
                        opacity=0.9,
                        line=dict(width=1, color='white')
                    ),
                    legendgroup=f'key_{key_id}',
                    showlegend=True,
                    customdata=customdata_list,
                    visible='legendonly',  # 默认隐藏，点击图例可显示
                    hovertemplate=f'<b>按键 {key_id}</b><br>' +
                                 '<b>力度</b>: %{x:.0f} (log₁₀: %{customdata[4]:.2f})<br>' +
                                 '<b>相对延时</b>: %{y:.2f}ms<br>' +
                                 '<b>原始延时</b>: %{customdata[2]:.2f}ms<br>' +
                                 f'<i>平均延时: {mean_delay:.2f}ms</i><extra></extra>'
                ))
    
    def generate_key_force_interaction_plot(self, analysis_result: Dict[str, Any]) -> Any:
        """
        生成按键-力度交互效应图
        
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
            
            # 为算法分配颜色
            algorithm_colors = [
                '#1f77b4',  # 蓝色
                '#ff7f0e',  # 橙色
                '#2ca02c',  # 绿色
                '#d62728',  # 红色
                '#9467bd',  # 紫色
                '#8c564b',  # 棕色
                '#e377c2',  # 粉色
                '#7f7f7f'   # 灰色
            ]
            
            if is_multi_algorithm and algorithm_results:
                # 多算法模式
                # algorithm_results的key是内部的algorithm_name（唯一标识）
                # 但我们需要提取display_name用于显示
                algorithm_internal_names = sorted(algorithm_results.keys())
                
                # 构建显示名称列表（如果display_name相同，则添加文件名后缀以区分）
                algorithm_display_names = []
                display_name_count = {}  # 统计每个display_name出现的次数
                
                for alg_name in algorithm_internal_names:
                    alg_result = algorithm_results[alg_name]
                    display_name = alg_result.get('display_name', alg_name)
                    
                    # 统计display_name出现次数
                    if display_name not in display_name_count:
                        display_name_count[display_name] = 0
                    display_name_count[display_name] += 1
                    
                    # 如果display_name重复，添加文件名后缀以区分
                    if display_name_count[display_name] > 1:
                        # 从algorithm_name中提取文件名（去掉算法名前缀）
                        # algorithm_name格式：算法名_文件名（无扩展名）
                        parts = alg_name.rsplit('_', 1)
                        if len(parts) == 2:
                            filename_part = parts[1]
                            display_name = f"{display_name} ({filename_part})"
                    
                    algorithm_display_names.append(display_name)
                
                # 收集所有按键ID，并统计每个按键在每个曲子中的出现次数
                all_key_ids = set()
                key_piece_stats = {}  # 统计每个按键在每个曲子中的出现次数: {key_id: {piece_name: count}}
                for alg_idx, algorithm_internal_name in enumerate(algorithm_internal_names):
                    alg_result = algorithm_results[algorithm_internal_name]
                    algorithm_display_name = algorithm_display_names[alg_idx]
                    interaction_plot_data = alg_result.get('interaction_plot_data', {})
                    key_data = interaction_plot_data.get('key_data', {})
                    for key_id, data in key_data.items():
                        all_key_ids.add(key_id)
                        if key_id not in key_piece_stats:
                            key_piece_stats[key_id] = {}
                        # 获取该按键在这个曲子中的出现次数
                        sample_count = data.get('sample_count', len(data.get('forces', [])))
                        key_piece_stats[key_id][algorithm_display_name] = sample_count
                
                all_key_ids = sorted(all_key_ids)
                n_keys = len(all_key_ids)
                
                # 为按键分配颜色
                if n_keys <= 20:
                    key_colors = cm.get_cmap('tab20')(np.linspace(0, 1, n_keys))
                else:
                    key_colors = cm.get_cmap('viridis')(np.linspace(0, 1, n_keys))
                key_color_hex = [mcolors.rgb2hex(c[:3]) for c in key_colors]
                
                # 创建控制图注（使用显示名称）
                self._create_algorithm_control_legends(fig, algorithm_display_names, algorithm_colors)
                self._create_key_control_legends(fig, all_key_ids, key_color_hex, key_piece_stats)
                
                # 添加数据traces
                # 传入内部名称列表和显示名称列表的映射
                self._add_data_traces_multi_algorithm(
                    fig, all_key_ids, 
                    algorithm_internal_names, algorithm_display_names,
                    algorithm_results, algorithm_colors
                )
            else:
                # 单算法模式
                interaction_plot_data = analysis_result.get('interaction_plot_data', {})
                key_data = interaction_plot_data.get('key_data', {})
                
                if not key_data:
                    return self._create_empty_plot("没有交互效应图数据")
                
                n_keys = len(key_data)
                
                # 为按键分配颜色
                if n_keys <= 20:
                    colors = cm.get_cmap('tab20')(np.linspace(0, 1, n_keys))
                else:
                    colors = cm.get_cmap('viridis')(np.linspace(0, 1, n_keys))
                
                color_hex = [mcolors.rgb2hex(c[:3]) for c in colors]
                
                # 添加数据traces
                self._add_data_traces_single_algorithm(fig, key_data, color_hex)
            
            # 生成对数刻度的刻度（显示原始力度值，但是刻度标签是对数刻度）
            # 收集所有力度数据用于生成刻度
            all_forces = []
            if is_multi_algorithm and algorithm_results:
                for alg_result in algorithm_results.values():
                    interaction_plot_data = alg_result.get('interaction_plot_data', {})
                    key_data = interaction_plot_data.get('key_data', {})
                    for data in key_data.values():
                        forces = data.get('forces', [])
                        all_forces.extend([f for f in forces if f > 0])
            else:
                interaction_plot_data = analysis_result.get('interaction_plot_data', {})
                key_data = interaction_plot_data.get('key_data', {})
                for data in key_data.values():
                    forces = data.get('forces', [])
                    all_forces.extend([f for f in forces if f > 0])

            # 生成合理的刻度点（10的倍数）
            tick_vals = []
            tick_texts = []
            tick_positions = []
            if all_forces:
                min_force = min(all_forces)
                max_force = max(all_forces)
                min_log = math.floor(math.log10(min_force))
                max_log = math.ceil(math.log10(max_force))
                tick_vals = [10**i for i in range(min_log, max_log + 1) if 10**i >= min_force and 10**i <= max_force]
                tick_texts = [f"{int(v)}" for v in tick_vals]
                tick_positions = [math.log10(v) for v in tick_vals]
            
            # 删除title，因为UI区域已有标题
            fig.update_layout(
                xaxis_title='锤速 (log₁₀)',
                yaxis_title='相对延时 (ms)',  # 使用相对延时
                xaxis=dict(
                    type='log',  # 使用对数轴
                    showgrid=True,
                    gridcolor='lightgray',
                    gridwidth=1,
                    tickmode='array' if tick_positions else 'auto',
                    tickvals=tick_positions if tick_positions else None,
                    ticktext=tick_texts if tick_texts else None
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
                    groupclick='toggleitem',  # 点击按键图例时，切换该按键的所有算法数据
                    itemclick='toggle',  # 点击图例项时切换显示/隐藏
                    # 注意：Plotly的legend文字颜色是全局的，无法单独为每个图例项设置不同的透明度
                    # 我们通过marker的opacity和size来区分选中/未选中状态
                    # 文字保持不透明，通过marker的变化来指示选中状态
                    font=dict(
                        size=11,
                        color='rgba(0, 0, 0, 1.0)'  # 图例文字颜色（黑色，不透明）
                    )
                ),
                uirevision='key-force-interaction'
            )
            return fig
            
        except Exception as e:
            logger.error(f"生成交互效应图失败: {e}")
            logger.error(traceback.format_exc())
            return self._create_empty_plot(f"生成交互效应图失败: {str(e)}")