#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
全局常量配置文件
统一管理评级标准、阈值、配置等全局常量
"""

from typing import Dict, Tuple, List

# ==================== 评级配置 ====================

# 评级范围配置（用于后端逻辑和数据处理）
# 基于误差范围进行评级，与评级统计和表格筛选保持一致
GRADE_RANGE_CONFIG: Dict[str, Tuple[float, float]] = {
    'correct': (float('-inf'), 20),        # 优秀: 误差 ≤ 20ms
    'minor': (20, 30),                     # 良好: 20ms < 误差 ≤ 30ms
    'moderate': (30, 50),                  # 一般: 30ms < 误差 ≤ 50ms
    'large': (50, 1000),                   # 较差: 50ms < 误差 ≤ 1000ms
    'severe': (1000, float('inf')),        # 严重: 误差 > 1000ms
    'major': (float('inf'), float('inf'))  # 失败: 无匹配 (特殊处理)
}

# 评级显示配置（用于UI展示）
# 格式: (grade_key, display_name, bootstrap_color_class)
GRADE_DISPLAY_CONFIG: List[Tuple[str, str, str]] = [
    ('correct', '优秀 (≤20ms)', 'success'),
    ('minor', '良好 (20-30ms)', 'warning'),
    ('moderate', '一般 (30-50ms)', 'info'),
    ('large', '较差 (50-100ms)', 'danger'),
    ('severe', '严重 (100-200ms)', 'dark')
    # 注意：不再显示失败匹配，因为匹配质量评级只统计成功匹配
]

# 评级名称映射
GRADE_NAMES: Dict[str, str] = {
    'correct': '优秀',
    'minor': '良好',
    'moderate': '一般',
    'large': '较差',
    'severe': '严重',
    'major': '失败'
}

# 评级颜色映射（Bootstrap样式类）
GRADE_COLORS: Dict[str, str] = {
    'correct': 'success',   # 绿色
    'minor': 'warning',     # 黄色
    'moderate': 'info',     # 蓝色
    'large': 'danger',      # 红色
    'severe': 'dark',       # 深色
    'major': 'secondary'    # 灰色
}

# 所有评级级别（按顺序）
GRADE_LEVELS: List[str] = ['correct', 'minor', 'moderate', 'large', 'severe']

# 包含失败匹配的完整评级级别
GRADE_LEVELS_WITH_FAILED: List[str] = ['correct', 'minor', 'moderate', 'large', 'severe', 'major']


# ==================== 兼容性别名 ====================

# 为了兼容旧代码，提供别名
GRADE_CONFIGS = GRADE_DISPLAY_CONFIG  # layout_components.py 中使用的名称


# ==================== 其他全局常量 ====================

# 时间相关常量
TIME_UNIT_0_1MS_TO_MS = 10.0  # 0.1ms 转换为 ms 的倍数

# 默认值
DEFAULT_MIN_DURATION_MS = 10  # 最小音符持续时间（毫秒）
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
