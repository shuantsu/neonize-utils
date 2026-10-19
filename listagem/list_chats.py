import os
import sys
import threading
from neonize.client import NewClient
from neonize.events import ConnectedEv

def list_chats(search_query: str = ""):
    client = NewClient("/root/whatsapp/whatsapp_session.db")

    @client.event(ConnectedEv)
    def on_connected(client_inst, event):
        query = search_query.lower()
        
        print("================== GRUPOS ==================")
        try:
            groups = client_inst.get_joined_groups()
            for g in groups:
                name = getattr(g.GroupName, 'Name', 'Sem Nome') if hasattr(g, 'GroupName') else 'Sem Nome'
                jid_str = f"{g.User}@g.us"
                if not query or query in name.lower():
                    print(f"[GRUPO] Nome: {name} | JID: {jid_str}")
        except Exception as e:
            print(f"Erro ao listar grupos: {e}")

        print("\n================== CONTATOS ==================")
        try:
            contacts = client_inst.contact.get_all_contacts()
            if isinstance(contacts, dict):
                for jid, contact in contacts.items():
                    full_name = getattr(contact.Info, 'FullName', '') if hasattr(contact, 'Info') else ''
                    push_name = getattr(contact.Info, 'PushName', '') if hasattr(contact, 'Info') else ''
                    first_name = getattr(contact.Info, 'FirstName', '') if hasattr(contact, 'Info') else ''
                    phone = getattr(contact.Info, 'RedactedPhone', '') if hasattr(contact, 'Info') else ''
                    
                    display_name = full_name or push_name or first_name or "Desconhecido"
                    jid_user = getattr(jid, 'User', str(jid))
                    jid_server = getattr(jid, 'Server', 's.whatsapp.net')
                    full_jid = f"{jid_user}@{jid_server}"
                    
                    if not query or query in display_name.lower() or query in jid_user:
                        print(f"[CONTATO] Nome: {display_name} | JID/Telefone: {jid_user} | Servidor: {jid_server}")
        except Exception as e:
            print(f"Erro ao listar contatos: {e}")

        os._exit(0)

    try:
        client.connect()
    except Exception as e:
        print(f"Erro na conexão: {e}")
        os._exit(1)

if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else ""
    list_chats(query)
