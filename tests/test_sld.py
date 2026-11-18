"""M3: resolução SLD — renomeação, laços, limite de profundidade, negação por falha."""
import pytest

from motor.parser import ler_programa, ler_termo
from motor.sld import BaseConhecimento, ErroFloundering, ErroInstanciacao, Motor, derivacao
from motor.termos import formatar


def motor(txt, limite=200):
    return Motor(BaseConhecimento(ler_programa(txt)), limite=limite)


def resp(m, q):
    return [formatar(r) for r in m.respostas(ler_termo(q))]


def test_fatos_e_regras_ordem_prolog():
    m = motor("pai(a,b). pai(b,c). pai(b,d). avo(X,Z) :- pai(X,Y), pai(Y,Z).")
    assert resp(m, "avo(a, Z)") == ["avo(a, c)", "avo(a, d)"]


def test_renomeacao_de_variaveis():
    # a mesma cláusula usada duas vezes no mesmo ramo exige variáveis novas
    m = motor("anc(X,Y) :- pai(X,Y). anc(X,Z) :- pai(X,Y), anc(Y,Z). pai(a,b). pai(b,c). pai(c,d).")
    assert resp(m, "anc(a, W)") == ["anc(a, b)", "anc(a, c)", "anc(a, d)"]


def test_deteccao_de_lacos_em_ciclo():
    prog = "alc(R,R) :- p(R). alc(R,S) :- h(R,T), alc(T,S). p(a). p(b). p(c). h(a,b). h(b,a). h(b,c)."
    m = motor(prog)
    assert sorted(resp(m, "alc(a, X)")) == ["alc(a, a)", "alc(a, b)", "alc(a, c)"]
    # consulta que falha precisa terminar (sem laço infinito)
    m2 = motor(prog)
    assert resp(m2, "alc(a, z)") == []
    assert m2.lacos, "o laço a -> b -> a deveria ter sido podado"


def test_limite_de_profundidade():
    m = motor("n(z). n(s(X)) :- n(X).", limite=5)
    assert m.provar(ler_termo("n(s(s(z)))"))
    assert m.provar(ler_termo("n(s(s(s(s(s(s(z)))))))")) is None
    assert m.limite_atingido


def test_negacao_por_falha():
    m = motor("ave(piu). ave(tux). pinguim(tux). voa(X) :- ave(X), \\+ pinguim(X).")
    assert resp(m, "voa(X)") == ["voa(piu)"]


def test_negacao_com_variavel_livre_e_recusada():
    m = motor("ave(piu). pinguim(tux). estranho :- \\+ pinguim(X).")
    with pytest.raises(ErroFloundering):
        m.provar(ler_termo("estranho"))
    with pytest.raises(ErroFloundering):
        m.provar(ler_termo("\\+ pinguim(X)"))


def test_embutidos():
    m = motor("faixa(H) :- H >= 8, H < 18. dif(X, Y) :- X \\= Y.")
    assert m.provar(ler_termo("faixa(8)")) and not m.provar(ler_termo("faixa(18)"))
    assert m.provar(ler_termo("dif(a, b)")) and not m.provar(ler_termo("dif(a, a)"))
    with pytest.raises(ErroInstanciacao):
        m.provar(ler_termo("faixa(X)"))


def test_ocorrencia_no_motor():
    m = motor("igual(X, X).")
    assert m.provar(ler_termo("igual(Y, f(Y))")) is None


def test_arvore_e_derivacao():
    m = motor("a :- b, c. b. c :- d. d.")
    s = m.provar(ler_termo("a"))
    arv = s.arvores()[0]
    assert [formatar(f.objetivo) for f in arv.filhos] == ["b", "c"]
    passos = derivacao(s)
    assert [formatar(p["selecionado"]) for p in passos] == ["a", "b", "c", "d"]
    assert passos[-1]["novo"] == []
