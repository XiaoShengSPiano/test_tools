#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
会话管理器

负责管理用户会话和后端实例，支持多用户并发访问。
"""

import uuid
import time
import threading
import os
from typing import Dict, Optional, Tuple
from backend.piano_analysis_backend import PianoAnalysisBackend
import os
from utils.logger import Logger

logger = Logger.get_logger()


class SessionManager:
    """
    会话管理器类
    
    负责管理用户会话和后端实例，支持多用户并发访问。
    每个会话都有独立的backend实例，确保数据隔离。
    """
    
    def __init__(self, history_manager):
        """
        初始化会话管理器
        
        Args:
            history_manager: 全局历史管理器实例
        """
        self.history_manager = history_manager
        self.backends: Dict[str, PianoAnalysisBackend] = {}  # session_id -> backend
        self.session_activity: Dict[str, float] = {}  # session_id -> last_activity_time
        self.lock = threading.Lock()  # 线程锁，确保线程安全
        # 只在主进程中记录初始化日志（避免Flask debug模式下的重复日志）
        if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
            logger.info("SessionManager初始化完成")
    
    def get_or_create_backend(self, session_id: Optional[str] = None) -> Tuple[str, PianoAnalysisBackend]:
        """
        获取或创建后端实例
        
        Args:
            session_id: 会话ID，如果为None则创建新会话
            
        Returns:
            tuple: (session_id, backend)
        """
        with self.lock:
            # 如果没有提供session_id，创建新会话
            if not session_id:
                session_id = str(uuid.uuid4())
                logger.info(f"创建新会话: {session_id}")
            
            # 如果会话不存在，创建新的backend实例
            if session_id not in self.backends:
                self.backends[session_id] = PianoAnalysisBackend(session_id, self.history_manager)
                logger.debug(f"✅ 为会话 {session_id} 创建backend实例")
            
            # 更新活动时间
            self.session_activity[session_id] = time.time()
            
            return session_id, self.backends[session_id]
    
    def get_backend(self, session_id: str) -> Optional[PianoAnalysisBackend]:
        """
        获取后端实例
        
        Args:
            session_id: 会话ID
            
        Returns:
            Optional[PianoAnalysisBackend]: 后端实例，如果不存在则返回None
        """
        with self.lock:
            return self.backends.get(session_id)
    
    def remove_session(self, session_id: str) -> bool:
        """
        移除会话
        
        Args:
            session_id: 会话ID
            
        Returns:
            bool: 是否成功移除
        """
        with self.lock:
            if session_id in self.backends:
                del self.backends[session_id]
                if session_id in self.session_activity:
                    del self.session_activity[session_id]
                logger.info(f"🗑️ 移除会话: {session_id}")
                return True
            return False
    
    def cleanup_inactive_sessions(self, inactive_threshold: int = 30 * 60) -> int:
        """
        清理长时间未活动的会话
        
        Args:
            inactive_threshold: 未活动时间阈值（秒），默认30分钟
            
        Returns:
            int: 清理的会话数量
        """
        with self.lock:
            current_time = time.time()
            inactive_sessions = []
            
            for session_id, last_activity in self.session_activity.items():
                if current_time - last_activity > inactive_threshold:
                    inactive_sessions.append(session_id)
            
            for session_id in inactive_sessions:
                self.remove_session(session_id)
            
            if inactive_sessions:
                logger.info(f"🧹 清理了 {len(inactive_sessions)} 个未活动会话")
            
            return len(inactive_sessions)
    
    def get_session_count(self) -> int:
        """获取当前活跃会话数量"""
        with self.lock:
            return len(self.backends)
    
    def update_activity(self, session_id: str) -> None:
        """更新会话活动时间"""
        with self.lock:
            if session_id in self.backends:
                self.session_activity[session_id] = time.time()

