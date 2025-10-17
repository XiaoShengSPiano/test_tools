import sqlite3
import base64
from datetime import datetime
import threading
import os
import json
from utils.logger import Logger

logger = Logger.get_logger()

class HistoryManager:
    """历史记录管理器 spmid_history表"""

    def __init__(self, db_path=None):
        # 如果没有指定路径，则在backend目录下创建数据库
        if db_path is None:
            backend_dir = os.path.dirname(os.path.abspath(__file__))
            self.db_path = os.path.join(backend_dir, "history_spmid.db")
        else:
            self.db_path = db_path

        self._lock = threading.RLock()
        self.init_database()

    def init_database(self):
        """初始化数据库表结构 - 根据实际表结构"""
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
                logger.info("✅ 创建新的spmid_history表（包含file_content字段）")
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
        import hashlib

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
                        # 如果是字符串，尝试解码为bytes
                        try:
                            file_content = base64.b64decode(file_content)
                        except:
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
                import traceback
                traceback.print_exc()
                conn.rollback()  # 添加回滚操作
                return None
            finally:
                conn.close()

    def get_record_details(self, record_id):
        """获取特定记录的详细信息 - 修复文件内容获取逻辑"""
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
                import traceback
                traceback.print_exc()
                return None
            finally:
                conn.close()

    def get_history_list(self, limit=50):
        """获取历史记录列表 - 根据实际表结构"""
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
                import traceback
                traceback.print_exc()
                return []
            finally:
                conn.close()

    def add_record(self, filename, file_content, analysis_result, analysis_duration=0, notes=""):
        """添加SPMID文件记录 - 根据实际表结构"""
        import hashlib

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
                import traceback
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
