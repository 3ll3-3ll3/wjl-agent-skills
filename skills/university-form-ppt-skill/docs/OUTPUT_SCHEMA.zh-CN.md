# 输出字段规范

学生认证与教师认证默认使用完全相同的用户侧字段和顺序。每个表单字段单独放在可复制代码块中。

生成后的交付顺序：真实 PPT 渲染 PNG、PPTX、学校中文名、Official English Name、First name、Last name、Student ID、Address、City、State/Province、Postal/Zip code，最后经纬度。

教师模式中，同一个随机数字 ID 实际写入 `{{facultyid}}`，但为兼容现有工作流，默认输出字段名仍为 `Student ID`；用户明确要求时可以显示 `Faculty ID`。

默认不输出 Country/Region、Address line 2、VAT/GST ID。
