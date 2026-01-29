"""
数据概览组件
用于显示数据源信息、音符统计等概览信息
"""
from dash import html
import dash_bootstrap_components as dbc
from utils.logger import Logger

logger = Logger.get_logger()


def create_data_overview_card(stats_data, algorithm_name=None):
    """
    创建数据概览卡片
    
    Args:
        stats_data: 统计数据字典，包含以下字段：
            - valid_record_notes: 录制有效音符数
            - valid_replay_notes: 播放有效音符数
            - matched_pairs: 匹配对数
            - invalid_record_notes: 录制无效音符数
            - invalid_replay_notes: 播放无效音符数
        algorithm_name: 算法名称（可选，用于标题显示）
        
    Returns:
        dbc.Card: 数据概览卡片
    """
    if not stats_data:
        return html.Div()

    # 从统计数据中获取各项指标
    record_valid = stats_data.get('valid_record_notes', 0)
    replay_valid = stats_data.get('valid_replay_notes', 0)
    matched_pairs = stats_data.get('matched_pairs', 0)
    record_invalid = stats_data.get('invalid_record_notes', 0)
    replay_invalid = stats_data.get('invalid_replay_notes', 0)
    
    # 计算音符总数 = 有效音符 + 无效音符
    total_notes = record_valid + replay_valid + record_invalid + replay_invalid
    
    title = "数据概览" if not algorithm_name else f"数据概览 - {algorithm_name}"
    
    card = dbc.Card([
        dbc.CardHeader([
            html.H4([
                html.I(className="fas fa-info-circle me-2", style={'color': '#17a2b8'}),
                title
            ], className="mb-0")
        ]),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    _create_stat_item("音符总数", total_notes, "dark")
                ], width=3),
                dbc.Col([
                    _create_stat_item("录制有效音符", record_valid, "primary")
                ], width=3),
                dbc.Col([
                    _create_stat_item("播放有效音符", replay_valid, "info")
                ], width=3),
                dbc.Col([
                    _create_stat_item("匹配对数", matched_pairs, "success")
                ], width=3),
            ])
        ])
    ], className="shadow-sm mb-4")
    return card


def _create_stat_item(label, value, color="primary"):
    """
    创建单个统计项
    
    Args:
        label: 标签文本
        value: 数值
        color: Bootstrap颜色类
        
    Returns:
        html.Div: 统计项组件
    """
    color_map = {
        'primary': '#007bff',
        'success': '#28a745',
        'info': '#17a2b8',
        'warning': '#ffc107',
        'danger': '#dc3545',
        'dark': '#343a40',
    }
    
    return html.Div([
        html.H3(str(value), className=f"text-{color} mb-1"),
        html.P(label, className="text-muted mb-0")
    ], className="text-center")
