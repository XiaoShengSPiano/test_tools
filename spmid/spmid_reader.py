import struct
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, BinaryIO, Union, Optional
import io

# =============================================================================
# 标准 Note 类（用于项目兼容性）
# =============================================================================

@dataclass
class Note:
    """
    标准 Note 数据结构（使用 Pandas Series）
    
    包含完整的时间属性和拆分元数据，用于项目中的分析和处理
    """
    offset: int
    id: int
    finger: int
    hammers: pd.Series  # 索引为时间戳
    uuid: str
    velocity: int
    after_touch: pd.Series

    # 时间属性 - 在初始化后计算
    key_on_ms: float = 0.0     # 按键开始时间（毫秒）
    key_off_ms: float = 0.0    # 按键结束时间（毫秒）
    duration_ms: float = 0.0   # 持续时间（毫秒）
    first_hammer_velocity: int = 0   # 第一个锤速值
    first_hammer_time: float = 0.0    # 第一个锤击时间

    # 拆分元数据 - 用于标识拆分后的音符
    split_parent_idx: int = None   # 父索引（原始数据的索引）
    split_seq: int = None          # 拆分序号（0, 1, 2...）
    is_split: bool = False                   # 是否是拆分数据

    def __post_init__(self):
        """数据类初始化后计算预处理属性"""
        self._compute_time_properties()

    def _compute_time_properties(self):
        """预计算时间属性并保存为成员变量"""
        if self.after_touch is not None and not self.after_touch.empty:
            # 按键开始时间（第一个触后数据点）
            self.key_on_ms = (self.after_touch.index[0] + self.offset) / 10.0
            # 按键结束时间（最后一个触后数据点）
            self.key_off_ms = (self.after_touch.index[-1] + self.offset) / 10.0
            # 持续时间（key_off - key_on）
            self.duration_ms = self.key_off_ms - self.key_on_ms
        else:
            # 如果没有after_touch数据，设为None
            self.key_on_ms = 0.0
            self.key_off_ms = 0.0
            self.duration_ms = 0.0

        if self.hammers is not None and not self.hammers.empty:
            # 第一个锤速值
            self.first_hammer_velocity = int(self.hammers.values[0])
            # 第一个锤击时间
            self.first_hammer_time = (self.hammers.index[0] + self.offset) / 10.0
        else:
            self.first_hammer_velocity = 0
            self.first_hammer_time = 0.0

    def get_first_hammer_velocity(self) -> int:
        """获取第一个锤速值"""
        return self.first_hammer_velocity
    
    def get_first_hammer_time(self) -> float:
        """获取第一个锤击时间（包含offset）"""
        return self.first_hammer_time
    
    def get_after_touch_timestamps_avg(self) -> float:
        """获取触后时间戳平均值"""
        if self.after_touch is None or self.after_touch.empty:
            return 0.0
        return np.mean(self.after_touch.index)

# =============================================================================
# 优化版 Note 类（轻量级，使用 NumPy）

# =============================================================================

@dataclass
class OptimizedNote:
    """
    优化版 Note 数据结构（轻量级，使用 NumPy arrays）
    
    用于高速读取，后续可以转换为标准 Note（Pandas Series）
    """
    offset: int
    id: int
    finger: int
    velocity: int
    uuid: str

    hammers_ts: np.ndarray    # 时间戳数组
    hammers_val: np.ndarray   # 值数组

    after_ts: np.ndarray      # 时间戳数组
    after_val: np.ndarray     # 值数组

    @property
    def length(self) -> int:
        """音符长度（从after_touch的最后一个时间戳计算）"""
        return int(self.after_ts[-1]) if self.after_ts.size else 0

    def to_pandas(self) -> Tuple[pd.Series, pd.Series]:
        """
        转换为 Pandas Series（需要时再转换，延迟计算）
        
        Returns:
            Tuple[pd.Series, pd.Series]: (hammers, after_touch)
        """
        hammers = pd.Series(self.hammers_val, index=self.hammers_ts, name="hammer")
        after_touch = pd.Series(self.after_val, index=self.after_ts, name="after_touch")
        return hammers, after_touch
    
    def to_standard_note(self) -> Note:
        """
        转换为标准 Note 对象（包含时间属性和拆分元数据）
        
        Returns:
            Note: 标准 Note 对象
        """
        hammers, after_touch = self.to_pandas()
        
        note = Note(
            offset=self.offset,
            id=self.id,
            finger=self.finger,
            velocity=self.velocity,
            uuid=self.uuid,
            hammers=hammers,
            after_touch=after_touch,
            # 时间属性会在 __post_init__ 中自动计算
            key_on_ms=None,
            key_off_ms=None,
            duration_ms=None,
            # 拆分元数据默认值
            split_parent_idx=None,
            split_seq=None,
            is_split=False
        )
        
        return note


# =============================================================================
# 高性能 SPMID Reader
# =============================================================================

class OptimizedSPMidReader:
    """
    高性能优化版 SPMID Reader
    
    特点：
    - 使用 NumPy 批量读取，避免逐个创建 Pandas Series
    - 使用 np.frombuffer 零拷贝解析
    - 返回 OptimizedNote，可按需转换为标准 Note
    """
    
    FILE_MAGIC = 0x44495053  # 'SPID'
    INFO_MAGIC = 0x4F464E49  # 'INFO'
    NOTE_MAGIC = 0x45544F4E  # 'NOTE'

    def __init__(self, source: Union[str, bytes, bytearray, io.BytesIO]):
        """
        初始化优化版 SPMidReader
        
        Args:
            source: 数据源（文件路径、bytes、bytearray、BytesIO）
        """
        self.source = source
        self.tracks: List[List[OptimizedNote]] = []
        self._open()
        self._parse_header()
        self._parse_blocks()

    # ---------- I/O 操作 ----------

    def _open(self):
        """打开数据源"""
        if isinstance(self.source, (bytes, bytearray)):
            self.f = io.BytesIO(self.source)
        elif isinstance(self.source, io.BytesIO):
            self.f = self.source
        else:
            self.f = open(self.source, "rb")

    def _read(self, n: int) -> bytes:
        """读取指定字节数"""
        b = self.f.read(n)
        if len(b) != n:
            raise EOFError("Unexpected EOF")
        return b

    def _u8(self) -> int:
        """读取 uint8"""
        return struct.unpack("<B", self._read(1))[0]

    def _u16(self) -> int:
        """读取 uint16"""
        return struct.unpack("<H", self._read(2))[0]

    def _u32(self) -> int:
        """读取 uint32"""
        return struct.unpack("<I", self._read(4))[0]

    def _read_cstring(self, encrypted=False) -> str:
        """读取 C 风格字符串（以 \0 结尾）"""
        buf = bytearray()
        while True:
            chunk = self.f.read(64)
            if b"\x00" in chunk:
                i = chunk.index(0)
                buf.extend(chunk[:i])
                self.f.seek(i - len(chunk) + 1, 1)
                break
            buf.extend(chunk)
        if encrypted:
            buf = bytes(b ^ 0xB6 for b in buf)
        return buf.decode("utf-8", errors="replace")

    # ---------- 解析逻辑 ----------

    def _parse_header(self):
        """解析文件头"""
        if self._u32() != self.FILE_MAGIC:
            raise ValueError("Invalid SPMID file")

        _ = self._u32()  # crc
        _ = self._u32()  # version
        block_count = self._u32()

        self.blocks = [(self._u32(), self._u32()) for _ in range(block_count)]

    def _parse_blocks(self):
        """解析所有数据块"""
        for offset, _ in self.blocks:
            self.f.seek(offset)
            magic = self._u32()
            if magic == self.INFO_MAGIC:
                self._parse_info()
            elif magic == self.NOTE_MAGIC:
                self._parse_note()

    def _parse_info(self):
        """解析 INFO 块"""
        count = self._u32()
        for _ in range(count):
            self._read_cstring(encrypted=True)
            self._read_cstring(encrypted=True)

    def _parse_note(self):
        """解析 NOTE 块（使用 NumPy 批量读取，高性能）"""
        _total_time = self._u32()
        note_count = self._u32()
        notes: List[OptimizedNote] = []

        for _ in range(note_count):
            offset = self._u32()
            note_id = self._u8()
            finger = self._u8()
            hammer_count = self._u8()
            _ = self._u8()  # reserved
            uuid = self._read_cstring()

            offset = self._u32()
            velocity = self._u16()

            # -------- hammer（NumPy 批量读取）--------
            if hammer_count:
                buf = self._read(hammer_count * 6)
                arr = np.frombuffer(
                    buf,
                    dtype=[("t", "<u4"), ("v", "<u2")]
                )
                h_ts = arr["t"].copy()
                h_val = arr["v"].copy()
            else:
                h_ts = np.empty(0, dtype=np.uint32)
                h_val = np.empty(0, dtype=np.uint16)

            # -------- after_touch（NumPy + cumsum）--------
            touch_count = self._u32()
            if touch_count:
                buf = self._read(touch_count * 4)
                arr = np.frombuffer(buf, dtype="<u2").reshape(-1, 2)
                periods = arr[:, 0]
                values = arr[:, 1]
                a_ts = np.cumsum(periods, dtype=np.uint32)
                a_val = values.copy()
            else:
                a_ts = np.empty(0, dtype=np.uint32)
                a_val = np.empty(0, dtype=np.uint16)

            _ = self._u16()  # key-off period
            _ = self._u16()

            notes.append(
                OptimizedNote(
                    offset=offset,
                    id=note_id,
                    finger=finger,
                    velocity=velocity,
                    uuid=uuid,
                    hammers_ts=h_ts,
                    hammers_val=h_val,
                    after_ts=a_ts,
                    after_val=a_val,
                )
            )

        self.tracks.append(notes)

    # ---------- 公共 API ----------

    def get_track(self, idx: int) -> List[OptimizedNote]:
        """获取指定索引的音轨"""
        return self.tracks[idx]

    @property
    def track_count(self) -> int:
        """获取音轨数量"""
        return len(self.tracks)
    
    @property
    def get_track_count(self) -> int:
        """获取音轨数量（兼容旧接口）"""
        return len(self.tracks)
    
    def get_track_as_standard_notes(self, idx: int) -> List[Note]:
        """
        获取指定音轨并转换为标准 Note 列表
        
        Args:
            idx: 音轨索引
            
        Returns:
            List[Note]: 标准 Note 对象列表
        """
        optimized_notes = self.get_track(idx)
        return [note.to_standard_note() for note in optimized_notes]


# =============================================================================
# 兼容性别名
# =============================================================================

# 为了向后兼容，将 OptimizedSPMidReader 也命名为 SPMidReader
SPMidReader = OptimizedSPMidReader
