"""
文件上传管理器 - 统一处理文件上传逻辑，消除冗余
"""
import logging
from typing import Optional, Tuple, Dict, Any
from backend.piano_analysis_backend import PianoAnalysisBackend

logger = logging.getLogger(__name__)


class UploadManager:
    """文件上传管理器 - 统一处理所有上传相关逻辑"""

    def __init__(self, backend: PianoAnalysisBackend):
        self.backend = backend

    def process_upload(self, contents: Optional[str], filename: Optional[str]) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        统一的文件上传处理入口

        Args:
            contents: 上传文件的内容（base64编码）
            filename: 上传文件的文件名

        Returns:
            tuple: (success, data, error_msg)
        """
        logger.info(f"🎯 统一上传管理器收到文件上传: {filename}")

        # 1. 清理旧状态（总是允许重新上传）
        self._clear_upload_state()
        logger.info("🔄 已清理上传状态，允许重新上传")

        # 2. 验证输入
        validation_result = self._validate_upload_input(contents, filename)
        if not validation_result[0]:
            return validation_result

        # 3. 处理文件上传
        try:
            return self.backend.data_manager.process_file_upload(contents, filename, self.backend.history_manager)
        except Exception as e:
            logger.error(f"❌ 文件上传处理异常: {e}")
            return False, None, f"文件处理异常: {str(e)}"

    def _clear_upload_state(self) -> None:
        """清理上传相关状态"""
        self.backend._last_upload_content = None
        self.backend._last_upload_time = None
        self.backend._last_selected_history_id = None
        self.backend._last_history_time = None
        self.backend._data_source = None

    def _validate_upload_input(self, contents: Optional[str], filename: Optional[str]) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """验证上传输入"""
        if not contents:
            logger.warning("❌ 文件内容为空")
            return False, None, "文件内容为空"

        if not filename:
            logger.warning("❌ 文件名为空")
            return False, None, "文件名为空"

        logger.info(f"✅ 上传输入验证通过: {filename} (内容长度: {len(contents)})")
        return True, None, None

    def clear_all_states(self) -> None:
        """清理所有相关状态"""
        self._clear_upload_state()
        self.backend.clear_data_state()
        logger.info("🧹 已清理所有上传和数据状态")
