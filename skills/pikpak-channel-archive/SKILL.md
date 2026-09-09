---
name: pikpak-channel-archive
description: 读取指定 Telegram PikPak 资源频道的完整可访问历史，建立本地唯一消息库、增量与快照，并生成 Raindrop 导入 CSV；适用于层楼资源归档、更新频道库、整理 PikPak 链接或重建收藏夹。
---

# 目标

把 Telegram 资源频道中真正包含 PikPak 链接的发布内容整理成可长期维护的本地主库，并生成可导入 Raindrop 的 CSV。该 Skill 是独立功能，不依赖 LoveAV 的其他业务规则。

# 触发条件

在用户提出以下请求时使用：

- 归档层楼或其他指定 PikPak 资源频道；
- 更新 PikPak 频道消息库；
- 从完整历史提取 PikPak 链接和密码；
- 生成或重建对应的 Raindrop CSV；
- 查看本轮新增、变化、缺失、重复或密码冲突。

# 工作流

1. 确认精确来源配置与目标输出目录；不得根据相似群名猜测私人群组。
2. 默认通过本机 `tgctl` 执行健康检查并只读分页到历史尽头；用户也可以提供完整 history JSON。
3. 只收录含合法 PikPak URL 的消息，不下载图片、视频或文档。
4. 按规范 URL 合并重复发布，保留全部来源消息；一条消息包含多个链接时分别建档。
5. 识别 URL 外的明确密码信息，生成 `#有密码` 或 `#无密码` 状态。
6. 在写入前比较现有主库；有变化时先创建快照，再原子更新 `current` 和本轮 `updates`。
7. 验证清单、数量和 SHA-256 后报告结果。

详细的收录、目录和输出契约见 [references/archive-contract.md](references/archive-contract.md)。通过 Telegram 读取时还要读取 [references/tgctl-reader.md](references/tgctl-reader.md)。

# 输入模式

## Telegram 只读模式

用户明确要求直接读取频道时运行：

```powershell
python scripts/archive_pikpak_channel.py --live
```

必须成功读取到 `source_exhausted=true`。达到安全上限但历史尚未读完时停止，不得生成伪完整主库。

## 离线 JSON 模式

用户提供 TG Exporter 完整 history JSON 时运行：

```powershell
python scripts/archive_pikpak_channel.py --input <完整历史.json>
```

输入必须明确标记 `ok=true`、`complete=true`、`source_exhausted=true`。

# 核心规则

- URL 必须使用 `http/https`，hostname 为 `mypikpak.com` 或其真实子域名。
- 同一规范 URL 在主库中只保留一条，所有重复发布保存在 `source_messages`。
- 只从 URL 之外的明确“密码、提取码、访问码、口令、pwd、password”标签识别密码。
- 分享 token 自身出现 `pwd` 不得被识别成密码。
- 唯一密码写入 `password`；多个不同密码标记 `conflict`，不得猜测。
- 每条记录必须包含 `password_tag`，值为 `#有密码` 或 `#无密码`；结构化标签同步使用“有密码”或“无密码”。
- Raindrop `note` 第一行是当前 PikPak URL，第二行是密码状态；有密码时下一行写密码，然后按原顺序保留消息其余内容。
- 当前 URL 在同一条 Raindrop `note` 中只出现一次；隐藏链接需补到开头。
- 不收录没有 PikPak URL 的播报、公告、导航、支付入口或纯媒体消息。

# 数据边界

数据流固定为：

```text
Telegram 资源频道 → 本地主库 → Raindrop 导入 CSV
```

- 本地主库是唯一真源；Raindrop 用于搜索和浏览。
- 不把 Raindrop 导出自动回灌、比较或合并进主库。
- 不自动写入 Raindrop 账号；只生成 CSV。
- 不把真实群 ID、Telegram 正文、PikPak URL、Session、Token 或用户数据提交到 Skill 仓库。

# 安全边界

- 默认只读 Telegram，不发送、不转发、不标记已读。
- 不下载任何媒体。
- 不读取或显示 Telegram Session、API hash、验证码、密码或其他凭据。
- 用户没有明确授权保存资源原文时，只能预览统计，不能建立长期消息库。
- 覆盖、删除、恢复或迁移私人数据前必须预览影响并取得确认。
- 远端 Raindrop 已存在记录不会被重复导入自动覆盖；不得声称 CSV 已更新远端收藏。

# 完成报告

至少报告输入、资源与唯一资源数量，重复、多链接、隐藏链接、密码状态、忽略媒体、消息边界、差异、快照、输出路径、SHA-256、Telegram 写入状态和 Raindrop 本地文件状态。

# 示例

```text
使用 $pikpak-channel-archive 更新层楼 PikPak 资源频道本地主库，并生成最新 Raindrop CSV。
```

```text
使用 $pikpak-channel-archive 处理我提供的完整 TG Exporter JSON，只预览统计，不写入现有主库。
```

# 参考资料

- [references/archive-contract.md](references/archive-contract.md)：收录、密码、文件结构、增量和验收契约。
- [references/tgctl-reader.md](references/tgctl-reader.md)：本机 TG Exporter、私人配置、健康检查和只读分页。
