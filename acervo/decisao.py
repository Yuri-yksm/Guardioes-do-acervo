"""Decisão de um pedido, com prova — orquestra Prolog/Python (M2/M3) e SAT (M4).

Procedimento (idêntico em prolog/consultas.pl: decide/6):
  1. se pode(P,A,R,H) tem prova            -> PERMITIDO   [prova de pode]
  2. senão, se permitido(P,A,R,H) tem prova -> NEGADO por proibição
                                               [prova de permitido, prova de proibido]
  3. senão                                 -> NEGADO por falta de permissão

Antes disso verifica-se a consistência da entrada (restrições de
integridade). Se a entrada tem fatos incertos ("um_de"), a resposta vem
da camada SAT: o pedido é consequência (permitido), a negação é
consequência (negado) ou nenhum dos dois (resposta não única).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from motor.parser import ler_termo
from motor.sld import Motor, NoProva
from motor.termos import Struct, atomo, formatar

from . import prolog as pl
from .base import motor_da_entrada
from .entrada import Entrada, Pedido
from .explicacao import via_delegacao


@dataclass
class Decisao:
    pedido: Pedido
    resultado: str                    # permitido | negado | nao_unica | inconsistente
    motivo: str = ""                  # papel | delegacao | proibicao | sem_permissao | ...
    arvores: list[NoProva] = field(default_factory=list)
    diagnostico: list[str] = field(default_factory=list)
    violacoes: list = field(default_factory=list)
    avisos: list = field(default_factory=list)
    mundos: dict = field(default_factory=dict)      # resultado -> lista de mundos
    modelos: int | None = None
    lacos: int = 0
    limite_atingido: bool = False
    motor: str = "python"


# ---------------------------------------------------------------------
# Núcleo SLD (um mundo, entrada sem incerteza)
# ---------------------------------------------------------------------

def decidir_sld(m: Motor, p: Pedido) -> tuple[str, str, list[NoProva]]:
    s = m.provar(p.atomo("pode"))
    if s:
        arv = s.arvores()[0]
        return "permitido", ("delegacao" if via_delegacao(arv) else "papel"), [arv]
    s1 = m.provar(p.atomo("permitido"))
    if s1:
        s2 = m.provar(p.atomo("proibido"))
        return "negado", "proibicao", [s1.arvores()[0], s2.arvores()[0]]
    return "negado", "sem_permissao", []


def _nomes(m: Motor, objetivo: str) -> list:
    return m.respostas(ler_termo(objetivo))


def diagnosticar(m: Motor, p: Pedido) -> list[str]:
    """Por que não há permissão? (explicação de uma falha finita)"""
    out = []
    P, A, R, H = p.pessoa, p.acao, p.recurso, p.hora
    if not m.provar(atomo("hora", H)):
        out.append(f"hora {H} inválida (o domínio é 0..23)")
    tipos = [t.args[1].nome for t in _nomes(m, f"tipo({R}, T)")]
    if not tipos:
        out.append(f"recurso {R} desconhecido (sem tipo)")
        return out
    T = tipos[0]
    papeis = [t.args[1].nome for t in _nomes(m, f"tem_papel({P}, X)")]
    if not papeis:
        out.append(f"{P} não tem nenhum papel")
    else:
        out.append(f"papéis efetivos de {P} (com herança): {', '.join(papeis)}")
    quem = [t.args[0].nome for t in _nomes(m, f"permissao(X, {A}, {T})")]
    if quem:
        out.append(f"a permissão {A} sobre {T} pertence a: {', '.join(quem)} — nenhum deles é alcançável "
                   f"a partir dos papéis de {P} (a herança só desce)")
    else:
        out.append(f"nenhum papel tem a permissão {A} sobre {T}")
    for d in _nomes(m, f"delega(D, {P}, {A}, {T}, I, F)"):
        de, _, _, _, i, f = d.args
        motivos = []
        if not (i <= H < f):
            motivos.append(f"fora do horário (vale em [{i}h, {f}h), pedido às {H}h)")
        if not m.provar(atomo("permissao_efetiva", de, A, T)):
            motivos.append(f"{formatar(de)} não tem a permissão para delegar")
        out.append(f"delegação de {formatar(de)} não se aplica: " + "; ".join(motivos or ["?"]))
    return out


def motivo_proibicao(arv: NoProva) -> str:
    return arv.nome or arv.rotulo


# ---------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------

def verificar(e: Entrada, extras=()) -> tuple[list, list]:
    m = motor_da_entrada(e, extras)
    viol = [v.args[0] for v in m.respostas(ler_termo("violacao(X)"))]
    avis = [v.args[0] for v in m.respostas(ler_termo("aviso(X)"))]
    return viol, avis


def decidir(e: Entrada, p: Pedido, motor: str = "python", limite: int = 200) -> Decisao:
    if e.tem_incerteza:
        return _decidir_incerto(e, p, limite, motor)
    viol, avis = verificar(e)
    if viol:
        return Decisao(p, "inconsistente", "violacao", violacoes=viol, avisos=avis, motor=motor)

    m = motor_da_entrada(e, limite=limite)
    if motor == "prolog":
        (dec, arvs), = pl.decidir_lote(e, [p], limite=limite)
        res, mot = ("permitido", "") if dec == "permitido" else ("negado", dec[len("negado("):-1])
        if res == "permitido":
            mot = "delegacao" if via_delegacao(arvs[0]) else "papel"
    else:
        res, mot, arvs = decidir_sld(m, p)
    d = Decisao(p, res, mot, arvs, avisos=avis, motor=motor)
    if mot == "sem_permissao":
        d.diagnostico = diagnosticar(m, p)
    d.lacos = len(m.lacos)
    d.limite_atingido = m.limite_atingido
    return d


def _decidir_incerto(e: Entrada, p: Pedido, limite: int, motor: str = "python") -> Decisao:
    """Duas vias independentes que precisam concordar:
      (a) camada SAT: o pedido (ou a negação) é consequência, por refutação?
      (b) enumeração: decide-se em cada mundo compatível com as restrições,
          com o motor escolhido (SLD Python ou Prolog)."""
    from sat.camada import CamadaSAT
    c = CamadaSAT(e, [p.hora])
    alvo = p.atomo("pode")
    st = c.status(alvo)
    d = Decisao(p, "", motor=f"sat+{motor}")
    d.modelos = c.contar_modelos()
    viol = c.violacoes()
    d.violacoes = viol["forcadas"]
    if st == "inconsistente":
        d.resultado, d.motivo = "inconsistente", "nenhum mundo satisfaz as restrições"
        d.violacoes = viol["possiveis"]
        return d
    if viol["possiveis"]:
        d.diagnostico.append("mundos descartados por violar restrições: " +
                             ", ".join(formatar(v) for v in viol["possiveis"]))

    # (b) decisão mundo a mundo
    mundos = c.mundos()
    if motor == "prolog":
        por_mundo = [pl.decidir_lote(e, [p], extras=w, limite=limite)[0] for w in mundos]
        por_mundo = [("permitido" if dec == "permitido" else "negado", arvs) for dec, arvs in por_mundo]
    else:
        por_mundo = []
        for w in mundos:
            res, _, arvs = decidir_sld(motor_da_entrada(e, w, limite), p)
            por_mundo.append((res, arvs))
    d.mundos = {"permitido": [w for w, (r, _) in zip(mundos, por_mundo) if r == "permitido"],
                "negado": [w for w, (r, _) in zip(mundos, por_mundo) if r == "negado"]}
    esperado_sat = {"sempre": "permitido", "nunca": "negado", "depende": "nao_unica"}[st]
    resultados = {r for r, _ in por_mundo}
    por_enum = resultados.pop() if len(resultados) == 1 else "nao_unica"
    if por_enum != esperado_sat:
        d.diagnostico.append(f"DIVERGÊNCIA: SAT diz {esperado_sat}, enumeração diz {por_enum}")

    d.resultado = esperado_sat
    onde = "no único mundo possível" if d.modelos == 1 else f"nos {d.modelos} mundos possíveis"
    if st == "sempre":
        d.motivo = f"consequência lógica (vale {onde})"
    elif st == "nunca":
        d.motivo = f"a negação é consequência (vale {onde})"
    else:
        d.motivo = "depende de fatos incertos da entrada"
    if st in ("sempre", "nunca"):
        w, (res, arvs) = mundos[0], por_mundo[0]
        d.arvores = arvs
        m = motor_da_entrada(e, w, limite)
        if res == "negado" and not arvs:
            d.motivo += "; nenhuma permissão aplicável"
            d.diagnostico += diagnosticar(m, p)
        elif res == "negado":
            d.motivo += "; proibição prevalece"
    return d


def quem_pode(e: Entrada, acao: str, recurso: str, h: int, motor: str = "python") -> list[str]:
    obj = Struct("pode", (ler_termo("P"), Struct(acao), Struct(recurso), h))
    if motor == "prolog":
        rs, _ = pl.consultar(e, obj)
    else:
        rs = motor_da_entrada(e).respostas(obj)
    return [formatar(r.args[0]) for r in rs]
