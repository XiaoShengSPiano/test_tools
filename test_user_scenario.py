#!/usr/bin/env python3
"""
测试用户场景：上传两个不同算法处理的文件
"""

from backend.force_curve_analyzer import ForceCurveAnalyzer
import numpy as np

class MockNote:
    def __init__(self, data_length, key_id, algorithm_name, note_type):
        self.offset = 100
        self.id = key_id  # 按键ID
        self.algorithm_name = algorithm_name
        self.note_type = note_type  # 'record' or 'replay'

        # 为不同算法生成不同的数据模式
        np.random.seed(hash(algorithm_name + str(key_id)) % 2**32)
        if algorithm_name == 'algorithm_A':
            # 算法A的数据模式
            base_value = 50 + np.sin(np.linspace(0, 4*np.pi, data_length)) * 20
        else:
            # 算法B的数据模式（略有不同）
            base_value = 45 + np.sin(np.linspace(0, 4*np.pi, data_length)) * 25

        class MockSeries:
            def __init__(self, values):
                self.index = np.arange(len(values))
                self.values = values
            @property
            def empty(self):
                return False

        # 添加一些噪声
        noise = np.random.normal(0, 2, data_length)
        self.after_touch = MockSeries(base_value + noise)

def simulate_user_scenario():
    """
    模拟用户场景：
    - 上传了同一个曲子的两个不同算法处理结果
    - 每个算法都有自己的录制-播放配对
    """
    analyzer = ForceCurveAnalyzer()

    print("=== 模拟用户场景：两个不同算法的曲子 ===")
    print()

    # 模拟算法A的处理结果
    print("算法A处理结果：")
    record_note_A = MockNote(1000, key_id=60, algorithm_name='algorithm_A', note_type='record')
    replay_note_A = MockNote(950, key_id=60, algorithm_name='algorithm_A', note_type='replay')

    result_A = analyzer.compare_curves(record_note_A, replay_note_A, record_note_A, replay_note_A)
    if result_A:
        print(f"✅ 算法A曲线对比成功，相似度: {result_A['overall_similarity']:.3f}")
    else:
        print("❌ 算法A曲线对比失败")

    # 模拟算法B的处理结果
    print("算法B处理结果：")
    record_note_B = MockNote(1100, key_id=60, algorithm_name='algorithm_B', note_type='record')
    replay_note_B = MockNote(1050, key_id=60, algorithm_name='algorithm_B', note_type='replay')

    result_B = analyzer.compare_curves(record_note_B, replay_note_B, record_note_B, replay_note_B)
    if result_B:
        print(f"✅ 算法B曲线对比成功，相似度: {result_B['overall_similarity']:.3f}")
    else:
        print("❌ 算法B曲线对比失败")

    print()
    print("=== 分析结果 ===")

    if result_A and result_B:
        similarity_A = result_A['overall_similarity']
        similarity_B = result_B['overall_similarity']

        print(f"算法A相似度: {similarity_A:.3f}")
        print(f"算法B相似度: {similarity_B:.3f}")
        if abs(similarity_A - similarity_B) > 0.1:
            print("🔍 发现差异：两个算法对同一个曲子的处理结果不同")
        else:
            print("🔍 两个算法对同一个曲子的处理结果相似")

        # 模拟用户点击时的行为
        print()
        print("=== 模拟用户点击行为 ===")
        print("当用户点击算法A的瀑布图时，会看到算法A内部的曲线对比")
        print("当用户点击算法B的瀑布图时，会看到算法B内部的曲线对比")
        print("这是当前的正确行为，因为每个算法独立处理数据")

    print()
    print("=== 潜在问题分析 ===")
    print("如果用户期望跨算法比较同一个原始音符的处理结果，")
    print("可能需要额外的UI功能来支持这种比较模式。")

if __name__ == "__main__":
    simulate_user_scenario()
