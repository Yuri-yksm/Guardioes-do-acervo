"""Explicação legível (M5): árvore de prova, regras usadas, substituições,
papéis percorridos, delegação usada e proibição aplicada."""
from __future__ import annotations

from motor.sld import BaseConhecimento, NoProva
from motor.termos import NAO, Struct, Var, formatar, vars_clausula
from motor.unificacao import aplicar, unificar

from .base import montar_kb

ROTULO_RESULTADO = {
    "permitido": "PERMITIDO",
    "negado": "NEGADO",
    "nao_unica": "SEM RESPOSTA ÚNICA",
    "inconsistente": "ENTRADA INCONSISTENTE",
}

_KB_REGRAS: BaseConhecimento | None = None


def _kb_regras() -> BaseConhecimento:
    global _KB_REGRAS
    if _KB_REGRAS is None:
        _KB_REGRAS = montar_kb([])
    return _KB_REGRAS


def completar(no: NoProva) -> NoProva:
    """Reconstrói nome da regra e ligações das variáveis a partir do rótulo
    (necessário para árvores vindas do Prolog, que só trazem o rótulo)."""
    if "#" in no.rotulo and not no.ligacoes:
        pred, k = no.rotulo.rsplit("#", 1)
        nome, ar = pred.rsplit("/", 1)
        cls = _kb_regras().clausulas((nome, int(ar)))
        c = cls[int(k) - 1]
        s = unificar(c.cabeca, no.objetivo, {})
        for lit, f in zip(c.corpo, no.filhos):
            if s is None:
                break
            s = unificar(lit, f.objetivo, s)
        if s is not None:
            no.ligacoes = {v.nome: aplicar(v, s) for v in vars_clausula(c) if not v.nome.startswith("_")}
        no.nome = c.nome
    for f in no.filhos:
        completar(f)
    return no


def via_delegacao(arv: NoProva) -> bool:
    return any(isinstance(n.objetivo, Struct) and n.objetivo.nome == "delegacao_valida" for n in arv.percorrer())


# ---------------------------------------------------------------------
# Árvore
# ---------------------------------------------------------------------

def desenhar(arv: NoProva, contador: list | None = None) -> tuple[list[str], list[str]]:
    """(linhas da árvore, linhas de substituições numeradas)"""
    contador = contador if contador is not None else [0]
    linhas, subs = [], []

    def rotulo(n: NoProva) -> str:
        if n.rotulo == "fato":
            return "fato"
        if n.rotulo == "builtin":
            return "comparação"
        if n.rotulo == "naf":
            return "negação por falha: não há prova (mundo fechado)"
        return n.nome or n.rotulo

    def go(n: NoProva, prefixo: str, ultimo: bool, raiz: bool):
        marca = "" if raiz else ("└─ " if ultimo else "├─ ")
        num = ""
        if "#" in n.rotulo:
            contador[0] += 1
            num = f"[{contador[0]}] "
            if n.ligacoes:
                lig = ", ".join(f"{k} ↦ {formatar(v)}" for k, v in n.ligacoes.items())
                subs.append(f"[{contador[0]}] {n.nome or n.rotulo}: {{{lig}}}")
        linhas.append(f"{prefixo}{marca}{num}{formatar(n.objetivo)}   ⟸ {rotulo(n)}")
        filho_pref = prefixo + ("" if raiz else ("   " if ultimo else "│  "))
        for i, f in enumerate(n.filhos):
            go(f, filho_pref, i == len(n.filhos) - 1, False)

    go(arv, "", True, True)
    return linhas, subs


def regras_usadas(arvs) -> list[str]:
    vistos = {}
    for a in arvs:
        for n in a.percorrer():
            if "#" in n.rotulo:
                vistos.setdefault(n.nome or n.rotulo, None)
    return list(vistos)


def cadeias_de_papeis(arvs) -> list[str]:
    out = []
    for a in arvs:
        for n in a.percorrer():
            o = n.objetivo
            if isinstance(o, Struct) and o.nome == "tem_papel" and n.filhos:
                p = formatar(o.args[0])
                cadeia = [formatar(n.filhos[0].objetivo.args[1])]
                for m in n.percorrer():
                    if isinstance(m.objetivo, Struct) and m.objetivo.nome == "herda":
                        cadeia.append(formatar(m.objetivo.args[1]))
                s = f"{p}: " + " → ".join(cadeia)
                if s not in out:
                    out.append(s)
    return out


def delegacoes_usadas(arvs) -> list[str]:
    out = []
    for a in arvs:
        for n in a.percorrer():
            o = n.objetivo
            if isinstance(o, Struct) and o.nome == "delega":
                d, p, ac, t, i, f = (formatar(x) for x in o.args)
                s = f"{d} → {p}: {ac} {t}, válida em [{i}h, {f}h)"
                if s not in out:
                    out.append(s)
    return out


# ---------------------------------------------------------------------
# Relatório da decisão
# ---------------------------------------------------------------------

def relatorio(d, detalhado: bool = True) -> str:
    L = []
    p = d.pedido
    for a in d.arvores:
        completar(a)
    L.append(f"Pedido: {p.pessoa} pode {p.acao} {p.recurso} às {p.hora}h?   (motor: {d.motor})")
    L.append(f"Resposta: {ROTULO_RESULTADO[d.resultado]}" + (f" — {_motivo(d)}" if _motivo(d) else ""))

    if d.resultado == "inconsistente":
        L.append("")
        L.append("Restrições de integridade violadas:")
        L += [f"  • {formatar(v)}" for v in d.violacoes] or ["  • (nenhum mundo possível satisfaz as restrições)"]
        L.append("Com premissas inconsistentes qualquer conclusão seria consequência; "
                 "o sistema se recusa a decidir.")
        return "\n".join(L)

    if d.resultado == "nao_unica":
        L.append("")
        L.append(f"Mundos possíveis (escolhas dos fatos incertos): {d.modelos}")
        for res in ("permitido", "negado"):
            for w in d.mundos.get(res, []):
                L.append(f"  • {', '.join(formatar(x) for x in w)}  ⇒  {res.upper()}")
        L.append("Motivo: o pedido não é consequência da entrada, e a sua negação também não é "
                 "(verificado por refutação na camada SAT).")

    if d.modelos and d.resultado in ("permitido", "negado") and d.mundos and d.arvores:
        L.append("(entrada com fatos incertos: abaixo, a prova em um dos mundos possíveis)")

    if d.arvores:
        L.append("")
        cont = [0]
        titulos = ["Prova"] if len(d.arvores) == 1 else ["Prova da permissão", "Prova da proibição (que prevalece)"]
        todas_subs = []
        for t, a in zip(titulos, d.arvores):
            L.append(f"{t}:")
            linhas, subs = desenhar(a, cont)
            L += ["  " + x for x in linhas]
            todas_subs += subs
            L.append("")
        cp = cadeias_de_papeis(d.arvores)
        if cp:
            L.append("Papéis percorridos: " + "; ".join(cp))
        dl = delegacoes_usadas(d.arvores)
        L.append("Delegação usada: " + ("; ".join(dl) if dl else "nenhuma"))
        if d.motivo == "proibicao":
            L.append("Proibição aplicada: " + (d.arvores[1].nome or d.arvores[1].rotulo))
        else:
            L.append("Proibição aplicada: nenhuma (\\+ proibido(...) provado por falha finita)")
        L.append("Regras usadas:")
        L += ["  • " + r for r in regras_usadas(d.arvores)]
        if detalhado and todas_subs:
            L.append("")
            L.append("Substituições aplicadas (variáveis de cada regra, numeradas como na árvore):")
            L += ["  " + s for s in todas_subs]

    if d.diagnostico:
        L.append("")
        L.append("Por que não há permissão:" if d.motivo == "sem_permissao" else "Observações:")
        L += [f"  • {x}" for x in d.diagnostico]

    if d.avisos:
        L.append("")
        L.append("Avisos sobre a entrada:")
        L += [f"  ⚠ {formatar(a)}" for a in d.avisos]
    if d.lacos:
        L.append(f"  ⚠ laços detectados e podados durante a busca: {d.lacos}")
    if d.limite_atingido:
        L.append("  ⚠ limite de profundidade atingido: a resposta pode estar incompleta")
    return "\n".join(L).rstrip()


def _motivo(d) -> str:
    if d.resultado == "permitido":
        if d.mundos:
            return d.motivo
        return "por delegação" if d.motivo == "delegacao" else "por papel"
    if d.resultado == "negado":
        if d.mundos:
            return d.motivo
        if d.motivo == "proibicao":
            return "proibição prevalece: " + ((d.arvores[1].nome or d.arvores[1].rotulo) if len(d.arvores) > 1 else "")
        return "nenhuma permissão aplicável"
    if d.resultado == "nao_unica":
        return d.motivo
    return ""
