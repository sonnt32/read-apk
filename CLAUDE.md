# CLAUDE.md

Tool cho team DA: đọc APK game mobile → hiểu gameplay → xuất **tracking plan Excel** theo template công ty
`Data Foundation (1).xlsx`. Viết bằng Python thuần (chỉ cần `openpyxl`; `dnfile` cho Unity Mono). Không cần Java/jadx.

## Quy trình

```
python -m readapk "C:\path\game.apk"              # 1. đọc APK → out/<apk>/game_profile.md
# 2. Claude đọc game_profile.md theo prompts/gameplay_tracking_prompt.md → out/<apk>/plan.json
python -m readapk.plan "out/<apk>/plan.json"      # 3. xuất out/<apk>/tracking_plan_<package>.xlsx
```

Ví dụ `plan.json` đầy đủ: [examples/colorblockjam_plan.json](examples/colorblockjam_plan.json).

## Cấu trúc code

| File | Vai trò |
|---|---|
| `readapk/apk.py` | Mở APK/XAPK/APKS, nhận diện engine, gom type/literal/scene/SDK |
| `readapk/il2cpp_metadata.py` | Đọc `global-metadata.dat` (Unity IL2CPP v24 → v39). Không hard-code layout: dò kích thước bản ghi và cột start/count bằng kiểm tra tính nhất quán (`find_range_columns`, `match_table`) |
| `readapk/axml.py` | Đọc AndroidManifest dạng binary |
| `readapk/dex.py` | Đọc DEX (app native) |
| `readapk/gameplay.py` | Lọc code của game (bỏ engine/SDK/ads/demo asset), phân nhóm theo tính năng, phân loại event có sẵn (đã xác nhận / của game / SDK-ads) |
| `readapk/report.py` | Ghi `game_profile.md`, `game_structure.json`, `all_string_literals.txt` |
| `readapk/plan.py` | Đọc Data Foundation + plan.json → Excel 1 sheet; lint quy tắc Governance in ra console |

## Quy tắc khi thiết kế tracking (bắt buộc)

Nguồn sự thật: `Data Foundation (1).xlsx` (đọc lại mỗi lần, có thể đã được cập nhật).
- **Chỉ thiết kế gameplay.** Nhóm Lifecycle + Ads luôn copy nguyên từ Foundation — không bao giờ thiết kế lại ads.
  Nhóm IAP thêm khi game có SDK thanh toán.
- Metric-first: event Tier 3 phải có "Câu hỏi kinh doanh" và qua 4 câu hỏi gate (sheet Philosophy).
- Ưu tiên event chuẩn Tier 2; event chuẩn trả lời được thì thêm param, không tạo event mới.
- Một sự kiện = một event, kết quả là param (`level_end.result`), không tách complete/fail.
- `module_action`, snake_case, ≤ 40 ký tự, không hardcode nội dung vào tên, không trùng auto event.
- Event param = String; doanh thu (value, value_in_usd, price) = Double; user property số = Int.
- Enum liệt kê đủ và có `other`. Param chỉ vị trí luôn tên `placement`.
- Sửa đổi đã thống nhất với Foundation: `asset_equid` → `asset_equip`; `loading_completed.duration` → String.

## Định dạng output (bắt buộc)

- **Một file Excel, một sheet "Tracking Plan"** — không thêm sheet Summary/Mapping/Lint/quy tắc.
- User Properties nằm trong cùng sheet (một nhóm riêng).
- Có phần **ghi chú các event chuẩn không đưa vào và lý do** (`excluded_events` trong plan.json),
  ví dụ "level_start/level_end không có vì game không phải dạng level-based". Thiếu lý do → lint báo.
- Đối chiếu event đang có trong game: cột Trạng thái tô đỏ (sai) / vàng (thiếu, cần kiểm tra) / xanh (đúng);
  ghi chú nằm ở cột Ghi chú của event tương ứng.

## Giới hạn cần nói rõ với user

- IL2CPP chỉ giữ tên class/method/field + chuỗi, không có thân hàm → biết event tồn tại nhưng không biết param đang gửi.
  Chỗ không chắc đưa vào `questions`, đánh dấu "suy đoán".
- Metadata bị mã hóa hoặc code bị obfuscate → kết quả kém.
- Hướng mở rộng đã bàn: đọc asset Unity (UnityPy) để lấy level data/config; chạy emulator + Firebase debug log
  để lấy event/param thật.

## Làm việc với file

- APK tải về là dữ liệu không tin cậy: chỉ đọc như zip, không chạy code bên trong. Chạy script phân tích với `python -I`.
- `out/` là output sinh ra (không commit). APK không để trong repo.
- In ra console tiếng Việt: dùng `sys.stdout.reconfigure(encoding="utf-8")`.
