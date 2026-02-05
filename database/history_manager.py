import sqlite3
import os
import threading
from dataclasses import dataclass, asdict
from typing import Optional, List
from pathlib import Path
from spmid.spmid_reader import OptimizedNote

from abc import ABC, abstractmethod

@dataclass
class ParquetRecord:
    """Parquet 存储记录模型 - 最终设计版"""
    filename: str            # 原始文件名
    file_md5: str             # 文件 MD5 值
    motor_type: str           # 电机类型 (D3/D4)
    algorithm: str            # 算法类型 (PID/SMC)
    piano_type: str           # 琴类型
    file_date: str            # 文件创建日期
    track_data_path: str      # 单个 Parquet 文件路径
    id: Optional[int] = None

class BaseHistoryManager(ABC):
    """历史记录管理器抽象基类，支持多种数据库后端"""

    @abstractmethod
    def init_storage(self) -> None:
        """初始化存储（如创建表、建立连接等）"""
        pass

    @abstractmethod
    def save_record(self, record: ParquetRecord) -> Optional[int]:
        """保存历史记录并返回 ID，若已存在则返回现有 ID"""
        pass

    @abstractmethod
    def get_all_records(self, limit: int = 20) -> List[dict]:
        """获取最近的历史记录列表"""
        pass

    @abstractmethod
    def get_record_by_id(self, record_id: int) -> Optional[dict]:
        """通过 ID 获取单条记录"""
        pass

    @abstractmethod
    def get_records_by_filename(self, filename: str) -> List[dict]:
        """通过文件名获取记录列表"""
        pass

    @abstractmethod
    def delete_record_by_id(self, record_id: int) -> bool:
        """通过 ID 删除记录"""
        pass

class SQLiteHistoryManager(BaseHistoryManager):
    """基于 SQLite 的历史记录管理器实现"""
    
    def __init__(self, db_path: str = "track_data.db"):
        self.db_path = db_path
        self.table_name = "track_data"
        self._lock = threading.RLock()
        self.init_storage()

    def init_storage(self) -> None:
        """初始化数据库表结构"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT,
                    file_md5 TEXT UNIQUE,
                    motor_type TEXT,
                    algorithm TEXT,
                    piano_type TEXT,
                    file_date TEXT,
                    track_data_path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            conn.close()

    def save_record(self, filename: str, file_md5: str, motor_type: str, 
                   algorithm: str, piano_type: str, file_date: str, 
                   track_data: List[List['OptimizedNote']]) -> Optional[int]:
        """
        保存记录到数据库及 Parquet 文件 (V3 高级接口)
        
        此方法会自动：
        1. 检查 MD5 是否已存在
        2. 如果不存在，保存 track_data 到 Parquet 文件
        3. 将 元数据 + Parquet 路径 写入数据库
        """
        with self._lock:
            # 1. 查重
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(f"SELECT id, track_data_path FROM {self.table_name} WHERE file_md5 = ?", (file_md5,))
            row = cursor.fetchone()
            
            if row:
                conn.close()
                return row[0]  # 已存在，直接返回 ID

            # 2. 准备 Parquet 存储路径
            # 存储在 track_data 文件夹下，以 MD5 命名
            storage_dir = Path("track_data_storage")
            storage_dir.mkdir(exist_ok=True)
            parquet_path = storage_dir / f"{file_md5}.parquet"
            
            # 3. 保存 Parquet 文件
            from .parquet_utility import ParquetUtility
            try:
                ParquetUtility.save_parquet(track_data, str(parquet_path))
            except Exception as e:
                conn.close()
                raise IOError(f"Failed to save Parquet file: {e}")

            # 4. 插入数据库
            try:
                cursor.execute(f'''
                    INSERT INTO {self.table_name} 
                    (filename, file_md5, motor_type, algorithm, piano_type, file_date, track_data_path, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
                ''', (
                    filename, file_md5, motor_type, algorithm, piano_type, file_date, str(parquet_path.absolute())
                ))
                record_id = cursor.lastrowid
                conn.commit()
                return record_id
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    def get_all_records(self, limit: int = 20) -> List[dict]:
        """获取最近的历史记录"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM {self.table_name} ORDER BY id DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]

    def get_record_by_id(self, record_id: int) -> Optional[dict]:
        """通过 ID 获取记录"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM {self.table_name} WHERE id = ?", (record_id,))
            row = cursor.fetchone()
            conn.close()
            return dict(row) if row else None

    def get_record_by_md5(self, file_md5: str) -> Optional[dict]:
        """通过 MD5 获取单条记录"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM {self.table_name} WHERE file_md5 = ?", (file_md5,))
            row = cursor.fetchone()
            conn.close()
            return dict(row) if row else None

    def get_records_by_filename(self, filename: str) -> List[dict]:
        """通过文件名筛选记录"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            # 支持模糊查询或精确查询，这里默认精确
            cursor.execute(f"SELECT * FROM {self.table_name} WHERE filename = ? ORDER BY created_at DESC", (filename,))
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]

    def delete_record_by_id(self, record_id: int, delete_file: bool = True) -> bool:
        """
        通过 ID 删除记录
        
        Args:
            record_id: 数据库记录 ID
            delete_file: 是否同时从磁盘删除关联的 Parquet 文件
        """
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 1. 查找文件路径（以便删除文件）
            cursor.execute(f"SELECT track_data_path FROM {self.table_name} WHERE id = ?", (record_id,))
            row = cursor.fetchone()
            
            if not row:
                conn.close()
                return False
                
            file_path = row['track_data_path']
            
            # 2. 从数据库删除记录
            cursor.execute(f"DELETE FROM {self.table_name} WHERE id = ?", (record_id,))
            deleted = cursor.rowcount > 0
            
            conn.commit()
            conn.close()
            
            # 3. 删除物理文件
            if deleted and delete_file and file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"警告: 数据库记录已删除，但无法删除 Parquet 文件: {e}")
            
            return deleted

class ParquetDataLoader:
    """数据加载器封装：将数据库记录转换为音轨数据"""
    
    @staticmethod
    def load_from_record(record: dict):
        """
        从数据库记录加载音轨数据（List[List[OptimizedNote]]）
        
        Args:
            record: 包含 track_data_path 的数据库记录字典
        """
        from .parquet_utility import ParquetUtility
        path = record.get("track_data_path")
        if not path or not os.path.exists(path):
            raise FileNotFoundError(f"Parquet file does not exist: {path}")
        
        tracks = ParquetUtility.load_parquet(path)
        return tracks
