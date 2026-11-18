"""Caso 11: termos, átomos e cláusulas como dados; leitor de Prolog."""
import pytest

from acervo.base import regras
from motor.parser import ErroSintaxe, ler_programa, ler_termo
from motor.unificacao import variante
from motor.termos import NAO, Struct, Var, canonico, de_lista, formatar, lista


def test_termos_e_operadores():
    t = ler_termo("p(X, f(a, 10), [b, c | T])")
    assert t.nome == "p" and t.args[0] == Var("X")
    assert t.args[1] == Struct("f", (Struct("a"), 10))
    assert ler_termo("H >= I") == Struct(">=", (Var("H"), Var("I")))
    assert ler_termo("\\+ q(X)") == Struct(NAO, (Struct("q", (Var("X"),)),))
    assert ler_termo("\\+(q(X))") == ler_termo("\\+ q(X)")
    assert ler_termo("'pode/4#1'") == Struct("pode/4#1")
    assert de_lista(ler_termo("[a, b]")) == [Struct("a"), Struct("b")]


def test_clausulas_e_anotacoes():
    cs = ler_programa(":- dynamic p/1.\n%@ R: regra\nq(X) :- p(X), X > 1, \\+ r(X).\np(2).\n")
    assert len(cs) == 2
    r, f = cs
    assert r.nome == "R: regra" and len(r.corpo) == 3 and r.corpo[2].nome == NAO
    assert f.eh_fato


def test_canonico_ida_e_volta():
    for txt in ["no(pode(a, b, c, 10), 'pode/4#1', [no(\\+ x(1), naf, [])])", "f(X, [1, 2], 'A b')"]:
        t = ler_termo(txt)
        assert variante(ler_termo(canonico(t)), t)


def test_regras_do_contexto_sao_lidas():
    rs = regras()
    nomes = {c.nome.split(":")[0] for c in rs if c.nome}
    for r in ["R1a", "R1b", "R1c", "R1d", "R2", "R3a", "R3b", "R4", "R5a", "R5b", "R5c", "R6", "R7", "V1", "A1"]:
        assert r in nomes


def test_erro_de_sintaxe():
    with pytest.raises(ErroSintaxe):
        ler_programa("p(X :- q.")


def test_formatacao():
    assert formatar(ler_termo("pode(bia, ler, catalogo, 10)")) == "pode(bia, ler, catalogo, 10)"
    assert formatar(lista([1, 2])) == "[1, 2]"
