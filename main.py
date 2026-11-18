#!/usr/bin/env python3
"""Guardiões do acervo — controle de acesso por regras (interface, M5).

Exemplos
  python main.py --entrada casos/exemplo_enunciado.json --pergunta "davi aprovar p8 10h"
  python main.py --entrada casos/exemplo_enunciado.json --pergunta pedido --pessoa bia --acao ler --recurso "reserva técnica" --hora 20
  python main.py --entrada casos/exemplo_enunciado.json --pergunta consultas --motor ambos
  python main.py --entrada casos/exemplo_enunciado.json --pergunta quem --acao aprovar --recurso p8 --hora 10
  python main.py --entrada casos/exemplo_enunciado.json --pergunta consulta --objetivo "tem_papel(bia, X)"
  python main.py --entrada casos/exemplo_enunciado.json --pergunta derivacao --pessoa bia --acao editar --recurso catalogo --hora 10
  python main.py --entrada casos/proprio_03_papel_incerto.json --pergunta modelos
  python main.py --entrada casos/exemplo_enunciado.json --pergunta consequencia --pessoa gil --acao ler --recurso reserva_tecnica --hora 20
  python main.py --entrada casos/exemplo_enunciado.json --pergunta conflitos
  python main.py --entrada casos/exemplo_enunciado.json --pergunta dimacs --saida exemplo.cnf
  python main.py --entrada casos/exemplo_enunciado.json --pergunta fatos --saida fatos.pl
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acervo import prolog as pl  # noqa: E402
from acervo.base import motor_da_entrada  # noqa: E402
from acervo.decisao import decidir, quem_pode, verificar  # noqa: E402
from acervo.entrada import Entrada, ErroEntrada, Pedido, normalizar  # noqa: E402
from acervo.explicacao import ROTULO_RESULTADO, completar, desenhar, relatorio  # noqa: E402
from motor.parser import ErroSintaxe, ler_termo  # noqa: E402
from motor.sld import ErroFloundering, ErroInstanciacao, derivacao  # noqa: E402
from motor.termos import Struct, formatar  # noqa: E402
from motor.unificacao import formatar_subst  # noqa: E402

PERGUNTAS = ["pedido", "consultas", "quem", "consulta", "derivacao", "validar", "consistencia",
             "consequencia", "modelos", "conflitos", "dimacs", "fatos"]


def _pedido(a) -> Pedido:
    falta = [n for n in ("pessoa", "acao", "recurso", "hora") if getattr(a, n) is None]
    if falta:
        raise ErroEntrada("informe " + ", ".join("--" + f for f in falta))
    return Pedido.de(a.pessoa, a.acao, a.recurso, a.hora)


def _atalho(texto: str) -> Pedido | None:
    """'davi aprovar p8 10h' ou 'davi, aprovar, p8, 10h'"""
    partes = [x for x in re.split(r"[,\s]+", texto.strip()) if x]
    if len(partes) >= 4 and re.fullmatch(r"\d{1,2}(h|:00)?", partes[-1]):
        recurso = "_".join(partes[2:-1])
        return Pedido.de(partes[0], partes[1], recurso, partes[-1])
    return None


# ---------------------------------------------------------------------

def q_pedido(e, a, p=None):
    p = p or _pedido(a)
    motores = ["python", "prolog"] if a.motor == "ambos" else [a.motor]
    decs = [decidir(e, p, m, a.limite) for m in motores]
    print(relatorio(decs[0], detalhado=not a.resumo))
    if len(decs) == 2:
        iguais = decs[0].resultado == decs[1].resultado
        print(f"\nConferência Python × Prolog: {'mesma resposta' if iguais else 'DIVERGÊNCIA'} "
              f"({decs[0].resultado} / {decs[1].resultado})")
        return 0 if iguais else 2
    return 0


def q_consultas(e, a):
    if not e.consultas:
        print("A entrada não tem o campo \"consultas\".")
        return 1
    motores = ["python", "prolog"] if a.motor == "ambos" else [a.motor]
    falhas = 0
    print(f"{'pedido':<40} " + " ".join(f"{m:<14}" for m in motores) + " esperado")
    for c in e.consultas:
        rs = [decidir(e, c.pedido, m, a.limite) for m in motores]
        ok = c.esperado is None or all(r.resultado == c.esperado for r in rs)
        falhas += not ok
        print(f"{str(c.pedido):<40} " + " ".join(f"{r.resultado:<14}" for r in rs)
              + f" {c.esperado or '-':<14}{'' if ok else '  ✗'}")
    print(f"\n{len(e.consultas) - falhas}/{len(e.consultas)} de acordo com o esperado.")
    return 0 if falhas == 0 else 2


def q_quem(e, a):
    if None in (a.acao, a.recurso, a.hora):
        raise ErroEntrada("informe --acao, --recurso e --hora")
    ac, rec, h = normalizar(a.acao), normalizar(a.recurso), Pedido.de("x", "x", "x", a.hora).hora
    if e.tem_incerteza:
        print("A entrada tem fatos incertos: use --pergunta pedido para cada pessoa.")
        return 1
    ps = quem_pode(e, ac, rec, h, "python" if a.motor == "ambos" else a.motor)
    print(f"Quem pode {ac} {rec} às {h}h?  ?- pode(P, {ac}, {rec}, {h}).")
    if not ps:
        print("Ninguém.")
    elif len(ps) == 1:
        print(f"Resposta única: P = {ps[0]}")
    else:
        print(f"Resposta não única ({len(ps)} substituições para P): " + ", ".join(ps))
    if a.motor == "ambos":
        pp = quem_pode(e, ac, rec, h, "prolog")
        print(f"Conferência Python × Prolog: {'mesmas respostas' if pp == ps else 'DIVERGÊNCIA'}")
    return 0


def q_consulta(e, a):
    if not a.objetivo:
        raise ErroEntrada('informe --objetivo, por exemplo --objetivo "tem_papel(bia, X)"')
    g = ler_termo(a.objetivo)
    if a.motor == "prolog":
        rs, arv = pl.consultar(e, g, limite=a.limite)
    else:
        m = motor_da_entrada(e, limite=a.limite)
        sols = list(m.resolver(g))
        rs = list(dict.fromkeys(s.resposta(g) for s in sols))
        arv = sols[0].arvores()[0] if sols else None
    print(f"?- {formatar(g)}.")
    if not rs:
        print("false. (falha finita: não há prova)")
        return 0
    for r in rs:
        print(f"   {formatar(r)}")
    print(f"{len(rs)} resposta(s){' — não única' if len(rs) > 1 else ''}.")
    if arv is not None and not a.resumo:
        print("\nPrimeira prova:")
        linhas, subs = desenhar(completar(arv))
        print("\n".join("  " + x for x in linhas))
        if subs:
            print("Substituições:")
            print("\n".join("  " + s for s in subs))
    return 0


def q_derivacao(e, a):
    g = ler_termo(a.objetivo) if a.objetivo else _pedido(a).atomo("pode")
    m = motor_da_entrada(e, limite=a.limite)
    s = m.provar(g)
    if s is None:
        print(f"?- {formatar(g)}.  falha finita: não existe refutação SLD.")
        return 0
    print(f"Refutação SLD de  ← {formatar(g)}")
    print("(cada passo: resolvente, literal selecionado, cláusula renomeada, unificador)\n")
    for i, p in enumerate(derivacao(s), 1):
        res = ", ".join(formatar(x) for x in p["resolvente"])
        print(f"G{i-1}: ← {res}")
        if p["rotulo"] == "naf":
            print(f"   seleciona {formatar(p['selecionado'])}: sub-derivação de "
                  f"{formatar(p['selecionado'].args[0])} falha finitamente ⇒ literal removido")
        elif p["rotulo"] == "builtin":
            print(f"   seleciona {formatar(p['selecionado'])}: comparação avaliada (verdadeira)")
        else:
            nome = p["clausula"].nome or "fato"
            print(f"   seleciona {formatar(p['selecionado'])}  com  {p['clausula']}   [{nome}]")
            print(f"   θ{i} = {formatar_subst(p['mgu'])}")
    print(f"G{len(s.passos)}: □   (cláusula vazia — refutação concluída)")
    print(f"\nResposta: {formatar(s.resposta(g))}")
    return 0


def q_validar(e, a):
    from sat.camada import CamadaSAT
    print(f"Entrada: {e.origem}" + (f" — {e.descricao}" if e.descricao else ""))
    if e.tem_incerteza:
        print("Fatos incertos:")
        for gi in e.incertos:
            print(f"  • {gi.descricao}")
        c = CamadaSAT(e)
        v = c.violacoes()
        print(f"Consistente (algum mundo satisfaz as restrições): {'sim' if c.consistente() else 'NÃO'}")
        print("Violações forçadas: " + (", ".join(map(formatar, v["forcadas"])) or "nenhuma"))
        print("Violações possíveis: " + (", ".join(map(formatar, v["possiveis"])) or "nenhuma"))
        return 0
    viol, avis = verificar(e)
    print("Violações (restrições de integridade): " + (", ".join(map(formatar, viol)) or "nenhuma"))
    print("Avisos: " + (", ".join(map(formatar, avis)) or "nenhum"))
    print("Entrada " + ("CONSISTENTE." if not viol else "INCONSISTENTE."))
    return 0


def q_consistencia(e, a):
    from sat.camada import CamadaSAT
    t = time.perf_counter()
    c = CamadaSAT(e)
    ok = c.consistente()
    tam = c.tamanho()
    print("Pergunta: a entrada é consistente?  (KB ∧ ¬violacao(...) para toda violação possível é satisfazível?)")
    print(f"Grounding: {tam['regras_ground']} regras ground, horas representativas {tam['horas']}")
    print(f"FNC: {tam['variaveis']} variáveis, {tam['clausulas']} cláusulas"
          + (f", {tam['componentes_recursivas']} componente(s) recursiva(s) codificadas em camadas" if tam['componentes_recursivas'] else ""))
    print(f"DPLL: {'SATISFAZÍVEL' if ok else 'INSATISFAZÍVEL'}  ({c.resolvedor.estat}, {time.perf_counter() - t:.3f}s)")
    print("Resposta: " + ("consistente." if ok else "INCONSISTENTE."))
    if not ok:
        v = c.violacoes()
        print("Violações forçadas (valem em todo mundo): " + ", ".join(map(formatar, v["forcadas"])))
    return 0


def q_consequencia(e, a):
    from sat.camada import CamadaSAT
    p = _pedido(a)
    c = CamadaSAT(e, [p.hora])
    alvo = p.atomo("pode")
    print(f"Pergunta: {formatar(alvo)} é consequência da entrada?")
    if not c.consistente():
        print("A entrada é inconsistente: KB ∧ restrições já é insatisfazível (toda fórmula seria consequência).")
        return 0
    sim = c.consequencia(alvo)
    nao = not c.satisfazivel_com(alvo, True)
    print(f"Refutação 1: KB ∧ restrições ∧ ¬{formatar(alvo)}  →  {'INSATISFAZÍVEL' if sim else 'satisfazível'}")
    print(f"Refutação 2: KB ∧ restrições ∧ {formatar(alvo)}   →  {'INSATISFAZÍVEL' if nao else 'satisfazível'}")
    if sim:
        print("Resposta: sim, é consequência (PERMITIDO em todo modelo).")
    elif nao:
        print("Resposta: a NEGAÇÃO é consequência (NEGADO em todo modelo).")
    else:
        print("Resposta: nem o pedido nem a sua negação são consequência — resposta não única.")
        for v in (True, False):
            for w in c.mundos(alvo, v, 10):
                print(f"   {'PERMITIDO' if v else 'NEGADO':<9} quando {', '.join(map(formatar, w))}")
    return 0


def q_modelos(e, a):
    from sat.camada import CamadaSAT
    extras = []
    p = None
    if a.pessoa:
        p = _pedido(a)
        extras = [p.hora]
    c = CamadaSAT(e, extras)
    n = c.contar_modelos()
    print("Pergunta: quantos modelos a entrada tem?")
    print(f"Contagem exata (#DPLL) de KB ∧ restrições: {n} modelo(s)")
    if e.tem_incerteza:
        print("Cada modelo corresponde a uma escolha dos fatos incertos (o resto é determinado pelo completamento):")
        for w in c.mundos(maximo=50):
            print(f"  • {', '.join(map(formatar, w))}")
    else:
        print("Sem fatos incertos: o mundo fechado determina um único modelo." if n == 1 else "")
    if p:
        alvo = p.atomo("pode")
        print(f"Modelos com {formatar(alvo)}: {c.contar_modelos(alvo, True)};  "
              f"com ¬{formatar(alvo)}: {c.contar_modelos(alvo, False)}")
    return 0


def _comprimir(exs: list[str]) -> list[str]:
    """Junta faixas de horário adjacentes do mesmo (pessoa, ação, recurso)."""
    grupos: dict = {}
    for x in exs:
        chave, faixa = x.rsplit(", ", 1)
        ini, _, fim = faixa.replace("h", "").partition("–")
        grupos.setdefault(chave, []).append((int(ini), int(fim or ini)))
    out = []
    for k, fs in grupos.items():
        fs.sort()
        juntas = [list(fs[0])]
        for i, f in fs[1:]:
            if i == juntas[-1][1] + 1:
                juntas[-1][1] = f
            else:
                juntas.append([i, f])
        out.append(k + ", " + ", ".join(f"{i}h" if i == f else f"{i}h–{f}h" for i, f in juntas))
    return out


def q_conflitos(e, a):
    from sat.camada import CamadaSAT
    c = CamadaSAT(e)
    print("Verificação da política com SAT: pares de regras que permitem e negam o mesmo pedido")
    print("(para cada permitido(x) e proibido(x) possíveis, testa-se KB ∧ permitido(x) ∧ proibido(x))\n")
    cs = c.conflitos()
    if not cs:
        print("Nenhum conflito.")
    for k in cs:
        print(f"• {k.regra_permite}\n  × {k.regra_nega}")
        for x in _comprimir(k.exemplos):
            print(f"     {x}")
    print("\nPela regra R7 a proibição prevalece em todos esses casos (negar prevalece).")
    inc = c.papeis_incompativeis()
    print("\nPessoas que acumulam papéis incompatíveis: " + (", ".join(map(formatar, inc)) or "nenhuma"))
    return 0


def q_dimacs(e, a):
    from sat.camada import CamadaSAT
    texto = CamadaSAT(e).dimacs()
    if a.saida:
        Path(a.saida).write_text(texto, encoding="utf-8")
        print(f"FNC gravada em {a.saida}")
    else:
        print(texto, end="")
    return 0


def q_fatos(e, a):
    destino = a.saida or "-"
    if destino == "-":
        for f in e.fatos():
            print(formatar(f).replace(", ", ",") + ".")
    else:
        pl.escrever_fatos(e.fatos(), destino)
        print(f"Fatos gravados em {destino}  (carregue com carregar_fatos('{destino}') em prolog/consultas.pl)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Guardiões do acervo — controle de acesso por regras",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--entrada", required=True, help="arquivo JSON do caso")
    ap.add_argument("--pergunta", default="pedido",
                    help=f"uma de: {', '.join(PERGUNTAS)}; ou um pedido curto como \"davi aprovar p8 10h\"")
    ap.add_argument("--pessoa"); ap.add_argument("--acao"); ap.add_argument("--recurso"); ap.add_argument("--hora")
    ap.add_argument("--objetivo", help="objetivo Prolog para --pergunta consulta/derivacao")
    ap.add_argument("--motor", choices=["python", "prolog", "ambos"], default="python")
    ap.add_argument("--limite", type=int, default=200, help="limite de profundidade da busca SLD")
    ap.add_argument("--saida", help="arquivo de saída (dimacs, fatos)")
    ap.add_argument("--resumo", action="store_true", help="omitir substituições/árvores longas")
    a = ap.parse_args(argv)

    try:
        e = Entrada.de_arquivo(a.entrada)
        if a.motor != "python" and not pl.disponivel():
            raise ErroEntrada("motor Prolog pedido, mas swipl não está instalado")
        if a.pergunta in PERGUNTAS:
            return globals()[f"q_{a.pergunta}"](e, a)
        p = _atalho(a.pergunta)
        if p is None:
            raise ErroEntrada(f"pergunta desconhecida: {a.pergunta!r}. Use {', '.join(PERGUNTAS)} "
                              "ou um pedido como \"davi aprovar p8 10h\"")
        return q_pedido(e, a, p)
    except (ErroEntrada, ErroSintaxe, FileNotFoundError) as ex:
        print(f"erro: {ex}", file=sys.stderr)
        return 1
    except (ErroFloundering, ErroInstanciacao, pl.ErroProlog) as ex:
        print(f"erro de execução: {ex}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
