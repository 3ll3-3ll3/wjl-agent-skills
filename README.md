# WJL Agent Skills

[简体中文](README.md) | [English](README.en.md)

这是我的 Codex / Agent Skills 统一仓库，采用 monorepo 方式管理：一个仓库下放置多个相对独立的 Skill，每个 Skill 保留自己的 `SKILL.md`、脚本、参考资料、资源、测试和局部文档。

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

`skills/` 下的每个目录都是一个可独立安装或调用的 Skill。

## 管理约定

- 新的个人 Skill 默认添加到 `skills/<skill-name>/`，不再为每个 Skill 单独创建仓库。
- 每个 Skill 必须保留自己的 `SKILL.md`，并把只属于该 Skill 的脚本、参考资料、资源、测试和文档放在其目录内。
- 只有两个或更多 Skill 确实复用同一套实现时，才考虑抽取到 `shared/`。
- 不提交运行时私有数据、凭据、Token、Session、浏览器资料、本地数据库、Telegram 导出或用户生成记录。
- 某个 Skill 只有在确实需要独立 Release、Issue、分发或单独维护生命周期时，才考虑重新拆成独立仓库。

## Skill 语言规范

本仓库的 `SKILL.md` 统一采用“**英文骨架 + 中文业务规则**”。

### Machine-facing：英文

以下内容优先保持英文，以便 Agent 路由、工具调用和代码维护保持稳定：

- YAML metadata 中的 `name`、`description`
- `Trigger`、`Workflow` 等结构性章节与触发说明
- tool names、function names、class names、variable names
- file paths、commands、environment variables
- JSON keys、API fields、schemas、code

### Business rules：中文

以下内容优先使用简体中文，以保证复杂约束表达准确：

- 业务规则与领域约束
- 异常处理与边界情况
- 禁止事项与安全边界
- 验收标准与最终检查
- 容易误解、容易出错的细节

### Examples：贴近真实输入

示例输入输出应贴近实际使用语言。中文工作流优先给中文示例；代码、命令、字段名、URL、占位符和其他技术标识保持原样。

### 避免无意义中英混写

不要为了“看起来专业”在一句业务规则里频繁切换中英文。应写成完整、自然的中文句子，只保留必要的技术标识，例如：

> 若 `school_name` 过长，应优先扩大文本框宽度；只有无法保持单行时，才允许最小幅度减小字号，不得改变整体版式。

而不是把同一句规则拆成中文、英文动词和变量名的混合句。

## README 语言

人类阅读文档仍以简体中文为默认：

- `README.md`：简体中文，GitHub 默认首页
- `README.en.md`：英文补充版

这与 `SKILL.md` 的混合语言规范不冲突：README 负责给人阅读，`SKILL.md` 负责让 Agent 稳定执行。

## 当前 Skills

- `skills/loveav`
- `skills/university-form-ppt-skill`

本仓库是这些 Skills 的主要源码真源。以后新增 Skill 也默认直接进入本仓库。