# 保研导师套磁 Skill

用于把推免阶段的导师筛选、套磁、去重、发送和回信跟进固化为可复用流程。

## 主要能力

- 从官网和近期论文/项目中筛候选导师；
- 按 AI/机器学习/CV/大数据/智能感知等偏好排序；
- 检查跨项目、跨 Outlook/Gmail 的已联系历史，避免重复发送；
- 按“80%固定 + 20%个性化”起草套磁邮件；
- 用户明确授权后逐封单独发送；
- 读取导师回信、分类、起草跟进；
- 把结构化联系状态持续维护在 `data/` 中。

## 目录

```text
skills/baoyan-advisor-outreach/
├── SKILL.md
├── README.md
├── AGENTS.md
├── data/
│   ├── science-island-2027-outreach.yaml
│   └── iat-2027-outreach.yaml
└── references/
    ├── email-writing-rules.md
    └── reply-playbook.md
```

## 当前基线

截至 2026-09-16：

- 科学岛 2027 推免历史继续保存在 `science-island-2027-outreach.yaml`；
- 国家卓越工程师学院（先进技术研究院）2027 推免已新增 `iat-2027-outreach.yaml`，记录本轮 **54 位已联系导师**：Outlook 18 位、Gmail 36 位；
- 先研院 Gmail 第二批已按项目与专业领域建立标签；
- 数据文件保存去重所需的姓名、公开邮箱、项目/专业、批次、方向摘要、发送渠道和回信状态，不保存完整邮件正文、邮箱内部 message/thread id、密码、令牌或简历/成绩单原件。

## 使用方式

典型指令：

- “再找一些候选导师”；
- “把这几位挨个写邮件给我看”；
- “这几封全部逐个发”；
- “查邮箱里哪些老师回了”；
- “给这位老师起草回复”；
- “把新发送和回信状态同步到 Skill”。

执行细则以 `SKILL.md` 为唯一真源。
