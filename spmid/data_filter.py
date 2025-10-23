#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SPMID数据过滤器

负责SPMID数据的过滤和验证，包括：
- 音符有效性检查
- 阈值检查
- 无效音符统计
"""

from .spmid_reader import Note
from .motor_threshold_checker import MotorThresholdChecker
from typing import List, Tuple, Dict, Any, Optional
from utils.logger import Logger

logger = Logger.get_logger()


class DataFilter:
    """SPMID数据过滤器类"""
    
    def __init__(self, threshold_checker: Optional[MotorThresholdChecker] = None):
        """
        初始化数据过滤器
        
        Args:
            threshold_checker: 电机阈值检查器实例
        """
        self.threshold_checker = threshold_checker
    
    def filter_valid_notes_data(self, record_data: List[Note], replay_data: List[Note]) -> Tuple[List[Note], List[Note], Dict[str, Any]]:
        """
        过滤有效音符数据
        
        对录制数据和播放数据进行有效性检查，过滤掉无效的音符（如锤速为0、持续时间过短、触后力度过弱等）
        
        Args:
            record_data: 录制数据，包含所有录制的音符
            replay_data: 播放数据，包含所有播放的音符
            
        Returns:
            Tuple[List[Note], List[Note], Dict[str, Any]]: 过滤结果
                - valid_record_data: 过滤后的有效录制音符列表
                - valid_replay_data: 过滤后的有效播放音符列表  
                - invalid_counts: 无效音符统计信息，包含：
                    - record_data: 录制数据的统计信息
                    - replay_data: 播放数据的统计信息
                    每个统计信息包含：
                    - total_notes: 总音符数
                    - valid_notes: 有效音符数
                    - invalid_notes: 无效音符数
                    - invalid_reasons: 无效原因统计
        """
        logger.info("🔍 开始过滤有效音符数据")
        
        # 过滤录制数据
        valid_record_data, record_invalid_counts = self._filter_valid_notes_with_details(record_data, "录制")
        
        # 过滤播放数据
        valid_replay_data, replay_invalid_counts = self._filter_valid_notes_with_details(replay_data, "播放")
        
        # 合并无效音符统计
        invalid_counts = {
            'record_data': record_invalid_counts,
            'replay_data': replay_invalid_counts
        }
        
        logger.info(f"✅ 数据过滤完成: 录制 {len(valid_record_data)}/{len(record_data)}, 播放 {len(valid_replay_data)}/{len(replay_data)}")
        
        return valid_record_data, valid_replay_data, invalid_counts
    
    def _filter_valid_notes_with_details(self, notes: List[Note], data_type: str) -> Tuple[List[Note], Dict[str, Any]]:
        """
        过滤有效音符并返回详细统计
        
        对单个数据源（录制或播放）的音符进行有效性检查，并统计无效音符的详细信息
        
        Args:
            notes: 待过滤的音符列表
            data_type: 数据类型标识，用于日志记录（"录制"或"播放"）
            
        Returns:
            Tuple[List[Note], Dict[str, Any]]: 过滤结果和统计信息
                - valid_notes: 通过有效性检查的音符列表
                - invalid_counts: 无效音符统计信息，包含：
                    - total_notes: 输入的总音符数
                    - valid_notes: 有效音符数量
                    - invalid_notes: 无效音符数量
                    - invalid_reasons: 无效原因分类统计，包含：
                        - duration_too_short: 持续时间过短的数量
                        - after_touch_too_weak: 触后力度过弱的数量
                        - empty_data: 数据为空的数量
                        - other_errors: 其他错误的数量
        """
        valid_notes = []
        invalid_reasons = {
            'duration_too_short': 0,
            'after_touch_too_weak': 0,
            'empty_data': 0,
            'other_errors': 0
        }
        
        for note in notes:
            if self._is_note_valid(note):
                valid_notes.append(note)
            else:
                # 统计无效原因（这里可以扩展更详细的统计）
                invalid_reasons['other_errors'] += 1
        
        invalid_counts = {
            'total_notes': len(notes),
            'valid_notes': len(valid_notes),
            'invalid_notes': len(notes) - len(valid_notes),
            'invalid_reasons': invalid_reasons
        }
        
        return valid_notes, invalid_counts
    
    def _is_note_valid(self, note: Note) -> bool:
        """
        检查音符是否有效
        
        对单个音符进行全面的有效性检查，包括数据完整性、锤速、持续时间、触后力度等条件
        
        Args:
            note: 待检查的音符对象，包含hammers、after_touch等数据
            
        Returns:
            bool: 音符有效性检查结果
                - True: 音符通过所有有效性检查，可以用于后续分析
                - False: 音符未通过有效性检查，将被过滤掉
                
        检查条件包括：
            - 数据完整性：after_touch和hammers数据不能为空
            - 锤速检查：第一个锤子的速度不能为0
            - 持续时间：音符持续时间不能少于300ms
            - 触后力度：最大触后力度不能少于500
            - 阈值检查：通过电机阈值检查器验证是否能够发声
        """
        try:
            # 基本条件检查
            if len(note.after_touch) == 0 or len(note.hammers) == 0:
                self._log_invalid_note_details(note, "数据为空", "after_touch或hammers为空")
                return False
            
            # 获取第一个锤子的速度值
            first_hammer_velocity = note.hammers.values[0]
            
            # 检查锤速是否为0
            if first_hammer_velocity == 0:
                self._log_invalid_note_details(note, "锤速为0", f"锤速={first_hammer_velocity}")
                return False
            
            # 检查音符的基本条件
            chazhi = note.after_touch.index[-1] - note.after_touch.index[0]
            max_after_touch = max(note.after_touch.values)
            
            if chazhi < 300:
                self._log_invalid_note_details(note, "持续时间过短", f"持续时间={chazhi}ms (<300ms)")
                return False
                
            if max_after_touch < 500:
                self._log_invalid_note_details(note, "触后力度过弱", f"最大触后力度={max_after_touch} (<500)")
                return False
            
            # 使用电机阈值检查器判断是否发声
            if self.threshold_checker:
                motor_name = f"motor_{note.id}"
                is_valid = self.threshold_checker.check_threshold(first_hammer_velocity, motor_name)
                
                if not is_valid:
                    self._log_invalid_note_details(note, "阈值检查失败", f"锤速={first_hammer_velocity}, 电机={motor_name}")
                
                return is_valid
            else:
                # 如果没有阈值检查器，只进行基本检查
                return True
            
        except Exception as e:
            self._log_invalid_note_details(note, "异常错误", f"错误信息: {str(e)}")
            return False
    
    def _log_invalid_note_details(self, note: Note, reason: str, details: str) -> None:
        """
        记录无效音符的详细信息
        
        将无效音符的详细信息记录到日志中，便于调试和问题排查
        
        Args:
            note: 无效的音符对象，包含键ID等信息
            reason: 音符无效的原因（如"数据为空"、"锤速为0"等）
            details: 详细的错误信息，包含具体的数值或状态
            
        Returns:
            None: 无返回值，仅用于日志记录
        """
        logger.debug(f"无效音符 - 键ID: {note.id}, 原因: {reason}, 详情: {details}")
    
    def generate_invalid_notes_table_data(self, invalid_counts: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成无效音符的表格数据
        
        将无效音符的统计信息转换为适合UI表格显示的数据格式
        
        Args:
            invalid_counts: 无效音符统计信息，包含录制和播放数据的统计
                结构为：
                {
                    'record_data': {
                        'total_notes': int,      # 总音符数
                        'valid_notes': int,      # 有效音符数
                        'invalid_notes': int,    # 无效音符数
                        'invalid_reasons': dict  # 无效原因统计
                    },
                    'replay_data': {
                        # 同上结构
                    }
                }
            
        Returns:
            Dict[str, Any]: 适合UI表格显示的数据格式
                直接返回输入的invalid_counts，保持数据结构不变
                用于前端UI组件（如DataTable）显示无效音符统计信息
        """
        return invalid_counts
