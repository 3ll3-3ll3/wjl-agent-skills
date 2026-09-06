# 内嵌源码来源与维护规则

本目录最初从以下公开仓库的已跟踪源码完整复制：

```text
来源仓库：https://github.com/3ll3-3ll3/tg-exporter.git
来源提交：4af25ad5e35d671cd6401a534767b1656c43944d
来源正式版本：v0.3.2
正式 Tag 提交：79649668b9b45fad2783a0f8c6cc673205a9266a
```

复制内容包括源码、测试、文档、构建配置与发布脚本，不包括：

- 原仓库 `.git` 历史；
- 本地 Session、凭据、日志和导出消息；
- `dist/`、`build/`、虚拟环境与缓存；
- 历史 Candidate 二进制。

从内嵌 v0.3.3 开始，本目录是 LoveAV 所需 TG Exporter 的开发真源。后续功能、测试和构建在 `3ll3-3ll3/wjl-agent-skills` 中维护。原独立仓库保持原样，不归档、不删除、不修改历史分支、Tag 或 Release。

TG Exporter 只提供通用 Telegram GUI、daemon 和 `tgctl` 机器接口；LoveAV 的业务规则仍位于上级 Skill，不应复制进 Telegram 底层。
