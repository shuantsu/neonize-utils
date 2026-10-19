# neonize-utils

Scripts utilitários para WhatsApp via [`neonize`](https://pypi.org/project/neonize/) — autenticação com QR code, daemon de mensagens, envio de mídia e listagem de conversas.

## Estrutura

| Pasta | Papel | Scripts |
|---|---|---|
| `auth/` | Login e geração do QR code | `generate_qr.py`, `whatsapp_login.py`, `start_whatsapp.py` |
| `daemon/` | Processo em background | `wa_daemon.py`, `wa_store.py`, `wa_received.py`, `wa_recent.py`, `wa_enqueue.py` |
| `envio/` | Envio de mensagens e mídia | `send_media.py`, `send_video.py`, `send_whatsapp.py`, `send_wa.py` |
| `listagem/` | Consulta de conversas e contatos | `list_recent_messages.py`, `list_contacts_groups.py`, `list_chats.py`, `list_whatsapp.py` |

## Instalação

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Dependências: `neonize==0.5.2`, `segno==1.6.6`.

## Sessão

Todos os scripts instanciam o cliente sobre a **mesma** DB de sessão:

```python
NewClient("/root/whatsapp/whatsapp_session.db")
```

Por isso **apenas um processo neonize pode rodar por vez** — se o daemon estiver ativo, os scripts de `envio/` e `listagem/` falham ao abrir a conexão.

O arquivo `whatsapp_session.db` é a sessão autenticada da conta e está no `.gitignore`. Ele é gerado no primeiro login.

## Gerar o QR code

```bash
python3 auth/generate_qr.py
# -> /root/whatsapp/whatsapp_qr.png
```

Fluxo:

1. `neonize` conecta e, durante o pareamento, dispara o evento `qr` com os **bytes crus** da payload (não uma imagem).
2. O handler decodifica para `str` e passa para `segno.make()`.
3. `segno.save(path, scale=5)` grava o PNG — `scale=5` faz cada módulo do QR valer 5×5 px, o que o torna escaneável.

Escaneie o PNG no WhatsApp do telefone para concluir o vínculo. Depois que a sessão é autenticada, o evento `qr` não dispara mais — apague a DB para forçar um novo pareamento.

## Envio

```bash
python3 envio/send_wa.py 5511999999999 "mensagem"
python3 envio/send_whatsapp.py <id_do_grupo>@g.us "mensagem no grupo"
python3 envio/send_media.py <destino> <arquivo> [legenda] [--ptt]
python3 envio/send_video.py <destino> <arquivo> [legenda]
```

Destinatários podem ser passados por **alias** (nome definido em `aliases.json`,
gitignorado) — os scripts expandem para o JID sozinhos:

## Listagem

```bash
python3 listagem/list_chats.py
python3 listagem/list_contacts_groups.py
python3 listagem/list_whatsapp.py
python3 listagem/list_recent_messages.py [--chat <substring>]
```

## Licença

Uso pessoal.
