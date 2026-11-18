"""DPLL próprio: propagação unitária + retrocesso cronológico.

  r = DPLL(clausulas, nvars)
  r.resolver(assumpcoes=[...]) -> dict var->bool (modelo) ou None
  r.contar(assumpcoes=[...])   -> número exato de modelos sobre as variáveis 1..nvars
  r.enumerar(projecao, maximo) -> modelos distintos restritos às variáveis da projeção

A propagação usa listas de ocorrência: ao tornar um literal l verdadeiro,
só as cláusulas que contêm ¬l são reexaminadas.
"""
from __future__ import annotations

from collections import defaultdict


class DPLL:
    def __init__(self, clausulas, nvars: int | None = None):
        cl = []
        self.vazia = False
        for c in clausulas:
            c = list(dict.fromkeys(c))
            if any(-l in c for l in c):
                continue  # tautologia
            if not c:
                self.vazia = True
            cl.append(c)
        self.clausulas = cl
        self.n = nvars if nvars is not None else max((abs(l) for c in cl for l in c), default=0)
        self.ocorr: dict[int, list[int]] = defaultdict(list)
        for i, c in enumerate(cl):
            for l in c:
                self.ocorr[l].append(i)
        self.unitarias = [c[0] for c in cl if len(c) == 1]
        self.val: dict[int, bool] = {}
        self.trilha: list[int] = []
        self.estat = {"decisoes": 0, "propagacoes": 0, "conflitos": 0}

    # -- utilidades ----------------------------------------------------
    def _v(self, l: int):
        x = self.val.get(abs(l))
        return None if x is None else (x if l > 0 else not x)

    def _atribuir(self, l: int) -> None:
        self.val[abs(l)] = l > 0
        self.trilha.append(abs(l))

    def _desfazer(self, marca: int) -> None:
        while len(self.trilha) > marca:
            del self.val[self.trilha.pop()]

    def _propagar(self, fila: list[int]) -> bool:
        while fila:
            l = fila.pop()
            for ci in self.ocorr.get(-l, ()):
                livre, n_livres, sat = 0, 0, False
                for m in self.clausulas[ci]:
                    v = self._v(m)
                    if v is True:
                        sat = True
                        break
                    if v is None:
                        n_livres += 1
                        livre = m
                        if n_livres > 1:
                            break
                if sat or n_livres > 1:
                    continue
                if n_livres == 0:
                    self.estat["conflitos"] += 1
                    return False
                self._atribuir(livre)
                self.estat["propagacoes"] += 1
                fila.append(livre)
        return True

    def _clausula_aberta(self):
        for c in self.clausulas:
            if not any(self._v(l) is True for l in c):
                return c
        return None

    def _iniciar(self, assumpcoes) -> bool:
        self.val.clear()
        self.trilha.clear()
        if self.vazia:
            return False
        for l in list(self.unitarias) + list(assumpcoes):
            v = self._v(l)
            if v is False:
                return False
            if v is None:
                self._atribuir(l)
                if not self._propagar([l]):
                    return False
        return True

    # -- DPLL ------------------------------------------------------------
    def _dpll(self) -> bool:
        c = self._clausula_aberta()
        if c is None:
            return True
        l = next(m for m in c if self._v(m) is None)
        self.estat["decisoes"] += 1
        for lit in (l, -l):
            marca = len(self.trilha)
            self._atribuir(lit)
            if self._propagar([lit]) and self._dpll():
                return True
            self._desfazer(marca)
        return False

    def resolver(self, assumpcoes=()) -> dict[int, bool] | None:
        if not self._iniciar(assumpcoes):
            return None
        if not self._dpll():
            return None
        modelo = {v: self.val.get(v, False) for v in range(1, self.n + 1)}
        return modelo

    def satisfazivel(self, assumpcoes=()) -> bool:
        return self.resolver(assumpcoes) is not None

    # -- contagem de modelos (#DPLL) -----------------------------------
    def _contar(self) -> int:
        c = self._clausula_aberta()
        if c is None:
            livres = self.n - sum(1 for v in self.val if v <= self.n)
            return 2 ** livres
        l = next(m for m in c if self._v(m) is None)
        total = 0
        for lit in (l, -l):
            marca = len(self.trilha)
            self._atribuir(lit)
            if self._propagar([lit]):
                total += self._contar()
            self._desfazer(marca)
        return total

    def contar(self, assumpcoes=()) -> int:
        if not self._iniciar(assumpcoes):
            return 0
        return self._contar()

    # -- enumeração projetada ------------------------------------------
    def enumerar(self, projecao, maximo: int = 1000, assumpcoes=()) -> list[dict[int, bool]]:
        projecao = list(projecao)
        extra: list[list[int]] = []
        out = []
        while len(out) < maximo:
            r = DPLL(self.clausulas + extra, self.n)
            m = r.resolver(assumpcoes)
            if m is None:
                break
            parcial = {v: m[v] for v in projecao}
            out.append(parcial)
            if not projecao:
                break
            extra.append([-v if b else v for v, b in parcial.items()])
        return out
