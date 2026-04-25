# telegram-auto

`telegram-auto` 是一个面向 AI Agent 的 Telegram 工具，默认输出 JSON，用于读取会话、处理消息与执行常见交互操作。

## 功能概览

当前已支持以下能力：

- 登录、登出与会话状态检查
- 列出最近会话
- 列出指定聊天的消息
- 发送消息
- 回复指定消息
- 发送本地文件
- 转发消息
- 点击按钮消息中的按钮
- 下载消息中的媒体文件

## 安装

推荐使用 `uv tool install` 安装：

```bash
uv tool install git+https://github.com/dandkong/telegram-auto
```

安装完成后，可通过以下命令查看帮助：

```bash
telegram-auto --help
```

如需升级，可执行：

```bash
uv tool upgrade telegram-auto
```

## 配置方式

程序通过环境变量读取 Telegram 所需配置，并会自动加载当前执行目录下的 `.env` 文件。

使用前请先准备 Telegram 账号对应的 `TG_API_ID` 和 `TG_API_HASH`。

必填变量：

- `TG_API_ID`
- `TG_API_HASH`

可选变量：

- `TG_SESSION`：会话名，默认是 `telegram-auto-session`
- `ALL_PROXY`
- `HTTPS_PROXY`
- `HTTP_PROXY`

代理示例：

```env
ALL_PROXY=socks5://127.0.0.1:7890
```

## .env 示例

在执行命令的目录中创建 `.env` 文件，并填入以下内容：

```env
TG_API_ID=123456
TG_API_HASH=your_api_hash
TG_SESSION=telegram-auto-session
# ALL_PROXY=socks5://127.0.0.1:7890
```

## 认证

首次使用时，建议由人工先执行：

```bash
telegram-auto auth login
```

认证过程会要求你完成 Telegram 登录验证，通常包括：

- 输入手机号
- 输入 Telegram 发给你的验证码
- 如果账号开启了二次验证，可能还需要输入密码

登录成功后，会在本地生成 session 文件，用于后续复用登录状态。

检查当前 session 文件是否存在，以及当前授权状态：

```bash
telegram-auto auth status
```

尝试退出当前 Telegram 会话，并清除本地 session 文件：

```bash
telegram-auto auth logout
```

对于面向 agent 的使用方式，推荐流程是：

1. 人工首次执行 `telegram-auto auth login`
2. agent 执行业务命令前可先调用 `telegram-auto auth status`
3. 如需退出当前会话并清理本地登录态，再执行 `telegram-auto auth logout`

## 使用示例

### auth

交互式登录：

```bash
telegram-auto auth login
```

检查 session 文件和登录状态：

```bash
telegram-auto auth status
```

退出当前会话并删除本地 session：

```bash
telegram-auto auth logout
```

### dialogs

列出最近会话：

```bash
telegram-auto dialogs list --limit 10
```

参数：

- `--limit`：返回的会话数量，默认 `20`

### messages

列出消息：

```bash
telegram-auto messages list --chat me --limit 5
```

从某条消息开始继续向前翻：

```bash
telegram-auto messages list --chat me --limit 50 --offset-id 123
```

从某条消息开始继续向后翻：

```bash
telegram-auto messages list --chat me --limit 50 --offset-id 123 --reverse
```

查看频道帖子的评论区：

```bash
telegram-auto messages list --chat some_channel --reply-to 123 --limit 50
```

在单个聊天里搜索消息：

```bash
telegram-auto messages search --chat me --query "hello" --limit 20
```

全局搜索消息：

```bash
telegram-auto messages search --query "hello" --limit 20
```

发送消息：

```bash
telegram-auto messages send --chat me --text "hello"
```

回复消息：

```bash
telegram-auto messages reply --chat me --message-id 123 --text "收到"
```

发送文件：

```bash
telegram-auto messages send-file --chat me --path ./demo.txt --caption "附件说明"
```

转发消息：

```bash
telegram-auto messages forward --chat me --from-chat some_chat --message-id 123
```

常用参数：

- `--chat`：目标聊天，可使用用户名、`me` 或其他 Telethon 支持的目标标识
- `--limit`：消息数量，默认 `5`
- `--offset-id`：消息偏移 ID，默认 `0`
- `--reverse`：按从旧到新返回消息
- `--reply-to`：查看某条消息的回复/评论线程，适合频道评论区
- `--query`：搜索关键词，用于 `messages search`
- `--text`：发送或回复的文本内容
- `--message-id`：消息 ID
- `--from-chat`：转发来源聊天
- `--path`：本地文件路径
- `--caption`：文件说明文字

### buttons

点击按钮消息中的按钮：

```bash
telegram-auto buttons click --chat some_chat --message-id 123 --text "确认"
```

参数：

- `--chat`：消息所在聊天
- `--message-id`：目标消息 ID
- `--text`：按钮文字

### media

下载媒体文件（下载到目录，由 Telethon 自动命名）：

```bash
telegram-auto media download --chat some_chat --message-id 123
```

指定下载目录：

```bash
telegram-auto media download --chat some_chat --message-id 123 --dir ./downloads
```

下载到指定文件路径：

```bash
telegram-auto media download --chat some_chat --message-id 123 --file ./output/photo.jpg
```

说明：

- `--dir`：下载到目录，文件名由 Telethon 根据媒体信息自动确定，默认为当前工作目录
- `--file`：下载到指定的精确文件路径，父目录不存在时会自动创建
- 同时传入 `--dir` 和 `--file` 时，`--file` 优先

## 输出格式

所有命令默认输出 JSON，便于后续脚本处理。

成功返回时通常会包含：

- `ok`
- `command`
- `data`
- `account`

失败时会包含：

- `ok: false`
- `error.type`
- `error.message`
