#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SPMID加载器（优化版）
使用高性能 Reader 读取，然后转换为标准 Note 结构以保持兼容性
"""

import traceback
import time
import pandas as pd
import numpy as np
from typing import Optional, Tuple, List
from utils.logger import Logger

# 导入优化版的高性能 Reader（已整合到 spmid.spmid_reader）
from spmid.spmid_reader import OptimizedSPMidReader, OptimizedNote, Note
from spmid.filter_collector import FilterCollector

logger = Logger.get_logger()


class SPMIDLoader:
    """SPMID加载器 - 使用优化版 Reader，提供原版 Note 兼容性"""
    
    def __init__(self):
        """初始化SPMID加载器"""
        self.logger = logger
        self.record_data = None
        self.replay_data = None
        self.filter_collector = FilterCollector()  # 过滤信息收集器
    
    def clear_data(self) -> None:
        """清理加载的数据"""
        self.record_data = None
        self.replay_data = None
        self.filter_collector.clear()
        self.logger.info("✅ SPMID数据已清理")
    
    def load_spmid_data(self, spmid_bytes: bytes) -> bool:
        """
        加载SPMID数据（使用优化版 Reader）
        
        Args:
            spmid_bytes: SPMID文件字节数据
            
        Returns:
            bool: 是否加载成功
        """
        try:
            perf_loader_start = time.time()
            
            # 使用优化版 Reader 读取
            perf_load_start = time.time()
            success, error_msg = self._load_track_data_from_bytes(spmid_bytes)
            perf_load_end = time.time()
            self.logger.info(f"        ⏱️  [性能] SPMID-解析音轨数据: {(perf_load_end - perf_load_start)*1000:.2f}ms")
            
            if success:
                perf_loader_end = time.time()
                total_time_ms = (perf_loader_end - perf_loader_start) * 1000
                self.logger.info(f"        🏁 [SPMID-Loader] 加载完成，总耗时: {total_time_ms:.2f}ms")
                return True
            else:
                self.logger.error(f"❌ SPMID数据加载失败: {error_msg}")
                return False
                    
        except Exception as e:
            self.logger.error(f"❌ SPMID数据加载异常: {e}")
            self.logger.error(traceback.format_exc())
            return False
    
    def get_record_data(self) -> List[Note]:
        """获取录制数据"""
        return self.record_data
    
    def get_replay_data(self) -> List[Note]:
        """获取播放数据"""
        return self.replay_data
    
    def get_filter_collector(self) -> FilterCollector:
        """获取过滤信息收集器"""
        return self.filter_collector
    
    # ==================== 私有方法 ====================
    
    def _load_track_data_from_bytes(self, spmid_bytes: bytes) -> Tuple[bool, Optional[str]]:
        """
        从内存中的字节数据加载音轨（使用优化版 Reader）
        
        Args:
            spmid_bytes: SPMID文件字节数据
            
        Returns:
            tuple: (是否成功, 错误信息)
        """
        try:
            # 使用优化版 Reader 读取（高性能）
            perf_read_start = time.time()
            reader = OptimizedSPMidReader(spmid_bytes)
            perf_read_end = time.time()
            self.logger.info(f"        ⏱️  [性能] 优化版Reader读取: {(perf_read_end - perf_read_start)*1000:.2f}ms")
            
            # 检查音轨数量
            track_count = reader.track_count
            if track_count < 2:
                return False, f"SPMID文件音轨数量不足，需要至少2个音轨，当前只有{track_count}个"
            
            # 获取优化版的音轨数据
            optimized_record_data = reader.get_track(0)
            optimized_replay_data = reader.get_track(1)

            if not optimized_record_data or not optimized_replay_data:
                return False, "音轨数据为空"

            # 过滤录制音轨中的异常数据（在转换为Note之前）
            perf_filter_start = time.time()
            original_record_count = len(optimized_record_data)
            self.filter_collector.set_data_type('record')
            optimized_record_data = self._filter_abnormal_record_notes(optimized_record_data, 'record')
            filtered_record_count = original_record_count - len(optimized_record_data)
            perf_filter_end = time.time()
            self.logger.info(f"        ⏱️  [性能] 录制数据过滤: {(perf_filter_end - perf_filter_start)*1000:.2f}ms")
            if filtered_record_count > 0:
                self.logger.info(f"        🧹 录制轨道过滤掉 {filtered_record_count} 个异常Note（共 {original_record_count} 个）")

            # 过滤播放音轨中的异常数据（在转换为Note之前）
            perf_filter_replay_start = time.time()
            original_replay_count = len(optimized_replay_data)
            self.filter_collector.set_data_type('replay')
            optimized_replay_data = self._filter_abnormal_record_notes(optimized_replay_data, 'replay')
            filtered_replay_count = original_replay_count - len(optimized_replay_data)
            perf_filter_replay_end = time.time()
            self.logger.info(f"        ⏱️  [性能] 播放数据过滤: {(perf_filter_replay_end - perf_filter_replay_start)*1000:.2f}ms")
            if filtered_replay_count > 0:
                self.logger.info(f"        🧹 播放轨道过滤掉 {filtered_replay_count} 个异常Note（共 {original_replay_count} 个）")

            # 转换为原版 Note 结构（保持兼容性）
            perf_convert_start = time.time()
            self.record_data = self._convert_track_to_legacy(optimized_record_data)
            self.replay_data = self._convert_track_to_legacy(optimized_replay_data)
            perf_convert_end = time.time()
            self.logger.info(f"        ⏱️  [性能] 数据转换为兼容格式: {(perf_convert_end - perf_convert_start)*1000:.2f}ms")
            
            self.logger.info(f"✅ 音轨数据加载成功 - 录制: {len(self.record_data)} 个音符, 播放: {len(self.replay_data)} 个音符")
            return True, None
                
        except Exception as e:
            error_msg = f"音轨数据加载失败: {str(e)}"
            self.logger.error(f"❌ {error_msg}")
            self.logger.error(traceback.format_exc())
            return False, error_msg
    
    def _convert_track_to_legacy(self, optimized_notes: List[OptimizedNote]) -> List[Note]:
        """
        将优化版 Note 列表转换为原版 Note 列表
        
        Args:
            optimized_notes: 优化版 Note 列表（NumPy arrays）
            
        Returns:
            List[Note]: 原版 Note 列表（Pandas Series）
        """
        legacy_notes = []
        
        for opt_note in optimized_notes:
            # 转换为原版 Note
            legacy_note = self._convert_optimized_note_to_legacy(opt_note)
            legacy_notes.append(legacy_note)
        
        return legacy_notes

    def _filter_abnormal_record_notes(self, optimized_notes: List[OptimizedNote], data_type: str) -> List[OptimizedNote]:
        """
        过滤音轨中的异常Note（在转换为标准Note之前）
        
        适用于录制音轨和播放音轨

        过滤条件：
        1. after_val中最大值 < 500
        2. 或者 after_ts中最后一个值 - after_ts的第一个值小于300

        Args:
            optimized_notes: 优化版Note列表
            data_type: 数据类型（'record' 或 'replay'）

        Returns:
            List[OptimizedNote]: 过滤后的Note列表
        """
        filtered_notes = []
        filtered_count = 0

        for i, note in enumerate(optimized_notes):
            # 检查触后数据是否存在
            if note.after_val.size == 0 or note.after_ts.size == 0:
                # 数据为空，过滤掉并记录
                self.filter_collector.add_filtered_note(
                    note, i, 'empty_data',
                    detail="after_touch数据为空"
                )
                filtered_count += 1
                continue

            # 检查条件1: after_val中最大值 < 500
            max_after_val = np.max(note.after_val)
            condition1 = max_after_val < 500

            # 检查条件2: after_ts中最后一个值 - after_ts的第一个值小于300
            if note.after_ts.size >= 2:
                time_span = note.after_ts[-1] - note.after_ts[0]
                condition2 = time_span < 300
            else:
                # 只有一个时间点也算异常
                time_span = 0
                condition2 = True

            # 如果满足任一条件，则过滤掉并记录
            if condition1 or condition2:
                if condition1 and condition2:
                    reason = 'low_after_value'
                    detail = f"after_touch最大值={max_after_val}(<500), 持续时间={time_span*0.1:.1f}ms(<30ms)"
                elif condition1:
                    reason = 'low_after_value'
                    detail = f"after_touch最大值={max_after_val}(<500)"
                else:
                    reason = 'short_duration'
                    detail = f"持续时间={time_span*0.1:.1f}ms(<30ms)"
                
                self.filter_collector.add_filtered_note(
                    note, i, reason, detail=detail
                )
                filtered_count += 1
            else:
                filtered_notes.append(note)

        if filtered_count > 0:
            data_name = "录制" if data_type == 'record' else "播放"
            self.logger.info(f"      📊 {data_name}轨道异常数据过滤: 保留 {len(filtered_notes)}/{len(optimized_notes)} 个Note")

        return filtered_notes

    @staticmethod
    def _convert_optimized_note_to_legacy(opt_note: OptimizedNote) -> Note:
        """
        将单个优化版 Note 转换为原版 Note
        
        Args:
            opt_note: 优化版 Note（使用 NumPy arrays）
            
        Returns:
            Note: 原版 Note（使用 Pandas Series）
        """
        # 将 NumPy arrays 转换为 Pandas Series
        if len(opt_note.hammers_ts) > 0:
            hammers = pd.Series(
                data=opt_note.hammers_val,
                index=opt_note.hammers_ts,
                name="hammer"
            )
        else:
            hammers = pd.Series(dtype='int64', name="hammer")
        
        if len(opt_note.after_ts) > 0:
            after_touch = pd.Series(
                data=opt_note.after_val,
                index=opt_note.after_ts,
                name="after_touch"
            )
        else:
            after_touch = pd.Series(dtype='int64', name="after_touch")
        
        # 创建原版 Note 对象
        # __post_init__ 会自动计算时间属性
        legacy_note = Note(
            offset=opt_note.offset,
            id=opt_note.id,
            finger=opt_note.finger,
            velocity=opt_note.velocity,
            uuid=opt_note.uuid,
            hammers=hammers,
            after_touch=after_touch,
            # 时间属性会在 __post_init__ 中自动计算
            key_on_ms=None,
            key_off_ms=None,
            duration_ms=None,
            # 拆分元数据默认值
            split_parent_idx=None,
            split_seq=None,
            is_split=False
        )
        
        return legacy_note
