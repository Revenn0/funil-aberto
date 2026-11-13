"""Pix copia-e-cola (BR Code estático, padrão EMV do Banco Central) sem gateway e sem dependência.

Por que existe: o vendedor recebe Pix direto na própria chave, sem pagar taxa de checkout.
O código é determinístico: mesma entrada, mesma saída, e o CRC16 é conferido por teste
contra o exemplo do manual do BR Code (tests/test_pix.py).
"""
from __future__ import annotations

import re
import unicodedata


def _campo(id_: str, valor: str) -> str:
    if len(valor) > 99:
        raise ValueError(f"campo {id_} passa de 99 caracteres")
    return f"{id_}{len(valor):02d}{valor}"


def crc16(dados: str) -> str:
    """CRC16-CCITT-FALSE (polinômio 0x1021, início 0xFFFF), o que o BR Code exige."""
    crc = 0xFFFF
    for byte in dados.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"


def _ascii(texto: str, limite: int) -> str:
    # Banco recusa acento em nome e cidade em vários apps: normaliza para ASCII.
    sem = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem.strip()[:limite]


def copia_e_cola(chave: str, nome: str, cidade: str, valor: float | None = None,
                 txid: str = "***", descricao: str = "") -> str:
    if not chave:
        raise ValueError("chave Pix vazia")
    conta = _campo("00", "br.gov.bcb.pix") + _campo("01", chave)
    if descricao:
        conta += _campo("02", _ascii(descricao, 40))
    if txid != "***":
        txid = re.sub(r"[^A-Za-z0-9]", "", txid)[:25] or "***"
    corpo = (
        _campo("00", "01")
        + _campo("26", conta)
        + _campo("52", "0000")
        + _campo("53", "986")
        + (_campo("54", f"{valor:.2f}") if valor else "")
        + _campo("58", "BR")
        + _campo("59", _ascii(nome, 25))
        + _campo("60", _ascii(cidade, 15))
        + _campo("62", _campo("05", txid))
        + "6304"
    )
    return corpo + crc16(corpo)
