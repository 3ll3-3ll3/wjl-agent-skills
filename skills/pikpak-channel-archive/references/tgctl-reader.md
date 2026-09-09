# TG Exporter 只读读取

本 Skill 通过 `tgctl.exe` 读取 Telegram，不直接打开或复制 Session。

## 私人配置

默认沿用 `E:\Desktop\codex项目\LoveAV-Data`。来源配置位于 `config/telegram-sources.json`，工具配置位于 `config/tools.json`；这些文件以及真实群 ID 不得提交 GitHub。

可以通过 `PIKPAK_ARCHIVE_DATA_DIR` 指定其他数据根目录；旧的 `LOVEAV_DATA_DIR` 作为兼容回退。

## 定位与健康检查

适配器依次检查显式 `--tgctl`、私人 `tools.json`、本 Skill 或相邻 LoveAV 的正式 TG Exporter 构建、相邻独立仓库正式构建、`PATH`。

```powershell
python scripts/tg_exporter_adapter.py health
```

健康检查必须证明版本、Reader Schema、IPC 兼容性和已授权状态；不得输出账号资料或凭据。

## 完整历史分页

归档器每页最多读取500条并自动续页。后续页失败、游标缺失或重复、结构无效、版本不兼容、未登录、达到安全上限但未读完时，必须整体失败。

归档模式只允许使用 `version`、`status` 和 `messages history`。不得调用发送、转发、媒体下载或标记已读命令。
