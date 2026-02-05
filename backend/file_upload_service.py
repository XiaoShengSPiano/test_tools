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
import datetime
from backend.spmid_loader import SPMIDLoader
from typing import Tuple, Optional
from utils.logger import Logger


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
    
    def __init__(self, multi_algorithm_manager, history_manager=None):
        """
        初始化文件上传服务

        Args:
            multi_algorithm_manager: MultiAlgorithmManager 实例
            history_manager: SQLiteHistoryManager 实例 (V3)
        """
        self.multi_algorithm_manager = multi_algorithm_manager
        self.history_manager = history_manager
        logger.debug("[DEBUG] FileUploadService 初始化完成")
    
    async def add_file_as_algorithm(
        self,
        file_content_bytes: bytes,
        filename: str,
        algorithm_name: str,
        motor_type: str = "D3",
        algorithm_type: str = "PID",
        piano_type: str = "Grand",
        creation_time: Optional[int] = None
    ) -> Tuple[bool, str]:
        """
        将文件添加为算法（统一入口）

        Args:
            file_content_bytes: 文件内容（二进制数据）
            filename: 文件名
            algorithm_name: 用户指定的算法名称
            motor_type: 电机类型
            algorithm_type: 算法类型
            piano_type: 钢琴型号

        Returns:
            Tuple[bool, str]: (是否成功, 错误信息)
        """
        try:
            logger.debug(f"[DEBUG] 开始处理文件: {filename}, 算法显示名: {algorithm_name}")
            logger.debug(f"[DEBUG] 元数据: 电机={motor_type}, 算法={algorithm_type}, 钢琴={piano_type}")

            # 验证算法名
            is_valid, error_msg = self._validate_algorithm_name(algorithm_name)
            if not is_valid:
                logger.warning(f"算法名验证失败: {error_msg}")
                return False, error_msg

            # 验证文件内容
            if not file_content_bytes or len(file_content_bytes) == 0:
                error_msg = "文件内容为空"
                logger.error(error_msg)
                return False, error_msg

            # 1. 计算文件 MD5
            import hashlib
            file_md5 = hashlib.md5(file_content_bytes).hexdigest()
            logger.debug(f"[DEBUG] 文件 MD5: {file_md5}")

            # 2. 检查数据库中是否存在 (如果是新上传，我们通常还是重新解析以确保最新，或者从DB读)
            # 这里我们选择解析 SPMID 获得 OptimizedNote，然后存入数据库
            
            # 加载 SPMID 数据
            logger.debug("解析 SPMID 文件...")
            
            # 我们需要获取原始的 OptimizedNote 列表以便存入 Parquet
            from spmid.spmid_reader import OptimizedSPMidReader
            reader = OptimizedSPMidReader(file_content_bytes)
            if reader.track_count < 2:
                return False, f"SPMID 文件音轨不足: {reader.track_count}"
            
            # 获取所有音轨 (List[List[OptimizedNote]])
            all_tracks = [reader.get_track(i) for i in range(reader.track_count)]
            
            # 3. 保存到历史记录 (如果不存在)
            if self.history_manager:
                # 获取文件最后修改时间 (User Request: 仅使用此时间)
                if creation_time:
                    try:
                        ts = creation_time / 1000.0 if creation_time > 2e11 else creation_time
                        file_date = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                    except Exception as e:
                        logger.warning(f"解析文件修改时间失败: {e}")
                        file_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                else:
                    file_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                logger.debug(f"💾 使用文件日期: {file_date}")
                
                # save_record 会自动处理去重和 Parquet 存储
                record_id = self.history_manager.save_record(
                    filename=algorithm_name,
                    file_md5=file_md5,
                    motor_type=motor_type,
                    algorithm=algorithm_type,
                    piano_type=piano_type,
                    file_date=file_date,
                    track_data=all_tracks
                )
                if record_id:
                    logger.debug(f"✅ 记录已同步到数据库: ID={record_id}")
                else:
                    logger.debug(f"ℹ️ 数据库中已存在相同文件，记录已更新或跳过")

            # 4. 继续原来的内存分析流程 (使用 SPMIDLoader 将 OptimizedNote 转换为 Note)
            loader = SPMIDLoader()
            # 注意：SPMIDLoader.load_spmid_data 内部会重新创建 reader，虽然有点冗余但保证了兼容性逻辑（如过滤）
            load_success = loader.load_spmid_data(file_content_bytes)

            if not load_success:
                error_msg = "SPMID 文件解析失败（加载阶段）"
                logger.error(error_msg)
                return False, error_msg

            # 获取数据
            record_data = loader.get_record_data()
            replay_data = loader.get_replay_data()
            filter_collector = loader.get_filter_collector()

            if not record_data or not replay_data:
                error_msg = "SPMID 数据为空"
                logger.error(error_msg)
                return False, error_msg

            logger.info(f"   音符数量: 录制={len(record_data)}, 播放={len(replay_data)}")

            # 添加算法到管理器
            success, result = await self.multi_algorithm_manager.add_algorithm_async(
                algorithm_name,
                filename,
                record_data,   # List[Note]
                replay_data,   # List[Note]
                filter_collector  # FilterCollector (包含加载阶段的过滤信息)
            )

            if not success:
                logger.error(f"算法添加失败: {result}")
                return False, result

            # success=True 时，result 是 unique_algorithm_name
            unique_algorithm_name = result

            # 自动激活算法
            algorithm = self.multi_algorithm_manager.get_algorithm(unique_algorithm_name)
            if algorithm:
                algorithm.is_active = True
                logger.info(f"算法 '{algorithm_name}' 已自动激活")
            else:
                logger.warning(f"算法 '{algorithm_name}' 添加成功，但无法激活")

            return True, ""

        except Exception as e:
            error_msg = f"文件上传处理异常: {str(e)}"
            logger.error(error_msg)
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
            
            logger.debug(f"[DEBUG] 文件内容解码成功，大小: {len(decoded_bytes)} 字节")
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

