# PikPak 多来源资源归档

这是 LoveAV 的第八个主功能。它统一管理用户明确指定的多个 PikPak 资源群组或频道：对每个来源读取全部可访问历史，只保留真正带 PikPak URL 的资源帖，不保存图片、每日更新播报或普通公告。本功能的执行真源是 LoveAV 内的脚本、参考文档和测试。

## 多来源管理

- 稳定 `chat_id` 仍只保存在私人 `LoveAV-Data/config/telegram-sources.json`。
- 功能 8 来源索引保存在 `LoveAV-Data/config/pikpak-archive-sources.json`，只引用 `source_key`，不复制群 ID。
- 每个来源必须有唯一 `output_slug` 和自己的 `raindrop_folder`。
- 每个来源在 `LoveAV-Data/pikpak/<output_slug>/` 下独立维护主库、增量、快照和检查点；不因跨群链接重复而丢失任何来源的完整消息。
- 用户只说“运行功能 8”时，先列出已启用来源，让用户选单个或全部；已明确来源时直接执行。
- 新增来源时，先用会话发现确认唯一群组，再把稳定 ID 写入私人来源配置，并向功能 8 索引增加一条非敏感记录。
- 资源链接位于频道评论区时，在私人来源配置写入 `include_comments=true`。归档器随后逐帖调用 `messages.replies`，而不是把评论误当作 Forum Topic。
- 若评论只提供资源 Bot 的公开 start 按钮，还需在同一条私人来源配置写入 `resource_bot_username`。它是可发送目标白名单，不得从按钮内容动态改写。

## 单向数据流

本功能只允许以下方向：

```text
Telegram 资源频道 → 本地主库 → Raindrop 导入 CSV
```

Raindrop 只作为搜索和浏览入口。不得把 Raindrop 导出 CSV 自动回灌、比较或合并进本地主库。本地主库每次从该频道当前可访问的完整历史重新生成，但输出按增量管理：固定 `current` 保存最新状态，`updates` 保存每次差异，数据变化前在 `snapshots` 保存上一版。

## 私人来源配置

稳定 `chat_id` 只保存在：

```text
LoveAV-Data/config/telegram-sources.json
```

私人群 ID 和真实归档内容不得提交 GitHub。当前已纳入功能 8 的来源名单以私人 `pikpak-archive-sources.json` 为准，Skill 源码不写死用户的群组清单。

## 收录规则

- 合并检查 `text`、`caption`、富文本 `entities[].url` 和公开 URL 按钮。不读取或导出 callback data。
- 评论归档会把父频道帖的标题与说明放在前面，再接评论原文、PikPak URL 和密码；本地主库的来源消息仍指向实际评论消息。
- URL 必须是 `http/https`，hostname 为 `mypikpak.com` 或真实子域名。
- 只要消息含合法 PikPak URL，就视为资源帖。
- 纯每日更新播报、预览群公告、支付入口、频道导航和没有 PikPak URL 的普通消息全部排除。
- 如果未来的更新播报本身带有新的 PikPak 直链，该直链仍作为资源保留。
- 不下载图片、视频或文档。相册中没有正文的附属媒体消息直接忽略。
- 每个规范 PikPak URL 在主库中只有一条记录；重复发布消息完整保存在 `source_messages`。
- 一条消息含多个 PikPak URL 时，每个 URL 建立独立资源记录。
- 密码能唯一绑定时保存；同一 URL 出现多个不同密码时标记 `conflict`，不得猜测。
- 密码只能从 PikPak URL 之外的明确密码标签识别；链接 token 内自然出现的 `pwd` 不得误判。
- 每条本地主库记录必须显式包含 `#有密码` 或 `#无密码`；结构化 `tags` 列对应保存 `有密码` 或 `无密码`。

## 本地文件

每个来源的默认目录：

```text
LoveAV-Data/pikpak/<output_slug>/
├─ current/resource-library.jsonl
├─ current/resource-library.csv
├─ current/raindrop-full.csv
├─ current/manifest.json
├─ updates/YYYY-MM-DD/HHMMSS/
│  ├─ added-resources.jsonl
│  ├─ updated-resources.jsonl
│  ├─ removed-resources.jsonl
│  ├─ conflicts.jsonl
│  ├─ raindrop-added.csv
│  └─ report.json
├─ snapshots/YYYY-MM-DD_HHMMSS/
├─ state/checkpoint.json
```

- `current/resource-library.jsonl`：唯一正式主库，保存每个 URL 及全部来源消息。
- `current/resource-library.csv`：方便 Excel 查看，不作为另一份真源。
- `current/raindrop-full.csv`：固定六列 `folder,url,title,note,tags,created`，用于完整重建 Raindrop 收藏夹。
- Raindrop `note` 的第一行固定为当前 PikPak URL，第二行为 `#有密码` 或 `#无密码`；有密码时第三行写密码。随后移除当前 URL 的一次重复并按原顺序保留消息其余内容，最后附 Telegram 来源。
- `updates/.../raindrop-added.csv`：只含本次新增 URL，是日常应导入 Raindrop 的文件。
- `updates` 的其他文件分别保存新增、变化、当前缺失和密码冲突；即使本次没有变化，也生成报告作为运行记录。
- `snapshots`：只在数据变化或旧布局迁移时生成，保存更新前的完整版本。
- `checkpoint.json`：记录本次完整重建的消息边界。
- `current/manifest.json`：记录统计、增量数量、文件路径、SHA-256、快照位置和无 Telegram 写入声明。

若检测到旧的 `library/`、`raindrop/`、`backups/` 和根目录 `manifest.json`，首次运行会先将它们完整移入带 `legacy-layout` 标记的快照，再建立新布局，不直接删除旧数据。

## 执行

用户明确授权保存资源原文后运行：

```powershell
python scripts/archive_pikpak_channel.py --live
```

脚本必须读到 `source_exhausted=true` 才能生成主库；启用评论读取时，每一条父帖的评论也必须全部读完。达到安全上限、评论接口不可用或任何评论线程分页失败时必须整体失败。执行只读历史与评论请求，不下载媒体、不转发、不发送消息、不标记已读。

## 评论 Bot 按钮兑换

当频道评论里没有 PikPak 直链，只有 `t.me/<配置 Bot>?start=<payload>` 时，使用：

```powershell
python scripts/redeem_pikpak_channel_buttons.py `
  --source-key <私人来源键> `
  --folder "<Raindrop 收藏夹>" `
  --output-root "<该来源输出目录>"
```

默认是 dry-run。它完整读取频道与评论，只接受精确配置 Bot 的 start 链接，按 `Bot + payload` 去重，且只输出聚合数量，不显示 payload。真实兑换前必须在最后负责时刻取得用户精确确认：

```text
RUN_PIKPAK_CHANNEL_REDEEM
```

确认后才可向配置 Bot 发送 `/start <payload>`。默认两次成功任务间隔至少 65 秒，不得用并发绕过 Bot 限流。直链型 Bot 的每个任务只捕获后续 `mypikpak.com` 回复；如果第一项没有捕获直链，必须立即停止整批，不得继续发送剩余任务。若 Bot 返回的是另一个 Telegram 资源频道，必须先完成该频道的可读性与结果关联验收，再实现二段捕获；不可把 Telegram 频道链接误当成 PikPak 结果。成功项原子写入 `state/redeem-progress.json`，检查点键为不可逆 SHA-256，不保存 payload。全部任务成功后才更新功能 8 正式主库；部分失败、`FLOOD_WAIT` 或 `WRITE_OUTCOME_UNKNOWN` 都必须停止，不更新主库，下次从检查点续跑。本流程仍不下载媒体、不转发、不标记已读。

## 完成报告

至少报告：总消息数、资源消息数、唯一资源数、重复 URL 组数、多链接消息数、隐藏链接数、带密码资源数、密码冲突数、忽略媒体数、消息 ID 边界、新增/更新/缺失数量、快照、增量目录、输出文件和 SHA-256。
