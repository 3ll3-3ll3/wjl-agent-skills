# Svip 官方 PikPak 资源回复

这是 LoveAV 的第六个主功能，用于处理由 `tgctl` 读取的 Svip 结构化消息。用户明确要求直接读取 Telegram 时，LoveAV 可通过适配器调用 `tgctl`；分类器自身不连接 Telegram，不修改消息状态，也不声称能够恢复 Telegram 已省略的真实发送者。用户可在结果确认后另行要求把选中的原消息真实转发到另一个 Telegram 会话。

## 适用条件

用户提出以下请求时读取本参考：

- 读取或整理 Svip 的官方 PikPak 回复；
- 提取 Svip 中群主或管理员发布的资源链接；
- 复核 Svip 中发送者未知的 PikPak 消息。

Svip 的稳定 `chat_id` 必须来自私人配置。不得根据标题模糊匹配后直接处理，也不得把真实 `chat_id` 写入公开 Skill 仓库。

## 两层证据

第一层是 Telegram 可验证身份：

- 当前群主；
- 当前管理员；
- Telegram 明确标记的匿名管理员；
- Telegram 明确以当前群组身份发送。

这些记录分类为 `verified_moderator`。

第二层是 Svip 的业务模式：发送者被 Telegram 省略、消息包含真实 PikPak 链接、回复另一条消息且附带图片。它们分类为 `trusted_official_reply`，表示“业务规则高可信”，不表示已经验证出具体管理员身份。

## 确定性分类

按以下顺序分类：

1. 可验证群主、管理员、匿名管理员或本群身份：`verified_moderator`。
2. Telegram 返回具体发送者但没有管理员证据：`excluded_known_member`。
3. `telegram_sender_not_provided`，同时具有回复关系和图片：`trusted_official_reply`。
4. `telegram_sender_not_provided`，只具有回复关系或图片之一：`needs_review`。
5. `telegram_sender_not_provided`，两项都没有：`excluded_insufficient_evidence`。
6. `forwarded_message_without_actual_sender`：`needs_review`，不得把转发来源当实际发送者。
7. 其他身份不明情况：`needs_review`。

主结果只包含 `verified_moderator` 和 `trusted_official_reply`。待复核与排除记录必须分别报告。

## URL 边界

只接受 `http` 或 `https` 的 `mypikpak.com` 及其真实子域名。必须解析 hostname；`mypikpak.com.evil.com`、正文中单纯出现域名文字或其他协议不得匹配。检查过程不访问链接。

## 私人配置

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
      "title": "Svip"
    }
  }
}
```

该文件属于私人运行数据，不得提交 GitHub 或随 Skill 分发。

## 运行

优先让适配器自动完成健康检查和分页，不要求用户手工保存、拼接每一页：

```powershell
python scripts/tg_exporter_adapter.py history --chat <Svip-ref> --total-limit 1000
```

也可对管理员与 PikPak 域名做结构化搜索：

```powershell
python scripts/tg_exporter_adapter.py search --chat <Svip-ref> --sender-role admin --url-domain mypikpak.com --total-limit 1000
```

适配器输出可直接交给分类器；只有用户明确要求落盘时，才保存 JSON 后运行：

```powershell
python scripts/filter_svip_resource_replies.py <第一页.json> [更多页.json ...] --config <telegram-sources.json>
```

只有用户明确要求长期保存时才使用 `--output`。默认在当前对话中返回结果，不把 Telegram 原文写入长期文件或日志。

每个命中记录必须包含：

- `message_text`：保留消息的可见 `text` 和 `caption`；
- `message_copy_text`：用于整体复制，保留原文，并追加只存在于富文本 entity 中的隐藏 PikPak URL；
- 消息 ID、日期、是否含图片、PikPak URL、密码、分类和证据。

面向用户时，默认一条命中消息对应一个完整消息块，不得只剩 URL。可以额外给出一行一个的纯资源列表，但它不代替完整消息块。

当 URL 后紧跟 `密码`、`提取码`、`访问码`、`口令`、`pwd` 或 `password` 时，必须把密码与对应 URL 绑定。如果整条消息仅有一个 PikPak URL 且仅有一个唯一密码，即使密码在链接前或另一行，也必须回退绑定。多链接或多密码无法确定对应关系时不得猜测，应进入待复核。可复制资源行统一为 `URL 密码: xxxx`。URL 字段本身仍保持合法，不能把“密码”汉字拼进 URL 路径，也不能丢弃访问密码。

## 转发到收藏群

需要保留原消息的文字、媒体和转发来源时，必须使用 Telegram 真转发，不要用纯文本 `send` 代替。

1. 先使用 `dialogs --search` 查找目标会话，并以稳定 ID 确认唯一目标；同名、模糊匹配或无权发送时必须停止。
2. 默认只取 `main` 的原消息 ID；`review` 不得自动混入。
3. 先执行 dry-run，显示来源、目标、数量、去重后消息 ID 和批次边界。
4. 转发会改变远程账号状态；只有用户在最终负责时刻明确确认后，才传入 `FORWARD_SVIP_RESOURCES` 实际执行。
5. 单次最多 200 条。发送后连接中断并返回 `WRITE_OUTCOME_UNKNOWN` 时不得自动重试；应先读取目标群核对已到达的消息。

预览：

```powershell
python scripts/tg_exporter_adapter.py forward --from-chat <Svip-ref> --to-chat <收藏群-ref> --ids <消息ID...>
```

在用户确认后真实转发：

```powershell
python scripts/tg_exporter_adapter.py forward --from-chat <Svip-ref> --to-chat <收藏群-ref> --ids <消息ID...> --confirm FORWARD_SVIP_RESOURCES
```

## 结果说明

面向用户必须明确区分：

- “Telegram 已验证管理员来源”；
- “Svip 业务规则高可信”；
- “需要人工复核”；
- “明确普通成员或证据不足，已排除”。

不得把 `trusted_official_reply` 描述为已经查明具体管理员。规则只为稳定提取用户所需资源回复，不改变底层 Telegram 身份事实。
