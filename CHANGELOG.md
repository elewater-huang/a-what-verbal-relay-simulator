# Changelog / 版本紀錄

All notable changes to this project are documented here. / 本專案的重要修改記錄於此。

## [0.1.1] — 2026-11-18

Closer circle layout / 貼近式圍圈視角：

- Move host to the bottom center and seat all participants around a complete ring (not a semicircle).
- Use a compact ellipse with a 1.16:1 width-to-height ratio, without perspective depth or a distant meeting-table look.
- Keep left seat 1 on the screen's left and right seat 1 on its right; seat aliases remain unchanged.
- Add automated geometry tests for host position, mirrored directions, and compact aspect ratio.
- Refresh the README screenshot / 更新 README 執行截圖。

## [0.1.0] — 2026-11-18

Initial bilingual desktop prototype / 首次中英文桌面原型：

- Tkinter circular layout with 8 virtual participants plus a human host by default (configurable 3–16).
- Unique physical seat mapping (e.g. Left 1 = Right 8).
- Six fixed Chinese / English phrases with upstream yellow and downstream green visual events.
- Question relay back to the host and answer relay out to the asking participant.
- Independent left/right streams, adjustable response interval (2 s default), voice speed, and CSV event export.
- Optional local TTS and push-to-talk speech recognition; microphone/audio compatibility is unverified on some devices.
- Six engine unit tests.

### Known limitations / 已知限制

- Same-side ambiguous questions are resolved FIFO.
- Synthetic speech is queued and may lag the animated events under high traffic.
- Replay not yet implemented; use exported CSV logs.