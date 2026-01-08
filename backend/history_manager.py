import sqlite3
from datetime import datetime
import threading
import os
import json
import hashlib
import traceback
from utils.logger import Logger

logger = Logger.get_logger()

class HistoryManager:
    """历史记录管理器 spmid_history表"""

    def __init__(self, db_path=None, disable_database=False):
        """
        初始化历史记录管理器

        Args:
            db_path: 数据库路径
            disable_database: 是否禁用数据库功能（用于测试或特定环境）
        """
        self.disable_database = disable_database or os.environ.get('DISABLE_DATABASE', 'false').lower() == 'true'

        if not self.disable_database:
            # 如果没有指定路径，则在backend目录下创建数据库
            if db_path is None:
                backend_dir = os.path.dirname(os.path.abspath(__file__))
                self.db_path = os.path.join(backend_dir, "history_spmid.db")
            else:
                self.db_path = db_path

            self._lock = threading.RLock()
            self.init_database()
        else:
            # 禁用数据库时，使用内存存储作为替代
            self.db_path = None
            self._lock = threading.RLock()
            self._memory_storage = []

        # 只在主进程中记录初始化日志（避免Flask debug模式下的重复日志）
        if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
            pass

    def init_database(self):
        """初始化数据库表结构 - 根据实际表结构"""
        if self.disable_database:
            return

        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 检查表是否存在
            cursor.execute('''
                SELECT name FROM sqlite_master WHERE type='table' AND name='spmid_history'
            ''')
            table_exists = cursor.fetchone() is not None

            if not table_exists:
                # 创建新表 - 添加file_content字段用于存储原始文件内容
                cursor.execute('''
                    CREATE TABLE spmid_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        filename TEXT NOT NULL,
                        file_hash TEXT NOT NULL UNIQUE,
                        file_content BLOB,
                        upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        multi_hammers_count INTEGER DEFAULT 0,
                        drop_hammers_count INTEGER DEFAULT 0,
                        total_errors INTEGER DEFAULT 0,
                        file_size INTEGER DEFAULT 0
                    )
                ''')
            else:
                # 表已存在，检查列结构是否完整
                cursor.execute("PRAGMA table_info(spmid_history)")
                columns = [column[1] for column in cursor.fetchall()]

                # 需要的列及其定义 - 添加file_content字段
                required_columns = {
                    'file_hash': 'TEXT NOT NULL',
                    'file_content': 'BLOB',
                    'upload_time': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
                    'multi_hammers_count': 'INTEGER DEFAULT 0',
                    'drop_hammers_count': 'INTEGER DEFAULT 0',
                    'total_errors': 'INTEGER DEFAULT 0',
                    'file_size': 'INTEGER DEFAULT 0'
                }

                # 添加缺失的列
                for column_name, column_definition in required_columns.items():
                    if column_name not in columns:
                        try:
                            cursor.execute(f'ALTER TABLE spmid_history ADD COLUMN {column_name} {column_definition}')
                            logger.info(f"✅ 添加列: {column_name}")
                        except sqlite3.OperationalError as e:
                            logger.info(f"⚠️ 添加列 {column_name} 失败: {e}")

            # 创建索引以提高查询性能
            try:
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_spmid_history_upload_time 
                    ON spmid_history (upload_time)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_spmid_history_filename 
                    ON spmid_history (filename)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_spmid_history_file_hash 
                    ON spmid_history (file_hash)
                ''')
            except sqlite3.OperationalError as e:
                logger.info(f"⚠️ 创建索引失败: {e}")

            conn.commit()
            conn.close()

    def save_analysis_result(self, filename, backend, upload_id=None, file_content=None):
        """保存分析结果到数据库 - 修复文件内容保存逻辑"""

        if self.disable_database:
            logger.info(f"⚠️ 数据库功能已禁用，跳过保存分析结果: {filename}")
            # 返回一个假的ID用于兼容性
            return 999999

        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            try:
                # 准备分析数据
                multi_hammers_count = len(backend.multi_hammers) if hasattr(backend, 'multi_hammers') else 0
                drop_hammers_count = len(backend.drop_hammers) if hasattr(backend, 'drop_hammers') else 0
                total_errors = multi_hammers_count + drop_hammers_count

                # 优先使用传入的file_content，然后尝试从backend获取
                if not file_content and hasattr(backend, 'original_file_content'):
                    file_content = backend.original_file_content
                    logger.info("✅ 从backend获取原始文件内容")

                # 验证文件内容
                if file_content:
                    if isinstance(file_content, str):
                        # 如果是字符串，转换为bytes
                        file_content = file_content.encode('utf-8')

                    file_hash = hashlib.md5(file_content).hexdigest()
                    file_size = len(file_content)
                    logger.info(f"📊 文件信息: 大小 {file_size} 字节, 哈希 {file_hash[:8]}...")
                else:
                    # 如果没有文件内容，生成基于文件名的哈希，但不删除现有记录
                    file_hash = hashlib.md5(f"{filename}_{datetime.now().isoformat()}".encode()).hexdigest()
                    file_size = 0
                    logger.info("⚠️ 没有文件内容，使用文件名+时间戳生成哈希")

                # 修复：只有当有真实文件内容时才删除重复记录
                # 避免因为文件名相同而误删其他有效记录
                if file_content and file_size > 0:
                    cursor.execute('SELECT id FROM spmid_history WHERE file_hash = ?', (file_hash,))
                    existing_record = cursor.fetchone()
                    if existing_record:
                        logger.info(f"🔄 发现重复文件(哈希: {file_hash[:8]}...)，更新现有记录 ID: {existing_record[0]}")
                        # 更新现有记录而不是删除重新创建
                        cursor.execute('''
                            UPDATE spmid_history 
                            SET filename = ?, multi_hammers_count = ?, drop_hammers_count = ?, 
                                total_errors = ?, file_size = ?, upload_time = CURRENT_TIMESTAMP
                            WHERE file_hash = ?
                        ''', (filename, multi_hammers_count, drop_hammers_count, total_errors, file_size, file_hash))

                        history_id = existing_record[0]
                        conn.commit()
                        logger.info(f"✅ 更新现有记录完成，记录ID: {history_id}")
                        return history_id

                # 插入新记录到spmid_history表
                cursor.execute('''
                    INSERT INTO spmid_history 
                    (filename, file_hash, file_content, multi_hammers_count, drop_hammers_count, total_errors, file_size)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (filename, file_hash, file_content, multi_hammers_count, drop_hammers_count, total_errors, file_size))

                history_id = cursor.lastrowid
                conn.commit()

                logger.info(f"✅ 分析结果已保存到数据库，记录ID: {history_id}")
                logger.info(f"📊 保存信息: 多锤 {multi_hammers_count} 个, 丢锤 {drop_hammers_count} 个, 总计 {total_errors} 个")
                logger.info(f"💾 文件内容保存状态: {'已保存' if file_content else '未保存'}")
                return history_id

            except Exception as e:
                logger.info(f"❌ 保存分析结果失败: {e}")
                traceback.print_exc()
                conn.rollback()  # 添加回滚操作
                return None
            finally:
                conn.close()

    def get_record_details(self, record_id):
        """获取特定记录的详细信息 - 修复文件内容获取逻辑"""
        if self.disable_database:
            logger.info(f"⚠️ 数据库功能已禁用，无法获取记录详情: {record_id}")
            return None

        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            try:
                # 从spmid_history表获取记录 - 包含文件内容
                cursor.execute('''
                    SELECT id, filename, upload_time, multi_hammers_count, drop_hammers_count, 
                           total_errors, file_hash, file_size, file_content
                    FROM spmid_history WHERE id = ?
                ''', (record_id,))

                main_record = cursor.fetchone()
                if not main_record:
                    logger.info(f"❌ 未找到记录 ID: {record_id}")
                    return None

                logger.info(f"📋 查询到记录: {main_record[1]} (ID: {main_record[0]})")

                # 修复：安全获取文件内容并验证
                file_content = main_record[8] if len(main_record) > 8 else None
                file_size = main_record[7] if len(main_record) > 7 else 0

                # 验证文件内容的完整性
                if file_content:
                    actual_size = len(file_content)
                    logger.info(f"📊 文件内容: 声明大小 {file_size} 字节, 实际大小 {actual_size} 字节")
                    if actual_size == 0:
                        logger.info("⚠️ 文件内容为空，可能存在保存问题")
                        file_content = None
                else:
                    logger.info("⚠️ 该历史记录没有保存文件内容")

                return {
                    'main_record': main_record,
                    'file_content': file_content,
                    'error_details': []
                }

            except Exception as e:
                logger.info(f"❌ 获取记录详情失败: {e}")
                traceback.print_exc()
                return None
            finally:
                conn.close()

    def get_history_list(self, limit=50):
        """获取历史记录列表 - 根据实际表结构"""
        if self.disable_database:
            logger.info(f"⚠️ 数据库功能已禁用，返回空的历史记录列表")
            return []

        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            try:
                cursor.execute('''
                    SELECT id, filename, upload_time, multi_hammers_count, drop_hammers_count, 
                           total_errors, file_size
                    FROM spmid_history 
                    ORDER BY upload_time DESC 
                    LIMIT ?
                ''', (limit,))

                results = cursor.fetchall()
                logger.info(f"📊 从spmid_history表查询到 {len(results)} 条历史记录")

                # 转换为兼容格式
                history_list = []
                for row in results:
                    history_list.append({
                        'id': row[0],
                        'filename': row[1],
                        'upload_time': row[2],  # 使用实际的upload_time字段
                        'timestamp': row[2],    # 兼容性字段名
                        'multi_hammers_count': row[3],  # 使用实际字段名
                        'multi_hammers': row[3],        # 兼容性字段名
                        'drop_hammers_count': row[4],   # 使用实际字段名
                        'drop_hammers': row[4],         # 兼容性字段名
                        'total_errors': row[5],
                        'file_size': row[6] or 0,
                        'analysis_duration': 0.0  # 实际表中没有这个字段，设为默认值
                    })

                return history_list

            except Exception as e:
                logger.info(f"❌ 获取历史记录列表失败: {e}")
                traceback.print_exc()
                return []
            finally:
                conn.close()

    def add_record(self, filename, file_content, analysis_result, analysis_duration=0, notes=""):
        """添加SPMID文件记录 - 根据实际表结构"""

        file_hash = hashlib.md5(file_content).hexdigest()

        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            try:
                # 先删除可能存在的同文件记录，避免重复
                cursor.execute('DELETE FROM spmid_history WHERE file_hash = ?', (file_hash,))

                # 插入主记录到spmid_history表 - 只使用实际存在的列
                cursor.execute('''
                    INSERT INTO spmid_history 
                    (filename, file_hash, multi_hammers_count, drop_hammers_count, total_errors, file_size)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    filename,
                    file_hash,
                    analysis_result.get('multi_hammers_count', 0),
                    analysis_result.get('drop_hammers_count', 0),
                    analysis_result.get('total_errors', 0),
                    len(file_content)
                ))

                history_id = cursor.lastrowid
                conn.commit()

                logger.info(f"✅ 历史记录已保存到spmid_history表: {filename}, ID: {history_id}")
                return history_id

            except Exception as e:
                logger.info(f"❌ 添加历史记录失败: {e}")
                traceback.print_exc()
                return None
            finally:
                conn.close()

    def delete_record(self, record_id):
        """删除指定的历史记录"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            try:
                cursor.execute('DELETE FROM spmid_history WHERE id = ?', (record_id,))
                deleted_count = cursor.rowcount
                conn.commit()

                if deleted_count > 0:
                    logger.info(f"✅ 已删除历史记录 ID: {record_id}")
                    return True
                else:
                    logger.info(f"⚠️ 未找到要删除的记录 ID: {record_id}")
                    return False

            except Exception as e:
                logger.info(f"❌ 删除历史记录失败: {e}")
                return False
            finally:
                conn.close()

    def clear_all_records(self):
        """清空所有历史记录"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            try:
                cursor.execute('DELETE FROM spmid_history')
                deleted_count = cursor.rowcount
                conn.commit()

                logger.info(f"✅ 已清空所有历史记录，共删除 {deleted_count} 条记录")
                return deleted_count

            except Exception as e:
                logger.info(f"❌ 清空历史记录失败: {e}")
                return 0
            finally:
                conn.close()
    
    # ==================== 历史记录处理相关方法 ====================
    
    def process_history_selection(self, history_id, backend):
        """
        处理历史记录选择 - 从数据库加载历史记录并初始化backend状态

        Args:
            history_id: 历史记录ID
            backend: 后端实例

        Returns:
            tuple: (success, result_data, error_msg)
                   - success: 是否处理成功
                   - result_data: 成功时的结果数据（包含filename、main_record等）
                   - error_msg: 失败时的错误信息
        """
        if self.disable_database:
            logger.info(f"⚠️ 数据库功能已禁用，无法处理历史记录选择: {history_id}")
            return False, None, "数据库功能已禁用"

        try:
            logger.info(f"🔄 处理历史记录选择: {history_id}")

            # 获取历史记录详情
            record_details = self.get_record_details(history_id)
            if not record_details:
                return False, None, "历史记录不存在"
            
            # 解析历史记录信息
            filename, main_record = self._parse_history_record(record_details)
            
            # 初始化历史记录状态
            self._initialize_history_state(backend, history_id, filename)
            
            # 处理历史记录
            if 'file_content' in record_details and record_details['file_content']:
                success = self._load_history_file_content(backend, record_details['file_content'])
                if success:
                    result_data = {
                        'filename': filename,
                        'history_id': history_id,
                        'main_record': main_record,
                        'has_file_content': True,
                        'record_count': len(backend.data_manager.spmid_loader.get_record_data()),
                        'replay_count': len(backend.data_manager.spmid_loader.get_replay_data())
                    }
                    return True, result_data, None
                else:
                    return False, None, "历史文件分析失败"
            else:
                result_data = {
                    'filename': filename,
                    'history_id': history_id,
                    'main_record': main_record,
                    'has_file_content': False
                }
                return True, result_data, None
                
        except Exception as e:
            logger.error(f"❌ 历史记录处理错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, None, str(e)
    
    def save_upload_result(self, filename, backend):
        """
        保存上传结果到历史记录
        
        Args:
            filename: 文件名
            backend: 后端实例
            
        Returns:
            str: 历史记录ID
        """
        history_id = self.save_analysis_result(filename, backend)
        self._log_upload_success(filename, backend, history_id)
        return history_id
    
    # ==================== 私有方法 ====================
    
    def _initialize_history_state(self, backend, history_id, filename):
        """初始化历史记录状态"""
        # 清理数据状态
        backend.data_manager.clear_data_state()
        
        # 设置历史记录数据源信息
        backend.data_manager.set_history_data_source(history_id, filename)
        backend._data_source = 'history'
        backend._current_history_id = history_id
    
    def _load_history_file_content(self, backend, file_content):
        """加载历史记录文件内容"""
        logger.info("🔄 从数据库重新分析历史文件...")
        
        # 直接加载文件内容 - 已解码
        if isinstance(file_content, str):
            decoded_bytes = file_content.encode('utf-8')
        else:
            decoded_bytes = file_content
        success = backend.data_manager.spmid_loader.load_spmid_data(decoded_bytes)
        
        if success:
            logger.info("✅ 历史记录重新分析完成")
            logger.info(f"📊 数据统计: 录制 {len(backend.data_manager.spmid_loader.get_record_data())} 个音符, 播放 {len(backend.data_manager.spmid_loader.get_replay_data())} 个音符")
        
        return success
    
    def _log_upload_success(self, filename, backend, history_id):
        """记录文件上传成功信息"""
        logger.info(f"✅ 文件上传处理完成 - {filename}")
        logger.info(f"📊 数据统计: 录制 {len(backend.data_manager.spmid_loader.get_record_data())} 个音符, 播放 {len(backend.data_manager.spmid_loader.get_replay_data())} 个音符")
        logger.info(f"💾 历史记录ID: {history_id}")
    
    def _parse_history_record(self, record_details):
        """解析历史记录信息"""
        main_record = record_details['main_record']
        # main_record是一个tuple，格式为: (id, filename, upload_time, multi_hammers_count, drop_hammers_count, total_errors, file_hash, file_size, file_content)
        if isinstance(main_record, tuple) and len(main_record) >= 2:
            filename = main_record[1] if main_record[1] else '未知文件'
        else:
            filename = '未知文件'
        return filename, main_record
