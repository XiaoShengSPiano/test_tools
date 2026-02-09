import os
import sys

# 将当前目录添加到路径以便导入 spmid
sys.path.append(os.getcwd())

from spmid.spmid_reader import OptimizedSPMidReader

def check_raw_count(file_path):
    print(f"正在读取文件: {file_path}")
    try:
        reader = OptimizedSPMidReader(file_path)
        total_raw = 0
        for i in range(reader.track_count):
            track = reader.get_track(i)
            count = len(track)
            print(f"Track {i} 原始音符数: {count}")
            total_raw += count
        
        print(f"\n--- 结论 ---")
        print(f"未经过任何过滤的总音符数: {total_raw}")
        return total_raw
    except Exception as e:
        print(f"读取失败: {e}")
        return None

if __name__ == "__main__":
    # 使用之前转换的那个文件路径
    target_file = r"c:\Users\xuche\Desktop\spmid2parqute\test.spmid"
    if os.path.exists(target_file):
        check_raw_count(target_file)
    else:
        print(f"找不到文件: {target_file}")
