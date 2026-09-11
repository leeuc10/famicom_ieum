"""두 명이 한 화면에서 겨루는 2D 대전 격투 프로토타입 (Raspberry Pi 용).

입력은 input_adapter 가 논리 버튼 8개로 정규화해 넘겨준다.
이 파일은 키보드인지 ESP32 조작기인지 알지 못한다.
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass

import pygame

from fonts import find_korean_font
from input_adapter import KeyboardAdapter, Pad

WIDTH, HEIGHT, FPS = 960, 540, 60
# 프레임이 한 번 크게 튀어도 공격 판정이 한 프레임에 통째로 소진되지 않게
# dt 에 상한을 둔다. 라즈베리파이에서 순간적인 부하가 걸릴 때를 위한 것이다.
MAX_DT = 0.05
HUD_H = 92        # 상단 정보 막대 높이. 한글 세 줄이 들어갈 만큼 잡는다.

# 한글 폰트를 못 찾았을 때 빈 네모를 띄우는 대신 영문으로 물러난다.
# 전시 중에 글자가 깨져 보이는 것보다 낫다.
STRINGS_KO = {
    "subtitle": "2인용 대전 격투 프로토타입",
    "begin": "START 또는 A / B  :  대전 시작",
    "p1_keys": "1P   조이스틱 W A S D      A: F      B: G",
    "p2_keys": "2P   조이스틱 방향키       A: ,      B: .",
    "system": "SELECT: 타이틀        START + SELECT: 종료",
    "rule": "2선승제",
    "round": "라운드 {n}",
    "p1_round_win": "1P 라운드 획득",
    "p2_round_win": "2P 라운드 획득",
    "draw": "무승부",
    "next_round": "다음 라운드",
    "pause": "일시정지",
    "resume": "START : 계속하기",
    "p1_wins": "1P 승리!",
    "p2_wins": "2P 승리!",
    "rematch": "START / A / B : 다시 대전        SELECT : 타이틀",
}

STRINGS_EN = {
    "subtitle": "2 PLAYER FIGHTING PROTOTYPE",
    "begin": "START  or  A / B  :  BEGIN MATCH",
    "p1_keys": "1P   JOYSTICK W A S D    A: F    B: G",
    "p2_keys": "2P   JOYSTICK ARROWS    A: ,    B: .",
    "system": "SELECT: TITLE       START + SELECT: QUIT",
    "rule": "FIRST TO 2 ROUNDS WINS",
    "round": "ROUND {n}",
    "p1_round_win": "P1 ROUND WIN",
    "p2_round_win": "P2 ROUND WIN",
    "draw": "DRAW",
    "next_round": "NEXT ROUND",
    "pause": "PAUSE",
    "resume": "START : RESUME",
    "p1_wins": "P1 WINS!",
    "p2_wins": "P2 WINS!",
    "rematch": "START / A / B : REMATCH      SELECT : TITLE",
}
GROUND_Y = 430
FIGHTER_W, FIGHTER_H = 52, 86
MOVE_SPEED, JUMP_SPEED, GRAVITY = 260, -580, 1500
ROUND_TIME = 60.0
WHITE, INK, RED = (244, 241, 222), (28, 31, 45), (220, 62, 64)
BLUE, GOLD, SKY, GRASS = (55, 93, 180), (245, 191, 66), (100, 190, 228), (73, 160, 97)


@dataclass(frozen=True)
class AttackSpec:
    """공격 하나의 타이밍·판정·피해를 한곳에 모은 표.

    startup 동안은 판정이 없고, active 동안만 상대를 맞힐 수 있으며,
    recovery 동안은 아무것도 할 수 없다. hitstun 은 맞은 쪽이 굳는 시간이다.

    이득 프레임 = hitstun - (명중 후 남은 active + recovery).
    명중이 active 첫 프레임에 나기 때문에 남은 판정 프레임도 때린 쪽의
    구속 시간에 들어간다는 점에 주의한다. 이 값이 다음 공격의 startup 을
    넘어서면 맞은 쪽이 되받아칠 수 없는 무한 연타가 된다.
    """

    startup: float
    active: float
    recovery: float
    hitstun: float
    damage: int
    push: int
    reach: int
    height: int
    offset: int

    @property
    def duration(self) -> float:
        return self.startup + self.active + self.recovery


ATTACKS = {
    # 위 정의로 실측한 이득은 펀치 +0F, 킥 +2F 로 각자의 startup(3F, 6F)보다
    # 작다. 즉 맞은 쪽이 항상 되받아칠 수 있다. 가드를 넣기 전까지는
    # 때린 쪽에 이득을 더 주지 않는 편이 연타 우위를 막는 데 유리하다.
    "punch": AttackSpec(0.05, 0.06, 0.13, 0.18, 8, 24, 44, 28, 25),
    "kick": AttackSpec(0.10, 0.08, 0.16, 0.26, 13, 40, 62, 18, 58),
}


class Fighter:
    def __init__(self, name: str, color: tuple[int, int, int], x: int, facing: int) -> None:
        self.name, self.color = name, color
        self.start_x, self.facing = x, facing
        self.reset()

    def reset(self) -> None:
        # 위치는 실수로 들고 rect 는 렌더링·판정용으로만 파생시킨다.
        # int 좌표에 직접 더하면 매 프레임 소수점이 잘려 실효 속도가 프레임 레이트를 탄다.
        self.x = float(self.start_x)
        self.y = float(GROUND_Y - FIGHTER_H)
        self.rect = pygame.Rect(self.start_x, GROUND_Y - FIGHTER_H, FIGHTER_W, FIGHTER_H)
        self.velocity_y = 0.0
        self.health = 100
        self.attack = ""
        self.attack_time = 0.0
        self.attack_connected = False
        self.hitstun = 0.0
        self.hit_flash = 0.0

    def sync_rect(self) -> None:
        self.rect.topleft = (round(self.x), round(self.y))

    @staticmethod
    def clamp_x(x: float) -> float:
        return min(max(x, 16.0), WIDTH - 16.0 - FIGHTER_W)

    @property
    def on_ground(self) -> bool:
        return self.y + FIGHTER_H >= GROUND_Y

    @property
    def attacking(self) -> bool:
        return self.attack_time > 0

    @property
    def stunned(self) -> bool:
        return self.hitstun > 0

    @property
    def busy(self) -> bool:
        return self.attacking or self.stunned

    @property
    def attack_active(self) -> bool:
        """판정이 실제로 나가 있는 구간인지. 발동·경직 중에는 맞지 않는다."""
        if not self.attacking:
            return False
        spec = ATTACKS[self.attack]
        elapsed = spec.duration - self.attack_time
        return spec.startup <= elapsed < spec.startup + spec.active

    def try_jump(self) -> None:
        if self.on_ground and not self.busy:
            self.velocity_y = JUMP_SPEED

    def start_attack(self, kind: str) -> None:
        if not self.busy:
            self.attack = kind
            self.attack_time = ATTACKS[kind].duration
            self.attack_connected = False

    def attack_box(self) -> pygame.Rect:
        spec = ATTACKS[self.attack]
        x = self.rect.right if self.facing == 1 else self.rect.left - spec.reach
        return pygame.Rect(x, self.rect.y + spec.offset, spec.reach, spec.height)

    def take_hit(self, spec: AttackSpec, push: int) -> None:
        self.health = max(0, self.health - spec.damage)
        self.x = self.clamp_x(self.x + push)
        self.sync_rect()
        # 맞으면 내 공격은 끊기고 경직에 들어간다.
        self.attack_time = 0.0
        self.hitstun = spec.hitstun
        self.hit_flash = min(spec.hitstun, 0.13)

    def update(self, dt: float, pad: Pad, opponent: "Fighter") -> None:
        direction = int(pad.held["right"]) - int(pad.held["left"])
        if not self.busy:
            self.x += direction * MOVE_SPEED * dt
        self.velocity_y += GRAVITY * dt
        self.y += self.velocity_y * dt
        if self.y + FIGHTER_H >= GROUND_Y:
            self.y = float(GROUND_Y - FIGHTER_H)
            self.velocity_y = 0.0
        self.x = self.clamp_x(self.x)
        self.sync_rect()
        # 공격 중에는 방향을 잠근다. 상대가 머리 위를 넘어갈 때
        # 판정 박스가 등 뒤로 순간이동하는 것을 막는다.
        if not self.attacking:
            self.facing = 1 if opponent.rect.centerx > self.rect.centerx else -1

        self.attack_time = max(0.0, self.attack_time - dt)
        self.hitstun = max(0.0, self.hitstun - dt)
        self.hit_flash = max(0.0, self.hit_flash - dt)

    def draw(self, screen: pygame.Surface) -> None:
        body_color = WHITE if self.hit_flash > 0 else self.color
        r = self.rect
        # Deliberately pixel-art-like geometry, so no external assets are needed.
        pygame.draw.rect(screen, INK, r.inflate(4, 4), border_radius=4)
        pygame.draw.rect(screen, body_color, r, border_radius=3)
        pygame.draw.rect(screen, (255, 198, 150), (r.x + 12, r.y + 8, 28, 24))
        eye_x = r.x + (31 if self.facing == 1 else 17)
        pygame.draw.rect(screen, INK, (eye_x, r.y + 16, 5, 5))
        pygame.draw.rect(screen, INK, (r.x + 8, r.y + 36, 36, 9))
        pygame.draw.rect(screen, INK, (r.x + 8, r.bottom - 14, 13, 14))
        pygame.draw.rect(screen, INK, (r.right - 21, r.bottom - 14, 13, 14))
        if self.attack_active:
            pygame.draw.rect(screen, GOLD, self.attack_box())


class Game:
    def __init__(self, fullscreen: bool = True, margin: int = 0) -> None:
        pygame.init()
        pygame.display.set_caption("FAMI FIGHTERS")
        desktop_w, desktop_h = pygame.display.get_desktop_sizes()[0]
        if fullscreen:
            self.display = pygame.display.set_mode((desktop_w, desktop_h), pygame.FULLSCREEN)
        else:
            # 창 테두리와 데스크톱 패널을 위한 공간을 남긴다.
            scale = min(1.0, max(1, desktop_w - 80) / WIDTH,
                        max(1, desktop_h - 100) / HEIGHT)
            self.display = pygame.display.set_mode(
                (max(1, int(WIDTH * scale)), max(1, int(HEIGHT * scale))),
                pygame.RESIZABLE)
        self.screen = pygame.Surface((WIDTH, HEIGHT))
        self.margin = margin
        self.clock = pygame.time.Clock()
        korean = find_korean_font()
        self.strings = STRINGS_KO if korean else STRINGS_EN
        # 한글 폰트는 같은 포인트에서 라틴 폰트보다 작게 잡혀 조금 키운다.
        # 안티에일리어싱은 켠다. 한글은 획이 많아 끄면 작은 크기에서 뭉갠다.
        self.smooth = korean is not None
        self.font = pygame.font.Font(korean, 30 if korean else 28)
        self.hud_font = pygame.font.Font(korean, 24 if korean else 26)
        self.large_font = pygame.font.Font(korean, 74 if korean else 72)
        self.title_font = pygame.font.Font(None, 88)   # 로고는 라틴이라 기본 폰트 유지
        if korean is None:
            print("한글 폰트를 찾지 못해 영문 문구로 실행합니다.")
            print("  라즈베리파이 / 데비안 계열:  sudo apt install -y fonts-nanum")
            print("  또는 assets/fonts/ 에 ttf 파일을 넣으세요.")
        self.input = KeyboardAdapter()
        self.scene = "title"
        self.input_ready = False
        self.reset_match()

    def reset_match(self) -> None:
        self.p1 = Fighter("P1", RED, 205, 1)
        self.p2 = Fighter("P2", BLUE, 705, -1)
        self.round_number = 1
        self.p1_wins = self.p2_wins = 0
        self.round_time = ROUND_TIME
        self.round_result = ""
        self.result_timer = 0.0
        self.paused = False

    def reset_round(self) -> None:
        self.p1.reset()
        self.p2.reset()
        self.round_time = ROUND_TIME
        self.round_result = ""
        self.result_timer = 0.0

    def begin_match(self) -> None:
        self.reset_match()
        self.scene = "fight"

    def quit(self) -> None:
        pygame.quit()
        sys.exit()

    def handle_pads(self, pads: tuple[Pad, ...]) -> None:
        """논리 버튼을 씬 전환과 캐릭터 행동으로 옮긴다."""
        start = any(pad.pressed["start"] for pad in pads)
        select = any(pad.pressed["select"] for pad in pads)
        attack = any(pad.any_pressed("punch", "kick") for pad in pads)

        # Start+Select 동시: 게임 종료. 부팅 자동 실행 상태에서는 창을 닫을
        # 수단이 없어 종료 경로가 반드시 있어야 하고, 단독 버튼으로 두면
        # 전시 중에 관람객이 실수로 누르기 때문에 조합키로 막는다.
        if any(pad.held["start"] and pad.held["select"] for pad in pads):
            self.quit()
        if select:
            self.scene = "title"
            return

        if self.scene in ("title", "match_over"):
            # A/B 로도 시작할 수 있게 둔다. Start 를 못 찾는 사람이 많다.
            if start or attack:
                self.begin_match()
            return
        if self.scene != "fight":
            return

        # 결과 오버레이가 떠 있을 땐 일시정지 표시가 가려져 멈춘 것처럼 보이므로 막는다.
        if start and not self.round_result:
            self.paused = not self.paused
        if self.paused or self.round_result:
            return
        # 점프·공격 가능 여부 판단은 Fighter 가 들고 있다.
        # 경직 중이라면 입력이 그대로 버려진다.
        for fighter, pad in zip((self.p1, self.p2), pads):
            if pad.pressed["up"]:
                fighter.try_jump()
            if pad.pressed["punch"]:
                fighter.start_attack("punch")
            elif pad.pressed["kick"]:
                fighter.start_attack("kick")

    def finish_round(self, winner: Fighter | None) -> None:
        if self.round_result:
            return
        if winner is self.p1:
            self.p1_wins += 1
            self.round_result = self.tx("p1_round_win")
        elif winner is self.p2:
            self.p2_wins += 1
            self.round_result = self.tx("p2_round_win")
        else:
            self.round_result = self.tx("draw")
        self.result_timer = 2.0

    def separate_fighters(self) -> None:
        """겹친 두 캐릭터를 좌우로 밀어낸다.

        공중에 있는 쪽은 대상에서 제외한다. 상대를 뛰어넘는 동작을 막지 않기 위해서다.
        """
        a, b = self.p1, self.p2
        if not (a.on_ground and b.on_ground) or not a.rect.colliderect(b.rect):
            return
        overlap = min(a.rect.right, b.rect.right) - max(a.rect.left, b.rect.left)
        if overlap <= 0:
            return
        if a.x > b.x:
            a, b = b, a
        shift = overlap / 2 + 0.5
        wanted_a, wanted_b = a.x - shift, b.x + shift
        a.x, b.x = Fighter.clamp_x(wanted_a), Fighter.clamp_x(wanted_b)
        # 한쪽이 벽에 막혀 못 물러난 만큼은 반대쪽이 마저 밀려난다.
        lost_a, lost_b = wanted_a - a.x, wanted_b - b.x
        if lost_b:
            a.x = Fighter.clamp_x(a.x - lost_b)
        if lost_a:
            b.x = Fighter.clamp_x(b.x - lost_a)
        a.sync_rect()
        b.sync_rect()

    def resolve_hits(self) -> None:
        """양쪽 판정을 먼저 모두 확정한 뒤에 피해를 적용한다.

        한 명씩 순서대로 처리하면 먼저 도는 쪽이 상대 공격을 끊어
        동시 타격이 항상 P1 승리로 기울기 때문이다.
        """
        landed = []
        for attacker, defender in ((self.p1, self.p2), (self.p2, self.p1)):
            if attacker.attack_active and not attacker.attack_connected and attacker.attack_box().colliderect(defender.rect):
                attacker.attack_connected = True
                landed.append((attacker, defender))
        for attacker, defender in landed:
            spec = ATTACKS[attacker.attack]
            defender.take_hit(spec, spec.push * attacker.facing)

    def update(self, dt: float, pads: tuple[Pad, ...]) -> None:
        if self.scene != "fight" or self.paused:
            return
        if self.round_result:
            self.result_timer -= dt
            if self.result_timer <= 0:
                if self.p1_wins >= 2 or self.p2_wins >= 2:
                    self.round_result = ""
                    self.scene = "match_over"
                else:
                    self.round_number += 1
                    self.reset_round()
            return
        self.p1.update(dt, pads[0], self.p2)
        self.p2.update(dt, pads[1], self.p1)
        self.separate_fighters()
        self.resolve_hits()
        self.round_time = max(0.0, self.round_time - dt)
        if self.p1.health <= 0 and self.p2.health <= 0:
            self.finish_round(None)
        elif self.p1.health <= 0:
            self.finish_round(self.p2)
        elif self.p2.health <= 0:
            self.finish_round(self.p1)
        elif self.round_time <= 0:
            self.finish_round(self.p1 if self.p1.health > self.p2.health else self.p2 if self.p2.health > self.p1.health else None)

    def tx(self, key: str, **fmt: object) -> str:
        value = self.strings[key]
        return value.format(**fmt) if fmt else value

    def text(self, value: str, x: int, y: int, color: tuple[int, int, int] = WHITE, *, center: bool = False, large: bool = False, hud: bool = False) -> None:
        font = self.large_font if large else self.hud_font if hud else self.font
        surface = font.render(value, self.smooth, color)
        rect = surface.get_rect(center=(x, y)) if center else surface.get_rect(topleft=(x, y))
        self.screen.blit(surface, rect)

    def draw_stage(self) -> None:
        self.screen.fill(SKY)
        pygame.draw.circle(self.screen, GOLD, (WIDTH - 125, 105), 48)
        for x in range(-50, WIDTH + 60, 110):
            pygame.draw.polygon(self.screen, (74, 145, 100), [(x, GROUND_Y), (x + 75, 210), (x + 150, GROUND_Y)])
        pygame.draw.rect(self.screen, GRASS, (0, GROUND_Y, WIDTH, HEIGHT - GROUND_Y))
        pygame.draw.rect(self.screen, INK, (0, GROUND_Y, WIDTH, 5))

    def draw_health_bar(self, x: int, value: int, color: tuple[int, int, int], reverse: bool = False) -> None:
        box = pygame.Rect(x, 42, 330, 25)
        pygame.draw.rect(self.screen, INK, box.inflate(6, 6))
        filled = round(box.width * value / 100)
        bar = pygame.Rect(box.right - filled if reverse else box.left, box.top, filled, box.height)
        pygame.draw.rect(self.screen, color, bar)

    def draw_hud(self) -> None:
        pygame.draw.rect(self.screen, INK, (0, 0, WIDTH, HUD_H))
        self.text("P1", 20, 14, RED, hud=True)
        self.text("P2", WIDTH - 52, 14, BLUE, hud=True)
        self.draw_health_bar(20, self.p1.health, RED)
        self.draw_health_bar(WIDTH - 350, self.p2.health, BLUE, reverse=True)
        self.text(f"{self.p1_wins} - {self.p2_wins}", WIDTH // 2, 16, GOLD, center=True, hud=True)
        self.text(f"{math.ceil(self.round_time):02d}", WIDTH // 2, 46, WHITE, center=True, hud=True)
        self.text(self.tx("round", n=self.round_number), WIDTH // 2, 76, WHITE, center=True, hud=True)

    def overlay(self, heading: str, subheading: str) -> None:
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 170))
        self.screen.blit(shade, (0, 0))
        self.text(heading, WIDTH // 2, HEIGHT // 2 - 25, WHITE, center=True, large=True)
        self.text(subheading, WIDTH // 2, HEIGHT // 2 + 40, GOLD, center=True)

    def draw_fight(self) -> None:
        self.draw_stage()
        self.p1.draw(self.screen)
        self.p2.draw(self.screen)
        self.draw_hud()
        if self.round_result:
            self.overlay(self.round_result, self.tx("next_round"))
        elif self.paused:
            self.overlay(self.tx("pause"), self.tx("resume"))

    def draw_title(self) -> None:
        self.screen.fill(RED)
        pygame.draw.rect(self.screen, WHITE, (42, 40, WIDTH - 84, HEIGHT - 80), border_radius=8)
        logo = self.title_font.render("FAMI FIGHTERS", False, RED)
        self.screen.blit(logo, logo.get_rect(center=(WIDTH // 2, 138)))
        self.text(self.tx("subtitle"), WIDTH // 2, 202, INK, center=True)
        self.text(self.tx("rule"), WIDTH // 2, 240, GOLD, center=True)
        self.text(self.tx("begin"), WIDTH // 2, 296, BLUE, center=True)
        self.text(self.tx("p1_keys"), WIDTH // 2, 352, RED, center=True)
        self.text(self.tx("p2_keys"), WIDTH // 2, 390, BLUE, center=True)
        self.text(self.tx("system"), WIDTH // 2, 434, INK, center=True)

    def draw_match_over(self) -> None:
        self.draw_fight()
        winner = self.tx("p1_wins") if self.p1_wins > self.p2_wins else self.tx("p2_wins")
        self.overlay(winner, self.tx("rematch"))

    def run(self) -> None:
        while True:
            dt = min(self.clock.tick(FPS) / 1000, MAX_DT)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.quit()
            # 공격이 눌린 프레임에 바로 시작되도록 입력이 update 보다 앞선다.
            pads = self.input.poll()
            if not self.input_ready:
                self.input_ready = not any(any(pad.held.values()) for pad in pads)
                for pad in pads:
                    pad.clear()
            self.handle_pads(pads)
            self.update(dt, pads)
            if self.scene == "title":
                self.draw_title()
            elif self.scene == "match_over":
                self.draw_match_over()
            else:
                self.draw_fight()
            self.present()

    def present(self) -> None:
        """게임 좌표는 유지하고 실제 창 안에 비율을 보존해 표시한다."""
        width, height = self.display.get_size()
        scale = min(width / WIDTH, height / HEIGHT) * (1 - 2 * self.margin / 100)
        size = (max(1, int(WIDTH * scale)), max(1, int(HEIGHT * scale)))
        self.display.fill((0, 0, 0))
        frame = pygame.transform.scale(self.screen, size)
        self.display.blit(frame, ((width - size[0]) // 2, (height - size[1]) // 2))
        pygame.display.flip()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FAMI FIGHTERS")
    display_mode = parser.add_mutually_exclusive_group()
    display_mode.add_argument("--fullscreen", action="store_true", dest="fullscreen", help="전체 화면으로 실행")
    display_mode.add_argument("--windowed", action="store_false", dest="fullscreen", help="창 모드로 실행")
    parser.set_defaults(fullscreen=True)
    parser.add_argument("--margin", type=int, choices=range(0, 21), default=0,
                        metavar="0-20", help="각 가장자리 여백 비율(%%), 기본 0")
    args = parser.parse_args()
    Game(fullscreen=args.fullscreen, margin=args.margin).run()
