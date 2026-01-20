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
    
    直接使用 Note 对象，通过 note.uuid 唯一标识音符。
    
    Attributes:
        note: 音符对象（包含 uuid, hammers, after_touch 等完整数据）
        error_type: 错误类型（"多锤" 或 "丢锤" 或 "异常匹配对"）
        reason: 失败原因（可选）
    
    通过 note.uuid 访问音符的唯一标识符
    """
    note: Note                # Note 对象（含uuid属性）
    error_type: str = ""      # 错误类型
    reason: str = ""          # 失败原因

