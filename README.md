# WJL Agent Skills

这是我的 Codex / Agent Skills 统一仓库，采用“单仓多 Skill”的方式管理：一个仓库下放置多个相对独立的 Skill，每个 Skill 保留自己的 `SKILL.md`、脚本、参考资料、资源、测试和局部文档。

## 仓库结构

```text
wjl-agent-skills/
├── skills/
│   ├── loveav/
│   └── university-form-ppt-skill/
├── AGENTS.md
└── README.md
```

`skills/` 下的每个目录都是一个可独立安装或调用的 Skill。

## 管理约定

- 新的个人 Skill 默认添加到 `skills/<skill-name>/`，不再为每个 Skill 单独创建仓库。
- 每个 Skill 必须保留自己的 `SKILL.md`，并把只属于该 Skill 的脚本、参考资料、资源、测试和文档放在其目录内。
- 只有两个或更多 Skill 确实复用同一套实现时，才考虑抽取到 `shared/`。
- 不提交运行时私有数据、凭据、令牌、会话、浏览器资料、本地数据库、Telegram 导出或用户生成记录。
- 某个 Skill 只有在确实需要独立发布、问题跟踪、分发或单独维护生命周期时，才考虑重新拆成独立仓库。

## 语言规范

本仓库以后统一采用 **简体中文主体**。

所有 `SKILL.md`、`README.md`、`AGENTS.md`、`references/`、`docs/` 等说明文档，标题、章节、工作流、业务规则、异常处理、禁止事项、验收标准和示例说明都使用中文。

只有以下机器或代码相关内容保留原始英文：

- Skill 名、工具名、函数名、变量名；
- 文件名、路径、命令和参数；
- JSON/API 字段、固定配置键、URL；
- 代码、正则、占位符；
- Codex、GitHub、Telegram、Google Drive、PPTX、JSON、CSV 等产品或技术名称。

不再维护英文版 README，也不再采用“英文骨架 + 中文规则”的写法。除必要技术标识外，正文全部写中文。

## 当前 Skills

- `skills/loveav`
- `skills/university-form-ppt-skill`

本仓库是这些 Skills 的主要源码真源。以后新增 Skill 也默认直接进入本仓库。