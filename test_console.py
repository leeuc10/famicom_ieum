"""Headless checks: python -m unittest test_console."""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import pygame
from input_adapter import Pad, BUTTONS
from launcher import Launcher, load_games
from pong import PaddleGame


def pad(*buttons):
    result = Pad()
    result.feed({name: name in buttons for name in BUTTONS})
    return result


class ConsoleTests(unittest.TestCase):
    def tearDown(self):
        pygame.quit()

    def test_sprite_frames_and_attack_contact(self):
        from main import Game, ATTACKS
        game = Game(False)
        self.assertEqual(len(game.sprites.frames), 96)
        for sprite, pivot in game.sprites.frames.values():
            self.assertEqual(sprite.get_bounding_rect().bottom, sprite.get_height())
            self.assertTrue(sprite.get_flags() & pygame.SRCALPHA)
        for attack in ('punch', 'kick'):
            for facing in (1, -1):
                game.reset_match()
                a, b = game.p1, game.p2
                a.x = 400; a.sync_rect(); a.facing = facing
                a.start_attack(attack)
                spec = ATTACKS[attack]
                a.attack_time = spec.duration - spec.startup - .001
                box = a.attack_box()
                b.x = box.right-2 if facing==1 else box.left-b.rect.width+2
                b.sync_rect()
                game.resolve_hits()
                self.assertEqual(b.health, 100-spec.damage)
                a.attack_connected = False
                b.health = 100
                b.x = box.right+1 if facing==1 else box.left-b.rect.width-1
                b.sync_rect()
                game.resolve_hits()
                self.assertEqual(b.health,100)

    def test_visual_effects_expire_and_are_bounded(self):
        from game_fx import Sparks
        effect = Sparks()
        for _ in range(100):
            effect.burst((400, 240), (255, 200, 100))
        self.assertLessEqual(len(effect.items), 96)
        effect.update(1)
        self.assertEqual(effect.items, [])

    def test_gameplay_render_states(self):
        from main import Game
        from quest import Quest
        fight = Game(False)
        fight.begin_match()
        for attack in ('punch', 'kick'):
            fight.p1.attack_time = 0
            fight.p1.start_attack(attack)
            for _ in range(24):
                fight.update(1/60, (pad('right'), pad('left')))
                fight.draw_fight()
        pygame.quit()
        quest = Quest(False)
        quest.new_game()
        quest.enter_room((2, 0), None)
        for _ in range(30):
            quest.elapsed += 1/60
            quest.hero.bob += .2
            quest.draw()
        for facing in ('left', 'right', 'up', 'down'):
            quest.hero.facing = facing
            quest.hero.attack()
            quest.hero.swing = .18
            quest.draw()

    def test_player_system_keys_are_independent(self):
        from input_adapter import KeyboardAdapter
        from console_ui import back_combo
        class Keys:
            def __init__(self, values): self.values = values
            def __getitem__(self, key): return key in self.values
        for keys, expected in (((pygame.K_RETURN, pygame.K_F3), False),
                               ((pygame.K_F2, pygame.K_ESCAPE), False),
                               ((pygame.K_RETURN, pygame.K_ESCAPE), True),
                               ((pygame.K_F2, pygame.K_F3), True)):
            with patch('pygame.key.get_pressed', return_value=Keys(keys)):
                self.assertEqual(back_combo(KeyboardAdapter().poll()), expected)

    def test_knockback_is_time_based(self):
        from quest import Actor, ROOM, LAYOUTS
        distances = []
        for fps in (20, 30, 60, 120):
            actor = Actor(*ROOM.center, 26)
            actor.knock.update(320, 0)
            start = actor.pos.x
            for _ in range(fps):
                actor.apply_knock(1 / fps, LAYOUTS['open'])
            distances.append(actor.pos.x - start)
        self.assertLess(max(distances) - min(distances), 0.00001)

    def test_wiring_screen_fits_display(self):
        from input_adapter import run_wiring_test
        from console_ui import ConsoleDisplay
        captures = []
        def present(ui):
            captures.append(ui.screen.get_size())
            pygame.event.post(pygame.event.Event(pygame.QUIT))
        with patch.object(ConsoleDisplay, 'present', present):
            run_wiring_test()
        self.assertEqual(captures, [(800, 480)])

    def test_list_and_invalid_registry(self):
        games, error = load_games()
        self.assertFalse(error)
        self.assertTrue(games)
        for entry in games:
            self.assertTrue((Path(__file__).parent / entry['script']).is_file(), entry)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'games.json'
            for data in ('{', '{}', '[{}]', '[{"title":"a","script":"b","players":2}]'):
                path.write_text(data)
                self.assertTrue(load_games(path)[1])
            path.write_text('[]')
            self.assertEqual(load_games(path), ([], ''))

    def test_navigation_and_exit_confirmation(self):
        menu = Launcher(False)
        menu.handle((pad('left'),))
        self.assertEqual(menu.selected, len(menu.games) - 1)   # 목록 끝으로 돌아간다
        menu.handle((pad('right'),))
        self.assertEqual(menu.selected, 0)
        self.assertTrue(menu.handle((pad('select'),)))
        self.assertTrue(menu.confirm_exit)
        menu.handle((pad('kick'),))
        self.assertFalse(menu.confirm_exit)
        menu.handle((pad('select'),))
        self.assertFalse(menu.handle((pad('punch'),)))

    def test_child_launch_return_and_failure(self):
        menu = Launcher(False, 5)
        with patch('launcher.subprocess.run', return_value=subprocess.CompletedProcess([], 0)) as run:
            menu.launch()
            args = run.call_args.args[0]
            self.assertEqual(args[-3:], ['--windowed', '--margin', '5'])
            self.assertTrue(pygame.display.get_init())
            self.assertFalse(menu.ui.ready)
            self.assertFalse(menu.message)
        with patch('launcher.subprocess.run', side_effect=OSError('test failure')):
            menu.launch()
            self.assertTrue(menu.message)
            self.assertTrue(pygame.display.get_init())
        menu.games = [{'title': 'missing', 'script': 'no-such-game.py'}]
        with patch('launcher.subprocess.run') as run:
            menu.launch()
            run.assert_not_called()
            self.assertTrue(menu.message)

    def test_real_child_and_game_exit(self):
        menu = Launcher(False)
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / 'child.py'
            script.write_text('import sys\nassert sys.argv[1:] == ["--windowed", "--margin", "0"]\n')
            menu.games = [{'title': 'Smoke', 'script': str(script)}]
            menu.launch()
            self.assertFalse(menu.message)
            self.assertTrue(pygame.display.get_init())
        import sys
        for module, klass in (('main', 'Game'), ('pong', 'PaddleGame'), ('quest', 'Quest')):
            result = subprocess.run([sys.executable, '-c',
                f'import pygame; from {module} import {klass}; '
                f'game = {klass}(fullscreen=False); '
                'pygame.event.post(pygame.event.Event(pygame.QUIT)); game.run()'],
                cwd=Path(__file__).parent, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_layout_pages_and_empty_state(self):
        menu = Launcher(False)
        menu.games *= 4
        for selected in (0, 3, 7):
            menu.selected = selected
            menu.draw(); menu.ui.present()
        menu.confirm_exit = True
        menu.draw(); menu.ui.present()
        menu.games = []
        menu.draw(); menu.ui.present()
        self.assertEqual(menu.ui.screen.get_size(), (800, 480))

    def test_paddle_scoring_bounds_and_collision(self):
        game = PaddleGame(False)
        game.state = 'play'
        game.countdown = 0
        game.ball.update(60, game.paddles[0].centery)
        game.velocity.update(-260, 0)
        game.update(0.01, (pad(), pad()))
        self.assertGreater(game.velocity.x, 0)
        for _ in range(100):
            game.update(0.035, (pad('up'), pad('down')))
        self.assertEqual(game.paddles[0].top, 92)
        self.assertEqual(game.paddles[1].bottom, 416)
        game.scores = [6, 0]
        game.countdown = 0
        game.ball.update(820, 250)
        game.update(0, (pad(), pad()))
        self.assertEqual(game.scores, [7, 0])
        self.assertEqual(game.state, 'over')
        game.draw(); game.ui.present()


if __name__ == '__main__':
    unittest.main()
