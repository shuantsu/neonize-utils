#!/usr/bin/env python3
"""Lista as últimas N mensagens recebidas no WhatsApp via offline/live sync.

Uso:
    python3.14 -u /root/whatsapp/listagem/list_recent_messages.py [N] [opções]

Exemplos:
    python3.14 -u /root/whatsapp/listagem/list_recent_messages.py 20
    python3.14 -u /root/whatsapp/listagem/list_recent_messages.py 5 --chat Jesué
    python3.14 -u /root/whatsapp/listagem/list_recent_messages.py 10 --include-status --include-me
    python3.14 -u /root/whatsapp/listagem/list_recent_messages.py 20 --format json --output /tmp/msgs.json

Como funciona (limitação da API):
    - O WhatsApp/whatsmeow NÃO tem endpoint "busque as últimas N".
    - O script conecta com /root/whatsapp/whatsapp_session.db e coleta o que o servidor
      entrega: OfflineSync (msgs recebidas enquanto offline) + mensagens
      ao vivo + HistorySync (quando enviado).
    - Por isso o resultado = "últimas mensagens entregues no sync", não um
      SELECT no histórico completo.
"""
import argparse
import datetime
import json
import os
import sys

from neonize.client import NewClient
from neonize.events import (
    ConnectedEv,
    HistorySyncEv,
    MessageEv,
    OfflineSyncCompletedEv,
    OfflineSyncPreviewEv,
)
from neonize.utils import extract_text

DEFAULT_OUT = "/tmp/opencode/recent_messages.jsonl"


DB_PATH = "/root/whatsapp/wa_messages.db"
NAMES_PATH = "/root/whatsapp/wa_names.json"


def parse_args():
    p = argparse.ArgumentParser(description="Lista últimas N mensagens do WhatsApp")
    p.add_argument(
        "n",
        nargs="?",
        default="20",
        help="quantidade (default: 20). Se não for número, é tratado como filtro --chat",
    )
    p.add_argument("--offline", action="store_true", help="não conecta: só lê wa_messages.db (rápido)")
    p.add_argument("--timeout", type=int, default=35, help="segundos coletando (default: 35)")
    p.add_argument("--include-status", action="store_true", help="incluir status@broadcast")
    p.add_argument("--include-newsletters", action="store_true", help="incluir @newsletter")
    p.add_argument("--include-me", action="store_true", help="incluir msgs enviadas por mim (default: só recebidas)")
    p.add_argument("--include-noise", action="store_true", help="incluir msgs sem texto (reactions, chaves, mídia sem caption)")
    p.add_argument("--chat", default="", help="filtrar por substring do chat/pushname (ex: Jesué, 1203631838)")
    p.add_argument("--output", default=DEFAULT_OUT, help=f"arquivo JSONL (default: {DEFAULT_OUT})")
    p.add_argument("--format", choices=["text", "json"], default="text", help="saída no stdout")
    p.add_argument("--quiet-period", type=int, default=8, help="sair antes se N msgs e silêncio de X seg (0=desliga)")
    args = p.parse_args()
    raw = str(args.n).strip()
    try:
        args.n = max(1, int(raw))
    except ValueError:
        if args.chat:
            p.error(f"posicional {raw!r} inválido (já existe --chat {args.chat!r})")
        args.chat = raw
        args.n = 20
    return args


def fmt_jid(j):
    try:
        u = getattr(j, "User", "")
        s = getattr(j, "Server", "")
        return f"{u}@{s}" if u else str(j)
    except Exception:
        return str(j)


def normalize_ts(ts):
    """Aceita segundos, ms ou micros; retorna (ts_ms, datetime_str)."""
    try:
        ts = int(ts)
    except Exception:
        return 0, "?"
    if ts <= 0:
        return 0, "?"
    # micros (>1e14) -> /1e6 ; ms (>1e11) -> /1e3 ; segundos caso contrário
    if ts > 10_000_000_000_000:
        sec = ts / 1_000_000
        ms = ts // 1000
    elif ts > 100_000_000_000:
        sec = ts / 1000
        ms = ts
    else:
        sec = ts
        ms = ts * 1000
    try:
        dt = datetime.datetime.fromtimestamp(sec).strftime("%d/%m %H:%M")
    except Exception:
        dt = str(ts)
    return ms, dt


def is_noise_text(t):
    return (
        not t
        or t.startswith("<sem texto")
        or t.startswith("<tipo")
        or t.startswith("<erro")
        or t.startswith("<vazio")
    )


def load_names():
    """Retorna (contatos, grupos) como {jid: nome}."""
    try:
        with open(NAMES_PATH) as f:
            d = json.load(f)
        return d.get("contacts", {}) or {}, d.get("groups", {}) or {}
    except Exception:
        return {}, {}


def load_local_db():
    """Lê o histórico local mantido pelo wa_daemon (read-only, offline)."""
    rows = []
    if not os.path.exists(DB_PATH):
        return rows
    import sqlite3

    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT id, chat, sender, pushname, is_from_me, is_group, "
            "timestamp_ms, datetime, text FROM messages"
        )
        for r in cur:
            rows.append(
                {
                    "id": r["id"] or "",
                    "timestamp_ms": int(r["timestamp_ms"] or 0),
                    "datetime": r["datetime"] or "?",
                    "chat": r["chat"] or "",
                    "sender": r["sender"] or "",
                    "pushname": r["pushname"] or "",
                    "is_from_me": bool(r["is_from_me"]),
                    "is_group": bool(r["is_group"]),
                    "text": r["text"] or "",
                    "source": "local_db",
                }
            )
        conn.close()
    except Exception as e:
        print(f"aviso: não li {DB_PATH}: {e}", flush=True)
    return rows


def msg_to_dict(msg):
    info = msg.Info
    src = info.MessageSource
    raw_ts = int(getattr(info, "Timestamp", 0))
    ts_ms, dt = normalize_ts(raw_ts)
    try:
        text = extract_text(msg.Message) or ""
    except Exception:
        text = ""
    if not text:
        try:
            fields = [f.name for f, _ in msg.Message.ListFields()]
            text = f"<sem texto - tipo: {fields}>" if fields else "<sem texto>"
        except Exception:
            text = "<sem texto>"
    return {
        "id": getattr(info, "ID", ""),
        "timestamp_ms": ts_ms,
        "datetime": dt,
        "chat": fmt_jid(src.Chat),
        "sender": fmt_jid(src.Sender),
        "pushname": getattr(info, "Pushname", ""),
        "is_from_me": bool(getattr(src, "IsFromMe", False)),
        "is_group": bool(getattr(src, "IsGroup", False)),
        "text": text,
        "source": "live/offline",
    }


def finalize(args, collected, n, elapsed=0.0):
    """Dedup + filtros + ordenação + impressão."""
    by_id = {}
    for d in collected:
        _id = d.get("id") or f"{d.get('chat')}-{d.get('timestamp_ms')}-{str(d.get('text', ''))[:20]}"
        if _id not in by_id:
            by_id[_id] = d
        else:
            old_noise = is_noise_text(by_id[_id].get("text", ""))
            new_noise = is_noise_text(d.get("text", ""))
            if old_noise and not new_noise:
                by_id[_id] = d
    rows = list(by_id.values())

    if not args.include_me:
        rows = [r for r in rows if not r.get("is_from_me")]
    if not args.include_status:
        rows = [r for r in rows if r.get("chat") != "status@broadcast"]
    if not args.include_newsletters:
        rows = [r for r in rows if "@newsletter" not in str(r.get("chat"))]
    if not args.include_noise:
        rows = [r for r in rows if not is_noise_text(r.get("text", ""))]
    if args.chat:
        contacts, groups = load_names()
        q = args.chat.lower()
        named = {
            jid
            for jid, nm in list(groups.items()) + list(contacts.items())
            if nm and q in str(nm).lower()
        }

        def match(r):
            chat = str(r.get("chat", ""))
            if q in chat.lower() or q in str(r.get("pushname", "")).lower():
                return True
            return any(j in chat for j in named)

        rows = [r for r in rows if match(r)]

    rows.sort(key=lambda r: r.get("timestamp_ms", 0), reverse=True)
    top = rows[:n]

    srcs = {}
    for r in by_id.values():
        s = r.get("source", "?")
        srcs[s] = srcs.get(s, 0) + 1
    print(
        f"\n===== ÚLTIMAS {len(top)} "
        f"(de {len(by_id)} únicas, {len(collected)} brutas | fontes: {srcs} | {elapsed:.0f}s) =====",
        flush=True,
    )
    if args.format == "json":
        print(json.dumps(top, ensure_ascii=False, indent=2), flush=True)
    else:
        for i, r in enumerate(top, 1):
            grp = " [grupo]" if r.get("is_group") else ""
            mine = " [eu]" if r.get("is_from_me") else ""
            print(
                f"{i}. [{r.get('datetime')}] {r.get('pushname')}{grp}{mine} ({r.get('chat')}): {r.get('text')}",
                flush=True,
            )


def main():
    args = parse_args()
    n = max(1, args.n)
    collected = []
    last_msg_time = [0.0]
    import time as _time
    start = _time.time()

    # limpa saída
    try:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        open(args.output, "w").close()
    except Exception as e:
        print(f"aviso: não limpei {args.output}: {e}", flush=True)

    def save(d, live=True):
        collected.append(d)
        try:
            with open(args.output, "a") as f:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
        except Exception:
            pass
        if live:
            last_msg_time[0] = _time.time()

    # fonte primária: histórico local (inclui msgs enviadas por mim)
    db_rows = load_local_db()
    last_msg_time[0] = start
    for r in db_rows:
        save(r, live=False)
    print(
        f"HISTÓRICO LOCAL: {len(db_rows)} msgs de {DB_PATH}"
        + (" (modo --offline, sem conexão)" if args.offline else ""),
        flush=True,
    )

    if args.offline:
        finalize(args, collected, n, elapsed=_time.time() - start)
        os._exit(0)

    client = NewClient("/root/whatsapp/whatsapp_session.db")

    @client.event(ConnectedEv)
    def on_connected(c, ev):
        print("CONECTADO - coletando sync + ao vivo...", flush=True)

    @client.event(OfflineSyncPreviewEv)
    def on_preview(c, ev):
        print(f"OFFLINE PREVIEW: total={ev.Total} msgs={ev.Message}", flush=True)

    @client.event(OfflineSyncCompletedEv)
    def on_completed(c, ev):
        print(f"OFFLINE SYNC COMPLETO: count={ev.Count}", flush=True)

    @client.event(HistorySyncEv)
    def on_history(c, ev):
        try:
            convs = getattr(ev.Data, "conversations", [])
            print(f"HISTORY SYNC: {len(convs)} conversas", flush=True)
            for conv in convs:
                for m in getattr(conv, "messages", []):
                    try:
                        wbi = getattr(m, "message", None)
                        if wbi is None:
                            continue
                        ts = getattr(wbi, "messageTimestamp", 0)
                        ts_ms, dt = normalize_ts(ts)
                        key = getattr(wbi, "key", None)
                        chat = getattr(key, "remoteJid", "") if key else ""
                        sender = getattr(key, "participant", "") or chat
                        frm = bool(getattr(key, "fromMe", False))
                        e2e = getattr(wbi, "message", None)
                        try:
                            txt = extract_text(e2e) if e2e else ""
                        except Exception:
                            txt = ""
                        if not txt and e2e is not None:
                            try:
                                txt = f"<sem texto - tipo: {[f.name for f, _ in e2e.ListFields()]}>"
                            except Exception:
                                txt = "<sem texto>"
                        save({
                            "id": getattr(key, "id", "") if key else "",
                            "timestamp_ms": ts_ms,
                            "datetime": dt,
                            "chat": chat,
                            "sender": sender,
                            "pushname": getattr(wbi, "pushName", ""),
                            "is_from_me": frm,
                            "is_group": "@g.us" in str(chat),
                            "text": txt or "<sem texto>",
                            "source": "history_sync",
                        })
                    except Exception as e:
                        print(f"erro history msg: {e}", flush=True)
        except Exception as e:
            print(f"erro HistorySync: {e}", flush=True)

    @client.event(MessageEv)
    def on_message(c, msg):
        try:
            d = msg_to_dict(msg)
            save(d)
            if args.format == "text":
                print(f"MSG [{d['datetime']}] {d['pushname']} ({d['chat']}): {d['text'][:120]}", flush=True)
        except Exception as e:
            print(f"erro MessageEv: {e}", flush=True)

    print(f"Conectando (timeout {args.timeout}s, N={n})...", flush=True)
    import threading

    def run():
        try:
            client.connect()
        except Exception as e:
            print(f"Erro conexao: {e}", flush=True)

    t = threading.Thread(target=run, daemon=True)
    t.start()

    # espera com saída antecipada por quiet-period
    elapsed = 0
    while elapsed < args.timeout:
        _time.sleep(1)
        elapsed = _time.time() - start
        if args.quiet_period > 0 and collected and (_time.time() - last_msg_time[0]) >= args.quiet_period:
            # só sai cedo se já passou da metade do timeout (evita sair antes do sync)
            if elapsed >= args.timeout / 2:
                break

    # ---- pós-processamento: dedup, filtros, ordenação ----
    finalize(args, collected, n, elapsed=elapsed)

    os._exit(0)


if __name__ == "__main__":
    main()
