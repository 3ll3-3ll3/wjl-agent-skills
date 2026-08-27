# Agent Instructions

Use `SKILL.md` as the operational source of truth for this Skill.

## Routing

- Determine `student` vs `faculty` mode before selecting a template.
- Student template: `assets/certificate_template.pptx`.
- Faculty template: `assets/teacher_certificate_template.pptx`.
- Student placeholders: `{{name}}`, `{{student_id}}`, `{{school_name}}`.
- Faculty placeholders: `{{name}}`, `{{facultyid}}`, `{{school_name}}`.

## Business Rules

- 只能替换当前模式允许的占位符，禁止顺带修改其他文字或重建整页。
- 第一行姓名 + 数字 ID 必须保持单行。
- 正文替换后必须保持自然连续的英文段落流；若出现一词一行、孤立字段或后续文字不再连续流动，直接判定 QA 失败。
- 右下角官方英文校名必须使用全名并保持单行；必要时只能做最小局部适配。
- 源模板中的演示/无效标识必须保持可见。
- 学生和教师模式使用同一聊天字段契约。
- Google Drive 归档是强制步骤，且必须按 `学生认证` / `教师认证` 分目录。
- 每次归档完成前必须回读目标文件夹，确认 MD/PPTX/PNG 三件套真实存在。
- 具体学校的生成记录不得提交到 GitHub。

## Final Checks

- Verify the correct template was selected.
- Verify only approved placeholders changed.
- Verify the final PPTX was actually rendered to PNG.
- 验证第一行、正文文字流、右下角校名和演示/无效标识均通过视觉检查。
- 验证 Drive 三件套已上传并回读确认后，才能声称任务完整完成。