:- encoding(utf8).
% =====================================================================
%  Ponte Python <-> SWI-Prolog (usada por acervo/prolog.py e pelos testes)
%
%  swipl -q prolog/ponte.pl -- FATOS.pl CONSULTAS.pl
%
%  CONSULTAS.pl contém termos:
%    decidir(Id, Pessoa, Acao, Recurso, Hora).
%    todas(Id, Objetivo).
%    limite(N).
%  Para cada consulta é impressa uma linha  r(Id, Resultado).
%  em write_canonical, que o parser Python lê.
% =====================================================================

:- ensure_loaded(consultas).
:- initialization(main, main).

main :-
    current_prolog_flag(argv, [Fatos, Consultas|_]),
    carregar_fatos(Fatos),
    setup_call_cleanup(open(Consultas, read, S, [encoding(utf8)]), processar(S), close(S)).

processar(S) :-
    read_term(S, T, []),
    (   T == end_of_file -> true
    ;   executar(T), processar(S)
    ).

executar(limite(N)) :- !,
    retractall(limite_profundidade(_)),
    assertz(limite_profundidade(N)).
executar(C) :-
    arg(1, C, Id),
    nb_setval(limite_atingido, false),
    catch(resultado(C, R), E, R = erro(E)),
    nb_getval(limite_atingido, Lim),
    emitir(r(Id, R, Lim)).

resultado(decidir(_, P, A, Rec, H), decisao(D, Provas)) :-
    decide(P, A, Rec, H, D, Provas).
resultado(todas(_, G), respostas(Rs, Arvore)) :-
    respostas(G, Rs),
    (   prova(G, T) -> Arvore = T ; Arvore = nenhuma ).

emitir(T) :-
    write_canonical(T), write('.'), nl, flush_output.
