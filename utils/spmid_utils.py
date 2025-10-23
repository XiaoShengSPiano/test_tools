"""
SPMID工具模块 - 处理SPMID相关的导入和备用实现
"""
import os
import sys
from utils.logger import Logger

logger = Logger.get_logger()

# 导入SPMID相关模块
try:
    from spmid.types import NoteInfo, Diffs, ErrorNote
    from spmid.spmid_analyzer import spmid_analysis
    from spmid.spmid_reader import SPMidReader
    SPMID_AVAILABLE = True
except ImportError as e:
    logger.warning(f"⚠️ SPMID模块导入失败 (utils): {e}")
    SPMID_AVAILABLE = False

    # 使用统一的备用类型定义
    from spmid.types import FallbackNoteInfo as NoteInfo, FallbackDiffs as Diffs, FallbackErrorNote as ErrorNote

    def spmid_analysis(*args):
        """备用的SPMID分析函数，返回空结果"""
        return [], [], []
    
    class SPMidReader:
        """备用的SPMID读取器类"""
        def __init__(self, *args):
            pass
        def get_track(self, *args):
            return []

# 导出模块级别的变量和函数
__all__ = ['NoteInfo', 'Diffs', 'ErrorNote', 'spmid_analysis', 'SPMidReader', 'SPMID_AVAILABLE']