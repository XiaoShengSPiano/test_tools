"""
Parquet 转换与存储工具
专门负责 OptimizedNote 列表与 Parquet 文件之间的转换
不包含任何 SPMID 解析逻辑，仅处理结构化数据持久化
"""
import numpy as np
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional
from spmid.spmid_reader import OptimizedNote

class ParquetUtility:
    """Parquet 持久化工具类"""

    @staticmethod
    def notes_to_dataframe(tracks: List[List[OptimizedNote]]) -> pd.DataFrame:
        """
        将 OptimizedNote 列表转换为适合 Parquet 存储的 DataFrame
        """
        records = []
        for track_idx, track in enumerate(tracks):
            for note in track:
                record = {
                    'track': track_idx,
                    'note_offset': note.offset,
                    'note_id': note.id,
                    'finger': note.finger,
                    'velocity': note.velocity,
                    'uuid': note.uuid,
                    # 序列化 NumPy 数组为 bytes 以便高效存储
                    'hammers_ts': note.hammers_ts.tobytes(),
                    'hammers_val': note.hammers_val.tobytes(),
                    'after_ts': note.after_ts.tobytes(),
                    'after_val': note.after_val.tobytes(),
                }
                records.append(record)
        return pd.DataFrame(records)

    @staticmethod
    def save_parquet(tracks: List[List[OptimizedNote]], output_path: str, compression: str = 'snappy') -> str:
        """
        保存音轨数据到 Parquet
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        df = ParquetUtility.notes_to_dataframe(tracks)
        df.to_parquet(path, index=False, compression=compression)
        return str(path)

    @staticmethod
    def load_parquet(file_path: str) -> List[List[OptimizedNote]]:
        """
        从 Parquet 加载数据并还原为项目标准的 OptimizedNote 列表
        """
        if not Path(file_path).exists():
            raise FileNotFoundError(f"Parquet file not found: {file_path}")
            
        df = pd.read_parquet(file_path)
        tracks: List[List[OptimizedNote]] = []
        
        # 按 track 索引分组恢复
        for track_idx in sorted(df['track'].unique()):
            track_df = df[df['track'] == track_idx]
            track_notes = []
            # 使用 itertuples 替代 iterrows 提升性能
            for row in track_df.itertuples(index=False):
                note = OptimizedNote(
                    offset=int(row.note_offset),
                    id=int(row.note_id),
                    finger=int(row.finger),
                    velocity=int(row.velocity),
                    uuid=row.uuid,
                    # 从 bytes 还原为指定的 NumPy 类型
                    hammers_ts=np.frombuffer(row.hammers_ts, dtype=np.uint32).copy(),
                    hammers_val=np.frombuffer(row.hammers_val, dtype=np.uint16).copy(),
                    after_ts=np.frombuffer(row.after_ts, dtype=np.uint32).copy(),
                    after_val=np.frombuffer(row.after_val, dtype=np.uint16).copy()
                )
                track_notes.append(note)
            tracks.append(track_notes)
            
        return tracks
