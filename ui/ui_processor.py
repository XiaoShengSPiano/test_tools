#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
UI处理器模块
负责处理UI内容生成，包括文件上传和历史记录选择的UI反馈
"""

from dash import html
import plotly.graph_objects as go
from ui.layout_components import create_report_layout
from utils.logger import Logger

logger = Logger.get_logger()


class UIProcessor:
    """UI处理器 - 负责生成各种UI内容"""
    
    def __init__(self):
        """初始化UI处理器"""
        self.logger = logger
    
    def create_upload_success_content(self, result_data):
        """
        创建文件上传成功的内容
        
        Args:
            result_data: 包含filename、history_id、record_count、replay_count的字典
            
        Returns:
            html.Div: 成功内容
        """
        return html.Div([
            html.H4("✅ 文件上传成功", className="text-center text-success"),
            html.P(f"文件名: {result_data['filename']}", className="text-center"),
            html.P(f"历史记录ID: {result_data['history_id']}", className="text-center"),
            html.P(f"录制音符: {result_data['record_count']} 个", className="text-center"),
            html.P(f"播放音符: {result_data['replay_count']} 个", className="text-center"),
            html.P("数据已加载并分析完成，可以查看瀑布图和生成报告", className="text-center text-muted")
        ])
    
    def create_upload_error_content(self, filename, error_msg):
        """
        创建文件上传错误的内容
        
        Args:
            filename: 文件名
            error_msg: 错误信息
            
        Returns:
            html.Div: 错误内容
        """
        if self._is_track_count_error(error_msg):
            return self._create_track_count_error_content(filename)
        elif self._is_file_format_error(error_msg):
            return self._create_file_format_error_content(filename)
        else:
            return self._create_general_upload_error_content(filename, error_msg)
    
    def create_general_error_content(self, error_msg):
        """
        创建一般错误内容
        
        Args:
            error_msg: 错误信息
            
        Returns:
            html.Div: 错误内容
        """
        return html.Div([
            html.H4("❌ 处理失败", className="text-center text-danger"),
            html.P(f"错误信息: {error_msg}", className="text-center"),
            html.P("请检查文件或联系管理员", className="text-center text-muted")
        ])
    
    def create_history_basic_info_content(self, result_data):
        """
        创建历史记录基本信息内容
        
        Args:
            result_data: 包含filename、main_record等的字典
            
        Returns:
            html.Div: 基本信息内容
        """
        main_record = result_data['main_record']
        # main_record是一个tuple，格式为: (id, filename, upload_time, ...)
        record_id = main_record[0] if len(main_record) > 0 else '未知'
        upload_time = main_record[2] if len(main_record) > 2 else '未知'
        
        return html.Div([
            html.H4("📋 历史记录基本信息", className="text-center"),
            html.P(f"文件名: {result_data['filename']}", className="text-center"),
            html.P(f"创建时间: {upload_time}", className="text-center"),
            html.P(f"记录ID: {record_id}", className="text-center"),
            html.P("⚠️ 该历史记录没有保存文件内容，无法重新分析", className="text-center text-warning")
        ])
    
    def create_empty_figure(self, title):
        """
        创建空的Plotly figure对象
        
        Args:
            title: 标题
            
        Returns:
            go.Figure: 空图表
        """
        fig = go.Figure()
        fig.add_annotation(
            text=title,
            xref="paper", yref="paper",
            x=0.5, y=0.5, xanchor='center', yanchor='middle',
            showarrow=False, font=dict(size=16, color="gray")
        )
        fig.update_layout(
            title=title,
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            plot_bgcolor='white',
            paper_bgcolor='white'
        )
        return fig
    
    def create_fallback_waterfall(self, filename, timestamp, error_msg):
        """
        创建瀑布图生成失败时的备用内容
        
        Args:
            filename: 文件名
            timestamp: 时间戳
            error_msg: 错误信息
            
        Returns:
            go.Figure: 错误图表
        """
        fig = go.Figure()
        fig.add_annotation(
            text=f"瀑布图生成失败<br>文件: {filename}<br>时间: {timestamp}<br>错误: {error_msg}",
            xref="paper", yref="paper",
            x=0.5, y=0.5, xanchor='center', yanchor='middle',
            showarrow=False, font=dict(size=16, color="red")
        )
        fig.update_layout(
            title="瀑布图生成失败",
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            plot_bgcolor='white',
            paper_bgcolor='white'
        )
        return fig
    
    def create_fallback_report(self, filename, record_id, error_msg):
        """
        创建分析报告生成失败时的备用内容
        
        Args:
            filename: 文件名
            record_id: 记录ID
            error_msg: 错误信息
            
        Returns:
            html.Div: 错误内容
        """
        return html.Div([
            html.H4("❌ 报告生成失败", className="text-center text-danger"),
            html.P(f"文件: {filename}", className="text-center"),
            html.P(f"记录ID: {record_id}", className="text-center"),
            html.P(f"错误信息: {error_msg}", className="text-center"),
            html.P("请检查数据完整性或重新分析", className="text-center text-muted")
        ])
    
    def create_error_content(self, title, message):
        """
        创建错误内容
        
        Args:
            title: 错误标题
            message: 错误消息
            
        Returns:
            html.Div: 错误内容
        """
        return html.Div([
            html.H4(f"❌ {title}", className="text-center text-danger"),
            html.P(message, className="text-center"),
            html.P("请检查数据或联系管理员", className="text-center text-muted")
        ])
    
    def generate_history_waterfall(self, backend, filename, main_record):
        """
        生成历史记录瀑布图
        
        Args:
            backend: 后端实例
            filename: 文件名
            main_record: 主记录
            
        Returns:
            go.Figure: 瀑布图或错误图
        """
        try:
            fig = backend.generate_waterfall_plot()
            if fig:
                return fig
            else:
                return self.create_fallback_waterfall(filename, main_record.get('timestamp', ''), "瀑布图生成失败")
        except Exception as e:
            self.logger.error(f"❌ 历史记录瀑布图生成失败: {e}")
            return self.create_fallback_waterfall(filename, main_record.get('timestamp', ''), str(e))
    
    def generate_history_report(self, backend, filename, history_id):
        """
        生成历史记录报告
        
        Args:
            backend: 后端实例
            filename: 文件名
            history_id: 历史记录ID
            
        Returns:
            html.Div: 报告内容或错误内容
        """
        try:
            report_content = create_report_layout(backend)
            if report_content:
                return report_content
            else:
                return self.create_fallback_report(filename, history_id, "报告生成失败")
        except Exception as e:
            self.logger.error(f"❌ 历史记录报告生成失败: {e}")
            return self.create_fallback_report(filename, history_id, str(e))
    
    # ==================== 私有方法 ====================
    
    def _is_track_count_error(self, error_msg):
        """判断是否为轨道数量错误"""
        return error_msg and ("轨道" in error_msg or "track" in error_msg.lower())

    def _is_file_format_error(self, error_msg):
        """判断是否为文件格式错误"""
        return error_msg and ("Invalid file format" in error_msg or "SPID" in error_msg or "file format" in error_msg)

    def _create_track_count_error_content(self, filename):
        """创建轨道数量不足的错误内容"""
        return html.Div([
            html.H4("❌ 轨道数量不足", className="text-center text-danger"),
            html.P(f"文件: {filename}", className="text-center"),
            html.P("SPMID文件需要包含至少2个轨道（录制轨道+播放轨道）", className="text-center"),
            html.P("请检查文件是否正确生成", className="text-center text-muted")
        ])

    def _create_file_format_error_content(self, filename):
        """创建文件格式错误的错误内容"""
        return html.Div([
            html.H4("❌ 文件格式错误", className="text-center text-danger"),
            html.P(f"文件: {filename}", className="text-center"),
            html.P("文件格式不正确，请确保上传的是有效的SPMID文件", className="text-center"),
            html.P("SPMID文件应该是由钢琴分析工具生成的", className="text-center text-muted")
        ])

    def _create_general_upload_error_content(self, filename, error_msg):
        """创建一般上传错误的错误内容"""
        return html.Div([
            html.H4("❌ 文件上传失败", className="text-center text-danger"),
            html.P(f"文件: {filename}", className="text-center"),
            html.P(f"错误信息: {error_msg}", className="text-center"),
            html.P("请检查文件是否完整或重新上传", className="text-center text-muted")
        ])

