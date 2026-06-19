# QQ 群 LLM 东海帝皇聊天机器人

这是一个可在 QQ 群中使用的通用聊天机器人项目。它把 QQ 消息接入、模型调用和角色风格分开，后端可以换成任意兼容 Chat Completions 格式的模型服务。

- QQ 接入：官方 QQ 机器人 API，或普通 QQ 号 + NapCat / OneBot v11
- 模型：任意 OpenAI-compatible LLM API
- 人设：东海帝皇启发的轻量同人风格
- 触发：支持群里 @、前缀触发、全群概率短插话
- 扩展：支持自动记忆、长回复拆分、随机拍一拍

## 1. 准备

你需要：

- Python 3.10 或更新版本。
- 一个可用的模型服务 API Key。
- 一个 QQ 群。
- 任选一种 QQ 接入方式：
  - 官方 QQ 开放平台机器人。
  - 普通 QQ 小号 + NapCat。

普通 QQ 号路线更像真实 QQ 用户，能进入真实群，但属于非官方个人号方案，存在风控、冻结、掉线、重新登录等风险。建议只用小号。

## 2. 安装

在 PowerShell 中进入项目目录：

```powershell
Set-Location F:\qq-llm-bot
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
notepad .env
```

最少需要填写：

```dotenv
LLM_API_KEY=你的模型服务_API_Key
LLM_BASE_URL=https://api.example.com/v1
LLM_MODEL=你的模型名
BOT_NAME=东海帝皇
```

`LLM_BASE_URL` 需要指向兼容 `/chat/completions` 的接口根地址。

## 3. 模型配置

常用配置：

```dotenv
LLM_THINKING=disabled
LLM_TEMPERATURE=0.85
LLM_MAX_TOKENS=0
LLM_TIMEOUT=0
```

说明：

- `LLM_THINKING=disabled`：更适合群聊，速度通常更快。
- `LLM_THINKING=enabled`：适合复杂推理题，但会更慢。
- `LLM_MAX_TOKENS=0`：不主动限制模型输出长度。
- `LLM_TIMEOUT=0`：不设置请求等待上限，长题会一直等接口返回。

如果服务商支持推理强度参数，可以配置：

```dotenv
LLM_THINKING=enabled
LLM_REASONING_EFFORT=high
```

## 4. 官方 QQ 机器人方案

在 `.env` 中填写：

```dotenv
QQ_APPID=你的QQ机器人AppID
QQ_APPSECRET=你的QQ机器人AppSecret
```

启动：

```powershell
.\.venv\Scripts\python.exe bot.py
```

看到类似日志即代表上线：

```text
robot 「你的机器人名字」 on_ready!
```

然后在群里发送：

```text
@你的机器人 帝皇，打个招呼
```

## 5. 普通 QQ 号 + NapCat 方案

NapCat 负责登录普通 QQ 号、收发 QQ 消息；本项目的 `onebot_bot.py` 负责接收 OneBot v11 事件、调用 LLM 并生成回复。

`.env` 中至少需要：

```dotenv
ONEBOT_HOST=127.0.0.1
ONEBOT_PORT=8080
ONEBOT_PATH=/onebot/v11/ws
ONEBOT_GROUP_REPLY_MODE=at
```

启动 OneBot 服务：

```powershell
.\.venv\Scripts\python.exe onebot_bot.py
```

然后在 NapCat WebUI 里新增网络配置：

```text
类型：WebSocket 客户端 / 反向 WebSocket
URL：ws://127.0.0.1:8080/onebot/v11/ws
```

控制台出现：

```text
[onebot] NapCat 已连接
```

就可以在真实 QQ 群里测试：

```text
@你的普通QQ机器人 帝皇，打个招呼
```

## 6. 普通 QQ 号快速登录

如果本机已经缓存过登录账号，可以用 `-q` 指定快速登录：

```powershell
.\launcher.bat -q 你的QQ号
```

本项目也可以放一个专用启动脚本，例如：

```bat
call "%~dp0launcher.bat" -q 你的QQ号
```

如果缓存失效，仍然需要重新扫码一次。

## 7. 群聊触发模式

```dotenv
# at     = 群里 @ 机器人时回复，推荐
# prefix = 不用 @，但必须以 TRIGGER_PREFIXES 中的前缀开头
# all    = 监听所有群消息；未 @ 时可按概率短插话
ONEBOT_GROUP_REPLY_MODE=at
```

指定前缀触发：

```dotenv
TRIGGER_PREFIXES=帝皇,teio
```

全群随机短插话：

```dotenv
ONEBOT_GROUP_REPLY_MODE=all
ONEBOT_AUTO_REPLY_MATH_ONLY=false
ONEBOT_AUTO_REPLY_PROBABILITY=0.15
ONEBOT_AUTO_REPLY_MAX_CHARS=30
```

短回复后随机拍一拍：

```dotenv
ONEBOT_AUTO_REPLY_POKE_PROBABILITY=0.8
```

## 8. 自动记忆

项目会把原始群聊保存到本地 `memory_data/`，并只把包含指定关键词的内容写入长期记忆文件。

```dotenv
MEMORY_AUTO_SAVE=true
MEMORY_AUTO_LOAD=true
MEMORY_SAVE_RAW_GROUP_MESSAGES=true
MEMORY_LONG_TERM_FILE=auto_memory.md
MEMORY_CAPTURE_KEYWORDS=记住,以后,下次,如果有人,有人提到,参考这个回复
```

这些运行时记忆文件默认不提交到仓库。

## 9. 常见问题

收不到消息：

- 确认机器人账号已经进群。
- 确认触发模式和你的发送方式一致。
- 确认 NapCat WebSocket 已连接。
- 确认程序窗口没有退出。

模型接口报错：

- 检查 `LLM_API_KEY`。
- 检查 `LLM_BASE_URL` 是否指向兼容 `/chat/completions` 的地址。
- 检查 `LLM_MODEL` 是否是服务商支持的模型名。
- 检查账户额度、地区限制或服务商状态。

机器人回复太长：

```dotenv
MAX_REPLY_CHARS=600
LLM_MAX_TOKENS=400
```

机器人回复被截断：

```dotenv
MAX_REPLY_CHARS=0
LLM_MAX_TOKENS=0
```

## 10. 长期运行

先在本地跑通，再放到服务器。服务器上流程一样：安装 Python、复制项目、填写 `.env`、安装依赖、启动脚本。

Windows 可以用计划任务、NSSM 或 PM2 托管；Linux 建议用 `systemd`。
