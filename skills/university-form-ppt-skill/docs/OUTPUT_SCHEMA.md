# 输出字段规范

学生认证与教师认证默认使用完全相同的用户侧字段和顺序。每个表单字段单独放在可复制代码块中。

生成后的交付顺序：

1. 真实 PPT 渲染 PNG；
2. PPTX；
3. 学校中文名；
4. `Official English Name`；
5. `First name`；
6. `Last name`；
7. `Student ID`；
8. `Address`；
9. `City`；
10. `State/Province`；
11. `Postal/Zip code`；
12. 最后输出经纬度。

教师模式中，同一个随机数字 ID 实际写入 `{{facultyid}}`，但为兼容现有工作流，默认输出字段名仍为 `Student ID`；用户明确要求时可以显示 `Faculty ID`。

除非用户明确要求，否则默认不输出 `Country/Region`、`Address line 2` 或 `VAT/GST ID`。