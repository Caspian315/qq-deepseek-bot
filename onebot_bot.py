# -*- coding: utf-8 -*-
import asyncio
import json
import os
import re
import time
from collections import defaultdict
from typing import Any, Dict, Iterable, Tuple

import httpx
import websockets
from dotenv import load_dotenv

from auto_memory import record_group_message
from bot import TRIGGER_PREFIXES, apply_trigger_prefix, ask_deepseek


load_dotenv()


def env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


ONEBOT_HOST = os.getenv("ONEBOT_HOST", "127.0.0.1").strip()
ONEBOT_PORT = int(os.getenv("ONEBOT_PORT", "8080"))
ONEBOT_PATH = os.getenv("ONEBOT_PATH", "/onebot/v11/ws").strip()
ONEBOT_ACCESS_TOKEN = os.getenv("ONEBOT_ACCESS_TOKEN", "").strip()
ONEBOT_GROUP_REPLY_MODE = os.getenv("ONEBOT_GROUP_REPLY_MODE", "at").strip().lower()
ONEBOT_QUOTE_REPLY = os.getenv("ONEBOT_QUOTE_REPLY", "true").strip().lower() == "true"
ONEBOT_MESSAGE_CHUNK_SIZE = int(os.getenv("ONEBOT_MESSAGE_CHUNK_SIZE", "1800"))
ONEBOT_AUTO_REPLY_MATH_ONLY = env_bool("ONEBOT_AUTO_REPLY_MATH_ONLY", "true")
ONEBOT_AUTO_REPLY_MAX_CHARS = int(os.getenv("ONEBOT_AUTO_REPLY_MAX_CHARS", "180"))
ONEBOT_AUTO_REPLY_COOLDOWN_SECONDS = float(os.getenv("ONEBOT_AUTO_REPLY_COOLDOWN_SECONDS", "45"))
ONEBOT_AUTO_REPLY_PREFACE = os.getenv("ONEBOT_AUTO_REPLY_PREFACE", "这题都能卡？先别急。").strip()
ONEBOT_ALLOWED_GROUPS = {
    item.strip()
    for item in os.getenv("ONEBOT_ALLOWED_GROUPS", "").split(",")
    if item.strip()
}
conversation_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
send_locks: Dict[int, asyncio.Lock] = {}
auto_reply_last_at: Dict[str, float] = defaultdict(float)

MATH_KEYWORDS = (
    "数学",
    "高数",
    "数分",
    "数学分析",
    "高等代数",
    "线性代数",
    "离散数学",
    "组合数学",
    "图论",
    "数论",
    "概率",
    "统计",
    "函数",
    "定义域",
    "值域",
    "导数",
    "微分",
    "积分",
    "极限",
    "级数",
    "矩阵",
    "行列式",
    "特征值",
    "特征向量",
    "向量",
    "方程",
    "不等式",
    "单调",
    "连续",
    "可导",
    "奇函数",
    "偶函数",
    "集合",
    "映射",
    "同余",
    "模",
    "证明",
    "证得",
    "求解",
    "递推",
    "数列",
    "几何",
    "三角",
    "正弦",
    "余弦",
    "泰勒",
    "拉格朗日",
    "柯西",
)


def log(message: str) -> None:
    print(f"[onebot] {message}", flush=True)


def websocket_path(websocket: Any, path: str | None) -> str:
    if path:
        return path.split("?", 1)[0]
    request = getattr(websocket, "request", None)
    request_path = getattr(request, "path", "") if request else ""
    return str(request_path).split("?", 1)[0]


def websocket_headers(websocket: Any) -> Dict[str, str]:
    request = getattr(websocket, "request", None)
    headers = getattr(request, "headers", None) if request else None
    if headers is None:
        headers = getattr(websocket, "request_headers", {})
    return {str(key).lower(): str(value) for key, value in dict(headers).items()}


async def check_connection(websocket: Any, path: str | None) -> bool:
    actual_path = websocket_path(websocket, path)
    if actual_path != ONEBOT_PATH:
        log(f"拒绝连接：路径 {actual_path} 不等于 {ONEBOT_PATH}")
        await websocket.close(code=1008, reason="invalid path")
        return False

    if ONEBOT_ACCESS_TOKEN:
        headers = websocket_headers(websocket)
        auth = headers.get("authorization", "")
        expected = f"Bearer {ONEBOT_ACCESS_TOKEN}"
        if auth != expected:
            log("拒绝连接：access token 不匹配")
            await websocket.close(code=1008, reason="invalid token")
            return False

    return True


def message_segments(event: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    message = event.get("message", [])
    if isinstance(message, list):
        return message
    return []


def extract_text_and_mention(event: Dict[str, Any]) -> Tuple[str, bool]:
    self_id = str(event.get("self_id", ""))
    text_parts = []
    mentioned = False

    for segment in message_segments(event):
        segment_type = segment.get("type")
        data = segment.get("data", {}) or {}

        if segment_type == "text":
            text_parts.append(str(data.get("text", "")))
        elif segment_type == "at":
            qq = str(data.get("qq", ""))
            if qq == self_id:
                mentioned = True
            elif qq and qq != "all":
                text_parts.append(f"@{qq} ")

    if text_parts:
        return "".join(text_parts).strip(), mentioned

    raw_message = str(event.get("raw_message", ""))
    if self_id and re.search(rf"\[CQ:at,qq={re.escape(self_id)}\]", raw_message):
        mentioned = True
        raw_message = re.sub(rf"\[CQ:at,qq={re.escape(self_id)}\]", "", raw_message)
    raw_message = re.sub(r"\[CQ:[^\]]+\]", "", raw_message)
    return raw_message.strip(), mentioned


def event_sender_name(event: Dict[str, Any]) -> str:
    sender = event.get("sender", {}) or {}
    for key in ("card", "nickname", "user_id"):
        value = sender.get(key)
        if value:
            return str(value)
    return str(event.get("user_id", "群友"))


def allowed_group(group_id: str) -> bool:
    return not ONEBOT_ALLOWED_GROUPS or group_id in ONEBOT_ALLOWED_GROUPS


def is_math_related(text: str) -> bool:
    if not text:
        return False

    lowered = text.lower()
    if any(keyword in text for keyword in MATH_KEYWORDS):
        return True

    math_patterns = (
        r"(?:f|g|h)\s*\(",
        r"[a-z]\s*(?:\^|²|³|=|≤|≥|<|>)",
        r"(?:\\frac|\\sqrt|\\sum|\\int|\\mathbb|\\infty)",
        r"(?:∑|∫|√|∞|≤|≥|≠|∈|∉|⊂|⊆|⊇)",
        r"\b(?:sin|cos|tan|log|ln|mod)\b",
        r"\d+\s*(?:\+|-|\*|/|\^|=|<|>)\s*\d+",
    )
    return any(re.search(pattern, lowered) for pattern in math_patterns)


def is_auto_short_reply(text: str, mentioned: bool) -> bool:
    if mentioned or ONEBOT_GROUP_REPLY_MODE != "all":
        return False
    return not ONEBOT_AUTO_REPLY_MATH_ONLY or is_math_related(text)


def can_auto_reply(group_id: str) -> bool:
    if ONEBOT_AUTO_REPLY_COOLDOWN_SECONDS <= 0:
        return True

    now = time.monotonic()
    last = auto_reply_last_at[group_id]
    if now - last < ONEBOT_AUTO_REPLY_COOLDOWN_SECONDS:
        return False

    auto_reply_last_at[group_id] = now
    return True


def auto_short_prompt(text: str) -> str:
    preface_rule = (
        f"回复必须先说“{ONEBOT_AUTO_REPLY_PREFACE}”，再给正常数学提示。"
        if ONEBOT_AUTO_REPLY_PREFACE
        else "直接给正常数学提示。"
    )
    return (
        "【未被@的数学短插话】群里正在讨论数学。"
        "请只用1到2句话给关键提示、纠正或思路提醒；"
        "不要完整长篇解题，不要展开证明，语气自然一点。"
        f"{preface_rule}\n\n"
        f"{text}"
    )


def apply_auto_reply_preface(reply: str) -> str:
    reply = (reply or "").strip()
    if not ONEBOT_AUTO_REPLY_PREFACE:
        return reply
    if reply.startswith(ONEBOT_AUTO_REPLY_PREFACE):
        return reply
    return f"{ONEBOT_AUTO_REPLY_PREFACE}{reply}"


def shorten_auto_reply(reply: str) -> str:
    reply = " ".join((reply or "").split())
    if ONEBOT_AUTO_REPLY_MAX_CHARS <= 0 or len(reply) <= ONEBOT_AUTO_REPLY_MAX_CHARS:
        return reply

    window = reply[: ONEBOT_AUTO_REPLY_MAX_CHARS + 1]
    cut = max(
        window.rfind("。"),
        window.rfind("！"),
        window.rfind("？"),
        window.rfind(";"),
        window.rfind("；"),
    )
    if cut < ONEBOT_AUTO_REPLY_MAX_CHARS // 2:
        cut = ONEBOT_AUTO_REPLY_MAX_CHARS
    else:
        cut += 1
    return reply[:cut].rstrip() + "..."


def group_prompt_text(text: str, mentioned: bool) -> str:
    mode = ONEBOT_GROUP_REPLY_MODE

    if TRIGGER_PREFIXES:
        prefixed = apply_trigger_prefix(text)
        if mode == "all":
            if not mentioned and ONEBOT_AUTO_REPLY_MATH_ONLY and not is_math_related(text):
                return ""
            return prefixed or text
        return prefixed if (mentioned or mode == "prefix") else ""

    if mode == "all":
        if not mentioned and ONEBOT_AUTO_REPLY_MATH_ONLY and not is_math_related(text):
            return ""
        return text
    if mode == "prefix":
        log("当前为 prefix 模式，但 TRIGGER_PREFIXES 为空；这条消息不会触发。")
        return ""
    return text if mentioned else ""


async def send_action(websocket: Any, action: str, params: Dict[str, Any]) -> None:
    payload = {
        "action": action,
        "params": params,
        "echo": f"{action}:{time.time_ns()}",
    }
    websocket_id = id(websocket)
    send_lock = send_locks.setdefault(websocket_id, asyncio.Lock())
    async with send_lock:
        await websocket.send(json.dumps(payload, ensure_ascii=False))


def quote_prefix(event: Dict[str, Any]) -> str:
    if not ONEBOT_QUOTE_REPLY:
        return ""
    message_id = event.get("message_id")
    if message_id is None:
        return ""
    return f"[CQ:reply,id={message_id}]"


def split_reply(reply: str) -> list[str]:
    reply = (reply or "").strip()
    if not reply:
        return []
    if ONEBOT_MESSAGE_CHUNK_SIZE <= 0 or len(reply) <= ONEBOT_MESSAGE_CHUNK_SIZE:
        return [reply]

    chunks = []
    rest = reply
    while len(rest) > ONEBOT_MESSAGE_CHUNK_SIZE:
        window = rest[: ONEBOT_MESSAGE_CHUNK_SIZE + 1]
        cut = max(
            window.rfind("\n"),
            window.rfind("。"),
            window.rfind("！"),
            window.rfind("？"),
            window.rfind(";"),
            window.rfind("；"),
        )
        if cut < ONEBOT_MESSAGE_CHUNK_SIZE // 2:
            cut = ONEBOT_MESSAGE_CHUNK_SIZE
        else:
            cut += 1
        chunks.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        chunks.append(rest)
    return [chunk for chunk in chunks if chunk]


async def send_group_reply(websocket: Any, event: Dict[str, Any], group_id: str, reply: str) -> None:
    chunks = split_reply(reply)
    for index, chunk in enumerate(chunks):
        await send_action(
            websocket,
            "send_group_msg",
            {
                "group_id": int(group_id) if group_id.isdigit() else group_id,
                "message": (quote_prefix(event) if index == 0 else "") + chunk,
            },
        )
        if index < len(chunks) - 1:
            await asyncio.sleep(0.8)


async def send_private_reply(websocket: Any, user_id: str, reply: str) -> None:
    chunks = split_reply(reply)
    for index, chunk in enumerate(chunks):
        await send_action(
            websocket,
            "send_private_msg",
            {
                "user_id": int(user_id) if user_id.isdigit() else user_id,
                "message": chunk,
            },
        )
        if index < len(chunks) - 1:
            await asyncio.sleep(0.8)


async def handle_group_message(websocket: Any, event: Dict[str, Any]) -> None:
    self_id = str(event.get("self_id", ""))
    user_id = str(event.get("user_id", ""))
    group_id = str(event.get("group_id", ""))

    if user_id == self_id or not allowed_group(group_id):
        return

    raw_text, mentioned = extract_text_and_mention(event)
    sender_name = event_sender_name(event)
    if record_group_message(event, sender_name, raw_text, mentioned):
        log(f"已写入自动长期记忆: group_id={group_id}, user_id={user_id}")

    auto_short = is_auto_short_reply(raw_text, mentioned)
    text = group_prompt_text(raw_text, mentioned)
    if not text:
        return
    if auto_short:
        if not can_auto_reply(group_id):
            log(f"跳过数学自动插话：group_id={group_id}, cooldown={ONEBOT_AUTO_REPLY_COOLDOWN_SECONDS}s")
            return
        text = auto_short_prompt(text)

    log(f"收到群聊消息: group_id={group_id}, user_id={user_id}, content={text}")
    conversation_id = f"onebot:group:{group_id}"
    async with conversation_locks[conversation_id]:
        log(f"开始调用 DeepSeek: {conversation_id}")
        try:
            reply = await ask_deepseek(conversation_id, sender_name, text)
        except httpx.TimeoutException:
            log("DeepSeek 请求超时")
            reply = (
                "题目我已经看全了，但这次推理超过了后台等待时间。\n"
                "这类长证明题建议把题目分成几段发，或者让我先只做其中一问。"
            )
        except httpx.HTTPStatusError as exc:
            log(f"DeepSeek HTTP error: {exc.response.status_code} {exc.response.text[:300]}")
            reply = "DeepSeek 接口这次报错了，稍后再试一下。"
        if auto_short:
            reply = apply_auto_reply_preface(reply)
            reply = shorten_auto_reply(reply)
        log(f"DeepSeek 回复已生成: {conversation_id}")
        await send_group_reply(websocket, event, group_id, reply)


async def handle_private_message(websocket: Any, event: Dict[str, Any]) -> None:
    self_id = str(event.get("self_id", ""))
    user_id = str(event.get("user_id", ""))
    if user_id == self_id:
        return

    text, _ = extract_text_and_mention(event)
    if not text:
        return

    log(f"收到私聊消息: user_id={user_id}, content={text}")
    conversation_id = f"onebot:private:{user_id}"
    async with conversation_locks[conversation_id]:
        log(f"开始调用 DeepSeek: {conversation_id}")
        try:
            reply = await ask_deepseek(conversation_id, "私聊用户", text)
        except httpx.TimeoutException:
            log("DeepSeek 请求超时")
            reply = "这次推理超时了。长题可以分段发，或者先让我只做其中一问。"
        except httpx.HTTPStatusError as exc:
            log(f"DeepSeek HTTP error: {exc.response.status_code} {exc.response.text[:300]}")
            reply = "DeepSeek 接口这次报错了，稍后再试一下。"
        log(f"DeepSeek 回复已生成: {conversation_id}")
        await send_private_reply(websocket, user_id, reply)


async def handle_event(websocket: Any, event: Dict[str, Any]) -> None:
    if event.get("post_type") != "message":
        return

    message_type = event.get("message_type")
    try:
        if message_type == "group":
            await handle_group_message(websocket, event)
        elif message_type == "private":
            await handle_private_message(websocket, event)
    except Exception as exc:
        log(f"处理消息失败: {type(exc).__name__}: {exc}")


async def websocket_handler(websocket: Any, path: str | None = None) -> None:
    if not await check_connection(websocket, path):
        return

    log("NapCat 已连接")
    tasks: set[asyncio.Task] = set()
    try:
        async for raw in websocket:
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                task = asyncio.create_task(handle_event(websocket, event))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
    finally:
        for task in tasks:
            task.cancel()
        send_locks.pop(id(websocket), None)
        log("NapCat 已断开")


async def main() -> None:
    log(f"启动 OneBot WebSocket 服务: ws://{ONEBOT_HOST}:{ONEBOT_PORT}{ONEBOT_PATH}")
    log(f"群聊触发模式: {ONEBOT_GROUP_REPLY_MODE}")
    if ONEBOT_GROUP_REPLY_MODE == "all" and ONEBOT_AUTO_REPLY_MATH_ONLY:
        log(
            "全群监听已启用：仅数学相关消息自动短回复，"
            f"冷却 {ONEBOT_AUTO_REPLY_COOLDOWN_SECONDS}s，最多 {ONEBOT_AUTO_REPLY_MAX_CHARS} 字，"
            f"开场白：{ONEBOT_AUTO_REPLY_PREFACE or '无'}"
        )
    async with websockets.serve(
        websocket_handler,
        ONEBOT_HOST,
        ONEBOT_PORT,
        max_size=8 * 1024 * 1024,
        ping_interval=30,
        ping_timeout=30,
    ):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
