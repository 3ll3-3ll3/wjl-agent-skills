# PikPak 资源频道归档

这是 LoveAV 第六功能的频道归档模式。它适用于用户明确指定的 PikPak 资源频道：读取全部可访问历史，只保留真正带 PikPak URL 的资源帖，不保存图片、每日更新播报或普通公告。

## 单向数据流

本功能只允许以下方向：

```text
Telegram 资源频道 → 本地主库 → Raindrop 导入 CSV
```

Raindrop 只作为搜索和浏览入口。不得把 Raindrop 导出 CSV 自动回灌、比较或合并进本地主库。本地主库每次从该频道当前可访问的完整历史重新生成，并在覆盖前自动备份上一版。

## 私人来源配置

稳定 `chat_id` 只保存在：

```text
LoveAV-Data/config/telegram-sources.json
```

推荐来源键为 `cenglou_pikpak_vip`。私人群 ID 和真实归档内容不得提交 GitHub。

## 收录规则

- 合并检查 `text`、`caption` 和富文本 `entities[].url`。
- URL 必须是 `http/https`，hostname 为 `mypikpak.com` 或真实子域名。
- 只要消息含合法 PikPak URL，就视为资源帖。
- 纯每日更新播报、预览群公告、支付入口、频道导航和没有 PikPak URL 的普通消息全部排除。
- 如果未来的更新播报本身带有新的 PikPak 直链，该直链仍作为资源保留。
- 不下载图片、视频或文档。相册中没有正文的附属媒体消息直接忽略。
- 每个规范 PikPak URL 在主库中只有一条记录；重复发布消息完整保存在 `source_messages`。
- 一条消息含多个 PikPak URL 时，每个 URL 建立独立资源记录。
- 密码能唯一绑定时保存；同一 URL 出现多个不同密码时标记 `conflict`，不得猜测。

## 本地文件

默认目录：

```text
LoveAV-Data/pikpak/cenglou-vip/
├─ library/resource-library.jsonl
├─ library/resource-library.csv
├─ raindrop/raindrop-full.csv
├─ state/checkpoint.json
├─ backups/
└─ manifest.json
```

- `resource-library.jsonl`：唯一正式主库，保存每个 URL 及全部来源消息。
- `resource-library.csv`：方便 Excel 查看，不作为另一份真源。
- `raindrop-full.csv`：固定六列 `folder,url,title,note,tags,created`，可直接导入 Raindrop。
- `checkpoint.json`：记录本次完整重建的消息边界。
- `manifest.json`：记录统计、文件路径、SHA-256、备份位置和无 Telegram 写入声明。

## 执行

用户明确授权保存资源原文后运行：

```powershell
python scripts/archive_pikpak_channel.py --live
```

脚本必须读到 `source_exhausted=true` 才能生成主库；达到安全上限但历史尚未读完时必须失败。执行只读历史请求，不下载媒体、不转发、不发送消息、不标记已读。

## 完成报告

至少报告：总消息数、资源消息数、唯一资源数、重复 URL 组数、多链接消息数、隐藏链接数、带密码资源数、密码冲突数、忽略媒体数、消息 ID 边界、输出文件和 SHA-256。
