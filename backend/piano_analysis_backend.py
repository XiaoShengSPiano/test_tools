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
                    
                table_data.append({
                        'key_id': key_id,
                        'count': len(offsets),
                        'median': f"{median_val/10:.2f}ms",
                        'mean': f"{mean_val/10:.2f}ms",
                        'std': f"{std_val/10:.2f}ms",
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
                        'status': f'invalid (R:{record_count}, P:{replay_count})'
                    })
            
            if not table_data:
                return [{
                    'key_id': "无数据",
                    'count': 0,
                    'median': "N/A",
                    'mean': "N/A",
                    'std': "N/A",
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
            
            # 提取数据用于绘图
            key_ids = []
            median_values = []
            mean_values = []
            std_values = []
            status_list = []
            
            for item in alignment_data:
                key_id = item['key_id']
                # 从字符串中提取数值，去除单位
                median_str = item['median'].replace('ms', '') if isinstance(item['median'], str) else str(item['median'])
                mean_str = item['mean'].replace('ms', '') if isinstance(item['mean'], str) else str(item['mean'])
                std_str = item['std'].replace('ms', '') if isinstance(item['std'], str) else str(item['std'])
                status = item['status']
                
                try:
                    # 跳过无效的key_id
                    if key_id == '无数据' or key_id == '错误' or not str(key_id).isdigit():
                        continue
                    
                    key_ids.append(int(key_id))
                    median_values.append(float(median_str))
                    mean_values.append(float(mean_str))
                    std_values.append(float(std_str))
                    status_list.append(status)
                except (ValueError, TypeError) as e:
                    logger.warning(f"⚠️ 跳过无效数据: {e}")
                    continue
            
            if not key_ids:
                logger.warning("⚠️ 没有有效的偏移对齐数据，无法生成柱状图")
                return self.plot_generator._create_empty_plot("没有有效的偏移对齐数据")
            
            # 创建Plotly图表 - 3个子图分别显示柱状图
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
            
            fig = make_subplots(
                rows=3, cols=1,
                subplot_titles=('中位数偏移', '均值偏移', '标准差'),
                vertical_spacing=0.08,
                row_heights=[0.33, 0.33, 0.34]
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
            
            # 添加未匹配数据的中位数柱状图
            if unmatched_indices:
                unmatched_key_ids = [key_ids[i] for i in unmatched_indices]
                unmatched_median = [median_values[i] for i in unmatched_indices]
                unmatched_mean = [mean_values[i] for i in unmatched_indices]
                unmatched_std = [std_values[i] for i in unmatched_indices]
                
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
            
            # 更新布局
            fig.update_layout(
                title={
                    'text': '偏移对齐分析柱状图',
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 28}
                },
                height=1200,
                showlegend=False,
                margin=dict(l=100, r=100, t=150, b=120)
            )
            
            # 更新坐标轴
            fig.update_xaxes(title_text="键位ID", row=3, col=1)
            fig.update_yaxes(title_text="中位数偏移 (ms)", row=1, col=1)
            fig.update_yaxes(title_text="均值偏移 (ms)", row=2, col=1)
            fig.update_yaxes(title_text="标准差 (ms)", row=3, col=1)
            
            logger.info(f"✅ 偏移对齐分析柱状图生成成功，包含 {len(key_ids)} 个键位（匹配: {len(matched_indices)}, 未匹配: {len(unmatched_indices)}）")
            return fig
            
        except Exception as e:
            logger.error(f"❌ 生成偏移对齐分析柱状图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self.plot_generator._create_empty_plot(f"生成柱状图失败: {str(e)}")

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

        except Exception as e:
            logger.error(f"错误分析失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
