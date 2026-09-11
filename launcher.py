"""Controller-first game library. Register Python games in games.json."""
import json
from pathlib import Path
import subprocess
import sys

import pygame

from console_ui import BG, GOLD, MUTED, WHITE, ConsoleDisplay, back_combo, options

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

    def draw(self):
        ui = self.ui
        ui.screen.fill(BG)
        pygame.draw.rect(ui.screen, GOLD, (32, 32, 6, 39), border_radius=3)
        ui.text('FAMI CONSOLE', 52, 27, 28)
        ui.text(ui.label('함께 고르고, 바로 플레이.', 'Pick a game. Play together.'), 52, 67, 18, MUTED)
        ui.text(f'{len(self.games):02d} GAMES', 738, 43, 18, GOLD, center=True)
        if self.games:
            # A bounded page keeps any number of registered games inside 800x480.
            start = (self.selected // 3) * 3
            for index in range(start, min(start + 3, len(self.games))):
                x = 32 + (index - start) * 250
                game = self.games[index]
                active = index == self.selected
                rect = pygame.Rect(x, 126, 236, 228)
                pygame.draw.rect(ui.screen, (43, 49, 66) if active else (29, 33, 46), rect, border_radius=14)
                if active:
                    pygame.draw.rect(ui.screen, GOLD, rect, 3, border_radius=14)
                accent = (235, 102, 108) if index % 2 == 0 else (102, 187, 220)
                pygame.draw.rect(ui.screen, accent, (x + 18, 144, 200, 102), border_radius=8)
                ui.text(f'{index + 1:02d}', x + 118, 154, 64, BG, center=True)
                title = game.get('title_ko', game['title']) if ui.ko else game['title']
                desc = game.get('description_ko', game.get('description', '')) if ui.ko else game.get('description', '')
                ui.text(title, x + 18, 262, 22, GOLD if active else WHITE, max_width=200)
                ui.text(desc, x + 18, 298, 18, MUTED, max_width=200)
                ui.text(game.get('players', ''), x + 18, 325, 18, MUTED)
            ui.text(f'{self.selected + 1} / {len(self.games)}', 400, 368, 18, MUTED, center=True)
        else:
            ui.text(ui.label('등록된 게임이 없습니다', 'No games registered'), 400, 218, 28, center=True)
            ui.text('games.json', 400, 265, 22, GOLD, center=True)
        if self.message:
            ui.text(self.message, 400, 397, 18, GOLD, center=True, max_width=730)
        pygame.draw.line(ui.screen, (62, 67, 82), (32, 429), (768, 429))
        ui.text(ui.label('방향: 선택     A / START: 실행     SELECT: 종료 메뉴',
                         'D-pad: Choose    A / START: Play    SELECT: Exit menu'),
                400, 440, 18, center=True)
        if self.confirm_exit:
            shade = pygame.Surface((800, 480), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 190))
            ui.screen.blit(shade, (0, 0))
            pygame.draw.rect(ui.screen, (43, 49, 66), (100, 164, 600, 155), border_radius=14)
            ui.text(ui.label('통합 메뉴를 종료할까요?', 'Exit FAMI CONSOLE?'), 400, 185, 28, center=True)
            ui.text(ui.label('게임 메뉴만 종료합니다.', 'Closes the game menu.'), 400, 231, 18, MUTED, center=True)
            ui.text(ui.label('A / START: 종료     B / SELECT: 취소',
                             'A / START: Exit    B / SELECT: Cancel'), 400, 272, 22, GOLD, center=True)

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
