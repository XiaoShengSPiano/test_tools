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
    
    def __init__(self, data_filter=None):
        """
        初始化多算法图表生成器
        
        Args:
            data_filter: 数据过滤器实例（可选）
        """
        self.data_filter = data_filter
        
        # 使用全局颜色方案
        self.COLORS = ALGORITHM_COLOR_PALETTE
        
        logger.info("MultiAlgorithmPlotGenerator初始化完成")
    
    def generate_unified_waterfall_plot(
        self,
        backend,                        # 后端实例，用于获取全局平均延时
        analyzers: List[Any],           # 分析器列表（单算法时1个，多算法时多个）
        algorithm_names: List[str],     # 算法名称列表
        is_multi_algorithm: bool,       # 是否多算法模式
        time_filter=None,
        key_filter=None
    ) -> Any:
        """
        生成统一的瀑布图（支持单算法和多算法模式）
        
        单算法模式：analyzers包含1个分析器
        多算法模式：analyzers包含多个分析器
        
        Args:
            analyzers: 分析器列表
            algorithm_names: 算法名称列表
            is_multi_algorithm: 是否多算法模式
            time_filter: 时间过滤器
            key_filter: 按键过滤器
            
        Returns:
            go.Figure: Plotly图表对象
        """
        if not analyzers:
            logger.warning("没有分析器，无法生成瀑布图")
            return self._create_empty_plot("没有分析器")

        try:
            mode_str = "多算法" if is_multi_algorithm else "单算法"
            logger.info(f"开始生成瀑布图，模式: {mode_str}，共 {len(analyzers)} 个分析器")

            # 为多算法分配y_offset范围（确保明确区分）
            if is_multi_algorithm:
                algorithm_y_range = 100  # 每个算法分配的y轴范围
            else:
                algorithm_y_range = 0  # 单算法不需要偏移

            # 获取平均延时数据（参考 grade_detail_callbacks.py 的逻辑）
            avg_delay_ms = 0.0
            try:
                if is_multi_algorithm and algorithm_names and algorithm_names[0] != 'single':
                    # 多算法模式，使用第一个算法的平均延时
                    active_algorithms = backend.get_active_algorithms() if hasattr(backend, 'get_active_algorithms') else []
                    target_algorithm = next((alg for alg in active_algorithms if alg.metadata.algorithm_name == algorithm_names[0]), None)
                    if target_algorithm and target_algorithm.analyzer and hasattr(target_algorithm.analyzer, 'get_global_average_delay'):
                        avg_delay_0_1ms = target_algorithm.analyzer.get_global_average_delay()
                        avg_delay_ms = avg_delay_0_1ms / 10.0
                else:
                    # 单算法模式
                    avg_delay_0_1ms = backend.get_global_average_delay()
                    avg_delay_ms = avg_delay_0_1ms / 10.0
                logger.info(f"使用平均延时: {avg_delay_ms:.2f}ms")
            except Exception as e:
                logger.warning(f"获取平均延时失败: {e}，使用默认值0.0ms")
            
            # 收集所有数据点用于全局归一化
            all_values = []
            all_bars_by_algorithm = []
            
            # 处理每个分析器
            for alg_idx, (analyzer, algorithm_name) in enumerate(zip(analyzers, algorithm_names)):
                if not analyzer:
                    logger.warning(f"分析器 '{algorithm_name}' 为空，跳过")
                    continue
                
                logger.info(f"处理分析器 '{algorithm_name}': 生成包含所有数据的瀑布图")

                # 计算当前算法的y_offset
                current_y_offset = alg_idx * algorithm_y_range if is_multi_algorithm else 0

                # 收集当前分析器的完整数据：匹配对 + 丢锤 + 多锤
                algorithm_bars = self._collect_algorithm_comprehensive_data(
                    analyzer, current_y_offset, algorithm_name, alg_idx, avg_delay_ms
                )

                # 注意：丢锤和多锤数据不应该被过滤器过滤，应该始终显示
                # 过滤器只应该影响匹配对数据的显示，但这里我们选择显示所有数据

                # 收集力度值用于全局颜色归一化
                for bar in algorithm_bars:
                    all_values.append(bar.get('velocity', 0.5))
                
                all_bars_by_algorithm.append({
                    'analyzer': analyzer,
                    'bars': algorithm_bars,
                    'algorithm_name': algorithm_name,
                    'y_offset': current_y_offset
                })
            
            if not all_bars_by_algorithm:
                logger.warning("没有有效的数据点，无法生成瀑布图")
                return self._create_empty_plot("没有有效的数据点")
            
            # 全局归一化力度值（用于颜色映射）
            if all_values:
                vmin = min(all_values)
                vmax = max(all_values)
            else:
                vmin, vmax = 0, 1
            
            # 使用colormap
            import matplotlib.pyplot as plt
            cmap = plt.colormaps['tab20b']
            norm = lambda v: (v - vmin) / (vmax - vmin) if vmax > vmin else 0.5
            
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
                    # 计算颜色
                    velocity = bar.get('velocity', 0.5)
                    color = 'rgba' + str(tuple(int(255*x) for x in cmap(norm(velocity))[:3]) + (0.9,))

                    # 创建trace名称
                    data_type = bar.get('data_type', '')
                    if data_type == 'drop_hammer':
                        trace_name = f"{algorithm_name} - 丢锤"
                    elif data_type == 'multi_hammer':
                        trace_name = f"{algorithm_name} - 多锤"
                    else:
                        trace_name = f"{algorithm_name} - {bar['label']}"
                    
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
                            bar.get('raw_velocity', 0),
                            bar.get('label', 'unknown'),
                            bar.get('source_index', 0),
                            algorithm_name
                        ]]
                    ))
            
            # 配置图表布局
            self._configure_unified_waterfall_layout(fig, all_bars_by_algorithm, is_multi_algorithm)

            logger.info(f"瀑布图生成成功: 总计 {total_bars} 个bars (匹配对: {matched_bars}, 丢锤: {drop_hammer_bars}, 多锤: {multi_hammer_bars})")
            return fig

        except Exception as e:
            logger.error(f"生成瀑布图失败: {e}")
            logger.error(traceback.format_exc())
            return self._create_empty_plot(f"生成瀑布图失败: {str(e)}")

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
        logger.info(f"匹配对数据: {len(matched_bars)} 个bars")

        # 2. 收集丢锤数据
        drop_hammer_bars = self._collect_drop_hammer_data(analyzer, y_offset, algorithm_name)
        algorithm_bars.extend(drop_hammer_bars)
        logger.info(f"丢锤数据: {len(drop_hammer_bars)} 个bars")

        # 3. 收集多锤数据
        multi_hammer_bars = self._collect_multi_hammer_data(analyzer, y_offset, algorithm_name)
        algorithm_bars.extend(multi_hammer_bars)
        logger.info(f"多锤数据: {len(multi_hammer_bars)} 个bars")

        total_bars = len(algorithm_bars)
        logger.info(f"算法 '{algorithm_name}' 数据收集完成: 总计 {total_bars} 个瀑布图条形")

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
        bars = []
        drop_hammers = getattr(analyzer, 'drop_hammers', [])
        initial_valid_record_data = getattr(analyzer, 'initial_valid_record_data', [])

        if not drop_hammers:
            logger.info("没有丢锤数据")
            return bars

        logger.info(f"开始收集丢锤数据: {len(drop_hammers)} 个")

        for idx, error_note in enumerate(drop_hammers):
            try:
                # 获取音符索引
                note_index = self._get_error_note_index(error_note)

                # 验证索引并获取note对象
                if not self._is_valid_index(note_index, len(initial_valid_record_data)):
                    continue

                note = initial_valid_record_data[note_index] or self._create_default_note(error_note, note_index)

                # 只处理有after_touch数据的note
                if hasattr(note, 'after_touch') and note.after_touch is not None and hasattr(note.after_touch, 'index') and len(note.after_touch.index) > 0:
                    bars.extend(self._extract_note_bars_for_multi(
                        note, 'record', y_offset, 0.1, algorithm_name,
                        "失败", note_index, 0.0, 0.0, 'drop_hammer'
                    ))

                    # 为丢锤数据创建悬停信息
                    for bar in bars[-1:]:  # 只处理刚添加的bar
                        # 丢锤数据：录制存在但播放缺失
                        bar['text'] = '<b>丢锤错误 (录制数据):</b><br>' + \
                                     f'类型: record<br>' + \
                                     f'键位: {getattr(note, "id", "N/A")}<br>' + \
                                     f'锤速: {getattr(note, "hammers", ["N/A"])[0] if hasattr(note, "hammers") and note.hammers else "N/A"}<br>' + \
                                     f'等级: 失败 (丢锤)<br>' + \
                                     f'索引: {note_index}<br>' + \
                                     f'按键按下: {bar["t_on"]/10:.2f}ms<br>' + \
                                     f'按键释放: {bar["t_off"]/10:.2f}ms<br>' + \
                                     f'错误类型: 丢锤 (播放数据缺失)<br>'

                    logger.info(f"丢锤 #{idx} 处理完成")
                else:
                    logger.warning(f"丢锤 #{idx} 缺少after_touch数据，跳过")

            except Exception as e:
                logger.error(f"处理丢锤 #{idx} 失败: {e}")
                continue

        logger.info(f"丢锤数据收集完成: {len(bars)} 个bars")
        return bars

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
        bars = []
        multi_hammers = getattr(analyzer, 'multi_hammers', [])
        initial_valid_replay_data = getattr(analyzer, 'initial_valid_replay_data', [])

        if not multi_hammers:
            logger.info("没有多锤数据")
            return bars

        logger.info(f"🔨 开始收集多锤数据: {len(multi_hammers)} 个")

        for idx, error_note in enumerate(multi_hammers):
            try:
                # 获取音符索引
                note_index = self._get_error_note_index(error_note)

                # 验证索引并获取note对象
                if not self._is_valid_index(note_index, len(initial_valid_replay_data)):
                    continue

                note = initial_valid_replay_data[note_index] or self._create_default_note(error_note, note_index)

                # 只处理有after_touch数据的note
                if hasattr(note, 'after_touch') and note.after_touch is not None and hasattr(note.after_touch, 'index') and len(note.after_touch.index) > 0:
                    bars.extend(self._extract_note_bars_for_multi(
                        note, 'replay', y_offset, 0.1, algorithm_name,
                        "失败", note_index, 0.0, 0.0, 'multi_hammer'
                    ))

                    # 为多锤数据创建悬停信息
                    for bar in bars[-1:]:  # 只处理刚添加的bar
                        # 多锤数据：播放存在但录制缺失
                        bar['text'] = '<b>多锤错误 (播放数据):</b><br>' + \
                                     f'类型: replay<br>' + \
                                     f'键位: {getattr(note, "id", "N/A")}<br>' + \
                                     f'锤速: {getattr(note, "hammers", ["N/A"])[0] if hasattr(note, "hammers") and note.hammers else "N/A"}<br>' + \
                                     f'等级: 失败 (多锤)<br>' + \
                                     f'索引: {note_index}<br>' + \
                                     f'按键按下: {bar["t_on"]/10:.2f}ms<br>' + \
                                     f'按键释放: {bar["t_off"]/10:.2f}ms<br>' + \
                                     f'错误类型: 多锤 (录制数据缺失)<br>'

                    logger.info(f"多锤 #{idx} 处理完成")
                else:
                    logger.warning(f"多锤 #{idx} 缺少after_touch数据，跳过")

            except Exception as e:
                logger.error(f"处理多锤 #{idx} 失败: {e}")
                continue

        logger.info(f"多锤数据收集完成: {len(bars)} 个bars")
        return bars

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
            # 计算延时
            record_keyon = self._calculate_note_keyon_time(record_note)
            replay_keyon = self._calculate_note_keyon_time(replay_note)
            delay_ms = (replay_keyon - record_keyon) / 10.0
            relative_delay_ms = delay_ms - avg_delay_ms

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

    def _get_error_note_index(self, error_note) -> int:
        """
        从错误note中获取音符索引
        """
        note_index = error_note.global_index if hasattr(error_note, 'global_index') and error_note.global_index >= 0 else None
        if note_index is None and hasattr(error_note, 'infos') and error_note.infos is not None and len(error_note.infos) > 0:
            note_index = error_note.infos[0].index
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
                replay_velocity = replay_info.get('raw_velocity', 'N/A')
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
                logger.debug(f"合并完成 - 最终文本长度: {len(merged_text)}, 包含播放数据: {'播放数据:' in merged_text}")

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

    def _calculate_note_keyon_time(self, note) -> float:
        """
        计算音符的按键开始时间

        Args:
            note: Note对象

        Returns:
            float: keyon时间（0.1ms单位）
        """
        try:
            if hasattr(note, 'after_touch') and note.after_touch is not None and hasattr(note.after_touch, 'index') and len(note.after_touch.index) > 0:
                return note.after_touch.index[0] + getattr(note, 'offset', 0)
            elif hasattr(note, 'hammers') and note.hammers is not None and hasattr(note.hammers, 'index') and len(note.hammers.index) > 0:
                # 如果没有after_touch，使用第一个锤子的时间作为keyon
                return note.hammers.index[0] + getattr(note, 'offset', 0)
            else:
                return 0.0
        except (IndexError, AttributeError, TypeError):
            return 0.0

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
        bars = []
        if not note:
            logger.warning(f"⚠️ _extract_note_bars_for_multi: note为空, label={label}, data_type={data_type}")
            return bars
        
        if not hasattr(note, 'hammers'):
            logger.warning(f"⚠️ _extract_note_bars_for_multi: note没有hammers属性, key_id={getattr(note, 'id', 'N/A')}, label={label}, data_type={data_type}")
            return bars
        
        if note.hammers is None:
            logger.warning(f"⚠️ _extract_note_bars_for_multi: note.hammers为None, key_id={getattr(note, 'id', 'N/A')}, label={label}, data_type={data_type}")
            return bars

        # 力度值将在每个锤子的循环中单独处理

        # 为每个note创建一个基于after_touch事件的bar
        bars = []
        key_id = getattr(note, 'id', 1)

        # 计算基于after_touch的事件时间
        try:
            if hasattr(note, 'after_touch') and note.after_touch is not None and len(note.after_touch) > 0 and hasattr(note.after_touch, 'index') and len(note.after_touch.index) > 0:
                # 使用after_touch的开始和结束时间
                key_on_time = note.after_touch.index[0] + getattr(note, 'offset', 0)
                key_off_time = note.after_touch.index[-1] + getattr(note, 'offset', 0)
                logger.info(f"🔧 使用after_touch创建bar: key_id={key_id}, 时间范围=[{key_on_time/10:.1f}, {key_off_time/10:.1f}]ms")
            else:
                logger.warning(f"⚠️ note缺少after_touch数据: key_id={key_id}")
                return bars

            # 应用Y轴偏移
            actual_key_id = key_id + y_offset
            if label == 'replay':
                actual_key_id += 0.2  # 播放数据稍微偏移

            # 使用第一个锤击的力度作为代表力度
            hammer_velocity = "N/A"
            hammer_velocity_norm = 0.5
            if hasattr(note, 'hammers') and note.hammers is not None and hasattr(note.hammers, 'values') and len(note.hammers.values) > 0:
                hammer_velocity = note.hammers.values[0]  # 使用第一个锤击的力度
                try:
                    hammer_velocity_norm = float(hammer_velocity) / 127.0
                except (ValueError, TypeError):
                    hammer_velocity_norm = 0.5

            # 调试：检查坐标值是否在合理范围内
            logger.info(f"📍 绘制数据点: key_id={key_id}, y_offset={y_offset}, label={label}, actual_key_id={actual_key_id:.2f}, 时间范围=[{key_on_time/10:.1f}, {key_off_time/10:.1f}]ms")

            # 将match_index转换为整数作为source_index
            source_index = 0
            try:
                if isinstance(match_index, str) and match_index != "N/A":
                    source_index = int(match_index)
                elif isinstance(match_index, int):
                    source_index = match_index
            except (ValueError, TypeError):
                source_index = 0

            bar = {
                't_on': float(key_on_time),
                't_off': float(key_off_time),
                'key_id': actual_key_id,           # 用于绘图的实际键位ID（包含偏移）
                'original_key_id': key_id,         # 原始整数键位ID（用于显示）
                'velocity': hammer_velocity_norm,  # 标准化力度 (0.0-1.0) 用于颜色映射
                'raw_velocity': hammer_velocity,   # 原始力度 用于显示
                'color_intensity': color_intensity,
                'algorithm_name': algorithm_name,
                'label': label,
                'data_type': data_type,
                'hammer_index': 0,                # 固定为0，因为只有一个bar
                'grade_name': grade_name,         # 评价等级
                'match_index': match_index,       # 匹配系统评级时的索引
                'source_index': source_index,     # 音符在原始数据数组中的索引（用于点击处理）
                'delay_ms': delay_ms,             # 延时（毫秒）
                'relative_delay_ms': relative_delay_ms,  # 相对延时（延时 - 平均延时）
                'first_hammer_time': key_on_time  # 第一个锤子的锤击时间
            }

            # 为bar生成hover文本
            bar_type_suffix = ""
            if data_type == "drop_hammer":
                bar_type_suffix = " (丢锤)"
            elif data_type == "multi_hammer":
                bar_type_suffix = " (多锤)"

            # 根据数据类型构建不同的hover文本
            if label == 'record':
                # 录制数据不显示延时信息
                bar['text'] = (
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
                # 播放数据显示延时信息（会在合并时添加平均延时）
                bar['text'] = (
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

            bars.append(bar)
            logger.info(f"✅ 为 {data_type} 成功创建了 1 个bar (基于after_touch事件)")

        except (TypeError, ValueError, AttributeError) as e:
            logger.warning(f"🚫 创建 {data_type} bar失败: {e}")
            return bars

        return bars
    
    def _apply_key_filter(self, data: List, key_filter: set) -> List:
        """应用按键过滤"""
        if not key_filter:
            return data
        return [note for note in data if note.keyId in key_filter]
    
    def _hex_to_rgba(self, hex_color: str, alpha: float) -> str:
        """
        将十六进制颜色转换为rgba格式
        
        Args:
            hex_color: 十六进制颜色（如 '#1f77b4'）
            alpha: 透明度（0-1）
            
        Returns:
            str: rgba颜色字符串（如 'rgba(31, 119, 180, 0.8)'）
        """
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return f'rgba({r}, {g}, {b}, {alpha})'
    
    def generate_multi_algorithm_offset_alignment_plot(
        self,
        algorithms: List[AlgorithmDataset]
    ) -> List[Dict[str, Any]]:
        """
        生成多算法偏移对齐分析图（并排柱状图，不同颜色）
        
        返回5个独立的图表，每个图表显示一个指标：
        - 中位数偏移
        - 均值偏移
        - 标准差
        - 方差
        - 相对延时
        
        Args:
            algorithms: 激活的算法数据集列表
            
        Returns:
            List[Dict[str, Any]]: 包含图表信息的字典列表
            每个字典包含: {'title': str, 'figure': go.Figure}
        """
        if not algorithms:
            logger.debug("ℹ️ 没有激活的算法，跳过多算法偏移对齐分析图生成")
            # 返回包含5个空图表的列表
            empty_fig = self._create_empty_plot("没有激活的算法")
            return [
                {'title': '中位数偏移', 'figure': empty_fig},
                {'title': '均值偏移', 'figure': empty_fig},
                {'title': '标准差', 'figure': empty_fig},
                {'title': '方差', 'figure': empty_fig},
                {'title': '相对延时', 'figure': empty_fig}
            ]
        
        try:
            # 过滤出就绪的算法
            ready_algorithms = [alg for alg in algorithms if alg.is_ready()]
            if not ready_algorithms:
                logger.warning("⚠️ 没有就绪的算法，无法生成多算法偏移对齐分析图")
                empty_fig = self._create_empty_plot("没有就绪的算法")
                return [
                    {'title': '中位数偏移', 'figure': empty_fig},
                    {'title': '均值偏移', 'figure': empty_fig},
                    {'title': '标准差', 'figure': empty_fig},
                    {'title': '方差', 'figure': empty_fig},
                    {'title': '相对延时', 'figure': empty_fig}
                ]
            
            logger.info(f"📊 开始生成多算法偏移对齐分析图，共 {len(ready_algorithms)} 个算法")
            
            # 为每个算法分配颜色（使用全局颜色方案）
            colors = ALGORITHM_COLOR_PALETTE
            
            # 收集所有算法的数据
            all_algorithms_data = []
            
            for alg_idx, algorithm in enumerate(ready_algorithms):
                algorithm_name = algorithm.metadata.algorithm_name
                
                if not algorithm.analyzer:
                    logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有分析器，跳过")
                    continue
                
                # 获取精确偏移对齐数据（误差 ≤ 50ms）
                try:
                    # 从analyzer获取精确偏移数据
                    offset_data = algorithm.analyzer.get_precision_offset_alignment_data()
                    
                    # 按按键ID分组并计算统计信息
                    from collections import defaultdict
                    
                    # 计算该算法的平均延时（用于计算相对延时）
                    me_0_1ms = algorithm.analyzer.get_mean_error() if hasattr(algorithm.analyzer, 'get_mean_error') else 0.0
                    mean_delay = me_0_1ms / 10.0  # 平均延时（ms，带符号）
                    
                    # 按按键ID分组有效匹配的偏移数据（只使用keyon_offset）
                    key_groups = defaultdict(list)
                    key_groups_relative = defaultdict(list)  # 用于存储相对延时
                    for item in offset_data:
                        key_id = item.get('key_id', 'N/A')
                        keyon_offset = item.get('keyon_offset', 0)  # 原始延时（0.1ms单位，带符号）
                        keyon_offset_abs = abs(keyon_offset)  # 绝对值用于其他统计
                        keyon_offset_ms = keyon_offset / 10.0  # 转换为ms
                        relative_delay = keyon_offset_ms - mean_delay  # 相对延时
                        key_groups[key_id].append(keyon_offset_abs)
                        key_groups_relative[key_id].append(relative_delay)
                    
                    # 提取数据
                    algorithm_key_ids = []
                    algorithm_median = []
                    algorithm_mean = []
                    algorithm_std = []
                    algorithm_variance = []
                    algorithm_relative_mean = []  # 相对延时的均值
                    
                    for key_id, offsets in key_groups.items():
                        if offsets:
                            try:
                                key_id_int = int(key_id)
                                algorithm_key_ids.append(key_id_int)
                                algorithm_median.append(np.median(offsets) / 10.0)  # 转换为ms
                                algorithm_mean.append(np.mean(offsets) / 10.0)  # 转换为ms
                                algorithm_std.append(np.std(offsets) / 10.0)  # 转换为ms
                                algorithm_variance.append(np.var(offsets) / 100.0)  # 转换为ms²
                                
                                # 计算相对延时的均值
                                if key_id in key_groups_relative:
                                    relative_delays = key_groups_relative[key_id]
                                    algorithm_relative_mean.append(np.mean(relative_delays))
                                else:
                                    algorithm_relative_mean.append(0.0)
                            except (ValueError, TypeError):
                                continue
                    
                    if algorithm_key_ids:
                        all_algorithms_data.append({
                            'name': algorithm_name,
                            'display_name': algorithm.metadata.display_name,  # 显示名称
                            'key_ids': algorithm_key_ids,
                            'median': algorithm_median,
                            'mean': algorithm_mean,
                            'std': algorithm_std,
                            'variance': algorithm_variance,
                            'relative_mean': algorithm_relative_mean,  # 相对延时的均值
                            'color': colors[alg_idx % len(colors)],
                            'analyzer': algorithm.analyzer
                        })
                except Exception as e:
                    logger.warning(f"⚠️ 获取算法 '{algorithm_name}' 的偏移对齐数据失败: {e}")
                    continue
            
            if not all_algorithms_data:
                logger.warning("⚠️ 没有有效的偏移对齐数据，无法生成柱状图")
                empty_fig = self._create_empty_plot("没有有效的偏移对齐数据")
                return [
                    {'title': '中位数偏移', 'figure': empty_fig},
                    {'title': '均值偏移', 'figure': empty_fig},
                    {'title': '标准差', 'figure': empty_fig},
                    {'title': '方差', 'figure': empty_fig},
                    {'title': '相对延时', 'figure': empty_fig}
                ]
            
            # 准备独立的图表列表
            figures_list = []
            
            # 定义5个指标的配置
            metrics = [
                ('中位数偏移', 'median', 'ms', 'median'),
                ('均值偏移', 'mean', 'ms', 'mean'),
                ('标准差', 'std', 'ms', 'std'),
                ('方差', 'variance', 'ms²', 'variance'),
                ('相对延时', 'relative_mean', 'ms', 'relative')
            ]
            
            # 计算x轴位置逻辑（grouped bar chart）
            # 获取所有键位的并集
            all_key_ids = set()
            for alg_data in all_algorithms_data:
                all_key_ids.update(alg_data['key_ids'])
            all_key_ids = sorted(list(all_key_ids))
            
            # 为每个算法计算x轴位置
            num_algorithms = len(all_algorithms_data)
            bar_width = 0.8 / num_algorithms
            
            min_key_id = max(1, min(all_key_ids)) if all_key_ids else 1
            max_key_id = max(all_key_ids) if all_key_ids else 90
            
            for metric_name, data_key, unit, legend_group_suffix in metrics:
                fig = go.Figure()
                
                for alg_idx, alg_data in enumerate(all_algorithms_data):
                    algorithm_name = alg_data['name']
                    display_name = alg_data.get('display_name', algorithm_name)
                    color = alg_data['color']
                    
                    # 准备数据
                    x_positions = []
                    y_values = []
                    
                    key_to_val = dict(zip(alg_data['key_ids'], alg_data[data_key]))
                    
                    for key_id in all_key_ids:
                        if key_id in alg_data['key_ids']:
                            x_positions.append(key_id + (alg_idx - num_algorithms / 2 + 0.5) * bar_width)
                            y_values.append(key_to_val[key_id])
                        # 如果没有数据则不添加
                    
                    if not x_positions:
                        continue
                        
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
                        legend='legend',  # 默认legend
                        legendgroup=algorithm_name, # 所有图表共用legendgroup，实现联动显示/隐藏
                        hovertemplate=f'算法: {display_name}<br>键位: %{{x:.0f}}<br>{metric_name}: %{{y:.2f}}{unit}<extra></extra>'
                    ))
                
                # 设置图表布局
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
                        bgcolor='rgba(255,255,255,0.8)', bordercolor='rgba(0,0,0,0.2)', borderwidth=1,
                        orientation='h', font=dict(size=11),
                        title_text=metric_name
                    ),
                    margin=dict(l=60, r=40, t=100, b=60),
                    height=500,  # 每个图表的独立高度
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font=dict(size=12)
                )
                
                figures_list.append({
                    'title': metric_name,
                    'figure': fig
                })
            
            logger.info(f"✅ 多算法偏移对齐分析图生成成功，共 {len(figures_list)} 个独立图表")
            return figures_list
            
        except Exception as e:
            logger.error(f"❌ 生成多算法偏移对齐分析图失败: {e}")
            
            logger.error(traceback.format_exc())
            empty_fig = self._create_empty_plot(f"生成失败: {str(e)}")
            return [
                {'title': '生成失败', 'figure': empty_fig}
            ]
    
    def export_multi_algorithm_delay_histogram_data_to_csv(self, algorithms: List[AlgorithmDataset], filename: str = None) -> Optional[List[str]]:
        """
        将多算法延时分布直方图的数据导出为CSV文件，按文件名分组分别存储

        Args:
            algorithms: 激活的算法数据集列表
            filename: 自定义文件名前缀，如果为None则自动生成

        Returns:
            List[str]: CSV文件路径列表，如果导出失败则返回None
        """
        try:
            import csv
            import os
            from datetime import datetime

            if not algorithms:
                logger.debug("ℹ️ 没有激活的算法，跳过导出")
                return None

            # 过滤出就绪的算法
            ready_algorithms = [alg for alg in algorithms if alg.is_ready()]
            if not ready_algorithms:
                logger.warning("⚠️ 没有就绪的算法，无法导出")
                return None

            # 按文件名分组收集数据
            csv_data_by_filename = {}

            for algorithm in ready_algorithms:
                algorithm_name = algorithm.metadata.algorithm_name
                display_name = algorithm.metadata.display_name
                filename_display = algorithm.metadata.filename

                if not algorithm.analyzer or not algorithm.analyzer.note_matcher:
                    logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有分析器，跳过")
                    continue

                try:
                    # 从analyzer获取精确偏移数据（误差 ≤ 50ms）
                    offset_data = algorithm.analyzer.get_precision_offset_alignment_data()

                    if not offset_data:
                        logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有匹配数据，跳过")
                        continue

                    # 获取matched_pairs以便查找按键ID
                    matched_pairs = algorithm.analyzer.get_matched_pairs() if hasattr(algorithm.analyzer, 'get_matched_pairs') else []
                    record_note_dict = {r_idx: r_note for r_idx, _, r_note, _ in matched_pairs} if matched_pairs else {}
                    replay_note_dict = {p_idx: p_note for _, p_idx, _, p_note in matched_pairs} if matched_pairs else {}

                    # 步骤1：提取原始延时数据（带符号的keyon_offset）
                    absolute_delays_ms = [item.get('keyon_offset', 0.0) / 10.0 for item in offset_data]

                    if not absolute_delays_ms:
                        logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有有效延时数据，跳过")
                        continue

                    # 步骤2：计算该算法的平均延时（用于计算相对延时）
                    n = len(absolute_delays_ms)
                    mean_delay_ms = sum(absolute_delays_ms) / n

                    # 初始化该文件名的列表（如果不存在）
                    if filename_display not in csv_data_by_filename:
                        csv_data_by_filename[filename_display] = []

                    # 为每个数据点创建记录
                    for i, item in enumerate(offset_data):
                        absolute_delay = absolute_delays_ms[i]
                        relative_delay = absolute_delay - mean_delay_ms

                        # 获取录制和播放按键ID
                        record_index = item.get('record_index', -1)
                        replay_index = item.get('replay_index', -1)
                        record_key_id = record_note_dict.get(record_index, None)
                        replay_key_id = replay_note_dict.get(replay_index, None)

                        record_key_id_value = record_key_id.id if record_key_id and hasattr(record_key_id, 'id') else item.get('key_id', 'N/A')
                        replay_key_id_value = replay_key_id.id if replay_key_id and hasattr(replay_key_id, 'id') else item.get('key_id', 'N/A')

                        csv_data_by_filename[filename_display].append({
                            '算法名称': algorithm_name,
                            '显示名称': display_name,
                            '录制索引': record_index,
                            '回放索引': replay_index,
                            '录制按键ID': record_key_id_value,
                            '回放按键ID': replay_key_id_value,
                            '录制按键时间(ms)': item.get('record_keyon', 0) / 10.0,
                            '回放按键时间(ms)': item.get('replay_keyon', 0) / 10.0,
                            '绝对延时(ms)': absolute_delay,
                            '算法平均延时(ms)': mean_delay_ms,
                            '相对延时(ms)': relative_delay
                        })

                except Exception as e:
                    logger.warning(f"⚠️ 处理算法 '{algorithm_name}' 时出错: {e}")
                    continue

            if not csv_data_by_filename:
                logger.warning("⚠️ 没有有效数据，无法导出")
                return None

            # 生成文件名前缀
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename_prefix = f"delay_histogram_data_{timestamp}"
            else:
                # 如果提供了自定义文件名，去掉扩展名作为前缀
                filename_prefix = filename.replace('.csv', '')

            # 创建输出目录
            output_dir = "exports"
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)

            # 写入多个CSV文件
            fieldnames = ['算法名称', '显示名称', '录制索引', '回放索引',
                         '录制按键ID', '回放按键ID',
                         '录制按键时间(ms)', '回放按键时间(ms)',
                         '绝对延时(ms)', '算法平均延时(ms)', '相对延时(ms)']

            exported_files = []
            total_records = 0

            for filename_key, csv_data in csv_data_by_filename.items():
                # 为每个文件名生成单独的CSV文件
                safe_filename = "".join(c for c in filename_key if c.isalnum() or c in (' ', '-', '_')).rstrip()
                csv_filename = f"{filename_prefix}_{safe_filename}.csv"
                filepath = os.path.join(output_dir, csv_filename)

                with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(csv_data)

                exported_files.append(filepath)
                total_records += len(csv_data)
                logger.info(f"✅ 文件 '{filename_key}' 的延时分布数据已导出到: {filepath}")
                logger.info(f"📊 导出 {len(csv_data)} 条记录")

            logger.info(f"✅ 共导出 {len(exported_files)} 个CSV文件，总计 {total_records} 条记录")
            return exported_files

        except Exception as e:
            logger.error(f"❌ 导出多算法延时分布数据失败: {e}")
            return None

    def export_multi_algorithm_pre_match_data_to_csv(self, algorithms: List[AlgorithmDataset], filename: str = None) -> Optional[List[str]]:
        """
        导出多算法匹配前的数据到CSV文件（测试功能）

        在按键匹配之前进行编号，为每个算法的录制和播放音符分别分配索引并导出CSV。

        Args:
            algorithms: 激活的算法数据集列表
            filename: 自定义文件名前缀，如果为None则自动生成

        Returns:
            List[str]: CSV文件路径列表，如果导出失败则返回None
        """
        try:
            import csv
            import os
            from datetime import datetime

            if not algorithms:
                logger.debug("ℹ️ 没有激活的算法，跳过导出")
                return None

            # 过滤出就绪的算法
            ready_algorithms = [alg for alg in algorithms if alg.is_ready()]
            if not ready_algorithms:
                logger.warning("⚠️ 没有就绪的算法，无法导出")
                return None

            # 生成文件名前缀
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename_prefix = f"pre_match_data_{timestamp}"
            else:
                # 如果提供了自定义文件名，去掉扩展名作为前缀
                filename_prefix = filename.replace('.csv', '')

            # 创建输出目录
            output_dir = "exports"
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)

            # 写入多个CSV文件
            fieldnames = ['算法名称', '显示名称', '录制索引', '回放索引',
                         '录制按键ID', '回放按键ID',
                         '录制按键时间(ms)', '回放按键时间(ms)']

            exported_files = []
            total_records = 0

            for algorithm in ready_algorithms:
                algorithm_name = algorithm.metadata.algorithm_name
                display_name = algorithm.metadata.display_name
                filename_display = algorithm.metadata.filename

                # 获取匹配前的数据（空数据过滤之后，按键匹配之前）
                initial_valid_record = algorithm.analyzer.get_initial_valid_record_data() if hasattr(algorithm.analyzer, 'get_initial_valid_record_data') else None
                initial_valid_replay = algorithm.analyzer.get_initial_valid_replay_data() if hasattr(algorithm.analyzer, 'get_initial_valid_replay_data') else None

                if not initial_valid_record or not initial_valid_replay:
                    logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有匹配前的数据，跳过")
                    continue

                # 为每个文件名生成单独的CSV文件
                safe_filename = "".join(c for c in filename_display if c.isalnum() or c in (' ', '-', '_')).rstrip()
                csv_filename = f"{filename_prefix}_{safe_filename}.csv"
                filepath = os.path.join(output_dir, csv_filename)

                csv_data = []

                # 获取录制和播放数据的数量
                record_count = len(initial_valid_record)
                replay_count = len(initial_valid_replay)

                # 使用较大的数量作为行数
                max_count = max(record_count, replay_count)

                # 并排编号录制和播放索引
                for i in range(max_count):
                    # 录制数据
                    if i < record_count:
                        record_note = initial_valid_record[i]
                        record_index = i  # 录制索引
                        record_key_id = getattr(record_note, 'id', 'N/A')

                        # 获取录制音符的时间信息
                        record_keyon_time = 0
                        if hasattr(record_note, 'after_touch') and record_note.after_touch is not None and not record_note.after_touch.empty:
                            record_keyon_time = record_note.after_touch.index[0] + record_note.offset
                        elif hasattr(record_note, 'hammers') and record_note.hammers is not None and not record_note.hammers.empty:
                            record_keyon_time = record_note.hammers.index[0] + record_note.offset
                    else:
                        record_index = -1  # 没有录制数据
                        record_key_id = 'N/A'
                        record_keyon_time = 0

                    # 播放数据
                    if i < replay_count:
                        replay_note = initial_valid_replay[i]
                        replay_index = i  # 播放索引
                        replay_key_id = getattr(replay_note, 'id', 'N/A')

                        # 获取播放音符的时间信息
                        replay_keyon_time = 0
                        if hasattr(replay_note, 'after_touch') and replay_note.after_touch is not None and not replay_note.after_touch.empty:
                            replay_keyon_time = replay_note.after_touch.index[0] + replay_note.offset
                        elif hasattr(replay_note, 'hammers') and replay_note.hammers is not None and not replay_note.hammers.empty:
                            replay_keyon_time = replay_note.hammers.index[0] + replay_note.offset
                    else:
                        replay_index = -1  # 没有播放数据
                        replay_key_id = 'N/A'
                        replay_keyon_time = 0

                    csv_data.append({
                        '算法名称': algorithm_name,
                        '显示名称': display_name,
                        '录制索引': record_index,
                        '回放索引': replay_index,
                        '录制按键ID': record_key_id,
                        '回放按键ID': replay_key_id,
                        '录制按键时间(ms)': record_keyon_time / 10.0 if record_keyon_time else 0,
                        '回放按键时间(ms)': replay_keyon_time / 10.0 if replay_keyon_time else 0
                    })

                # 写入CSV文件
                with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(csv_data)

                exported_files.append(filepath)
                total_records += len(csv_data)
                logger.info(f"✅ 算法 '{algorithm_name}' 的匹配前数据已导出到: {filepath}")
                logger.info(f"📊 录制音符: {len(initial_valid_record)} 个, 播放音符: {len(initial_valid_replay)} 个")
                logger.info(f"📊 导出记录数: {len(csv_data)} 条")

            logger.info(f"✅ 共导出 {len(exported_files)} 个CSV文件，总计 {total_records} 条记录")
            return exported_files

        except Exception as e:
            logger.error(f"❌ 导出多算法匹配前数据失败: {e}")
            return None

    def generate_multi_algorithm_delay_histogram_plot(
        self,
        algorithms: List[AlgorithmDataset]
    ) -> Any:
        """
        生成多算法延时分布直方图（叠加显示，不同颜色，图例控制）

        为每个算法生成直方图和正态拟合曲线，使用不同颜色区分，叠加显示在同一图表中。

        数据筛选：只使用误差≤50ms的按键数据
        数据处理：
        - 只使用误差≤50ms的按键数据
        - 相对时延（原始时延 - 平均时延）用于分布图：消除整体偏移，更公平地比较稳定性
        - 均值偏移：显示原始延时的平均值，反映算法整体延时倾向
        - 方差：基于原始延时计算，反映绝对稳定性
        - 相对延时分布图均值接近0，标准差反映相对稳定性
        - 延时有正有负，反映相对于平均水平的偏差

        Args:
            algorithms: 激活的算法数据集列表

        Returns:
            go.Figure: Plotly图表对象
        """
        if not algorithms:
            logger.debug("ℹ️ 没有激活的算法，跳过多算法延时分布直方图生成")
            return self._create_empty_plot("没有激活的算法")
        
        try:
            # 过滤出就绪的算法
            ready_algorithms = [alg for alg in algorithms if alg.is_ready()]
            if not ready_algorithms:
                logger.warning("⚠️ 没有就绪的算法，无法生成多算法延时分布直方图")
                return self._create_empty_plot("没有就绪的算法")
            
            logger.info(f"📊 开始生成多算法延时分布直方图，共 {len(ready_algorithms)} 个算法")
            
            # 为每个算法分配颜色（使用全局颜色方案）
            colors = ALGORITHM_COLOR_PALETTE
            
            
            
            fig = go.Figure()
            
            # 收集所有算法的数据
            all_delays = []  # 用于确定全局范围

            for alg_idx, algorithm in enumerate(ready_algorithms):
                algorithm_name = algorithm.metadata.algorithm_name
                display_name = algorithm.metadata.display_name
                filename = algorithm.metadata.filename

                # 创建更具描述性的图注名称：算法名 (文件名)
                descriptive_name = f"{display_name} ({filename})"

                if not algorithm.analyzer or not algorithm.analyzer.note_matcher:
                    logger.warning(f"⚠️ 算法 '{descriptive_name}' 没有分析器或匹配器，跳过")
                    continue
                
                try:
                    # 从analyzer获取精确偏移数据（误差 ≤ 50ms）
                    offset_data = algorithm.analyzer.get_precision_offset_alignment_data()

                    if not offset_data:
                        logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有精确匹配数据（≤50ms），跳过")
                        continue

                    # 提取精确匹配的原始延时数据（带符号的keyon_offset）
                    absolute_delays_ms = [item.get('keyon_offset', 0.0) / 10.0 for item in offset_data]

                    if not absolute_delays_ms:
                        logger.warning(f"⚠️ 算法 '{algorithm_name}' 筛选后没有有效延时数据，跳过")
                        continue

                    # 步骤3：计算该算法的平均延时（均值偏移）
                    n = len(absolute_delays_ms)
                    mean_delay_ms = sum(absolute_delays_ms) / n

                    # 步骤4：计算相对延时（消除整体偏移，用于分布图）
                    # 相对延时 = 原始延时 - 平均延时
                    # 这样均值接近0，更适合评估相对稳定性
                    relative_delays_ms = [delay - mean_delay_ms for delay in absolute_delays_ms]

                    all_delays.extend(relative_delays_ms)

                    # 步骤5：计算统计量
                    # 均值偏移：使用原始延时的平均值，反映算法整体的延时倾向
                    mean_offset = mean_delay_ms

                    # 方差：使用原始延时的方差，反映绝对稳定性
                    if n > 1:
                        var_offset = sum((x - mean_delay_ms) ** 2 for x in absolute_delays_ms) / (n - 1)
                        std_offset = var_offset ** 0.5
                    else:
                        var_offset = 0.0
                        std_offset = 0.0

                    # 相对延时的统计量（用于正态拟合）
                    if n > 1:
                        var_relative = sum((x - 0) ** 2 for x in relative_delays_ms) / (n - 1)  # 相对均值=0
                        std_relative = var_relative ** 0.5
                    else:
                        std_relative = 0.0
                    
                    color = colors[alg_idx % len(colors)]
                    
                    # 添加直方图
                    fig.add_trace(go.Histogram(
                        x=relative_delays_ms,
                        histnorm='probability density',
                        name=f'{descriptive_name} - 延时分布',
                        marker_color=color,
                        opacity=0.85,  # 增加不透明度，使颜色更明显
                        marker_line_color=color,  # 添加边框颜色，使用相同颜色但更深的边框
                        marker_line_width=0.5,
                        legendgroup=descriptive_name,
                        showlegend=True
                    ))
                    
                    # 生成正态拟合曲线（基于相对延时，均值=0）
                    if std_relative > 0:
                        min_x = min(relative_delays_ms)
                        max_x = max(relative_delays_ms)
                        span = max(1e-6, 3 * std_relative)
                        x_start = min(-span, min_x)  # 相对均值=0
                        x_end = max(span, max_x)

                        num_pts = 200
                        step = (x_end - x_start) / (num_pts - 1) if num_pts > 1 else 1.0
                        xs = [x_start + i * step for i in range(num_pts)]
                        ys = [(1.0 / (std_relative * (2 * math.pi) ** 0.5)) *
                              math.exp(-0.5 * ((x - 0) / std_relative) ** 2)  # 均值=0
                              for x in xs]

                        # 添加正态拟合曲线
                        fig.add_trace(go.Scatter(
                            x=xs,
                            y=ys,
                            mode='lines',
                            name=f'{descriptive_name} - 正态拟合 (μ={mean_offset:.2f}ms, σ={std_offset:.2f}ms)',
                            line=dict(color=color, width=2),
                            legendgroup=descriptive_name,
                            showlegend=True
                        ))
                    
                except Exception as e:
                    logger.warning(f"⚠️ 获取算法 '{algorithm_name}' 的延时数据失败: {e}")
                    continue
            
            if not all_delays:
                logger.warning("⚠️ 没有有效的延时数据，无法生成直方图")
                return self._create_empty_plot("没有有效的延时数据")
            
            # 设置布局（删除title，因为UI区域已有标题）
            fig.update_layout(
                xaxis_title='相对延时 (ms)',
                yaxis_title='概率密度',
                bargap=0.05,
                plot_bgcolor='white',
                paper_bgcolor='white',
                font=dict(size=12),
                height=500,
                clickmode='event+select',  # 启用点击和选择事件
                legend=dict(
                    orientation='h',
                    yanchor='bottom',
                    y=1.05,  # 图注更靠上，给标题留出空间
                    xanchor='left',
                    x=0.0,  # 从最左边开始，避免挤压居中标题
                    bgcolor='rgba(255, 255, 255, 0.9)',
                    bordercolor='gray',
                    borderwidth=1
                ),
                margin=dict(t=100, b=60, l=60, r=60)  # 增加顶部边距，给图注和标题更多空间
            )
            
            logger.info(f"✅ 多算法延时分布直方图生成成功，共 {len(ready_algorithms)} 个算法")
            return fig
            
        except Exception as e:
            logger.error(f"❌ 生成多算法延时分布直方图失败: {e}")
            
            logger.error(traceback.format_exc())
            return self._create_empty_plot(f"生成失败: {str(e)}")
    
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
            selected_algorithm_names: 指定参与对比的算法名称列表，如果为None则使用所有激活算法

        Returns:
            go.Figure: Plotly图表对象
        """
        if not algorithms:
            logger.debug("没有激活的算法，跳过多算法按键与延时散点图生成")
            return self._create_empty_plot("没有激活的算法")
        
        try:
            # 首先根据 selected_algorithm_names 筛选算法（如果指定了的话）
            if selected_algorithm_names:
                filtered_algorithms = [alg for alg in algorithms if alg.metadata.algorithm_name in selected_algorithm_names]
                logger.info(f"根据用户选择筛选算法: {selected_algorithm_names} -> 找到 {len(filtered_algorithms)} 个匹配算法")
            else:
                filtered_algorithms = algorithms
                logger.info("未指定算法筛选，使用所有传入算法")

            # 过滤出激活且就绪的算法（确保只显示用户选择的算法）
            # 记录传入的算法状态，用于调试
            for alg in filtered_algorithms:
                logger.debug(f"算法 '{alg.metadata.algorithm_name}': is_active={alg.is_active}, is_ready={alg.is_ready()}")

            ready_algorithms = [alg for alg in filtered_algorithms if alg.is_active and alg.is_ready()]
            if not ready_algorithms:
                logger.warning("没有激活且就绪的算法，无法生成多算法按键与延时散点图")
                return self._create_empty_plot("没有激活的算法")
            
            logger.info(f"开始生成多算法按键与延时散点图，共 {len(ready_algorithms)} 个激活算法: {[alg.metadata.algorithm_name for alg in ready_algorithms]}")
            
            # 如果需要只显示公共按键，先计算交集
            common_keys = None
            if only_common_keys:
                key_sets = []
                for alg in ready_algorithms:
                    if alg.analyzer and alg.analyzer.note_matcher:
                        offset_data = alg.analyzer.note_matcher.get_precision_offset_alignment_data()
                        if offset_data:
                            keys = set(item.get('key_id') for item in offset_data if item.get('key_id') is not None)
                            key_sets.append(keys)
                
                if key_sets:
                    common_keys = set.intersection(*key_sets)
                    logger.info(f"只显示公共按键: 共 {len(common_keys)} 个")
                else:
                    common_keys = set()
                    logger.warning("没有找到任何公共按键")
            
            # 为每个算法分配颜色（使用全局颜色方案）
            colors = ALGORITHM_COLOR_PALETTE
            
            fig = go.Figure()
            
            # 收集所有激活算法的数据和统计信息
            algorithm_data_list = []
            
            for alg_idx, algorithm in enumerate(ready_algorithms):
                algorithm_name = algorithm.metadata.algorithm_name
                display_name = algorithm.metadata.display_name
                filename = algorithm.metadata.filename

                # 创建更具描述性的图注名称：算法名 (文件名)
                descriptive_name = f"{display_name} ({filename})"

                if not algorithm.analyzer or not algorithm.analyzer.note_matcher:
                    logger.warning(f"⚠️ 算法 '{descriptive_name}' 没有分析器或匹配器，跳过")
                    continue

                try:
                    offset_data = algorithm.analyzer.get_precision_offset_alignment_data()

                    if not offset_data:
                        logger.warning(f"⚠️ 算法 '{descriptive_name}' 没有精确匹配数据（≤50ms），跳过")
                        continue

                    # 获取该算法的平均延时，用于hovertemplate显示
                    mean_error_0_1ms = algorithm.analyzer.get_mean_error()
                    algorithm_mean_delay_ms = mean_error_0_1ms / 10.0

                    # 获取matched_pairs以便查找时间信息
                    matched_pairs = algorithm.analyzer.matched_pairs
                    record_note_dict = {r_idx: r_note for r_idx, _, r_note, _ in matched_pairs}
                    replay_note_dict = {p_idx: p_note for _, p_idx, _, p_note in matched_pairs}

                    # 提取按键ID和延时数据（带符号值）
                    key_ids = []
                    delays_ms = []  # 带符号，用于显示和计算阈值
                    customdata_list = []  # 用于存储customdata，包含record_index和replay_index
                    
                    for item in offset_data:
                        key_id = item.get('key_id')
                        keyon_offset = item.get('keyon_offset', 0)  # 单位：0.1ms
                        record_index = item.get('record_index')
                        replay_index = item.get('replay_index')
                        
                        if key_id is None or key_id == 'N/A':
                            continue
                            
                        # 过滤非公共按键
                        if only_common_keys and common_keys is not None:
                            if key_id not in common_keys:
                                continue
                        
                        try:
                            key_id_int = int(key_id)
                            delay_ms = keyon_offset / 10.0  # 带符号，保留原始值

                            # 获取录制和播放按键的时间信息
                            record_hammer_time_ms = 0.0
                            replay_hammer_time_ms = 0.0

                            # 获取录制音符的锤子时间
                            if record_index in record_note_dict:
                                record_note = record_note_dict[record_index]
                                if hasattr(record_note, 'hammers') and record_note.hammers is not None and not record_note.hammers.empty:
                                    record_hammer_time_ms = (record_note.hammers.index[0] + record_note.offset) / 10.0

                            # 获取播放音符的锤子时间
                            if replay_index in replay_note_dict:
                                replay_note = replay_note_dict[replay_index]
                                if hasattr(replay_note, 'hammers') and replay_note.hammers is not None and not replay_note.hammers.empty:
                                    replay_hammer_time_ms = (replay_note.hammers.index[0] + replay_note.offset) / 10.0

                            key_ids.append(key_id_int)
                            delays_ms.append(delay_ms)
                            # 添加customdata：包含record_index、replay_index、算法名称，用于点击时查找匹配对
                            customdata_list.append([record_index, replay_index, key_id_int, delay_ms, filename, record_hammer_time_ms, replay_hammer_time_ms])
                        except (ValueError, TypeError):
                            continue
                    
                    if not key_ids:
                        logger.warning(f"⚠️ 算法 '{descriptive_name}' 没有有效的散点图数据，跳过")
                        continue

                    color = colors[alg_idx % len(colors)]
                    
                    # 直接使用数据概览页面的数据，不重新计算
                    # 使用analyzer的方法，确保与数据概览页面完全一致
                    me_0_1ms = algorithm.analyzer.get_mean_error()  # 总体均值（0.1ms单位，带符号）
                    std_0_1ms = algorithm.analyzer.get_standard_deviation()  # 总体标准差（0.1ms单位，带符号）
                    
                    # 转换为ms单位
                    mu = me_0_1ms / 10.0  # 总体均值（ms，带符号）
                    sigma = std_0_1ms / 10.0  # 总体标准差（ms，带符号）
                    
                    # 计算相对延时：绝对延时减去平均延时
                    # 相对延时反映了每个匹配对相对于算法平均水平的"提前"或"延迟"
                    delays_array = np.array(delays_ms)
                    relative_delays_array = delays_array - mu  # 相对延时
                    relative_delays_ms = relative_delays_array.tolist()

                    # 计算相对延时的统计值（用于阈值）
                    if len(relative_delays_ms) > 1:
                        relative_mu = np.mean(relative_delays_array)  # 应该接近0
                        relative_sigma = np.std(relative_delays_array, ddof=1)  # 样本标准差
                        upper_threshold = relative_mu + 3 * relative_sigma
                        lower_threshold = relative_mu - 3 * relative_sigma
                    else:
                        relative_mu = 0.0
                        relative_sigma = 0.0
                        upper_threshold = 0.0
                        lower_threshold = 0.0

                    # 对数据按照按键ID排序，确保横轴按键ID有序递增
                    sorted_indices = sorted(range(len(key_ids)), key=lambda i: key_ids[i])
                    key_ids[:] = [key_ids[i] for i in sorted_indices]
                    delays_ms[:] = [delays_ms[i] for i in sorted_indices]
                    relative_delays_ms[:] = [relative_delays_ms[i] for i in sorted_indices]
                    customdata_list[:] = [customdata_list[i] for i in sorted_indices]

                    # 保存算法数据，用于后续添加散点图和阈值线
                    algorithm_data_list.append({
                        'name': descriptive_name,  # 使用描述性名称
                        'display_name': display_name,
                        'filename': filename,
                        'descriptive_name': descriptive_name,
                        'key_ids': key_ids,
                        'delays_ms': delays_ms,  # 绝对延时，用于customdata
                        'relative_delays_ms': relative_delays_ms,  # 相对延时，用于绘图
                        'customdata': customdata_list,  # 保存customdata
                        'color': color,
                        'mu': mu,
                        'sigma': sigma,
                        'algorithm_mean_delay_ms': algorithm_mean_delay_ms,  # 添加算法平均延时
                        'relative_mu': relative_mu,
                        'relative_sigma': relative_sigma,
                        'upper_threshold': upper_threshold,
                        'lower_threshold': lower_threshold
                    })
                    
                except Exception as e:
                    logger.warning(f"⚠️ 获取算法 '{descriptive_name}' 的按键与延时数据失败: {e}")
                    continue
            
            # 添加散点图数据
            for alg_data in algorithm_data_list:
                # 为超过阈值的点使用不同颜色和大小（基于相对延时）
                marker_colors = []
                marker_sizes = []
                for relative_delay in alg_data['relative_delays_ms']:
                    if relative_delay > alg_data['upper_threshold'] or relative_delay < alg_data['lower_threshold']:
                        # 超过阈值的点使用更深的颜色，更大尺寸
                        marker_colors.append(alg_data['color'])
                        marker_sizes.append(12)
                    else:
                        marker_colors.append(alg_data['color'])
                        marker_sizes.append(8)

                # 将按键ID转换为字符串格式，只显示ID数字
                key_id_strings = [str(kid) for kid in alg_data['key_ids']]

                fig.add_trace(go.Scatter(
                    x=key_id_strings,
                    y=alg_data['relative_delays_ms'],  # 使用相对延时
                    mode='markers',
                    name=f"{alg_data['descriptive_name']} - 匹配对",
                    marker=dict(
                        size=marker_sizes,
                        color=marker_colors,
                        opacity=0.6,
                        line=dict(width=1, color=alg_data['color'])
                    ),
                    customdata=alg_data['customdata'],  # 添加customdata，包含record_index、replay_index和算法名称
                    legendgroup=alg_data['descriptive_name'],
                    showlegend=True,
                    hovertemplate=f"算法: {alg_data['descriptive_name']}<br>按键: %{{customdata[2]}}<br>相对延时: %{{y:.2f}}ms<br>绝对延时: %{{customdata[3]:.2f}}ms<br>平均延时: {alg_data['algorithm_mean_delay_ms']:.2f}ms<br>录制锤子时间: %{{customdata[5]:.2f}}ms<br>播放锤子时间: %{{customdata[6]:.2f}}ms<extra></extra>"
                ))
            
            # 获取所有唯一的按键ID，用于确定阈值线的范围
            all_key_ids = set()
            for alg_data in algorithm_data_list:
                all_key_ids.update(alg_data['key_ids'])

            # 对按键ID排序，创建完整的按键标签列表
            sorted_key_ids = sorted(all_key_ids)
            key_labels = [str(kid) for kid in sorted_key_ids]
            
            # 为每个激活的算法添加阈值线（只显示激活算法的阈值）
            # 使用go.Scatter创建水平线，使其能够响应图例点击
            for alg_data in algorithm_data_list:
                # 添加相对延时的平均值参考线（0线，因为相对延时的平均值是0）
                # 使用Scatter创建水平线，设置相同的legendgroup，使其与散点图一起响应图例点击
                fig.add_trace(go.Scatter(
                    x=key_labels,
                    y=[0] * len(key_labels),  # 相对延时的平均值是0
                    mode='lines',
                    name=f"{alg_data['name']} - 平均值",
                    line=dict(
                        color=alg_data['color'],
                        width=1.5,
                        dash='dot'
                    ),
                    legendgroup=alg_data['name'],  # 与散点图使用相同的图例组
                    showlegend=True,
                    hovertemplate=f"算法: {alg_data['name']}<br>相对延时平均值 = 0ms<br>绝对延时平均值 = {alg_data['mu']:.2f}ms<extra></extra>"
                ))
                # 注意：已移除标注，信息通过悬停（hover）显示

                # 添加相对延时的上阈值线（相对均值 + 3倍相对标准差）
                fig.add_trace(go.Scatter(
                    x=key_labels,
                    y=[alg_data['upper_threshold']] * len(key_labels),
                    mode='lines',
                    name=f"{alg_data['name']} - 上阈值",
                    line=dict(
                        color=alg_data['color'],
                        width=2,
                        dash='dash'
                    ),
                    legendgroup=alg_data['name'],  # 与散点图使用相同的图例组
                    showlegend=True,
                    hovertemplate=f"算法: {alg_data['name']}<br>相对延时上阈值 = {alg_data['upper_threshold']:.2f}ms<extra></extra>"
                ))

                # 添加相对延时的下阈值线（相对均值 - 3倍相对标准差）
                fig.add_trace(go.Scatter(
                    x=key_labels,
                    y=[alg_data['lower_threshold']] * len(key_labels),
                    mode='lines',
                    name=f"{alg_data['name']} - 下阈值",
                    line=dict(
                        color=alg_data['color'],
                        width=2,
                        dash='dash'
                    ),
                    legendgroup=alg_data['name'],  # 与散点图使用相同的图例组
                    showlegend=True,
                    hovertemplate=f"算法: {alg_data['name']}<br>相对延时下阈值 = {alg_data['lower_threshold']:.2f}ms<extra></extra>"
                ))
            
            # 设置布局
            fig.update_layout(
                # 删除title，因为UI区域已有标题
                xaxis_title='按键',
                yaxis_title='相对延时 (ms)',
                xaxis=dict(
                    showgrid=True,
                    gridcolor='lightgray',
                    gridwidth=1,
                    type='category'  # 设置为类别轴，因为x轴现在是字符串
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
                margin=dict(t=90, b=60, l=60, r=60)  # 增加顶部边距，为图例和标注留出空间
            )
            
            logger.info(f"✅ 多算法按键与延时散点图生成成功，共 {len(ready_algorithms)} 个算法")
            return fig
            
        except Exception as e:
            logger.error(f"❌ 生成多算法按键与延时散点图失败: {e}")
            
            logger.error(traceback.format_exc())
            return self._create_empty_plot(f"生成失败: {str(e)}")
    
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
            logger.debug("ℹ️ 没有激活的算法，跳过Z-Score标准化散点图生成")
            return self._create_empty_plot("没有激活的算法")
        
        try:
            # 过滤出激活且就绪的算法
            ready_algorithms = [alg for alg in algorithms if alg.is_active and alg.is_ready()]
            if not ready_algorithms:
                logger.warning("没有激活且就绪的算法，无法生成Z-Score标准化散点图")
                return self._create_empty_plot("没有激活的算法")
            
            logger.info(f"开始生成多算法Z-Score标准化散点图，共 {len(ready_algorithms)} 个激活算法")
            
            # 为每个算法分配颜色（使用全局颜色方案）
            colors = ALGORITHM_COLOR_PALETTE
            
    
            fig = go.Figure()

            # 用于收集所有算法的x轴范围
            all_x_min = None
            all_x_max = None

            # 用于收集所有按键ID，用于创建完整的按键标签列表
            all_key_ids = set()
            
            # 收集所有激活算法的数据
            for alg_idx, algorithm in enumerate(ready_algorithms):
                algorithm_name = algorithm.metadata.algorithm_name
                display_name = algorithm.metadata.display_name
                filename = algorithm.metadata.filename

                # 创建更具描述性的图注名称：算法名 (文件名)
                descriptive_name = f"{display_name} ({filename})"

                if not algorithm.analyzer or not algorithm.analyzer.note_matcher:
                    logger.warning(f"⚠️ 算法 '{descriptive_name}' 没有分析器或匹配器，跳过")
                    continue
                
                try:
                    offset_data = algorithm.analyzer.get_precision_offset_alignment_data()

                    if not offset_data:
                        logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有精确匹配数据（≤50ms），跳过")
                        continue
                    
                    # 获取matched_pairs以便查找时间信息
                    matched_pairs = algorithm.analyzer.matched_pairs
                    record_note_dict = {r_idx: r_note for r_idx, _, r_note, _ in matched_pairs}
                    replay_note_dict = {p_idx: p_note for _, p_idx, _, p_note in matched_pairs}

                    # 提取按键ID和延时数据
                    key_ids = []
                    delays_ms = []
                    customdata_list = []
                    
                    for item in offset_data:
                        key_id = item.get('key_id')
                        keyon_offset = item.get('keyon_offset', 0)  # 单位：0.1ms
                        record_index = item.get('record_index')
                        replay_index = item.get('replay_index')
                        
                        if key_id is None or key_id == 'N/A':
                            continue
                        
                        try:
                            key_id_int = int(key_id)
                            delay_ms = keyon_offset / 10.0  # 转换为ms
                            
                            # 获取录制和播放按键的时间信息
                            record_hammer_time_ms = 0.0
                            replay_hammer_time_ms = 0.0

                            # 获取录制音符的锤子时间
                            if record_index in record_note_dict:
                                record_note = record_note_dict[record_index]
                                if hasattr(record_note, 'hammers') and record_note.hammers is not None and not record_note.hammers.empty:
                                    record_hammer_time_ms = (record_note.hammers.index[0] + record_note.offset) / 10.0

                            # 获取播放音符的锤子时间
                            if replay_index in replay_note_dict:
                                replay_note = replay_note_dict[replay_index]
                                if hasattr(replay_note, 'hammers') and replay_note.hammers is not None and not replay_note.hammers.empty:
                                    replay_hammer_time_ms = (replay_note.hammers.index[0] + replay_note.offset) / 10.0

                            key_ids.append(key_id_int)
                            delays_ms.append(delay_ms)  # 保持绝对延时用于其他计算
                            # 注意：customdata_list 仍然使用绝对延时，因为hover显示需要同时显示绝对和相对延时
                            customdata_list.append([
                                record_index,
                                replay_index,
                                key_id_int,
                                delay_ms,  # 绝对延时
                                filename,  # 使用文件名作为图注显示
                                record_hammer_time_ms,
                                replay_hammer_time_ms
                            ])
                        except (ValueError, TypeError):
                            continue
                    
                    if not key_ids:
                        logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有有效的散点图数据，跳过")
                        continue
                    
                    # 获取该算法的总体均值和标准差（用于Z-Score标准化和相对延时计算）
                    me_0_1ms = algorithm.analyzer.get_mean_error()  # 总体均值（0.1ms单位，带符号）
                    std_0_1ms = algorithm.analyzer.get_standard_deviation()  # 总体标准差（0.1ms单位，带符号）

                    # 转换为ms单位
                    mu = me_0_1ms / 10.0  # 总体均值（ms，带符号）
                    sigma = std_0_1ms / 10.0  # 总体标准差（ms，带符号）

                    # 计算相对延时：绝对延时减去平均延时
                    delays_array = np.array(delays_ms)
                    relative_delays_array = delays_array - mu  # 相对延时
                    relative_delays_ms = relative_delays_array.tolist()

                    # 计算Z-Score：z = (x_i - μ) / σ
                    if sigma > 0:
                        z_scores_array = (delays_array - mu) / sigma
                        # 转换为列表，确保Plotly正确处理
                        z_scores = z_scores_array.tolist()
                        logger.info(f"🔍 算法 '{algorithm_name}': μ={mu:.2f}ms, σ={sigma:.2f}ms, 原始延时范围=[{delays_array.min():.2f}, {delays_array.max():.2f}]ms, 相对延时范围=[{relative_delays_array.min():.2f}, {relative_delays_array.max():.2f}]ms, Z-Score范围=[{z_scores_array.min():.2f}, {z_scores_array.max():.2f}]")
                    else:
                        z_scores = [0.0] * len(delays_ms)
                        logger.warning(f"⚠️ 算法 '{algorithm_name}' 的标准差为0，无法进行Z-Score标准化")

                    # 对数据按照按键ID排序，确保横轴按键ID有序递增
                    sorted_indices = sorted(range(len(key_ids)), key=lambda i: key_ids[i])
                    key_ids[:] = [key_ids[i] for i in sorted_indices]
                    z_scores[:] = [z_scores[i] for i in sorted_indices]
                    customdata_list[:] = [customdata_list[i] for i in sorted_indices]

                    color = colors[alg_idx % len(colors)]

                    # 添加散点图（使用Z-Score值作为y轴）
                    fig.add_trace(go.Scatter(
                        x=[str(kid) for kid in key_ids],  # 将按键ID转换为字符串格式
                        y=z_scores,  # 使用Z-Score值，不是原始延时值
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
                        hovertemplate=f"算法: {descriptive_name}<br>键位: %{{x}}<br>延时: %{{customdata[3]:.2f}}ms<br>Z-Score: %{{y:.2f}}<br>录制锤子时间: %{{customdata[5]:.2f}}ms<br>播放锤子时间: %{{customdata[6]:.2f}}ms<extra></extra>"
                    ))
                    
                    # 收集所有按键ID，用于后续创建完整的按键标签列表
                    if key_ids:
                        all_key_ids.update(key_ids)
                    
                except Exception as e:
                    logger.warning(f"⚠️ 获取算法 '{descriptive_name}' 的Z-Score数据失败: {e}")
                    continue
            
            # 获取所有唯一的按键ID，用于确定阈值线的范围
            # 对按键ID排序，创建完整的按键标签列表
            sorted_key_ids = sorted(all_key_ids)
            key_labels = [str(kid) for kid in sorted_key_ids]

            # 为每个算法添加阈值线（与按键与延时散点图一样的对比曲线）
            # 虽然Z-Score标准化后所有算法的参考线值相同，但为每个算法添加独立的线，
            # 使其能够响应图例点击，与散点图一起显示/隐藏
            for alg_idx, algorithm in enumerate(ready_algorithms):
                algorithm_name = algorithm.metadata.algorithm_name
                display_name = algorithm.metadata.display_name
                filename = algorithm.metadata.filename

                # 创建更具描述性的图注名称：算法名 (文件名)
                descriptive_name = f"{display_name} ({filename})"
                color = colors[alg_idx % len(colors)]

                # 添加该算法的Z-Score = 0参考线（均值线）
                fig.add_trace(go.Scatter(
                    x=key_labels,
                    y=[0] * len(key_labels),
                    mode='lines',
                    name=f"{descriptive_name} - Z=0",
                    line=dict(
                        color=color,
                        width=1.5,
                        dash='dot'
                    ),
                    legendgroup=descriptive_name,  # 与散点图使用相同的图例组
                    showlegend=True,
                    hovertemplate=f"算法: {descriptive_name}<br>Z-Score = 0 (均值线)<extra></extra>"
                ))

                # 添加该算法的Z-Score = +3阈值线（上阈值）
                fig.add_trace(go.Scatter(
                    x=key_labels,
                    y=[3] * len(key_labels),
                    mode='lines',
                    name=f"{descriptive_name} - Z=+3",
                    line=dict(
                        color=color,
                        width=2,
                        dash='dash'
                    ),
                    legendgroup=descriptive_name,  # 与散点图使用相同的图例组
                    showlegend=True,
                    hovertemplate=f"算法: {descriptive_name}<br>Z-Score = +3 (上阈值)<extra></extra>"
                ))

                # 添加该算法的Z-Score = -3阈值线（下阈值）
                fig.add_trace(go.Scatter(
                    x=key_labels,
                    y=[-3] * len(key_labels),
                    mode='lines',
                    name=f"{descriptive_name} - Z=-3",
                    line=dict(
                        color=color,
                        width=2,
                        dash='dash'
                    ),
                    legendgroup=descriptive_name,  # 与散点图使用相同的图例组
                    showlegend=True,
                    hovertemplate=f"算法: {descriptive_name}<br>Z-Score = -3 (下阈值)<extra></extra>"
                ))
            
            # 设置布局
            fig.update_layout(
                # 删除title，因为UI区域已有标题
                xaxis_title='按键ID',
                yaxis_title='Z-Score (标准化延时)',
                xaxis=dict(
                    showgrid=True,
                    gridcolor='lightgray',
                    gridwidth=1,
                    type='category'  # 设置为类别轴，因为x轴现在是字符串
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
            
            logger.info(f"✅ 多算法Z-Score标准化散点图生成成功，共 {len(ready_algorithms)} 个算法")
            return fig
            
        except Exception as e:
            logger.error(f"❌ 生成多算法Z-Score标准化散点图失败: {e}")
            
            logger.error(traceback.format_exc())
            return self._create_empty_plot(f"生成Z-Score散点图失败: {str(e)}")

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
            
            fig = go.Figure()
            
            # 颜色列表
            colors = self.COLORS
            
            # 过滤出激活且就绪的算法
            ready_algorithms = [alg for alg in algorithms if alg.is_active and alg.is_ready()]
            if not ready_algorithms:
                return self._create_empty_plot("没有激活且就绪的算法")
            
            # 收集所有延时数据，用于自动调整Y轴
            all_delays = []
            has_data = False
            
            # 遍历每个算法
            for alg_idx, algorithm in enumerate(ready_algorithms):
                algorithm_name = algorithm.metadata.algorithm_name
                display_name = algorithm.metadata.display_name
                color = colors[alg_idx % len(colors)]
                
                # 获取该算法的精确偏移数据（误差 ≤ 50ms）
                if not algorithm.analyzer or not algorithm.analyzer.note_matcher:
                    continue

                offset_data = algorithm.analyzer.get_precision_offset_alignment_data()
                if not offset_data:
                    continue
                
                # 提取目标按键的延时数据
                key_delays = []
                customdata_list = []
                
                for item in offset_data:
                    key_id = item.get('key_id')
                    if key_id == target_key_id:
                        keyon_offset = item.get('keyon_offset', 0)
                        delay_ms = keyon_offset / 10.0  # ms
                        key_delays.append(delay_ms)
                        
                        # 记录详细信息，用于悬停
                        record_index = item.get('record_index')
                        replay_index = item.get('replay_index')
                        # 自定义数据格式: [record_index, replay_index, delay_ms, algorithm_name]
                        # 这对于交互可能有用，但在此处主要用于hover
                        customdata_list.append([record_index, replay_index, delay_ms, algorithm.metadata.filename])
                
                if not key_delays:
                    continue
                
                has_data = True    
                all_delays.extend(key_delays)
                
                # 1. 添加箱线图（显示统计分布）
                fig.add_trace(go.Box(
                    y=key_delays,
                    x=[display_name] * len(key_delays), # X轴为算法名称
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
                    # 更新交互信息
                    customdata=customdata_list,
                    hovertemplate=f'算法: {display_name}<br>按键: {target_key_id}<br>延时: %{{y:.2f}}ms<extra></extra>'
                ))

            # 更新布局
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
            
            if not has_data:
                return self._create_empty_plot(f"按键 {target_key_id} 在选定的算法中没有数据")
                
            return fig
            
        except Exception as e:
            logger.error(f"❌ 生成单键对比图失败: {e}")
            
            logger.error(traceback.format_exc())
            return self._create_empty_plot(f"生成失败: {str(e)}")

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
        if not algorithms:
            logger.debug("没有激活的算法，跳过多算法锤速与相对延时散点图生成")
            return self._create_empty_plot("没有激活的算法")

        try:
            # 过滤出激活且就绪的算法
            ready_algorithms = [alg for alg in algorithms if alg.is_active and alg.is_ready()]
            if not ready_algorithms:
                logger.warning("没有激活且就绪的算法，无法生成锤速与相对延时散点图")
                return self._create_empty_plot("没有激活的算法")

            logger.info(f"开始生成多算法锤速与相对延时散点图，共 {len(ready_algorithms)} 个激活算法")

            # 为每个算法分配颜色（使用全局颜色方案）
            colors = ALGORITHM_COLOR_PALETTE
            
            fig = go.Figure()

            for alg_idx, algorithm in enumerate(ready_algorithms):
                algorithm_name = algorithm.metadata.algorithm_name
                display_name = algorithm.metadata.display_name
                filename = algorithm.metadata.filename

                # 创建更具描述性的图注名称：算法名 (文件名)
                descriptive_name = f"{display_name} ({filename})"

                if not algorithm.analyzer or not algorithm.analyzer.note_matcher:
                    logger.warning(f"算法 '{descriptive_name}' 没有分析器或匹配器，跳过")
                    continue

                try:
                    matched_pairs = algorithm.analyzer.get_matched_pairs()

                    if not matched_pairs:
                        logger.warning(f"算法 '{descriptive_name}' 没有匹配数据，跳过")
                        continue

                    offset_data = algorithm.analyzer.get_precision_offset_alignment_data()

                    # 提取锤速和延时数据
                    hammer_velocities = []
                    delays_ms = []  # 延时（ms单位，带符号）
                    scatter_customdata = []  # 存储record_idx、replay_idx和algorithm_name，用于点击事件识别

                    # 创建匹配对索引到偏移数据的映射
                    offset_map = {}
                    for item in offset_data:
                        record_idx = item.get('record_index')
                        replay_idx = item.get('replay_index')
                        if record_idx is not None and replay_idx is not None:
                            offset_map[(record_idx, replay_idx)] = item

                    for record_idx, replay_idx, record_note, replay_note in matched_pairs:
                        # 获取播放音符的锤速（第一个锤速值）
                        if len(replay_note.hammers) > 0 and len(replay_note.hammers.values) > 0:
                            hammer_velocity = replay_note.hammers.values[0]
                        else:
                            continue

                        # 从偏移数据中获取延时
                        keyon_offset = None
                        if (record_idx, replay_idx) in offset_map:
                            keyon_offset = offset_map[(record_idx, replay_idx)].get('keyon_offset', 0)
                        else:
                            # 如果偏移数据中没有这个匹配对，跳过处理
                            continue

                        # 将延时从0.1ms转换为ms（带符号）
                        delay_ms = keyon_offset / 10.0

                        # 跳过锤速为0或负数的数据点（对数无法处理）
                        if hammer_velocity <= 0:
                            continue

                        # 获取按键ID
                        key_id = record_note.id if hasattr(record_note, 'id') else None

                        hammer_velocities.append(hammer_velocity)
                        delays_ms.append(delay_ms)
                        # 存储record_idx、replay_idx、algorithm_name和key_id，用于点击事件识别和显示
                        scatter_customdata.append([record_idx, replay_idx, display_name, key_id])

                    if not hammer_velocities:
                        logger.warning(f"算法 '{algorithm_name}' 没有有效的散点图数据，跳过")
                        continue

                    # 获取该算法的总体均值和标准差，用于计算相对延时和阈值
                    me_0_1ms = algorithm.analyzer.get_mean_error() if hasattr(algorithm.analyzer, 'get_mean_error') else 0.0
                    std_0_1ms = algorithm.analyzer.get_standard_deviation() if hasattr(algorithm.analyzer, 'get_standard_deviation') else 0.0

                    mu = me_0_1ms / 10.0  # 总体均值（ms，带符号）
                    sigma = std_0_1ms / 10.0  # 总体标准差（ms，带符号）

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

                    # 将锤速转换为对数形式（类似分贝）：log10(velocity)
                    log_velocities = [math.log10(v) for v in hammer_velocities]

                    color = colors[alg_idx % len(colors)]

                    # 添加散点图数据（x轴使用对数形式的锤速，y轴使用相对延时值）
                    # customdata格式: [delay_ms, original_velocity, record_idx, replay_idx, algorithm_name, key_id]
                    # 第一个元素用于hover显示延时，第二个元素用于hover显示原始锤速，后四个用于点击事件识别和显示
                    combined_customdata = [[delay_ms, orig_vel, record_idx, replay_idx, alg_name, key_id]
                                          for delay_ms, orig_vel, (record_idx, replay_idx, alg_name, key_id)
                                          in zip(delays_ms, hammer_velocities, scatter_customdata)]

                    fig.add_trace(go.Scatter(
                        x=log_velocities,
                        y=relative_delays,  # 使用相对延时值，不是Z-Score值
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
                        hovertemplate=f"算法: {descriptive_name}<br>按键: %{{customdata[5]}}<br>锤速: %{{customdata[1]:.0f}} (log: %{{x:.2f}})<br>相对延时: %{{y:.2f}}ms<br>绝对延时: %{{customdata[0]:.2f}}ms<extra></extra>",
                        customdata=combined_customdata
                    ))

                    # 添加相对延时的参考线和平行于x轴的阈值线
                    if len(log_velocities) > 0:
                        # 获取x轴范围（使用所有算法的对数范围）
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

                        # 计算x轴范围
                        x_min = min(all_log_velocities) if all_log_velocities else 0
                        x_max = max(all_log_velocities) if all_log_velocities else 2

                        # 添加相对延时的平均值参考线（0线，因为相对延时的平均值是0）
                        fig.add_trace(go.Scatter(
                            x=[x_min, x_max],
                            y=[relative_mu, relative_mu],  # 相对延时的平均值
                            mode='lines',
                            name=f'{descriptive_name} - 平均值',
                            line=dict(
                                color=color,
                                width=1.5,
                                dash='dot'
                            ),
                            legendgroup=descriptive_name,
                            showlegend=True,
                            hovertemplate=f"算法: {descriptive_name}<br>相对延时平均值 = {relative_mu:.2f}ms<extra></extra>"
                        ))

                        # 添加相对延时的上阈值线（相对均值 + 3倍相对标准差）
                        fig.add_trace(go.Scatter(
                            x=[x_min, x_max],
                            y=[upper_threshold, upper_threshold],
                            mode='lines',
                            name=f'{descriptive_name} - 上阈值',
                            line=dict(
                                color=color,
                                width=2,
                                dash='dash'
                            ),
                            legendgroup=descriptive_name,
                            showlegend=True,
                            hovertemplate=f"算法: {descriptive_name}<br>相对延时上阈值 = {upper_threshold:.2f}ms<extra></extra>"
                        ))

                        # 添加相对延时的下阈值线（相对均值 - 3倍相对标准差）
                        fig.add_trace(go.Scatter(
                            x=[x_min, x_max],
                            y=[lower_threshold, lower_threshold],
                            mode='lines',
                            name=f'{descriptive_name} - 下阈值',
                            line=dict(
                                color=color,
                                width=2,
                                dash='dash'
                            ),
                            legendgroup=descriptive_name,
                            showlegend=True,
                            hovertemplate=f"算法: {descriptive_name}<br>相对延时下阈值 = {lower_threshold:.2f}ms<extra></extra>"
                        ))


                except Exception as e:
                    logger.warning(f"获取算法 '{descriptive_name}' 的锤速与相对延时数据失败: {e}")
                    continue

            # 设置布局
            fig.update_layout(
                # 删除title，因为UI区域已有标题
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

            logger.info(f"多算法锤速与相对延时散点图生成成功，共 {len(ready_algorithms)} 个算法")
            return fig

        except Exception as e:
            logger.error(f"生成多算法锤速与相对延时散点图失败: {e}")

            logger.error(traceback.format_exc())
            return self._create_empty_plot(f"生成锤速与相对延时散点图失败: {str(e)}")

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
        if not algorithms:
            logger.debug("没有激活的算法，跳过多算法锤速与延时散点图生成")
            return self._create_empty_plot("没有激活的算法")
        
        try:
            # 过滤出就绪的算法
            ready_algorithms = [alg for alg in algorithms if alg.is_ready()]
            if not ready_algorithms:
                logger.warning("⚠️ 没有就绪的算法，无法生成多算法锤速与延时散点图")
                return self._create_empty_plot("没有就绪的算法")
            
            logger.info(f"📊 开始生成多算法锤速与延时散点图，共 {len(ready_algorithms)} 个算法")
            
            # 为每个算法分配颜色（使用全局颜色方案）
            colors = ALGORITHM_COLOR_PALETTE
            
            
            fig = go.Figure()

            for alg_idx, algorithm in enumerate(ready_algorithms):
                algorithm_name = algorithm.metadata.algorithm_name
                display_name = algorithm.metadata.display_name
                filename = algorithm.metadata.filename

                # 创建更具描述性的图注名称：算法名 (文件名)
                descriptive_name = f"{display_name} ({filename})"

                if not algorithm.analyzer or not algorithm.analyzer.note_matcher:
                    logger.warning(f"⚠️ 算法 '{descriptive_name}' 没有分析器或匹配器，跳过")
                    continue

                try:
                    matched_pairs = algorithm.analyzer.get_matched_pairs()

                    if not matched_pairs:
                        logger.warning(f"⚠️ 算法 '{descriptive_name}' 没有匹配数据，跳过")
                        continue

                    offset_data = algorithm.analyzer.get_precision_offset_alignment_data()

                    # 提取锤速和延时数据，并计算Z-Score（与按键与延时Z-Score散点图相同）
                    hammer_velocities = []
                    delays_ms = []  # 延时（ms单位，带符号，用于计算Z-Score）
                    scatter_customdata = []  # 存储record_idx、replay_idx和algorithm_name，用于点击事件识别
                    
                    # 创建匹配对索引到偏移数据的映射
                    offset_map = {}
                    for item in offset_data:
                        record_idx = item.get('record_index')
                        replay_idx = item.get('replay_index')
                        if record_idx is not None and replay_idx is not None:
                            offset_map[(record_idx, replay_idx)] = item
                    
                    for record_idx, replay_idx, record_note, replay_note in matched_pairs:
                        # 获取播放音符的锤速（第一个锤速值）
                        if len(replay_note.hammers) > 0 and len(replay_note.hammers.values) > 0:
                            hammer_velocity = replay_note.hammers.values[0]
                        else:
                            continue
                        
                        # 从偏移数据中获取延时
                        keyon_offset = None
                        if (record_idx, replay_idx) in offset_map:
                            keyon_offset = offset_map[(record_idx, replay_idx)].get('keyon_offset', 0)
                        else:
                            # 如果偏移数据中没有这个匹配对，跳过处理
                            # 这是为了避免使用私有API
                            continue
                        
                        # 将延时从0.1ms转换为ms（带符号，用于Z-Score计算）
                        delay_ms = keyon_offset / 10.0
                        
                        # 跳过锤速为0或负数的数据点（对数无法处理）
                        if hammer_velocity <= 0:
                            continue
                        
                        # 获取按键ID
                        key_id = record_note.id if hasattr(record_note, 'id') else None
                        
                        hammer_velocities.append(hammer_velocity)
                        delays_ms.append(delay_ms)
                        # 存储record_idx、replay_idx、algorithm_name和key_id，用于点击事件识别和显示
                        scatter_customdata.append([record_idx, replay_idx, filename, key_id])
                    
                    if not hammer_velocities:
                        logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有有效的散点图数据，跳过")
                        continue
                    
                    # 计算Z-Score（与按键与延时Z-Score散点图相同的计算方式）
                    me_0_1ms = algorithm.analyzer.get_mean_error() if hasattr(algorithm.analyzer, 'get_mean_error') else 0.0
                    std_0_1ms = algorithm.analyzer.get_standard_deviation() if hasattr(algorithm.analyzer, 'get_standard_deviation') else 0.0
                    
                    mu = me_0_1ms / 10.0  # 总体均值（ms，带符号）
                    sigma = std_0_1ms / 10.0  # 总体标准差（ms，带符号）
                    
                    # 计算Z-Score：z = (x_i - μ) / σ
                    delays_array = np.array(delays_ms)
                    if sigma > 0:
                        z_scores = ((delays_array - mu) / sigma).tolist()
                    else:
                        z_scores = [0.0] * len(delays_ms)
                    
                    # 将锤速转换为对数形式（类似分贝）：log10(velocity)
                    log_velocities = [math.log10(v) for v in hammer_velocities]
                    
                    color = colors[alg_idx % len(colors)]
                    
                    # 添加散点图数据（x轴使用对数形式的锤速，y轴使用Z-Score值）
                    # customdata格式: [delay_ms, original_velocity, record_idx, replay_idx, algorithm_name, key_id]
                    # 第一个元素用于hover显示延时，第二个元素用于hover显示原始锤速，后四个用于点击事件识别和显示
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
                        hovertemplate=f'算法: {descriptive_name}<br>按键: %{{customdata[5]}}<br>锤速: %{{customdata[1]:.0f}} (log: %{{x:.2f}})<br>延时: %{{customdata[0]:.2f}}ms<br>Z-Score: %{{y:.2f}}<extra></extra>',
                        customdata=combined_customdata
                    ))
                    
                    # 添加Z-Score参考线（与按键与延时Z-Score散点图相同）
                    if len(log_velocities) > 0:
                        # 获取x轴范围（使用所有算法的对数范围）
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
                        
                        # 对数形式
                        x_min = min(all_log_velocities) if all_log_velocities else 0
                        x_max = max(all_log_velocities) if all_log_velocities else 2
                        
                        # 添加Z=0的水平虚线（均值线）
                        fig.add_trace(go.Scatter(
                            x=[x_min, x_max],
                            y=[0, 0],
                            mode='lines',
                            name=f'{descriptive_name} - Z=0',
                            line=dict(
                                color=color,
                                width=1.5,
                                dash='dot'
                            ),
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
                            line=dict(
                                color=color,
                                width=2,
                                dash='dash'
                            ),
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
                            line=dict(
                                color=color,
                                width=2,
                                dash='dash'
                            ),
                            legendgroup=descriptive_name,
                            showlegend=True,
                            hovertemplate=f'算法: {descriptive_name}<br>Z-Score = -3 (下阈值)<extra></extra>'
                        ))
                    
                except Exception as e:
                    logger.warning(f"⚠️ 获取算法 '{algorithm_name}' 的锤速与延时数据失败: {e}")
                    continue
            
            # 设置布局
            
            fig.update_layout(
                # 删除title，因为UI区域已有标题
                xaxis_title='锤速（log₁₀）',
                yaxis_title='Z-Score（标准化延时）',
                xaxis=dict(
                    showgrid=True,
                    gridcolor='lightgray',
                    gridwidth=1,
                    # 使用线性刻度，让Plotly自动处理，但设置合适的范围
                    autorange=True,
                    # 设置刻度格式
                    tickformat='.1f',  # 显示1位小数
                    dtick=0.2  # 每0.2个单位一个刻度
                ),
                yaxis=dict(
                    showgrid=True,
                    gridcolor='lightgray',
                    gridwidth=1,
                    # 限制Y轴范围到合理的Z-Score区间，通常Z-Score在-5到+5之间
                    range=[-5, 5],
                    # 设置合适的刻度
                    dtick=1,  # 每个整数一个刻度
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
            
            logger.info(f"✅ 多算法锤速与延时散点图生成成功，共 {len(ready_algorithms)} 个算法")
            return fig
            
        except Exception as e:
            logger.error(f"❌ 生成多算法锤速与延时散点图失败: {e}")
            
            logger.error(traceback.format_exc())
            return self._create_empty_plot(f"生成失败: {str(e)}")
    
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
        if not algorithms:
            logger.debug("ℹ️ 没有激活的算法，跳过多算法按键与锤速散点图生成")
            return self._create_empty_plot("没有激活的算法")
        
        try:
            # 过滤出就绪的算法
            ready_algorithms = [alg for alg in algorithms if alg.is_ready()]
            if not ready_algorithms:
                logger.warning("⚠️ 没有就绪的算法，无法生成多算法按键与锤速散点图")
                return self._create_empty_plot("没有就绪的算法")
            
            logger.info(f"📊 开始生成多算法按键与锤速散点图，共 {len(ready_algorithms)} 个算法")
            
            # 为每个算法分配不同的标记形状和颜色方案
            marker_symbols = ['circle', 'square', 'diamond', 'triangle-up', 'x', 'star', 'cross', 'pentagon']
            colorscales = ['Viridis', 'Plasma', 'Inferno', 'Magma', 'Cividis', 'Turbo', 'Blues', 'Reds']
            
            
            fig = go.Figure()
            
            # 收集所有算法的延时范围，用于统一颜色条
            all_delays = []
            
            for alg_idx, algorithm in enumerate(ready_algorithms):
                algorithm_name = algorithm.metadata.algorithm_name
                display_name = algorithm.metadata.display_name
                filename = algorithm.metadata.filename

                # 创建更具描述性的图注名称：算法名 (文件名)
                descriptive_name = f"{display_name} ({filename})"

                if not algorithm.analyzer or not algorithm.analyzer.note_matcher:
                    logger.warning(f"⚠️ 算法 '{descriptive_name}' 没有分析器或匹配器，跳过")
                    continue

                try:
                    matched_pairs = algorithm.analyzer.get_matched_pairs()

                    if not matched_pairs:
                        logger.warning(f"⚠️ 算法 '{descriptive_name}' 没有匹配数据，跳过")
                        continue

                    offset_data = algorithm.analyzer.get_precision_offset_alignment_data()
                    
                    # 提取按键ID、锤速和延时数据
                    key_ids = []
                    hammer_velocities = []
                    delays_ms = []
                    
                    # 创建匹配对索引到偏移数据的映射
                    offset_map = {}
                    for item in offset_data:
                        record_idx = item.get('record_index')
                        replay_idx = item.get('replay_index')
                        if record_idx is not None and replay_idx is not None:
                            offset_map[(record_idx, replay_idx)] = item
                    
                    for record_idx, replay_idx, record_note, replay_note in matched_pairs:
                        key_id = record_note.id
                        
                        if len(replay_note.hammers) > 0 and len(replay_note.hammers.values) > 0:
                            hammer_velocity = replay_note.hammers.values[0]
                        else:
                            continue
                        
                        keyon_offset = None
                        if (record_idx, replay_idx) in offset_map:
                            keyon_offset = offset_map[(record_idx, replay_idx)].get('keyon_offset', 0)
                        else:
                            # 如果偏移数据中没有这个匹配对，跳过处理
                            continue
                        
                        delay_ms = abs(keyon_offset) / 10.0
                        
                        try:
                            key_id_int = int(key_id)
                            key_ids.append(key_id_int)
                            hammer_velocities.append(hammer_velocity)
                            delays_ms.append(delay_ms)
                            all_delays.append(delay_ms)
                        except (ValueError, TypeError):
                            continue
                    
                    if not key_ids:
                        logger.warning(f"⚠️ 算法 '{algorithm_name}' 没有有效的散点图数据，跳过")
                        continue
                    
                    marker_symbol = marker_symbols[alg_idx % len(marker_symbols)]
                    colorscale = colorscales[alg_idx % len(colorscales)]
                    
                    # 添加散点图数据，使用不同的标记形状和颜色方案区分算法
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
                                x=1.02 + (alg_idx * 0.08),  # 每个算法的颜色条位置不同
                                y=0.5 - (alg_idx * 0.3 / len(ready_algorithms))
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
                    
                except Exception as e:
                    logger.warning(f"⚠️ 获取算法 '{algorithm_name}' 的按键与锤速数据失败: {e}")
                    continue
            
            if not all_delays:
                logger.warning("⚠️ 没有有效的散点图数据，无法生成图表")
                return self._create_empty_plot("没有有效的散点图数据")
            
            # 设置布局
            fig.update_layout(
                # 删除title，因为UI区域已有标题
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
                margin=dict(t=70, b=60, l=60, r=200)  # 增加右侧边距，为多个颜色条留出空间
            )
            
            logger.info(f"✅ 多算法按键与锤速散点图生成成功，共 {len(ready_algorithms)} 个算法")
            return fig
            
        except Exception as e:
            logger.error(f"❌ 生成多算法按键与锤速散点图失败: {e}")
            
            logger.error(traceback.format_exc())
            return self._create_empty_plot(f"生成失败: {str(e)}")
    
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
    
    def _extract_song_identifier(self, filename: str) -> str:
        """
        从文件名中提取曲子标识（用于判断是否是同一首曲子）
        
        Args:
            filename: 原始文件名
            
        Returns:
            str: 曲子标识（去掉路径和扩展名）
        """
        import os
        # 去掉路径，只保留文件名
        basename = os.path.basename(filename)
        # 去掉扩展名
        song_id = os.path.splitext(basename)[0]
        return song_id
    
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

                # 详细记录原始数据用于调试
                logger.debug(f"[DEBUG] 处理记录: record_keyon_raw={record_keyon_raw} (type: {type(record_keyon_raw)}), keyon_offset_raw={keyon_offset_raw} (type: {type(keyon_offset_raw)})")

                # 检查数据类型有效性（支持 numpy 类型）
                record_keyon_is_valid = isinstance(record_keyon_raw, (int, float, np.integer, np.floating))
                keyon_offset_is_valid = isinstance(keyon_offset_raw, (int, float, np.integer, np.floating))

                logger.debug(f"[DEBUG] 类型检查: record_keyon_is_valid={record_keyon_is_valid}, keyon_offset_is_valid={keyon_offset_is_valid}")

                if not record_keyon_is_valid:
                    logger.debug(f"[DEBUG] 跳过记录: record_keyon无效 ({record_keyon_raw}, type: {type(record_keyon_raw)})")
                    continue
                if not keyon_offset_is_valid:
                    logger.debug(f"[DEBUG] 跳过记录: keyon_offset无效 ({keyon_offset_raw}, type: {type(keyon_offset_raw)})")
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

    def _configure_multi_algorithm_axes(self, fig, all_relative_delays: List[float]) -> None:
        """
        配置多算法图表的轴

        Args:
            fig: Plotly图表对象
            all_relative_delays: 所有相对延时数据
        """
        if not all_relative_delays:
            y_axis_min, y_axis_max, dtick = (-25, 25, 5)
        else:
            y_min = min(all_relative_delays)
            y_max = max(all_relative_delays)

            # 计算整体标准差
            delays_array = np.array(all_relative_delays)
            overall_std_dev = np.std(delays_array)

            # 根据标准差确定显示范围
            if overall_std_dev <= 3:  # 各算法数据高度集中
                y_half_range = 12  # ±12ms
                dtick = 3
            elif overall_std_dev <= 8:  # 中等集中
                y_half_range = 20  # ±20ms
                dtick = 4
            elif overall_std_dev <= 20:  # 适中离散
                y_half_range = 35  # ±35ms
                dtick = 7
            elif overall_std_dev <= 40:  # 较大离散
                y_half_range = 60  # ±60ms
                dtick = 10
            else:  # 超大离散
                y_half_range = max(60, overall_std_dev * 1.5)  # 至少±60ms，或1.5倍标准差
                dtick = 15

            # 以0为中心对称显示，但确保显示所有算法的数据
            y_axis_min = min(y_min - 2, -y_half_range)
            y_axis_max = max(y_max + 2, y_half_range)

            # 多算法比较时，确保有足够的对比空间
            actual_range = y_axis_max - y_axis_min
            if actual_range < 20:
                y_axis_min = -10
                y_axis_max = 10
                dtick = 2

        # 设置布局
        fig.update_layout(
            xaxis_title='偏移后播放时间 (播放时间 - 平均延时) (ms)',
            yaxis_title='相对延时 (ms)',
            plot_bgcolor='white',
            paper_bgcolor='white',
            font=dict(size=12),
            height=500,
            hovermode='closest',
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

        # 设置Y轴
        fig.update_yaxes(
            range=[y_axis_min, y_axis_max],
            dtick=dtick,
            tickformat='.1f'
        )

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

    def _configure_multi_algorithm_plot_axes(self, fig: Any, algorithm_results: List[Tuple[Dict[str, Any], str]]) -> None:
        """
        配置多算法图表的轴

        Args:
            fig: Plotly图表对象
            algorithm_results: 算法结果列表
        """
        # 收集所有相对延时数据并配置轴
        all_relative_delays = []
        for trace in fig.data:
            all_relative_delays.extend(trace.y)

        self._configure_multi_algorithm_axes(fig, all_relative_delays)

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
            logger.debug("没有激活的算法，跳过多算法延时时间序列图生成")
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

            logger.info(f"多算法延时时间序列图生成成功，共 {len(ready_algorithms)} 个算法")
            return {
                'raw_delay_plot': raw_delay_plot,
                'relative_delay_plot': fig
            }

        except Exception as e:
            logger.error(f"生成多算法延时时间序列图失败: {e}")
            logger.error(traceback.format_exc())
            empty_plot = self._create_empty_plot(f"生成失败: {str(e)}")
            return {
                'raw_delay_plot': empty_plot,
                'relative_delay_plot': empty_plot
            }

    def _configure_unified_waterfall_layout(self, fig: go.Figure, all_bars_by_algorithm: List[Dict], is_multi_algorithm: bool) -> None:
        """
        配置统一的瀑布图布局，包括标题、轴标签、图例和动态高度调整。

        Args:
            fig: Plotly图形对象
            all_bars_by_algorithm: 按算法分组的所有条形数据
            is_multi_algorithm: 是否多算法模式
        """
        # 计算动态高度
        if is_multi_algorithm:
            num_algorithms = len(all_bars_by_algorithm)
            # 多算法模式：每个算法分配更多高度
            base_height_per_algorithm = 600
            total_height = max(800, base_height_per_algorithm * num_algorithms)
        else:
            # 单算法模式：固定高度
            total_height = 800

        # 计算y轴范围（考虑多算法偏移）
        if is_multi_algorithm:
            num_algorithms = len(all_bars_by_algorithm)
            max_y_offset = (num_algorithms - 1) * 100  # 每个算法偏移100
            y_min = 0.5
            y_max = 89.5 + max_y_offset + 1  # 留出一些余量

            # 为多算法创建合适的刻度
            tick_vals = []
            tick_texts = []
            for alg_idx in range(num_algorithms):
                base_offset = alg_idx * 100
                for key_id in range(21, 109, 12):  # 每12个键显示一个刻度
                    tick_vals.append(key_id + base_offset)
                    if alg_idx == 0:
                        tick_texts.append(str(key_id))
                    else:
                        tick_texts.append(f"{key_id}({alg_idx+1})")

            y_axis_config = dict(
                tickmode='array',
                tickvals=tick_vals,
                ticktext=tick_texts,
                range=[y_min, y_max],
                autorange=False
            )
        else:
            # 单算法模式：标准钢琴键范围
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
            yaxis_title='按键ID' + (' (多算法偏移)' if is_multi_algorithm else ''),
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
