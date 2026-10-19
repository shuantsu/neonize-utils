import sys
from neonize.client import NewClient
from neonize.types import JID

def send_message(phone: str, text: str):
    client = NewClient("/root/whatsapp/whatsapp_session.db")
    # Formata o número (ex: 5511999999999)
    recipient = JID(user=phone, server="s.whatsapp.net")
    try:
        # Nota: Para apenas enviar sem manter o loop de eventos conectado indefinidamente, 
        # o neonize precisa conectar, enviar e fechar. Ou podemos usar a sessão existente.
        # Vamos rodar em modo rápido conectando.
        import threading
        import time
        
        sent = False
        def on_connect(client_instance):
            nonlocal sent
            try:
                client_instance.send_message(recipient, text)
                print(f"Mensagem enviada com sucesso para {phone}!")
                sent = True
            except Exception as e:
                print(f"Erro ao enviar: {e}")
            finally:
                client_instance.stop()

        # Registramos um callback de status de login ou apenas conectamos
        client.connect()
    except Exception as e:
        print(f"Erro de conexão: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python3 send_wa.py <numero> <mensagem>")
        print("Exemplo: python3 send_wa.py 5511999999999 'Olá do neonize'")
        sys.exit(1)
    
    phone = sys.argv[1]
    text = sys.argv[2]
    send_message(phone, text)
