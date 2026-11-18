"""Representação de termos, átomos e cláusulas (Caso 11).

Termo  ::= Var | Struct | int
  - Var(nome, idx): variável lógica. `idx` distingue cópias renomeadas
    de uma mesma variável de cláusula (X, X_1, X_2, ...).
  - Struct(nome, args): constante (args vazio) ou termo composto
    f(t1, ..., tn). Um átomo (fórmula atômica) é um Struct cujo nome é
    o predicado.
  - int: constante numérica (usada para horas).

Clausula(cabeca, corpo): cláusula de Horn  cabeca :- l1, ..., ln.
Literais do corpo podem ser \\+(G) (negação por falha) ou embutidos
de comparação.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Iterator, Union


@dataclass(frozen=True, repr=False)
class Var:
    nome: str
    idx: int = 0

    def __str__(self) -> str:
        return self.nome if self.idx == 0 else f"{self.nome}_{self.idx}"

    __repr__ = __str__


@dataclass(frozen=True, repr=False)
class Struct:
    nome: str
    args: tuple = ()

    @property
    def aridade(self) -> int:
        return len(self.args)

    @property
    def chave(self) -> tuple[str, int]:
        return (self.nome, len(self.args))

    def __str__(self) -> str:
        return formatar(self)

    __repr__ = __str__


Termo = Union[Var, Struct, int]


def atomo(nome: str, *args) -> Struct:
    """Atalho: atomo('papel', 'bia', 'coordenador') -> papel(bia, coordenador).
    Strings viram constantes; ints ficam ints; termos ficam como estão."""
    return Struct(nome, tuple(_conv(a) for a in args))


def _conv(a) -> Termo:
    if isinstance(a, (Var, Struct)):
        return a
    if isinstance(a, bool):
        raise TypeError("booleanos não são termos")
    if isinstance(a, int):
        return a
    if isinstance(a, str):
        return Struct(a)
    raise TypeError(f"não sei converter {a!r} em termo")


NAO = "\\+"
NIL = Struct("[]")


def lista(itens, cauda: Termo = NIL) -> Termo:
    t = cauda
    for x in reversed(list(itens)):
        t = Struct("[|]", (_conv(x), t))
    return t


def de_lista(t: Termo) -> list:
    out = []
    while isinstance(t, Struct) and t.nome == "[|]" and len(t.args) == 2:
        out.append(t.args[0])
        t = t.args[1]
    if t != NIL:
        raise ValueError("não é uma lista própria")
    return out


@dataclass
class Clausula:
    cabeca: Struct
    corpo: tuple = ()
    nome: str | None = None      # nome legível vindo de "%@ ..."
    rotulo: str = ""             # pred/aridade#n (igual ao do Prolog) ou 'fato'

    @property
    def eh_fato(self) -> bool:
        return not self.corpo

    def __str__(self) -> str:
        if not self.corpo:
            return formatar(self.cabeca) + "."
        return formatar(self.cabeca) + " :- " + ", ".join(formatar(l) for l in self.corpo) + "."


# ---------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------

def variaveis(t: Termo) -> Iterator[Var]:
    if isinstance(t, Var):
        yield t
    elif isinstance(t, Struct):
        for a in t.args:
            yield from variaveis(a)


def eh_ground(t: Termo) -> bool:
    return next(variaveis(t), None) is None


def vars_clausula(c: Clausula) -> list[Var]:
    vistos: dict[Var, None] = {}
    for t in (c.cabeca, *c.corpo):
        for v in variaveis(t):
            vistos.setdefault(v, None)
    return list(vistos)


_ATOMO_SIMPLES = re.compile(r"^[a-z][A-Za-z0-9_]*$")
_SIMBOLICO = re.compile(r"^[+\-*/\\^<>=~:.?@#&$]+$")
_INFIXOS = {"<", ">", "=<", ">=", "=:=", "=\\=", "=", "\\=", "+", "-", "*", "/", "=@=", "=="}


def formatar_atomo(nome: str) -> str:
    if _ATOMO_SIMPLES.match(nome) or _SIMBOLICO.match(nome) or nome in ("[]", "!", ";"):
        return nome
    return "'" + nome.replace("\\", "\\\\").replace("'", "\\'") + "'"


def formatar(t: Termo) -> str:
    """Formatação legível no estilo Prolog."""
    if isinstance(t, Var):
        return str(t)
    if isinstance(t, int):
        return str(t)
    if t.nome == "[|]" and len(t.args) == 2:
        itens, cauda = [], t
        while isinstance(cauda, Struct) and cauda.nome == "[|]" and len(cauda.args) == 2:
            itens.append(formatar(cauda.args[0]))
            cauda = cauda.args[1]
        s = "[" + ", ".join(itens)
        if cauda != NIL:
            s += " | " + formatar(cauda)
        return s + "]"
    if not t.args:
        return formatar_atomo(t.nome)
    if t.nome == NAO and len(t.args) == 1:
        return "\\+ " + formatar(t.args[0])
    if t.nome in _INFIXOS and len(t.args) == 2:
        return f"{formatar(t.args[0])} {t.nome} {formatar(t.args[1])}"
    return formatar_atomo(t.nome) + "(" + ", ".join(formatar(a) for a in t.args) + ")"


def canonico(t: Termo) -> str:
    """Forma canônica (sem operadores), aceita por SWI-Prolog e pelo nosso parser."""
    if isinstance(t, Var):
        return f"_{t.nome.lstrip('_')}{t.idx}"
    if isinstance(t, int):
        return str(t)
    if t.nome == "[|]" and len(t.args) == 2:
        return "'[|]'(" + canonico(t.args[0]) + "," + canonico(t.args[1]) + ")"
    if not t.args:
        return formatar_atomo(t.nome)
    return formatar_atomo(t.nome) + "(" + ",".join(canonico(a) for a in t.args) + ")"
