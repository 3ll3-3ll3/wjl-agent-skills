# MissAV 浏览器脚本规则

## 权威来源

- 完整脚本模板：`assets/missav-browser-script.txt`，来自 Windows v0.5.13 已验证原版。
- 参考女优 Tag 真源：用户配置的正式 `missav-library.csv`。
- 类型边界：`assets/missav-type-boundary-tags.txt`。
- 确定性生成器：`scripts/generate_missav_browser_script.py`。

当前本机正式库为：

```text
E:\Desktop\codex项目\LoveAV-Data\missav\library\missav-library.csv
```

默认黑名单位于同一数据树：

```text
E:\Desktop\codex项目\LoveAV-Data\missav\rules\1-参考女优Tag库黑名单.txt
E:\Desktop\codex项目\LoveAV-Data\missav\rules\2-Raindrop导出黑名单.txt
```

路径不存在时必须要求用户指定实际正式库，不能回退到 `Miss_AV.html`、旧内置 Tag TXT、女优合集 CSV 或模型临时生成的名单。

## 参考女优 Tag 派生

每次生成脚本时重新读取正式主体库，不维护第二份参考女优资料库：

1. 读取每行主 `tags`。
2. 解析 `loveav_variants_json`，读取每个 MissAV/123AV 来源变体的 `tags`。
3. 每组 Tags 保持原顺序，从开头逐项判断。
4. Tag 命中系统标签、类型边界、包含数字/空白/网址，或不符合中文、日文、合法拉丁姓名形状时停止读取该组后续 Tags。
5. 对识别出的女优 Tag 精确去重，保留首次出现顺序。
6. 应用第一层参考女优 Tag 黑名单后得到最终 `REFERENCE_ACTRESS_TAGS`。

该集合的语义是：新作品的最终 Tags 只要含其中任一完整 Tag，即视为参考女优命中。派生过程只读，不修改主体库、不生成长期参考库文件，也不把普通类型 Tags 自动当成女优。

## 两层黑名单

- 第一层黑名单在生成脚本前从派生参考集合中排除完整 Tag；它只取消参考命中资格。
- 第二层黑名单注入 `RAINDROP_EXPORT_BLACKLIST_TAGS`；作品命中任一完整 Tag 时不写入 Raindrop HTML/CSV，但处理报告保留记录与原因。
- 两层黑名单均为 UTF-8 TXT、每行一个完整 Tag；不得合并语义。`# `（井号后紧跟一个空格）开头的行是说明注释，不作为 Tag；以井号开头但没有该空格的真实 Tag 不受影响。

## 生成命令

```powershell
python scripts/generate_missav_browser_script.py `
  --library <missav-library.csv> `
  --codes-file <一行一个番号.txt> `
  --reference-blacklist <第一层黑名单.txt> `
  --export-blacklist <第二层黑名单.txt> `
  --output <完整脚本.js>
```

省略黑名单参数时，生成器必须从 `<主体库目录的上一级>\rules\` 自动读取上述两个固定文件名。第一层允许是 0 字节空文件；任一文件缺失时必须停止并报出路径，不能静默当成空列表。显式参数只用于迁移、测试或用户另行指定的数据目录。番号也可以通过可重复的 `--code <番号>` 传入。

生成器必须报告主体库行数、来源变体数、两层黑名单路径/条数/哈希、黑名单前女优 Tag 数、第一层命中数、最终注入数、番号数以及主体库、模板、输出脚本的 SHA-256。报告不得输出完整私人 Tag 列表。

## 模板与执行边界

- 只替换 `CODE_TEXT`、`REFERENCE_ACTRESS_TAGS`、`RAINDROP_EXPORT_BLACKLIST_TAGS` 三个占位区。
- 缺少任一占位区、模板不是异步浏览器脚本、正式库格式错误或最终参考集合为空时停止。
- Agent 只把完整脚本交给用户；脚本由用户在已登录的 MissAV 页面 Console 手动运行。
- 不使用 `javascript:` URL、原始 CDP 或其他绕过方式代替用户运行。
- 原版三目录和优先级保持不变：`需要查找` 优先，其次 `参考女优Tag命中`，最后 `其他`；三个目录即使为空也创建。
- 123AV 数据只通过主体库来源变体贡献已识别女优 Tag，不触发 123AV 网络或账号操作。

## 长期保存边界

完整脚本默认在对话中返回，只有用户要求时才保存 `.js`。每批长期重要结果仍只有最终 `*_missav_raindrop_import_threeway.csv`；脚本、代码 TXT、链接 TXT 和摘要 JSON 默认不长期保存。
