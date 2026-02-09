"""
延时关系分析模块
负责分析延时与按键、延时与锤速之间的关系
"""

from typing import Dict, List, Any
from collections import defaultdict
from utils.logger import Logger

logger = Logger.get_logger()


class DelayAnalysis:
    """延时关系分析器 - 分析延时与按键、延时与锤速之间的关系"""
    
    def __init__(self, analyzer=None):
        """
        初始化延时分析器
        
        Args:
            analyzer: SPMIDAnalyzer实例
        """
        self.analyzer = analyzer
    
    def analyze_key_force_interaction(self) -> Dict[str, Any]:
        """
        生成按键-力度交互效应图所需的数据
        """
        try:
            if not self.analyzer:
                return self._create_empty_interaction_result("分析器不存在")

            # 直接从 analyzer 中获取匹配对
            matched_pairs = getattr(self.analyzer, 'matched_pairs', [])
            if not matched_pairs:
                return self._create_empty_interaction_result("没有匹配数据")
            
            # 获取整体平均延时 (ms)
            if hasattr(self.analyzer, 'get_mean_error'):
                mean_delay = self.analyzer.get_mean_error() / 10.0
            else:
                mean_delay = 0.0

            # 按按键分组收集数据
            key_groups = defaultdict(lambda: {
                'forces': [], 'delays': [], 'absolute_delays': [],
                'record_indices': [], 'replay_indices': []
            })
            
            for rec_note, rep_note, _, _ in matched_pairs:
                # 提取力度 (播放锤速)
                force = rep_note.first_hammer_velocity
                if force is None or force <= 0:
                    continue
                
                # 计算延时 (ms)
                abs_delay = rep_note.key_on_ms - rec_note.key_on_ms
                
                group = key_groups[rec_note.id]
                group['forces'].append(float(force))
                group['delays'].append(float(abs_delay - mean_delay))  # 相对延时
                group['absolute_delays'].append(float(abs_delay))
                group['record_indices'].append(rec_note.uuid)
                group['replay_indices'].append(rep_note.uuid)
            
            if not key_groups:
                return self._create_empty_interaction_result("没有有效数据")

            # 封装结果
            interaction_data = {
                key_id: {
                    **vals,
                    'mean_delay': float(mean_delay),
                    'sample_count': len(vals['forces'])
                }
                for key_id, vals in key_groups.items()
            }
            
            logger.info(f"按键-力度交互分析完成，处理了 {len(interaction_data)} 个按键")
            return {
                'status': 'success',
                'interaction_plot_data': {
                    'key_data': interaction_data,
                    'mean_delay': float(mean_delay),
                    'message': f'已处理 {len(interaction_data)} 个按键的数据'
                }
            }
            
        except Exception as e:
            logger.error(f"按键-力度交互分析失败: {e}", exc_info=True)
            return self._create_empty_interaction_result(f"分析失败: {str(e)}")
    
    def _create_empty_interaction_result(self, message: str) -> Dict[str, Any]:
        """反馈错误结果"""
        return {
            'status': 'error',
            'message': message,
            'interaction_plot_data': {}
        }
