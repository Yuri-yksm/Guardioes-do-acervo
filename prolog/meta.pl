:- encoding(utf8).
% =====================================================================
%  Meta-interpretador prova(Objetivo, Arvore)  — M2
%
%  Mesma estratégia do motor Python (motor/sld.py):
%    - seleção do literal mais à esquerda, cláusulas na ordem do programa;
%    - limite de profundidade (limite_profundidade/1);
%    - detecção de laços: objetivo variante (=@=) de um ancestral falha;
%    - negação por falha só para objetivos ground (senão: erro de
%      floundering); a sub-busca começa sem ancestrais.
%
%  Árvore:  no(Objetivo, Rotulo, Filhos)
%    Rotulo = fato | builtin | naf | 'pred/aridade#n' (n-ésima cláusula)
% =====================================================================

:- ensure_loaded('../regras/acervo').

:- dynamic limite_profundidade/1.
limite_profundidade(200).

prova(G, T) :-
    limite_profundidade(L),
    prova_lit(G, T, [], L).

prova_corpo(true, [], _, _) :- !.
prova_corpo((A, B), Ts, Anc, L) :- !,
    prova_corpo(A, TA, Anc, L),
    prova_corpo(B, TB, Anc, L),
    append(TA, TB, Ts).
prova_corpo(G, [T], Anc, L) :-
    prova_lit(G, T, Anc, L).

% negação por falha (hipótese do mundo fechado)
prova_lit(\+ G, no(\+ G, naf, []), _, _) :- !,
    (   ground(G) -> true ; throw(erro_floundering(G)) ),
    limite_profundidade(L0),
    \+ prova_lit(G, _, [], L0).
% embutidos de comparação e unificação
prova_lit(G, no(G, builtin, []), _, _) :-
    embutido(G), !,
    call(G).
% resolução com uma cláusula do programa
prova_lit(G, no(G, Rot, Filhos), Anc, L) :-
    (   L =< 0 -> nb_setval(limite_atingido, true), fail ; true ),
    \+ ( member(A, Anc), A =@= G ),
    L1 is L - 1,
    clause(G, Corpo, Ref),
    rotulo(G, Corpo, Ref, Rot),
    prova_corpo(Corpo, Filhos, [G|Anc], L1).

embutido(G) :-
    functor(G, N, 2),
    memberchk(N, [<, >, =<, >=, =:=, =\=, =, \=]).

rotulo(_, true, _, fato) :- !.
rotulo(G, _, Ref, Rot) :-
    functor(G, N, A),
    functor(Modelo, N, A),
    nth_clause(Modelo, K, Ref), !,
    format(atom(Rot), '~w/~w#~w', [N, A, K]).

% ---------------------------------------------------------------------
% Carregamento dos fatos gerados a partir do JSON
% ---------------------------------------------------------------------

predicados_de_entrada([papel/2, herda/2, permissao/3, delega/6, solicitante/2,
                       tipo/2, horario/3, excecao_horario/1, acao_de_controle/1,
                       proibicao/3, incompativel/2, e_papel/1, pessoa/1, acao/1,
                       hora/1]).

limpar_fatos :-
    predicados_de_entrada(Ps),
    forall(member(N/A, Ps), (functor(H, N, A), retractall(H))).

carregar_fatos(Arquivo) :-
    limpar_fatos,
    setup_call_cleanup(open(Arquivo, read, S, [encoding(utf8)]),
                       ler_fatos(S),
                       close(S)).

ler_fatos(S) :-
    read_term(S, T, []),
    (   T == end_of_file -> true
    ;   assertz(T), ler_fatos(S)
    ).
