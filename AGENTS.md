# Repository Policy

本仓库是个人 Codex / Agent Skills 的 monorepo。

## Repository layout

- 每个 Skill 位于 `skills/<skill-name>/`。
- 每个 Skill 必须有自己的 `SKILL.md`，作为该 Skill 的执行真源。
- 只属于某个 Skill 的 scripts、references、assets、tests 和 docs 保留在该 Skill 目录内。
- 只有两个或更多 Skill 确实复用同一实现时，才考虑抽取到 `shared/`。

## Editing rules

1. 任务只针对某个 Skill 时，修改范围应尽量限制在该 Skill 内，除非确实需要根级调整。
2. 不得顺带改变无关 Skill 的行为。
3. 必须保留现有 Skill 的安全边界、数据规则、模板约束和兼容性要求。
4. 不提交运行时私有数据、凭据、Token、Session、浏览器资料、本地数据库、Telegram 导出或用户生成记录。
5. 机械、确定性的工作优先放到脚本；`SKILL.md` 重点描述工作流、决策、约束和验收标准。
6. 新的个人 Skill 默认添加到 `skills/<skill-name>/`，而不是新建独立仓库。
7. 迁移、重构或大规模改写完成前，必须确认所有受影响 Skill 仍包含 `SKILL.md` 和必要 assets/tests。

## Skill language convention

所有当前和未来的 `SKILL.md` 统一采用：

> **English skeleton + 中文业务规则**

### Machine-facing content: English

以下内容优先使用英文：

- YAML metadata 中的 `name`、`description`
- `Goal`、`Trigger`、`Workflow`、`Business Rules`、`Edge Cases`、`Final Checks`、`Examples`、`References` 等结构性章节名
- trigger / routing 描述
- tool names、function names、class names、variable names
- file paths、commands、environment variables
- JSON keys、API fields、schemas、code

机器相关标识必须保持原始拼写，不为了中文化而翻译或重命名。

### Business rules: Simplified Chinese

以下内容优先使用简体中文：

- 复杂业务规则与领域约束
- 异常处理与边界情况
- 禁止事项与安全边界
- 验收标准和最终检查
- 容易误解、容易出错、需要精确表达的细节

如果某条规则用中文能表达得更准确，就不要为了“全英文”而强行翻译。

### Workflow structure

`Workflow` 应优先用简洁英文描述结构步骤，例如：

```text
1. Identify input and mode.
2. Select the approved template.
3. Apply deterministic processing.
4. Validate the result.
5. Deliver or persist the approved output.
```

若某一步内部包含复杂约束，可以在对应 `Business Rules` 中用中文展开，不要把结构步骤写成长篇中英混杂句。

### Examples

- 示例输入输出应贴近真实用户语言。
- 中文用户工作流优先给中文示例。
- exact tool names、paths、commands、placeholders、JSON/API fields 和 code 保持原样。
- 不要求为了形式而做中英双份完全重复示例。

### Avoid noisy mixed sentences

禁止这种写法：

> 如果 student mode 的 school_name too long 就 resize textbox 但是不要 change layout。

推荐写法：

> 若学生模式下 `school_name` 过长，应优先扩大文本框宽度；只有无法保持单行时，才允许最小幅度减小字号，不得改变整体版式。

即：完整业务句子使用一种自然语言，只保留必要技术标识。

## README language policy

README 属于人类可读文档，继续采用中文优先：

- 根 `README.md`：简体中文默认首页
- 根 `README.en.md`：英文补充版
- Skill 级 `README.md`：默认简体中文
- Skill 级 `README.en.md`：需要时提供英文版

README 的语言策略与 `SKILL.md` 的混合语言结构是两套不同规则，不要混淆。

## Maintenance invariant

当某个 Skill 被实质性修改时，应顺带把该 Skill 的 `SKILL.md` 调整到上述语言规范；但不要为了样式对完全无关、稳定的代码和历史文件做大规模无意义改动。行为正确性、规则精确性和可维护性优先。