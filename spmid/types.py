"""
SPMID类型定义模块
统一管理所有SPMID相关的数据类型定义
"""
from dataclasses import dataclass
from typing import List


@dataclass
class NoteInfo:
    """音符信息"""
    index: int
    keyId: int
    keyOn: int
    keyOff: int


@dataclass
class Diffs:
    """锤击间隔统计信息"""
    mean: float
    std: float
    max: float
    min: float


@dataclass
class ErrorNote:
    """错误音符信息"""
    infos: List[NoteInfo]
    diffs: List[Diffs]
    error_type: str = ""      # 错误类型："多锤" 或 "丢锤"
    global_index: int = -1    # 全局索引


# 备用类型定义（用于导入失败时的容错处理）
@dataclass
class FallbackNoteInfo:
    """备用音符信息"""
    index: int = 0
    keyId: int = 0
    keyOn: int = 0
    keyOff: int = 0


@dataclass
class FallbackDiffs:
    """备用锤击间隔统计信息"""
    mean: float = 0.0
    std: float = 0.0
    max: float = 0.0
    min: float = 0.0


@dataclass
class FallbackErrorNote:
    """备用错误音符信息"""
    infos: List[FallbackNoteInfo] = None
    diffs: List[FallbackDiffs] = None
    error_type: str = ""
    global_index: int = -1

    def __post_init__(self):
        if self.infos is None:
            self.infos = []
        if self.diffs is None:
            self.diffs = []
