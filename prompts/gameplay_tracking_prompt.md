# Prompt: thiết kế tracking gameplay → plan.json → Excel

Quy trình:
1. `python -m readapk game.apk` → `out/<game>/game_profile.md`
2. Đưa prompt dưới đây + `game_profile.md` + `Data Foundation (1).xlsx` cho Claude → `out/<game>/plan.json`
3. `python -m readapk.plan "out/<game>/plan.json"` → `out/<game>/tracking_plan_<package>.xlsx`

Nhóm Lifecycle và Ads được tool copy nguyên từ Data Foundation, KHÔNG cần thiết kế.

---

Bạn là Data Analyst của team DA. File `game_profile.md` là cấu trúc code của game, được trích ra từ APK
(class, method, field, enum, chuỗi log analytics, event đang có). File `Data Foundation (1).xlsx` là
MASTER TRACKING TEMPLATE của công ty: mọi quy tắc trong đó là bắt buộc.

Nhiệm vụ: thiết kế tracking **gameplay** cho game này, xuất ra **một file JSON** đúng schema bên dưới.

Quy tắc (theo Data Foundation):
- Metric-first: mọi event Tier 3 phải có `question` (câu hỏi kinh doanh) và qua 4 câu hỏi gate ở sheet Philosophy.
- Ưu tiên event chuẩn (sheet Events, nhóm 3–6). Nếu event chuẩn trả lời được thì THÊM PARAM (`extra_params`),
  không tạo event mới. Event Tier 3 chỉ dùng khi không có event chuẩn nào phù hợp.
- Một sự kiện là một event, kết quả đưa vào param (ví dụ `level_end.result`, không tách thành complete/fail).
- Tên theo dạng `module_action`, snake_case, ≤ 40 ký tự, không hardcode nội dung, không trùng auto event.
- Event param là String; doanh thu (value, value_in_usd, price) là Double; user property dạng số là Int.
- Enum phải liệt kê đủ giá trị và có `other`. Param chỉ vị trí luôn đặt tên `placement`.
- Không thiết kế event quảng cáo (đã có trong template). Điểm gameplay có ads: dùng source/placement (ví dụ `source=reward_ad`).
- Mọi kết luận về game dẫn class/method làm bằng chứng (`evidence`, `code_location`). Chỗ không chắc → đưa vào `questions`.
- Đối chiếu event / param / user property đang có trong game → `existing_mapping`
  với status: `red` (sai hoàn toàn), `yellow` (thiếu / cần sửa / dev cần kiểm tra), `green` (đúng).

Schema `plan.json` (xem ví dụ đầy đủ: `examples/colorblockjam_plan.json`):

```json
{
  "game": {"name": "", "package": "", "version": "", "engine": "", "genre": "",
           "core_loop": "", "summary": "",
           "features": [{"name": "", "evidence": "Class.Method, ..."}]},
  "include_iap": true,
  "level_based": true,
  "excluded_events": {"level_reopen": "lý do không dùng event chuẩn này, dẫn bằng chứng trong code"},
  "standard_events": [
    {"event": "level_start", "priority": "P0|P1|P2", "status": "Mới|Sửa|Giữ",
     "trigger": "(tùy chọn, ghi đè trigger chuẩn)",
     "code_location": "Class.Method",
     "param_values": {"play_type": "giá trị enum cụ thể cho game này"},
     "extra_params": [{"name": "", "type": "String", "values": "a | b | other", "metric": ""}],
     "note": ""}
  ],
  "custom_events": [
    {"group": "", "tier": "T3", "event": "", "priority": "", "question": "", "trigger": "",
     "code_location": "", "params": [{"name": "", "type": "String", "values": "", "metric": ""}]}
  ],
  "user_properties": [
    {"tier": "T3", "property": "", "type": "String|Int", "meaning": "", "update_when": "", "values": "", "note": ""}
  ],
  "existing_mapping": [
    {"old_event": "", "old_params": "", "new_event": "", "new_params": "", "note": "", "status": "red|yellow|green"}
  ],
  "questions": ["câu hỏi cho dev / PM"]
}
```

`standard_events` chỉ liệt kê event chuẩn của nhóm 4–6 (Level, Economy, Tutorial/Feature/Loading) mà game
này cần, cộng IAP (nhóm 3) nếu `include_iap`.

BẮT BUỘC: mọi event chuẩn nhóm 3–6 (và user property chuẩn) KHÔNG dùng phải có lý do trong `excluded_events`,
ví dụ `"level_start": "Game không phải dạng level-based (sandbox, không có màn chơi)"`. Nếu game không level-based
thì đặt `"level_based": false` và ghi lý do cho `current_level`. Tool báo lint nếu thiếu lý do.

Output cuối là MỘT file Excel, MỘT sheet "Tracking Plan": các nhóm event + nhóm User Properties + phần
ghi chú các event chuẩn không áp dụng. `existing_mapping` được gộp vào cột Ghi chú của event tương ứng.
