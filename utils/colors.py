#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
全局颜色常量定义
统一管理所有颜色相关配置
"""

# ==================== 算法颜色方案 ====================

# 标准算法颜色方案 - 用于多算法对比显示
ALGORITHM_COLOR_PALETTE = [
    '#1f77b4',  # 蓝色 - 主要算法颜色
    '#ff7f0e',  # 橙色 - 对比算法颜色
    '#2ca02c',  # 绿色 - 良好性能颜色
    '#d62728',  # 红色 - 警告/错误颜色
    '#9467bd',  # 紫色 - 辅助颜色
    '#8c564b',  # 棕色 - 第三算法颜色
    '#e377c2',  # 粉色 - 第四算法颜色
    '#7f7f7f',  # 灰色 - 默认/备用颜色
]

# 兼容性别名
COLOR_PALETTE = ALGORITHM_COLOR_PALETTE

# ==================== 评级颜色方案 ====================

# 评级颜色映射（十六进制颜色码）- 用于图表
GRADE_HEX_COLORS = {
    'correct': '#2ca02c',   # 绿色 - 优秀 (≤20ms)
    'minor': '#FFD700',     # 金色 - 良好 (20-30ms)
    'moderate': '#FFA500',  # 橙色 - 一般 (30-50ms)
    'large': '#DC143C',     # 深红 - 较差 (50-1000ms)
    'severe': '#8B0000',    # 暗红 - 严重 (>1000ms)
    'major': '#808080',     # 灰色 - 失败 (无匹配)
}

# 评级颜色映射（Bootstrap样式类）- 用于UI组件
GRADE_BOOTSTRAP_COLORS = {
    'correct': 'success',   # 绿色 - 优秀
    'minor': 'warning',     # 黄色 - 良好
    'moderate': 'info',     # 蓝色 - 一般
    'large': 'danger',      # 红色 - 较差
    'severe': 'dark',       # 深色 - 严重
    'major': 'secondary'    # 灰色 - 失败
}

# 兼容性别名（保留旧的命名以兼容现有代码）
QUALITY_COLORS = {
    'excellent': GRADE_HEX_COLORS['correct'],
    'good': GRADE_HEX_COLORS['minor'],
    'fair': GRADE_HEX_COLORS['moderate'],
    'poor': GRADE_HEX_COLORS['large'],
    'severe': GRADE_HEX_COLORS['severe'],
    'failed': GRADE_HEX_COLORS['major'],
}

# 从constants.py迁移的兼容性别名
GRADE_COLORS = GRADE_BOOTSTRAP_COLORS

# ==================== 异常类型颜色方案 ====================

# 异常类型颜色映射（十六进制颜色码）
EXCEPTION_COLORS = {
    'drop_hammer': '#FF6347',    # 番茄红 - 丢锤
    'multi_hammer': '#FF4500',   # 橙红 - 多锤
    'silent': '#708090',         # 暗灰 - 不发声
}
