import io
import base64
import platform
import os
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib

matplotlib.use('Agg')
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.font_manager as fm
from matplotlib.gridspec import GridSpec
from utils.logger import Logger

logger = Logger.get_logger()


class PDFReportGenerator:
    """PDF报告生成器 - 修复跨平台中文字体问题"""

    def __init__(self, backend):
        """初始化PDF生成器"""
        self.backend = backend
        # 初始化跨平台中文字体配置
        self.chinese_font = self._setup_chinese_font()

    def _setup_chinese_font(self):
        """只使用项目自带的NotoSansCJKsc-Regular.otf，避免ttc集合字体问题"""
        font_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fonts', 'NotoSansCJKsc-Regular.otf')
        if os.path.exists(font_path):
            try:
                chinese_font = fm.FontProperties(fname=font_path)
            except Exception as e:
                logger.error(f"❌ 项目字体文件加载失败，程序终止: {e}")
                import sys
                sys.exit(1)
        else:
            logger.error("❌ 未找到项目字体文件fonts/NotoSansCJKsc-Regular.otf，程序终止")
            import sys
            sys.exit(1)
        # PDF相关设置
        plt.rcParams['pdf.fonttype'] = 42
        plt.rcParams['font.family'] = 'sans-serif'
        plt.rcParams['axes.unicode_minus'] = False
        plt.rcParams['font.size'] = 10
        plt.rcParams['savefig.dpi'] = 150
        # 字体测试，失败直接退出程序
        try:
            fig, ax = plt.subplots(figsize=(0.1, 0.1))
            ax.text(0.5, 0.5, '测试', fontsize=8, ha='center', fontproperties=chinese_font)
            plt.close(fig)
            logger.info(f"✅ PDF生成器字体配置完成: {font_path}")
        except Exception as e:
            logger.error(f"❌ 字体测试失败，程序终止: {e}")
            import sys
            sys.exit(1)
        return chinese_font

    def generate_pdf_report(self, filename=""):
        """生成中文PDF分析报告"""
        try:
            logger.info("🔄 开始生成中文PDF报告...")

            # 创建内存中的PDF文件
            pdf_buffer = io.BytesIO()

            # 获取当前分析的文件名
            data_source = filename or "未知数据源"

            with PdfPages(pdf_buffer) as pdf:
                logger.info("📊 生成概览页面...")
                # 第一页：数据源和统计概览
                self._create_overview_page(pdf, data_source)

                logger.info("🖼️ 生成每个异常的详细分析页面...")
                # 后续页面：每个异常的详细数据和对比图
                self._create_all_detailed_pages(pdf)

            pdf_buffer.seek(0)
            logger.info("✅ 中文PDF报告生成完成")
            return pdf_buffer.getvalue()
        except Exception as e:
            logger.error(f"❌ PDF生成失败: {e}")
            raise e


    def _create_premium_card(self, ax, x, y, width, height, value, label, color):
        """创建高级卡片 - 专业美观设计"""
        from matplotlib.patches import FancyBboxPatch

        # 卡片基底 - 圆角设计
        rect = FancyBboxPatch((x - width / 2, y - height / 2), width, height,
                              boxstyle='round,pad=0.1,rounding_size=0.05',
                              facecolor='white', edgecolor='#e2e8f0',
                              linewidth=1.5, zorder=1)
        ax.add_patch(rect)

        # 添加渐变背景 - 顶部渐变条
        gradient = plt.Rectangle((x - width / 2, y - height / 2 + height * 0.7), width, height * 0.3,
                                 facecolor=color, alpha=0.15, zorder=0)
        ax.add_patch(gradient)

        # 添加装饰图标 - 左上角
        icon_x = x - width / 2 + 0.05
        icon_y = y + height / 2 - 0.05
        ax.scatter(icon_x, icon_y, s=30, color=color, marker='o', zorder=2)

        # 数值显示 - 优化设计
        ax.text(x, y + height * 0.15, value,
                fontsize=36, fontweight='bold', ha='center', color=color)

        # 标签显示 - 优化设计
        ax.text(x, y - height * 0.15, label,
                fontsize=14, ha='center', color='#4a5568')

        # 添加装饰线条 - 底部
        ax.plot([x - width / 3, x + width / 3], [y - height / 2 + 0.02, y - height / 2 + 0.02],
                color=color, linewidth=2, alpha=0.5)


    def _create_stat_card(self, ax, x, y, width, height, value, label, color):
        """创建统计卡片 - 增强视觉效果"""
        # 卡片背景
        rect = plt.Rectangle((x - width / 2, y - height / 2), width, height,
                             facecolor='white', edgecolor='#e2e8f0',
                             linewidth=1.5, zorder=1)
        ax.add_patch(rect)

        # 添加阴影效果
        shadow = plt.Rectangle((x - width / 2 + 0.01, y - height / 2 - 0.01), width, height,
                               facecolor='#f0f0f0', edgecolor='none', zorder=0)
        ax.add_patch(shadow)

        # 数值显示
        ax.text(x, y + height * 0.15, value,
                fontsize=36, fontweight='bold', ha='center', color=color)

        # 标签显示
        ax.text(x, y - height * 0.15, label,
                fontsize=14, ha='center', color='#4a5568')

    def _create_all_detailed_pages(self, pdf):
        """创建所有异常的详细分析页面 - 修复详细页生成问题"""
        # 确保使用正确的属性名
        if not hasattr(self.backend, 'all_error_notes') or not self.backend.all_error_notes:
            logger.warning("⚠️ 没有检测到异常音符，跳过详细分析页面生成")
            return

        total_errors = len(self.backend.all_error_notes)
        # 总页数 = 概览页(1) + 异常页面数
        total_pages = 1 + total_errors
        logger.info(f"📊 正在生成 {total_errors} 个异常的详细分析页面...")

        for i in range(total_errors):
            try:
                # 显示进度
                if (i + 1) % 3 == 0 or i == 0:
                    logger.info(f"📈 进度: {i + 1}/{total_errors} 个异常分析页面")

                error_note = self.backend.all_error_notes[i]
                # 实际页码 = 概览页(1) + 当前异常索引(i) + 1
                actual_page_num = i + 2
                self._create_single_error_page(pdf, error_note, actual_page_num, total_pages, i + 1)

            except Exception as e:
                logger.error(f"❌ 生成第{i + 1}个异常页面失败: {e}")
                continue

        logger.info(f"✅ 所有 {total_errors} 个异常详细页面生成完成")

    def _draw_compact_comparison(self, ax, error_note, error_type):
        """绘制紧凑的中文对比图"""
        if not error_note.infos:
            ax.text(0.5, 0.5, '无可用数据', ha='center', va='center', fontsize=10,
                   fontproperties=self.chinese_font)
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis('off')
            return

        record_info = error_note.infos[0]

        if len(error_note.infos) == 1:
            # 丢锤情况 - 紧凑布局
            ax.text(0.5, 0.8, '【丢锤检测】', ha='center', va='center',
                    fontsize=14, fontweight='bold', color='#e53e3e',
                    fontproperties=self.chinese_font)

            # 创建中文信息框 - 紧凑布局
            info_text = f'键位: {record_info.keyId}\n录制时间: {record_info.keyOn}-{record_info.keyOff}ms\n时长: {record_info.keyOff - record_info.keyOn}ms\n状态: 播放数据缺失'

            ax.text(0.5, 0.5, info_text, ha='center', va='center', fontsize=10,
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="#ffeeee"),
                    fontproperties=self.chinese_font)
        else:
            # 多锤情况 - 紧凑布局
            play_info = error_note.infos[1]
            ax.text(0.5, 0.9, '【多锤检测】', ha='center', va='center',
                    fontsize=14, fontweight='bold', color='#d69e2e',
                    fontproperties=self.chinese_font)

            # 左右对比显示 - 紧凑布局
            record_text = f'【录制】\n键位: {record_info.keyId}\n开始: {record_info.keyOn}ms\n结束: {record_info.keyOff}ms\n时长: {record_info.keyOff - record_info.keyOn}ms'

            play_text = f'【播放】\n键位: {play_info.keyId}\n开始: {play_info.keyOn}ms\n结束: {play_info.keyOff}ms\n时长: {play_info.keyOff - play_info.keyOn}ms'

            # 添加对比卡片 - 紧凑布局
            self._create_comparison_card(ax, 0.25, 0.6, record_text, '#eeffff')
            self._create_comparison_card(ax, 0.75, 0.6, play_text, '#fffff0')

            # 添加对比箭头 - 紧凑布局
            ax.annotate('', xy=(0.45, 0.6), xytext=(0.55, 0.6),
                        arrowprops=dict(arrowstyle='<->', color='#718096', lw=2))

            # 添加对比结论 - 紧凑布局
            ax.text(0.5, 0.3, f'检测到多锤异常: 录制与播放数据不匹配',
                    ha='center', fontsize=10, color='#d69e2e', fontweight='bold',
                    fontproperties=self.chinese_font)

        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')

    def _create_comparison_card(self, ax, x, y, text, bgcolor):
        """创建对比卡片"""
        # 添加背景
        rect = plt.Rectangle((x-0.12, y-0.15), 0.24, 0.3,
                           facecolor=bgcolor, edgecolor='#cccccc', linewidth=1)
        ax.add_patch(rect)

        # 添加文本
        ax.text(x, y, text, ha='center', va='center', fontsize=9,
               fontproperties=self.chinese_font)

    def _create_detailed_data_display(self, ax, error_note, error_type):
        """创建详细数据显示区域 - 优化表格布局"""
        ax.axis('off')

        # 标题
        ax.text(0.5, 0.95, f'{error_type}异常详细分析',
                fontsize=16, fontweight='bold', ha='center', color='#2c3e50',
                fontproperties=self.chinese_font)

        # 异常描述
        if error_type == '丢锤':
            description = "此异常表示检测到录制数据但未找到对应的播放数据"
            desc_color = '#e53e3e'
        else:
            description = "此异常表示录制数据与播放数据存在不匹配的情况"
            desc_color = '#d69e2e'

        ax.text(0.5, 0.88, description,
                fontsize=12, ha='center', color=desc_color,
                fontproperties=self.chinese_font)

        # 数据容器
        data_y = 0.78
        data_height = 0.7

        # 创建数据区域背景
        rect = plt.Rectangle((0.05, data_y - data_height), 0.9, data_height,
                             facecolor='#f8f9fa', edgecolor='#e2e8f0',
                             linewidth=1, zorder=0)
        ax.add_patch(rect)

        # 显示每个数据项的详细信息
        current_y = data_y - 0.05

        # 使用表格形式展示数据
        cell_height = 0.07  # 减小行高
        cell_width = 0.85
        cell_x = 0.075

        # 表头 - 优化列宽
        headers = ['数据类型', '键位', '按下时间(ms)', '释放时间(ms)', '持续时长(ms)', '均值', '标准差', '最大值', '最小值']
        col_widths = [0.12, 0.08, 0.11, 0.11, 0.11, 0.09, 0.09, 0.09, 0.09]

        # 绘制表头
        x_pos = cell_x
        for i, header in enumerate(headers):
            ax.text(x_pos + col_widths[i] / 2, current_y, header,
                    fontsize=9, ha='center', va='center', fontweight='bold',
                    fontproperties=self.chinese_font)
            x_pos += col_widths[i]

        current_y -= cell_height

        # 数据行
        for i, info in enumerate(error_note.infos):
            data_type = '录制数据' if i == 0 else '播放数据'
            color = '#3498db' if i == 0 else '#e74c3c'

            duration = info.keyOff - info.keyOn if info.keyOff > info.keyOn else 0

            # 获取统计数据
            stats = {'mean': 'N/A', 'std': 'N/A', 'max': 'N/A', 'min': 'N/A'}
            if i < len(error_note.diffs):
                diff = error_note.diffs[i]
                stats = {
                    'mean': f'{diff.mean:.3f}',
                    'std': f'{diff.std:.3f}',
                    'max': f'{diff.max:.3f}',
                    'min': f'{diff.min:.3f}'
                }

            # 数据单元格
            cell_data = [
                data_type,
                str(info.keyId),
                str(info.keyOn),
                str(info.keyOff),
                f'{duration:.1f}',
                stats['mean'],
                stats['std'],
                stats['max'],
                stats['min']
            ]

            # 绘制数据行
            x_pos = cell_x
            for j, data in enumerate(cell_data):
                # 数据类型列特殊着色
                cell_color = color if j == 0 else '#2c3e50'
                # 减小字体大小
                ax.text(x_pos + col_widths[j] / 2, current_y, data,
                        fontsize=8, ha='center', va='center', color=cell_color,
                        fontproperties=self.chinese_font)
                x_pos += col_widths[j]

            current_y -= cell_height

        # 如果没有播放数据，显示说明
        if len(error_note.infos) == 1:
            # 增加间隔，调整说明卡片位置
            current_y -= 0.05  # 在原有位置基础上向下移动，增加间隔
            # 创建说明卡片
            note_rect = plt.Rectangle((cell_x - 0.02, current_y - 0.03), 0.7, 0.08,
                                      facecolor='#fff5f5', edgecolor='#fed7d7',
                                      linewidth=1, zorder=1)
            ax.add_patch(note_rect)

            ax.text(cell_x, current_y, '播放数据信息: 未检测到匹配的播放数据，这是导致丢锤异常的原因',
                    fontsize=9, ha='left', va='center', color='#e53e3e',
                    fontproperties=self.chinese_font)

    def _create_overview_page(self, pdf, data_source):
        """创建中文概览页面 - 优化标题与描述间距，减少空白"""
        fig = plt.figure(figsize=(8.5, 11), facecolor='white')
        # 调整高度比例：减少头部空间，增加主体内容空间
        gs = GridSpec(3, 1, height_ratios=[0.15, 0.7, 0.15], figure=fig, hspace=0.03)

        # 头部区域 - 优化间距
        ax_header = fig.add_subplot(gs[0])
        ax_header.axis('off')

        # 报告标题 - 优化位置和间距
        ax_header.text(0.5, 0.9, 'SPMID数据分析报告',
                       fontsize=22, fontweight='bold', ha='center',
                       color='#1a365d', fontproperties=self.chinese_font)

        # 副标题 - 增加与主标题的间距
        ax_header.text(0.5, 0.5, f'数据源: {data_source}',
                       fontsize=14, ha='center', color='#2d3748',
                       fontproperties=self.chinese_font)

        # 生成时间 - 优化位置
        current_time = datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')
        ax_header.text(0.5, 0.1, f'生成时间: {current_time}',
                       fontsize=10, ha='center', color='#718096',
                       fontproperties=self.chinese_font)

        # 主体区域 - 重新优化布局
        ax_main = fig.add_subplot(gs[1])
        ax_main.axis('off')

        # 顶部分割线
        ax_main.plot([0.1, 0.9], [0.98, 0.98], color='#e2e8f0', linewidth=2)

        # 获取统计数据
        summary = self.backend.get_summary_info()

        # 第一行卡片 - 优化位置和比例
        card_width = 0.32
        card_height = 0.25
        first_row_y = 0.82

        # 总检测数量卡片
        self._create_enhanced_stat_card(ax_main, 0.25, first_row_y, card_width, card_height,
                               summary["detailed_stats"]["total_notes"], '总检测数量', '#2b6cb0')

        # 检测准确率卡片
        self._create_enhanced_stat_card(ax_main, 0.75, first_row_y, card_width, card_height,
                               f'{summary["accuracy"]:.1f}%', '检测准确率', '#38a169')

        # 第二行卡片 - 优化位置
        second_row_y = 0.52

        # 多锤异常卡片
        self._create_enhanced_stat_card(ax_main, 0.25, second_row_y, card_width, card_height,
                               summary["detailed_stats"]["multi_hammers"], '多锤异常', '#d69e2e')

        # 丢锤异常卡片
        self._create_enhanced_stat_card(ax_main, 0.75, second_row_y, card_width, card_height,
                               summary["detailed_stats"]["drop_hammers"], '丢锤异常', '#e53e3e')

        # 中间分割线 - 调整位置
        ax_main.plot([0.1, 0.9], [0.32, 0.32], color='#e2e8f0', linewidth=1)

        # 底部区域 - 报告说明，优化间距
        ax_desc = fig.add_subplot(gs[2])
        ax_desc.axis('off')

        # 报告说明标题 - 增加与上方内容的间距
        ax_desc.text(0.5, 0.95, '报告内容说明',
                     fontsize=14, fontweight='bold', ha='center', color='#1a365d',
                     fontproperties=self.chinese_font)

        # 报告说明内容 - 优化布局和间距
        desc_items = [
            '• 本报告分析了每个检测到的异常项',
            '• 每个异常项单独成页，包含详细数据和对比图',
            '• 多锤异常：录制与播放数据不匹配',
            '• 丢锤异常：录制了但播放时缺失的音符'
        ]

        # 内容布局 - 优化间距
        start_y = 0.8
        line_height = 0.15

        for i, item in enumerate(desc_items):
            y_pos = start_y - i * line_height
            ax_desc.text(0.08, y_pos, item,
                         fontsize=10, ha='left', color='#2d3748',
                         fontproperties=self.chinese_font)

        # 底部签名 - 调整位置
        ax_desc.text(0.5, 0.02, 'SPMID数据分析系统 自动生成',
                     fontsize=8, ha='center', color='#a0aec0',
                     fontproperties=self.chinese_font)

        plt.tight_layout()
        pdf.savefig(fig, bbox_inches='tight', facecolor='white', pad_inches=0.3)
        plt.close()

    def _create_enhanced_stat_card(self, ax, x, y, width, height, value, label, color):
        """创建增强的统计卡片 - 优化视觉效果和间距"""
        # 卡片背景 - 添加圆角和阴影效果
        from matplotlib.patches import FancyBboxPatch

        # 主卡片
        card = FancyBboxPatch((x - width / 2, y - height / 2), width, height,
                              boxstyle='round,pad=0.02,rounding_size=0.03',
                              facecolor='white', edgecolor='#e2e8f0',
                              linewidth=1.5, zorder=2)
        ax.add_patch(card)

        # 阴影效果
        shadow = FancyBboxPatch((x - width / 2 + 0.008, y - height / 2 - 0.008), width, height,
                                boxstyle='round,pad=0.02,rounding_size=0.03',
                                facecolor='#f0f0f0', edgecolor='none', zorder=1, alpha=0.3)
        ax.add_patch(shadow)

        # 顶部装饰条
        top_bar = plt.Rectangle((x - width / 2, y - height / 2 + height * 0.8), width, height * 0.2,
                               facecolor=color, alpha=0.15, zorder=1)
        ax.add_patch(top_bar)

        # 数值显示 - 优化字体和位置
        ax.text(x, y + height * 0.1, str(value),
                fontsize=32, fontweight='bold', ha='center', color=color)

        # 标签显示 - 优化字体和位置
        ax.text(x, y - height * 0.2, label,
                fontsize=13, ha='center', color='#4a5568', fontweight='medium',
                fontproperties=self.chinese_font)

        # 装饰元素
        ax.scatter(x - width / 2 + 0.04, y + height / 2 - 0.04,
                  s=25, color=color, marker='o', zorder=3, alpha=0.7)

    def _create_single_error_page(self, pdf, error_note, page_num, total_pages, error_index):
        """创建单个异常的分析页面 - 修复图表失帧问题"""
        fig = plt.figure(figsize=(8.5, 11), facecolor='white')
        fig.set_dpi(300)
        # 调整高度比例：给对比图更多空间，减少数据区下方空白
        gs = GridSpec(3, 1, height_ratios=[0.1, 0.30, 0.60], figure=fig)

        # 头部区域 - 保持不变
        ax_header = fig.add_subplot(gs[0])
        ax_header.axis('off')

        # 获取异常信息
        error_type = getattr(error_note, 'error_type', '未知异常')
        key_id = error_note.infos[0].keyId if error_note.infos else 'N/A'

        # 标题颜色
        title_color = '#e53e3e' if error_type == '丢锤' else '#d69e2e'

        # 主标题
        ax_header.text(0.5, 0.7, f'键位 {key_id} - {error_type}异常',
                       fontsize=20, fontweight='bold', ha='center', color=title_color,
                       fontproperties=self.chinese_font)

        # 副标题
        ax_header.text(0.5, 0.3, f'第{page_num}页 / 共{total_pages}页 | 异常编号: {error_index}',
                       fontsize=12, ha='center', color='#4a5568',
                       fontproperties=self.chinese_font)

        # 详细数据区域 - 保持不变
        ax_data = fig.add_subplot(gs[1])
        self._create_compact_data_display(ax_data, error_note, error_type)

        # 图表区域 - 增加高度比例解决失帧问题
        ax_plot = fig.add_subplot(gs[2])
        self._create_comparison_plot_for_report(ax_plot, error_note, error_index, error_type)

        plt.tight_layout()
        # 保存时指定较高dpi，避免图像在PDF中被过度压缩导致丢细节
        pdf.savefig(fig, bbox_inches='tight', facecolor='white', pad_inches=0.3, dpi=300)
        plt.close()

    def _create_compact_data_display(self, ax, error_note, error_type):
        """创建紧凑的数据显示区域"""
        ax.axis('off')

        # 标题
        ax.text(0.5, 0.95, f'{error_type}异常详细数据',
                fontsize=16, fontweight='bold', ha='center', color='#000000',
                fontproperties=self.chinese_font)

        # 异常描述
        description = "录制数据与播放数据存在不匹配"
        ax.text(0.5, 0.88, description,
                fontsize=12, ha='center', color='#808080',
                fontproperties=self.chinese_font)

        # 数据表格
        current_y = 0.80
        cell_height = 0.07
        cell_x = 0.075

        # 表头
        headers = ['类型', '键位', '按下(ms)', '释放(ms)', '时长(ms)', '均值', '标准差', '最大值', '最小值']
        col_widths = [0.1, 0.08, 0.1, 0.1, 0.1, 0.09, 0.09, 0.09, 0.09]

        # 绘制表头
        x_pos = cell_x
        for i, header in enumerate(headers):
            ax.text(x_pos + col_widths[i] / 2, current_y, header,
                    fontsize=10, ha='center', va='center', fontweight='bold',
                    fontproperties=self.chinese_font)
            x_pos += col_widths[i]

        current_y -= cell_height

        # 数据行
        colors = ['#3182ce', '#e53e3e']
        for i, info in enumerate(error_note.infos):
            data_type = "录制数据" if i == 0 else "播放数据"
            color = colors[min(i, 1)]
            duration = info.keyOff - info.keyOn

            # 获取统计数据
            stats = {'mean': 'N/A', 'std': 'N/A', 'max': 'N/A', 'min': 'N/A'}
            if i < len(error_note.diffs):
                diff = error_note.diffs[i]
                stats = {
                    'mean': f'{diff.mean:.3f}',
                    'std': f'{diff.std:.3f}',
                    'max': f'{diff.max:.3f}',
                    'min': f'{diff.min:.3f}'
                }

            # 数据单元格
            cell_data = [
                data_type,
                str(info.keyId),
                str(info.keyOn),
                str(info.keyOff),
                f'{duration:.1f}',
                stats['mean'],
                stats['std'],
                stats['max'],
                stats['min']
            ]

            # 绘制数据行
            x_pos = cell_x
            for j, data in enumerate(cell_data):
                cell_color = color if j == 0 else '#2c3e50'
                ax.text(x_pos + col_widths[j] / 2, current_y, data,
                        fontsize=10, ha='center', va='center', color=cell_color,
                        fontweight='medium', fontproperties=self.chinese_font)
                x_pos += col_widths[j]

            current_y -= cell_height

        # 如果没有播放数据，显示说明
        if len(error_note.infos) == 1:
            current_y -= 0.05
            note_rect = plt.Rectangle((cell_x - 0.02, current_y - 0.04), 0.96, 0.1,
                                      facecolor='#fff5f5', edgecolor='#fed7d7',
                                      linewidth=1, zorder=1)
            ax.add_patch(note_rect)

            ax.text(cell_x + 0.02, current_y, '播放数据信息: 未检测到匹配的播放数据，这是导致丢锤异常的原因',
                    fontsize=11, ha='left', va='center', color='#e53e3e',
                    fontweight='medium', fontproperties=self.chinese_font)

    def _create_comparison_plot_for_report(self, ax, error_note, index, error_type):
        """创建对比图 - 修复图片失帧和优化布局"""
        ax.clear()

        key_id = error_note.infos[0].keyId if error_note.infos else 'N/A'

        # 设置图表标题 - 优化间距
        ax.set_title(f'数据对比分析图 - 键位{key_id}',
                     fontsize=16, fontweight='bold', color='#2c3e50', pad=15,
                     fontproperties=self.chinese_font)

        try:
            # 尝试获取真实图像
            image_base64 = self.backend.get_note_image_base64(index - 1)

            if image_base64 and image_base64.startswith('data:image/png;base64,'):
                # 显示真实SPMID对比图 - 修复失帧问题
                image_data = base64.b64decode(image_base64.split(',')[1])
                image_buffer = io.BytesIO(image_data)

                from PIL import Image
                img = Image.open(image_buffer)

                # 移除alpha通道避免PDF显示问题
                if img.mode in ('RGBA', 'LA'):
                    img = img.convert('RGB')

                # 高质量显示 - 禁用插值避免失帧，设置合适的DPI
                ax.imshow(img, aspect='auto', interpolation='nearest',
                         resample=False, extent=[0, 1, 0, 1])

                # 优化布局 - 减少空白
                ax.set_xlim(0, 1)
                ax.set_ylim(0, 1)
                ax.margins(0.02)  # 添加小边距避免裁剪
                ax.axis('off')

            else:
                # 使用备用绘制方法
                self._draw_compact_comparison(ax, error_note, error_type)

        except Exception as e:
            # 错误处理 - 优化布局
            ax.text(0.5, 0.5, f'对比图生成失败\n错误: {str(e)}',
                    ha='center', va='center', fontsize=12,
                    bbox=dict(boxstyle="round,pad=0.5", facecolor="#ffeeee", edgecolor="#ff6b6b"),
                    fontproperties=self.chinese_font)
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis('off')
