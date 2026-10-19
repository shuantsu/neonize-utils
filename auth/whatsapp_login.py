import time
import segno
from neonize.client import NewClient

client = NewClient("/root/whatsapp/whatsapp_session.db")

@client.event.qr
def qr_handler(client: NewClient, qr_data: bytes):
    print("QR Code recebido!")
    qr_str = qr_data.decode("utf-8", errors="ignore")
    qrcode = segno.make(qr_str)
    qrcode.save("/root/whatsapp/whatsapp_qr.png", scale=5)
    print("QR Code salvo em /root/whatsapp/whatsapp_qr.png. Escaneie no WhatsApp.")

if __name__ == "__main__":
    print("Iniciando cliente WhatsApp (mantenham-se rodando)...")
    client.connect()
