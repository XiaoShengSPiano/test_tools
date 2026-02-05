#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据管理模块
负责数据加载、文件上传处理等核心功能
"""
import traceback
from typing import Optional, Tuple, Dict, Any
from utils.logger import Logger
# 导入各个专门的处理模块
from .spmid_loader import SPMIDLoader

logger = Logger.get_logger()


class DataManager:
    """数据管理器 - 作为协调器，处理各个专门的数据处理模块"""
    
    def __init__(self):
        """初始化数据管理器"""
        # 初始化各个专门的处理模块
        self.spmid_loader = SPMIDLoader()
        
        # 数据源信息
        self.data_source_info = {
            'type': None,
            'filename': None,
            'history_id': None
        }
        
        # 分析结果数据
        self.valid_record_data = None
        self.valid_replay_data = None
        
        logger.info("✅ DataManager初始化完成")
    
    def clear_data_state(self) -> None:
        """清理所有数据状态"""
        self.data_source_info = {
            'type': None,
            'filename': None,
            'history_id': None
        }
        self.valid_record_data = None
        self.valid_replay_data = None
        self.spmid_loader.clear_data()
        logger.info("✅ 数据状态已清理")
    
    def set_upload_data_source(self, filename: str) -> None:
        """设置上传数据源信息"""
        self.data_source_info = {
            'type': 'upload',
            'filename': filename,
            'history_id': None
        }
        logger.info(f"✅ 设置上传数据源: {filename}")
    
    def set_history_data_source(self, history_id: str, filename: str) -> None:
        """设置历史数据源信息"""
        self.data_source_info = {
            'type': 'history',
            'filename': filename,
            'history_id': history_id
        }
        logger.info(f"✅ 设置历史数据源: {filename} (ID: {history_id})")
    
    def get_data_source_info(self) -> Dict[str, Any]:
        """获取数据源信息"""
        return self.data_source_info.copy()
    
    def get_data_source_type(self) -> Optional[str]:
        """获取数据源类型"""
        return self.data_source_info.get('type')
    
    def get_filename(self) -> Optional[str]:
        """获取文件名"""
        return self.data_source_info.get('filename')
    
    def get_history_id(self) -> Optional[str]:
        """获取历史记录ID"""
        return self.data_source_info.get('history_id')
    
    def is_upload_source(self) -> bool:
        """判断是否为上传数据源"""
        return self.data_source_info.get('type') == 'upload'

    def is_history_source(self) -> bool:
        """判断是否为历史数据源"""
        return self.data_source_info.get('type') == 'history'
    
    def load_spmid_data(self, spmid_bytes: bytes) -> bool:
        """
        加载SPMID数据
        
        Args:
            spmid_bytes: SPMID文件字节数据
            
        Returns:
            bool: 是否加载成功
        """
        return self.spmid_loader.load_spmid_data(spmid_bytes)
    
    def get_record_data(self):
        """获取录制数据"""
        return self.spmid_loader.get_record_data()
    
    def get_replay_data(self):
        """获取播放数据"""
        return self.spmid_loader.get_replay_data()
    
    def get_filter_collector(self):
        """获取过滤信息收集器"""
        return self.spmid_loader.get_filter_collector()