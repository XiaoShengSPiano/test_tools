#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
系统延时自动探测与分析工具

该脚本用于分析SPMID数据中录制与回放的时间偏移分布，
以探测可能存在的固定系统延时（System Latency）。

核心原理：
基于统计学方法（互相关思想），计算所有同KeyID音符对的时间差分布。
即便数据量不一致（存在多录/漏录），系统延时也会表现为直方图上的显著峰值。
"""

import os
import sys
import argparse
import numpy as np
import matplotlib.pyplot as plt
from typing import List, Dict, Tuple
import statistics

# 添加项目根目录到Python路径，以便导入项目模块
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

try:
    from spmid.spmid_reader import SPMidReader, Note
except ImportError:
    print("❌ 无法导入项目模块，请确保脚本在tools目录下运行，且项目结构完整。")
    sys.exit(1)

def load_data(file_path: str) -> Tuple[List[Note], List[Note]]:
    """加载SPMID数据"""
    print(f"📂 正在加载文件: {file_path}")
    try:
        with SPMidReader(file_path) as reader:
            record_data = reader.get_track(0)
            replay_data = reader.get_track(1)
            
            if not record_data or not replay_data:
                print("❌ 数据加载失败：录制或回放数据为空")
                sys.exit(1)
                
            print(f"✅ 数据加载成功")
            print(f"   - 录制音符数: {len(record_data)}")
            print(f"   - 回放音符数: {len(replay_data)}")
            return record_data, replay_data
    except Exception as e:
        print(f"❌ 文件读取错误: {e}")
        sys.exit(1)

def get_note_time(note: Note) -> float:
    """获取音符的绝对开始时间 (ms)"""
    # spmid内部时间单位通常为0.1ms，这里转换为ms
    try:
        return (note.after_touch.index[0] + note.offset) / 10.0
    except (IndexError, AttributeError) as e:
        raise ValueError(f"音符ID {note.id} 的after_touch数据无效: {e}") from e

def calculate_time_differences(record_data: List[Note], replay_data: List[Note], max_diff_ms: float = 2000.0) -> List[float]:
    """
    计算所有同KeyID音符对的时间差
    
    Args:
        record_data: 录制数据
        replay_data: 回放数据
        max_diff_ms: 最大统计范围（毫秒），超过此范围的差异被忽略
        
    Returns:
        List[float]: 时间差列表 (ms)
    """
    print("🔄 正在计算时间差分布...")
    differences = []
    
    # 建立回放数据的索引：key_id -> list of notes
    replay_map = {}
    for note in replay_data:
        if note.id not in replay_map:
            replay_map[note.id] = []
        replay_map[note.id].append(note)
    
    # 遍历录制数据
    match_count = 0
    total_pairs = 0
    
    for r_note in record_data:
        if r_note.id in replay_map:
            r_time = get_note_time(r_note)
            
            # 与所有同名回放音符计算差异
            for p_note in replay_map[r_note.id]:
                p_time = get_note_time(p_note)
                diff = p_time - r_time
                
                # 只记录在合理范围内的差异，减少噪音
                if abs(diff) <= max_diff_ms:
                    differences.append(diff)
                    total_pairs += 1
            match_count += 1
            
    print(f"✅ 计算完成：处理了 {match_count} 个录制音符，生成了 {total_pairs} 个潜在时间差样本")
    return differences

def analyze_latency(differences: List[float], bin_size_ms: float = 1.0) -> Dict:
    """
    分析时间差分布，寻找系统延时
    
    Args:
        differences: 时间差列表
        bin_size_ms: 直方图桶大小 (ms)
        
    Returns:
        Dict: 分析结果
    """
    if not differences:
        return {'peak_latency': 0.0, 'confidence': 0.0}
    
    print("📊 正在分析分布特征...")
    
    # 1. 计算直方图
    bins = np.arange(min(differences), max(differences) + bin_size_ms, bin_size_ms)
    hist, bin_edges = np.histogram(differences, bins=bins)
    
    # 2. 找到峰值
    peak_idx = np.argmax(hist)
    peak_latency = (bin_edges[peak_idx] + bin_edges[peak_idx+1]) / 2
    peak_count = hist[peak_idx]
    
    # 3. 计算峰值附近的统计量 (FWHM范围或简单窗口)
    # 取峰值附近 +/- 10ms 的数据进行更精确的统计
    near_peak_data = [d for d in differences if abs(d - peak_latency) < 10.0]
    
    if near_peak_data:
        refined_mean = statistics.mean(near_peak_data)
        refined_median = statistics.median(near_peak_data)
        refined_std = statistics.stdev(near_peak_data) if len(near_peak_data) > 1 else 0.0
    else:
        refined_mean = peak_latency
        refined_median = peak_latency
        refined_std = 0.0
        
    # 4. 计算置信度 (峰值占比)
    total_samples = len(differences)
    # 计算信噪比：峰值高度 / 平均高度
    avg_height = np.mean(hist)
    snr = peak_count / avg_height if avg_height > 0 else 0
    
    return {
        'peak_latency': peak_latency,           # 直方图峰值（众数估计）
        'refined_mean': refined_mean,           # 峰值附近的均值
        'refined_median': refined_median,       # 峰值附近的中位数
        'std_dev': refined_std,                 # 峰值附近的离散度
        'peak_count': peak_count,               # 峰值样本数
        'total_samples': total_samples,         # 总样本数
        'snr': snr                              # 信噪比
    }

def plot_distribution(differences: List[float], result: Dict, output_path: str):
    """绘制分布直方图"""
    print(f"🎨 正在生成图表: {output_path}")
    
    plt.figure(figsize=(12, 6))
    
    # 绘制主直方图
    plt.hist(differences, bins=200, color='skyblue', edgecolor='black', alpha=0.7, label='Time Differences')
    
    # 标记检测到的延时
    latency = result['refined_median']
    plt.axvline(x=latency, color='red', linestyle='--', linewidth=2, label=f'Detected Latency: {latency:.2f} ms')
    
    # 添加文本信息
    info_text = (
        f"Detected Latency: {latency:.2f} ms\n"
        f"Peak SNR: {result['snr']:.1f}\n"
        f"Jitter (StdDev): {result['std_dev']:.2f} ms"
    )
    plt.text(0.02, 0.95, info_text, transform=plt.gca().transAxes, 
             verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    
    plt.title('System Latency Detection (Record vs Replay Time Differences)')
    plt.xlabel('Time Difference (Replay - Record) [ms]')
    plt.ylabel('Count')
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    # 如果范围太大，聚焦到峰值附近
    peak = result['peak_latency']
    plt.xlim(peak - 100, peak + 100)
    
    try:
        plt.savefig(output_path, dpi=100)
        print(f"✅ 图表已保存")
    except Exception as e:
        print(f"❌ 图表保存失败: {e}")
    finally:
        plt.close()

def find_spmid_files(directory: str) -> List[str]:
    """递归查找目录下的 .spmid 文件"""
    spmid_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.spmid'):
                spmid_files.append(os.path.join(root, file))
    return spmid_files

def main():
    parser = argparse.ArgumentParser(description='SPMID系统延时分析工具')
    parser.add_argument('file', nargs='?', help='SPMID文件路径')
    parser.add_argument('--dir', default='history', help='搜索目录 (默认: history)')
    parser.add_argument('--output', default='latency_analysis.png', help='输出图表文件名')
    
    args = parser.parse_args()
    
    target_file = args.file
    
    # 如果未指定文件，自动查找
    if not target_file:
        print(f"🔍 未指定文件，正在 '{args.dir}' 目录下搜索 .spmid 文件...")
        search_dir = os.path.join(project_root, args.dir)
        if not os.path.exists(search_dir):
            search_dir = project_root # 如果找不到history目录，搜根目录
            
        found_files = find_spmid_files(search_dir)
        
        if not found_files:
            print("❌ 未找到任何 .spmid 文件")
            sys.exit(1)
            
        # 按修改时间排序，取最新的
        found_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        target_file = found_files[0]
        print(f"👉 自动选择最新的文件: {os.path.basename(target_file)}")
    
    if not os.path.exists(target_file):
        print(f"❌ 文件不存在: {target_file}")
        sys.exit(1)
        
    # 1. 加载数据
    record_data, replay_data = load_data(target_file)
    
    # 2. 计算时间差
    differences = calculate_time_differences(record_data, replay_data)
    
    if not differences:
        print("❌ 未能生成有效的时间差数据（可能是没有相同的KeyID）")
        sys.exit(1)
        
    # 3. 分析
    result = analyze_latency(differences)
    
    # 4. 输出报告
    print("\n" + "="*50)
    print("              系统延时分析报告")
    print("="*50)
    print(f"文件: {os.path.basename(target_file)}")
    print("-" * 30)
    print(f"检测到的系统延时: {result['refined_median']:.2f} ms")
    print("-" * 30)
    print(f"统计详情:")
    print(f"  - 峰值位置 (Mode): {result['peak_latency']:.2f} ms")
    print(f"  - 精确均值 (Mean): {result['refined_mean']:.2f} ms")
    print(f"  - 抖动/标准差 (Std): {result['std_dev']:.2f} ms")
    print(f"  - 信号强度 (SNR):   {result['snr']:.1f}")
    print(f"  - 有效样本数:       {result['total_samples']}")
    print("\n结论:")
    if result['snr'] > 5:
        print(f"✅ 检测到显著的固定延时。建议在算法中补偿 {result['refined_median']:.2f} ms。")
    elif result['snr'] > 2:
        print(f"⚠️ 检测到弱延时信号，可能存在较大的抖动或不稳定的延时。")
    else:
        print(f"❌ 未检测到明显的固定延时，数据可能已对齐或完全不相关。")
    print("="*50 + "\n")
    
    # 5. 绘图
    plot_distribution(differences, result, args.output)

if __name__ == '__main__':
    main()

