# Guardiões do acervo — controle de acesso por regras

Trabalho final de Lógica para Computação, **contexto 4**. O museu precisa decidir, a cada pedido, se uma pessoa pode executar uma ação sobre um recurso num dado horário. O sistema responde **permitido** ou **negado** e mostra a cadeia de regras usada: papéis percorridos, delegação usada, proibição aplicada e substituições.

A ideia central do projeto é que **as regras são escritas uma única vez**, em [`regras/acervo.pl`](regras/acervo.pl). Esse mesmo arquivo é carregado por três consumidores, que precisam chegar às mesmas respostas (os testes conferem isso em todo o domínio):

| Consumidor | Módulo | O que faz |
|---|---|---|
| SWI-Prolog | `prolog/` (M2) | meta-interpretador `prova(Objetivo, Arvore)` e consultas `decide/6`, `quem_pode/4`, … |
| Motor próprio em Python | `motor/` (M3) | termos, unificação com verificação de ocorrência, resolução SLD, negação por falha |
| Camada SAT | `sat/` (M4) | grounding, completamento de Clark, Tseitin, DIMACS, DPLL, contagem de modelos |

## Instalação

```bash
python3 --version              # 3.10 ou superior
pip install -r requirements.txt   # pytest (e pycosat, usado só para conferir o DPLL nos testes)
sudo apt install swi-prolog-nox   # opcional: sem ele, os testes do Prolog são pulados
```

## Como rodar

```bash
pytest                                   # todos os testes (≈ 290, ~25 s)

python main.py --entrada casos/exemplo_enunciado.json --pergunta "davi aprovar p8 10h"
python main.py --entrada casos/exemplo_enunciado.json --pergunta consultas --motor ambos
```

### Perguntas disponíveis (`--pergunta`)

| Pergunta | O que responde |
|---|---|
| `"pessoa acao recurso 10h"` ou `pedido --pessoa … --acao … --recurso … --hora …` | decisão com prova, regras, substituições e diagnóstico |
| `consultas` | todas as consultas do JSON numa tabela, conferindo o campo `esperado` |
| `quem --acao A --recurso R --hora H` | `?- pode(P, A, R, H).` (avisa quando a resposta não é única) |
| `consulta --objetivo "tem_papel(bia, X)"` | qualquer objetivo Prolog, com a primeira prova |
| `derivacao` (pedido ou `--objetivo`) | refutação SLD passo a passo: resolventes, cláusulas renomeadas, unificadores |
| `validar` | violações de integridade e avisos (ciclos, delegações sem efeito) |
| `consistencia` | SAT: a entrada é consistente? |
| `consequencia` (pedido) | SAT: o pedido é consequência? E a sua negação? (refutação) |
| `modelos` | #DPLL: quantos modelos existem (e quais são, se houver fatos incertos) |
| `conflitos` | bônus: pares de regras que permitem e negam a mesma coisa; papéis incompatíveis |
| `dimacs --saida x.cnf` | FNC exportada em DIMACS |
| `fatos --saida x.pl` | fatos Prolog gerados do JSON |

Opções: `--motor python|prolog|ambos` (padrão `python`; `ambos` confere um contra o outro), `--limite N` (profundidade da busca SLD, padrão 200) e `--resumo` (omite as substituições).

### Exemplo de saída

```
$ python main.py --entrada casos/exemplo_enunciado.json --pergunta "davi aprovar p7 10h" --resumo
Pedido: davi pode aprovar p7 às 10h?   (motor: python)
Resposta: NEGADO — proibição prevalece: R4: separação de funções (ninguém aprova o próprio pedido)

Prova da permissão:
  [1] permitido(davi, aprovar, p7, 10)   ⟸ R3b: permitido por delegação
  ├─ hora(10)   ⟸ fato
  ├─ tipo(p7, emprestimo)   ⟸ fato
  └─ [2] delegacao_valida(davi, aprovar, emprestimo, 10)   ⟸ R2: delegação válida (no intervalo e com delegante habilitado)
     ├─ hora(10)   ⟸ fato
     ├─ delega(bia, davi, aprovar, emprestimo, 9, 12)   ⟸ fato
     ├─ 10 >= 9   ⟸ comparação
     ├─ 10 < 12   ⟸ comparação
     └─ [3] permissao_efetiva(bia, aprovar, emprestimo)   ⟸ R1d: permissão efetiva obtida por papel
        ...
Prova da proibição (que prevalece):
  [6] proibido(davi, aprovar, p7, 10)   ⟸ R4: separação de funções (ninguém aprova o próprio pedido)
  ├─ hora(10)   ⟸ fato
  ├─ acao_de_controle(aprovar)   ⟸ fato
  └─ solicitante(p7, davi)   ⟸ fato

Papéis percorridos: bia: coordenador
Delegação usada: bia → davi: aprovar emprestimo, válida em [9h, 12h)
Proibição aplicada: R4: separação de funções (ninguém aprova o próprio pedido)
```

## Formato da entrada (JSON)

É o exemplo do enunciado, mais campos opcionais. A descrição completa está em [`acervo/entrada.py`](acervo/entrada.py).

```jsonc
{
  "papeis": {"bia": "coordenador", "lia": ["tecnico", "comissao"],
             "hugo": {"um_de": ["tecnico", "estagiario"]}},          // incerteza
  "herda": [["coordenador", "tecnico"]],                             // [superior, inferior]
  "permissoes": [["tecnico", "editar", "catalogo"]],                 // [papel, ação, tipo]
  "delegacoes": [["bia", "davi", "aprovar", "emprestimo", 9, 12]],   // [de, para, ação, tipo, início, fim)
  "pedidos": {"p7": "davi", "p9": {"um_de": ["bia", "davi"]}},       // pedidos são do tipo "emprestimo"
  "horarios": {"reserva_tecnica": [8, 18]},
  "excecoes_de_horario": ["seguranca"],
  "acoes_de_controle": ["aprovar"],                 // separação de funções (padrão)
  "proibicoes": [["estagiario", "editar", "catalogo"]],
  "papeis_incompativeis": [["tesoureiro", "auditor"]],
  "recursos": {"vitrine_3": "vitrine"},
  "consultas": [{"pessoa": "edu", "acao": "ler", "recurso": "catalogo", "hora": 10, "esperado": "permitido"}],
  "esperado": {"consistente": true, "modelos": 1}
}
```

Nomes com acento ou espaço são normalizados (`"reserva técnica"` → `reserva_tecnica`), e as horas aceitam `10` ou `"10h"`.

## Casos

| Arquivo | O que explora |
|---|---|
| `exemplo_enunciado.json` | os **10 casos de aceitação** |
| `proprio_01_ciclo_heranca` | ciclo curador ↔ conservador: detectado (aviso), a busca termina e as respostas estão certas; SAT com codificação em camadas |
| `proprio_02_inconsistente_papeis` | **entrada inconsistente**: o diretor herda papéis incompatíveis |
| `proprio_03_papel_incerto` | **resposta não única**: hugo é técnico *ou* estagiário (2 modelos) |
| `proprio_04_solicitante_incerto` | resposta não única pela separação de funções |
| `proprio_05_bordas_horario` | limites de [8, 18) e [9, 12); hora inválida (25) |
| `proprio_06_delegacao_sem_efeito` | delegante sem permissão (aviso); delegação não é transitiva |
| `proprio_07_proibicao_explicita` | proibição herdada vence permissão; conflito R3a × R6 detectado pelo SAT |
| `proprio_08_excecao_herdada` | exceção de horário herdada pelo chefe de segurança |
| `proprio_09_inconsistente_intervalos` | delegação e horário com intervalo vazio |
| `proprio_10_multiplos_papeis` | vários papéis, recurso com tipo próprio, duas ações de controle |
| `proprio_11_incerteza_com_restricao` | as restrições eliminam um mundo e a resposta volta a ser única |

Resultado: **todos os casos de aceitação e todas as 44 consultas dos casos próprios passam**, nos três caminhos (Python, Prolog e SAT).

## Testes (M6)

| Arquivo | Cobre |
|---|---|
| `test_aceitacao.py` | os 10 casos do enunciado, com resposta **e motivo**, nos três caminhos |
| `test_casos.py` | todas as consultas de `casos/`, consistência, nº de modelos, violações, avisos e conflitos esperados |
| `test_equivalencia.py` | Python × Prolog × SAT em **todo** pedido pessoa × ação × recurso × hora; árvores de prova iguais nó a nó; consultas abertas com as mesmas respostas na mesma ordem |
| `test_unificacao.py` | mgu, verificação de ocorrência, composição (propriedade t(σθ) = (tσ)θ), variantes |
| `test_sld.py` | renomeação, laços, limite de profundidade, negação por falha, floundering |
| `test_sat.py` | DPLL e #DPLL contra força bruta e pycosat; FNC distributiva equivalente; Tseitin preserva modelos; DIMACS |
| `test_cli.py` | todas as perguntas da linha de comando |

`pycosat` e `swipl` só são usados para **conferir** resultados nos testes. Unificação, resolução e DPLL são implementações próprias.

## Estrutura

```
regras/acervo.pl        regras do contexto (fonte única)
prolog/meta.pl          meta-interpretador prova/2 (laços, limite, NAF segura) e carregamento de fatos
prolog/consultas.pl     decide/6, quem_pode/4, violacoes/1, avisos/1, conflitos/1
prolog/ponte.pl         execução em lote chamada pelo Python
motor/termos.py         Caso 11 — termos, átomos, cláusulas
motor/unificacao.py     Caso 19 — unificação, ocorrência, composição
motor/parser.py         leitor do subconjunto de Prolog
motor/sld.py            resolução SLD, árvore de prova, derivação linear
sat/formula.py          fórmulas, NNF, FNC distributiva, Tseitin, DIMACS (Casos 12–14)
sat/dpll.py             DPLL, contagem e enumeração de modelos
sat/grounding.py        instanciação das regras no domínio finito
sat/codificacao.py      completamento de Clark + camadas para recursão
sat/camada.py           consistência, consequência, modelos, conflitos
acervo/                 entrada JSON, decisão, explicação, ponte Prolog
docs/modelagem.md       M1: vocabulário, regras em LPO, forma clausal, skolemização, derivação
```

## Como a ementa aparece

| Item | Onde |
|---|---|
| Lógica proposicional | `sat/`: átomos ground como variáveis, FNC, DPLL |
| Linguagem e semântica | vocabulário em `docs/modelagem.md`; modelo do mundo fechado; completamento |
| Sistemas dedutivos | árvores de prova (Prolog e Python) em toda resposta |
| Aspectos computacionais | fórmulas como dados, FNC, Tseitin, DIMACS, DPLL |
| Princípio da resolução | `--pergunta consequencia` (refutação SAT) e a derivação em `docs/modelagem.md` §4 |
| Lógica de predicados | `regras/acervo.pl`: regras escritas uma vez, valendo para qualquer entrada |
| Substituição e resolução | `motor/`: mgu com ocorrência, composição, SLD com renomeação, laços e limite |

## Decisões e limitações

Estão detalhadas em [`docs/modelagem.md` §6](docs/modelagem.md#6-decisões-de-projeto-e-limitações): intervalos semiabertos, delegação não transitiva, proibições herdadas, detecção de laços por variante de ancestral (a alternativa completa seria a tabulação) e incerteza restrita a `um_de`.

## Para a defesa (entrada nova ao vivo)

1. Escrever o JSON no formato acima (os campos opcionais podem ser omitidos).
2. `python main.py --entrada novo.json --pergunta validar`: consistência, ciclos, delegações sem efeito.
3. `python main.py --entrada novo.json --pergunta "pessoa acao recurso 10h" --motor ambos`: decisão nos dois motores.
4. `--pergunta conflitos`, `--pergunta modelos` e `--pergunta derivacao` para as perguntas de lógica.
