# Video Automation

Dự án gồm **2 pipeline** xử lý video theo lô để đăng Reels / Stories:

| Pipeline | Dùng khi nào | Chạy bằng |
|----------|-------------|-----------|
| **Batch** | Video đã có âm thanh — thêm background, nhạc nền, text | `run_videos.bat` |
| **Voice** | Video chưa có giọng đọc — generate TTS, subtitle tự động, nhạc nền, text | `run_voice.bat` |

---

## Cài đặt

Yêu cầu **Python 3.10+**. Chạy 1 lần:

```bash
pip install -r requirements.txt
```

---

## Cấu trúc dự án

```
project/
├── src/
│   ├── ffmpeg_utils.py          ← Shared: FFmpeg helpers
│   ├── image_utils.py           ← Shared: PIL text rendering
│   ├── batch_processor.py       ← Logic pipeline Batch
│   └── voice_processor.py       ← Logic pipeline Voice
│
├── config/
│   ├── videos_config.json       ← Cấu hình pipeline Batch
│   └── voice_config.json        ← Cấu hình pipeline Voice
│
├── background.jpg               ← Ảnh nền (kích thước = kích thước output)
├── audio/
│   └── audio_template.wav       ← Nhạc nền mặc định
│
├── source_video/                ← Video nguồn cho pipeline Batch
├── source_video_not_voice/      ← Video nguồn cho pipeline Voice
├── output/                      ← Output pipeline Batch (tự tạo)
├── output_voice/                ← Output pipeline Voice (tự tạo)
│
├── run_videos.py                ← Entry point Batch
├── run_voice.py                 ← Entry point Voice
├── run_videos.bat               ← Windows launcher Batch
├── run_voice.bat                ← Windows launcher Voice
├── run.bat                      ← Menu chọn pipeline
└── requirements.txt
```

---

## Pipeline 1 — Batch (`run_videos.bat`)

### Cách dùng

1. Bỏ video vào `source_video/`
2. Mở `config/videos_config.json`, chỉnh `"text"` và các tham số khác
3. Double-click `run_videos.bat` — hoặc:

```bash
python run_videos.py
# Chỉ định config khác:
python run_videos.py --config config/videos_config.json
```

Output: `output/<tên_gốc>_output.mp4`

### `config/videos_config.json` — tham số

**Video**

| Key | Mặc định | Ý nghĩa |
|-----|----------|---------|
| `source_dir` | `"source_video"` | Thư mục chứa video nguồn |
| `output_dir` | `"output"` | Thư mục xuất output (tự tạo) |
| `background_path` | `"background.jpg"` | Ảnh nền. Kích thước ảnh = kích thước output |
| `video_scale` | `0.95` | Thu nhỏ video xuống X%. `0.95` = 95%, video luôn được canh giữa |

**Âm lượng**

| Key | Mặc định | Ý nghĩa |
|-----|----------|---------|
| `bg_music_volume` | `0.25` | Âm lượng nhạc nền (`0.0` = tắt, `1.0` = nguyên bản) |
| `original_audio_volume` | `1.0` | Âm lượng audio gốc của video |
| `audio_path` | `"audio/audio_template.wav"` | File nhạc nền. Tự loop nếu ngắn hơn video |

**Text overlay** — hiện xuyên suốt, dùng chung cho tất cả video

| Key | Mặc định | Ý nghĩa |
|-----|----------|---------|
| `text` | `"Comment Below"` | Nội dung text. Dùng `\n` để xuống dòng |
| `text_position_x` | `"center"` | Vị trí ngang: `"center"` \| `"left"` \| `"right"` \| số pixel từ trái |
| `text_position_y` | `0.88` | Vị trí dọc (`0.0` = trên, `1.0` = dưới) |
| `text_font_size` | `48` | Cỡ chữ (pixel) |
| `text_color` | `[255, 255, 255]` | Màu chữ RGB. Trắng = `[255,255,255]`, vàng = `[255,220,0]` |
| `text_stroke_color` | `[0, 0, 0]` | Màu viền chữ RGB |
| `text_stroke_width` | `2` | Độ dày viền (pixel). `0` = tắt viền |
| `text_font_path` | `null` | Đường dẫn file `.ttf`. `null` = dùng Arial |
| `text_padding_x` | `40` | Lề hai bên khi text xuống dòng (pixel) |

**Chất lượng xuất**

| Key | Mặc định | Ý nghĩa |
|-----|----------|---------|
| `output_fps` | `30` | Frame/giây |
| `output_codec` | `"libx264"` | Codec video (H.264) |
| `output_preset` | `"fast"` | Tốc độ encode: `ultrafast`→nhanh/file to ↔ `slow`→chậm/file nhỏ |
| `output_crf` | `23` | Chất lượng: `18` = cao, `23` = cân bằng, `28` = file nhỏ |
| `output_audio_codec` | `"aac"` | Codec audio |

---

## Pipeline 2 — Voice (`run_voice.bat`)

> Yêu cầu kết nối Internet (Microsoft Edge TTS).

### Cách dùng

1. Bỏ video vào `source_video_not_voice/`
2. Mở `config/voice_config.json`, thêm entry vào mảng `"videos"`
3. Double-click `run_voice.bat` — hoặc:

```bash
python run_voice.py
# Chỉ định config khác:
python run_voice.py --config config/voice_config.json
```

Output: `output_voice/<tên_gốc>_output.mp4`

### `config/voice_config.json` — cấu trúc

File gồm 2 phần:
- `"settings"` — cấu hình mặc định cho tất cả video
- `"videos"` — danh sách video, có thể override từng key từ settings

```json
{
  "settings": { ... },
  "videos": [
    {
      "video": "1.mp4",
      "audio_script": "Nội dung giọng đọc...",
      "text": "Comment \"vendor\"\nto get my vendor list",
      "voice": "en-US-AndrewNeural",
      "voice_rate": "+5%"
    }
  ]
}
```

### Phần `videos` — cấu hình từng video

| Key | Bắt buộc | Ý nghĩa |
|-----|:--------:|---------|
| `video` | ✓ | Tên file trong `source_dir` |
| `audio_script` | ✓ | Script TTS — giọng sẽ đọc đoạn text này |
| `text` | ✓ | Text tĩnh CTA hiện xuyên suốt video. Hỗ trợ `\n` |
| `voice` | — | Override giọng đọc (nếu khác `settings`) |
| `voice_rate` | — | Override tốc độ đọc |
| `voice_volume` | — | Override âm lượng TTS |

### Phần `settings` — cấu hình chung

**Đường dẫn**

| Key | Mặc định | Ý nghĩa |
|-----|----------|---------|
| `source_dir` | `"source_video_not_voice"` | Thư mục video nguồn |
| `output_dir` | `"output_voice"` | Thư mục xuất output |
| `background_path` | `"background.jpg"` | Ảnh nền |
| `video_scale` | `0.95` | Thu nhỏ video nguồn |

**Giọng đọc TTS**

| Key | Mặc định | Ý nghĩa |
|-----|----------|---------|
| `voice` | `"en-US-AndrewNeural"` | Giọng Neural. Xem danh sách đầy đủ ở cuối trang |
| `voice_rate` | `"+0%"` | Tốc độ: `"+20%"` = nhanh hơn, `"-10%"` = chậm hơn |
| `voice_volume` | `"+0%"` | Âm lượng TTS (offset %) |
| `voice_audio_volume` | `1.0` | Hệ số khuếch đại TTS khi mix (0.0–2.0) |

**Audio mix**

| Key | Mặc định | Ý nghĩa |
|-----|----------|---------|
| `original_audio_volume` | `0.25` | Âm lượng audio gốc video |
| `mute_original_audio` | `false` | `true` = tắt hoàn toàn audio gốc |
| `bg_music_enabled` | `true` | Bật/tắt nhạc nền |
| `bg_music_path` | `"audio/audio_template.wav"` | File nhạc nền |
| `bg_music_volume` | `0.15` | Âm lượng nhạc nền |

**Subtitle chạy theo giọng đọc**

| Key | Mặc định | Ý nghĩa |
|-----|----------|---------|
| `subtitle_font_size` | `46` | Cỡ chữ subtitle (pixel) |
| `subtitle_words_per_line` | `3` | Số từ tối đa mỗi dòng hiển thị |
| `subtitle_position_y` | `0.72` | Vị trí dọc (`0.0`=trên, `1.0`=dưới) |
| `subtitle_color` | `[255,255,255]` | Màu chữ RGB |
| `subtitle_stroke_color` | `[0,0,0]` | Màu viền RGB |
| `subtitle_stroke_width` | `2` | Độ dày viền |
| `subtitle_font_path` | `null` | Đường dẫn font `.ttf`. `null` = Arial |

**Text tĩnh CTA** — tương tự `text_*` bên pipeline Batch

**Chất lượng xuất** — tương tự `output_*` bên pipeline Batch

### Cảnh báo thời lượng

| Tình huống | Hành động |
|-----------|-----------|
| Audio TTS **dài hơn** video | Cảnh báo + **tự cắt** audio tại thời điểm kết thúc video |
| Audio TTS ngắn hơn video **>3s** | Cảnh báo thông tin (phần còn lại không có giọng) |

Để điều chỉnh: thêm/bớt nội dung `audio_script`, hoặc tăng/giảm `voice_rate`.

---

## Ví dụ nhanh

**Đổi text và chạy Batch:**
```json
"text": "Comment \"list\" to get my vendor list"
```

**Tắt audio gốc, chỉ dùng voice TTS + nhạc nền:**
```json
"mute_original_audio": true,
"bg_music_enabled": true,
"bg_music_volume": 0.15
```

**Text giữa màn hình:**
```json
"text_position_x": "center",
"text_position_y": 0.50
```

**Dùng font tùy chỉnh:**
```json
"text_font_path": "C:/Windows/Fonts/BeVietnamPro-Bold.ttf",
"subtitle_font_path": "C:/Windows/Fonts/BeVietnamPro-Bold.ttf"
```

**Xuất chất lượng cao:**
```json
"output_preset": "slow",
"output_crf": 18
```

---

## Danh sách voice gợi ý (en-US)

| Voice | Giới tính | Phong cách |
|-------|:---------:|-----------|
| `en-US-AndrewNeural` | Nam | Tự nhiên, thân thiện |
| `en-US-BrianNeural` | Nam | Chuyên nghiệp |
| `en-US-ChristopherNeural` | Nam | Trầm, uy tín |
| `en-US-AvaNeural` | Nữ | Tự nhiên, rõ ràng |
| `en-US-EmmaNeural` | Nữ | Trẻ trung, năng động |

Xem toàn bộ danh sách:
```bash
python -c "import asyncio, edge_tts; voices = asyncio.run(edge_tts.list_voices()); [print(v['ShortName'], v['Gender']) for v in voices if v['Locale'].startswith('en-US')]"
```

---

## Lưu ý

- Video nguồn hỗ trợ: `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm`, `.m4v`
- Tên file Unicode (tiếng Việt, tiếng Trung, emoji) được xử lý tự động
- Kích thước output = kích thước `background.jpg` — thay ảnh là thay resolution
- Nhạc nền tự loop nếu ngắn hơn video, tự cắt nếu dài hơn
- Pipeline Voice cần kết nối Internet để gọi Microsoft Edge TTS
