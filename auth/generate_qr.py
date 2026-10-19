import time
import os
import segno
from neonize.client import NewClient

client = NewClient("/root/whatsapp/whatsapp_session.db")

qr_saved = False

@client.event.qr
def qr_handler(client: NewClient, qr_data: bytes):
    global qr_saved
    print("QR Code recebido!")
    qr_str = qr_data.decode("utf-8", errors="ignore")
    qrcode = segno.make(qr_str)
    qrcode.save("/root/whatsapp/whatsapp_qr.png", scale=5)
    print("QR Code salvo em /root/whatsapp/whatsapp_qr.png")
    qr_saved = True
    time.sleep(0.5)
    os._exit(0)

if __name__ == "__main__":
    print("Iniciando conexão para gerar o QR code...")
    import threading
    def run_client():
        try:
            client.connect()
        except Exception as e:
            print("Erro:", e)

    t = threading.Thread(target=run_client, daemon=True)
    t.start()

    # Aguarda até 20 segundos o evento de QR
    for _ in range(20):
        if qr_saved:
            break
        time.sleep(1)

    if not qr_saved:
        print("Timeout aguardando QR code.")
    os._exit(0)
