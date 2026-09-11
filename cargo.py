"""둘이서 짐 나르기 — 판자 하나를 둘이 들고 화물을 받아 투입구에 넣는 협동 게임.

라인업의 다른 세 게임은 대전이거나 혼자다. 이 게임은 유일하게 협동이라
규칙 자체가 "혼자서는 못 한다" 로 만들어져 있다.

  가로 이동은 두 사람 의도의 평균이다. 한 사람만 밀면 절반 속도로 가고,
  서로 반대로 밀면 판자는 제자리에 선다. 말을 맞추는 것이 곧 조작이다.

  세로는 각자 자기 쪽 손 높이만 정한다. 두 손 높이가 어긋난 만큼 판자가
  기울고, 화물은 낮은 쪽으로 미끄러진다. 받을 때는 수평이 안전하고,
  넣을 때는 일부러 오른쪽을 낮춰야 한다. 같은 조작이 안전장치이자 무기다.
"""
import math
import random

import pygame

from console_ui import (BG, GOLD, INK, LINE, MUTED, P1, P2, PANEL, PANEL_HI, WHITE,
                        ConsoleDisplay, back_combo, options)
from game_fx import Sparks, glow
from theme import EMBER, SKIN, mix, shade

FIELD = pygame.Rect(24, 84, 752, 332)
FLOOR_Y = 392                   # 두 사람이 서 있는 바닥
PLANK_LEN = 176
HALF = PLANK_LEN // 2
PLANK_THICK = 12
CRATE = 34
HAND_HIGH, HAND_LOW = 250, 340  # 손 높이. 값이 작을수록 높이 든 것이다.
TILT_LIMIT = 52                 # 양끝 높이차 상한. 이 이상은 손이 판자를 놓친다.
CX_MIN, CX_MAX = 122, 620       # 판자 중심이 오갈 수 있는 범위
CHUTE = pygame.Rect(704, 290, 76, 28)   # 투입구. 화물이 여기 닿으면 배달 성공
SLIDE_G = 940                   # 기울기 1 일 때 화물이 받는 가속
GRAVITY = 900
CARRY_SPEED = 230               # 두 사람이 같은 방향으로 밀 때의 이동 속도
HAND_SPEED = 190
LIVES = 3
WARN_TIME = 0.9                 # 낙하 예고 시간. 부스에서 처음 잡은 사람도 반응할 수 있게.
SPAWN_X = (86, 660)
CRATE_TONES = ((178, 128, 84), (150, 118, 98), (190, 150, 96))


class Crate:
    """화물 하나. 판자 위에서는 u/vel(판자 축 1차원), 공중에서는 pos/fall(2차원)을 쓴다.

    두 상태를 한 객체로 두면 '받았다/떨어뜨렸다' 가 리스트 이동 한 번으로 끝난다.
    """

    __slots__ = ('u', 'vel', 'pos', 'fall', 'grace', 'tone')

    def __init__(self, x, y, fall, tone):
        self.pos = pygame.Vector2(x, y)
        self.fall = pygame.Vector2(fall)
        self.u = 0.0
        self.vel = 0.0
        self.grace = 0.0        # 방금 판자에서 굴러떨어진 화물이 곧바로 다시 얹히지 않게.
        self.tone = tone

    def rect(self):
        return pygame.Rect(round(self.pos.x) - CRATE // 2, round(self.pos.y) - CRATE // 2,
                           CRATE, CRATE)


class CargoGame:
    def __init__(self, fullscreen=True, margin=0):
        self.ui = ConsoleDisplay(fullscreen, margin)
        self.sparks = Sparks()
        self.chute_glow = glow(34, GOLD)
        self.crate_art = {}
        self.state = 'title'
        self.reset()

    def reset(self):
        self.cx = 300.0
        self.hands = [300.0, 300.0]
        self.load = []          # 판자 위 화물
        self.air = []           # 공중 화물
        self.warnings = []      # [예고 x, 남은 시간]
        self.delivered = 0
        self.lives = LIVES
        self.next_drop = 1.4
        self.flash = 0.0
        self.elapsed = 0.0

    # --- 판자 기하 -------------------------------------------------------

    def ends(self):
        return (pygame.Vector2(self.cx - HALF, self.hands[0]),
                pygame.Vector2(self.cx + HALF, self.hands[1]))

    def axis(self):
        """판자 방향 단위 벡터와 기울기. 미끄러짐·회전·착지 판정이 모두 여기서 나온다."""
        left, right = self.ends()
        return (right - left).normalize(), (right.y - left.y) / PLANK_LEN

    def seat(self, crate, direction):
        """판자 축 좌표 u 를 화면 좌표로 옮긴다. 화물은 판자 윗면에 앉는다."""
        left, right = self.ends()
        up = pygame.Vector2(direction.y, -direction.x)
        return (left + right) / 2 + direction * crate.u + up * (PLANK_THICK / 2 + CRATE / 2)

    def surface_at(self, x):
        left, right = self.ends()
        ratio = (x - left.x) / PLANK_LEN
        return left.y + (right.y - left.y) * ratio - PLANK_THICK / 2

    # --- 진행 -----------------------------------------------------------

    def update(self, dt, pads):
        dt = min(dt, 0.035)
        self.elapsed += dt
        self.flash = max(0.0, self.flash - dt * 2.4)
        self.sparks.update(dt)
        self.move_plank(dt, pads)
        self.slide_load(dt)
        self.fly(dt)
        self.schedule(dt)

    def move_plank(self, dt, pads):
        intent = sum(pad.held['right'] - pad.held['left'] for pad in pads[:2])
        self.cx = max(CX_MIN, min(CX_MAX, self.cx + intent / 2 * CARRY_SPEED * dt))
        for i, pad in enumerate(pads[:2]):
            self.hands[i] = max(HAND_HIGH, min(HAND_LOW, self.hands[i] +
                                (pad.held['down'] - pad.held['up']) * HAND_SPEED * dt))
        # 한계를 넘은 높이차는 두 손이 같은 양씩 되돌린다. 한쪽만 고치면
        # 먼저 버튼을 뗀 사람이 손해를 보고, 그러면 협동이 아니라 눈치 싸움이 된다.
        gap = self.hands[1] - self.hands[0]
        if abs(gap) > TILT_LIMIT:
            over = (abs(gap) - TILT_LIMIT) / 2 * (1 if gap > 0 else -1)
            self.hands[0] = max(HAND_HIGH, min(HAND_LOW, self.hands[0] + over))
            self.hands[1] = max(HAND_HIGH, min(HAND_LOW, self.hands[1] - over))

    def slide_load(self, dt):
        direction, slope = self.axis()
        for crate in self.load:
            # 살짝 기운 정도는 정지 마찰이 잡아 준다. 그래야 '수평 유지' 가
            # 픽셀 단위 곡예가 아니라 실제로 쓸 수 있는 전략이 된다.
            if abs(slope) < 0.05 and abs(crate.vel) < 14:
                crate.vel = 0.0
            else:
                crate.vel += SLIDE_G * slope * dt
                crate.vel -= crate.vel * 2.6 * dt
            crate.u += crate.vel * dt
        self.separate()
        for crate in list(self.load):
            if abs(crate.u) > HALF + CRATE * 0.35:
                self.load.remove(crate)
                crate.pos = self.seat(crate, direction)
                crate.fall = direction * crate.vel
                crate.grace = 0.18
                self.air.append(crate)

    def separate(self):
        """판자 위 화물끼리 겹치지 않게 민다. 축 하나짜리 문제라 짧은 완화로 충분하다."""
        self.load.sort(key=lambda crate: crate.u)
        for _ in range(2):
            for a, b in zip(self.load, self.load[1:]):
                overlap = CRATE - (b.u - a.u)
                if overlap > 0:
                    a.u -= overlap / 2
                    b.u += overlap / 2
                    a.vel = b.vel = (a.vel + b.vel) / 2

    def fly(self, dt):
        left, right = self.ends()
        for crate in list(self.air):
            crate.grace = max(0.0, crate.grace - dt)
            crate.fall.y += GRAVITY * dt
            previous = crate.pos.y
            crate.pos += crate.fall * dt
            if crate.fall.y > 0 and crate.rect().colliderect(CHUTE):
                self.air.remove(crate)
                self.delivered += 1
                self.sparks.burst(CHUTE.center, GOLD, 16)
                continue
            # 착지는 '이번 프레임에 윗면을 통과했는가' 로 본다. 낙하가 빨라져도
            # 화물이 판자를 뚫고 지나가는 일이 없다.
            if not crate.grace and left.x <= crate.pos.x <= right.x and crate.fall.y > 0:
                top = self.surface_at(crate.pos.x)
                if previous + CRATE / 2 <= top <= crate.pos.y + CRATE / 2:
                    self.catch(crate)
                    continue
            if crate.pos.y - CRATE / 2 > FLOOR_Y:
                self.air.remove(crate)
                self.smash(crate)

    def catch(self, crate):
        direction, _ = self.axis()
        left, right = self.ends()
        self.air.remove(crate)
        crate.u = max(-HALF, min(HALF, (crate.pos.x - (left.x + right.x) / 2) / direction.x))
        crate.vel = crate.fall.x * 0.25
        self.load.append(crate)
        self.separate()
        self.sparks.burst(crate.pos, crate.tone, 10)

    def smash(self, crate):
        self.lives -= 1
        self.flash = 1.0
        self.sparks.burst((crate.pos.x, FLOOR_Y), EMBER, 18)
        if self.lives <= 0:
            self.state = 'over'

    def schedule(self, dt):
        for warning in list(self.warnings):
            warning[1] -= dt
            if warning[1] <= 0:
                self.warnings.remove(warning)
                speed = min(250, 130 + self.delivered * 5)
                self.air.append(Crate(warning[0], FIELD.top + 36, (0, speed),
                                      random.choice(CRATE_TONES)))
        self.next_drop -= dt
        if self.next_drop <= 0:
            # 공중에 셋 이상 두지 않는다. 화면이 복잡해지는 만큼 어려워지는 게 아니라
            # 그냥 손쓸 수 없어진다.
            if len(self.air) + len(self.warnings) < 3:
                self.warnings.append([random.randint(*SPAWN_X), WARN_TIME])
                self.next_drop = max(1.3, 2.7 - self.delivered * 0.05)
            else:
                self.next_drop = 0.4

    # --- 그리기 ----------------------------------------------------------

    def crate_face(self, tone, angle):
        """각도별로 한 번만 만들어 두고 재사용한다. Pi 에서 매 프레임 회전하면 아깝다."""
        key = (tone, round(angle / 4) * 4)
        art = self.crate_art.get(key)
        if art is None:
            base = pygame.Surface((CRATE, CRATE), pygame.SRCALPHA)
            pygame.draw.rect(base, shade(tone, 0.55), (0, 0, CRATE, CRATE), border_radius=4)
            pygame.draw.rect(base, tone, (2, 2, CRATE - 4, CRATE - 4), border_radius=3)
            pygame.draw.rect(base, shade(tone, 1.18), (2, 2, CRATE - 4, 9), border_radius=3)
            pygame.draw.line(base, shade(tone, 0.7), (3, CRATE - 11), (CRATE - 4, CRATE - 11), 2)
            pygame.draw.line(base, shade(tone, 0.7), (CRATE // 2, 12), (CRATE // 2, CRATE - 12), 2)
            art = pygame.transform.rotate(base, key[1])
            self.crate_art[key] = art
        return art

    def draw_header(self):
        ui = self.ui
        ui.text('CARGO CARRY', 32, 26, 28)
        ui.text(ui.label('둘이서 짐 나르기', 'CO-OP DELIVERY'), 32, 60, 14, MUTED)
        ui.text(str(self.delivered), 400, 16, 40, GOLD, center=True)
        ui.text(ui.label('배달 완료', 'DELIVERED'), 400, 62, 14, MUTED, center=True)
        for i in range(LIVES):
            x = 690 + i * 30
            alive = i < self.lives
            color = P1 if alive else LINE
            if alive and self.flash > 0:
                color = mix(P1, WHITE, self.flash)
            pygame.draw.rect(ui.screen, color, (x, 30, 22, 22), 0 if alive else 2, border_radius=4)
            if alive:
                pygame.draw.line(ui.screen, shade(color, 0.6), (x + 3, 40), (x + 18, 40), 2)
        ui.text(ui.label('남은 기회', 'LIVES'), 724, 58, 14, MUTED, center=True)

    def draw_field(self):
        ui = self.ui
        ui.panel(FIELD, fill=PANEL, border=LINE, radius=10)
        for x in range(FIELD.left + 24, FIELD.right, 32):
            pygame.draw.line(ui.screen, (34, 43, 58), (x, FIELD.top + 4), (x, FLOOR_Y - 2))
        for y in range(FIELD.top + 20, FLOOR_Y, 32):
            pygame.draw.line(ui.screen, (34, 43, 58), (FIELD.left + 4, y), (FIELD.right - 4, y))
        # 천장 레일. 화물이 어디서 오는지 설명해 주고, 비어 보이던 윗공간을 잡아 준다.
        rail = pygame.Rect(FIELD.left + 3, FIELD.top + 8, FIELD.width - 6, 9)
        pygame.draw.rect(ui.screen, shade(PANEL, 1.5), rail)
        pygame.draw.line(ui.screen, LINE, (rail.left, rail.bottom), (rail.right, rail.bottom), 2)
        for x in range(FIELD.left + 52, FIELD.right - 20, 104):
            pygame.draw.line(ui.screen, shade(PANEL, 1.28), (x, rail.bottom), (x, rail.bottom + 13), 4)
            pygame.draw.circle(ui.screen, shade(PANEL, 1.45), (x, rail.bottom + 15), 4)
        # 금색 ㄱ자 모서리. 다른 화면과 같은 규칙으로 경기장 끝을 표시한다.
        for corner_x, step_x in ((FIELD.left + 14, 1), (FIELD.right - 14, -1)):
            for corner_y, step_y in ((FIELD.top + 14, 1), (FIELD.bottom - 14, -1)):
                pygame.draw.line(ui.screen, GOLD, (corner_x, corner_y),
                                 (corner_x + step_x * 22, corner_y), 3)
                pygame.draw.line(ui.screen, GOLD, (corner_x, corner_y),
                                 (corner_x, corner_y + step_y * 22), 3)
        pygame.draw.rect(ui.screen, shade(PANEL, 0.62),
                         (FIELD.left + 3, FLOOR_Y, FIELD.width - 6, FIELD.bottom - FLOOR_Y - 3))
        pygame.draw.line(ui.screen, EMBER, (FIELD.left + 3, FLOOR_Y), (FIELD.right - 3, FLOOR_Y), 2)

    def draw_warnings(self):
        ui = self.ui
        for x, left in self.warnings:
            if (self.elapsed * 8) % 2 < 1:
                continue
            for y in range(FIELD.top + 38, FLOOR_Y - 40, 20):
                pygame.draw.line(ui.screen, shade(GOLD, 0.45), (x, y), (x, y + 9), 2)
            pygame.draw.polygon(ui.screen, GOLD, [(x - 11, FIELD.top + 19), (x + 11, FIELD.top + 19),
                                                 (x, FIELD.top + 34)])

    def draw_carrier(self, index, color):
        ui = self.ui
        x = round(self.cx + (HALF if index else -HALF))
        hand = round(self.hands[index])
        for side in (-1, 1):
            pygame.draw.line(ui.screen, INK, (x + side * 6, 362), (x + side * 7, FLOOR_Y), 7)
        pygame.draw.rect(ui.screen, color, (x - 10, 336, 20, 28), border_radius=5)
        pygame.draw.rect(ui.screen, shade(color, 1.25), (x - 10, 336, 20, 9), border_radius=4)
        for side in (-1, 1):
            pygame.draw.line(ui.screen, SKIN, (x + side * 8, 342), (x + side * 3, hand + 4), 5)
        pygame.draw.circle(ui.screen, SKIN, (x, 322), 11)
        pygame.draw.circle(ui.screen, color, (x, 322), 11,
                           draw_top_left=True, draw_top_right=True)
        pygame.draw.line(ui.screen, shade(color, 1.3), (x - 13, 322), (x + 13, 322), 3)
        ui.text('1P' if index == 0 else '2P', x, FLOOR_Y + 4, 14, color, center=True)

    def draw_plank(self):
        ui = self.ui
        left, right = self.ends()
        pygame.draw.line(ui.screen, INK, left, right, PLANK_THICK + 4)
        pygame.draw.line(ui.screen, (156, 118, 78), left, right, PLANK_THICK)
        pygame.draw.line(ui.screen, (196, 154, 104),
                         left + (0, -3), right + (0, -3), 3)

    def draw_hopper(self):
        ui = self.ui
        ui.screen.blit(self.chute_glow, (CHUTE.centerx - 34, CHUTE.centery - 34))
        pygame.draw.polygon(ui.screen, shade(PANEL_HI, 1.1),
                            [(700, 290), (784, 290), (762, 346), (722, 346)])
        pygame.draw.polygon(ui.screen, LINE,
                            [(700, 290), (784, 290), (762, 346), (722, 346)], 2)
        pygame.draw.rect(ui.screen, PANEL_HI, (722, 344, 40, FLOOR_Y - 344))
        pygame.draw.rect(ui.screen, LINE, (722, 344, 40, FLOOR_Y - 344), 2)
        for i in range(min(self.delivered, 4)):
            pygame.draw.rect(ui.screen, shade(CRATE_TONES[i % 3], 0.8),
                             (726, FLOOR_Y - 12 - i * 11, 32, 9), border_radius=2)
        pygame.draw.line(ui.screen, GOLD, (700, 290), (784, 290), 3)
        # 투입구가 어디인지는 금색 하나로 끝낸다. 처음 보는 사람도 목표를 즉시 안다.
        ui.text(ui.label('투입구', 'DROP HERE'), 742, 266, 14, GOLD, center=True)

    def draw(self):
        ui = self.ui
        ui.screen.fill(BG)
        self.draw_header()
        self.draw_field()
        self.draw_warnings()
        for index, color in ((0, P1), (1, P2)):
            self.draw_carrier(index, color)
        self.draw_plank()
        direction, _ = self.axis()
        angle = -math.degrees(math.atan2(direction.y, direction.x))
        for crate in self.load:
            art = self.crate_face(crate.tone, angle)
            ui.screen.blit(art, art.get_rect(center=self.seat(crate, direction)))
        for crate in self.air:
            art = self.crate_face(crate.tone, 0)
            ui.screen.blit(art, art.get_rect(center=crate.pos))
        self.sparks.draw(ui.screen)
        self.draw_hopper()
        ui.text(ui.label('좌우: 함께 이동   위/아래: 내 쪽 높이   START + SELECT: 메뉴',
                         'L/R: Move together   Up/Down: Your end   START + SELECT: Menu'),
                400, 438, 18, MUTED, center=True)
        if self.state != 'play':
            self.draw_overlay()

    def draw_overlay(self):
        ui = self.ui
        ui.shade(200)
        card = pygame.Rect(84, 142, 632, 208)
        ui.panel(card, fill=PANEL_HI, border=GOLD, radius=14)
        heading, accent = {
            'title': (ui.label('둘이서 짐 나르기', 'CARGO CARRY'), GOLD),
            'paused': (ui.label('일시정지', 'PAUSED'), GOLD),
            'over': (ui.label(f'{self.delivered}개 배달!', f'{self.delivered} DELIVERED!'), P2),
        }[self.state]
        ui.text(heading, 400, card.top + 20, 34, accent, center=True)
        pygame.draw.line(ui.screen, LINE, (card.left + 60, card.top + 72),
                         (card.right - 60, card.top + 72))
        if self.state == 'over':
            ui.text(ui.label('화물 세 개를 놓쳤습니다.', 'Three crates hit the floor.'),
                    400, card.top + 86, 22, MUTED, center=True)
            ui.text(ui.label('한 번 더 해볼까요?', 'Try again?'), 400, card.top + 122, 22,
                    WHITE, center=True)
        else:
            ui.text(ui.label('판자는 둘이 함께 든다. 좌우는 두 사람 의도의 평균으로 움직인다.',
                             'One plank, two carriers. Left/right moves on the average of both.'),
                    400, card.top + 86, 18, MUTED, center=True)
            ui.text(ui.label('1P  A / D · W / S', '1P  A / D · W / S'), 290, card.top + 118, 22,
                    P1, center=True)
            ui.text(ui.label('2P  ← / → · ↑ / ↓', '2P  L/R · Up/Down'), 510, card.top + 118, 22,
                    P2, center=True)
        ui.text(ui.label('A / START: 시작·계속        SELECT: 메뉴',
                         'A / START: Play·Resume        SELECT: Menu'),
                400, card.top + 162, 16, MUTED, center=True)

    def run(self):
        while True:
            dt = self.ui.clock.tick(60) / 1000
            closed, pads = self.ui.poll()
            if closed or back_combo(pads):
                break
            pressed = lambda *keys: any(p.any_pressed(*keys) for p in pads)
            if pressed('select'):
                break
            if self.state != 'play' and pressed('start', 'punch'):
                if self.state in ('title', 'over'):
                    self.reset()
                self.state = 'play'
            elif self.state == 'play' and pressed('start'):
                self.state = 'paused'
            if self.state == 'play':
                self.update(dt, pads)
            self.draw()
            self.ui.present()
        pygame.quit()


if __name__ == '__main__':
    args = options()
    CargoGame(args.fullscreen, args.margin).run()
