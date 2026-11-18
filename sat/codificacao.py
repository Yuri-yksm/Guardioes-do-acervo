"""Codificação do programa ground em FNC.

Semântica: o programa (com negação estratificada) tem, para cada escolha
dos fatos incertos, um único modelo (o modelo perfeito / mundo fechado).
Codificamos isso com o COMPLETAMENTO DE CLARK:

    a  ↔  corpo_1 ∨ ... ∨ corpo_k        (para cada átomo derivado a)

O completamento só é exato quando não há recursão positiva entre
átomos ground. A herança (alcanca/2) é recursiva e, com hierarquia
cíclica, o completamento admitiria "laços sem suporte" (a e b se
justificando mutuamente). Para cada componente fortemente conexa S
de tamanho n usamos então a codificação em camadas do ponto fixo:

    a@0     ↔  ∨ corpos sem átomos de S
    a@k     ↔  a@(k-1) ∨ ∨ corpos com b∈S trocado por b@(k-1)   (k = 1..n)
    a       ↔  a@n

que equivale ao menor ponto fixo (n iterações bastam).

Fatos certos viram cláusulas unitárias; cada grupo incerto "um_de" vira
"pelo menos um" + "no máximo um" (pares).
"""
from __future__ import annotations

from motor.termos import Struct, formatar

from .formula import E, Nao, Ou, P, Tseitin, Vocabulario
from .grounding import ProgramaGround


def nome(a: Struct) -> str:
    return formatar(a).replace(" ", "")


def componentes(nos: list, arestas: dict) -> list[list]:
    """Tarjan (iterativo)."""
    indice, baixo, na_pilha = {}, {}, set()
    pilha, out, cont = [], [], [0]
    for raiz in nos:
        if raiz in indice:
            continue
        trabalho = [(raiz, iter(arestas.get(raiz, ())))]
        indice[raiz] = baixo[raiz] = cont[0]; cont[0] += 1
        pilha.append(raiz); na_pilha.add(raiz)
        while trabalho:
            v, it = trabalho[-1]
            avancou = False
            for w in it:
                if w not in indice:
                    indice[w] = baixo[w] = cont[0]; cont[0] += 1
                    pilha.append(w); na_pilha.add(w)
                    trabalho.append((w, iter(arestas.get(w, ()))))
                    avancou = True
                    break
                if w in na_pilha:
                    baixo[v] = min(baixo[v], indice[w])
            if avancou:
                continue
            trabalho.pop()
            if trabalho:
                u = trabalho[-1][0]
                baixo[u] = min(baixo[u], baixo[v])
            if baixo[v] == indice[v]:
                comp = []
                while True:
                    w = pilha.pop(); na_pilha.discard(w)
                    comp.append(w)
                    if w == v:
                        break
                out.append(comp)
    return out


class Codificacao:
    def __init__(self, prog: ProgramaGround, grupos_incertos: list[list[Struct]] = ()):
        self.prog = prog
        self.ts = Tseitin(Vocabulario())
        self.voc = self.ts.voc
        self.componentes_recursivas: list[list[Struct]] = []
        idb = prog.idb()
        # variáveis dos átomos de entrada e derivados primeiro (ids pequenos e estáveis)
        for a in prog.certos + prog.incertos + idb:
            self.voc.id(nome(a))

        # 1) fatos certos
        for a in prog.certos:
            self.ts.clausulas.append([self.voc.id(nome(a))])
        # 2) grupos incertos: exatamente um
        self.vars_incertas: list[int] = []
        for g in grupos_incertos:
            ids = [self.voc.id(nome(a)) for a in g]
            self.vars_incertas += ids
            self.ts.clausulas.append(list(ids))
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    self.ts.clausulas.append([-ids[i], -ids[j]])
        # 3) completamento (com camadas nas componentes recursivas)
        idb_set = set(idb)
        arestas = {a: [b for r in prog.regras_de(a) for b in r.pos if b in idb_set] for a in idb}
        for comp in componentes(idb, arestas):
            recursiva = len(comp) > 1 or comp[0] in arestas.get(comp[0], ())
            if recursiva:
                self.componentes_recursivas.append(comp)
                self._camadas(comp)
            else:
                a = comp[0]
                self.ts.definir(nome(a), Ou(*[self._corpo(r) for r in prog.regras_de(a)]))

    def _lit_neg(self, b: Struct):
        return Nao(P(nome(b))) if b in self.prog.possiveis else None

    def _corpo(self, r, troca=None):
        fs = []
        for b in r.pos:
            fs.append(P(troca(b) if troca else nome(b)))
        for b in r.neg:
            l = self._lit_neg(b)
            if l is not None:
                fs.append(l)
        return E(*fs)

    def _camadas(self, comp: list[Struct]) -> None:
        S = set(comp)
        n = len(comp)
        for a in comp:
            externos = [r for r in self.prog.regras_de(a) if not any(b in S for b in r.pos)]
            self.ts.definir(f"{nome(a)}@0", Ou(*[self._corpo(r) for r in externos]))
        for k in range(1, n + 1):
            for a in comp:
                internos = [r for r in self.prog.regras_de(a) if any(b in S for b in r.pos)]
                troca = lambda b, k=k: f"{nome(b)}@{k-1}" if b in S else nome(b)
                self.ts.definir(f"{nome(a)}@{k}",
                                Ou(P(f"{nome(a)}@{k-1}"), *[self._corpo(r, troca) for r in internos]))
        for a in comp:
            self.ts.definir(nome(a), P(f"{nome(a)}@{n}"))

    # -- acesso ------------------------------------------------------------
    @property
    def clausulas(self) -> list[list[int]]:
        return self.ts.clausulas

    @property
    def nvars(self) -> int:
        return len(self.voc)

    def lit(self, a: Struct) -> int | None:
        """Literal do átomo, ou None se o átomo é impossível (falso sempre)."""
        if a not in self.prog.possiveis:
            return None
        return self.voc.id(nome(a))
