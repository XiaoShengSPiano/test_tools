#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
持续时间差异表格点击处理器

负责处理持续时间差异表格的点击事件，显示曲线对比
"""

import logging
from dash import callback_context
from typing import Dict, Any, Optional, Tuple
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
from dash import dcc

from ui.duration_diff_curves import DurationDiffCurvePlotter, get_duration_diff_pairs_from_backend

logger = logging.getLogger(__name__)


class DurationDiffClickHandler:
    """持续时间差异表格点击处理器"""
    
    def __init__(self):
        """初始化处理器"""
        self.plotter = DurationDiffCurvePlotter()
    
    def handle_table_click(self, active_cell, close_modal_clicks, close_btn_clicks,
                          table_data, session_id, current_style, backend, active_algorithms):
        """
        处理持续时间差异表格点击事件
        
        Args:
            active_cell: 活动单元格
            close_modal_clicks: 关闭按钮点击次数
            close_btn_clicks: 关闭按钮2点击次数
            table_data: 表格数据
            session_id: 会话ID
            current_style: 当前模态框样式
            backend: 后端实例
            active_algorithms: 活动算法列表
            
        Returns:
            Tuple[modal_style, comparison_container_children, clicked_point_info]
        """
        # 检测触发源
        trigger_info = self._detect_trigger(active_cell, close_modal_clicks, close_btn_clicks)
        
        if trigger_info.get('is_close'):
            return self._handle_close_modal()
        
        if trigger_info.get('should_skip'):
            return current_style, [], {}
        
        # 处理表格点击
        return self._handle_table_cell_click(
            active_cell, table_data, backend, active_algorithms
        )
    
    def _detect_trigger(self, active_cell, close_modal_clicks, close_btn_clicks) -> Dict[str, Any]:
        """
        检测触发源
        
        Returns:
            Dict: {'is_close': bool, 'should_skip': bool, 'continue': bool}
        """
        ctx = callback_context
        if not ctx.triggered:
            return {'should_skip': True, 'is_close': False, 'continue': False}
        
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        
        # 检查是否是关闭按钮
        if trigger_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            return {'is_close': True, 'should_skip': False, 'continue': False}
        
        # 检查是否是表格点击
        if trigger_id == 'duration-diff-table' and active_cell:
            return {'is_close': False, 'should_skip': False, 'continue': True}
        
        # 其他情况（如初始化触发）
        return {'should_skip': True, 'is_close': False, 'continue': False}
    
    def _handle_close_modal(self) -> Tuple[Dict, list, Dict]:
        """
        处理关闭模态框
        
        Returns:
            Tuple[modal_style, empty_list, empty_dict]
        """
        logger.info("关闭持续时间差异曲线对比模态框")
        modal_style = {
            'display': 'none',
            'position': 'fixed',
            'zIndex': '9999',
            'left': '0',
            'top': '0',
            'width': '100%',
            'height': '100%',
            'backgroundColor': 'rgba(0,0,0,0.6)',
            'backdropFilter': 'blur(5px)'
        }
        return modal_style, [], {}
    
    def _handle_table_cell_click(self, active_cell, table_data, backend, 
                                 active_algorithms) -> Tuple[Dict, list, Dict]:
        """
        处理表格单元格点击
        
        Args:
            active_cell: 活动单元格
            table_data: 表格数据
            backend: 后端实例
            active_algorithms: 活动算法列表
            
        Returns:
            Tuple[modal_style, comparison_container_children, clicked_point_info]
        """
        try:
            # 获取点击的行号
            row_idx = active_cell['row']
            
            if not table_data or row_idx >= len(table_data):
                logger.warning(f"无效的行索引: {row_idx}")
                return self._create_error_response("无效的行索引")
            
            # 获取行数据
            row_data = table_data[row_idx]
            
            # 获取持续时间差异数据
            duration_diff_pairs = get_duration_diff_pairs_from_backend(backend, active_algorithms)
            
            if not duration_diff_pairs:
                logger.warning("未找到持续时间差异数据")
                return self._create_error_response("未找到持续时间差异数据")
            
            # 根据索引找到对应的匹配对
            pair_index = row_data.get('index', 0) - 1  # 索引从1开始，需要减1
            
            if pair_index < 0 or pair_index >= len(duration_diff_pairs):
                logger.warning(f"无效的匹配对索引: {pair_index}")
                return self._create_error_response("无效的匹配对索引")
            
            # 提取匹配对数据
            pair_data = self._extract_pair_data(duration_diff_pairs[pair_index])
            
            if not pair_data:
                return self._create_error_response("提取匹配对数据失败")
            
            # 生成曲线对比图
            comparison_ui = self._create_comparison_ui(pair_data)
            
            # 显示模态框
            modal_style = self._create_show_modal_style()
            
            # 保存点击信息
            clicked_info = {
                'key_id': pair_data['key_id'],
                'record_idx': pair_data['record_idx'],
                'replay_idx': pair_data['replay_idx']
            }
            
            logger.info(f"显示持续时间差异曲线: 按键{pair_data['key_id']}, "
                       f"录制索引{pair_data['record_idx']}, 播放索引{pair_data['replay_idx']}")
            
            return modal_style, comparison_ui, clicked_info
            
        except Exception as e:
            logger.error(f"处理表格点击失败: {e}", exc_info=True)
            return self._create_error_response(str(e))
    
    def _extract_pair_data(self, pair_tuple) -> Optional[Dict[str, Any]]:
        """
        提取匹配对数据

        Args:
            pair_tuple: (record_idx, replay_idx, record_note, replay_note,
                        record_duration, replay_duration, duration_ratio,
                        record_keyon, record_keyoff, replay_keyon, replay_keyoff)

        Returns:
            Dict: 提取的数据字典
        """
        try:
            if len(pair_tuple) < 11:
                logger.error(f"匹配对数据格式错误: 长度={len(pair_tuple)}")
                return None

            record_idx, replay_idx, record_note, replay_note, \
                record_duration, replay_duration, duration_ratio, \
                record_keyon, record_keyoff, replay_keyon, replay_keyoff = pair_tuple

            return {
                'record_idx': record_idx,
                'replay_idx': replay_idx,
                'record_note': record_note,
                'replay_note': replay_note,
                'record_duration': record_duration,
                'replay_duration': replay_duration,
                'duration_ratio': duration_ratio,
                'record_keyon': record_keyon,
                'record_keyoff': record_keyoff,
                'replay_keyon': replay_keyon,
                'replay_keyoff': replay_keyoff,
                'key_id': record_note.id if record_note else 'N/A'
            }
            
        except Exception as e:
            logger.error(f"提取匹配对数据失败: {e}")
            return None
    
    def _create_comparison_ui(self, pair_data: Dict[str, Any]) -> list:
        """
        创建曲线对比UI
        
        Args:
            pair_data: 匹配对数据
            
        Returns:
            list: UI组件列表
        """
        try:
            # 生成对比图（使用通用接口）
            # 对于拆分的按键数据，强制绘制分割点
            fig, split_analysis = self.plotter.create_comparison_figure(
                note_a=pair_data['record_note'],
                note_b=pair_data['replay_note'],
                key_id=pair_data['key_id'],
                duration_a=pair_data['record_duration'],
                duration_b=pair_data['replay_duration'],
                duration_ratio=pair_data['duration_ratio'],
                label_a='录制',
                label_b='播放',
                force_draw_split_point=True  # 强制绘制分割点
            )
            
            # 获取分割分析信息UI
            split_info_ui = self._create_split_info_ui(split_analysis)
            
            # 创建UI布局
            ui_components = []
            
            # 添加分割点信息（如果有）
            if split_info_ui:
                ui_components.append(split_info_ui)
            
            # 添加图表
            ui_components.append(
                dbc.Row([
                    dbc.Col([
                        dcc.Graph(
                            figure=fig,
                            config={'displayModeBar': True, 'displaylogo': False}
                        )
                    ], width=12)
                ])
            )
            
            return ui_components
            
        except Exception as e:
            logger.error(f"创建对比UI失败: {e}")
            return self._create_error_ui(str(e))
    
    def _create_split_info_ui(self, split_analysis: Optional[Dict]):
        """
        创建分割点信息UI

        Args:
            split_analysis: 分割分析结果

        Returns:
            dbc.Row or None: 分割点信息UI组件
        """
        try:
            if not split_analysis:
                # 分析完全失败
                return dbc.Row([
                    dbc.Col([
                        dbc.Alert([
                            dcc.Markdown("### ⚠️ 分割点分析失败\n\n无法分析此数据的分割点。")
                        ], color="warning", style={'marginBottom': '20px'})
                    ], width=12)
                ])

            if not split_analysis.get('best_candidate'):
                # 没有找到最佳分割点
                candidates = split_analysis.get('candidates', [])
                record_keyoff = split_analysis.get('record_keyoff', 0)
                next_hammer = split_analysis.get('next_hammer', 0)

                if candidates:
                    info_msg = f"""
### ⚠️ 未找到有效分割点

**搜索范围**: [{record_keyoff:.1f}ms, {next_hammer:.1f}ms]

找到 {len(candidates)} 个候选点，但均不符合分割条件。
"""
                else:
                    info_msg = f"""
### ⚠️ 未找到分割点

**搜索范围**: [{record_keyoff:.1f}ms, {next_hammer:.1f}ms]

在指定范围内未找到任何分割点候选。
"""

                return dbc.Row([
                    dbc.Col([
                        dbc.Alert([
                            dcc.Markdown(info_msg)
                        ], color="warning", style={'marginBottom': '20px'})
                    ], width=12)
                ])

            # 找到最佳分割点
            best = split_analysis['best_candidate']
            candidates = split_analysis['candidates']

            # 获取信息
            best_time = best['time']
            best_value = best['value']

            # 获取锤击点信息
            record_keyoff = split_analysis.get('record_keyoff', 0)
            next_hammer = split_analysis.get('next_hammer', 0)

            # 构建分割点信息
            split_info = f"""
### 🎯 最佳分割点

**搜索范围**: [{record_keyoff:.1f}ms, {next_hammer:.1f}ms]

**分割点**: {best_time:.1f}ms（触后值: {best_value:.1f}）
"""

            return dbc.Row([
                dbc.Col([
                    dbc.Alert([
                        dcc.Markdown(split_info)
                    ], color="success", style={'marginBottom': '20px'})
                ], width=12)
            ])

        except Exception as e:
            logger.error(f"创建分割点信息UI失败: {e}")
            return dbc.Row([
                dbc.Col([
                    dbc.Alert([
                        dcc.Markdown(f"### ❌ 分割点信息显示错误\n\n{e}")
                    ], color="danger", style={'marginBottom': '20px'})
                ], width=12)
            ])
    
    def _create_show_modal_style(self) -> Dict:
        """
        创建显示模态框的样式
        
        Returns:
            Dict: 样式字典
        """
        return {
            'display': 'block',
            'position': 'fixed',
            'zIndex': '9999',
            'left': '0',
            'top': '0',
            'width': '100%',
            'height': '100%',
            'backgroundColor': 'rgba(0,0,0,0.6)',
            'backdropFilter': 'blur(5px)'
        }
    
    def _create_error_response(self, error_msg: str) -> Tuple[Dict, list, Dict]:
        """
        创建错误响应
        
        Args:
            error_msg: 错误信息
            
        Returns:
            Tuple[modal_style, error_ui, empty_dict]
        """
        modal_style = self._create_show_modal_style()
        error_ui = self._create_error_ui(error_msg)
        return modal_style, error_ui, {}
    
    def _create_error_ui(self, error_msg: str) -> list:
        """
        创建错误UI
        
        Args:
            error_msg: 错误信息
            
        Returns:
            list: 错误UI组件列表
        """
        return [
            dbc.Alert(
                f"❌ 错误: {error_msg}",
                color="danger"
            )
        ]


print("Duration difference click handler loaded successfully")

