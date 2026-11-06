# read-apk

Đọc file APK game, trích xuất cấu trúc code gameplay để viết kịch bản tracking event.
Viết bằng Python thuần, không cần Java/jadx/Il2CppDumper.

## Chạy

```
python -m readapk "C:\path\game.apk"
python -m readapk game.xapk -o out/mygame
```

Output trong `out/<tên apk>/`:

| File | Nội dung |
|---|---|
| `game_profile.md` | Báo cáo cho người/Claude đọc: SDK, scene, event có sẵn, class gameplay theo tính năng |
| `game_structure.json` | Dữ liệu đầy đủ dạng JSON |
| `all_string_literals.txt` | Toàn bộ chuỗi trong code (để tra cứu) |

## Sinh file Excel tracking plan

1. Claude đọc `game_profile.md` theo [prompts/gameplay_tracking_prompt.md](prompts/gameplay_tracking_prompt.md)
   và viết `out/<game>/plan.json` (chỉ phần gameplay).
2. Tạo Excel theo template Data Foundation:

```
python -m readapk.plan "out/<game>/plan.json"
```

File `tracking_plan_<package>.xlsx` có một sheet duy nhất **Tracking Plan**: các nhóm event, nhóm User Properties,
và phần ghi chú các event chuẩn không áp dụng kèm lý do (`excluded_events` trong plan.json).
- Nhóm Lifecycle + Ads luôn copy nguyên từ `Data Foundation (1).xlsx`; nhóm IAP thêm khi game có IAP.
- Đã áp dụng các sửa đổi: `asset_equid` → `asset_equip`, `loading_completed.duration` → String.
- Lint in ra console: kiểm tra quy tắc Governance (naming, kiểu dữ liệu, enum thiếu `other`, `placement`,
  event chuẩn bị loại mà thiếu lý do...).
- Event đang có trong game: trạng thái tô màu đỏ / vàng / xanh theo quy tắc Governance, ghi chú đối chiếu nằm ở cột Ghi chú.

## Hỗ trợ

| Loại app | Đọc được |
|---|---|
| Unity IL2CPP (metadata v24 → v39 / Unity 6) | class, method, field, enum, assembly, string literal |
| Unity Mono | như trên (cần `pip install dnfile`) |
| Native Java/Kotlin | class + method trong DEX, string |
| XAPK / APKS (split APK) | tự mở các APK con |

Ads bị loại khỏi phần gameplay (class quảng cáo và tên event ads được liệt kê riêng ở cuối báo cáo).

## Hạn chế

- `global-metadata.dat` bị mã hóa (một số game có bảo vệ): tool báo lỗi, chưa giải mã được.
- IL2CPP không giữ code thân hàm, nên chỉ có tên. Biết `LevelManager.OnLevelComplete` tồn tại
  nhưng không biết bên trong làm gì.
- Code bị obfuscate (tên class thành `a`, `b`...) thì báo cáo ít giá trị.
- Chuỗi literal trong IL2CPP không gắn với class nào; phân loại event/SDK là ước lượng.
