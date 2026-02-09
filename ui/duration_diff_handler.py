#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Duration Difference Handler - Displays duration difference pairs in a table
"""

from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass

# Dash imports
import dash
from dash import html, dcc, Input, Output, State
import dash_bootstrap_components as dbc
import dash_table

from utils.logger import Logger
from spmid.spmid_reader import Note
from components.common_curve_plotter import DurationDiffCurvePlotter

logger = Logger.get_logger()

@dataclass
class DurationDiffPair:
    """持续时间差异对数据"""
    record_idx: int
    replay_idx: int
    record_note: Note
    replay_note: Note
    duration_ratio: float

class DurationDiffHandler:
    """持续时间差异分析处理器"""

    def __init__(self):
        self.diff_pairs: List[DurationDiffPair] = []
        self.plotter = DurationDiffCurvePlotter()

    def set_diff_pairs(self, diff_pairs_data: List[Any]) -> None:
        """从匹配结果设置持续时间差异数据"""
        self.diff_pairs = []
        for data in diff_pairs_data:
            # 支持多种输入格式以便向后兼容
            if isinstance(data, (list, tuple)) and len(data) >= 7:
                self.diff_pairs.append(DurationDiffPair(
                    record_idx=data[0],
                    replay_idx=data[1],
                    record_note=data[2],
                    replay_note=data[3],
                    duration_ratio=data[6]
                ))
            elif isinstance(data, dict):
                 self.diff_pairs.append(DurationDiffPair(
                    record_idx=data.get('record_idx', 0),
                    replay_idx=data.get('replay_idx', 0),
                    record_note=data.get('record_note'),
                    replay_note=data.get('replay_note'),
                    duration_ratio=data.get('duration_ratio', 1.0)
                ))
            else:
                logger.warning(f"跳过无效的持续时间差异数据: 类型={type(data)}, 数据={data}")


    def create_table_data(self) -> List[Dict]:
        """创建表格显示数据"""
        table_data = []
        for i, pair in enumerate(self.diff_pairs):
            table_data.append({
                "index": i + 1,
                "key_id": pair.record_note.id if pair.record_note else "N/A",
                "record_duration": f"{pair.record_note.duration_ms:.1f} ms" if pair.record_note and pair.record_note.duration_ms is not None else "0.0 ms",
                "replay_duration": f"{pair.replay_note.duration_ms:.1f} ms" if pair.replay_note and pair.replay_note.duration_ms is not None else "0.0 ms",
                "duration_ratio": f"{pair.duration_ratio:.2f}",
                "diff_level": self._get_diff_level(pair.duration_ratio)
            })
        return table_data

    def _get_diff_level(self, ratio: float) -> str:
        if ratio >= 3.0: return "非常显著 (Significant)"
        elif ratio >= 2.0: return "显著 (Large)"
        elif ratio >= 1.5: return "一般 (Medium)"
        return "轻微 (Small)"

print("Duration difference handler loaded successfully")

# 全局处理器实例
duration_diff_handler = DurationDiffHandler()

def create_duration_diff_layout() -> html.Div:
    """创建持续时间差异分析布局"""
    table_data = duration_diff_handler.create_table_data()

    return html.Div([
        html.H4([html.I(className="bi bi-clock-history me-2"), "持续时间差异分析"], className="mb-4"),
        
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("差异列表"),
                    dbc.CardBody([
                        dash_table.DataTable(
                            id="duration-diff-table",
                            columns=[
                                {"name": "序号", "id": "index"},
                                {"name": "按键ID", "id": "key_id"},
                                {"name": "录制时长", "id": "record_duration"},
                                {"name": "播放时长", "id": "replay_duration"},
                                {"name": "时长比值", "id": "duration_ratio"},
                                {"name": "差异等级", "id": "diff_level"}
                            ],
                            data=table_data,
                            page_size=10,
                            style_table={"overflowX": "auto"},
                            style_cell={"textAlign": "center", "padding": "10px"},
                            row_selectable="single",
                            selected_rows=[0] if table_data else []
                        )
                    ])
                ], className="shadow-sm")
            ], width=5),
            
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("曲线对比与拆分分析"),
                    dbc.CardBody([
                        html.Div(id="duration-diff-plot-container", children=[
                            html.P("请在左侧表格中选择一行查看曲线详情", className="text-muted text-center py-5")
                        ])
                    ])
                ], className="shadow-sm")
            ], width=7)
        ])
    ])

def register_duration_diff_callbacks(app, session_manager):
    """注册回调"""
    @app.callback(
        Output("duration-diff-plot-container", "children"),
        [Input("duration-diff-table", "selected_rows")],
        [State("session-id", "data")]
    )
    def update_plot(selected_rows, session_id):
        if not selected_rows or not duration_diff_handler.diff_pairs:
            return html.P("未选择数据", className="text-muted text-center py-5")
            
        idx = selected_rows[0]
        if idx >= len(duration_diff_handler.diff_pairs):
            return html.P("无效的选择", className="text-danger")
            
        pair = duration_diff_handler.diff_pairs[idx]
        
        # 使用统一绘图器
        # 我们需要构造一个匹配对格式 (rec_note, rep_note, match_type, error_ms)
        matched_pair = (pair.record_note, pair.replay_note, "DURATION_DIFF", 0.0)
        
        # 由于这里是在独立分析中，我们不知道全局平均延时，暂设为0或尝试计算
        fig = duration_diff_handler.plotter.create_comparison_figure(matched_pair)
        
        return dcc.Graph(figure=fig)

def get_duration_diff_layout(session_manager):
    """获取页面布局并更新数据"""
    try:
        backend = session_manager.get_backend(session_manager.get_current_session_id())
        if backend:
            # 尝试从 active 算法中获取数据
            algs = backend.get_active_algorithms()
            if algs:
                matcher = getattr(algs[0].analyzer, 'note_matcher', None)
                if matcher and hasattr(matcher, 'duration_diff_pairs'):
                    duration_diff_handler.set_diff_pairs(matcher.duration_diff_pairs)
    except Exception as e:
        logger.error(f"更新持续时间差异数据失败: {e}")
        
    return create_duration_diff_layout()
