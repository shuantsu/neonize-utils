#!/usr/bin/env python3
"""Enfileira envio no outbox do daemon (OFFLINE — nunca conecta, nunca derruba o daemon).

Uso:
    wa_enqueue.py <target> --text "mensagem"
    wa_enqueue.py <target> --file /caminho/arquivo.mp3 [--caption "legenda"] [--ptt]
"""
import os
import sqlite3
import sys
import time

sys.path.insert(0, "/root/whatsapp/daemon")
from wa_store import DB_PATH, OUTBOX_SCHEMA  # noqa: E402


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)
    target = args[0]
    kind, text, path, caption, ptt = "text", "", "", "", 0
    i = 1
    while i < len(args):
        if args[i] == "--text" and i + 1 < len(args):
            text = args[i + 1]
            i += 2
        elif args[i] == "--file" and i + 1 < len(args):
            kind, path = "media", args[i + 1]
            i += 2
        elif args[i] == "--caption" and i + 1 < len(args):
            caption = args[i + 1]
            i += 2
        elif args[i] == "--ptt":
            ptt = 1
            i += 1
        else:
            i += 1
    if kind == "text" and not text:
        print("erro: informe --text ou --file")
        sys.exit(1)
    if kind == "media" and not os.path.isfile(path):
        print(f"erro: arquivo nao encontrado: {path}")
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(OUTBOX_SCHEMA)
    cur = conn.execute(
        "INSERT INTO outbox (target, kind, text, file, caption, ptt, created_ms) VALUES (?,?,?,?,?,?,?)",
        (target, kind, text, path, caption, ptt, int(time.time() * 1000)),
    )
    conn.commit()
    print(f"enfileirado #{cur.lastrowid} para {target} (daemon envia em ~5s)")
    conn.close()


if __name__ == "__main__":
    main()
