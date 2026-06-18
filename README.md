# QQ 群 DeepSeek V4 Pro 东海帝皇聊天机器人

这是一个最小可运行的 QQ 群聊天机器人：

- QQ 接入：官方 QQ 机器人 API + `qq-botpy`
- 模型：DeepSeek 官方 API 的 `deepseek-v4-pro`
- 人设：东海帝皇启发的同人风格
- 触发：QQ群里 `@机器人 你的问题`

## 1. 准备账号

你需要：

- 一个 QQ 群，且你能把机器人添加进群，最好是群主或管理员。
- QQ 开放平台机器人：<https://q.qq.com/>
- DeepSeek API Key：<https://platform.deepseek.com/>
- Python 3.10 或更新版本。

## 2. 创建 QQ 机器人

1. 打开 QQ 开放平台，创建机器人。
2. 在机器人后台找到并保存 `AppID` 和 `AppSecret`。
3. 到沙箱配置里选择你的测试QQ群，把机器人添加到群里。
4. 开启群聊消息相关能力，事件通道使用官方 WebSocket 接入。
5. 先在沙箱群测试，确认能收到 `@机器人` 的消息后再走发布流程。

注意：官方文档已经提示旧 `Token` 鉴权废弃，新接入请使用 `AppID` + `AppSecret`。

## 3. 创建 DeepSeek API Key

1. 打开 DeepSeek Platform。
2. 创建 API Key。
3. 确认账户有余额或赠送额度。
4. 本项目默认模型是 `deepseek-v4-pro`。

群聊建议保持 `DEEPSEEK_THINKING=disabled`，速度更快，语气也更像聊天。

## 4. 本地安装

在 PowerShell 中执行：

```powershell
Set-Location F:\qq-deepseek-bot
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
notepad .env
```

把 `.env` 改成这样：

```dotenv
QQ_APPID=你的QQ机器人AppID
QQ_APPSECRET=你的QQ机器人AppSecret
DEEPSEEK_API_KEY=你的DeepSeek_API_Key
DEEPSEEK_MODEL=deepseek-v4-pro
```

## 5. 启动机器人

```powershell
.\.venv\Scripts\python.exe bot.py
```

看到类似下面的日志就说明上线了：

```text
robot 「你的机器人名字」 on_ready!
```

然后在QQ群里发送：

```text
@你的机器人 帝皇，今天适合训练吗？
```

机器人会调用 DeepSeek V4 Pro，并用东海帝皇风格回复。

## 6. 常用调整

只允许指定前缀触发：

```dotenv
TRIGGER_PREFIXES=帝皇,teio
```

修改二创人设：

```dotenv
PERSONA_FILE=persona_teio.md
```

人设文件只影响表达风格和长期记忆。机器人仍会优先按高水平语言模型处理数学、代码、事实和学习问题。

让回复更短：

```dotenv
MAX_REPLY_CHARS=600
DEEPSEEK_MAX_TOKENS=400
```

取消固定回复长度上限：

```dotenv
MAX_REPLY_CHARS=0
DEEPSEEK_MAX_TOKENS=0
```

普通 QQ 号方案下，长回复会按 `ONEBOT_MESSAGE_CHUNK_SIZE` 自动拆成多条 QQ 消息发送。

开启 DeepSeek 思考模式：

```dotenv
DEEPSEEK_THINKING=enabled
DEEPSEEK_REASONING_EFFORT=high
```

## 7. 常见问题

收不到消息：

- 确认机器人在沙箱群或已发布可用群里。
- 确认你是 `@机器人` 触发。
- 确认后台开启了群聊消息事件。
- 确认程序没有退出，控制台没有报错。

发不出消息：

- QQ 群聊被动回复有时间和频次限制，测试时不要刷太快。
- 检查 `AppID` 和 `AppSecret` 是否正确。
- 检查机器人是否仍在 WebSocket 在线状态。

DeepSeek 报错：

- 检查 `DEEPSEEK_API_KEY`。
- 检查账户额度。
- 检查模型名是否是 `deepseek-v4-pro`。

## 8. 上服务器长期运行

先在本地跑通，再放到云服务器。服务器上流程一样：安装 Python、复制项目、填写 `.env`、安装依赖、运行 `python bot.py`。

Windows 服务器可以用计划任务、NSSM 或 PM2 托管；Linux 服务器建议用 `systemd`。

## 9. 普通 QQ 号 + NapCat 方案

如果你的官方 QQ 机器人后台提示“不支持 AIGC 机器人进入社群场景”，可以改用普通 QQ 号方案：

- NapCat 负责登录普通 QQ 号、接收群消息、发送群消息。
- 本项目的 `onebot_bot.py` 负责接收 OneBot v11 事件、调用 DeepSeek、生成回复。

风险提醒：这是非官方个人号路线，可能触发 QQ 风控、冻结、掉线或需要重新登录。建议使用小号，不要使用主号。

安装新增依赖：

```powershell
Set-Location F:\qq-deepseek-bot
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

确认 `.env` 中至少有：

```dotenv
DEEPSEEK_API_KEY=你的DeepSeek_API_Key
DEEPSEEK_MODEL=deepseek-v4-pro
ONEBOT_HOST=127.0.0.1
ONEBOT_PORT=8080
ONEBOT_PATH=/onebot/v11/ws
ONEBOT_GROUP_REPLY_MODE=at
```

启动本项目的 OneBot 服务：

```powershell
# 如果你还开着官方 QQ 机器人版本 bot.py，先在那个窗口按 Ctrl+C 停掉
.\.venv\Scripts\python.exe onebot_bot.py
```

然后在 NapCat WebUI 里新增网络配置：

```text
类型：WebSocket 客户端 / 反向 WebSocket
URL：ws://127.0.0.1:8080/onebot/v11/ws
```

保存后，控制台出现：

```text
[onebot] NapCat 已连接
```

就可以在真实 QQ 群里测试：

```text
@你的普通QQ机器人 帝皇，打个招呼
```
