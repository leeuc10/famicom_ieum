"""한글 폰트 탐색.

라즈베리파이 기본 이미지에는 한글 폰트가 없을 수 있다. 이름만 보고 고르면
글리프가 없는 폰트를 집어 화면이 빈 네모로 깨지므로, 실제 렌더 결과까지
확인한 뒤에 돌려준다. 못 찾으면 None 을 주고 호출한 쪽이 영문으로 물러난다.
"""

from __future__ import annotations

from pathlib import Path

import pygame

# 직접 넣은 폰트를 최우선으로 쓴다. 픽셀 폰트(갈무리 등)를 여기 두면
# 페미컴 느낌을 유지하면서 한글을 쓸 수 있다.
FONT_DIR = Path(__file__).parent / "assets" / "fonts"

# 시스템에 설치된 한글 폰트 후보. 앞에 있을수록 우선한다.
# 라즈베리파이는 fonts-nanum, 데스크톱 리눅스는 noto, macOS 는 Apple 계열이 잡힌다.
KOREAN_FONTS = (
    "nanumgothic", "nanumbarungothic", "nanumsquare",
    "notosanscjkkr", "notosanskr", "notosansmonocjkkr",
    "applesdgothicneo", "applegothic", "malgungothic",
)


def _draws_hangul(path: str | None) -> bool:
    """폰트 이름만 믿지 않고 한글이 실제로 그려지는지 확인한다.

    글리프가 없는 폰트는 .notdef(빈 네모)를 대신 그리는데, 이름 매칭만으로는
    이를 걸러낼 수 없다. 같은 폰트로 그린 .notdef 와 픽셀이 같으면 탈락시킨다.
    """
    try:
        pygame.font.init()          # 호출 순서에 상관없이 동작하게. 이미 켜져 있으면 무시된다.
        font = pygame.font.Font(path, 28)
        sample = font.render("한글", False, (255, 255, 255), (0, 0, 0))
        notdef = font.render("\uffff\uffff", False, (255, 255, 255), (0, 0, 0))
    except Exception:
        return False
    if sample.get_size() != notdef.get_size():
        return True
    return pygame.image.tostring(sample, "RGB") != pygame.image.tostring(notdef, "RGB")


def find_korean_font() -> str | None:
    """쓸 수 있는 한글 폰트 경로. 못 찾으면 None."""
    pygame.font.init()              # match_font 는 폰트 서브시스템이 켜져 있어야 한다.
    if FONT_DIR.is_dir():
        for path in sorted(FONT_DIR.iterdir()):
            if path.suffix.lower() in (".ttf", ".otf", ".ttc") and _draws_hangul(str(path)):
                return str(path)
    for name in KOREAN_FONTS:
        path = pygame.font.match_font(name)
        if path and _draws_hangul(path):
            return path
    return None
