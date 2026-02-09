#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
全局常量配置文件
统一管理评级标准、阈值、配置等全局常量（不包括颜色定义）
"""

from typing import Dict, Tuple, List

# 导入颜色定义（颜色相关配置统一在 colors.py 中管理）
from .colors import GRADE_BOOTSTRAP_COLORS as GRADE_COLORS

# ==================== 评级配置 (Single Source of Truth) ====================

# 评级阈值定义 (ms)
# 基于 NoteMatcher 的核心对齐标准
GRADE_THRESHOLDS = {
    'excellent': 20.0,
    'good': 30.0,
    'fair': 50.0,
    'poor': 100.0,
    'severe': 200.0
}

# 评级名称映射
GRADE_NAMES: Dict[str, str] = {
    'excellent': '优秀',
    'good': '良好',
    'fair': '一般',
    'poor': '较差',
    'severe': '严重',
    'failed': '失败'
}

# 评级显示配置（用于UI仪表盘、统计和统计卡片）
# 格式: (grade_key, display_label, bootstrap_color_class)
GRADE_DISPLAY_CONFIG: List[Tuple[str, str, str]] = [
    ('excellent', f'优秀 (≤{GRADE_THRESHOLDS["excellent"]}ms)', 'success'),
    ('good', f'良好 ({GRADE_THRESHOLDS["excellent"]}-{GRADE_THRESHOLDS["good"]}ms)', 'warning'),
    ('fair', f'一般 ({GRADE_THRESHOLDS["good"]}-{GRADE_THRESHOLDS["fair"]}ms)', 'info'),
    ('poor', f'较差 ({GRADE_THRESHOLDS["fair"]}-{GRADE_THRESHOLDS["poor"]}ms)', 'danger'),
    ('severe', f'严重 ({GRADE_THRESHOLDS["poor"]}-{GRADE_THRESHOLDS["severe"]}ms)', 'dark')
]

# 核心评级级别列表
GRADE_LEVELS: List[str] = ['excellent', 'good', 'fair', 'poor', 'severe']

# 包含失败匹配的完整级别列表
GRADE_LEVELS_WITH_FAILED: List[str] = GRADE_LEVELS + ['failed']


def get_grade_by_delay(delay_ms: float) -> str:
    """
    根据延时差值获取对应的评级 key
    
    Args:
        delay_ms: 延时值（绝对值或相对值，取绝对值进行比较）
        
    Returns:
        str: 对应的等级 key (excellent, good, fair, poor, severe, failed)
    """
    abs_delay = abs(delay_ms)
    if abs_delay <= GRADE_THRESHOLDS['excellent']:
        return 'excellent'
    elif abs_delay <= GRADE_THRESHOLDS['good']:
        return 'good'
    elif abs_delay <= GRADE_THRESHOLDS['fair']:
        return 'fair'
    elif abs_delay <= GRADE_THRESHOLDS['poor']:
        return 'poor'
    elif abs_delay <= GRADE_THRESHOLDS['severe']:
        return 'severe'
    else:
        return 'failed'


# ==================== 兼容性别名 (已弃用，请逐步迁移) ====================

GRADE_CONFIGS = GRADE_DISPLAY_CONFIG # 用于 ui/components/grade_statistics.py 等

# ==================== 其他全局常量 ====================

# 时间相关常量
TIME_UNIT_0_1MS_TO_MS = 10.0  # 0.1ms 转换为 ms 的倍数


DEFAULT_MAX_DELAY_THRESHOLD_MS = 200  # 默认最大延时阈值（毫秒）

# UI相关常量
MAX_DISPLAY_ROWS = 1000  # 表格最大显示行数
DEFAULT_PAGE_SIZE = 50   # 默认分页大小

# 文件相关常量
ALLOWED_FILE_EXTENSIONS = ['.spmid']  # 允许上传的文件扩展名
MAX_FILE_SIZE_MB = 100  # 最大文件大小（MB）

# 算法相关常量
DEFAULT_ALGORITHM_NAME = 'SPMID分析'  # 默认算法名称
MAX_ALGORITHMS = 10  # 最多支持的算法数量
