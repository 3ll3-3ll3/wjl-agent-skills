# Google Drive 生成记录归档规则

具体生成记录只保存到 Google Drive，并按认证类型完全分开：

```text
大学PPT生成记录/学生认证/<中文学校名>/
大学PPT生成记录/教师认证/<中文学校名>/
```

同一次生成保存同名 `.md/.pptx/.png` 三件套，文件名使用本地时间精确到 1 分钟的 `YYYY-MM-DD_HH-mm`。

同一学校、同一认证类型、同一分钟再次生成时，才追加 `_<student_id>` 防止文件名冲突。

MD 至少记录：

- 认证类型；
- 使用模板；
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
- 校区；
- 经纬度；
- PPT QA 结果；
- 真实 Drive PPT URL；
- 真实 Drive PNG URL。

禁止预先拼接或伪造 Drive URL。

归档必须自动完成：

```text
确认学生/教师目录
-> 确认学校子目录
-> 上传 PPTX
-> 上传实际渲染 PNG
-> 使用真实返回链接写 MD
-> 上传 MD
-> 回读目标文件夹
-> 确认三件套存在
```

任一步失败都不能声称任务已经完整完成。