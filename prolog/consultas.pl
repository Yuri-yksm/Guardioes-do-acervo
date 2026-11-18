:- encoding(utf8).
% =====================================================================
%  Consultas do contexto (M2) — todas passam pelo meta-interpretador,
%  que detecta laços na herança.
%
%  Uso direto no SWI-Prolog:
%    $ python main.py --entrada casos/exemplo_enunciado.json --pergunta fatos --saida /tmp/f.pl
%    $ swipl prolog/consultas.pl
%    ?- carregar_fatos('/tmp/f.pl').
%    ?- decide(davi, aprovar, p8, 10, D, Provas).
%    ?- quem_pode(aprovar, p8, 10, Pessoas).
%    ?- violacoes(V), avisos(A).
% =====================================================================

:- ensure_loaded(meta).

% Decisão com prova. Mesmo procedimento do Python (acervo/decisao.py):
%   permitido            -> [prova de pode/4]
%   negado(proibicao)    -> [prova de permitido/4, prova de proibido/4]
%   negado(sem_permissao)-> []
decide(P, A, R, H, permitido, [T]) :-
    prova(pode(P, A, R, H), T), !.
decide(P, A, R, H, negado(proibicao), [TP, TD]) :-
    prova(permitido(P, A, R, H), TP), !,
    prova(proibido(P, A, R, H), TD), !.
decide(_, _, _, _, negado(sem_permissao), []).

% Todas as respostas distintas de um objetivo (na ordem da busca).
respostas(G, Rs) :-
    findall(G, prova(G, _), Todas),
    sem_repetir(Todas, Rs).

sem_repetir([], []).
sem_repetir([X|Xs], [X|Ys]) :-
    exclude(==(X), Xs, Resto),
    sem_repetir(Resto, Ys).

quem_pode(A, R, H, Pessoas) :-
    respostas(pode(P, A, R, H), Rs),
    findall(P, member(pode(P, A, R, H), Rs), Pessoas).

papeis_de(P, Papeis) :-
    respostas(tem_papel(P, _), Rs),
    findall(R, member(tem_papel(_, R), Rs), Papeis).

violacoes(Vs) :- respostas(violacao(_), Rs), findall(V, member(violacao(V), Rs), Vs).
avisos(As)    :- respostas(aviso(_), Rs),    findall(A, member(aviso(A), Rs), As).
consistente   :- violacoes([]).
conflitos(Cs) :- respostas(conflito(_, _, _, _), Cs).
