"""Grounding: instancia as regras (as MESMAS de regras/acervo.pl) para o
domínio finito da entrada.

Algoritmo (de baixo para cima, como num grounder de ASP):
  1. Os átomos "possíveis" começam com os fatos certos e os incertos.
  2. Para cada regra, juntam-se os literais positivos (não embutidos) com
     os átomos possíveis já conhecidos; comparações são avaliadas assim
     que ficam ground; literais negativos ficam guardados (devem ser
     ground — regra segura).
  3. A cabeça de cada instância vira um átomo possível. Repete-se até o
     ponto fixo.

Resultado: lista de regras ground  cabeca <- pos ∧ ¬neg  e o conjunto
de átomos possíveis. Átomos fora desse conjunto são falsos em todo
modelo (hipótese do mundo fechado), então ¬a com a impossível é
simplesmente verdadeiro.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from motor.sld import COMPARACOES, EMBUTIDOS, avaliar
from motor.termos import NAO, Clausula, Struct, eh_ground, formatar
from motor.unificacao import aplicar, unificar


class ErroGrounding(Exception):
    pass


@dataclass(frozen=True)
class RegraGround:
    cabeca: Struct
    pos: tuple
    neg: tuple
    rotulo: str
    nome: str | None

    def __str__(self) -> str:
        corpo = [formatar(a) for a in self.pos] + ["¬" + formatar(a) for a in self.neg]
        return f"{formatar(self.cabeca)} ← " + (" ∧ ".join(corpo) if corpo else "⊤")


@dataclass
class ProgramaGround:
    regras: list[RegraGround]
    possiveis: set
    certos: list[Struct]
    incertos: list[Struct]

    def regras_de(self, a: Struct) -> list[RegraGround]:
        return self._por_cabeca.get(a, [])

    def __post_init__(self):
        d = defaultdict(list)
        for r in self.regras:
            d[r.cabeca].append(r)
        self._por_cabeca = dict(d)

    def idb(self) -> list[Struct]:
        return list(self._por_cabeca)

    def atomos_do_predicado(self, nome: str) -> list[Struct]:
        return [a for a in self._por_cabeca if a.nome == nome]


def aterrar(regras: list[Clausula], certos: list[Struct], incertos: list[Struct] = ()) -> ProgramaGround:
    regras = [r for r in regras if not r.eh_fato]
    possiveis: set = set(certos) | set(incertos)
    indice: dict = defaultdict(list)
    for a in list(dict.fromkeys(list(certos) + list(incertos))):
        indice[a.chave].append(a)

    produzidas: dict = {}
    mudou = True
    while mudou:
        mudou = False
        for r in regras:
            for s in _juncoes(r, indice):
                cab = aplicar(r.cabeca, s)
                if not eh_ground(cab):
                    raise ErroGrounding(f"regra insegura (cabeça não ground): {r}")
                pos, neg = [], []
                for l in r.corpo:
                    if l.chave == (NAO, 1):
                        g = aplicar(l.args[0], s)
                        if not eh_ground(g):
                            raise ErroGrounding(f"regra insegura (negação não ground): {r}")
                        neg.append(g)
                    elif l.chave not in EMBUTIDOS:
                        pos.append(aplicar(l, s))
                rg = RegraGround(cab, tuple(pos), tuple(neg), r.rotulo, r.nome)
                if rg not in produzidas:
                    produzidas[rg] = None
                    if cab not in possiveis:
                        possiveis.add(cab)
                        indice[cab.chave].append(cab)
                        mudou = True
    return ProgramaGround(list(produzidas), possiveis, list(certos), list(incertos))


def _juncoes(r: Clausula, indice):
    positivos = [l for l in r.corpo if l.chave != (NAO, 1) and l.chave not in EMBUTIDOS]
    embutidos = [l for l in r.corpo if l.chave in EMBUTIDOS]

    def filtrar(s, pendentes):
        """avalia os embutidos já ground; devolve (s', pendentes') ou None"""
        resto = []
        for b in pendentes:
            if b.nome == "=":
                s2 = unificar(b.args[0], b.args[1], s)
                if s2 is None:
                    return None
                s = s2
                continue
            g = aplicar(b, s)
            if not eh_ground(g):
                resto.append(b)
                continue
            if b.nome == "\\=":
                if unificar(g.args[0], g.args[1], {}) is not None:
                    return None
                continue
            x, y = avaliar(g.args[0], {}), avaliar(g.args[1], {})
            ok = {"<": x < y, ">": x > y, "=<": x <= y, ">=": x >= y, "=:=": x == y, "=\\=": x != y}[b.nome]
            if not ok:
                return None
        return s, resto

    def go(i, s, pendentes):
        f = filtrar(s, pendentes)
        if f is None:
            return
        s, pendentes = f
        if i == len(positivos):
            if pendentes:
                raise ErroGrounding(f"comparação com variável livre em: {r}")
            yield s
            return
        lit = positivos[i]
        for a in list(indice.get(lit.chave, ())):
            s2 = unificar(lit, a, s)
            if s2 is not None:
                yield from go(i + 1, s2, pendentes)

    yield from go(0, {}, embutidos)
