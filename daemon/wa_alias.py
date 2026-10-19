#!/usr/bin/env python3
"""Aliases de destinatários — mantém telefone/JID fora da skill, em arquivo local.

Uso (agente):
    1. ANTES de enviar, verifique se o alvo já existe:  wa_alias.py get <nome>
    2. Se ainda não existir, persista:                  wa_alias.py set <nome> <jid>
    3. Envie usando o NOME, nunca o JID:
           wa_enqueue.py "contato" --text "oi"     (o script expande sozinho)

Arquivo: /root/whatsapp/aliases.json  ({ "contato": "5511999999999@s.whatsapp.net", ... })
NUNCA versione este arquivo (está no .gitignore).
"""
import json
import os
import sys

ALIASES_PATH = "/root/whatsapp/aliases.json"


def load_aliases():
    if not os.path.exists(ALIASES_PATH):
        return {}
    try:
        with open(ALIASES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_aliases(data):
    tmp = ALIASES_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, ALIASES_PATH)
    os.chmod(ALIASES_PATH, 0o600)


def _norm(key):
    return str(key or "").strip().lower()


def is_concrete(target):
    """True se o alvo já é JID/número (não precisa de alias)."""
    t = str(target or "").strip()
    if "@" in t:
        return True
    return t.replace("-", "").isdigit() and len(t) >= 6


def resolve_alias(target):
    """Expande um nome de alias para o JID. Retorna o próprio alvo se não for alias."""
    t = str(target or "").strip()
    if not t or is_concrete(t):
        return t
    aliases = load_aliases()
    return aliases.get(_norm(t), t)


def remember_alias(name, jid):
    """Persiste o par (nome, jid). Não sobrescreve alias existente."""
    aliases = load_aliases()
    key = _norm(name)
    if not key or "@" not in str(jid):
        return False
    if key in aliases:
        return False
    aliases[key] = str(jid).strip()
    save_aliases(aliases)
    return True


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    cmd = args[0]
    if cmd == "get" and len(args) > 1:
        print(resolve_alias(args[1]))
    elif cmd == "set" and len(args) > 2:
        ok = remember_alias(args[1], args[2])
        print(f"salvo: {args[1]}" if ok else f"ja existia ou jid invalido: {args[1]}")
        if not ok:
            sys.exit(1)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
