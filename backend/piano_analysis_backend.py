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
        
        # 初始化分析器实例
        self.analyzer = SPMIDAnalyzer()
        
        # 初始化延时分析器（延迟初始化，因为需要analyzer）
        self.delay_analysis = None
        
        
        logger.info(f"✅ PianoAnalysisBackend初始化完成 (Session: {session_id})")

    
    # ==================== 数据管理相关方法 ====================
    
    def clear_data_state(self) -> None:
        """清理所有数据状态"""
        self.data_manager.clear_data_state()
        self.plot_generator.set_data()
        self.data_filter.set_data(None, None)
        self.table_generator.set_data()
        self.analyzer = None
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
    
    # ==================== 时间对齐分析相关方法 ====================
    
    # def spmid_offset_alignment(self) -> Tuple[pd.DataFrame, np.ndarray]:
    #     """执行SPMID偏移量对齐分析"""
    #     if not self.analyzer:
    #         logger.error("没有可用的分析器实例")
    #         return pd.DataFrame(), np.array([])
        
    #     # 从分析器获取偏移统计信息
    #     offset_stats = self.analyzer.get_offset_statistics()
        
    #     # 创建DataFrame
    #     df_stats = pd.DataFrame([{
    #         'total_pairs': offset_stats.get('total_pairs', 0),
    #         'keyon_avg_offset': offset_stats.get('keyon_offset_stats', {}).get('average', 0.0),
    #         'keyon_max_offset': offset_stats.get('keyon_offset_stats', {}).get('max', 0.0),
    #         'keyon_min_offset': offset_stats.get('keyon_offset_stats', {}).get('min', 0.0),
    #         'keyon_std_offset': offset_stats.get('keyon_offset_stats', {}).get('std', 0.0),
    #         'keyoff_avg_offset': offset_stats.get('keyoff_offset_stats', {}).get('average', 0.0),
    #         'keyoff_max_offset': offset_stats.get('keyoff_offset_stats', {}).get('max', 0.0),
    #         'keyoff_min_offset': offset_stats.get('keyoff_offset_stats', {}).get('min', 0.0),
    #         'keyoff_std_offset': offset_stats.get('keyoff_offset_stats', {}).get('std', 0.0)
    #     }])
        
    #     # 创建偏移数组
    #     offset_data = self.analyzer.get_offset_alignment_data()
    #     all_offsets_array = np.array([item['average_offset'] for item in offset_data])
        
    #     return df_stats, all_offsets_array
    
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
    
    def generate_delay_histogram_plot(self) -> Any:
        """
        生成延时分布直方图，并叠加正态拟合曲线（基于已匹配按键对的带符号keyon_offset）。
        x轴：延时 (ms)，y轴：概率密度
        """
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

            # TODO
            fig.add_trace(go.Histogram(
                x=delays_ms,
                histnorm='probability density',
                name='延时分布',
                marker_color='rgba(33, 150, 243, 0.6)',
                opacity=0.7
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
                title={
                    'text': '延时分布直方图（附正态拟合曲线）',
                    'x': 0.5,
                    'xanchor': 'center',
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
                    y=1.02,
                    xanchor='left',
                    x=0.0,
                    bgcolor='rgba(255, 255, 255, 0.9)',
                    bordercolor='gray',
                    borderwidth=1
                ),
                margin=dict(t=70, b=60, l=60, r=60)
            )

            return fig
        except Exception as e:
            logger.error(f"生成延时直方图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self.plot_generator._create_empty_plot(f"生成延时直方图失败: {str(e)}")
    

    
    def get_offset_alignment_data(self) -> List[Dict[str, Any]]:
        """获取偏移对齐数据 - 转换为DataTable格式，包含无效音符分析"""
        
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
        """生成偏移对齐分析柱状图 - 键位为横坐标，中位数、均值、标准差为纵坐标，分3个子图显示"""
        
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
                        textfont=dict(size=20),
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
                        textfont=dict(size=20),
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
                        textfont=dict(size=20),
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
                        textfont=dict(size=20),
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
                        textfont=dict(size=20),
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
                        textfont=dict(size=20),
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
                        textfont=dict(size=20),
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
                        textfont=dict(size=20),
                        hovertemplate='键位: %{x}<br>方差: %{y:.2f}ms²<br>状态: 未匹配<extra></extra>',
                        showlegend=False
                    ),
                    row=4, col=1
                )
            
            # 更新布局 - 增大图表区域
            fig.update_layout(
                title={
                    'text': '偏移对齐分析柱状图',
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 28}
                },
                height=2000,  # 进一步增加高度，确保参考线可见
                showlegend=False,
                margin=dict(l=100, r=150, t=180, b=120)  # 增加顶部和右侧边距，为参考线标注留空间
            )
            
            # 更新坐标轴
            fig.update_xaxes(title_text="键位ID", row=4, col=1)
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
        生成按键与延时的散点图
        x轴：按键ID（key_id）
        y轴：延时（keyon_offset，转换为ms）
        数据来源：所有已匹配的按键对
        """
        try:
            # 从分析器获取原始偏移对齐数据（包含每个匹配对的详细信息）
            if not self.analyzer or not self.analyzer.note_matcher:
                logger.warning("⚠️ 分析器或匹配器不存在，无法生成散点图")
                return self.plot_generator._create_empty_plot("分析器或匹配器不存在")
            
            offset_data = self.analyzer.note_matcher.get_offset_alignment_data()
            
            if not offset_data:
                logger.warning("⚠️ 没有匹配数据，无法生成散点图")
                return self.plot_generator._create_empty_plot("没有匹配数据")
            
            # 提取按键ID和延时数据
            key_ids = []
            delays_ms = []  # 延时（ms单位）
            
            for item in offset_data:
                key_id = item.get('key_id')
                keyon_offset = item.get('keyon_offset', 0)  # 单位：0.1ms
                
                # 跳过无效数据
                if key_id is None or key_id == 'N/A':
                    continue
                
                try:
                    key_id_int = int(key_id)
                    # 将延时从0.1ms转换为ms，并使用绝对值
                    delay_ms = abs(keyon_offset) / 10.0
                    
                    key_ids.append(key_id_int)
                    delays_ms.append(delay_ms)
                except (ValueError, TypeError) as e:
                    logger.warning(f"⚠️ 跳过无效数据点: key_id={key_id}, error={e}")
                    continue
            
            if not key_ids:
                logger.warning("⚠️ 没有有效的散点图数据")
                return self.plot_generator._create_empty_plot("没有有效的散点图数据")
            
            # 创建Plotly散点图
            import plotly.graph_objects as go
            
            fig = go.Figure()
            
            # 添加散点图数据
            fig.add_trace(go.Scatter(
                x=key_ids,
                y=delays_ms,
                mode='markers',
                name='匹配对',
                marker=dict(
                    size=8,
                    color='#2e7d32',
                    opacity=0.6,
                    line=dict(width=1, color='#1b5e20')
                ),
                hovertemplate='键位: %{x}<br>延时: %{y:.2f}ms<extra></extra>'
            ))
            
            # 添加趋势线（可选，帮助观察延时分布趋势）
            if len(key_ids) > 1:
                # 计算每个按键的平均延时
                from collections import defaultdict
                key_delay_groups = defaultdict(list)
                for k, d in zip(key_ids, delays_ms):
                    key_delay_groups[k].append(d)
                
                sorted_keys = sorted(key_delay_groups.keys())
                avg_delays = [sum(key_delay_groups[k]) / len(key_delay_groups[k]) for k in sorted_keys]
                
                fig.add_trace(go.Scatter(
                    x=sorted_keys,
                    y=avg_delays,
                    mode='lines+markers',
                    name='平均延时',
                    line=dict(color='#1976d2', width=2, dash='dash'),
                    marker=dict(size=6, color='#1976d2'),
                    hovertemplate='键位: %{x}<br>平均延时: %{y:.2f}ms<extra></extra>'
                ))
            
            # 更新布局
            fig.update_layout(
                title={
                    'text': '按键与延时散点图（已匹配按键对）',
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
                margin=dict(t=70, b=60, l=60, r=60)  # 增加顶部边距，为图例留出空间
            )
            
            logger.info(f"✅ 按键-延时散点图生成成功，包含 {len(key_ids)} 个数据点")
            return fig
            
        except Exception as e:
            logger.error(f"❌ 生成散点图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self.plot_generator._create_empty_plot(f"生成散点图失败: {str(e)}")
    
    def generate_hammer_velocity_delay_scatter_plot(self) -> Any:
        """
        生成锤速与延时的散点图
        x轴：锤速（播放锤速）
        y轴：延时（keyon_offset，转换为ms）
        数据来源：所有已匹配的按键对
        """
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
            
            # 提取锤速和延时数据
            hammer_velocities = []  # 锤速（播放音符的第一个锤速值）
            delays_ms = []  # 延时（ms单位）
            
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
                
                # 将延时从0.1ms转换为ms，并使用绝对值
                delay_ms = abs(keyon_offset) / 10.0
                
                hammer_velocities.append(hammer_velocity)
                delays_ms.append(delay_ms)
            
            if not hammer_velocities:
                logger.warning("⚠️ 没有有效的散点图数据")
                return self.plot_generator._create_empty_plot("没有有效的散点图数据")
            
            # 创建Plotly散点图
            import plotly.graph_objects as go
            
            fig = go.Figure()
            
            # 添加散点图数据
            fig.add_trace(go.Scatter(
                x=hammer_velocities,
                y=delays_ms,
                mode='markers',
                name='匹配对',
                marker=dict(
                    size=8,
                    color='#d32f2f',
                    opacity=0.6,
                    line=dict(width=1, color='#b71c1c')
                ),
                hovertemplate='锤速: %{x}<br>延时: %{y:.2f}ms<extra></extra>'
            ))
            
            # 添加趋势线（可选，帮助观察延时与锤速的关系）
            if len(hammer_velocities) > 1:
                # 按锤速分组计算平均延时
                from collections import defaultdict
                velocity_delay_groups = defaultdict(list)
                for v, d in zip(hammer_velocities, delays_ms):
                    # 将锤速按区间分组（每10个单位一组）
                    velocity_group = (v // 10) * 10
                    velocity_delay_groups[velocity_group].append(d)
                
                sorted_velocities = sorted(velocity_delay_groups.keys())
                avg_delays = [sum(velocity_delay_groups[v]) / len(velocity_delay_groups[v]) for v in sorted_velocities]
                
                fig.add_trace(go.Scatter(
                    x=sorted_velocities,
                    y=avg_delays,
                    mode='lines+markers',
                    name='平均延时',
                    line=dict(color='#1976d2', width=2, dash='dash'),
                    marker=dict(size=6, color='#1976d2'),
                    hovertemplate='锤速区间: %{x}<br>平均延时: %{y:.2f}ms<extra></extra>'
                ))
            
            # 更新布局
            fig.update_layout(
                title={
                    'text': '锤速与延时散点图（已匹配按键对）',
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 18, 'color': '#2c3e50'}
                },
                xaxis_title='锤速',
                yaxis_title='延时 (ms)',
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
        生成按键与锤速的散点图，颜色表示延时
        x轴：按键ID（key_id）
        y轴：锤速（播放锤速）
        颜色：延时（keyon_offset，转换为ms，使用颜色映射）
        数据来源：所有已匹配的按键对
        """
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
                title={
                    'text': '按键与锤速散点图（颜色表示延时，已匹配按键对）',
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
        """生成瀑布图"""
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
    
    def get_invalid_notes_table_data(self) -> Dict[str, Any]:
        """获取无效音符表格数据"""
        return self.table_generator.get_invalid_notes_table_data()
    
    def get_error_table_data(self, error_type: str) -> List[Dict[str, Any]]:
        """获取错误表格数据"""
        return self.table_generator.get_error_table_data(error_type)
    
    
    # ==================== 内部方法 ====================
    
    def _perform_error_analysis(self) -> None:
        """执行错误分析"""
        try:
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
    
