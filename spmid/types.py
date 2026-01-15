"""
SPMID类型定义模块
统一管理所有SPMID相关的数据类型定义
"""
from dataclasses import dataclass
from typing import List, TYPE_CHECKING

from .spmid_reader import Note


@dataclass
class ErrorNote:
    """
    错误音符信息
    
    重构后直接使用 Note 对象，保留完整的音符数据，便于后续绘制曲线等操作。
    
    Attributes:
        notes: 音符对象列表（直接使用 Note，包含完整的 hammers, after_touch 等数据）
        diffs: 锤击间隔统计列表
        error_type: 错误类型（"多锤" 或 "丢锤" 或 "不发声音符"）
        global_index: 全局索引
        reason: 失败原因（可选）
    """
    notes: List[Note]  # 改为使用 Note 对象，而不是 NoteInfo
    error_type: str = ""      # 错误类型："多锤" 或 "丢锤" 或 "不发声音符"
    global_index: int = -1    # 全局索引
    reason: str = ""         # 失败原因（可选）

