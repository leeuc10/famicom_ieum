"""FAMI QUEST — 혼자 하는 탑다운 던전 탐험.

초기 젤다의 문법을 그대로 따른다. 화면 한 장이 방 하나이고, 문을 넘으면
화면째로 넘어간다. 스크롤이 없으니 방 하나를 한눈에 보고 싸울 수 있다.

조작은 방향키와 A(검) 뿐이다. 부스에서 처음 잡는 사람이 설명 없이도
움직일 수 있어야 하므로 버튼을 늘리지 않았다. 1P/2P 조작기 어느 쪽으로도
조종할 수 있게 두 패드 입력을 합쳐서 받는다.
"""
import math
import random

import pygame
from game_fx import Sparks, glow

from console_ui import (BG, GOLD, INK, LINE, MUTED, P1, P2, PANEL, PANEL_HI, WHITE,
                        ConsoleDisplay, back_combo, options)
from input_adapter import BUTTONS
from theme import SKIN, shade

TILE = 40
COLS, ROWS = 19, 9
ROOM = pygame.Rect(20, 78, COLS * TILE, ROWS * TILE)
SOLID = '#X~'
# 문은 벽 한가운데 한 칸씩 뚫는다. 방향 -> (열, 행) 과 이동 벡터.
DOORS = {
    'up': ((COLS // 2, 0), (0, -1)),
    'down': ((COLS // 2, ROWS - 1), (0, 1)),
    'left': ((0, ROWS // 2), (-1, 0)),
    'right': ((COLS - 1, ROWS // 2), (1, 0)),
}
OPPOSITE = {'up': 'down', 'down': 'up', 'left': 'right', 'right': 'left'}
STEP = {'up': (0, -1), 'down': (0, 1), 'left': (-1, 0), 'right': (1, 0)}

HERO_SPEED = 138
SWORD_TIME = 0.30           # 휘두르는 전체 시간
SWORD_ACTIVE = (0.04, 0.19)  # 이 구간에만 칼날에 판정이 있다
INVULN = 0.9                # 맞은 뒤 무적. 연속으로 갈려 나가는 것을 막는다
TRANSITION = 0.38
DOOR_PUSH = 4               # 문턱을 이만큼 밀고 나가면 옆 방으로 넘어간다

PALETTE = {
    'd': (16, 18, 28), 'g': (86, 168, 106), 'y': GOLD, 's': SKIN,
    'k': (16, 18, 28), 'w': (238, 238, 232), 'b': (124, 108, 176),
    'o': (226, 118, 92), 'p': (150, 88, 170), 'm': (84, 44, 98),
    'e': (255, 92, 92), 'n': (60, 66, 88),
}

HERO_ART = {
    'down': (
        '....dddd....', '...dggggd...', '..dggggggd..', '..dssssssd..',
        '..dskssksd..', '..dssssssd..', '.dggggggggd.', '.dgyyyyyygd.',
        'ddsgggggggsd', '.dggggggggd.', '..dbbbbbbd..', '...dd..dd...'),
    'up': (
        '....dddd....', '...dggggd...', '..dggggggd..', '..dggggggd..',
        '..dggggggd..', '..dggggggd..', '.dggggggggd.', '.dgyyyyyygd.',
        'ddsgggggggsd', '.dggggggggd.', '..dbbbbbbd..', '...dd..dd...'),
    'side': (
        '....dddd....', '...dgggggd..', '..dggggggd..', '..dsssssd...',
        '..dsskssd...', '..dsssssd...', '.dgggggggd..', '.dgyyyyygd..',
        '.dgggggggsd.', '.dgggggggd..', '..dbbbbbbd..', '...dd.dd....'),
}
ENEMY_ART = {
    'octorok': (
        '..dddddddd..', '.dooooooood.', '.doowoowood.', '.dookookood.',
        '.dooooooood.', '.dooooooood.', '.dooooooood.', '..dooooood..',
        '..dddddddd..', '.d..d..d..d.', '.d..d..d..d.', '............'),
    'keese': (
        '............', '.d........d.', 'ddd..dd..ddd', 'dbbddbbddbbd',
        '.dbbbbbbbbd.', '..dbwbbwbd..', '..dbkbbkbd..', '..dbbbbbbd..',
        '...dbbbbd...', '....dbbd....', '............', '............'),
    'stalfos': (
        '...dddddd...', '..dwwwwwwd..', '..dwkwwkwd..', '..dwwwwwwd..',
        '..dwdwwdwd..', '...dwwwwd...', '..dwwwwwwd..', '.dwdwwwwdwd.',
        '.dwdwwwwdwd.', '..dwwddwwd..', '..dwd..dwd..', '..ddd..ddd..'),
    'boss': (
        '...mm......mm...', '..mppm....mppm..', '..mpppmmmmpppm..',
        '.mppppppppppppm.', '.mpppppppppppppm', 'mppppppppppppppm',
        'mppmeeppppeemppm', 'mppmeeppppeemppm', 'mppppppppppppppm',
        'mppppwwwwwwppppm', 'mpppwmwmwmwmpppm', '.mppwwwwwwwwppm.',
        '.mppppppppppppm.', '..mmppppppppmm..', '...mm.mmmm.mm...',
        '....m..mm..m....'),
}

LAYOUTS = {
    'open': (
        '###################', '#.................#', '#.................#',
        '#.................#', '#.................#', '#.................#',
        '#.................#', '#.................#', '###################'),
    'pillars': (
        '###################', '#.................#', '#...XX.......XX...#',
        '#...XX.......XX...#', '#.................#', '#...XX.......XX...#',
        '#...XX.......XX...#', '#.................#', '###################'),
    'bars': (
        '###################', '#.................#', '#....X.......X....#',
        '#....X.......X....#', '#.................#', '#....X.......X....#',
        '#....X.......X....#', '#.................#', '###################'),
    'pit': (
        '###################', '#.................#', '#..~~~~.....~~~~..#',
        '#..~~~~.....~~~~..#', '#.................#', '#..~~~~.....~~~~..#',
        '#..~~~~.....~~~~..#', '#.................#', '###################'),
    'maze': (
        '###################', '#.................#', '#..XXXXXX.XXXXXX..#',
        '#..X...........X..#', '#..X...........X..#', '#..X...........X..#',
        '#..XXXXXX.XXXXXX..#', '#.................#', '###################'),
    'hall': (
        '###################', '#.................#', '#.XX...........XX.#',
        '#.XX...........XX.#', '#.................#', '#.XX...........XX.#',
        '#.XX...........XX.#', '#.................#', '###################'),
}

# 던전은 4x3 격자 위에 놓는다. 이웃한 칸이 있으면 그쪽에 문이 뚫린다.
# reward 는 그 방의 적을 모두 없앴을 때 한 번만 나온다.
ROOMS = {
    (1, 2): {'layout': 'open', 'enemies': ()},
    (0, 2): {'layout': 'pillars', 'enemies': (('keese', 7, 2), ('keese', 11, 6), ('keese', 9, 4)),
             'reward': 'heart'},
    (2, 2): {'layout': 'bars', 'enemies': (('octorok', 3, 2), ('octorok', 15, 6)),
             'reward': 'key'},
    (1, 1): {'layout': 'maze', 'enemies': (('octorok', 6, 4), ('octorok', 12, 4), ('stalfos', 9, 1)),
             'reward': 'heart'},
    (0, 1): {'layout': 'pit', 'enemies': (('stalfos', 7, 4), ('stalfos', 11, 4)),
             'reward': 'container'},
    (2, 1): {'layout': 'hall', 'enemies': (('octorok', 5, 4), ('octorok', 13, 4),
                                           ('keese', 9, 2), ('keese', 9, 6)),
             'reward': 'key'},
    (1, 0): {'layout': 'pillars', 'enemies': (('stalfos', 7, 2), ('stalfos', 11, 2),
                                              ('stalfos', 9, 6)),
             'reward': 'container'},
    (2, 0): {'layout': 'open', 'enemies': (('boss', 9, 3),)},
    (3, 0): {'layout': 'open', 'enemies': ()},
}
START_ROOM = (1, 2)
BOSS_ROOM = (2, 0)
CROWN_ROOM = (3, 0)
# 보스 방은 열쇠로만 들어간다. 두 입구를 모두 잠가 두고, 연 문은 계속 열려 있다.
LOCKED = {frozenset(((2, 1), (2, 0))), frozenset(((1, 0), (2, 0)))}
# 왕관이 있는 방은 보스를 쓰러뜨려야 열린다.
SEALED = frozenset(((2, 0), (3, 0)))

ENEMY_STATS = {           # (체력, 속도, 접촉 피해(반칸), 크기)
    'octorok': (2, 66, 1, 26),
    'keese': (1, 112, 1, 26),
    'stalfos': (3, 58, 2, 26),
    'boss': (12, 78, 2, 56),
}


def make_sprite(pattern, scale):
    surface = pygame.Surface((len(pattern[0]) * scale, len(pattern) * scale), pygame.SRCALPHA)
    for row, line in enumerate(pattern):
        for col, char in enumerate(line):
            if char != '.':
                surface.fill(PALETTE[char], (col * scale, row * scale, scale, scale))
    return surface


def cell_rect(col, row):
    return pygame.Rect(ROOM.x + col * TILE, ROOM.y + row * TILE, TILE, TILE)


def merge_pads(pads):
    """두 조작기를 한 사람 몫으로 합친다. 어느 쪽을 집어도 조종이 된다."""
    held = {b: any(p.held[b] for p in pads) for b in BUTTONS}
    pressed = {b: any(p.pressed[b] for p in pads) for b in BUTTONS}
    return held, pressed


class Actor:
    """방 안에서 움직이는 것들의 공통 부분 — 위치, 충돌, 넉백."""

    def __init__(self, x, y, size):
        self.rect = pygame.Rect(0, 0, size, size)
        self.rect.center = (x, y)
        self.pos = pygame.Vector2(self.rect.center)
        self.knock = pygame.Vector2()
        self.flash = 0.0

    def sync(self):
        self.rect.center = (round(self.pos.x), round(self.pos.y))

    def slide(self, dx, dy, tiles):
        """x 와 y 를 따로 밀어 벽을 타고 미끄러지게 한다.

        한 번에 옮기면 모서리에 닿는 순간 두 축이 함께 막혀서 벽에 붙어
        버린다. 탑다운에서는 이게 바로 '조작이 뻑뻑하다'는 느낌이 된다.
        """
        for axis, amount in ((0, dx), (1, dy)):
            if not amount:
                continue
            self.pos[axis] += amount
            self.sync()
            if blocked(tiles, self.rect):
                self.pos[axis] -= amount
                self.sync()

    def apply_knock(self, dt, tiles):
        if self.knock.length_squared() < 400:
            self.knock.update(0, 0)
            return
        # 60fps 감속을 시간 기준으로 적분해 이동 거리도 동일하게 유지한다.
        rate = -60 * math.log(0.80)
        duration = min(dt, math.log(self.knock.length() / 20) / rate)
        decay = math.exp(-rate * duration)
        distance = self.knock * ((1 - decay) / rate)
        self.slide(distance.x, distance.y, tiles)
        self.knock *= decay
        if duration < dt or self.knock.length_squared() <= 400.000001:
            self.knock.update(0, 0)


def blocked(tiles, rect):
    for x, y in ((rect.left, rect.top), (rect.right - 1, rect.top),
                 (rect.left, rect.bottom - 1), (rect.right - 1, rect.bottom - 1)):
        col, row = (x - ROOM.x) // TILE, (y - ROOM.y) // TILE
        if not (0 <= col < COLS and 0 <= row < ROWS) or tiles[row][col] in SOLID:
            return True
    return False


class Hero(Actor):
    def __init__(self):
        super().__init__(ROOM.centerx, ROOM.centery, 26)
        self.facing = 'down'
        self.max_health = 6          # 반 칸 단위. 6 = 하트 3개
        self.health = 6
        self.keys = 0
        self.swing = 0.0
        self.struck = set()          # 한 번 휘두를 때 같은 적을 여러 번 때리지 않게
        self.invuln = 0.0
        self.bob = 0.0

    @property
    def swinging(self):
        return self.swing > 0

    @property
    def blade(self):
        """칼날 판정. 발동·회수 구간에는 None 이라 휘두르자마자 맞지는 않는다."""
        elapsed = SWORD_TIME - self.swing
        if not (SWORD_ACTIVE[0] <= elapsed < SWORD_ACTIVE[1]):
            return None
        # 칼날 폭은 적 크기(20)와 비슷하게 잡는다. 원작처럼 얇게 두면 살짝
        # 어긋나기만 해도 빗나가서, 처음 잡는 사람이 검이 고장난 줄 안다.
        r = self.rect
        if self.facing == 'right':
            return pygame.Rect(r.right - 5, r.centery - 12, 36, 24)
        if self.facing == 'left':
            return pygame.Rect(r.left - 31, r.centery - 12, 36, 24)
        if self.facing == 'up':
            return pygame.Rect(r.centerx - 12, r.top - 31, 24, 36)
        return pygame.Rect(r.centerx - 12, r.bottom - 5, 24, 36)

    def attack(self):
        if not self.swinging:
            self.swing = SWORD_TIME
            self.struck.clear()

    def hurt(self, amount, source):
        if self.invuln > 0:
            return False
        self.health = max(0, self.health - amount)
        self.invuln = INVULN
        away = pygame.Vector2(self.rect.center) - pygame.Vector2(source)
        self.knock = away.normalize() * 320 if away.length_squared() else pygame.Vector2(0, 320)
        return True

    def update(self, dt, held, tiles):
        self.swing = max(0.0, self.swing - dt)
        self.invuln = max(0.0, self.invuln - dt)
        self.apply_knock(dt, tiles)
        dx = held['right'] - held['left']
        dy = held['down'] - held['up']
        # 휘두르는 동안은 제자리에 선다. 걸어 다니며 칼을 흔들면 판정이 지저분해진다.
        if self.swinging or self.knock.length_squared():
            return
        if dx and dy:
            dx, dy = dx * 0.7071, dy * 0.7071
        if dx or dy:
            self.facing = ('right' if dx > 0 else 'left') if abs(dx) >= abs(dy) else \
                          ('down' if dy > 0 else 'up')
            self.bob += dt * 9
            self.slide(dx * HERO_SPEED * dt, dy * HERO_SPEED * dt, tiles)
        else:
            self.bob = 0.0


class Enemy(Actor):
    def __init__(self, kind, col, row):
        self.kind = kind
        health, speed, self.touch, size = ENEMY_STATS[kind]
        super().__init__(*cell_rect(col, row).center, size)
        self.health, self.speed = health, speed
        self.direction = random.choice(list(STEP.values()))
        self.timer = random.uniform(0.4, 1.4)
        self.shot_timer = random.uniform(1.2, 2.6)
        self.dead = False

    def hit(self, power, source):
        self.health -= power
        self.flash = 0.12
        away = pygame.Vector2(self.rect.center) - pygame.Vector2(source)
        self.knock = away.normalize() * 300 if away.length_squared() else pygame.Vector2()
        if self.health <= 0:
            self.dead = True

    def update(self, dt, tiles, hero, shots):
        self.flash = max(0.0, self.flash - dt)
        self.apply_knock(dt, tiles)
        if self.knock.length_squared():
            return
        self.timer -= dt
        if self.kind == 'stalfos':
            # 해골은 느리지만 늘 플레이어 쪽으로 한 축씩 다가온다. 도망갈 곳이 줄어든다.
            if self.timer <= 0:
                self.timer = random.uniform(0.5, 0.9)
                gap = pygame.Vector2(hero.rect.center) - pygame.Vector2(self.rect.center)
                self.direction = ((1 if gap.x > 0 else -1), 0) if abs(gap.x) > abs(gap.y) \
                    else (0, (1 if gap.y > 0 else -1))
        elif self.timer <= 0:
            self.timer = random.uniform(0.5, 1.5)
            self.direction = random.choice(list(STEP.values()))
        before = self.rect.topleft
        self.slide(self.direction[0] * self.speed * dt, self.direction[1] * self.speed * dt, tiles)
        if self.rect.topleft == before:        # 벽에 막히면 바로 방향을 튼다
            self.direction = random.choice(list(STEP.values()))
            self.timer = random.uniform(0.4, 1.0)
        if self.kind in ('octorok', 'boss'):
            self.shot_timer -= dt
            if self.shot_timer <= 0:
                self.shot_timer = random.uniform(1.4, 2.6) if self.kind == 'octorok' else 1.7
                self.fire(hero, shots)

    def fire(self, hero, shots):
        if self.kind == 'octorok':
            shots.append(Shot(self.rect.center, self.direction, 210))
            return
        # 보스는 네 방향으로 한꺼번에 뿌린다. 붙어서 계속 때리기만 하면 안 되게.
        for step in STEP.values():
            shots.append(Shot(self.rect.center, step, 170))


class Shot:
    def __init__(self, center, direction, speed):
        self.rect = pygame.Rect(0, 0, 12, 12)
        self.rect.center = center
        self.pos = pygame.Vector2(center)
        self.velocity = pygame.Vector2(direction) * speed
        self.dead = False

    def update(self, dt, tiles):
        self.pos += self.velocity * dt
        self.rect.center = (round(self.pos.x), round(self.pos.y))
        if blocked(tiles, self.rect):
            self.dead = True


class Pickup:
    ART = {
        'heart': ('.XX.XX.', 'XXXXXXX', 'XXXXXXX', '.XXXXX.', '..XXX..', '...X...'),
        'container': ('.XX.XX.', 'XXXXXXX', 'XXXXXXX', '.XXXXX.', '..XXX..', '...X...'),
        'key': ('.XXX.', 'X...X', 'X...X', '.XXX.', '..X..', '..XX.', '..X..', '..XX.'),
        'crown': ('X.X.X.X', 'X.X.X.X', 'XXXXXXX', 'XXXXXXX', '.XXXXX.'),
    }
    COLOR = {'heart': P1, 'container': P1, 'key': GOLD, 'crown': GOLD}

    def __init__(self, kind, center):
        self.kind = kind
        self.rect = pygame.Rect(0, 0, 26, 26)
        self.rect.center = center
        self.taken = False


class Quest:
    def __init__(self, fullscreen=True, margin=0):
        self.ui = ConsoleDisplay(fullscreen, margin)
        scale = 3
        self.art = {f'hero_{k}': make_sprite(v, scale) for k, v in HERO_ART.items()}
        self.art['hero_left'] = pygame.transform.flip(self.art['hero_side'], True, False)
        self.art['hero_right'] = self.art['hero_side']
        for kind, pattern in ENEMY_ART.items():
            self.art[kind] = make_sprite(pattern, 4 if kind == 'boss' else scale)
        self.torch_glow = glow(66, (255, 156, 66))
        self.new_game()
        self.state = 'title'

    # ---------- 진행 ----------

    def new_game(self):
        self.sparks = Sparks()
        self.hero = Hero()
        self.room = START_ROOM
        self.visited = {START_ROOM}
        self.unlocked = set()
        self.boss_down = False
        self.crown = False
        self.elapsed = 0.0
        self.message = ''
        self.message_time = 0.0
        self.rooms = {}
        self.surfaces = {}
        self.transition = None
        self.enter_room(START_ROOM, None)
        self.state = 'play'

    def room_state(self, coord):
        """방 상태는 처음 들어갈 때 만들고 계속 들고 있는다.

        젤다 원작은 방을 나갔다 오면 적이 되살아나지만, 여기서는 되살리지
        않는다. 부스에서 3분쯤 잡고 노는 게임이라 앞선 전투가 지워지면
        진행하는 맛이 사라진다.
        """
        if coord not in self.rooms:
            spec = ROOMS[coord]
            self.rooms[coord] = {
                'enemies': [Enemy(*e) for e in spec['enemies']],
                'shots': [], 'pickups': [], 'rewarded': not spec.get('reward'),
            }
            if coord == CROWN_ROOM:
                self.rooms[coord]['pickups'].append(Pickup('crown', ROOM.center))
        return self.rooms[coord]

    def tiles(self, coord):
        """방의 타일 격자. 이웃이 있는 쪽 벽에 문을 뚫어 둔다."""
        grid = [list(row) for row in LAYOUTS[ROOMS[coord]['layout']]]
        for direction, ((col, row), step) in DOORS.items():
            neighbour = (coord[0] + step[0], coord[1] + step[1])
            if neighbour in ROOMS and self.door_open(coord, neighbour):
                grid[row][col] = '.'
        return [''.join(row) for row in grid]

    def door_open(self, a, b):
        pair = frozenset((a, b))
        if pair == SEALED:
            return self.boss_down
        if pair in LOCKED:
            return pair in self.unlocked
        return True

    def enter_room(self, coord, from_direction):
        self.sparks.items.clear()
        self.room = coord
        self.visited.add(coord)
        self.grid = self.tiles(coord)
        if from_direction:
            col, row = DOORS[OPPOSITE[from_direction]][0]
            spot = cell_rect(col, row).center
            inset = STEP[from_direction]
            self.hero.pos.update(spot[0] + inset[0] * TILE, spot[1] + inset[1] * TILE)
            self.hero.sync()
        self.room_state(coord)

    def repaint(self, coord=None):
        self.surfaces.pop(coord or self.room, None)

    def try_door(self):
        """문 앞에서의 처리 — 열린 문은 통과, 닫힌 문은 여는 시도."""
        for direction, ((col, row), step) in DOORS.items():
            neighbour = (self.room[0] + step[0], self.room[1] + step[1])
            if neighbour not in ROOMS:
                continue
            gate = cell_rect(col, row)
            if not self.door_open(self.room, neighbour):
                # 닫힌 문은 타일이 막혀 있어 그 위에 올라설 수 없다. 그래서
                # 통과 판정과 달리 '문 앞에 서서 그쪽을 보고 있는가' 로 본다.
                if self.hero.facing == direction and gate.inflate(12, 12).colliderect(self.hero.rect):
                    self.knock_on(neighbour)
                continue
            if not gate.colliderect(self.hero.rect):
                continue
            # 문 칸 안에서 바깥쪽으로 충분히 나갔을 때만 넘어간다.
            past = (self.hero.rect.centerx - gate.centerx) * step[0] + \
                   (self.hero.rect.centery - gate.centery) * step[1]
            if past >= DOOR_PUSH:
                self.start_transition(direction, neighbour)
                return

    def knock_on(self, neighbour):
        pair = frozenset((self.room, neighbour))
        if pair == SEALED:
            self.say(self.ui.label('안쪽의 무언가가 문을 붙잡고 있다',
                                   'Something inside holds this door'))
        elif self.hero.keys > 0:
            self.hero.keys -= 1
            self.unlocked.add(pair)
            self.grid = self.tiles(self.room)
            self.repaint(self.room)
            self.repaint(neighbour)
            self.say(self.ui.label('열쇠로 문을 열었다', 'The key turns'))
        else:
            self.say(self.ui.label('열쇠가 필요하다', 'It needs a key'))

    def start_transition(self, direction, target):
        old_room, old_pos = self.room, pygame.Vector2(self.hero.pos)
        self.enter_room(target, direction)
        self.transition = {'time': TRANSITION, 'step': STEP[direction],
                           'from': old_room, 'from_pos': old_pos,
                           'to_pos': pygame.Vector2(self.hero.pos)}

    def say(self, text):
        self.message, self.message_time = text, 2.0

    # ---------- 한 프레임 ----------

    def update(self, dt, held, pressed):
        self.sparks.update(dt)
        self.elapsed += dt
        self.message_time = max(0.0, self.message_time - dt)
        if self.transition:
            self.transition['time'] -= dt
            if self.transition['time'] <= 0:
                self.transition = None
            return
        state = self.room_state(self.room)
        if pressed['punch']:
            self.hero.attack()
        self.hero.update(dt, held, self.grid)

        for enemy in state['enemies']:
            enemy.update(dt, self.grid, self.hero, state['shots'])
        for shot in state['shots']:
            shot.update(dt, self.grid)

        blade = self.hero.blade
        for enemy in state['enemies']:
            if blade and id(enemy) not in self.hero.struck and blade.colliderect(enemy.rect):
                self.hero.struck.add(id(enemy))
                enemy.hit(1, self.hero.rect.center)
                self.sparks.burst(enemy.rect.center, GOLD, 10)
            if not enemy.dead and enemy.rect.colliderect(self.hero.rect):
                self.hero.hurt(enemy.touch, enemy.rect.center)
        for shot in state['shots']:
            if not shot.dead and shot.rect.colliderect(self.hero.rect):
                self.hero.hurt(1, shot.rect.center)
                shot.dead = True

        for enemy in state['enemies']:
            if enemy.dead and random.random() < 0.25:
                state['pickups'].append(Pickup('heart', enemy.rect.center))
        if any(e.dead and e.kind == 'boss' for e in state['enemies']):
            self.boss_down = True
            self.repaint(BOSS_ROOM)
            self.repaint(CROWN_ROOM)
            self.grid = self.tiles(self.room)
            self.say(self.ui.label('동쪽 문이 열렸다', 'The east door opens'))
        state['enemies'] = [e for e in state['enemies'] if not e.dead]
        state['shots'] = [s for s in state['shots'] if not s.dead
                          and ROOM.colliderect(s.rect)]

        if not state['enemies'] and not state['rewarded']:
            state['rewarded'] = True
            state['pickups'].append(Pickup(ROOMS[self.room]['reward'], ROOM.center))
        for pickup in state['pickups']:
            if pickup.rect.colliderect(self.hero.rect):
                self.collect(pickup)
        state['pickups'] = [p for p in state['pickups'] if not p.taken]

        if self.hero.health <= 0:
            self.state = 'dead'
        elif self.crown:
            self.state = 'win'
        else:
            self.try_door()

    def collect(self, pickup):
        pickup.taken = True
        self.sparks.burst(pickup.rect.center, Pickup.COLOR[pickup.kind], 14)
        if pickup.kind == 'key':
            self.hero.keys += 1
            self.say(self.ui.label('열쇠를 얻었다', 'Found a key'))
        elif pickup.kind == 'heart':
            self.hero.health = min(self.hero.max_health, self.hero.health + 2)
        elif pickup.kind == 'container':
            self.hero.max_health += 2
            self.hero.health = self.hero.max_health
            self.say(self.ui.label('하트 그릇! 최대 체력이 늘었다', 'Heart container! Max life up'))
        else:
            self.crown = True

    # ---------- 그리기 ----------

    def room_surface(self, coord):
        """방의 정지된 부분(바닥·벽·문)을 표면 하나에 구워 둔다.

        방은 한 화면에 고정되어 있고 문이 열릴 때만 바뀐다. 매 프레임
        타일 171칸을 다시 그릴 이유가 없어서 캐시하고, 문이 열리면 버린다.
        """
        if coord in self.surfaces:
            return self.surfaces[coord]
        surface = pygame.Surface(ROOM.size)
        tiles = self.tiles(coord)
        for row in range(ROWS):
            for col in range(COLS):
                rect = pygame.Rect(col * TILE, row * TILE, TILE, TILE)
                char = tiles[row][col]
                if char == '.':
                    self.paint_floor(surface, rect, col, row)
                elif char == '~':
                    self.paint_pit(surface, rect, row > 0 and tiles[row - 1][col] == '~')
                elif char == 'X':
                    self.paint_block(surface, rect)
                else:
                    self.paint_wall(surface, rect, row)
        for direction, ((col, row), step) in DOORS.items():
            neighbour = (coord[0] + step[0], coord[1] + step[1])
            if neighbour in ROOMS:
                self.paint_door(surface, pygame.Rect(col * TILE, row * TILE, TILE, TILE),
                                step, self.door_open(coord, neighbour),
                                frozenset((coord, neighbour)) == SEALED)
        self.surfaces[coord] = surface
        return surface

    @staticmethod
    def paint_floor(surface, rect, col, row):
        surface.fill((36, 34, 54) if (col + row) % 2 else (31, 30, 48), rect)
        pygame.draw.rect(surface, (22,24,37), rect, 1)
        pygame.draw.line(surface, (47,45,64), (rect.x+3,rect.y+3),(rect.right-4,rect.y+3))
        # 고정 무늬로 게임의 난수열에 영향을 주지 않는다.
        if (col * 7 + row * 11) % 5 == 0:
            pygame.draw.lines(surface,(24,25,39),False,[(rect.x+8,rect.y+12),
                (rect.x+17,rect.y+19),(rect.x+13,rect.y+28)],2)
        if (col * 3 + row) % 11 == 0:
            pygame.draw.line(surface,(54,72,61),(rect.x+4,rect.bottom-5),(rect.x+12,rect.bottom-7),3)

    @staticmethod
    def paint_pit(surface, rect, joined_above):
        surface.fill((9, 9, 16), rect)
        if not joined_above:
            # 위턱은 구덩이의 맨 윗칸에만. 칸마다 그리면 한 구덩이가 여러 층으로 쪼개 보인다.
            surface.fill((48, 46, 72), (rect.x, rect.y, TILE, 3))

    @staticmethod
    def paint_block(surface, rect):
        body = (88, 80, 116)
        surface.fill(body, rect)
        surface.fill(shade(body, 1.3), (rect.x + 2, rect.y + 2, TILE - 4, 4))
        surface.fill(shade(body, 1.3), (rect.x + 2, rect.y + 2, 4, TILE - 4))
        surface.fill(shade(body, 0.62), (rect.x + 2, rect.bottom - 6, TILE - 4, 4))
        surface.fill(shade(body, 0.62), (rect.right - 6, rect.y + 2, 4, TILE - 4))
        pygame.draw.rect(surface, shade(body, 0.8), rect.inflate(-14, -14), 3)

    @staticmethod
    def paint_wall(surface, rect, row):
        """벽돌 줄눈을 엇갈리게 넣는다.

        가로줄만 그으면 벽 전체가 줄무늬로 보인다. 세로 줄눈을 한 칸씩
        어긋나게 넣어야 벽돌처럼 읽힌다.
        """
        body = (70, 74, 104)
        mortar = shade(body, 0.6)
        surface.fill(body, rect)
        half = TILE // 2
        for band in range(2):
            y = rect.y + band * half
            surface.fill(mortar, (rect.x, y, TILE, 2))
            seam = rect.x + (half if (row + band) % 2 else 0)
            surface.fill(mortar, (seam, y, 2, half))
        surface.fill(shade(body, 1.28), (rect.x, rect.y, TILE, 3))

    @staticmethod
    def paint_door(surface, rect, step, is_open, sealed):
        if is_open:
            surface.fill((8, 8, 14), rect)                     # 바깥으로 이어지는 어둠
            if step[0]:                                        # 좌우 문 — 상하 인방
                surface.fill(GOLD, (rect.x, rect.y, TILE, 5))
                surface.fill(GOLD, (rect.x, rect.bottom - 5, TILE, 5))
            else:                                              # 상하 문 — 좌우 문설주
                surface.fill(GOLD, (rect.x, rect.y, 5, TILE))
                surface.fill(GOLD, (rect.right - 5, rect.y, 5, TILE))
            return
        surface.fill((58, 44, 32) if not sealed else (44, 34, 46), rect)
        bar = GOLD if not sealed else (150, 110, 170)
        for i in range(4):                                     # 창살
            offset = 6 + i * 9
            if step[0]:
                surface.fill(bar, (rect.x + 4, rect.y + offset, TILE - 8, 4))
            else:
                surface.fill(bar, (rect.x + offset, rect.y + 4, 4, TILE - 8))
        plate = pygame.Rect(0, 0, 16, 16)
        plate.center = rect.center
        pygame.draw.rect(surface, INK, plate, border_radius=3)
        pygame.draw.rect(surface, bar, plate, 2, border_radius=3)
        surface.fill(bar, (plate.centerx - 2, plate.centery - 3, 4, 7))

    def draw_pixels(self, pattern, x, y, color, scale):
        for row, line in enumerate(pattern):
            for col, char in enumerate(line):
                if char == 'X':
                    self.ui.screen.fill(color, (x + col * scale, y + row * scale, scale, scale))

    def draw_actors(self, offset):
        screen = self.ui.screen
        state = self.room_state(self.room)
        for pickup in state['pickups']:
            art = Pickup.ART[pickup.kind]
            scale = 3 if pickup.kind in ('container', 'crown') else 2
            width, height = len(art[0]) * scale, len(art) * scale
            bob = round(math.sin(self.elapsed * 4) * 2)
            x = pickup.rect.centerx - width // 2 + offset[0]
            y = pickup.rect.centery - height // 2 + offset[1] + bob
            self.draw_pixels(art, x + 2, y + 2, INK, scale)
            self.draw_pixels(art, x, y, Pickup.COLOR[pickup.kind], scale)
        for enemy in state['enemies']:
            sprite = self.art[enemy.kind]
            phase = self.elapsed * (11 if enemy.kind == 'keese' else 5) + enemy.rect.x * .03
            bob = round(math.sin(phase)* (5 if enemy.kind == 'keese' else 2))
            pygame.draw.ellipse(screen, INK, (enemy.rect.centerx-16,enemy.rect.bottom-5,32,9))
            if enemy.kind == 'keese':
                # 날개를 접고 펴는 실루엣. 충돌 크기는 변하지 않는다.
                sprite = pygame.transform.scale(sprite, (round(30+9*math.sin(phase)),36))
            elif enemy.kind == 'boss':
                sprite = pygame.transform.scale(sprite,(64,round(64+3*math.sin(phase))))
            if enemy.flash > 0:
                sprite = sprite.copy()
                sprite.fill(WHITE, special_flags=pygame.BLEND_RGB_ADD)
            screen.blit(sprite, sprite.get_rect(center=(enemy.rect.centerx + offset[0],
                                                        enemy.rect.centery + offset[1] + bob)))
            if enemy.health < ENEMY_STATS[enemy.kind][0]:
                bar = pygame.Rect(enemy.rect.centerx-15, enemy.rect.top-13, 30, 3)
                pygame.draw.rect(screen, INK, bar.inflate(2,2))
                bar.width = round(30*max(0,enemy.health)/ENEMY_STATS[enemy.kind][0])
                pygame.draw.rect(screen, P1, bar)
        for shot in state['shots']:
            center = (shot.rect.centerx + offset[0], shot.rect.centery + offset[1])
            pygame.draw.circle(screen, INK, center, 7)
            pygame.draw.circle(screen, (206, 176, 132), center, 5)
        self.draw_hero(offset)
        self.sparks.draw(screen)

    def draw_hero(self, offset):
        hero = self.hero
        # 무적 시간에는 한 프레임 걸러 지운다. 원작에서 맞은 걸 알려 주던 방식.
        if hero.invuln > 0 and int(hero.invuln * 22) % 2:
            return
        if hero.swinging:
            self.draw_sword(offset)
        sprite = self.art[f'hero_{hero.facing}']
        cx, cy = hero.rect.centerx + offset[0], hero.rect.centery + offset[1]
        pygame.draw.ellipse(self.ui.screen, INK, (cx-15,cy+11,30,9))
        if hero.bob and not hero.swinging:
            # 두 발이 번갈아 앞쪽으로 나오는 보행 프레임.
            step = round(math.sin(hero.bob)*3)
            sprite = sprite.copy()
            sprite.fill((0,0,0,0),(0,30,36,6))
            pygame.draw.rect(sprite,(16,18,28),(8,29+max(0,step),7,4))
            pygame.draw.rect(sprite,(16,18,28),(22,29+max(0,-step),7,4))
        bob = round(math.sin(hero.bob) * 1.5)
        self.ui.screen.blit(sprite, sprite.get_rect(
            center=(hero.rect.centerx + offset[0], hero.rect.centery + offset[1] + bob)))

    def draw_sword(self, offset):
        hero = self.hero
        elapsed = SWORD_TIME - hero.swing
        reach = 34 * min(1.0, elapsed / SWORD_ACTIVE[1])
        r = hero.rect.move(offset)
        if hero.facing == 'right':
            blade = pygame.Rect(r.right - 4, r.centery - 4, reach, 8)
        elif hero.facing == 'left':
            blade = pygame.Rect(r.left + 4 - reach, r.centery - 4, reach, 8)
        elif hero.facing == 'up':
            blade = pygame.Rect(r.centerx - 4, r.top + 4 - reach, 8, reach)
        else:
            blade = pygame.Rect(r.centerx - 4, r.bottom - 4, 8, reach)
        pygame.draw.rect(self.ui.screen, INK, blade.inflate(4, 4), border_radius=3)
        pygame.draw.rect(self.ui.screen, (214, 222, 236), blade, border_radius=2)
        hilt = pygame.Rect(0, 0, 12, 12)
        hilt.center = r.center
        pygame.draw.rect(self.ui.screen, GOLD, hilt, border_radius=2)

    def draw_hud(self):
        ui = self.ui
        ui.text('FAMI QUEST', 32, 14, 22, GOLD)
        heart = ('.XX.XX.', 'XXXXXXX', 'XXXXXXX', '.XXXXX.', '..XXX..', '...X...')
        for i in range(self.hero.max_health // 2):
            x, y = 32 + i * 26, 44
            self.draw_pixels(heart, x, y, PANEL_HI, 3)
            filled = self.hero.health - i * 2
            if filled >= 2:
                self.draw_pixels(heart, x, y, P1, 3)
            elif filled == 1:                     # 반 칸
                half = tuple(line[:len(line) // 2 + 1] for line in heart)
                self.draw_pixels(half, x, y, P1, 3)
        self.draw_pixels(Pickup.ART['key'], 300, 42, GOLD, 3)
        ui.text(f'x{self.hero.keys}', 322, 46, 22, WHITE)
        minutes, seconds = divmod(int(self.elapsed), 60)
        ui.text(f'{minutes}:{seconds:02d}', 470, 46, 22, MUTED)
        # 지도. 다녀온 방만 켜진다.
        for (col, row) in ROOMS:
            rect = pygame.Rect(660 + col * 26, 26 + row * 16, 22, 12)
            if (col, row) == self.room:
                pygame.draw.rect(ui.screen, GOLD, rect, border_radius=2)
            elif (col, row) in self.visited:
                pygame.draw.rect(ui.screen, PANEL_HI, rect, border_radius=2)
            else:
                pygame.draw.rect(ui.screen, LINE, rect, 1, border_radius=2)
        boss = next((e for e in self.room_state(self.room)['enemies'] if e.kind == 'boss'), None)
        if boss:
            bar = pygame.Rect(ROOM.x, ROOM.y - 12, ROOM.width, 8)
            pygame.draw.rect(ui.screen, INK, bar.inflate(4, 4))
            pygame.draw.rect(ui.screen, P1, (bar.x, bar.y,
                                             round(bar.width * boss.health / ENEMY_STATS['boss'][0]),
                                             bar.height))

    def draw(self):
        ui = self.ui
        ui.screen.fill(BG)
        self.draw_hud()
        ui.screen.set_clip(ROOM)
        if self.transition:
            progress = 1 - self.transition['time'] / TRANSITION
            step, width, height = self.transition['step'], ROOM.width, ROOM.height
            old = (-step[0] * width * progress, -step[1] * height * progress)
            new = (old[0] + step[0] * width, old[1] + step[1] * height)
            ui.screen.blit(self.room_surface(self.transition['from']),
                           (ROOM.x + old[0], ROOM.y + old[1]))
            ui.screen.blit(self.room_surface(self.room), (ROOM.x + new[0], ROOM.y + new[1]))
            start = self.transition['from_pos'] + pygame.Vector2(old)
            end = self.transition['to_pos'] + pygame.Vector2(new)
            here = start.lerp(end, progress)
            sprite = self.art[f'hero_{self.hero.facing}']
            ui.screen.blit(sprite, sprite.get_rect(center=(round(here.x), round(here.y))))
        else:
            ui.screen.blit(self.room_surface(self.room), ROOM.topleft)
            # 빛은 반투명 표면을 재사용하고 작은 불꽃만 매 프레임 그린다.
            for x in (ROOM.left+60,ROOM.right-60):
                y = ROOM.top+35
                ui.screen.blit(self.torch_glow,(x-66,y-66))
                pygame.draw.rect(ui.screen,INK,(x-4,y,8,18))
                flicker = math.sin(self.elapsed*12+x)*3
                pygame.draw.polygon(ui.screen,(238,125,57),[(x-7,y+2),(x-3,y-13-flicker),
                    (x+1,y-6),(x+5,y-16+flicker),(x+7,y+2)])
                pygame.draw.ellipse(ui.screen,GOLD,(x-3,y-7,6,10))
            self.draw_actors((0, 0))
        ui.screen.set_clip(None)
        pygame.draw.rect(ui.screen, LINE, ROOM.inflate(4, 4), 2)
        if self.message_time > 0:
            plate = pygame.Rect(0, 0, ui.fonts[18].size(self.message)[0] + 40, 34)
            plate.center = (400, ROOM.bottom - 30)
            ui.panel(plate, fill=INK, border=GOLD, radius=8)
            ui.text(self.message, 400, plate.top + 6, 18, GOLD, center=True)
        ui.text(ui.label('방향키: 이동    A: 검    START: 일시정지    SELECT: 메뉴',
                         'D-pad: Move    A: Sword    START: Pause    SELECT: Menu'),
                400, 448, 16, MUTED, center=True)
        if self.state != 'play':
            self.draw_overlay()

    def draw_overlay(self):
        ui = self.ui
        ui.shade(205)
        card = pygame.Rect(96, 132, 608, 216)
        ui.panel(card, fill=PANEL_HI, border=GOLD, radius=14)
        if self.state == 'title':
            ui.text('FAMI QUEST', 400, card.top + 22, 40, GOLD, center=True)
            ui.text(ui.label('던전에 숨겨진 왕관을 되찾아라.',
                             'Take back the crown hidden in the dungeon.'),
                    400, card.top + 78, 18, WHITE, center=True)
            ui.text(ui.label('방향키로 걷고, A 로 검을 찌른다.',
                             'Walk with the d-pad, stab with A.'),
                    400, card.top + 108, 18, MUTED, center=True)
            ui.text(ui.label('잠긴 문에는 열쇠가 필요하다.', 'Locked doors need a key.'),
                    400, card.top + 136, 18, MUTED, center=True)
            ui.text(ui.label('A / START: 시작', 'A / START: Begin'),
                    400, card.top + 172, 22, GOLD, center=True)
        elif self.state == 'paused':
            ui.text(ui.label('일시정지', 'PAUSED'), 400, card.top + 60, 40, GOLD, center=True)
            ui.text(ui.label('A / START: 계속하기        SELECT: 메뉴',
                             'A / START: Resume        SELECT: Menu'),
                    400, card.top + 130, 18, MUTED, center=True)
        elif self.state == 'dead':
            ui.text(ui.label('쓰러졌다', 'YOU FELL'), 400, card.top + 46, 40, P1, center=True)
            ui.text(ui.label('던전은 처음부터 다시 시작된다.', 'The dungeon resets to the start.'),
                    400, card.top + 112, 18, MUTED, center=True)
            ui.text(ui.label('A / START: 다시 도전', 'A / START: Try again'),
                    400, card.top + 156, 22, GOLD, center=True)
        else:
            minutes, seconds = divmod(int(self.elapsed), 60)
            ui.text(ui.label('왕관을 되찾았다!', 'THE CROWN IS YOURS!'),
                    400, card.top + 40, 34, GOLD, center=True)
            ui.text(f'{minutes}:{seconds:02d}', 400, card.top + 96, 40, WHITE, center=True)
            ui.text(ui.label('걸린 시간', 'CLEAR TIME'), 400, card.top + 144, 16, MUTED, center=True)
            ui.text(ui.label('A / START: 다시 도전', 'A / START: Play again'),
                    400, card.top + 176, 22, GOLD, center=True)

    def run(self):
        while True:
            dt = min(self.ui.clock.tick(60) / 1000, 0.05)
            closed, pads = self.ui.poll()
            if closed or back_combo(pads):
                break
            held, pressed = merge_pads(pads)
            if pressed['select']:
                break
            if self.state == 'play':
                if pressed['start']:
                    self.state = 'paused'
                else:
                    self.update(dt, held, pressed)
            elif pressed['start'] or pressed['punch']:
                if self.state == 'paused':
                    self.state = 'play'
                else:
                    self.new_game()
            self.draw()
            self.ui.present()
        pygame.quit()


if __name__ == '__main__':
    args = options()
    Quest(args.fullscreen, args.margin).run()
