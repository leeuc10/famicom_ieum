"""Two-player paddle game for the console controllers."""
import random

import pygame

from console_ui import BG, GOLD, MUTED, WHITE, ConsoleDisplay, back_combo, options


class PaddleGame:
    def __init__(self, fullscreen=True, margin=0):
        self.ui = ConsoleDisplay(fullscreen, margin)
        self.scores = [0, 0]
        self.paddles = [pygame.Rect(42, 218, 14, 84), pygame.Rect(744, 218, 14, 84)]
        self.ys = [218.0, 218.0]
        self.state = 'title'
        self.serve()

    def serve(self):
        self.ball = pygame.Vector2(400, 254)
        self.velocity = pygame.Vector2(random.choice((-260, 260)), random.choice((-120, 120)))
        self.countdown = 0.8

    def update(self, dt, pads):
        dt = min(dt, 0.035)
        for i, pad in enumerate(pads[:2]):
            self.ys[i] = max(92, min(332, self.ys[i] +
                                    (pad.held['down'] - pad.held['up']) * 320 * dt))
            self.paddles[i].y = round(self.ys[i])
        if self.countdown > 0:
            self.countdown -= dt
            return
        self.ball += self.velocity * dt
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
                self.ball.x = paddle.right + 8 if i == 0 else paddle.left - 8
                self.velocity.x = min(abs(self.velocity.x) * 1.06, 450) * (1 if i == 0 else -1)
                self.velocity.y = (self.ball.y - paddle.centery) / 42 * 240
        if self.ball.x < -8 or self.ball.x > 808:
            scorer = 1 if self.ball.x < 0 else 0
            self.scores[scorer] += 1
            if self.scores[scorer] >= 7:
                self.state = 'over'
            else:
                self.serve()

    def draw(self):
        ui = self.ui
        ui.screen.fill(BG)
        ui.text('PADDLE DUEL', 32, 24, 28)
        ui.text(f'{self.scores[0]}    :    {self.scores[1]}', 580, 20, 40, GOLD, center=True)
        pygame.draw.rect(ui.screen, (30, 36, 49), (24, 92, 752, 324), border_radius=10)
        for y in range(100, 408, 24):
            pygame.draw.rect(ui.screen, (69, 75, 93), (398, y, 4, 12))
        for paddle, color in zip(self.paddles, ((235, 102, 108), (102, 187, 220))):
            pygame.draw.rect(ui.screen, color, paddle, border_radius=5)
        pygame.draw.circle(ui.screen, WHITE, (round(self.ball.x), round(self.ball.y)), 8)
        ui.text(ui.label('위/아래: 이동   START: 일시정지   START + SELECT: 메뉴',
                         'Up/Down: Move   START: Pause   START + SELECT: Menu'),
                400, 438, 18, MUTED, center=True)
        if self.state != 'play':
            pygame.draw.rect(ui.screen, (43, 49, 66), (90, 167, 620, 163), border_radius=12)
            title = {'title': ui.label('패들 듀얼 · 7점 먼저!', 'PADDLE DUEL · FIRST TO 7'),
                     'paused': ui.label('일시정지', 'PAUSED'),
                     'over': ui.label(f'{1 if self.scores[0] >= 7 else 2}P 승리!',
                                      f'PLAYER {1 if self.scores[0] >= 7 else 2} WINS!')}[self.state]
            ui.text(title, 400, 184, 28, GOLD, center=True)
            ui.text(ui.label('1P: W / S       2P: 방향키 위 / 아래',
                             '1P: W / S       2P: UP / DOWN'), 400, 233, 22, center=True)
            ui.text(ui.label('A / START: 시작·계속   SELECT: 메뉴',
                             'A / START: Play / Resume   SELECT: Menu'), 400, 283, 18, MUTED, center=True)

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
