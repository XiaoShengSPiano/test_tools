#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据过滤模块
负责按键过滤、时间过滤等数据筛选功能
"""

from typing import List, Dict, Any, Optional, Tuple
from utils.logger import Logger

logger = Logger.get_logger()


class DataFilter:
    """数据过滤器 - 负责按键过滤功能"""
    
    def __init__(self):
        """初始化数据过滤器"""
        self.valid_record_data = None
        self.valid_replay_data = None
        
        # 过滤设置
        self.key_filter = set()  # 按键过滤
        
        # 可用按键
        self.available_keys = set()
    
    def set_data(self, valid_record_data=None, valid_replay_data=None):
        """设置有效数据"""
        self.valid_record_data = valid_record_data
        self.valid_replay_data = valid_replay_data
        
        # 更新可用按键
        self._update_available_keys()
    
    def _collect_keys_from_notes(self, notes_data) -> set:
        """从音符数据中收集唯一的按键ID"""
        keys = set()
        if notes_data:
            for note in notes_data:
                if hasattr(note, 'id'):
                    keys.add(note.id)
        return keys
    
    def _update_available_keys(self) -> None:
        """更新可用按键列表"""
        self.available_keys.clear()

        # 从有效数据中收集按键
        self.available_keys.update(self._collect_keys_from_notes(self.valid_record_data))
        self.available_keys.update(self._collect_keys_from_notes(self.valid_replay_data))

        logger.info(f"可用按键更新完成: {len(self.available_keys)}个按键")
    
    def get_available_keys(self) -> List[int]:
        """
        获取可用按键列表
        
        Returns:
            List[int]: 可用按键ID列表
        """
        return sorted(list(self.available_keys))
    
    def set_key_filter(self, key_ids: List[int]) -> None:
        """
        设置按键过滤
        
        Args:
            key_ids: 要过滤的按键ID列表
        """
        if key_ids is None:
            self.key_filter.clear()
            logger.info("按键过滤已清除")
        else:
            self.key_filter = set(key_ids)
            logger.info(f"按键过滤已设置: {len(self.key_filter)}个按键")
    
    def get_key_filter_status(self) -> Dict[str, Any]:
        """
        获取按键过滤状态
        
        Returns:
            Dict[str, Any]: 过滤状态信息
        """
        return {
            'enabled': len(self.key_filter) > 0,
            'filtered_keys': sorted(list(self.key_filter)),
            'total_available_keys': len(self.available_keys),
            'available_keys': sorted(list(self.available_keys))
        }