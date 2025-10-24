#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SPMID加载器
专门负责SPMID文件的加载和验证
"""

import os
import tempfile
import traceback
from typing import Optional, Tuple
from utils.logger import Logger

# SPMID相关导入
import spmid

logger = Logger.get_logger()


class SPMIDLoader:
    """SPMID加载器 - 专门负责SPMID文件的加载和验证"""
    
    def __init__(self):
        """初始化SPMID加载器"""
        self.logger = logger
        self.record_data = None
        self.replay_data = None
    
    def clear_data(self) -> None:
        """清理加载的数据"""
        self.record_data = None
        self.replay_data = None
        self.logger.info("✅ SPMID数据已清理")
    
    def load_spmid_data(self, spmid_bytes: bytes) -> bool:
        """
        加载SPMID数据
        
        Args:
            spmid_bytes: SPMID文件字节数据
            
        Returns:
            bool: 是否加载成功
        """
        try:
            # 创建临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix='.spmid') as temp_file:
                temp_file.write(spmid_bytes)
                temp_file_path = temp_file.name
            
            try:
                # 加载音轨数据
                success, error_msg = self._load_track_data(temp_file_path)
                if success:
                    self.logger.info("✅ SPMID数据加载完成")
                    return True
                else:
                    self.logger.error(f"❌ SPMID数据加载失败: {error_msg}")
                    return False
            finally:
                # 清理临时文件
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                    
        except Exception as e:
            self.logger.error(f"❌ SPMID数据加载异常: {e}")
            self.logger.error(traceback.format_exc())
            return False
    
    def get_record_data(self):
        """获取录制数据"""
        return self.record_data
    
    def get_replay_data(self):
        """获取播放数据"""
        return self.replay_data
    
    # ==================== 私有方法 ====================
    
    def _load_track_data(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        加载音轨数据
        
        Args:
            file_path: SPMID文件路径
            
        Returns:
            tuple: (是否成功, 错误信息)
        """
        try:
            with spmid.SPMidReader(file_path) as reader:
                # 检查音轨数量
                track_count = reader.get_track_count
                if track_count < 2:
                    return False, f"SPMID文件音轨数量不足，需要至少2个音轨，当前只有{track_count}个"
                
                # 加载录制音轨（第0个音轨）
                self.record_data = reader.get_track(0)
                if not self.record_data:
                    return False, "录制音轨数据为空"
                
                # 加载播放音轨（第1个音轨）
                self.replay_data = reader.get_track(1)
                if not self.replay_data:
                    return False, "播放音轨数据为空"
                
                self.logger.info(f"✅ 音轨数据加载成功 - 录制: {len(self.record_data)} 个音符, 播放: {len(self.replay_data)} 个音符")
                return True, None
                
        except Exception as e:
            error_msg = f"音轨数据加载失败: {str(e)}"
            self.logger.error(f"❌ {error_msg}")
            self.logger.error(traceback.format_exc())
            return False, error_msg

