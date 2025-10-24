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
import numpy as np
from typing import Optional, Tuple, Any
from utils.logger import Logger

# 绘图相关导入
import spmid
import plotly.graph_objects as go

logger = Logger.get_logger()


class PlotGenerator:
    """绘图生成器 - 负责各种图表的生成"""
    
    def __init__(self):
        """初始化绘图生成器"""
        self.valid_record_data = None
        self.valid_replay_data = None
        self.matched_pairs = None
        self.analyzer = None  # SPMIDAnalyzer实例
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
    
    def generate_waterfall_plot(self) -> Any:
        """
        生成瀑布图 - 调用SPMIDAnalyzer获取有效数据
        
        Returns:
            Any: 瀑布图对象
        """
        try:
            if not self.analyzer:
                logger.error("没有可用的分析器实例，无法生成瀑布图")
                return self._create_empty_plot("分析器不存在")
            
            # 调用SPMIDAnalyzer的analyze方法获取有效数据
            valid_record_data = self.analyzer.get_valid_record_data()
            valid_replay_data = self.analyzer.get_valid_replay_data()
            
            if not valid_record_data or not valid_replay_data:
                logger.error("有效数据不存在，无法生成瀑布图")
                return self._create_empty_plot("数据不存在")
            
            # 使用spmid模块生成瀑布图
            fig = spmid.plot_bar_plotly(valid_record_data, valid_replay_data)
            
            logger.info("✅ 瀑布图生成成功")
            return fig
            
        except Exception as e:
            logger.error(f"瀑布图生成失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._create_empty_plot(f"生成瀑布图失败: {str(e)}")
    
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
        
        detail_figure1 = spmid.plot_note_comparison_plotly(record_note, None)
        detail_figure2 = spmid.plot_note_comparison_plotly(None, replay_note)
        detail_figure_combined = spmid.plot_note_comparison_plotly(record_note, replay_note)

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
        
        detail_figure1 = spmid.plot_note_comparison_plotly(record_note, None)
        detail_figure2 = spmid.plot_note_comparison_plotly(None, play_note)
        detail_figure_combined = spmid.plot_note_comparison_plotly(record_note, play_note)

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
