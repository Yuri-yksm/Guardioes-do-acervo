"""Leitor de um subconjunto de Prolog.

Aceita:
  - cláusulas  `H.`  e  `H :- L1, ..., Ln.`; diretivas `:- ...` são ignoradas;
  - comentários `% ...` e `/* ... */`; um comentário `%@ texto` dá nome
    à cláusula seguinte;
  - variáveis, átomos (simples, entre aspas ou simbólicos), inteiros,
    termos compostos, listas `[a, b | T]`;
  - operadores: :- (1200), , (1000), \\+ (900, prefixo),
    = \\= < > =< >= =:= =\\= == \\== =@= (700), + - (500), * / (400),
    e também a forma canônica `>=(H, I)` / `\\+(G)` produzida por
    write_canonical/1 do SWI-Prolog.
"""
from __future__ import annotations

import itertools
import re
from dataclasses import dataclass

from .termos import NIL, Clausula, Struct, Termo, Var

INFIXOS = {
    ":-": (1200, "xfx"),
    ",": (1000, "xfy"),
    "=": (700, "xfx"), "\\=": (700, "xfx"), "<": (700, "xfx"), ">": (700, "xfx"),
    "=<": (700, "xfx"), ">=": (700, "xfx"), "=:=": (700, "xfx"), "=\\=": (700, "xfx"),
    "==": (700, "xfx"), "\\==": (700, "xfx"), "=@=": (700, "xfx"),
    "+": (500, "yfx"), "-": (500, "yfx"),
    "*": (400, "yfx"), "/": (400, "yfx"),
}
PREFIXOS = {":-": (1200, "fx"), "\\+": (900, "fy"), "-": (200, "fy"),
            "dynamic": (1150, "fx"), "discontiguous": (1150, "fx"), "table": (1150, "fx")}

SIMB = set("+-*/\\^<>=~:.?@#&$")


class ErroSintaxe(Exception):
    pass


@dataclass
class Tok:
    tipo: str      # num, var, atom, qatom, punct, end, eof
    valor: str
    pos: int
    colado: bool   # sem espaço antes (para distinguir f( de f ()
    nota: str | None = None   # anotação %@ que precede o token


_RE_NUM = re.compile(r"\d+")
_RE_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def tokenizar(texto: str) -> list[Tok]:
    toks: list[Tok] = []
    i, n = 0, len(texto)
    espaco = True
    nota: str | None = None
    while i < n:
        c = texto[i]
        if c.isspace():
            i += 1
            espaco = True
            continue
        if c == "%":
            fim = texto.find("\n", i)
            fim = n if fim < 0 else fim
            linha = texto[i:fim]
            if linha.startswith("%@"):
                nota = linha[2:].strip()
            i = fim
            espaco = True
            continue
        if texto.startswith("/*", i):
            fim = texto.find("*/", i + 2)
            if fim < 0:
                raise ErroSintaxe("comentário /* sem fechamento")
            i = fim + 2
            espaco = True
            continue
        ini = i
        if c.isdigit():
            m = _RE_NUM.match(texto, i)
            toks.append(Tok("num", m.group(), ini, not espaco, nota))
            i = m.end()
        elif c.isalpha() or c == "_":
            m = _RE_ID.match(texto, i)
            v = m.group()
            tipo = "var" if (v[0].isupper() or v[0] == "_") else "atom"
            toks.append(Tok(tipo, v, ini, not espaco, nota))
            i = m.end()
        elif c == "'":
            j, buf = i + 1, []
            while True:
                if j >= n:
                    raise ErroSintaxe("átomo entre aspas sem fechamento")
                if texto[j] == "\\" and j + 1 < n:
                    buf.append(texto[j + 1]); j += 2; continue
                if texto[j] == "'":
                    if j + 1 < n and texto[j + 1] == "'":
                        buf.append("'"); j += 2; continue
                    break
                buf.append(texto[j]); j += 1
            toks.append(Tok("qatom", "".join(buf), ini, not espaco, nota))
            i = j + 1
        elif c in "()[],|":
            toks.append(Tok("punct", c, ini, not espaco, nota))
            i += 1
        elif c == "!" or c == ";":
            toks.append(Tok("atom", c, ini, not espaco, nota))
            i += 1
        elif c in SIMB:
            # ponto final: '.' seguido de espaço, '%' ou fim
            if c == "." and (i + 1 >= n or texto[i + 1].isspace() or texto[i + 1] == "%"):
                toks.append(Tok("end", ".", ini, not espaco, nota))
                nota = None
                i += 1
                espaco = True
                continue
            j = i
            while j < n and texto[j] in SIMB:
                j += 1
            toks.append(Tok("atom", texto[i:j], ini, not espaco, nota))
            i = j
        else:
            raise ErroSintaxe(f"caractere inesperado {c!r} na posição {i}")
        espaco = False
    toks.append(Tok("eof", "", n, False, None))
    return toks


class _Parser:
    def __init__(self, texto: str):
        self.toks = tokenizar(texto)
        self.i = 0
        self.vars: dict[str, Var] = {}
        self._anon = itertools.count(1)

    # -- utilidades
    def peek(self) -> Tok:
        return self.toks[self.i]

    def next(self) -> Tok:
        t = self.toks[self.i]
        self.i += 1
        return t

    def esperar(self, tipo: str, valor: str | None = None) -> Tok:
        t = self.next()
        if t.tipo != tipo or (valor is not None and t.valor != valor):
            raise ErroSintaxe(f"esperava {valor or tipo}, encontrei {t.valor!r} (posição {t.pos})")
        return t

    def _eh_inicio_termo(self, t: Tok) -> bool:
        if t.tipo in ("num", "var", "qatom"):
            return True
        if t.tipo == "atom":
            return t.valor not in INFIXOS or t.valor in PREFIXOS
        return t.tipo == "punct" and t.valor in "(["

    # -- termos
    def termo(self, maxp: int = 1200) -> Termo:
        esq, pesq = self.primario(maxp)
        while True:
            t = self.peek()
            op = t.valor if (t.tipo == "atom" or (t.tipo == "punct" and t.valor == ",")) else None
            if op not in INFIXOS:
                break
            p, tipo = INFIXOS[op]
            if p > maxp:
                break
            limite_esq = p if tipo == "yfx" else p - 1
            if pesq > limite_esq:
                break
            self.next()
            dir_max = p if tipo == "xfy" else p - 1
            dir_ = self.termo(dir_max)
            esq, pesq = Struct(op, (esq, dir_)), p
        return esq

    def argumentos(self) -> tuple:
        args = [self.termo(999)]
        while self.peek().tipo == "punct" and self.peek().valor == ",":
            self.next()
            args.append(self.termo(999))
        self.esperar("punct", ")")
        return tuple(args)

    def primario(self, maxp: int) -> tuple[Termo, int]:
        t = self.next()
        if t.tipo == "num":
            return int(t.valor), 0
        if t.tipo == "var":
            if t.valor == "_":
                return Var(f"_G{next(self._anon)}"), 0
            return self.vars.setdefault(t.valor, Var(t.valor)), 0
        if t.tipo == "punct" and t.valor == "(":
            x = self.termo(1200)
            self.esperar("punct", ")")
            return x, 0
        if t.tipo == "punct" and t.valor == "[":
            if self.peek().tipo == "punct" and self.peek().valor == "]":
                self.next()
                return self._depois_atomo("[]", maxp)
            itens = [self.termo(999)]
            while self.peek().tipo == "punct" and self.peek().valor == ",":
                self.next()
                itens.append(self.termo(999))
            cauda: Termo = NIL
            if self.peek().tipo == "punct" and self.peek().valor == "|":
                self.next()
                cauda = self.termo(999)
            self.esperar("punct", "]")
            for x in reversed(itens):
                cauda = Struct("[|]", (x, cauda))
            return cauda, 0
        if t.tipo in ("atom", "qatom"):
            nome = t.valor
            prox = self.peek()
            if prox.tipo == "punct" and prox.valor == "(" and prox.colado:
                self.next()
                return Struct(nome, self.argumentos()), 0
            if t.tipo == "atom" and nome in PREFIXOS:
                p, tipo = PREFIXOS[nome]
                # número negativo
                if nome == "-" and prox.tipo == "num" and prox.colado:
                    self.next()
                    return -int(prox.valor), 0
                if self._eh_inicio_termo(prox) and not (prox.tipo == "atom" and prox.valor in INFIXOS and prox.valor not in PREFIXOS):
                    if p > maxp:
                        p = 999
                    argmax = p if tipo == "fy" else p - 1
                    arg = self.termo(argmax)
                    return Struct(nome, (arg,)), p
            return self._depois_atomo(nome, maxp)
        raise ErroSintaxe(f"token inesperado {t.valor!r} (posição {t.pos})")

    def _depois_atomo(self, nome: str, maxp: int) -> tuple[Termo, int]:
        p = INFIXOS.get(nome, (0,))[0]
        return Struct(nome), (p if p <= maxp else 0)

    # -- programa
    def programa(self) -> list[tuple[Termo, str | None]]:
        out = []
        while self.peek().tipo != "eof":
            nota = self.peek().nota
            self.vars = {}
            t = self.termo(1200)
            self.esperar("end")
            out.append((t, nota))
        return out


def ler_termo(texto: str) -> Termo:
    """Lê um único termo (o ponto final é opcional)."""
    texto = texto.strip()
    if not texto.endswith("."):
        texto += " ."
    p = _Parser(texto)
    t = p.termo(1200)
    p.esperar("end")
    if p.peek().tipo != "eof":
        raise ErroSintaxe("texto extra depois do termo")
    return t


def ler_termos(texto: str) -> list[Termo]:
    return [t for t, _ in _Parser(texto).programa()]


def achatar_conj(t: Termo) -> list[Termo]:
    if isinstance(t, Struct) and t.nome == "," and len(t.args) == 2:
        return achatar_conj(t.args[0]) + achatar_conj(t.args[1])
    if t == Struct("true"):
        return []
    return [t]


def termo_para_clausula(t: Termo, nota: str | None = None) -> Clausula | None:
    """None para diretivas (:- ...)."""
    if isinstance(t, Struct) and t.nome == ":-" and len(t.args) == 1:
        return None
    if isinstance(t, Struct) and t.nome == ":-" and len(t.args) == 2:
        cab, corpo = t.args
        lits = achatar_conj(corpo)
    else:
        cab, lits = t, []
    if not isinstance(cab, Struct):
        raise ErroSintaxe(f"cabeça inválida: {cab}")
    for l in lits:
        if not isinstance(l, Struct):
            raise ErroSintaxe(f"literal inválido no corpo: {l}")
    return Clausula(cab, tuple(lits), nome=nota)


def ler_programa(texto: str) -> list[Clausula]:
    out = []
    for t, nota in _Parser(texto).programa():
        c = termo_para_clausula(t, nota)
        if c is not None:
            out.append(c)
    return out
