"""Controller-first game library. Register Python games in games.json."""
import json
from pathlib import Path
import subprocess
import sys

import pygame

from console_ui import (BG, GOLD, INK, LINE, MUTED, P1, P2, PANEL, PANEL_HI, WHITE,
                        ConsoleDisplay, back_combo, options)
from theme import shade

ROOT = Path(__file__).resolve().parent


def load_games(path=ROOT / 'games.json'):
    try:
        entries = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(entries, list):
            raise ValueError('games.json must contain a list')
        for entry in entries:
            if not isinstance(entry, dict) or not all(
                isinstance(entry.get(key), str) and entry[key].strip()
                for key in ('title', 'script')
            ):
                raise ValueError('Each game needs a title and script')
            if any(key in entry and not isinstance(entry[key], str)
                   for key in ('title_ko', 'description', 'description_ko', 'players')):
                raise ValueError('Game labels must be strings')
        return entries, ''
    except (OSError, ValueError) as exc:
        return [], str(exc)


class Launcher:
    def __init__(self, fullscreen=True, margin=0):
        self.ui = ConsoleDisplay(fullscreen, margin)
        self.games, self.error = load_games()
        self.selected = 0
        self.confirm_exit = False
        self.message = self.ui.label('게임 목록을 읽지 못했습니다. games.json을 확인하세요.',
                                     'Cannot read games.json. Check the file.') if self.error else ''
        if self.error:
            print(self.error, file=sys.stderr)

    def launch(self):
        if not self.games:
            return
        game = self.games[self.selected]
        script = ROOT / game['script']
        if not script.is_file():
            self.message = self.ui.label('게임 파일이 없습니다: ', 'Missing game file: ') + game['script']
            return
        self.message = ''
        self.draw()
        self.ui.text(self.ui.label('게임 시작 중…', 'Starting game…'), 400, 382, center=True, color=GOLD)
        self.ui.present()
        args = [sys.executable, str(script),
                '--fullscreen' if self.ui.fullscreen else '--windowed',
                '--margin', str(self.ui.margin)]
        # Release SDL before starting the child so it owns the display and HID focus.
        pygame.quit()
        try:
            result = subprocess.run(args, cwd=script.parent, check=False)
            failed = result.returncode != 0
        except OSError as exc:
            print(exc, file=sys.stderr)
            failed = True
        finally:
            self.ui.open()
        if failed:
            self.message = self.ui.label('게임 실행 오류. 터미널 로그를 확인하세요.',
                                         'Game failed. Check the terminal log.')

    def handle(self, pads):
        if not pads:
            return True
        pressed = lambda *keys: any(p.any_pressed(*keys) for p in pads)
        if self.confirm_exit:
            if pressed('select', 'kick'):
                self.confirm_exit = False
            elif pressed('start', 'punch'):
                return False
        elif back_combo(pads) or pressed('select'):
            self.confirm_exit = True
        elif self.games:
            if pressed('left', 'up'):
                self.selected = (self.selected - 1) % len(self.games)
                self.message = ''
            elif pressed('right', 'down'):
                self.selected = (self.selected + 1) % len(self.games)
                self.message = ''
            elif pressed('start', 'punch'):
                self.launch()
        return True

    def card(self, index, start):
        """게임 한 칸. 고른 칸은 살짝 떠오르고 금색 테두리가 붙는다."""
        ui = self.ui
        active = index == self.selected
        game = self.games[index]
        rect = pygame.Rect(32 + (index - start) * 250, 120 if active else 126, 236, 234 if active else 222)
        if active:
            # 떠 있는 느낌을 주는 그림자. 선택이 색 하나로만 표시되면 눈에 덜 띈다.
            ui.panel(rect.move(0, 6), fill=INK, radius=14)
        ui.panel(rect, fill=PANEL_HI if active else PANEL,
                 border=GOLD if active else LINE, radius=14, width=3 if active else 2)
        accent = P1 if index % 2 == 0 else P2
        art = pygame.Rect(rect.x + 18, rect.y + 18, 200, 102)
        pygame.draw.rect(ui.screen, accent, art, border_radius=8)
        # 대각선 무늬로 단색 덩어리에 결을 넣는다.
        stripes = pygame.Surface(art.size, pygame.SRCALPHA)
        for x in range(-art.height, art.width, 26):
            pygame.draw.polygon(stripes, (*INK, 28), [(x, art.height), (x + 11, art.height),
                                                      (x + 11 + art.height, 0), (x + art.height, 0)])
        ui.screen.blit(stripes, art.topleft)
        ui.text(f'{index + 1:02d}', art.centerx, art.y + 12, 64, shade(accent, 0.45), center=True)
        title = game.get('title_ko', game['title']) if ui.ko else game['title']
        desc = game.get('description_ko', game.get('description', '')) if ui.ko else game.get('description', '')
        ui.text(title, rect.x + 18, art.bottom + 16, 22, GOLD if active else WHITE, max_width=200)
        ui.text(desc, rect.x + 18, art.bottom + 52, 18, MUTED, max_width=200)
        ui.text(game.get('players', ''), rect.x + 18, art.bottom + 79, 14, MUTED)
        if active:
            ui.text('▶', rect.right - 34, art.bottom + 74, 22, GOLD)

    def draw(self):
        ui = self.ui
        ui.screen.fill(BG)
        pygame.draw.rect(ui.screen, GOLD, (32, 32, 6, 39), border_radius=3)
        ui.text('FAMI CONSOLE', 52, 27, 28)
        ui.text(ui.label('함께 고르고, 바로 플레이.', 'Pick a game. Play together.'), 52, 67, 18, MUTED)
        ui.text(f'{len(self.games):02d} GAMES', 738, 43, 18, GOLD, center=True)
        pygame.draw.line(ui.screen, LINE, (32, 100), (768, 100))
        if self.games:
            # A bounded page keeps any number of registered games inside 800x480.
            start = (self.selected // 3) * 3
            for index in range(start, min(start + 3, len(self.games))):
                self.card(index, start)
            # 페이지 점. 등록된 게임이 세 개를 넘어갈 때 어디쯤인지 알려 준다.
            pages = (len(self.games) + 2) // 3
            if pages > 1:
                for page in range(pages):
                    x = 400 - (pages - 1) * 9 + page * 18
                    pygame.draw.circle(ui.screen, GOLD if page == start // 3 else LINE, (x, 374), 4)
            else:
                ui.text(f'{self.selected + 1} / {len(self.games)}', 400, 366, 14, MUTED, center=True)
        else:
            ui.text(ui.label('등록된 게임이 없습니다', 'No games registered'), 400, 208, 28, center=True)
            ui.text('games.json', 400, 258, 22, GOLD, center=True)
        if self.message:
            ui.text(self.message, 400, 394, 18, GOLD, center=True, max_width=730)
        pygame.draw.line(ui.screen, LINE, (32, 429), (768, 429))
        ui.text(ui.label('방향: 선택     A / START: 실행     SELECT: 종료 메뉴',
                         'D-pad: Choose    A / START: Play    SELECT: Exit menu'),
                400, 440, 18, center=True)
        if self.confirm_exit:
            ui.shade(200)
            card = pygame.Rect(100, 164, 600, 155)
            ui.panel(card, fill=PANEL_HI, border=GOLD, radius=14)
            ui.text(ui.label('통합 메뉴를 종료할까요?', 'Exit FAMI CONSOLE?'), 400, card.top + 22, 28, center=True)
            ui.text(ui.label('게임 메뉴만 종료합니다.', 'Closes the game menu.'), 400, card.top + 66, 18, MUTED, center=True)
            ui.text(ui.label('A / START: 종료     B / SELECT: 취소',
                             'A / START: Exit    B / SELECT: Cancel'), 400, card.top + 106, 22, GOLD, center=True)

    def run(self):
        running = True
        while running:
            self.ui.clock.tick(60)
            closed, pads = self.ui.poll()
            if closed:
                break
            running = self.handle(pads)
            self.draw()
            self.ui.present()
        pygame.quit()


if __name__ == '__main__':
    args = options()
    Launcher(args.fullscreen, args.margin).run()
