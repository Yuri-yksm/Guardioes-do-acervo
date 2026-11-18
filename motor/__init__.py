"""Motor de inferência próprio (M3): termos, unificação e resolução SLD."""
from .termos import Clausula, Struct, Var, atomo, formatar
from .unificacao import aplicar, compor, mgu, unificar, variante
from .parser import ler_programa, ler_termo
from .sld import BaseConhecimento, ErroFloundering, Motor

__all__ = [
    "Clausula", "Struct", "Var", "atomo", "formatar",
    "aplicar", "compor", "mgu", "unificar", "variante",
    "ler_programa", "ler_termo",
    "BaseConhecimento", "ErroFloundering", "Motor",
]
