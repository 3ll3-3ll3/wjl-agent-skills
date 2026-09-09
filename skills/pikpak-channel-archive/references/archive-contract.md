# 归档契约

## 单向数据流

```text
Telegram 资源频道 → 本地主库 → Raindrop 导入 CSV
```

本地主库每次根据频道当前可访问的完整历史重建。`current` 保存最新状态，`updates` 保存本次差异，发生变化前由 `snapshots` 保存上一版。Raindrop 导出不反向更新主库。

## 收录与合并

- 同时检查 `text`、`caption` 和富文本 `entities[].url`。
- 合法 URL 的 hostname 必须是 `mypikpak.com` 或真实子域名。
- 每个规范 URL 只有一条主记录；重复消息完整保存在 `source_messages`。
- 一条消息包含多个 URL 时，每个 URL 单独建立记录。
- 不含 PikPak URL 的播报、公告、导航、支付入口和附属媒体不收录。
- 不下载图片、视频、文档或缩略图。

## 密码与标签

- 先排除 URL，再从明确密码标签中识别值，避免链接 token 内的 `pwd` 被误判。
- 唯一密码使用 `provided` 和 `#有密码`；没有密码使用 `not_provided` 和 `#无密码`。
- 同一 URL 有多个不同密码时使用 `conflict` 和 `#有密码`，保留全部密码供复核。
- CSV 的结构化 `tags` 使用不带井号的“有密码”或“无密码”；正文展示使用 `#有密码` 或 `#无密码`。

## 文件结构

```text
<输出根目录>/
├─ current/
│  ├─ resource-library.jsonl
│  ├─ resource-library.csv
│  ├─ raindrop-full.csv
│  └─ manifest.json
├─ updates/YYYY-MM-DD/HHMMSS/
│  ├─ added-resources.jsonl
│  ├─ updated-resources.jsonl
│  ├─ removed-resources.jsonl
│  ├─ conflicts.jsonl
│  ├─ raindrop-added.csv
│  └─ report.json
├─ snapshots/YYYY-MM-DD_HHMMSS/
└─ state/checkpoint.json
```

- `resource-library.jsonl` 是唯一正式主库。
- `resource-library.csv` 只用于 Excel 查看。
- `raindrop-full.csv` 用于完整重建收藏夹。
- `raindrop-added.csv` 只包含本轮新增链接，适合日常导入。
- `manifest.json` 记录统计、路径、SHA-256、快照和无 Telegram 写入声明。

## Raindrop 六列

固定列为 `folder,url,title,note,tags,created`。每条 `note` 依次写当前 PikPak URL、密码状态、可用密码、保持原顺序的消息剩余内容，以及 Telegram 原消息地址和消息 ID。

## 完整性要求

- 只有 `source_exhausted=true` 才能提交新主库。
- 写入使用临时文件原子替换。
- 数据变化时先生成快照。
- CSV 使用 UTF-8 BOM，并防止表格公式注入。
- 所有输出记录 SHA-256。
