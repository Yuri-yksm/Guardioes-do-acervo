"""M5: a linha de comando responde a todas as perguntas."""
import pytest

import main
from conftest import RAIZ

EX = str(RAIZ / "casos" / "exemplo_enunciado.json")
INCERTO = str(RAIZ / "casos" / "proprio_03_papel_incerto.json")
INCONS = str(RAIZ / "casos" / "proprio_02_inconsistente_papeis.json")


def rodar(capsys, *args):
    cod = main.main(list(args))
    return cod, capsys.readouterr()


def test_pedido_curto(capsys):
    cod, out = rodar(capsys, "--entrada", EX, "--pergunta", "davi aprovar p8 10h")
    assert cod == 0 and "PERMITIDO" in out.out and "Substituições aplicadas" in out.out


def test_pedido_por_opcoes(capsys):
    cod, out = rodar(capsys, "--entrada", EX, "--pergunta", "pedido", "--pessoa", "bia",
                     "--acao", "ler", "--recurso", "reserva técnica", "--hora", "20h")
    assert cod == 0 and "NEGADO" in out.out and "R5b" in out.out


def test_consultas(capsys):
    cod, out = rodar(capsys, "--entrada", EX, "--pergunta", "consultas")
    assert cod == 0 and "10/10" in out.out


@pytest.mark.parametrize("pergunta", ["consistencia", "modelos", "conflitos", "validar", "dimacs"])
def test_perguntas_globais(capsys, pergunta):
    cod, out = rodar(capsys, "--entrada", EX, "--pergunta", pergunta)
    assert cod == 0 and out.out


def test_consequencia(capsys):
    cod, out = rodar(capsys, "--entrada", EX, "--pergunta", "consequencia", "--pessoa", "gil",
                     "--acao", "ler", "--recurso", "reserva_tecnica", "--hora", "20")
    assert "INSATISFAZÍVEL" in out.out and "é consequência" in out.out


def test_nao_unica_mostra_motivo(capsys):
    cod, out = rodar(capsys, "--entrada", INCERTO, "--pergunta", "hugo editar catalogo 10h")
    assert "SEM RESPOSTA ÚNICA" in out.out and "papel(hugo, tecnico)" in out.out


def test_inconsistente(capsys):
    cod, out = rodar(capsys, "--entrada", INCONS, "--pergunta", "dora pagar fatura 10h")
    assert "INCONSISTENTE" in out.out and "papeis_incompativeis" in out.out


def test_quem_resposta_nao_unica(capsys):
    cod, out = rodar(capsys, "--entrada", EX, "--pergunta", "quem", "--acao", "aprovar", "--recurso", "p8", "--hora", "10")
    assert "não única" in out.out and "bia, davi" in out.out


def test_derivacao(capsys):
    cod, out = rodar(capsys, "--entrada", EX, "--pergunta", "derivacao", "--pessoa", "bia",
                     "--acao", "editar", "--recurso", "catalogo", "--hora", "10")
    assert "□" in out.out and "θ1" in out.out


def test_consulta_com_floundering_da_erro(capsys):
    cod, out = rodar(capsys, "--entrada", EX, "--pergunta", "consulta", "--objetivo", "\\+ proibido(X, ler, catalogo, 10)")
    assert cod == 3 and "variáveis livres" in out.err


def test_entrada_invalida(tmp_path, capsys):
    f = tmp_path / "ruim.json"
    f.write_text('{"papeis": {"a": "b"}, "campo_estranho": 1}')
    cod, out = rodar(capsys, "--entrada", str(f), "--pergunta", "validar")
    assert cod == 1 and "campos desconhecidos" in out.err
