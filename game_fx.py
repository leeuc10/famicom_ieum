"""Bounded cosmetic effects; never read by game rules or collision code."""
import math
import pygame


class Sparks:
    def __init__(self):
        self.items = []

    def burst(self, pos, color, count=12):
        for i in range(count):
            angle = i * math.tau / count + 0.23
            speed = 65 + (i % 4) * 28
            self.items.append([float(pos[0]), float(pos[1]), math.cos(angle)*speed,
                               math.sin(angle)*speed, 0.34 + (i % 3)*0.06, color])
        self.items = self.items[-96:]

    def update(self, dt):
        for p in self.items:
            p[0] += p[2]*dt
            p[1] += p[3]*dt
            p[3] += 100*dt
            p[4] -= dt
        self.items = [p for p in self.items if p[4] > 0]

    def draw(self, surface):
        for x,y,vx,vy,life,color in self.items:
            end = (x-vx*.025, y-vy*.025)
            pygame.draw.line(surface, color, (x,y), end, 3 if life > .16 else 1)


def glow(radius, color):
    image = pygame.Surface((radius*2, radius*2), pygame.SRCALPHA)
    for r in range(radius, 0, -4):
        alpha = int(2 + 28 * (1-r/radius)**2)
        pygame.draw.circle(image, (*color, alpha), (radius, radius), r)
    return image
