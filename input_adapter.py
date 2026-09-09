"""입력 어댑터 — 물리 장치와 게임 로직 사이의 논리 버튼 계층.

게임은 키보드도 ESP32도 모른다. 아래 논리 버튼 8개만 본다.

    left  right  up  down  punch  kick  start  select

ESP32-S3 컨트롤러는 USB HID 키보드로 인식되며 아래 KEYBOARD_LAYOUTS 와
똑같은 키를 보낸다. 즉 이 어댑터 하나가 키보드와 실제 조작기를 모두 받는다.
전송 방식을 시리얼이나 UDP 로 바꾸더라도 Pad 계약만 지키면 게임은 그대로다.

held    : 지금 눌려 있는가.  이동처럼 누르는 동안 계속 필요한 입력에 쓴다.
pressed : 이번 프레임에 새로 눌렸는가.  점프·공격처럼 한 번만 반응할 입력에 쓴다.

pressed 를 KEYDOWN 이벤트가 아니라 프레임 간 상태 차이로 계산한다.
이벤트 전달 방식(OS 키 반복, 장치별 리포트 주기)에 판정이 좌우되지 않게
하기 위해서다. 어떤 어댑터를 끼워도 엣지 판정 규칙이 한 곳에만 존재한다.
"""

from __future__ import annotations

import sys

import pygame

from fonts import find_korean_font

BUTTONS = ("left", "right", "up", "down", "punch", "kick", "start", "select")


class Pad:
    """컨트롤러 한 대의 논리 버튼 상태."""

    __slots__ = ("held", "pressed")

    def __init__(self) -> None:
        self.clear()

    def clear(self) -> None:
        self.held = dict.fromkeys(BUTTONS, False)
        self.pressed = dict.fromkeys(BUTTONS, False)

    def feed(self, raw: dict[str, bool]) -> None:
        """이번 프레임의 원시 상태를 받아 held/pressed 를 갱신한다."""
        self.pressed = {b: raw[b] and not self.held[b] for b in BUTTONS}
        self.held = raw

    def any_pressed(self, *names: str) -> bool:
        return any(self.pressed[n] for n in names)


# 1P/2P 키보드 매핑. ESP32 펌웨어(firmware/fami_pad)가 보내는 키와 동일하므로
# 조작기를 꽂아도 이 표가 그대로 적용된다.
KEYBOARD_LAYOUTS = (
    {   # 1P
        "left": (pygame.K_a,),
        "right": (pygame.K_d,),
        "up": (pygame.K_w,),
        "down": (pygame.K_s,),
        "punch": (pygame.K_f,),
        "kick": (pygame.K_g,),
        "start": (pygame.K_RETURN, pygame.K_SPACE, pygame.K_p),
        "select": (pygame.K_ESCAPE,),
    },
    {   # 2P
        "left": (pygame.K_LEFT,),
        "right": (pygame.K_RIGHT,),
        "up": (pygame.K_UP,),
        "down": (pygame.K_DOWN,),
        "punch": (pygame.K_COMMA,),
        "kick": (pygame.K_PERIOD,),
        # 조작기에는 각자 Start/Select 가 달리지만 키보드 개발 환경에서는
        # 1P 와 같은 키를 공유한다. 게임이 "누가" 눌렀는지는 보지 않는다.
        "start": (pygame.K_RETURN, pygame.K_SPACE, pygame.K_p),
        "select": (pygame.K_ESCAPE,),
    },
)


class KeyboardAdapter:
    """키보드 상태를 논리 버튼으로 옮긴다. USB HID 조작기도 이 경로를 탄다."""

    name = "keyboard"

    def __init__(self, layouts=KEYBOARD_LAYOUTS) -> None:
        self.layouts = layouts
        self.pads = tuple(Pad() for _ in layouts)

    def poll(self) -> tuple[Pad, ...]:
        keys = pygame.key.get_pressed()
        for pad, layout in zip(self.pads, self.layouts):
            pad.feed({b: any(keys[k] for k in ks) for b, ks in layout.items()})
        return self.pads


# ESP32-S3 컨트롤러 배선. 실제 진실은 firmware/fami_pad/fami_pad.ino 에 있고
# 여기 표는 진단 화면이 "이 버튼은 몇 번 핀" 이라고 알려주기 위해 둔 사본이다.
ESP32_PINS = {
    "up": 4, "down": 5, "left": 6, "right": 7,
    "punch": 15, "kick": 16, "start": 17, "select": 18,
}
PLAYER_SELECT_PIN = 8          # 개방 = 1P, GND = 2P

# 진단 화면에 쓰는 한글 라벨. 배선하면서 보기 쉬우라고 물리 부품 이름으로 쓴다.
BUTTON_LABELS_KO = {
    "up": "위", "down": "아래", "left": "왼쪽", "right": "오른쪽",
    "punch": "펀치 A", "kick": "킥 B", "start": "START", "select": "SELECT",
}

# 조이스틱 → 버튼 순서로 보여 준다. 실제 조작기 배치와 같은 순서다.
DISPLAY_ORDER = ("up", "down", "left", "right", "punch", "kick", "start", "select")

# 같은 버튼이 이 시간 안에 두 번 눌리면 스위치 채터링으로 본다.
BOUNCE_WINDOW_MS = 40


def run_wiring_test() -> None:
    """배선 점검 화면. 게임을 켜지 않고 버튼 8개 x 2패드를 확인한다.

    각 버튼의 눌림 상태, 누적 입력 횟수, 채터링 의심 횟수를 함께 보여 준다.
    채터링 수치가 올라가면 스위치 불량이거나 배선이 길어 노이즈를 타는 것이다.
    """
    pygame.init()
    screen = pygame.display.set_mode((900, 470))
    pygame.display.set_caption("FAMI FIGHTERS - 배선 점검")
    clock = pygame.time.Clock()
    korean = find_korean_font()
    smooth = korean is not None
    font = pygame.font.Font(korean, 26 if korean else 24)
    head = pygame.font.Font(korean, 34)
    title = "조작기 배선 점검" if korean else "PAD WIRING TEST"
    guide = ("Q 또는 창 닫기로 종료   /   노이즈 값이 0보다 크면 스위치 불량이나 배선 문제"
             if korean else
             "Q or close window to quit   /   BOUNCE > 0 means a noisy switch")
    col_press = "입력" if korean else "PRESS"
    col_bounce = "노이즈" if korean else "BOUNCE"
    labels = BUTTON_LABELS_KO if korean else {b: b.upper() for b in BUTTONS}

    ink, dim, live, warn = (28, 31, 45), (150, 156, 170), (245, 191, 66), (220, 62, 64)
    paper, p1_color, p2_color = (244, 241, 222), (220, 62, 64), (55, 93, 180)

    adapter = KeyboardAdapter()
    counts = [dict.fromkeys(BUTTONS, 0) for _ in adapter.pads]
    bounces = [dict.fromkeys(BUTTONS, 0) for _ in adapter.pads]
    last_ms = [dict.fromkeys(BUTTONS, -BOUNCE_WINDOW_MS * 100) for _ in adapter.pads]

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_q):
                pygame.quit()
                return

        now = pygame.time.get_ticks()
        pads = adapter.poll()
        for i, pad in enumerate(pads):
            for b in BUTTONS:
                if pad.pressed[b]:
                    counts[i][b] += 1
                    if now - last_ms[i][b] < BOUNCE_WINDOW_MS:
                        bounces[i][b] += 1
                    last_ms[i][b] = now

        screen.fill(paper)
        screen.blit(head.render(title, smooth, ink), (40, 24))
        screen.blit(font.render(guide, smooth, dim), (40, 60))

        for i, pad in enumerate(pads):
            x = 40 + i * 440
            color = p1_color if i == 0 else p2_color
            screen.blit(head.render(f"{i + 1}P", smooth, color), (x, 100))
            screen.blit(font.render("GPIO", smooth, dim), (x + 62, 108))
            screen.blit(font.render(col_press, smooth, dim), (x + 250, 108))
            screen.blit(font.render(col_bounce, smooth, dim), (x + 318, 108))
            for row, b in enumerate(DISPLAY_ORDER):
                y = 140 + row * 38
                box = pygame.Rect(x, y, 26, 26)
                pygame.draw.rect(screen, color if pad.held[b] else paper, box)
                pygame.draw.rect(screen, ink, box, 2)
                screen.blit(font.render(str(ESP32_PINS[b]), smooth, dim), (x + 66, y + 5))
                screen.blit(font.render(labels[b], smooth, live if pad.held[b] else ink), (x + 110, y + 5))
                screen.blit(font.render(str(counts[i][b]), smooth, ink), (x + 252, y + 5))
                bounce = bounces[i][b]
                screen.blit(font.render(str(bounce), smooth, warn if bounce else dim), (x + 322, y + 5))

        pygame.display.flip()
        clock.tick(60)


if __name__ == "__main__":
    if "--test" in sys.argv:
        run_wiring_test()
    else:
        print("사용법: python3 input_adapter.py --test    (조작기 배선 점검 화면)")
