"""Send any media via WhatsApp (neonize). Usage: send_media.py <target> <file> [caption] [--ptt]"""
import mimetypes
import os
import sys
import threading

from neonize.client import NewClient
from neonize.utils.jid import build_jid
from neonize.events import ConnectedEv

sys.path.insert(0, "/root/whatsapp/daemon")
from wa_alias import resolve_alias  # noqa: E402

SESSION = "/root/whatsapp/whatsapp_session.db"
VIDEO_EXT = {".mp4", ".mov", ".3gp", ".mkv", ".webm"}
AUDIO_EXT = {".mp3", ".ogg", ".opus", ".m4a", ".wav", ".aac", ".flac"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def get_recipient(target: str):
    target = resolve_alias(target).strip()
    if "@" in target:
        user, server = target.split("@", 1)
        return build_jid(user, server=server)
    if "-" in target or (target.startswith("120363") and len(target) >= 16):
        return build_jid(target, server="g.us")
    return build_jid(target)


def main():
    args = [a for a in sys.argv[1:] if a != "--ptt"]
    ptt = "--ptt" in sys.argv
    if len(args) < 2:
        print("Uso: send_media.py <numero_ou_jid> <arquivo> [legenda] [--ptt]")
        sys.exit(1)
    target, path = args[0], args[1]
    caption = args[2] if len(args) > 2 else None
    if not os.path.isfile(path):
        print(f"Arquivo nao encontrado: {path}")
        sys.exit(1)
    ext = os.path.splitext(path)[1].lower()
    client = NewClient(SESSION)
    recipient = get_recipient(target)
    done = threading.Event()

    def do_send(c):
        if ext in VIDEO_EXT and not ptt:
            return c.send_video(recipient, path, caption=caption)
        if ext in AUDIO_EXT:
            # caption nao suportado em audio; envia audio + texto separado se houver legenda
            r = c.send_audio(recipient, path, ptt=ptt)
            if caption:
                c.send_message(recipient, caption)
            return r
        if ext in IMAGE_EXT:
            return c.send_image(recipient, path, caption=caption)
        mime, _ = mimetypes.guess_type(path)
        return c.send_document(
            recipient, path, caption=caption,
            filename=os.path.basename(path), mimetype=mime,
        )

    @client.event(ConnectedEv)
    def on_connected(client_inst, event):
        print("Conectado ao WhatsApp! Enviando midia...")
        try:
            do_send(client_inst)
            print(f"Midia enviada com sucesso para {target}!")
        except Exception as e:
            print(f"Erro ao enviar midia: {e}")
        finally:
            done.set()
            os._exit(0)

    def run():
        try:
            client.connect()
        except Exception as e:
            print(f"Erro na conexao: {e}")
            done.set()

    threading.Thread(target=run, daemon=True).start()
    done.wait(timeout=110)
    print("Processo finalizado.")
    os._exit(0)


if __name__ == "__main__":
    main()
