import sys
import os
import threading

# Add current directory to path
sys.path.append(os.getcwd())

from backend.history_manager import SQLiteHistoryManager, HistoryRecord

def test_sqlite_manager():
    print("🚀 Starting SQLiteHistoryManager Verification...")
    
    # 用测试数据库和自定义表名
    db_path = "test_history_v2.db"
    table_name = "test_table_custom"
    if os.path.exists(db_path):
        os.remove(db_path)
        
    try:
        manager = SQLiteHistoryManager(db_path=db_path, table_name=table_name)
        print(f"✅ Initialization successful with table: {table_name}")
        
        # 1. 测试保存
        record = HistoryRecord(
            filename="test_file_001.spmid",
            motor_type="D3",
            algorithm="PID",
            date_str="2026-02-02-19-00-00",
            record_track_path="/path/to/record.parquet",
            playback_track_path="/path/to/playback.parquet"
        )
        
        record_id = manager.save_record(record)
        print(f"✅ Save successful, ID: {record_id}")
        
        # 2. 测试获取单个
        retrieved = manager.get_record(record_id)
        assert retrieved is not None
        assert retrieved.filename == "test_file_001.spmid"
        assert retrieved.motor_type == "D3"
        assert retrieved.algorithm == "PID"
        print(f"✅ Get record successful: {retrieved.filename}")
        
        # 3. 测试列表
        history_list = manager.get_history_list(limit=10)
        assert len(history_list) == 1
        print(f"✅ List records successful, count: {len(history_list)}")
        
        # 4. 测试删除
        success = manager.delete_record(record_id)
        assert success is True
        assert manager.get_record(record_id) is None
        print("✅ Delete successful")
        
        # 5. 测试清空
        manager.save_record(record)
        manager.save_record(record)
        count = manager.clear_all_records()
        assert count == 2
        assert len(manager.get_history_list()) == 0
        print(f"✅ Clear all successful, cleared {count} records")
        
        print("\n✨ All tests passed successfully!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

if __name__ == "__main__":
    test_sqlite_manager()
