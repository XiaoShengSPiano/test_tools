#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
检查SPMID文件中的低质量音符
- 压感值最大值 < 500
- 持续时间 < 30ms
"""

import sys
import numpy as np
from pathlib import Path
from spmid.spmid_reader import OptimizedSPMidReader
from utils.logger import Logger

logger = Logger.get_logger()


def analyze_note_quality(note, note_type: str, index: int):
    """
    分析单个音符的质量
    
    Args:
        note: OptimizedNote对象
        note_type: 'record' 或 'replay'
        index: 音符索引
        
    Returns:
        tuple: (has_issue: bool, has_no_hammers: bool)
    """
    issues = []
    has_no_hammers = len(note.hammers_ts) == 0
    
    # 检查1: after_touch数据是否为空
    if note.after_val.size == 0 or note.after_ts.size == 0:
        issues.append("after_touch数据为空")
    else:
        # 检查2: 压感值最大值
        max_after_val = np.max(note.after_val)
        if max_after_val < 500:
            issues.append(f"压感值过低: 最大值={max_after_val} (<500)")
        
        # 检查3: 持续时间
        time_span = note.after_ts[-1] - note.after_ts[0]
        duration_ms = time_span * 0.1
        if time_span < 300:  # 300 * 0.1ms = 30ms
            issues.append(f"持续时间过短: {duration_ms:.1f}ms (<30ms)")
    
    # 如果有问题，输出详细信息
    if issues:
        logger.warning(f"[{note_type}] 音符 #{index} (键位ID={note.id}) 存在问题:")
        logger.warning(f"  UUID: {note.uuid}")
        logger.warning(f"  Velocity: {note.velocity}")
        logger.warning(f"  Finger: {note.finger}")
        logger.warning(f"  Offset: {note.offset}")
        
        # Hammers信息
        if len(note.hammers_ts) > 0:
            logger.warning(f"  Hammers数量: {len(note.hammers_ts)}")
            logger.warning(f"  第一个Hammer: 时间={note.hammers_ts[0]*0.1:.1f}ms, 值={note.hammers_val[0]}")
            if len(note.hammers_ts) > 1:
                logger.warning(f"  最后一个Hammer: 时间={note.hammers_ts[-1]*0.1:.1f}ms, 值={note.hammers_val[-1]}")
        else:
            logger.warning(f"  Hammers数量: 0 (无hammers数据)")
        
        # After-touch信息
        if len(note.after_ts) > 0:
            max_val = np.max(note.after_val)
            min_val = np.min(note.after_val)
            time_span = note.after_ts[-1] - note.after_ts[0]
            logger.warning(f"  After-touch数量: {len(note.after_ts)}")
            logger.warning(f"  After-touch范围: 最小={min_val}, 最大={max_val}")
            logger.warning(f"  持续时间: {time_span*0.1:.1f}ms (时间跨度: {note.after_ts[0]} -> {note.after_ts[-1]})")
            
            # 显示前5个after-touch数据点
            if len(note.after_ts) <= 5:
                logger.warning(f"  After-touch数据点: {list(zip(note.after_ts, note.after_val))}")
            else:
                logger.warning(f"  前5个After-touch数据点: {list(zip(note.after_ts[:5], note.after_val[:5]))}")
        else:
            logger.warning(f"  After-touch数量: 0 (无after-touch数据)")
        
        # 问题列表
        for issue in issues:
            logger.warning(f"  ⚠️  {issue}")
        
        # 如果没有hammers数据，特别标注
        if has_no_hammers:
            logger.warning(f"  🔴 该音符没有Hammers数据")
        
        logger.warning("")  # 空行分隔
        
        return True, has_no_hammers
    
    return False, has_no_hammers


def check_spmid_file(filepath: str):
    """
    检查SPMID文件中的低质量音符
    
    Args:
        filepath: SPMID文件路径
    """
    logger.info("="*80)
    logger.info(f"开始检查SPMID文件: {filepath}")
    logger.info("="*80)
    logger.info("")
    
    try:
        # 读取SPMID文件（OptimizedSPMidReader在初始化时自动解析）
        reader = OptimizedSPMidReader(filepath)
        
        # 获取音轨数据（track 0=录制, track 1=播放）
        record_notes = reader.get_track(0)
        replay_notes = reader.get_track(1) if reader.track_count > 1 else []
        
        logger.info(f"文件读取成功:")
        logger.info(f"  录制音符总数: {len(record_notes)}")
        logger.info(f"  播放音符总数: {len(replay_notes)}")
        logger.info("")
        
        # 检查录制音符
        logger.info("-"*80)
        logger.info("检查录制音符 (Record)")
        logger.info("-"*80)
        logger.info("")
        
        record_issue_count = 0
        record_no_hammers_count = 0
        for i, note in enumerate(record_notes):
            has_issue, has_no_hammers = analyze_note_quality(note, 'Record', i)
            if has_issue:
                record_issue_count += 1
                if has_no_hammers:
                    record_no_hammers_count += 1
        
        if record_issue_count == 0:
            logger.info("✅ 录制音符全部正常，无低质量音符")
        else:
            logger.warning(f"⚠️  录制音符中发现 {record_issue_count} 个低质量音符")
            logger.warning(f"   其中 {record_no_hammers_count} 个音符没有Hammers数据")
        
        logger.info("")
        
        # 检查播放音符
        logger.info("-"*80)
        logger.info("检查播放音符 (Replay)")
        logger.info("-"*80)
        logger.info("")
        
        replay_issue_count = 0
        replay_no_hammers_count = 0
        for i, note in enumerate(replay_notes):
            has_issue, has_no_hammers = analyze_note_quality(note, 'Replay', i)
            if has_issue:
                replay_issue_count += 1
                if has_no_hammers:
                    replay_no_hammers_count += 1
        
        if replay_issue_count == 0:
            logger.info("✅ 播放音符全部正常，无低质量音符")
        else:
            logger.warning(f"⚠️  播放音符中发现 {replay_issue_count} 个低质量音符")
            logger.warning(f"   其中 {replay_no_hammers_count} 个音符没有Hammers数据")
        
        logger.info("")
        
        # 总结
        logger.info("="*80)
        logger.info("检查完成 - 统计摘要")
        logger.info("="*80)
        logger.info(f"录制音符: {len(record_notes)} 个, 低质量: {record_issue_count} 个 ({record_issue_count/len(record_notes)*100:.2f}%)")
        logger.info(f"  └─ 其中无Hammers数据: {record_no_hammers_count} 个 ({record_no_hammers_count/record_issue_count*100:.1f}% of 低质量)" if record_issue_count > 0 else "")
        logger.info(f"播放音符: {len(replay_notes)} 个, 低质量: {replay_issue_count} 个 ({replay_issue_count/len(replay_notes)*100:.2f}%)")
        logger.info(f"  └─ 其中无Hammers数据: {replay_no_hammers_count} 个 ({replay_no_hammers_count/replay_issue_count*100:.1f}% of 低质量)" if replay_issue_count > 0 else "")
        logger.info(f"总计: {len(record_notes) + len(replay_notes)} 个, 低质量: {record_issue_count + replay_issue_count} 个")
        logger.info(f"  └─ 总无Hammers数据: {record_no_hammers_count + replay_no_hammers_count} 个")
        logger.info("="*80)
        
        return record_issue_count, replay_issue_count
        
    except Exception as e:
        logger.error(f"检查文件时发生错误: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None, None


def check_folder(folder_path: str):
    """
    批量检查文件夹中的所有SPMID文件
    
    Args:
        folder_path: 文件夹路径
    """
    folder = Path(folder_path)
    
    if not folder.exists():
        logger.error(f"文件夹不存在: {folder_path}")
        return
    
    if not folder.is_dir():
        logger.error(f"路径不是文件夹: {folder_path}")
        return
    
    # 查找所有.spmid文件
    spmid_files = list(folder.glob("*.spmid"))
    
    if not spmid_files:
        logger.warning(f"文件夹中没有找到SPMID文件: {folder_path}")
        return
    
    logger.info("="*80)
    logger.info(f"批量检查模式 - 文件夹: {folder_path}")
    logger.info(f"找到 {len(spmid_files)} 个SPMID文件")
    logger.info("="*80)
    logger.info("")
    
    # 统计总数
    total_files = len(spmid_files)
    success_files = 0
    total_record_notes = 0
    total_replay_notes = 0
    total_record_issues = 0
    total_replay_issues = 0
    total_record_no_hammers = 0
    total_replay_no_hammers = 0
    
    # 逐个处理文件
    for i, filepath in enumerate(spmid_files, 1):
        logger.info(f"\n{'='*80}")
        logger.info(f"[{i}/{total_files}] 处理文件: {filepath.name}")
        logger.info(f"{'='*80}\n")
        
        try:
            # 读取文件
            reader = OptimizedSPMidReader(str(filepath))
            record_notes = reader.get_track(0)
            replay_notes = reader.get_track(1) if reader.track_count > 1 else []
            
            logger.info(f"文件读取成功:")
            logger.info(f"  录制音符: {len(record_notes)} 个")
            logger.info(f"  播放音符: {len(replay_notes)} 个")
            logger.info("")
            
            # 检查录制音符
            record_issue_count = 0
            record_no_hammers_count = 0
            for j, note in enumerate(record_notes):
                has_issue, has_no_hammers = analyze_note_quality(note, 'Record', j)
                if has_issue:
                    record_issue_count += 1
                    if has_no_hammers:
                        record_no_hammers_count += 1
            
            # 检查播放音符
            replay_issue_count = 0
            replay_no_hammers_count = 0
            for j, note in enumerate(replay_notes):
                has_issue, has_no_hammers = analyze_note_quality(note, 'Replay', j)
                if has_issue:
                    replay_issue_count += 1
                    if has_no_hammers:
                        replay_no_hammers_count += 1
            
            # 文件统计摘要
            logger.info("-"*80)
            logger.info(f"文件统计: {filepath.name}")
            logger.info("-"*80)
            if len(record_notes) > 0:
                logger.info(f"录制: {len(record_notes)} 个, 低质量: {record_issue_count} 个 ({record_issue_count/len(record_notes)*100:.2f}%)")
                if record_issue_count > 0:
                    logger.info(f"  └─ 无Hammers: {record_no_hammers_count} 个 ({record_no_hammers_count/record_issue_count*100:.1f}%)")
            
            if len(replay_notes) > 0:
                logger.info(f"播放: {len(replay_notes)} 个, 低质量: {replay_issue_count} 个 ({replay_issue_count/len(replay_notes)*100:.2f}%)")
                if replay_issue_count > 0:
                    logger.info(f"  └─ 无Hammers: {replay_no_hammers_count} 个 ({replay_no_hammers_count/replay_issue_count*100:.1f}%)")
            logger.info("")
            
            # 累加统计
            total_record_notes += len(record_notes)
            total_replay_notes += len(replay_notes)
            total_record_issues += record_issue_count
            total_replay_issues += replay_issue_count
            total_record_no_hammers += record_no_hammers_count
            total_replay_no_hammers += replay_no_hammers_count
            success_files += 1
            
        except Exception as e:
            logger.error(f"处理文件 {filepath.name} 时出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
            continue
    
    # 输出总体统计
    logger.info("\n" + "="*80)
    logger.info("批量检查完成 - 总体统计")
    logger.info("="*80)
    logger.info(f"处理文件数: {success_files}/{total_files}")
    logger.info(f"")
    logger.info(f"录制音符总计: {total_record_notes} 个")
    logger.info(f"  └─ 低质量: {total_record_issues} 个 ({total_record_issues/total_record_notes*100:.2f}%)" if total_record_notes > 0 else "")
    logger.info(f"     └─ 无Hammers: {total_record_no_hammers} 个 ({total_record_no_hammers/total_record_issues*100:.1f}%)" if total_record_issues > 0 else "")
    logger.info(f"")
    logger.info(f"播放音符总计: {total_replay_notes} 个")
    logger.info(f"  └─ 低质量: {total_replay_issues} 个 ({total_replay_issues/total_replay_notes*100:.2f}%)" if total_replay_notes > 0 else "")
    logger.info(f"     └─ 无Hammers: {total_replay_no_hammers} 个 ({total_replay_no_hammers/total_replay_issues*100:.1f}%)" if total_replay_issues > 0 else "")
    logger.info(f"")
    logger.info(f"总音符数: {total_record_notes + total_replay_notes} 个")
    logger.info(f"总低质量: {total_record_issues + total_replay_issues} 个")
    logger.info(f"总无Hammers: {total_record_no_hammers + total_replay_no_hammers} 个")
    logger.info("="*80)


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法:")
        print("  单文件模式: python check_low_quality_notes.py <spmid_file_path>")
        print("  批量模式:   python check_low_quality_notes.py <folder_path>")
        print("")
        print("示例:")
        print("  python check_low_quality_notes.py test.spmid")
        print("  python check_low_quality_notes.py ./spmid_files/")
        sys.exit(1)
    
    path = sys.argv[1]
    path_obj = Path(path)
    
    # 检查路径是否存在
    if not path_obj.exists():
        logger.error(f"路径不存在: {path}")
        sys.exit(1)
    
    # 判断是文件还是文件夹
    if path_obj.is_file():
        # 单文件模式
        logger.info("单文件检查模式")
        record_count, replay_count = check_spmid_file(path)
        if record_count is not None:
            logger.info("\n详细日志已记录到 logs/app.log")
    elif path_obj.is_dir():
        # 批量文件夹模式
        check_folder(path)
        logger.info("\n详细日志已记录到 logs/app.log")
    else:
        logger.error(f"无效的路径类型: {path}")
        sys.exit(1)


if __name__ == "__main__":
    main()
