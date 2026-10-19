import time
import segno
from neonize.client import NewClient
from neonize.events import ConnectedEv

client = NewClient("/root/whatsapp/whatsapp_session.db")

@client.event.qr
def qr_handler(client: NewClient, qr_data: bytes):
    print("QR Code recebido!")
    qr_str = qr_data.decode("utf-8", errors="ignore")
    qrcode = segno.make(qr_str)
    qrcode.save("/root/whatsapp/whatsapp_qr.png", scale=5)
    print("QR Code salvo em /root/whatsapp/whatsapp_qr.png")

@client.event(ConnectedEv)
def connected_handler(client: NewClient, event: ConnectedEv):
    print("WhatsApp conectado com sucesso!")

if __name__ == "__main__":
    print("Iniciando cliente WhatsApp...")
    client.connect()
