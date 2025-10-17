from typing import List
from utils.logger import Logger
logger = Logger.get_logger()

class SPMidWriter:
    """优化的SPMID写入器"""
    
    def __init__(self, output_path: str):
        self.output_path = output_path
        self.tracks: List[List] = [[], []]
        self.note_count = 0
    
    def get_track(self, track_index: int) -> List:
        if 0 <= track_index < len(self.tracks):
            return self.tracks[track_index]
        raise IndexError(f"轨道索引超出范围: {track_index}")
    
    def insert_note(self, track_index: int, note):
        if 0 <= track_index < len(self.tracks):
            self.tracks[track_index].append(note)
            self.note_count += 1
    
    def truncate_tracks_by_replay_time(self):
        """
        根据播放音轨的最后一个时间戳截断录制音轨
        如果录制音轨远长于播放音轨，以播放音轨的最后一个时间戳为基准，舍弃长于这个时间戳的录制音轨
        """
        if len(self.tracks) < 2:
            logger.warning("音轨数量不足，无法进行截断操作")
            return
        
        record_track = self.tracks[0]  # 录制音轨
        replay_track = self.tracks[1]  # 播放音轨
        
        if not replay_track:
            logger.warning("播放音轨为空，无法进行截断操作")
            return
        
        # 计算播放音轨的最后时间戳（最后一个key_off）
        def _get_key_on_off(note):
            try:
                # 计算key_on
                if hasattr(note, 'hammers') and note.hammers is not None and not note.hammers.empty:
                    key_on = int(note.hammers.index[0]) + int(note.offset)
                elif hasattr(note, 'after_touch') and note.after_touch is not None and not note.after_touch.empty:
                    key_on = int(note.after_touch.index[0]) + int(note.offset)
                else:
                    key_on = int(note.offset)

                # 计算key_off
                if hasattr(note, 'hammers') and note.hammers is not None and not note.hammers.empty:
                    key_off = int(note.hammers.index[-1]) + int(note.offset)
                elif hasattr(note, 'after_touch') and note.after_touch is not None and not note.after_touch.empty:
                    key_off = int(note.after_touch.index[-1]) + int(note.offset)
                else:
                    key_off = int(note.offset)
                return key_on, key_off
            except Exception:
                return int(getattr(note, 'offset', 0)), int(getattr(note, 'offset', 0))
        
        # 计算播放轨道的最后时间戳（最后一个key_off）
        try:
            replay_last_time = max(_get_key_on_off(note)[1] for note in replay_track)
        except Exception:
            logger.warning("无法计算播放音轨的最后时间戳")
            return
        
        if replay_last_time <= 0:
            logger.warning("播放音轨的最后时间戳无效")
            return
        
        # 记录截断前的音符数量
        before_truncate_record = len(record_track)
        before_truncate_replay = len(replay_track)
        
        # 根据该时间戳过滤两条轨道：仅保留 key_on < replay_last_time 的音符
        self.tracks[0] = [note for note in record_track if _get_key_on_off(note)[0] < replay_last_time]
        self.tracks[1] = [note for note in replay_track if _get_key_on_off(note)[0] < replay_last_time]
        
        # 更新音符计数
        self.note_count = len(self.tracks[0]) + len(self.tracks[1])
        
        logger.info(f"基于播放最后时间戳 {replay_last_time} 进行音轨截断:")
        logger.info(f"  录制音轨: {before_truncate_record} -> {len(self.tracks[0])} 个音符")
        logger.info(f"  播放音轨: {before_truncate_replay} -> {len(self.tracks[1])} 个音符")
        logger.info(f"  总音符数: {self.note_count}")
    
    def save(self):
        logger.info(f"保存SPMID文件到: {self.output_path}")
        logger.info(f"轨道0音符数量: {len(self.tracks[0])}")
        logger.info(f"轨道1音符数量: {len(self.tracks[1])}")
        logger.info(f"总音符数量: {self.note_count}")
