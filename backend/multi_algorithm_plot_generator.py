#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
多算法图表生成器

负责生成支持多算法对比的图表，使用面向对象设计。
"""
import math
import traceback
from typing import List, Optional, Any, Dict, Tuple
import plotly.graph_objects as go
import numpy as np
from backend.multi_algorithm_manager import AlgorithmDataset
from utils.logger import Logger
from utils.colors import ALGORITHM_COLOR_PALETTE

logger = Logger.get_logger()


class MultiAlgorithmPlotGenerator:
    """
    多算法图表生成器类
    
    负责生成支持多算法对比的图表，包括：
    - 瀑布图（多算法叠加显示）
    - 偏移对齐分析图（多算法并排柱状图）
    - 延时分布直方图（多算法叠加显示）
    """
    
    def __init__(self, key_filter=None):
        """
        初始化多算法图表生成器
        
        Args:
            key_filter: 按键过滤器实例（可选）
        """
        self.key_filter = key_filter
        
        # 使用全局颜色方案
        self.COLORS = ALGORITHM_COLOR_PALETTE
        
    
    def generate_unified_waterfall_plot(
        self,
        backend,                        # 后端实例，用于获取全局平均延时
        analyzers: List[Any],           # 分析器列表，根据SPMID文件数量自动处理
        algorithm_names: List[str],     # 算法名称列表
        time_filter=None,
        key_filter=None
    ) -> Any:
        """
        生成统一的瀑布图（自动根据SPMID文件数量处理）
        
        根据analyzers的数量自动判断：
        - 1个文件：不需要y轴偏移
        - 多个文件：每个文件分配独立的y轴范围
        
        Args:
            backend: 后端实例
            analyzers: 分析器列表
            algorithm_names: 算法名称列表
            time_filter: 时间过滤器
            key_filter: 按键过滤器
            
        Returns:
            go.Figure: Plotly图表对象
        """
        if not analyzers:
            logger.warning("没有分析器，无法生成瀑布图")
            return self._create_empty_plot("没有分析器")

        try:
            # 自动判断是否为多文件模式
            is_multi_file = len(analyzers) > 1
            logger.info(f"开始生成瀑布图，共 {len(analyzers)} 个SPMID文件")

            # 根据文件数量决定是否分配y_offset范围
            algorithm_y_range = 100 if is_multi_file else 0  # 多文件时每个分配100的y轴范围

            # 获取平均延时数据
            avg_delay_ms = self._get_average_delay(backend, is_multi_file, algorithm_names)
            
            # 收集所有数据点用于全局归一化
            all_bars_by_algorithm = []

            # 处理每个分析器
            for alg_idx, (analyzer, algorithm_name) in enumerate(zip(analyzers, algorithm_names)):
                if not analyzer:
                    logger.warning(f"分析器 '{algorithm_name}' 为空，跳过")
                    continue

                # 计算当前算法的y_offset
                current_y_offset = alg_idx * algorithm_y_range if is_multi_file else 0

                # 收集当前分析器的完整数据：匹配对 + 丢锤 + 多锤
                algorithm_bars = self._collect_algorithm_comprehensive_data(
                    analyzer, current_y_offset, algorithm_name, alg_idx, avg_delay_ms
                )

                all_bars_by_algorithm.append({
                    'analyzer': analyzer,
                    'bars': algorithm_bars,
                    'algorithm_name': algorithm_name,
                    'y_offset': current_y_offset
                })

            if not all_bars_by_algorithm:
                logger.warning("没有有效的数据点，无法生成瀑布图")
                return self._create_empty_plot("没有有效的数据点")

            # 收集所有有效的锤速值并计算全局范围（用于颜色归一化）
            all_values = self._collect_velocity_values(all_bars_by_algorithm)
            vmin, vmax = self._calculate_velocity_range(all_values)

            # 创建图表
            fig = go.Figure()
            
            # 为每个条形段添加trace
            total_bars = 0
            drop_hammer_bars = 0
            multi_hammer_bars = 0
            matched_bars = 0
            
            for alg_data in all_bars_by_algorithm:
                bars = alg_data['bars']
                algorithm_name = alg_data['algorithm_name']

                logger.info(f"算法 '{algorithm_name}': 准备绘制 {len(bars)} 个bars")

                for bar in bars:
                    total_bars += 1
                    data_type = bar.get('data_type', '')
                    if data_type == 'drop_hammer':
                        drop_hammer_bars += 1
                    elif data_type == 'multi_hammer':
                        multi_hammer_bars += 1
                    else:
                        matched_bars += 1

                    # 添加bar的trace
                    success = self._add_waterfall_bar_trace(fig, bar, algorithm_name, vmin, vmax)
                    if not success:
                        # 数据无效被跳过，统计需要调整
                        total_bars -= 1
                        if data_type == 'drop_hammer':
                            drop_hammer_bars -= 1
                        elif data_type == 'multi_hammer':
                            multi_hammer_bars -= 1
                        else:
                            matched_bars -= 1
            
            # 配置图表布局
            self._configure_unified_waterfall_layout(fig, all_bars_by_algorithm, is_multi_file)

            logger.info(f"瀑布图生成成功: 总计 {total_bars} 个bars (匹配对: {matched_bars}, 丢锤: {drop_hammer_bars}, 多锤: {multi_hammer_bars})")
            return fig

        except Exception as e:
            return self._handle_generation_error(e, "瀑布图")

    def _collect_algorithm_comprehensive_data(self, analyzer, y_offset: float, algorithm_name: str, alg_idx: int, avg_delay_ms: float = 0.0) -> List[Dict]:
        """
        收集单个算法的完整瀑布图数据：匹配对 + 丢锤 + 多锤

        这个方法作为统一入口，协调各个子模块的数据收集工作。

        Args:
            analyzer: SPMIDAnalyzer实例
            y_offset: Y轴偏移量
            algorithm_name: 算法名称
            alg_idx: 算法索引
            avg_delay_ms: 平均延时（用于相对延时计算）

        Returns:
            List[Dict]: 该算法的所有瀑布图数据
        """
        algorithm_bars = []

        logger.info(f"开始收集算法 '{algorithm_name}' 的瀑布图数据")

        # 1. 收集匹配对数据（成功和失败的匹配）
        matched_bars = self._collect_matched_pair_data(analyzer, y_offset, algorithm_name, avg_delay_ms)
        algorithm_bars.extend(matched_bars)

        # 2. 收集丢锤数据
        drop_hammer_bars = self._collect_drop_hammer_data(analyzer, y_offset, algorithm_name)
        algorithm_bars.extend(drop_hammer_bars)

        # 3. 收集多锤数据
        multi_hammer_bars = self._collect_multi_hammer_data(analyzer, y_offset, algorithm_name)
        algorithm_bars.extend(multi_hammer_bars)

        return algorithm_bars

    def _collect_matched_pair_data(self, analyzer, y_offset: float, algorithm_name: str, avg_delay_ms: float) -> List[Dict]:
        """
        收集匹配对数据（成功匹配和失败匹配）

        Args:
            analyzer: SPMIDAnalyzer实例
            y_offset: Y轴偏移量
            algorithm_name: 算法名称
            avg_delay_ms: 平均延时

        Returns:
            List[Dict]: 匹配对的瀑布图数据
        """
        bars = []

        if not hasattr(analyzer, 'note_matcher') or not analyzer.note_matcher:
            logger.info("没有note_matcher，跳过匹配对数据收集")
            return bars

        note_matcher = analyzer.note_matcher
        if not hasattr(note_matcher, 'match_results'):
            logger.info("没有match_results，跳过匹配对数据收集")
            return bars

        logger.info(f"开始收集匹配对数据，共 {len(note_matcher.match_results)} 个匹配结果")

        for result in note_matcher.match_results:
            try:
                # 获取录制和播放音符
                record_note = note_matcher._record_data[result.record_index]
                replay_note = note_matcher._replay_data[result.replay_index] if result.replay_index is not None else None

                # 计算延时和评级
                grade_name, color_intensity, delay_ms, relative_delay_ms = self._calculate_match_grading(
                    result, record_note, replay_note, avg_delay_ms
                )

                record_match_index = getattr(result, 'record_index', 'N/A')
                replay_match_index = getattr(result, 'replay_index', 'N/A')

                # 处理录制数据
                if hasattr(record_note, 'after_touch') and record_note.after_touch is not None:
                    record_bars = self._extract_note_bars_for_multi(
                        record_note, 'record', y_offset, color_intensity,
                        algorithm_name, grade_name, record_match_index, delay_ms, relative_delay_ms
                    )
                    bars.extend(record_bars)

                    # 处理播放数据（如果存在）
                    if replay_note is not None and hasattr(replay_note, 'after_touch') and replay_note.after_touch is not None:
                        replay_bars = self._extract_note_bars_for_multi(
                            replay_note, 'replay', y_offset, color_intensity,
                            algorithm_name, grade_name, replay_match_index, delay_ms, relative_delay_ms
                        )

                        # 合并hover信息
                        if record_bars and replay_bars:
                            self._merge_matched_hover_info(record_bars, replay_bars, avg_delay_ms)

                        bars.extend(replay_bars)

            except (IndexError, AttributeError, TypeError) as e:
                logger.warning(f"处理匹配结果失败: {e}")
                continue

        logger.info(f"匹配对数据收集完成: {len(bars)} 个bars")
        return bars

    def _collect_error_hammer_data(
        self, 
        analyzer, 
        y_offset: float, 
        algorithm_name: str,
        error_type: str,
        errors: List,
        data_source: List,
        data_type: str,
        error_label: str,
        error_description: str
    ) -> List[Dict]:
        """
        统一的错误锤数据收集方法
        
        Args:
            analyzer: SPMIDAnalyzer实例
            y_offset: Y轴偏移量
            algorithm_name: 算法名称
            error_type: 错误类型标识 ('drop_hammer' 或 'multi_hammer')
            errors: 错误列表
            data_source: 数据源列表
            data_type: 数据类型 ('record' 或 'replay')
            error_label: 错误标签（用于悬停文本标题）
            error_description: 错误描述（用于悬停文本详情）
            
        Returns:
            List[Dict]: 错误锤的瀑布图数据
        """
        bars = []
        
        if not errors:
            logger.info(f"没有{error_label}数据")
            return bars
        
        logger.info(f"开始收集{error_label}数据: {len(errors)} 个")
        
        for idx, error_note in enumerate(errors):
            try:
                # 获取音符索引
                note_index = self._get_error_note_index(error_note)
                
                # 验证索引并获取note对象
                if not self._is_valid_index(note_index, len(data_source)):
                    continue
                
                note = data_source[note_index]
                if note is None:
                    note = self._create_default_note(error_note, note_index)
                
                # 只处理有after_touch数据的note
                if hasattr(note, 'after_touch') and note.after_touch is not None and hasattr(note.after_touch, 'index') and len(note.after_touch.index) > 0:
                    bars.extend(self._extract_note_bars_for_multi(
                        note, data_type, y_offset, 0.1, algorithm_name,
                        "失败", note_index, 0.0, 0.0, error_type
                    ))
                    
                    # 创建悬停信息
                    for bar in bars[-1:]:  # 只处理刚添加的bar
                        bar['text'] = f'<b>{error_label}:</b><br>' + \
                                     f'类型: {data_type}<br>' + \
                                     f'键位: {getattr(note, "id", "N/A")}<br>' + \
                                     f'锤速: {self._extract_hammer_velocity(note)}<br>' + \
                                     f'等级: 失败 ({error_label})<br>' + \
                                     f'索引: {note_index}<br>' + \
                                     f'按键按下: {bar["t_on"]/10:.2f}ms<br>' + \
                                     f'按键释放: {bar["t_off"]/10:.2f}ms<br>' + \
                                     f'错误类型: {error_description}<br>'
                    
                    logger.info(f"{error_label} #{idx} 处理完成")
                else:
                    logger.warning(f"{error_label} #{idx} 缺少after_touch数据，跳过")
            
            except Exception as e:
                logger.error(f"处理{error_label} #{idx} 失败: {e}")
                continue
        
        logger.info(f"{error_label}数据收集完成: {len(bars)} 个bars")
        return bars
    
    def _collect_drop_hammer_data(self, analyzer, y_offset: float, algorithm_name: str) -> List[Dict]:
        """
        收集丢锤错误数据

        Args:
            analyzer: SPMIDAnalyzer实例
            y_offset: Y轴偏移量
            algorithm_name: 算法名称

        Returns:
            List[Dict]: 丢锤的瀑布图数据
        """
        return self._collect_error_hammer_data(
            analyzer=analyzer,
            y_offset=y_offset,
            algorithm_name=algorithm_name,
            error_type='drop_hammer',
            errors=getattr(analyzer, 'drop_hammers', []),
            data_source=getattr(analyzer, 'initial_valid_record_data', []),
            data_type='record',
            error_label='丢锤错误 (录制数据)',
            error_description='丢锤 (播放数据缺失)'
        )

    def _collect_multi_hammer_data(self, analyzer, y_offset: float, algorithm_name: str) -> List[Dict]:
        """
        收集多锤错误数据

        Args:
            analyzer: SPMIDAnalyzer实例
            y_offset: Y轴偏移量
            algorithm_name: 算法名称

        Returns:
            List[Dict]: 多锤的瀑布图数据
        """
        return self._collect_error_hammer_data(
            analyzer=analyzer,
            y_offset=y_offset,
            algorithm_name=algorithm_name,
            error_type='multi_hammer',
            errors=getattr(analyzer, 'multi_hammers', []),
            data_source=getattr(analyzer, 'initial_valid_replay_data', []),
            data_type='replay',
            error_label='多锤错误 (播放数据)',
            error_description='多锤 (录制数据缺失)'
        )

    def _calculate_match_grading(self, result, record_note, replay_note, avg_delay_ms: float):
        """
        计算匹配结果的评级和延时信息

        Returns:
            tuple: (grade_name, color_intensity, delay_ms, relative_delay_ms)
        """
        grade_name = "未知"
        delay_ms = 0.0
        relative_delay_ms = 0.0

        if result.is_success and record_note and replay_note:
            # 计算延时（直接使用Note.key_on_ms，单位已是ms）
            if record_note.key_on_ms is not None and replay_note.key_on_ms is not None:
                delay_ms = replay_note.key_on_ms - record_note.key_on_ms
                relative_delay_ms = delay_ms - avg_delay_ms
            else:
                delay_ms = 0.0
                relative_delay_ms = 0.0

            # 评级
            if delay_ms <= 20:
                color_intensity, grade_name = 0.8, "优秀"
            elif delay_ms <= 30:
                color_intensity, grade_name = 0.6, "良好"
            elif delay_ms <= 50:
                color_intensity, grade_name = 0.4, "一般"
            elif delay_ms <= 1000:
                color_intensity, grade_name = 0.3, "较差"
            else:
                color_intensity, grade_name = 0.2, "严重"
        else:
            color_intensity, grade_name = 0.1, "失败"
            relative_delay_ms = 0.0 - avg_delay_ms

        return grade_name, color_intensity, delay_ms, relative_delay_ms


    # TODO
    def _get_error_note_index(self, error_note) -> int:
        """
        从错误note中获取音符索引
        """
        note_index = error_note.global_index if hasattr(error_note, 'global_index') and error_note.global_index >= 0 else None
        # 如果global_index不可用，尝试从notes获取（向后兼容）
        if note_index is None and hasattr(error_note, 'notes') and error_note.notes is not None and len(error_note.notes) > 0:
            # Note对象没有index属性，使用global_index
            note_index = error_note.global_index
        return note_index

    def _is_valid_index(self, index: int, data_length: int) -> bool:
        """
        验证索引是否有效
        """
        if index is None or index < 0:
            return False
        if index >= data_length:
            logger.warning(f"索引超出范围: {index} >= {data_length}")
            return False
        return True

    def _create_default_note(self, error_note, index: int):
        """
        创建默认的note对象用于显示
        """
        class DefaultNote:
            def __init__(self, key_id, index):
                self.id = key_id
                self.offset = 0
                # 为默认note创建基本的after_touch数据
                self.after_touch = type('AfterTouch', (), {
                    'index': [index * 10, (index + 1) * 10]  # 简单的开始和结束时间
                })()

        return DefaultNote(error_note.keyId if hasattr(error_note, 'keyId') else 60, index)

    def _merge_matched_hover_info(self, record_bars: List[Dict], replay_bars: List[Dict], avg_delay_ms: float) -> None:
        """
        将匹配的replay信息合并到record bars的hover文本中，实现统一的悬停显示。

        Args:
            record_bars: 录制数据的条形列表
            replay_bars: 播放数据的条形列表
            avg_delay_ms: 平均延时（毫秒）
        """
        # 匹配逻辑：按键位对应（确保record和replay的相同键位数据配对）
        for record_bar in record_bars:
            # 查找对应的replay bar（通过original_key_id匹配）
            replay_info = None
            record_key_id = record_bar.get('original_key_id')

            for replay_bar in replay_bars:
                if replay_bar.get('original_key_id') == record_key_id:
                    replay_info = replay_bar
                    break

            if replay_info:
                logger.info(f"合并键位 {record_key_id}: 录制和播放数据配对成功")

                # 获取record的原始文本
                original_text = record_bar.get('text', '')
                logger.info(f"原始record文本长度: {len(original_text)}")

                # 提取replay相关的完整信息
                replay_velocity = replay_info.get('velocity', 'N/A')
                replay_key_press = replay_info.get('t_on', 0) / 10
                replay_key_release = replay_info.get('t_off', 0) / 10
                replay_grade = replay_info.get('grade_name', '未知')
                replay_match_index = replay_info.get('match_index', 'N/A')
                replay_delay_ms = replay_info.get('delay_ms', 0.0)
                replay_relative_delay_ms = replay_info.get('relative_delay_ms', 0.0)
                replay_first_hammer = replay_info.get('first_hammer_time', 'N/A')

                logger.info(f"🎵 播放数据: 锤速={replay_velocity}, 等级={replay_grade}, 延时={replay_delay_ms:.2f}ms")

                # 在record的hover文本中添加完整的replay信息部分
                replay_section = '<br><b>播放数据:</b><br>' + \
                            f'类型: replay<br>' + \
                            f'键位: {record_key_id}<br>' + \
                            f'锤速: {replay_velocity}<br>' + \
                            f'等级: {replay_grade}<br>' + \
                            f'索引: {replay_match_index}<br>' + \
                            f'绝对延时: {replay_delay_ms:.2f}ms<br>' + \
                            f'相对延时: {replay_relative_delay_ms:+.2f}ms<br>' + \
                            f'平均延时: {avg_delay_ms:.2f}ms<br>' + \
                            f'首锤时间: {replay_first_hammer} ({replay_first_hammer/10:.2f}ms)<br>' + \
                            f'按键按下: {replay_key_press:.2f}ms<br>' + \
                            f'按键释放: {replay_key_release:.2f}ms<br>'

                merged_text = original_text + replay_section

                record_bar['text'] = merged_text
                # 为replay bar创建独立的悬停信息
                replay_text = '<b>播放数据:</b><br>' + \
                             f'类型: replay<br>' + \
                             f'键位: {record_key_id}<br>' + \
                             f'锤速: {replay_velocity}<br>' + \
                             f'等级: {replay_grade}<br>' + \
                             f'索引: {replay_match_index}<br>' + \
                             f'绝对延时: {replay_delay_ms:.2f}ms<br>' + \
                             f'相对延时: {replay_relative_delay_ms:+.2f}ms<br>' + \
                             f'平均延时: {avg_delay_ms:.2f}ms<br>' + \
                             f'首锤时间: {replay_first_hammer} ({replay_first_hammer/10:.2f}ms)<br>' + \
                             f'按键按下: {replay_key_press:.2f}ms<br>' + \
                             f'按键释放: {replay_key_release:.2f}ms<br>'
                replay_info['text'] = replay_text
            else:
                logger.warning(f"键位 {record_key_id}: 未找到对应的播放数据，无法合并hover信息")
                # 为没有匹配播放数据的record bar添加提示
                original_text = record_bar.get('text', '')
                no_replay_section = '<br><b>播放数据:</b><br>未找到匹配的播放数据<br>'
                record_bar['text'] = original_text + no_replay_section


    def _extract_note_bars_for_multi(self, note, label: str, y_offset: float, color_intensity: float, algorithm_name: str, grade_name: str = "未知", match_index: str = "N/A", delay_ms: float = 0.0, relative_delay_ms: float = 0.0, data_type: str = None) -> List[Dict]:
        """
        为多算法模式提取音符条形数据

        Args:
            note: Note对象
            label: 'record' 或 'replay'
            y_offset: Y轴偏移量
            color_intensity: 颜色强度 (0.0-1.0)
            algorithm_name: 算法名称
            data_type: 数据类型 ('drop_hammer', 'multi_hammer', None)

        Returns:
            List[Dict]: 条形数据列表
        """
        # 验证note数据
        if not self._validate_note_for_bar(note, label, data_type):
            return []
        
        key_id = getattr(note, 'id', 1)
        
        # 从Note对象获取预计算的时间属性
        if note.key_on_ms is None or note.key_off_ms is None:
            logger.warning(f"⚠️ note缺少时间数据: key_id={key_id}")
            return []
        
        # 转换为0.1ms单位（bar字典存储的单位）
        key_on_time = note.key_on_ms * 10.0
        key_off_time = note.key_off_ms * 10.0
        
        try:
            # 计算Y轴位置
            actual_key_id = self._calculate_y_position(key_id, y_offset, label)
            
            # 提取锤速信息
            hammer_velocity = self._extract_hammer_velocity(note)
            
            # 解析match_index
            source_index = self._parse_match_index(match_index)
            
            # 创建bar字典
            bar = self._create_bar_dict(
                key_on_time, key_off_time, actual_key_id, key_id,
                hammer_velocity, color_intensity,
                algorithm_name, label, data_type, grade_name, match_index,
                source_index, delay_ms, relative_delay_ms
            )
            
            # 生成hover文本
            bar['text'] = self._generate_hover_text(
                bar, label, data_type, algorithm_name, key_id,
                hammer_velocity, grade_name, match_index,
                delay_ms, relative_delay_ms, key_on_time, key_off_time
            )

            return [bar]
            
        except (TypeError, ValueError, AttributeError) as e:
            logger.warning(f"🚫 创建 {data_type} bar失败: {e}")
            return []
    
    def _validate_note_for_bar(self, note, label: str, data_type: str) -> bool:
        """验证note对象是否有效"""
        if not note:
            logger.warning(f"⚠️ note为空, label={label}, data_type={data_type}")
            return False
        
        if not hasattr(note, 'hammers'):
            logger.warning(f"⚠️ note没有hammers属性, key_id={getattr(note, 'id', 'N/A')}, label={label}, data_type={data_type}")
            return False
        
        if note.hammers is None:
            logger.warning(f"⚠️ note.hammers为None, key_id={getattr(note, 'id', 'N/A')}, label={label}, data_type={data_type}")
            return False
        
        return True
    
    def _calculate_y_position(self, key_id: int, y_offset: float, label: str) -> float:
        """计算Y轴位置"""
        actual_key_id = key_id + y_offset
        if label == 'replay':
            actual_key_id += 0.2  # 播放数据稍微偏移
        return actual_key_id
    
    def _extract_hammer_velocity(self, note) -> Any:
        """提取锤速信息"""
        velocity = note.get_first_hammer_velocity()
        return velocity if velocity is not None else "N/A"

    def _normalize_velocity_value(self, velocity: float, vmin: float, vmax: float) -> float:
        """将锤速值归一化到[0,1]范围用于颜色映射

        Args:
            velocity: 锤速值
            vmin: 锤速最小值
            vmax: 锤速最大值

        Returns:
            float: 归一化后的值 (0.0-1.0)
        """
        if vmax > vmin:
            # 正常情况：数据有变化范围，进行min-max归一化
            return (velocity - vmin) / (vmax - vmin)
        elif vmax == vmin:
            # 特殊情况：所有锤速值都相同，所有点用相同颜色
            return 0.5  # 中间色调
        else:
            # 理论上不会发生，但保持健壮性
            return 0.5

    def _calculate_velocity_color(self, velocity: float, vmin: float, vmax: float) -> str:
        """根据锤速值计算颜色

        Args:
            velocity: 锤速值
            vmin: 锤速最小值
            vmax: 锤速最大值

        Returns:
            str: RGBA颜色字符串
        """
        import matplotlib.pyplot as plt
        cmap = plt.colormaps['YlOrRd']  # 从浅黄到深红，越大越深

        # 归一化并映射到颜色
        normalized = self._normalize_velocity_value(velocity, vmin, vmax)
        color = 'rgba' + str(tuple(int(255*x) for x in cmap(normalized)[:3]) + (0.9,))
        return color

    def _create_bar_trace_name(self, algorithm_name: str, data_type: str, bar_label: str) -> str:
        """创建bar的trace名称

        Args:
            algorithm_name: 算法名称
            data_type: 数据类型 ('drop_hammer', 'multi_hammer', 或其他)
            bar_label: bar标签

        Returns:
            str: trace名称
        """
        if data_type == 'drop_hammer':
            return f"{algorithm_name} - 丢锤"
        elif data_type == 'multi_hammer':
            return f"{algorithm_name} - 多锤"
        else:
            return f"{algorithm_name} - {bar_label}"

    def _collect_velocity_values(self, all_bars_by_algorithm: List[Dict]) -> List[float]:
        """从所有算法的bars中收集有效的锤速值

        Args:
            all_bars_by_algorithm: 所有算法的bars数据列表

        Returns:
            List[float]: 有效的锤速值列表
        """
        all_values = []
        total_bars = 0
        valid_bars = 0
        na_bars = 0
        
        for alg_data in all_bars_by_algorithm:
            for bar in alg_data['bars']:
                total_bars += 1
                velocity = bar.get('velocity')
                if velocity != "N/A" and isinstance(velocity, (int, float)):
                    all_values.append(velocity)
                    valid_bars += 1
                else:
                    na_bars += 1
        
        logger.info(f"🎨 锤速收集统计: 总bars={total_bars}, 有效锤速={valid_bars}, 无效/N/A={na_bars}")
        if all_values:
            logger.info(f"🎨 锤速范围: min={min(all_values)}, max={max(all_values)}, 样本数={len(all_values)}")
        
        return all_values

    def _calculate_velocity_range(self, velocity_values: List[float]) -> Tuple[float, float]:
        """计算锤速值的全局范围

        Args:
            velocity_values: 锤速值列表

        Returns:
            Tuple[float, float]: (vmin, vmax)
        """
        if velocity_values:
            return min(velocity_values), max(velocity_values)
        else:
            return 0.0, 1.0

    def _add_waterfall_bar_trace(self, fig: go.Figure, bar: Dict, algorithm_name: str,
                                vmin: float, vmax: float) -> bool:
        """添加单个瀑布图bar的trace

        Args:
            fig: Plotly图表对象
            bar: bar数据字典
            algorithm_name: 算法名称
            vmin: 锤速最小值
            vmax: 锤速最大值

        Returns:
            bool: 是否成功添加（False表示数据无效被跳过）
        """
        # 获取锤速数据并计算颜色
        velocity = bar.get('velocity')
        if velocity == "N/A" or not isinstance(velocity, (int, float)):
            # 如果没有锤速数据，使用默认颜色（灰色）
            color = 'rgba(128, 128, 128, 0.9)'
        else:
            # 有锤速数据，使用基于锤速的颜色映射
            color = self._calculate_velocity_color(velocity, vmin, vmax)

        # 创建trace名称
        data_type = bar.get('data_type', '')
        trace_name = self._create_bar_trace_name(algorithm_name, data_type, bar['label'])

        # 添加水平线段
        fig.add_trace(go.Scatter(
            x=[bar['t_on']/10, bar['t_off']/10],
            y=[bar['key_id'], bar['key_id']],
            mode='lines',
            line=dict(color=color, width=3),
            name=trace_name,
            showlegend=False,
            legendgroup=algorithm_name,
            hoverinfo='text' if bar.get('text') else 'skip',
            text=bar.get('text', ''),
            customdata=[[
                bar['t_on']/10,
                bar['t_off']/10,
                int(bar.get('original_key_id', bar.get('key_id', 0))),
                bar.get('velocity', 'N/A'),
                bar.get('label', 'unknown'),
                bar.get('source_index', 0),
                algorithm_name
            ]]
        ))
        return True

    def _handle_generation_error(self, error: Exception, plot_type: str, include_traceback: bool = True,
                                return_dict: bool = False, return_list: bool = False) -> Any:
        """通用图表生成错误处理方法

        Args:
            error: 捕获的异常
            plot_type: 图表类型描述（用于错误消息）
            include_traceback: 是否包含完整的堆栈跟踪
            return_dict: 是否返回字典格式的错误结果（用于返回多个图表的方法）
            return_list: 是否返回列表格式的错误结果（用于返回图表列表的方法）

        Returns:
            Any: 空的图表对象、错误字典或错误列表
        """
        logger.error(f"❌ 生成{plot_type}失败: {error}")
        if include_traceback:
            logger.error(traceback.format_exc())

        empty_plot = self._create_empty_plot(f"生成失败: {str(error)}")

        if return_dict:
            return {
                'raw_delay_plot': empty_plot,
                'relative_delay_plot': empty_plot
            }
        elif return_list:
            return [{'title': '生成失败', 'figure': empty_plot}]
        else:
            return empty_plot

    def _get_multi_file_average_delay(self, backend, algorithm_names: List[str]) -> float:
        """获取多文件模式的平均延时

        Args:
            backend: 后端实例
            algorithm_names: 算法名称列表

        Returns:
            float: 平均延时(ms)
        """
        if not algorithm_names or algorithm_names[0] == 'single':
            return 0.0

        try:
            # 获取活跃算法列表
            active_algorithms = backend.get_active_algorithms()
            
            if not active_algorithms:
                return 0.0

            # 找到第一个匹配的算法
            target_algorithm_name = algorithm_names[0]
            target_algorithm = None
            for alg in active_algorithms:
                if (hasattr(alg, 'metadata') and
                    hasattr(alg.metadata, 'algorithm_name') and
                    alg.metadata.algorithm_name == target_algorithm_name):
                    target_algorithm = alg
                    break

            # 获取该算法的平均延时
            if (target_algorithm and
                target_algorithm.analyzer and
                hasattr(target_algorithm.analyzer, 'get_global_average_delay')):

                avg_delay_0_1ms = target_algorithm.analyzer.get_global_average_delay()
                return avg_delay_0_1ms / 10.0

        except Exception as e:
            logger.warning(f"获取多文件平均延时失败: {e}")

        return 0.0

    def _get_single_file_average_delay(self, backend) -> float:
        """获取单文件模式的平均延时

        Args:
            backend: 后端实例

        Returns:
            float: 平均延时(ms)
        """
        try:
            avg_delay_0_1ms = backend.get_global_average_delay()
            return avg_delay_0_1ms / 10.0
        except Exception as e:
            logger.warning(f"获取单文件平均延时失败: {e}")
            return 0.0

    def _get_average_delay(self, backend, is_multi_file: bool, algorithm_names: List[str]) -> float:
        """统一获取平均延时（自动选择单文件或多文件模式）

        Args:
            backend: 后端实例
            is_multi_file: 是否为多文件模式
            algorithm_names: 算法名称列表

        Returns:
            float: 平均延时(ms)
        """
        if is_multi_file:
            return self._get_multi_file_average_delay(backend, algorithm_names)
        else:
            return self._get_single_file_average_delay(backend)
    
    def _parse_match_index(self, match_index) -> int:
        """解析match_index为source_index"""
        source_index = 0
        try:
            if isinstance(match_index, str) and match_index != "N/A":
                source_index = int(match_index)
            elif isinstance(match_index, int):
                source_index = match_index
        except (ValueError, TypeError):
            source_index = 0
        return source_index
    
    def _create_bar_dict(self, key_on_time: float, key_off_time: float, actual_key_id: float,
                        key_id: int, hammer_velocity,
                        color_intensity: float, algorithm_name: str, label: str,
                        data_type: str, grade_name: str, match_index, source_index: int,
                        delay_ms: float, relative_delay_ms: float) -> Dict:
        """创建bar字典"""
        return {
            't_on': float(key_on_time),
            't_off': float(key_off_time),
            'key_id': actual_key_id,
            'original_key_id': key_id,
            'velocity': hammer_velocity,
            'color_intensity': color_intensity,
            'algorithm_name': algorithm_name,
            'label': label,
            'data_type': data_type,
            'hammer_index': 0,
            'grade_name': grade_name,
            'match_index': match_index,
            'source_index': source_index,
            'delay_ms': delay_ms,
            'relative_delay_ms': relative_delay_ms,
            'first_hammer_time': key_on_time
        }
    
    def _generate_hover_text(self, bar: Dict, label: str, data_type: str,
                            algorithm_name: str, key_id: int, hammer_velocity,
                            grade_name: str, match_index, delay_ms: float,
                            relative_delay_ms: float, key_on_time: float,
                            key_off_time: float) -> str:
        """生成hover文本"""
        # 生成数据类型后缀
        bar_type_suffix = ""
        if data_type == "drop_hammer":
            bar_type_suffix = " (丢锤)"
        elif data_type == "multi_hammer":
            bar_type_suffix = " (多锤)"
        
        # 根据label构建不同的hover文本
        if label == 'record':
            return (
                f'算法: {algorithm_name}<br>'
                f'类型: {label}{bar_type_suffix}<br>'
                f'键位: {key_id}<br>'
                f'锤速: {hammer_velocity}<br>'
                f'等级: {grade_name}<br>'
                f'索引: {match_index}<br>'
                f'按键按下: {key_on_time/10:.2f}ms<br>'
                f'按键释放: {key_off_time/10:.2f}ms<br>'
            )
        else:
            return (
                f'算法: {algorithm_name}<br>'
                f'类型: {label}{bar_type_suffix}<br>'
                f'键位: {key_id}<br>'
                f'锤速: {hammer_velocity}<br>'
                f'等级: {grade_name}<br>'
                f'索引: {match_index}<br>'
                f'绝对延时: {delay_ms:.2f}ms<br>'
                f'相对延时: {relative_delay_ms:+.2f}ms<br>'
                f'按键按下: {key_on_time/10:.2f}ms<br>'
                f'按键释放: {key_off_time/10:.2f}ms<br>'
            )
    
    def _apply_key_filter(self, data: List, key_filter: set) -> List:
        """应用按键过滤"""
        if not key_filter:
            return data
        return [note for note in data if note.keyId in key_filter]
    
    
    def generate_multi_algorithm_offset_alignment_plot(
        self,
        algorithms: List[AlgorithmDataset]
    ) -> List[Dict[str, Any]]:
        """
        生成多算法偏移对齐分析图（并排柱状图，不同颜色）
        
        返回5个独立的图表，每个图表显示一个指标：
        - 中位数偏移、均值偏移、标准差、方差、相对延时
        
        Args:
            algorithms: 激活的算法数据集列表
            
        Returns:
            List[Dict[str, Any]]: 包含图表信息的字典列表
        """
        # 验证输入
        if not algorithms:
            return self._create_empty_offset_figures("没有激活的算法")
        
        try:
            # 过滤就绪的算法
            ready_algorithms = [alg for alg in algorithms if alg.is_ready()]
            if not ready_algorithms:
                logger.warning("⚠️ 没有就绪的算法，无法生成多算法偏移对齐分析图")
                return self._create_empty_offset_figures("没有就绪的算法")
            
            # 收集所有算法的数据
            all_algorithms_data = self._collect_all_algorithms_offset_data(ready_algorithms)
            
            if not all_algorithms_data:
                logger.warning("⚠️ 没有有效的偏移对齐数据，无法生成柱状图")
                return self._create_empty_offset_figures("没有有效的偏移对齐数据")
            
            # 生成图表
            figures_list = self._generate_offset_metric_figures(all_algorithms_data)
            
            return figures_list
            
        except Exception as e:
            return self._handle_generation_error(e, "多算法偏移对齐分析图", return_list=True)
    
    def _create_empty_offset_figures(self, message: str) -> List[Dict[str, Any]]:
        """创建空的偏移对齐图表列表"""
        empty_fig = self._create_empty_plot(message)
        return [
            {'title': '中位数偏移', 'figure': empty_fig},
            {'title': '均值偏移', 'figure': empty_fig},
            {'title': '标准差', 'figure': empty_fig},
            {'title': '方差', 'figure': empty_fig},
            {'title': '相对延时', 'figure': empty_fig}
        ]
    
    def _collect_all_algorithms_offset_data(self, ready_algorithms: List[AlgorithmDataset]) -> List[Dict]:
        """收集所有算法的偏移对齐数据"""
        all_algorithms_data = []
        colors = ALGORITHM_COLOR_PALETTE
        
        for alg_idx, algorithm in enumerate(ready_algorithms):
            algorithm_data = self._collect_single_algorithm_offset_data(
                algorithm, alg_idx, colors
            )
            if algorithm_data:
                all_algorithms_data.append(algorithm_data)
        
        return all_algorithms_data
    
    def _collect_single_algorithm_offset_data(self, algorithm: AlgorithmDataset, 
                                              alg_idx: int, colors: List[str]) -> Optional[Dict]:
        """收集单个算法的偏移对齐数据"""
        algorithm_name = algorithm.metadata.algorithm_name
        
        if not algorithm.analyzer:
            logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有分析器，跳过")
            return None
        
        try:
            # 获取偏移数据
            offset_data = algorithm.analyzer.get_precision_offset_alignment_data()
            
            # 计算平均延时
            mean_delay = self._calculate_mean_delay(algorithm.analyzer)
            
            # 按key_id分组
            key_groups, key_groups_relative = self._group_offset_data_by_key(
                offset_data, mean_delay
            )
            
            # 计算统计数据
            statistics = self._calculate_offset_statistics(key_groups, key_groups_relative)
            
            if not statistics['key_ids']:
                return None
            
            return {
                'name': algorithm_name,
                'display_name': algorithm.metadata.display_name,
                'color': colors[alg_idx % len(colors)],
                'analyzer': algorithm.analyzer,
                **statistics
            }
        except Exception as e:
            logger.warning(f"⚠️ 获取算法 '{algorithm_name}' 的偏移对齐数据失败: {e}")
            return None
    
    def _calculate_mean_delay(self, analyzer) -> float:
        """计算算法的平均延时"""
        me_0_1ms = analyzer.get_mean_error() if hasattr(analyzer, 'get_mean_error') else 0.0
        return me_0_1ms / 10.0  # 转换为ms
    
    def _group_offset_data_by_key(self, offset_data: List[Dict], 
                                   mean_delay: float) -> Tuple[Dict, Dict]:
        """按key_id分组偏移数据"""
        from collections import defaultdict
        
        key_groups = defaultdict(list)
        key_groups_relative = defaultdict(list)
        
        for item in offset_data:
            key_id = item.get('key_id', 'N/A')
            keyon_offset = item.get('keyon_offset', 0)
            keyon_offset_abs = abs(keyon_offset)
            keyon_offset_ms = keyon_offset / 10.0
            relative_delay = keyon_offset_ms - mean_delay
            
            key_groups[key_id].append(keyon_offset_abs)
            key_groups_relative[key_id].append(relative_delay)
        
        return key_groups, key_groups_relative
    
    def _calculate_offset_statistics(self, key_groups: Dict, 
                                     key_groups_relative: Dict) -> Dict:
        """计算偏移统计数据"""
        key_ids = []
        median = []
        mean = []
        std = []
        variance = []
        relative_mean = []
        
        for key_id, offsets in key_groups.items():
            if not offsets:
                continue
            
            try:
                key_id_int = int(key_id)
                key_ids.append(key_id_int)
                median.append(np.median(offsets) / 10.0)
                mean.append(np.mean(offsets) / 10.0)
                std.append(np.std(offsets) / 10.0)
                variance.append(np.var(offsets) / 100.0)
                
                # 计算相对延时的均值
                if key_id in key_groups_relative:
                    relative_mean.append(np.mean(key_groups_relative[key_id]))
                else:
                    relative_mean.append(0.0)
            except (ValueError, TypeError):
                continue
        
        return {
            'key_ids': key_ids,
            'median': median,
            'mean': mean,
            'std': std,
            'variance': variance,
            'relative_mean': relative_mean
        }
    
    def _generate_offset_metric_figures(self, all_algorithms_data: List[Dict]) -> List[Dict[str, Any]]:
        """生成所有指标的图表"""
        # 定义指标配置
        metrics = [
            ('中位数偏移', 'median', 'ms'),
            ('均值偏移', 'mean', 'ms'),
            ('标准差', 'std', 'ms'),
            ('方差', 'variance', 'ms²'),
            ('相对延时', 'relative_mean', 'ms')
        ]
        
        # 计算全局参数
        all_key_ids = self._get_all_key_ids(all_algorithms_data)
        num_algorithms = len(all_algorithms_data)
        bar_width = 0.8 / num_algorithms
        min_key_id = max(1, min(all_key_ids)) if all_key_ids else 1
        max_key_id = max(all_key_ids) if all_key_ids else 90
        
        # 为每个指标生成图表
        figures_list = []
        for metric_name, data_key, unit in metrics:
            fig = self._create_single_offset_metric_figure(
                metric_name, data_key, unit, all_algorithms_data,
                all_key_ids, num_algorithms, bar_width, min_key_id, max_key_id
            )
            figures_list.append({'title': metric_name, 'figure': fig})
        
        return figures_list
    
    def _get_all_key_ids(self, all_algorithms_data: List[Dict]) -> List[int]:
        """获取所有键位ID的并集"""
        all_key_ids = set()
        for alg_data in all_algorithms_data:
            all_key_ids.update(alg_data['key_ids'])
        return sorted(list(all_key_ids))
    
    def _create_single_offset_metric_figure(self, metric_name: str, data_key: str, 
                                            unit: str, all_algorithms_data: List[Dict],
                                            all_key_ids: List[int], num_algorithms: int,
                                            bar_width: float, min_key_id: int, 
                                            max_key_id: int) -> go.Figure:
        """创建单个指标的图表"""
        fig = go.Figure()
        
        # 为每个算法添加trace
        for alg_idx, alg_data in enumerate(all_algorithms_data):
            self._add_algorithm_trace_to_figure(
                fig, alg_data, alg_idx, data_key, metric_name, unit,
                all_key_ids, num_algorithms, bar_width
            )
        
        # 配置布局
        self._configure_offset_figure_layout(
            fig, metric_name, unit, min_key_id, max_key_id
        )
        
        return fig
    
    def _add_algorithm_trace_to_figure(self, fig: go.Figure, alg_data: Dict, 
                                       alg_idx: int, data_key: str, metric_name: str,
                                       unit: str, all_key_ids: List[int], 
                                       num_algorithms: int, bar_width: float):
        """添加算法的trace到图表"""
        algorithm_name = alg_data['name']
        display_name = alg_data.get('display_name', algorithm_name)
        color = alg_data['color']
        
        # 准备数据
        x_positions = []
        y_values = []
        key_to_val = dict(zip(alg_data['key_ids'], alg_data[data_key]))
        
        for key_id in all_key_ids:
            if key_id in alg_data['key_ids']:
                x_pos = key_id + (alg_idx - num_algorithms / 2 + 0.5) * bar_width
                x_positions.append(x_pos)
                y_values.append(key_to_val[key_id])
        
        if not x_positions:
            return
        
        # 添加柱状图trace
        fig.add_trace(go.Bar(
            x=x_positions,
            y=y_values,
            name=display_name,
            marker_color=color,
            opacity=0.8,
            width=bar_width,
            text=[f'{val:.2f}' for val in y_values],
            textposition='outside',
            textfont=dict(size=8),
            showlegend=True,
            legendgroup=algorithm_name,
            hovertemplate=f'算法: {display_name}<br>键位: %{{x:.0f}}<br>{metric_name}: %{{y:.2f}}{unit}<extra></extra>'
        ))
    
    def _configure_offset_figure_layout(self, fig: go.Figure, metric_name: str, 
                                        unit: str, min_key_id: int, max_key_id: int):
        """配置偏移图表的布局"""
        fig.update_layout(
            title=dict(text=metric_name, x=0.5, xanchor='center'),
            xaxis_title='键位ID',
            yaxis_title=f'{metric_name} ({unit})',
            xaxis=dict(
                tickmode='linear',
                tick0=min_key_id,
                dtick=1,
                range=[min_key_id - 1, max_key_id + 1]
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor='lightgray',
                gridwidth=1
            ),
            template='simple_white',
            showlegend=True,
            legend=dict(
                x=0.01, y=1.12, xanchor='left', yanchor='top',
                bgcolor='rgba(255,255,255,0.8)',
                bordercolor='rgba(0,0,0,0.2)',
                borderwidth=1,
                orientation='h',
                font=dict(size=11),
                title_text=metric_name
            ),
            margin=dict(l=60, r=40, t=100, b=60),
            height=500,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(size=12)
        )

    def generate_multi_algorithm_delay_histogram_plot(
        self,
        algorithms: List[AlgorithmDataset]
    ) -> Any:
        """
        生成多算法延时分布直方图（叠加显示，不同颜色，图例控制）

        为每个算法生成直方图和正态拟合曲线，使用不同颜色区分，叠加显示在同一图表中。
        数据筛选：只使用误差≤50ms的按键数据

        Args:
            algorithms: 激活的算法数据集列表

        Returns:
            go.Figure: Plotly图表对象
        """
        # 验证并准备算法
        ready_algorithms = self._validate_and_prepare_algorithms(algorithms)
        if not ready_algorithms:
            return self._create_empty_plot("没有就绪的算法")
        
        try:
            fig = go.Figure()
            all_delays = []
            
            # 为每个算法收集数据并添加traces
            for alg_idx, algorithm in enumerate(ready_algorithms):
                delay_data = self._collect_algorithm_delay_data(algorithm, alg_idx)
                if not delay_data:
                    continue
                
                all_delays.extend(delay_data['relative_delays'])
                
                # 添加直方图和正态拟合曲线
                self._add_histogram_traces(fig, delay_data)
            
            if not all_delays:
                logger.warning("⚠️ 没有有效的延时数据，无法生成直方图")
                return self._create_empty_plot("没有有效的延时数据")
            
            # 配置布局
            self._configure_histogram_layout(fig)
            return fig
            
        except Exception as e:
            return self._handle_generation_error(e, "多算法延时分布直方图")
    
    def _collect_algorithm_delay_data(self, algorithm: AlgorithmDataset, alg_idx: int) -> Optional[Dict]:
        """收集单个算法的延时数据"""
        # 提取元数据
        metadata = self._extract_algorithm_metadata(algorithm)
        descriptive_name = metadata['descriptive_name']
        
        # 验证分析器
        if not self._validate_analyzer(algorithm, descriptive_name):
            return None
        
        try:
            # 获取偏移数据
            offset_data = self._get_offset_data(algorithm)
            if not offset_data:
                logger.warning(f"⚠️ 算法 '{metadata['algorithm_name']}' 没有精确匹配数据（≤50ms），跳过")
                return None
            
            # 提取绝对延时
            absolute_delays_ms = [item.get('keyon_offset', 0.0) / 10.0 for item in offset_data]
            if not absolute_delays_ms:
                logger.warning(f"⚠️ 算法 '{metadata['algorithm_name']}' 筛选后没有有效延时数据，跳过")
                return None
            
            # 计算平均延时
            mean_delay_ms = self._calculate_mean_delay(algorithm.analyzer)
            
            # 计算相对延时和统计量
            relative_delays_ms = [delay - mean_delay_ms for delay in absolute_delays_ms]
            statistics = self._calculate_delay_statistics(
                absolute_delays_ms, relative_delays_ms, mean_delay_ms
            )
            
            return {
                'descriptive_name': descriptive_name,
                'relative_delays': relative_delays_ms,
                'statistics': statistics,
                'color': self._get_algorithm_color(alg_idx)
            }
        except Exception as e:
            logger.warning(f"⚠️ 获取算法 '{metadata['algorithm_name']}' 的延时数据失败: {e}")
            return None
    
    def _calculate_delay_statistics(self, absolute_delays: List[float], 
                                    relative_delays: List[float], 
                                    mean_delay: float) -> Dict[str, float]:
        """计算延时统计量"""
        n = len(absolute_delays)
        
        # 绝对延时统计（反映整体稳定性）
        if n > 1:
            var_offset = sum((x - mean_delay) ** 2 for x in absolute_delays) / (n - 1)
            std_offset = var_offset ** 0.5
        else:
            std_offset = 0.0
        
        # 相对延时统计（用于正态拟合）
        if n > 1:
            var_relative = sum(x ** 2 for x in relative_delays) / (n - 1)
            std_relative = var_relative ** 0.5
        else:
            std_relative = 0.0
        
        return {
            'mean_offset': mean_delay,
            'std_offset': std_offset,
            'std_relative': std_relative
        }
    
    def _add_histogram_traces(self, fig: go.Figure, delay_data: Dict):
        """添加直方图和正态拟合曲线traces"""
        descriptive_name = delay_data['descriptive_name']
        relative_delays = delay_data['relative_delays']
        stats = delay_data['statistics']
        color = delay_data['color']
        
        # 添加直方图
        fig.add_trace(go.Histogram(
            x=relative_delays,
            histnorm='probability density',
            name=f'{descriptive_name} - 延时分布',
            marker_color=color,
            opacity=0.85,
            marker_line_color=color,
            marker_line_width=0.5,
            legendgroup=descriptive_name,
            showlegend=True
        ))
        
        # 添加正态拟合曲线
        if stats['std_relative'] > 0:
            xs, ys = self._generate_normal_curve(
                relative_delays, stats['std_relative']
            )
            fig.add_trace(go.Scatter(
                x=xs,
                y=ys,
                mode='lines',
                name=f'{descriptive_name} - 正态拟合 (μ={stats["mean_offset"]:.2f}ms, σ={stats["std_offset"]:.2f}ms)',
                line=dict(color=color, width=2),
                legendgroup=descriptive_name,
                showlegend=True
            ))
    
    def _generate_normal_curve(self, relative_delays: List[float], 
                               std_relative: float) -> Tuple[List[float], List[float]]:
        """生成正态分布拟合曲线的坐标"""
        min_x = min(relative_delays)
        max_x = max(relative_delays)
        span = max(1e-6, 3 * std_relative)
        x_start = min(-span, min_x)
        x_end = max(span, max_x)
        
        num_pts = 200
        step = (x_end - x_start) / (num_pts - 1) if num_pts > 1 else 1.0
        xs = [x_start + i * step for i in range(num_pts)]
        ys = [(1.0 / (std_relative * (2 * math.pi) ** 0.5)) *
              math.exp(-0.5 * (x / std_relative) ** 2) for x in xs]
        
        return xs, ys
    
    def _configure_histogram_layout(self, fig: go.Figure):
        """配置直方图布局"""
        fig.update_layout(
            xaxis_title='相对延时 (ms)',
            yaxis_title='概率密度',
            bargap=0.05,
            plot_bgcolor='white',
            paper_bgcolor='white',
            font=dict(size=12),
            height=500,
            clickmode='event+select',
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.05,
                xanchor='left',
                x=0.0,
                bgcolor='rgba(255, 255, 255, 0.9)',
                bordercolor='gray',
                borderwidth=1
            ),
            margin=dict(t=100, b=60, l=60, r=60)
        )
    
    def generate_multi_algorithm_key_delay_scatter_plot(
        self,
        algorithms: List[AlgorithmDataset],
        only_common_keys: bool = False,
        selected_algorithm_names: List[str] = None
    ) -> Any:
        """
        生成多算法按键与延时散点图（叠加显示，不同颜色，图例控制）

        Args:
            algorithms: 激活的算法数据集列表
            only_common_keys: 是否只显示公共按键
            selected_algorithm_names: 指定参与对比的算法名称列表

        Returns:
            go.Figure: Plotly图表对象
        """
        try:
            # 筛选和准备算法
            filtered_algorithms = self._filter_algorithms_by_names(
                algorithms, selected_algorithm_names
            )
            ready_algorithms = self._validate_and_prepare_algorithms(filtered_algorithms)
            if not ready_algorithms:
                return self._create_empty_plot("没有激活的算法")
            
            logger.info(f"开始生成多算法按键与延时散点图，共 {len(ready_algorithms)} 个激活算法")
            
            # 计算公共按键（如果需要）
            common_keys = self._calculate_common_keys(ready_algorithms) if only_common_keys else None
            
            fig = go.Figure()
            
            # 收集所有算法数据
            algorithm_data_list = []
            for alg_idx, algorithm in enumerate(ready_algorithms):
                alg_data = self._collect_scatter_algorithm_data(algorithm, alg_idx, common_keys)
                if alg_data:
                    algorithm_data_list.append(alg_data)
            
            if not algorithm_data_list:
                logger.warning("没有有效的算法数据")
                return self._create_empty_plot("没有有效的算法数据")
            
            # 添加散点图和阈值线
            self._add_scatter_plot_traces(fig, algorithm_data_list)
            self._add_scatter_threshold_lines(fig, algorithm_data_list)
            
            # 配置布局
            self._configure_scatter_plot_layout(fig)
            
            return fig
            
        except Exception as e:
            return self._handle_generation_error(e, "多算法按键与延时散点图")
    
    def generate_multi_algorithm_key_delay_zscore_scatter_plot(
        self,
        algorithms: List[AlgorithmDataset]
    ) -> Any:
        """
        生成多算法按键与延时Z-Score标准化散点图
        
        Z-Score标准化公式：z = (x_i - μ) / σ
        - x_i: 每个数据点的延时值
        - μ: 该算法的总体均值
        - σ: 该算法的总体标准差
        
        Args:
            algorithms: 激活的算法数据集列表
            
        Returns:
            go.Figure: Plotly图表对象
        """
        if not algorithms:
            return self._create_empty_plot("没有激活的算法")
        
        try:
            # 验证和准备算法列表
            ready_algorithms = self._validate_and_prepare_algorithms(algorithms)
            if not ready_algorithms:
                return self._create_empty_plot("没有激活的算法")
            
            fig = go.Figure()
            all_key_ids = set()
            
            # 收集所有激活算法的数据
            for alg_idx, algorithm in enumerate(ready_algorithms):
                metadata = self._extract_algorithm_metadata(algorithm)
                descriptive_name = metadata['descriptive_name']
                
                if not self._validate_analyzer(algorithm, descriptive_name):
                    continue
                
                try:
                    # 提取散点图数据
                    scatter_data = self._extract_scatter_delay_data(algorithm, metadata)
                    if not scatter_data:
                        continue
                    
                    key_ids, delays_ms, customdata_list = scatter_data
                    
                    # 计算Z-Score值
                    z_scores, mu, sigma = self._calculate_zscore_values(delays_ms, algorithm)
                    
                    # 排序数据
                    key_ids, z_scores, customdata_list = self._sort_scatter_data(
                        key_ids, z_scores, customdata_list
                    )
                    
                    # 添加散点图traces
                    color = self._get_algorithm_color(alg_idx)
                    self._add_zscore_scatter_traces(
                        fig, key_ids, z_scores, customdata_list, descriptive_name, color
                    )
                    
                    # 收集按键ID
                    all_key_ids.update(key_ids)
                    
                except Exception as e:
                    logger.warning(f"⚠️ 获取算法 '{descriptive_name}' 的Z-Score数据失败: {e}")
                    continue
            
            # 添加阈值线（Z=0, ±3）
            sorted_key_ids = sorted(all_key_ids)
            key_labels = [str(kid) for kid in sorted_key_ids]
            self._add_zscore_threshold_lines(fig, key_labels, ready_algorithms)
            
            # 配置布局
            self._configure_zscore_layout(fig)
            
            return fig
            
        except Exception as e:
            return self._handle_generation_error(e, "多算法Z-Score标准化散点图")

    def generate_single_key_delay_comparison_plot(
        self,
        algorithms: List[AlgorithmDataset],
        target_key_id: int
    ) -> Any:
        """
        生成单键多曲延时对比图（散点图+箱线图）
        
        Args:
            algorithms: 算法数据集列表
            target_key_id: 目标按键ID
            
        Returns:
            Any: Plotly图表对象
        """
        if not algorithms:
            return self._create_empty_plot("没有激活的算法")
            
        if target_key_id is None:
            return self._create_empty_plot("请选择一个按键进行分析")
            
        try:
            # 验证和准备算法列表
            ready_algorithms = self._validate_and_prepare_algorithms(algorithms)
            if not ready_algorithms:
                return self._create_empty_plot("没有激活且就绪的算法")
            
            fig = go.Figure()
            has_data = False
            
            # 遍历每个算法
            for alg_idx, algorithm in enumerate(ready_algorithms):
                metadata = self._extract_algorithm_metadata(algorithm)
                display_name = metadata['display_name']
                filename = metadata['filename']
                descriptive_name = metadata['descriptive_name']
                
                # 验证分析器
                if not self._validate_analyzer(algorithm, descriptive_name):
                    continue
                
                # 获取偏移数据
                offset_data = self._get_offset_data(algorithm)
                if not offset_data:
                    continue
                
                # 提取目标按键的延时数据
                key_delays, customdata_list = self._extract_single_key_delays(
                    offset_data, target_key_id, filename
                )
                
                if not key_delays:
                    continue
                
                has_data = True
                
                # 添加箱线图
                color = self._get_algorithm_color(alg_idx)
                self._add_box_trace(
                    fig, key_delays, display_name, target_key_id, customdata_list, color
                )
            
            if not has_data:
                return self._create_empty_plot(f"按键 {target_key_id} 在选定的算法中没有数据")
            
            # 配置布局
            self._configure_single_key_layout(fig, target_key_id)
            
            return fig
            
        except Exception as e:
            return self._handle_generation_error(e, "单键对比图")

    def generate_multi_algorithm_hammer_velocity_relative_delay_scatter_plot(
        self,
        algorithms: List[AlgorithmDataset]
    ) -> Any:
        """
        生成多算法锤速与相对延时散点图（叠加显示，不同颜色，图例控制）

        Args:
            algorithms: 激活的算法数据集列表

        Returns:
            go.Figure: Plotly图表对象
        """
        try:
            # 验证和准备算法列表
            ready_algorithms = self._validate_and_prepare_algorithms(algorithms)
            if not ready_algorithms:
                return self._create_empty_plot("没有激活的算法")

            logger.info(f"开始生成多算法锤速与相对延时散点图，共 {len(ready_algorithms)} 个激活算法")
            
            fig = go.Figure()
            
            # 计算x轴范围
            x_min, x_max = self._calculate_log_velocity_range(ready_algorithms)

            for alg_idx, algorithm in enumerate(ready_algorithms):
                metadata = self._extract_algorithm_metadata(algorithm)
                algorithm_name = metadata['algorithm_name']
                descriptive_name = metadata['descriptive_name']
                display_name = metadata['display_name']

                # 验证分析器
                if not self._validate_analyzer(algorithm, descriptive_name):
                    continue

                try:
                    # 获取匹配对
                    matched_pairs = self._get_matched_pairs(algorithm)
                    if not matched_pairs:
                        logger.warning(f"算法 '{descriptive_name}' 没有匹配数据，跳过")
                        continue

                    # 获取偏移数据并创建映射
                    offset_data = self._get_offset_data(algorithm)
                    offset_map = self._create_offset_map(offset_data)

                    # 提取锤速和延时数据（使用algorithm_name作为唯一标识）
                    hammer_velocities, delays_ms, scatter_customdata = \
                        self._extract_hammer_velocity_delay_data(matched_pairs, offset_map, algorithm_name)

                    if not hammer_velocities:
                        logger.warning(f"算法 '{descriptive_name}' 没有有效的散点图数据，跳过")
                        continue

                    # 计算相对延时统计
                    relative_delays, statistics = \
                        self._calculate_relative_delay_statistics(delays_ms, algorithm)

                    # 将锤速转换为对数形式
                    log_velocities = [math.log10(v) for v in hammer_velocities]

                    # 获取算法颜色
                    color = self._get_algorithm_color(alg_idx)

                    # 添加散点图trace
                    self._add_hammer_velocity_scatter_trace(
                        fig, log_velocities, relative_delays, delays_ms,
                        hammer_velocities, scatter_customdata, descriptive_name, color
                    )

                    # 添加阈值线
                    if len(log_velocities) > 0:
                        self._add_relative_delay_threshold_lines(
                            fig, x_min, x_max, statistics, descriptive_name, color
                        )

                except Exception as e:
                    logger.warning(f"获取算法 '{descriptive_name}' 的锤速与相对延时数据失败: {e}")
                    continue

            # 配置布局
            self._configure_hammer_velocity_layout(fig)

            logger.info(f"多算法锤速与相对延时散点图生成成功，共 {len(ready_algorithms)} 个算法")
            return fig

        except Exception as e:
            return self._handle_generation_error(e, "多算法锤速与相对延时散点图")

    def generate_multi_algorithm_hammer_velocity_delay_scatter_plot(
        self,
        algorithms: List[AlgorithmDataset]
    ) -> Any:
        """
        生成多算法锤速与延时散点图（叠加显示，不同颜色，图例控制）
        
        Args:
            algorithms: 激活的算法数据集列表
            
        Returns:
            go.Figure: Plotly图表对象
        """
        try:
            # 验证和准备算法列表
            ready_algorithms = self._validate_and_prepare_algorithms(algorithms)
            if not ready_algorithms:
                return self._create_empty_plot("没有激活的算法")
            
            logger.info(f"📊 开始生成多算法锤速与延时散点图，共 {len(ready_algorithms)} 个算法")
            
            fig = go.Figure()
            
            # 计算x轴范围
            x_min, x_max = self._calculate_log_velocity_range(ready_algorithms)

            for alg_idx, algorithm in enumerate(ready_algorithms):
                metadata = self._extract_algorithm_metadata(algorithm)
                algorithm_name = metadata['algorithm_name']
                descriptive_name = metadata['descriptive_name']
                display_name = metadata['display_name']

                # 验证分析器
                if not self._validate_analyzer(algorithm, descriptive_name):
                    continue

                try:
                    # 获取匹配对
                    matched_pairs = self._get_matched_pairs(algorithm)
                    if not matched_pairs:
                        logger.warning(f"⚠️ 算法 '{descriptive_name}' 没有匹配数据，跳过")
                        continue

                    # 获取偏移数据并创建映射
                    offset_data = self._get_offset_data(algorithm)
                    offset_map = self._create_offset_map(offset_data)

                    # 提取锤速和延时数据（使用algorithm_name作为唯一标识）
                    hammer_velocities, delays_ms, scatter_customdata = \
                        self._extract_hammer_velocity_delay_data(matched_pairs, offset_map, algorithm_name)

                    if not hammer_velocities:
                        logger.warning(f"⚠️ 算法 '{descriptive_name}' 没有有效的散点图数据，跳过")
                        continue

                    # 计算Z-Score
                    z_scores, mu, sigma = self._calculate_zscore_values(delays_ms, algorithm)

                    # 将锤速转换为对数形式
                    log_velocities = [math.log10(v) for v in hammer_velocities]

                    # 获取算法颜色
                    color = self._get_algorithm_color(alg_idx)

                    # 添加散点图trace
                    self._add_hammer_velocity_zscore_scatter_trace(
                        fig, log_velocities, z_scores, delays_ms,
                        hammer_velocities, scatter_customdata, descriptive_name, color
                    )

                    # 添加Z-Score阈值线
                    if len(log_velocities) > 0:
                        self._add_zscore_threshold_lines_for_velocity(
                            fig, x_min, x_max, descriptive_name, color
                        )

                except Exception as e:
                    logger.warning(f"⚠️ 获取算法 '{descriptive_name}' 的锤速与延时数据失败: {e}")
                    continue

            # 配置布局
            self._configure_hammer_velocity_zscore_layout(fig)

            logger.info(f"✅ 多算法锤速与延时散点图生成成功，共 {len(ready_algorithms)} 个算法")
            return fig
            
        except Exception as e:
            return self._handle_generation_error(e, "多算法锤速与延时散点图")
    
    def generate_multi_algorithm_key_hammer_velocity_scatter_plot(
        self,
        algorithms: List[AlgorithmDataset]
    ) -> Any:
        """
        生成多算法按键与锤速散点图（颜色表示延时，叠加显示，不同标记形状区分算法）
        
        Args:
            algorithms: 激活的算法数据集列表
            
        Returns:
            go.Figure: Plotly图表对象
        """
        try:
            # 验证和准备算法列表
            ready_algorithms = self._validate_and_prepare_algorithms(algorithms)
            if not ready_algorithms:
                return self._create_empty_plot("没有激活的算法")
            
            logger.info(f"📊 开始生成多算法按键与锤速散点图，共 {len(ready_algorithms)} 个算法")
            
            fig = go.Figure()
            all_delays = []
            
            for alg_idx, algorithm in enumerate(ready_algorithms):
                metadata = self._extract_algorithm_metadata(algorithm)
                algorithm_name = metadata['algorithm_name']
                descriptive_name = metadata['descriptive_name']

                # 验证分析器
                if not self._validate_analyzer(algorithm, descriptive_name):
                    continue

                try:
                    # 获取匹配对
                    matched_pairs = self._get_matched_pairs(algorithm)
                    if not matched_pairs:
                        logger.warning(f"⚠️ 算法 '{descriptive_name}' 没有匹配数据，跳过")
                        continue

                    # 获取偏移数据并创建映射
                    offset_data = self._get_offset_data(algorithm)
                    offset_map = self._create_offset_map(offset_data)
                    
                    # 提取按键ID、锤速和延时数据
                    key_ids, hammer_velocities, delays_ms = \
                        self._extract_key_hammer_velocity_data(matched_pairs, offset_map)
                    
                    if not key_ids:
                        logger.warning(f"⚠️ 算法 '{descriptive_name}' 没有有效的散点图数据，跳过")
                        continue
                    
                    # 添加到总延时列表
                    all_delays.extend(delays_ms)
                    
                    # 添加散点图trace
                    self._add_key_hammer_velocity_scatter_trace(
                        fig, key_ids, hammer_velocities, delays_ms,
                        descriptive_name, algorithm_name, alg_idx,
                        len(ready_algorithms), all_delays
                    )
                    
                except Exception as e:
                    logger.warning(f"⚠️ 获取算法 '{descriptive_name}' 的按键与锤速数据失败: {e}")
                    continue
            
            if not all_delays:
                logger.warning("⚠️ 没有有效的散点图数据，无法生成图表")
                return self._create_empty_plot("没有有效的散点图数据")
            
            # 配置布局
            self._configure_key_hammer_velocity_layout(fig)
            
            logger.info(f"✅ 多算法按键与锤速散点图生成成功，共 {len(ready_algorithms)} 个算法")
            return fig
            
        except Exception as e:
            return self._handle_generation_error(e, "多算法按键与锤速散点图")
    
    def _create_empty_plot(self, message: str) -> go.Figure:
        """创建空图表（用于错误提示）"""
        fig = go.Figure()
        fig.add_annotation(
            x=0.5,
            y=0.5,
            text=message,
            showarrow=False,
            font=dict(size=16, color='gray'),
            xref='paper',
            yref='paper'
        )
        fig.update_layout(
            xaxis=dict(showgrid=False, showticklabels=False),
            yaxis=dict(showgrid=False, showticklabels=False),
            height=400
        )
        return fig
    
    # ==================== 通用辅助方法 ====================
    
    def _validate_and_prepare_algorithms(self, algorithms: List[AlgorithmDataset]) -> Optional[List[AlgorithmDataset]]:
        """
        验证和准备算法列表
        
        Args:
            algorithms: 算法数据集列表
            
        Returns:
            Optional[List[AlgorithmDataset]]: 就绪的算法列表，如果验证失败返回None
        """
        if not algorithms:
            logger.warning("没有传入任何算法")
            return None
        
        ready_algorithms = [alg for alg in algorithms if alg.is_active and alg.is_ready()]
        
        if not ready_algorithms:
            logger.warning("没有激活且就绪的算法")
            return None
        
        logger.info(f"验证通过: 共 {len(ready_algorithms)} 个就绪算法")
        return ready_algorithms
    
    def _extract_algorithm_metadata(self, algorithm: AlgorithmDataset) -> Dict[str, str]:
        """
        提取算法元数据
        
        Args:
            algorithm: 算法数据集
            
        Returns:
            Dict[str, str]: 包含 algorithm_name, display_name, filename, descriptive_name 的字典
        """
        return {
            'algorithm_name': algorithm.metadata.algorithm_name,
            'display_name': algorithm.metadata.display_name,
            'filename': algorithm.metadata.filename,
            'descriptive_name': f"{algorithm.metadata.display_name} ({algorithm.metadata.filename})"
        }
    
    def _validate_analyzer(self, algorithm: AlgorithmDataset, descriptive_name: str) -> bool:
        """
        验证算法的分析器是否可用
        
        Args:
            algorithm: 算法数据集
            descriptive_name: 算法的描述性名称（用于日志）
            
        Returns:
            bool: 分析器可用返回True，否则返回False
        """
        if not algorithm.analyzer or not algorithm.analyzer.note_matcher:
            logger.warning(f"⚠️ 算法 '{descriptive_name}' 没有分析器或匹配器，跳过")
            return False
        return True
    
    def _get_algorithm_color(self, algorithm_index: int) -> str:
        """
        获取算法对应的颜色
        
        Args:
            algorithm_index: 算法索引
            
        Returns:
            str: 颜色代码
        """
        return self.COLORS[algorithm_index % len(self.COLORS)]
    
    # ==================== 数据获取和转换方法（消除重复代码） ====================
    
    def _get_offset_data(self, algorithm: AlgorithmDataset):
        """
        获取算法的精确偏移对齐数据
        
        Args:
            algorithm: 算法数据集
            
        Returns:
            偏移对齐数据列表，如果获取失败返回空列表
        """
        try:
            if algorithm.analyzer:
                return algorithm.analyzer.get_precision_offset_alignment_data() or []
        except Exception as e:
            logger.warning(f"获取偏移数据失败: {e}")
        return []
    
    def _get_matched_pairs(self, algorithm: AlgorithmDataset):
        """
        获取算法的匹配对数据
        
        Args:
            algorithm: 算法数据集
            
        Returns:
            匹配对列表，如果获取失败返回空列表
        """
        try:
            if algorithm.analyzer:
                return algorithm.analyzer.matched_pairs or []
        except Exception as e:
            logger.warning(f"获取匹配对失败: {e}")
        return []
    
    def _create_note_dicts(self, matched_pairs):
        """
        从匹配对创建音符字典
        
        Args:
            matched_pairs: 匹配对列表 [(record_idx, replay_idx, record_note, replay_note), ...]
            
        Returns:
            Tuple[Dict, Dict]: (record_note_dict, replay_note_dict)
        """
        record_note_dict = {r_idx: r_note for r_idx, _, r_note, _ in matched_pairs}
        replay_note_dict = {p_idx: p_note for _, p_idx, _, p_note in matched_pairs}
        return record_note_dict, replay_note_dict
    
    def _create_offset_map(self, offset_data):
        """
        创建偏移数据索引映射
        
        Args:
            offset_data: 偏移对齐数据列表
            
        Returns:
            Dict: 以 (record_index, replay_index) 为键的偏移数据字典
        """
        offset_map = {}
        for item in offset_data:
            record_idx = item.get('record_index')
            replay_idx = item.get('replay_index')
            if record_idx is not None and replay_idx is not None:
                offset_map[(record_idx, replay_idx)] = item
        return offset_map
    
    def _convert_offset_to_ms(self, keyon_offset) -> float:
        """
        将偏移量从 0.1ms 单位转换为 ms
        
        Args:
            keyon_offset: 偏移量（0.1ms 单位）
            
        Returns:
            float: 偏移量（ms 单位）
        """
        return keyon_offset / 10.0
    
    def _filter_algorithms_by_names(self, algorithms: List[AlgorithmDataset], 
                                    selected_names: List[str] = None) -> List[AlgorithmDataset]:
        """根据名称筛选算法"""
        if selected_names:
            filtered = [alg for alg in algorithms 
                       if alg.metadata.algorithm_name in selected_names]
            logger.info(f"根据用户选择筛选算法: {selected_names} -> 找到 {len(filtered)} 个匹配算法")
            return filtered
        else:
            logger.info("未指定算法筛选，使用所有传入算法")
            return algorithms
    
    def _calculate_common_keys(self, algorithms: List[AlgorithmDataset]) -> Optional[set]:
        """计算所有算法的公共按键"""
        key_sets = []
        for alg in algorithms:
            if alg.analyzer and alg.analyzer.note_matcher:
                offset_data = alg.analyzer.note_matcher.get_precision_offset_alignment_data()
                if offset_data:
                    keys = set(item.get('key_id') for item in offset_data 
                              if item.get('key_id') is not None)
                    key_sets.append(keys)
        
        if key_sets:
            common_keys = set.intersection(*key_sets)
            logger.info(f"只显示公共按键: 共 {len(common_keys)} 个")
            return common_keys
        else:
            logger.warning("没有找到任何公共按键")
            return set()
    
    def _collect_scatter_algorithm_data(self, algorithm: AlgorithmDataset, alg_idx: int,
                                       common_keys: Optional[set]) -> Optional[Dict]:
        """收集单个算法的散点图数据"""
        metadata = self._extract_algorithm_metadata(algorithm)
        if not self._validate_analyzer(algorithm, metadata['descriptive_name']):
            return None
        
        try:
            # 获取基础数据
            offset_data = self._get_offset_data(algorithm)
            if not offset_data:
                logger.warning(f"⚠️ 算法 '{metadata['descriptive_name']}' 没有精确匹配数据，跳过")
                return None
            
            # 获取平均延时
            algorithm_mean_delay_ms = self._calculate_mean_delay(algorithm.analyzer)
            
            # 获取匹配对
            matched_pairs = self._get_matched_pairs(algorithm)
            record_note_dict, replay_note_dict = self._create_note_dicts(matched_pairs)
            
            # 提取延时数据（传递algorithm_name作为唯一标识）
            delay_data = self._extract_scatter_delay_data(
                offset_data, record_note_dict, replay_note_dict, 
                common_keys, metadata['algorithm_name']
            )
            
            if not delay_data['key_ids']:
                logger.warning(f"⚠️ 算法 '{metadata['descriptive_name']}' 没有有效的散点图数据，跳过")
                return None
            
            # 计算统计量和相对延时
            stats = self._calculate_scatter_statistics(
                delay_data['delays_ms'], algorithm.analyzer
            )
            
            # 合并数据（先合并再排序，因为排序需要relative_delays_ms）
            result_data = {
                **metadata,
                **delay_data,
                **stats,
                'color': self._get_algorithm_color(alg_idx),
                'algorithm_mean_delay_ms': algorithm_mean_delay_ms
            }
            
            # 排序数据
            self._sort_scatter_data(result_data)
            
            return result_data
        except Exception as e:
            logger.warning(f"⚠️ 获取算法 '{metadata['descriptive_name']}' 的按键与延时数据失败: {e}")
            return None
    
    def _extract_scatter_delay_data(self, offset_data: List[Dict], 
                                    record_note_dict: Dict, replay_note_dict: Dict,
                                    common_keys: Optional[set], algorithm_name: str) -> Dict:
        """提取散点图的延时数据"""
        key_ids = []
        delays_ms = []
        customdata_list = []
        
        for item in offset_data:
            key_id = item.get('key_id')
            if key_id is None or key_id == 'N/A':
                continue
            
            # 过滤非公共按键
            if common_keys is not None and key_id not in common_keys:
                continue
            
            try:
                key_id_int = int(key_id)
                keyon_offset = item.get('keyon_offset', 0)
                delay_ms = self._convert_offset_to_ms(keyon_offset)
                
                # 获取锤子时间
                record_index = item.get('record_index')
                replay_index = item.get('replay_index')
                record_hammer_time = self._get_hammer_time(record_note_dict, record_index)
                replay_hammer_time = self._get_hammer_time(replay_note_dict, replay_index)
                
                key_ids.append(key_id_int)
                delays_ms.append(delay_ms)
                customdata_list.append([
                    record_index, replay_index, key_id_int, delay_ms, 
                    algorithm_name, record_hammer_time, replay_hammer_time
                ])
            except (ValueError, TypeError):
                continue
        
        return {
            'key_ids': key_ids,
            'delays_ms': delays_ms,
            'customdata': customdata_list
        }
    
    def _get_hammer_time(self, note_dict: Dict, index: int) -> float:
        """获取音符的锤子时间"""
        if index in note_dict:
            note = note_dict[index]
            if (hasattr(note, 'hammers') and note.hammers is not None and 
                not note.hammers.empty):
                return (note.hammers.index[0] + note.offset) / 10.0
        return 0.0
    
    def _calculate_scatter_statistics(self, delays_ms: List[float], analyzer) -> Dict:
        """计算散点图统计量"""
        # 获取总体统计（复用analyzer方法）
        me_0_1ms = analyzer.get_mean_error()
        std_0_1ms = analyzer.get_standard_deviation()
        mu = me_0_1ms / 10.0
        sigma = std_0_1ms / 10.0
        
        # 计算相对延时
        delays_array = np.array(delays_ms)
        relative_delays_array = delays_array - mu
        relative_delays_ms = relative_delays_array.tolist()
        
        # 计算相对延时的阈值
        if len(relative_delays_ms) > 1:
            relative_mu = np.mean(relative_delays_array)
            relative_sigma = np.std(relative_delays_array, ddof=1)
            upper_threshold = relative_mu + 3 * relative_sigma
            lower_threshold = relative_mu - 3 * relative_sigma
        else:
            relative_mu = 0.0
            relative_sigma = 0.0
            upper_threshold = 0.0
            lower_threshold = 0.0
        
        return {
            'mu': mu,
            'sigma': sigma,
            'relative_delays_ms': relative_delays_ms,
            'relative_mu': relative_mu,
            'relative_sigma': relative_sigma,
            'upper_threshold': upper_threshold,
            'lower_threshold': lower_threshold
        }
    
    def _sort_scatter_data(self, data: Dict):
        """按键ID排序散点图数据"""
        sorted_indices = sorted(range(len(data['key_ids'])), 
                               key=lambda i: data['key_ids'][i])
        data['key_ids'][:] = [data['key_ids'][i] for i in sorted_indices]
        data['delays_ms'][:] = [data['delays_ms'][i] for i in sorted_indices]
        data['relative_delays_ms'][:] = [data['relative_delays_ms'][i] for i in sorted_indices]
        data['customdata'][:] = [data['customdata'][i] for i in sorted_indices]
    
    def _add_scatter_plot_traces(self, fig: go.Figure, algorithm_data_list: List[Dict]):
        """添加散点图traces"""
        for alg_data in algorithm_data_list:
            # 计算marker样式
            marker_colors = []
            marker_sizes = []
            for relative_delay in alg_data['relative_delays_ms']:
                if (relative_delay > alg_data['upper_threshold'] or 
                    relative_delay < alg_data['lower_threshold']):
                    marker_colors.append(alg_data['color'])
                    marker_sizes.append(12)
                else:
                    marker_colors.append(alg_data['color'])
                    marker_sizes.append(8)
            
            key_id_strings = [str(kid) for kid in alg_data['key_ids']]
            
            fig.add_trace(go.Scatter(
                x=key_id_strings,
                y=alg_data['relative_delays_ms'],
                mode='markers',
                name=f"{alg_data['descriptive_name']} - 匹配对",
                marker=dict(
                    size=marker_sizes,
                    color=marker_colors,
                    opacity=0.6,
                    line=dict(width=1, color=alg_data['color'])
                ),
                customdata=alg_data['customdata'],
                legendgroup=alg_data['descriptive_name'],
                showlegend=True,
                hovertemplate=f"算法: {alg_data['descriptive_name']}<br>按键: %{{customdata[2]}}<br>相对延时: %{{y:.2f}}ms<br>绝对延时: %{{customdata[3]:.2f}}ms<br>平均延时: {alg_data['algorithm_mean_delay_ms']:.2f}ms<br>录制锤子时间: %{{customdata[5]:.2f}}ms<br>播放锤子时间: %{{customdata[6]:.2f}}ms<extra></extra>"
            ))
    
    def _add_scatter_threshold_lines(self, fig: go.Figure, algorithm_data_list: List[Dict]):
        """添加散点图阈值线"""
        # 获取所有按键ID
        all_key_ids = set()
        for alg_data in algorithm_data_list:
            all_key_ids.update(alg_data['key_ids'])
        key_labels = [str(kid) for kid in sorted(all_key_ids)]
        
        for alg_data in algorithm_data_list:
            descriptive_name = alg_data['descriptive_name']
            color = alg_data['color']
            
            # 平均值线（0线）
            fig.add_trace(go.Scatter(
                x=key_labels,
                y=[0] * len(key_labels),
                mode='lines',
                name=f"{descriptive_name} - 平均值",
                line=dict(color=color, width=1.5, dash='dot'),
                legendgroup=descriptive_name,
                showlegend=True,
                hovertemplate=f"算法: {descriptive_name}<br>相对延时平均值 = 0ms<br>绝对延时平均值 = {alg_data['mu']:.2f}ms<extra></extra>"
            ))
            
            # 上阈值线
            fig.add_trace(go.Scatter(
                x=key_labels,
                y=[alg_data['upper_threshold']] * len(key_labels),
                mode='lines',
                name=f"{descriptive_name} - 上阈值",
                line=dict(color=color, width=2, dash='dash'),
                legendgroup=descriptive_name,
                showlegend=True,
                hovertemplate=f"算法: {descriptive_name}<br>相对延时上阈值 = {alg_data['upper_threshold']:.2f}ms<extra></extra>"
            ))
            
            # 下阈值线
            fig.add_trace(go.Scatter(
                x=key_labels,
                y=[alg_data['lower_threshold']] * len(key_labels),
                mode='lines',
                name=f"{descriptive_name} - 下阈值",
                line=dict(color=color, width=2, dash='dash'),
                legendgroup=descriptive_name,
                showlegend=True,
                hovertemplate=f"算法: {descriptive_name}<br>相对延时下阈值 = {alg_data['lower_threshold']:.2f}ms<extra></extra>"
            ))
    
    def _configure_scatter_plot_layout(self, fig: go.Figure):
        """配置散点图布局"""
        fig.update_layout(
            xaxis_title='按键',
            yaxis_title='相对延时 (ms)',
            xaxis=dict(
                showgrid=True,
                gridcolor='lightgray',
                gridwidth=1,
                type='category'
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor='lightgray',
                gridwidth=1
            ),
            hovermode='closest',
            plot_bgcolor='white',
            paper_bgcolor='white',
            font=dict(size=12),
            height=800,
            showlegend=True,
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.02,
                xanchor='left',
                x=0.0,
                bgcolor='rgba(255, 255, 255, 0.9)',
                bordercolor='gray',
                borderwidth=1
            ),
            margin=dict(t=90, b=60, l=60, r=60)
        )
    
    def _calculate_zscore_values(self, delays_ms: List[float], algorithm) -> Tuple[List[float], float, float]:
        """
        计算Z-Score值
        
        Args:
            delays_ms: 绝对延时列表（毫秒）
            algorithm: 算法数据集对象
            
        Returns:
            Tuple[List[float], float, float]: (Z-Score列表, 均值, 标准差)
        """
        # 获取总体均值和标准差（0.1ms单位）
        me_0_1ms = algorithm.analyzer.get_mean_error()
        std_0_1ms = algorithm.analyzer.get_standard_deviation()
        
        # 转换为ms单位
        mu = me_0_1ms / 10.0
        sigma = std_0_1ms / 10.0
        
        # 计算Z-Score：z = (x_i - μ) / σ
        if sigma > 0:
            delays_array = np.array(delays_ms)
            z_scores_array = (delays_array - mu) / sigma
            z_scores = z_scores_array.tolist()
            
            logger.info(f"🔍 Z-Score计算: μ={mu:.2f}ms, σ={sigma:.2f}ms, "
                       f"原始延时范围=[{delays_array.min():.2f}, {delays_array.max():.2f}]ms, "
                       f"Z-Score范围=[{z_scores_array.min():.2f}, {z_scores_array.max():.2f}]")
        else:
            z_scores = [0.0] * len(delays_ms)
            logger.warning(f"⚠️ 标准差为0，无法进行Z-Score标准化")
        
        return z_scores, mu, sigma
    
    def _add_zscore_scatter_traces(self, fig: go.Figure, key_ids: List[int], z_scores: List[float],
                                   customdata_list: List, descriptive_name: str, color: str):
        """添加Z-Score散点图traces"""
        fig.add_trace(go.Scatter(
            x=[str(kid) for kid in key_ids],
            y=z_scores,
            mode='markers',
            name=f"{descriptive_name} - Z-Score",
            marker=dict(
                size=8,
                color=color,
                opacity=0.6,
                line=dict(width=1, color=color)
            ),
            customdata=customdata_list,
            legendgroup=descriptive_name,
            showlegend=True,
            hovertemplate=f"算法: {descriptive_name}<br>键位: %{{x}}<br>"
                         f"延时: %{{customdata[3]:.2f}}ms<br>Z-Score: %{{y:.2f}}<br>"
                         f"录制锤子时间: %{{customdata[5]:.2f}}ms<br>"
                         f"播放锤子时间: %{{customdata[6]:.2f}}ms<extra></extra>"
        ))
    
    def _add_zscore_threshold_lines(self, fig: go.Figure, key_labels: List[str],
                                    ready_algorithms: List, thresholds: List[float] = [0, 3, -3]):
        """
        添加Z-Score阈值线
        
        Args:
            fig: Plotly图表对象
            key_labels: 按键标签列表
            ready_algorithms: 准备好的算法列表
            thresholds: 阈值列表，默认[0, 3, -3]
        """
        threshold_names = {0: 'Z=0 (均值线)', 3: 'Z=+3 (上阈值)', -3: 'Z=-3 (下阈值)'}
        threshold_styles = {0: 'dot', 3: 'dash', -3: 'dash'}
        threshold_widths = {0: 1.5, 3: 2, -3: 2}
        
        for alg_idx, algorithm in enumerate(ready_algorithms):
            metadata = self._extract_algorithm_metadata(algorithm)
            descriptive_name = metadata['descriptive_name']
            color = self._get_algorithm_color(alg_idx)
            
            for threshold in thresholds:
                fig.add_trace(go.Scatter(
                    x=key_labels,
                    y=[threshold] * len(key_labels),
                    mode='lines',
                    name=f"{descriptive_name} - {threshold_names[threshold].split()[0]}",
                    line=dict(
                        color=color,
                        width=threshold_widths[threshold],
                        dash=threshold_styles[threshold]
                    ),
                    legendgroup=descriptive_name,
                    showlegend=True,
                    hovertemplate=f"算法: {descriptive_name}<br>{threshold_names[threshold]}<extra></extra>"
                ))
    
    def _configure_zscore_layout(self, fig: go.Figure):
        """配置Z-Score散点图布局"""
        fig.update_layout(
            xaxis_title='按键ID',
            yaxis_title='Z-Score (标准化延时)',
            xaxis=dict(
                showgrid=True,
                gridcolor='lightgray',
                gridwidth=1,
                type='category'
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor='lightgray',
                gridwidth=1
            ),
            hovermode='closest',
            plot_bgcolor='white',
            paper_bgcolor='white',
            font=dict(size=12),
            height=800,
            showlegend=True,
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.02,
                xanchor='left',
                x=0.0,
                bgcolor='rgba(255, 255, 255, 0.9)',
                bordercolor='gray',
                borderwidth=1
            ),
            margin=dict(t=90, b=60, l=60, r=60)
        )
    
    def _extract_single_key_delays(self, offset_data: List[Dict], target_key_id: int, 
                                   filename: str) -> Tuple[List[float], List]:
        """
        提取单个按键的延时数据
        
        Args:
            offset_data: 偏移数据列表
            target_key_id: 目标按键ID
            filename: 文件名（用于customdata）
            
        Returns:
            Tuple[List[float], List]: (延时列表, customdata列表)
        """
        key_delays = []
        customdata_list = []
        
        for item in offset_data:
            key_id = item.get('key_id')
            if key_id == target_key_id:
                keyon_offset = item.get('keyon_offset', 0)
                delay_ms = keyon_offset / 10.0  # 转换为ms
                key_delays.append(delay_ms)
                
                # 记录详细信息，用于悬停
                record_index = item.get('record_index')
                replay_index = item.get('replay_index')
                customdata_list.append([record_index, replay_index, delay_ms, filename])
        
        return key_delays, customdata_list
    
    def _add_box_trace(self, fig: go.Figure, key_delays: List[float], display_name: str,
                      target_key_id: int, customdata_list: List, color: str):
        """
        添加箱线图trace
        
        Args:
            fig: Plotly图表对象
            key_delays: 延时列表
            display_name: 算法显示名称
            target_key_id: 目标按键ID
            customdata_list: 自定义数据列表
            color: 颜色
        """
        fig.add_trace(go.Box(
            y=key_delays,
            x=[display_name] * len(key_delays),  # X轴为算法名称
            name=display_name,
            boxpoints='all',  # 显示所有点
            jitter=0.5,       # 点的抖动范围
            pointpos=-1.8,    # 点显示在箱线图左侧
            marker=dict(
                color=color,
                size=6,
                opacity=0.7
            ),
            line=dict(color=color),
            fillcolor='rgba(255,255,255,0)',  # 透明填充
            showlegend=False,  # 箱线图不显示图例，避免重复
            customdata=customdata_list,
            hovertemplate=f'算法: {display_name}<br>按键: {target_key_id}<br>延时: %{{y:.2f}}ms<extra></extra>'
        ))
    
    def _configure_single_key_layout(self, fig: go.Figure, target_key_id: int):
        """
        配置单键对比图布局
        
        Args:
            fig: Plotly图表对象
            target_key_id: 目标按键ID
        """
        fig.update_layout(
            title=dict(
                text=f"按键 {target_key_id} 延时分布对比 (多曲目/算法)",
                x=0.5,
                xanchor='center'
            ),
            xaxis=dict(
                title="曲子 / 算法",
                showgrid=False
            ),
            yaxis=dict(
                title="相对延时 (ms)",
                showgrid=True,
                gridcolor='lightgray',
                zeroline=True,
                zerolinecolor='gray'
            ),
            plot_bgcolor='white',
            paper_bgcolor='white',
            hovermode='closest',
            showlegend=False,  # 不需要图例，X轴标签已说明
            height=400,
            margin=dict(l=60, r=40, t=60, b=40)
        )
    
    def _extract_hammer_velocity_delay_data(self, matched_pairs: List[Tuple], 
                                           offset_map: Dict, algorithm_name: str) -> Tuple[List, List, List]:
        """
        提取锤速和延时数据
        
        Args:
            matched_pairs: 匹配对列表
            offset_map: 偏移数据映射
            algorithm_name: 算法唯一标识符（算法名_文件名）
            
        Returns:
            Tuple[List, List, List]: (锤速列表, 延时列表(ms), customdata列表)
        """
        hammer_velocities = []
        delays_ms = []
        scatter_customdata = []
        
        for record_idx, replay_idx, record_note, replay_note in matched_pairs:
            # 获取播放音符的锤速（第一个锤速值）
            if len(replay_note.hammers) > 0 and len(replay_note.hammers.values) > 0:
                hammer_velocity = replay_note.hammers.values[0]
            else:
                continue
            
            # 跳过锤速为0或负数的数据点（对数无法处理）
            if hammer_velocity <= 0:
                continue
            
            # 从偏移数据中获取延时
            if (record_idx, replay_idx) not in offset_map:
                continue
            
            keyon_offset = offset_map[(record_idx, replay_idx)].get('keyon_offset', 0)
            delay_ms = self._convert_offset_to_ms(keyon_offset)
            
            # 获取按键ID
            key_id = record_note.id if hasattr(record_note, 'id') else None
            
            hammer_velocities.append(hammer_velocity)
            delays_ms.append(delay_ms)
            # 使用algorithm_name（完整的唯一标识符）而不是display_name
            scatter_customdata.append([record_idx, replay_idx, algorithm_name, key_id])
        
        return hammer_velocities, delays_ms, scatter_customdata
    
    def _calculate_relative_delay_statistics(self, delays_ms: List[float], 
                                            algorithm) -> Tuple[List[float], Dict]:
        """
        计算相对延时统计信息
        
        Args:
            delays_ms: 绝对延时列表(ms)
            algorithm: 算法数据集
            
        Returns:
            Tuple[List[float], Dict]: (相对延时列表, 统计信息字典)
        """
        # 获取该算法的总体均值和标准差
        me_0_1ms = algorithm.analyzer.get_mean_error() if hasattr(algorithm.analyzer, 'get_mean_error') else 0.0
        std_0_1ms = algorithm.analyzer.get_standard_deviation() if hasattr(algorithm.analyzer, 'get_standard_deviation') else 0.0
        
        mu = me_0_1ms / 10.0  # 总体均值（ms）
        sigma = std_0_1ms / 10.0  # 总体标准差（ms）
        
        # 计算相对延时：绝对延时减去平均延时
        delays_array = np.array(delays_ms)
        relative_delays = (delays_array - mu).tolist()
        
        # 计算相对延时的统计值（用于阈值）
        if len(relative_delays) > 1:
            relative_mu = np.mean(relative_delays)  # 应该接近0
            relative_sigma = np.std(relative_delays, ddof=1)  # 样本标准差
            upper_threshold = relative_mu + 3 * relative_sigma
            lower_threshold = relative_mu - 3 * relative_sigma
        else:
            relative_mu = 0.0
            relative_sigma = 0.0
            upper_threshold = 0.0
            lower_threshold = 0.0
        
        statistics = {
            'mu': mu,
            'sigma': sigma,
            'relative_mu': relative_mu,
            'relative_sigma': relative_sigma,
            'upper_threshold': upper_threshold,
            'lower_threshold': lower_threshold
        }
        
        return relative_delays, statistics
    
    def _add_hammer_velocity_scatter_trace(self, fig: go.Figure, log_velocities: List[float],
                                          relative_delays: List[float], delays_ms: List[float],
                                          hammer_velocities: List[float], scatter_customdata: List,
                                          descriptive_name: str, color: str):
        """
        添加锤速散点图trace
        
        Args:
            fig: Plotly图表对象
            log_velocities: 对数锤速列表
            relative_delays: 相对延时列表
            delays_ms: 绝对延时列表
            hammer_velocities: 锤速列表
            scatter_customdata: 自定义数据列表
            descriptive_name: 算法描述名称
            color: 颜色
        """
        # 组合customdata: [delay_ms, original_velocity, record_idx, replay_idx, algorithm_name, key_id]
        combined_customdata = [[delay_ms, orig_vel, record_idx, replay_idx, alg_name, key_id]
                              for delay_ms, orig_vel, (record_idx, replay_idx, alg_name, key_id)
                              in zip(delays_ms, hammer_velocities, scatter_customdata)]
        
        fig.add_trace(go.Scatter(
            x=log_velocities,
            y=relative_delays,
            mode='markers',
            name=f"{descriptive_name} - 相对延时",
            marker=dict(
                size=8,
                color=color,
                opacity=0.6,
                line=dict(width=1, color=color)
            ),
            legendgroup=descriptive_name,
            showlegend=True,
            hovertemplate=f"算法: {descriptive_name}<br>按键: %{{customdata[5]}}<br>"
                         f"锤速: %{{customdata[1]:.0f}} (log: %{{x:.2f}})<br>"
                         f"相对延时: %{{y:.2f}}ms<br>绝对延时: %{{customdata[0]:.2f}}ms<extra></extra>",
            customdata=combined_customdata
        ))
    
    def _calculate_log_velocity_range(self, ready_algorithms: List) -> Tuple[float, float]:
        """
        计算所有算法的对数锤速范围
        
        Args:
            ready_algorithms: 准备好的算法列表
            
        Returns:
            Tuple[float, float]: (x_min, x_max)
        """
        all_log_velocities = []
        
        for alg in ready_algorithms:
            try:
                matched_pairs = alg.analyzer.note_matcher.get_matched_pairs()
                for record_idx, replay_idx, record_note, replay_note in matched_pairs:
                    if len(replay_note.hammers) > 0 and len(replay_note.hammers.values) > 0:
                        vel = replay_note.hammers.values[0]
                        if vel > 0:
                            all_log_velocities.append(math.log10(vel))
            except:
                continue
        
        x_min = min(all_log_velocities) if all_log_velocities else 0
        x_max = max(all_log_velocities) if all_log_velocities else 2
        
        return x_min, x_max
    
    def _add_relative_delay_threshold_lines(self, fig: go.Figure, x_min: float, x_max: float,
                                           statistics: Dict, descriptive_name: str, color: str):
        """
        添加相对延时阈值线
        
        Args:
            fig: Plotly图表对象
            x_min: X轴最小值
            x_max: X轴最大值
            statistics: 统计信息字典
            descriptive_name: 算法描述名称
            color: 颜色
        """
        relative_mu = statistics['relative_mu']
        upper_threshold = statistics['upper_threshold']
        lower_threshold = statistics['lower_threshold']
        
        # 添加平均值参考线（0线）
        fig.add_trace(go.Scatter(
            x=[x_min, x_max],
            y=[relative_mu, relative_mu],
            mode='lines',
            name=f'{descriptive_name} - 平均值',
            line=dict(color=color, width=1.5, dash='dot'),
            legendgroup=descriptive_name,
            showlegend=True,
            hovertemplate=f"算法: {descriptive_name}<br>相对延时平均值 = {relative_mu:.2f}ms<extra></extra>"
        ))
        
        # 添加上阈值线
        fig.add_trace(go.Scatter(
            x=[x_min, x_max],
            y=[upper_threshold, upper_threshold],
            mode='lines',
            name=f'{descriptive_name} - 上阈值',
            line=dict(color=color, width=2, dash='dash'),
            legendgroup=descriptive_name,
            showlegend=True,
            hovertemplate=f"算法: {descriptive_name}<br>相对延时上阈值 = {upper_threshold:.2f}ms<extra></extra>"
        ))
        
        # 添加下阈值线
        fig.add_trace(go.Scatter(
            x=[x_min, x_max],
            y=[lower_threshold, lower_threshold],
            mode='lines',
            name=f'{descriptive_name} - 下阈值',
            line=dict(color=color, width=2, dash='dash'),
            legendgroup=descriptive_name,
            showlegend=True,
            hovertemplate=f"算法: {descriptive_name}<br>相对延时下阈值 = {lower_threshold:.2f}ms<extra></extra>"
        ))
    
    def _configure_hammer_velocity_layout(self, fig: go.Figure):
        """配置锤速与相对延时图布局"""
        fig.update_layout(
            xaxis_title='log₁₀(锤速)',
            yaxis_title='相对延时 (ms)',
            xaxis=dict(
                showgrid=True,
                gridcolor='lightgray',
                gridwidth=1
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor='lightgray',
                gridwidth=1
            ),
            hovermode='closest',
            plot_bgcolor='white',
            paper_bgcolor='white',
            font=dict(size=12),
            height=800,
            showlegend=True,
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.02,
                xanchor='left',
                x=0.0,
                bgcolor='rgba(255, 255, 255, 0.9)',
                bordercolor='gray',
                borderwidth=1
            ),
            margin=dict(t=90, b=60, l=60, r=60)
        )
    
    def _add_hammer_velocity_zscore_scatter_trace(self, fig: go.Figure, log_velocities: List[float],
                                                  z_scores: List[float], delays_ms: List[float],
                                                  hammer_velocities: List[float], scatter_customdata: List,
                                                  descriptive_name: str, color: str):
        """
        添加锤速Z-Score散点图trace
        
        Args:
            fig: Plotly图表对象
            log_velocities: 对数锤速列表
            z_scores: Z-Score列表
            delays_ms: 绝对延时列表
            hammer_velocities: 锤速列表
            scatter_customdata: 自定义数据列表
            descriptive_name: 算法描述名称
            color: 颜色
        """
        # 组合customdata: [delay_ms, original_velocity, record_idx, replay_idx, algorithm_name, key_id]
        combined_customdata = [[delay_ms, orig_vel, record_idx, replay_idx, alg_name, key_id]
                              for delay_ms, orig_vel, (record_idx, replay_idx, alg_name, key_id)
                              in zip(delays_ms, hammer_velocities, scatter_customdata)]
        
        fig.add_trace(go.Scatter(
            x=log_velocities,
            y=z_scores,
            mode='markers',
            name=f'{descriptive_name} - Z-Score',
            marker=dict(
                size=8,
                color=color,
                opacity=0.6,
                line=dict(width=1, color=color)
            ),
            legendgroup=descriptive_name,
            showlegend=True,
            hovertemplate=f'算法: {descriptive_name}<br>按键: %{{customdata[5]}}<br>'
                         f'锤速: %{{customdata[1]:.0f}} (log: %{{x:.2f}})<br>'
                         f'延时: %{{customdata[0]:.2f}}ms<br>Z-Score: %{{y:.2f}}<extra></extra>',
            customdata=combined_customdata
        ))
    
    def _add_zscore_threshold_lines_for_velocity(self, fig: go.Figure, x_min: float, x_max: float,
                                                 descriptive_name: str, color: str):
        """
        为锤速图添加Z-Score阈值线
        
        Args:
            fig: Plotly图表对象
            x_min: X轴最小值
            x_max: X轴最大值
            descriptive_name: 算法描述名称
            color: 颜色
        """
        # 添加Z=0的水平虚线（均值线）
        fig.add_trace(go.Scatter(
            x=[x_min, x_max],
            y=[0, 0],
            mode='lines',
            name=f'{descriptive_name} - Z=0',
            line=dict(color=color, width=1.5, dash='dot'),
            legendgroup=descriptive_name,
            showlegend=True,
            hovertemplate=f'算法: {descriptive_name}<br>Z-Score = 0 (均值线)<extra></extra>'
        ))
        
        # 添加Z=+3的水平虚线（上阈值）
        fig.add_trace(go.Scatter(
            x=[x_min, x_max],
            y=[3, 3],
            mode='lines',
            name=f'{descriptive_name} - Z=+3',
            line=dict(color=color, width=2, dash='dash'),
            legendgroup=descriptive_name,
            showlegend=True,
            hovertemplate=f'算法: {descriptive_name}<br>Z-Score = +3 (上阈值)<extra></extra>'
        ))
        
        # 添加Z=-3的水平虚线（下阈值）
        fig.add_trace(go.Scatter(
            x=[x_min, x_max],
            y=[-3, -3],
            mode='lines',
            name=f'{descriptive_name} - Z=-3',
            line=dict(color=color, width=2, dash='dash'),
            legendgroup=descriptive_name,
            showlegend=True,
            hovertemplate=f'算法: {descriptive_name}<br>Z-Score = -3 (下阈值)<extra></extra>'
        ))
    
    def _configure_hammer_velocity_zscore_layout(self, fig: go.Figure):
        """配置锤速Z-Score图布局"""
        fig.update_layout(
            xaxis_title='锤速（log₁₀）',
            yaxis_title='Z-Score（标准化延时）',
            xaxis=dict(
                showgrid=True,
                gridcolor='lightgray',
                gridwidth=1,
                autorange=True,
                tickformat='.1f',
                dtick=0.2
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor='lightgray',
                gridwidth=1,
                range=[-5, 5],
                dtick=1,
                tickformat='.1f'
            ),
            hovermode='closest',
            plot_bgcolor='white',
            paper_bgcolor='white',
            font=dict(size=12),
            height=500,
            showlegend=True,
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.02,
                xanchor='left',
                x=0.0,
                bgcolor='rgba(255, 255, 255, 0.9)',
                bordercolor='gray',
                borderwidth=1
            ),
            margin=dict(t=70, b=60, l=60, r=60)
        )
    
    def _extract_key_hammer_velocity_data(self, matched_pairs: List[Tuple], 
                                          offset_map: Dict) -> Tuple[List[int], List[float], List[float]]:
        """
        提取按键ID、锤速和延时数据
        
        Args:
            matched_pairs: 匹配对列表
            offset_map: 偏移数据映射
            
        Returns:
            Tuple[List[int], List[float], List[float]]: (按键ID列表, 锤速列表, 延时列表)
        """
        key_ids = []
        hammer_velocities = []
        delays_ms = []
        
        for record_idx, replay_idx, record_note, replay_note in matched_pairs:
            key_id = record_note.id
            
            # 获取锤速
            if len(replay_note.hammers) > 0 and len(replay_note.hammers.values) > 0:
                hammer_velocity = replay_note.hammers.values[0]
            else:
                continue
            
            # 获取延时
            if (record_idx, replay_idx) not in offset_map:
                continue
            
            keyon_offset = offset_map[(record_idx, replay_idx)].get('keyon_offset', 0)
            delay_ms = abs(keyon_offset) / 10.0
            
            try:
                key_id_int = int(key_id)
                key_ids.append(key_id_int)
                hammer_velocities.append(hammer_velocity)
                delays_ms.append(delay_ms)
            except (ValueError, TypeError):
                continue
        
        return key_ids, hammer_velocities, delays_ms
    
    def _add_key_hammer_velocity_scatter_trace(self, fig: go.Figure, key_ids: List[int],
                                               hammer_velocities: List[float], delays_ms: List[float],
                                               descriptive_name: str, algorithm_name: str,
                                               alg_idx: int, num_algorithms: int, all_delays: List[float]):
        """
        添加按键与锤速散点图trace
        
        Args:
            fig: Plotly图表对象
            key_ids: 按键ID列表
            hammer_velocities: 锤速列表
            delays_ms: 延时列表
            descriptive_name: 算法描述名称
            algorithm_name: 算法名称
            alg_idx: 算法索引
            num_algorithms: 算法总数
            all_delays: 所有延时列表（用于颜色范围）
        """
        marker_symbols = ['circle', 'square', 'diamond', 'triangle-up', 'x', 'star', 'cross', 'pentagon']
        colorscales = ['Viridis', 'Plasma', 'Inferno', 'Magma', 'Cividis', 'Turbo', 'Blues', 'Reds']
        
        marker_symbol = marker_symbols[alg_idx % len(marker_symbols)]
        colorscale = colorscales[alg_idx % len(colorscales)]
        
        fig.add_trace(go.Scatter(
            x=key_ids,
            y=hammer_velocities,
            mode='markers',
            name=f'{descriptive_name}',
            marker=dict(
                size=8,
                color=delays_ms,
                colorscale=colorscale,
                colorbar=dict(
                    title=f'{descriptive_name}<br>延时 (ms)',
                    thickness=15,
                    len=0.3,
                    x=1.02 + (alg_idx * 0.08),
                    y=0.5 - (alg_idx * 0.3 / num_algorithms)
                ),
                cmin=min(all_delays) if all_delays else 0,
                cmax=max(all_delays) if all_delays else 100,
                symbol=marker_symbol,
                line=dict(width=1, color='rgba(0,0,0,0.3)')
            ),
            legendgroup=algorithm_name,
            showlegend=True,
            hovertemplate=f'算法: {algorithm_name}<br>键位: %{{x}}<br>锤速: %{{y}}<br>延时: %{{marker.color:.2f}}ms<extra></extra>'
        ))
    
    def _configure_key_hammer_velocity_layout(self, fig: go.Figure):
        """配置按键与锤速散点图布局"""
        fig.update_layout(
            xaxis_title='按键ID',
            yaxis_title='锤速',
            xaxis=dict(
                showgrid=True,
                gridcolor='lightgray',
                gridwidth=1,
                dtick=10
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor='lightgray',
                gridwidth=1
            ),
            hovermode='closest',
            plot_bgcolor='white',
            paper_bgcolor='white',
            font=dict(size=12),
            height=500,
            showlegend=True,
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.02,
                xanchor='left',
                x=0.0,
                bgcolor='rgba(255, 255, 255, 0.9)',
                bordercolor='gray',
                borderwidth=1
            ),
            margin=dict(t=70, b=60, l=60, r=200)
        )
    
    
    def _should_generate_time_series_plot(self, algorithms: List[AlgorithmDataset]) -> Tuple[bool, str]:
        """
        判断是否应该生成延时时间序列图

        条件：
        1. 至少有2个算法

        Args:
            algorithms: 算法数据集列表

        Returns:
            Tuple[bool, str]: (是否应该生成, 原因说明)
        """
        if not algorithms or len(algorithms) < 2:
            return False, "需要至少2个算法才能进行对比"

        # 只要有至少2个算法就可以生成图表，不再限制同种算法的不同曲子
        return True, ""
    
    def _filter_ready_algorithms(self, algorithms: List[AlgorithmDataset]) -> List[AlgorithmDataset]:
        """
        过滤出就绪的算法

        Args:
            algorithms: 原始算法列表

        Returns:
            List[AlgorithmDataset]: 就绪的算法列表
        """
        return [alg for alg in algorithms if alg.is_ready()]

    def _prepare_algorithm_colors(self) -> List[str]:
        """
        准备算法颜色列表

        Returns:
            List[str]: 颜色列表
        """
        return ALGORITHM_COLOR_PALETTE

    def _process_single_algorithm_data(self, algorithm: AlgorithmDataset) -> Optional[Dict[str, Any]]:
        """
        处理单个算法的时间序列数据

        Args:
            algorithm: 算法数据集

        Returns:
            Optional[Dict[str, Any]]: 处理后的数据，包含时间、延时等信息，如果处理失败返回None
        """
        algorithm_name = algorithm.metadata.algorithm_name
        display_name = algorithm.metadata.display_name

        if not algorithm.analyzer or not algorithm.analyzer.note_matcher:
            logger.warning(f"⚠️ 算法 '{display_name}' 没有分析器或匹配器，跳过")
            return None

        try:
            offset_data = algorithm.analyzer.note_matcher.get_precision_offset_alignment_data()

            if not offset_data:
                logger.warning(f"⚠️ 算法 '{display_name}' 没有匹配数据，跳过")
                return None

            # 提取时间和延时数据
            data_points = []

            for item in offset_data:
                record_keyon_raw = item.get('record_keyon')  # 单位：0.1ms
                keyon_offset_raw = item.get('keyon_offset')  # 单位：0.1ms
                key_id = item.get('key_id')
                record_index = item.get('record_index')
                replay_index = item.get('replay_index')

                # 检查数据类型有效性（支持 numpy 类型）
                record_keyon_is_valid = isinstance(record_keyon_raw, (int, float, np.integer, np.floating))
                keyon_offset_is_valid = isinstance(keyon_offset_raw, (int, float, np.integer, np.floating))


                if not record_keyon_is_valid:
                    continue
                if not keyon_offset_is_valid:
                    continue

                # 使用原始数据
                record_keyon = record_keyon_raw
                keyon_offset = keyon_offset_raw

                # 转换为ms单位
                time_ms = record_keyon / 10.0
                delay_ms = keyon_offset / 10.0

                data_points.append({
                    'time': time_ms,
                    'delay': delay_ms,
                    'key_id': key_id if key_id is not None else 'N/A',
                    'record_index': record_index,
                    'replay_index': replay_index
                })

            if not data_points:
                logger.warning(f"算法 '{display_name}' 没有有效时间序列数据，跳过")
                return None

            # 按时间排序，确保按时间顺序显示
            data_points.sort(key=lambda x: x['time'])

            # 计算该算法的平均延时
            me_0_1ms = algorithm.analyzer.get_mean_error() if hasattr(algorithm.analyzer, 'get_mean_error') else 0.0
            mean_delay = me_0_1ms / 10.0  # 平均延时（ms，带符号）

            # 计算相对延时
            relative_delays_ms = []
            for point in data_points:
                delay_ms = point['delay']
                relative_delay = delay_ms - mean_delay
                relative_delays_ms.append(relative_delay)

            # 提取排序后的数据
            times_ms = [point['time'] for point in data_points]
            delays_ms = [point['delay'] for point in data_points]
            replay_times_ms = [point['time'] + point['delay'] for point in data_points]
            replay_times_offset_ms = [replay_time - mean_delay for replay_time in replay_times_ms]

            # customdata 包含 [key_id, record_index, replay_index, algorithm_name, 原始延时, 平均延时, 播放时间, 录制时间]
            customdata_list = [[point['key_id'], point['record_index'], point['replay_index'],
                               algorithm_name, point['delay'], mean_delay, replay_time, point['time']]
                              for point, replay_time in zip(data_points, replay_times_ms)]

            return {
                'algorithm_name': algorithm_name,
                'display_name': display_name,
                'data_points': data_points,
                'times_ms': times_ms,
                'delays_ms': delays_ms,
                'relative_delays_ms': relative_delays_ms,
                'replay_times_ms': replay_times_ms,
                'replay_times_offset_ms': replay_times_offset_ms,
                'customdata_list': customdata_list,
                'mean_delay': mean_delay
            }

        except Exception as e:
            logger.warning(f"获取算法 '{display_name}' 的时间序列数据失败: {e}")
            return None

    def _create_relative_delay_traces(self, fig, algorithm_data: Dict[str, Any], color: str) -> None:
        """
        为相对延时图创建trace

        Args:
            fig: Plotly图表对象
            algorithm_data: 算法数据
            color: 算法颜色
        """
        algorithm_name = algorithm_data['algorithm_name']
        display_name = algorithm_data['display_name']
        replay_times_ms = algorithm_data['replay_times_ms']
        replay_times_offset_ms = algorithm_data['replay_times_offset_ms']
        relative_delays_ms = algorithm_data['relative_delays_ms']
        customdata_list = algorithm_data['customdata_list']
        mean_delay = algorithm_data['mean_delay']

        # 添加偏移后的播放音轨散点图（X轴=偏移后的播放时间，Y轴=相对延时）
        fig.add_trace(go.Scatter(
            x=replay_times_offset_ms,  # X轴使用偏移后的播放时间（播放时间 - 平均延时）
            y=relative_delays_ms,  # Y轴使用相对延时
            mode='markers+lines',  # 显示数据点并按时间顺序连接
            name=f'{display_name} (偏移后，平均延时: {mean_delay:.2f}ms)',
            marker=dict(
                size=5,
                color=color,
                line=dict(width=0.5, color=color)
            ),
            line=dict(color=color, width=1.5),
            legendgroup=f"{algorithm_name}_offset",
            showlegend=True,
            hovertemplate='<b>算法</b>: ' + display_name + ' (偏移后)<br>' +
                         '<b>偏移后播放时间（X轴）</b>: %{x:.2f}ms<br>' +
                         '<b>相对延时（Y轴）</b>: %{y:.2f}ms<br>' +
                         '<b>实际播放时间</b>: %{customdata[6]:.2f}ms<br>' +
                         '<b>录制时间</b>: %{customdata[7]:.2f}ms<br>' +
                         '<b>原始延时</b>: %{customdata[4]:.2f}ms<br>' +
                         '<b>平均延时</b>: %{customdata[5]:.2f}ms<br>' +
                         '<b>按键ID</b>: %{customdata[0]}<br>' +
                         '<extra></extra>',
            customdata=customdata_list
        ))

    def _add_algorithm_reference_lines(self, fig, algorithm_data: Dict[str, Any], color: str) -> None:
        """
        为算法添加参考线

        Args:
            fig: Plotly图表对象
            algorithm_data: 算法数据
            color: 算法颜色
        """
        algorithm_name = algorithm_data['algorithm_name']
        display_name = algorithm_data['display_name']
        delays_ms = algorithm_data['delays_ms']
        replay_times_offset_ms = algorithm_data['replay_times_offset_ms']
        algorithm = algorithm_data.get('algorithm_instance')

        if not delays_ms or len(delays_ms) == 0 or not algorithm or not algorithm.analyzer:
            return

        # 计算标准差
        std_0_1ms = algorithm.analyzer.get_standard_deviation() if hasattr(algorithm.analyzer, 'get_standard_deviation') else 0.0
        std_delay = std_0_1ms / 10.0

        # 获取时间范围
        replay_time_offset_min = min(replay_times_offset_ms) if replay_times_offset_ms else 0
        replay_time_offset_max = max(replay_times_offset_ms) if replay_times_offset_ms else 1

        # 添加零线参考线
        fig.add_trace(go.Scatter(
            x=[replay_time_offset_min, replay_time_offset_max],
            y=[0, 0],
            mode='lines',
            name=f'{display_name} - 零线',
            line=dict(dash='dash', color=color, width=1.5),
            hovertemplate=f'<b>{display_name} 零线</b>: 0.00ms<extra></extra>',
            showlegend=False,
            legendgroup=algorithm_name
        ))

        # 添加±3σ参考线
        if std_delay > 0:
            fig.add_trace(go.Scatter(
                x=[replay_time_offset_min, replay_time_offset_max],
                y=[3 * std_delay, 3 * std_delay],
                mode='lines',
                name=f'{display_name} - +3σ',
                line=dict(dash='dot', color=color, width=1),
                hovertemplate=f'<b>{display_name} +3σ</b>: {3 * std_delay:.2f}ms<extra></extra>',
                showlegend=False,
                legendgroup=algorithm_name
            ))
            fig.add_trace(go.Scatter(
                x=[replay_time_offset_min, replay_time_offset_max],
                y=[-3 * std_delay, -3 * std_delay],
                mode='lines',
                name=f'{display_name} - -3σ',
                line=dict(dash='dot', color=color, width=1),
                hovertemplate=f'<b>{display_name} -3σ</b>: {-3 * std_delay:.2f}ms<extra></extra>',
                showlegend=False,
                legendgroup=algorithm_name
            ))

    def _collect_all_relative_delay_data(self, ready_algorithms: List[AlgorithmDataset], colors: List[str], apply_time_offset: bool = False) -> List[Tuple[float, float, List, str, str]]:
        """
        收集所有算法的相对延时数据

        Args:
            ready_algorithms: 就绪的算法列表
            colors: 颜色列表
            apply_time_offset: 是否应用时间轴偏移（减去平均延时）

        Returns:
            List[Tuple[float, float, List, str, str]]: 相对数据列表 (time_ms, relative_delay_ms, customdata, descriptive_name, color)
        """
        all_relative_data = []

        for alg_idx, algorithm in enumerate(ready_algorithms):
            algorithm_name = algorithm.metadata.algorithm_name
            display_name = algorithm.metadata.display_name
            filename = algorithm.metadata.filename
            descriptive_name = f"{display_name} ({filename})"
            color = colors[alg_idx % len(colors)]

            if not algorithm.analyzer or not algorithm.analyzer.note_matcher:
                continue

            try:
                offset_data = algorithm.analyzer.get_precision_offset_alignment_data()

                if not offset_data:
                    continue

                # 计算该算法的平均延时（用于相对延时计算）
                me_0_1ms = algorithm.analyzer.note_matcher.get_mean_error()
                mean_delay = me_0_1ms / 10.0  # 平均延时（ms）

                # 提取播放音轨数据
                for item in offset_data:
                    record_keyon_raw = item.get('record_keyon')
                    replay_keyon_raw = item.get('replay_keyon')  # 播放时间
                    key_id = item.get('key_id')
                    record_index = item.get('record_index')
                    replay_index = item.get('replay_index')
                    record_velocity = item.get('record_velocity')
                    replay_velocity = item.get('replay_velocity')
                    velocity_diff = item.get('velocity_diff')
                    relative_delay = item.get('relative_delay', 0)

                    # 类型检查
                    record_keyon_is_valid = isinstance(record_keyon_raw, (int, float, np.integer, np.floating))
                    replay_keyon_is_valid = isinstance(replay_keyon_raw, (int, float, np.integer, np.floating))

                    if not record_keyon_is_valid or not replay_keyon_is_valid:
                        continue

                    # 转换为ms单位
                    time_ms = record_keyon_raw / 10.0  # X轴：录制时间
                    replay_time_ms = replay_keyon_raw / 10.0  # 播放时间

                    # 计算相对延时（绝对延时 - 平均延时）
                    relative_delay_ms = (replay_time_ms - time_ms) - mean_delay

                    # 如果需要时间轴偏移，使用偏移后的播放时间轴
                    if apply_time_offset:
                        time_ms = replay_time_ms - mean_delay  # 播放时间 - 平均延时
                        y_value = relative_delay_ms  # Y轴：相对延时
                    else:
                        time_ms = replay_time_ms  # X轴：播放时间
                        y_value = relative_delay_ms  # Y轴：相对延时

                    # 存储原始时间值（在修改time_ms之前）
                    original_record_time = record_keyon_raw / 10.0
                    customdata = [key_id, record_index, replay_index, algorithm_name, replay_time_ms - original_record_time, relative_delay, mean_delay, record_velocity, replay_velocity, velocity_diff, replay_time_ms, original_record_time]

                    all_relative_data.append((time_ms, y_value, customdata, descriptive_name, color))

            except Exception as e:
                logger.warning(f"⚠️ 处理算法 '{algorithm_name}' 的相对延时数据失败: {e}")

        return all_relative_data

    def _create_raw_delay_plot_for_algorithms(self, all_raw_data: List[Tuple[float, float, List, str, str]]) -> Any:
        """
        为多算法创建原始延时图表

        Args:
            all_raw_data: 所有原始延时数据

        Returns:
            Any: Plotly图表对象
        """
        

        raw_delay_fig = go.Figure()

        # 按算法分组数据
        algorithm_data = {}
        for time_ms, delay_ms, customdata, descriptive_name, color in all_raw_data:
            if descriptive_name not in algorithm_data:
                algorithm_data[descriptive_name] = {
                    'times': [], 'delays': [], 'customdata': [], 'color': color
                }
            algorithm_data[descriptive_name]['times'].append(time_ms)
            algorithm_data[descriptive_name]['delays'].append(delay_ms)
            algorithm_data[descriptive_name]['customdata'].append(customdata)

        # 添加每个算法的trace
        for descriptive_name, data in algorithm_data.items():
            if data['times'] and data['delays']:
                # 确保数据按时间排序
                sorted_indices = sorted(range(len(data['times'])), key=lambda i: data['times'][i])
                sorted_times = [data['times'][i] for i in sorted_indices]
                sorted_delays = [data['delays'][i] for i in sorted_indices]
                sorted_customdata = [data['customdata'][i] for i in sorted_indices]

                raw_delay_fig.add_trace(go.Scatter(
                    x=sorted_times,
                    y=sorted_delays,
                    mode='markers+lines',
                    name=f'{descriptive_name} (相对延时)',
                    marker=dict(
                        size=4,
                        color=data['color'],
                        symbol='circle'  # 实心圆点
                    ),
                    line=dict(color=data['color'], width=1, dash='dot'),
                    hovertemplate='<b>算法</b>: ' + descriptive_name + '<br>' +
                                 '<b>播放时间</b>: %{x:.2f}ms<br>' +
                                 '<b>录制时间</b>: %{customdata[11]:.2f}ms<br>' +
                                 '<b>相对延时</b>: %{y:.2f}ms<br>' +
                                 '<b>平均延时</b>: %{customdata[6]:.2f}ms<br>' +
                                 '<b>录制锤速</b>: %{customdata[7]}<br>' +
                                 '<b>播放锤速</b>: %{customdata[8]}<br>' +
                                 '<b>锤速差值</b>: %{customdata[9]}<br>' +
                                 '<b>按键ID</b>: %{customdata[0]}<br>' +
                                 '<extra></extra>',
                    customdata=sorted_customdata
                ))

        # 配置布局
        raw_delay_fig.update_layout(
            xaxis_title='播放时间 (ms)',
            yaxis_title='相对延时 (ms)',
            showlegend=True,
            template='plotly_white',
            height=400,
            hovermode='closest',
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.02,
                xanchor='left',
                x=0.0,
                bgcolor='rgba(255, 255, 255, 0.9)',
                bordercolor='gray',
                borderwidth=1
            ),
            margin=dict(t=100, b=60, l=60, r=60)
        )

        return raw_delay_fig

    def _process_all_algorithms_data(self, ready_algorithms: List[AlgorithmDataset], colors: List[str]) -> Tuple[Any, List[Tuple[Dict[str, Any], str]]]:
        """
        处理所有算法的数据并创建相对延时图的traces

        Args:
            ready_algorithms: 就绪的算法列表
            colors: 颜色列表

        Returns:
            Tuple[Any, List[Tuple[Dict[str, Any], str]]]: (图表对象, 算法结果列表)
        """
        
        fig = go.Figure()

        all_delays = []
        algorithm_results = []

        for alg_idx, algorithm in enumerate(ready_algorithms):
            logger.info(f"[DEBUG] 处理算法 {alg_idx}: {algorithm.metadata.display_name}")
            algorithm_data = self._process_single_algorithm_data(algorithm)
            if algorithm_data is None:
                logger.warning(f"[DEBUG] 算法 {algorithm.metadata.display_name} 返回None，跳过")
                continue

            logger.info(f"[DEBUG] 算法 {algorithm.metadata.display_name} 返回数据: relative_delays_ms长度={len(algorithm_data.get('relative_delays_ms', []))}")

            # 添加算法实例引用（用于后续参考线计算）
            algorithm_data['algorithm_instance'] = algorithm

            color = colors[alg_idx % len(colors)]

            # 创建相对延时图的trace
            logger.info(f"[DEBUG] 为算法 {algorithm.metadata.display_name} 创建traces")
            self._create_relative_delay_traces(fig, algorithm_data, color)

            # 添加参考线
            self._add_algorithm_reference_lines(fig, algorithm_data, color)

            # 收集数据用于统计
            relative_delays = algorithm_data.get('relative_delays_ms', [])
            all_delays.extend(relative_delays)
            algorithm_results.append((algorithm_data, color))

            logger.info(f"[DEBUG] 算法 {algorithm.metadata.display_name} 处理完成，添加了 {len(relative_delays)} 个数据点")

        return fig, algorithm_results

    def _create_multi_algorithm_relative_plot(self, ready_algorithms: List[AlgorithmDataset], colors: List[str], apply_time_offset: bool = False) -> Any:
        """
        创建多算法相对延时图

        Args:
            ready_algorithms: 就绪的算法列表
            colors: 颜色列表
            apply_time_offset: 是否应用时间轴偏移

        Returns:
            Any: 相对延时图表对象
        """
        all_relative_data = self._collect_all_relative_delay_data(ready_algorithms, colors, apply_time_offset)
        return self._create_raw_delay_plot_for_algorithms(all_relative_data)

    def generate_multi_algorithm_delay_time_series_plot(
        self,
        algorithms: List[AlgorithmDataset]
    ) -> Any:
        """
        生成多算法延时时间序列图（两张相对延时图：播放时间轴对比）

        Args:
            algorithms: 激活的算法数据集列表

        Returns:
            Dict[str, Any]: 包含上方相对延时图和下方相对延时图的字典
        """
        if not algorithms:
            return self._create_empty_plot("没有激活的算法")

        try:
            # 1. 过滤就绪的算法
            ready_algorithms = self._filter_ready_algorithms(algorithms)
            if not ready_algorithms:
                logger.warning("没有就绪的算法，无法生成多算法延时时间序列图")
                return self._create_empty_plot("没有就绪的算法")

            # 2. 检查是否应该生成图表
            should_generate, reason = self._should_generate_time_series_plot(ready_algorithms)
            if not should_generate:
                logger.info(f"跳过延时时间序列图生成: {reason}")
                return self._create_empty_plot(reason)

            logger.info(f"开始生成多算法延时时间序列图，共 {len(ready_algorithms)} 个算法")

            # 3. 准备颜色
            colors = self._prepare_algorithm_colors()

            # 4. 处理所有算法数据并创建相对延时图
            fig, algorithm_results = self._process_all_algorithms_data(ready_algorithms, colors)

            # 检查是否有实际的数据用于绘图
            has_data = any(len(trace.y) > 0 for trace in fig.data) if fig.data else False
            logger.info(f"[DEBUG] has_data检查: fig.data存在={fig.data is not None}, traces数量={len(fig.data) if fig.data else 0}, has_data={has_data}")

            if not has_data:
                logger.warning("没有有效的时间序列数据，无法生成图表")
                # 记录更多调试信息
                for i, alg in enumerate(ready_algorithms):
                    logger.warning(f"  算法 {i}: {alg.metadata.display_name}")
                return self._create_empty_plot("没有有效的时间序列数据")

            # 5. 配置相对延时图的图注
            fig.update_layout(
                title='相对延时时间序列图（播放时间轴）',
                height=500,
                showlegend=True,
                legend=dict(
                    orientation='h',
                    yanchor='bottom',
                    y=1.02,
                    xanchor='left',
                    x=0.0,
                    bgcolor='rgba(255, 255, 255, 0.9)',
                    bordercolor='gray',
                    borderwidth=1,
                    title='算法图例'
                ),
                template='plotly_white',
                hovermode='closest'
            )

            # 6. 创建上方相对延时图（播放时间轴）
            raw_delay_plot = self._create_multi_algorithm_relative_plot(ready_algorithms, colors, apply_time_offset=False)
            if raw_delay_plot:
                raw_delay_plot.update_layout(
                    title='相对延时时间序列图（播放时间轴）',
                    height=500,
                    showlegend=True,
                    legend=dict(
                        orientation='h',
                        yanchor='bottom',
                        y=1.02,
                        xanchor='left',
                        x=0.0,
                        bgcolor='rgba(255, 255, 255, 0.9)',
                        bordercolor='gray',
                        borderwidth=1,
                        title='算法图例'
                    ),
                    template='plotly_white',
                    hovermode='closest'
                )

            return {
                'raw_delay_plot': raw_delay_plot,
                'relative_delay_plot': fig
            }

        except Exception as e:
            return self._handle_generation_error(e, "多算法延时时间序列图", return_dict=True)

    def _configure_unified_waterfall_layout(self, fig: go.Figure, all_bars_by_algorithm: List[Dict], is_multi_file: bool) -> None:
        """
        配置统一的瀑布图布局，包括标题、轴标签、图例和动态高度调整。

        Args:
            fig: Plotly图形对象
            all_bars_by_algorithm: 按算法分组的所有条形数据
            is_multi_file: 是否多文件模式
        """
        # 计算动态高度
        if is_multi_file:
            num_files = len(all_bars_by_algorithm)
            # 多文件模式：每个文件分配更多高度
            base_height_per_file = 600
            total_height = max(800, base_height_per_file * num_files)
        else:
            # 单文件模式：固定高度
            total_height = 800

        # 计算y轴范围（考虑多文件偏移）
        if is_multi_file:
            num_files = len(all_bars_by_algorithm)
            max_y_offset = (num_files - 1) * 100  # 每个文件偏移100
            y_min = 0.5
            y_max = 89.5 + max_y_offset + 1  # 留出一些余量

            # 为多文件创建合适的刻度
            tick_vals = []
            tick_texts = []
            for file_idx in range(num_files):
                base_offset = file_idx * 100
                for key_id in range(21, 109, 12):  # 每12个键显示一个刻度
                    tick_vals.append(key_id + base_offset)
                    if file_idx == 0:
                        tick_texts.append(str(key_id))
                    else:
                        tick_texts.append(f"{key_id}({file_idx+1})")

            y_axis_config = dict(
                tickmode='array',
                tickvals=tick_vals,
                ticktext=tick_texts,
                range=[y_min, y_max],
                autorange=False
            )
        else:
            # 单文件模式：标准钢琴键范围
            y_axis_config = dict(
                tickmode='array',
                tickvals=list(range(1, 89)),
                range=[0.5, 89.5],
                autorange=False
            )

        # 配置布局
        fig.update_layout(
            title='瀑布图 - 钢琴按键事件时序可视化',
            xaxis_title='时间 (ms)',
            yaxis_title='按键ID' + (' (多文件偏移)' if is_multi_file else ''),
            yaxis=y_axis_config,
            height=total_height,
            showlegend=True,
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.02,
                xanchor='left',
                x=0.0,
                bgcolor='rgba(255, 255, 255, 0.9)',
                bordercolor='gray',
                borderwidth=1
            ),
            template='plotly_white',
            hovermode='closest',
            margin=dict(l=80, r=60, t=100, b=80)
        )
