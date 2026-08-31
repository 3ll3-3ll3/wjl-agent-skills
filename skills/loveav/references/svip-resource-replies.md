# Svip 官方 PikPak 资源回复

这是 LoveAV 的第六个主功能，用于处理已经由 `tgctl` 读取的 Svip 结构化消息。它不连接 Telegram，不修改消息状态，也不声称能够恢复 Telegram 已省略的真实发送者。

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

先用 `tgctl messages history` 读取所需范围并保存 JSON，再运行：

```powershell
python scripts/filter_svip_resource_replies.py <第一页.json> [更多页.json ...] --config <telegram-sources.json>
```

只有用户明确要求长期保存时才使用 `--output`。默认在当前对话中返回结果，不保存 Telegram 原文。输出只包含消息 ID、日期、PikPak URL、与 URL 绑定的最小密码信息、可复制资源行、分类与证据，不包含其余原始正文。

当 URL 后紧跟 `密码`、`提取码`、`访问码`、`口令`、`pwd` 或 `password` 时，必须把密码与对应 URL 绑定，并把 `URL 密码: xxxx` 作为一个完整可复制资源行。URL 字段本身仍保持合法，不能把“密码”汉字拼进 URL 路径，也不能丢弃访问密码。

## 结果说明

面向用户必须明确区分：

- “Telegram 已验证管理员来源”；
- “Svip 业务规则高可信”；
- “需要人工复核”；
- “明确普通成员或证据不足，已排除”。

不得把 `trusted_official_reply` 描述为已经查明具体管理员。规则只为稳定提取用户所需资源回复，不改变底层 Telegram 身份事实。
