"""
锤速对比图处理器 - 处理锤速对比图的生成和交互
"""

import traceback
from typing import Optional, Tuple, List, Any, Union, Dict

import pandas as pd
import plotly.graph_objects as go
from plotly.graph_objs import Figure

from dash import html, dcc, no_update
from dash._callback import NoUpdate

from backend.piano_analysis_backend import PianoAnalysisBackend
from backend.multi_algorithm_manager import AlgorithmDataset
from backend.session_manager import SessionManager
from ui.scatter_handler_base import ScatterHandlerBase
from utils.logger import Logger
from spmid.note_matcher import MatchType


logger = Logger.get_logger()


# Type definition
class VelocityDataItem(Dict[str, Any]):
    """锤速数据项的类型定义"""
    pass


class VelocityComparisonHandler(ScatterHandlerBase):
    """
    锤速对比图处理器
    
    负责处理锤速对比图的生成、点击交互和数据管理
    """
    
    def handle_generate_hammer_velocity_comparison_plot(self, report_content: html.Div, session_id: str) -> Figure:
        """
        生成锤速对比图
        
        Args:
            report_content: 报告内容（触发器）
            session_id: 会话ID，用于获取后端实例
            
        Returns:
            plotly图表对象或空图表（当无数据或错误时）
        """
        backend = self.session_manager.get_backend(session_id)
        if not backend:
            return go.Figure()  # 返回空图表而不是 no_update
        
        try:
            logger.info("[DEBUG] 开始生成锤速对比图")
            
            # 验证环境条件
            if not self._validate_velocity_comparison_prerequisites(backend):
                logger.warning("[WARNING] 锤速对比图前提条件验证失败")
                return go.Figure()  # 返回空图表
            
            # 收集锤速数据
            logger.debug("[DEBUG] 开始收集锤速数据")
            velocity_data = self._collect_velocity_comparison_data(backend)
            logger.debug(f"[DEBUG] 收集到 {len(velocity_data)} 个锤速数据点")
            
            if not velocity_data:
                logger.warning("[WARNING] 没有收集到锤速数据")
                return go.Figure()  # 返回空图表
            
            # 生成对比图表
            logger.debug("[DEBUG] 开始生成锤速对比图表")
            fig = self._create_velocity_comparison_plot(velocity_data)
            logger.debug("[DEBUG] 锤速对比图表生成完成")
            return fig
            
        except Exception as e:
            logger.error(f"[ERROR] 生成锤速对比图失败: {e}")
            logger.error(traceback.format_exc())
            return go.Figure()  # 返回空图表
    
    def handle_hammer_velocity_comparison_click(
        self, click_data: Optional[Dict[str, Any]],
        close_modal_clicks: Optional[int],
        close_btn_clicks: Optional[int],
        session_id: str,
        current_style: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[Union[html.Div, dcc.Graph]], Dict[str, Any], Optional[Dict[str, Any]]]:
        """处理锤速对比图点击，显示对应按键的曲线对比（悬浮窗）"""
        from dash import callback_context
        
        # 检测触发源
        ctx = callback_context
        if not ctx.triggered:
            logger.warning("[WARNING] 锤速对比图点击回调：没有触发源")
            return current_style, [], no_update, no_update
        
        trigger_prop = ctx.triggered[0]['prop_id']
        trigger_id_raw = trigger_prop.split('.')[0]
        
        # 1. 解析 Plot ID
        plot_id = trigger_id_raw
        if trigger_id_raw.startswith('{'):
            try:
                import json
                plot_id = json.loads(trigger_id_raw).get('id', trigger_id_raw)
            except Exception:
                pass
        
        logger.debug(f"[DEBUG] 锤速对比图点击回调触发：prop_id={trigger_prop}, plot_id={plot_id}")
        
        # 如果点击了关闭按钮，只有当模态框是由本回调打开时才处理
        if plot_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            if current_style and current_style.get('display') == 'block' and click_data is not None:
                new_style = current_style.copy()
                new_style['display'] = 'none'
                return new_style, [], no_update, None
            return current_style, [], no_update, no_update
        
        # 如果是锤速对比图点击
        if plot_id == 'hammer-velocity-comparison-plot':
            if not click_data or 'points' not in click_data:
                logger.warning("[WARNING] 锤速对比图点击数据为空")
                return current_style, [], no_update, no_update
            
            return self._handle_hammer_velocity_comparison_click_logic(click_data, session_id, current_style)
        
        # 其他情况，保持当前状态
        return current_style, [], no_update, no_update
    
    # ==================== 私有方法 ====================
    
    def _handle_modal_close_trigger(self) -> Tuple[Dict[str, Any], List[Union[html.Div, dcc.Graph]], Dict[str, Any], Optional[Dict[str, Any]]]:
        """处理模态框关闭触发"""
        return {'display': 'none'}, [], no_update, no_update
    
    def _handle_hammer_velocity_comparison_click_logic(self, click_data, session_id, current_style):
        """处理锤速对比图点击的具体逻辑"""
        backend = self.session_manager.get_backend(session_id)
        if not backend:
            return current_style, [], no_update, no_update
        
        try:
            # 解析点击数据 - 锤速对比图需要至少8个元素的customdata
            parsed_data = self._parse_plot_click_data(click_data, "锤速对比图", 8)
            if not parsed_data:
                return current_style, [], no_update, no_update
            
            customdata = parsed_data['customdata']
            
            # 解析锤速对比图的customdata格式: [key_id, algorithm_name, record_velocity, replay_velocity, velocity_diff, absolute_delay, record_index, replay_index]
            key_id = int(customdata[0])
            algorithm_name = customdata[1]
            record_index = customdata[6]  # record_index在第7位（索引6），现在是UUID字符串
            replay_index = customdata[7]  # replay_index在第8位（索引7），现在是UUID字符串
            
            logger.info(f"🖱️ 锤速对比图点击: 算法={algorithm_name}, 按键={key_id}, record_index={record_index}, replay_index={replay_index}")
            
            # 构造click_data，包含算法名称、索引信息和customdata
            plot_click_data = {
                'algorithm_name': algorithm_name,
                'record_index': record_index,
                'replay_index': replay_index,
                'customdata': [customdata]  # 传递处理后的customdata以获取延时信息
            }
            
            detail_figure1, detail_figure2, detail_figure_combined = self._generate_velocity_comparison_detail_plots(backend, plot_click_data)

            # 计算中心时间
            center_time_ms = self._calculate_center_time_for_note_pair(backend, record_index, replay_index, algorithm_name)
            
            # 存储点击点信息
            point_info = {
                'key_id': key_id,
                'algorithm_name': algorithm_name,
                'record_idx': record_index,
                'replay_idx': replay_index,
                'source_plot_id': 'hammer-velocity-comparison-plot',
                'center_time_ms': center_time_ms
            }
            
            # 显示模态框
            modal_style = {
                'display': 'block',
                'position': 'fixed',
                'zIndex': '9999',
                'left': '0',
                'top': '0',
                'width': '100%',
                'height': '100%',
                'backgroundColor': 'rgba(0,0,0,0.6)',
                'backdropFilter': 'blur(5px)'
            }
            return modal_style, [dcc.Graph(
                figure=detail_figure_combined,
                style={'height': '800px'}
            )], point_info, no_update
            
        except Exception as e:
            logger.error(f"[ERROR] 处理锤速对比图点击失败: {e}")
            logger.error(traceback.format_exc())
            modal_style = {
                'display': 'block',
                'position': 'fixed',
                'zIndex': '9999',
                'left': '0',
                'top': '0',
                'width': '100%',
                'height': '100%',
                'backgroundColor': 'rgba(0,0,0,0.6)',
                'backdropFilter': 'blur(5px)'
            }
            return modal_style, [html.Div([
                html.P(f"无法生成详细图表", className="text-danger text-center")
            ])], no_update, no_update
    
    def _parse_plot_click_data(self, click_data: Dict[str, Any], plot_name: str, expected_customdata_length: int) -> Optional[Dict[str, Any]]:
        """
        解析图表点击数据
        
        Args:
            click_data: 原始点击数据
            plot_name: 图表名称（用于日志）
            expected_customdata_length: 期望的customdata长度
            
        Returns:
            Optional[Dict]: 包含customdata的字典，失败返回None
        """
        try:
            point = click_data['points'][0]
            customdata = point.get('customdata')
            
            if not customdata or len(customdata) < expected_customdata_length:
                logger.warning(f"[WARNING] {plot_name} customdata长度不足: 期望至少{expected_customdata_length}个元素，实际{len(customdata) if customdata else 0}个")
                return None
            
            return {'customdata': customdata}
            
        except Exception as e:
            logger.error(f"[ERROR] 解析{plot_name}点击数据失败: {e}")
            return None
    
    def _generate_velocity_comparison_detail_plots(self, backend: PianoAnalysisBackend, click_data: Dict[str, Any]) -> Tuple[Any, Any, Any]:
        """
        生成锤速对比图的详细曲线图
        """
        # 验证必要参数
        algorithm_name = click_data.get('algorithm_name')
        record_index = click_data.get('record_index')
        replay_index = click_data.get('replay_index')

        if record_index is None or replay_index is None:
            logger.error(f"[ERROR] 锤速对比图缺少必要参数: algorithm_name={algorithm_name}, record_index={record_index}, replay_index={replay_index}")
            return None, None, None

        # 生成图表 - 使用backend的方法，就像其他处理器一样
        if algorithm_name:
            # 多算法模式
            logger.debug(f"🔍 调用backend.generate_multi_algorithm_scatter_detail_plot_by_indices: algorithm_name='{algorithm_name}', record_index={record_index}, replay_index={replay_index}")

            detail_figure1, detail_figure2, detail_figure_combined = backend.generate_multi_algorithm_scatter_detail_plot_by_indices(
                algorithm_name=algorithm_name,
                record_index=record_index,
                replay_index=replay_index
            )
        else:
            # 单算法模式
            logger.debug(f"🔍 调用backend.generate_scatter_detail_plot_by_indices: record_index={record_index}, replay_index={replay_index}")

            detail_figure1, detail_figure2, detail_figure_combined = backend.generate_scatter_detail_plot_by_indices(
                record_index=record_index,
                replay_index=replay_index
            )

        logger.debug(f"🔍 锤速对比图生成结果: figure1={detail_figure1 is not None}, figure2={detail_figure2 is not None}, figure_combined={detail_figure_combined is not None}")

        return detail_figure1, detail_figure2, detail_figure_combined
    
    def _calculate_delays_for_velocity_comparison_click(
        self,
        backend: PianoAnalysisBackend,
        algorithm_name: Optional[str]
    ) -> Dict[str, float]:
        """
        锤速对比图点击的延时计算函数
        
        Args:
            backend: 后端实例
            algorithm_name: 算法名称（多算法模式）或None（单算法模式）
            
        Returns:
            Dict[str, float]: 延时字典，格式为 {algorithm_name: delay_ms} 或 {'default': delay_ms}
            
        Raises:
            RuntimeError: 如果无法获取分析器
        """
        # 验证后端状态和确定延时键名
        if algorithm_name and backend.multi_algorithm_manager:
            # 多算法模式：验证算法存在并获取平均延时
            algorithm = backend.multi_algorithm_manager.get_algorithm(algorithm_name)
            if not algorithm or not algorithm.analyzer:
                error_msg = f"无法获取算法 '{algorithm_name}' 的分析器"
                logger.error(f"[ERROR] {error_msg}")
                raise RuntimeError(error_msg)
            # 获取算法平均延时
            mean_error_0_1ms = algorithm.analyzer.get_mean_error()
            delay_value = mean_error_0_1ms / 10.0
            delay_key = algorithm_name
        else:
            # 单算法模式
            analyzer = backend._get_current_analyzer()
            if not analyzer:
                error_msg = "后端没有分析器"
                logger.error(f"[ERROR] {error_msg}")
                raise RuntimeError(error_msg)
            mean_error_0_1ms = analyzer.get_mean_error()
            delay_value = mean_error_0_1ms / 10.0
            delay_key = 'default'
        
        return {delay_key: delay_value}
    
    def _validate_velocity_comparison_prerequisites(self, backend: PianoAnalysisBackend) -> bool:
        """
        验证生成锤速对比图的必要前提条件
        
        Args:
            backend: 后端实例
            
        Returns:
            bool: 是否满足生成条件
        """
        # 使用通用的分析模式判断方法
        mode, algorithm_count = backend.get_current_analysis_mode()
        
        if mode == "multi":
            # 有活跃的多算法数据
            logger.info(f"[INFO] 检测到多算法模式，活跃算法数量: {algorithm_count}")
            return True
        elif mode == "single":
            # 没有活跃的多算法，但有单算法分析器
            logger.info("[INFO] 检测到单算法模式，支持生成锤速对比图（显示该算法的锤速分布）")
            return True
        else:
            # 两者都没有
            logger.warning("[WARNING] 没有可用的分析器，无法生成锤速对比图")
            return False
    
    def _collect_velocity_comparison_data(self, backend: PianoAnalysisBackend) -> List[VelocityDataItem]:
        """
        收集锤速对比数据 - 从精确匹配对获取数据
        
        Args:
            backend: 后端实例
            
        Returns:
            List[VelocityDataItem]: 锤速对比数据列表
        """
        velocity_data = []
        
        try:
            # 使用通用的分析模式判断方法
            mode, algorithm_count = backend.get_current_analysis_mode()
            
            if mode == "multi":
                # 多算法模式：从每个活跃算法的精确匹配对收集数据
                logger.info(f"[INFO] 多算法模式：从精确匹配对收集锤速对比数据，活跃算法数量: {algorithm_count}")
                
                active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()
                logger.info(f"[INFO] 活跃算法列表: {[alg.metadata.algorithm_name for alg in active_algorithms]}")
                for algorithm in active_algorithms:
                    logger.debug(f"[DEBUG] 处理算法: {algorithm.metadata.algorithm_name}")
                    algorithm_velocity_data = self._extract_velocity_data_from_precision_matches(algorithm)
                    logger.info(f"[INFO] 算法 {algorithm.metadata.algorithm_name} 收集到 {len(algorithm_velocity_data)} 个锤速数据点")
                    velocity_data.extend(algorithm_velocity_data)
            elif mode == "single":
                # 单算法模式：从单算法的精确匹配对收集数据
                logger.info("[INFO] 单算法模式：从精确匹配对收集锤速数据")
                
                # 创建临时算法对象来复用逻辑
                class TempAlgorithmDataset:
                    def __init__(self, analyzer, algorithm_name="单算法"):
                        self.analyzer = analyzer
                        self.metadata = type('Metadata', (), {'algorithm_name': algorithm_name})()
                
                temp_algorithm = TempAlgorithmDataset(backend._get_current_analyzer(), "单算法")
                algorithm_velocity_data = self._extract_velocity_data_from_precision_matches(temp_algorithm)
                velocity_data.extend(algorithm_velocity_data)
            else:
                logger.warning("[WARNING] 没有可用的分析器")
                return []
            
            logger.info(f"[INFO] 锤速对比数据收集完成，总数据点数量: {len(velocity_data)}")
            return velocity_data
            
        except Exception as e:
            logger.error(f"[ERROR] 收集锤速对比数据失败: {e}")
            logger.error(traceback.format_exc())
            return []
    
    def _extract_velocity_data_from_precision_matches(self, algorithm: AlgorithmDataset) -> List[VelocityDataItem]:
        """
        从精确匹配对中提取锤速数据
        
        Args:
            algorithm: 算法数据集
            
        Returns:
            List[VelocityDataItem]: 该算法的锤速数据列表
        """
        # 验证算法有效性
        if not algorithm.analyzer or not algorithm.analyzer.note_matcher:
            return []
        
        # 获取匹配对（直接从NoteMatcher获取，它现在已经包含了所有匹配对且带评级）
        matched_pairs = algorithm.analyzer.note_matcher.matched_pairs
        if not matched_pairs:
            return []
        
        velocity_data = []
        
        # 处理每个匹配对
        for record_note, replay_note, match_type, keyon_error_ms in matched_pairs:
            try:
                # 只处理精确匹配（优秀、良好、一般），对应误差 ≤ 50ms
                if match_type not in [MatchType.EXCELLENT, MatchType.GOOD, MatchType.FAIR]:
                    continue
                
                # 提取锤速
                record_velocity = self._get_velocity_from_note(record_note)
                replay_velocity = self._get_velocity_from_note(replay_note)
                
                if record_velocity is None or replay_velocity is None:
                    continue
                
                # 构建数据项
                velocity_item = {
                    'key_id': record_note.id,
                    'algorithm_name': algorithm.metadata.algorithm_name,
                    'record_velocity': record_velocity,
                    'replay_velocity': replay_velocity,
                    'record_hammer_time_ms': record_note.first_hammer_time,
                    'replay_hammer_time_ms': replay_note.first_hammer_time,
                    'record_index': record_note.uuid,
                    'replay_index': replay_note.uuid,
                    'absolute_delay': (replay_note.key_on_ms - record_note.key_on_ms)
                }
                
                velocity_data.append(velocity_item)
                
            except Exception as e:
                logger.warning(f"[WARNING] 提取匹配项速度数据失败 (UUID={record_note.uuid}): {e}")
                continue
        
        return velocity_data
    
    def _get_velocity_from_note(self, note: Any) -> Optional[float]:
        """
        从音符中提取锤速

        Args:
            note: 音符对象

        Returns:
            Optional[float]: 锤速值
        """
        try:
            if not note:
                return None

            return note.first_hammer_velocity

        except Exception as e:
            logger.warning(f"[WARNING] 从音符提取锤速失败: {e}")
            return None
    
    def _build_velocity_data_item(self, item: Dict, algorithm_name: str,
                                 record_note: Any, replay_note: Any,
                                 record_velocity: float, replay_velocity: float) -> VelocityDataItem:
        """
        构建锤速数据项

        Args:
            item: 精确匹配项数据
            algorithm_name: 算法名称
            record_note: 录制音符
            replay_note: 播放音符
            record_velocity: 录制锤速
            replay_velocity: 播放锤速

        Returns:
            VelocityDataItem: 锤速数据项
        """
        # 获取锤击时间
        record_hammer_time = record_note.first_hammer_time
        replay_hammer_time = replay_note.first_hammer_time

        return {
            'key_id': item.get('key_id'),
            'algorithm_name': algorithm_name,
            'record_velocity': record_velocity,
            'replay_velocity': replay_velocity,
            'record_hammer_time_ms': record_hammer_time,
            'replay_hammer_time_ms': replay_hammer_time,
            'record_index': item.get('record_index'),
            'replay_index': item.get('replay_index'),
            'absolute_delay': item.get('keyon_offset', 0) / 10.0  # 转换为毫秒
        }
    
    def _create_velocity_comparison_plot(self, velocity_data: List[VelocityDataItem]) -> Figure:
        """
        创建锤速对比散点图
        
        Args:
            velocity_data: 锤速数据列表
            
        Returns:
            Figure: 配置完整的图表对象
        """
        if not velocity_data:
            logger.warning("[WARNING] 没有锤速数据，创建空图表")
            return go.Figure()
        
        try:
            # 按算法分组数据
            algorithm_groups = {}
            for item in velocity_data:
                alg_name = item['algorithm_name']
                if alg_name not in algorithm_groups:
                    algorithm_groups[alg_name] = []
                algorithm_groups[alg_name].append(item)
            
            # 创建图表
            fig = go.Figure()
            
            # 为每个算法添加散点图
            colors = ['blue', 'red', 'green', 'orange', 'purple', 'brown', 'pink', 'gray', 'olive', 'cyan']
            
            for idx, (alg_name, data) in enumerate(algorithm_groups.items()):
                color = colors[idx % len(colors)]
                
                plot_data = self._prepare_velocity_plot_data(data)
                
                fig.add_trace(go.Scattergl(
                    x=plot_data['x_values'],
                    y=plot_data['y_values'],
                    mode='markers',
                    name=f'{alg_name} ({len(data)}点)',
                    marker=dict(
                        color=color,
                        size=8,
                        opacity=0.7,
                        line=dict(width=1, color='white')
                    ),
                    text=plot_data['hover_texts'],
                    customdata=plot_data['custom_data'],
                    hovertemplate='<b>%{text}</b><br>' +
                                '算法: ' + alg_name + '<extra></extra>'
                ))
            
            # 配置布局
            fig.update_layout(
                title=dict(
                    x=0.5,
                    font=dict(size=16, weight='bold')
                ),
                xaxis=dict(
                    title='按键ID',
                    gridcolor='lightgray',
                    showgrid=True,
                    zeroline=True,
                    zerolinecolor='lightgray',
                    tickmode='linear',
                    dtick=1  # 按键ID通常是整数
                ),
                yaxis=dict(
                    title='锤速差值 (播放锤速 - 录制锤速)',
                    gridcolor='lightgray',
                    showgrid=True,
                    zeroline=True,
                    zerolinecolor='red',  # 高亮零线
                    zerolinewidth=2
                ),
                plot_bgcolor='white',
                paper_bgcolor='white',
                hovermode='closest',
                showlegend=True,
                legend=dict(
                    x=0.01,  # 更靠左
                    y=1.02,  # 移到图表上方
                    xanchor='left',
                    yanchor='bottom',  # 从图注底部定位，这样会完全在图表上方
                    bgcolor='rgba(255,255,255,0.95)',
                    bordercolor='gray',
                    borderwidth=1,
                    font=dict(size=10),
                    orientation='h'  # 水平排列图注
                )
            )
            
            # 添加水平参考线（锤速差值=0，表示理想情况）
            fig.add_shape(
                type='line',
                x0=min(item['key_id'] for item in velocity_data),
                y0=0,
                x1=max(item['key_id'] for item in velocity_data),
                y1=0,
                line=dict(color='red', width=2, dash='dash'),
                name='理想基准线 (锤速差值=0)'
            )
            
            logger.info(f"[INFO] 锤速对比图创建完成，包含 {len(algorithm_groups)} 个算法，{len(velocity_data)} 个数据点")
            return fig
            
        except Exception as e:
            logger.warning(f"[WARNING] 创建锤速对比图失败: {e}")
            return go.Figure()
    
    def _prepare_velocity_plot_data(self, algorithm_data: List[VelocityDataItem]) -> Dict[str, Union[List[str], List[float], List[str]]]:
        """
        准备绘图数据
        
        Args:
            algorithm_data: 单个算法的锤速数据
            
        Returns:
            Dict: 包含x_values, y_values, hover_texts, custom_data的字典
        """
        x_values = []
        y_values = []
        hover_texts = []
        custom_data = []
        
        for item in algorithm_data:
            # 横轴：按键ID
            x_values.append(item['key_id'])
            # 纵轴：播放锤速 - 录制锤速的差值
            velocity_diff = item['replay_velocity'] - item['record_velocity']
            y_values.append(velocity_diff)
            
            # 创建悬浮文本
            hover_text = (
                f'按键: {item["key_id"]}<br>'
                f'录制锤速: {item["record_velocity"]:.0f}<br>'
                f'播放锤速: {item["replay_velocity"]:.0f}<br>'
                f'锤速差值: {velocity_diff:+.0f}<br>'
                f'录制锤子时间: {item["record_hammer_time_ms"]:.2f} ms<br>'
                f'播放锤子时间: {item["replay_hammer_time_ms"]:.2f} ms'
            )
            hover_texts.append(hover_text)
            
            # 构建customdata: [key_id, algorithm_name, record_velocity, replay_velocity, velocity_diff, absolute_delay, record_index, replay_index]
            custom_data.append([
                item['key_id'],
                item['algorithm_name'],
                item['record_velocity'],
                item['replay_velocity'],
                velocity_diff,
                item['absolute_delay'],
                item['record_index'],
                item['replay_index']
            ])
        
        return {
            'x_values': x_values,
            'y_values': y_values,
            'hover_texts': hover_texts,
            'custom_data': custom_data
        }
