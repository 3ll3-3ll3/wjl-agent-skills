---
name: university-form-ppt-skill
description: Identify a university and certification mode from a school name, email, domain, or related clue; verify official school and campus data; generate a short demo identity; fill the approved student or faculty PPT template; render-check the result; and archive the completed record to Google Drive.
---

# Goal

根据用户提供的学校、邮箱、域名或认证线索，生成符合既定模板规则的学生或教师认证 PPT，并完成学校信息核验、实际渲染验收和 Google Drive 归档。

# Trigger

Use this skill when the user asks to generate, redo, update, validate, or archive a student/faculty university certificate PPT, or when the user provides a clear university clue that belongs to this workflow.

Typical triggers include:

- a Chinese or English university name;
- a student or faculty email address;
- a student/faculty email domain such as `@stu.scu.edu.cn`;
- a school, college, faculty, or department name;
- another clear clue tied to one university.

Determine the mode before selecting a template:

- `student` = 学生认证
- `faculty` = 教师认证

If the institution is clear but the role genuinely cannot be determined, ask only for the certification mode. Do not infer a person's real name from an email username or local-part.

# Workflow

1. Identify the university and certification mode.
2. Verify the official Chinese name, official English full name, campus, address, postal code, and coordinates.
3. Generate a short random pinyin demo identity and a fresh numeric ID.
4. Select the latest approved student or faculty template.
5. Replace only approved placeholders.
6. Validate first-line flow, body text flow, signature line, and preserved markings.
7. Render the final PPTX to PNG and perform visual QA.
8. Prepare the required chat fields and artifacts.
9. Archive matching MD/PPTX/PNG files to the correct Google Drive branch.
10. Read the Drive folder back and only then report full completion.

# Business Rules

## 学校信息核验

学校信息按以下优先级核验：

1. 学校官网；
2. 官方招生页面；
3. 官方国际交流/交换页面；
4. 官方联系方式或信息公开页面；
5. 在校区与地址已确认后，再使用可靠地图或地理来源补充坐标。

必须核验：

- 学校官方中文名；
- 学校官方英文全名；
- 主要/代表性校区；
- `Address`；
- `City`；
- `State/Province`；
- `Postal/Zip code`；
- 校区经纬度。

学校英文名必须使用核验后的官方英文全名。禁止自行翻译、缩写、裁剪或编造。所有 `{{school_name}}` 替换必须使用同一官方英文全名。

## 校区与坐标

- 地址与经纬度必须指向真实且互相对应的校区。
- 优先输出 WGS84；如来源为 GCJ-02/BD-09，可在内部规范化后再输出。
- 只有一个相关校区时，输出一个 Latitude/Longitude 对。
- 多校区时最多输出两个最重要、最常用或最具代表性的校区，并清楚标注。
- 表单地址必须对应所选主校区。
- 禁止编造地址、邮编、校区或坐标。

## 随机身份与字段

每次运行：

- 生成正常的二字或三字中文姓名；
- 转写为拼音；
- 优先使用较短组合，保护 PPT 第一行；
- 本项目固定约定：`First name` = 姓氏拼音，`Last name` = 名字拼音；
- PPT `{{name}}` = `SurnamePinyin GivenNamePinyin`。

每次必须生成新的数字 ID：

- 通常 7–8 位；
- 除非用户明确要求，否则不使用固定学校前缀；
- 学生模式写入 `{{student_id}}`；
- 教师模式写入 `{{facultyid}}`；
- 为兼容现有聊天/表单流程，两种模式默认都使用 `Student ID` 作为返回字段名，除非用户明确要求显示 `Faculty ID`。

若第一行发生换行，处理优先级必须是：先换更短姓名，再换更短数字 ID，再重新渲染。禁止通过修改正文的字体、字号、行距、正文文本框大小或正文位置来解决第一行溢出。

## Approved templates

Use the latest user-approved template for the selected mode:

- `student`: `assets/certificate_template.pptx`
  - expected SHA-256: `3dfa888b44be1d1219bf07d6600f3f76ef20b13488d6b24ca5c09333102ab4e2`
- `faculty`: `assets/teacher_certificate_template.pptx`
  - expected SHA-256: `c0f315f563e96b4cd9696f8a6d9bd4f61efd5a9c241c34a1a07e880c3c5b47a9`

Expected placeholders:

### Student template

- `{{name}}`: 1
- `{{student_id}}`: 1
- `{{school_name}}`: 2

### Faculty template

- `{{name}}`: 1
- `{{facultyid}}`: 1
- `{{school_name}}`: 2

只能替换当前模式允许的占位符。优先直接修改 PPTX XML，避免重建文本框。

## PPT 格式保护

除获准占位符文字外，应尽可能保持模板原样，包括：

- 页面尺寸；
- 背景、图片、形状、主题；
- 正文字体、字号、颜色；
- 行距、段距；
- 正文文本框大小和位置；
- 日期；
- 学院/部门文字；
- 专业/项目文字；
- 其他非占位符文本；
- 整体版式。

禁止从零重建整页 PPT。

## 正文自然顺排与右下角校名

- 第一行中的姓名 + 数字 ID 必须保持在同一行。
- 后续正文必须像正常英文段落一样自然连续流动。
- 若替换后出现“一行一个单词”、字段/单词孤立成行或后续文字不再按原段落顺序连续流动，则直接判定 QA 失败。
- 禁止通过人为硬换行或硬拆词修复。
- 正确效果是：替换后的后续单词继续按原段落顺序自然向后顺排。
- 若正文文字流异常，只允许做最小必要的局部修复，例如规范化正文文字流，或最小调整正文文本框宽度、字间距或段落布局；不得改变整体视觉设计。
- 右下角校名必须使用官方英文全名并保持单行。
- 如右下角确需适配，只允许对该区域做最小必要的宽度、位置、字间距或字号调整。
- 禁止把官方英文全名替换为简称。

## 演示/无效标识

如果源模板存在 `SAMPLE / NOT VALID`、`仅供演示，不具效力` 或其他明确演示/无效标识，必须保持清晰可见。禁止删除、隐藏、裁剪、覆盖或弱化到不可见。

## Chat delivery fields

Student and faculty modes use the same user-facing field order:

1. actual PNG rendered from the final PPT;
2. PPTX file;
3. Chinese university name;
4. `Official English Name`;
5. `First name`;
6. `Last name`;
7. `Student ID`;
8. `Address`;
9. `City`;
10. `State/Province`;
11. `Postal/Zip code`;
12. coordinates last.

每个表单字段必须单独放在可复制代码块中。除非用户明确要求，否则不输出 `Country/Region`、`Address line 2` 或 `VAT/GST ID`。

## Google Drive archive

Every generation must archive automatically in the same workflow.

Permanent paths:

- `student`: `大学PPT生成记录/学生认证/<中文学校名>/`
- `faculty`: `大学PPT生成记录/教师认证/<中文学校名>/`

Each run stores exactly three matching files:

- `<record_stem>.md`
- `<record_stem>.pptx`
- `<record_stem>.png`

`record_stem` 使用本地生成时间，精确到 1 分钟：`YYYY-MM-DD_HH-mm`。如果同一学校、同一认证类型在同一分钟再次生成，才追加 `_<student_id>` 防止冲突。

MD 至少包含：

- 认证类型（`学生认证` 或 `教师认证`）；
- 使用的模板；
- 学校中文名；
- 官方英文全名；
- 用户原始输入；
- `First name`；
- `Last name`；
- 完整随机拼音姓名；
- `Student ID`；
- `Address`；
- `City`；
- `State/Province`；
- `Postal/Zip code`；
- 所选校区；
- 坐标；
- PPT QA 结果；
- 真实 Google Drive PPT URL；
- 真实 Google Drive PNG URL。

禁止预先拼接或伪造 Drive URL。

归档是强制完成门槛：必须确认正确模式目录和学校子目录存在，上传最终 PPTX 和实际渲染 PNG，用真实返回链接生成/更新 MD，再上传 MD，最后回读目标学校文件夹确认三件套真实存在。任一外部步骤失败，都必须明确说明：`该步骤当前没有成功完成。` 禁止在没有真实结果时声称上传、渲染、GitHub 写入、commit、替换或回读成功。

## REDO

若任何生成记录有误，必须执行完整 REDO：

```text
PPT regenerate/fix text flow
-> PNG render
-> visual QA
-> replace/update Drive PPTX
-> replace/update Drive PNG
-> update Drive MD
-> Drive readback verification
```

禁止只修聊天里的文件而保留错误的 Drive 版本。

## Repository role

GitHub 只保存可复用工作流，不保存具体学校的生成记录。仓库中维护：

- `SKILL.md`
- README/docs
- research/PPT/output/archive rules
- identity generation code
- student/faculty PPT generation code
- archive helper code
- tests
- latest approved student template
- latest approved faculty template

具体学校的 MD/PPTX/PNG 记录只进入 Google Drive。

# Edge Cases

- 学校已确定但认证角色不明确：只询问 `student` 或 `faculty`，不要猜。
- 邮箱用户名像真实姓名：仍不得据此推断本人真实姓名。
- 多校区来源冲突：先确定真实主校区，再决定表单地址和坐标。
- 第一行换行：先缩短随机姓名，再缩短数字 ID；不要动正文格式。
- 正文出现单词逐行掉落：判定 QA 失败，做最小局部文字流修复后重新渲染。
- 右下角官方英文名过长：只调整右下角局部区域，且必须保持官方全名。
- Drive 上传部分成功：不得声称任务整体完成，必须报告缺失步骤。
- 模板 SHA 与预期不符：模板同步不完整，不能继续假装使用了已批准模板。

# Final Checks

Before delivery, verify all applicable items:

- `name + numeric ID` remains on the first line.
- The numeric ID is not stranded on a new line.
- 正文保持正常连续顺排，不出现一词一行或替换导致的孤立片段。
- 正文学校名是核验后的官方英文全名。
- 右下角学校名与正文一致，且保持单行。
- 未批准的非占位符内容没有被意外修改。
- 整体版式和格式正常。
- 源模板中的演示/无效标识仍然可见。
- The PPTX was actually rendered to PNG; AI-generated images are not a substitute.
- Drive 中预期的 MD/PPTX/PNG 三件套已通过回读确认。

Any failed check requires a fix and a new render before delivery.

# Examples

```text
用户：190311055@stu.xpu.edu.cn
```

Expected behavior:

1. Identify the university and student mode.
2. Verify official school and campus data.
3. Generate the short demo identity and numeric ID.
4. Fill only the approved student placeholders.
5. Render, QA, deliver fields, archive to Drive, and read back the folder.

```text
用户：这是教师邮箱，请按教师认证重新生成。
```

Expected behavior:

1. Select `faculty` mode.
2. Use `assets/teacher_certificate_template.pptx`.
3. Write the numeric ID into `{{facultyid}}`.
4. Preserve all shared layout, rendering, delivery, and archive rules.

# References

- `docs/PPT_RULES.md`
- `docs/OUTPUT_SCHEMA.md`
- `docs/RECORDS_POLICY.md`
- `docs/RESEARCH_POLICY.md`
- `docs/MAINTAINER_GUIDE.md`
- `assets/README.md`

# Maintenance Invariant

当用户永久修改该工作流时，应同步更新相关 `SKILL.md`、业务文档、脚本、测试，以及用户明确替换的模板。只有真实 GitHub 写入成功后才能声称仓库同步完成。