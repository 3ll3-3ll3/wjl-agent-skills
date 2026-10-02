# PikPak 链接消息

这是 LoveAV 的第六个主功能，用于从 `tgctl` 读取的一个或多个 `pikpak消息` 分类群组中提取 PikPak 链接、密码和完整消息，并分别生成可导入 Raindrop 的 CSV。Svip 是现有来源之一。用户明确要求直接读取 Telegram 时，LoveAV 可通过适配器调用 `tgctl`；分类器本身不连接 Telegram，也不修改消息状态。

## 已锁定选择规则

发送者身份不再参与筛选。只要消息满足以下条件，就默认进入主结果：

1. 来自 TG Exporter 当前分类为 `pikpak消息`，且已在私人配置中用稳定 `chat_id` 复核的来源；
2. 包含合法的 `http` 或 `https` PikPak URL；
3. URL 的 hostname 是 `mypikpak.com` 或其真实子域名。

已知普通成员、匿名管理员、当前管理员、群身份发送、Telegram 未提供发送者以及转发来源不明，都不会因为身份差异被排除。可取得的身份字段只保留为可选上下文，不得把未知身份猜成具体管理员。

`mypikpak.com.evil.com`、正文中单纯出现域名文字、其他协议或解析失败的 URL 不属于有效资源。URL 合法性检查不访问链接。

## 私人来源配置

推荐配置位置：

```text
LoveAV-Data/config/telegram-sources.json
```

结构：

```json
{
  "schema_version": 1,
  "sources": {
    "svip": {
      "chat_id": "<Telegram标记后的负数群组ID>",
      "title": "Svip",
      "raindrop_folder": "Svip PikPak链接消息"
    }
  }
}
```

该文件属于私人运行数据，不得提交 GitHub 或随 Skill 分发。

## 读取与分类

优先让适配器自动完成健康检查和分页；对每个候选来源分别执行：

```powershell
python scripts/tg_exporter_adapter.py history --chat <Svip-ref> --total-limit 1000
```

分类器消费结构化结果：

```powershell
python scripts/filter_svip_resource_replies.py <第一页.json> [更多页.json ...] --config <telegram-sources.json>
```

分类输出使用 `schema_version=3`。所有合法资源消息的 `classification` 固定为 `accepted_pikpak_resource` 并进入 `results.main`。`identity_context` 和 `identity_evidence` 只描述 Telegram 实际提供的上下文，不决定是否接受。

每个主结果必须包含：

- `message_text`：可见 `text` 和 `caption`；
- `message_copy_text`：完整可复制文字，并追加只存在于富文本 entity 中的隐藏 PikPak URL；
- 消息 ID、日期、图片与回复关系；
- `pikpak_resources`：URL、与该 URL 绑定的密码及可复制资源行；
- `password_status`：`bound`、`not_provided` 或 `ambiguous`；
- `identity_context`：仅供审计的发送者上下文。

面向用户时，一条命中消息对应一个完整消息块，不能只剩 URL。

## URL 与密码

当 URL 后紧跟 `密码`、`提取码`、`访问码`、`口令`、`pwd` 或 `password` 时，把密码与该 URL 绑定。如果整条消息只有一个 PikPak URL 和一个唯一密码，即使密码位于链接前或另一行，也可以绑定。

多链接或多密码无法确定关系时不得猜测，但链接仍属于主结果：

- 能确定的密码照常保存；
- 不能确定的密码留空；
- `password_status=ambiguous`；
- Raindrop Note 显示 `密码：待确认`；
- 添加 `密码待确认` Tag。

可复制资源行使用：

```text
https://mypikpak.com/s/example 密码: abcd
```

URL 字段始终只保存合法 URL，不能把密码文字拼进 URL。

## Raindrop 导出

Raindrop 是第六功能 PikPak 链接消息的最终管理入口，不建设另一套消息数据库。每个来源使用私人配置中的独立 `raindrop_folder`；Svip 当前收藏夹为：

```text
Svip PikPak链接消息
```

分类成功后使用：

```powershell
python scripts/export_svip_raindrop_csv.py <分类结果.json> --raindrop-library <Raindrop官方导出.csv>
```

`--raindrop-library` 可省略，但省略时只能做本批内部去重，不能证明链接是否已存在于 Raindrop。

导入 CSV 固定为 UTF-8 BOM 和六列：

```text
folder,url,title,note,tags,created
```

字段规则：

- `folder`：使用当前来源私人配置中的 `raindrop_folder`；
- `url`：一行一个纯 PikPak URL；
- `title`：原消息第一行有意义的资源标题；没有标题时使用 `<来源名> PikPak｜日期｜消息 ID`；一条消息有多个链接时追加 `｜序号/总数`；
- `note`：完整命中消息、当前资源、密码、消息 ID、消息时间和“发送者身份不参与筛选”的说明；
- `tags`：固定包含 `<来源名>, PikPak`，有密码时添加 `有密码`，密码不明确时添加 `密码待确认`；
- `created`：Telegram 原消息时间，不使用 CSV 生成时间。

输出默认位置：

```text
LoveAV-Data/svip/outputs/YYYY-MM-DD/YYYY-MM-DD_svip_pikpak_raindrop_import.csv
LoveAV-Data/svip/update-review/YYYY-MM-DD_svip_pikpak_raindrop_update_review.csv
```

同一批相同 URL 只输出一次。已有 Raindrop URL 默认不再次输出；新密码补全或密码冲突进入 `update-review`，不能依赖重复导入覆盖已有书签。生成 CSV 只表示 `exported`，不能声称已经成功导入 Raindrop。

允许长期保存的 Telegram 正文只限这些被选中导入 Raindrop 的 PikPak 资源消息。读取范围中的其他消息、排除项和临时结果不得长期保存。

## 转发到收藏群

需要保留图片、排版和转发来源时，可另行把选中原消息真转发到 Telegram 收藏群。Raindrop 导出与 Telegram 转发相互独立。

1. 先使用 `dialogs --search` 查找目标会话，并用稳定 ID 确认唯一目标；
2. 只使用已接受主结果的消息 ID；
3. 先执行 dry-run，展示来源、目标、数量和消息 ID；
4. 只有用户在最终负责时刻明确确认后，才传入 `FORWARD_SVIP_RESOURCES`；
5. 单次最多 200 条，写入结果未知时不得自动重试。

预览：

```powershell
python scripts/tg_exporter_adapter.py forward --from-chat <Svip-ref> --to-chat <收藏群-ref> --ids <消息ID...>
```

确认后真实转发：

```powershell
python scripts/tg_exporter_adapter.py forward --from-chat <Svip-ref> --to-chat <收藏群-ref> --ids <消息ID...> --confirm FORWARD_SVIP_RESOURCES
```

## 结果报告

每次至少报告：

- 输入消息数量；
- 合法 PikPak 消息数量；
- 唯一 URL 数量；
- 本批重复数量；
- Raindrop 历史重复数量；
- 新增导出数量；
- 密码补全与密码冲突数量；
- 无效或伪造域名数量。

不得继续使用“只有管理员链接才是主结果”或“普通成员链接需要排除”的旧语义。
