# TG Exporter 内嵌集成

TG Exporter 是 LoveAV 的本地 Telegram 读取助手，不是第七个业务功能。完整可维护源码位于：

```text
tools/tg-exporter/
```

LoveAV 仓库中的这份源码是后续开发真源。原独立 `tg-exporter` 仓库、历史分支、Tag 和 Release 保持原样，本 Skill 不归档、不删除也不修改它们。

## 职责分界

- TG Exporter：登录 Telegram、读取会话和消息、分页、返回结构化身份与消息数据。
- LoveAV：理解自然语言、选择读取范围、自动续页、执行六个业务功能、组织结果和可疑项。
- TG Exporter 不内置 MissAV、PikPak、女优 Tag 或其他 LoveAV 业务分类。
- LoveAV 不直接打开 Telegram Session，不复制凭据，也不绕过 TG Exporter daemon。

默认仍使用用户上传的 HTML、JSON、TXT、CSV、MD、LOG 或粘贴文本。只有用户明确要求直接读取 Telegram 时，才调用本适配器。

## 自动定位

适配器按以下优先级寻找 `tgctl.exe`：

1. 命令行 `--tgctl`；
2. 私人 `tools.json`；
3. LoveAV 内嵌工具的正式构建目录；
4. 工作区相邻 `tg-exporter` 的正式构建目录；
5. `PATH`。

不会自动采用路径中带 `candidate` 的文件。私人配置推荐放在：

```text
LoveAV-Data/config/tools.json
```

格式：

```json
{
  "tg_exporter": {
    "tgctl_path": "E:\\path\\to\\release-v0.3.2\\tgctl.exe"
  }
}
```

该配置不得提交 GitHub。

## 健康检查

先运行：

```powershell
python scripts/tg_exporter_adapter.py health
```

返回机器可读 JSON，只包含版本、协议、Reader Schema、授权状态、运行状态、导出占用和能力列表，不回传账号资料、Session 内容或凭据。

内嵌 v0.3.3 提供：

```powershell
tgctl version --json
tgctl status --json
```

适配器兼容正式 v0.3.2。由于 v0.3.2 尚无 `version` 命令，只允许从规范的 `release-v0.3.2` 路径推断版本；其他无法证明版本的旧二进制必须拒绝。

## 自动分页

读取最近 1000 条：

```powershell
python scripts/tg_exporter_adapter.py history --chat <ref> --total-limit 1000
```

按筛选条件搜索：

```powershell
python scripts/tg_exporter_adapter.py search --chat <ref> --url-domain mypikpak.com --total-limit 1000
```

适配器每页最多 500 条，自动使用 `next_cursor` 续页，按 `(source_chat_id, message_id)` 去除分页边界重复。来源耗尽或达到用户要求数量时正常结束。

以下情况必须失败，不能把部分结果报成完成：

- 后续页面超时或返回错误；
- `has_more=true` 却没有 `next_cursor`；
- 游标重复；
- 页结构无效；
- 版本、Schema 或 IPC 不兼容；
- Telegram 尚未登录。

默认只把结构化结果交给当前 Agent 处理，不写原始消息文件。只有用户明确要求保存原始分页结果时才使用 `--output`。

## 会话发现与转发

LoveAV 可以通过适配器只读查找目标会话：

```powershell
python scripts/tg_exporter_adapter.py dialogs --search "<目标会话名>"
```

`forward` 默认始终是 dry-run。真实转发必须同时满足：用户明确要求、来源和目标稳定 ID 已确认、转发数量和消息 ID 预览已展示，以及最终负责时刻获得用户再次确认。

如果要保留图片、caption 和 Telegram 原始消息语义，应使用 `forward`；`send` 只用于用户明确要求的重组纯文本。

## 安全边界

- 只读阶段调用 `version`、`status`、`dialogs list`、`messages history` 和 `messages search`。
- `forward` 是受确认保护的可选写操作；无确认词时适配器只执行 dry-run。
- 不自动调用 `send`、媒体下载或任何标记已读功能。
- Telegram 登录仍由 TG Exporter GUI 完成。
- 不记录或提交真实聊天正文、URL、群 ID、Session、API 凭据和日志。
- Svip 分类继续遵循 `svip-resource-replies.md`：发送者身份仅供上下文展示，不参与接受或排除，也不能把未知身份猜成具体管理员。
