# 维护说明

正式执行规则以 `SKILL.md` 为准。

## 双模式

- `student` -> `assets/certificate_template.pptx`
- `faculty` -> `assets/teacher_certificate_template.pptx`

教师认证与学生认证使用同一套学校查询、随机姓名和数字 ID、输出字段、版式保护、渲染验收、REDO 和 Drive 自动归档逻辑。

区别主要在模板与 ID placeholder：

- 学生：`{{student_id}}`
- 教师：`{{facultyid}}`

如果邮箱/域名明显属于学生或教师体系，自动选择模式；角色无法可靠判断时只询问认证类型。

正文替换后的自然顺排是硬性验收条件：不得出现“一行一个单词”、字段/单词孤立成行，或后续文本不再按原段落顺序连续流动。发生这种情况必须做最小必要的文字流调整并重新渲染验收。

Drive 目录固定分开：

```text
大学PPT生成记录/学生认证/<学校>/
大学PPT生成记录/教师认证/<学校>/
```

每次记录使用 `YYYY-MM-DD_HH-mm` 命名三件套；Drive 上传并回读确认是强制完成门槛。

## Language convention

`SKILL.md` 使用 English skeleton + 中文业务规则：

- metadata、Trigger、Workflow、tool names、paths、commands、fields 使用英文或保留原始技术标识；
- 复杂业务规则、异常、禁止事项、验收标准使用中文；
- 不要把同一句业务规则写成杂乱的中英混合句。

## Synchronization

规则变更时同步更新相关：

- `SKILL.md`
- docs
- scripts
- tests
- 用户明确替换的 template binaries

只有真实 GitHub 写入成功后才能声称仓库同步完成。