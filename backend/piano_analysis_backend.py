#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
重构后的钢琴分析后端API
使用模块化架构，将原来的大类拆分为多个专门的模块
"""

import os
import tempfile
import pandas as pd
import numpy as np
from typing import Optional, Tuple, Dict, Any, List
from utils.logger import Logger

# SPMID相关导入
from spmid.spmid_analyzer import SPMIDAnalyzer

# 导入各个模块
from .data_manager import DataManager
from .plot_generator import PlotGenerator
from .data_filter import DataFilter
from .time_filter import TimeFilter
from .table_data_generator import TableDataGenerator
from .history_manager import HistoryManager
from .delay_analysis import DelayAnalysis
from .multi_algorithm_manager import MultiAlgorithmManager, AlgorithmDataset, AlgorithmStatus

logger = Logger.get_logger()


class PianoAnalysisBackend:

    def __init__(self, session_id=None, history_manager=None):
        """
        初始化钢琴分析后端
        
        Args:
            session_id: 会话ID，用于标识不同的分析会话
            history_manager: 全局历史管理器实例
        """
        self.session_id = session_id
        
        # 初始化各个模块
        self.data_manager = DataManager()
        self.data_filter = DataFilter()
        self.plot_generator = PlotGenerator(self.data_filter)
        self.time_filter = TimeFilter()
        self.table_generator = TableDataGenerator()
        
        # 使用全局的历史管理器实例
        self.history_manager = history_manager
        
        # 初始化分析器实例（已废弃，仅用于向后兼容）
        self.analyzer = None
        
        # 初始化延时分析器（延迟初始化，因为需要analyzer）
        self.delay_analysis = None
        
        # ==================== 多算法对比模式 ====================
        # 模式开关：始终为True（仅支持多算法模式）
        self.multi_algorithm_mode: bool = True
        
        # 多算法管理器（延迟初始化，仅在启用多算法模式时创建）
        self.multi_algorithm_manager: Optional[MultiAlgorithmManager] = None
        
        logger.info(f"✅ PianoAnalysisBackend初始化完成 (Session: {session_id})")

    
    # ==================== 数据管理相关方法 ====================
    
    def clear_data_state(self) -> None:
        """清理所有数据状态"""
        self.data_manager.clear_data_state()
        self.plot_generator.set_data()
        self.data_filter.set_data(None, None)
        self.table_generator.set_data()
        self.analyzer = None
        
        # 清理多算法管理器
        if self.multi_algorithm_manager:
            self.multi_algorithm_manager.clear_all()
        
        logger.info("✅ 所有数据状态已清理")
    
    def set_upload_data_source(self, filename: str) -> None:
        """设置上传数据源信息"""
        self.data_manager.set_upload_data_source(filename)
    
    def set_history_data_source(self, history_id: str, filename: str) -> None:
        """设置历史数据源信息"""
        self.data_manager.set_history_data_source(history_id, filename)
    
    def get_data_source_info(self) -> Dict[str, Any]:
        """获取数据源信息"""
        return self.data_manager.get_data_source_info()
    
    def process_file_upload(self, contents, filename):
        """
        处理文件上传 - 统一的文件上传入口
        
        Args:
            contents: 上传文件的内容（base64编码）
            filename: 上传文件的文件名
            
        Returns:
            tuple: (info_content, error_content, error_msg)
        """
        return self.data_manager.process_file_upload(contents, filename, self.history_manager)
    
    def process_history_selection(self, history_id):
        """
        处理历史记录选择 - 统一的历史记录入口
        
        Args:
            history_id: 历史记录ID
            
        Returns:
            tuple: (success, result_data, error_msg)
        """
        return self.history_manager.process_history_selection(history_id, self)
    
    def load_spmid_data(self, spmid_bytes: bytes) -> bool:
        """
        加载SPMID数据
        
        Args:
            spmid_bytes: SPMID文件字节数据
            
        Returns:
            bool: 是否加载成功
        """
        try:
            # 使用数据管理器加载数据
            success = self.data_manager.load_spmid_data(spmid_bytes)
            
            if success:
                # 同步数据到各个模块
                self._sync_data_to_modules()
                logger.info("✅ SPMID数据加载成功")
            else:
                logger.error("❌ SPMID数据加载失败")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ SPMID数据加载异常: {e}")
            return False
            
    def _sync_data_to_modules(self) -> None:
        """同步数据到各个模块"""
        # 获取数据
        record_data = self.data_manager.get_record_data()
        replay_data = self.data_manager.get_replay_data()
        valid_record_data = self.data_manager.get_valid_record_data()
        valid_replay_data = self.data_manager.get_valid_replay_data()
        
        # 同步到各个模块
        self.plot_generator.set_data(valid_record_data, valid_replay_data, analyzer=self.analyzer)
        self.data_filter.set_data(valid_record_data, valid_replay_data)
        self.time_filter.set_data(valid_record_data, valid_replay_data)
        
        # 如果有分析器，同步分析结果
        if self.analyzer:
            self._sync_analysis_results()
    
    def _sync_analysis_results(self) -> None:
        """同步分析结果到各个模块"""
        if not self.analyzer:
            return
        
        try:
            # 获取分析结果
            multi_hammers = getattr(self.analyzer, 'multi_hammers', [])
            drop_hammers = getattr(self.analyzer, 'drop_hammers', [])
            silent_hammers = getattr(self.analyzer, 'silent_hammers', [])
            invalid_notes_table_data = getattr(self.analyzer, 'invalid_notes_table_data', {})
            matched_pairs = getattr(self.analyzer, 'matched_pairs', [])
            
            # 合并所有错误音符
            all_error_notes = multi_hammers + drop_hammers + silent_hammers
            
            # 设置all_error_notes属性供UI层使用
            self.all_error_notes = all_error_notes
            
            # 同步到各个模块
            valid_record_data = getattr(self.analyzer, 'valid_record_data', [])
            valid_replay_data = getattr(self.analyzer, 'valid_replay_data', [])
            self.data_filter.set_data(valid_record_data, valid_replay_data)
            
            # 获取有效数据
            valid_record_data = self.data_manager.get_valid_record_data()
            valid_replay_data = self.data_manager.get_valid_replay_data()
            
            self.plot_generator.set_data(valid_record_data, valid_replay_data, matched_pairs, analyzer=self.analyzer)
            
            # 同步到TimeFilter
            self.time_filter.set_data(valid_record_data, valid_replay_data)
            
            self.table_generator.set_data(
                valid_record_data=valid_record_data,
                valid_replay_data=valid_replay_data,
                multi_hammers=multi_hammers,
                drop_hammers=drop_hammers,
                silent_hammers=silent_hammers,
                all_error_notes=all_error_notes,
                invalid_notes_table_data=invalid_notes_table_data,
                matched_pairs=matched_pairs,
                analyzer=self.analyzer
            )
            
            logger.info("✅ 分析结果同步完成")

        except Exception as e:
            logger.error(f"同步分析结果失败: {e}")
    
    # TODO
    def get_global_average_delay(self) -> float:
        """
        获取整首曲子的平均时延（基于已配对数据）
        
        Returns:
            float: 平均时延（0.1ms单位）
        """
        if not self.analyzer:
            return 0.0
        
        # 保持内部单位为0.1ms，由UI层负责显示时换算为ms
        average_delay_0_1ms = self.analyzer.get_global_average_delay()
        return average_delay_0_1ms
    
    def get_variance(self) -> float:
        """
        获取已配对按键的总体方差
        
        Returns:
            float: 总体方差（(0.1ms)²单位）
        """
        if not self.analyzer:
            return 0.0
        
        variance_0_1ms_squared = self.analyzer.get_variance()
        return variance_0_1ms_squared
    
    def get_standard_deviation(self) -> float:
        """
        获取已配对按键的总体标准差
        
        Returns:
            float: 总体标准差（0.1ms单位）
        """
        if not self.analyzer:
            return 0.0
        
        std_0_1ms = self.analyzer.get_standard_deviation()
        return std_0_1ms
    
    def get_mean_absolute_error(self) -> float:
        """
        获取已配对按键的平均绝对误差（MAE）
        
        Returns:
            float: 平均绝对误差（0.1ms单位）
        """
        if not self.analyzer:
            return 0.0
        
        mae_0_1ms = self.analyzer.get_mean_absolute_error()
        return mae_0_1ms
    
    def get_mean_squared_error(self) -> float:
        """
        获取已配对按键的均方误差（MSE）
        
        Returns:
            float: 均方误差（(0.1ms)²单位）
        """
        if not self.analyzer:
            return 0.0
        
        mse_0_1ms_squared = self.analyzer.get_mean_squared_error()
        return mse_0_1ms_squared

    def get_root_mean_squared_error(self) -> float:
        """
        获取已配对按键的均方根误差（RMSE）
        
        Returns:
            float: 均方根误差（0.1ms单位）
        """
        if not self.analyzer:
            return 0.0
        
        rmse_0_1ms = self.analyzer.get_root_mean_squared_error()
        return rmse_0_1ms
    
    def get_mean_error(self) -> float:
        """
        获取已匹配按键对的平均误差（ME）
        
        Returns:
            float: 平均误差ME（0.1ms单位）
        """
        if not self.analyzer:
            return 0.0
        
        me_0_1ms = self.analyzer.get_mean_error()
        return me_0_1ms
    
    def get_coefficient_of_variation(self) -> float:
        """
        获取已配对按键的变异系数（Coefficient of Variation, CV）
        
        Returns:
            float: 变异系数（百分比，例如 15.5 表示 15.5%）
        """
        if not self.analyzer:
            return 0.0
        
        cv = self.analyzer.get_coefficient_of_variation()
        return cv
    
    def generate_delay_time_series_plot(self) -> Any:
        """
        生成延时时间序列图（支持单算法和多算法模式）
        x轴：时间（record_keyon，转换为ms）
        y轴：延时（keyon_offset，转换为ms）
        数据来源：所有已匹配的按键对，按时间顺序排列
        """
        # 检查是否在多算法模式
        if self.multi_algorithm_mode and self.multi_algorithm_manager:
            # 多算法模式：生成多算法对比时间序列图
            active_algorithms = self.multi_algorithm_manager.get_active_algorithms()
            if not active_algorithms:
                logger.warning("⚠️ 多算法模式下没有激活的算法，返回空图表")
                return self.plot_generator._create_empty_plot("没有激活的算法")
            
            # 使用多算法图表生成器
            from backend.multi_algorithm_plot_generator import MultiAlgorithmPlotGenerator
            multi_plot_generator = MultiAlgorithmPlotGenerator(self.data_filter)
            return multi_plot_generator.generate_multi_algorithm_delay_time_series_plot(
                active_algorithms
            )
        
        # 单算法模式
        try:
            if not self.analyzer or not self.analyzer.note_matcher:
                return self.plot_generator._create_empty_plot("没有分析器")
            
            offset_data = self.analyzer.get_offset_alignment_data()
            if not offset_data:
                return self.plot_generator._create_empty_plot("无匹配数据")
            
            import plotly.graph_objects as go
            fig = go.Figure()
            
            # 提取时间和延时数据
            data_points = []  # 存储所有数据点，用于排序
            
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
                return self.plot_generator._create_empty_plot("无有效时间序列数据")
            
            # 按时间排序，确保按时间顺序显示
            data_points.sort(key=lambda x: x['time'])
            
            # 计算平均延时（用于计算相对延时）
            me_0_1ms = self.get_mean_error()  # 平均延时（0.1ms单位，带符号）
            mean_delay = me_0_1ms / 10.0  # 平均延时（ms，带符号）
            
            # 计算相对延时：每个点的延时减去平均延时
            # 标准公式：相对延时 = 延时 - 平均延时（对所有点统一适用）
            relative_delays_ms = []
            for point in data_points:
                delay_ms = point['delay']
                relative_delay = delay_ms - mean_delay
                relative_delays_ms.append(relative_delay)
            
            # 提取排序后的数据
            times_ms = [point['time'] for point in data_points]
            delays_ms = [point['delay'] for point in data_points]  # 保留原始延时用于hover显示
            # customdata 包含 [key_id, record_index, replay_index, 原始延时, 平均延时]，用于点击时查找匹配对和显示原始值
            customdata_list = [[point['key_id'], point['record_index'], point['replay_index'], point['delay'], mean_delay] 
                              for point in data_points]
            
            # 添加散点图（使用相对延时）
            fig.add_trace(go.Scatter(
                x=times_ms,
                y=relative_delays_ms,
                mode='markers+lines',  # 同时显示点和线，便于观察趋势
                name=f'相对延时时间序列 (平均延时: {mean_delay:.2f}ms)',
                marker=dict(
                    size=6,
                    color='#2196F3',
                    line=dict(width=0.5, color='#1976D2')
                ),
                line=dict(color='#2196F3', width=1),
                hovertemplate='<b>时间</b>: %{x:.2f}ms<br>' +
                             '<b>相对延时</b>: %{y:.2f}ms<br>' +
                             '<b>原始延时</b>: %{customdata[3]:.2f}ms<br>' +
                             '<b>平均延时</b>: %{customdata[4]:.2f}ms<br>' +
                             '<b>按键ID</b>: %{customdata[0]}<br>' +
                             '<extra></extra>',
                customdata=customdata_list
            ))
            
            # 计算统计量，用于添加参考线
            # 使用与数据概览界面相同的方法，确保一致性
            if delays_ms:
                std_0_1ms = self.get_standard_deviation()  # 标准差（0.1ms单位）
                
                # 转换为ms单位
                std_delay = std_0_1ms / 10.0  # 标准差（ms）
                
                # 添加零线参考线（相对延时的均值应该为0）
                fig.add_trace(go.Scatter(
                    x=[times_ms[0], times_ms[-1]] if times_ms else [0, 1],
                    y=[0, 0],
                    mode='lines',
                    name='平均延时（零线）',
                    line=dict(dash='dash', color='red', width=2),
                    hovertemplate=f'<b>平均延时（零线）</b>: 0.00ms<extra></extra>',
                    showlegend=False
                ))
                
                # 添加±3σ参考线（相对延时的±3σ，以0为中心）
                if std_delay > 0:
                    fig.add_trace(go.Scatter(
                        x=[times_ms[0], times_ms[-1]] if times_ms else [0, 1],
                        y=[3 * std_delay, 3 * std_delay],
                        mode='lines',
                        name='+3σ',
                        line=dict(dash='dot', color='orange', width=1.5),
                        hovertemplate=f'<b>+3σ</b>: {3 * std_delay:.2f}ms<extra></extra>',
                        showlegend=False
                    ))
                    fig.add_trace(go.Scatter(
                        x=[times_ms[0], times_ms[-1]] if times_ms else [0, 1],
                        y=[-3 * std_delay, -3 * std_delay],
                        mode='lines',
                        name='-3σ',
                        line=dict(dash='dot', color='orange', width=1.5),
                        hovertemplate=f'<b>-3σ</b>: {-3 * std_delay:.2f}ms<extra></extra>',
                        showlegend=False
                    ))
            
            fig.update_layout(
                # 删除title，因为UI区域已有标题
                xaxis_title='时间 (ms)',
                yaxis_title='相对延时 (ms)',
                plot_bgcolor='white',
                paper_bgcolor='white',
                font=dict(size=12),
                height=500,
                hovermode='closest',
                legend=dict(
                    orientation='h',
                    yanchor='bottom',
                    y=1.02,
                    xanchor='right',
                    x=1
                ),
                margin=dict(t=80, b=60, l=60, r=60)
            )
            
            return fig
        except Exception as e:
            logger.error(f"生成延时时间序列图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self.plot_generator._create_empty_plot(f"生成延时时间序列图失败: {str(e)}")
    
    def generate_delay_histogram_plot(self) -> Any:
        """
        生成延时分布直方图，并叠加正态拟合曲线（基于已匹配按键对的带符号keyon_offset）。
        x轴：延时 (ms)，y轴：概率密度（支持单算法和多算法模式）
        """
        # 检查是否在多算法模式
        if self.multi_algorithm_mode and self.multi_algorithm_manager:
            # 多算法模式：生成多算法对比直方图
            active_algorithms = self.multi_algorithm_manager.get_active_algorithms()
            if not active_algorithms:
                logger.warning("⚠️ 多算法模式下没有激活的算法，返回空图表")
                return self.plot_generator._create_empty_plot("没有激活的算法")
            
            # 使用多算法图表生成器
            from backend.multi_algorithm_plot_generator import MultiAlgorithmPlotGenerator
            multi_plot_generator = MultiAlgorithmPlotGenerator(self.data_filter)
            return multi_plot_generator.generate_multi_algorithm_delay_histogram_plot(
                active_algorithms
            )
        
        # 向后兼容：使用原有逻辑（已废弃）
        try:
            if not self.analyzer or not self.analyzer.note_matcher:
                return self.plot_generator._create_empty_plot("没有分析器")

            offset_data = self.analyzer.get_offset_alignment_data()
            if not offset_data:
                return self.plot_generator._create_empty_plot("无匹配数据")

            # 注意：这里使用带符号的keyon_offset，而非绝对值
            # keyon_offset = replay_keyon - record_keyon
            # 正值表示延迟，负值表示提前，零值表示无延时
            delays_ms = [item.get('keyon_offset', 0.0) / 10.0 for item in offset_data]
            if not delays_ms:
                return self.plot_generator._create_empty_plot("无有效延时数据")

            import plotly.graph_objects as go
            import math
            fig = go.Figure()

            # 添加直方图
            fig.add_trace(go.Histogram(
                x=delays_ms,
                histnorm='probability density',
                name='延时分布',
                marker_color='#2196F3',  # 使用更饱和的蓝色
                opacity=0.9,  # 增加不透明度，使颜色更明显
                marker_line_color='#1976D2',  # 添加边框颜色，增强对比度
                marker_line_width=1
            ))

            # ========== 步骤1：计算统计量 ==========
            # 计算样本均值和样本标准差（使用n-1作为分母，无偏估计）
            n = len(delays_ms)
            mean_val = sum(delays_ms) / n  # 样本均值：μ = (1/n) * Σx_i
            if n > 1:
                # 样本方差：s² = (1/(n-1)) * Σ(x_i - μ)²
                var = sum((x - mean_val) ** 2 for x in delays_ms) / (n - 1)
                std_val = var ** 0.5  # 样本标准差：s = √s²
            else:
                std_val = 0.0  # 只有一个数据点，无法计算标准差

            # ========== 步骤2：生成正态拟合曲线 ==========
            if std_val > 0:  # 只有当标准差大于0时才绘制曲线（需要离散性）
                # ----- 2.1 确定曲线绘制范围 -----
                # 获取实际数据的最小值和最大值
                min_x = min(delays_ms)  # 数据最小值（可能为负，表示提前）
                max_x = max(delays_ms)  # 数据最大值（可能为正，表示延迟）
                
                # 计算3σ范围（正态分布中约99.7%的数据落在[μ-3σ, μ+3σ]范围内）
                # max(1e-6, ...) 防止标准差极小导致范围过小或除零错误
                span = max(1e-6, 3 * std_val)  # 3σ范围的一半宽度
                
                # 确定曲线起点和终点：取数据范围与3σ范围的并集
                # 这样既覆盖实际数据，又展示理论分布特征
                x_start = min(mean_val - span, min_x)  # 起点：理论下界与实际最小值的较小者
                x_end = max(mean_val + span, max_x)    # 终点：理论上界与实际最大值的较大者
                
                # ----- 2.2 生成均匀分布的x坐标点 -----
                # 在[x_start, x_end]范围内均匀生成200个点，用于绘制平滑曲线
                num_pts = 200  # 固定200个点，足够平滑且计算高效
                step = (x_end - x_start) / (num_pts - 1) if num_pts > 1 else 1.0  # 点之间的间距
                xs = [x_start + i * step for i in range(num_pts)]  # 生成均匀分布的x坐标序列
                
                # ----- 2.3 计算每个x点的概率密度值（正态分布PDF） -----
                # 正态分布概率密度函数：f(x) = (1/(σ√(2π))) * exp(-0.5 * ((x-μ)/σ)²)
                # 其中：
                #   - 1/(σ√(2π))：归一化常数，确保曲线下面积为1
                #   - exp(-0.5 * ((x-μ)/σ)²)：指数项，在均值处最大，远离均值时快速衰减
                #   - (x-μ)/σ：标准化偏差（z-score），表示距离均值有多少个标准差
                ys = [(1.0 / (std_val * (2 * math.pi) ** 0.5)) * 
                      math.exp(-0.5 * ((x - mean_val) / std_val) ** 2) 
                      for x in xs]
                
                # ----- 2.4 绘制正态拟合曲线 -----
                # 使用Scatter图用线段连接所有(x, y)点，形成连续平滑的曲线
                fig.add_trace(go.Scatter(
                    x=xs,  # 200个x坐标（延时值，单位：ms）
                    y=ys,  # 200个对应的概率密度值
                    mode='lines',  # 用线段连接点，形成连续曲线
                    name=f"正态拟合 (μ={mean_val:.2f}ms, σ={std_val:.2f}ms)",  # 图例显示均值和标准差
                    line=dict(color='#e53935', width=2)  # 红色曲线，线宽2像素
                ))

            fig.update_layout(
                # 删除title，因为UI区域已有标题
                xaxis_title='延时 (ms)',
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
                    x=0.0,  # 从最左边开始
                    bgcolor='rgba(255, 255, 255, 0.9)',
                    bordercolor='gray',
                    borderwidth=1
                ),
                margin=dict(t=100, b=60, l=60, r=60)  # 增加顶部边距，给图注和标题更多空间
            )

            return fig
        except Exception as e:
            logger.error(f"生成延时直方图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self.plot_generator._create_empty_plot(f"生成延时直方图失败: {str(e)}")
    
    def get_delay_range_data_points(self, delay_min_ms: float, delay_max_ms: float) -> List[Dict[str, Any]]:
        """
        获取指定延时范围内的数据点详情（支持单算法和多算法模式）
        
        Args:
            delay_min_ms: 最小延时值（ms）
            delay_max_ms: 最大延时值（ms）
            
        Returns:
            List[Dict[str, Any]]: 该延时范围内的数据点列表，每个数据点包含完整信息
        """
        try:
            # 检查是否在多算法模式
            if self.multi_algorithm_mode and self.multi_algorithm_manager:
                # 多算法模式：合并所有激活算法的数据
                active_algorithms = self.multi_algorithm_manager.get_active_algorithms()
                if not active_algorithms:
                    return []
                
                filtered_data = []
                for algorithm in active_algorithms:
                    if not algorithm.analyzer or not algorithm.analyzer.note_matcher:
                        continue
                    
                    # 从算法获取原始偏移数据
                    offset_data = algorithm.analyzer.get_offset_alignment_data()
                    if not offset_data:
                        continue
                    
                    algorithm_name = algorithm.metadata.algorithm_name
                    
                    # 筛选出指定延时范围内的数据点
                    for item in offset_data:
                        delay_ms = item.get('keyon_offset', 0.0) / 10.0
                        if delay_min_ms <= delay_ms <= delay_max_ms:
                            # 添加延时值（ms）和算法名称到数据中
                            item_copy = item.copy()
                            item_copy['delay_ms'] = delay_ms
                            item_copy['algorithm_name'] = algorithm_name
                            filtered_data.append(item_copy)
                
                return filtered_data
            
            # 单算法模式
            if not self.analyzer or not self.analyzer.note_matcher:
                return []
            
            offset_data = self.analyzer.get_offset_alignment_data()
            if not offset_data:
                return []
            
            # 筛选出指定延时范围内的数据点
            # keyon_offset 单位是 0.1ms，需要转换为 ms 进行比较
            filtered_data = []
            for item in offset_data:
                delay_ms = item.get('keyon_offset', 0.0) / 10.0
                if delay_min_ms <= delay_ms <= delay_max_ms:
                    # 添加延时值（ms）到数据中，方便显示
                    item_copy = item.copy()
                    item_copy['delay_ms'] = delay_ms
                    filtered_data.append(item_copy)
            
            return filtered_data
        except Exception as e:
            logger.error(f"获取延时范围数据点失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    
    def get_offset_alignment_data(self) -> List[Dict[str, Any]]:
        """获取偏移对齐数据 - 转换为DataTable格式，包含无效音符分析（支持单算法和多算法模式）"""
        
        # 检查是否在多算法模式
        if self.multi_algorithm_mode and self.multi_algorithm_manager:
            # 多算法模式：合并所有算法的数据，添加"算法名称"列
            active_algorithms = self.multi_algorithm_manager.get_active_algorithms()
            if not active_algorithms:
                return [{
                    'algorithm_name': "无数据",
                    'key_id': "无数据",
                    'count': 0,
                    'median': "N/A",
                    'mean': "N/A",
                    'std': "N/A",
                    'variance': "N/A",
                    'min': "N/A",
                    'max': "N/A",
                    'range': "N/A",
                    'status': 'no_data'
                }]
            
            # 使用字典按按键ID分组，每个按键ID包含多个算法的数据
            from collections import defaultdict
            import numpy as np
            
            # 第一层：按键ID -> 第二层：算法名称 -> 数据
            key_algorithm_data = defaultdict(dict)
            
            for algorithm in active_algorithms:
                algorithm_name = algorithm.metadata.algorithm_name
                
                if not algorithm.analyzer:
                    continue
                
                try:
                    # 从analyzer获取偏移数据
                    offset_data = algorithm.analyzer.get_offset_alignment_data()
                    invalid_offset_data = algorithm.analyzer.get_invalid_notes_offset_analysis()
                    
                    # 按按键ID分组有效匹配的偏移数据（只使用keyon_offset）
                    key_groups = defaultdict(list)
                    for item in offset_data:
                        key_id = item.get('key_id', 'N/A')
                        keyon_offset_abs = abs(item.get('keyon_offset', 0))  # 只使用keyon_offset
                        key_groups[key_id].append(keyon_offset_abs)
                    
                    # 按按键ID分组无效音符数据
                    invalid_key_groups = defaultdict(list)
                    for item in invalid_offset_data:
                        key_id = item.get('key_id', 'N/A')
                        invalid_key_groups[key_id].append(item)
                    
                    # 处理有效匹配的按键
                    for key_id, offsets in key_groups.items():
                        if offsets:
                            median_val = np.median(offsets)
                            mean_val = np.mean(offsets)
                            std_val = np.std(offsets)
                            variance_val = np.var(offsets)  # 方差（单位：(0.1ms)²）
                            min_val = np.min(offsets)
                            max_val = np.max(offsets)
                            range_val = max_val - min_val
                            
                            key_algorithm_data[key_id][algorithm_name] = {
                                'algorithm_name': algorithm_name,
                                'key_id': key_id,
                                'count': len(offsets),
                                'median': f"{median_val/10:.2f}ms",
                                'mean': f"{mean_val/10:.2f}ms",
                                'std': f"{std_val/10:.2f}ms",
                                'variance': f"{variance_val/100:.2f}ms²",  # 转换为ms²
                                'min': f"{min_val/10:.2f}ms",
                                'max': f"{max_val/10:.2f}ms",
                                'range': f"{range_val/10:.2f}ms",
                                'status': 'matched'
                            }
                    
                    # 处理无效音符的按键
                    for key_id, invalid_items in invalid_key_groups.items():
                        if key_id not in key_groups:  # 只处理没有有效匹配的按键
                            record_count = sum(1 for item in invalid_items if item.get('data_type') == 'record')
                            replay_count = sum(1 for item in invalid_items if item.get('data_type') == 'replay')
                            
                            if key_id not in key_algorithm_data:
                                key_algorithm_data[key_id] = {}
                            
                            key_algorithm_data[key_id][algorithm_name] = {
                                'algorithm_name': algorithm_name,
                                'key_id': key_id,
                                'count': len(invalid_items),
                                'median': "N/A",
                                'mean': "N/A",
                                'std': "N/A",
                                'variance': "N/A",
                                'min': "N/A",
                                'max': "N/A",
                                'range': "N/A",
                                'status': f'invalid (R:{record_count}, P:{replay_count})'
                            }
                except Exception as e:
                    logger.warning(f"⚠️ 获取算法 '{algorithm_name}' 的偏移对齐数据失败: {e}")
                    continue
            
            # 将数据按按键ID排序，然后按算法名称排序（确保同一按键ID的数据在一起）
            table_data = []
            
            # 对按键ID进行排序（处理数字和字符串混合的情况）
            def sort_key_id(key_id):
                """按键ID排序函数：数字按键按数值排序，字符串按键按字符串排序"""
                if isinstance(key_id, (int, float)):
                    return (0, key_id)  # 数字类型，优先级0
                elif isinstance(key_id, str):
                    try:
                        # 尝试转换为数字
                        num_key = int(key_id)
                        return (0, num_key)
                    except (ValueError, TypeError):
                        # 无法转换为数字，按字符串排序
                        return (1, str(key_id))
                else:
                    return (2, str(key_id))
            
            # 按按键ID排序
            sorted_key_ids = sorted(key_algorithm_data.keys(), key=sort_key_id)
            
            for key_id in sorted_key_ids:
                # 对每个按键ID下的算法按名称排序（确保显示顺序一致）
                algorithms_for_key = sorted(key_algorithm_data[key_id].keys())
                for algorithm_name in algorithms_for_key:
                    table_data.append(key_algorithm_data[key_id][algorithm_name])
            
            if not table_data:
                return [{
                    'algorithm_name': "无数据",
                    'key_id': "无数据",
                    'count': 0,
                    'median': "N/A",
                    'mean': "N/A",
                    'std': "N/A",
                    'variance': "N/A",
                    'min': "N/A",
                    'max': "N/A",
                    'range': "N/A",
                    'status': 'no_data'
                }]
            
            return table_data
        
        # 向后兼容：使用原有逻辑（已废弃）
        try:
            # 从分析器获取偏移数据
            offset_data = self.analyzer.get_offset_alignment_data()
            invalid_offset_data = self.analyzer.get_invalid_notes_offset_analysis()
            
            # 按按键ID分组并计算统计信息
            from collections import defaultdict
            import numpy as np
            
            # 按按键ID分组有效匹配的偏移数据（只使用keyon_offset）
            key_groups = defaultdict(list)
            for item in offset_data:
                key_id = item.get('key_id', 'N/A')
                keyon_offset_abs = abs(item.get('keyon_offset', 0))  # 只使用keyon_offset
                key_groups[key_id].append(keyon_offset_abs)
            
            # 按按键ID分组无效音符数据
            invalid_key_groups = defaultdict(list)
            for item in invalid_offset_data:
                key_id = item.get('key_id', 'N/A')
                invalid_key_groups[key_id].append(item)
            
            # 转换为DataTable格式
            table_data = []
            
            # 处理有效匹配的按键
            for key_id, offsets in key_groups.items():
                if offsets:
                    median_val = np.median(offsets)
                    mean_val = np.mean(offsets)
                    std_val = np.std(offsets)
                    variance_val = np.var(offsets)  # 方差（单位：(0.1ms)²）
                    min_val = np.min(offsets)
                    max_val = np.max(offsets)
                    range_val = max_val - min_val
                    
                    table_data.append({
                        'key_id': key_id,
                        'count': len(offsets),
                        'median': f"{median_val/10:.2f}ms",
                        'mean': f"{mean_val/10:.2f}ms",
                        'std': f"{std_val/10:.2f}ms",
                        'variance': f"{variance_val/100:.2f}ms²",  # 转换为ms²
                        'min': f"{min_val/10:.2f}ms",
                        'max': f"{max_val/10:.2f}ms",
                        'range': f"{range_val/10:.2f}ms",
                        'status': 'matched'
                    })
            
            # 处理无效音符的按键
            for key_id, invalid_items in invalid_key_groups.items():
                if key_id not in key_groups:  # 只处理没有有效匹配的按键
                    record_count = sum(1 for item in invalid_items if item.get('data_type') == 'record')
                    replay_count = sum(1 for item in invalid_items if item.get('data_type') == 'replay')
                    
                    table_data.append({
                        'key_id': key_id,
                        'count': len(invalid_items),
                        'median': "N/A",
                        'mean': "N/A",
                        'std': "N/A",
                        'variance': "N/A",
                        'min': "N/A",
                        'max': "N/A",
                        'range': "N/A",
                        'status': f'invalid (R:{record_count}, P:{replay_count})'
                    })
            
            # 不再添加汇总行
            
            if not table_data:
                return [{
                    'key_id': "无数据",
                    'count': 0,
                    'median': "N/A",
                    'mean': "N/A",
                    'std': "N/A",
                    'variance': "N/A",
                    'min': "N/A",
                    'max': "N/A",
                    'range': "N/A",
                    'status': 'no_data'
                }]
            
            return table_data
            
        except Exception as e:
            logger.error(f"获取偏移对齐数据失败: {e}")
            return [{
                'key_id': "错误",
                'count': 0,
                'median': "N/A",
                'mean': "N/A",
                'std': "N/A",
                'variance': "N/A",
                'min': "N/A",
                'max': "N/A",
                'range': "N/A",
                'status': 'error'
            }]
    
    
    def generate_offset_alignment_plot(self) -> Any:
        """生成偏移对齐分析柱状图 - 键位为横坐标，中位数、均值、标准差为纵坐标，分4个子图显示（支持单算法和多算法模式）"""
        
        # 检查是否在多算法模式
        if self.multi_algorithm_mode and self.multi_algorithm_manager:
            # 多算法模式：生成多算法对比柱状图
            active_algorithms = self.multi_algorithm_manager.get_active_algorithms()
            if not active_algorithms:
                logger.warning("⚠️ 多算法模式下没有激活的算法，返回空图表")
                return self.plot_generator._create_empty_plot("没有激活的算法")
            
            # 使用多算法图表生成器
            from backend.multi_algorithm_plot_generator import MultiAlgorithmPlotGenerator
            multi_plot_generator = MultiAlgorithmPlotGenerator(self.data_filter)
            return multi_plot_generator.generate_multi_algorithm_offset_alignment_plot(
                active_algorithms
            )
        
        # 向后兼容：使用原有逻辑（已废弃）
        try:
            # 获取偏移对齐分析数据
            alignment_data = self.get_offset_alignment_data()
            
            if not alignment_data:
                logger.warning("⚠️ 没有偏移对齐分析数据，无法生成柱状图")
                return self.plot_generator._create_empty_plot("没有偏移对齐分析数据")
            
            # 直接从表格数据提取（包括方差）
            key_ids = []
            median_values = []
            mean_values = []
            std_values = []
            variance_values = []
            status_list = []
            
            import numpy as np
            
            for item in alignment_data:
                key_id = item['key_id']
                status = item['status']
                
                try:
                    # 跳过无效的key_id
                    if key_id == '无数据' or key_id == '错误' or not str(key_id).isdigit():
                        continue
                    
                    key_id_int = int(key_id)
                    key_ids.append(key_id_int)
                    
                    # 从字符串中提取数值，去除单位
                    median_str = item['median'].replace('ms', '').replace('N/A', '0') if isinstance(item['median'], str) else str(item['median'])
                    mean_str = item['mean'].replace('ms', '').replace('N/A', '0') if isinstance(item['mean'], str) else str(item['mean'])
                    std_str = item['std'].replace('ms', '').replace('N/A', '0') if isinstance(item['std'], str) else str(item['std'])
                    variance_str = item.get('variance', '0').replace('ms²', '').replace('N/A', '0') if isinstance(item.get('variance', '0'), str) else str(item.get('variance', '0'))
                    
                    median_values.append(float(median_str))
                    mean_values.append(float(mean_str))
                    std_values.append(float(std_str))
                    variance_values.append(float(variance_str))
                    status_list.append(status)
                except (ValueError, TypeError) as e:
                    logger.warning(f"⚠️ 跳过无效数据: {e}")
                    continue
            
            if not key_ids:
                logger.warning("⚠️ 没有有效的偏移对齐数据，无法生成柱状图")
                return self.plot_generator._create_empty_plot("没有有效的偏移对齐数据")
            
            # 确保key_ids的最小值至少为1（按键ID不可能为负数）
            min_key_id = max(1, min(key_ids)) if key_ids else 1
            max_key_id = max(key_ids) if key_ids else 90
            
            # 创建Plotly图表 - 4个子图分别显示柱状图（中位数、均值、标准差、方差）
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
            
            fig = make_subplots(
                rows=4, cols=1,
                subplot_titles=('中位数偏移', '均值偏移', '标准差', '方差'),
                vertical_spacing=0.05,
                row_heights=[0.25, 0.25, 0.25, 0.25]
            )
            
            # 根据状态设置不同的颜色
            matched_indices = [i for i, status in enumerate(status_list) if status == 'matched']
            unmatched_indices = [i for i, status in enumerate(status_list) if status == 'unmatched']
            
            # 添加匹配数据的中位数柱状图
            if matched_indices:
                matched_key_ids = [key_ids[i] for i in matched_indices]
                matched_median = [median_values[i] for i in matched_indices]
                matched_mean = [mean_values[i] for i in matched_indices]
                matched_std = [std_values[i] for i in matched_indices]
                matched_variance = [variance_values[i] for i in matched_indices]
                
                fig.add_trace(
                    go.Bar(
                        x=matched_key_ids,
                        y=matched_median,
                        name='匹配-中位数',
                        marker_color='#1f77b4',
                        opacity=0.8,
                        width=1.0,
                        text=[f'{val:.2f}' for val in matched_median],
                        textposition='outside',
                        textfont=dict(size=10),
                        hovertemplate='键位: %{x}<br>中位数: %{y:.2f}ms<br>状态: 匹配<extra></extra>',
                        showlegend=False
                    ),
                    row=1, col=1
                )
                
                fig.add_trace(
                    go.Bar(
                        x=matched_key_ids,
                        y=matched_mean,
                        name='匹配-均值',
                        marker_color='#ff7f0e',
                        opacity=0.8,
                        width=1.0,
                        text=[f'{val:.2f}' for val in matched_mean],
                        textposition='outside',
                        textfont=dict(size=10),
                        hovertemplate='键位: %{x}<br>均值: %{y:.2f}ms<br>状态: 匹配<extra></extra>',
                        showlegend=False
                    ),
                    row=2, col=1
                )
                
                # 计算总体均值：与数据概览页面的"平均时延"一致
                # 使用get_mean_absolute_error()方法，该方法使用绝对值的keyon_offset计算平均延时
                overall_mean_0_1ms = self.analyzer.get_mean_absolute_error()  # 单位：0.1ms
                overall_mean = overall_mean_0_1ms / 10.0  # 转换为ms
                
                # 添加总体均值参考线（红色虚线）- 与数据概览页面的"平均时延"一致
                fig.add_hline(
                    y=overall_mean,
                    line_dash="dash",
                    line_color="red",
                    line_width=2,
                    annotation_text=f"平均时延: {overall_mean:.2f}ms",
                    annotation_position="top right",
                    row=2, col=1
                )
                
                fig.add_trace(
                    go.Bar(
                        x=matched_key_ids,
                        y=matched_std,
                        name='匹配-标准差',
                        marker_color='#2ca02c',
                        opacity=0.8,
                        width=1.0,
                        text=[f'{val:.2f}' for val in matched_std],
                        textposition='outside',
                        textfont=dict(size=10),
                        hovertemplate='键位: %{x}<br>标准差: %{y:.2f}ms<br>状态: 匹配<extra></extra>',
                        showlegend=False
                    ),
                    row=3, col=1
                )
                
                # 计算总体标准差：与延时误差统计指标保持一致
                # 使用get_standard_deviation()方法，该方法使用绝对值的keyon_offset计算总体标准差
                # 公式：σ = √(σ²) = √((1/n) * Σ(|x_i| - μ_abs)²)
                overall_std_0_1ms = self.analyzer.get_standard_deviation()  # 单位：0.1ms
                overall_std = overall_std_0_1ms / 10.0  # 转换为ms
                
                # 添加总体标准差参考线（红色虚线）- 与柱状图计算方式一致（都使用绝对值）
                fig.add_hline(
                    y=overall_std,
                    line_dash="dash",
                    line_color="red",
                    line_width=2,
                    annotation_text=f"总体标准差: {overall_std:.2f}ms",
                    annotation_position="top right",
                    row=3, col=1
                )
                
                # 添加方差柱状图
                fig.add_trace(
                    go.Bar(
                        x=matched_key_ids,
                        y=matched_variance,
                        name='匹配-方差',
                        marker_color='#9467bd',
                        opacity=0.8,
                        width=1.0,
                        text=[f'{val:.2f}' for val in matched_variance],
                        textposition='outside',
                        textfont=dict(size=10),
                        hovertemplate='键位: %{x}<br>方差: %{y:.2f}ms²<br>状态: 匹配<extra></extra>',
                        showlegend=False
                    ),
                    row=4, col=1
                )
                
                # 计算总体方差：与延时误差统计指标保持一致
                # 使用get_variance()方法，该方法使用带符号的keyon_offset计算总体方差
                # 公式：σ² = (1/n) * Σ(x_i - μ)²，其中 x_i 是带符号的keyon_offset
                overall_variance_0_1ms_squared = self.analyzer.get_variance()  # 单位：(0.1ms)²
                overall_variance = overall_variance_0_1ms_squared / 100.0  # 转换为ms²
                
                # 添加总体方差参考线（红色虚线）
                fig.add_hline(
                    y=overall_variance,
                    line_dash="dash",
                    line_color="red",
                    line_width=2,
                    annotation_text=f"总体方差: {overall_variance:.2f}ms²",
                    annotation_position="top right",
                    row=4, col=1
                )
            
            # 添加未匹配数据的中位数柱状图
            if unmatched_indices:
                unmatched_key_ids = [key_ids[i] for i in unmatched_indices]
                unmatched_median = [median_values[i] for i in unmatched_indices]
                unmatched_mean = [mean_values[i] for i in unmatched_indices]
                unmatched_std = [std_values[i] for i in unmatched_indices]
                unmatched_variance = [variance_values[i] for i in unmatched_indices]
                
                fig.add_trace(
                    go.Bar(
                        x=unmatched_key_ids,
                        y=unmatched_median,
                        name='未匹配-中位数',
                        marker_color='#d62728',
                        opacity=0.8,
                        width=1.0,
                        text=[f'{val:.2f}' for val in unmatched_median],
                        textposition='outside',
                        textfont=dict(size=10),
                        hovertemplate='键位: %{x}<br>中位数: %{y:.2f}ms<br>状态: 未匹配<extra></extra>',
                        showlegend=False
                    ),
                    row=1, col=1
                )
                
                fig.add_trace(
                    go.Bar(
                        x=unmatched_key_ids,
                        y=unmatched_mean,
                        name='未匹配-均值',
                        marker_color='#9467bd',
                        opacity=0.8,
                        width=1.0,
                        text=[f'{val:.2f}' for val in unmatched_mean],
                        textposition='outside',
                        textfont=dict(size=10),
                        hovertemplate='键位: %{x}<br>均值: %{y:.2f}ms<br>状态: 未匹配<extra></extra>',
                        showlegend=False
                    ),
                    row=2, col=1
                )
                
                fig.add_trace(
                    go.Bar(
                        x=unmatched_key_ids,
                        y=unmatched_std,
                        name='未匹配-标准差',
                        marker_color='#8c564b',
                        opacity=0.8,
                        width=1.0,
                        text=[f'{val:.2f}' for val in unmatched_std],
                        textposition='outside',
                        textfont=dict(size=10),
                        hovertemplate='键位: %{x}<br>标准差: %{y:.2f}ms<br>状态: 未匹配<extra></extra>',
                        showlegend=False
                    ),
                    row=3, col=1
                )
                
                # 添加未匹配数据的方差柱状图
                fig.add_trace(
                    go.Bar(
                        x=unmatched_key_ids,
                        y=unmatched_variance,
                        name='未匹配-方差',
                        marker_color='#bcbd22',
                        opacity=0.8,
                        width=1.0,
                        text=[f'{val:.2f}' for val in unmatched_variance],
                        textposition='outside',
                        textfont=dict(size=10),
                        hovertemplate='键位: %{x}<br>方差: %{y:.2f}ms²<br>状态: 未匹配<extra></extra>',
                        showlegend=False
                    ),
                    row=4, col=1
                )
            
            # 更新布局 - 增大图表区域
            fig.update_layout(
                # 删除title，因为UI区域已有标题
                height=2000,  # 进一步增加高度，确保参考线可见
                showlegend=False,
                margin=dict(l=100, r=150, t=180, b=120)  # 增加顶部和右侧边距，为参考线标注留空间
            )
            
            # 更新坐标轴 - 设置x轴范围，确保不显示负数
            fig.update_xaxes(
                title_text="键位ID",
                range=[min_key_id - 1, max_key_id + 1],  # 设置x轴范围，确保不显示负数
                row=1, col=1
            )
            fig.update_xaxes(
                title_text="键位ID",
                range=[min_key_id - 1, max_key_id + 1],
                row=2, col=1
            )
            fig.update_xaxes(
                title_text="键位ID",
                range=[min_key_id - 1, max_key_id + 1],
                row=3, col=1
            )
            fig.update_xaxes(
                title_text="键位ID",
                range=[min_key_id - 1, max_key_id + 1],
                row=4, col=1
            )
            fig.update_yaxes(title_text="中位数偏移 (ms)", row=1, col=1)
            fig.update_yaxes(title_text="均值偏移 (ms)", row=2, col=1)
            fig.update_yaxes(title_text="标准差 (ms)", row=3, col=1)
            fig.update_yaxes(title_text="方差 (ms²)", row=4, col=1)
            
            logger.info(f"✅ 偏移对齐分析柱状图生成成功，包含 {len(key_ids)} 个键位（匹配: {len(matched_indices)}, 未匹配: {len(unmatched_indices)}）")
            return fig
            
        except Exception as e:
            logger.error(f"❌ 生成偏移对齐分析柱状图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self.plot_generator._create_empty_plot(f"生成柱状图失败: {str(e)}")
    
    def generate_key_delay_scatter_plot(self) -> Any:
        """
        生成按键与延时的散点图（支持单算法和多算法模式）
        x轴：按键ID（key_id）
        y轴：延时（keyon_offset，转换为ms）
        数据来源：所有已匹配的按键对
        """
        # 检查是否在多算法模式
        if self.multi_algorithm_mode and self.multi_algorithm_manager:
            # 多算法模式：生成多算法对比散点图
            active_algorithms = self.multi_algorithm_manager.get_active_algorithms()
            if not active_algorithms:
                logger.warning("⚠️ 多算法模式下没有激活的算法，返回空图表")
                return self.plot_generator._create_empty_plot("没有激活的算法")
            
            # 使用多算法图表生成器
            from backend.multi_algorithm_plot_generator import MultiAlgorithmPlotGenerator
            multi_plot_generator = MultiAlgorithmPlotGenerator(self.data_filter)
            return multi_plot_generator.generate_multi_algorithm_key_delay_scatter_plot(
                active_algorithms
            )
        
        # 向后兼容：使用原有逻辑（已废弃）
        try:
            # 从分析器获取原始偏移对齐数据（包含每个匹配对的详细信息）
            if not self.analyzer or not self.analyzer.note_matcher:
                logger.warning("⚠️ 分析器或匹配器不存在，无法生成散点图")
                return self.plot_generator._create_empty_plot("分析器或匹配器不存在")
            
            offset_data = self.analyzer.note_matcher.get_offset_alignment_data()
            
            if not offset_data:
                logger.warning("⚠️ 没有匹配数据，无法生成散点图")
                return self.plot_generator._create_empty_plot("没有匹配数据")
            
            # 提取按键ID和延时数据（带符号值）
            key_ids = []
            delays_ms = []  # 延时（ms单位，带符号）
            customdata_list = []  # 用于存储customdata，包含record_index和replay_index
            
            for item in offset_data:
                key_id = item.get('key_id')
                keyon_offset = item.get('keyon_offset', 0)  # 单位：0.1ms
                record_index = item.get('record_index')
                replay_index = item.get('replay_index')
                
                # 跳过无效数据
                if key_id is None or key_id == 'N/A':
                    continue
                
                try:
                    key_id_int = int(key_id)
                    # 将延时从0.1ms转换为ms（保留符号）
                    delay_ms = keyon_offset / 10.0
                    
                    key_ids.append(key_id_int)
                    delays_ms.append(delay_ms)
                    # 添加customdata：包含record_index和replay_index，用于点击时查找匹配对
                    customdata_list.append([record_index, replay_index, key_id_int, delay_ms])
                except (ValueError, TypeError) as e:
                    logger.warning(f"⚠️ 跳过无效数据点: key_id={key_id}, error={e}")
                    continue
            
            if not key_ids:
                logger.warning("⚠️ 没有有效的散点图数据")
                return self.plot_generator._create_empty_plot("没有有效的散点图数据")
            
            # 直接使用数据概览页面的数据，不重新计算
            # 使用backend的方法，确保与数据概览页面完全一致
            me_0_1ms = self.get_mean_error()  # 总体均值（0.1ms单位，带符号）
            std_0_1ms = self.get_standard_deviation()  # 总体标准差（0.1ms单位，带符号）
            
            # 转换为ms单位
            mu = me_0_1ms / 10.0  # 总体均值（ms，带符号）
            sigma = std_0_1ms / 10.0  # 总体标准差（ms，带符号）
            
            # 计算阈值
            upper_threshold = mu + 3 * sigma  # 上阈值：μ + 3σ
            lower_threshold = mu - 3 * sigma  # 下阈值：μ - 3σ
            
            # 创建Plotly散点图
            import plotly.graph_objects as go
            
            fig = go.Figure()
            
            # 添加散点图数据（带符号的延时）
            # 为超过阈值的点使用不同颜色
            marker_colors = []
            marker_sizes = []
            for delay in delays_ms:
                if delay > upper_threshold or delay < lower_threshold:
                    # 超过阈值的点使用红色，更大尺寸
                    marker_colors.append('#d62728')  # 红色
                    marker_sizes.append(12)
                else:
                    marker_colors.append('#2e7d32')  # 绿色
                    marker_sizes.append(8)
            
            fig.add_trace(go.Scatter(
                x=key_ids,
                y=delays_ms,
                mode='markers',
                name='匹配对',
                marker=dict(
                    size=marker_sizes,
                    color=marker_colors,
                    opacity=0.6,
                    line=dict(width=1, color='#1b5e20')
                ),
                customdata=customdata_list,  # 添加customdata，包含record_index和replay_index
                hovertemplate='键位: %{x}<br>延时: %{y:.2f}ms<extra></extra>'
            ))
            
            # 注意：已删除平均延时的趋势线
            
            # 获取x轴范围，用于确定标注位置
            x_max = max(key_ids) if key_ids else 90
            x_min = min(key_ids) if key_ids else 1
            
            # 添加总体均值参考线（μ）- 使用Scatter创建，支持悬停显示
            fig.add_trace(go.Scatter(
                x=[x_min, x_max],
                y=[mu, mu],
                mode='lines',
                name='μ',
                line=dict(
                    color='blue',
                    width=1.5,
                    dash='dot'
                ),
                showlegend=True,
                hovertemplate=f"μ = {mu:.2f}ms<extra></extra>"
            ))
            
            # 添加上阈值线（μ + 3σ）- 使用Scatter创建，支持悬停显示
            fig.add_trace(go.Scatter(
                x=[x_min, x_max],
                y=[upper_threshold, upper_threshold],
                mode='lines',
                name='μ+3σ',
                line=dict(
                    color='red',
                    width=2,
                    dash='dash'
                ),
                showlegend=True,
                hovertemplate=f"μ+3σ = {upper_threshold:.2f}ms<extra></extra>"
            ))
            
            # 添加下阈值线（μ - 3σ）- 使用Scatter创建，支持悬停显示
            fig.add_trace(go.Scatter(
                x=[x_min, x_max],
                y=[lower_threshold, lower_threshold],
                mode='lines',
                name='μ-3σ',
                line=dict(
                    color='orange',
                    width=2,
                    dash='dash'
                ),
                showlegend=True,
                hovertemplate=f"μ-3σ = {lower_threshold:.2f}ms<extra></extra>"
            ))
            
            # 更新布局（删除title，因为UI区域已有标题）
            fig.update_layout(
                xaxis_title='按键ID',
                yaxis_title='延时 (ms)',
                xaxis=dict(
                    showgrid=True,
                    gridcolor='lightgray',
                    gridwidth=1,
                    dtick=10  # 每10个按键显示一个刻度
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
                    orientation='h',  # 水平排列图例
                    yanchor='bottom',
                    y=1.02,  # 图例在图表区域上方
                    xanchor='left',
                    x=0.0,  # 图例在左侧对齐
                    bgcolor='rgba(255, 255, 255, 0.9)',
                    bordercolor='gray',
                    borderwidth=1
                ),
                margin=dict(t=90, b=60, l=60, r=60)  # 增加顶部边距，为图例和标注留出空间
            )
            
            logger.info(f"✅ 按键-延时散点图生成成功，包含 {len(key_ids)} 个数据点")
            return fig
            
        except Exception as e:
            logger.error(f"❌ 生成散点图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self.plot_generator._create_empty_plot(f"生成散点图失败: {str(e)}")
    
    def generate_key_delay_zscore_scatter_plot(self) -> Any:
        """
        生成按键与延时Z-Score标准化散点图（支持单算法和多算法模式）
        x轴：按键ID（key_id）
        y轴：Z-Score标准化延时值，z = (x_i - μ) / σ
        """
        # 检查是否在多算法模式
        if self.multi_algorithm_mode and self.multi_algorithm_manager:
            # 多算法模式：生成多算法对比Z-Score散点图
            active_algorithms = self.multi_algorithm_manager.get_active_algorithms()
            if not active_algorithms:
                logger.warning("⚠️ 多算法模式下没有激活的算法，返回空图表")
                return self.plot_generator._create_empty_plot("没有激活的算法")
            
            # 使用多算法图表生成器
            from backend.multi_algorithm_plot_generator import MultiAlgorithmPlotGenerator
            multi_plot_generator = MultiAlgorithmPlotGenerator(self.data_filter)
            return multi_plot_generator.generate_multi_algorithm_key_delay_zscore_scatter_plot(
                active_algorithms
            )
        
        # 向后兼容：暂不支持，返回空图表
        logger.warning("⚠️ Z-Score标准化散点图目前仅支持多算法模式")
        return self.plot_generator._create_empty_plot("Z-Score标准化散点图目前仅支持多算法模式")
    
    def generate_hammer_velocity_delay_scatter_plot(self) -> Any:
        """
        生成锤速与延时的散点图（支持单算法和多算法模式）
        x轴：锤速（播放锤速）
        y轴：延时（keyon_offset，转换为ms）
        数据来源：所有已匹配的按键对
        """
        # 检查是否在多算法模式
        if self.multi_algorithm_mode and self.multi_algorithm_manager:
            # 多算法模式：生成多算法对比散点图
            active_algorithms = self.multi_algorithm_manager.get_active_algorithms()
            if not active_algorithms:
                logger.warning("⚠️ 多算法模式下没有激活的算法，返回空图表")
                return self.plot_generator._create_empty_plot("没有激活的算法")
            
            # 使用多算法图表生成器
            from backend.multi_algorithm_plot_generator import MultiAlgorithmPlotGenerator
            multi_plot_generator = MultiAlgorithmPlotGenerator(self.data_filter)
            return multi_plot_generator.generate_multi_algorithm_hammer_velocity_delay_scatter_plot(
                active_algorithms
            )
        
        # 向后兼容：使用原有逻辑（已废弃）
        try:
            # 从分析器获取原始偏移对齐数据和匹配对
            if not self.analyzer or not self.analyzer.note_matcher:
                logger.warning("⚠️ 分析器或匹配器不存在，无法生成散点图")
                return self.plot_generator._create_empty_plot("分析器或匹配器不存在")
            
            matched_pairs = self.analyzer.note_matcher.get_matched_pairs()
            
            if not matched_pairs:
                logger.warning("⚠️ 没有匹配数据，无法生成散点图")
                return self.plot_generator._create_empty_plot("没有匹配数据")
            
            # 获取偏移对齐数据（已包含延时信息）
            offset_data = self.analyzer.note_matcher.get_offset_alignment_data()
            
            # 提取锤速和延时数据，并计算Z-Score（与按键与延时Z-Score散点图相同）
            hammer_velocities = []  # 锤速（播放音符的第一个锤速值）
            delays_ms = []  # 延时（ms单位，用于计算Z-Score）
            scatter_customdata = []  # 存储record_idx和replay_idx，用于点击事件识别
            
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
                    continue  # 跳过没有锤速数据的音符
                
                # 从偏移数据中获取延时（keyon_offset），如果找不到则计算
                keyon_offset = None
                if (record_idx, replay_idx) in offset_map:
                    keyon_offset = offset_map[(record_idx, replay_idx)].get('keyon_offset', 0)
                else:
                    # 备用方案：直接计算（使用私有方法）
                    try:
                        record_keyon, _ = self.analyzer.note_matcher._calculate_note_times(record_note)
                        replay_keyon, _ = self.analyzer.note_matcher._calculate_note_times(replay_note)
                        keyon_offset = replay_keyon - record_keyon
                    except:
                        continue  # 如果计算失败，跳过该数据点
                
                # 将延时从0.1ms转换为ms（带符号，用于Z-Score计算）
                delay_ms = keyon_offset / 10.0
                
                hammer_velocities.append(hammer_velocity)
                delays_ms.append(delay_ms)
                # 存储record_idx和replay_idx，用于点击事件识别
                scatter_customdata.append([record_idx, replay_idx])
            
            if not hammer_velocities:
                logger.warning("⚠️ 没有有效的散点图数据")
                return self.plot_generator._create_empty_plot("没有有效的散点图数据")
            
            # 计算Z-Score（与按键与延时Z-Score散点图相同的计算方式）
            import numpy as np
            me_0_1ms = self.get_mean_error()  # 总体均值（0.1ms单位，带符号）
            std_0_1ms = self.get_standard_deviation()  # 总体标准差（0.1ms单位，带符号）
            
            mu = me_0_1ms / 10.0  # 总体均值（ms，带符号）
            sigma = std_0_1ms / 10.0  # 总体标准差（ms，带符号）
            
            # 计算Z-Score：z = (x_i - μ) / σ
            delays_array = np.array(delays_ms)
            if sigma > 0:
                z_scores = ((delays_array - mu) / sigma).tolist()
            else:
                z_scores = [0.0] * len(delays_ms)
            
            # 创建Plotly散点图
            import plotly.graph_objects as go
            
            fig = go.Figure()
            
            # 添加散点图数据（y轴使用Z-Score值）
            # customdata格式: [delay_ms, record_idx, replay_idx]
            # 第一个元素用于hover显示，后两个用于点击事件识别
            combined_customdata = [[delay_ms, record_idx, replay_idx] 
                                  for delay_ms, (record_idx, replay_idx) 
                                  in zip(delays_ms, scatter_customdata)]
            
            fig.add_trace(go.Scatter(
                x=hammer_velocities,
                y=z_scores,
                mode='markers',
                name='匹配对',
                marker=dict(
                    size=8,
                    color='#d32f2f',
                    opacity=0.6,
                    line=dict(width=1, color='#b71c1c')
                ),
                hovertemplate='锤速: %{x}<br>延时: %{customdata[0]:.2f}ms<br>Z-Score: %{y:.2f}<extra></extra>',
                customdata=combined_customdata
            ))
            
            # 添加Z-Score参考线（与按键与延时Z-Score散点图相同）
            if len(hammer_velocities) > 0:
                # 获取x轴范围
                x_min = min(hammer_velocities) if hammer_velocities else 0
                x_max = max(hammer_velocities) if hammer_velocities else 100
                
                # 添加Z=0的水平虚线（均值线）
                fig.add_trace(go.Scatter(
                    x=[x_min, x_max],
                    y=[0, 0],
                    mode='lines',
                    name='Z=0',
                    line=dict(
                        color='#1976d2',
                        width=1.5,
                        dash='dot'
                    ),
                    hovertemplate='Z-Score = 0 (均值线)<extra></extra>'
                ))
                
                # 添加Z=+3的水平虚线（上阈值）
                fig.add_trace(go.Scatter(
                    x=[x_min, x_max],
                    y=[3, 3],
                    mode='lines',
                    name='Z=+3',
                    line=dict(
                        color='#1976d2',
                        width=2,
                        dash='dash'
                    ),
                    hovertemplate='Z-Score = +3 (上阈值)<extra></extra>'
                ))
                
                # 添加Z=-3的水平虚线（下阈值）
                fig.add_trace(go.Scatter(
                    x=[x_min, x_max],
                    y=[-3, -3],
                    mode='lines',
                    name='Z=-3',
                    line=dict(
                        color='#1976d2',
                        width=2,
                        dash='dash'
                    ),
                    hovertemplate='Z-Score = -3 (下阈值)<extra></extra>'
                ))
            
            # 更新布局
            fig.update_layout(
                # 删除title，因为UI区域已有标题
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
                    orientation='h',  # 水平排列图例
                    yanchor='bottom',
                    y=1.02,  # 图例在图表区域上方
                    xanchor='left',
                    x=0.0,  # 图例在左侧对齐
                    bgcolor='rgba(255, 255, 255, 0.9)',
                    bordercolor='gray',
                    borderwidth=1
                ),
                margin=dict(t=70, b=60, l=60, r=60)  # 增加顶部边距，为图例留出空间
            )
            
            logger.info(f"✅ 锤速-延时散点图生成成功，包含 {len(hammer_velocities)} 个数据点")
            return fig
            
        except Exception as e:
            logger.error(f"❌ 生成散点图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self.plot_generator._create_empty_plot(f"生成散点图失败: {str(e)}")
    
    def generate_key_hammer_velocity_scatter_plot(self) -> Any:
        """
        生成按键与锤速的散点图，颜色表示延时（支持单算法和多算法模式）
        x轴：按键ID（key_id）
        y轴：锤速（播放锤速）
        颜色：延时（keyon_offset，转换为ms，使用颜色映射）
        数据来源：所有已匹配的按键对
        """
        # 检查是否在多算法模式
        if self.multi_algorithm_mode and self.multi_algorithm_manager:
            # 多算法模式：生成多算法对比散点图
            active_algorithms = self.multi_algorithm_manager.get_active_algorithms()
            if not active_algorithms:
                logger.warning("⚠️ 多算法模式下没有激活的算法，返回空图表")
                return self.plot_generator._create_empty_plot("没有激活的算法")
            
            # 使用多算法图表生成器
            from backend.multi_algorithm_plot_generator import MultiAlgorithmPlotGenerator
            multi_plot_generator = MultiAlgorithmPlotGenerator(self.data_filter)
            return multi_plot_generator.generate_multi_algorithm_key_hammer_velocity_scatter_plot(
                active_algorithms
            )
        
        # 向后兼容：使用原有逻辑（已废弃）
        try:
            # 从分析器获取原始偏移对齐数据和匹配对
            if not self.analyzer or not self.analyzer.note_matcher:
                logger.warning("⚠️ 分析器或匹配器不存在，无法生成散点图")
                return self.plot_generator._create_empty_plot("分析器或匹配器不存在")
            
            matched_pairs = self.analyzer.note_matcher.get_matched_pairs()
            
            if not matched_pairs:
                logger.warning("⚠️ 没有匹配数据，无法生成散点图")
                return self.plot_generator._create_empty_plot("没有匹配数据")
            
            # 获取偏移对齐数据（已包含延时信息）
            offset_data = self.analyzer.note_matcher.get_offset_alignment_data()
            
            # 提取按键ID、锤速和延时数据
            key_ids = []  # 按键ID
            hammer_velocities = []  # 锤速（播放音符的第一个锤速值）
            delays_ms = []  # 延时（ms单位，用于颜色映射）
            
            # 创建匹配对索引到偏移数据的映射
            offset_map = {}
            for item in offset_data:
                record_idx = item.get('record_index')
                replay_idx = item.get('replay_index')
                if record_idx is not None and replay_idx is not None:
                    offset_map[(record_idx, replay_idx)] = item
            
            for record_idx, replay_idx, record_note, replay_note in matched_pairs:
                # 获取按键ID
                key_id = record_note.id
                
                # 获取播放音符的锤速（第一个锤速值）
                if len(replay_note.hammers) > 0 and len(replay_note.hammers.values) > 0:
                    hammer_velocity = replay_note.hammers.values[0]
                else:
                    continue  # 跳过没有锤速数据的音符
                
                # 从偏移数据中获取延时（keyon_offset），如果找不到则计算
                keyon_offset = None
                if (record_idx, replay_idx) in offset_map:
                    keyon_offset = offset_map[(record_idx, replay_idx)].get('keyon_offset', 0)
                else:
                    # 备用方案：直接计算（使用私有方法）
                    try:
                        record_keyon, _ = self.analyzer.note_matcher._calculate_note_times(record_note)
                        replay_keyon, _ = self.analyzer.note_matcher._calculate_note_times(replay_note)
                        keyon_offset = replay_keyon - record_keyon
                    except:
                        continue  # 如果计算失败，跳过该数据点
                
                # 将延时从0.1ms转换为ms，使用绝对值（用于颜色映射）
                delay_ms = abs(keyon_offset) / 10.0
                
                try:
                    key_id_int = int(key_id)
                    key_ids.append(key_id_int)
                    hammer_velocities.append(hammer_velocity)
                    delays_ms.append(delay_ms)
                except (ValueError, TypeError):
                    continue  # 跳过无效的按键ID
            
            if not key_ids:
                logger.warning("⚠️ 没有有效的散点图数据")
                return self.plot_generator._create_empty_plot("没有有效的散点图数据")
            
            # 创建Plotly散点图，使用颜色映射表示延时
            import plotly.graph_objects as go
            
            # 计算延时的最小值和最大值，用于颜色映射
            min_delay = min(delays_ms)
            max_delay = max(delays_ms)
            
            fig = go.Figure()
            
            # 添加散点图数据，颜色映射到延时值
            fig.add_trace(go.Scatter(
                x=key_ids,
                y=hammer_velocities,
                mode='markers',
                name='匹配对',
                marker=dict(
                    size=8,
                    color=delays_ms,  # 颜色映射到延时值
                    colorscale='Viridis',  # 使用Viridis颜色方案（从蓝色到黄色）
                    colorbar=dict(
                        title='延时 (ms)',
                        thickness=20,
                        len=0.6,
                        x=1.02
                    ),
                    cmin=min_delay,
                    cmax=max_delay,
                    opacity=0.7,
                    line=dict(width=0.5, color='rgba(0,0,0,0.3)'),
                    showscale=True  # 显示颜色条
                ),
                hovertemplate='键位: %{x}<br>锤速: %{y}<br>延时: %{marker.color:.2f}ms<extra></extra>'
            ))
            
            # 更新布局
            fig.update_layout(
                # 删除title，因为UI区域已有标题
                xaxis_title='按键ID',
                yaxis_title='锤速',
                xaxis=dict(
                    showgrid=True,
                    gridcolor='lightgray',
                    gridwidth=1,
                    dtick=10  # 每10个按键显示一个刻度
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
                showlegend=False,  # 不需要图例，因为有颜色条
                margin=dict(t=60, b=60, l=60, r=100)  # 右侧边距增加，为颜色条留出空间
            )
            
            logger.info(f"✅ 按键-锤速散点图生成成功，包含 {len(key_ids)} 个数据点")
            return fig
            
        except Exception as e:
            logger.error(f"❌ 生成散点图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self.plot_generator._create_empty_plot(f"生成散点图失败: {str(e)}")

    # ==================== 绘图相关方法 ====================
    
    def generate_waterfall_plot(self) -> Any:
        """生成瀑布图（支持单算法和多算法模式）"""
        # 检查是否在多算法模式
        if self.multi_algorithm_mode and self.multi_algorithm_manager:
            # 多算法模式：生成多算法对比瀑布图
            active_algorithms = self.multi_algorithm_manager.get_active_algorithms()
            if not active_algorithms:
                logger.warning("⚠️ 多算法模式下没有激活的算法，返回空图表")
                return self.plot_generator._create_empty_plot("没有激活的算法")
            
            # 使用多算法图表生成器
            from backend.multi_algorithm_plot_generator import MultiAlgorithmPlotGenerator
            multi_plot_generator = MultiAlgorithmPlotGenerator(self.data_filter)
            return multi_plot_generator.generate_multi_algorithm_waterfall_plot(
                active_algorithms,
                self.time_filter
            )
        
        # 向后兼容：使用原有逻辑（已废弃）
        # 检查是否有分析结果
        if not self.analyzer:
            logger.error("分析器不存在，无法生成瀑布图")
            return self.plot_generator._create_empty_plot("分析器不存在")
        
        # 检查是否有有效数据
        has_valid_data = (hasattr(self.analyzer, 'valid_record_data') and self.analyzer.valid_record_data and
                         hasattr(self.analyzer, 'valid_replay_data') and self.analyzer.valid_replay_data)
        
        if not has_valid_data:
            logger.error("没有有效的分析数据，无法生成瀑布图")
            return self.plot_generator._create_empty_plot("没有有效的分析数据")
        
        # 确保数据已同步到PlotGenerator
        if not self.plot_generator.valid_record_data or not self.plot_generator.valid_replay_data:
            logger.info("🔄 同步数据到PlotGenerator")
            self._sync_analysis_results()
        
        return self.plot_generator.generate_waterfall_plot(self.time_filter)
    
    def generate_watefall_conbine_plot(self, key_on: float, key_off: float, key_id: int) -> Tuple[Any, Any, Any]:
        """生成瀑布图对比图"""
        return self.plot_generator.generate_watefall_conbine_plot(key_on, key_off, key_id)
    
    def generate_watefall_conbine_plot_by_index(self, index: int, is_record: bool) -> Tuple[Any, Any, Any]:
        """根据索引生成瀑布图对比图"""
        return self.plot_generator.generate_watefall_conbine_plot_by_index(index, is_record)
    
    def generate_scatter_detail_plot_by_indices(self, record_index: int, replay_index: int) -> Tuple[Any, Any, Any]:
        """
        根据record_index和replay_index生成散点图点击的详细曲线图
        
        Args:
            record_index: 录制音符索引
            replay_index: 播放音符索引
            
        Returns:
            Tuple[Any, Any, Any]: (录制音符图, 播放音符图, 对比图)
        """
        if not self.analyzer or not self.analyzer.note_matcher:
            logger.warning("⚠️ 分析器或匹配器不存在，无法生成详细曲线图")
            return None, None, None
        
        # 从matched_pairs中查找对应的Note对象
        matched_pairs = self.analyzer.matched_pairs
        record_note = None
        play_note = None
        
        for r_idx, p_idx, r_note, p_note in matched_pairs:
            if r_idx == record_index and p_idx == replay_index:
                record_note = r_note
                play_note = p_note
                break
        
        if record_note is None or play_note is None:
            logger.warning(f"⚠️ 未找到匹配对: record_index={record_index}, replay_index={replay_index}")
            return None, None, None
        
        # 使用spmid模块生成详细图表
        import spmid
        detail_figure1 = spmid.plot_note_comparison_plotly(record_note, None)
        detail_figure2 = spmid.plot_note_comparison_plotly(None, play_note)
        detail_figure_combined = spmid.plot_note_comparison_plotly(record_note, play_note)
        
        logger.info(f"✅ 生成散点图点击的详细曲线图，record_index={record_index}, replay_index={replay_index}")
        return detail_figure1, detail_figure2, detail_figure_combined
    
    def generate_multi_algorithm_scatter_detail_plot_by_indices(
        self,
        algorithm_name: str,
        record_index: int,
        replay_index: int
    ) -> Tuple[Any, Any, Any]:
        """
        根据算法名称、record_index和replay_index生成多算法散点图点击的详细曲线图
        
        Args:
            algorithm_name: 算法名称
            record_index: 录制音符索引
            replay_index: 播放音符索引
            
        Returns:
            Tuple[Any, Any, Any]: (录制音符图, 播放音符图, 对比图)
        """
        if not self.multi_algorithm_mode or not self.multi_algorithm_manager:
            logger.warning("⚠️ 不在多算法模式，无法生成多算法详细曲线图")
            return None, None, None
        
        algorithm = self.multi_algorithm_manager.get_algorithm(algorithm_name)
        if not algorithm or not algorithm.analyzer or not algorithm.analyzer.note_matcher:
            logger.warning(f"⚠️ 算法 '{algorithm_name}' 不存在或没有分析器，无法生成详细曲线图")
            return None, None, None
        
        # 从matched_pairs中查找对应的Note对象
        matched_pairs = algorithm.analyzer.matched_pairs
        record_note = None
        play_note = None
        
        for r_idx, p_idx, r_note, p_note in matched_pairs:
            if r_idx == record_index and p_idx == replay_index:
                record_note = r_note
                play_note = p_note
                break
        
        if record_note is None or play_note is None:
            logger.warning(f"⚠️ 未找到匹配对: 算法={algorithm_name}, record_index={record_index}, replay_index={replay_index}")
            return None, None, None
        
        # 使用spmid模块生成详细图表
        import spmid
        detail_figure1 = spmid.plot_note_comparison_plotly(record_note, None, algorithm_name=algorithm_name)
        detail_figure2 = spmid.plot_note_comparison_plotly(None, play_note, algorithm_name=algorithm_name)
        detail_figure_combined = spmid.plot_note_comparison_plotly(record_note, play_note, algorithm_name=algorithm_name)
        
        logger.info(f"✅ 生成多算法散点图点击的详细曲线图，算法={algorithm_name}, record_index={record_index}, replay_index={replay_index}")
        return detail_figure1, detail_figure2, detail_figure_combined
    
    def generate_multi_algorithm_detail_plot_by_index(
        self, 
        algorithm_name: str, 
        index: int, 
        is_record: bool
    ) -> Tuple[Any, Any, Any]:
        """
        多算法模式下，根据算法名称和索引生成详细图表
        
        Args:
            algorithm_name: 算法名称
            index: 音符索引
            is_record: 是否为录制数据
            
        Returns:
            Tuple[Any, Any, Any]: (录制音符图, 播放音符图, 对比图)
        """
        if not self.multi_algorithm_manager:
            self._ensure_multi_algorithm_manager()
        
        # 获取对应的算法数据集
        algorithm = self.multi_algorithm_manager.get_algorithm(algorithm_name)
        if not algorithm or not algorithm.is_ready():
            logger.error(f"算法 '{algorithm_name}' 不存在或未就绪")
            return None, None, None
        
        # 从算法的analyzer中获取数据
        if not algorithm.analyzer:
            logger.error(f"算法 '{algorithm_name}' 没有分析器")
            return None, None, None
        
        # 获取算法的有效数据
        valid_record_data = algorithm.analyzer.valid_record_data if hasattr(algorithm.analyzer, 'valid_record_data') else []
        valid_replay_data = algorithm.analyzer.valid_replay_data if hasattr(algorithm.analyzer, 'valid_replay_data') else []
        matched_pairs = algorithm.analyzer.matched_pairs if hasattr(algorithm.analyzer, 'matched_pairs') else []
        
        record_note = None
        play_note = None
        
        if is_record:
            if index < 0 or index >= len(valid_record_data):
                logger.error(f"录制数据索引 {index} 超出范围 [0, {len(valid_record_data)-1}]")
                return None, None, None
            record_note = valid_record_data[index]
            
            # 从matched_pairs中查找匹配的播放音符
            if matched_pairs:
                for record_index, replay_index, r_note, p_note in matched_pairs:
                    if record_index == index:
                        play_note = p_note
                        break
        else:
            if index < 0 or index >= len(valid_replay_data):
                logger.error(f"播放数据索引 {index} 超出范围 [0, {len(valid_replay_data)-1}]")
                return None, None, None
            play_note = valid_replay_data[index]
            
            # 从matched_pairs中查找匹配的录制音符
            if matched_pairs:
                for record_index, replay_index, r_note, p_note in matched_pairs:
                    if replay_index == index:
                        record_note = r_note
                        break
        
        # 使用spmid模块生成详细图表
        import spmid
        detail_figure1 = spmid.plot_note_comparison_plotly(record_note, None, algorithm_name=algorithm_name)
        detail_figure2 = spmid.plot_note_comparison_plotly(None, play_note, algorithm_name=algorithm_name)
        detail_figure_combined = spmid.plot_note_comparison_plotly(record_note, play_note, algorithm_name=algorithm_name)
        
        logger.info(f"✅ 生成算法 '{algorithm_name}' 的详细图表，索引={index}, 类型={'record' if is_record else 'play'}")
        return detail_figure1, detail_figure2, detail_figure_combined
    
    def generate_multi_algorithm_error_detail_plot_by_index(
        self,
        algorithm_name: str,
        index: int,
        error_type: str,  # 'drop' 或 'multi'
        expected_key_id=None  # 期望的keyId，用于验证
    ) -> Tuple[Any, Any, Any]:
        """
        多算法模式下，根据算法名称和索引生成错误音符（丢锤/多锤）的详细图表
        
        Args:
            algorithm_name: 算法名称
            index: 音符索引（在initial_valid_record_data或initial_valid_replay_data中的索引）
            error_type: 错误类型，'drop'表示丢锤（录制有，播放无），'multi'表示多锤（播放有，录制无）
            
        Returns:
            Tuple[Any, Any, Any]: (录制音符图, 播放音符图, 对比图)
        """
        if not self.multi_algorithm_manager:
            self._ensure_multi_algorithm_manager()
        
        # 获取对应的算法数据集
        algorithm = self.multi_algorithm_manager.get_algorithm(algorithm_name)
        if not algorithm or not algorithm.is_ready():
            logger.error(f"算法 '{algorithm_name}' 不存在或未就绪")
            return None, None, None
        
        # 从算法的analyzer中获取数据
        if not algorithm.analyzer:
            logger.error(f"算法 '{algorithm_name}' 没有分析器")
            return None, None, None
        
        # 获取初始有效数据（第一次过滤后的数据，包含所有有效音符）
        initial_valid_record_data = getattr(algorithm.analyzer, 'initial_valid_record_data', None)
        initial_valid_replay_data = getattr(algorithm.analyzer, 'initial_valid_replay_data', None)
        
        if initial_valid_record_data is None or initial_valid_replay_data is None:
            logger.error(f"算法 '{algorithm_name}' 没有初始有效数据")
            return None, None, None
        
        # 获取匹配对列表，尝试查找是否有匹配的音符对
        # 包括正常的matched_pairs和超过阈值的exceeds_threshold_matched_pairs
        matched_pairs = getattr(algorithm.analyzer, 'matched_pairs', [])
        note_matcher = getattr(algorithm.analyzer, 'note_matcher', None)
        exceeds_threshold_matched_pairs = []
        if note_matcher and hasattr(note_matcher, 'exceeds_threshold_matched_pairs'):
            exceeds_threshold_matched_pairs = note_matcher.exceeds_threshold_matched_pairs
        
        record_note = None
        play_note = None
        
        if error_type == 'drop':
            # 丢锤：录制有，播放可能无也可能有（如果超过阈值但能匹配到）
            if index < 0 or index >= len(initial_valid_record_data):
                logger.error(f"录制数据索引 {index} 超出范围 [0, {len(initial_valid_record_data)-1}]")
                return None, None, None
            record_note = initial_valid_record_data[index]
            
            # 验证NoteID：从表格数据中获取的keyId应该与音符的id一致
            if expected_key_id is not None:
                if str(record_note.id) != str(expected_key_id):
                    logger.error(f"❌ NoteID不匹配: 表格中的keyId={expected_key_id}, 音符的id={record_note.id}, 算法={algorithm_name}, index={index}")
                    return None, None, None
                logger.info(f"✅ NoteID验证通过: keyId={expected_key_id}, 音符id={record_note.id}")
            
            # 尝试从matched_pairs和exceeds_threshold_matched_pairs中查找匹配的播放音符
            play_note = None
            # 先检查正常的matched_pairs
            if matched_pairs:
                for record_index, replay_index, r_note, p_note in matched_pairs:
                    if record_index == index:
                        play_note = p_note
                        logger.info(f"🔍 丢锤数据在matched_pairs中找到匹配的播放音符: replay_index={replay_index}")
                        break
            # 如果没找到，再检查超过阈值的匹配对
            if play_note is None and exceeds_threshold_matched_pairs:
                for record_index, replay_index, r_note, p_note in exceeds_threshold_matched_pairs:
                    if record_index == index:
                        play_note = p_note
                        logger.info(f"🔍 丢锤数据在exceeds_threshold_matched_pairs中找到匹配的播放音符（超过阈值）: replay_index={replay_index}")
                        break
            
            if play_note is None:
                logger.info(f"✅ 生成丢锤详细曲线图（无匹配播放数据），算法={algorithm_name}, index={index}")
            else:
                logger.info(f"✅ 生成丢锤详细曲线图（有匹配播放数据，显示对比图），算法={algorithm_name}, index={index}")
                
        elif error_type == 'multi':
            # 多锤：播放有，录制可能无也可能有（如果超过阈值但能匹配到）
            if index < 0 or index >= len(initial_valid_replay_data):
                logger.error(f"播放数据索引 {index} 超出范围 [0, {len(initial_valid_replay_data)-1}]")
                return None, None, None
            play_note = initial_valid_replay_data[index]
            
            # 验证NoteID：从表格数据中获取的keyId应该与音符的id一致
            if expected_key_id is not None:
                if str(play_note.id) != str(expected_key_id):
                    logger.error(f"❌ NoteID不匹配: 表格中的keyId={expected_key_id}, 音符的id={play_note.id}, 算法={algorithm_name}, index={index}")
                    return None, None, None
                logger.info(f"✅ NoteID验证通过: keyId={expected_key_id}, 音符id={play_note.id}")
            
            # 尝试从matched_pairs和exceeds_threshold_matched_pairs中查找匹配的录制音符
            record_note = None
            # 先检查正常的matched_pairs
            if matched_pairs:
                for record_index, replay_index, r_note, p_note in matched_pairs:
                    if replay_index == index:
                        record_note = r_note
                        logger.info(f"🔍 多锤数据在matched_pairs中找到匹配的录制音符: record_index={record_index}")
                        break
            # 如果没找到，再检查超过阈值的匹配对
            if record_note is None and exceeds_threshold_matched_pairs:
                for record_index, replay_index, r_note, p_note in exceeds_threshold_matched_pairs:
                    if replay_index == index:
                        record_note = r_note
                        logger.info(f"🔍 多锤数据在exceeds_threshold_matched_pairs中找到匹配的录制音符（超过阈值）: record_index={record_index}")
                        break
            
            if record_note is None:
                logger.info(f"✅ 生成多锤详细曲线图（无匹配录制数据），算法={algorithm_name}, index={index}")
            else:
                logger.info(f"✅ 生成多锤详细曲线图（有匹配录制数据，显示对比图），算法={algorithm_name}, index={index}")
        else:
            logger.error(f"未知的错误类型: {error_type}")
            return None, None, None
        
        # 生成图表
        import spmid.spmid_plot as spmid
        try:
            # 验证 Note 对象是否有效
            if error_type == 'drop' and record_note:
                logger.info(f"🔍 丢锤 - record_note ID={record_note.id}, after_touch长度={len(record_note.after_touch) if hasattr(record_note, 'after_touch') and record_note.after_touch is not None else 0}, hammers长度={len(record_note.hammers) if hasattr(record_note, 'hammers') and record_note.hammers is not None else 0}")
            elif error_type == 'multi' and play_note:
                logger.info(f"🔍 多锤 - play_note ID={play_note.id}, after_touch长度={len(play_note.after_touch) if hasattr(play_note, 'after_touch') and play_note.after_touch is not None else 0}, hammers长度={len(play_note.hammers) if hasattr(play_note, 'hammers') and play_note.hammers is not None else 0}")
            
            detail_figure1 = spmid.plot_note_comparison_plotly(record_note, None, algorithm_name=algorithm_name)
            detail_figure2 = spmid.plot_note_comparison_plotly(None, play_note, algorithm_name=algorithm_name)
            detail_figure_combined = spmid.plot_note_comparison_plotly(record_note, play_note, algorithm_name=algorithm_name)
            
            # 验证图表是否有效
            if detail_figure1 is None or detail_figure2 is None or detail_figure_combined is None:
                logger.error(f"❌ 图表生成失败，部分图表为None")
                return None, None, None
            
            logger.info(f"✅ 图表生成成功: figure1数据点={len(detail_figure1.data)}, figure2数据点={len(detail_figure2.data)}, figure_combined数据点={len(detail_figure_combined.data)}")
            
            return detail_figure1, detail_figure2, detail_figure_combined
        except Exception as e:
            logger.error(f"❌ 生成图表时出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None, None, None
    
    def get_note_image_base64(self, global_index: int) -> str:
        """获取音符图像Base64编码"""
        return self.plot_generator.get_note_image_base64(global_index)
    
    # ==================== 数据过滤相关方法 ====================
    
    def get_available_keys(self) -> List[int]:
        """获取可用按键列表"""
        return self.data_filter.get_available_keys()
    
    def set_key_filter(self, key_ids: List[int]) -> None:
        """设置按键过滤"""
        self.data_filter.set_key_filter(key_ids)
    
    def get_key_filter_status(self) -> Dict[str, Any]:
        """获取按键过滤状态"""
        return self.data_filter.get_key_filter_status()
    
    def set_time_filter(self, time_range: Optional[Tuple[float, float]]) -> None:
        """设置时间范围过滤"""
        self.time_filter.set_time_filter(time_range)
    
    def get_time_filter_status(self) -> Dict[str, Any]:
        """获取时间过滤状态"""
        return self.time_filter.get_time_filter_status()
    
    def get_time_range(self) -> Tuple[float, float]:
        """获取时间范围信息"""
        return self.time_filter.get_time_range()
    
    def get_display_time_range(self) -> Tuple[float, float]:
        """获取显示时间范围"""
        return self.time_filter.get_display_time_range()
    
    def update_time_range_from_input(self, start_time: float, end_time: float) -> Tuple[bool, str]:
        """从输入更新时间范围"""
        success = self.time_filter.update_time_range_from_input(start_time, end_time)
        if success:
            return True, "时间范围更新成功"
        else:
            return False, "时间范围更新失败"
    
    def get_time_range_info(self) -> Dict[str, Any]:
        """获取时间范围详细信息"""
        return self.time_filter.get_time_range_info()
    
    def reset_display_time_range(self) -> None:
        """重置显示时间范围"""
        self.time_filter.reset_display_time_range()
    
    def get_filtered_data(self) -> Dict[str, Any]:
        """获取过滤后的数据"""
        return self.data_filter.get_filtered_data()
    
    # ==================== 表格数据相关方法 ====================
    
    def get_summary_info(self) -> Dict[str, Any]:
        """获取摘要信息"""
        return self.table_generator.get_summary_info()
    
    def get_invalid_notes_table_data(self) -> List[Dict[str, Any]]:
        """
        获取无效音符表格数据（支持单算法和多算法模式）
        
        Returns:
            List[Dict[str, Any]]: 无效音符统计表格数据
        """
        # 检查是否在多算法模式
        if self.multi_algorithm_mode and self.multi_algorithm_manager:
            # 多算法模式：为每个激活的算法生成数据
            active_algorithms = self.multi_algorithm_manager.get_active_algorithms()
            
            if not active_algorithms:
                return []
            
            table_data = []
            
            for algorithm in active_algorithms:
                algorithm_name = algorithm.metadata.algorithm_name
                
                if not algorithm.analyzer:
                    continue
                
                try:
                    # 获取算法的无效音符统计数据
                    invalid_notes_table_data = getattr(algorithm.analyzer, 'invalid_notes_table_data', {})
                    
                    if not invalid_notes_table_data:
                        # 如果没有数据，添加默认的空数据
                        table_data.append({
                            'algorithm_name': algorithm_name,
                            'data_type': '录制数据',
                            'total_notes': 0,
                            'valid_notes': 0,
                            'invalid_notes': 0,
                            'duration_too_short': 0,
                            'empty_data': 0,
                            'silent_notes': 0,
                            'other_errors': 0
                        })
                        table_data.append({
                            'algorithm_name': algorithm_name,
                            'data_type': '回放数据',
                            'total_notes': 0,
                            'valid_notes': 0,
                            'invalid_notes': 0,
                            'duration_too_short': 0,
                            'empty_data': 0,
                            'silent_notes': 0,
                            'other_errors': 0
                        })
                        continue
                    
                    # 处理录制数据
                    record_data = invalid_notes_table_data.get('record_data', {})
                    invalid_reasons = record_data.get('invalid_reasons', {})
                    table_data.append({
                        'algorithm_name': algorithm_name,
                        'data_type': '录制数据',
                        'total_notes': record_data.get('total_notes', 0),
                        'valid_notes': record_data.get('valid_notes', 0),
                        'invalid_notes': record_data.get('invalid_notes', 0),
                        'duration_too_short': invalid_reasons.get('duration_too_short', 0),
                        'empty_data': invalid_reasons.get('empty_data', 0),
                        'silent_notes': invalid_reasons.get('silent_notes', 0),
                        'other_errors': invalid_reasons.get('other_errors', 0)
                    })
                    
                    # 处理回放数据
                    replay_data = invalid_notes_table_data.get('replay_data', {})
                    replay_invalid_reasons = replay_data.get('invalid_reasons', {})
                    table_data.append({
                        'algorithm_name': algorithm_name,
                        'data_type': '回放数据',
                        'total_notes': replay_data.get('total_notes', 0),
                        'valid_notes': replay_data.get('valid_notes', 0),
                        'invalid_notes': replay_data.get('invalid_notes', 0),
                        'duration_too_short': replay_invalid_reasons.get('duration_too_short', 0),
                        'empty_data': replay_invalid_reasons.get('empty_data', 0),
                        'silent_notes': replay_invalid_reasons.get('silent_notes', 0),
                        'other_errors': replay_invalid_reasons.get('other_errors', 0)
                    })
                    
                except Exception as e:
                    logger.error(f"❌ 获取算法 '{algorithm_name}' 的无效音符统计数据失败: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    continue
            
            return table_data
        
        # 向后兼容：使用原有逻辑（已废弃）
        return self.table_generator.get_invalid_notes_table_data()
    
    def get_error_table_data(self, error_type: str) -> List[Dict[str, Any]]:
        """获取错误表格数据（支持单算法和多算法模式）"""
        # 检查是否在多算法模式
        if self.multi_algorithm_mode and self.multi_algorithm_manager:
            # 多算法模式：合并所有激活算法的错误数据，添加"算法名称"列
            active_algorithms = self.multi_algorithm_manager.get_active_algorithms()
            if not active_algorithms:
                return []
            
            table_data = []
            for algorithm in active_algorithms:
                algorithm_name = algorithm.metadata.algorithm_name
                
                if not algorithm.analyzer:
                    continue
                
                # 获取该算法的错误数据
                if error_type == '丢锤':
                    error_notes = algorithm.analyzer.drop_hammers if hasattr(algorithm.analyzer, 'drop_hammers') else []
                elif error_type == '多锤':
                    error_notes = algorithm.analyzer.multi_hammers if hasattr(algorithm.analyzer, 'multi_hammers') else []
                else:
                    continue
                
                # 转换为表格数据格式，添加算法名称
                for note in error_notes:
                    row = {
                        'algorithm_name': algorithm_name,
                        'data_type': 'record' if error_type == '丢锤' else 'play',
                        'keyId': note.keyId if hasattr(note, 'keyId') else 'N/A',
                        'keyOn': f"{note.keyOn:.2f}" if hasattr(note, 'keyOn') and note.keyOn is not None else 'N/A',
                        'keyOff': f"{note.keyOff:.2f}" if hasattr(note, 'keyOff') and note.keyOff is not None else 'N/A',
                        'index': note.index if hasattr(note, 'index') else 'N/A',
                        'analysis_reason': getattr(note, 'analysis_reason', '未匹配')
                    }
                    table_data.append(row)
            
            return table_data
        
        # 向后兼容：使用原有逻辑（已废弃）
        return self.table_generator.get_error_table_data(error_type)
    
    
    # ==================== 内部方法 ====================
    
    def _perform_error_analysis(self) -> None:
        """执行错误分析"""
        try:
            # 确保analyzer存在（向后兼容，已废弃）
            if self.analyzer is None:
                self.analyzer = SPMIDAnalyzer()
                logger.info("✅ 重新初始化analyzer（向后兼容）")
            
            # 执行分析
            record_data = self.data_manager.get_record_data()
            replay_data = self.data_manager.get_replay_data()
            
            if not record_data or not replay_data:
                logger.error("数据不存在，无法执行错误分析")
                return
            
            analysis_result = self.analyzer.analyze(record_data, replay_data)
        
            # 解包分析结果
            self.analyzer.multi_hammers, self.analyzer.drop_hammers, self.analyzer.silent_hammers, \
            self.analyzer.valid_record_data, self.analyzer.valid_replay_data, \
            self.analyzer.invalid_notes_table_data, self.analyzer.matched_pairs = analysis_result
            
            # 同步数据到数据管理器
            self.data_manager.set_analysis_results(
                self.analyzer.valid_record_data, 
                self.analyzer.valid_replay_data
            )
            
            # 同步分析结果到各个模块
            self._sync_analysis_results()
            
            logger.info("✅ 错误分析完成")
            
            # 初始化延时分析器（在分析完成后）
            if self.analyzer:
                self.delay_analysis = DelayAnalysis(self.analyzer)

        except Exception as e:
            logger.error(f"错误分析失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    # ==================== 延时关系分析相关方法 ====================
    
    def get_delay_by_key_analysis(self) -> Dict[str, Any]:
        """
        获取延时与按键的关系分析结果
        
        Returns:
            Dict[str, Any]: 分析结果，包含描述性统计、ANOVA检验、事后检验、异常按键等
        """
        try:
            if not self.delay_analysis:
                if self.analyzer:
                    self.delay_analysis = DelayAnalysis(self.analyzer)
                else:
                    logger.warning("⚠️ 分析器不存在，无法进行延时与按键分析")
                    return {
                        'status': 'error',
                        'message': '分析器不存在'
                    }
            
            result = self.delay_analysis.analyze_delay_by_key()
            logger.info("✅ 延时与按键关系分析完成")
            return result
            
        except Exception as e:
            logger.error(f"❌ 延时与按键分析失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'status': 'error',
                'message': f'分析失败: {str(e)}'
            }
    
    def get_delay_by_velocity_analysis(self) -> Dict[str, Any]:
        """
        获取延时与锤速的关系分析结果
        
        Returns:
            Dict[str, Any]: 分析结果，包含相关性分析、回归分析、分组分析等
        """
        try:
            if not self.delay_analysis:
                if self.analyzer:
                    self.delay_analysis = DelayAnalysis(self.analyzer)
                else:
                    logger.warning("⚠️ 分析器不存在，无法进行延时与锤速分析")
                    return {
                        'status': 'error',
                        'message': '分析器不存在'
                    }
            
            result = self.delay_analysis.analyze_delay_by_velocity()
            logger.info("✅ 延时与锤速关系分析完成")
            return result
            
        except Exception as e:
            logger.error(f"❌ 延时与锤速分析失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'status': 'error',
                'message': f'分析失败: {str(e)}'
            }
    
    def generate_delay_by_key_analysis_plots(self) -> Dict[str, Any]:
        """
        生成延时与按键关系的可视化图表
        
        Returns:
            Dict[str, Any]: 包含箱线图的字典
        """
        try:
            analysis_result = self.get_delay_by_key_analysis()
            
            if analysis_result.get('status') != 'success':
                return {
                    'boxplot': self.plot_generator._create_empty_plot("分析失败"),
                    'analysis_result': analysis_result
                }
            
            boxplot = self.plot_generator.generate_delay_by_key_boxplot(analysis_result)
            
            return {
                'boxplot': boxplot,
                'analysis_result': analysis_result
            }
            
        except Exception as e:
            logger.error(f"❌ 生成延时与按键分析图表失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'boxplot': self.plot_generator._create_empty_plot(f"生成失败: {str(e)}"),
                'analysis_result': {}
            }
    
    def generate_delay_by_velocity_analysis_plot(self) -> Any:
        """
        生成延时与锤速关系的可视化图表
        
        Returns:
            Any: Plotly图表对象
        """
        try:
            analysis_result = self.get_delay_by_velocity_analysis()
            
            if analysis_result.get('status') != 'success':
                return self.plot_generator._create_empty_plot("分析失败")
            
            return self.plot_generator.generate_delay_by_velocity_analysis_plot(analysis_result)
            
        except Exception as e:
            logger.error(f"❌ 生成延时与锤速分析图表失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self.plot_generator._create_empty_plot(f"生成失败: {str(e)}")
    
    def get_force_delay_by_key_analysis(self) -> Dict[str, Any]:
        """
        获取每个按键的力度与延时关系分析结果
        
        按按键ID分组，对每个按键分析其内部的力度（锤速）与延时的统计关系。
        包括：相关性分析、回归分析、描述性统计等。
        
        支持多算法模式：返回所有激活算法的数据。
        
        Returns:
            Dict[str, Any]: 分析结果，包含：
                - key_analysis: 每个按键的分析结果列表（单算法模式）
                - overall_summary: 整体摘要统计
                - scatter_data: 散点图数据（按按键分组）
                - algorithm_results: 多算法模式下的各算法结果（多算法模式）
                - status: 状态标识
        """
        try:
            # 多算法模式：返回所有激活算法的数据
            if self.multi_algorithm_mode and self.multi_algorithm_manager:
                active_algorithms = self.multi_algorithm_manager.get_active_algorithms()
                if not active_algorithms:
                    logger.warning("⚠️ 没有激活的算法，无法进行按键力度-延时分析")
                    return {
                        'status': 'error',
                        'message': '没有激活的算法'
                    }
                
                # 为每个算法生成分析结果
                algorithm_results = {}
                for algorithm in active_algorithms:
                    if not algorithm.analyzer:
                        logger.warning(f"⚠️ 算法 '{algorithm.metadata.algorithm_name}' 没有分析器，跳过")
                        continue
                    
                    algorithm_name = algorithm.metadata.algorithm_name
                    delay_analysis = DelayAnalysis(algorithm.analyzer)
                    result = delay_analysis.analyze_force_delay_by_key()
                    
                    if result.get('status') == 'success':
                        algorithm_results[algorithm_name] = result
                        logger.info(f"✅ 算法 '{algorithm_name}' 的按键力度-延时分析完成")
                
                if not algorithm_results:
                    logger.warning("⚠️ 没有成功分析的算法")
                    return {
                        'status': 'error',
                        'message': '没有成功分析的算法'
                    }
                
                # 返回多算法结果
                return {
                    'status': 'success',
                    'multi_algorithm_mode': True,
                    'algorithm_results': algorithm_results,
                    # 为了向后兼容，也包含第一个算法的结果
                    'key_analysis': list(algorithm_results.values())[0].get('key_analysis', []),
                    'overall_summary': list(algorithm_results.values())[0].get('overall_summary', {}),
                    'scatter_data': list(algorithm_results.values())[0].get('scatter_data', {}),
                }
            
            # 单算法模式（向后兼容）
            if not self.delay_analysis:
                if self.analyzer:
                    self.delay_analysis = DelayAnalysis(self.analyzer)
                else:
                    logger.warning("⚠️ 分析器不存在，无法进行按键力度-延时分析")
                    return {
                        'status': 'error',
                        'message': '分析器不存在'
                    }
            
            result = self.delay_analysis.analyze_force_delay_by_key()
            logger.info("✅ 按键力度-延时分析完成")
            return result
            
        except Exception as e:
            logger.error(f"❌ 按键力度-延时分析失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'status': 'error',
                'message': f'分析失败: {str(e)}'
            }
    
    def get_key_force_interaction_analysis(self) -> Dict[str, Any]:
        """
        获取按键与力度的联合统计关系分析结果（多因素分析）
        
        使用多因素ANOVA和交互效应分析，评估：
        1. 按键对延时的主效应
        2. 力度对延时的主效应
        3. 按键×力度的交互效应
        
        支持多算法模式：使用第一个激活算法的数据进行分析。
        
        Returns:
            Dict[str, Any]: 分析结果，包含：
                - two_way_anova: 双因素ANOVA结果
                - interaction_effect: 交互效应分析结果
                - stratified_regression: 分层回归分析结果
                - interaction_plot_data: 交互效应图数据
                - status: 状态标识
        """
        try:
            # 多算法模式：返回所有激活算法的数据
            if self.multi_algorithm_mode and self.multi_algorithm_manager:
                active_algorithms = self.multi_algorithm_manager.get_active_algorithms()
                if not active_algorithms:
                    logger.warning("⚠️ 没有激活的算法，无法进行按键-力度交互分析")
                    return {
                        'status': 'error',
                        'message': '没有激活的算法'
                    }
                
                # 为每个算法生成分析结果
                algorithm_results = {}
                for algorithm in active_algorithms:
                    if not algorithm.analyzer:
                        logger.warning(f"⚠️ 算法 '{algorithm.metadata.algorithm_name}' 没有分析器，跳过")
                        continue
                    
                    algorithm_name = algorithm.metadata.algorithm_name
                    delay_analysis = DelayAnalysis(algorithm.analyzer)
                    result = delay_analysis.analyze_key_force_interaction()
                    
                    if result.get('status') == 'success':
                        algorithm_results[algorithm_name] = result
                        logger.info(f"✅ 算法 '{algorithm_name}' 的按键-力度交互分析完成")
                
                if not algorithm_results:
                    logger.warning("⚠️ 没有成功分析的算法")
                    return {
                        'status': 'error',
                        'message': '没有成功分析的算法'
                    }
                
                # 返回多算法结果
                return {
                    'status': 'success',
                    'multi_algorithm_mode': True,
                    'algorithm_results': algorithm_results,
                    # 为了向后兼容，也包含第一个算法的结果（用于交互效应强度等统计信息）
                    'two_way_anova': list(algorithm_results.values())[0].get('two_way_anova', {}),
                    'interaction_effect': list(algorithm_results.values())[0].get('interaction_effect', {}),
                    'stratified_regression': list(algorithm_results.values())[0].get('stratified_regression', {}),
                }
            
            # 单算法模式（向后兼容）
            if not self.delay_analysis:
                if self.analyzer:
                    self.delay_analysis = DelayAnalysis(self.analyzer)
                else:
                    logger.warning("⚠️ 分析器不存在，无法进行按键-力度交互分析")
                    return {
                        'status': 'error',
                        'message': '分析器不存在'
                    }
            
            result = self.delay_analysis.analyze_key_force_interaction()
            logger.info("✅ 按键-力度交互分析完成")
            return result
            
        except Exception as e:
            logger.error(f"❌ 按键-力度交互分析失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'status': 'error',
                'message': f'分析失败: {str(e)}'
            }
    
    # generate_force_delay_by_key_plot 已删除（功能与按键-力度交互效应图重复）
    
    def generate_key_force_interaction_plot(self) -> Any:
        """
        生成按键-力度交互效应图
        
        Returns:
            Any: Plotly图表对象
        """
        try:
            analysis_result = self.get_key_force_interaction_analysis()
            
            if analysis_result.get('status') != 'success':
                return self.plot_generator._create_empty_plot("分析失败")
            
            return self.plot_generator.generate_key_force_interaction_plot(analysis_result)
            
        except Exception as e:
            logger.error(f"❌ 生成交互效应图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self.plot_generator._create_empty_plot(f"生成失败: {str(e)}")
    
    # ==================== 多算法对比模式相关方法 ====================
    
    def _ensure_multi_algorithm_manager(self, max_algorithms: Optional[int] = None) -> None:
        """
        确保multi_algorithm_manager已初始化（多算法模式始终启用）
        
        Args:
            max_algorithms: 最大算法数量（None表示无限制）
        """
        if self.multi_algorithm_manager is None:
            self.multi_algorithm_manager = MultiAlgorithmManager(max_algorithms=max_algorithms)
            limit_text = "无限制" if max_algorithms is None else str(max_algorithms)
            logger.info(f"✅ 初始化多算法管理器 (最大算法数: {limit_text})")
    
    def enable_multi_algorithm_mode(self, max_algorithms: Optional[int] = None) -> Tuple[bool, bool, Optional[str]]:
        """
        启用多算法对比模式（向后兼容方法，现在只是确保管理器已初始化）
        
        Args:
            max_algorithms: 最大算法数量（None表示无限制）
            
        Returns:
            Tuple[bool, bool, Optional[str]]: (是否成功, 是否有现有数据需要迁移, 文件名)
        """
        try:
            self._ensure_multi_algorithm_manager(max_algorithms)
            
            # 检查是否有现有的分析数据需要迁移
            has_existing_data = False
            existing_filename = None
            
            if self.analyzer and self.analyzer.note_matcher and hasattr(self.analyzer, 'matched_pairs') and len(self.analyzer.matched_pairs) > 0:
                # 有已分析的数据
                has_existing_data = True
                # 获取文件名
                data_source_info = self.get_data_source_info()
                existing_filename = data_source_info.get('filename', '未知文件')
                logger.info(f"检测到现有分析数据，文件名: {existing_filename}")
            
            return True, has_existing_data, existing_filename
            
        except Exception as e:
            logger.error(f"❌ 初始化多算法管理器失败: {e}")
            return False, False, None
    
    def migrate_existing_data_to_algorithm(self, algorithm_name: str) -> Tuple[bool, str]:
        """
        将现有的单算法分析数据迁移到多算法模式
        
        Args:
            algorithm_name: 用户指定的算法名称
            
        Returns:
            Tuple[bool, str]: (是否成功, 错误信息)
        """
        if not self.multi_algorithm_manager:
            self._ensure_multi_algorithm_manager()
        
        if not self.analyzer or not self.analyzer.note_matcher:
            return False, "没有可迁移的分析数据"
        
        try:
            # 获取原始数据
            record_data = self.data_manager.get_record_data()
            replay_data = self.data_manager.get_replay_data()
            
            if not record_data or not replay_data:
                return False, "原始数据不存在"
            
            # 获取文件名
            data_source_info = self.get_data_source_info()
            filename = data_source_info.get('filename', '未知文件')
            
            # 生成唯一的算法名称（算法名_文件名（无扩展名））
            unique_algorithm_name = self.multi_algorithm_manager._generate_unique_algorithm_name(algorithm_name, filename)
            
            # 创建算法数据集（使用唯一名称作为内部标识，原始名称作为显示名称）
            color_index = 0
            algorithm = AlgorithmDataset(unique_algorithm_name, algorithm_name, filename, color_index)
            
            # 直接使用现有的 analyzer，而不是重新分析
            algorithm.analyzer = self.analyzer
            algorithm.record_data = record_data
            algorithm.replay_data = replay_data
            algorithm.metadata.status = AlgorithmStatus.READY
            
            # 添加到管理器
            self.multi_algorithm_manager.algorithms[unique_algorithm_name] = algorithm
            
            logger.info(f"✅ 现有数据已迁移为算法: {algorithm_name}")
            return True, ""
            
        except Exception as e:
            logger.error(f"❌ 迁移现有数据失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, str(e)
    
    # disable_multi_algorithm_mode 方法已移除 - 不再支持单算法模式
    
    def is_multi_algorithm_mode(self) -> bool:
        """检查是否处于多算法对比模式（始终返回True）"""
        return True
    
    async def add_algorithm(self, algorithm_name: str, filename: str, 
                           contents: str) -> Tuple[bool, str]:
        """
        添加算法到多算法管理器（异步）
        
        Args:
            algorithm_name: 算法名称（用户指定）
            filename: 文件名
            contents: 文件内容（base64编码）
            
        Returns:
            Tuple[bool, str]: (是否成功, 错误信息)
        """
        if not self.multi_algorithm_manager:
            self._ensure_multi_algorithm_manager()
        
        try:
            # 解码文件内容
            import base64
            decoded_bytes = base64.b64decode(contents.split(',')[1] if ',' in contents else contents)
            
            # 加载SPMID数据
            from .spmid_loader import SPMIDLoader
            loader = SPMIDLoader()
            success = loader.load_spmid_data(decoded_bytes)
            
            if not success:
                return False, "SPMID文件解析失败"
            
            # 获取数据
            record_data = loader.get_record_data()
            replay_data = loader.get_replay_data()
            
            if not record_data or not replay_data:
                return False, "数据为空"
            
            # 异步添加算法
            success, error_msg = await self.multi_algorithm_manager.add_algorithm_async(
                algorithm_name, filename, record_data, replay_data
            )
            
            return success, error_msg
            
        except Exception as e:
            logger.error(f"❌ 添加算法失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, str(e)
    
    def remove_algorithm(self, algorithm_name: str) -> bool:
        """
        从多算法管理器中移除算法
        
        Args:
            algorithm_name: 算法名称
            
        Returns:
            bool: 是否成功
        """
        if not self.multi_algorithm_mode or not self.multi_algorithm_manager:
            return False
        
        return self.multi_algorithm_manager.remove_algorithm(algorithm_name)
    
    def get_all_algorithms(self) -> List[Dict[str, Any]]:
        """
        获取所有算法的信息列表
        
        Returns:
            List[Dict[str, Any]]: 算法信息列表
        """
        if not self.multi_algorithm_mode or not self.multi_algorithm_manager:
            return []
        
        algorithms = []
        for alg in self.multi_algorithm_manager.get_all_algorithms():
            # 确保is_active有值，如果为None则默认为True（新上传的文件应该默认显示）
            is_active = alg.is_active if alg.is_active is not None else True
            if alg.is_active is None:
                alg.is_active = True
                logger.info(f"✅ 确保算法 '{alg.metadata.algorithm_name}' 默认显示: is_active={is_active}")
            
            algorithms.append({
                'algorithm_name': alg.metadata.algorithm_name,  # 内部唯一标识（用于查找）
                'display_name': alg.metadata.display_name,  # 显示名称（用于UI显示）
                'filename': alg.metadata.filename,
                'status': alg.metadata.status.value,
                'is_active': is_active,
                'color': alg.color,
                'is_ready': alg.is_ready()
            })
        
        return algorithms
    
    def get_key_matched_pairs_by_algorithm(self, algorithm_name: str, key_id: int) -> List[Tuple[int, int, Any, Any, float]]:
        """
        获取指定算法和按键ID的所有匹配对，按时间戳排序
        
        Args:
            algorithm_name: 算法名称
            key_id: 按键ID
            
        Returns:
            List[Tuple[int, int, Note, Note, float]]: 匹配对列表，每个元素为(record_index, replay_index, record_note, replay_note, record_keyon)
        """
        if not self.multi_algorithm_mode or not self.multi_algorithm_manager:
            return []
        
        algorithm = self.multi_algorithm_manager.get_algorithm(algorithm_name)
        if not algorithm or not algorithm.is_ready() or not algorithm.analyzer:
            return []
        
        matched_pairs = algorithm.analyzer.matched_pairs if hasattr(algorithm.analyzer, 'matched_pairs') else []
        if not matched_pairs:
            return []
        
        # 获取偏移对齐数据以获取时间戳
        offset_data = algorithm.analyzer.get_offset_alignment_data()
        offset_map = {}
        for item in offset_data:
            record_idx = item.get('record_index')
            replay_idx = item.get('replay_index')
            if record_idx is not None and replay_idx is not None:
                offset_map[(record_idx, replay_idx)] = item.get('record_keyon', 0)
        
        # 筛选指定按键ID的匹配对
        key_pairs = []
        for record_idx, replay_idx, record_note, replay_note in matched_pairs:
            if record_note.id == key_id:
                record_keyon = offset_map.get((record_idx, replay_idx), 0)
                key_pairs.append((record_idx, replay_idx, record_note, replay_note, record_keyon))
        
        # 按时间戳排序
        key_pairs.sort(key=lambda x: x[4])
        
        return key_pairs
    
    def get_active_algorithms(self) -> List[AlgorithmDataset]:
        """
        获取激活的算法列表（用于对比显示）
        
        Returns:
            List[AlgorithmDataset]: 激活的算法列表
        """
        if not self.multi_algorithm_mode or not self.multi_algorithm_manager:
            return []
        
        return self.multi_algorithm_manager.get_active_algorithms()
    
    def toggle_algorithm(self, algorithm_name: str) -> bool:
        """
        切换算法的显示/隐藏状态
        
        Args:
            algorithm_name: 算法名称
            
        Returns:
            bool: 是否成功
        """
        if not self.multi_algorithm_mode or not self.multi_algorithm_manager:
            return False
        
        return self.multi_algorithm_manager.toggle_algorithm(algorithm_name)
    
    def rename_algorithm(self, old_name: str, new_name: str) -> bool:
        """
        重命名算法
        
        Args:
            old_name: 旧名称
            new_name: 新名称
            
        Returns:
            bool: 是否成功
        """
        if not self.multi_algorithm_mode or not self.multi_algorithm_manager:
            return False
        
        return self.multi_algorithm_manager.rename_algorithm(old_name, new_name)
    
    def get_multi_algorithm_statistics(self) -> Dict[str, Any]:
        """
        获取多算法对比统计信息
        
        Returns:
            Dict[str, Any]: 对比统计信息
        """
        if not self.multi_algorithm_mode or not self.multi_algorithm_manager:
            return {}
        
        return self.multi_algorithm_manager.get_comparison_statistics()
    
