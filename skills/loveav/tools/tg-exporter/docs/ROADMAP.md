# Roadmap

路线图只记录当前优先级，不替代 `HANDOFF.md` 的实时状态。

## 已完成基线（v0.1.4 + main hotfix）

- [x] PySide6 Windows GUI
- [x] Telethon 用户账号登录 + Session 复用
- [x] Windows system proxy 自动检测/传入 Telethon
- [x] 本地轮转日志与中文错误诊断
- [x] API 设置 / 重置登录 / 打开日志目录
- [x] 完整群组 catalogue + searchable focused workspace
- [x] 工作群选择跨启动持久化
- [x] 每群独立导出模式
- [x] Date range / current unread / since-last
- [x] Current-unread frozen snapshot
- [x] Option B：每群独立“导出后标已读”，默认 OFF
- [x] Text/caption-only export
- [x] 每群独立 `result.json`
- [x] 每次独立 batch directory
- [x] Desktop-style 核心 JSON serializer
- [x] 本地 checkpoint 单调不减
- [x] qasync-safe 非阻塞 login/dialog 流
- [x] one-file EXE + portable ZIP + SHA256SUMS Release
- [x] shutdown `disconnect()` await/None hotfix 已在 main、CI 通过

## P0：最近一次用户反馈闭环

- [ ] 将 main 上 shutdown hotfix 发布为新 PATCH Release（建议 v0.1.5，若无其他版本规划冲突）
- [ ] 用户真实验证“关闭程序不再弹 Unhandled exception”

## P1：真实 Telegram 行为验证

- [ ] 5-group mixed-mode E2E
- [ ] `导出后标已读` OFF：确认多端未读不变化
- [ ] `导出后标已读` ON：确认只推进到 frozen upper id
- [ ] 导出过程中新增消息保持下一批未读
- [ ] since-last 真实群 checkpoint 行为

## P1：输出可靠性

- [ ] `result.json.tmp → replace` atomic write
- [ ] sanitized group-title folder collision 防护（稳定 chat-id suffix）
- [ ] 写文件中断/异常回归测试

## P1：Telegram Desktop 纯文本兼容

- [ ] 同一群同一窗口官方 Desktop differential test
- [ ] 正确 chat type
- [ ] 正确 top-level chat id 规则
- [ ] 保留原始首尾 whitespace

## P2：JSON 兼容增强

- [ ] rich text entity mapping（bold/link/mention/code/...）
- [ ] forward metadata
- [ ] service message 的文本分析友好策略

注意：媒体 metadata 完整克隆不是当前产品目标；不要把“兼容”扩展成自动下载媒体。

## P2：GUI / 可用性

- [ ] 每行实时消息级进度
- [ ] 一键仅重试失败群
- [ ] 更清晰的批次完成摘要
- [ ] 可选保存每群更多 UI 规则（谨慎保持 settings schema 向后兼容）

## P2：内部技术债

- [ ] 收敛 `gui.py → gui_async.py → focused_gui.py` 三层继承
- [ ] 在重构前补 qasync dialog / shutdown 回归测试
- [ ] 明确 Telethon service lifecycle state machine

## 暂不推进

除非用户重新提出：

- 360/杀软误报治理
- 代码签名申请
- 完整媒体备份
- 云端消息数据库
- master archive / historical merge
- HTML 作为独立 Telegram 抓取格式

未来如果增加 HTML，采用：

```text
Telegram → result.json → local preview.html
```

JSON 继续作为唯一权威数据源。
