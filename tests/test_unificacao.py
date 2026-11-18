"""Caso 19: unificação, verificação de ocorrência, composição de substituições."""
import itertools
import random

from motor.parser import ler_termo
from motor.termos import Struct, Var, eh_ground
from motor.unificacao import aplicar, compor, idempotente, mgu, substituir, unificar, variante

T = ler_termo


def test_unifica_simples():
    s = mgu(T("p(X, b)"), T("p(a, Y)"))
    assert s == {Var("X"): Struct("a"), Var("Y"): Struct("b")}


def test_falha_por_simbolo_e_aridade():
    assert mgu(T("p(a)"), T("p(b)")) is None
    assert mgu(T("p(a)"), T("q(a)")) is None
    assert mgu(T("p(a)"), T("p(a, b)")) is None
    assert mgu(T("p(1)"), T("p(a)")) is None


def test_verificacao_de_ocorrencia():
    assert mgu(T("X"), T("f(X)")) is None
    assert mgu(T("p(X, X)"), T("p(Y, f(Y))")) is None
    # sem a verificação, o algoritmo aceitaria (termo infinito)
    assert unificar(T("X"), T("f(X)"), {}, verificar_ocorrencia=False) is not None


def test_mgu_encadeado_e_idempotente():
    a, b = T("p(X, Y, Z)"), T("p(Y, Z, a)")
    s = mgu(a, b)
    assert aplicar(a, s) == aplicar(b, s) == T("p(a, a, a)")
    assert idempotente(s) == s
    for t in s.values():
        assert not (set(s) & set(_vars(t)))


def test_mgu_mais_geral():
    s = mgu(T("f(X, g(Y))"), T("f(g(Z), W)"))
    assert aplicar(T("f(X, g(Y))"), s) == T("f(g(Z), g(Y))")


def _vars(t):
    from motor.termos import variaveis
    return list(variaveis(t))


def test_composicao_propriedade():
    sigma = {Var("X"): T("f(Y)"), Var("Z"): T("a")}
    theta = {Var("Y"): T("b"), Var("X"): T("c"), Var("W"): T("Z")}
    c = compor(sigma, theta)
    for t in [T("g(X, Y, Z, W)"), T("h(X)"), T("W")]:
        assert substituir(t, c) == substituir(substituir(t, sigma), theta)
    # o exemplo clássico: X/f(Y) seguido de Y/b dá X/f(b), Y/b
    assert c[Var("X")] == T("f(b)") and c[Var("Y")] == T("b")
    assert Var("Z") in c and c[Var("Z")] == T("a")


def test_composicao_aleatoria():
    rnd = random.Random(7)
    nomes = ["X", "Y", "Z", "W"]

    def termo(d=0):
        r = rnd.random()
        if d > 2 or r < 0.3:
            return Var(rnd.choice(nomes))
        if r < 0.5:
            return Struct(rnd.choice("abc"))
        return Struct(rnd.choice("fg"), tuple(termo(d + 1) for _ in range(rnd.randint(1, 2))))

    for _ in range(300):
        a, b = termo(), termo()
        s = mgu(a, b)
        if s is not None:
            assert aplicar(a, s) == aplicar(b, s)
            # composição com outra substituição
            th = mgu(termo(), termo()) or {}
            t = termo()
            assert substituir(t, compor(s, th)) == substituir(substituir(t, s), th)


def test_variante():
    assert variante(T("p(X, Y, X)"), T("p(A, B, A)"))
    assert not variante(T("p(X, Y, X)"), T("p(A, B, B)"))
    assert not variante(T("p(X, X)"), T("p(A, B)"))
    assert not variante(T("p(X)"), T("p(a)"))
    assert variante(T("alcanca(coordenador, R)"), T("alcanca(coordenador, S)"))
