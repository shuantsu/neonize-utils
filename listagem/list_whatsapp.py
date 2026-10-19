import os
import threading
from neonize.client import NewClient
from neonize.events import ConnectedEv

def list_whatsapp():
    client = NewClient("/root/whatsapp/whatsapp_session.db")

    @client.event(ConnectedEv)
    def on_connected(client_inst, event):
        print("=== GRUPOS PARTICIPANDO ===")
        try:
            groups = client_inst.get_joined_groups()
            for g in groups:
                print(f"Grupo JID: {g.JID} | Nome: {getattr(g, 'Name', 'N/A')}")
        except Exception as e:
            print(f"Erro ao listar grupos: {e}")

        print("\n=== CONTATOS ===")
        try:
            contacts = client_inst.contact.get_all_contacts()
            if isinstance(contacts, dict):
                for jid, contact in contacts.items():
                    print(f"JID: {jid} | Contato: {contact}")
            else:
                for c in contacts:
                    print(f"Contato: {c}")
        except Exception as e:
            print(f"Erro ao listar contatos: {e}")

        os._exit(0)

    try:
        client.connect()
    except Exception as e:
        print(f"Erro na conexão: {e}")
        os._exit(1)

if __name__ == "__main__":
    list_whatsapp()
