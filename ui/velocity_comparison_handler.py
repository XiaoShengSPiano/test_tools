"""
锤速对比图处理器 - 处理锤速对比图的生成和交互
"""

import traceback
from typing import Optional, Tuple, List, Any, Union, Dict

import plotly.graph_objects as go
from plotly.graph_objs import Figure

from dash import html, dcc, no_update

from backend.piano_analysis_backend import PianoAnalysisBackend
from backend.multi_algorithm_manager import AlgorithmDataset
from ui.scatter_handler_base import ScatterHandlerBase
from utils.logger import Logger
from spmid.note_matcher import MatchType


logger = Logger.get_logger()


class VelocityComparisonHandler(ScatterHandlerBase):
    """
    锤速对比图处理器
    
    负责处理锤速对比图的生成、点击交互和数据管理
    """
    
    def handle_generate_hammer_velocity_comparison_plot(self, report_content: html.Div, session_id: str) -> Figure:
        """生成锤速对比图"""
        backend = self.session_manager.get_backend(session_id)
        if not backend:
            return go.Figure()
        
        try:
            if not self._validate_velocity_comparison_prerequisites(backend):
                return go.Figure()
            
            velocity_data = self._collect_velocity_comparison_data(backend)
            if not velocity_data:
                return go.Figure()
            
            return self._create_velocity_comparison_plot(velocity_data)
            
        except Exception as e:
            logger.error(f"[ERROR] 生成锤速对比图失败: {e}")
            logger.error(traceback.format_exc())
            return go.Figure()
    
    def handle_hammer_velocity_comparison_click(self, click_data, session_id, current_style):
        """处理锤速对比图点击，显示对应按键的曲线对比（悬浮窗）"""
        plot_id = self._get_triggered_plot_id()
        if not plot_id:
            return no_update, no_update, no_update
            
        if plot_id in ['close-key-curves-modal', 'close-key-curves-modal-btn']:
            return self._handle_modal_close()
        
        if plot_id == 'hammer-velocity-comparison-plot':
            if not click_data or 'points' not in click_data:
                return current_style, [], no_update
            return self._handle_comparison_click_logic(click_data, session_id, current_style)
        
        return no_update, no_update, no_update
    
    # ==================== 私有方法 ====================
    
    def _handle_comparison_click_logic(self, click_data, session_id, current_style):
        """处理锤速对比图点击的具体逻辑"""
        backend = self.session_manager.get_backend(session_id)
        if not backend:
            return current_style, [], no_update
        
        # 解析数据 (customdata格式: [key_id, algorithm_name, record_velocity, replay_velocity, velocity_diff, absolute_delay, record_index, replay_index])
        parsed = self._parse_plot_click_data(click_data, "锤速对比图", 8)
        if not parsed:
            return current_style, [], no_update
            
        customdata = parsed['customdata']
        key_id = int(customdata[0])
        algorithm_name = customdata[1]
        record_index = customdata[6]
        replay_index = customdata[7]
        
        # 计算中心时间
        center_time_ms = self._calculate_center_time_for_note_pair(backend, record_index, replay_index, algorithm_name)
        
        point_info = {
            'key_id': key_id,
            'algorithm_name': algorithm_name,
            'record_idx': record_index,
            'replay_idx': replay_index,
            'source_plot_id': 'hammer-velocity-comparison-plot',
            'center_time_ms': center_time_ms
        }
        
        # 生成详细曲线图
        figures = self._generate_key_delay_detail_plots(backend, {
            'algorithm_name': algorithm_name,
            'record_index': record_index,
            'replay_index': replay_index
        })
        
        if figures[2]: # combined_figure
            return self._create_modal_response(figures[2], point_info, height='800px')
            
        return current_style, [], no_update

    def _validate_velocity_comparison_prerequisites(self, backend: PianoAnalysisBackend) -> bool:
        """验证预览条件"""
        mode, algorithm_count = backend.get_current_analysis_mode()
        return mode != "none"
    
    def _collect_velocity_comparison_data(self, backend: PianoAnalysisBackend) -> List[Dict[str, Any]]:
        """收集锤速对比数据"""
        velocity_data = []
        mode, count = backend.get_current_analysis_mode()
        
        if mode == "multi":
            active_algorithms = backend.multi_algorithm_manager.get_active_algorithms()
            for algorithm in active_algorithms:
                velocity_data.extend(self._extract_velocity_data_from_precision_matches(algorithm))
        elif mode == "single":
            # 伪造一个算法对象以复用逻辑
            class TempAlg:
                def __init__(self, analyzer):
                    self.analyzer = analyzer
                    self.metadata = type('Meta', (), {'algorithm_name': '单算法'})()
            velocity_data.extend(self._extract_velocity_data_from_precision_matches(TempAlg(backend._get_current_analyzer())))
            
        return velocity_data
    
    def _extract_velocity_data_from_precision_matches(self, algorithm) -> List[Dict[str, Any]]:
        """从精确匹配对中提取锤速数据"""
        if not algorithm.analyzer or not algorithm.analyzer.note_matcher:
            return []
        
        matched_pairs = algorithm.analyzer.note_matcher.matched_pairs
        velocity_data = []
        
        for record_note, replay_note, match_type, _ in matched_pairs:
            # 只处理精确匹配
            if match_type not in [MatchType.EXCELLENT, MatchType.GOOD, MatchType.FAIR]:
                continue
                
            rec_v = record_note.first_hammer_velocity
            rep_v = replay_note.first_hammer_velocity
            
            if rec_v is None or rep_v is None:
                continue
                
            velocity_data.append({
                'key_id': record_note.id,
                'algorithm_name': algorithm.metadata.algorithm_name,
                'record_velocity': rec_v,
                'replay_velocity': rep_v,
                'record_hammer_time_ms': record_note.first_hammer_time,
                'replay_hammer_time_ms': replay_note.first_hammer_time,
                'record_index': record_note.uuid,
                'replay_index': replay_note.uuid,
                'absolute_delay': (replay_note.key_on_ms - record_note.key_on_ms)
            })
        
        return velocity_data
    
    def _create_velocity_comparison_plot(self, velocity_data: List[Dict[str, Any]]) -> Figure:
        """创建对比散点图"""
        fig = go.Figure()
        algorithm_groups = {}
        for item in velocity_data:
            alg = item['algorithm_name']
            if alg not in algorithm_groups: algorithm_groups[alg] = []
            algorithm_groups[alg].append(item)
            
        colors = ['blue', 'red', 'green', 'orange', 'purple', 'brown']
        for idx, (alg_name, data) in enumerate(algorithm_groups.items()):
            color = colors[idx % len(colors)]
            
            x_vals = [d['key_id'] for d in data]
            y_vals = [d['replay_velocity'] - d['record_velocity'] for d in data]
            custom_data = [[d['key_id'], d['algorithm_name'], d['record_velocity'], d['replay_velocity'], 
                           y_vals[i], d['absolute_delay'], d['record_index'], d['replay_index']] for i, d in enumerate(data)]
            
            fig.add_trace(go.Scattergl(
                x=x_vals, y=y_vals, mode='markers',
                name=f'{alg_name} ({len(data)})',
                marker=dict(color=color, size=8, opacity=0.7),
                customdata=custom_data,
                hovertemplate='按键: %{x}<br>差值: %{y:+.0f}<extra></extra>'
            ))
            
        fig.update_layout(
            title="锤速对比图 (播放 - 录制)",
            xaxis_title="按键ID",
            yaxis_title="锤速差值",
            plot_bgcolor='white'
        )
        return fig
