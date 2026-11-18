"""Montagem da base de conhecimento: regras (regras/acervo.pl) + fatos."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from motor.parser import ler_programa
from motor.sld import BaseConhecimento, Motor
from motor.termos import Clausula, Struct

from .entrada import HORAS, Entrada

RAIZ = Path(__file__).resolve().parent.parent
ARQ_REGRAS = RAIZ / "regras" / "acervo.pl"


@lru_cache(maxsize=1)
def _texto_regras() -> str:
    return ARQ_REGRAS.read_text(encoding="utf-8")


def regras() -> list[Clausula]:
    """Cópias novas das regras a cada chamada (rótulos são atribuídos na KB)."""
    return ler_programa(_texto_regras())


def nomes_regras() -> dict[str, str]:
    kb = BaseConhecimento(regras())
    return kb.nomes_regras()


def montar_kb(fatos: list[Struct]) -> BaseConhecimento:
    kb = BaseConhecimento(regras())
    for f in fatos:
        kb.adicionar(Clausula(f))
    return kb


def kb_da_entrada(e: Entrada, extras: list[Struct] = (), horas=HORAS) -> BaseConhecimento:
    """KB para um mundo: fatos certos + escolha `extras` para os incertos.
    Os extras entram logo após os fatos do mesmo predicado não importa:
    para manter a mesma ordem do Prolog, eles vão ao final."""
    return montar_kb(e.fatos(horas) + list(extras))


def motor_da_entrada(e: Entrada, extras=(), limite: int = 200) -> Motor:
    return Motor(kb_da_entrada(e, extras), limite=limite)
