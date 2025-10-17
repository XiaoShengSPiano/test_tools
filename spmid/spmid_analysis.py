from matplotlib import figure
from .spmid_reader import Note, find_best_matching_notes_debug
from .types import NoteInfo, Diffs, ErrorNote
from .motor_threshold_checker import MotorThresholdChecker
from typing import List
from utils.logger import Logger

import pandas as pd
import matplotlib.pyplot as plt
import os

logger = Logger.get_logger()


def _create_error_note_with_stats(record_note, replay_note, record_index, replay_index, 
                                 record_keyon, record_keyoff, replay_keyon, replay_keyoff):
    """
    创建包含统计信息的错误音符对象
    
    Args:
        record_note: 录制音符对象
        replay_note: 播放音符对象
        record_index: 录制音符索引
        replay_index: 播放音符索引
        record_keyon/record_keyoff: 录制音符时间戳
        replay_keyon/replay_keyoff: 播放音符时间戳
    
    Returns:
        ErrorNote: 包含统计信息的错误音符对象
    """
    # 计算录制数据的统计信息
    record_diffs = pd.Series(record_note.after_touch.index).diff().dropna()
    record_note_info = NoteInfo(index=record_index, keyId=record_note.id, 
                               keyOn=record_keyon, keyOff=record_keyoff)
    record_diff_stats = Diffs(mean=record_diffs.mean(), std=record_diffs.std(), 
                             max=record_diffs.max(), min=record_diffs.min())
    
    # 计算播放数据的统计信息
    replay_diffs = pd.Series(replay_note.after_touch.index).diff().dropna()
    replay_note_info = NoteInfo(index=replay_index, keyId=replay_note.id, 
                               keyOn=replay_keyon, keyOff=replay_keyoff)
    replay_diff_stats = Diffs(mean=replay_diffs.mean(), std=replay_diffs.std(), 
                             max=replay_diffs.max(), min=replay_diffs.min())
    
    # 创建错误音符对象
    return ErrorNote(infos=[record_note_info, replay_note_info], 
                    diffs=[record_diff_stats, replay_diff_stats])


def _filter_valid_notes(notes: List[Note], threshold_checker: MotorThresholdChecker) -> List[Note]:
    """
    过滤掉不发声的无效音符
    
    Args:
        notes: 音符列表
        threshold_checker: 电机阈值检查器
    
    Returns:
        List[Note]: 过滤后的有效音符列表
    """
    valid_notes = []
    invalid_count = 0
    
    for note in notes:
        # 检查音符的基本条件
        chazhi = note.after_touch.index[-1] - note.after_touch.index[0]
        if chazhi < 300 or max(note.after_touch.values) < 500:
            invalid_count += 1
            logger.debug(f"音符 {note.id} 被过滤：基本条件不满足")
            continue
        
        # 检查锤子是否发声
        has_sound = False
        for hammer_velocity in note.hammers.values:
            # 使用电机阈值检查器判断是否发声
            # 映射规则：motor_{NoteID}，例如 NoteID=3 -> motor_3
            motor_name = f"motor_{note.id}"
            if threshold_checker.check_threshold(hammer_velocity, motor_name):
                has_sound = True
                break
        
        if has_sound:
            valid_notes.append(note)
        else:
            invalid_count += 1
            logger.debug(f"音符 {note.id} 被过滤：锤子不发声")
    
    logger.info(f"过滤完成：原始音符 {len(notes)} 个，有效音符 {len(valid_notes)} 个，无效音符 {invalid_count} 个")
    return valid_notes


def spmid_analysis(record_data: List[Note], replay_data: List[Note]):
    """
    分析SPMID数据，统计多锤、丢锤和不发声锤子
    
    Args:
        record_data: 录制数据
        replay_data: 播放数据
    
    Returns:
        tuple: (multi_hammers, drop_hammers, silent_hammers, valid_record_data, valid_replay_data)
    """
    # 初始化电机阈值检查器
    threshold_checker = _initialize_threshold_checker()
    if threshold_checker is None:
        # 初始化失败，直接抛出异常
        raise RuntimeError("电机阈值检查器初始化失败，无法进行SPMID数据分析")
    
    # 过滤有效音符并统计无效音符数量
    valid_record_data, valid_replay_data, invalid_counts = _filter_valid_notes_data(record_data, replay_data, threshold_checker)
    
    # 分析多锤和丢锤问题（不发声的音符已被过滤掉，无需额外处理）
    drop_hammers, multi_hammers = _analyze_hammer_issues(valid_record_data, valid_replay_data)
    
    # 记录无效音符统计信息
    _log_invalid_notes_statistics(record_data, replay_data, valid_record_data, valid_replay_data, invalid_counts)
    
    # 不发声的音符已被过滤掉，返回空列表
    silent_hammers = []
    
    return multi_hammers, drop_hammers, silent_hammers, valid_record_data, valid_replay_data

def _initialize_threshold_checker():
    """初始化电机阈值检查器"""
    try:
        return MotorThresholdChecker(
            fit_equations_path=os.path.join(os.path.dirname(__file__), "quadratic_fit_formulas.json"),
            pwm_thresholds_path=os.path.join(os.path.dirname(__file__), "inflection_pwm_values.json")
        )
    except Exception as e:
        logger.error(f"初始化电机阈值检查器失败: {e}")
        return None

def _filter_valid_notes_data(record_data, replay_data, threshold_checker):
    """过滤有效音符数据并统计无效音符信息"""
    valid_record_data, invalid_record_notes = _filter_valid_notes_with_details(record_data, threshold_checker)
    valid_replay_data, invalid_replay_notes = _filter_valid_notes_with_details(replay_data, threshold_checker)
    
    # 统计无效音符信息
    invalid_counts = {
        'record_invalid': len(invalid_record_notes),
        'replay_invalid': len(invalid_replay_notes),
        'record_total': len(record_data),
        'replay_total': len(replay_data),
        'invalid_record_notes': invalid_record_notes,
        'invalid_replay_notes': invalid_replay_notes
    }
    
    return valid_record_data, valid_replay_data, invalid_counts

def _filter_valid_notes_with_details(notes, threshold_checker):
    """过滤有效音符并返回无效音符的详细信息"""
    valid_notes = []
    invalid_notes = []
    
    for i, note in enumerate(notes):
        try:
            # 检查音符是否有效
            if _is_note_valid(note, threshold_checker):
                valid_notes.append(note)
            else:
                # 收集无效音符的详细信息
                invalid_info = _create_invalid_note_info(note, i)
                invalid_notes.append(invalid_info)
        except Exception as e:
            # 处理异常情况
            invalid_info = _create_invalid_note_info(note, i, error_msg=str(e))
            invalid_notes.append(invalid_info)
    
    return valid_notes, invalid_notes

def _is_note_valid(note, threshold_checker):
    """检查音符是否有效"""
    try:
        # 基本条件检查
        if len(note.after_touch) == 0 or len(note.hammers) == 0:
            return False
        
        # 检查音符的基本条件
        chazhi = note.after_touch.index[-1] - note.after_touch.index[0]
        if chazhi < 300 or max(note.after_touch.values) < 500:
            return False
        
        # 检查锤子是否发声
        for hammer_velocity in note.hammers.values:
            # 使用电机阈值检查器判断是否发声
            # 映射规则：motor_{NoteID}，例如 NoteID=3 -> motor_3
            motor_name = f"motor_{note.id}"
            if threshold_checker.check_threshold(hammer_velocity, motor_name):
                return True
        
        return False
    except Exception:
        return False

def _create_invalid_note_info(note, index, error_msg=None):
    """创建无效音符的详细信息"""
    try:
        # 提取基本信息
        keyon = note.after_touch.index[0] + note.offset if len(note.after_touch) > 0 else note.offset
        keyoff = note.after_touch.index[-1] + note.offset if len(note.after_touch) > 0 else note.offset
        duration = keyoff - keyon
        max_after_touch = max(note.after_touch.values) if len(note.after_touch) > 0 else 0
        hammer_count = len(note.hammers)
        
        return {
            'index': index,
            'key_id': note.id,
            'keyon': keyon,
            'keyoff': keyoff,
            'duration': duration,
            'max_after_touch': max_after_touch,
            'hammer_count': hammer_count,
            'after_touch_count': len(note.after_touch),
            'error_msg': error_msg,
            'is_duration_too_short': duration < 300,
            'is_after_touch_too_weak': max_after_touch < 500,
            'is_empty_data': len(note.after_touch) == 0 or len(note.hammers) == 0
        }
    except Exception as e:
        return {
            'index': index,
            'key_id': getattr(note, 'id', 'unknown'),
            'error_msg': f"Failed to extract note info: {str(e)}"
        }

def _log_invalid_notes_statistics(record_data, replay_data, valid_record_data, valid_replay_data, invalid_counts):
    """记录无效音符统计信息"""
    logger.info("📊 音符过滤统计:")
    logger.info(f"  录制数据: 总计 {invalid_counts['record_total']} 个音符, "
               f"有效 {len(valid_record_data)} 个, "
               f"无效 {invalid_counts['record_invalid']} 个")
    logger.info(f"  回放数据: 总计 {invalid_counts['replay_total']} 个音符, "
               f"有效 {len(valid_replay_data)} 个, "
               f"无效 {invalid_counts['replay_invalid']} 个")
    
    # 计算过滤率
    record_filter_rate = (invalid_counts['record_invalid'] / invalid_counts['record_total'] * 100) if invalid_counts['record_total'] > 0 else 0
    replay_filter_rate = (invalid_counts['replay_invalid'] / invalid_counts['replay_total'] * 100) if invalid_counts['replay_total'] > 0 else 0
    
    logger.info(f"  过滤率: 录制 {record_filter_rate:.1f}%, 回放 {replay_filter_rate:.1f}%")
    
    # 详细分析无效音符的原因
    _analyze_invalid_notes_reasons(invalid_counts['invalid_record_notes'], "录制")
    _analyze_invalid_notes_reasons(invalid_counts['invalid_replay_notes'], "回放")

def _analyze_invalid_notes_reasons(invalid_notes, data_type):
    """分析无效音符的原因"""
    if not invalid_notes:
        return
    
    # 统计各种无效原因
    reasons = {
        'duration_too_short': 0,
        'after_touch_too_weak': 0,
        'empty_data': 0,
        'other_errors': 0
    }
    
    for note_info in invalid_notes:
        if note_info.get('is_empty_data', False):
            reasons['empty_data'] += 1
        elif note_info.get('is_duration_too_short', False):
            reasons['duration_too_short'] += 1
        elif note_info.get('is_after_touch_too_weak', False):
            reasons['after_touch_too_weak'] += 1
        else:
            reasons['other_errors'] += 1
    
    logger.info(f"  {data_type}数据无效原因分析:")
    if reasons['duration_too_short'] > 0:
        logger.info(f"    持续时间过短 (<300): {reasons['duration_too_short']} 个")
    if reasons['after_touch_too_weak'] > 0:
        logger.info(f"    触后力度过弱 (<500): {reasons['after_touch_too_weak']} 个")
    if reasons['empty_data'] > 0:
        logger.info(f"    数据为空: {reasons['empty_data']} 个")
    if reasons['other_errors'] > 0:
        logger.info(f"    其他错误: {reasons['other_errors']} 个")
    
    # 显示前几个无效音符的详细信息（用于调试）
    if len(invalid_notes) > 0:
        logger.debug(f"  {data_type}数据无效音符示例:")
        for i, note_info in enumerate(invalid_notes[:3]):  # 只显示前3个
            logger.debug(f"    音符 {i+1}: 键位={note_info.get('key_id', 'N/A')}, "
                        f"持续时间={note_info.get('duration', 'N/A')}, "
                        f"最大触后={note_info.get('max_after_touch', 'N/A')}, "
                        f"锤子数={note_info.get('hammer_count', 'N/A')}")
            if note_info.get('error_msg'):
                logger.debug(f"      错误信息: {note_info['error_msg']}")

def _analyze_hammer_issues(valid_record_data, valid_replay_data):
    """分析多锤和丢锤问题"""
    multi_hammers = []
    drop_hammers = []
    
    # 分析录制数据中的问题
    _analyze_record_data_issues(valid_record_data, valid_replay_data, multi_hammers, drop_hammers)
    
    # 分析回放数据中的问题
    _analyze_replay_data_issues(valid_replay_data, valid_record_data, multi_hammers)
    
    return drop_hammers, multi_hammers

def _analyze_record_data_issues(valid_record_data, valid_replay_data, multi_hammers, drop_hammers):
    """分析录制数据中的问题"""
    for i, note in enumerate(valid_record_data):
        note_info = _extract_note_info(note, i)
        logger.debug(f'id = {note_info["key_id"]}, keyon = {note_info["keyon"]}')
        
        # todo 按键匹配算法
        index = find_best_matching_notes_debug(valid_replay_data, note_info["keyon"], note_info["keyoff"], note_info["key_id"])
        
        if index == -1:
            # 丢锤：录制有，回放没有
            _handle_drop_hammer_case(note, note_info, drop_hammers)
        else:
            # 比较锤子数量
            _compare_hammer_counts(note, valid_replay_data[index], note_info, index, multi_hammers, drop_hammers)

def _analyze_replay_data_issues(valid_replay_data, valid_record_data, multi_hammers):
    """分析回放数据中的问题"""
    for i, note in enumerate(valid_replay_data):
        note_info = _extract_note_info(note, i)
        logger.debug(f'id = {note_info["key_id"]}, keyon = {note_info["keyon"]}')
        
        index = find_best_matching_notes_debug(valid_record_data, note_info["keyon"], note_info["keyoff"], note_info["key_id"])
        
        if index == -1:
            # 多锤：回放有，录制没有
            _handle_multi_hammer_case(note, note_info, multi_hammers)

def _extract_note_info(note, index):
    """提取音符基本信息"""
    return {
        'keyon': note.after_touch.index[0] + note.offset,
        'keyoff': note.after_touch.index[-1] + note.offset,
        'key_id': note.id,
        'index': index
    }

def _handle_drop_hammer_case(note, note_info, drop_hammers):
    """处理丢锤情况"""
    logger.info(f"🔍 检测到丢锤：录制有 NoteId={note_info['key_id']}，播放没有对应音符")
    logger.debug("未查找到对应音符块")
    
    diffs = pd.Series(note.after_touch.index).diff().dropna()
    diff_stats = Diffs(mean=diffs.mean(), std=diffs.std(), max=diffs.max(), min=diffs.min())
    note_info_obj = NoteInfo(index=note_info['index'], keyId=note_info['key_id'], 
                           keyOn=note_info['keyon'], keyOff=note_info['keyoff'])
    error_note = ErrorNote(infos=[note_info_obj], diffs=[diff_stats])
    drop_hammers.append(error_note)

def _handle_multi_hammer_case(note, note_info, multi_hammers):
    """处理多锤情况"""
    logger.debug("未查找到对应音符块")
    
    diffs = pd.Series(note.after_touch.index).diff().dropna()
    diff_stats = Diffs(mean=diffs.mean(), std=diffs.std(), max=diffs.max(), min=diffs.min())
    note_info_obj = NoteInfo(index=note_info['index'], keyId=note_info['key_id'], 
                           keyOn=note_info['keyon'], keyOff=note_info['keyoff'])
    error_note = ErrorNote(infos=[note_info_obj], diffs=[diff_stats])
    multi_hammers.append(error_note)

def _compare_hammer_counts(record_note, replay_note, note_info, replay_index, multi_hammers, drop_hammers):
    """比较锤子数量并处理相应情况"""
    record_hammers = len(record_note.hammers)
    play_hammers = len(replay_note.hammers)
    
    replay_keyon = replay_note.after_touch.index[0] + replay_note.offset
    replay_keyoff = replay_note.after_touch.index[-1] + replay_note.offset
    
    if record_hammers < play_hammers:
        # 多锤：录制锤子少，回放锤子多
        error_note = _create_error_note_with_stats(
            record_note, replay_note, note_info['index'], replay_index,
            note_info['keyon'], note_info['keyoff'], replay_keyon, replay_keyoff
        )
        multi_hammers.append(error_note)
        logger.info(f"多锤数据: {record_note.id}")
    elif record_hammers > play_hammers:
        # 丢锤：录制锤子多，回放锤子少
        error_note = _create_error_note_with_stats(
            record_note, replay_note, note_info['index'], replay_index,
            note_info['keyon'], note_info['keyoff'], replay_keyon, replay_keyoff
        )
        drop_hammers.append(error_note)
        logger.info(f"丢锤数据: {record_note.id}")



def get_figure_by_index(record_data: List[Note], replay_data: List[Note], record_index:int, replay_index:int)->figure:
    record_note = record_data[record_index]
    replay_note = replay_data[replay_index]
    record_note.after_touch.plot(label='record after_touch', color='blue')
    plt.scatter(x=record_note.hammers.index, y=record_note.hammers.values, color='blue', label='record hammers')
    replay_note.after_touch.plot(label='play after_touch', color='red')
    plt.scatter(x=replay_note.hammers.index, y=replay_note.hammers.values, color='red', label='play hammers')
    plt.xlabel('Time (100us)') 
    plt.legend()
    plt.tight_layout()
    return plt.gcf()


def spmid_mutil_and_drop_judge(record_key_of_notes, replay_key_of_notes):
    """
        判断多锤、漏锤情况
    """
    mutil_hammers = []
    drop_hammers = []