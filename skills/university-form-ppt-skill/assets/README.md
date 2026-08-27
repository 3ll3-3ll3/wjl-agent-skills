# 模板资源

本工作流使用两套当前用户批准的模板。

## 学生模板

路径：`assets/certificate_template.pptx`

预期 SHA-256：

```text
3dfa888b44be1d1219bf07d6600f3f76ef20b13488d6b24ca5c09333102ab4e2
```

预期占位符：

- `{{name}}`：1 处；
- `{{student_id}}`：1 处；
- `{{school_name}}`：2 处。

## 教师模板

路径：`assets/teacher_certificate_template.pptx`

预期 SHA-256：

```text
c0f315f563e96b4cd9696f8a6d9bd4f61efd5a9c241c34a1a07e880c3c5b47a9
```

预期占位符：

- `{{name}}`：1 处；
- `{{facultyid}}`：1 处；
- `{{school_name}}`：2 处。

## 业务规则

如果用户替换任一模板，必须在同一次变更中同步更新对应 SHA、相关脚本、测试和工作流文档。

源模板中的任何演示或无效标识必须保持可见。

如果仓库中的模板二进制 SHA 与预期 SHA 不一致，则模板同步尚未完成，禁止声称模板已成功更新。