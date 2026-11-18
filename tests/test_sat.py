"""M4: FNC, Tseitin, DIMACS, DPLL, contagem — conferidos por força bruta
(e por pycosat, se estiver instalado)."""
import itertools
import random

import pytest

from sat.dpll import DPLL
from sat.formula import (E, Equiv, Imp, Nao, Ou, P, Tseitin, Vocabulario, atomos, avaliar,
                         fnc_distributiva, ler_dimacs, nnf, para_dimacs)


def forca_bruta(cls, n):
    tot, algum = 0, None
    for bits in itertools.product([False, True], repeat=n):
        v = {i + 1: b for i, b in enumerate(bits)}
        if all(any(v[abs(l)] == (l > 0) for l in c) for c in cls):
            tot += 1
            algum = algum or v
    return tot, algum


def cnf_aleatoria(rnd, n, m, k=3):
    return [[rnd.choice([-1, 1]) * rnd.randint(1, n) for _ in range(rnd.randint(1, k))] for _ in range(m)]


def test_dpll_contra_forca_bruta():
    rnd = random.Random(42)
    for _ in range(400):
        n = rnd.randint(1, 8)
        cls = cnf_aleatoria(rnd, n, rnd.randint(1, 30))
        tot, _ = forca_bruta(cls, n)
        r = DPLL(cls, n)
        m = r.resolver()
        assert (m is not None) == (tot > 0)
        if m:
            assert all(any(m[abs(l)] == (l > 0) for l in c) for c in cls)
        assert r.contar() == tot


def test_dpll_assumpcoes_e_enumeracao():
    cls = [[1, 2], [-1, 3]]
    r = DPLL(cls, 3)
    assert r.resolver([-2])[1] is True
    assert r.resolver([-3, -2]) is None
    ms = r.enumerar([1, 2, 3], 100)
    assert len(ms) == forca_bruta(cls, 3)[0] == 4


def test_clausula_vazia_e_tautologia():
    assert DPLL([[]], 1).resolver() is None
    assert DPLL([[1, -1]], 1).contar() == 2


def formula_aleatoria(rnd, nomes, d=0):
    if d > 3 or rnd.random() < 0.3:
        return P(rnd.choice(nomes))
    op = rnd.choice(["n", "e", "o", "i", "q"])
    f = lambda: formula_aleatoria(rnd, nomes, d + 1)
    return {"n": lambda: Nao(f()), "e": lambda: E(f(), f()), "o": lambda: Ou(f(), f()),
            "i": lambda: Imp(f(), f()), "q": lambda: Equiv(f(), f())}[op]()


def test_fnc_distributiva_equivalente():
    rnd = random.Random(1)
    nomes = ["p", "q", "r"]
    for _ in range(200):
        f = formula_aleatoria(rnd, nomes)
        cnf = fnc_distributiva(f)
        for bits in itertools.product([False, True], repeat=3):
            v = dict(zip(nomes, bits))
            assert avaliar(f, v) == avaliar(nnf(f), v)
            assert avaliar(f, v) == all(any(v[n] == pol for n, pol in c) for c in cnf)


def test_tseitin_preserva_modelos():
    """Tseitin é equissatisfazível e, como cada auxiliar é definida por ↔,
    o número de modelos é o mesmo da fórmula original."""
    rnd = random.Random(3)
    nomes = ["p", "q", "r", "s"]
    for _ in range(150):
        f = formula_aleatoria(rnd, nomes)
        voc = Vocabulario()
        for x in nomes:
            voc.id(x)
        ts = Tseitin(voc)
        ts.afirmar(f)
        orig = sum(avaliar(f, dict(zip(nomes, b))) for b in itertools.product([False, True], repeat=4))
        assert DPLL(ts.clausulas, len(voc)).contar() == orig


def test_dimacs_ida_e_volta():
    cls = [[1, -2], [2, 3, -1], [3]]
    txt = para_dimacs(cls, 3, ["teste"])
    assert txt.startswith("c teste\np cnf 3 3")
    assert ler_dimacs(txt) == (3, cls)


def test_confere_com_pycosat():
    pycosat = pytest.importorskip("pycosat")
    rnd = random.Random(9)
    for _ in range(200):
        n = rnd.randint(3, 25)
        cls = cnf_aleatoria(rnd, n, rnd.randint(5, 90))
        esperado = pycosat.solve(cls) != "UNSAT"
        assert DPLL(cls, n).satisfazivel() == esperado
        if n <= 12:
            assert DPLL(cls, n).contar() == sum(1 for _ in pycosat.itersolve(cls, vars=n))


def test_formula_str():
    assert str(Imp(P("a"), Ou(P("b"), Nao(P("c"))))) == "a → (b ∨ ¬c)"
    assert atomos(Equiv(P("a"), E(P("b"), P("c")))) == {"a", "b", "c"}
