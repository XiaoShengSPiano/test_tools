#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
瀑布图生成器模块
负责生成包含所有数据（配对按键、丢锤、多锤）的瀑布图
严格遵循单一职责原则，将大函数拆分为多个小函数
"""

from typing import Any, Dict, List, Optional, Tuple
from utils.logger import Logger
import plotly.graph_objects as go
import numpy as np
from spmid.note_matcher import MatchType

logger = Logger.get_logger()

# MatchType到评级的映射
MATCH_TYPE_TO_GRADE = {
    MatchType.EXCELLENT: 'correct',   # 优秀 (≤20ms)
    MatchType.GOOD: 'minor',          # 良好 (20-30ms)
    MatchType.FAIR: 'moderate',       # 一般 (30-50ms)
    MatchType.POOR: 'large',          # 较差 (50-100ms)
    MatchType.SEVERE: 'severe',       # 严重 (100-200ms)
    MatchType.FAILED: 'major'         # 失败 (>200ms)
}


class WaterfallPlotGenerator:
    """瀑布图生成器 - 负责生成包含所有数据的瀑布图"""

    def __init__(self):
        """初始化瀑布图生成器"""
        self._setup_color_scheme()

    def _setup_color_scheme(self) -> None:
        """设置颜色方案"""
        # 配对按键的颜色
        self.matched_color = 'rgba(70, 130, 180, 0.8)'  # 钢蓝色
        # 丢锤按键的颜色
        self.drop_hammer_color = 'rgba(220, 20, 60, 0.8)'  # 深红色
        # 多锤按键的颜色
        self.multi_hammer_color = 'rgba(255, 140, 0, 0.8)'  # 深橙色

    def generate_comprehensive_waterfall_plot(self,
                                             analyzer,
                                             time_filter=None,
                                             key_filter=None) -> Any:
        """
        生成包含所有数据的瀑布图 - 包括配对数据、丢锤和多锤数据

        Args:
            analyzer: SPMIDAnalyzer实例，包含note_matcher和错误检测结果
            time_filter: 时间过滤器
            key_filter: 按键过滤器

        Returns:
            go.Figure: Plotly图表对象
        """
        try:
            # 保存过滤器参数供后续方法使用
            self._key_filter = key_filter
            self._time_filter = time_filter

            # 收集所有数据 - 包括配对数据、丢锤和多锤
            all_data = self._collect_all_comprehensive_data(analyzer, time_filter, key_filter)

            # 生成图表
            fig = self._create_waterfall_figure(all_data)

            logger.info("✅ 包含所有数据的瀑布图生成成功")
            return fig

        except Exception as e:
            logger.error(f"生成包含所有数据的瀑布图失败: {e}")
            return self._create_error_figure(f"生成瀑布图失败: {str(e)}")

    def _collect_all_comprehensive_data(self, analyzer, time_filter=None, key_filter=None) -> Dict[str, List]:
        """
        收集所有瀑布图数据：配对数据 + 丢锤 + 多锤

        Args:
            analyzer: SPMIDAnalyzer实例
            time_filter: 时间过滤器
            key_filter: 按键过滤器

        Returns:
            Dict[str, List]: 按评级分类的数据字典
        """
        # 初始化评级分类数据结构
        graded_data = {
            'correct': [],    # 优秀: 误差 ≤ 20ms
            'minor': [],      # 良好: 20ms < 误差 ≤ 30ms
            'moderate': [],   # 一般: 30ms < 误差 ≤ 50ms
            'large': [],      # 较差: 50ms < 误差 ≤ 100ms
            'severe': [],     # 严重: 100ms < 误差 ≤ 200ms
            'major': []       # 失败: 误差 > 200ms（丢锤/多锤）
        }

        # 获取原始数据用于提取丢锤和多锤的音符对象
        initial_valid_record_data = getattr(analyzer, 'initial_valid_record_data', [])
        initial_valid_replay_data = getattr(analyzer, 'initial_valid_replay_data', [])

        # 1. 处理配对数据（从match_results）
        if hasattr(analyzer, 'note_matcher') and analyzer.note_matcher:
            note_matcher = analyzer.note_matcher
            if hasattr(note_matcher, 'match_results'):
                for result in note_matcher.match_results:
                    # 获取对应的音符对象
                    # 优先使用result.pair（包含拆分后的实际note对象）
                    # 如果pair不存在（失败匹配），则从原始数据获取
                    try:
                        if result.pair is not None:
                            # 成功匹配：使用pair中的实际note对象（支持拆分数据）
                            record_note, replay_note = result.pair
                        else:
                            # 失败匹配：从原始数据获取
                            record_note = note_matcher._record_data[result.record_index]
                            replay_note = None if result.replay_index is None else note_matcher._replay_data[result.replay_index]
                    except (IndexError, AttributeError, TypeError) as e:
                        logger.warning(f"⚠️ 无法获取音符对象: record_index={result.record_index}, replay_index={result.replay_index}, error={e}")
                        continue

                    # 检查是否符合过滤条件
                    if not (self._should_include_note(record_note, time_filter, key_filter) and
                            self._should_include_note(replay_note, time_filter, key_filter)):
                        continue

                    # 直接使用匹配阶段的评级结果（避免重复评级）
                    grade_key = MATCH_TYPE_TO_GRADE.get(result.match_type, 'moderate')
                    
                    # 获取误差信息（用于显示，不用于评级）
                    error_ms = result.error_ms if result.error_ms is not None else 0
                    
                    # 添加录制音符的条形
                    record_bars = self._extract_note_bars(record_note, 'record')
                    for bar in record_bars:
                        bar['grade'] = grade_key
                        bar['error_ms'] = error_ms
                        if not result.is_success:
                            bar['match_status'] = 'failed'
                        graded_data[grade_key].append(bar)

                    # 添加播放音符的条形
                    if replay_note is not None:
                        replay_bars = self._extract_note_bars(replay_note, 'replay')
                        for bar in replay_bars:
                            bar['grade'] = grade_key
                            bar['error_ms'] = error_ms
                            if not result.is_success:
                                bar['match_status'] = 'failed'
                            graded_data[grade_key].append(bar)

        # 2. 处理丢锤数据
        drop_hammers = getattr(analyzer, 'drop_hammers', [])
        if drop_hammers:
            for error_note in drop_hammers:
                if hasattr(error_note, 'global_index') and error_note.global_index >= 0:
                    try:
                        note = initial_valid_record_data[error_note.global_index]
                        if self._should_include_note(note, time_filter, key_filter):
                            bars = self._extract_note_bars(note, 'record')
                            for bar in bars:
                                bar['grade'] = 'major'
                                bar['error_ms'] = float('inf')
                                bar['data_type'] = 'drop_hammer'
                                bar['source_index'] = error_note.global_index
                                bar['error_reason'] = getattr(error_note, 'reason', '')
                                graded_data['major'].append(bar)
                    except (IndexError, AttributeError):
                        logger.warning(f"处理丢锤数据失败 (索引{error_note.global_index}): 使用ErrorNote信息")
                        # 如果无法从原始数据获取，使用ErrorNote的基本信息
                        if hasattr(error_note, 'infos') and error_note.infos:
                            note_info = error_note.infos[0]
                            bar = {
                                't_on': note_info.keyOn,
                                't_off': note_info.keyOff,
                                'key_id': note_info.keyId,
                                'value': 0.5,
                                'label': 'record',
                                'grade': 'major',
                                'error_ms': float('inf'),
                                'data_type': 'drop_hammer',
                                'source_index': error_note.global_index,
                                'error_reason': getattr(error_note, 'reason', '')
                            }
                            graded_data['major'].append(bar)

        # 3. 处理多锤数据
        multi_hammers = getattr(analyzer, 'multi_hammers', [])
        if multi_hammers:
            for error_note in multi_hammers:
                if hasattr(error_note, 'global_index') and error_note.global_index >= 0:
                    try:
                        note = initial_valid_replay_data[error_note.global_index]
                        if self._should_include_note(note, time_filter, key_filter):
                            bars = self._extract_note_bars(note, 'replay')
                            for bar in bars:
                                bar['grade'] = 'major'
                                bar['error_ms'] = float('inf')
                                bar['data_type'] = 'multi_hammer'
                                bar['source_index'] = error_note.global_index
                                bar['error_reason'] = getattr(error_note, 'reason', '')
                                graded_data['major'].append(bar)
                    except (IndexError, AttributeError):
                        logger.warning(f"处理多锤数据失败 (索引{error_note.global_index}): 使用ErrorNote信息")
                        # 如果无法从原始数据获取，使用ErrorNote的基本信息
                        if hasattr(error_note, 'infos') and error_note.infos:
                            note_info = error_note.infos[0]
                            bar = {
                                't_on': note_info.keyOn,
                                't_off': note_info.keyOff,
                                'key_id': note_info.keyId,
                                'value': 0.5,
                                'label': 'replay',
                                'grade': 'major',
                                'error_ms': float('inf'),
                                'data_type': 'multi_hammer',
                                'source_index': error_note.global_index,
                                'error_reason': getattr(error_note, 'reason', '')
                            }
                            graded_data['major'].append(bar)

        return graded_data

    def _should_include_note(self, note, time_filter=None, key_filter=None) -> bool:
        """
        检查音符是否应该被包含在瀑布图中

        Args:
            note: 音符对象
            time_filter: 时间过滤器
            key_filter: 按键过滤器

        Returns:
            bool: 是否应该包含
        """
        # 应用按键过滤
        if key_filter and hasattr(note, 'id'):
            if note.id not in key_filter:
                return False

        # 应用时间过滤
        if time_filter and hasattr(time_filter, 'get_time_range'):
            time_range = time_filter.get_time_range()
            if time_range:
                start_time_01ms, end_time_01ms = time_range
                try:
                    key_on = note.after_touch.index[0] + note.offset if len(note.after_touch) > 0 else note.offset
                    key_off = (note.after_touch.index[-1] + note.offset
                              if len(note.after_touch) > 0 else key_on)

                    if not (key_on >= start_time_01ms and key_off <= end_time_01ms):
                        return False
                except (IndexError, AttributeError):
                    return False

        return True



    def _extract_note_bars(self, note, label: str) -> List[Dict]:
        """
        从音符中提取bar段数据

        Args:
            note: 音符对象
            label: 数据标签 ('record' 或 'replay')

        Returns:
            List[Dict]: bar段数据列表
        """
        bars = []

        try:
            # 计算key_on和key_off时间
            key_on = note.hammers.index[0] + note.offset if len(note.hammers) > 0 else note.offset
            key_off = (note.after_touch.index[-1] + note.offset
                      if len(note.after_touch) > 0 else key_on)

            key_id = note.id

            # 为每个锤击创建bar段
            for i in range(len(note.hammers)):
                t_hammer = note.hammers.index[i] + note.offset
                v_hammer = note.hammers.values[i]

                bar = {
                    't_on': t_hammer,
                    't_off': key_off,
                    'key_id': key_id,
                    'value': v_hammer,
                    'label': label,
                    'index': i
                }
                bars.append(bar)

        except (IndexError, AttributeError) as e:
            logger.warning(f"提取音符bar段失败: {e}")

        return bars


    def _create_waterfall_figure(self, graded_data: Dict[str, List]) -> go.Figure:
        """
        创建基于评级分类的瀑布图Figure

        Args:
            graded_data: 按评级分类的数据

        Returns:
            go.Figure: Plotly图表对象
        """
        fig = go.Figure()

        # 添加不同评级的数据
        self._add_graded_data_traces(fig, graded_data)

        # 配置图表布局
        self._configure_graded_waterfall_layout(fig, graded_data)

        return fig

    def _add_graded_data_traces(self, fig: go.Figure, graded_data: Dict[str, List]) -> None:
        """
        添加按评级分类的数据traces

        Args:
            fig: Plotly图表对象
            graded_data: 按评级分类的数据
        """
        # 定义评级颜色映射
        grade_colors = {
            'correct': 'rgba(0, 128, 0, 0.8)',      # 绿色 - 优秀
            'minor': 'rgba(0, 255, 0, 0.8)',        # 浅绿 - 良好
            'moderate': 'rgba(255, 255, 0, 0.8)',   # 黄色 - 一般
            'large': 'rgba(255, 165, 0, 0.8)',      # 橙色 - 较差
            'severe': 'rgba(255, 0, 0, 0.8)',       # 红色 - 严重
            'major': 'rgba(128, 0, 128, 0.8)'       # 紫色 - 失败
        }

        # 定义评级显示名称
        grade_names = {
            'correct': '优秀匹配 (≤20ms)',
            'minor': '良好匹配 (20-30ms)',
            'moderate': '一般匹配 (30-50ms)',
            'large': '较差匹配 (50ms-1s)',
            'severe': '严重匹配 (>1s)',
            'major': '匹配失败'
        }

        # 为每个评级添加数据
        for grade_key, grade_data in graded_data.items():
            if not grade_data:
                continue

            color = grade_colors.get(grade_key, 'rgba(128, 128, 128, 0.8)')
            name = grade_names.get(grade_key, f'评级:{grade_key}')

            self._add_single_grade_traces(fig, grade_data, name, color, grade_key)

    def _add_single_grade_traces(self, fig: go.Figure, data: List[Dict], name: str, color: str, grade_key: str) -> None:
        """
        添加单个评级的数据traces

        Args:
            fig: Plotly图表对象
            data: 该评级的数据列表
            name: trace名称
            color: 颜色
            grade_key: 评级键
        """
        for item in data:
            # 计算实际的key_id（加上小的偏移以区分录制和播放）
            base_key_id = item['key_id']
            if item.get('label') == 'replay':
                actual_key_id = base_key_id + 0.2  # 播放数据稍微偏移
            else:
                actual_key_id = base_key_id

            # 创建hover文本
            hover_text = self._create_graded_hover_text(item, grade_key)

            # 添加Plotly散点图trace
            fig.add_trace(go.Scatter(
                x=[item['t_on']/10, item['t_off']/10],  # 转换为ms
                y=[actual_key_id, actual_key_id],
                mode='lines',
                line=dict(color=color, width=3),
                name=name,
                showlegend=True,
                legendgroup=grade_key,
                hoverinfo='text',
                hovertext=hover_text,
                customdata=[[item['t_on']/10, item['t_off']/10, item['key_id'],
                            item.get('value', 0), grade_key, item.get('error_ms', 0)]]
            ))

    def _create_graded_hover_text(self, item: Dict, grade_key: str) -> str:
        """
        创建基于评级的hover文本

        Args:
            item: 数据项
            grade_key: 评级键

        Returns:
            str: hover文本
        """
        grade_names = {
            'correct': '优秀匹配',
            'minor': '良好匹配',
            'moderate': '一般匹配',
            'large': '较差匹配',
            'severe': '严重匹配',
            'major': '匹配失败'
        }

        grade_name = grade_names.get(grade_key, f'评级:{grade_key}')
        error_ms = item.get('error_ms', 0)

        if grade_key == 'major':
            data_type = item.get('data_type', '')
            if data_type == 'drop_hammer':
                error_info = "丢锤: 录制数据无对应播放"
            elif data_type == 'multi_hammer':
                error_info = "多锤: 播放数据无对应录制"
            else:
                error_info = "匹配失败"
        elif error_ms == float('inf'):
            error_info = "无误差数据"
        else:
            error_info = f"误差: {error_ms:.2f}ms"

        # 添加额外信息
        extra_info = ""
        if item.get('data_type') in ['drop_hammer', 'multi_hammer']:
            extra_info = f'<br>原因: {item.get("error_reason", "未知")}'

        return (f'评级: {grade_name}<br>'
                f'按键ID: {item["key_id"]}<br>'
                f'力度: {item.get("value", 0):.3f}<br>'
                f'{error_info}{extra_info}<br>'
                f'开始时间: {item["t_on"]/10:.1f}ms<br>'
                f'结束时间: {item["t_off"]/10:.1f}ms<br>'
                f'数据来源: {item.get("label", "unknown")}')

    def _configure_graded_waterfall_layout(self, fig: go.Figure, graded_data: Dict[str, List]) -> None:
        """
        配置基于评级的瀑布图布局

        Args:
            fig: Plotly图表对象
            graded_data: 按评级分类的数据
        """
        # 计算统计信息
        total_points = sum(len(data) for data in graded_data.values())

        # 创建标题
        title = f'钢琴按键匹配质量瀑布图 (共{total_points}个事件)'
        title += '<br><span style="font-size:10px; color:#666;">'

        grade_stats = []
        grade_names = {
            'correct': '优秀', 'minor': '良好', 'moderate': '一般',
            'large': '较差', 'severe': '严重', 'major': '失败'
        }

        # 统计不同类型的失败匹配
        if graded_data.get('major'):
            drop_hammer_count = sum(1 for item in graded_data['major'] if item.get('data_type') == 'drop_hammer')
            multi_hammer_count = sum(1 for item in graded_data['major'] if item.get('data_type') == 'multi_hammer')
            other_failed_count = len(graded_data['major']) - drop_hammer_count - multi_hammer_count

            if drop_hammer_count > 0:
                grade_stats.append(f'丢锤: {drop_hammer_count}')
            if multi_hammer_count > 0:
                grade_stats.append(f'多锤: {multi_hammer_count}')
            if other_failed_count > 0:
                grade_stats.append(f'其他失败: {other_failed_count}')
        else:
            for grade_key, count in graded_data.items():
                if count and grade_key != 'major':
                    grade_name = grade_names.get(grade_key, grade_key)
                    grade_stats.append(f'{grade_name}: {len(count)}')

        title += ' | '.join(grade_stats)
        title += '</span>'

        # 设置图表布局
        fig.update_layout(
            title=title,
            xaxis_title='时间 (ms)',
            yaxis_title='按键ID',
            yaxis=dict(tickmode='array', tickvals=list(range(1, 89)), range=[0.5, 89.5]),
            height=800,
            showlegend=True,
            template='plotly_white'
        )



    def _add_single_type_traces(self, fig: go.Figure, data: List[Dict],
                               name: str, color: str, y_offset: float) -> None:
        """
        添加单一类型数据的traces

        Args:
            fig: Plotly图表对象
            data: 数据列表
            name: trace名称
            color: 颜色
            y_offset: Y轴偏移
        """
        if not data:
            return

        for item in data:
            # 计算实际的key_id（加上偏移）
            actual_key_id = item['key_id'] + y_offset

            # 创建hover文本
            hover_text = self._create_hover_text(item)

            fig.add_trace(go.Scatter(
                x=[item['t_on']/10, item['t_off']/10],  # 转换为ms
                y=[actual_key_id, actual_key_id],
                mode='lines',
                line=dict(color=color, width=3),
                name=name,
                showlegend=True,  # 启用图例
                legendgroup=name,  # 按类型分组
                hoverinfo='text',
                hovertext=hover_text,
                customdata=[[item['t_on']/10, item['t_off']/10, item['key_id'], item['value'], item.get('data_type', 'unknown'), item['index']]]
            ))

    def _create_hover_text(self, item: Dict) -> str:
        """
        创建hover文本

        Args:
            item: 数据项

        Returns:
            str: hover文本
        """
        data_type_map = {
            'matched': '配对按键',
            'drop_hammer': '丢锤按键',
            'multi_hammer': '多锤按键',
            'unmatched_record': '未匹配录制',
            'unmatched_replay': '未匹配播放'
        }

        data_type = data_type_map.get(item.get('data_type', 'unknown'), '未知类型')

        return (f'类型: {data_type}<br>'
                f'按键ID: {item["key_id"]}<br>'
                f'力度: {item["value"]:.3f}<br>'
                f'开始时间: {item["t_on"]/10:.1f}ms<br>'
                f'结束时间: {item["t_off"]/10:.1f}ms<br>'
                f'数据来源: {item["label"]}')

    def _configure_waterfall_layout(self, fig: go.Figure, filtered_data: Dict[str, List]) -> None:
        """
        配置瀑布图布局

        Args:
            fig: Plotly图表对象
            filtered_data: 过滤后的数据
        """
        # 计算数据统计
        total_points = sum(len(data) for data in filtered_data.values())

        # 创建标题
        title = f'钢琴按键事件瀑布图 (共{total_points}个事件)'
        title += '<br><span style="font-size:10px; color:#666;">'
        title += f'配对按键: {len(filtered_data["matched"])} | '
        title += f'丢锤按键: {len(filtered_data["drop_hammers"])} | '
        title += f'多锤按键: {len(filtered_data["multi_hammers"])}'
        title += '</span>'

        # 设置布局
        fig.update_layout(
            title=title,
            xaxis_title='时间 (ms)',
            yaxis_title='按键ID',
            yaxis=dict(
                tickmode='array',
                tickvals=list(range(1, 89)),  # 钢琴按键范围
                range=[0.5, 89.5]  # 显示完整按键范围
            ),
            height=800,
            showlegend=True,  # 启用图例
            legend=dict(
                orientation='h',  # 水平排列
                yanchor='bottom',
                y=1.02,  # 图例位置
                xanchor='center',
                x=0.5,
                bgcolor='rgba(255,255,255,0.8)',
                bordercolor='rgba(0,0,0,0.2)',
                borderwidth=1
            ),
            template='plotly_white',
            hovermode='closest'
        )

    def _create_error_figure(self, error_msg: str) -> go.Figure:
        """
        创建错误图表

        Args:
            error_msg: 错误消息

        Returns:
            go.Figure: 错误图表
        """
        fig = go.Figure()
        fig.add_annotation(
            text=error_msg,
            xref="paper", yref="paper",
            x=0.5, y=0.5, xanchor='center', yanchor='middle',
            showarrow=False, font_size=16
        )
        fig.update_layout(
            title="图表生成失败",
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            plot_bgcolor='white'
        )
        return fig
