"""Two-player paddle game for the console controllers."""
import random
import math
from game_fx import Sparks, glow

import pygame

from console_ui import (BG, GOLD, INK, LINE, MUTED, P1, P2, PANEL, PANEL_HI, WHITE,
                        ConsoleDisplay, back_combo, options)
from theme import shade

COURT = pygame.Rect(24, 92, 752, 324)
TARGET = 7


class PaddleGame:
    def __init__(self, fullscreen=True, margin=0):
        self.ui = ConsoleDisplay(fullscreen, margin)
        self.sparks = Sparks()
        self.ball_glow = glow(28, P2)
        self.scores = [0, 0]
        self.paddles = [pygame.Rect(42, 218, 14, 84), pygame.Rect(744, 218, 14, 84)]
        self.ys = [218.0, 218.0]
        self.state = 'title'
        self.serve()

    def serve(self):
        self.ball = pygame.Vector2(400, 254)
        self.velocity = pygame.Vector2(random.choice((-260, 260)), random.choice((-120, 120)))
        self.countdown = 0.8
        self.trail = []

    def update(self, dt, pads):
        dt = min(dt, 0.035)
        self.sparks.update(dt)
        for i, pad in enumerate(pads[:2]):
            self.ys[i] = max(92, min(332, self.ys[i] +
                                    (pad.held['down'] - pad.held['up']) * 320 * dt))
            self.paddles[i].y = round(self.ys[i])
        if self.countdown > 0:
            self.countdown -= dt
            return
        self.ball += self.velocity * dt
        # 잔상은 공이 어디서 왔는지 보여 준다. 800x480 에서 공이 작아 놓치기 쉽다.
        self.trail.append((self.ball.x, self.ball.y))
        del self.trail[:-9]
        if self.ball.y < 100:
            self.ball.y = 100
            self.velocity.y = abs(self.velocity.y)
        elif self.ball.y > 408:
            self.ball.y = 408
            self.velocity.y = -abs(self.velocity.y)
        ball_rect = pygame.Rect(round(self.ball.x) - 8, round(self.ball.y) - 8, 16, 16)
        for i, paddle in enumerate(self.paddles):
            toward = self.velocity.x < 0 if i == 0 else self.velocity.x > 0
            if toward and paddle.colliderect(ball_rect):
                self.sparks.burst(self.ball, P1 if i == 0 else P2, 14)
                self.ball.x = paddle.right + 8 if i == 0 else paddle.left - 8
                self.velocity.x = min(abs(self.velocity.x) * 1.06, 450) * (1 if i == 0 else -1)
                self.velocity.y = (self.ball.y - paddle.centery) / 42 * 240
        if self.ball.x < -8 or self.ball.x > 808:
            scorer = 1 if self.ball.x < 0 else 0
            self.scores[scorer] += 1
            if self.scores[scorer] >= TARGET:
                self.state = 'over'
            else:
                self.serve()

    def draw_header(self):
        ui = self.ui
        ui.text('PADDLE DUEL', 32, 26, 28)
        ui.text(str(self.scores[0]), 356, 16, 40, P1, center=True)
        ui.text(':', 400, 20, 34, LINE, center=True)
        ui.text(str(self.scores[1]), 444, 16, 40, P2, center=True)
        ui.text(ui.label(f'{TARGET}점 먼저', f'FIRST TO {TARGET}'), 400, 62, 14, MUTED, center=True)

    def draw_court(self):
        ui = self.ui
        ui.panel(COURT, fill=PANEL, border=LINE, radius=10)
        for x in range(COURT.left+20, COURT.right, 32):
            pygame.draw.line(ui.screen, (34,43,58), (x,COURT.top+4),(x,COURT.bottom-4))
        for y in range(COURT.top+16,COURT.bottom,32):
            pygame.draw.line(ui.screen, (34,43,58), (COURT.left+4,y),(COURT.right-4,y))
        pygame.draw.circle(ui.screen, P2, COURT.center, 52, 2)
        pygame.draw.circle(ui.screen, LINE, COURT.center, 59, 1)
        for y in range(COURT.top + 10, COURT.bottom - 8, 24):
            pygame.draw.rect(ui.screen, LINE, (398, y, 4, 12))
        # 금색 ㄱ자 모서리. 코트가 어디까지인지 한눈에 잡아 준다.
        for corner_x, step_x in ((COURT.left + 14, 1), (COURT.right - 14, -1)):
            for corner_y, step_y in ((COURT.top + 14, 1), (COURT.bottom - 14, -1)):
                pygame.draw.line(ui.screen, GOLD, (corner_x, corner_y),
                                 (corner_x + step_x * 22, corner_y), 3)
                pygame.draw.line(ui.screen, GOLD, (corner_x, corner_y),
                                 (corner_x, corner_y + step_y * 22), 3)
        ui.text('1P', 150, COURT.top + 16, 14, P1, center=True)
        ui.text('2P', 650, COURT.top + 16, 14, P2, center=True)

    def draw_play(self):
        ui = self.ui
        for paddle, color in zip(self.paddles, (P1, P2)):
            pygame.draw.rect(ui.screen, INK, paddle.inflate(6, 6), border_radius=7)
            pygame.draw.rect(ui.screen, color, paddle, border_radius=5)
            pygame.draw.rect(ui.screen, shade(color, 1.25),
                             (paddle.x + 3, paddle.y + 6, paddle.width - 6, 14), border_radius=3)
        for i, (x, y) in enumerate(self.trail):
            fade = (i + 1) / (len(self.trail) + 1)
            pygame.draw.circle(ui.screen, shade(PANEL_HI, 1 + fade), (round(x), round(y)),
                               round(3 + 4 * fade))
        ui.screen.blit(self.ball_glow, (round(self.ball.x)-28, round(self.ball.y)-28))
        self.sparks.draw(ui.screen)
        pygame.draw.circle(ui.screen, INK, (round(self.ball.x), round(self.ball.y)), 10)
        pygame.draw.circle(ui.screen, WHITE, (round(self.ball.x), round(self.ball.y)), 8)
        if self.countdown > 0 and self.state == 'play':
            ui.text(ui.label('준비', 'READY'), 400, COURT.centery + 68, 18, GOLD, center=True)

    def draw(self):
        ui = self.ui
        ui.screen.fill(BG)
        self.draw_header()
        self.draw_court()
        self.draw_play()
        ui.text(ui.label('위/아래: 이동   START: 일시정지   START + SELECT: 메뉴',
                         'Up/Down: Move   START: Pause   START + SELECT: Menu'),
                400, 438, 18, MUTED, center=True)
        if self.state != 'play':
            self.draw_overlay()

    def draw_overlay(self):
        ui = self.ui
        ui.shade(200)
        card = pygame.Rect(100, 158, 600, 178)
        ui.panel(card, fill=PANEL_HI, border=GOLD, radius=14)
        winner = 1 if self.scores[0] >= TARGET else 2
        heading, accent = {
            'title': (ui.label('패들 듀얼', 'PADDLE DUEL'), GOLD),
            'paused': (ui.label('일시정지', 'PAUSED'), GOLD),
            'over': (ui.label(f'{winner}P 승리!', f'PLAYER {winner} WINS!'),
                     P1 if winner == 1 else P2),
        }[self.state]
        ui.text(heading, 400, card.top + 24, 34, accent, center=True)
        pygame.draw.line(ui.screen, LINE, (card.left + 60, card.top + 76),
                         (card.right - 60, card.top + 76))
        ui.text(ui.label('1P  W / S', '1P  W / S'), 290, card.top + 92, 22, P1, center=True)
        ui.text(ui.label('2P  위 / 아래', '2P  UP / DOWN'), 510, card.top + 92, 22, P2, center=True)
        ui.text(ui.label('A / START: 시작·계속        SELECT: 메뉴',
                         'A / START: Play·Resume        SELECT: Menu'),
                400, card.top + 132, 16, MUTED, center=True)

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
                    self.scores = [0, 0]
                    self.ys = [218.0, 218.0]
                    self.serve()
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
    PaddleGame(args.fullscreen, args.margin).run()
