# 仓库维护规则

本仓库用于统一维护个人 Codex / Agent Skills，采用 monorepo 结构。

## 仓库结构

- 每个 Skill 位于 `skills/<skill-name>/`。
- 每个 Skill 必须保留自己的 `SKILL.md`，作为该 Skill 的执行真源。
- 只属于某个 Skill 的脚本、参考资料、资源、测试和文档，应保留在该 Skill 目录内。
- 只有两个或更多 Skill 确实复用同一实现时，才考虑抽取到 `shared/`。

## 修改规则

1. 任务只针对某个 Skill 时，修改范围应尽量限制在该 Skill 内，除非确实需要根级调整。
2. 不得顺带改变无关 Skill 的行为。
3. 必须保留现有 Skill 的安全边界、数据规则、模板约束和兼容性要求。
4. 不提交运行时私有数据、凭据、Token、Session、浏览器资料、本地数据库、Telegram 导出或用户生成记录。
5. 机械、确定性的工作优先放到脚本；`SKILL.md` 重点描述工作流、决策、约束和验收标准。
6. 新的个人 Skill 默认添加到 `skills/<skill-name>/`，而不是新建独立仓库。
7. 迁移、重构或大规模改写完成前，必须确认所有受影响 Skill 仍包含 `SKILL.md` 和必要的资源、脚本与测试。

## 全仓库语言规范

从现在开始，本仓库所有当前和未来的 Skill 统一采用以下语言规则：

> **主体内容全部使用简体中文。**

适用范围包括：

- `SKILL.md` 的标题、章节名、触发说明、工作流、业务规则、异常处理、禁止事项、验收标准和示例说明；
- `README.md`、`AGENTS.md`、`references/`、`docs/`、`assets/README.md` 等人类或 Agent 可读文档；
- YAML、JSON 等配置文件中可以自然使用中文的说明文字；
- 新增注释和维护说明，在不影响代码兼容性的前提下优先使用中文。

以下内容因为属于机器标识、代码或外部协议，可以保留原始英文，不为了中文化而强行改名：

- YAML/JSON 的固定键名，例如 `name`、`description`、`status`；
- Skill 名、工具名、函数名、类名、变量名；
- 文件名、文件路径、命令、参数、环境变量；
- API 字段、JSON key、schema、URL；
- 代码、正则表达式、占位符，例如 `{{school_name}}`；
- 产品、网站、协议和技术名称，例如 Codex、GitHub、Telegram、Google Drive、PPTX、JSON、CSV。

除上述必须保留的技术标识外，不再使用英文段落、英文标题或英文解释。不要为了“机器兼容”额外维护英文版业务规则。

## 代码块规则

只有确实需要精确复制的内容才使用代码块，例如：

```text
skills/<skill-name>/SKILL.md
```

或：

```powershell
node scripts/organize_whos_answers.js <JSON路径>
```

代码块只用于命令、路径、数据结构、占位符和代码，不用代码块承载大段英文说明。

## README 规则

- 根目录只保留中文 `README.md`。
- Skill 级只保留中文 `README.md`。
- 不再维护 `README.en.md` 或其他英文 README 副本。
- 新增或修改 README 时，正文全部使用中文；必要技术标识保持原样。

## Skill 编写规则

新建或实质性修改 `SKILL.md` 时，统一使用中文章节，例如：

- `# 目标`
- `# 触发条件`
- `# 工作流`
- `# 业务规则`
- `# 异常与边界`
- `# 最终验收`
- `# 示例`
- `# 参考资料`

YAML frontmatter 的固定键名保持原样，但 `description` 的说明文字使用中文。

## 维护不变量

任何规则调整都必须优先保证执行正确性、规则精确性和可维护性。语言统一不得导致函数名、字段名、占位符、文件路径、命令或外部接口被错误翻译。