#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
collect_data.py
================
Công cụ quét đệ quy một thư mục báo cáo lớn (chứa rất nhiều thư mục báo cáo
con nằm rải rác ở nhiều cấp khác nhau), tìm các cặp file:

    - group_summary.csv  -> chứa worst_slack của từng group
    - group_members.csv  -> chứa chi tiết từng path/member trong group

Mục tiêu: lọc ra các vi phạm slack "nặng" (slack < ngưỡng cho phép) và xuất
thành 1 file CSV tổng hợp duy nhất để dễ xem/ sort/ chia sẻ.

Cách hoạt động (logic giữ nguyên từ bản gốc, chỉ tổ chức lại cho rõ ràng
và dễ tái sử dụng):
    1. os.walk() đi qua toàn bộ cây thư mục của ROOT_DIR.
    2. Tại mỗi thư mục có đủ 2 file group_summary.csv + group_members.csv:
        a. Đọc group_summary.csv -> lấy tập hợp các giá trị "worst_slack"
           (hoặc "slack") thỏa điều kiện < SLACK_THRESHOLD.
        b. Đọc group_members.csv -> với mỗi dòng có cột "slack" khớp với
           1 trong các giá trị vi phạm ở bước (a), lấy các cột cần quan
           tâm (TARGET_COLUMNS) và lưu lại kèm đường dẫn thư mục tương đối.
    3. Ghi toàn bộ kết quả ra 1 file CSV tổng hợp duy nhất.

Cách dùng nhanh (xem thêm trong README.md):
    python collect_data.py --root output_reports --out sorted_critical_violations.csv --threshold -0.4
"""

import os
import csv
import argparse
import sys


# ----------------------------------------------------------------------------
# CẤU HÌNH MẶC ĐỊNH
# Các giá trị này chỉ là MẶC ĐỊNH; có thể override bằng tham số dòng lệnh (CLI)
# nên không cần sửa trực tiếp trong code khi đổi project/threshold.
# ----------------------------------------------------------------------------
DEFAULT_ROOT_DIR = "output_reports"          # thư mục báo cáo gốc cần quét
DEFAULT_SUMMARY_FILE = "sorted_critical_violations.csv"  # file kết quả tổng hợp
DEFAULT_SLACK_THRESHOLD = -0.4                # ngưỡng slack bị coi là vi phạm nặng

# Tên 2 file cần tìm trong mỗi thư mục báo cáo con
FILE_SUMMARY = "group_summary.csv"
FILE_MEMBERS = "group_members.csv"

# Các cột cần lấy ra từ group_members.csv (có thể chỉnh tùy nhu cầu báo cáo)
TARGET_COLUMNS = ["startpoint", "endpoint", "slack", "launch_clock", "capture_clock"]


def parse_args():
    """Đọc tham số dòng lệnh, cho phép cấu hình mà không cần sửa code."""
    parser = argparse.ArgumentParser(
        description="Quét cây thư mục báo cáo và lọc các vi phạm slack nặng."
    )
    parser.add_argument(
        "--root", "-r",
        default=DEFAULT_ROOT_DIR,
        help=f"Thư mục báo cáo gốc cần quét (mặc định: {DEFAULT_ROOT_DIR})",
    )
    parser.add_argument(
        "--out", "-o",
        default=DEFAULT_SUMMARY_FILE,
        help=f"Đường dẫn file CSV kết quả (mặc định: {DEFAULT_SUMMARY_FILE})",
    )
    parser.add_argument(
        "--threshold", "-t",
        type=float,
        default=DEFAULT_SLACK_THRESHOLD,
        help=f"Ngưỡng slack vi phạm, lấy các giá trị < ngưỡng này "
             f"(mặc định: {DEFAULT_SLACK_THRESHOLD})",
    )
    parser.add_argument(
        "--columns", "-c",
        nargs="+",
        default=TARGET_COLUMNS,
        help=f"Danh sách cột cần trích từ group_members.csv "
             f"(mặc định: {' '.join(TARGET_COLUMNS)})",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Không in log chi tiết ra màn hình, chỉ in thông báo kết quả cuối.",
    )
    return parser.parse_args()


def read_violating_slacks(path_summary, slack_threshold, log):
    """
    Đọc group_summary.csv và trả về tập hợp (set) các giá trị slack (dạng
    chuỗi, đã strip) thỏa điều kiện vi phạm (< slack_threshold).

    Dùng 'set' để tra cứu nhanh ở bước đối chiếu với group_members.csv,
    và để tránh trùng lặp khi nhiều group có cùng giá trị slack.
    """
    worst_slacks = set()

    with open(path_summary, mode="r", encoding="utf-8-sig") as f_sum:
        reader_sum = csv.DictReader(f_sum)

        # Chuẩn hóa tên cột: bỏ khoảng trắng dư + chuyển về lowercase
        # để không bị lỗi khi file gốc có header viết hoa/thường lẫn lộn.
        if reader_sum.fieldnames:
            reader_sum.fieldnames = [n.strip().lower() for n in reader_sum.fieldnames]
        else:
            log(f"  [Bỏ qua] {path_summary}: file rỗng hoặc không có header.")
            return worst_slacks

        for row in reader_sum:
            # Hỗ trợ cả 2 tên cột "worst_slack" hoặc "slack" tùy format báo cáo
            ws_val = row.get("worst_slack") or row.get("slack")
            if not ws_val:
                continue
            try:
                if float(ws_val.strip()) < slack_threshold:
                    worst_slacks.add(ws_val.strip())
            except ValueError:
                # Giá trị không phải số (ví dụ "N/A") -> bỏ qua, không phải lỗi nghiêm trọng
                continue

    return worst_slacks


def read_matching_members(path_members, worst_slacks, target_columns, relative_folder):
    """
    Đọc group_members.csv, chỉ giữ lại các dòng có cột 'slack' khớp với
    1 trong các giá trị vi phạm đã tìm thấy ở group_summary.csv.

    Trả về list các dict, mỗi dict là 1 dòng kết quả sẵn sàng để ghi CSV.
    """
    matched_rows = []

    with open(path_members, mode="r", encoding="utf-8-sig") as f_mem:
        reader_mem = csv.DictReader(f_mem)
        if reader_mem.fieldnames:
            reader_mem.fieldnames = [n.strip().lower() for n in reader_mem.fieldnames]

        for row in reader_mem:
            # Dọn khoảng trắng dư ở cả key và value để so khớp chính xác
            clean_row = {k.strip(): v.strip() for k, v in row.items() if k}
            current_slack = clean_row.get("slack")

            if current_slack in worst_slacks:
                data_entry = {"directory": relative_folder}
                for col in target_columns:
                    data_entry[col] = clean_row.get(col, "N/A")
                matched_rows.append(data_entry)

    return matched_rows


def run_advanced_filtering(root_dir, out_file, slack_threshold, target_columns, quiet=False):
    """
    Hàm chính: quét toàn bộ cây thư mục root_dir, lọc vi phạm slack nặng
    theo slack_threshold, ghi kết quả ra out_file.

    Trả về số dòng vi phạm đã tìm thấy (int).
    """
    def log(msg):
        if not quiet:
            print(msg)

    final_output = []

    log(f" --- Đang bắt đầu quét hệ thống thư mục: {root_dir} --- ")
    log(f" --- Ngưỡng lọc Slack: < {slack_threshold} --- ")

    if not os.path.isdir(root_dir):
        print(f"[LỖI] Không tìm thấy thư mục gốc: {root_dir}", file=sys.stderr)
        return 0

    # os.walk duyệt toàn bộ cây thư mục, bất kể độ sâu phân cấp
    for root, dirs, files in os.walk(root_dir):
        if FILE_SUMMARY in files and FILE_MEMBERS in files:
            path_summary = os.path.join(root, FILE_SUMMARY)
            path_members = os.path.join(root, FILE_MEMBERS)
            relative_folder = os.path.relpath(root, root_dir)

            try:
                # Bước 1: tìm các giá trị slack vi phạm trong group_summary.csv
                worst_slacks = read_violating_slacks(path_summary, slack_threshold, log)

                # Bước 2: nếu có vi phạm, lấy chi tiết tương ứng trong group_members.csv
                if worst_slacks:
                    matched_rows = read_matching_members(
                        path_members, worst_slacks, target_columns, relative_folder
                    )
                    final_output.extend(matched_rows)
                    if matched_rows:
                        log(f"  [OK] {relative_folder}: {len(matched_rows)} vi phạm.")

            except Exception as e:
                # Không để 1 thư mục lỗi làm dừng toàn bộ quá trình quét
                print(f"Lỗi tại {relative_folder}: {e}", file=sys.stderr)

    # Bước 3: xuất báo cáo tổng hợp cuối cùng
    if final_output:
        header = ["directory"] + target_columns
        with open(out_file, mode="w", newline="", encoding="utf-8") as out_f:
            writer = csv.DictWriter(out_f, fieldnames=header)
            writer.writeheader()
            writer.writerows(final_output)
        log(f" --- Thành công! Đã tìm thấy {len(final_output)} vi phạm nặng (< {slack_threshold}).")
        log(f" --- Kết quả: {out_file}")
    else:
        log(f"Không tìm thấy path nào có Slack < {slack_threshold}.")

    return len(final_output)


def main():
    args = parse_args()
    run_advanced_filtering(
        root_dir=args.root,
        out_file=args.out,
        slack_threshold=args.threshold,
        target_columns=args.columns,
        quiet=args.quiet,
    )


if __name__ == "__main__":
    main()
