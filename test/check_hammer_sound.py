import os
import sys
import argparse
import io
from collections import defaultdict
from contextlib import redirect_stdout

# 确保可以从任意工作目录运行：把项目根目录加入 sys.path
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from utils.logger import Logger
from spmid.spmid_reader import SPMidReader
from spmid.motor_threshold_checker import MotorThresholdChecker


def main():
    parser = argparse.ArgumentParser(description="统计SPMID文件中每个音符的锤子是否发声，并将终端打印输出写入日志")
    parser.add_argument("spmid_file", help="SPMID 文件路径")
    parser.add_argument("--equations", default=os.path.join("spmid", "quadratic_fit_formulas.json"), help="拟合公式JSON文件路径，默认 spmid/quadratic_fit_formulas.json")
    parser.add_argument("--thresholds", default=os.path.join("spmid", "inflection_pwm_values.json"), help="PWM阈值JSON文件路径，默认 spmid/inflection_pwm_values.json")
    parser.add_argument("--verbose", action="store_true", help="是否输出更详细的日志")
    args = parser.parse_args()

    logger = Logger.get_logger()

    if not os.path.exists(args.spmid_file):
        logger.error(f"输入文件不存在: {args.spmid_file}")
        sys.exit(1)

    # 解析JSON路径（兼容从任意工作目录执行）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    def resolve_path(p):
        if os.path.isabs(p):
            return p
        if os.path.exists(p):
            return p
        # 尝试相对于仓库根目录
        candidate = os.path.join(repo_root, p)
        if os.path.exists(candidate):
            return candidate
        # 尝试相对于脚本目录
        candidate = os.path.join(script_dir, p)
        if os.path.exists(candidate):
            return candidate
        return p  # 返回原始路径以便报错

    equations_path = resolve_path(args.equations)
    thresholds_path = resolve_path(args.thresholds)

    # 初始化检查器
    try:
        checker = MotorThresholdChecker(
            fit_equations_path=equations_path,
            pwm_thresholds_path=thresholds_path,
        )
        logger.info(f"电机阈值检查器初始化完成 (equations={equations_path}, thresholds={thresholds_path})")
    except Exception as e:
        logger.error(f"电机阈值检查器初始化失败: {e}")
        sys.exit(1)

    # 读取SPMID
    try:
        reader = SPMidReader.from_file(args.spmid_file, verbose=args.verbose)
        logger.info(f"SPMID读取完成，音轨数: {reader.track_count}")
    except Exception as e:
        logger.error(f"读取SPMID失败: {e}")
        sys.exit(1)

    total_notes = 0
    total_hammers = 0
    total_sounding = 0
    total_silent = 0
    silent_by_key = defaultdict(int)

    missing_motor_logged = set()

    for track_index in range(reader.track_count):
        notes = reader.get_track(track_index)
        track_label = "录制" if track_index == 0 else ("播放" if track_index == 1 else f"轨道{track_index}")
        prefix = f"[{track_label}] "
        logger.info(f"{prefix}开始处理音轨 {track_index}，音符数: {len(notes)}")

        for note_index, note in enumerate(notes):
            total_notes += 1
            motor_name = f"motor_{note.id}"  # NoteID 映射到 motor_{NoteID}
            if note.hammers is None or note.hammers.empty:
                logger.info(f"{prefix}跳过空锤子音符: track={track_index}, note_idx={note_index}, NoteID={note.id}")
                continue

            note_hammers = len(note.hammers)
            note_sounding = 0
            note_silent = 0

            logger.info(f"{prefix}音符开始: track={track_index}, note_idx={note_index}, NoteID={note.id}, 锤子数={note_hammers}")

            for hammer_time, hammer_velocity in note.hammers.items():
                total_hammers += 1

                # 规则：velocity<=0 必定不发声，直接判定并跳过阈值检查
                early_blocked = False
                result = False
                if hammer_velocity is not None and hammer_velocity <= 0:
                    early_blocked = True
                else:
                    # 捕获检查器内部的 print 输出并写入日志
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        try:
                            result = checker.check_threshold(hammer_velocity, motor_name)
                        except Exception as ex:
                            result = False
                            logger.error(f"{prefix}检查阈值时发生异常: motor={motor_name}, velocity={hammer_velocity}, err={ex}")
                    printed = buf.getvalue().strip()
                    if printed:
                        for line in printed.splitlines():
                            # 若是缺少电机配置的提示，只记录一次
                            if ("阈值不存在" in line or "无法计算电机" in line) and motor_name not in missing_motor_logged:
                                logger.warning(f"{prefix}{line}")
                                missing_motor_logged.add(motor_name)
                            else:
                                logger.info(f"{prefix}{line}")

                t_abs = note.offset + hammer_time
                status = "发声" if result else "不发声"
                logger.info(
                    f"{prefix}  锤子: t_rel={hammer_time}, t_abs={t_abs}, NoteID={note.id}, motor={motor_name}, velocity={hammer_velocity}, 结果={status}{' (velocity<=0 强制不发声)' if early_blocked else ''}"
                )
                if result:
                    note_sounding += 1
                    total_sounding += 1
                else:
                    note_silent += 1
                    total_silent += 1
                    silent_by_key[note.id] += 1
                    logger.info(
                        f"{prefix}  不发声锤子记录: keyId={note.id}, motor={motor_name}, t_rel={hammer_time}, t_abs={t_abs}, velocity={hammer_velocity}"
                    )

            logger.info(
                f"{prefix}音符结束: track={track_index}, note_idx={note_index}, NoteID={note.id}, 发声={note_sounding}, 不发声={note_silent}"
            )

    logger.info("=" * 60)
    logger.info("统计汇总")
    logger.info(f"音符总数: {total_notes}")
    logger.info(f"锤子总数: {total_hammers}")
    logger.info(f"发声锤子: {total_sounding}")
    logger.info(f"不发声锤子: {total_silent}")
    if silent_by_key:
        logger.info("不发声按键汇总(按数量降序)：")
        for key_id, cnt in sorted(silent_by_key.items(), key=lambda x: x[1], reverse=True):
            logger.info(f"  keyId={key_id}, motor=motor_{key_id}, 不发声数={cnt}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()


