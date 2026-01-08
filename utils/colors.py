#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
全局颜色常量定义
"""

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

# 其他颜色方案
# 质量等级颜色映射
QUALITY_COLORS = {
    'excellent': '#2ca02c',  # 绿色 - 优秀匹配
    'good': '#90EE90',      # 浅绿 - 良好匹配
    'fair': '#FFD700',      # 金色 - 一般匹配
    'poor': '#FFA500',      # 橙色 - 较差匹配
    'severe': '#DC143C',    # 深红 - 严重匹配
    'failed': '#808080',    # 灰色 - 失败匹配
}

# 异常类型颜色映射
EXCEPTION_COLORS = {
    'drop_hammer': '#FF6347',    # 番茄红 - 丢锤
    'multi_hammer': '#FF4500',   # 橙红 - 多锤
    'silent': '#708090',         # 暗灰 - 不发声
}
