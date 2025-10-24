#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据管理模块
负责数据加载、文件上传处理等核心功能
"""

import base64
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
    
    def set_analysis_results(self, valid_record_data, valid_replay_data):
        """设置分析结果数据"""
        self.valid_record_data = valid_record_data
        self.valid_replay_data = valid_replay_data
    
    def get_valid_record_data(self):
        """获取有效录制数据"""
        return self.valid_record_data
    
    def get_valid_replay_data(self):
        """获取有效回放数据"""
        return self.valid_replay_data
    
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
    
    # ==================== 文件上传处理相关方法 ====================
    
    def process_file_upload(self, contents, filename, history_manager):
        """
        处理文件上传
        
        Args:
            contents: 上传文件的内容（base64编码）
            filename: 上传文件的文件名
            history_manager: 历史记录管理器
            
        Returns:
            tuple: (success, data, error_msg)
                   - success: 是否成功
                   - data: 成功时的数据字典，包含filename, record_count, replay_count, history_id
                   - error_msg: 失败时的错误信息
        """
        try:
            logger.info(f"新文件上传: {filename}")
            
            # 验证输入参数
            if not contents:
                return False, None, "文件内容为空"
            
            if not filename:
                return False, None, "文件名为空"
            
            # 初始化上传状态
            self._initialize_upload_state(filename)
            
            # 解码文件内容
            decoded_bytes = self._decode_file_contents(contents)
            
            # 加载SPMID数据
            success, error_msg = self._load_spmid_data(decoded_bytes)
            
            if success:
                # 处理上传成功的情况
                return self._handle_upload_success(filename, history_manager)
            else:
                # 处理上传失败的情况
                return False, None, error_msg

        except Exception as e:
            logger.error(f"❌ 文件处理错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, None, str(e)
    
    def _initialize_upload_state(self, filename):
        """初始化文件上传状态"""
        self.clear_data_state()
        self.set_upload_data_source(filename)

    def _decode_file_contents(self, contents):
        """解码文件内容"""
        try:
            # 验证contents格式
            if not isinstance(contents, str):
                raise ValueError("文件内容必须是字符串格式")
            
            if ',' not in contents:
                raise ValueError("文件内容格式错误，缺少分隔符")
            
            content_type, content_string = contents.split(',', 1)
            
            if not content_string:
                raise ValueError("文件内容为空")
            
            # 验证是否为base64格式
            if not content_string.strip():
                raise ValueError("文件内容为空")
            
            return base64.b64decode(content_string)
            
        except ValueError as e:
            logger.error(f"❌ 文件内容格式错误: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ 文件解码失败: {e}")
            raise ValueError(f"文件解码失败: {str(e)}")

    def _load_spmid_data(self, decoded_bytes):
        """加载SPMID数据"""
        success = False
        error_msg = None
        
        try:
            success = self.spmid_loader.load_spmid_data(decoded_bytes)
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ 文件处理错误: {error_msg}")
            import traceback
            logger.error(traceback.format_exc())
        
        return success, error_msg

    def _handle_upload_success(self, filename, history_manager):
        """处理文件上传成功的情况"""
        # 保存分析结果到历史记录
        history_id = history_manager.save_analysis_result(filename, self)
        
        # 记录成功信息
        self._log_upload_success(filename, history_id)
        
        # 返回成功数据
        data = {
            'filename': filename,
            'record_count': len(self.get_record_data()),
            'replay_count': len(self.get_replay_data()),
            'history_id': history_id
        }
        
        return True, data, None

    def _log_upload_success(self, filename, history_id):
        """记录文件上传成功信息"""
        logger.info(f"✅ 文件上传处理完成 - {filename}")
        logger.info(f"📊 数据统计: 录制 {len(self.get_record_data())} 个音符, 播放 {len(self.get_replay_data())} 个音符")
        logger.info(f"💾 历史记录ID: {history_id}")