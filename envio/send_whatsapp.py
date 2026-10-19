import sys
import os
import threading
from neonize.client import NewClient
from neonize.utils.jid import build_jid
from neonize.events import ConnectedEv

sys.path.insert(0, "/root/whatsapp/daemon")
from wa_alias import resolve_alias  # noqa: E402

def get_recipient(target: str):
    target = resolve_alias(target).strip()
    if "@" in target:
        user, server = target.split("@", 1)
        return build_jid(user, server=server)
    # Grupos sem o @g.us explícito (identificados por padrão de grupo: contém hífen ou 18 dígitos)
    if "-" in target or (target.startswith("120363") and len(target) >= 16):
        return build_jid(target, server="g.us")
    return build_jid(target)

def send_message(target: str, text: str):
    client = NewClient("/root/whatsapp/whatsapp_session.db")
    recipient = get_recipient(target)
    
    connected_event = threading.Event()

    @client.event(ConnectedEv)
    def on_connected(client_inst, event):
        print("Conectado ao WhatsApp! Enviando mensagem...")
        try:
            client_inst.send_message(recipient, text)
            print(f"Mensagem enviada com sucesso para {target}!")
        except Exception as e:
            print(f"Erro ao enviar mensagem: {e}")
        finally:
            connected_event.set()
            os._exit(0)

    def run_client():
        try:
            client.connect()
        except Exception as e:
            print(f"Erro na conexão: {e}")
            connected_event.set()

    t = threading.Thread(target=run_client, daemon=True)
    t.start()

    connected_event.wait(timeout=25)
    print("Processo finalizado.")
    os._exit(0)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python3 send_whatsapp.py <numero_ou_jid_ou_alias> <mensagem>")
        print("Exemplo: python3 send_whatsapp.py <id_do_grupo>@g.us 'Olá grupo'")
        print("Alias: nomes definidos em /root/whatsapp/aliases.json são expandidos automaticamente.")
        sys.exit(1)
    
    target = sys.argv[1]
    text = sys.argv[2]
    send_message(target, text)
