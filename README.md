# Slack Violation Scanner

Công cụ dòng lệnh để quét đệ quy một thư mục báo cáo lớn (ví dụ kết quả
clock-group / timing analysis từ PnR/STA), tìm tất cả các thư mục con chứa
cặp file `group_summary.csv` + `group_members.csv`, lọc ra các vi phạm slack
**nặng hơn một ngưỡng cho phép**, và xuất thành **một file CSV tổng hợp duy
nhất** — dễ mở bằng Excel, sort, hoặc đưa vào báo cáo.

## 1. Cấu trúc bộ tool

```
slack_violation_scanner/
├── collect_data.py              # Script chính, chạy bằng CLI
├── README.md                    # Tài liệu này
├── sample_data/
│   └── output_reports/          # Thư mục input MẪU (giả lập report thực tế)
│       ├── scan_chain_cr/setup_check/
│       │   ├── group_summary.csv
│       │   └── group_members.csv
│       └── scan_chain_rx0/hold_check/
│           ├── group_summary.csv
│           └── group_members.csv
└── sample_output/
    └── sorted_critical_violations.csv   # Output MẪU sau khi chạy thử
```

> Trong thực tế, `output_reports/` của bạn có thể có rất nhiều cấp thư mục
> con lồng nhau (vd: `output_reports/<block>/<corner>/<group>/...`) — script
> không quan tâm độ sâu, nó dùng `os.walk()` để tự động duyệt hết.

## 2. Input cần có

Với **mỗi** thư mục báo cáo con (ở bất kỳ độ sâu nào trong cây thư mục gốc),
cần có 2 file:

### `group_summary.csv`
Chứa giá trị slack tệ nhất (worst slack) của mỗi group. Cột cần có 1 trong 2
tên sau (không phân biệt hoa/thường): `worst_slack` hoặc `slack`.

```csv
group_name,worst_slack,num_paths
SETUP_CR_GROUP_A,-0.512,12
SETUP_CR_GROUP_C,-0.834,8
```

### `group_members.csv`
Chứa chi tiết từng path (startpoint/endpoint/slack/clock...) thuộc các
group trên. Bắt buộc phải có cột `slack` để đối chiếu với
`group_summary.csv`.

```csv
startpoint,endpoint,slack,launch_clock,capture_clock
U_CR_FF1/Q,U_CR_FF2/D,-0.512,clk_cr,clk_cr
U_CR_FF5/Q,U_CR_FF6/D,-0.834,clk_cr,clk_cr
```

**Cách script đối chiếu:** với mỗi giá trị `worst_slack` trong
`group_summary.csv` mà nhỏ hơn ngưỡng (`< threshold`), script sẽ tìm trong
`group_members.csv` tất cả các dòng có cột `slack` **trùng giá trị đó**, rồi
lấy ra các cột cần quan tâm.

## 3. Cách dùng

### Chạy nhanh với tham số mặc định
(mặc định: quét thư mục `output_reports`, ngưỡng `-0.4`, xuất ra
`sorted_critical_violations.csv`)

```bash
python3 collect_data.py
```

### Chạy thử với dữ liệu mẫu đi kèm

```bash
python3 collect_data.py --root sample_data/output_reports \
                         --out sample_output/sorted_critical_violations.csv \
                         --threshold -0.4
```

Kết quả mong đợi — file `sorted_critical_violations.csv`:

```csv
directory,startpoint,endpoint,slack,launch_clock,capture_clock
scan_chain_rx0/hold_check,U_RX0_FF3/Q,U_RX0_FF4/D,-0.451,clk_rx0,clk_rx0
scan_chain_cr/setup_check,U_CR_FF1/Q,U_CR_FF2/D,-0.512,clk_cr,clk_cr
scan_chain_cr/setup_check,U_CR_FF5/Q,U_CR_FF6/D,-0.834,clk_cr,clk_cr
```

### Các tham số dòng lệnh (CLI)

| Tham số            | Viết tắt | Mặc định                          | Ý nghĩa |
|---------------------|----------|-------------------------------------|---------|
| `--root`            | `-r`     | `output_reports`                    | Thư mục báo cáo gốc cần quét |
| `--out`              | `-o`     | `sorted_critical_violations.csv`    | File CSV kết quả tổng hợp |
| `--threshold`        | `-t`     | `-0.4`                              | Ngưỡng slack: lấy các giá trị `< threshold` |
| `--columns`          | `-c`     | `startpoint endpoint slack launch_clock capture_clock` | Danh sách cột cần trích từ `group_members.csv` |
| `--quiet`            | `-q`     | (tắt)                               | Không in log từng thư mục, chỉ in thông báo cuối |

Ví dụ tùy biến: chỉ lấy slack nặng hơn `-0.8` và thêm cột `transition`:

```bash
python3 collect_data.py --root /data/nas-raid-0/truongnx/output_reports \
                         --threshold -0.8 \
                         --columns startpoint endpoint slack launch_clock capture_clock transition \
                         --out critical_slack_lt_0.8.csv
```

## 4. Output

Một file CSV duy nhất với cột đầu tiên `directory` (đường dẫn tương đối của
thư mục báo cáo con, để biết vi phạm thuộc group/corner nào), theo sau là
các cột đã chọn ở `--columns`.

File này có thể mở trực tiếp bằng Excel để sort theo `slack` tăng dần, lọc
theo `launch_clock`, hoặc paste vào báo cáo/email.

## 5. Một số lưu ý khi áp dụng vào dữ liệu thực tế

- **Tên cột không phân biệt hoa/thường**: script tự động chuyển header về
  lowercase và bỏ khoảng trắng dư trước khi xử lý, nên không lo file gốc
  viết hoa/thường lẫn lộn (`Slack`, `SLACK`, `slack `...).
- **1 thư mục lỗi không làm dừng cả quá trình quét**: nếu 1 cặp file
  summary/members bị lỗi format, script chỉ in cảnh báo (`Lỗi tại ...`) và
  tiếp tục quét các thư mục còn lại.
- **Đối chiếu theo giá trị slack dạng chuỗi**: script so khớp `slack` giữa
  2 file theo đúng chuỗi ký tự (sau khi `strip()`), nên nếu 2 file có cùng
  giá trị nhưng định dạng số khác nhau (ví dụ `-0.40` vs `-0.4`) thì sẽ
  **không khớp**. Nếu gặp tình huống này trong dữ liệu thực tế, có thể cần
  chuẩn hóa định dạng số trước khi so sánh (so sánh bằng `float` thay vì
  chuỗi) — báo lại nếu cần mình bổ sung phần này.
- **Nhiều cấp thư mục lồng nhau**: không cần chỉnh gì, `os.walk()` xử lý
  mọi độ sâu tự động.
- **File rất lớn / rất nhiều thư mục**: script đọc từng file theo dòng
  (streaming qua `csv.DictReader`), không load toàn bộ vào RAM một lúc, nên
  phù hợp với report tree lớn.

## 6. Mở rộng trong tương lai (gợi ý)

- Thêm tham số `--recursive-depth` nếu muốn giới hạn độ sâu quét.
- Thêm so sánh slack bằng `float` thay vì chuỗi để tránh lệch định dạng số.
- Thêm cột `group_name` (lấy từ `group_summary.csv`) vào output để biết rõ
  vi phạm thuộc group nào, không chỉ thư mục nào.
- Xuất thêm thống kê tổng số vi phạm theo từng `launch_clock`/`capture_clock`.
