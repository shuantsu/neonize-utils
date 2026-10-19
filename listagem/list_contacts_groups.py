import sqlite3
import os
import sys
import threading
from neonize.client import NewClient
from neonize.events import ConnectedEv

def main():
    search_term = sys.argv[1].lower() if len(sys.argv) > 1 else ""

    print("=" * 60)
    print(f"CONTATOS SALVOS (Banco Local) {f'[Filtro: {search_term}]' if search_term else ''}")
    print("=" * 60)
    try:
        conn = sqlite3.connect('/root/whatsapp/whatsapp_session.db')
        cursor = conn.cursor()
        cursor.execute("SELECT their_jid, full_name, push_name, first_name FROM whatsmeow_contacts")
        rows = cursor.fetchall()
        count = 0
        for row in rows:
            jid, full_name, push_name, first_name = row
            name = full_name or push_name or first_name or "Desconhecido"
            phone = jid.split('@')[0] if '@' in jid else jid
            
            if search_term and search_term not in name.lower() and search_term not in phone:
                continue
                
            print(f"👤 {name} | JID/Número: {phone} ({jid})")
            count += 1
        print(f"\nTotal exibido: {count} contatos")
        conn.close()
    except Exception as e:
        print(f"Erro ao ler contatos: {e}")

    print("\n" + "=" * 60)
    print("GRUPOS DO WHATSAPP")
    print("=" * 60)

    client = NewClient("/root/whatsapp/whatsapp_session.db")
    done_event = threading.Event()

    @client.event(ConnectedEv)
    def on_connected(client_inst, event):
        try:
            groups = client_inst.get_joined_groups()
            g_count = 0
            for g in groups:
                group_name = getattr(g, 'GroupName', 'Sem Nome')
                group_jid = getattr(g, 'JID', None)
                if search_term and search_term not in group_name.lower():
                    continue
                print(f"👥 Grupo: {group_name} | JID: {group_jid}")
                g_count += 1
            print(f"\nTotal de grupos exibidos: {g_count}")
        except Exception as e:
            print(f"Erro ao listar grupos: {e}")
        finally:
            done_event.set()
            os._exit(0)

    def run_client():
        try:
            client.connect()
        except:
            done_event.set()
            os._exit(0)

    t = threading.Thread(target=run_client, daemon=True)
    t.start()

    done_event.wait(timeout=12)
    os._exit(0)

if __name__ == "__main__":
    main()
