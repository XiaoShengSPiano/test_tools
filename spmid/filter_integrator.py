#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
过滤信息整合器模块

职责：
1. 将FilterCollector收集的过滤信息转换为InvalidNotesStatistics格式
2. 整合多个来源的无效音符信息
3. 提供统一的接口供SPMIDAnalyzer使用

设计原则：
- 单一职责：只负责数据整合和转换
- 松耦合：不依赖具体的业务逻辑
- 清晰的接口：便于扩展
"""

from typing import List
from .filter_collector import FilterCollector, FilteredNoteInfo
from .invalid_notes_statistics import InvalidNotesStatistics
from .spmid_reader import Note
from utils.logger import Logger

logger = Logger.get_logger()


class FilterIntegrator:
    """
    过滤信息整合器
    
    负责将FilterCollector收集的过滤信息整合到InvalidNotesStatistics中。
    处理数据类型转换和映射。
    """
    
    # 过滤原因到InvalidNotesStatistics原因代码的映射
    REASON_MAPPING = {
        'low_after_value': 'low_after_value',  # 压感值过低（保持原样）
        'short_duration': 'short_duration',  # 持续时间过短（保持原样）
        'empty_data': 'empty_data',  # 数据为空
    }
    
    @staticmethod
    def convert_optimized_note_to_legacy(opt_note: any) -> Note:
        """
        将OptimizedNote转换为Note对象
        
        Args:
            opt_note: OptimizedNote对象
        
        Returns:
            Note: 转换后的Note对象
        """
        import pandas as pd
        
        # 转换hammers数据
        if len(opt_note.hammers_ts) > 0:
            hammers = pd.Series(
                data=opt_note.hammers_val,
                index=opt_note.hammers_ts,
                name="hammer"
            )
        else:
            hammers = pd.Series(dtype='int64', name="hammer")
        
        # 转换after_touch数据
        if len(opt_note.after_ts) > 0:
            after_touch = pd.Series(
                data=opt_note.after_val,
                index=opt_note.after_ts,
                name="after_touch"
            )
        else:
            after_touch = pd.Series(dtype='int64', name="after_touch")
        
        # 创建Note对象
        note = Note(
            offset=opt_note.offset,
            id=opt_note.id,
            finger=opt_note.finger,
            velocity=opt_note.velocity,
            uuid=opt_note.uuid,
            hammers=hammers,
            after_touch=after_touch,
            key_on_ms=None,
            key_off_ms=None,
            duration_ms=None,
            split_parent_idx=None,
            split_seq=None,
            is_split=False
        )
        
        return note
    
    @staticmethod
    def integrate_filter_data(
        filter_collector: FilterCollector,
        record_notes: List[Note],
        replay_notes: List[Note]
    ) -> InvalidNotesStatistics:
        """
        将FilterCollector的数据整合到InvalidNotesStatistics中
        
        Args:
            filter_collector: 过滤信息收集器
            record_notes: 录制音符列表（过滤后的有效数据）
            replay_notes: 播放音符列表（过滤后的有效数据）
        
        Returns:
            InvalidNotesStatistics: 整合后的统计对象
        """
        stats = InvalidNotesStatistics()
        
        # 设置总数和有效数
        record_filtered = filter_collector.get_filtered_notes('record')
        replay_filtered = filter_collector.get_filtered_notes('replay')
        
        stats.record_total = len(record_notes) + len(record_filtered)
        stats.record_valid = len(record_notes)
        
        stats.replay_total = len(replay_notes) + len(replay_filtered)
        stats.replay_valid = len(replay_notes)
        
        # 整合录制数据的过滤信息
        for filtered_info in record_filtered:
            # 转换OptimizedNote为Note
            if hasattr(filtered_info.note, 'hammers_ts'):
                # 是OptimizedNote，需要转换
                note = FilterIntegrator.convert_optimized_note_to_legacy(filtered_info.note)
            else:
                # 已经是Note对象
                note = filtered_info.note
            
            # 映射原因代码
            reason = FilterIntegrator.REASON_MAPPING.get(
                filtered_info.reason,
                'other_errors'
            )
            
            # 添加到统计对象
            stats.add_invalid_note(
                note=note,
                index=filtered_info.index,
                reason=reason,
                data_type='录制'
            )
        
        # 整合播放数据的过滤信息
        for filtered_info in replay_filtered:
            # 转换OptimizedNote为Note
            if hasattr(filtered_info.note, 'hammers_ts'):
                # 是OptimizedNote，需要转换
                note = FilterIntegrator.convert_optimized_note_to_legacy(filtered_info.note)
            else:
                # 已经是Note对象
                note = filtered_info.note
            
            # 映射原因代码
            reason = FilterIntegrator.REASON_MAPPING.get(
                filtered_info.reason,
                'other_errors'
            )
            
            # 添加到统计对象
            stats.add_invalid_note(
                note=note,
                index=filtered_info.index,
                reason=reason,
                data_type='播放'
            )
        
        logger.info(f"📊 过滤信息整合完成: 录制={len(record_filtered)}个, 播放={len(replay_filtered)}个")
        
        return stats
