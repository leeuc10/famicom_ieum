"""STARFALL: a sixty-second solo flight through a meteor field."""
import math
import random
from dataclasses import dataclass

import pygame
from console_ui import (BG, GOLD, LINE, MUTED, P1, P2, PANEL, PANEL_HI, WHITE,
                        ConsoleDisplay, back_combo, options)
from game_fx import Sparks

FIELD = pygame.Rect(24, 86, 752, 330)
DURATION = 60


@dataclass
class Meteor:
    x: float
    y: float
    radius: int
    speed: float
    drift: float


class Starfall:
    def __init__(self, fullscreen=True, margin=0, rng=None):
        self.ui = ConsoleDisplay(fullscreen, margin)
        self.rng = rng or random.Random()
        self.player = 0
        self.best = 0
        self.reset()
        self.state = 'title'

    def reset(self):
        self.ship = pygame.Vector2(400, 365)
        self.rocks = []
        self.shots = []
        self.sparks = Sparks()
        self.elapsed = self.spawn = self.fire = 0.0
        self.shield = self.cooldown = self.invincible = 0.0
        self.lives = 3
        self.score = 0
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
        if self.state == 'play' and pad.any_pressed('start'):
            self.state = 'paused'
        elif self.state != 'play' and pad.any_pressed('start', 'punch'):
            if self.state in ('over', 'won'):
                self.reset()
            else:
                self.state = 'play'
        return True

    def update(self, dt, pads):
        if self.state != 'play' or len(pads) <= self.player:
            return
        dt = max(0, min(dt, .035))
        pad = pads[self.player]
        self.elapsed = min(DURATION, self.elapsed + dt)
        for name in ('fire', 'shield', 'cooldown', 'invincible'):
            setattr(self, name, max(0, getattr(self, name) - dt))
        self.sparks.update(dt)
        move = pygame.Vector2(pad.held['right'] - pad.held['left'],
                              pad.held['down'] - pad.held['up'])
        if move.length_squared():
            self.ship += move.normalize() * 245 * dt
        self.ship.x = max(FIELD.left + 18, min(FIELD.right - 18, self.ship.x))
        self.ship.y = max(FIELD.top + 22, min(FIELD.bottom - 20, self.ship.y))
        if pad.pressed['kick'] and self.cooldown == 0:
            self.shield, self.cooldown = 1.2, 5.0
        if pad.held['punch'] and self.fire == 0:
            self.shots.append(pygame.Vector2(self.ship.x, self.ship.y - 19))
            self.fire = .16
        for shot in self.shots:
            shot.y -= 520 * dt
        self.shots = [s for s in self.shots if s.y >= FIELD.top]
        self.spawn -= dt
        if self.spawn <= 0:
            self.spawn += max(.25, .8 - self.elapsed * .009)
            self.rocks.append(Meteor(self.rng.uniform(52, 748), 65,
                                    self.rng.randint(14, 24),
                                    self.rng.uniform(85, 125) + self.elapsed * 1.4,
                                    self.rng.uniform(-25, 25)))
        survivors = []
        for rock in self.rocks:
            rock.y += rock.speed * dt
            rock.x += rock.drift * dt
            if rock.x < FIELD.left + rock.radius or rock.x > FIELD.right - rock.radius:
                rock.x = max(FIELD.left + rock.radius, min(FIELD.right - rock.radius, rock.x))
                rock.drift *= -1
            hit = next((s for s in self.shots if
                        (s.x-rock.x)**2 + (s.y-rock.y)**2 <= (rock.radius+5)**2), None)
            if hit is not None:
                self.shots.remove(hit)
                self.score += 10
                self.sparks.burst((rock.x, rock.y), GOLD)
                continue
            radius = 31 if self.shield else 10
            if self.ship.distance_squared_to((rock.x, rock.y)) < (rock.radius + radius)**2:
                if self.shield or self.invincible:
                    self.sparks.burst((rock.x, rock.y), P2)
                else:
                    self.lives -= 1
                    self.invincible = 1.5
                    self.sparks.burst(self.ship, P1, 20)
                continue
            if rock.y - rock.radius <= FIELD.bottom:
                survivors.append(rock)
        self.rocks = survivors
        if self.lives <= 0:
            self.state = 'over'
        elif self.elapsed >= DURATION:
            self.score += 100 * self.lives
            self.state = 'won'
        self.best = max(self.best, self.score)

    def draw_ship(self):
        screen = self.ui.screen
        x, y = self.ship
        if self.shield:
            pygame.draw.circle(screen, P2, (round(x), round(y)), 31, 3)
        if self.invincible and int(self.elapsed * 12) % 2:
            return
        flame = 9 + int(4 * math.sin(self.elapsed * 35))
        pygame.draw.polygon(screen, GOLD, [(x-6, y+13), (x, y+13+flame), (x+6, y+13)])
        pygame.draw.polygon(screen, P2, [(x, y-19), (x-17, y+15), (x, y+8), (x+17, y+15)])
        pygame.draw.polygon(screen, WHITE, [(x, y-13), (x-5, y+6), (x+5, y+6)])

    def draw(self):
        ui = self.ui
        ui.screen.fill(BG)
        ui.text('STARFALL', 28, 18, 28, P2)
        ui.text(f'{self.score:05d}', 392, 16, 34, GOLD, center=True)
        ui.text(ui.label('점수', 'SCORE'), 392, 56, 14, MUTED, center=True)
        ui.text(f'{max(0, math.ceil(DURATION-self.elapsed)):02d}s', 730, 20, 28, WHITE, center=True)
        ui.panel(FIELD, fill=PANEL, border=LINE)
        previous_clip = ui.screen.get_clip()
        ui.screen.set_clip(FIELD.inflate(-4, -4))
        for i in range(65):
            x = FIELD.left + (i * 137 + 19) % FIELD.width
            y = FIELD.top + (i * 71 + self.elapsed * (20 + i % 4 * 12)) % FIELD.height
            pygame.draw.line(ui.screen, MUTED if i % 4 == 0 else LINE, (x, y), (x, y+3))
        for shot in self.shots:
            pygame.draw.line(ui.screen, GOLD, shot, (shot.x, shot.y+12), 4)
        for rock in self.rocks:
            points = [(rock.x + math.cos(i*math.tau/9) * rock.radius * (1 if i%2 else .85),
                       rock.y + math.sin(i*math.tau/9) * rock.radius * (1 if i%2 else .85))
                      for i in range(9)]
            pygame.draw.polygon(ui.screen, (112, 83, 91), points)
            pygame.draw.polygon(ui.screen, P1, points, 2)
            pygame.draw.circle(ui.screen, PANEL, (round(rock.x-4), round(rock.y-3)), rock.radius//4)
        self.draw_ship()
        self.sparks.draw(ui.screen)
        ui.screen.set_clip(previous_clip)
        ui.text(f'HP {"●" * self.lives}', 34, 425, 18, P1)
        shield_text = ui.label('B 방어 준비', 'B SHIELD READY') if not self.cooldown else ui.label(
            f'B 방어 {self.cooldown:.1f}초', f'B SHIELD {self.cooldown:.1f}s')
        ui.text(shield_text, 245, 425, 18, P2)
        ui.text(ui.label('A 발사  START 정지', 'A FIRE  START PAUSE'), 490, 425, 18, MUTED)
        ui.text(ui.label('SELECT: 메뉴', 'SELECT: MENU'), 400, 455, 14, MUTED, center=True)
        if self.state != 'play':
            ui.shade(185)
            ui.panel(pygame.Rect(88, 122, 624, 250), fill=PANEL_HI, border=P2)
            title = {'title': ui.label('스타폴', 'STARFALL'), 'paused': ui.label('일시정지', 'PAUSED'),
                     'won': ui.label('항로 돌파!', 'FLIGHT COMPLETE!'),
                     'over': ui.label('비행 종료', 'FLIGHT ENDED')}[self.state]
            ui.text(title, 400, 142, 34, P2, center=True)
            if self.state == 'title':
                lines = [ui.label('60초 동안 운석을 피하고 격추하세요.', 'Dodge and destroy meteors for 60 seconds.'),
                         ui.label('방향: 이동   A: 연사   B: 1.2초 방어', 'D-pad: Move   Hold A: Fire   B: 1.2s Shield'),
                         ui.label('방어 재사용 5초 · 시작한 조작기로 플레이', 'Shield reloads in 5s. Use the pad that starts.')]
            else:
                lines = [ui.label(f'점수 {self.score}   이번 실행 최고 {self.best}', f'Score {self.score}   Session best {self.best}'),
                         ui.label('생존 성공 시 남은 체력당 100점!', 'Survive: earn 100 bonus points per remaining HP!'),
                         ui.label(f'{self.player+1}P 조작기 사용', f'PLAYER {self.player+1} CONTROLS')]
            for i, line in enumerate(lines):
                ui.text(line, 400, 201+i*32, 18, WHITE if i == 0 else MUTED, center=True, max_width=580)
            ui.text(ui.label('A / START: 시작·계속   SELECT: 메뉴', 'A / START: Play / Resume   SELECT: Menu'),
                    400, 326, 18, GOLD, center=True)

    def run(self):
        while True:
            dt = self.ui.clock.tick(60) / 1000
            closed, pads = self.ui.poll()
            if closed or not self.handle(pads):
                break
            self.update(dt, pads)
            self.draw()
            self.ui.present()
        pygame.quit()


if __name__ == '__main__':
    args = options()
    Starfall(args.fullscreen, args.margin).run()
