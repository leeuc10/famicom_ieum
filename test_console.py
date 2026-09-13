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
        for module, klass in (('main', 'Game'), ('pong', 'PaddleGame'), ('quest', 'Quest'),
                              ('cargo', 'CargoGame'), ('starfall', 'Starfall'), ('breakout', 'PrismBreak')):
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


    def test_breakout_collision_lives_and_stages(self):
        from breakout import PrismBreak, FIELD, RADIUS
        game = PrismBreak(False)
        game.reset()
        game.launch()
        game.ball.update(400, game.paddle.top-RADIUS-2)
        game.velocity.update(0, 470)
        game.update(.05, (pad(), pad()))
        self.assertLess(game.velocity.y, 0)
        game.ball.update(30, FIELD.bottom+RADIUS+1)
        game.velocity.update(0, 300)
        game.update(.01, (pad(), pad()))
        self.assertEqual((game.lives, game.state), (2, 'ready'))
        self.assertEqual(len(game.bricks), 40)
        game.level = 3
        game.bricks = [[pygame.Rect(360, 160, 66, 22), 2, 0]]
        for expected_hp in (1, 0):
            game.state = 'play'
            game.ball.update(390, 195)
            game.velocity.update(0, -470)
            game.update(.04, (pad(), pad()))
            if expected_hp:
                self.assertEqual(game.bricks[0][1], expected_hp)
                self.assertGreater(game.velocity.y, 0)
        self.assertEqual((game.state, game.score), ('won', 235))
        game.update(.04, (pad(), pad()))
        self.assertEqual(game.score, 235)
        game.handle((pad('punch'), pad()))
        self.assertEqual((game.level, game.lives, game.score, game.state), (1, 3, 0, 'ready'))
        self.assertEqual(game.best, 235)
        game.bricks = [[pygame.Rect(360, 160, 66, 22), 1, 0]]
        game.state = 'play'
        game.ball.update(390, 195)
        game.velocity.update(0, -470)
        game.update(.04, (pad(), pad()))
        self.assertEqual((game.level, game.state), (2, 'ready'))
        game.lives = 1
        game.launch()
        game.ball.update(30, FIELD.bottom+RADIUS+1)
        game.velocity.update(0, 300)
        game.update(.01, (pad(), pad()))
        self.assertEqual((game.lives, game.state), (0, 'over'))

    def test_breakout_controller_pause_and_bounds(self):
        from breakout import PrismBreak, FIELD
        game = PrismBreak(False)
        game.handle((pad(), pad('start')))
        self.assertEqual((game.player, game.state), (1, 'ready'))
        game.update(.02, (pad('right'), pad()))
        self.assertEqual(game.x, 400)
        game.handle((pad(), pad('start')))
        game.update(.02, (pad(), pad('right')))
        self.assertEqual(game.x, 400)
        game.handle((pad(), pad('start')))
        self.assertEqual(game.state, 'ready')
        game.update(.02, (pad(), pad('right', 'kick')))
        self.assertAlmostEqual(game.x, 404)
        for _ in range(100):
            game.update(.02, (pad(), pad('right')))
        self.assertLessEqual(game.paddle.right, FIELD.right)
        self.assertEqual(game.ball.x, game.x)
        game.handle((pad(), pad('punch')))
        self.assertEqual(game.state, 'play')
        for state in ('title', 'ready', 'play', 'paused', 'won', 'over'):
            game.state = state
            game.draw()
            game.ui.present()
        self.assertFalse(game.handle((pad(), pad('select'))))

    def test_starfall_damage_shield_scoring_and_finish(self):
        from starfall import Starfall, Meteor, DURATION
        game = Starfall(False)
        game.reset()
        game.spawn = 99
        game.rocks = [Meteor(400, 365, 18, 0, 0) for _ in range(3)]
        game.update(.01, (pad(), pad()))
        self.assertEqual(game.lives, 2)  # A cluster costs only one life.
        game.invincible = 0
        game.rocks = [Meteor(400, 365, 18, 0, 0)]
        game.update(.01, (pad('kick'), pad()))
        self.assertEqual(game.lives, 2)
        self.assertGreater(game.cooldown, 0)
        game.rocks = [Meteor(400, 200, 18, 0, 0)]
        game.shots = [pygame.Vector2(400, 205)]
        game.update(.01, (pad(), pad()))
        self.assertEqual(game.score, 10)
        self.assertFalse(game.rocks)
        game.elapsed = DURATION - .01
        game.update(.02, (pad(), pad()))
        self.assertEqual((game.state, game.score), ('won', 210))
        game.update(.02, (pad(), pad()))
        self.assertEqual(game.score, 210)
        game.handle((pad('start'), pad()))
        self.assertEqual((game.state, game.lives, game.score), ('play', 3, 0))
        self.assertEqual(game.best, 210)
        game.invincible = 0
        game.lives = 1
        game.rocks = [Meteor(400, 365, 18, 0, 0)]
        game.update(.01, (pad(), pad()))
        self.assertEqual(game.state, 'over')

    def test_starfall_controller_pause_bounds_and_render(self):
        from starfall import Starfall, FIELD
        game = Starfall(False)
        game.handle((pad(), pad('start')))
        self.assertEqual(game.player, 1)
        x = game.ship.x
        game.update(.02, (pad('left'), pad()))
        self.assertEqual(game.ship.x, x)
        game.handle((pad(), pad('start')))
        elapsed = game.elapsed
        game.update(.02, (pad(), pad('right')))
        self.assertEqual(game.elapsed, elapsed)
        game.handle((pad(), pad('start')))
        for _ in range(400):
            game.update(.02, (pad(), pad('right', 'down', 'punch')))
        self.assertLess(game.ship.x, FIELD.right)
        self.assertLess(game.ship.y, FIELD.bottom)
        self.assertLess(len(game.shots), 10)
        self.assertLess(len(game.rocks), 30)
        for state in ('title', 'play', 'paused', 'won', 'over'):
            game.state = state
            game.draw()
            game.ui.present()
        self.assertFalse(game.handle((pad(), pad('start', 'select'))))

    def test_cargo_is_carried_by_both_players(self):
        """가로 이동이 두 사람 의도의 평균이라는 규칙은 이 게임의 전부다."""
        from cargo import CargoGame, CARRY_SPEED
        game = CargoGame(False)
        for inputs, expected in ((('right', 'left'), 0), (('right', 'right'), CARRY_SPEED),
                                 (('right', None), CARRY_SPEED / 2)):
            game.reset()
            start = game.cx
            for _ in range(60):
                game.move_plank(1 / 60, tuple(pad(*(name,) if name else ()) for name in inputs))
            self.assertAlmostEqual(game.cx - start, expected, delta=1)
        # 높이차 상한을 넘기면 두 손이 같은 양씩 물러난다. 한쪽만 손해 보면 협동이 아니다.
        from cargo import TILT_LIMIT
        game.reset()
        for _ in range(300):
            game.move_plank(1 / 60, (pad('up'), pad('down')))
        self.assertAlmostEqual(game.hands[1] - game.hands[0], TILT_LIMIT, delta=0.01)
        self.assertAlmostEqual(sum(game.hands) / 2, 300, delta=0.01)

    def test_cargo_catch_slide_deliver_and_drop(self):
        from cargo import CargoGame, Crate, CRATE_TONES, CX_MAX, FIELD
        game = CargoGame(False)
        game.state = 'play'

        def play(frames, *inputs):
            for _ in range(frames):
                game.next_drop = 99           # 검사 중에는 새 화물이 끼어들지 않게 한다
                game.warnings.clear()
                game.update(1 / 60, tuple(pad(*keys) for keys in inputs))

        def drop_at(x):
            game.air.append(Crate(x, FIELD.top + 36, (0, 150), CRATE_TONES[0]))

        drop_at(game.cx)                       # 수평 판자는 화물을 받아 붙잡는다
        play(120, (), ())
        self.assertEqual((len(game.load), game.lives), (1, 3))
        play(60, (), ())
        self.assertEqual(len(game.load), 1)
        play(120, ('up',), ('down',))          # 기울이면 낮은 쪽으로 미끄러져 판자를 벗어난다
        self.assertEqual(len(game.load), 0)
        play(180, (), ())
        self.assertEqual((game.lives, game.delivered), (2, 0))   # 투입구 밖이면 바닥에 깨진다

        game.cx = CX_MAX                       # 투입구 앞에서 기울이면 배달된다
        game.hands = [300.0, 300.0]            # 받을 때는 다시 수평으로
        drop_at(CX_MAX)
        play(120, (), ())
        self.assertEqual(len(game.load), 1)
        play(150, ('up',), ('down',))
        self.assertEqual((game.delivered, game.lives, len(game.air)), (1, 2, 0))

        game.cx = 200                          # 세 번 놓치면 경기가 끝난다
        for _ in range(2):
            drop_at(660)
            play(200, (), ())
        self.assertEqual((game.lives, game.state), (0, 'over'))

    def test_cargo_load_never_overlaps_or_leaks(self):
        from cargo import CargoGame, Crate, CRATE_TONES, CRATE, HALF, FIELD
        game = CargoGame(False)
        game.state = 'play'
        for _ in range(5):
            game.air.append(Crate(game.cx, FIELD.top + 36, (0, 150), CRATE_TONES[0]))
            for _ in range(100):
                game.next_drop = 99
                game.warnings.clear()
                game.update(1 / 60, (pad(), pad()))
        for a, b in zip(game.load, game.load[1:]):
            self.assertGreaterEqual(b.u - a.u, CRATE - 0.01)
        for crate in game.load:
            self.assertLessEqual(abs(crate.u), HALF + CRATE)
        self.assertEqual(len(game.load) + len(game.air) + game.delivered + (3 - game.lives), 5)
        game.draw(); game.ui.present()
        self.assertEqual(game.ui.screen.get_size(), (800, 480))


if __name__ == '__main__':
    unittest.main()
