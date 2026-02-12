"""
绘图服务 - 负责所有图表生成的统一入口

将绘图逻辑从 PianoAnalysisBackend 中分离，提供清晰的绘图服务接口
"""
from typing import Any, Dict, List, Optional, Tuple, Union
import logging

logger = logging.getLogger(__name__)


class PlotService:
    """
    绘图服务类 - 统一管理所有图表生成
    
    职责：
    1. 协调单算法和多算法绘图生成器
    2. 处理算法激活状态
    3. 生成各类图表（时间序列、直方图、散点图、瀑布图等）
    """
    
    def __init__(self, backend):
        """
        初始化绘图服务
        
        Args:
            backend: PianoAnalysisBackend 实例
        """
        self.backend = backend
        self.logger = logger
    
    # ==================== 属性代理与辅助 ====================
    
    @property
    def plot_generator(self):
        """单算法绘图生成器"""
        return self.backend.plot_generator
    
    @property
    def multi_plot_gen(self):
        """多算法绘图生成器代理 (统一简称)"""
        return self.backend.multi_algorithm_plot_generator
    
    @property
    def multi_algorithm_manager(self):
        """多算法管理器"""
        return self.backend.multi_algorithm_manager
    
    @property
    def force_curve_analyzer(self):
        """力度曲线分析器"""
        return self.backend.force_curve_analyzer
    
    def _get_active_algs(self) -> List[Any]:
        """获取活跃算法列表"""
        return self.backend.get_active_algorithms()

    def _get_active_algs_or_empty_plot(self, message: str = "没有激活的算法") -> Union[List[Any], Any]:
        """快速获取算法列表，如果没有则返回空图表"""
        algs = self._get_active_algs()
        if not algs:
            return self.plot_generator._create_empty_plot(message)
        return algs

    def _get_current_analyzer(self, algorithm_name: Optional[str] = None):
        """获取当前分析器"""
        return self.backend._get_current_analyzer(algorithm_name)
    
    # ==================== 时间序列与分布图 ====================
    
    def generate_delay_time_series_plot(self) -> Any:
        """
        生成延时时间序列图（支持单算法和多算法模式）
        x轴：时间（record_keyon，转换为ms）
        y轴：延时（keyon_offset，转换为ms）
        数据来源：所有已匹配的按键对，按时间顺序排列
        """
        algs = self._get_active_algs()

        if not algs:
            return {
                'raw_delay_plot': self.plot_generator._create_empty_plot("没有激活的算法"),
                'relative_delay_plot': self.plot_generator._create_empty_plot("没有激活的算法")
            }

        self.logger.info(f"处理 {len(algs)} 个激活算法")
        return self.multi_plot_gen.generate_multi_algorithm_delay_time_series_plot(
            algs
        )

    def generate_delay_histogram_plot(self) -> Any:
        """
        生成延时分布直方图，并叠加正态拟合曲线（基于绝对时延）。

        数据筛选：只使用误差≤50ms的按键数据
        绝对时延 = keyon_offset（直接测量值）
        - 反映算法的实际延时表现
        - 与阈值设定（20/50ms）对应
        """
        res = self._get_active_algs_or_empty_plot()
        return self.multi_plot_gen.generate_multi_algorithm_delay_histogram_plot(res) if isinstance(res, list) else res

    def generate_offset_alignment_plot(self) -> Any:
        """生成偏移对齐分析柱状图 - 键位为横坐标，中位数、均值、标准差为纵坐标，分4个子图显示（支持单算法和多算法模式）"""
        res = self._get_active_algs_or_empty_plot()
        return self.multi_plot_gen.generate_multi_algorithm_offset_alignment_plot(res) if isinstance(res, list) else {}

    # ==================== 散点图 ====================
    
    def generate_key_delay_zscore_scatter_plot(self) -> Any:
        """
        生成按键与延时Z-Score标准化散点图（支持单算法和多算法模式）
        x轴：按键ID（key_id）
        y轴：延时的Z-Score标准化值
        点的颜色：根据延时大小着色（深蓝→浅蓝→绿→黄→橙→红）
        """
        res = self._get_active_algs_or_empty_plot()
        return self.multi_plot_gen.generate_multi_algorithm_key_delay_zscore_scatter_plot(res) if isinstance(res, list) else res

    def generate_single_key_delay_comparison_plot(self, key_id: int) -> Any:
        """
        生成单键多曲延时对比图
        
        Args:
            key_id: 要对比的按键ID
        """
        res = self._get_active_algs_or_empty_plot()
        return self.multi_plot_gen.generate_single_key_delay_comparison_plot(res, key_id) if isinstance(res, list) else res

    def generate_key_delay_scatter_plot(
        self, 
        only_common_keys: bool = False,
        selected_algorithm_names: List[str] = None
    ) -> Any:
        """
        生成按键与延时的散点图（支持单算法和多算法模式）
        x轴：按键ID（key_id）
        y轴：延时（keyon_offset，转换为ms）
        点的颜色：根据延时大小着色（深蓝→浅蓝→绿→黄→橙→红）
        数据来源：所有已匹配的按键对
        """
        res = self._get_active_algs_or_empty_plot()
        if not isinstance(res, list): return res
        return self.multi_plot_gen.generate_multi_algorithm_key_delay_scatter_plot(
            res, only_common_keys=only_common_keys, selected_algorithm_names=selected_algorithm_names)

    def generate_hammer_velocity_delay_scatter_plot(self) -> Any:
        """
        生成锤速与延时的散点图（支持单算法和多算法模式）
        x轴：锤速（播放锤速）
        y轴：延时（keyon_offset，转换为ms）
        """
        res = self._get_active_algs_or_empty_plot()
        return self.multi_plot_gen.generate_multi_algorithm_hammer_velocity_delay_scatter_plot(res) if isinstance(res, list) else res

    def generate_hammer_velocity_relative_delay_scatter_plot(self) -> Any:
        """
        生成锤速与相对延时的散点图（支持单算法和多算法模式）
        x轴：log₁₀(锤速)（播放锤速的对数值）
        y轴：相对延时（去除平均延时后的延时）
        """
        res = self._get_active_algs_or_empty_plot()
        return self.multi_plot_gen.generate_multi_algorithm_hammer_velocity_relative_delay_scatter_plot(res) if isinstance(res, list) else res

    def generate_key_hammer_velocity_scatter_plot(self) -> Any:
        """
        生成按键与锤速的散点图，颜色表示延时（支持单算法和多算法模式）
        x轴：按键ID（key_id）
        y轴：锤速（播放锤速）
        点的颜色：根据延时大小着色
        """
        res = self._get_active_algs_or_empty_plot()
        return self.multi_plot_gen.generate_multi_algorithm_key_hammer_velocity_scatter_plot(res) if isinstance(res, list) else res

    def generate_key_force_interaction_plot(self) -> Any:
        """
        生成按键-力度交互效应图
        
        显示不同按键在不同力度下的延时表现
        x轴：log₁₀(播放锤速)
        y轴：延时 (ms)
        不同颜色表示不同算法/按键
        """
        res = self._get_active_algs_or_empty_plot()
        if not isinstance(res, list): return res
        # 获取交互分析结果并生成图表
        analysis_result = self.backend.get_key_force_interaction_analysis()
        return self.plot_generator.generate_key_force_interaction_plot(analysis_result)

    # ==================== 瀑布图 ====================
    
    def generate_waterfall_plot(self, data_types: List[str] = None, key_ids: List[int] = None, key_filter=None) -> Any:
        """生成瀑布图（根据SPMID文件数量自动处理）

        Args:
            data_types: 要显示的数据类型列表，默认显示所有类型
            key_ids: 要显示的按键ID列表，默认显示所有按键
            key_filter: 按键筛选条件
        """
        algs = self._get_active_algs()
        if not algs: return self.plot_generator._create_empty_plot("没有激活的算法")

        # 准备数据
        analyzers = [alg.analyzer for alg in algs if alg.analyzer]
        names = [alg.metadata.algorithm_name for alg in algs]
        k_filter = key_filter or (self.backend.key_filter.key_filter if self.backend.key_filter else None)
        
        self.logger.info(f"处理 {len(algs)} 个SPMID文件，数据类型: {data_types}，按键ID: {key_ids}")
        return self.multi_plot_gen.generate_unified_waterfall_plot(
            self.backend,                # 后端实例
            analyzers,                   # 分析器列表
            names,             # 算法名称列表
            k_filter,  # 按键过滤器
            data_types,                 # 数据类型选择
            key_ids                     # 按键ID选择
        )

    def get_waterfall_key_statistics(self, data_types: List[str] = None) -> Dict[str, Any]:
        """获取瀑布图按键统计信息
        
        Args:
            data_types: 数据类型列表，如果为None则统计所有类型
        """
        algs = self._get_active_algs()
        if not algs: return {'available_keys': [], 'summary': {}}

        analyzers = [alg.analyzer for alg in algs if alg.analyzer]
        names = [alg.metadata.algorithm_name for alg in algs]

        return self.multi_plot_gen.get_waterfall_key_statistics(
            self.backend, analyzers, names, data_types
        )

    # ==================== 详细图表（点击交互） ====================

    def _find_detail_notes(self, analyzer, record_index, replay_index, is_record=None):
        """统一查找详情音符对象的内部方法"""
        if not analyzer or not analyzer.note_matcher:
            return None, None
            
        # 1. 尝试通过 UUID 精确对查找 (如果两个索引都提供)
        if record_index is not None and replay_index is not None:
            matched = analyzer.note_matcher.find_matched_pair_by_uuid(record_index, replay_index)
            if matched:
                return matched[0], matched[1]
            
        # 1.1 扩展查找：如果只有 record_index，寻找任何匹配到该 record 的对 (用于多算法对比)
        if record_index is not None:
            # 在匹配对中搜索
            for rec, rep, match_type, error_ms in analyzer.note_matcher.matched_pairs:
                if str(getattr(rec, 'uuid', '')) == str(record_index):
                    return rec, rep
            
            # 在丢锤中搜索 (录制侧有，回放侧无)
            r_note = next((n for n in analyzer.drop_hammers if str(getattr(n, 'uuid', n.offset)) == str(record_index)), None)
            if r_note:
                return r_note, None

        # 1.2 扩展查找：如果只有 replay_index，寻找任何匹配到该 replay 的对
        if replay_index is not None:
            # 在匹配对中搜索
            for rec, rep, match_type, error_ms in analyzer.note_matcher.matched_pairs:
                if str(getattr(rep, 'uuid', '')) == str(replay_index):
                    return rec, rep
            
            # 在多锤中搜索 (录制侧无，回放侧有)
            p_note = next((n for n in analyzer.multi_hammers if str(getattr(n, 'uuid', n.offset)) == str(replay_index)), None)
            if p_note:
                return None, p_note
            
        # 2. 尝试备选方案：通过 Index/Offset 查找 (兼容单算法模式)
        if is_record is not None:
            pairs = analyzer.get_matched_pairs()
            for r_n, p_n in pairs:
                if (is_record and r_n.offset == record_index) or (not is_record and p_n.offset == replay_index):
                    return r_n, p_n
            
        return None, None

    def generate_scatter_detail_plot_by_indices(self, record_index: int, replay_index: int) -> Tuple[Any, Any, Any]:
        """
        根据record_index和replay_index生成散点图点击的详细曲线图 (单算法模式)

        Args:
            record_index: 录制音符索引
            replay_index: 播放音符索引

        Returns:
            Tuple[Any, Any, Any]: (录制音符图, 播放音符图, 对比图)
        """
        # 委托给多算法通用逻辑，algorithm_name=None 表示单算法模式
        return self.generate_multi_algorithm_scatter_detail_plot_by_indices(None, record_index, replay_index)

    def generate_multi_algorithm_scatter_detail_plot_by_indices(
        self, algorithm_name: Optional[str], record_index: Any, replay_index: Any
    ) -> Tuple[Any, Any, Any]:
        """
        多算法模式下，根据算法名和索引生成散点图点击的详细曲线图
        此方法也作为单算法模式的通用入口 (当algorithm_name为None时)

        Args:
            algorithm_name: 算法名称 (None表示单算法模式)
            record_index: 录制音符索引或UUID
            replay_index: 播放音符索引或UUID

        Returns:
            Tuple[Any, Any, Any]: (录制音符图, 播放音符图, 对比图)
        """
        analyzer = self._get_current_analyzer(algorithm_name)
        r_note, p_note = self._find_detail_notes(analyzer, record_index, replay_index)
        
        if not r_note and not p_note:
            self.logger.warning(f"无法定位音符 (算法={algorithm_name}): record={record_index}, replay={replay_index}")
            return None, None, None

        # 计算平均延时视图
        mean_delays = {}
        mean_delay_val = 0.0
        if analyzer:
            mean_error_0_1ms = analyzer.get_mean_error()
            mean_delay_val = mean_error_0_1ms / 10.0  # 转换为毫秒
            mean_delays[algorithm_name or 'default'] = mean_delay_val

        # 确保我们有录制侧的标识符，以便在其他算法中寻找对应点
        search_record_uuid = record_index
        if search_record_uuid is None and r_note:
            search_record_uuid = getattr(r_note, 'uuid', None)

        # 收集交叉比对音符 (仅在多算法模式下有用)
        others = []
        if algorithm_name and self.backend.multi_algorithm_manager:
            active_algs = self.backend.multi_algorithm_manager.get_active_algorithms()
            for alg in active_algs:
                if alg.metadata.algorithm_name == algorithm_name: continue
                if not alg.analyzer: continue
                
                try:
                    alg_mean_error = alg.analyzer.get_mean_error()
                    mean_delays[alg.metadata.algorithm_name] = alg_mean_error / 10.0
                except Exception:
                    mean_delays[alg.metadata.algorithm_name] = 0.0 # Default if error
                
                # 寻找其他算法中匹配到同一录制UUID的播放音符
                if search_record_uuid is not None:
                    _, other_p = self._find_detail_notes(alg.analyzer, search_record_uuid, None)
                    if other_p: 
                        others.append((alg.metadata.algorithm_name, other_p))

        # 生成结果
        f1 = self.plot_generator.generate_note_comparison_plot(r_note, None, algorithm_name=algorithm_name, mean_delays=mean_delays)
        f2 = self.plot_generator.generate_note_comparison_plot(None, p_note, algorithm_name=algorithm_name, mean_delays=mean_delays)
        f_comb = self.plot_generator.generate_note_comparison_plot(r_note, p_note, algorithm_name=algorithm_name, 
                                                                 other_algorithm_notes=others, mean_delays=mean_delays)
        return f1, f2, f_comb

    def generate_multi_algorithm_detail_plot_by_index(self, algorithm_name: str, index: int, is_record: bool) -> Tuple[Any, Any, Any]:
        """
        多算法模式下，根据算法名和单个索引生成瀑布图点击的详细曲线图

        Args:
            algorithm_name: 算法名称
            index: 音符索引（录制或播放）
            is_record: True表示index是录制索引，False表示播放索引

        Returns:
            Tuple[Any, Any, Any]: (录制音符图, 播放音符图, 对比图)
        """
        # 委托给中心逻辑，将index映射到record_index或replay_index
        return self.generate_multi_algorithm_scatter_detail_plot_by_indices(
            algorithm_name, index if is_record else None, index if not is_record else None)

    def generate_multi_algorithm_error_detail_plot_by_index(self, algorithm_name: str, index: int, is_record: bool) -> Tuple[Any, Any, Any]:
        """
        多算法模式下，根据算法名和索引生成错误详情的详细曲线图（用于丢锤/多锤详情）

        Args:
            algorithm_name: 算法名称
            index: 音符索引（录制或播放）
            is_record: True表示index是录制索引，False表示播放索引

        Returns:
            Tuple[Any, Any, Any]: (录制音符图, 播放音符图, 对比图)
        """
        # 委托给中心逻辑，将index映射到record_index或replay_index
        return self.generate_multi_algorithm_scatter_detail_plot_by_indices(
            algorithm_name, index if is_record else None, index if not is_record else None)

    # ==================== 相对延时分布图 ====================
    
    def generate_relative_delay_distribution_plot(self) -> Any:
        """
        生成同种算法不同曲子的相对延时分布图

        Returns:
            plotly Figure对象
        """
        res = self._get_active_algs_or_empty_plot()
        return self.multi_plot_gen.generate_relative_delay_distribution_plot(res) if isinstance(res, list) else res
