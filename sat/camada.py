"""Camada proposicional (M4): as três perguntas e a verificação da política.

  CamadaSAT(entrada, horas_extras=[10, 14])
    .consistente()            -> bool  (KB ∧ restrições satisfazível?)
    .violacoes()              -> violações possíveis e forçadas
    .consequencia(atomo)      -> bool  (KB ∧ restrições ∧ ¬atomo insatisfazível?)
    .status(atomo)            -> 'sempre' | 'nunca' | 'depende' | 'inconsistente'
    .contar_modelos()         -> int
    .mundos(atomo=None)       -> lista de escolhas dos fatos incertos
    .conflitos()              -> pares de regras que permitem e negam o mesmo pedido
    .dimacs()                 -> texto DIMACS

Domínio do horário: em vez de 24 horas, usam-se representantes das
faixas em que todas as comparações H >= I, H < F têm o mesmo valor
(0 e cada fronteira de intervalo), mais as horas das perguntas.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from acervo.base import kb_da_entrada
from acervo.entrada import Entrada
from motor.termos import Struct, formatar

from .codificacao import Codificacao, nome
from .dpll import DPLL
from .formula import para_dimacs
from .grounding import aterrar


@dataclass
class Conflito:
    regra_permite: str
    regra_nega: str
    exemplos: list = field(default_factory=list)


class CamadaSAT:
    def __init__(self, e: Entrada, horas_extras=()):
        self.e = e
        self.horas = e.horas_criticas(horas_extras)
        kb = kb_da_entrada(e, horas=self.horas)
        regras = [c for c in kb.todas() if not c.eh_fato]
        certos = e.fatos(self.horas)
        incertos = [a for g in e.incertos for a in g.atomos]
        self.prog = aterrar(regras, certos, incertos)
        self.cod = Codificacao(self.prog, [g.atomos for g in e.incertos])
        self.resolvedor = DPLL(self.cod.clausulas, self.cod.nvars)
        self.violacoes_possiveis = self.prog.atomos_do_predicado("violacao")
        self._ic = [-self.cod.lit(v) for v in self.violacoes_possiveis]

    # -- perguntas básicas ------------------------------------------------
    def tamanho(self) -> dict:
        return {"variaveis": self.cod.nvars, "clausulas": len(self.cod.clausulas),
                "regras_ground": len(self.prog.regras), "horas": self.horas,
                "componentes_recursivas": len(self.cod.componentes_recursivas)}

    def consistente(self) -> bool:
        return self.resolvedor.satisfazivel(self._ic)

    def violacoes(self) -> dict:
        """{'forcadas': [...], 'possiveis': [...]}: forçada = vale em todo mundo."""
        forc, poss = [], []
        for v in self.violacoes_possiveis:
            l = self.cod.lit(v)
            if self.resolvedor.satisfazivel([l]):
                poss.append(v.args[0])
                if not self.resolvedor.satisfazivel([-l]):
                    forc.append(v.args[0])
        return {"forcadas": forc, "possiveis": poss}

    def _assume(self, atomo: Struct, valor: bool):
        l = self.cod.lit(atomo)
        if l is None:
            return None if valor else []    # None => impossível
        return [l if valor else -l]

    def satisfazivel_com(self, atomo: Struct, valor: bool, restricoes: bool = True) -> bool:
        a = self._assume(atomo, valor)
        if a is None:
            return False
        return self.resolvedor.satisfazivel((self._ic if restricoes else []) + a)

    def consequencia(self, atomo: Struct) -> bool:
        """Refutação: KB ∧ restrições ∧ ¬atomo é insatisfazível?"""
        return not self.satisfazivel_com(atomo, False)

    def status(self, atomo: Struct) -> str:
        if not self.consistente():
            return "inconsistente"
        pode_v = self.satisfazivel_com(atomo, True)
        pode_f = self.satisfazivel_com(atomo, False)
        if pode_v and not pode_f:
            return "sempre"
        if pode_f and not pode_v:
            return "nunca"
        return "depende"

    def contar_modelos(self, atomo: Struct | None = None, valor: bool = True) -> int:
        a = [] if atomo is None else self._assume(atomo, valor)
        if a is None:
            return 0
        return self.resolvedor.contar(self._ic + a)

    def mundos(self, atomo: Struct | None = None, valor: bool = True, maximo: int = 50) -> list[list[Struct]]:
        """Escolhas dos fatos incertos compatíveis (opcionalmente com atomo=valor)."""
        a = [] if atomo is None else self._assume(atomo, valor)
        if a is None:
            return []
        incertos = [x for g in self.e.incertos for x in g.atomos]
        ids = [self.cod.voc.id(nome(x)) for x in incertos]
        out = []
        for m in self.resolvedor.enumerar(ids, maximo, self._ic + a):
            out.append([x for x, i in zip(incertos, ids) if m[i]])
        return out

    def dimacs(self) -> str:
        com = [f"Guardiões do acervo — {self.e.origem or 'entrada'}",
               f"horas representativas: {self.horas}"]
        com += [f"{i} {self.cod.voc.nome(i)}" for i in range(1, self.cod.nvars + 1)]
        return para_dimacs(self.cod.clausulas, self.cod.nvars, com)

    # -- bônus: verificação da política -----------------------------------
    def faixa(self, h: int) -> str:
        hs = self.horas
        i = hs.index(h)
        fim = (hs[i + 1] - 1) if i + 1 < len(hs) else 23
        return f"{h}h" if fim == h else f"{h}h–{fim}h"

    def conflitos(self) -> list[Conflito]:
        """Pares (regra que permite, regra que nega) que valem juntos para o
        mesmo (pessoa, ação, recurso, hora) em algum modelo."""
        pares: dict = {}
        for perm in self.prog.atomos_do_predicado("permitido"):
            proib = Struct("proibido", perm.args)
            lp, ln = self.cod.lit(perm), self.cod.lit(proib)
            if ln is None:
                continue
            m = self.resolvedor.resolver([lp, ln])
            if m is None:
                continue
            verdade = lambda a: (self.cod.lit(a) is not None) and m[self.cod.lit(a)]
            ativo = lambda r: all(verdade(b) for b in r.pos) and not any(verdade(b) for b in r.neg)
            rp = [r for r in self.prog.regras_de(perm) if ativo(r)]
            rn = [r for r in self.prog.regras_de(proib) if ativo(r)]
            for a in rp:
                for b in rn:
                    k = (a.nome or a.rotulo, b.nome or b.rotulo)
                    c = pares.setdefault(k, Conflito(*k))
                    p, ac, rec, h = perm.args
                    c.exemplos.append(f"{formatar(p)}, {formatar(ac)}, {formatar(rec)}, {self.faixa(h)}")
        return list(pares.values())

    def papeis_incompativeis(self) -> list:
        return [v for v in self.violacoes()["possiveis"] if isinstance(v, Struct) and v.nome == "papeis_incompativeis"]
