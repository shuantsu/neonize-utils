#!/usr/bin/env python3
"""Lista as últimas N mensagens RECEBIDAS (is_from_me=0) do SQLite local, sem rede.

Uso:
    python3.14 -u /root/whatsapp/daemon/wa_received.py [N] [--format text|json] [--chat FILTRO]
        [--include-status] [--include-newsletters] [--include-noise]

Exemplos:
    wa_received.py 15
    wa_received.py 50 --format json
    wa_received.py 15 --chat jesue
"""
import argparse
import json
import sqlite3
import sys
import unicodedata

sys.path.insert(0, "/root/whatsapp/daemon")
from wa_store import DB_PATH, NAMES_PATH, display_name, load_names

SESSION_PATH = "/root/whatsapp/whatsapp_session.db"


def parse_args():
    p = argparse.ArgumentParser(description="Últimas N mensagens recebidas (offline)")
    p.add_argument("n", nargs="?", type=int, default=15, help="quantidade (default: 15)")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.add_argument("--chat", default="", help="filtro substring chat/nome/pushname")
    p.add_argument("--include-status", action="store_true")
    p.add_argument("--include-newsletters", action="store_true")
    p.add_argument("--include-noise", action="store_true")
    return p.parse_args()


def load_lid_map():
    try:
        con = sqlite3.connect(SESSION_PATH)
        rows = con.execute("SELECT lid, pn FROM whatsmeow_lid_map").fetchall()
        con.close()
        return dict(rows)
    except Exception:
        return {}


def resolved_name(chat, names, lid2pn):
    base = display_name(chat, names)
    if base != chat:
        return base
    if "@lid" in chat:
        lid = chat.split("@")[0]
        pn = lid2pn.get(lid)
        if pn:
            hit = names.get("contacts", {}).get(pn + "@s.whatsapp.net")
            if hit:
                return hit
    return base


def norm(s):
    """lowercase sem acento para filtro tolerante (jesue == Jesué)."""
    return "".join(
        c for c in unicodedata.normalize("NFD", (s or "").lower()) if unicodedata.category(c) != "Mn"
    )


def main():
    args = parse_args()
    names = load_names()
    lid2pn = load_lid_map()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    noise_filter = "" if args.include_noise else "AND text NOT LIKE '<sem texto%' AND text NOT LIKE '<tipo%' AND text NOT LIKE '<erro%' AND text NOT LIKE '<vazio%'"
    status_filter = "" if args.include_status else "AND chat != 'status@broadcast'"
    news_filter = "" if args.include_newsletters else "AND chat NOT LIKE '%@newsletter%'"
    # com filtro de chat: busca pool maior sem filtro SQL (LIKE é acento-sensível)
    # e filtra depois com normalização; sem filtro: LIMIT direto.
    pool = max(1, args.n)
    use_post_filter = bool(args.chat)
    if use_post_filter:
        pool = max(pool * 20, 200)

    rows = conn.execute(
        f"""SELECT chat, sender, pushname, is_from_me, datetime, timestamp_ms, text
            FROM messages
            WHERE is_from_me=0 {noise_filter} {status_filter} {news_filter}
            ORDER BY timestamp_ms DESC LIMIT ?""",
        (pool,),
    ).fetchall()

    out = []
    for r in rows:
        d = dict(r)
        d["name"] = resolved_name(d["chat"], names, lid2pn)
        out.append(d)

    # filtro pós-resolução por nome/chat/pushname (ex: "Pai" só existe via lid_map, "jesue" == "Jesué")
    if args.chat:
        q = norm(args.chat)
        out = [d for d in out if q in norm(d["chat"]) or q in norm(d["pushname"]) or q in norm(d["sender"]) or q in norm(d["name"])]
        out = out[: max(1, args.n)]

    if args.format == "json":
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    if not out:
        print("nenhuma mensagem recebida no cache com esses filtros.")
        return
    for i, d in enumerate(out, 1):
        sender = d["pushname"] or d["sender"]
        print(f"{i}. [{d['datetime']}] {d['name']} ({d['chat']}) | {sender}: {d['text']}")


if __name__ == "__main__":
    main()
