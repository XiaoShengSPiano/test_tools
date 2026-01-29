#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
检查有效播放数据中每个 Note 的 after_touch 的 key（index）在相邻项之间是否相差 2。

若存在差值不为 2 的相邻项，则统计数量并将该 note 的详细数据输出到日志文件。
使用与主应用相同的过滤后播放数据（SPMIDLoader.get_replay_data()）。
输出仅写入专用日志文件，不输出到控制台。不使用项目 Logger，直接写文件并格式化。
"""

import sys
import argparse
import os
from collections import Counter
from pathlib import Path
from datetime import datetime

# 项目根目录加入 path，便于导入 backend / spmid
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

LOG_DIR = _project_root / "logs"
LOG_FILE = LOG_DIR / "check_after_touch_key_step.log"
EXPECTED_KEY_STEP = 2

# 当前写入的日志文件句柄（由 run 内打开/关闭）
_log_handle = None


def _writelog(*lines: str) -> None:
    """将若干行写入日志文件，带时间戳和统一格式。不输出到控制台。"""
    global _log_handle
    if _log_handle is None or _log_handle.closed:
        return
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for line in lines:
        _log_handle.write(f"[{ts}] {line}\n")
    _log_handle.flush()


def get_after_touch_keys(note):
    """获取 note.after_touch 的 index 列表（即 key 序列）。"""
    if not hasattr(note, "after_touch") or note.after_touch is None or note.after_touch.empty:
        return None
    return note.after_touch.index.tolist()


def check_key_steps(keys):
    """检查相邻 key 是否都相差 EXPECTED_KEY_STEP。返回 (前key, 后key, 实际差值) 的违规列表。"""
    violations = []
    for i in range(len(keys) - 1):
        prev_key = int(keys[i])
        next_key = int(keys[i + 1])
        diff = next_key - prev_key
        if diff != EXPECTED_KEY_STEP:
            violations.append((prev_key, next_key, diff))
    return violations


def get_after_touch_intervals(keys):
    """获取 after_touch 相邻 key 的间隔列表 [key[i+1]-key[i]]。"""
    if not keys or len(keys) < 2:
        return None
    return [int(keys[i + 1]) - int(keys[i]) for i in range(len(keys) - 1)]


def _format_note_detail(note, note_index: int, violations: list, intervals: list) -> str:
    """格式化为可读的多行文本。"""
    keys = get_after_touch_keys(note)
    lines = [
        "  note_index_in_replay: %s" % note_index,
        "  offset: %s" % getattr(note, "offset", None),
        "  id: %s" % getattr(note, "id", None),
        "  finger: %s" % getattr(note, "finger", None),
        "  velocity: %s" % getattr(note, "velocity", None),
        "  uuid: %s" % getattr(note, "uuid", None),
        "  key_on_ms: %s" % getattr(note, "key_on_ms", None),
        "  key_off_ms: %s" % getattr(note, "key_off_ms", None),
        "  duration_ms: %s" % getattr(note, "duration_ms", None),
        "  after_touch_key_count: %s" % (len(keys) if keys else 0),
    ]
    if keys:
        lines.append("  after_touch_keys: %s" % keys)
    if intervals:
        lines.append("  after_touch_intervals: %s" % intervals)
    lines.append("  violations:")
    for p, n, d in violations:
        lines.append("    - 前key=%s, 后key=%s, 差值=%s" % (p, n, d))
    return "\n".join(lines)


def run(spmid_path: str) -> None:
    """加载 SPMID，检查过滤后播放轨 after_touch 相邻 key 步长，结果写入日志文件。"""
    global _log_handle

    os.makedirs(LOG_DIR, exist_ok=True)
    _log_handle = open(LOG_FILE, "a", encoding="utf-8")

    try:
        from backend.spmid_loader import SPMIDLoader
    except Exception as e:
        _writelog("ERROR: 导入失败: %s" % e)
        if _log_handle and not _log_handle.closed:
            _log_handle.close()
            _log_handle = None
        return

    try:
        path = Path(spmid_path)
        if not path.is_file():
            _writelog("ERROR: 文件不存在: %s" % spmid_path)
            return

        _writelog(
            "======== 开始检查 after_touch key 步长 ========",
            "  日志文件: %s" % LOG_FILE,
            "  输入文件: %s" % spmid_path,
            "  期望相邻 key 差值: %s" % EXPECTED_KEY_STEP,
            "",
        )

        loader = SPMIDLoader()
        with open(path, "rb") as f:
            data = f.read()

        if not loader.load_spmid_data(data):
            _writelog("ERROR: SPMID 加载失败: %s" % spmid_path)
            return

        replay_notes = loader.get_replay_data()
        if not replay_notes:
            _writelog("WARNING: 过滤后播放数据为空")
            return

        total_notes_with_after_touch = 0
        notes_with_violations = 0
        total_violations = 0
        violation_details = []

        for idx, note in enumerate(replay_notes):
            keys = get_after_touch_keys(note)
            if keys is None or len(keys) < 2:
                continue

            total_notes_with_after_touch += 1
            violations = check_key_steps(keys)
            if not violations:
                continue

            notes_with_violations += 1
            total_violations += len(violations)
            intervals = get_after_touch_intervals(keys)
            violation_details.append((idx, note, violations, intervals))

            # 每条违规 note：先一行摘要，再多行详情
            _writelog(
                "[after_touch key 步长异常] note_index=%s, offset=%s, id=%s, key_on_ms=%s, 违规数=%s"
                % (idx, getattr(note, "offset", None), getattr(note, "id", None), getattr(note, "key_on_ms", None), len(violations))
            )
            _writelog(_format_note_detail(note, idx, violations, intervals or []))
            _writelog("")  # 空行分隔

        # 汇总
        _writelog(
            "======== 统计结果 ========",
            "  有效播放 note 数(含 after_touch 且至少 2 个 key): %s" % total_notes_with_after_touch,
            "  存在相邻 key 差值≠%s 的 note 数: %s" % (EXPECTED_KEY_STEP, notes_with_violations),
            "  总违规间隔数: %s" % total_violations,
        )
        if violation_details:
            indices = [d[0] for d in violation_details]
            _writelog("  违规 note 的 replay 内索引列表: %s" % indices)
            # 按 note.id 分组统计异常频率
            id_counts = {}
            for _idx, note, _violations, _intervals in violation_details:
                nid = getattr(note, "id", None)
                id_counts[nid] = id_counts.get(nid, 0) + 1
            _writelog("  按 id 分组的异常频率 (id -> 出现次数):")
            for nid in sorted(id_counts.keys(), key=lambda x: (x is None, x)):
                _writelog("    id=%s: %s 次" % (nid, id_counts[nid]))
            # 异常 note 的 after_touch 时间间隔汇总统计
            all_intervals = []
            for _idx, _note, _violations, intervals in violation_details:
                if intervals:
                    all_intervals.extend(intervals)
            if all_intervals:
                n_int = len(all_intervals)
                _writelog("  异常 note 的 after_touch 间隔汇总:")
                _writelog("    间隔总数: %s" % n_int)
                _writelog("    最小值: %s" % min(all_intervals))
                _writelog("    最大值: %s" % max(all_intervals))
                _writelog("    平均值: %s" % (sum(all_intervals) / n_int))
                cnt = Counter(all_intervals)
                _writelog("    间隔值 -> 出现次数:")
                for v in sorted(cnt.keys()):
                    _writelog("      %s -> %s" % (v, cnt[v]))
        _writelog("======== 检查结束 ========", "")
    finally:
        if _log_handle and not _log_handle.closed:
            _log_handle.close()
            _log_handle = None


def main():
    parser = argparse.ArgumentParser(
        description="检查有效播放数据中 after_touch 相邻 key 是否相差 2，结果写入日志文件（不输出到控制台）"
    )
    parser.add_argument("spmid_file", type=str, help="SPMID 文件路径")
    args = parser.parse_args()
    run(args.spmid_file)


if __name__ == "__main__":
    main()
