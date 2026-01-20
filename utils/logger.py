import logging
import os
import threading
from datetime import datetime
import sys


class LevelFilter(logging.Filter):
    """日志级别过滤器 - 只显示指定级别的日志"""
    
    def __init__(self, level=None, exact_match=False):
        """
        初始化过滤器
        :param level: 日志级别 (例如 logging.DEBUG)
        :param exact_match: 是否精确匹配（True=仅显示该级别，False=显示该级别及以上）
        """
        super().__init__()
        self.level = level
        self.exact_match = exact_match
    
    def filter(self, record):
        if self.level is None:
            return True
        if self.exact_match:
            return record.levelno == self.level
        else:
            return record.levelno >= self.level


class ColoredFormatter(logging.Formatter):
    """彩色日志格式化器"""
    
    # ANSI颜色代码
    COLORS = {
        'DEBUG': '\033[36m',      # 青色
        'INFO': '\033[32m',       # 绿色
        'WARNING': '\033[33m',    # 黄色
        'ERROR': '\033[31m',      # 红色
        'CRITICAL': '\033[35m',   # 紫色
        'RESET': '\033[0m'        # 重置
    }
    
    def format(self, record):
        # 获取原始格式化的消息
        log_message = super().format(record)
        
        # 为错误级别添加红色
        if record.levelno >= logging.ERROR:
            color = self.COLORS['ERROR']
            reset = self.COLORS['RESET']
            return f"{color}{log_message}{reset}"
        
        return log_message


class Logger:
    _logger = None
    _initialized = False
    _init_message_logged = False  # 添加标志防止重复输出初始化信息
    _lock = threading.Lock()  # 添加线程锁
    _log_dir = 'logs'
    _normal_log_file = os.path.join(_log_dir, 'app.log')
    _error_log_file = os.path.join(_log_dir, 'error.log')
    _console_handler = None
    _normal_file_handler = None
    _error_file_handler = None
    _enable_console = True
    _enable_file = True
    _process_id = None  # 记录进程ID

    @classmethod
    def get_logger(cls, enable_console=True, enable_file=True):
        """
        获取logger实例。
        :param enable_console: 是否启用控制台输出
        :param enable_file: 是否启用文件输出
        """
        # 检查进程ID，如果进程ID发生变化，说明是Werkzeug重新加载
        current_process_id = os.getpid()
        if cls._process_id is not None and cls._process_id != current_process_id:
            # 进程ID发生变化，重置初始化状态
            cls._initialized = False
            cls._init_message_logged = False
            cls._logger = None
            cls._console_handler = None
            cls._normal_file_handler = None
            cls._error_file_handler = None
        
        # 使用双重检查锁定模式确保线程安全
        if cls._initialized and cls._logger is not None:
            return cls._logger
        
        with cls._lock:
            # 再次检查，防止多线程同时初始化
            if cls._initialized and cls._logger is not None:
                return cls._logger
            
            # 只在第一次调用时初始化
            if not cls._initialized:
                cls._process_id = current_process_id
                cls._enable_console = enable_console
                cls._enable_file = enable_file
                
                # 创建日志目录
                os.makedirs(cls._log_dir, exist_ok=True)
                
                # 清理根logger的handlers
                root_logger = logging.getLogger()
                for h in list(root_logger.handlers):
                    root_logger.removeHandler(h)
                
                # 创建主logger
                logger = logging.getLogger('piano_app')
                logger.setLevel(logging.DEBUG)  # 设置最低级别为DEBUG
                
                # 创建格式化器
                normal_formatter = logging.Formatter(
                    '[%(asctime)s] %(levelname)s: %(filename)s:%(lineno)d %(funcName)s: %(message)s'
                )
                colored_formatter = ColoredFormatter(
                    '[%(asctime)s] %(levelname)s: %(filename)s:%(lineno)d %(funcName)s: %(message)s'
                )
                
                # 清理现有handlers
                for h in list(logger.handlers):
                    logger.removeHandler(h)
                
                # 创建控制台handler（彩色输出）
                if cls._console_handler is None:
                    cls._console_handler = logging.StreamHandler()
                    cls._console_handler.setFormatter(colored_formatter)
                    cls._console_handler.setLevel(logging.DEBUG)  # 控制台输出所有级别
                
                # 创建正常日志文件handler（记录所有日志）
                if cls._normal_file_handler is None:
                    cls._normal_file_handler = logging.FileHandler(
                        cls._normal_log_file, 
                        encoding='utf-8',
                        mode='a'
                    )
                    cls._normal_file_handler.setFormatter(normal_formatter)
                    cls._normal_file_handler.setLevel(logging.DEBUG)  # 记录所有级别
                
                # 创建错误日志文件handler（只记录错误）
                if cls._error_file_handler is None:
                    cls._error_file_handler = logging.FileHandler(
                        cls._error_log_file, 
                        encoding='utf-8',
                        mode='a'
                    )
                    cls._error_file_handler.setFormatter(normal_formatter)
                    cls._error_file_handler.setLevel(logging.ERROR)  # 只记录ERROR及以上级别
                
                # 添加handlers到logger
                if cls._enable_console:
                    logger.addHandler(cls._console_handler)
                if cls._enable_file:
                    logger.addHandler(cls._normal_file_handler)
                    logger.addHandler(cls._error_file_handler)
                
                cls._logger = logger
                cls._initialized = True
                
                # 记录日志系统初始化信息（只记录一次）
                # 使用文件锁来确保跨进程的唯一性
                init_flag_file = os.path.join(cls._log_dir, '.logger_init_flag')
                if not os.path.exists(init_flag_file):
                    cls._logger.info("[INFO] 日志系统初始化完成")
                    cls._logger.info(f"[INFO] 正常日志文件: {cls._normal_log_file}")
                    cls._logger.info(f"[ERROR] 错误日志文件: {cls._error_log_file}")
                    cls._logger.info(f"[CONSOLE] 控制台输出: {'启用' if cls._enable_console else '禁用'}")
                    cls._logger.info(f"[FILE] 文件输出: {'启用' if cls._enable_file else '禁用'}")
                    # 创建标志文件
                    try:
                        with open(init_flag_file, 'w') as f:
                            f.write(str(current_process_id))
                    except:
                        pass  # 如果无法创建文件，忽略错误
        
        return cls._logger

    @classmethod
    def _reconfigure_handlers(cls):
        """重新配置handlers"""
        if cls._logger is None:
            return
        
        # 移除所有现有handlers
        for h in list(cls._logger.handlers):
            cls._logger.removeHandler(h)
        
        # 重新添加handlers
        if cls._enable_console and cls._console_handler:
            cls._logger.addHandler(cls._console_handler)
        if cls._enable_file:
            if cls._normal_file_handler:
                cls._logger.addHandler(cls._normal_file_handler)
            if cls._error_file_handler:
                cls._logger.addHandler(cls._error_file_handler)

    @classmethod
    def set_console(cls, enable: bool):
        """设置控制台输出开关"""
        cls._enable_console = enable
        cls._reconfigure_handlers()
        if cls._logger:
            cls._logger.info(f"🖥️ 控制台输出已{'启用' if enable else '禁用'}")

    @classmethod
    def set_file(cls, enable: bool):
        """设置文件输出开关"""
        cls._enable_file = enable
        cls._reconfigure_handlers()
        if cls._logger:
            cls._logger.info(f"💾 文件输出已{'启用' if enable else '禁用'}")

    @classmethod
    def set_level(cls, level: str, exact_match: bool = False):
        """
        设置日志级别
        :param level: 日志级别 ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
        :param exact_match: 是否精确匹配（True=仅显示该级别，False=显示该级别及以上）
        """
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        
        if level.upper() not in level_map:
            if cls._logger:
                cls._logger.error(f"❌ 无效的日志级别: {level}")
            return
        
        log_level = level_map[level.upper()]
        
        # 设置logger的级别为DEBUG（最低级别），由filter来控制显示
        if cls._logger:
            cls._logger.setLevel(logging.DEBUG)
        
        # 为所有handlers添加过滤器
        level_filter = LevelFilter(level=log_level, exact_match=exact_match)
        
        if cls._console_handler:
            # 移除旧的过滤器
            cls._console_handler.filters.clear()
            cls._console_handler.addFilter(level_filter)
            cls._console_handler.setLevel(logging.DEBUG)  # handler接收所有级别，由filter控制
        
        if cls._normal_file_handler:
            cls._normal_file_handler.filters.clear()
            cls._normal_file_handler.addFilter(level_filter)
            cls._normal_file_handler.setLevel(logging.DEBUG)
        
        if cls._logger:
            match_type = "仅显示" if exact_match else "显示及以上"
            cls._logger.info(f"📊 日志级别已设置为: {level.upper()} ({match_type})")

    @classmethod
    def get_log_files(cls):
        """获取日志文件路径"""
        return {
            'normal_log': cls._normal_log_file,
            'error_log': cls._error_log_file
        }

    @classmethod
    def clear_logs(cls):
        """清空日志文件"""
        try:
            if os.path.exists(cls._normal_log_file):
                with open(cls._normal_log_file, 'w', encoding='utf-8') as f:
                    f.write('')
            if os.path.exists(cls._error_log_file):
                with open(cls._error_log_file, 'w', encoding='utf-8') as f:
                    f.write('')
            if cls._logger:
                cls._logger.info("🗑️ 日志文件已清空")
        except Exception as e:
            if cls._logger:
                cls._logger.error(f"❌ 清空日志文件失败: {e}")

    @classmethod
    def get_log_stats(cls):
        """获取日志文件统计信息"""
        stats = {}
        try:
            if os.path.exists(cls._normal_log_file):
                with open(cls._normal_log_file, 'r', encoding='utf-8') as f:
                    stats['normal_log_lines'] = len(f.readlines())
                stats['normal_log_size'] = os.path.getsize(cls._normal_log_file)
            else:
                stats['normal_log_lines'] = 0
                stats['normal_log_size'] = 0
                
            if os.path.exists(cls._error_log_file):
                with open(cls._error_log_file, 'r', encoding='utf-8') as f:
                    stats['error_log_lines'] = len(f.readlines())
                stats['error_log_size'] = os.path.getsize(cls._error_log_file)
            else:
                stats['error_log_lines'] = 0
                stats['error_log_size'] = 0
                
        except Exception as e:
            if cls._logger:
                cls._logger.error(f"❌ 获取日志统计信息失败: {e}")
            stats = {'error': str(e)}
        
        return stats