#!/usr/bin/env python3
from backend.force_curve_analyzer import ForceCurveAnalyzer
import numpy as np

# 创建模拟不同算法的音符对象
class MockNote:
    def __init__(self, data_length, algorithm_name):
        self.offset = 100
        self.algorithm_name = algorithm_name
        class MockSeries:
            def __init__(self, length):
                self.index = np.arange(length)
                self.values = np.random.rand(length) * 100
            @property
            def empty(self):
                return False
        self.after_touch = MockSeries(data_length)

if __name__ == "__main__":
    analyzer = ForceCurveAnalyzer()
    note1 = MockNote(1000, 'algorithm_A')
    note2 = MockNote(1200, 'algorithm_B')

    print('测试不同算法的曲线对比...')
    result = analyzer.compare_curves(note1, note2)
    if result:
        print('✅ 不同算法曲线对比成功')
        print(f'整体相似度: {result["overall_similarity"]:.3f}')
    else:
        print('❌ 曲线对比失败')
