import struct
import pandas as pd
from dataclasses import dataclass
from typing import List, Tuple, BinaryIO, Union, Optional
import matplotlib.pyplot as plt
import io
import traceback  # 新增traceback
from utils.logger import Logger
logger = Logger.get_logger()

@dataclass
class Note:
    offset: int
    id: int
    finger: int
    hammers: pd.Series  # 索引为时间戳
    uuid: str
    velocity: int
    after_touch: pd.Series

    @property
    def length(self) -> int:
        """获取音符总长度（来自after_touch最后一个时间点）"""
        if not self.after_touch.empty:
            return self.after_touch.index[-1]
        return 0

class SPMidReader:
    # 定义文件结构和块类型的常量
    FILE_MAGIC = 0x44495053  # 'SPID'
    INFO_MAGIC = 0x4F464E49  # 'INFO'
    NOTE_MAGIC = 0x45544F4E  # 'NOTE'
    
    # 结构体格式定义
    FMT_UINT8 = '<B'
    FMT_UINT16 = '<H'
    FMT_UINT32 = '<I'
    
    def __init__(self, source: Union[str, bytes, bytearray, io.BytesIO], verbose: bool = False):
        """
        初始化SPMidReader
        
        Args:
            source: 数据源，可以是：
                - str: 文件路径
                - bytes: 二进制数据
                - bytearray: 二进制数据
                - io.BytesIO: 二进制流对象
            verbose: 是否启用详细日志
        """
        self.source = source
        self.tracks = []
        self.verbose = verbose
        self.file_size = 0
        self.file_handle = None
        self.is_binary_source = isinstance(source, (bytes, bytearray, io.BytesIO))
        
        self._open_source()
        self._parse_header()
        self._parse_blocks()
    
    def __del__(self):
        """确保文件资源被释放"""
        self.close()
    
    def __enter__(self):
        """支持上下文管理器"""
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        """上下文管理器退出时关闭文件"""
        self.close()
    
    def close(self):
        """显式关闭文件资源"""
        if self.file_handle and not self.file_handle.closed:
            self.file_handle.close()
        self.file_handle = None
    
    def _open_source(self) -> None:
        """打开数据源"""
        try:
            if self.is_binary_source:
                # 处理二进制数据源
                if isinstance(self.source, io.BytesIO):
                    # 已经是BytesIO对象
                    self.file_handle = self.source
                    self.file_handle.seek(0, 2)  # 移动到末尾
                    self.file_size = self.file_handle.tell()
                    self.file_handle.seek(0)     # 回到开头
                else:
                    # bytes或bytearray，转换为BytesIO
                    if isinstance(self.source, bytearray):
                        data = bytes(self.source)
                    else:
                        data = self.source
                    self.file_handle = io.BytesIO(data)
                    self.file_size = len(data)
            else:
                # 处理文件路径
                self.file_handle = open(self.source, 'rb')
                self.file_handle.seek(0, 2)  # 移动到文件末尾
                self.file_size = self.file_handle.tell()
                self.file_handle.seek(0)     # 回到文件开头
                
        except Exception as e:
            logger.error(f"打开SPMID数据源失败: {e}\n{traceback.format_exc()}")
            self.close()
            raise IOError(f"Failed to open source: {e}") from e
    
    def _read(self, fmt: str) -> int:
        """从数据源中读取指定格式的数据"""
        size = struct.calcsize(fmt)
        data = self.file_handle.read(size)
        if len(data) < size:
            raise EOFError("Unexpected end of data")
        return struct.unpack(fmt, data)[0]
    
    def _read_string(self, encrypted: bool = False) -> str:
        """读取以空字符结尾的字符串"""
        str_bytes = bytearray()
        while True:
            byte = self.file_handle.read(1)
            if not byte:
                raise EOFError("Unexpected end of data while reading string")
            
            if byte == b'\x00':
                break
                
            if encrypted:
                str_bytes.append(ord(byte) ^ 0xB6)
            else:
                str_bytes.append(ord(byte))
        
        return str_bytes.decode('utf-8', errors='replace')
    
    def _seek(self, position: int) -> None:
        """移动到数据源指定位置"""
        self.file_handle.seek(position)
    
    def _parse_header(self) -> None:
        """解析文件头部信息"""
        try:
            self._seek(0)  # 确保在数据开头

            magic = self._read(self.FMT_UINT32)
            if magic != self.FILE_MAGIC:
                logger.error(f"SPMID文件头magic不符: 期望0x{self.FILE_MAGIC:08X}, 实际0x{magic:08X}")
                self.close()
                raise ValueError(f"Invalid file format. Expected 0x{self.FILE_MAGIC:08X}, got 0x{magic:08X}")

            crc = self._read(self.FMT_UINT32)
            version = self._read(self.FMT_UINT32)
            block_count = self._read(self.FMT_UINT32)

            if self.verbose:
                logger.info(f"Magic: 0x{magic:08X}, CRC: 0x{crc:08X}, Version: 0x{version:08X}")
                logger.info(f"Block count: {block_count}")

            # 读取块偏移和大小
            self.blocks = []
            for _ in range(block_count):
                offset = self._read(self.FMT_UINT32)
                size = self._read(self.FMT_UINT32)
                self.blocks.append((offset, size))

                if self.verbose:
                    logger.info(f"Block offset: 0x{offset:08X}, size: 0x{size:08X}")

        except Exception as e:
            logger.error(f"解析SPMID文件头失败: {e}\n{traceback.format_exc()}")
            self.close()
            raise

    def _parse_blocks(self) -> None:
        """解析所有数据块"""
        for offset, size in self.blocks:
            self._seek(offset)
            magic = self._read(self.FMT_UINT32)
            
            if magic == self.INFO_MAGIC:
                self._parse_info_block()
            elif magic == self.NOTE_MAGIC:
                self._parse_note_block()
    
    def _parse_info_block(self) -> None:
        """解析INFO块"""
        item_count = self._read(self.FMT_UINT32)
        if self.verbose:
            logger.info(f"INFO block items: {item_count}")
        
        for _ in range(item_count):
            key = self._read_string(encrypted=True)
            value = self._read_string(encrypted=True)
            if self.verbose:
                logger.info(f"  {key}: {value}")
    
    def _parse_note_block(self) -> None:
        """解析NOTE块"""
        total_time = self._read(self.FMT_UINT32)
        note_count = self._read(self.FMT_UINT32)
        notes = []
        
        if self.verbose:
            logger.info(f"Total time: {total_time}, Notes: {note_count}")
        
        for _ in range(note_count):
            # 读取音符基础信息
            offset = self._read(self.FMT_UINT32)
            note_id = self._read(self.FMT_UINT8)
            finger = self._read(self.FMT_UINT8)
            hammer_count = self._read(self.FMT_UINT8)
            _ = self._read(self.FMT_UINT8)  # 跳过保留字段
            uuid = self._read_string()
            
            # 再次读取offset和velocity（根据原始格式）
            offset = self._read(self.FMT_UINT32)
            velocity = self._read(self.FMT_UINT16)
            
            # 读取hammer数据并转换为Series
            timestamps = []
            values = []
            for _ in range(hammer_count):
                x = self._read(self.FMT_UINT32)
                y = self._read(self.FMT_UINT16)
                timestamps.append(x)
                values.append(y)
            hammers_series = pd.Series(values, index=timestamps, name="hammer_value")
            
            # 读取after_touch数据并转换为Series
            touch_count = self._read(self.FMT_UINT32)
            timestamps = []
            values = []
            cumulative_time = 0
            for _ in range(touch_count):
                period = self._read(self.FMT_UINT16)
                value = self._read(self.FMT_UINT16)
                cumulative_time += period
                timestamps.append(cumulative_time)
                values.append(value)
            after_touch_series = pd.Series(values, index=timestamps, name="after_touch")
            
            # 跳过key-off数据（未使用）
            _ = self._read(self.FMT_UINT16)  # period
            _ = self._read(self.FMT_UINT16)  # value
            
            # 创建Note对象并添加到列表
            note = Note(
                offset=offset,
                id=note_id,
                finger=finger,
                hammers=hammers_series,
                uuid=uuid,
                after_touch=after_touch_series,
                velocity=velocity
            )
            notes.append(note)
            
            if self.verbose:
                logger.info(f"Note: offset={offset}, id={note_id}, finger={finger}, "
                           f"hammers={len(hammers_series)}, uuid={uuid}, length={note.length}")
        
        self.tracks.append(notes)
    
    @property
    def track_count(self) -> int:
        """返回音轨数量"""
        return len(self.tracks)
    
    def get_track(self, index: int) -> List[Note]:
        """获取指定音轨的音符列表"""
        if 0 <= index < len(self.tracks):
            return self.tracks[index]
        raise IndexError(f"Track index out of range. Valid range: 0-{len(self.tracks)-1}")
    
    @classmethod
    def from_file(cls, file_path: str, verbose: bool = False) -> 'SPMidReader':
        """
        从文件创建SPMidReader实例
        
        Args:
            file_path: 文件路径
            verbose: 是否启用详细日志
            
        Returns:
            SPMidReader实例
        """
        return cls(file_path, verbose)
    
    @classmethod
    def from_bytes(cls, data: Union[bytes, bytearray], verbose: bool = False) -> 'SPMidReader':
        """
        从二进制数据创建SPMidReader实例
        
        Args:
            data: 二进制数据
            verbose: 是否启用详细日志
            
        Returns:
            SPMidReader实例
        """
        return cls(data, verbose)
    
    @classmethod
    def from_bytesio(cls, data: io.BytesIO, verbose: bool = False) -> 'SPMidReader':
        """
        从BytesIO对象创建SPMidReader实例
        
        Args:
            data: BytesIO对象
            verbose: 是否启用详细日志
            
        Returns:
            SPMidReader实例
        """
        return cls(data, verbose)
    
    def get_binary_data(self) -> bytes:
        """
        获取当前数据的二进制表示
        
        Returns:
            二进制数据
        """
        if self.is_binary_source and isinstance(self.source, (bytes, bytearray)):
            return bytes(self.source) if isinstance(self.source, bytearray) else self.source
        elif self.file_handle:
            current_pos = self.file_handle.tell()
            self.file_handle.seek(0)
            data = self.file_handle.read()
            self.file_handle.seek(current_pos)
            return data
        else:
            raise RuntimeError("No data available")
    
    def save_to_file(self, file_path: str) -> None:
        """
        将当前数据保存到文件
        
        Args:
            file_path: 目标文件路径
        """
        data = self.get_binary_data()
        with open(file_path, 'wb') as f:
            f.write(data)