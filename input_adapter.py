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
        # 시스템 버튼도 플레이어별 키를 구분한다.
        "start": (pygame.K_F2,),
        "select": (pygame.K_F3,),
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
    from console_ui import ConsoleDisplay, BG, GOLD, MUTED, WHITE, P1, P2, PANEL, LINE
    ui = ConsoleDisplay()
    counts = [dict.fromkeys(BUTTONS, 0) for _ in range(2)]
    bounces = [dict.fromkeys(BUTTONS, 0) for _ in range(2)]
    last_ms = [dict.fromkeys(BUTTONS, -10000) for _ in range(2)]
    labels = BUTTON_LABELS_KO if ui.ko else {b: b.upper() for b in BUTTONS}
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_q):
                pygame.quit()
                return
        pads = ui.input.poll()
        if any(p.held['start'] and p.held['select'] for p in pads):
            pygame.quit()
            return
        now = pygame.time.get_ticks()
        ui.screen.fill(BG)
        ui.text(ui.label('컨트롤러 점검', 'CONTROLLER CHECK'), 32, 22, 28)
        ui.text('USB / GPIO', 624, 30, 18, GOLD)
        for i, pad in enumerate(pads):
            x = 24 + i * 388
            color = P1 if i == 0 else P2
            ui.panel((x, 78, 364, 338), fill=PANEL, border=LINE)
            ui.text(f'{i+1}P', x+16, 88, 28, color)
            ui.text('GPIO', x+172, 99, 14, MUTED)
            ui.text(ui.label('입력', 'PRESS'), x+240, 99, 14, MUTED)
            ui.text(ui.label('노이즈', 'NOISE'), x+296, 99, 14, MUTED)
            for row, button in enumerate(DISPLAY_ORDER):
                if pad.pressed[button]:
                    counts[i][button] += 1
                    if now-last_ms[i][button] < BOUNCE_WINDOW_MS:
                        bounces[i][button] += 1
                    last_ms[i][button] = now
                y = 136 + row * 33
                pygame.draw.circle(ui.screen, color if pad.held[button] else LINE, (x+24, y+11), 6)
                ui.text(labels[button], x+42, y, 18, WHITE)
                ui.text(str(ESP32_PINS[button]), x+185, y, 18, MUTED)
                ui.text(str(counts[i][button]), x+245, y, 18, color)
                ui.text(str(bounces[i][button]), x+310, y, 18, GOLD if bounces[i][button] else MUTED)
        ui.text(ui.label('같은 패드의 START + SELECT: 종료  /  키보드 Q',
                         'Same pad START + SELECT: Exit  /  Keyboard Q'),
                400, 439, 18, MUTED, center=True)
        ui.present()
        ui.clock.tick(60)


if __name__ == "__main__":
    if "--test" in sys.argv:
        run_wiring_test()
    else:
        print("사용법: python3 input_adapter.py --test    (조작기 배선 점검 화면)")
