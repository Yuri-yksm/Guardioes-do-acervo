"""Fórmulas proposicionais como dados, FNC, Tseitin e DIMACS (Casos 11–14).

Fórmula ::= P(nome) | Const(bool) | Nao(f) | E(f1, ..., fn) | Ou(f1, ..., fn)
          | Imp(f, g) | Equiv(f, g)

Duas conversões para FNC:
  - fnc_distributiva(f): NNF + distribuição de ∨ sobre ∧ (equivalente,
    mas pode crescer exponencialmente; usada em fórmulas pequenas);
  - Tseitin (classe Tseitin): uma variável nova por subfórmula, tamanho
    linear e equissatisfazível — é a usada pela camada SAT.

Uma cláusula é uma lista de inteiros não nulos (literal DIMACS).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


class Formula:
    def __invert__(self):
        return Nao(self)

    def __and__(self, o):
        return E(self, o)

    def __or__(self, o):
        return Ou(self, o)


@dataclass(frozen=True)
class P(Formula):
    nome: str

    def __str__(self):
        return self.nome


@dataclass(frozen=True)
class Const(Formula):
    valor: bool

    def __str__(self):
        return "⊤" if self.valor else "⊥"


@dataclass(frozen=True)
class Nao(Formula):
    f: Formula

    def __str__(self):
        return f"¬{_par(self.f)}"


@dataclass(frozen=True, init=False)
class E(Formula):
    fs: tuple

    def __init__(self, *fs):
        object.__setattr__(self, "fs", tuple(fs))

    def __str__(self):
        return " ∧ ".join(_par(f) for f in self.fs) if self.fs else "⊤"


@dataclass(frozen=True, init=False)
class Ou(Formula):
    fs: tuple

    def __init__(self, *fs):
        object.__setattr__(self, "fs", tuple(fs))

    def __str__(self):
        return " ∨ ".join(_par(f) for f in self.fs) if self.fs else "⊥"


@dataclass(frozen=True)
class Imp(Formula):
    a: Formula
    b: Formula

    def __str__(self):
        return f"{_par(self.a)} → {_par(self.b)}"


@dataclass(frozen=True)
class Equiv(Formula):
    a: Formula
    b: Formula

    def __str__(self):
        return f"{_par(self.a)} ↔ {_par(self.b)}"


def _par(f: Formula) -> str:
    return str(f) if isinstance(f, (P, Const, Nao)) else f"({f})"


# ---------------------------------------------------------------------
# Semântica
# ---------------------------------------------------------------------

def avaliar(f: Formula, v: dict[str, bool]) -> bool:
    if isinstance(f, P):
        return v[f.nome]
    if isinstance(f, Const):
        return f.valor
    if isinstance(f, Nao):
        return not avaliar(f.f, v)
    if isinstance(f, E):
        return all(avaliar(g, v) for g in f.fs)
    if isinstance(f, Ou):
        return any(avaliar(g, v) for g in f.fs)
    if isinstance(f, Imp):
        return (not avaliar(f.a, v)) or avaliar(f.b, v)
    if isinstance(f, Equiv):
        return avaliar(f.a, v) == avaliar(f.b, v)
    raise TypeError(f)


def atomos(f: Formula) -> set[str]:
    if isinstance(f, P):
        return {f.nome}
    if isinstance(f, Const):
        return set()
    if isinstance(f, Nao):
        return atomos(f.f)
    if isinstance(f, (E, Ou)):
        return set().union(*[atomos(g) for g in f.fs]) if f.fs else set()
    return atomos(f.a) | atomos(f.b)


# ---------------------------------------------------------------------
# NNF e FNC por distribuição (Caso 12)
# ---------------------------------------------------------------------

def sem_implicacoes(f: Formula) -> Formula:
    if isinstance(f, (P, Const)):
        return f
    if isinstance(f, Nao):
        return Nao(sem_implicacoes(f.f))
    if isinstance(f, E):
        return E(*[sem_implicacoes(g) for g in f.fs])
    if isinstance(f, Ou):
        return Ou(*[sem_implicacoes(g) for g in f.fs])
    if isinstance(f, Imp):
        return Ou(Nao(sem_implicacoes(f.a)), sem_implicacoes(f.b))
    a, b = sem_implicacoes(f.a), sem_implicacoes(f.b)
    return E(Ou(Nao(a), b), Ou(a, Nao(b)))


def nnf(f: Formula) -> Formula:
    f = sem_implicacoes(f)

    def go(g: Formula, neg: bool) -> Formula:
        if isinstance(g, P):
            return Nao(g) if neg else g
        if isinstance(g, Const):
            return Const(g.valor != neg)
        if isinstance(g, Nao):
            return go(g.f, not neg)
        if isinstance(g, E):
            fs = [go(h, neg) for h in g.fs]
            return Ou(*fs) if neg else E(*fs)
        if isinstance(g, Ou):
            fs = [go(h, neg) for h in g.fs]
            return E(*fs) if neg else Ou(*fs)
        raise TypeError(g)

    return go(f, False)


def fnc_distributiva(f: Formula) -> list[list[tuple[str, bool]]]:
    """FNC equivalente como lista de cláusulas de literais (nome, polaridade)."""
    def go(g: Formula) -> list[frozenset]:
        if isinstance(g, P):
            return [frozenset({(g.nome, True)})]
        if isinstance(g, Nao):
            return [frozenset({(g.f.nome, False)})]
        if isinstance(g, Const):
            return [] if g.valor else [frozenset()]
        if isinstance(g, E):
            out = []
            for h in g.fs:
                out += go(h)
            return out
        if isinstance(g, Ou):
            acc = [frozenset()]
            for h in g.fs:
                acc = [a | b for a in acc for b in go(h)]
            return acc
        raise TypeError(g)

    out = []
    for c in go(nnf(f)):
        nomes = {n for n, _ in c}
        if any((n, True) in c and (n, False) in c for n in nomes):
            continue  # tautologia
        if c not in out:
            out.append(c)
    return [sorted(c) for c in out]


# ---------------------------------------------------------------------
# Vocabulário e Tseitin (Caso 13)
# ---------------------------------------------------------------------

class Vocabulario:
    """Mapeia nomes de variáveis proposicionais em inteiros 1..n."""

    def __init__(self):
        self.ids: dict[str, int] = {}
        self.nomes: list[str] = [""]

    def id(self, nome: str) -> int:
        i = self.ids.get(nome)
        if i is None:
            i = len(self.nomes)
            self.ids[nome] = i
            self.nomes.append(nome)
        return i

    def novo_aux(self, prefixo: str = "τ") -> int:
        return self.id(f"{prefixo}{len(self.nomes)}")

    def __len__(self):
        return len(self.nomes) - 1

    def nome(self, i: int) -> str:
        return self.nomes[abs(i)]

    def lit_str(self, l: int) -> str:
        return ("¬" if l < 0 else "") + self.nome(l)


class Tseitin:
    """Transforma fórmulas em cláusulas acrescentando variáveis auxiliares.

    `literal(f)` devolve um literal equivalente a f (sob as cláusulas
    geradas); `afirmar(f)` acrescenta f como restrição."""

    def __init__(self, voc: Vocabulario | None = None):
        self.voc = voc or Vocabulario()
        self.clausulas: list[list[int]] = []
        self._cache: dict[Formula, int] = {}
        self._verdade: int | None = None

    def _top(self) -> int:
        if self._verdade is None:
            self._verdade = self.voc.id("⊤")
            self.clausulas.append([self._verdade])
        return self._verdade

    def literal(self, f: Formula) -> int:
        if isinstance(f, P):
            return self.voc.id(f.nome)
        if isinstance(f, Const):
            return self._top() if f.valor else -self._top()
        if isinstance(f, Nao):
            return -self.literal(f.f)
        if f in self._cache:
            return self._cache[f]
        if isinstance(f, (Imp, Equiv)):
            x = self.literal(sem_implicacoes(f))
            self._cache[f] = x
            return x
        filhos = [self.literal(g) for g in f.fs]
        if not filhos:
            return self._top() if isinstance(f, E) else -self._top()
        if len(filhos) == 1:
            return filhos[0]
        x = self.voc.novo_aux()
        if isinstance(f, E):
            # x ↔ (l1 ∧ ... ∧ ln)
            for l in filhos:
                self.clausulas.append([-x, l])
            self.clausulas.append([x] + [-l for l in filhos])
        else:
            # x ↔ (l1 ∨ ... ∨ ln)
            for l in filhos:
                self.clausulas.append([x, -l])
            self.clausulas.append([-x] + filhos)
        self._cache[f] = x
        return x

    def afirmar(self, f: Formula) -> None:
        if isinstance(f, E):
            for g in f.fs:
                self.afirmar(g)
        elif isinstance(f, Ou) and all(isinstance(g, (P, Nao)) and (not isinstance(g, Nao) or isinstance(g.f, P)) for g in f.fs):
            self.clausulas.append([self.literal(g) for g in f.fs])
        else:
            self.clausulas.append([self.literal(f)])

    def definir(self, nome: str, f: Formula) -> None:
        """nome ↔ f  (usado no completamento de Clark)."""
        a = self.voc.id(nome)
        x = self.literal(f)
        self.clausulas.append([-a, x])
        self.clausulas.append([a, -x])


# ---------------------------------------------------------------------
# DIMACS (Caso 14)
# ---------------------------------------------------------------------

def para_dimacs(clausulas: Iterable[list[int]], nvars: int, comentarios: Iterable[str] = ()) -> str:
    cl = list(clausulas)
    linhas = [f"c {c}" for c in comentarios]
    linhas.append(f"p cnf {nvars} {len(cl)}")
    linhas += [" ".join(map(str, c)) + " 0" for c in cl]
    return "\n".join(linhas) + "\n"


def ler_dimacs(texto: str) -> tuple[int, list[list[int]]]:
    nvars, cl, atual = 0, [], []
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("c") or linha.startswith("%"):
            continue
        if linha.startswith("p"):
            nvars = int(linha.split()[2])
            continue
        for x in map(int, linha.split()):
            if x == 0:
                cl.append(atual)
                atual = []
            else:
                atual.append(x)
    if atual:
        cl.append(atual)
    return nvars, cl
