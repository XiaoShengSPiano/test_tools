#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
文件上传服务 - 统一的文件上传处理逻辑

重构目标：
- 统一文件上传入口
"""

import traceback
import asyncio
import base64
import time
from backend.spmid_loader import SPMIDLoader
from typing import Tuple, Optional
from utils.logger import Logger
# 延迟导入，避免循环依赖
# from backend.piano_analysis_backend import PianoAnalysisBackend

logger = Logger.get_logger()


class FileUploadService:
    """
    文件上传服务 - 统一处理所有文件上传逻辑
    
    核心职责：
    1. 文件内容解码和验证
    2. 算法名称验证
    3. 调用 multi_algorithm_manager 添加算法
    4. 自动激活新添加的算法
    """
    
    def __init__(self, multi_algorithm_manager):
        """
        初始化文件上传服务

        Args:
            multi_algorithm_manager: MultiAlgorithmManager 实例
        """
        self.multi_algorithm_manager = multi_algorithm_manager
        logger.info("[OK] FileUploadService 初始化完成")
    
    async def add_file_as_algorithm(
        self, 
        file_content_bytes: bytes, 
        filename: str,
        algorithm_name: str
    ) -> Tuple[bool, str]:
        """
        将文件添加为算法（统一入口）
        
        Args:
            file_content_bytes: 文件内容（二进制数据）
            filename: 文件名
            algorithm_name: 用户指定的算法名称
            
        Returns:
            Tuple[bool, str]: (是否成功, 错误信息)
        """
        try:
            perf_service_start = time.time()
            logger.info(f"    📁 [Backend-Service] 开始处理: {filename}, 算法名: {algorithm_name}")
            
            # ============ 子步骤3.1: 验证算法名 ============
            perf_step31_start = time.time()
            is_valid, error_msg = self._validate_algorithm_name(algorithm_name)
            perf_step31_end = time.time()
            logger.info(f"    ⏱️  [性能] 子步骤3.1-验证算法名: {(perf_step31_end - perf_step31_start)*1000:.2f}ms")
            
            if not is_valid:
                logger.warning(f"⚠️ 算法名验证失败: {error_msg}")
                return False, error_msg
            
            # ============ 子步骤3.2: 验证文件内容 ============
            if not file_content_bytes or len(file_content_bytes) == 0:
                error_msg = "文件内容为空"
                logger.error(f"❌ {error_msg}")
                return False, error_msg
            
            file_size_kb = len(file_content_bytes) / 1024
            logger.info(f"    ✅ 文件大小: {file_size_kb:.2f}KB")
            
            # ============ 子步骤3.3: 加载 SPMID 数据 ============
            perf_step33_start = time.time()
            logger.info(f"    🔄 解析 SPMID 文件...")
            
            loader = SPMIDLoader()
            load_success = loader.load_spmid_data(file_content_bytes)
            
            if not load_success:
                error_msg = "SPMID 文件解析失败"
                logger.error(f"❌ {error_msg}")
                return False, error_msg
            
            # 获取数据
            record_data = loader.get_record_data()
            replay_data = loader.get_replay_data()
            filter_collector = loader.get_filter_collector()
            
            if not record_data or not replay_data:
                error_msg = "SPMID 数据为空"
                logger.error(f"❌ {error_msg}")
                return False, error_msg
            
            perf_step33_end = time.time()
            logger.info(f"    ⏱️  [性能] 子步骤3.3-SPMID解析: {(perf_step33_end - perf_step33_start)*1000:.2f}ms")
            logger.info(f"    ✅ 音符数量: 录制={len(record_data)}, 播放={len(replay_data)}")
            
            # ============ 子步骤3.4: 添加算法到管理器 ============
            perf_step34_start = time.time()
            logger.info(f"    🔄 添加算法到 multi_algorithm_manager...")
            
            success, result = await self.multi_algorithm_manager.add_algorithm_async(
                algorithm_name,
                filename,
                record_data,   # List[Note]
                replay_data,   # List[Note]
                filter_collector  # FilterCollector (包含加载阶段的过滤信息)
            )
            
            perf_step34_end = time.time()
            logger.info(f"    ⏱️  [性能] 子步骤3.4-算法添加及分析: {(perf_step34_end - perf_step34_start)*1000:.2f}ms")
            
            if not success:
                logger.error(f"❌ 算法添加失败: {result}")
                return False, result
            
            # success=True 时，result 是 unique_algorithm_name
            unique_algorithm_name = result
            
            # ============ 子步骤3.5: 自动激活算法 ============
            perf_step35_start = time.time()
            algorithm = self.multi_algorithm_manager.get_algorithm(unique_algorithm_name)
            if algorithm:
                algorithm.is_active = True
                logger.info(f"    ✅ 算法 '{algorithm_name}' ({unique_algorithm_name}) 已自动激活")
            else:
                logger.warning(f"    ⚠️ 算法 '{algorithm_name}' 添加成功，但无法获取实例进行激活（唯一标识: {unique_algorithm_name}）")
            perf_step35_end = time.time()
            logger.info(f"    ⏱️  [性能] 子步骤3.5-激活算法: {(perf_step35_end - perf_step35_start)*1000:.2f}ms")
            
            # ============ Service层总耗时 ============
            perf_service_end = time.time()
            service_time_ms = (perf_service_end - perf_service_start) * 1000
            logger.info(f"    🏁 [Backend-Service] 处理完成，耗时: {service_time_ms:.2f}ms")
            
            return True, ""
            
        except Exception as e:
            error_msg = f"文件上传处理异常: {str(e)}"
            logger.error(f"❌ {error_msg}")
            import traceback
            logger.error(traceback.format_exc())
            return False, error_msg
    
    def _validate_algorithm_name(self, algorithm_name: str) -> Tuple[bool, str]:
        """
        验证算法名称
        
        Args:
            algorithm_name: 算法名称
            
        Returns:
            Tuple[bool, str]: (是否有效, 错误信息)
        """
        if not algorithm_name or not algorithm_name.strip():
            return False, "算法名称不能为空"
        
        algorithm_name = algorithm_name.strip()
        
        # 检查算法名是否已存在
        if self.multi_algorithm_manager:
            existing_algorithm = self.multi_algorithm_manager.get_algorithm(algorithm_name)
            if existing_algorithm:
                return False, f"算法名称 '{algorithm_name}' 已存在，请使用其他名称"
        
        return True, ""
    
    @staticmethod
    def decode_base64_file_content(file_content: str) -> Optional[bytes]:
        """
        解码 base64 文件内容（静态方法，供UI层使用）
        
        统一处理 base64 解码逻辑，支持以下格式：
        1. "data:application/octet-stream;base64,{base64_data}"
        2. "{base64_data}"
        
        Args:
            file_content: base64 编码的文件内容
            
        Returns:
            Optional[bytes]: 解码后的二进制数据，失败返回 None
        """
        try:
            if not file_content:
                return None
            
            # 处理 "data:mime;base64,data" 格式
            if ',' in file_content:
                file_content = file_content.split(',', 1)[1]
            
            # 解码 base64
            decoded_bytes = base64.b64decode(file_content)
            
            logger.info(f"✅ 文件内容解码成功，大小: {len(decoded_bytes)} 字节")
            return decoded_bytes
            
        except Exception as e:
            logger.error(f"❌ 文件内容解码失败: {e}")
            return None
    
    def validate_file_upload(self, file_content: str, filename: str) -> Tuple[bool, str]:
        """
        验证文件上传（用于UI层的预验证）
        
        Args:
            file_content: 文件内容
            filename: 文件名
            
        Returns:
            Tuple[bool, str]: (是否有效, 错误信息)
        """
        # 验证文件名
        if not filename or not filename.strip():
            return False, "文件名不能为空"
        
        if not filename.lower().endswith('.spmid'):
            return False, "只支持 .spmid 文件"
        
        # 验证文件内容
        if not file_content:
            return False, "文件内容为空"
        
        return True, ""

