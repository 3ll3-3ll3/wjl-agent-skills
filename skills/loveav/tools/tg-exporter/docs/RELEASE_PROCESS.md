# Release Process

本文件定义 TG Exporter Windows 正式版本发布流程。正式用户下载入口是 GitHub Releases，不是 Actions Artifact。

## 1. 什么时候需要 Release

需要：用户可见功能变化、Telegram 行为变化、影响 EXE/tgctl 的 bug 修复、依赖/打包方式变化、需要用户重新下载验证的修复。

通常不需要：纯文档修改、不影响二进制行为的注释。

## 2. 发布前状态检查

先读：

```text
AGENTS.md
HANDOFF.md
docs/ARCHITECTURE.md
docs/DECISIONS.md
docs/TESTING.md
SECURITY.md
```

涉及 CLI/Codex 还必须读 `docs/CODEX_TGCTL.md`。

确认：

- 从最新 main 开发；
- 没有遗漏的冲突/未合并依赖；
- 没有 Session/API 凭据/日志/真实聊天正文进入仓库；
- 新行为有单元测试；
- HANDOFF 明确区分 CI 与真人 Telegram E2E；
- Telegram write safety 没被绕过。

## 3. 版本号

采用 `vMAJOR.MINOR.PATCH` 风格。发布时同步：

1. 根目录 `VERSION`；
2. `pyproject.toml` `[project].version`；
3. `src/telegram_exporter/__init__.py` `__version__`；
4. `docs/releases/vX.Y.Z.md`；
5. `HANDOFF.md` candidate/正式状态。

VERSION、pyproject、package version 不应互相矛盾。

## 4. 分支 / PR

标准流程：

```text
latest main
→ feature/fix branch
→ tests
→ PR
→ Windows CI
→ all green
→ merge
```

用户可见二进制版本的合并提交建议使用：

```text
release: vX.Y.Z
```

这样 push 到 main 后自动触发 Release workflow。

不得为了发版直接在 main 上堆未经 PR/CI 验证的功能代码。

## 5. PR Windows CI（v0.1.9+）

`.github/workflows/windows-build.yml` 至少完成：

```text
Install
pytest -q
GUI + tgctl import check
Build TGExporter one-file EXE
Build tgctl one-file console EXE
Smoke-test TGExporter.exe
Smoke-test tgctl.exe
Upload temporary CI artifacts
```

两种 executable 都必须通过 packaged smoke-test 才能合并。

## 6. 正式 Release workflow

`.github/workflows/release.yml` 在：

- push 到 `main` 且 head commit message 以 `release:` 开头；或
- 手工 `workflow_dispatch`

时执行。不要在 VERSION 未更新时随意 dispatch。

v0.1.9+ 必须完成：

```text
Install
pytest
GUI + tgctl import check
Build TGExporter one-file
Build TGExporter portable onedir
Build standalone tgctl.exe
Copy tgctl.exe into portable TGExporter directory
Smoke-test GUI one-file
Smoke-test GUI portable
Smoke-test standalone tgctl
Smoke-test portable tgctl
Prepare release assets + SHA256SUMS
Create/update GitHub Release
```

## 7. 正式资产（v0.1.9+）

至少：

```text
TGExporter-vX.Y.Z-windows-x64.exe
TGExporter-vX.Y.Z-windows-x64-portable.zip
tgctl.exe
SHA256SUMS.txt
```

Portable ZIP 内应有：

```text
TGExporter/
├─ TGExporter.exe
└─ tgctl.exe
```

以及 PyInstaller onedir 依赖文件。

`SHA256SUMS.txt` 至少记录 GUI one-file、portable zip、standalone tgctl.exe 的 SHA-256。

## 8. Release notes

Release workflow 从：

```text
docs/releases/<VERSION>.md
```

读取正式 notes。notes 必须描述**当前真实行为**，不要复制旧版目录/能力说明导致 Release 页面和二进制不一致。

涉及 tgctl 的版本应明确：

- 新命令；
- read vs write；
- dry-run / batch limit；
- Session reuse / SESSION_BUSY；
- 哪些真实 Telegram write E2E 尚待用户验证；
- 明确不做 MCP/监听/媒体 write 等边界。

## 9. Release 后核验

只有下面全部满足，才能对用户说“新版本已发布”：

- tag 正确；
- target commit 正确；
- `draft=false`；
- `prerelease=false`；
- 所有正式 assets 存在；
- SHA256 与 `SHA256SUMS.txt` 一致；
- Release notes 与当前版本一致；
- Release workflow conclusion=success。

固定最新版入口：

```text
https://github.com/3ll3-3ll3/tg-exporter/releases/latest
```

## 10. 发布后 HANDOFF

Release 成功后必须更新 `HANDOFF.md`：

- 正式版本；
- PR；
- merge/release target commit；
- Release workflow run id；
- 正式资产名与 SHA-256；
- main 是否只有文档类未发布提交；
- 真人 Telegram E2E 已完成/仍待完成清单。

发布后的纯 HANDOFF/docs commit 不需要再发二进制，但正常 Windows CI 仍应通过。

## 11. tgctl 真人写操作

GitHub Actions 不连接用户真实 Telegram。Release 可以在完整 mock/unit/packaged smoke-test 通过后发布，但必须明确：真正 `forward` / `send` 仍需用户在本机账号做 E2E。

真人验证原则：

```text
关闭 GUI
→ tgctl dry-run
→ 用户确认
→ Saved Messages 真正写入
```

不要自行向陌生人/陌生群发消息，也不要故意制造 FloodWait。

## 12. Hotfix 原则

明确 bug → regression test → Windows CI → 影响实际使用则尽快 PATCH Release。不要把多个未经验证的大功能塞进紧急 hotfix。

## 13. 品牌与兼容路径

用户可见品牌：

```text
TG Exporter / TG 导出器
TGExporter.exe
tgctl.exe
```

内部 Python package 继续 `telegram_exporter`。

历史本地目录继续：

```text
%APPDATA%\TelegramMultiChatExporter\
```

以确保 API settings、Telegram Session、导出设置和 checkpoint 可跨版本复用。
