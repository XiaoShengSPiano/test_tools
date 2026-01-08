#!/usr/bin/env python3
# -*- coding: utf-8 -*-

print('开始检查数据获取逻辑')

# 模拟数据获取
class MockBackend:
    pass

class MockAlgorithm:
    def __init__(self):
        self.analyzer = MockAnalyzer()

class MockAnalyzer:
    def __init__(self):
        self.note_matcher = MockNoteMatcher()

class MockNoteMatcher:
    def __init__(self):
        # 创建模拟数据
        self.duration_diff_pairs = [
            (1, 2, type('Note', (), {'id': 60})(), type('Note', (), {'id': 60})(), 100.0, 250.0, 2.5),
        ]

backend = MockBackend()
algorithms = [MockAlgorithm()]

# 尝试获取数据
try:
    from ui.layout_components import _get_duration_diff_data
    result = _get_duration_diff_data(backend, algorithms)
    print(f'获取到数据: {len(result)} 条')
    for item in result:
        print(f'  {item}')
except Exception as e:
    print(f'错误: {e}')



