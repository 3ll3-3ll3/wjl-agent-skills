# WJL Agent Skills

[简体中文](README.md) | [English](README.en.md)

这是我的 Codex / Agent Skills 统一仓库，采用常见的 monorepo 方式管理：一个仓库下放置多个独立 Skill，每个 Skill 都有自己的 `SKILL.md`、脚本、参考资料、资源、测试和局部文档。

## 仓库结构

```text
wjl-agent-skills/
├── skills/
│   ├── loveav/
│   └── university-form-ppt-skill/
├── AGENTS.md
├── README.md
└── README.en.md
```

`skills/` 下的每个目录都是一个相对独立、可单独安装或使用的 Skill。

## 管理约定

- 新的个人 Skill 默认添加到 `skills/<skill-name>/`，不再为每个 Skill 单独创建仓库。
- 每个 Skill 必须保留自己的 `SKILL.md`，并把只属于该 Skill 的脚本、参考资料、资源、测试和文档放在其目录内。
- 只有当两个或更多 Skill 确实复用同一套实现时，才考虑抽取到未来的 `shared/` 目录，避免过早抽象。
- 不提交运行时私有数据、凭据、Token、Session、浏览器资料、本地数据库、Telegram 导出或用户生成记录。
- 某个 Skill 只有在确实需要独立 Release、Issue、分发或单独维护生命周期时，才考虑重新拆成独立仓库。

## 文档语言约定

本仓库以后统一采用：

1. **简体中文为默认语言。** `README.md` 默认使用简体中文，也是 GitHub 首页优先展示的说明。
2. **英文为第二语言。** 英文说明使用 `README.en.md`。
3. 需要双语的人类可读文档时，优先使用 `README.md` + `README.en.md` 的命名方式。
4. 两种语言版本应尽量保持结构和信息同步；新增重要功能、边界或使用说明时，应优先更新中文，再同步英文。
5. `SKILL.md` 属于 Agent 执行规范，可按实际执行效果选择最稳定的语言，不强制为了展示而维护重复翻译版本。

## 当前 Skills

- `skills/loveav`
- `skills/university-form-ppt-skill`

迁移完成后，本仓库是这些 Skills 的主要源码真源。以后新增 Skill 也默认直接进入本仓库。