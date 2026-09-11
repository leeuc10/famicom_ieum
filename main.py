"""두 명이 한 화면에서 겨루는 2D 대전 격투 프로토타입 (Raspberry Pi 용).

입력은 input_adapter 가 논리 버튼 8개로 정규화해 넘겨준다.
이 파일은 키보드인지 ESP32 조작기인지 알지 못한다.

색은 theme.py 한곳에서 가져온다. 런처·패들 듀얼과 같은 팔레트를 써야
세 화면이 한 기기의 화면처럼 보이고, 1P/2P 색도 게임마다 흔들리지 않는다.
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from dataclasses import dataclass

import pygame
from game_fx import Sparks

from fonts import find_korean_font
from input_adapter import KeyboardAdapter, Pad
from theme import (EMBER, GOLD, INK, LINE, MUTED, P1, P2, PANEL, PANEL_HI,
                   SKIN, WHITE, mix, shade)

WIDTH, HEIGHT, FPS = 960, 540, 60
# 프레임이 한 번 크게 튀어도 공격 판정이 한 프레임에 통째로 소진되지 않게
# dt 에 상한을 둔다. 라즈베리파이에서 순간적인 부하가 걸릴 때를 위한 것이다.
MAX_DT = 0.05
HUD_H = 96        # 상단 정보 막대 높이. 이름·체력·타이머·라운드가 들어간다.

# 한글 폰트를 못 찾았을 때 빈 네모를 띄우는 대신 영문으로 물러난다.
# 전시 중에 글자가 깨져 보이는 것보다 낫다.
STRINGS_KO = {
    "subtitle": "2인용 대전 격투 프로토타입",
    "begin": "START  또는  A / B   ·   대전 시작",
    "row_move": "이동 · 점프",
    "row_punch": "펀치 (A)",
    "row_kick": "킥 (B)",
    "p1_move": "W A S D",
    "p1_punch": "F",
    "p1_kick": "G",
    "p2_move": "방향키",
    "p2_punch": ",",
    "p2_kick": ".",
    "system": "SELECT : 타이틀        START + SELECT : 종료",
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
    "begin": "START  or  A / B   ·   BEGIN MATCH",
    "row_move": "MOVE · JUMP",
    "row_punch": "PUNCH (A)",
    "row_kick": "KICK (B)",
    "p1_move": "W A S D",
    "p1_punch": "F",
    "p1_kick": "G",
    "p2_move": "ARROWS",
    "p2_punch": ",",
    "p2_kick": ".",
    "system": "SELECT : TITLE        START + SELECT : QUIT",
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

# 무대는 해질녘으로 잡는다. UI 가 어두운 남색이라 파란 대낮 하늘과는 따로 놀고,
# 어두운 배경 위에서 산호색/하늘색 파이터가 훨씬 또렷하게 읽힌다.
SKY_TOP = (26, 24, 50)
SKY_HORIZON = (150, 74, 82)
SUN_CORE = (255, 220, 152)
SUN_POS = (WIDTH - 178, 214)
# (색, 봉우리 간격, 높이, 밑변 y). 뒤쪽 능선일수록 밝고 완만해 거리가 읽힌다.
RIDGES = (
    ((62, 52, 96), 190, 168, GROUND_Y - 26),
    ((42, 37, 70), 142, 116, GROUND_Y - 10),
    ((26, 25, 46), 104, 70, GROUND_Y),
)
FLOOR = (23, 22, 38)


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


def build_stage() -> pygame.Surface:
    """무대 배경을 한 번만 그려 캐시한다.

    배경은 움직이지 않는데 매 프레임 폴리곤을 다시 그리면 라즈베리파이에서
    프레임을 깎아먹는다. 표면 하나로 만들어 두고 블릿만 한다.
    """
    stage = pygame.Surface((WIDTH, HEIGHT))
    # 하늘. 노을을 지평선 쪽에 몰아주려고 t 를 제곱해 기울인다.
    for y in range(GROUND_Y):
        stage.fill(mix(SKY_TOP, SKY_HORIZON, (y / GROUND_Y) ** 2.4), (0, y, WIDTH, 1))

    rng = random.Random(7)          # 별 배치는 실행할 때마다 같아야 한다
    for _ in range(80):
        x, y = rng.randrange(WIDTH), rng.randrange(8, 300)
        tone = rng.randrange(110, 215)
        size = 2 if tone > 190 else 1
        stage.fill((tone, tone, min(255, tone + 28)), (x, y, size, size))

    glow = pygame.Surface((280, 280), pygame.SRCALPHA)
    for radius, alpha in ((136, 18), (106, 26), (78, 38)):
        pygame.draw.circle(glow, (*EMBER, alpha), (140, 140), radius)
    stage.blit(glow, (SUN_POS[0] - 140, SUN_POS[1] - 140))
    pygame.draw.circle(stage, SUN_CORE, SUN_POS, 50)

    for color, spacing, height, base in RIDGES:
        points, x = [(-spacing, HEIGHT)], -spacing
        while x < WIDTH + spacing:
            points.append((x, base))
            points.append((x + spacing // 2, base - height + rng.randrange(-20, 21)))
            x += spacing
        points += [(x, base), (x, HEIGHT)]
        pygame.draw.polygon(stage, color, points)

    pygame.draw.rect(stage, FLOOR, (0, GROUND_Y, WIDTH, HEIGHT - GROUND_Y))
    pygame.draw.rect(stage, EMBER, (0, GROUND_Y - 3, WIDTH, 3))      # 지면에 걸린 노을
    pygame.draw.rect(stage, INK, (0, GROUND_Y, WIDTH, 4))
    # 바닥 줄무늬. 아래로 갈수록 간격을 벌려 바닥이 눕도록 보이게 한다.
    y, gap = GROUND_Y + 9, 7
    while y < HEIGHT:
        stage.fill(shade(FLOOR, 1.55), (0, y, WIDTH, 1))
        y, gap = y + gap, int(gap * 1.5) + 1
    pygame.draw.ellipse(stage, shade(FLOOR, 1.35), (WIDTH // 2 - 300, GROUND_Y + 6, 600, 76), 2)

    # 무대 뒤의 문과 등롱, 원근을 가진 돌바닥.
    for x in (110, WIDTH-110):
        pygame.draw.rect(stage, (36,29,46), (x-8,GROUND_Y-167,16,167))
        pygame.draw.rect(stage, (99,57,58), (x-5,GROUND_Y-161,5,155))
    pygame.draw.polygon(stage,(39,29,45),[(50,GROUND_Y-165),(WIDTH-50,GROUND_Y-165),
        (WIDTH-80,GROUND_Y-184),(80,GROUND_Y-184)])
    pygame.draw.line(stage,EMBER,(80,GROUND_Y-182),(WIDTH-80,GROUND_Y-182),3)
    for x in (160,WIDTH-160):
        pygame.draw.line(stage,INK,(x,GROUND_Y-164),(x,GROUND_Y-122),3)
        pygame.draw.rect(stage,(176,88,62),(x-12,GROUND_Y-127,24,31),border_radius=7)
        pygame.draw.rect(stage,GOLD,(x-6,GROUND_Y-123,12,23),border_radius=5)
        pygame.draw.line(stage,INK,(x-15,GROUND_Y-127),(x+15,GROUND_Y-127),4)
    for x in range(-400, WIDTH+500, 120):
        pygame.draw.line(stage,shade(FLOOR,1.6),(WIDTH//2+(x-WIDTH//2)*.55,GROUND_Y+4),
                         (x,HEIGHT),1)

    # 비네트. 가장자리를 눌러 가운데 싸움에 눈이 가게 한다.
    vignette = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    for i in range(80):
        pygame.draw.rect(vignette, (0, 0, 0, int(78 * (1 - i / 80) ** 2)),
                         (i, i, WIDTH - 2 * i, HEIGHT - 2 * i), 1)
    stage.blit(vignette, (0, 0))
    return stage


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
        self.health_ghost = 100.0   # 체력 막대 잔상. 표시용이라 판정에는 쓰지 않는다.
        self.attack = ""
        self.attack_time = 0.0
        self.attack_connected = False
        self.hitstun = 0.0
        self.hit_flash = 0.0
        self.hit_dir = 1
        self.pose_time = 0.0
        self.walk_cycle = 0.0
        self.moving = False

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
    def attack_phase(self) -> float:
        """공격이 시작된 뒤 흐른 시간. 판정과 팔다리 그리기가 함께 본다."""
        return ATTACKS[self.attack].duration - self.attack_time

    @property
    def attack_active(self) -> bool:
        """판정이 실제로 나가 있는 구간인지. 발동·경직 중에는 맞지 않는다."""
        if not self.attacking:
            return False
        spec = ATTACKS[self.attack]
        return spec.startup <= self.attack_phase < spec.startup + spec.active

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
        self.hit_dir = 1 if push >= 0 else -1

    def update(self, dt: float, pad: Pad, opponent: "Fighter") -> None:
        self.pose_time += dt
        direction = int(pad.held["right"]) - int(pad.held["left"])
        self.moving = bool(direction) and not self.busy
        self.walk_cycle += dt * 13 if self.moving else 0
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
        # 체력은 곧바로 줄지만 잔상은 늦게 따라온다. 방금 얼마나 깎였는지
        # 눈으로 읽히게 하려는 표시이고, 승패 판정은 self.health 만 본다.
        self.health_ghost = (max(self.health, self.health_ghost - 46 * dt)
                             if self.health_ghost > self.health else float(self.health))

    def limb_extension(self) -> float:
        """팔다리가 얼마나 뻗었는지(0~1). 음수는 뒤로 당기는 예비 동작."""
        spec = ATTACKS[self.attack]
        elapsed = self.attack_phase
        if elapsed < spec.startup:
            return -0.28 * (elapsed / spec.startup)
        if elapsed < spec.startup + spec.active:
            return 1.0
        rest = (elapsed - spec.startup - spec.active) / spec.recovery
        return max(0.0, 1.0 - rest) ** 0.6

    def draw_limb(self, screen: pygame.Surface, shoulder: tuple[float, float], hip: tuple[float, float]) -> None:
        """공격을 판정 박스가 아니라 뻗은 팔다리로 보여 준다.

        예전에는 판정 박스를 그대로 노란 사각형으로 그렸는데, 그건 디버그
        표시지 동작이 아니다. 실제 판정을 보고 싶으면 --hitbox 로 켠다.
        """
        spec = ATTACKS[self.attack]
        extension = self.limb_extension()
        if self.attack == "punch":
            # 기존 가드 팔을 이 팔로 대체한다. 어깨 -> 팔꿈치 -> 주먹을 연결한다.
            root = (shoulder[0] + self.facing * 12, shoulder[1])
            reach = max(0.0, extension)
            hand = (root[0] + self.facing * (10 + (spec.reach + 4) * extension),
                    root[1] - 5)
            elbow = (root[0] + (hand[0] - root[0]) * .48,
                     root[1] + 12 * (1 - reach))
            pygame.draw.lines(screen, INK, False, [root, elbow, hand], 13)
            pygame.draw.lines(screen, SKIN, False, [root, elbow, hand], 9)
            glove = pygame.Rect(0, 0, 17, 16)
            glove.center = hand
            pygame.draw.rect(screen, INK, glove.inflate(4, 4), border_radius=5)
            pygame.draw.rect(screen, self.color, glove, border_radius=4)
            pygame.draw.line(screen, shade(self.color, 1.3),
                             (glove.left+3, glove.top+3), (glove.right-4, glove.top+3), 3)
            if self.attack_active:
                for dy in (-10, 10):
                    pygame.draw.line(screen, GOLD,
                                     (hand[0]-self.facing*18, hand[1]+dy),
                                     (hand[0]-self.facing*33, hand[1]+dy), 2)
            return
        # 킥은 새 막대를 붙이지 않고 앞다리의 무릎과 발목을 움직인다.
        phase = self.attack_phase
        if phase < spec.startup:
            lift = min(1.0, phase / spec.startup)
            stretch = 0.0
        elif phase < spec.startup + spec.active:
            lift, stretch = 1.0, 1.0
        else:
            recovery = (phase - spec.startup - spec.active) / spec.recovery
            stretch = max(0.0, 1 - recovery * 2)
            lift = min(1.0, max(0.0, (1 - recovery) * 2))
        facing = self.facing
        root = (hip[0] + facing*5, hip[1])
        knee = (root[0] + facing*(10 + lift*9 + stretch*20),
                root[1] - lift*15)
        ankle = (root[0] + facing*(8 + stretch*(FIGHTER_W/2 + spec.reach - 24)),
                 self.rect.bottom - 5 - lift*21 + stretch*4)
        points = [root, knee, ankle]
        pygame.draw.lines(screen, INK, False, points, 16)
        pygame.draw.lines(screen, shade(self.color, .82), False, points, 12)
        pygame.draw.line(screen, shade(self.color, 1.25),
                         (knee[0],knee[1]-3), (ankle[0],ankle[1]-3), 3)
        # 발등과 발바닥이 있는 부츠로 주먹과 구분한다.
        boot = [(ankle[0]-facing*7,ankle[1]-5),
                (ankle[0]+facing*5,ankle[1]-8),
                (ankle[0]+facing*11,ankle[1]+7),
                (ankle[0]-facing*6,ankle[1]+7)]
        pygame.draw.polygon(screen, INK, boot)
        pygame.draw.line(screen, WHITE, (ankle[0]+facing*8,ankle[1]-4),
                         (ankle[0]+facing*11,ankle[1]+6), 3)
        if self.attack_active:
            pygame.draw.line(screen, GOLD, (ankle[0]-facing*6,ankle[1]-17),
                             (ankle[0]-facing*25,ankle[1]-20), 2)

    def draw_impact(self, screen: pygame.Surface) -> None:
        """맞은 순간 튀는 불꽃. 어느 쪽에서 맞았는지도 같이 보여 준다."""
        progress = 1 - self.hit_flash / 0.13
        origin_x = self.rect.centerx - self.hit_dir * (FIGHTER_W // 2)
        origin_y = self.rect.centery - 8
        inner = 10 + 18 * progress
        outer = inner + 16 * (1 - progress) + 6
        for i in range(7):
            angle = i * math.tau / 7 + progress * 0.9
            cos, sin = math.cos(angle), math.sin(angle)
            pygame.draw.line(screen, GOLD if i % 2 else WHITE,
                             (origin_x + cos * inner, origin_y + sin * inner),
                             (origin_x + cos * outer, origin_y + sin * outer), 3)

    def draw(self, screen: pygame.Surface, hitbox: bool = False) -> None:
        r = self.rect
        # 바닥 그림자. 뜰수록 작고 옅어져 높이가 읽힌다.
        lift = min(1.0, max(0.0, GROUND_Y - r.bottom) / 150)
        width = round(FIGHTER_W * (1 - 0.45 * lift))
        shadow = pygame.Surface((width, 14), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, round(120 * (1 - 0.65 * lift))), shadow.get_rect())
        screen.blit(shadow, (r.centerx - width // 2, GROUND_Y - 9))

        # 관절을 따로 그려 걷기·점프·피격 자세를 만든다. 판정 rect는 그대로다.
        base = WHITE if self.hit_flash > 0 else self.color
        sway = math.sin(self.walk_cycle) if self.moving else 0
        breath = math.sin(self.pose_time * 3) * 1.5
        lean = -self.hit_dir * 7 if self.stunned else self.facing * (3 if self.moving else 0)
        cx = r.centerx + lean
        hip = (cx, r.bottom - 25)
        shoulder = (cx, r.y + 33 + breath)
        def limb(points, color, width):
            pygame.draw.lines(screen, INK, False, points, width+4)
            pygame.draw.lines(screen, color, False, points, width)
        for side in (-1, 1):
            if self.attacking and self.attack == "kick" and side == self.facing:
                continue
            stride = side * sway * 12
            foot = (r.centerx + side*13 + stride, r.bottom-3)
            knee = (hip[0]+side*11-stride*.3, r.bottom-15)
            if not self.on_ground:
                foot = (r.centerx+side*21, r.bottom-17)
                knee = (hip[0]+side*13, r.bottom-28)
            limb([hip, knee, foot], shade(base, .7 if side == -1 else .95), 12)
            pygame.draw.line(screen, INK, foot, (foot[0]+self.facing*9,foot[1]), 9)
        torso = [(cx-16,shoulder[1]-6),(cx+16,shoulder[1]-6),
                 (hip[0]+12,hip[1]),(hip[0]-12,hip[1])]
        pygame.draw.polygon(screen, INK, torso)
        pygame.draw.polygon(screen, base, torso)
        pygame.draw.line(screen, shade(base,1.3), (cx-11,shoulder[1]-3),(cx-7,hip[1]-5),4)
        pygame.draw.polygon(screen, WHITE, [(cx-7,shoulder[1]-5),(cx,shoulder[1]+9),(cx+7,shoulder[1]-5)])
        pygame.draw.line(screen, INK,(cx-13,hip[1]-2),(cx+13,hip[1]-2),7)
        pygame.draw.rect(screen,GOLD,(cx-4,hip[1]-5,8,6))
        # 뒤팔과 앞팔을 서로 다른 자세로 둔다.
        for side in (-1,1):
            if self.attacking and self.attack == "punch" and side == self.facing:
                continue
            arm_x = cx + side*15
            elbow = (arm_x + side*6, shoulder[1]+14)
            hand = (arm_x+self.facing*8, shoulder[1]+3-side*4)
            limb([(arm_x,shoulder[1]),elbow,hand],SKIN,8)
            pygame.draw.circle(screen,INK,hand,8)
            pygame.draw.circle(screen,shade(base,.8),hand,6)
        head = pygame.Rect(0,0,27,26)
        head.midbottom=(cx+self.facing*2,shoulder[1]-2)
        pygame.draw.rect(screen,INK,head.inflate(4,4),border_radius=5)
        pygame.draw.rect(screen,SKIN,head,border_radius=4)
        pygame.draw.rect(screen,INK,(head.x,head.y,head.w,7))
        pygame.draw.rect(screen,base,(head.x-2,head.y+5,head.w+4,5))
        ribbon_x=head.centerx-self.facing*15
        pygame.draw.lines(screen,base,False,[(ribbon_x,head.y+8),
            (ribbon_x-self.facing*15,head.y+10+math.sin(self.pose_time*8)*4),
            (ribbon_x-self.facing*23,head.y+15)],4)
        eye_x=head.x+(18 if self.facing==1 else 4)
        pygame.draw.rect(screen,INK,(eye_x,head.y+12,5,4))
        if self.attacking:
            self.draw_limb(screen, shoulder, hip)

        if self.hit_flash > 0:
            self.draw_impact(screen)
        if hitbox and self.attack_active:
            pygame.draw.rect(screen, GOLD, self.attack_box(), 2)


class Game:
    def __init__(self, fullscreen: bool = True, margin: int = 0, hitbox: bool = False) -> None:
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
        pygame.mouse.set_visible(False)
        self.screen = pygame.Surface((WIDTH, HEIGHT))
        self.margin = margin
        self.hitbox = hitbox
        self.clock = pygame.time.Clock()
        korean = find_korean_font()
        self.strings = STRINGS_KO if korean else STRINGS_EN
        # 한글 폰트는 같은 포인트에서 라틴 폰트보다 작게 잡혀 조금 키운다.
        # 안티에일리어싱은 켠다. 한글은 획이 많아 끄면 작은 크기에서 뭉갠다.
        self.smooth = korean is not None
        self.fonts = {
            "small": pygame.font.Font(korean, 19 if korean else 20),
            "hud": pygame.font.Font(korean, 22 if korean else 24),
            "body": pygame.font.Font(korean, 26 if korean else 26),
            "timer": pygame.font.Font(korean, 38 if korean else 40),
            "large": pygame.font.Font(korean, 66 if korean else 68),
        }
        self.title_font = pygame.font.Font(None, 96)   # 로고는 라틴이라 기본 폰트 유지
        if korean is None:
            print("한글 폰트를 찾지 못해 영문 문구로 실행합니다.")
            print("  라즈베리파이 / 데비안 계열:  sudo apt install -y fonts-nanum")
            print("  또는 assets/fonts/ 에 ttf 파일을 넣으세요.")
        self.stage = build_stage()
        self.title_bg = self.build_title_bg()
        self.input = KeyboardAdapter()
        self.scene = "title"
        self.input_ready = False
        self.time = 0.0
        self.shake = 0.0
        self.sparks = Sparks()
        self.reset_match()

    def build_title_bg(self) -> pygame.Surface:
        """타이틀 배경도 한 번만 그린다. 대각선 줄무늬 + 비네트."""
        surface = pygame.Surface((WIDTH, HEIGHT))
        surface.fill(INK)
        for x in range(-HEIGHT, WIDTH, 46):
            pygame.draw.polygon(surface, PANEL, [(x, HEIGHT), (x + 22, HEIGHT),
                                                 (x + 22 + HEIGHT, 0), (x + HEIGHT, 0)])
        # 좌우에서 산호/하늘색 빛이 번져 들어오게 해 두 사람이 맞붙는 화면임을 암시한다.
        wash = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        pygame.draw.ellipse(wash, (*P1, 30), (-200, -240, 760, 580))
        pygame.draw.ellipse(wash, (*P2, 30), (WIDTH - 560, -240, 760, 580))
        surface.blit(wash, (0, 0))
        # 비네트는 반드시 별도 표면에 그려 블릿한다. pygame.draw 는 알파를 섞지 않고
        # 덮어쓰기 때문에, 같은 표면에 겹쳐 그리면 링이 끝나는 자리에 각진 경계가 남는다.
        vignette = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        for i in range(110):
            pygame.draw.rect(vignette, (*INK, int(170 * (1 - i / 110) ** 2)),
                             (i, i, WIDTH - 2 * i, HEIGHT - 2 * i), 1)
        surface.blit(vignette, (0, 0))
        return surface

    def reset_match(self) -> None:
        self.p1 = Fighter("P1", P1, 205, 1)
        self.p2 = Fighter("P2", P2, 705, -1)
        self.round_number = 1
        self.p1_wins = self.p2_wins = 0
        self.round_time = ROUND_TIME
        self.round_result = ""
        self.round_accent = GOLD
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
            self.round_accent = P1
        elif winner is self.p2:
            self.p2_wins += 1
            self.round_result = self.tx("p2_round_win")
            self.round_accent = P2
        else:
            self.round_result = self.tx("draw")
            self.round_accent = GOLD
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
            self.sparks.burst(defender.rect.center, GOLD if attacker.attack == "kick" else WHITE)
            defender.take_hit(spec, spec.push * attacker.facing)
            # 화면 흔들림은 타격감 표시일 뿐이라 판정에는 영향을 주지 않는다.
            self.shake = max(self.shake, 0.09 + spec.damage * 0.006)

    def update(self, dt: float, pads: tuple[Pad, ...]) -> None:
        if not self.paused:
            self.sparks.update(dt)
        self.shake = max(0.0, self.shake - dt)
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

    def text(self, value: str, x: int, y: int, color: tuple[int, int, int] = WHITE, *,
             center: bool = False, right: bool = False, size: str = "body",
             shadow: bool = False) -> None:
        font = self.fonts[size]
        surface = font.render(value, self.smooth, color)
        if center:
            rect = surface.get_rect(center=(x, y))
        elif right:
            rect = surface.get_rect(topright=(x, y))
        else:
            rect = surface.get_rect(topleft=(x, y))
        if shadow:
            self.screen.blit(font.render(value, self.smooth, INK), rect.move(2, 3))
        self.screen.blit(surface, rect)

    def draw_health_bar(self, x: int, fighter: Fighter, reverse: bool = False) -> None:
        box = pygame.Rect(x, 44, 352, 26)
        pygame.draw.rect(self.screen, INK, box.inflate(8, 8), border_radius=5)
        pygame.draw.rect(self.screen, PANEL_HI, box)
        for value, tone in ((fighter.health_ghost, WHITE), (fighter.health, fighter.color)):
            filled = round(box.width * value / 100)
            if filled <= 0:
                continue
            bar = pygame.Rect(box.right - filled if reverse else box.left, box.top, filled, box.height)
            pygame.draw.rect(self.screen, tone, bar)
            pygame.draw.rect(self.screen, shade(tone, 1.18), (bar.x, bar.y, bar.width, 7))
        for i in range(1, 4):                                   # 25 씩 눈금
            tick = box.left + box.width * i // 4
            pygame.draw.line(self.screen, INK, (tick, box.top), (tick, box.bottom - 1))
        pygame.draw.rect(self.screen, LINE, box, 2)

    def draw_round_pips(self, x: int, wins: int, color: tuple[int, int, int], step: int) -> None:
        """따낸 라운드를 점수 숫자 대신 마름모로 보여 준다. 2선승이라 두 칸이다."""
        for i in range(2):
            cx, cy = x + i * step, 25
            points = [(cx, cy - 9), (cx + 9, cy), (cx, cy + 9), (cx - 9, cy)]
            pygame.draw.polygon(self.screen, color if i < wins else PANEL_HI, points)
            pygame.draw.polygon(self.screen, INK if i < wins else LINE, points, 2)

    def draw_hud(self) -> None:
        pygame.draw.rect(self.screen, INK, (0, 0, WIDTH, HUD_H))
        pygame.draw.rect(self.screen, LINE, (0, HUD_H - 2, WIDTH, 2))
        self.text("1P", 26, 12, P1, size="hud")
        self.text("2P", WIDTH - 26, 12, P2, size="hud", right=True)
        self.draw_round_pips(84, self.p1_wins, P1, 26)
        self.draw_round_pips(WIDTH - 84, self.p2_wins, P2, -26)
        self.draw_health_bar(26, self.p1)
        self.draw_health_bar(WIDTH - 378, self.p2, reverse=True)

        plate = pygame.Rect(0, 0, 122, 56)
        plate.midtop = (WIDTH // 2, 8)
        urgent = self.round_time <= 10
        pygame.draw.rect(self.screen, PANEL, plate, border_radius=6)
        pygame.draw.rect(self.screen, P1 if urgent else GOLD, plate, 2, border_radius=6)
        self.text(f"{math.ceil(self.round_time):02d}", plate.centerx, plate.centery - 1,
                  P1 if urgent else WHITE, center=True, size="timer")
        self.text(self.tx("round", n=self.round_number), WIDTH // 2, 80, MUTED,
                  center=True, size="small")

    def overlay(self, heading: str, subheading: str, accent: tuple[int, int, int] = GOLD) -> None:
        shade_layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade_layer.fill((*INK, 195))
        self.screen.blit(shade_layer, (0, 0))
        band = pygame.Rect(0, HEIGHT // 2 - 84, WIDTH, 168)
        pygame.draw.rect(self.screen, PANEL, band)
        pygame.draw.rect(self.screen, accent, (0, band.top, WIDTH, 4))
        pygame.draw.rect(self.screen, accent, (0, band.bottom - 4, WIDTH, 4))
        self.text(heading, WIDTH // 2, band.centery - 22, accent, center=True, size="large", shadow=True)
        self.text(subheading, WIDTH // 2, band.centery + 44, MUTED, center=True, size="small")

    def draw_fight(self) -> None:
        self.screen.blit(self.stage, (0, 0))
        self.p1.draw(self.screen, self.hitbox)
        self.p2.draw(self.screen, self.hitbox)
        self.sparks.draw(self.screen)
        self.draw_hud()
        if self.round_result:
            self.overlay(self.round_result, self.tx("next_round"), self.round_accent)
        elif self.paused:
            self.overlay(self.tx("pause"), self.tx("resume"))

    def draw_control_card(self, rect: pygame.Rect, label: str, color: tuple[int, int, int],
                          keys: tuple[str, str, str]) -> None:
        """1P/2P 조작을 한 장씩. 한 줄에 몰아 넣으면 아무도 안 읽는다."""
        pygame.draw.rect(self.screen, PANEL, rect, border_radius=10)
        pygame.draw.rect(self.screen, color, (rect.x, rect.y, rect.width, 36),
                         border_top_left_radius=10, border_top_right_radius=10)
        self.text(label, rect.x + 16, rect.y + 7, INK, size="hud")
        rows = (self.tx("row_move"), self.tx("row_punch"), self.tx("row_kick"))
        for i, (name, key) in enumerate(zip(rows, keys)):
            y = rect.y + 54 + i * 38
            self.text(name, rect.x + 16, y, MUTED, size="small")
            # 키는 자판 모양 상자에 담는다. 맨 글자로 두면 ',' 나 '.' 가 먼지처럼 보인다.
            cap = pygame.Rect(0, 0, max(36, self.fonts["hud"].size(key)[0] + 22), 32)
            cap.topright = (rect.right - 16, y - 4)
            pygame.draw.rect(self.screen, PANEL_HI, cap, border_radius=6)
            pygame.draw.rect(self.screen, LINE, cap, 2, border_radius=6)
            self.text(key, cap.centerx, cap.centery - 1, WHITE, center=True, size="hud")
            if i < 2:
                pygame.draw.line(self.screen, LINE, (rect.x + 16, y + 30),
                                 (rect.right - 16, y + 30))
        pygame.draw.rect(self.screen, LINE, rect, 2, border_radius=10)

    def draw_title(self) -> None:
        self.screen.blit(self.title_bg, (0, 0))
        # 로고는 산호/하늘색을 어긋나게 깔아 아케이드 간판처럼 보이게 한다.
        for dx, dy, tone in ((-5, 5, P1), (5, -5, P2)):
            ghost = self.title_font.render("FAMI FIGHTERS", True, tone)
            self.screen.blit(ghost, ghost.get_rect(center=(WIDTH // 2 + dx, 108 + dy)))
        logo = self.title_font.render("FAMI FIGHTERS", True, WHITE)
        self.screen.blit(logo, logo.get_rect(center=(WIDTH // 2, 108)))

        pygame.draw.line(self.screen, LINE, (300, 148), (WIDTH - 300, 148), 2)
        pygame.draw.polygon(self.screen, GOLD, [(WIDTH // 2, 140), (WIDTH // 2 + 9, 148),
                                                (WIDTH // 2, 156), (WIDTH // 2 - 9, 148)])
        self.text(self.tx("subtitle"), WIDTH // 2, 180, MUTED, center=True, size="small")

        pill = pygame.Rect(0, 0, self.fonts["hud"].size(self.tx("rule"))[0] + 44, 38)
        pill.center = (WIDTH // 2, 222)
        pygame.draw.rect(self.screen, GOLD, pill, 2, border_radius=19)
        self.text(self.tx("rule"), WIDTH // 2, 221, GOLD, center=True, size="hud")

        card = pygame.Rect(76, 264, 372, 176)
        self.draw_control_card(card, "1P", P1,
                               (self.tx("p1_move"), self.tx("p1_punch"), self.tx("p1_kick")))
        card.right = WIDTH - 76
        self.draw_control_card(card, "2P", P2,
                               (self.tx("p2_move"), self.tx("p2_punch"), self.tx("p2_kick")))

        # 깜빡임은 "여기를 누르라"는 신호다. 전시장에서는 이게 있어야 사람이 손을 댄다.
        if self.time % 1.15 < 0.74:
            self.text(self.tx("begin"), WIDTH // 2, 478, GOLD, center=True, size="hud")
        self.text(self.tx("system"), WIDTH // 2, 512, MUTED, center=True, size="small")

    def draw_match_over(self) -> None:
        self.draw_fight()
        p1_won = self.p1_wins > self.p2_wins
        self.overlay(self.tx("p1_wins") if p1_won else self.tx("p2_wins"),
                     self.tx("rematch"), P1 if p1_won else P2)

    def run(self) -> None:
        while True:
            dt = min(self.clock.tick(FPS) / 1000, MAX_DT)
            self.time += dt
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
        x, y = (width - size[0]) // 2, (height - size[1]) // 2
        if self.shake > 0:
            # 타격 순간에만 화면을 조금 흔든다. 크게 흔들면 눈이 피로해진다.
            amount = min(1.0, self.shake / 0.16) * scale
            x += round(math.sin(self.time * 88) * 7 * amount)
            y += round(math.cos(self.time * 67) * 5 * amount)
        self.display.blit(frame, (x, y))
        pygame.display.flip()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FAMI FIGHTERS")
    display_mode = parser.add_mutually_exclusive_group()
    display_mode.add_argument("--fullscreen", action="store_true", dest="fullscreen", help="전체 화면으로 실행")
    display_mode.add_argument("--windowed", action="store_false", dest="fullscreen", help="창 모드로 실행")
    parser.set_defaults(fullscreen=True)
    parser.add_argument("--margin", type=int, choices=range(0, 21), default=0,
                        metavar="0-20", help="각 가장자리 여백 비율(%%), 기본 0")
    parser.add_argument("--hitbox", action="store_true", help="공격 판정 박스를 표시(타이밍 조정용)")
    args = parser.parse_args()
    Game(fullscreen=args.fullscreen, margin=args.margin, hitbox=args.hitbox).run()
