#!/usr/bin/env python3
"""Daemon persistente: conecta UMA vez e grava tudo no SQLite. Consultas ficam instantâneas.

Uso:
    nohup /root/whatsapp/.venv/bin/python -u /root/whatsapp/daemon/wa_daemon.py > /tmp/opencode/wa_daemon.log 2>&1 &
    /root/whatsapp/.venv/bin/python -u /root/whatsapp/daemon/wa_daemon.py --migrate-once
    /root/whatsapp/.venv/bin/python -u /root/whatsapp/daemon/wa_daemon.py --migrate-and-run
"""
import glob
import json
import os
import sqlite3
import sys
import threading
import time

sys.path.insert(0, "/root/whatsapp/daemon")
from wa_store import DB_PATH, NAMES_PATH, SCHEMA, OUTBOX_SCHEMA, get_conn, normalize_ts, upsert

from neonize.client import NewClient
from neonize.events import (
    ConnectedEv,
    HistorySyncEv,
    MessageEv,
    OfflineSyncCompletedEv,
    OfflineSyncPreviewEv,
)
from neonize.utils import extract_text

SESSION = os.environ.get("WA_SESSION", "/root/whatsapp/whatsapp_session.db")
PID_FILE = "/tmp/opencode/wa_daemon.pid"
MEDIA_DIR = os.environ.get("WA_MEDIA_DIR", "/root/projetos/downloads/wa_inbox")

MEDIA_SCHEMA = """
CREATE TABLE IF NOT EXISTS media (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    mimetype TEXT
);
"""

MEDIA_FIELDS = ("audioMessage", "documentMessage", "imageMessage", "videoMessage", "stickerMessage")

# Fontes locais para migração total (JSONL = 1 JSON por linha, JSON = lista).
MIGRATION_SOURCES = [
    "/tmp/opencode/recent_messages.jsonl",
    "/tmp/opencode/recent30.jsonl",
    "/tmp/opencode/recent100.jsonl",
    "/tmp/opencode/merged30.json",
]


def _iter_records_from_file(path):
    """Gera dicts de mensagem de um arquivo .jsonl ou .json. Ignora linhas inválidas."""
    if path.endswith(".jsonl"):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if isinstance(d, dict):
                    yield d
    elif path.endswith(".json"):
        with open(path) as f:
            data = json.load(f)
        items = data.get("messages") if isinstance(data, dict) and "messages" in data else data
        if isinstance(items, list):
            for d in items:
                if isinstance(d, dict):
                    yield d
        elif isinstance(items, dict):
            yield items


def migrate_all(conn=None, sources=None):
    """Migra ABSOLUTAMENTE todas as mensagens locais para o SQLite via upsert.

    - Lê `sources` + glob de /tmp/opencode/*.jsonl e *.json.
    - Aceita chaves `timestamp` ou `timestamp_ms`; normalização via wa_store.upsert.
    - Prefere texto real sobre ruído (<sem texto...>), deduplica por id.
    - Retorna dict com stats: {files, read, applied, skipped}.
    Pode ser chamada sem daemon rodando (abre/fecha conn própria) ou com conn existente.
    """
    if sources is None:
        sources = list(MIGRATION_SOURCES)
        for pat in ("/tmp/opencode/*.jsonl", "/tmp/opencode/*.json"):
            for p in glob.glob(pat):
                if p not in sources:
                    sources.append(p)
    own_conn = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.executescript(SCHEMA)
        own_conn = True
    stats = {"files": 0, "read": 0, "applied": 0, "skipped": 0}
    for path in sources:
        if not os.path.isfile(path):
            continue
        try:
            n_file = 0
            for d in _iter_records_from_file(path):
                stats["read"] += 1
                n_file += 1
                # garante timestamp_ms a partir de timestamp quando necessário
                if "timestamp_ms" not in d and "timestamp" in d:
                    d["timestamp_ms"] = d["timestamp"]
                try:
                    if upsert(conn, d):
                        stats["applied"] += 1
                    else:
                        stats["skipped"] += 1
                except Exception:
                    stats["skipped"] += 1
            conn.commit()
            stats["files"] += 1
            print(f"MIGRATE: {path}: {n_file} lidos", flush=True)
        except Exception as e:
            print(f"MIGRATE erro em {path}: {e}", flush=True)
    if own_conn:
        conn.commit()
        conn.close()
    print(
        f"MIGRATE TOTAL: {stats['files']} arquivos, {stats['read']} lidos, "
        f"{stats['applied']} aplicados, {stats['skipped']} ignorados",
        flush=True,
    )
    return stats


def fmt_jid(j):
    try:
        u = getattr(j, "User", "")
        s = getattr(j, "Server", "")
        return f"{u}@{s}" if u else str(j)
    except Exception:
        return str(j)


def main():
    # modo utilitário: só migra e sai (sem conectar, sem derrubar daemon rodando)
    if "--migrate-once" in sys.argv:
        migrate_all()
        return

    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    # conn thread-safe: eventos neonize rodam em threads separadas
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.executescript(SCHEMA)
    conn.executescript(MEDIA_SCHEMA)
    conn.executescript(OUTBOX_SCHEMA)
    os.makedirs(MEDIA_DIR, exist_ok=True)
    lock = threading.Lock()
    saved = [0]

    def save(d):
        with lock:
            if upsert(conn, d):
                saved[0] += 1
                # commit barato a cada msg para consulta instantânea ver dado fresco
                conn.commit()

    # migração total no boot: garante que tudo que já temos está no SQLite
    try:
        with lock:
            migrate_all(conn)
    except Exception as e:
        print(f"aviso migrate no boot: {e}", flush=True)

    client = NewClient(SESSION)

    def _outbox_recipient(target):
        from neonize.utils.jid import build_jid
        target = (target or "").strip()
        if "@" in target:
            user, server = target.split("@", 1)
            return build_jid(user, server=server)
        if "-" in target or (target.startswith("120363") and len(target) >= 16):
            return build_jid(target, server="g.us")
        return build_jid(target)

    def _outbox_consumer():
        import mimetypes
        video_ext = {".mp4", ".mov", ".3gp", ".mkv", ".webm"}
        audio_ext = {".mp3", ".ogg", ".opus", ".m4a", ".wav", ".aac", ".flac"}
        image_ext = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
        while True:
            try:
                time.sleep(5)
                try:
                    connected = client.is_connected()
                except Exception:
                    connected = True
                if not connected:
                    continue
                with lock:
                    row = conn.execute(
                        "SELECT id, target, kind, text, file, caption, ptt, attempts FROM outbox "
                        "WHERE status='pending' AND attempts < 5 ORDER BY id LIMIT 1"
                    ).fetchone()
                    if not row:
                        continue
                    oid = row[0]
                    conn.execute(
                        "UPDATE outbox SET status='sending', attempts=attempts+1 WHERE id=?", (oid,)
                    )
                    conn.commit()
                _, target, kind, text, path, caption, ptt, _ = row
                try:
                    recipient = _outbox_recipient(target)
                    if kind == "media" and path and os.path.isfile(path):
                        ext = os.path.splitext(path)[1].lower()
                        if ext in video_ext and not ptt:
                            client.send_video(recipient, path, caption=caption or None)
                        elif ext in audio_ext:
                            client.send_audio(recipient, path, ptt=bool(ptt))
                            if caption:
                                client.send_message(recipient, caption)
                        elif ext in image_ext:
                            client.send_image(recipient, path, caption=caption or None)
                        else:
                            mime, _ = mimetypes.guess_type(path)
                            client.send_document(
                                recipient, path, caption=caption or None,
                                filename=os.path.basename(path), mimetype=mime,
                            )
                    else:
                        client.send_message(recipient, text or "")
                    with lock:
                        conn.execute("UPDATE outbox SET status='done', error='' WHERE id=?", (oid,))
                        conn.commit()
                    print(f"OUTBOX #{oid} enviado para {target}", flush=True)
                except Exception as e:
                    with lock:
                        conn.execute("UPDATE outbox SET status='pending', error=? WHERE id=?", (str(e)[:300], oid))
                        conn.commit()
                    print(f"OUTBOX #{oid} falhou (retry): {e}", flush=True)
            except Exception as e:
                print(f"erro outbox loop: {e}", flush=True)

    threading.Thread(target=_outbox_consumer, daemon=True).start()

    @client.event(ConnectedEv)
    def on_connected(c, ev):
        print("DAEMON CONECTADO - cache ativo", flush=True)
        # atualiza mapa de nomes (grupos precisam de conexão; contatos vêm do sqlite)
        try:
            groups = {}
            for g in c.get_joined_groups():
                try:
                    jid = getattr(g, "JID", None)
                    name = getattr(g, "Name", "") or getattr(getattr(g, "GroupName", None), "Name", "")
                    if not name:
                        name = str(getattr(g, "GroupName", ""))
                    if jid:
                        ju = getattr(jid, "User", "")
                        js = getattr(jid, "Server", "g.us")
                        if ju:
                            groups[f"{ju}@{js}"] = str(name) if name else f"{ju}@{js}"
                except Exception:
                    continue
            contacts = {}
            try:
                scon = sqlite3.connect(SESSION)
                cur = scon.cursor()
                cur.execute("SELECT their_jid, full_name, push_name, first_name FROM whatsmeow_contacts")
                for jid, full, push, first in cur.fetchall():
                    contacts[str(jid)] = full or push or first or str(jid)
                scon.close()
            except Exception as e:
                print(f"aviso nomes contatos: {e}", flush=True)
            with open(NAMES_PATH, "w") as f:
                json.dump({"contacts": contacts, "groups": groups}, f, ensure_ascii=False)
            print(f"nomes atualizados: {len(contacts)} contatos, {len(groups)} grupos", flush=True)
        except Exception as e:
            print(f"erro atualizando nomes: {e}", flush=True)

    @client.event(OfflineSyncPreviewEv)
    def on_preview(c, ev):
        print(f"OFFLINE PREVIEW: total={ev.Total}", flush=True)

    @client.event(OfflineSyncCompletedEv)
    def on_completed(c, ev):
        print(f"OFFLINE SYNC: count={ev.Count} salvos={saved[0]}", flush=True)

    @client.event(HistorySyncEv)
    def on_history(c, ev):
        n = 0
        try:
            for conv in getattr(ev.Data, "conversations", []):
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
                        n += 1
                    except Exception:
                        continue
        except Exception as e:
            print(f"erro HistorySync: {e}", flush=True)
        print(f"HISTORY SYNC: {n} msgs (total salvos={saved[0]})", flush=True)

    @client.event(MessageEv)
    def on_message(c, msg):
        try:
            info = msg.Info
            src = info.MessageSource
            msg_id = getattr(info, "ID", "")
            ts_ms, dt = normalize_ts(int(getattr(info, "Timestamp", 0)))
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
            # download de mídia recebida (áudio/doc/imagem/vídeo/sticker)
            try:
                fields = [f.name for f, _ in msg.Message.ListFields()]
                media_field = next((f for f in fields if f in MEDIA_FIELDS), None)
                if media_field and msg_id:
                    sub = getattr(msg.Message, media_field, None)
                    orig = str(getattr(sub, "fileName", "") or getattr(sub, "FileName", "") or "")
                    mime = str(getattr(sub, "mimetype", "") or getattr(sub, "Mimetype", "") or "")
                    ext = ""
                    if "." in orig:
                        ext = "." + orig.rsplit(".", 1)[-1][:8]
                    elif "/" in mime:
                        ext = "." + mime.split("/", 1)[-1].split(";")[0][:8]
                    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in (orig or media_field))[:60]
                    dest = os.path.join(MEDIA_DIR, f"{msg_id}_{safe}{ext}")
                    if not os.path.isfile(dest):
                        c.download_any(msg.Message, dest)
                    with lock:
                        conn.execute(
                            "INSERT OR REPLACE INTO media (id, path, mimetype) VALUES (?,?,?)",
                            (msg_id, dest, mime),
                        )
                        conn.commit()
                    text = f"{text} [arquivo: {dest}]"
                    print(f"MIDIA salva: {dest}", flush=True)
            except Exception as e:
                print(f"aviso midia {msg_id}: {e}", flush=True)
            save({
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
            })
        except Exception as e:
            print(f"erro MessageEv: {e}", flush=True)

    # loop com reconnect: connect() bloqueia; se cair, espera e reconecta
    while True:
        try:
            print("conectando...", flush=True)
            client.connect()
        except Exception as e:
            print(f"conexão caiu: {e} - retry em 10s", flush=True)
        time.sleep(10)


if __name__ == "__main__":
    main()
