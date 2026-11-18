"""Mesmas respostas em todo o domínio:
   motor Python (SLD)  ==  SWI-Prolog (meta-interpretador)  ==  camada SAT.

Para cada entrada sem incerteza e consistente, todos os pedidos
pessoa × ação × recurso × hora são decididos pelos três caminhos, e as
árvores de prova do Python e do Prolog são comparadas nó a nó."""
import pytest

from acervo import prolog as pl
from acervo.base import motor_da_entrada
from acervo.decisao import decidir_sld
from acervo.entrada import Entrada, Pedido
from motor.parser import ler_termo
from motor.termos import formatar
from sat.camada import CamadaSAT

from conftest import CASOS, precisa_prolog

CERTOS = [c for c in CASOS if not Entrada.de_arquivo(c).tem_incerteza]


def todos_pedidos(e: Entrada, horas):
    return [Pedido(p, a, r, h) for p in e.pessoas() for a in e.acoes()
            for r in e.recursos_conhecidos() for h in horas]


def horas_teste(e: Entrada):
    hs = set(e.horas_criticas())
    hs |= {h - 1 for h in hs if h > 0} | {23}
    return sorted(hs)


def assinatura(no):
    return (formatar(no.objetivo), no.rotulo, [assinatura(f) for f in no.filhos])


@pytest.mark.parametrize("caminho", CERTOS, ids=[c.stem for c in CERTOS])
def test_sld_igual_sat(caminho):
    e = Entrada.de_arquivo(caminho)
    hs = list(range(24)) if caminho.stem == "exemplo_enunciado" else horas_teste(e)
    c = CamadaSAT(e, hs)
    if not c.consistente():
        # premissas inconsistentes: tanto pode(...) quanto ¬pode(...) são consequência
        p = todos_pedidos(e, hs)[0]
        assert c.status(p.atomo("pode")) == "inconsistente"
        assert c.consequencia(p.atomo("pode")) and not c.satisfazivel_com(p.atomo("pode"), True)
        return
    for p in todos_pedidos(e, hs):
        res, _, _ = decidir_sld(motor_da_entrada(e), p)
        st = c.status(p.atomo("pode"))
        assert st in ("sempre", "nunca"), (p, st)
        assert (res == "permitido") == (st == "sempre"), p


@precisa_prolog
@pytest.mark.parametrize("caminho", CERTOS, ids=[c.stem for c in CERTOS])
def test_python_igual_prolog_decisoes_e_arvores(caminho):
    e = Entrada.de_arquivo(caminho)
    peds = todos_pedidos(e, horas_teste(e))
    prolog = pl.decidir_lote(e, peds)
    for p, (dec_pl, arvs_pl) in zip(peds, prolog):
        res, mot, arvs = decidir_sld(motor_da_entrada(e), p)
        dec_py = "permitido" if res == "permitido" else f"negado({mot})"
        assert dec_py == dec_pl, p
        assert [assinatura(a) for a in arvs] == [assinatura(a) for a in arvs_pl], p


CONSULTAS = ["tem_papel(X, Y)", "alcanca(X, Y)", "permitido(P, A, R, 10)", "proibido(P, A, R, 20)",
             "violacao(V)", "aviso(V)", "delegacao_valida(P, A, T, H)", "pode(P, A, R, 9)"]


@precisa_prolog
@pytest.mark.parametrize("caminho", CERTOS, ids=[c.stem for c in CERTOS])
@pytest.mark.parametrize("consulta", CONSULTAS)
def test_python_igual_prolog_consultas_abertas(caminho, consulta):
    e = Entrada.de_arquivo(caminho)
    g = ler_termo(consulta)
    py = [formatar(r) for r in motor_da_entrada(e).respostas(g)]
    rs, _ = pl.consultar(e, g)
    assert py == [formatar(r) for r in rs]      # mesmas respostas, na mesma ordem


@precisa_prolog
def test_floundering_nos_dois_motores():
    from motor.sld import ErroFloundering
    e = Entrada.de_arquivo(CASOS[0])
    g = ler_termo("\\+ proibido(X, ler, catalogo, 10)")
    with pytest.raises(ErroFloundering):
        motor_da_entrada(e).provar(g)
    with pytest.raises(pl.ErroProlog, match="floundering"):
        pl.consultar(e, g)


def test_ciclo_codificado_em_camadas():
    caminho = next(c for c in CASOS if "ciclo" in c.stem)
    c = CamadaSAT(Entrada.de_arquivo(caminho))
    assert c.tamanho()["componentes_recursivas"] >= 1
    # sem as camadas, o completamento aceitaria alcanca(curador, X) "auto-justificado";
    # aqui o único modelo é o do mundo fechado
    assert c.contar_modelos() == 1
