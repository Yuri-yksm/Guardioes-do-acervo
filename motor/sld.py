"""Resolução SLD (encadeamento para trás) sobre cláusulas de Horn.

Estratégia idêntica à do Prolog e à do meta-interpretador prolog/meta.pl:
  - regra de seleção: literal mais à esquerda;
  - busca em profundidade, cláusulas na ordem do programa;
  - renomeação de variáveis a cada uso de cláusula;
  - unificação com verificação de ocorrência;
  - limite de profundidade (comprimento do ramo de ancestrais);
  - detecção de laços: um objetivo que é variante de um ancestral seu
    no mesmo ramo é descartado (o ramo falha);
  - negação por falha: \\+ G só é avaliado se G for ground (sem
    variáveis livres); caso contrário, ErroFloundering. A prova de G
    é feita numa busca separada; \\+ G vale se essa busca falha
    finitamente (hipótese do mundo fechado).

Cada passo de resolução fica registrado numa lista encadeada imutável
(`Passo`), o que permite reconstruir tanto a derivação linear
(resolventes + unificadores) quanto a árvore de prova.
"""
from __future__ import annotations

import itertools
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterator

from .termos import NAO, Clausula, Struct, Termo, Var, eh_ground, formatar, vars_clausula
from .unificacao import Subst, aplicar, restringir, unificar, variante

sys.setrecursionlimit(max(sys.getrecursionlimit(), 50000))

COMPARACOES = {"<", ">", "=<", ">=", "=:=", "=\\="}
EMBUTIDOS = {(op, 2) for op in COMPARACOES} | {("=", 2), ("\\=", 2)}


class ErroFloundering(Exception):
    """Negação por falha aplicada a objetivo com variáveis livres."""

    def __init__(self, objetivo: Termo):
        super().__init__(f"negação por falha com variáveis livres: \\+ {formatar(objetivo)}")
        self.objetivo = objetivo


class ErroInstanciacao(Exception):
    pass


class BaseConhecimento:
    def __init__(self, clausulas=()):
        self.por_pred: dict[tuple[str, int], list[Clausula]] = defaultdict(list)
        for c in clausulas:
            self.adicionar(c)

    def adicionar(self, c: Clausula) -> Clausula:
        lst = self.por_pred[c.cabeca.chave]
        n = len(lst) + 1
        c.rotulo = "fato" if c.eh_fato else f"{c.cabeca.nome}/{c.cabeca.aridade}#{n}"
        lst.append(c)
        return c

    def clausulas(self, chave) -> list[Clausula]:
        return self.por_pred.get(chave, [])

    def nomes_regras(self) -> dict[str, str]:
        return {c.rotulo: (c.nome or c.rotulo) for cs in self.por_pred.values() for c in cs if not c.eh_fato}

    def todas(self):
        for cs in self.por_pred.values():
            yield from cs


# ---------------------------------------------------------------------
# Registro de passos e árvore de prova
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class Passo:
    no: int                      # id do nó (objetivo) resolvido neste passo
    literal: Struct              # literal selecionado (sem aplicar subst)
    rotulo: str                  # 'fato' | 'pred/n#k' | 'builtin' | 'naf'
    filhos: tuple                # ids dos subobjetivos introduzidos
    clausula: Clausula | None    # cláusula renomeada usada
    antes: Subst
    depois: Subst
    resolvente: tuple            # frames restantes após o passo
    anterior: "Passo | None"


@dataclass
class NoProva:
    objetivo: Termo
    rotulo: str
    filhos: list["NoProva"] = field(default_factory=list)
    ligacoes: dict = field(default_factory=dict)   # variáveis da cláusula -> valores (nome original)
    nome: str | None = None

    def para_termo(self) -> Termo:
        """Mesmo formato do meta-interpretador: no(Objetivo, Rotulo, [Filhos])."""
        from .termos import lista
        return Struct("no", (self.objetivo, Struct(self.rotulo), lista([f.para_termo() for f in self.filhos])))

    def percorrer(self):
        yield self
        for f in self.filhos:
            yield from f.percorrer()


@dataclass
class Solucao:
    subst: Subst
    passos: list[Passo]           # em ordem cronológica
    raizes: list[int]
    objetivos: list[Struct]

    def resposta(self, t: Termo) -> Termo:
        return aplicar(t, self.subst)

    def arvores(self) -> list[NoProva]:
        por_no = {p.no: p for p in self.passos}

        def montar(i: int, lit: Struct) -> NoProva:
            p = por_no[i]
            no = NoProva(aplicar(p.literal, self.subst), p.rotulo)
            if p.clausula is not None:
                no.nome = p.clausula.nome
                no.ligacoes = {
                    str(Var(v.nome)): aplicar(v, self.subst)
                    for v in vars_clausula(p.clausula)
                    if not v.nome.startswith("_")
                }
                for cid, lit_f in zip(p.filhos, p.clausula.corpo):
                    no.filhos.append(montar(cid, lit_f))
            return no

        return [montar(r, o) for r, o in zip(self.raizes, self.objetivos)]


# ---------------------------------------------------------------------
# Motor
# ---------------------------------------------------------------------

class Motor:
    def __init__(self, kb: BaseConhecimento, limite: int = 200, verificar_ocorrencia: bool = True):
        self.kb = kb
        self.limite = limite
        self.oc = verificar_ocorrencia
        self._ids = itertools.count()
        self._ren = itertools.count(1)
        self.limite_atingido = False
        self.lacos: list[Termo] = []
        self.passos_executados = 0

    # -- API ---------------------------------------------------------
    def resolver(self, objetivos) -> Iterator[Solucao]:
        if isinstance(objetivos, Struct):
            objetivos = [objetivos]
        objetivos = list(objetivos)
        raizes = [next(self._ids) for _ in objetivos]
        frames = tuple((o, (), r) for o, r in zip(objetivos, raizes))
        for s, log in self._sld(frames, {}, None):
            passos = []
            while log is not None:
                passos.append(log)
                log = log.anterior
            passos.reverse()
            yield Solucao(s, passos, raizes, objetivos)

    def provar(self, objetivo) -> Solucao | None:
        return next(self.resolver(objetivo), None)

    def respostas(self, objetivo: Struct) -> list[Termo]:
        """Instâncias distintas do objetivo, na ordem em que aparecem."""
        vistos, out = set(), []
        for sol in self.resolver(objetivo):
            r = sol.resposta(objetivo)
            if r not in vistos:
                vistos.add(r)
                out.append(r)
        return out

    # -- núcleo --------------------------------------------------------
    def _renomear(self, c: Clausula) -> Clausula:
        k = next(self._ren)
        ren = {v: Var(v.nome, k) for v in vars_clausula(c)}
        return Clausula(aplicar(c.cabeca, ren), tuple(aplicar(l, ren) for l in c.corpo), c.nome, c.rotulo)

    def _sld(self, resolvente: tuple, s: Subst, log: Passo | None):
        if not resolvente:
            yield s, log
            return
        lit, anc, no = resolvente[0]
        resto = resolvente[1:]
        chave = lit.chave
        self.passos_executados += 1

        # negação por falha
        if chave == (NAO, 1):
            g = aplicar(lit.args[0], s)
            if not eh_ground(g):
                raise ErroFloundering(g)
            if self._tem_prova(g):
                return
            yield from self._sld(resto, s, Passo(no, lit, "naf", (), None, s, s, resto, log))
            return

        # embutidos
        if chave in EMBUTIDOS:
            s2 = self._embutido(lit, s)
            if s2 is None:
                return
            yield from self._sld(resto, s2, Passo(no, lit, "builtin", (), None, s, s2, resto, log))
            return

        # limite de profundidade
        if len(anc) >= self.limite:
            self.limite_atingido = True
            return
        # detecção de laços (variante de ancestral)
        atual = aplicar(lit, s)
        for a in anc:
            if variante(atual, aplicar(a, s)):
                self.lacos.append(atual)
                return

        novos_anc = anc + (lit,)
        for c in self.kb.clausulas(chave):
            r = self._renomear(c)
            s2 = unificar(r.cabeca, lit, s, self.oc)
            if s2 is None:
                continue
            ids = tuple(next(self._ids) for _ in r.corpo)
            novos = tuple((b, novos_anc, i) for b, i in zip(r.corpo, ids))
            nr = novos + resto
            yield from self._sld(nr, s2, Passo(no, lit, c.rotulo, ids, r, s, s2, nr, log))

    def _tem_prova(self, g: Struct) -> bool:
        frames = ((g, (), next(self._ids)),)
        for _ in self._sld(frames, {}, None):
            return True
        return False

    def _embutido(self, lit: Struct, s: Subst) -> Subst | None:
        op = lit.nome
        a, b = lit.args
        if op == "=":
            return unificar(a, b, s, self.oc)
        if op == "\\=":
            return s if unificar(a, b, s, self.oc) is None else None
        x, y = avaliar(a, s), avaliar(b, s)
        ok = {"<": x < y, ">": x > y, "=<": x <= y, ">=": x >= y, "=:=": x == y, "=\\=": x != y}[op]
        return s if ok else None


def avaliar(t: Termo, s: Subst) -> int:
    t = aplicar(t, s)
    if isinstance(t, int):
        return t
    if isinstance(t, Var):
        raise ErroInstanciacao(f"variável livre em expressão aritmética: {t}")
    if isinstance(t, Struct) and len(t.args) == 2 and t.nome in "+-*":
        x, y = avaliar(t.args[0], s), avaliar(t.args[1], s)
        return {"+": x + y, "-": x - y, "*": x * y}[t.nome]
    raise ErroInstanciacao(f"expressão aritmética inválida: {formatar(t)}")


# ---------------------------------------------------------------------
# Derivação linear (para M1 / explicação passo a passo)
# ---------------------------------------------------------------------

def derivacao(sol: Solucao, incluir_fatos: bool = True) -> list[dict]:
    """Lista de passos: resolvente antes, literal selecionado, cláusula
    (renomeada), unificador do passo e resolvente depois."""
    out = []
    atual = [aplicar(o, {}) for o in sol.objetivos]
    for p in sol.passos:
        antes = [aplicar(l, p.antes) for l in atual]
        mgu_passo = {}
        if p.clausula is not None:
            vs = set()
            from .termos import variaveis
            for t in (p.literal, p.clausula.cabeca):
                vs |= set(variaveis(aplicar(t, p.antes)))
            for t in p.clausula.corpo:
                vs |= set(variaveis(t))
            mgu_passo = restringir(p.depois, sorted(vs, key=str))
        elif p.rotulo == "builtin":
            from .termos import variaveis
            mgu_passo = restringir(p.depois, list(variaveis(aplicar(p.literal, p.antes))))
        atual = [f[0] for f in p.resolvente]
        out.append({
            "resolvente": antes,
            "selecionado": aplicar(p.literal, p.antes),
            "rotulo": p.rotulo,
            "clausula": p.clausula,
            "mgu": mgu_passo,
            "novo": [aplicar(l, p.depois) for l in atual],
        })
    return out
