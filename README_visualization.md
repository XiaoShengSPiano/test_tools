# SPMID音轨数据可视化工具

这个工具可以读取SPMID文件的单个音轨数据并进行可视化，帮助您理解SPMID文件的数据结构。

## 功能特性

- 📊 **多维度可视化**：锤子数据、触后数据、音符分布统计
- 🎨 **颜色编码**：不同音符ID使用不同颜色显示
- 📈 **时间轴分析**：显示绝对时间戳和相对时间戳
- 📋 **详细统计**：提供音轨的完整统计信息
- 💾 **图片导出**：支持PNG格式图片导出

## 使用方法

### 基本用法

```bash
# 可视化录制音轨 (轨道0)
python visualize_spmid_track.py your_file.spmid

# 可视化播放音轨 (轨道1)
python visualize_spmid_track.py your_file.spmid --track 1

# 指定输出文件
python visualize_spmid_track.py your_file.spmid --output my_visualization.png
```

### 命令行参数

- `file_path`: SPMID文件路径 (必需)
- `--track, -t`: 音轨索引，默认为0 (录制音轨)
- `--output, -o`: 输出图片文件路径 (可选)
- `--verbose, -v`: 显示详细信息

### 示例

```bash
# 使用测试文件
python visualize_spmid_track.py test/2025-08-13C大调音阶.spmid

# 可视化播放音轨并保存图片
python visualize_spmid_track.py test/2025-08-13C大调音阶.spmid --track 1 --output playback.png

# 显示详细信息
python visualize_spmid_track.py test/2025-08-13C大调音阶.spmid --verbose
```

## 可视化内容

### 1. 锤子数据图表
- **X轴**: 绝对时间戳 (毫秒)
- **Y轴**: 力度值
- **显示**: 每个锤子的击打时间和力度

### 2. 触后数据图表
- **X轴**: 绝对时间戳 (毫秒)
- **Y轴**: 压力值
- **显示**: 按键后的持续压力变化

### 3. 音符分布统计
- **X轴**: 音符ID (键位1-88)
- **Y轴**: 音符数量
- **显示**: 每个键位被按的次数

## 数据说明

### Note对象结构
```python
@dataclass
class Note:
    offset: int          # 全局时间偏移量
    id: int             # 音符ID (键位1-88)
    finger: int         # 手指编号
    hammers: pd.Series  # 锤子数据 (时间戳+力度值)
    uuid: str           # 唯一标识符
    velocity: int       # 初始力度值
    after_touch: pd.Series  # 触后数据 (时间戳+压力值)
```

### 数据含义
- **offset**: 音符在整个演奏中的开始时间
- **id**: 钢琴键位 (1-88)
- **hammers**: 多次锤击的时间和力度
- **after_touch**: 按键后的持续压力变化
- **velocity**: 按键时的初始力度

## 输出示例

脚本会输出以下信息：
- 音轨统计信息 (音符总数、键位范围、时间范围等)
- 前5个音符的详细信息
- 可视化图表 (显示或保存为PNG文件)

## 快速开始

1. 确保有SPMID文件
2. 运行可视化脚本：
   ```bash
   python visualize_spmid_track.py your_file.spmid
   ```
3. 查看生成的图表和统计信息

## 注意事项

- 需要安装matplotlib、pandas、numpy等依赖
- 中文字体支持需要相应的字体文件
- 大文件可能需要较长的处理时间

