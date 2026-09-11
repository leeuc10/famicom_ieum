"""FAMI CONSOLE 공용 팔레트.

런처와 두 게임이 한 기기의 화면처럼 보이려면 색이 한곳에서 나와야 한다.
특히 1P/2P 색은 게임마다 달라지면 관람객이 자기 쪽을 헷갈리므로,
여기 정한 두 색을 모든 화면이 그대로 쓴다.
"""

from __future__ import annotations

# 배경 5단계. 위로 갈수록 밝다. 패널을 겹칠 때 이 순서대로 올린다.
INK = (14, 16, 25)          # 가장 어두운 바탕·테두리
BG = (20, 23, 34)           # 화면 바탕
PANEL = (29, 33, 46)        # 카드 바탕
PANEL_HI = (43, 49, 66)     # 선택된 카드 / 떠 있는 패널
LINE = (62, 67, 82)         # 구분선

WHITE = (242, 240, 229)     # 본문
MUTED = (160, 167, 183)     # 보조 설명
GOLD = (255, 204, 102)      # 강조 한 가지. 남발하면 강조가 아니게 된다.
EMBER = (214, 138, 74)      # 노을·바닥 반사광

P1 = (235, 102, 108)
P1_DIM = (128, 52, 60)
P2 = (102, 187, 220)
P2_DIM = (44, 96, 128)

SKIN = (255, 206, 168)


def shade(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    """같은 색의 밝기만 바꾼다. 음영용 색을 따로 상수로 두지 않기 위해서."""
    return tuple(min(255, max(0, round(channel * factor))) for channel in color)


def mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    """a 에서 b 로 t(0~1) 만큼 섞는다. 그라데이션에 쓴다."""
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))
