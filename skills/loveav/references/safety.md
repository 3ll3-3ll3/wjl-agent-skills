# 安全与确认规则

当前版本默认是离线本地模式。Telegram、123AV、MissAV、Bad.news、海角和 Raindrop 的网络访问均默认禁止；后文网络相关条目只是未来兼容 adapter 的安全边界，不代表当前执行许可。

## Secrets 与隐私

禁止要求用户粘贴或上传：

- Telegram API hash；
- Bot Token；
- OTP；
- password；
- Session；
- cookies；
- browser storage；
- Raindrop token；
- 含上述内容的数据库。

宿主可以读取预先配置好的 secure store，但 Skill 只能看到 capability result 与 sanitized error。

禁止把 secrets 或 raw Telegram text 写入 logs、packages、generated source 或长期回复内容。只有用户明确要求当前会话摘录时，才允许短暂展示最小必要原文。

## Network boundaries

Manual mode 不执行 Telegram、MissAV、Bad.news、海角、Twitter、Raindrop 或 123AV network requests。

Browser script 默认只生成，不执行；只有用户明确要求且宿主存在受支持的 browser action 时，才可以运行。

任何 connected network action 前都必须明确说明：

- destination；
- purpose；
- scope；
- expected side effect。

HTTP 200 不能证明页面有效或远端写入成功。必须检查文档定义的成功证据，并分别识别 access challenge、login page、404、429、403、timeout 与 rate limit。

## Account 与 browser actions

以下操作必须在最后负责时刻取得明确确认：

- Telegram login；
- mark read；
- 123AV favorite/follow；
- 其他会改变 remote account state 的动作。

出现 CAPTCHA、未知 login state 或无法确认成功状态的页面时必须停止。禁止继续点击不明确页面，也禁止读取 password、cookie、Local Storage 或 Session Storage。

123AV account work 必须 single-lane per site。普通网络失败或 `Error 1015` 时等待 10 秒，再从最后一个确认成功项恢复；如果 side effect 状态未知，不得盲目重试。

## Data mutation

以下操作执行前必须先 preview：

- delete；
- restore；
- overwrite；
- migration commit；
- rule commit；
- package import。

Preview 必须展示受影响数量与 conflict/invalid 明细，并取得一次性确认。随后先创建 snapshot，再使用一个 transaction 完成；任一错误必须 rollback。若存在已发生的 remote side effect，要单独报告，不得伪装成整体原子事务。

## AI uncertainty

禁止把一次性的“智能猜测”直接升级成 permanent filter。

不确定格式必须进入 review list，解释证据，并且只有在用户明确确认 + 回归样本满足要求后才能添加规则。

用户要求纯列表时，禁止把解释文字或猜测值混入 plain-text block。