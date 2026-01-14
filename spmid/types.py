"""
SPMID类型定义模块
统一管理所有SPMID相关的数据类型定义
"""
from dataclasses import dataclass
from typing import List, TYPE_CHECKING

# 使用 TYPE_CHECKING 避免循环导入，同时保持类型提示
if TYPE_CHECKING:
    from .spmid_reader import Note


@dataclass
class Diffs:
    """锤击间隔统计信息"""
    mean: float
    std: float
    max: float
    min: float


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
    notes: List['Note']  # 改为使用 Note 对象，而不是 NoteInfo
    diffs: List[Diffs]
    error_type: str = ""      # 错误类型："多锤" 或 "丢锤" 或 "不发声音符"
    global_index: int = -1    # 全局索引
    reason: str = ""         # 失败原因（可选）
    
    # 为了向后兼容，提供 infos 属性（映射到 notes）
    @property
    def infos(self) -> List['Note']:
        """向后兼容属性：infos 映射到 notes"""
        return self.notes

