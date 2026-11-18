"""Substituições e unificação (Caso 19).

Uma substituição é um dict Var -> Termo. O motor usa a forma
*triangular* (uma ligação pode apontar para outra variável ligada) por
eficiência; `aplicar` percorre a cadeia até o fim. Para exibir e
comparar, `idempotente` produz a forma em que nenhum termo da imagem
contém variáveis do domínio.

Funções principais
  unificar(t1, t2, s)  -> s' ou None   (com verificação de ocorrência)
  mgu(t1, t2)          -> unificador mais geral idempotente ou None
  compor(sigma, theta) -> sigma∘theta  (aplicar sigma e depois theta)
  variante(t1, t2)     -> t1 e t2 são iguais a menos de renomeação?
"""
from __future__ import annotations

from .termos import Struct, Termo, Var

Subst = dict


def walk(t: Termo, s: Subst) -> Termo:
    while isinstance(t, Var) and t in s:
        t = s[t]
    return t


def aplicar(t: Termo, s: Subst) -> Termo:
    t = walk(t, s)
    if isinstance(t, Struct) and t.args:
        return Struct(t.nome, tuple(aplicar(a, s) for a in t.args))
    return t


def substituir(t: Termo, s: Subst) -> Termo:
    """Aplicação SIMULTÂNEA tσ (definição dos livros): cada variável do
    domínio é trocada uma única vez pela sua imagem. Coincide com
    `aplicar` quando σ é idempotente (como os mgus)."""
    if isinstance(t, Var):
        return s.get(t, t)
    if isinstance(t, Struct) and t.args:
        return Struct(t.nome, tuple(substituir(a, s) for a in t.args))
    return t


def ocorre(v: Var, t: Termo, s: Subst) -> bool:
    """Verificação de ocorrência: v aparece em t (sob s)?"""
    pilha = [t]
    while pilha:
        x = walk(pilha.pop(), s)
        if x == v:
            return True
        if isinstance(x, Struct):
            pilha.extend(x.args)
    return False


def unificar(a: Termo, b: Termo, s: Subst | None = None, verificar_ocorrencia: bool = True) -> Subst | None:
    """Algoritmo de Robinson iterativo. Devolve uma NOVA substituição que
    estende `s`, ou None se os termos não unificam."""
    s = dict(s) if s else {}
    pilha = [(a, b)]
    while pilha:
        x, y = pilha.pop()
        x = walk(x, s)
        y = walk(y, s)
        if x is y or (type(x) is type(y) and x == y):
            continue
        if isinstance(x, Var):
            if verificar_ocorrencia and ocorre(x, y, s):
                return None
            s[x] = y
        elif isinstance(y, Var):
            if verificar_ocorrencia and ocorre(y, x, s):
                return None
            s[y] = x
        elif isinstance(x, Struct) and isinstance(y, Struct):
            if x.nome != y.nome or len(x.args) != len(y.args):
                return None
            pilha.extend(zip(x.args, y.args))
        else:  # int x Struct, ou ints diferentes
            return None
    return s


def idempotente(s: Subst) -> Subst:
    r = {v: aplicar(v, s) for v in s}
    return {v: t for v, t in r.items() if t != v}


def mgu(a: Termo, b: Termo) -> Subst | None:
    s = unificar(a, b, {})
    return None if s is None else idempotente(s)


def compor(sigma: Subst, theta: Subst) -> Subst:
    """Composição σθ:  t(σθ) = (tσ)θ  para todo termo t (aplicação simultânea).
      σθ = { x/(xσ)θ : x ∈ dom σ, x ≠ (xσ)θ } ∪ { y/yθ : y ∈ dom θ − dom σ }"""
    r: Subst = {}
    for x, t in sigma.items():
        u = substituir(t, theta)
        if u != x:
            r[x] = u
    for y, t in theta.items():
        if y not in sigma and t != y:
            r[y] = t
    return r


def restringir(s: Subst, vs) -> Subst:
    return {v: aplicar(v, s) for v in vs if aplicar(v, s) != v}


def variante(a: Termo, b: Termo) -> bool:
    """a e b são variantes (iguais a menos de renomeação bijetiva)?"""
    ida: dict = {}
    volta: dict = {}
    pilha = [(a, b)]
    while pilha:
        x, y = pilha.pop()
        if isinstance(x, Var) or isinstance(y, Var):
            if not (isinstance(x, Var) and isinstance(y, Var)):
                return False
            if ida.setdefault(x, y) != y or volta.setdefault(y, x) != x:
                return False
        elif isinstance(x, Struct) and isinstance(y, Struct):
            if x.nome != y.nome or len(x.args) != len(y.args):
                return False
            pilha.extend(zip(x.args, y.args))
        elif type(x) is not type(y) or x != y:
            return False
    return True


def formatar_subst(s: Subst) -> str:
    from .termos import formatar
    if not s:
        return "{}"
    return "{" + ", ".join(f"{formatar(v)} ↦ {formatar(t)}" for v, t in s.items()) + "}"
