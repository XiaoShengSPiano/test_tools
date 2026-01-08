#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
sys.path.insert(0, '.')

# 检查文件内容
with open('ui/layout_components.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 检查函数定义是否存在
has_get_data = 'def _get_duration_diff_data' in content
has_create_table = 'def _create_duration_diff_table_row' in content

print(f'_get_duration_diff_data 函数定义存在: {has_get_data}')
print(f'_create_duration_diff_table_row 函数定义存在: {has_create_table}')

# 检查函数调用是否存在
has_call = '_create_duration_diff_table_row(backend, active_algorithms)' in content
print(f'函数调用存在: {has_call}')

# 尝试导入
try:
    from ui.layout_components import _get_duration_diff_data, _create_duration_diff_table_row
    print('导入成功')
except ImportError as e:
    print(f'导入失败: {e}')



