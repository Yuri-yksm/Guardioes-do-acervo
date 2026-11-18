"""Todos os arquivos de casos/: consultas com resposta esperada e
expectativas globais (consistência, número de modelos, violações,
avisos e conflitos)."""
import pytest

from acervo.decisao import decidir, verificar
from acervo.entrada import Entrada
from motor.termos import formatar
from sat.camada import CamadaSAT

from conftest import CASOS, precisa_prolog

PARES = [(c, i) for c in CASOS for i in range(len(Entrada.de_arquivo(c).consultas))]


def _id(par):
    c, i = par
    return f"{c.stem}#{i}"


@pytest.mark.parametrize("par", PARES, ids=[_id(p) for p in PARES])
def test_consulta_python(par):
    caminho, i = par
    e = Entrada.de_arquivo(caminho)
    c = e.consultas[i]
    assert decidir(e, c.pedido, "python").resultado == c.esperado


@precisa_prolog
@pytest.mark.parametrize("par", PARES, ids=[_id(p) for p in PARES])
def test_consulta_prolog(par):
    caminho, i = par
    e = Entrada.de_arquivo(caminho)
    c = e.consultas[i]
    assert decidir(e, c.pedido, "prolog").resultado == c.esperado


@pytest.mark.parametrize("caminho", CASOS, ids=[c.stem for c in CASOS])
def test_expectativas_globais(caminho):
    e = Entrada.de_arquivo(caminho)
    esp = e.esperado
    c = CamadaSAT(e)
    if "consistente" in esp:
        assert c.consistente() == esp["consistente"]
    if "modelos" in esp:
        assert c.contar_modelos() == esp["modelos"]
        # a contagem bate com a enumeração projetada nos fatos incertos
        assert len(c.mundos(maximo=1000)) == esp["modelos"] or (esp["modelos"] == 0 and not c.consistente())
    if not e.tem_incerteza:
        viol, avis = verificar(e)
        assert (not viol) == c.consistente()   # SLD e SAT concordam na consistência
        if "violacoes" in esp:
            assert sorted(map(formatar, viol)) == sorted(esp["violacoes"])
        if "avisos" in esp:
            assert sorted(map(formatar, avis)) == sorted(esp["avisos"])
    if "conflitos" in esp:
        pares = {(k.regra_permite.split(":")[0], k.regra_nega.split(":")[0]) for k in c.conflitos()}
        for a, b in esp["conflitos"]:
            assert (a, b) in pares


def test_ha_pelo_menos_oito_casos_proprios_com_inconsistente_e_nao_unica():
    proprios = [Entrada.de_arquivo(c) for c in CASOS if c.stem.startswith("proprio_")]
    assert len(proprios) >= 8
    esperados = {c.esperado for e in proprios for c in e.consultas}
    assert {"inconsistente", "nao_unica"} <= esperados
