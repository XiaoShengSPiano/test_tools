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

logger = Logger.get_logger()

@dataclass
class DurationDiffPair:
    """持续时间差异对数据
    
    简化设计：只存储索引、Note对象和比值
    其他数据（duration、keyon、keyoff）直接从Note对象获取
    """
    record_idx: int
    replay_idx: int
    record_note: Note
    replay_note: Note
    duration_ratio: float
    
    @property
    def record_duration(self) -> float:
        """录制持续时间(ms)"""
        return self.record_note.duration_ms if self.record_note and self.record_note.duration_ms is not None else 0.0
    
    @property
    def replay_duration(self) -> float:
        """播放持续时间(ms)"""
        return self.replay_note.duration_ms if self.replay_note and self.replay_note.duration_ms is not None else 0.0
    
    @property
    def record_keyon(self) -> Optional[float]:
        """录制key-on时间(ms)"""
        return self.record_note.key_on_ms if self.record_note else None
    
    @property
    def record_keyoff(self) -> Optional[float]:
        """录制key-off时间(ms)"""
        return self.record_note.key_off_ms if self.record_note else None
    
    @property
    def replay_keyon(self) -> Optional[float]:
        """播放key-on时间(ms)"""
        return self.replay_note.key_on_ms if self.replay_note else None
    
    @property
    def replay_keyoff(self) -> Optional[float]:
        """播放key-off时间(ms)"""
        return self.replay_note.key_off_ms if self.replay_note else None

class DurationDiffHandler:
    """Duration difference display handler"""

    def __init__(self):
        self.diff_pairs: List[DurationDiffPair] = []

    def set_diff_pairs(self, diff_pairs_data: List[Tuple]) -> None:
        """设置持续时间差异对数据
        
        Args:
            diff_pairs_data: 元组列表，每个元组包含11个元素：
                (record_idx, replay_idx, record_note, replay_note,
                 record_duration, replay_duration, duration_ratio,
                 record_keyon, record_keyoff, replay_keyon, replay_keyoff)
        """
        self.diff_pairs = []
        for data in diff_pairs_data:
            if len(data) >= 11:
                # 只提取必要的数据：索引、Note对象、比值
                # duration、keyon、keyoff 等信息直接从 Note 对象获取
                record_idx = data[0]
                replay_idx = data[1]
                record_note = data[2]
                replay_note = data[3]
                duration_ratio = data[6]
                
                self.diff_pairs.append(DurationDiffPair(
                    record_idx=record_idx,
                    replay_idx=replay_idx,
                    record_note=record_note,
                    replay_note=replay_note,
                    duration_ratio=duration_ratio
                ))
            else:
                logger.warning(f"跳过无效的持续时间差异数据: 长度={len(data)}, 期望=11")

    def create_table_data(self) -> List[Dict]:
        """创建表格显示数据
        
        所有数据从 Note 对象的属性自动获取，无需额外存储
        """
        table_data = []
        for i, pair in enumerate(self.diff_pairs):
            table_data.append({
                "index": i + 1,
                "key_id": pair.record_note.id if pair.record_note else "N/A",
                "record_idx": pair.record_idx,
                "replay_idx": pair.replay_idx,
                "record_duration": pair.record_duration,  # 从property获取
                "replay_duration": pair.replay_duration,  # 从property获取
                "duration_ratio": pair.duration_ratio,
                "record_keyon": pair.record_keyon,  # 从property获取
                "record_keyoff": pair.record_keyoff,  # 从property获取
                "replay_keyon": pair.replay_keyon,  # 从property获取
                "replay_keyoff": pair.replay_keyoff,  # 从property获取
                "diff_level": self._get_diff_level(pair.duration_ratio)
            })
        return table_data

    def _get_diff_level(self, ratio: float) -> str:
        """Get difference level description"""
        if ratio >= 3.0:
            return "significant"
        elif ratio >= 2.5:
            return "large"
        elif ratio >= 2.0:
            return "medium"
        else:
            return "small"

print("Duration difference handler loaded successfully")

# Global handler instance
duration_diff_handler = DurationDiffHandler()

def create_duration_diff_layout(handler: DurationDiffHandler) -> html.Div:
    """Create duration difference display layout"""
    table_data = handler.create_table_data()

    layout = html.Div([
        html.H3("Duration Difference Analysis"),
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Difference Pairs List"),
                    dbc.CardBody([
                        html.P("Found {} difference pairs (ratio >= 2.0)".format(len(handler.diff_pairs))),
                        dash_table.DataTable(
                            id="duration-diff-table",
                            columns=[
                                {"name": "Index", "id": "index"},
                                {"name": "Key ID", "id": "key_id"},
                                {"name": "Record Idx", "id": "record_idx"},
                                {"name": "Replay Idx", "id": "replay_idx"},
                                {"name": "Record Duration(ms)", "id": "record_duration"},
                                {"name": "Replay Duration(ms)", "id": "replay_duration"},
                                {"name": "Duration Ratio", "id": "duration_ratio"},
                                {"name": "Record KeyOn(ms)", "id": "record_keyon"},
                                {"name": "Record KeyOff(ms)", "id": "record_keyoff"},
                                {"name": "Replay KeyOn(ms)", "id": "replay_keyon"},
                                {"name": "Replay KeyOff(ms)", "id": "replay_keyoff"},
                                {"name": "Diff Level", "id": "diff_level"}
                            ],
                            data=table_data,
                            page_size=15,
                            style_table={"overflowX": "auto"},
                            style_cell={
                                "textAlign": "center",
                                "padding": "8px",
                                "minWidth": "80px",
                                "maxWidth": "150px"
                            },
                            style_header={
                                "backgroundColor": "rgb(230, 230, 230)",
                                "fontWeight": "bold"
                            },
                            style_data_conditional=[
                                {
                                    "if": {"column_id": "diff_level", "filter_query": "{diff_level} = 'significant'"},
                                    "backgroundColor": "rgb(255, 200, 200)",
                                    "color": "red",
                                    "fontWeight": "bold"
                                },
                                {
                                    "if": {"column_id": "diff_level", "filter_query": "{diff_level} = 'large'"},
                                    "backgroundColor": "rgb(255, 220, 200)",
                                    "color": "orange",
                                    "fontWeight": "bold"
                                }
                            ],
                            sort_action="native",
                            sort_by=[{"column_id": "record_keyon", "direction": "asc"}],
                            filter_action="native",
                            row_selectable="single",
                            selected_rows=[],
                            tooltip_header={
                                "index": "Pair index",
                                "key_id": "Piano key ID",
                                "record_idx": "Index in record data",
                                "replay_idx": "Index in replay data",
                                "record_duration": "Record note duration",
                                "replay_duration": "Replay note duration",
                                "duration_ratio": "Replay/Record duration ratio",
                                "record_keyon": "Record note key-on time",
                                "record_keyoff": "Record note key-off time",
                                "replay_keyon": "Replay note key-on time",
                                "replay_keyoff": "Replay note key-off time",
                                "diff_level": "Difference level category"
                            }
                        )
                    ])
                ])
            ], width=12)
        ]),
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Selected Pair Details"),
                    dbc.CardBody([
                        html.Div(id="selected-pair-details", children=[
                            html.P("Click a table row to view details", className="text-muted")
                        ])
                    ])
                ])
            ], width=12)
        ], className="mt-4")
    ])

    return layout

def register_duration_diff_callbacks(app, session_manager):
    """Register duration difference callbacks"""
    @app.callback(
        Output("selected-pair-details", "children"),
        [Input("duration-diff-table", "selected_rows"),
         Input("duration-diff-table", "data")]
    )
    def update_selected_pair_details(selected_rows, table_data):
        """Update selected pair details"""
        if not selected_rows or not table_data:
            return html.P("Click a table row to view details", className="text-muted")

        selected_index = selected_rows[0]
        if selected_index >= len(duration_diff_handler.diff_pairs):
            return html.P("Invalid selection", className="text-danger")

        pair = duration_diff_handler.diff_pairs[selected_index]

        details = html.Div([
            html.H5("Pair #{} Details".format(selected_index + 1), className="mb-3"),
            dbc.Row([
                dbc.Col([
                    html.H6("Record Info", className="text-primary"),
                    html.Table([
                        html.Tr([html.Td("Index:"), html.Td(str(pair.record_idx))]),
                        html.Tr([html.Td("Key ID:"), html.Td(str(pair.record_note.id if pair.record_note else "N/A"))]),
                        html.Tr([html.Td("Duration:"), html.Td("{:.1f} ms".format(pair.record_duration))]),
                        html.Tr([html.Td("KeyOn:"), html.Td("{:.1f} ms".format(pair.record_keyon) if pair.record_keyon is not None else "N/A")]),
                        html.Tr([html.Td("KeyOff:"), html.Td("{:.1f} ms".format(pair.record_keyoff) if pair.record_keyoff is not None else "N/A")])
                    ], className="table table-sm table-bordered")
                ], width=6),
                dbc.Col([
                    html.H6("Replay Info", className="text-success"),
                    html.Table([
                        html.Tr([html.Td("Index:"), html.Td(str(pair.replay_idx))]),
                        html.Tr([html.Td("Key ID:"), html.Td(str(pair.replay_note.id if pair.replay_note else "N/A"))]),
                        html.Tr([html.Td("Duration:"), html.Td("{:.1f} ms".format(pair.replay_duration))]),
                        html.Tr([html.Td("KeyOn:"), html.Td("{:.1f} ms".format(pair.replay_keyon) if pair.replay_keyon is not None else "N/A")]),
                        html.Tr([html.Td("KeyOff:"), html.Td("{:.1f} ms".format(pair.replay_keyoff) if pair.replay_keyoff is not None else "N/A")])
                    ], className="table table-sm table-bordered")
                ], width=6)
            ]),
            html.Hr(),
            dbc.Row([
                dbc.Col([
                    html.H6("Difference Analysis", className="text-warning"),
                    html.Table([
                        html.Tr([html.Td("Duration Ratio:"), html.Td("{:.2f}".format(pair.duration_ratio))]),
                        html.Tr([html.Td("Diff Level:"), html.Td(duration_diff_handler._get_diff_level(pair.duration_ratio))]),
                        html.Tr([html.Td("Time Difference:"), html.Td("{:.1f} ms".format(abs(pair.replay_duration - pair.record_duration)))])
                    ], className="table table-sm table-bordered")
                ], width=12)
            ])
        ])

        return details

def get_duration_diff_layout(session_manager):
    """Get duration difference layout"""
    update_duration_diff_data(session_manager)
    return create_duration_diff_layout(duration_diff_handler)

def update_duration_diff_data(session_manager):
    """Update duration difference data"""
    try:
        backend = session_manager.get_current_backend()
        if backend and hasattr(backend, "multi_algorithm_manager"):
            for algorithm in backend.multi_algorithm_manager.get_active_algorithms():
                if hasattr(algorithm.analyzer, "note_matcher") and hasattr(algorithm.analyzer.note_matcher, "duration_diff_pairs"):
                    diff_pairs = algorithm.analyzer.note_matcher.duration_diff_pairs
                    if diff_pairs:
                        duration_diff_handler.set_diff_pairs(diff_pairs)
                        logger.info("Updated duration difference data: {} pairs".format(len(diff_pairs)))
                        break
        elif backend and hasattr(backend, "_get_current_analyzer"):
            analyzer = backend._get_current_analyzer()
            if analyzer and hasattr(analyzer, "note_matcher") and hasattr(analyzer.note_matcher, "duration_diff_pairs"):
                diff_pairs = analyzer.note_matcher.duration_diff_pairs
                duration_diff_handler.set_diff_pairs(diff_pairs)
                logger.info("Updated duration difference data: {} pairs".format(len(diff_pairs)))
    except Exception as e:
        logger.error("Failed to update duration difference data: {}".format(e))
