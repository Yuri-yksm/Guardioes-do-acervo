"""Execução das consultas no SWI-Prolog (M2) e conversão das respostas.

Os fatos são gerados do JSON por `Entrada.fatos()` e gravados num .pl
temporário; o SWI-Prolog carrega regras/acervo.pl + prolog/meta.pl e
responde em write_canonical, que lemos com motor.parser.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from motor.parser import ler_termo
from motor.termos import Struct, Termo, canonico, de_lista
from motor.sld import NoProva

from .base import RAIZ
from .entrada import Entrada, Pedido

PONTE = RAIZ / "prolog" / "ponte.pl"


class ErroProlog(RuntimeError):
    pass


def disponivel() -> bool:
    return shutil.which("swipl") is not None


def escrever_fatos(fatos, caminho) -> None:
    linhas = ["% Fatos gerados automaticamente a partir do JSON de entrada.",
              "% Não edite: rode  python main.py --entrada X.json --pergunta fatos"]
    linhas += [canonico(f) + "." for f in fatos]
    Path(caminho).write_text("\n".join(linhas) + "\n", encoding="utf-8")


def arvore_de_termo(t: Termo) -> NoProva:
    """no(Objetivo, Rotulo, Filhos) -> NoProva"""
    assert isinstance(t, Struct) and t.nome == "no" and len(t.args) == 3, t
    obj, rot, filhos = t.args
    return NoProva(obj, rot.nome, [arvore_de_termo(f) for f in de_lista(filhos)])


@dataclass
class RespostaProlog:
    termo: Termo
    limite_atingido: bool


def executar(fatos, consultas: list[Termo], limite: int = 200, timeout: int = 60) -> list[RespostaProlog]:
    if not disponivel():
        raise ErroProlog("swipl não encontrado no PATH (instale o SWI-Prolog)")
    with tempfile.TemporaryDirectory() as d:
        ff, fc = Path(d) / "fatos.pl", Path(d) / "consultas.pl"
        escrever_fatos(fatos, ff)
        fc.write_text(f"limite({limite}).\n" + "".join(canonico(c) + ".\n" for c in consultas), encoding="utf-8")
        proc = subprocess.run(["swipl", "-q", str(PONTE), "--", str(ff), str(fc)],
                              capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise ErroProlog(f"swipl terminou com código {proc.returncode}:\n{proc.stderr}")
    out = []
    for linha in proc.stdout.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        r = ler_termo(linha)
        _id, res, lim = r.args
        out.append(RespostaProlog(res, lim == Struct("true")))
    if len(out) != len(consultas):
        raise ErroProlog(f"esperava {len(consultas)} respostas, recebi {len(out)}\n{proc.stderr}")
    return out


def decidir_lote(e: Entrada, pedidos: list[Pedido], extras=(), limite: int = 200):
    """Para cada pedido: (decisao, [arvores]) onde decisao é
    'permitido' | 'negado(proibicao)' | 'negado(sem_permissao)'."""
    cs = [Struct("decidir", (Struct(f"q{i}"), *p.atomo().args)) for i, p in enumerate(pedidos)]
    res = executar(e.fatos() + list(extras), cs, limite)
    out = []
    for r in res:
        t = r.termo
        if t.nome == "erro":
            raise ErroProlog(f"erro no Prolog: {t}")
        dec, provas = t.args
        nome = dec.nome if not dec.args else f"{dec.nome}({dec.args[0].nome})"
        out.append((nome, [arvore_de_termo(a) for a in de_lista(provas)]))
    return out


def consultar(e: Entrada, objetivo: Termo, extras=(), limite: int = 200):
    """(lista de respostas, árvore da primeira prova ou None)
    Erros de execução (ex.: floundering) voltam como ErroProlog."""
    res = executar(e.fatos() + list(extras), [Struct("todas", (Struct("q0"), objetivo))], limite)[0]
    t = res.termo
    if t.nome == "erro":
        raise ErroProlog(str(t.args[0]))
    rs, arv = t.args
    return de_lista(rs), (None if arv == Struct("nenhuma") else arvore_de_termo(arv))
