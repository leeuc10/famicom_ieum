"""Shared 800x480 console display and controller controls."""
import argparse

import pygame

from fonts import find_korean_font
from input_adapter import KeyboardAdapter
from theme import BG, EMBER, GOLD, INK, LINE, MUTED, P1, P1_DIM, P2, P2_DIM, PANEL, PANEL_HI, WHITE

WIDTH, HEIGHT = 800, 480
# 글자 크기 사다리. 임의의 숫자를 쓰지 않고 이 중에서만 고르면
# 화면끼리 글자 크기가 미묘하게 어긋나는 일이 없다.
SIZES = (14, 16, 18, 22, 28, 34, 40, 52, 64)


def options():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--fullscreen', dest='fullscreen', action='store_true')
    mode.add_argument('--windowed', dest='fullscreen', action='store_false')
    parser.set_defaults(fullscreen=True)
    parser.add_argument('--margin', type=int, choices=range(21), default=0, metavar='0-20')
    return parser.parse_args()


def back_combo(pads):
    return any(p.held['start'] and p.held['select'] for p in pads)


class ConsoleDisplay:
    def __init__(self, fullscreen=True, margin=0):
        self.fullscreen, self.margin = fullscreen, margin
        self.open()

    def open(self):
        pygame.init()
        pygame.display.set_caption('FAMI CONSOLE')
        dw, dh = pygame.display.get_desktop_sizes()[0]
        if self.fullscreen:
            self.display = pygame.display.set_mode((dw, dh), pygame.FULLSCREEN)
        else:
            scale = min(1, max(1, dw - 80) / WIDTH, max(1, dh - 100) / HEIGHT)
            self.display = pygame.display.set_mode((max(1, int(WIDTH * scale)),
                                                     max(1, int(HEIGHT * scale))), pygame.RESIZABLE)
        pygame.mouse.set_visible(False)
        self.screen = pygame.Surface((WIDTH, HEIGHT))
        path = find_korean_font()
        self.ko = path is not None
        self.fonts = {size: pygame.font.Font(path, size) for size in SIZES}
        self.input = KeyboardAdapter()
        self.clock = pygame.time.Clock()
        # A held launch/return button must be released before controlling the next screen.
        self.ready = False

    def label(self, ko, en):
        return ko if self.ko else en

    def text(self, value, x, y, size=22, color=WHITE, center=False, max_width=None, shadow=False):
        font = self.fonts[size]
        if max_width:
            original = value
            while value and font.size(value)[0] > max_width:
                original = original[:-1]
                value = original + '…' if original else ''
        image = font.render(value, True, color)
        rect = image.get_rect(midtop=(x, y)) if center else image.get_rect(topleft=(x, y))
        if shadow:
            # 밝은 무대 위에 글자가 겹칠 때만. 어두운 패널 위에서는 오히려 지저분하다.
            self.screen.blit(font.render(value, True, INK), rect.move(2, 2))
        self.screen.blit(image, rect)

    def panel(self, rect, fill=PANEL, border=None, radius=12, width=2):
        """카드·모달의 공통 생김새. 두께와 모서리를 한곳에서 정한다."""
        pygame.draw.rect(self.screen, fill, rect, border_radius=radius)
        if border:
            pygame.draw.rect(self.screen, border, rect, width, border_radius=radius)

    def shade(self, alpha=190):
        layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        layer.fill((*INK, alpha))
        self.screen.blit(layer, (0, 0))

    def poll(self):
        events = pygame.event.get()
        closed = any(e.type == pygame.QUIT for e in events)
        pads = self.input.poll()
        if not self.ready:
            if not any(any(p.held.values()) for p in pads):
                self.ready = True
            return closed, ()
        return closed, pads

    def present(self):
        w, h = self.display.get_size()
        scale = min(w / WIDTH, h / HEIGHT) * (1 - 2 * self.margin / 100)
        size = max(1, int(WIDTH * scale)), max(1, int(HEIGHT * scale))
        frame = pygame.transform.scale(self.screen, size)
        self.display.fill((0, 0, 0))
        self.display.blit(frame, ((w - size[0]) // 2, (h - size[1]) // 2))
        pygame.display.flip()
