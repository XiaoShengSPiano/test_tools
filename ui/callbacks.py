"""
回调函数模块 - 处理Dash应用的所有回调逻辑
包含文件上传、历史记录表格交互等回调函数
"""
import json
import time
import traceback
import uuid
import math

from typing import Dict, Optional, Union, TypedDict, Tuple, List, Any
from collections import defaultdict

import pandas as pd
import numpy as np

# SPMID导入
from spmid.spmid_analyzer import SPMIDAnalyzer
import spmid



from dash import html, no_update
from dash._callback import NoUpdate
            
import dash
import dash.dependencies
import dash.dcc as dcc
import dash_bootstrap_components as dbc
from dash import Input, Output, State, ALL, callback_context, dcc, dash_table
from dash._callback_context import CallbackContext
from datetime import datetime

import plotly.graph_objects as go
from plotly.graph_objects import Figure
from plotly.subplots import make_subplots

from ui.layout_components import empty_figure, create_multi_algorithm_upload_area, create_multi_algorithm_management_area
from backend.session_manager import SessionManager
from utils.ui_helpers import create_empty_figure
from ui.grade_detail_callbacks import register_all_callbacks
from utils.logger import Logger
# 后端类型导入
from backend.piano_analysis_backend import PianoAnalysisBackend


logger = Logger.get_logger()

# 自定义类型定义

class AlgorithmMetadata:
    """算法元数据的类型定义"""
    algorithm_name: str
    display_name: str
    filename: str

def register_callbacks(app, session_manager: SessionManager, history_manager):
    """
    注册所有回调函数
    
    注意：多页面重构后，只注册核心回调：
    - 会话管理
    - 文件上传
    - 算法管理
    
    散点图等详细分析回调将在各自页面中实现
    """

    # 导入回调模块
    from ui.session_callbacks import register_session_callbacks
    from ui.file_upload_callbacks import register_file_upload_callbacks
    from ui.algorithm_callbacks import register_algorithm_callbacks
    from ui.track_comparison_callbacks import register_callbacks as register_track_comparison_callbacks
    # from ui.scatter_callbacks import register_scatter_callbacks  # 暂时禁用，将在散点图页面重新实现

    # 注册会话和初始化管理回调
    register_session_callbacks(app, session_manager, history_manager)
    
    # 注册音轨对比回调
    register_track_comparison_callbacks(app, session_manager)

    # 注册文件上传回调
    register_file_upload_callbacks(app, session_manager)

    # 注册算法管理回调
    register_algorithm_callbacks(app, session_manager)

    # 注册评级详情核心回调 (包含按键筛选、对比模态框、跳转跳转等)
    register_all_callbacks(app, session_manager)


