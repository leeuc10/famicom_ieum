"""Prism Break: three short, controller-friendly solo brick fields."""
import math
import pygame
from console_ui import (BG, GOLD, LINE, MUTED, P1, P2, PANEL, PANEL_HI, WHITE,
                        ConsoleDisplay, back_combo, options)
from game_fx import Sparks

FIELD = pygame.Rect(24, 86, 752, 330)
RADIUS = 7
COLORS = (P1, GOLD, P2, (167, 144, 236))


class PrismBreak:
    def __init__(self, fullscreen=True, margin=0):
        self.ui = ConsoleDisplay(fullscreen, margin)
        self.player = 0
        self.best = 0
        self.reset()
        self.state = 'title'

    def reset(self):
        self.score, self.lives, self.level = 0, 3, 1
        self.sparks = Sparks()
        self.new_level()

    def new_level(self):
        self.bricks = []
        for row in range(4):
            for col in range(10):
                if self.level == 2 and (row + col) % 3 == 0:
                    continue
                if self.level == 3 and row in (1, 2) and col in (0, 4, 5, 9):
                    continue
                hp = 2 if self.level == 3 and row == 0 else 1
                self.bricks.append([pygame.Rect(43+col*72, 113+row*29, 66, 22), hp, row])
        self.serve()

    def serve(self):
        self.x = 400.0
        self.paddle = pygame.Rect(344, 382, 112, 12)
        self.ball = pygame.Vector2(self.x, self.paddle.top-RADIUS-1)
        self.velocity = pygame.Vector2(0, 0)
        self.trail = []
        self.state = 'ready'

    def launch(self):
        self.velocity = pygame.Vector2(100, -270-25*self.level)
        self.state = 'play'

    def handle(self, pads):
        if back_combo(pads):
            return False
        if self.state == 'title':
            for i, pad in enumerate(pads):
                if pad.any_pressed('select'):
                    return False
                if pad.any_pressed('start', 'punch'):
                    self.player = i
                    self.reset()
                    break
            return True
        if len(pads) <= self.player:
            return True
        pad = pads[self.player]
        if pad.any_pressed('select'):
            return False
        if self.state in ('over', 'won'):
            if pad.any_pressed('start', 'punch'):
                self.reset()
        elif self.state == 'paused':
            if pad.any_pressed('start', 'punch'):
                self.state = self.resume_state
        elif pad.any_pressed('start'):
            self.resume_state = self.state
            self.state = 'paused'
        elif self.state == 'ready' and pad.any_pressed('punch'):
            self.launch()
        return True

    def update(self, dt, pads):
        if self.state not in ('play', 'ready') or len(pads) <= self.player:
            return
        dt = max(0, min(dt, .05))
        self.sparks.update(dt)
        pad = pads[self.player]
        # Small steps keep fast balls from skipping thin bricks or the paddle.
        steps = max(1, math.ceil(dt / .004))
        for _ in range(steps):
            step = dt / steps
            speed = 200 if pad.held['kick'] else 430
            self.x = max(FIELD.left+56, min(FIELD.right-56,
                         self.x + (pad.held['right']-pad.held['left'])*speed*step))
            self.paddle.centerx = round(self.x)
            if self.state == 'ready':
                self.ball.update(self.x, self.paddle.top-RADIUS-1)
                continue
            self.advance_ball(step)
            if self.state != 'play':
                break
        if self.state == 'play':
            self.trail.append(tuple(self.ball))
            del self.trail[:-8]

    def advance_ball(self, dt):
        previous = self.ball.copy()
        self.ball += self.velocity*dt
        if self.ball.x < FIELD.left+RADIUS:
            self.ball.x = FIELD.left+RADIUS
            self.velocity.x = abs(self.velocity.x)
        elif self.ball.x > FIELD.right-RADIUS:
            self.ball.x = FIELD.right-RADIUS
            self.velocity.x = -abs(self.velocity.x)
        if self.ball.y < FIELD.top+RADIUS:
            self.ball.y = FIELD.top+RADIUS
            self.velocity.y = abs(self.velocity.y)
        if (self.velocity.y > 0 and previous.y+RADIUS <= self.paddle.top
                and self.ball.y+RADIUS >= self.paddle.top
                and self.paddle.left-RADIUS <= self.ball.x <= self.paddle.right+RADIUS):
            offset = max(-1, min(1, (self.ball.x-self.x)/56))
            angle = offset*math.radians(62)
            speed = min(470, self.velocity.length()+5)
            self.velocity.update(math.sin(angle)*speed, -math.cos(angle)*speed)
            self.ball.y = self.paddle.top-RADIUS
            self.sparks.burst(self.ball, P2, 6)
        for brick in self.bricks:
            rect, hp, row = brick
            box = rect.inflate(RADIUS*2, RADIUS*2)
            if not (box.left <= self.ball.x <= box.right and box.top <= self.ball.y <= box.bottom):
                continue
            if previous.y <= box.top:
                self.ball.y = box.top-.01
                self.velocity.y = -abs(self.velocity.y)
            elif previous.y >= box.bottom:
                self.ball.y = box.bottom+.01
                self.velocity.y = abs(self.velocity.y)
            elif previous.x <= box.left:
                self.ball.x = box.left-.01
                self.velocity.x = -abs(self.velocity.x)
            else:
                self.ball.x = box.right+.01
                self.velocity.x = abs(self.velocity.x)
            brick[1] -= 1
            self.score += 10
            self.sparks.burst(self.ball, COLORS[row], 10)
            if brick[1] == 0:
                self.bricks.remove(brick)
                self.score += 15
            self.best = max(self.best, self.score)
            break
        if not self.bricks:
            if self.level == 3:
                self.score += self.lives*100
                self.best = max(self.best, self.score)
                self.state = 'won'
            else:
                self.level += 1
                self.new_level()
        elif self.ball.y-RADIUS > FIELD.bottom:
            self.lives -= 1
            if self.lives == 0:
                self.state = 'over'
            else:
                self.serve()

    def draw(self):
        ui = self.ui
        ui.screen.fill(BG)
        ui.text('PRISM BREAK', 28, 20, 28, P2)
        ui.text(f'{self.score:05d}', 420, 16, 34, GOLD, center=True)
        ui.text(f'STAGE {self.level} / 3', 636, 27, 18, WHITE)
        ui.panel(FIELD, fill=PANEL, border=LINE)
        for x in range(44, 775, 32):
            pygame.draw.line(ui.screen, (34, 40, 56), (x, 90), (x, 412))
        for rect, hp, row in self.bricks:
            pygame.draw.rect(ui.screen, COLORS[row], rect, border_radius=4)
            pygame.draw.line(ui.screen, WHITE, (rect.x+6, rect.y+3), (rect.right-6, rect.y+3))
            if hp == 2:
                pygame.draw.rect(ui.screen, PANEL, rect.inflate(-12, -10), 2, border_radius=2)
        for i, point in enumerate(self.trail):
            pygame.draw.circle(ui.screen, MUTED, point, max(1, i//2))
        pygame.draw.rect(ui.screen, P2, self.paddle, border_radius=6)
        pygame.draw.rect(ui.screen, WHITE, self.paddle.inflate(-20, -6), border_radius=3)
        pygame.draw.circle(ui.screen, GOLD, self.ball, RADIUS+2)
        pygame.draw.circle(ui.screen, WHITE, self.ball, RADIUS)
        self.sparks.draw(ui.screen)
        ui.text(f'HP {self.lives}', 32, 430, 18, P1)
        ui.text(ui.label('좌우 이동  B 정밀 이동  START 정지', 'Left/Right Move  Hold B Precision  START Pause'),
                400, 430, 18, MUTED, center=True)
        ui.text(ui.label('SELECT: 메뉴', 'SELECT: Menu'), 400, 455, 14, MUTED, center=True)
        if self.state == 'ready':
            ui.text(ui.label('A: 공 발사', 'A: Launch ball'), 400, 290, 28, GOLD, center=True)
            ui.text(ui.label('패들 끝으로 받으면 공이 비스듬히 나갑니다.', 'Paddle edges aim the ball sideways.'),
                    400, 332, 18, MUTED, center=True)
        elif self.state != 'play':
            ui.shade(190)
            ui.panel(pygame.Rect(85, 123, 630, 244), fill=PANEL_HI, border=P2)
            title = {'title': ui.label('프리즘 브레이크', 'PRISM BREAK'),
                     'paused': ui.label('일시정지', 'PAUSED'),
                     'over': ui.label('도전 종료', 'GAME OVER'),
                     'won': ui.label('모든 스테이지 클리어!', 'ALL STAGES CLEAR!')}[self.state]
            ui.text(title, 400, 142, 34, P2, center=True)
            if self.state == 'title':
                lines = [ui.label('공을 받아 벽돌을 모두 깨세요. 총 3스테이지!', 'Break every brick across 3 stages!'),
                         ui.label('좌우: 이동   A: 발사   B 누르기: 정밀 이동', 'Left/Right: Move   A: Launch   Hold B: Precision'),
                         ui.label('시작한 조작기 하나로 플레이 · 기회 3번', 'Use the pad that starts. Three lives.')]
            else:
                lines = [ui.label(f'점수 {self.score}   이번 실행 최고 {self.best}', f'Score {self.score}   Session best {self.best}'),
                         ui.label('패들 가운데는 위로, 끝은 비스듬히!', 'Center aims upward; edges aim sideways!'),
                         ui.label(f'{self.player+1}P 조작기 사용', f'PLAYER {self.player+1} CONTROLS')]
            for i, line in enumerate(lines):
                ui.text(line, 400, 198+i*31, 18, WHITE if i == 0 else MUTED, center=True, max_width=590)
            ui.text(ui.label('A / START: 시작·계속   SELECT: 메뉴', 'A / START: Play / Resume   SELECT: Menu'),
                    400, 324, 18, GOLD, center=True)

    def run(self):
        while True:
            dt = self.ui.clock.tick(60)/1000
            closed, pads = self.ui.poll()
            if closed or not self.handle(pads):
                break
            self.update(dt, pads)
            self.draw()
            self.ui.present()
        pygame.quit()


if __name__ == '__main__':
    args = options()
    PrismBreak(args.fullscreen, args.margin).run()
