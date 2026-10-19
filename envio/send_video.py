"""Send video via WhatsApp (neonize). Usage: send_video.py <target> <file> [caption]"""
import os
import sys
import threading

from neonize.client import NewClient
from neonize.utils.jid import build_jid
from neonize.events import ConnectedEv

sys.path.insert(0, "/root/whatsapp/daemon")
from wa_alias import resolve_alias  # noqa: E402

SESSION = "/root/whatsapp/whatsapp_session.db"


def get_recipient(target: str):
    target = resolve_alias(target).strip()
    if "@" in target:
        user, server = target.split("@", 1)
        return build_jid(user, server=server)
    if "-" in target or (target.startswith("120363") and len(target) >= 16):
        return build_jid(target, server="g.us")
    return build_jid(target)


def main():
    if len(sys.argv) < 3:
        print("Uso: send_video.py <numero_ou_jid> <arquivo.mp4> [legenda]")
        sys.exit(1)
    target, path = sys.argv[1], sys.argv[2]
    caption = sys.argv[3] if len(sys.argv) > 3 else None
    if not os.path.isfile(path):
        print(f"Arquivo nao encontrado: {path}")
        sys.exit(1)
    client = NewClient(SESSION)
    recipient = get_recipient(target)
    done = threading.Event()

    @client.event(ConnectedEv)
    def on_connected(client_inst, event):
        print("Conectado ao WhatsApp! Enviando video...")
        try:
            client_inst.send_video(recipient, path, caption=caption)
            print(f"Video enviado com sucesso para {target}!")
        except Exception as e:
            print(f"Erro ao enviar video: {e}")
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
