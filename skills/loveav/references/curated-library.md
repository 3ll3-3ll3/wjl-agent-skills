# MissAV 主体库与 Raindrop CSV 契约

本契约只管理用户明确决定长期保留的 MissAV 精华数据，不归档每次处理的全部候选，也不改变现有规则、参考 Tag、两层黑名单或 Whos.tv 数据。

## 两类重要数据

LoveAV 的长期重要数据只有两类：

1. Whos.tv 已解决答案：继续使用既有固定目录、截止点、Markdown 和备份规则，本契约不移动也不改写它们。
2. MissAV 精华数据：使用一个本地主体库 CSV，加上每批单独保存的 Raindrop 导入 CSV。

临时预览、处理中间文件、代码列表、链接列表和浏览器脚本默认不落盘。规则数据维持现状，不随主体库迁移或合并。

## 建议目录

MissAV 数据目录由用户明确配置；不得擅自猜测、创建或移动已有私人目录。确定路径后采用：

```text
LoveAV-Data/
└─ missav/
   ├─ library/
   │  └─ missav-library.csv
   ├─ results/
   │  └─ YYYY-MM-DD_HHmm_<批次名>/
   │     └─ YYYY-MM-DD_HHmm_missav_raindrop_import_threeway.csv
   ├─ preview/                 # 可删除的导入预览与待复核项
   └─ backups/                 # 每次确认写库前的主体库备份
```

`missav-library.csv` 是唯一权威主体库。不得长期并行维护“Raindrop 库”和“Skill 新增库”两个真源，也不得再把 `seen-index.csv` 当作第二套历史库。

## 两种输入来源

主体库接收两种主要来源：

- 用户从 Raindrop 账号导出的官方 CSV；
- LoveAV 的 MissAV 功能处理后生成、可导入 Raindrop 的 CSV。

物理上合并为一行一个规范番号；逻辑上用来源标记保留出处：

- `loveav_in_raindrop=true`：该番号曾在用户提供的 Raindrop 导出中出现；
- `loveav_in_skill_added=true`：该番号曾由 LoveAV 处理结果确认入库；
- 同一番号两边都有时，两项都为 `true`，不得重复建行。

用户没有提供某份 CSV 时，只报告缺少来源，不得擅自访问 Raindrop、旧数据库或其他目录补齐。

## 支持的 Raindrop CSV 结构

### 官方无损 CSV

兼容 v0.5.13 已验证的 11 列：

```csv
id,title,note,excerpt,url,folder,tags,created,cover,highlights,favorite
```

导入官方 CSV 时，只接收目标 Raindrop 层级中的 MissAV 与 123AV 记录。必须保留其完整父子路径，包括 `日本AV` 父目录；不得把子目录提升为根目录。其他分支只在导入预览中标记为“范围外并跳过”，不得修改源 CSV 或远端 Raindrop。

路径判断基于规范化后的目录段，不做包含式模糊匹配：目录路径必须位于 `日本AV` 层级下，并在后续目录段中明确出现 `MissAV` 或 `123AV`。若路径结构不完整或存在同名歧义，进入 `review`，不得静默纳入或删除。

当前 LoveAV 不处理 123AV 业务，但保留 123AV 行作为主体库查重参考；它们不得触发 123AV 联网、收藏或关注操作。

### MissAV 脚本结果 CSV

兼容 v0.5.13 浏览器脚本生成的 14 列：

```csv
url,title,tags,actress_tags,type_tags,status,needs_lookup,reference_matches,excluded_from_raindrop,export_blacklist_matches,target_folder,actress_raw,matched_tag,notes
```

每次处理后，只有用户选择保留的行才能加入主体库。第二层黑名单排除项仍可出现在报告或预览中，但不得写入本批 Raindrop 导入 CSV，也不得因一次处理而自动进入主体库。

## 权威主体库结构

主体库以前 11 个 Raindrop 字段开头，并追加 LoveAV 元数据：

```csv
id,title,note,excerpt,url,folder,tags,created,cover,highlights,favorite,loveav_canonical_code,loveav_in_raindrop,loveav_in_skill_added,loveav_first_seen_at,loveav_last_seen_at,loveav_rule_version,loveav_status,loveav_variants_json,loveav_notes
```

约束：

- `loveav_canonical_code` 是唯一键，使用规范化 MissAV 番号；目录、URL、标题和 Raindrop ID 都不参与唯一性判断。
- 11 个 Raindrop 字段保持可往返的原始含义；空值不能覆盖已有非空值。
- 同一番号的来源字段发生差异时，保留当前主显示值，并把未采用的完整来源变体写入 `loveav_variants_json`，防止标题、URL、目录、Tags、备注或 Raindrop ID 丢失。
- `loveav_variants_json` 必须是单个 CSV 单元格中的合法 JSON 数组，内容仍不得包含凭据、Telegram 原文或浏览器资料。
- `loveav_status` 使用 `active` 或 `review`。存在番号身份歧义时保持 `review`，不得合并到其他行。
- 主体库使用 UTF-8、标准 CSV 引号和 CRLF/LF 兼容读取。写入时使用临时文件、关闭文件后原子替换，并先保存备份。
- 主体库是 Raindrop 字段的兼容超集，不建议把整份主体库原样导入 Raindrop；回写 Raindrop 时应生成只含目标记录和兼容列的导入 CSV。

## 番号查重与可疑项

查重主键是规范化番号，而不是 URL 或目录位置。先应用已验证的确定性规则；再处理可疑项：

1. 从标题和可信 MissAV/123AV 详情 URL 提取候选番号。
2. 对大小写、全半角、空格、下划线和连字符做可逆规范化。
3. 已验证格式直接生成 `loveav_canonical_code`。
4. 多个候选互相冲突、格式陌生或可能从普通文本误识别时，进入 `review`。
5. 用户要求进一步核实时，可通过互联网检索当前可信页面或官方/权威来源；必须记录支持与反对证据。证据仍不足时保持 `review`，不得凭模型猜测合并。
6. 用户确认某一行的番号，不等于自动创建一条永久通用规则；规则晋级仍遵守 `rule-learning.md`。

## 每次 MissAV 结果

每批结果目录只长期保存一个文件：

```text
YYYY-MM-DD_HHmm_missav_raindrop_import_threeway.csv
```

它必须：

- 只包含本批最终选择保留且允许进入 Raindrop 的记录；
- 保持脚本已验证的 CSV 列和三目录字段；
- 可直接用于 Raindrop 导入；
- 文件名包含本地时间和可辨识批次名；
- 不额外保存代码 TXT、链接 TXT、浏览器脚本、摘要 JSON 或整批 Telegram 原文。

用户需要番号列表、链接列表或完整浏览器脚本时，在对话中以独立代码块返回；只有用户另行明确要求才保存文件。

## 导入、预览与确认

任何新 CSV 都按同一流程处理：

1. 只读解析并识别结构、编码和来源类型。
2. 对 Raindrop 官方 CSV 应用 `日本AV → MissAV/123AV` 范围过滤，保留父子路径。
3. 规范化番号并与 `missav-library.csv` 比较。
4. 预览显示：新增、重复、将补全字段、冲突、无效、范围外、`review`。
5. 冲突预览必须展示双方差异；不得静默覆盖。
6. 用户确认后先备份，再原子写入唯一主体库。
7. 重建成功后报告主体库总数和本次来源标记变化；不得生成第二份长期历史索引。

同一 CSV 重复导入必须幂等。Skill 新增记录以后出现在 Raindrop 导出中时，只把 `loveav_in_raindrop` 更新为 `true` 并合并缺失字段，不能新增重复行。

## 与规则和 Whos.tv 的边界

- 参考女优 Tag、参考 Tag 黑名单和 Raindrop 导出黑名单维持现有文件与语义，本契约不搬迁、不覆盖、不从主体库反向生成。
- 主体库只提供历史查重和已有元数据参考，不能把库内 Tags 自动晋级为参考 Tag。
- Whos.tv 继续使用既有固定目录和状态文件；其中番号只有在用户明确选择后才能作为 MissAV 来源导入主体库。
- Google Drive 可以同步整个私人数据目录，但 GitHub 只保存 Skill、脚本、测试和契约，不提交主体库、批次 CSV 或私人备份。
