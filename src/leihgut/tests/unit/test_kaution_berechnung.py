"""Unit-Tests für BR-04: Kautionsberechnung.

Jeder Test referenziert Issue 0101 und BR-04.
Wertetabelle aus business-rules.adoc.
"""

import pytest

from leihgut.domain.regeln import berechne_kaution


# 0101 BR-04
@pytest.mark.parametrize(
    "wbw,erwartete_kaution",
    [
        (10, 5),    # unter Minimum → Minimum 5
        (25, 5),    # exakt Minimum-Grenze (25 * 0.20 = 5.0)
        (78, 16),   # kaufm. Runden: 15.6 → 16
        (77, 15),   # kaufm. Runden: 15.4 → 15
        (350, 70),  # Normalfall
        (498, 100), # Maximum-Grenze (498 * 0.20 = 99.6 → 100)
        (600, 100), # über Maximum → Maximum 100
    ],
)
def test_berechne_kaution(wbw: int, erwartete_kaution: int) -> None:
    # 0101
    assert berechne_kaution(wbw) == erwartete_kaution
