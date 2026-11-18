import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from acervo import prolog  # noqa: E402

CASOS = sorted((RAIZ / "casos").glob("*.json"))

precisa_prolog = pytest.mark.skipif(not prolog.disponivel(), reason="SWI-Prolog (swipl) não instalado")
