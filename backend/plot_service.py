"""
绘图服务 - 负责所有图表生成的统一入口

将绘图逻辑从 PianoAnalysisBackend 中分离，提供清晰的绘图服务接口
"""
from typing import Any, Dict, List, Optional, Tuple
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
            backend: PianoAnalysisBackend 实例，提供数据访问接口
        """
        self.backend = backend
        self.logger = logger
    
    @property
    def plot_generator(self):
        """单算法绘图生成器"""
        return self.backend.plot_generator
    
    @property
    def multi_algorithm_plot_generator(self):
        """多算法绘图生成器"""
        return self.backend.multi_algorithm_plot_generator
    
    @property
    def multi_algorithm_manager(self):
        """多算法管理器"""
        return self.backend.multi_algorithm_manager
    
    @property
    def force_curve_analyzer(self):
        """力度曲线分析器"""
        return self.backend.force_curve_analyzer
    
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
        active_algorithms = self.backend.get_active_algorithms()

        if not active_algorithms:
            return {
                'raw_delay_plot': self.plot_generator._create_empty_plot("没有激活的算法"),
                'relative_delay_plot': self.plot_generator._create_empty_plot("没有激活的算法")
            }

        self.logger.info(f"处理 {len(active_algorithms)} 个激活算法")
        return self.multi_algorithm_plot_generator.generate_multi_algorithm_delay_time_series_plot(
            active_algorithms
        )

    def generate_delay_histogram_plot(self) -> Any:
        """
        生成延时分布直方图，并叠加正态拟合曲线（基于绝对时延）。

        数据筛选：只使用误差≤50ms的按键数据
        绝对时延 = keyon_offset（直接测量值）
        - 反映算法的实际延时表现
        - 与阈值设定（20/50ms）对应
        """
        active_algorithms = self.backend.get_active_algorithms()

        if not active_algorithms:
            return self.plot_generator._create_empty_plot("没有激活的算法")

        return self.multi_algorithm_plot_generator.generate_multi_algorithm_delay_histogram_plot(
            active_algorithms
        )

    def generate_offset_alignment_plot(self) -> Any:
        """生成偏移对齐分析柱状图 - 键位为横坐标，中位数、均值、标准差为纵坐标，分4个子图显示（支持单算法和多算法模式）"""
        active_algorithms = self.backend.get_active_algorithms()

        if not active_algorithms:
            return {}

        return self.multi_algorithm_plot_generator.generate_multi_algorithm_offset_alignment_plot(
            active_algorithms
        )

    # ==================== 散点图 ====================
    
    def generate_key_delay_zscore_scatter_plot(self) -> Any:
        """
        生成按键与延时Z-Score标准化散点图（支持单算法和多算法模式）
        x轴：按键ID（key_id）
        y轴：延时的Z-Score标准化值
        点的颜色：根据延时大小着色（深蓝→浅蓝→绿→黄→橙→红）
        """
        active_algorithms = self.backend.get_active_algorithms()

        if not active_algorithms:
            return self.plot_generator._create_empty_plot("没有激活的算法")

        return self.multi_algorithm_plot_generator.generate_multi_algorithm_key_delay_zscore_scatter_plot(
            active_algorithms
        )

    def generate_single_key_delay_comparison_plot(self, key_id: int) -> Any:
        """
        生成单键多曲延时对比图
        
        Args:
            key_id: 要对比的按键ID
        """
        active_algorithms = self.backend.get_active_algorithms()

        if not active_algorithms:
            return self.plot_generator._create_empty_plot("没有激活的算法")

        return self.multi_algorithm_plot_generator.generate_single_key_delay_comparison_plot(
            active_algorithms,
            key_id
        )

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
        active_algorithms = self.backend.get_active_algorithms()

        if not active_algorithms:
            return self.plot_generator._create_empty_plot("没有激活的算法")

        return self.multi_algorithm_plot_generator.generate_multi_algorithm_key_delay_scatter_plot(
            active_algorithms,
            only_common_keys=only_common_keys,
            selected_algorithm_names=selected_algorithm_names
        )

    def generate_hammer_velocity_delay_scatter_plot(self) -> Any:
        """
        生成锤速与延时的散点图（支持单算法和多算法模式）
        x轴：锤速（播放锤速）
        y轴：延时（keyon_offset，转换为ms）
        """
        active_algorithms = self.backend.get_active_algorithms()

        if not active_algorithms:
            return self.plot_generator._create_empty_plot("没有激活的算法")

        return self.multi_algorithm_plot_generator.generate_multi_algorithm_hammer_velocity_delay_scatter_plot(
            active_algorithms
        )

    def generate_hammer_velocity_relative_delay_scatter_plot(self) -> Any:
        """
        生成锤速与相对延时的散点图（支持单算法和多算法模式）
        x轴：log₁₀(锤速)（播放锤速的对数值）
        y轴：相对延时（去除平均延时后的延时）
        """
        active_algorithms = self.backend.get_active_algorithms()

        if not active_algorithms:
            return self.plot_generator._create_empty_plot("没有激活的算法")

        return self.multi_algorithm_plot_generator.generate_multi_algorithm_hammer_velocity_relative_delay_scatter_plot(
            active_algorithms
        )

    def generate_key_hammer_velocity_scatter_plot(self) -> Any:
        """
        生成按键与锤速的散点图，颜色表示延时（支持单算法和多算法模式）
        x轴：按键ID（key_id）
        y轴：锤速（播放锤速）
        点的颜色：根据延时大小着色
        """
        active_algorithms = self.backend.get_active_algorithms()

        if not active_algorithms:
            return self.plot_generator._create_empty_plot("没有激活的算法")

        return self.multi_algorithm_plot_generator.generate_multi_algorithm_key_hammer_velocity_scatter_plot(
            active_algorithms
        )

    def generate_key_force_interaction_plot(self) -> Any:
        """
        生成按键-力度交互效应图
        
        显示不同按键在不同力度下的延时表现
        x轴：按键ID
        y轴：延时误差
        不同颜色表示不同力度分组
        """
        active_algorithms = self.backend.get_active_algorithms()

        if not active_algorithms:
            return self.plot_generator._create_empty_plot("没有激活的算法")

        # 获取交互分析结果并生成图表
        analysis_result = self.backend.get_key_force_interaction_analysis()
        return self.plot_generator.generate_key_force_interaction_plot(analysis_result)

    # ==================== 瀑布图 ====================
    
    def generate_waterfall_plot(self) -> Any:
        """生成瀑布图（根据SPMID文件数量自动处理）"""
        active_algorithms = self.backend.get_active_algorithms()

        if not active_algorithms:
            return self.plot_generator._create_empty_plot("没有激活的算法")

        # 准备数据
        analyzers = [alg.analyzer for alg in active_algorithms if alg.analyzer]
        algorithm_names = [alg.metadata.algorithm_name for alg in active_algorithms]

        # 使用多算法图表生成器，自动处理单/多文件
        self.logger.info(f"处理 {len(active_algorithms)} 个SPMID文件")
        return self.multi_algorithm_plot_generator.generate_unified_waterfall_plot(
            self.backend,                # 后端实例
            analyzers,                   # 分析器列表
            algorithm_names,             # 算法名称列表
            self.backend.time_filter,    # 时间过滤器
            self.backend.key_filter.key_filter if self.backend.key_filter else None  # 按键过滤器
        )

    def generate_watefall_conbine_plot(self, key_on: float, key_off: float, key_id: int) -> Tuple[Any, Any, Any]:
        """生成瀑布图对比图"""
        return self.plot_generator.generate_watefall_conbine_plot(key_on, key_off, key_id)
    
    def generate_watefall_conbine_plot_by_index(self, index: int, is_record: bool) -> Tuple[Any, Any, Any]:
        """根据索引生成瀑布图对比图"""
        return self.plot_generator.generate_watefall_conbine_plot_by_index(index, is_record)

    # ==================== 详细图表（点击交互） ====================
    
    def generate_scatter_detail_plot_by_indices(self, record_index: int, replay_index: int) -> Tuple[Any, Any, Any]:
        """
        根据record_index和replay_index生成散点图点击的详细曲线图

        Args:
            record_index: 录制音符索引
            replay_index: 播放音符索引

        Returns:
            Tuple[Any, Any, Any]: (录制音符图, 播放音符图, 对比图)
        """
        analyzer = self._get_current_analyzer()
        if not analyzer or not analyzer.note_matcher:
            self.logger.warning("分析器或匹配器不存在，无法生成详细曲线图")
            return None, None, None
        
        # 从precision_matched_pairs中查找对应的Note对象（确保只使用精确匹配对）
        precision_matched_pairs = analyzer.note_matcher.precision_matched_pairs
        record_note = None
        play_note = None
        
        for r_idx, p_idx, r_note, p_note in precision_matched_pairs:
            if r_idx == record_index and p_idx == replay_index:
                record_note = r_note
                play_note = p_note
                break
        
        if record_note is None or play_note is None:
            self.logger.warning(f"未找到匹配对: record_index={record_index}, replay_index={replay_index}")
            return None, None, None

        # 计算平均延时
        mean_delays = {}
        mean_delay_val = 0.0
        analyzer = self._get_current_analyzer()
        if analyzer:
            mean_error_0_1ms = analyzer.get_mean_error()
            mean_delay_val = mean_error_0_1ms / 10.0  # 转换为毫秒
            mean_delays['default'] = mean_delay_val
        else:
            self.logger.warning("无法获取单算法模式的平均延时")

        # 使用plot_generator生成详细图表
        detail_figure1 = self.plot_generator.generate_note_comparison_plot(record_note, None, mean_delays=mean_delays)
        detail_figure2 = self.plot_generator.generate_note_comparison_plot(None, play_note, mean_delays=mean_delays)
        detail_figure_combined = self.plot_generator.generate_note_comparison_plot(record_note, play_note, mean_delays=mean_delays)
        
        # 生成全过程处理图
        processing_stages_figure = None
        if self.force_curve_analyzer:
            try:
                comparison_result = self.force_curve_analyzer.compare_curves(
                    record_note, 
                    play_note,
                    mean_delay=mean_delay_val
                )
                if comparison_result:
                    processing_stages_figure = self.force_curve_analyzer.visualize_all_processing_stages(comparison_result)
            except Exception as e:
                self.logger.error(f"生成全过程处理图失败: {e}")

        self.logger.info(f"生成散点图点击的详细曲线图，record_index={record_index}, replay_index={replay_index}")
        return detail_figure1, detail_figure2, detail_figure_combined
    
    def generate_multi_algorithm_scatter_detail_plot_by_indices(
        self,
        algorithm_name: str,
        record_index: int,
        replay_index: int
    ) -> Tuple[Any, Any, Any]:
        """
        多算法模式下，根据算法名和索引生成散点图点击的详细曲线图

        Args:
            algorithm_name: 算法名称
            record_index: 录制音符索引
            replay_index: 播放音符索引

        Returns:
            Tuple[Any, Any, Any]: (录制音符图, 播放音符图, 对比图)
        """
        # 在多算法模式下，需要指定算法名称来获取分析器
        analyzer = self._get_current_analyzer(algorithm_name)
        if not analyzer or not analyzer.note_matcher:
            self.logger.warning(f"算法 {algorithm_name} 的分析器或匹配器不存在")
            return None, None, None

        # 通过UUID查找对应的Note对象
        matched_pair = analyzer.note_matcher.find_matched_pair_by_uuid(record_index, replay_index)

        if matched_pair is None:
            self.logger.warning(f"未找到匹配对 (算法={algorithm_name}): record_uuid={record_index}, replay_uuid={replay_index}")
            return None, None, None

        record_note, play_note, match_type, error_ms = matched_pair

        # 计算该算法的平均延时
        mean_delays = {}
        mean_delay_val = 0.0
        if analyzer:
            mean_error_0_1ms = analyzer.get_mean_error()
            mean_delay_val = mean_error_0_1ms / 10.0  # 转换为毫秒
            mean_delays[algorithm_name] = mean_delay_val

        # 收集其他算法中匹配到同一个record_index的播放音符
        other_algorithm_notes = []
        active_algorithms = self.backend.multi_algorithm_manager.get_active_algorithms() if self.backend.multi_algorithm_manager else []
        
        if len(active_algorithms) > 1:
            for alg in active_algorithms:
                # 跳过当前算法
                if alg.metadata.algorithm_name == algorithm_name:
                    continue
                
                # 检查该算法是否有有效的分析器和匹配器
                if not alg.analyzer or not alg.analyzer.note_matcher:
                    continue
                
                # 计算该算法的平均延时
                try:
                    alg_mean_error = alg.analyzer.get_mean_error()
                    mean_delays[alg.metadata.algorithm_name] = alg_mean_error / 10.0
                except:
                    mean_delays[alg.metadata.algorithm_name] = 0.0
                
                # 在该算法的匹配对中查找匹配到同一个record_index的播放音符
                alg_precision_pairs = alg.analyzer.note_matcher.precision_matched_pairs
                for r_idx, p_idx, r_note, p_note in alg_precision_pairs:
                    if r_idx == record_index:
                        other_algorithm_notes.append((alg.metadata.algorithm_name, p_note))
                        self.logger.info(f"找到算法 '{alg.metadata.algorithm_name}' 中匹配到 record_index={record_index} 的播放音符")
                        break

        # 使用plot_generator生成详细图表（包含其他算法的播放曲线）
        detail_figure1 = self.plot_generator.generate_note_comparison_plot(
            record_note, None, 
            algorithm_name=algorithm_name,
            other_algorithm_notes=[],  # 只显示录制音符，不显示其他
            mean_delays=mean_delays
        )
        detail_figure2 = self.plot_generator.generate_note_comparison_plot(
            None, play_note, 
            algorithm_name=algorithm_name,
            other_algorithm_notes=[],  # 只显示播放音符，不显示其他
            mean_delays=mean_delays
        )
        detail_figure_combined = self.plot_generator.generate_note_comparison_plot(
            record_note, play_note, 
            algorithm_name=algorithm_name,
            other_algorithm_notes=other_algorithm_notes,  # 组合图显示所有算法
            mean_delays=mean_delays
        )

        self.logger.info(f"生成多算法散点图点击的详细曲线图，算法={algorithm_name}, record_index={record_index}, replay_index={replay_index}, 其他算法数量={len(other_algorithm_notes)}")
        return detail_figure1, detail_figure2, detail_figure_combined

    def generate_multi_algorithm_detail_plot_by_index(
        self,
        algorithm_name: str,
        index: int,
        is_record: bool
    ) -> Tuple[Any, Any, Any]:
        """
        多算法模式下，根据算法名和单个索引生成瀑布图点击的详细曲线图

        Args:
            algorithm_name: 算法名称
            index: 音符索引（录制或播放）
            is_record: True表示index是录制索引，False表示播放索引

        Returns:
            Tuple[Any, Any, Any]: (录制音符图, 播放音符图, 对比图)
        """
        analyzer = self._get_current_analyzer(algorithm_name)
        if not analyzer or not analyzer.note_matcher:
            self.logger.warning(f"算法 {algorithm_name} 的分析器或匹配器不存在")
            return None, None, None

        # 从precision_matched_pairs中查找对应的Note对象
        precision_matched_pairs = analyzer.note_matcher.precision_matched_pairs
        record_note = None
        play_note = None
        
        for r_idx, p_idx, r_note, p_note in precision_matched_pairs:
            if is_record and r_idx == index:
                record_note = r_note
                play_note = p_note
                break
            elif not is_record and p_idx == index:
                record_note = r_note
                play_note = p_note
                break
        
        if record_note is None or play_note is None:
            self.logger.warning(f"未找到匹配对 (算法={algorithm_name}): index={index}, is_record={is_record}")
            return None, None, None

        # 计算该算法的平均延时
        mean_delays = {}
        mean_delay_val = 0.0
        if analyzer:
            mean_error_0_1ms = analyzer.get_mean_error()
            mean_delay_val = mean_error_0_1ms / 10.0
            mean_delays[algorithm_name] = mean_delay_val

        # 生成详细图表
        detail_figure1 = self.plot_generator.generate_note_comparison_plot(record_note, None, mean_delays=mean_delays)
        detail_figure2 = self.plot_generator.generate_note_comparison_plot(None, play_note, mean_delays=mean_delays)
        detail_figure_combined = self.plot_generator.generate_note_comparison_plot(record_note, play_note, mean_delays=mean_delays)

        self.logger.info(f"生成多算法瀑布图点击的详细曲线图，算法={algorithm_name}, index={index}, is_record={is_record}")
        return detail_figure1, detail_figure2, detail_figure_combined

    def generate_multi_algorithm_error_detail_plot_by_index(
        self,
        algorithm_name: str,
        index: int,
        is_record: bool
    ) -> Tuple[Any, Any, Any]:
        """
        多算法模式下，根据算法名和索引生成错误详情的详细曲线图（用于丢锤/多锤详情）

        Args:
            algorithm_name: 算法名称
            index: 音符索引（录制或播放）
            is_record: True表示index是录制索引，False表示播放索引

        Returns:
            Tuple[Any, Any, Any]: (录制音符图, 播放音符图, 对比图)
        """
        analyzer = self._get_current_analyzer(algorithm_name)
        if not analyzer or not analyzer.error_detector:
            self.logger.warning(f"算法 {algorithm_name} 的分析器或错误检测器不存在")
            return None, None, None

        error_detector = analyzer.error_detector
        record_note = None
        play_note = None

        # 搜索所有错误类型的数据
        if is_record:
            # 搜索录制侧错误
            for drop_idx, drop_note in error_detector.drop_hammers:
                if drop_idx == index:
                    record_note = drop_note
                    play_note = None
                    break
            
            if record_note is None:
                for multi_idx, multi_note in error_detector.multi_hammers:
                    if multi_idx == index:
                        record_note = multi_note
                        play_note = None
                        break
        else:
            # 搜索播放侧错误（通常播放侧不会有独立的错误音符）
            # 如果需要显示播放侧的错误，需要根据实际错误检测逻辑调整
            self.logger.warning(f"播放侧错误详情暂不支持: index={index}")
            return None, None, None

        if record_note is None:
            self.logger.warning(f"未找到错误音符 (算法={algorithm_name}): index={index}, is_record={is_record}")
            return None, None, None

        # 计算该算法的平均延时
        mean_delays = {}
        mean_delay_val = 0.0
        if analyzer:
            mean_error_0_1ms = analyzer.get_mean_error()
            mean_delay_val = mean_error_0_1ms / 10.0
            mean_delays[algorithm_name] = mean_delay_val

        # 生成详细图表（只有录制音符，没有播放音符）
        detail_figure1 = self.plot_generator.generate_note_comparison_plot(record_note, None, mean_delays=mean_delays)
        detail_figure2 = self.plot_generator.generate_note_comparison_plot(None, play_note, mean_delays=mean_delays) if play_note else None
        detail_figure_combined = self.plot_generator.generate_note_comparison_plot(record_note, play_note, mean_delays=mean_delays) if play_note else None

        self.logger.info(f"生成多算法错误详情的详细曲线图，算法={algorithm_name}, index={index}, is_record={is_record}")
        return detail_figure1, detail_figure2, detail_figure_combined

    # ==================== 相对延时分布图 ====================
    
    def generate_relative_delay_distribution_plot(self) -> Any:
        """
        生成同种算法不同曲子的相对延时分布图

        Returns:
            plotly Figure对象
        """
        active_algorithms = self.backend.get_active_algorithms()

        if not active_algorithms:
            return self.plot_generator._create_empty_plot("没有激活的算法")

        return self.multi_algorithm_plot_generator.generate_relative_delay_distribution_plot(
            active_algorithms
        )
    
