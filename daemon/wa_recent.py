#!/usr/bin/env python3
"""Consulta INSTANTÂNEA: lê só o SQLite local, sem conectar no WhatsApp.

Uso:
    /root/whatsapp/.venv/bin/python -u /root/whatsapp/daemon/wa_recent.py [N_CHATS] [--per-chat N] [--format text|json] [--chat FILTRO] [--include-me] [--include-status] [--include-newsletters] [--include-noise]

Exemplos:
    wa_recent.py 5                        # 5 últimos chats, 5 msgs cada (padrão)
    wa_recent.py 5 --per-chat 5 --format json
    wa_recent.py 10 --per-chat 3 --chat jesue
"""
import argparse
import json
import sqlite3
import sys

sys.path.insert(0, "/root/whatsapp/daemon")
from wa_store import DB_PATH, display_name, get_conn, is_noise_text, load_names


def parse_args():
    p = argparse.ArgumentParser(description="Últimos chats + mensagens (instantâneo, offline)")
    p.add_argument("n", nargs="?", type=int, default=5, help="nº de chats (default: 5)")
    p.add_argument("--per-chat", type=int, default=5, help="msgs por chat (default: 5)")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.add_argument("--chat", default="", help="filtro substring chat/nome")
    p.add_argument("--include-me", action="store_true", default=True, help="incluir enviadas (default: sim)")
    p.add_argument("--no-me", action="store_true", help="só recebidas")
    p.add_argument("--include-status", action="store_true")
    p.add_argument("--include-newsletters", action="store_true")
    p.add_argument("--include-noise", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    names = load_names()
    conn = get_conn()
    conn.row_factory = sqlite3.Row

    only_me_filter = "AND is_from_me=0" if args.no_me else ""
    noise_filter = "" if args.include_noise else "AND text NOT LIKE '<sem texto%' AND text NOT LIKE '<tipo%' AND text NOT LIKE '<erro%' AND text NOT LIKE '<vazio%'"
    status_filter = "" if args.include_status else "AND chat != 'status@broadcast'"
    news_filter = "" if args.include_newsletters else "AND chat NOT LIKE '%@newsletter%'"
    chat_filter = ""
    params: list = []
    if args.chat:
        chat_filter = "AND (chat LIKE ? OR pushname LIKE ?)"
        params = [f"%{args.chat}%", f"%{args.chat}%"]

    # últimos N chats por max(timestamp)
    q = f"""SELECT chat, MAX(timestamp_ms) AS last_ts FROM messages
            WHERE 1=1 {only_me_filter} {noise_filter} {status_filter} {news_filter} {chat_filter}
            GROUP BY chat ORDER BY last_ts DESC LIMIT ?"""
    rows = conn.execute(q, (*params, args.n)).fetchall()
    if not rows:
        print("cache vazio (daemon ainda não coletou nada?). Rode o daemon e aguarde o sync.")
        return

    result = []
    for r in rows:
        chat = r["chat"]
        msgs = conn.execute(
            f"""SELECT * FROM messages WHERE chat=?
                {only_me_filter} {noise_filter} {status_filter} {news_filter}
                ORDER BY timestamp_ms DESC LIMIT ?""",
            (chat, args.per_chat),
        ).fetchall()
        md = [dict(m) for m in msgs]
        result.append({"chat": chat, "name": display_name(chat, names), "messages": md})

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    for i, c in enumerate(result, 1):
        print(f"\n{i}. {c['name']} ({c['chat']})")
        for m in c["messages"]:
            me = " [eu]" if m["is_from_me"] else ""
            sender = m["pushname"] or m["sender"]
            print(f"   [{m['datetime']}] {sender}{me}: {m['text']}")


if __name__ == "__main__":
    main()
