# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


def env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


MEMORY_AUTO_SAVE = env_bool("MEMORY_AUTO_SAVE", "true")
MEMORY_AUTO_LOAD = env_bool("MEMORY_AUTO_LOAD", "true")
MEMORY_SAVE_RAW_GROUP_MESSAGES = env_bool("MEMORY_SAVE_RAW_GROUP_MESSAGES", "true")
MEMORY_LOG_DIR = os.getenv("MEMORY_LOG_DIR", "memory_data").strip()
MEMORY_LONG_TERM_FILE = os.getenv("MEMORY_LONG_TERM_FILE", "auto_memory.md").strip()
MEMORY_MAX_PROMPT_CHARS = int(os.getenv("MEMORY_MAX_PROMPT_CHARS", "3000"))
MEMORY_MIN_CAPTURE_CHARS = int(os.getenv("MEMORY_MIN_CAPTURE_CHARS", "8"))
MEMORY_CAPTURE_KEYWORDS = tuple(
    item.strip()
    for item in os.getenv(
        "MEMORY_CAPTURE_KEYWORDS",
        "记住,以后,以后如果,下次,如果有人,如果有人提到,有人提到,这部分记忆,参考这个回复",
    ).split(",")
    if item.strip()
)


def project_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parent / path


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def safe_group_id(group_id: str) -> str:
    return "".join(ch for ch in str(group_id) if ch.isalnum() or ch in {"_", "-"}) or "unknown"


def append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def should_capture_long_term(text: str) -> bool:
    stripped = (text or "").strip()
    if len(stripped) < MEMORY_MIN_CAPTURE_CHARS:
        return False
    return any(keyword in stripped for keyword in MEMORY_CAPTURE_KEYWORDS)


def memory_digest(group_id: str, user_id: str, text: str) -> str:
    source = f"{group_id}\n{user_id}\n{text.strip()}".encode("utf-8")
    return hashlib.sha1(source).hexdigest()[:16]


def append_long_term_memory(record: Dict[str, Any]) -> bool:
    path = project_path(MEMORY_LONG_TERM_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)

    digest = record["digest"]
    marker = f"<!-- memory:{digest} -->"
    if path.exists() and marker in path.read_text(encoding="utf-8", errors="ignore"):
        return False

    if not path.exists():
        path.write_text(
            "# 自动长期记忆\n\n"
            "这些内容来自群聊中的“记住/以后/如果有人提到”等指令，用于帮助机器人保持群内上下文。\n\n",
            encoding="utf-8",
        )

    block = (
        f"## {record['created_at']}\n\n"
        f"{marker}\n"
        f"- 群：{record['group_id']}\n"
        f"- 用户：{record['sender_name']}({record['user_id']})\n"
        f"- 内容：{record['text']}\n\n"
    )
    with path.open("a", encoding="utf-8") as file:
        file.write(block)
    return True


def record_group_message(event: Dict[str, Any], sender_name: str, text: str, mentioned: bool) -> bool:
    if not MEMORY_AUTO_SAVE:
        return False

    text = (text or "").strip()
    if not text:
        return False

    group_id = str(event.get("group_id", ""))
    user_id = str(event.get("user_id", ""))
    record = {
        "created_at": now_text(),
        "group_id": group_id,
        "user_id": user_id,
        "sender_name": sender_name,
        "message_id": event.get("message_id"),
        "mentioned_bot": mentioned,
        "text": text,
    }

    if MEMORY_SAVE_RAW_GROUP_MESSAGES:
        log_path = project_path(MEMORY_LOG_DIR) / f"group_{safe_group_id(group_id)}.jsonl"
        append_jsonl(log_path, record)

    if not should_capture_long_term(text):
        return False

    record["digest"] = memory_digest(group_id, user_id, text)
    return append_long_term_memory(record)


def load_auto_memory() -> str:
    if not MEMORY_AUTO_LOAD:
        return ""

    path = project_path(MEMORY_LONG_TERM_FILE)
    if not path.exists():
        return ""

    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        return ""
    if MEMORY_MAX_PROMPT_CHARS <= 0 or len(text) <= MEMORY_MAX_PROMPT_CHARS:
        return text
    return "（以下为自动长期记忆的最近部分）\n" + text[-MEMORY_MAX_PROMPT_CHARS:]
