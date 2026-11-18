# M1 · Modelagem formal — Guardiões do acervo

Este documento descreve o vocabulário de primeira ordem, as regras com quantificadores explícitos, a forma clausal (com skolemização) e uma derivação por resolução com os unificadores de cada passo. As mesmas regras, em sintaxe Prolog, estão em [`regras/acervo.pl`](../regras/acervo.pl): esse é o único arquivo de regras do projeto, e ele é lido pelo SWI-Prolog, pelo motor Python e pelo grounder SAT.

## 1. Vocabulário

**Universo.** Pessoas, papéis, ações, tipos de recurso, recursos (incluindo os pedidos) e as horas 0..23. Vale a hipótese de **nomes únicos**: constantes distintas denotam objetos distintos.

**Constantes.** São tiradas da entrada: `bia`, `davi`, `coordenador`, `tecnico`, `ler`, `aprovar`, `catalogo`, `reserva_tecnica`, `emprestimo`, `p7`, `p8`, `0`, …, `23`.

**Predicados de entrada** (fatos gerados do JSON):

| Predicado | Aridade | Significado |
|---|---|---|
| `Papel(p, r)` | 2 | o papel *r* foi atribuído diretamente à pessoa *p* |
| `Herda(r₁, r₂)` | 2 | o papel *r₁* herda as permissões de *r₂* (a herança desce de *r₁* para *r₂*) |
| `Permissao(r, a, t)` | 3 | o papel *r* pode executar a ação *a* sobre recursos do tipo *t* |
| `Delega(d, p, a, t, i, f)` | 6 | *d* delega a *p* a ação *a* sobre o tipo *t* no intervalo [*i*, *f*) |
| `Solicitante(x, p)` | 2 | o pedido *x* foi feito pela pessoa *p* |
| `Tipo(x, t)` | 2 | o recurso *x* é do tipo *t* (todo pedido é do tipo `emprestimo`) |
| `Horario(t, i, f)` | 3 | recursos do tipo *t* só podem ser acessados em [*i*, *f*) |
| `ExcecaoHorario(r)` | 1 | o papel *r* está isento da restrição de horário |
| `AcaoDeControle(a)` | 1 | a ação *a* está sob separação de funções (padrão: `aprovar`) |
| `Proibicao(r, a, t)` | 3 | proibição explícita: o papel *r* não pode executar *a* sobre *t* |
| `Incompativel(r₁, r₂)` | 2 | ninguém pode exercer *r₁* e *r₂* ao mesmo tempo |
| `EPapel(r)`, `Pessoa(p)`, `Acao(a)`, `Hora(h)` | 1 | predicados de domínio (tipagem do universo finito) |
| `≥`, `<` | 2 | ordem usual dos inteiros (predicados interpretados) |

**Predicados derivados:**

| Predicado | Significado |
|---|---|
| `Alcanca(r, s)` | *s* é alcançável a partir de *r* pela herança (reflexivo e transitivo) |
| `TemPapel(p, r)` | *p* exerce o papel *r*, diretamente ou por herança |
| `PermissaoEfetiva(p, a, t)` | *p* tem a permissão (*a*, *t*) por algum dos seus papéis |
| `DelegacaoValida(p, a, t, h)` | à hora *h*, *p* recebeu (*a*, *t*) por uma delegação válida |
| `Permitido(p, a, x, h)` | existe uma permissão (por papel ou por delegação) para o pedido |
| `IsentoHorario(p)` | *p* exerce algum papel com exceção de horário |
| `Proibido(p, a, x, h)` | alguma proibição se aplica ao pedido |
| `Pode(p, a, x, h)` | **decisão**: permitido e não proibido |
| `Conflito(p, a, x, h)` | a política permite e proíbe a mesma coisa |
| `Violacao(v)`, `Aviso(v)` | restrição de integridade violada / configuração suspeita |

**Funções.** São construtores que dão nome às violações: `papeisIncompativeis/3`, `delegacaoIntervaloVazio/4`, `horarioVazio/1`, `cicloHeranca/1` e `delegacaoSemEfeito/4`. Na skolemização aparecem também funções novas: `g/1`, `k₁/4` e `k₂/4` (seção 3).

## 2. Regras em lógica de predicados

Existenciais no antecedente são equivalentes a universais na regra inteira: ∀x (∃y φ → ψ) ≡ ∀x∀y (φ → ψ) quando *y* não ocorre em ψ. Por isso, eles somem na forma clausal sem exigir skolemização.

```
R1a  ∀r ( EPapel(r) → Alcanca(r, r) )
R1b  ∀r ∀s ( ∃t (Herda(r, t) ∧ Alcanca(t, s)) → Alcanca(r, s) )
R1c  ∀p ∀r ( ∃r₀ (Papel(p, r₀) ∧ Alcanca(r₀, r)) → TemPapel(p, r) )
R1d  ∀p ∀a ∀t ( ∃r (TemPapel(p, r) ∧ Permissao(r, a, t)) → PermissaoEfetiva(p, a, t) )

R2   ∀p ∀a ∀t ∀h ( Hora(h) ∧ ∃d ∃i ∃f (Delega(d, p, a, t, i, f) ∧ h ≥ i ∧ h < f
                    ∧ PermissaoEfetiva(d, a, t)) → DelegacaoValida(p, a, t, h) )

R3a  ∀p ∀a ∀x ∀h ( Hora(h) ∧ ∃t (Tipo(x, t) ∧ PermissaoEfetiva(p, a, t)) → Permitido(p, a, x, h) )
R3b  ∀p ∀a ∀x ∀h ( Hora(h) ∧ ∃t (Tipo(x, t) ∧ DelegacaoValida(p, a, t, h)) → Permitido(p, a, x, h) )

R4   ∀p ∀a ∀x ∀h ( Hora(h) ∧ AcaoDeControle(a) ∧ Solicitante(x, p) → Proibido(p, a, x, h) )
R5a  ∀p ∀a ∀x ∀h ( Pessoa(p) ∧ Acao(a) ∧ Hora(h) ∧ ∃t ∃i ∃f (Tipo(x, t) ∧ Horario(t, i, f) ∧ h < i)
                    ∧ ¬IsentoHorario(p) → Proibido(p, a, x, h) )
R5b  ∀p ∀a ∀x ∀h ( Pessoa(p) ∧ Acao(a) ∧ Hora(h) ∧ ∃t ∃i ∃f (Tipo(x, t) ∧ Horario(t, i, f) ∧ h ≥ f)
                    ∧ ¬IsentoHorario(p) → Proibido(p, a, x, h) )
R5c  ∀p ( ∃r (TemPapel(p, r) ∧ ExcecaoHorario(r)) → IsentoHorario(p) )
R6   ∀p ∀a ∀x ∀h ( Hora(h) ∧ ∃t ∃r (Tipo(x, t) ∧ TemPapel(p, r) ∧ Proibicao(r, a, t)) → Proibido(p, a, x, h) )

R7   ∀p ∀a ∀x ∀h ( Permitido(p, a, x, h) ∧ ¬Proibido(p, a, x, h) → Pode(p, a, x, h) )
R8   ∀p ∀a ∀x ∀h ( Permitido(p, a, x, h) ∧ Proibido(p, a, x, h) → Conflito(p, a, x, h) )

V1   ∀p ∀r₁ ∀r₂ ( Incompativel(r₁, r₂) ∧ TemPapel(p, r₁) ∧ TemPapel(p, r₂) → Violacao(papeisIncompativeis(p, r₁, r₂)) )
V2   ∀d ∀p ∀a ∀t ( ∃i ∃f (Delega(d, p, a, t, i, f) ∧ i ≥ f) → Violacao(delegacaoIntervaloVazio(d, p, a, t)) )
V3   ∀t ( ∃i ∃f (Horario(t, i, f) ∧ i ≥ f) → Violacao(horarioVazio(t)) )
A1   ∀r ( ∃t (Herda(r, t) ∧ Alcanca(t, r)) → Aviso(cicloHeranca(r)) )
A2   ∀d ∀p ∀a ∀t ( ∃i ∃f Delega(d, p, a, t, i, f) ∧ ¬PermissaoEfetiva(d, a, t) → Aviso(delegacaoSemEfeito(d, p, a, t)) )

IC   ∀v ¬Violacao(v)                                      (restrição de integridade)
```

As cinco regras mínimas do enunciado ficam assim:
1. Herança transitiva: R1a–R1c. `Herda` só é percorrido de *r₁* para *r₂*, então "a herança desce".
2. Delegação com validade: R2. Ela exige o intervalo e que o delegante tenha a permissão por papel.
3. "Negar prevalece": R7, pelo literal ¬Proibido.
4. Ninguém aprova o próprio pedido: R4.
5. Reserva técnica das 8h às 18h, exceto segurança: R5a, R5b e R5c, com `Horario(reserva_tecnica, 8, 18)` e `ExcecaoHorario(seguranca)`.

## 3. Forma clausal

O procedimento padrão é: eliminar → e ↔, empurrar ¬ para dentro, mover os quantificadores para fora (forma prenex), skolemizar os ∃, descartar os ∀ e distribuir ∨ sobre ∧. As variáveis de cada cláusula são implicitamente universais, e cada cláusula usa variáveis próprias.

```
C1a  ¬EPapel(r) ∨ Alcanca(r, r)
C1b  ¬Herda(r, t) ∨ ¬Alcanca(t, s) ∨ Alcanca(r, s)
C1c  ¬Papel(p, r₀) ∨ ¬Alcanca(r₀, r) ∨ TemPapel(p, r)
C1d  ¬TemPapel(p, r) ∨ ¬Permissao(r, a, t) ∨ PermissaoEfetiva(p, a, t)
C2   ¬Hora(h) ∨ ¬Delega(d, p, a, t, i, f) ∨ ¬(h ≥ i) ∨ ¬(h < f) ∨ ¬PermissaoEfetiva(d, a, t) ∨ DelegacaoValida(p, a, t, h)
C3a  ¬Hora(h) ∨ ¬Tipo(x, t) ∨ ¬PermissaoEfetiva(p, a, t) ∨ Permitido(p, a, x, h)
C3b  ¬Hora(h) ∨ ¬Tipo(x, t) ∨ ¬DelegacaoValida(p, a, t, h) ∨ Permitido(p, a, x, h)
C4   ¬Hora(h) ∨ ¬AcaoDeControle(a) ∨ ¬Solicitante(x, p) ∨ Proibido(p, a, x, h)
C5a  ¬Pessoa(p) ∨ ¬Acao(a) ∨ ¬Hora(h) ∨ ¬Tipo(x, t) ∨ ¬Horario(t, i, f) ∨ ¬(h < i) ∨ IsentoHorario(p) ∨ Proibido(p, a, x, h)
C5b  ¬Pessoa(p) ∨ ¬Acao(a) ∨ ¬Hora(h) ∨ ¬Tipo(x, t) ∨ ¬Horario(t, i, f) ∨ ¬(h ≥ f) ∨ IsentoHorario(p) ∨ Proibido(p, a, x, h)
C5c  ¬TemPapel(p, r) ∨ ¬ExcecaoHorario(r) ∨ IsentoHorario(p)
C6   ¬Hora(h) ∨ ¬Tipo(x, t) ∨ ¬TemPapel(p, r) ∨ ¬Proibicao(r, a, t) ∨ Proibido(p, a, x, h)
C7   ¬Permitido(p, a, x, h) ∨ Proibido(p, a, x, h) ∨ Pode(p, a, x, h)          ← DOIS literais positivos
C8   ¬Permitido(p, a, x, h) ∨ ¬Proibido(p, a, x, h) ∨ Conflito(p, a, x, h)
CV1  ¬Incompativel(r₁, r₂) ∨ ¬TemPapel(p, r₁) ∨ ¬TemPapel(p, r₂) ∨ Violacao(papeisIncompativeis(p, r₁, r₂))
CIC  ¬Violacao(v)
```

**Por que negação por falha?** C5a, C5b e C7 não são cláusulas de Horn: cada uma tem dois literais positivos. Em lógica clássica, R7 não permite concluir `Pode(edu, ler, catalogo, 10)`, porque nada prova ¬Proibido. Para isso é preciso a **hipótese do mundo fechado**: tudo o que não é derivável é falso. Operacionalmente, ela vira a negação por falha (`\+` no Prolog e no motor Python). Logicamente, ela vira o **completamento de Clark**, que é a semântica que a camada SAT codifica.

**Completamento e skolemização.** O completamento troca cada → por ↔. Por exemplo, o de `IsentoHorario` é

```
∀p ( IsentoHorario(p) ↔ ∃r (TemPapel(p, r) ∧ ExcecaoHorario(r)) )
```

A direção ← é C5c. A direção → tem um **∃ no consequente**, dentro do escopo de ∀p, e por isso exige uma função de Skolem *g*:

```
∀p ( ¬IsentoHorario(p) ∨ ∃r (TemPapel(p, r) ∧ ExcecaoHorario(r)) )
⇝ ∀p ( ¬IsentoHorario(p) ∨ (TemPapel(p, g(p)) ∧ ExcecaoHorario(g(p))) )     [skolemização: r := g(p)]
⇝ S1  ¬IsentoHorario(p) ∨ TemPapel(p, g(p))
   S2  ¬IsentoHorario(p) ∨ ExcecaoHorario(g(p))
```

*g(p)* é "o papel que justifica a isenção de *p*". Da mesma forma, a parte → do completamento de `Proibido` (disjunção dos corpos de R4, R5a, R5b e R6) gera as funções de Skolem *k₁(p, a, x, h)* e *k₂(p, a, x, h)* para o tipo e o papel de R6, e assim por diante. Num domínio finito com nomes únicos, essas funções podem ser trocadas pela disjunção sobre as constantes do domínio. É isso que o *grounding* faz (seção 5).

## 4. Derivação por resolução (com unificadores)

**Consulta:** `Permitido(bia, editar, catalogo, 10)`, ou seja, "bia pode editar o catálogo às 10h?". O caso de aceitação 3 depende dela.

**Fatos usados** (gerados do JSON do enunciado):

```
F1 Hora(10)   F2 Tipo(catalogo, catalogo)   F3 Papel(bia, coordenador)
F4 Herda(coordenador, tecnico)   F5 EPapel(tecnico)   F6 Permissao(tecnico, editar, catalogo)
```

**Refutação.** Acrescentamos a negação da conclusão e derivamos a cláusula vazia □. A cada passo, uma cópia renomeada da cláusula de programa (variáveis com índice) é resolvida com o literal mais à esquerda. θ é o unificador mais geral entre esse literal e o literal positivo da cláusula.

| # | Resolvente | Cláusula usada (renomeada) | Unificador θ |
|---|---|---|---|
| 0 | ¬Permitido(bia, editar, catalogo, 10) | negação da conclusão | — |
| 1 | ¬Hora(10) ∨ ¬Tipo(catalogo, t₁) ∨ ¬PermissaoEfetiva(bia, editar, t₁) | C3a | {p₁↦bia, a₁↦editar, x₁↦catalogo, h₁↦10} |
| 2 | ¬Tipo(catalogo, t₁) ∨ ¬PermissaoEfetiva(bia, editar, t₁) | F1 | {} |
| 3 | ¬PermissaoEfetiva(bia, editar, catalogo) | F2 | {t₁↦catalogo} |
| 4 | ¬TemPapel(bia, r₂) ∨ ¬Permissao(r₂, editar, catalogo) | C1d | {p₂↦bia, a₂↦editar, t₂↦catalogo} |
| 5 | ¬Papel(bia, r₀₃) ∨ ¬Alcanca(r₀₃, r₂) ∨ ¬Permissao(r₂, editar, catalogo) | C1c | {p₃↦bia, r₃↦r₂} |
| 6 | ¬Alcanca(coordenador, r₂) ∨ ¬Permissao(r₂, editar, catalogo) | F3 | {r₀₃↦coordenador} |
| 7 | ¬Herda(coordenador, t₄) ∨ ¬Alcanca(t₄, r₂) ∨ ¬Permissao(r₂, editar, catalogo) | C1b | {r₄↦coordenador, s₄↦r₂} |
| 8 | ¬Alcanca(tecnico, r₂) ∨ ¬Permissao(r₂, editar, catalogo) | F4 | {t₄↦tecnico} |
| 9 | ¬EPapel(tecnico) ∨ ¬Permissao(tecnico, editar, catalogo) | C1a | {r₅↦tecnico, r₂↦tecnico} |
| 10 | ¬Permissao(tecnico, editar, catalogo) | F5 | {} |
| 11 | □ | F6 | {} |

A composição θ₁θ₂…θ₁₁ restrita às variáveis da consulta mostra a cadeia de papéis percorrida: bia → coordenador → técnico, com a permissão vindo de técnico. No passo 9, o unificador liga **duas** variáveis ao mesmo tempo: r₅ (da cópia de C1a) e r₂ (que vem do passo 4). A verificação de ocorrência é feita em todo passo. Aqui ela nunca dispara, mas tentar unificar, por exemplo, `Alcanca(r, r)` com `Alcanca(s, f(s))` falharia.

O motor gera essa mesma derivação passo a passo, com os unificadores calculados por ele:

```
python main.py --entrada casos/exemplo_enunciado.json --pergunta derivacao \
               --pessoa bia --acao editar --recurso catalogo --hora 10
```

O sistema faz a mesma pergunta sobre `Pode(...)`: a refutação acima e, em seguida, o literal `\+ Proibido(bia, editar, catalogo, 10)`. Esse literal é resolvido por uma sub-derivação que **falha finitamente** para todas as cláusulas de `Proibido` (C4: `AcaoDeControle(editar)` não é fato; C5a/C5b: não há `Horario(catalogo, …)`; C6: não há `Proibicao(_, editar, catalogo)`). No completamento, esse raciocínio é uma refutação clássica: com

`Proibido(bia, editar, catalogo, 10) ↔ (corpo de C4) ∨ (corpo de C5a) ∨ (corpo de C5b) ∨ (corpo de C6)`

e os completamentos dos predicados de entrada (por exemplo, `AcaoDeControle(a) ↔ a = aprovar`), obtém-se ¬Proibido(bia, editar, catalogo, 10) e então Pode(...) por C7. A camada SAT confirma a conclusão: KB ∧ ¬Pode(bia, editar, catalogo, 10) é insatisfazível (veja `--pergunta consequencia`).

## 5. Da lógica de predicados à lógica proposicional (M4)

1. **Grounding.** Cada regra é instanciada com as constantes da entrada, de baixo para cima, gerando só as instâncias cujos literais positivos podem ser verdadeiros. As comparações (`h ≥ i`) são avaliadas nesse momento. Cada átomo ground vira uma variável proposicional.
2. **Domínio das horas.** Todas as comparações têm a forma `h ≥ b` ou `h < b`, em que *b* é uma fronteira de intervalo. Por isso, horas entre duas fronteiras consecutivas se comportam igual, e basta um representante por faixa: 0, cada fronteira e as horas perguntadas.
3. **Completamento de Clark.** Cada átomo derivado *a* recebe a fórmula `a ↔ corpo₁ ∨ … ∨ corpoₖ`. Fatos certos viram cláusulas unitárias, e átomos impossíveis são falsos (mundo fechado).
4. **Recursão positiva (herança).** Com hierarquia cíclica, o completamento aceitaria modelos em que `Alcanca(curador, x)` e `Alcanca(conservador, x)` se justificam um ao outro sem base. Para cada componente fortemente conexa de tamanho *n* do grafo de dependências ground, usamos camadas `a@0 … a@n`, que calculam o menor ponto fixo em *n* iterações.
5. **Tseitin.** Uma variável nova por subfórmula dá uma FNC de tamanho linear e equissatisfazível. Como cada auxiliar é definida por ↔, a contagem de modelos também se preserva. O resultado pode ser exportado em DIMACS.
6. **DPLL** com propagação unitária e retrocesso responde às três perguntas:
   - **consistência:** KB ∧ ⋀ ¬Violacao(v) é satisfazível?
   - **consequência por refutação:** KB ∧ IC ∧ ¬φ é insatisfazível?
   - **contagem de modelos:** #DPLL exato. Sem fatos incertos, há 1 modelo (o do mundo fechado). Com grupos `um_de`, há um modelo por escolha compatível com as restrições.

## 6. Decisões de projeto e limitações

- **Intervalos semiabertos** [início, fim): "das 8h às 18h" admite 8h..17h. Um intervalo com início ≥ fim é uma violação. Por isso, intervalos que atravessam a meia-noite (22h–6h) precisam ser escritos como dois intervalos.
- **Delegação não transitiva.** O delegante precisa da permissão **por papel** (R2 usa `PermissaoEfetiva`). Uma delegação recebida não pode ser repassada (caso `proprio_06`).
- **Proibições por papel são herdadas**, como as permissões (caso `proprio_07`). A exceção de horário também é herdada (caso `proprio_08`).
- **Detecção de laços por variante de ancestral.** É correta e completa para estas regras (a recursão de `Alcanca` é linear à direita). Em programas arbitrários ela pode podar respostas, e a alternativa completa seria a tabulação (`:- table` no SWI-Prolog).
- **Negação por falha segura.** Um `\+ G` com variáveis livres gera um erro de *floundering* nos dois motores, em vez de uma resposta errada. As regras foram escritas para que todo literal negativo fique ground quando for selecionado.
- **Incerteza** só é aceita na forma "exatamente um de" para papéis e solicitantes. Ela é tratada pela camada SAT e por enumeração de mundos, e as duas vias precisam concordar.
