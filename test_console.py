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

    def test_list_and_invalid_registry(self):
        games, error = load_games()
        self.assertFalse(error)
        self.assertEqual(len(games), 2)
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
        self.assertEqual(menu.selected, 1)
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
        for module, klass in (('main', 'Game'), ('pong', 'PaddleGame')):
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
