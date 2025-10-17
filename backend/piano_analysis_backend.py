"""
SPMID文件处理
负责SPMID文件的加载、分析、瀑布图生成和错误检测
"""
import base64
import io
import time
import os
import platform
import tempfile
from typing import List
import matplotlib.pyplot as plt
import matplotlib
import matplotlib.font_manager as fm
matplotlib.use('Agg')
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dataclasses import dataclass
from utils.logger import Logger


import numpy as np
import pandas as pd
from dtw import dtw

import sys
# 导入SPMID模块
import spmid

logger = Logger.get_logger()

class PianoAnalysisBackend:
    """钢琴分析后端API - SPMID文件处理"""

    def __init__(self, session_id=None):
        self.session_id = session_id
        self.record_data = None
        self.replay_data = None
        self.multi_hammers = []
        self.drop_hammers = []
        self.all_error_notes = []
        self.current_page = 0
        self.page_size = 10
        self.original_file_content = None  # 保存原始文件内容
        self.current_filename = ""  # 添加当前文件名存储

        # 新增：数据源状态管理
        self._data_source = None  # 'upload' 或 'history'
        self._current_history_id = None  # 当前历史记录ID
        self._last_upload_time = 0  # 最后上传时间
        self._last_history_time = 0  # 最后历史记录选择时间

        # 新增：内容变化检测
        self._last_upload_content = None  # 最后上传的文件内容
        
        # 新增：键ID筛选功能
        self.key_filter = None  # 当前选中的键ID列表
        self.available_keys = []  # 可用的键ID列表
        self._last_selected_history_id = None  # 最后选择的历史记录ID
        
        # 新增：时间轴筛选功能
        self.time_filter = None  # 当前时间筛选范围 (start_time, end_time)
        self.time_range = None  # 数据的时间范围 (min_time, max_time)
        self.display_time_range = None  # 用户设置的显示时间范围 (不影响原始数据)

        # 设置跨平台中文字体 - 参照td.py的实现
        self._setup_chinese_font()


        # 新增按键序列
        self.record_key_of_notes = {}
        self.replay_key_of_notes = {}
        
        # 新增：有效数据存储（经过发声检测过滤的数据）
        self.valid_record_data = None
        self.valid_replay_data = None

    
    def spmid_offset_alignment(self):
        """
        执行SPMID偏移量对齐分析
        
        功能说明：
        分析钢琴录制数据与回放数据之间的时间偏移，计算每个键位的时序偏差统计信息。
        通过DTW（动态时间规整）算法对齐时间序列，计算偏移量并生成统计报告。
        
        数据来源：
        - self.record_key_of_notes: 按键位ID分组的录制音符数据（来自有效数据过滤）
        - self.replay_key_of_notes: 按键位ID分组的播放音符数据（来自有效数据过滤）
        
        返回：
        - df_stats: DataFrame，包含每个键位的统计信息（键位ID、配对数、中位数、均值、标准差）
        - all_offsets: numpy数组，包含所有键位的偏移量数据
        """
        # 初始化统计变量
        key_stats = []  # 存储每个键位的统计信息列表
        all_offsets = []  # 存储所有键位的偏移量数据
        hammer_counts = {'record': 0, 'replay': 0}  # 统计录制和播放的锤子总数
        
        # 遍历所有钢琴键位进行对齐分析（键位ID范围：1-88）
        for key_id in range(1, 89):
            # 分析单个键位的对齐情况
            key_result = self._analyze_key_alignment(key_id, hammer_counts)
            if key_result:
                # 如果该键位有有效的对齐结果，添加到统计中
                key_stats.append(key_result['stats'])  # 键位统计信息
                all_offsets.extend(key_result['offsets'])  # 该键位的偏移量列表
        
        # 生成统计报告
        df_stats = pd.DataFrame(key_stats)  # 转换为DataFrame格式
        all_offsets = np.array(all_offsets)  # 转换为numpy数组
        self._print_alignment_summary(hammer_counts, all_offsets)  # 打印分析摘要
        
        return df_stats, all_offsets

    def _analyze_key_alignment(self, key_id, hammer_counts):
        """
        分析单个键位的对齐情况
        
        参数：
        - key_id: 钢琴键位ID（1-88）
        - hammer_counts: 字典，用于统计录制和播放的锤子总数
        
        数据来源：
        - self.record_key_of_notes: 按键位ID分组的录制音符字典
        - self.replay_key_of_notes: 按键位ID分组的播放音符字典
        
        返回：
        - dict: 包含'stats'（统计信息）和'offsets'（偏移量列表）的字典
        - None: 如果该键位没有数据或分析失败
        """
        # 获取指定键位的音符数据
        record_notes = self.record_key_of_notes.get(key_id, [])  # 录制数据中键位ID=key_id的所有音符
        replay_notes = self.replay_key_of_notes.get(key_id, [])  # 播放数据中键位ID=key_id的所有音符
        
        # 如果某个键位没有录制数据或播放数据，跳过分析
        if not record_notes or not replay_notes:
            return None
        
        # 提取锤子时间戳数据
        # hammer_times: {'record': [时间戳列表], 'replay': [时间戳列表]}
        hammer_times = self._extract_hammer_times(record_notes, replay_notes, hammer_counts)
        if not hammer_times:
            return None
        
        # 执行DTW（动态时间规整）对齐算法
        # offsets: 偏移量列表，表示录制和播放之间的时间差异
        offsets = self._perform_dtw_alignment(hammer_times['record'], hammer_times['replay'])
        if not offsets:
            return None
        
        # 计算该键位的统计信息（中位数、均值、标准差等）
        stats = self._calculate_key_statistics(key_id, offsets)
        
        return {'stats': stats, 'offsets': offsets}

    def _extract_hammer_times(self, record_notes, replay_notes, hammer_counts):
        """
        提取锤子时间戳数据
        
        参数：
        - record_notes: 录制数据中某个键位的音符列表
        - replay_notes: 播放数据中某个键位的音符列表
        - hammer_counts: 字典，用于统计锤子总数 {'record': 0, 'replay': 0}
        
        数据来源：
        - note.hammers: 音符的锤子数据（pandas Series，索引为时间戳）
        - note.offset: 音符的全局时间偏移量
        
        处理逻辑：
        1. 遍历录制音符，在播放音符中找到最佳匹配
        2. 提取匹配音符对的锤子时间戳
        3. 统计锤子总数
        
        返回：
        - dict: {'record': [录制时间戳列表], 'replay': [播放时间戳列表]}
        - None: 如果数据无效
        """
        record_times = []  # 存储录制数据的锤子时间戳
        replay_times = []  # 存储播放数据的锤子时间戳
        
        # 遍历录制数据中的每个音符
        for note in record_notes:
            # 在播放数据中找到最佳匹配的音符
            # 注意：这里存在逻辑问题，因为record_notes和replay_notes都是相同键位的音符
            match_note = spmid.find_best_matching_note(note, replay_notes)
            if match_note is None:
                continue  # 没有找到匹配的音符，跳过
            
            # 提取录制数据的时间戳
            # note.hammers.index: 锤子的相对时间戳
            # note.offset: 音符的全局时间偏移量
            # 最终时间戳 = 相对时间戳 + 全局偏移量
            record_times.extend(note.hammers.index + note.offset)
            hammer_counts['record'] += len(note.hammers)  # 统计录制锤子总数
            
            # 提取播放数据的时间戳
            # match_note.hammers.index: 匹配音符的锤子相对时间戳
            # match_note.offset: 匹配音符的全局时间偏移量
            replay_times.extend(match_note.hammers.index + match_note.offset)
            hammer_counts['replay'] += len(match_note.hammers)  # 统计播放锤子总数
        
        # 验证时间戳数据的有效性
        if not self._validate_hammer_times(record_times, replay_times):
            return None
        
        return {'record': record_times, 'replay': replay_times}

    def _validate_hammer_times(self, record_times, replay_times):
        """
        验证锤子时间戳数据的有效性
        
        参数：
        - record_times: 录制数据的锤子时间戳列表
        - replay_times: 播放数据的锤子时间戳列表
        
        验证条件：
        1. 时间戳列表不能为空
        2. 时间戳不能全部为None
        
        返回：
        - bool: True表示数据有效，False表示数据无效
        """
        if (len(record_times) == 0 or len(replay_times) == 0 or
            all(t is None for t in record_times) or 
            all(t is None for t in replay_times)):
            logger.debug("时间戳数据无效，跳过")
            return False
        return True

    def _perform_dtw_alignment(self, record_times, replay_times):
        """
        执行DTW（动态时间规整）对齐算法
        
        参数：
        - record_times: 录制数据的锤子时间戳列表
        - replay_times: 播放数据的锤子时间戳列表
        
        算法说明：
        DTW（Dynamic Time Warping）是一种时间序列对齐算法，用于处理两个时间序列
        在时间轴上的非线性对齐问题。在钢琴分析中，用于对齐录制和播放的锤子时间戳。
        
        处理过程：
        1. 将时间戳列表转换为numpy数组并重塑为列向量
        2. 使用DTW算法计算两个时间序列的最优对齐路径
        3. 根据对齐路径计算偏移量（播放时间 - 录制时间）
        
        返回：
        - list: 偏移量列表，表示录制和播放之间的时间差异（单位：毫秒）
        - None: 如果DTW对齐失败
        """
        try:
            # 执行DTW对齐
            # 将时间戳列表转换为numpy数组并重塑为列向量（DTW算法要求）
            alignment = dtw(
                np.array(record_times).reshape(-1, 1),  # 录制时间戳列向量
                np.array(replay_times).reshape(-1, 1),  # 播放时间戳列向量
                keep_internals=True  # 保留内部对齐信息
            )
            
            # 计算偏移量
            # alignment.index1: 录制时间戳的索引序列
            # alignment.index2: 播放时间戳的索引序列
            # 偏移量 = 播放时间戳 - 录制时间戳
            offsets = [
                replay_times[idx2] - record_times[idx1] 
                for idx1, idx2 in zip(alignment.index1, alignment.index2)
            ]
            
            return offsets
            
        except Exception as e:
            logger.warning(f"DTW对齐失败: {e}")
            return None

    def _calculate_key_statistics(self, key_id, offsets):
        """
        计算键位统计信息
        
        参数：
        - key_id: 钢琴键位ID（1-88）
        - offsets: 偏移量列表，表示录制和播放之间的时间差异
        
        统计指标：
        - count: 配对数（偏移量的数量）
        - median: 中位数偏移量（毫秒）
        - mean: 平均偏移量（毫秒）
        - std: 偏移量标准差（毫秒）
        
        返回：
        - dict: 包含键位统计信息的字典
        """
        return {
            'key_id': key_id,  # 键位ID
            'count': len(offsets),  # 配对数（该键位的偏移量数量）
            'median': np.median(offsets) if offsets else np.nan,  # 中位数偏移量
            'mean': np.mean(offsets) if offsets else np.nan,  # 平均偏移量
            'std': np.std(offsets) if offsets else np.nan  # 偏移量标准差
        }

    def _print_alignment_summary(self, hammer_counts, all_offsets):
        """
        打印对齐分析摘要
        
        参数：
        - hammer_counts: 字典，包含录制和播放的锤子总数统计
        - all_offsets: numpy数组，包含所有键位的偏移量数据
        
        输出内容：
        - 录制和播放的锤子总数
        - 总配对数
        - 整体偏移量统计（中位数、均值、标准差）
        """
        logger.info(f"录制歌曲的锤子总数: {hammer_counts['record']}")
        logger.info(f"回放歌曲的按键总数: {hammer_counts['replay']}")
        logger.info(f"总共配对数: {len(all_offsets)}")
        logger.info(f"所有按键偏移量中位数: {np.median(all_offsets):.2f} ms")
        logger.info(f"所有按键偏移量均值: {np.mean(all_offsets):.2f} ms")
        logger.info(f"所有按键偏移量标准差: {np.std(all_offsets):.2f} ms")


    def update_key_of_notes(self):
        """使用有效数据重新构建按键索引"""
        # 检查有效数据是否存在
        if self.valid_record_data is None or self.valid_replay_data is None:
            error_msg = "有效数据不存在，无法构建按键索引。请检查数据过滤过程。"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        # 清空现有数据
        self.record_key_of_notes = {}
        self.replay_key_of_notes = {}

        # 构建按键索引的辅助函数
        def _build_key_index(notes, key_dict):
            """构建按键索引的通用函数"""
            for note in notes:
                if note.id not in key_dict:
                    key_dict[note.id] = []
                key_dict[note.id].append(note)

        # 使用有效数据重新构建按键索引
        _build_key_index(self.valid_record_data, self.record_key_of_notes)
        _build_key_index(self.valid_replay_data, self.replay_key_of_notes)

        # 按时间排序所有键位的音符
        self._sort_and_log_key_notes(self.record_key_of_notes, "录制")
        self._sort_and_log_key_notes(self.replay_key_of_notes, "播放")

    def _sort_and_log_key_notes(self, key_dict, data_type):
        """
        对按键索引中的音符按时间排序并记录日志
        
        参数：
        - key_dict: 按键索引字典
        - data_type: 数据类型描述（"录制" 或 "播放"）
        """
        for key_id in range(1, 89):  # 钢琴键位ID范围：1-88
            if key_id in key_dict:
                key_dict[key_id] = sorted(key_dict[key_id], key=lambda note: note.offset)
                logger.debug(f"键位 {key_id} 有 {len(key_dict[key_id])} 个{data_type}音符")

    def _setup_chinese_font(self):
        """设置跨平台中文字体配置"""
        # 配置matplotlib基础设置
        self._configure_matplotlib_settings()
        
        # 获取系统字体列表
        font_candidates = self._get_system_font_candidates()
        
        # 尝试找到可用的中文字体
        self.chinese_font = self._find_available_font(font_candidates)
        
        # 测试字体是否可用
        self._test_font_availability()

    def _configure_matplotlib_settings(self):
        """配置matplotlib基础设置"""
        plt.rcParams.update({
            'pdf.fonttype': 42,  # 嵌入TrueType字体
            'font.family': 'sans-serif',
            'axes.unicode_minus': False,
            'font.size': 10,
            'savefig.dpi': 300,
            'font.sans-serif': [
                'Microsoft YaHei', 'SimHei', 'PingFang SC', 'Heiti SC',
                'WenQuanYi Micro Hei', 'Droid Sans Fallback', 'DejaVu Sans', 'Arial'
            ]
        })

    def _get_system_font_candidates(self):
        """根据操作系统获取字体候选列表"""
        system = platform.system()

        font_candidates = {
            'Windows': ['Microsoft YaHei', 'SimHei', 'SimSun', 'Arial Unicode MS'],
            'Darwin': ['PingFang SC', 'Heiti SC', 'STHeiti', 'Arial Unicode MS'],  # macOS
            'Linux': ['WenQuanYi Micro Hei', 'Droid Sans Fallback', 'DejaVu Sans']
        }
        
        return font_candidates.get(system, ['DejaVu Sans'])

    def _find_available_font(self, font_candidates):
        """从候选字体中找到第一个可用的字体"""
        for font_name in font_candidates:
            if self._is_font_available(font_name):
                logger.info(f"✅ 使用系统字体: {font_name}")
                return fm.FontProperties(family=font_name)
        
        # 如果所有候选字体都不可用，使用默认字体
        logger.warning("⚠️ 所有候选字体都不可用，使用默认字体 DejaVu Sans")
        return fm.FontProperties(family='DejaVu Sans')

    def _is_font_available(self, font_name):
        """检查指定字体是否可用"""
        try:
            font_prop = fm.FontProperties(family=font_name)
            font_path = fm.findfont(font_prop)
            
            # 检查字体文件是否存在
            if not font_path or not os.path.exists(font_path):
                return False
            
            # 避免使用字体集合文件
            if font_path.lower().endswith(('.otc', '.ttc')):
                logger.debug(f"⚠️ 跳过字体集合文件: {font_name}")
                return False
            
            return True
            
        except Exception as e:
            logger.debug(f"⚠️ 字体 {font_name} 检查失败: {e}")
            return False

    def _test_font_availability(self):
        """测试字体是否真正可用"""
        try:
            # 创建最小测试图形
            fig, ax = plt.subplots(figsize=(0.1, 0.1))
            ax.text(0.5, 0.5, '测试', fontsize=8, ha='center', fontproperties=self.chinese_font)
            plt.close(fig)
            logger.info("✅ 中文字体配置完成")

        except Exception as e:
            logger.warning(f"⚠️ 字体测试失败，回退到默认字体: {e}")
            self.chinese_font = fm.FontProperties(family='DejaVu Sans')

    def clear_data_state(self):
        """清理数据状态 - 在切换数据源时调用"""
        self.record_data = None
        self.replay_data = None
        self.multi_hammers = []
        self.drop_hammers = []
        self.all_error_notes = []
        self.original_file_content = None
        
        # 清理有效数据
        self.valid_record_data = None
        self.valid_replay_data = None
        
        # 清理键ID筛选状态
        self.key_filter = None
        self.available_keys = []
        
        # 清理时间轴筛选状态
        self.time_filter = None
        self.time_range = None
        logger.info(f"🧹 会话 {self.session_id[:8] if self.session_id else 'unknown'}... 数据状态已清理")

    def set_upload_data_source(self, filename):
        """设置为文件上传数据源"""
        self._data_source = 'upload'
        self._current_history_id = None
        self.current_filename = filename
        import time
        self._last_upload_time = time.time()
        logger.info(f"📁 数据源设置为文件上传: {filename}")

    def set_history_data_source(self, history_id, filename):
        """设置为历史记录数据源"""
        self._data_source = 'history'
        self._current_history_id = history_id
        self.current_filename = filename
        import time
        self._last_history_time = time.time()
        logger.info(f"📚 数据源设置为历史记录: {filename} (ID: {history_id})")

    def get_data_source_info(self):
        """获取当前数据源信息"""
        return {
            'source': self._data_source,
            'history_id': self._current_history_id,
            'filename': self.current_filename,
            'last_upload_time': self._last_upload_time,
            'last_history_time': self._last_history_time
        }

    def _validate_spmid_file(self, spmid_bytes):
        """
        验证SPMID文件并创建临时文件
        
        功能说明：
        1. 保存原始文件内容到实例变量中，用于后续可能的导出或备份
        2. 检查SPMID模块是否可用，确保能够正常解析文件
        3. 创建临时文件，将字节数据写入磁盘，供SPMidReader读取
        
        参数：
            spmid_bytes (bytes): SPMID文件的二进制数据
            
        返回：
            str: 临时文件的完整路径
            
        异常：
            Exception: 当SPMID模块不可用时抛出
        """
        # 保存原始文件内容到实例变量，用于后续可能的导出或备份操作
        self.original_file_content = spmid_bytes
        logger.info(f"✅ 已保存原始文件内容，大小: {len(spmid_bytes)} 字节")

        # SPMID模块已确保可用，直接进行数据分析

        # 记录当前会话信息，便于调试和日志追踪
        logger.info(f"会话 {self.session_id[:8] if self.session_id else 'unknown'}... 开始加载SPMID文件")

        # 创建临时文件：将内存中的字节数据写入磁盘临时文件
        # 使用NamedTemporaryFile确保文件名唯一，delete=False避免自动删除
        with tempfile.NamedTemporaryFile(suffix='.spmid', delete=False) as temp_file:
            temp_file.write(spmid_bytes)  # 写入二进制数据
            temp_file_path = temp_file.name  # 获取临时文件路径

        return temp_file_path

    def _load_track_data(self, temp_file_path):
        """
        加载轨道数据并验证
        
        功能说明：
        1. 使用SPMidReader读取临时SPMID文件
        2. 验证文件是否包含足够的轨道（至少2个：录制+播放）
        3. 分别加载录制轨道和播放轨道的数据
        4. 更新按键索引，建立按键ID到音符列表的映射关系
        
        参数：
            temp_file_path (str): 临时SPMID文件的完整路径
            
        异常：
            Exception: 当轨道数量不足时抛出
        """
        # 使用上下文管理器确保文件资源正确释放
        with spmid.SPMidReader(temp_file_path) as reader:
            # 检查轨道数量：钢琴分析需要至少2个轨道（录制轨道+播放轨道）
            logger.info(f"📊 SPMID文件包含 {reader.track_count} 个轨道")
            
            # 验证轨道数量是否满足分析要求
            if reader.track_count < 2:
                error_msg = f"❌ SPMID文件只包含 {reader.track_count} 个轨道，需要至少2个轨道（录制+播放）才能进行分析"
                logger.error(error_msg)
                print(error_msg)  # 在终端中提示用户
                raise Exception(error_msg)
            
            # 加载双轨道数据：
            # 轨道0：录制数据（实际演奏的钢琴数据）
            # 轨道1：播放数据（MIDI回放的数据）
            self.record_data = reader.get_track(0)  # 录制数据
            self.replay_data = reader.get_track(1)  # 播放数据
            
            # 记录加载结果，便于调试和监控
            logger.info(f"📊 加载轨道数据: 录制 {len(self.record_data)} 个音符, 播放 {len(self.replay_data)} 个音符")

    def _get_key_on_off(self, note):
        """
        获取音符的按键开始和结束时间
        
        功能说明：
        1. 计算音符的按键开始时间（key_on）：音符开始演奏的时间点
        2. 计算音符的按键结束时间（key_off）：音符结束演奏的时间点
        3. 优先使用hammers数据，其次使用after_touch数据，最后使用offset作为备选
        4. 所有时间都基于音符的offset进行相对时间计算
        
        参数：
            note: 音符对象，包含hammers、after_touch、offset等属性
            
        返回：
            tuple: (key_on, key_off) 按键开始和结束时间的元组
        """
        try:
            # 计算key_on（按键开始时间）
            # 优先级：hammers数据 > after_touch数据 > offset备选
            if hasattr(note, 'hammers') and note.hammers is not None and not note.hammers.empty:
                # 使用hammers数据的第一个时间点作为按键开始时间
                key_on = int(note.hammers.index[0]) + int(note.offset)
            elif hasattr(note, 'after_touch') and note.after_touch is not None and not note.after_touch.empty:
                # 使用after_touch数据的第一个时间点作为按键开始时间
                key_on = int(note.after_touch.index[0]) + int(note.offset)
            else:
                # 备选方案：直接使用offset作为按键开始时间
                key_on = int(note.offset)

            # 计算key_off（按键结束时间）
            # 优先级：hammers数据 > after_touch数据 > offset备选
            if hasattr(note, 'hammers') and note.hammers is not None and not note.hammers.empty:
                # 使用hammers数据的最后一个时间点作为按键结束时间
                key_off = int(note.hammers.index[-1]) + int(note.offset)
            elif hasattr(note, 'after_touch') and note.after_touch is not None and not note.after_touch.empty:
                # 使用after_touch数据的最后一个时间点作为按键结束时间
                key_off = int(note.after_touch.index[-1]) + int(note.offset)
            else:
                # 备选方案：直接使用offset作为按键结束时间
                key_off = int(note.offset)
                
            return key_on, key_off
        except Exception:
            # 异常处理：如果所有计算都失败，返回offset作为备选值
            return int(getattr(note, 'offset', 0)), int(getattr(note, 'offset', 0))

    def _trim_data_by_replay_time(self):
        """
        根据播放轨道的最后时间戳裁剪数据
        
        功能说明：
        1. 计算播放轨道中最后一个音符的结束时间（key_off）
        2. 以该时间戳为基准，裁剪录制和播放轨道的数据
        3. 只保留按键开始时间（key_on）小于该时间戳的音符
        4. 重新更新按键索引，确保数据一致性
        
        目的：
        - 避免分析播放轨道结束后的录制数据，这些数据可能是无效的
        - 确保录制和播放数据在时间范围上保持一致
        - 提高分析结果的准确性和可靠性
        """
        # 计算播放轨道的最后时间戳（最后一个key_off）
        # 这个时间戳将作为数据裁剪的基准点
        if self.replay_data:
            try:
                # 遍历所有播放音符，找到最晚的按键结束时间
                replay_last_time = max(self._get_key_on_off(n)[1] for n in self.replay_data)
            except Exception:
                # 如果计算失败，设置为0，表示不进行裁剪
                replay_last_time = 0
        else:
            # 如果没有播放数据，设置为0
            replay_last_time = 0

        # 根据时间戳过滤两条轨道：仅保留 key_on < replay_last_time 的音符
        if replay_last_time > 0:
            # 记录裁剪前的数据量，用于日志记录
            before_filter_record = len(self.record_data) if self.record_data else 0
            before_filter_replay = len(self.replay_data) if self.replay_data else 0
            
            # 过滤录制轨道：只保留按键开始时间早于播放结束时间的音符
            self.record_data = [n for n in (self.record_data or []) if self._get_key_on_off(n)[0] < replay_last_time]
            
            # 过滤播放轨道：只保留按键开始时间早于播放结束时间的音符
            self.replay_data = [n for n in (self.replay_data or []) if self._get_key_on_off(n)[0] < replay_last_time]
            
            # 记录裁剪结果，便于调试和监控
            logger.info(f"基于播放最后时间戳 {replay_last_time} 进行裁剪: 录制 {before_filter_record}->{len(self.record_data)} 条, 播放 {before_filter_replay}->{len(self.replay_data)} 条")

            # 数据裁剪完成，按键索引将在错误分析后更新

    def _perform_error_analysis(self):
        """
        执行错误分析并合并所有错误音符
        
        功能说明：
        1. 调用spmid_analysis函数进行异常检测，识别三种类型的错误：
           - 多锤：播放时产生多个锤击，但录制时只有一个
           - 丢锤：录制时有锤击，但播放时没有
           - 不发声：录制时有锤击，但音量太小或没有声音输出
        2. 为每个错误音符添加错误类型标识和全局索引
        3. 将所有错误音符合并到一个统一的列表中，便于UI显示和后续处理
        
        分析范围：
        - 仅处理经过时间裁剪后的数据，确保分析结果的准确性
        """
        # 执行异常分析：调用核心分析函数，检测三种类型的错误
        # 返回5个值：多锤、丢锤、不发声锤子、有效录制数据、有效播放数据
        analysis_result = spmid.spmid_analysis(self.record_data, self.replay_data)
        
        # 检查返回格式是否正确
        if len(analysis_result) != 5:
            error_msg = f"分析结果格式错误：期望5个值，实际{len(analysis_result)}个值"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # 解包分析结果
        self.multi_hammers, self.drop_hammers, self.silent_hammers, self.valid_record_data, self.valid_replay_data = analysis_result

        # 初始化统一错误音符列表，用于存储所有类型的错误
        self.all_error_notes = []

        # 处理所有错误类型
        self._process_error_notes(self.multi_hammers, "多锤")
        self._process_error_notes(self.drop_hammers, "丢锤")
        self._process_error_notes(self.silent_hammers, "不发声")

        # 记录分析完成信息，便于调试和监控
        logger.info(f"SPMID数据加载完成 - 多锤问题: {len(self.multi_hammers)} 个, 丢锤问题: {len(self.drop_hammers)} 个, 不发声锤子: {len(self.silent_hammers)} 个")
        
        # 在生成有效数据后，重新构建按键索引
        # 确保按键索引使用有效数据而不是原始数据
        self.update_key_of_notes()
        logger.info("✅ 按键索引已更新为使用有效数据")

    def _process_error_notes(self, error_list, error_type):
        """
        处理错误音符列表，为每个音符添加类型标识和全局索引
        
        参数：
        - error_list: 错误音符列表
        - error_type: 错误类型名称
        """
        for error_note in error_list:
            error_note.error_type = error_type  # 设置错误类型
            error_note.global_index = len(self.all_error_notes)  # 分配全局索引
            self.all_error_notes.append(error_note)  # 添加到统一列表

    def _cleanup_temp_file(self, temp_file_path):
        """
        安全删除临时文件
        
        功能说明：
        1. 尝试删除之前创建的临时SPMID文件
        2. 使用重试机制处理可能的文件锁定或权限问题
        3. 如果删除失败，记录警告但不影响程序正常运行
        
        参数：
            temp_file_path (str): 要删除的临时文件路径
            
        重试机制：
        - 最多重试3次
        - 每次重试间隔0.2秒
        - 如果所有重试都失败，记录警告日志
        """
        max_retries = 3  # 最大重试次数
        last_exception = None  # 记录最后一次异常
        
        # 重试循环：处理可能的文件锁定或权限问题
        for attempt in range(max_retries):
            try:
                # 检查文件是否存在，然后尝试删除
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)  # 删除文件
                    logger.info("临时文件已删除")
                break  # 删除成功，退出重试循环
            except Exception as e:
                last_exception = e  # 记录异常信息
                time.sleep(0.2)  # 等待0.2秒后重试
        else:
            # 如果所有重试都失败，记录警告但不影响程序运行
            logger.warning(f"⚠️ 临时文件删除失败，但不影响功能: {temp_file_path}，错误信息: {last_exception}")

    def load_spmid_data(self, spmid_bytes):
        """
        加载SPMID文件数据并进行异常分析
        
        这是SPMID数据分析的主入口函数，负责协调整个数据加载和分析流程。
        
        处理流程：
        1. 文件验证：验证SPMID模块可用性，创建临时文件
        2. 数据加载：读取轨道数据，验证轨道数量，建立按键索引
        3. 数据裁剪：根据播放轨道结束时间裁剪数据，确保时间范围一致
        4. 错误分析：检测多锤、丢锤、不发声等异常情况
        5. 时间更新：更新分析的时间范围信息
        6. 资源清理：删除临时文件，释放系统资源
        
        参数：
            spmid_bytes (bytes): SPMID文件的二进制数据
            
        返回：
            bool: 加载成功返回True，失败返回False
            
        异常处理：
        - 对于轨道数量不足等严重错误，会重新抛出异常
        - 对于其他错误，记录日志并返回False
        """
        try:
            # 步骤1：验证文件并创建临时文件
            # 检查SPMID模块可用性，保存原始数据，创建临时文件
            temp_file_path = self._validate_spmid_file(spmid_bytes)
            
            # 步骤2：加载轨道数据
            # 读取SPMID文件，验证轨道数量，加载录制和播放数据
            self._load_track_data(temp_file_path)
            
            # 步骤3：裁剪数据
            # 根据播放轨道结束时间裁剪数据，确保时间范围一致性
            self._trim_data_by_replay_time()
            
            # 步骤4：执行错误分析
            # 检测多锤、丢锤、不发声等异常，合并错误音符列表
            self._perform_error_analysis()

            # 步骤5：更新时间范围
            # 更新分析的时间范围信息，用于UI显示和后续处理
            self._update_time_range()

            # 步骤6：清理临时文件
            # 安全删除临时文件，释放系统资源
            self._cleanup_temp_file(temp_file_path)

            return True  # 所有步骤成功完成

        except Exception as e:
            logger.warning(f"加载SPMID数据失败: {e}")
            import traceback
            traceback.print_exc()
            # 对于单音轨错误，重新抛出异常让上层处理
            if "轨道" in str(e) or "track" in str(e).lower() or "SPMID文件只包含" in str(e):
                raise e
            return False

    def get_summary_info(self):
        """获取汇总信息"""
        # 计算总的检测数量
        total_record_notes = len(self.record_data) if self.record_data else 0
        total_replay_notes = len(self.replay_data) if self.replay_data else 0
        total_notes = max(total_record_notes, total_replay_notes)

        # 获取异常数量
        multi_hammers_count = len(self.multi_hammers)
        drop_hammers_count = len(self.drop_hammers)
        silent_hammers_count = len(self.silent_hammers)
        total_errors = len(self.all_error_notes)

        # 计算有效音符和无效音符数量
        # 有效音符 = 总音符数 - 不发声音符数
        valid_notes = total_notes - silent_hammers_count
        invalid_notes = silent_hammers_count

        # 计算准确率（只统计有效音符）
        if valid_notes > 0:
            # 有效音符中的错误 = 多锤 + 丢锤（不包括不发声）
            valid_errors = multi_hammers_count + drop_hammers_count
            accuracy = ((valid_notes - valid_errors) / valid_notes) * 100
        else:
            accuracy = 100.0

        return {
            "total_notes": total_notes,
            "valid_notes": valid_notes,
            "invalid_notes": invalid_notes,
            "multi_hammers": multi_hammers_count,
            "drop_hammers": drop_hammers_count,
            "silent_hammers": silent_hammers_count,
            "multi_hammers_count": multi_hammers_count,
            "drop_hammers_count": drop_hammers_count,
            "silent_hammers_count": silent_hammers_count,
            "total_errors": total_errors,
            "accuracy": accuracy
        }

    
    def generate_waterfall_plot(self):
        """生成SPMID瀑布图"""
        try:
            print("🎨 开始生成SPMID瀑布图...")

            if not self.record_data and not self.replay_data:
                return self._create_empty_plot("请先上传SPMID文件")

            # 使用筛选后的数据
            filtered_record, filtered_replay = self.get_filtered_data()
            # 获取显示时间范围用于设置x轴
            display_time_range = self.get_display_time_range()
            fig = spmid.plot_bar_plotly(filtered_record, filtered_replay, display_time_range)

            if fig is not None:
                # 更新布局以适配应用界面
                fig.update_layout(
                    height=800,
                    title="SPMID数据瀑布图分析",
                    template='plotly_white'
                )
                logger.info("✅ 瀑布图生成完成")
                return fig
            else:
                logger.warning("⚠️ 瀑布图生成返回空图表")
                return self._create_empty_plot("瀑布图生成失败：没有可显示的数据")

        except Exception as e:
            logger.error(f"生成瀑布图失败: {e}")
            import traceback
            traceback.print_exc()
            return self._create_empty_plot(f"生成瀑布图失败: {str(e)}")
        
    # todo        
    def generate_watefall_conbine_plot(self, key_on, key_off, key_id):

        index1 = spmid.find_best_matching_notes_debug(notes_list=self.record_data,target_key_id=key_id, target_keyon=key_on, target_keyoff=key_off)
        index2 = spmid.find_best_matching_notes_debug(notes_list=self.replay_data,target_key_id=key_id, target_keyon=key_on, target_keyoff=key_off)
        detail_figure1 = spmid.plot_note_comparison_plotly(self.record_data[index1], None)
        detail_figure2 = spmid.plot_note_comparison_plotly(None, self.replay_data[index2])
        detail_figure_combined = spmid.plot_note_comparison_plotly(self.record_data[index1], self.replay_data[index2])

        return detail_figure1, detail_figure2, detail_figure_combined

    def generate_watefall_conbine_plot_by_index(self, index: int, is_record: bool):
        record_note = None
        play_note = None
        if is_record:
            if index < 0 or index >= len(self.record_data):
                return None
            record_note = self.record_data[index]
            play_note = spmid.find_best_matching_note(record_note, self.replay_key_of_notes.get(record_note.id, []))

        else:
            if index < 0 or index >= len(self.replay_data):
                return None
            play_note = self.replay_data[index]
            record_note = spmid.find_best_matching_note(play_note, self.record_key_of_notes.get(play_note.id, []))
        
        detail_figure1 = spmid.plot_note_comparison_plotly(record_note, None)
        detail_figure2 = spmid.plot_note_comparison_plotly(None, play_note)
        detail_figure_combined = spmid.plot_note_comparison_plotly(record_note, play_note)

        return detail_figure1, detail_figure2, detail_figure_combined
        

    def get_note_image_base64(self, global_index: int) -> str:
        if global_index >= len(self.all_error_notes):
            return self._create_error_image("索引超出范围")

        error_note = self.all_error_notes[global_index]

        if self.record_data and self.replay_data:
            return self._create_real_image_with_spmid(error_note)
        else:
            return self._create_error_image("无SPMID数据")

    def _create_real_image_with_spmid(self, error_note: spmid.ErrorNote) -> str:
        """创建基于SPMID数据的错误分析图片"""
        try:
            if len(error_note.infos) == 0:
                return self._create_error_image("无数据")

            record_info = error_note.infos[0]
            self._setup_plot_figure()

            if len(error_note.infos) == 1:
                # 丢锤情况
                return self._create_drop_hammer_image(record_info)
            else:
                # 多锤情况
                play_info = error_note.infos[1]
                return self._create_multi_hammer_image(record_info, play_info)

        except Exception as e:
            logger.error(f"创建真实图片时出错: {e}")
            import traceback
            traceback.print_exc()
            return self._create_error_image(f"图片生成错误: {str(e)}")

    def _setup_plot_figure(self):
        """设置绘图基础配置"""
        plt.figure(figsize=(12, 6))
        plt.clf()

    def _create_drop_hammer_image(self, record_info) -> str:
        """创建丢锤检测图片"""
        if record_info.index >= len(self.record_data):
            return self._create_error_image("录制数据索引无效")

        record_note = self.record_data[record_info.index]

        # 绘制录制数据
        self._plot_record_data(record_note)
        
        # 设置图表样式
        self._setup_drop_hammer_style(record_info.keyId)
        
        return self._convert_plot_to_base64()

    def _create_multi_hammer_image(self, record_info, play_info) -> str:
        """创建多锤检测图片"""
        if (record_info.index >= len(self.record_data) or 
            play_info.index >= len(self.replay_data)):
            return self._create_error_image("数据索引无效")

        try:
            # 尝试使用spmid的内置函数
            return self._create_multi_hammer_with_spmid(record_info, play_info)
        except Exception:
            # 回退到手动绘制
            return self._create_multi_hammer_manual(record_info, play_info)

    def _create_multi_hammer_with_spmid(self, record_info, play_info) -> str:
        """使用spmid内置函数创建多锤图片"""
        # 使用spmid的算法生成对比图
        fig = spmid.get_figure_by_index(self.record_data, self.replay_data,
                                                record_info.index, play_info.index)

        # 设置中文标题和标签
        self._setup_multi_hammer_style(record_info.keyId)
        self._update_legend_to_chinese()
        
        return self._convert_plot_to_base64()

    def _create_multi_hammer_manual(self, record_info, play_info) -> str:
        """手动绘制多锤检测图片"""
        record_note = self.record_data[record_info.index]
        play_note = self.replay_data[play_info.index]

        # 绘制录制和播放数据
        self._plot_record_data(record_note)
        self._plot_play_data(play_note)
        
        # 设置图表样式
        self._setup_multi_hammer_style(record_info.keyId)
        
        return self._convert_plot_to_base64()

    def _plot_record_data(self, record_note):
        """绘制录制数据"""
        record_note.after_touch.plot(label='录制 after_touch', color='blue', linewidth=2)
        plt.scatter(x=record_note.hammers.index, y=record_note.hammers.values,
                                  color='blue', label='录制 hammers', s=60, alpha=0.7)

    def _plot_play_data(self, play_note):
        """绘制播放数据"""
        play_note.after_touch.plot(label='播放 after_touch', color='red', linewidth=2)
        plt.scatter(x=play_note.hammers.index, y=play_note.hammers.values,
                                  color='red', label='播放 hammers', s=60, alpha=0.7)

    def _setup_drop_hammer_style(self, key_id):
        """设置丢锤检测图表样式"""
        plt.title(f'丢锤检测 - 键位 {key_id} [检测到丢锤]',
                 fontsize=16, color='red', fontweight='bold')
        self._setup_common_style()

    def _setup_multi_hammer_style(self, key_id):
        """设置多锤检测图表样式"""
        plt.title(f'多锤检测 - 键位 {key_id} [检测到多锤]',
                                 fontsize=16, color='orange', fontweight='bold')
        self._setup_common_style()

    def _setup_common_style(self):
        """设置通用图表样式"""
        plt.xlabel('时间 (100us)', fontsize=12)
        plt.ylabel('力度值', fontsize=12)
        plt.legend(fontsize=11)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()

    def _update_legend_to_chinese(self):
        """将图例更新为中文"""
        handles, labels = plt.gca().get_legend_handles_labels()
        new_labels = []
        
        label_mapping = {
            'record after_touch': '录制 after_touch',
            'record hammers': '录制 hammers',
            'play after_touch': '播放 after_touch',
            'play hammers': '播放 hammers'
        }
        
        for label in labels:
            new_labels.append(label_mapping.get(label, label))
        
        plt.legend(handles, new_labels, fontsize=11)

    def _convert_plot_to_base64(self) -> str:
        """将matplotlib图形转换为base64字符串"""
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight')
        img_buffer.seek(0)
        img_base64 = base64.b64encode(img_buffer.read()).decode('utf-8')
        plt.close()

        return f"data:image/png;base64,{img_base64}"

    def _create_error_image(self, error_msg: str) -> str:
        """创建错误提示图片"""
        plt.figure(figsize=(8, 4))
        plt.text(0.5, 0.5, f"错误: {error_msg}", ha='center', va='center',
                fontsize=16, color='red', transform=plt.gca().transAxes)
        plt.axis('off')

        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight')
        img_buffer.seek(0)
        img_base64 = base64.b64encode(img_buffer.read()).decode('utf-8')
        plt.close()

        return f"data:image/png;base64,{img_base64}"

    def _create_empty_plot(self, message):
        """创建空图表"""
        fig = go.Figure()
        fig.add_annotation(
            text=message,
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=16)
        )
        fig.update_layout(
            height=400,
            xaxis=dict(visible=False),
            yaxis=dict(visible=False)
        )
        return fig

    def get_multi_hammers_data(self):
        """获取多锤表格数据"""
        table_data = []
        for i, error_note in enumerate(self.multi_hammers):
            # 录制数据行
            if len(error_note.infos) > 0 and len(error_note.diffs) > 0:
                record_info = error_note.infos[0]
                record_diff = error_note.diffs[0]
                table_data.append({
                    'global_index': error_note.global_index,
                    'problem_type': error_note.error_type,
                    'data_type': 'record',
                    'keyId': record_info.keyId,
                    'keyOn': record_info.keyOn,
                    'keyOff': record_info.keyOff,
                    'mean': f"{record_diff.mean:.2f}",
                    'std': f"{record_diff.std:.2f}",
                    'max': f"{record_diff.max:.2f}",
                    'min': f"{record_diff.min:.2f}",
                    "index": record_info.index
                })

            # 播放数据行 - 如果没有播放数据，显示"无匹配数据"
            if len(error_note.infos) > 1 and len(error_note.diffs) > 1:
                play_info = error_note.infos[1]
                play_diff = error_note.diffs[1]
                table_data.append({
                    'global_index': error_note.global_index,
                    'problem_type': '',
                    'data_type': 'play',
                    'keyId': play_info.keyId,
                    'keyOn': play_info.keyOn,
                    'keyOff': play_info.keyOff,
                    'mean': f"{play_diff.mean:.2f}",
                    'std': f"{play_diff.std:.2f}",
                    'max': f"{play_diff.max:.2f}",
                    'min': f"{play_diff.min:.2f}",
                    'index': play_info.index
                })
            else:
                # 没有匹配的播放数据
                table_data.append({
                    'global_index': error_note.global_index,
                    'problem_type': '',
                    'data_type': 'play',
                    'keyId': '无匹配',
                    'keyOn': '无匹配',
                    'keyOff': '无匹配',
                    'mean': '无匹配',
                    'std': '无匹配',
                    'max': '无匹配',
                    'min': '无匹配'
                })
        return table_data

    def get_available_keys(self):
        """获取可用的键ID列表"""
        if not self.available_keys and (self.record_data or self.replay_data):
            self._update_available_keys()
        return self.available_keys

    def _update_available_keys(self):
        """更新可用的键ID列表"""
        all_keys = set()
        key_stats = {}
        
        # 收集录制和播放数据中的所有键ID
        for track_data in [self.record_data, self.replay_data]:
            if track_data:
                for note in track_data:
                    if hasattr(note, 'id'):
                        key_id = int(note.id)
                        # 检查音符是否有有效的数据（after_touch或hammers不为空）
                        has_valid_data = False
                        if hasattr(note, 'after_touch') and note.after_touch is not None and not note.after_touch.empty:
                            has_valid_data = True
                        elif hasattr(note, 'hammers') and note.hammers is not None and not note.hammers.empty:
                            has_valid_data = True
                        
                        if has_valid_data:
                            all_keys.add(key_id)
                            key_stats[key_id] = key_stats.get(key_id, 0) + 1
        
        # 生成键ID选项列表
        self.available_keys = []
        for key_id in sorted(all_keys):
            count = key_stats.get(key_id, 0)
            key_name = self._get_key_name(key_id)
            self.available_keys.append({
                'label': f'{key_name} (ID:{key_id}, {count}次)',
                'value': key_id
            })
        
        logger.info(f"📊 更新可用键ID列表: {len(self.available_keys)} 个键位")

    def _get_key_name(self, key_id):
        """获取键位名称"""
        if key_id == 89:
            return "右踏板"
        elif key_id == 90:
            return "左踏板"
        else:
            return f"键位{key_id}"

    def set_key_filter(self, key_ids):
        """设置键ID筛选器"""
        self.key_filter = key_ids if key_ids else None
        logger.info(f"🔍 设置键ID筛选器: {self.key_filter}")

        """获取筛选后的数据"""
        if not self.key_filter:
            return self.record_data, self.replay_data
        
        filtered_record = []
        filtered_replay = []
        
        # 筛选录制数据
        if self.record_data:
            for note in self.record_data:
                if hasattr(note, 'id') and int(note.id) in self.key_filter:
                    filtered_record.append(note)
        
        # 筛选播放数据
        if self.replay_data:
            for note in self.replay_data:
                if hasattr(note, 'id') and int(note.id) in self.key_filter:
                    filtered_replay.append(note)
        
        logger.info(f"🔍 键ID筛选结果: 录制 {len(filtered_record)}/{len(self.record_data or [])} 个音符, 播放 {len(filtered_replay)}/{len(self.replay_data or [])} 个音符")
        return filtered_record, filtered_replay

    def get_key_filter_status(self):
        """获取键ID筛选状态信息"""
        if not self.key_filter:
            return "显示全部键位"
        
        key_names = []
        for key_id in self.key_filter:
            key_names.append(self._get_key_name(key_id))
        
        return f"当前显示：{', '.join(key_names)} ({len(self.key_filter)}个键位)"

    def get_offset_alignment_data(self):
        """获取偏移对齐表格数据"""
        try:
            # 检查有效数据是否存在
            if self.valid_record_data is None or self.valid_replay_data is None:
                logger.error("有效数据不存在，无法生成偏移对齐数据")
                return [{
                    'key_id': "错误",
                    'count': 0,
                    'median': "N/A",
                    'mean': "N/A",
                    'std': "N/A"
                }]
            
            df_stats, all_offsets = self.spmid_offset_alignment()
            
            # 将DataFrame转换为表格数据格式
            table_data = []
            for _, row in df_stats.iterrows():
                table_data.append({
                    'key_id': int(row['key_id']),
                    'count': int(row['count']),
                    'median': f"{row['median']:.2f}" if not pd.isna(row['median']) else "N/A",
                    'mean': f"{row['mean']:.2f}" if not pd.isna(row['mean']) else "N/A",
                    'std': f"{row['std']:.2f}" if not pd.isna(row['std']) else "N/A"
                })
            
            # 添加总体统计行
            if len(all_offsets) > 0:
                table_data.append({
                    'key_id': "总体",
                    'count': len(all_offsets),
                    'median': f"{np.median(all_offsets):.2f}",
                    'mean': f"{np.mean(all_offsets):.2f}",
                    'std': f"{np.std(all_offsets):.2f}"
                })
            
            return table_data
        except Exception as e:
            logger.error(f"获取偏移对齐数据失败: {e}")
            return [{
                'key_id': "错误",
                'count': 0,
                'median': "N/A",
                'mean': "N/A",
                'std': "N/A"
            }]

    def _update_time_range(self):
        """更新数据的时间范围"""
        all_times = []
        
        # 收集录制和播放数据中的所有时间戳
        for track_data in [self.record_data, self.replay_data]:
            if track_data:
                for note in track_data:
                    if hasattr(note, 'after_touch') and note.after_touch is not None and not note.after_touch.empty:
                        # 计算音符的开始和结束时间
                        try:
                            key_on = int(note.after_touch.index[0]) + int(note.offset)
                            key_off = int(note.after_touch.index[-1]) + int(note.offset)
                            all_times.extend([key_on, key_off])
                        except (ValueError, TypeError) as e:
                            logger.warning(f"⚠️ 跳过无效时间戳: {e}")
                            continue
        
        if all_times:
            time_min, time_max = min(all_times), max(all_times)
            # 确保时间范围合理
            if time_min == time_max:
                time_max = time_min + 1000  # 添加默认范围
            self.time_range = (time_min, time_max)
            logger.info(f"⏰ 更新时间范围: {self.time_range[0]} - {self.time_range[1]} (100us), 共收集 {len(all_times)} 个时间点")
        else:
            self.time_range = (0, 1000)  # 默认范围
            logger.warning("⚠️ 没有找到有效的时间数据，使用默认时间范围")

    def get_time_range(self):
        """获取数据的时间范围"""
        if not self.time_range:
            self._update_time_range()
        return self.time_range

    def _get_original_time_range(self):
        """获取原始数据的时间范围（不受用户设置影响）"""
        if not self.time_range:
            self._update_time_range()
        return self.time_range

    def get_display_time_range(self):
        """获取显示时间范围（用户设置的或原始数据范围）"""
        if self.display_time_range:
            return self.display_time_range
        else:
            return self.get_time_range()

    def set_time_filter(self, time_range):
        """设置时间轴筛选范围"""
        if time_range and len(time_range) == 2:
            start_time, end_time = time_range
            if start_time < end_time:
                self.time_filter = (int(start_time), int(end_time))
                logger.info(f"⏰ 设置时间轴筛选: {self.time_filter[0]} - {self.time_filter[1]} (100us)")
            else:
                self.time_filter = None
                logger.warning("⏰ 时间范围无效，已清除筛选")
        else:
            self.time_filter = None
            logger.info("⏰ 清除时间轴筛选")

    def get_time_filter_status(self):
        """获取时间轴筛选状态信息"""
        if not self.time_filter:
            return "显示全部时间范围"
        
        start_time, end_time = self.time_filter
        return f"时间范围: {start_time} - {end_time} (100us)"

    def update_time_range_from_input(self, start_time, end_time):
        """
        根据用户输入的时间范围设置显示的时间范围（不影响原始数据范围）
        Args:
            start_time (int): 开始时间 (100us)
            end_time (int): 结束时间 (100us)
        Returns:
            tuple: (success, message) - 成功状态和消息
        """
        try:
            # 验证输入参数
            if start_time is None or end_time is None:
                return False, "开始时间和结束时间不能为空"
            
            start_time = int(start_time)
            end_time = int(end_time)
            
            if start_time < 0 or end_time < 0:
                return False, "时间值不能为负数"
            
            if start_time >= end_time:
                return False, "开始时间必须小于结束时间"
            
            # 获取原始数据的时间范围（用于验证）
            original_min, original_max = self._get_original_time_range()
            
            # 验证输入范围是否在原始数据范围内
            if start_time < original_min:
                return False, f"开始时间 {start_time} 小于数据最小时间 {original_min}"
            
            if end_time > original_max:
                return False, f"结束时间 {end_time} 大于数据最大时间 {original_max}"
            
            # 设置显示时间范围（不影响原始数据）
            self.display_time_range = (start_time, end_time)
            logger.info(f"⏰ 用户设置显示时间范围: {start_time} - {end_time} (100us)")
            
            return True, f"显示时间范围已设置为: {start_time} - {end_time} (100us)"
            
        except (ValueError, TypeError) as e:
            return False, f"时间值格式错误: {str(e)}"
        except Exception as e:
            logger.error(f"❌ 设置显示时间范围失败: {e}")
            return False, f"设置显示时间范围失败: {str(e)}"

    def get_time_range_info(self):
        """获取时间范围信息，用于UI显示"""
        if not self.time_range:
            self._update_time_range()
        
        min_time, max_time = self.time_range
        return {
            'min_time': min_time,
            'max_time': max_time,
            'range': max_time - min_time,
            'current_filter': self.time_filter
        }

    def reset_display_time_range(self):
        """重置显示时间范围到原始数据范围"""
        self.display_time_range = None
        logger.info("⏰ 重置显示时间范围到原始数据范围")

    def get_filtered_data(self):
        """获取筛选后的数据（同时应用键ID和时间轴筛选）"""
        # 使用有效数据（经过发声检测过滤的数据）而不是原始数据
        base_record_data = self.valid_record_data if self.valid_record_data is not None else self.record_data
        base_replay_data = self.valid_replay_data if self.valid_replay_data is not None else self.replay_data
        
        # 首先应用键ID筛选
        if not self.key_filter:
            filtered_record = base_record_data
            filtered_replay = base_replay_data
        else:
            filtered_record = []
            filtered_replay = []
            
            # 筛选录制数据
            if base_record_data:
                for note in base_record_data:
                    if hasattr(note, 'id') and int(note.id) in self.key_filter:
                        filtered_record.append(note)
            
            # 筛选播放数据
            if base_replay_data:
                for note in base_replay_data:
                    if hasattr(note, 'id') and int(note.id) in self.key_filter:
                        filtered_replay.append(note)
        
        # 然后应用时间轴筛选
        if self.time_filter:
            start_time, end_time = self.time_filter
            
            # 时间轴筛选录制数据
            if filtered_record:
                time_filtered_record = []
                for note in filtered_record:
                    if hasattr(note, 'after_touch') and note.after_touch is not None and not note.after_touch.empty:
                        key_on = int(note.after_touch.index[0]) + int(note.offset)
                        key_off = int(note.after_touch.index[-1]) + int(note.offset)
                        # 检查音符是否与时间范围有重叠
                        if not (key_off < start_time or key_on > end_time):
                            time_filtered_record.append(note)
                filtered_record = time_filtered_record
            
            # 时间轴筛选播放数据
            if filtered_replay:
                time_filtered_replay = []
                for note in filtered_replay:
                    if hasattr(note, 'after_touch') and note.after_touch is not None and not note.after_touch.empty:
                        key_on = int(note.after_touch.index[0]) + int(note.offset)
                        key_off = int(note.after_touch.index[-1]) + int(note.offset)
                        # 检查音符是否与时间范围有重叠
                        if not (key_off < start_time or key_on > end_time):
                            time_filtered_replay.append(note)
                filtered_replay = time_filtered_replay
        
        logger.info(f"🔍 综合筛选结果: 录制 {len(filtered_record or [])}/{len(self.record_data or [])} 个音符, 播放 {len(filtered_replay or [])}/{len(self.replay_data or [])} 个音符")
        return filtered_record, filtered_replay

    def get_drop_hammers_data(self):
        """获取丢锤表格数据"""
        table_data = []
        for i, error_note in enumerate(self.drop_hammers):
            # 录制数据行
            if len(error_note.infos) > 0 and len(error_note.diffs) > 0:
                record_info = error_note.infos[0]
                record_diff = error_note.diffs[0]
                table_data.append({
                    'global_index': error_note.global_index,
                    'problem_type': error_note.error_type,
                    'data_type': 'record',
                    'keyId': record_info.keyId,
                    'keyOn': record_info.keyOn,
                    'keyOff': record_info.keyOff,
                    'mean': f"{record_diff.mean:.2f}",
                    'std': f"{record_diff.std:.2f}",
                    'max': f"{record_diff.max:.2f}",
                    'min': f"{record_diff.min:.2f}",
                    'index': record_info.index
                })

            # 播放数据行 - 如果没有播放数据，显示"无匹配数据"
            if len(error_note.infos) > 1 and len(error_note.diffs) > 1:
                play_info = error_note.infos[1]
                play_diff = error_note.diffs[1]
                table_data.append({
                    'global_index': error_note.global_index,
                    'problem_type': '',
                    'data_type': 'play',
                    'keyId': play_info.keyId,
                    'keyOn': play_info.keyOn,
                    'keyOff': play_info.keyOff,
                    'mean': f"{play_diff.mean:.2f}",
                    'std': f"{play_diff.std:.2f}",
                    'max': f"{play_diff.max:.2f}",
                    'min': f"{play_diff.min:.2f}",
                    'index': play_info.index
                })
            else:
                # 没有匹配的播放数据
                table_data.append({
                    'global_index': error_note.global_index,
                    'problem_type': '',
                    'data_type': 'play',
                    'keyId': '无匹配',
                    'keyOn': '无匹配',
                    'keyOff': '无匹配',
                    'mean': '无匹配',
                    'std': '无匹配',
                    'max': '无匹配',
                    'min': '无匹配'
                })
        return table_data

    def get_available_keys(self):
        """获取可用的键ID列表"""
        if not self.available_keys and (self.record_data or self.replay_data):
            self._update_available_keys()
        return self.available_keys

    def _update_available_keys(self):
        """更新可用的键ID列表"""
        all_keys = set()
        key_stats = {}
        
        # 收集录制和播放数据中的所有键ID
        for track_data in [self.record_data, self.replay_data]:
            if track_data:
                for note in track_data:
                    if hasattr(note, 'id'):
                        key_id = int(note.id)
                        # 检查音符是否有有效的数据（after_touch或hammers不为空）
                        has_valid_data = False
                        if hasattr(note, 'after_touch') and note.after_touch is not None and not note.after_touch.empty:
                            has_valid_data = True
                        elif hasattr(note, 'hammers') and note.hammers is not None and not note.hammers.empty:
                            has_valid_data = True
                        
                        if has_valid_data:
                            all_keys.add(key_id)
                            key_stats[key_id] = key_stats.get(key_id, 0) + 1
        
        # 生成键ID选项列表
        self.available_keys = []
        for key_id in sorted(all_keys):
            count = key_stats.get(key_id, 0)
            key_name = self._get_key_name(key_id)
            self.available_keys.append({
                'label': f'{key_name} (ID:{key_id}, {count}次)',
                'value': key_id
            })
        
        logger.info(f"📊 更新可用键ID列表: {len(self.available_keys)} 个键位")

    def _get_key_name(self, key_id):
        """获取键位名称"""
        if key_id == 89:
            return "右踏板"
        elif key_id == 90:
            return "左踏板"
        else:
            return f"键位{key_id}"

    def set_key_filter(self, key_ids):
        """设置键ID筛选器"""
        self.key_filter = key_ids if key_ids else None
        logger.info(f"🔍 设置键ID筛选器: {self.key_filter}")

    def get_key_filter_status(self):
        """获取键ID筛选状态信息"""
        if not self.key_filter:
            return "显示全部键位"
        
        key_names = []
        for key_id in self.key_filter:
            key_names.append(self._get_key_name(key_id))
        
        return f"当前显示：{', '.join(key_names)} ({len(self.key_filter)}个键位)"
