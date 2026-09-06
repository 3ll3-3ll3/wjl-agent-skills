# Deployment / Distribution

TG Exporter 没有服务器部署。这里的“部署”仅指：**构建 Windows 二进制、生成 Candidate、发布 GitHub Release、以及回滚到历史 Release。**

## 1. 当前版本

在 v0.3.1 正式 Release 完成之前：

```text
Production: v0.3.0
commit: 8e230e33ea928bcf71296e4e5379b097446dbec5
release target: v0.3.1 via PR #24
```

`v0.3.0` 以及所有历史 tag/Release 不得移动、覆盖、删除或原地重建。

## 2. 用户本地数据不是发布资产

Release/CI artifact 永远不得包含 `%APPDATA%\TelegramMultiChatExporter\` 下的 API credentials、Telegram Session/journal/lock、IPC secret、settings/state/job metadata、logs/avatar cache 或用户导出 JSON。升级继续复用既有 AppData；不要为安装/修复而清空、迁移或复制 Session。

## 3. Candidate CI

v0.3.1 PR gate 包括：full pytest、focused regressions、compileall、`git diff --check`、imports、source search-filter smoke、one-file/portable/tgctl PyInstaller、standalone+portable packaged domain+regex smoke、standalone+portable `SESSION_BUSY` JSON/native exit=8、packaged GUI/tgctl smoke、clean tree、Candidate SHA-256 + artifact。

Candidate artifact 只用于验收，不是正式分发入口；正式 Release 必须从 merged main 重建，因此 hash 可以不同。

## 4. 正式 Release 流程

默认流程：

```text
main
→ branch/PR
→ Windows CI green
→ local Windows / real-account acceptance
→ user explicit authorization
→ merge
→ Release workflow rebuild
→ verify tag/target/assets/SHA
```

### v0.3.1 one-release waiver

2026-08-30 用户明确授权 v0.3.1 **不等待剩余真人 E2E 直接发布**。这只对 v0.3.1 生效：真人项目记为 `waived/unverified`，不是 PASS。未来版本恢复默认人验门槛，除非用户再次明确豁免。

## 5. 正式 Release 资产

```text
TGExporter-vX.Y.Z-windows-x64.exe
TGExporter-vX.Y.Z-windows-x64-portable.zip
tgctl.exe
SHA256SUMS.txt
```

Release workflow 必须拒绝覆盖已经存在的 tag/Release。Portable ZIP 内包含同版本 `tgctl.exe`。

## 6. 发布前/后核验

发布前至少确认：

- VERSION / package version / notes 目标一致；
- no secrets/session/chat-body in repo/CI；
- full tests/builds/smokes pass；
- packaged search-filter smoke pass；
- legacy lock → `SESSION_BUSY` + native exit 8；
- write safety / no-auto-retry invariant 未破坏；
- human gate 是 PASS，或像 v0.3.1 一样有明确 release-specific waiver；
- Release notes 准确说明未验证项。

只有以下全部满足才能宣称“已发布”：

```text
correct tag
correct target commit
draft=false
prerelease=false
expected four assets exist
SHA256SUMS matches assets
release workflow conclusion=success
release notes match behavior
```

## 7. Rollback

二进制回滚：从 GitHub Releases 下载上一个已验证版本；保留 `%APPDATA%\TelegramMultiChatExporter\`；不删除/重建 `telegram.session`。未来若有不可逆本地 schema migration，必须提前在 ADR/HANDOFF/Release Notes 描述备份与回滚。

## 8. No cloud deployment

不要为当前项目创建 Cloudflare Worker、VPS、Web API、remote DB、Windows Service 或 24/7 server。daemon 是本机按需用户态进程，不是云服务。
