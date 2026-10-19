#!/usr/bin/env python3
"""Helpers compartilhados: SQLite cache + normalização + nomes."""
import datetime
import json
import os
import sqlite3

DB_PATH = os.environ.get("WA_DB", "/root/whatsapp/wa_messages.db")
NAMES_PATH = os.environ.get("WA_NAMES", "/root/whatsapp/wa_names.json")

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    chat TEXT NOT NULL,
    sender TEXT,
    pushname TEXT,
    is_from_me INTEGER DEFAULT 0,
    is_group INTEGER DEFAULT 0,
    timestamp_ms INTEGER NOT NULL,
    datetime TEXT,
    text TEXT,
    source TEXT
);
CREATE INDEX IF NOT EXISTS idx_msg_chat_ts ON messages(chat, timestamp_ms DESC);
CREATE INDEX IF NOT EXISTS idx_msg_ts ON messages(timestamp_ms DESC);
"""

OUTBOX_SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'text',
    text TEXT DEFAULT '',
    file TEXT DEFAULT '',
    caption TEXT DEFAULT '',
    ptt INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER DEFAULT 0,
    error TEXT DEFAULT '',
    created_ms INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox(status, id);
"""


def get_conn(path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def normalize_ts(ts) -> tuple[int, str]:
    try:
        ts = int(ts)
    except Exception:
        return 0, "?"
    if ts <= 0:
        return 0, "?"
    if ts > 10_000_000_000_000:  # micros
        sec = ts / 1_000_000
        ms = ts // 1000
    elif ts > 100_000_000_000:  # ms
        sec = ts / 1000
        ms = ts
    else:  # segundos
        sec = ts
        ms = ts * 1000
    try:
        dt = datetime.datetime.fromtimestamp(sec).strftime("%d/%m %H:%M")
    except Exception:
        dt = str(ts)
    return ms, dt


def is_noise_text(t: str) -> bool:
    if not t:
        return True
    return (
        t.startswith("<sem texto")
        or t.startswith("<tipo")
        or t.startswith("<erro")
        or t.startswith("<vazio")
    )


def upsert(conn: sqlite3.Connection, d: dict) -> bool:
    """Insere ou melhora registro existente (prefere texto real). Retorna True se inseriu/atualizou."""
    ts_raw = d.get("timestamp_ms", d.get("timestamp", 0))
    ms, dt = normalize_ts(ts_raw)
    if ms <= 0:
        return False
    _id = d.get("id") or f"{d.get('chat')}-{ms}-{str(d.get('text',''))[:20]}"
    if is_noise_text(d.get("text", "")):
        # não sobrescreve texto bom com ruído; só insere se não existir
        cur = conn.execute("SELECT id FROM messages WHERE id=?", (_id,))
        if cur.fetchone():
            return False
    try:
        conn.execute(
            """INSERT INTO messages (id, chat, sender, pushname, is_from_me, is_group, timestamp_ms, datetime, text, source)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 text=excluded.text, pushname=excluded.pushname, timestamp_ms=excluded.timestamp_ms,
                 datetime=excluded.datetime, source=excluded.source
               WHERE messages.text LIKE '<sem texto%' OR messages.text LIKE '<tipo%' OR messages.text LIKE '<erro%' OR messages.text LIKE '<vazio%'""",
            (
                _id,
                d.get("chat", ""),
                d.get("sender", ""),
                d.get("pushname", ""),
                1 if d.get("is_from_me") else 0,
                1 if d.get("is_group") else 0,
                ms,
                d.get("datetime") if len(str(d.get("datetime", ""))) <= 12 else dt,
                d.get("text", ""),
                d.get("source", ""),
            ),
        )
        # corrige datetime se veio no formato antigo (timestamp cru)
        if len(str(d.get("datetime", ""))) > 12:
            conn.execute("UPDATE messages SET datetime=? WHERE id=?", (dt, _id))
        return True
    except Exception:
        return False


def load_names() -> dict:
    try:
        with open(NAMES_PATH) as f:
            return json.load(f)
    except Exception:
        return {"contacts": {}, "groups": {}}


def display_name(chat: str, names: dict) -> str:
    if not chat:
        return "?"
    if chat == "status@broadcast":
        return "Status"
    if "@newsletter" in chat:
        return names.get("groups", {}).get(chat, chat)
    if "@g.us" in chat:
        return names.get("groups", {}).get(chat, chat)
    # contato individual: tenta nome salvo, senão pushname vem na mensagem
    return names.get("contacts", {}).get(chat, chat)
