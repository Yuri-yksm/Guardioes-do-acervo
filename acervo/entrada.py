"""Leitura e validação do JSON de entrada e geração automática dos fatos.

Formato (extensão do exemplo do enunciado; todos os campos exceto
"papeis" são opcionais):

{
  "papeis":   {"bia": "coordenador",            # um papel
               "ana": ["tecnico", "seguranca"],  # vários papéis
               "hugo": {"um_de": ["tecnico", "estagiario"]}},   # incerto
  "herda":    [["coordenador", "tecnico"], ...],     # [superior, inferior]
  "permissoes": [["estagiario", "ler", "catalogo"], ...],  # [papel, ação, tipo]
  "delegacoes": [["bia", "davi", "aprovar", "emprestimo", 9, 12], ...],
  "pedidos":  {"p7": "davi",
               "p9": {"solicitante": "edu", "tipo": "emprestimo"},
               "p10": {"um_de": ["davi", "edu"]}},        # solicitante incerto
  "tipo_pedido": "emprestimo",          # tipo de recurso dos pedidos (padrão)
  "recursos": {"vitrine_3": "vitrine"}, # recursos extras: nome -> tipo
  "horarios": {"reserva_tecnica": [8, 18]},    # tipo -> [abre, fecha)
  "excecoes_de_horario": ["seguranca"],
  "acoes_de_controle": ["aprovar"],     # separação de funções (padrão: aprovar)
  "proibicoes": [["estagiario", "editar", "catalogo"]],   # [papel, ação, tipo]
  "papeis_incompativeis": [["tecnico", "seguranca"]],
  "consultas": [{"pessoa": "edu", "acao": "ler", "recurso": "catalogo",
                 "hora": 10, "esperado": "permitido"}]
  "esperado": {"consistente": true, "modelos": 1}    # usado pelos testes
}

Todo tipo que aparece em permissões/delegações/horários/proibições e que
não é o tipo dos pedidos vira também um recurso de mesmo nome
(tipo(catalogo, catalogo)).
"""
from __future__ import annotations

import itertools
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from motor.termos import Struct, atomo

CAMPOS = {
    "papeis", "herda", "permissoes", "delegacoes", "pedidos", "tipo_pedido", "recursos",
    "horarios", "excecoes_de_horario", "acoes_de_controle", "proibicoes",
    "papeis_incompativeis", "consultas", "esperado", "descricao",
}

HORAS = range(0, 24)


class ErroEntrada(ValueError):
    pass


def normalizar(nome) -> str:
    """'Reserva Técnica' -> 'reserva_tecnica' (constante Prolog válida)."""
    if not isinstance(nome, str) or not nome.strip():
        raise ErroEntrada(f"nome inválido: {nome!r}")
    s = unicodedata.normalize("NFKD", nome.strip()).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9_]+", "_", s).strip("_").lower()
    if not s or not s[0].isalpha():
        s = "c_" + s
    return s


def hora(v) -> int:
    if isinstance(v, bool):
        raise ErroEntrada(f"hora inválida: {v!r}")
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        m = re.fullmatch(r"\s*(\d{1,2})\s*(h|:00)?\s*", v)
        if m:
            return int(m.group(1))
    raise ErroEntrada(f"hora inválida: {v!r} (use um inteiro, como 10, ou '10h')")


@dataclass(frozen=True)
class Pedido:
    pessoa: str
    acao: str
    recurso: str
    hora: int

    @staticmethod
    def de(pessoa, acao, recurso, h) -> "Pedido":
        return Pedido(normalizar(pessoa), normalizar(acao), normalizar(recurso), hora(h))

    def atomo(self, pred: str = "pode") -> Struct:
        return atomo(pred, self.pessoa, self.acao, self.recurso, self.hora)

    def __str__(self) -> str:
        return f"{self.pessoa}, {self.acao}, {self.recurso}, {self.hora}h"


@dataclass
class GrupoIncerto:
    """Exatamente um dos átomos é verdadeiro (um_de)."""
    descricao: str
    atomos: list[Struct]


@dataclass
class Consulta:
    pedido: Pedido
    esperado: str | None = None


@dataclass
class Entrada:
    pessoas_papeis: dict[str, list[str]]
    herda: list[tuple[str, str]]
    permissoes: list[tuple[str, str, str]]
    delegacoes: list[tuple[str, str, str, str, int, int]]
    solicitantes: dict[str, str]
    tipos_pedido: dict[str, str]
    recursos: dict[str, str]
    horarios: dict[str, tuple[int, int]]
    excecoes: list[str]
    acoes_controle: list[str]
    proibicoes: list[tuple[str, str, str]]
    incompativeis: list[tuple[str, str]]
    incertos: list[GrupoIncerto] = field(default_factory=list)
    consultas: list[Consulta] = field(default_factory=list)
    esperado: dict = field(default_factory=dict)
    descricao: str = ""
    origem: str = ""

    # ------------------------------------------------------------------
    @staticmethod
    def de_arquivo(caminho) -> "Entrada":
        p = Path(caminho)
        try:
            dados = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ErroEntrada(f"{p}: JSON inválido ({e})") from e
        e = Entrada.de_dict(dados)
        e.origem = str(p)
        return e

    @staticmethod
    def de_dict(d: dict) -> "Entrada":
        if not isinstance(d, dict):
            raise ErroEntrada("a entrada deve ser um objeto JSON")
        extras = set(d) - CAMPOS
        if extras:
            raise ErroEntrada(f"campos desconhecidos: {sorted(extras)}")
        if "papeis" not in d:
            raise ErroEntrada("campo obrigatório ausente: papeis")
        N = normalizar
        incertos: list[GrupoIncerto] = []

        def tuplas(chave, n, conv):
            out = []
            for i, item in enumerate(d.get(chave, [])):
                if not isinstance(item, list) or len(item) != n:
                    raise ErroEntrada(f"{chave}[{i}]: esperava lista com {n} elementos, recebi {item!r}")
                out.append(tuple(c(x) for c, x in zip(conv, item)))
            return out

        pp: dict[str, list[str]] = {}
        for pessoa, v in d["papeis"].items():
            p = N(pessoa)
            if isinstance(v, str):
                pp[p] = [N(v)]
            elif isinstance(v, list) and v:
                pp[p] = [N(x) for x in v]
            elif isinstance(v, dict) and set(v) == {"um_de"} and v["um_de"]:
                pp[p] = []
                opcoes = [N(x) for x in v["um_de"]]
                incertos.append(GrupoIncerto(f"papel de {p} ∈ {{{', '.join(opcoes)}}}",
                                             [atomo("papel", p, r) for r in opcoes]))
            else:
                raise ErroEntrada(f"papeis.{pessoa}: use um papel, uma lista ou {{\"um_de\": [...]}}")

        tipo_pedido = N(d.get("tipo_pedido", "emprestimo"))
        sol, tipos_ped = {}, {}
        for ped, v in d.get("pedidos", {}).items():
            k = N(ped)
            if isinstance(v, str):
                sol[k], tipos_ped[k] = N(v), tipo_pedido
            elif isinstance(v, dict) and "um_de" in v:
                opcoes = [N(x) for x in v["um_de"]]
                tipos_ped[k] = N(v.get("tipo", tipo_pedido))
                incertos.append(GrupoIncerto(f"solicitante de {k} ∈ {{{', '.join(opcoes)}}}",
                                             [atomo("solicitante", k, x) for x in opcoes]))
            elif isinstance(v, dict) and "solicitante" in v:
                sol[k], tipos_ped[k] = N(v["solicitante"]), N(v.get("tipo", tipo_pedido))
            else:
                raise ErroEntrada(f"pedidos.{ped}: formato inválido")

        horarios = {}
        for t, v in d.get("horarios", {}).items():
            if not isinstance(v, list) or len(v) != 2:
                raise ErroEntrada(f"horarios.{t}: use [abre, fecha]")
            horarios[N(t)] = (hora(v[0]), hora(v[1]))

        consultas = []
        for i, c in enumerate(d.get("consultas", [])):
            try:
                ped = Pedido.de(c["pessoa"], c["acao"], c["recurso"], c["hora"])
            except KeyError as e:
                raise ErroEntrada(f"consultas[{i}]: falta o campo {e}") from e
            esp = c.get("esperado")
            if esp is not None and esp not in ("permitido", "negado", "nao_unica", "inconsistente"):
                raise ErroEntrada(f"consultas[{i}].esperado inválido: {esp!r}")
            consultas.append(Consulta(ped, esp))

        return Entrada(
            pessoas_papeis=pp,
            herda=tuplas("herda", 2, (N, N)),
            permissoes=tuplas("permissoes", 3, (N, N, N)),
            delegacoes=tuplas("delegacoes", 6, (N, N, N, N, hora, hora)),
            solicitantes=sol,
            tipos_pedido=tipos_ped,
            recursos={N(k): N(v) for k, v in d.get("recursos", {}).items()},
            horarios=horarios,
            excecoes=[N(x) for x in d.get("excecoes_de_horario", [])],
            acoes_controle=[N(x) for x in d.get("acoes_de_controle", ["aprovar"])],
            proibicoes=tuplas("proibicoes", 3, (N, N, N)),
            incompativeis=tuplas("papeis_incompativeis", 2, (N, N)),
            incertos=incertos,
            consultas=consultas,
            esperado=d.get("esperado", {}),
            descricao=d.get("descricao", ""),
        )

    # ------------------------------------------------------------------
    @property
    def tem_incerteza(self) -> bool:
        return bool(self.incertos)

    def _uniq(self, it):
        return list(dict.fromkeys(it))

    def papeis_conhecidos(self) -> list[str]:
        rs = [r for rs in self.pessoas_papeis.values() for r in rs]
        rs += [a.args[1].nome for g in self.incertos for a in g.atomos if a.nome == "papel"]
        rs += [x for par in self.herda for x in par]
        rs += [p[0] for p in self.permissoes] + self.excecoes
        rs += [p[0] for p in self.proibicoes] + [x for par in self.incompativeis for x in par]
        return self._uniq(rs)

    def pessoas(self) -> list[str]:
        ps = list(self.pessoas_papeis)
        ps += [x for dl in self.delegacoes for x in dl[:2]]
        ps += list(self.solicitantes.values())
        ps += [a.args[1].nome for g in self.incertos for a in g.atomos if a.nome == "solicitante"]
        return self._uniq(ps)

    def acoes(self) -> list[str]:
        a = [p[1] for p in self.permissoes] + [dl[2] for dl in self.delegacoes]
        a += [p[1] for p in self.proibicoes] + self.acoes_controle
        return self._uniq(a)

    def tipos_recurso(self) -> list[tuple[str, str]]:
        """Pares (recurso, tipo)."""
        pares = [(p, t) for p, t in self.tipos_pedido.items()]
        pares += list(self.recursos.items())
        ja = {r for r, _ in pares}
        tipos_pedido = set(self.tipos_pedido.values())
        tipos = [p[2] for p in self.permissoes] + [dl[3] for dl in self.delegacoes]
        tipos += list(self.horarios) + [p[2] for p in self.proibicoes] + list(self.recursos.values())
        for t in self._uniq(tipos):
            if t not in ja and t not in tipos_pedido:
                pares.append((t, t))
                ja.add(t)
        return pares

    def recursos_conhecidos(self) -> list[str]:
        return [r for r, _ in self.tipos_recurso()]

    def horas_criticas(self, extras=()) -> list[int]:
        """Representantes das faixas de horário que se comportam igual:
        0, cada fronteira de intervalo e as horas extras pedidas."""
        hs = {0}
        for dl in self.delegacoes:
            hs |= {dl[4], dl[5]}
        for i, f in self.horarios.values():
            hs |= {i, f}
        hs |= set(extras)
        return sorted(h for h in hs if h in HORAS)

    # ------------------------------------------------------------------
    def fatos(self, horas=HORAS) -> list[Struct]:
        """Fatos certos, em ordem determinística (a mesma vai para o Prolog)."""
        F: list[Struct] = []
        for p, rs in self.pessoas_papeis.items():
            F += [atomo("papel", p, r) for r in rs]
        F += [atomo("herda", a, b) for a, b in self.herda]
        F += [atomo("permissao", *p) for p in self.permissoes]
        F += [atomo("delega", *dl) for dl in self.delegacoes]
        F += [atomo("solicitante", k, v) for k, v in self.solicitantes.items()]
        F += [atomo("tipo", r, t) for r, t in self.tipos_recurso()]
        F += [atomo("horario", t, i, f) for t, (i, f) in self.horarios.items()]
        F += [atomo("excecao_horario", r) for r in self.excecoes]
        F += [atomo("acao_de_controle", a) for a in self.acoes_controle]
        F += [atomo("proibicao", *p) for p in self.proibicoes]
        F += [atomo("incompativel", a, b) for a, b in self.incompativeis]
        F += [atomo("e_papel", r) for r in self.papeis_conhecidos()]
        F += [atomo("pessoa", p) for p in self.pessoas()]
        F += [atomo("acao", a) for a in self.acoes()]
        F += [atomo("hora", h) for h in horas]
        return F

    def mundos(self):
        """Cada escolha possível para os grupos incertos: lista de átomos extras."""
        if not self.incertos:
            yield []
            return
        for escolha in itertools.product(*[g.atomos for g in self.incertos]):
            yield list(escolha)
