:- encoding(utf8).
% =====================================================================
%  Guardiões do acervo — regras do contexto (controle de acesso)
%
%  Este arquivo contém SOMENTE as regras. Os fatos de cada caso são
%  gerados automaticamente a partir do JSON de entrada
%  (python main.py --entrada X.json --pergunta fatos).
%
%  O mesmo arquivo é lido por três consumidores:
%    1. SWI-Prolog (via prolog/meta.pl);
%    2. o motor SLD próprio em Python (motor/);
%    3. o grounder da camada SAT (sat/grounding.py).
%  Por isso ele usa um subconjunto simples de Prolog: cláusulas de Horn,
%  negação por falha (\+) e comparações aritméticas.
%
%  Comentários "%@ Rx: texto" dão nome à cláusula seguinte; o nome
%  aparece nas explicações.
%
%  Convenção de horário: intervalos semiabertos [Inicio, Fim).
%  "das 8h às 18h" admite 8, 9, ..., 17; às 18h já está fechado.
% =====================================================================

:- dynamic papel/2, herda/2, permissao/3, delega/6, solicitante/2,
           tipo/2, horario/3, excecao_horario/1, acao_de_controle/1,
           proibicao/3, incompativel/2, e_papel/1, pessoa/1, acao/1,
           hora/1.

% ---------------------------------------------------------------------
% Herança de papéis (regra mínima 1)
% Herda(Sup, Inf): Sup herda as permissões de Inf ("a herança desce").
% ---------------------------------------------------------------------

%@ R1a: todo papel alcança a si mesmo
alcanca(R, R) :- e_papel(R).
%@ R1b: herança transitiva (desce na hierarquia)
alcanca(R, S) :- herda(R, T), alcanca(T, S).
%@ R1c: papéis alcançáveis a partir do papel atribuído
tem_papel(P, R) :- papel(P, R0), alcanca(R0, R).
%@ R1d: permissão efetiva obtida por papel
permissao_efetiva(P, A, T) :- tem_papel(P, R), permissao(R, A, T).

% ---------------------------------------------------------------------
% Delegação com validade (regra mínima 2)
% Só vale no intervalo [I, F) e só se o delegante tem a permissão por
% papel (delegação não é transitiva).
% ---------------------------------------------------------------------

%@ R2: delegação válida (no intervalo e com delegante habilitado)
delegacao_valida(P, A, T, H) :- hora(H), delega(D, P, A, T, I, F), H >= I, H < F, permissao_efetiva(D, A, T).

% ---------------------------------------------------------------------
% Permissões
% ---------------------------------------------------------------------

%@ R3a: permitido por papel
permitido(P, A, R, H) :- hora(H), tipo(R, T), permissao_efetiva(P, A, T).
%@ R3b: permitido por delegação
permitido(P, A, R, H) :- hora(H), tipo(R, T), delegacao_valida(P, A, T, H).

% ---------------------------------------------------------------------
% Proibições (regras mínimas 4 e 5, e proibições explícitas)
% ---------------------------------------------------------------------

%@ R4: separação de funções (ninguém aprova o próprio pedido)
proibido(P, A, R, H) :- hora(H), acao_de_controle(A), solicitante(R, P).
%@ R5a: restrição de horário — antes da abertura
proibido(P, A, R, H) :- pessoa(P), acao(A), hora(H), tipo(R, T), horario(T, I, _F), H < I, \+ isento_horario(P).
%@ R5b: restrição de horário — depois do fechamento
proibido(P, A, R, H) :- pessoa(P), acao(A), hora(H), tipo(R, T), horario(T, _I, F), H >= F, \+ isento_horario(P).
%@ R6: proibição explícita atribuída a um papel
proibido(P, A, R, H) :- hora(H), tipo(R, T), tem_papel(P, Ro), proibicao(Ro, A, T).
%@ R5c: isenção de horário por papel (também herdada)
isento_horario(P) :- tem_papel(P, R), excecao_horario(R).

% ---------------------------------------------------------------------
% Decisão (regra mínima 3: negar prevalece)
% ---------------------------------------------------------------------

%@ R7: decisão — permitido e não proibido (negar prevalece)
pode(P, A, R, H) :- permitido(P, A, R, H), \+ proibido(P, A, R, H).
%@ R8: conflito de política — a mesma coisa é permitida e proibida
conflito(P, A, R, H) :- permitido(P, A, R, H), proibido(P, A, R, H).

% ---------------------------------------------------------------------
% Restrições de integridade (violação => entrada inconsistente)
% ---------------------------------------------------------------------

%@ V1: pessoa acumula papéis incompatíveis
violacao(papeis_incompativeis(P, R1, R2)) :- incompativel(R1, R2), tem_papel(P, R1), tem_papel(P, R2).
%@ V2: delegação com intervalo vazio
violacao(delegacao_intervalo_vazio(D, P, A, T)) :- delega(D, P, A, T, I, F), I >= F.
%@ V3: horário de funcionamento vazio
violacao(horario_vazio(T)) :- horario(T, I, F), I >= F.

% ---------------------------------------------------------------------
% Avisos (configuração suspeita, mas a entrada continua utilizável)
% ---------------------------------------------------------------------

%@ A1: ciclo na hierarquia de papéis
aviso(ciclo_heranca(R)) :- herda(R, T), alcanca(T, R).
%@ A2: delegação sem efeito — o delegante não tem a permissão
aviso(delegacao_sem_efeito(D, P, A, T)) :- delega(D, P, A, T, _I, _F), \+ permissao_efetiva(D, A, T).
