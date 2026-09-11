"""Load the approved martial artist and prepare all animation frames once.

The original generated sheet is preserved. Chroma key and the second player's
palette are applied only to the in-memory game surfaces, without extra packages.
"""
from pathlib import Path

import pygame

ATLAS = Path(__file__).parent / 'assets' / 'fighters' / 'martial-artist-v1.png'
SCALE = 0.40
# Actual body anchors in the generated atlas, rather than the centre of an
# extended arm or leg. This prevents the character sliding as it attacks.
ANCHORS = (
    (126, 382, 642, 900),
    (124, 386, 649, 904),
    (126, 390, 646, 900),
    (123, 363, 625, 895),
    (107, 346, 624, 890),
    (138, 392, 649, 895),
)


class FighterSprites:
    def __init__(self, specs):
        self.specs = specs
        source = pygame.image.load(str(ATLAS))
        if source.get_size() != (1024, 1536):
            raise ValueError('Fighter atlas must be 1024x1536')
        # Downsample before chroma/palette work to keep startup bounded on Pi.
        source = pygame.transform.scale(source, (512, 768))
        red = pygame.Surface(source.get_size(), pygame.SRCALPHA)
        blue = pygame.Surface(source.get_size(), pygame.SRCALPHA)
        for y in range(source.get_height()):
            for x in range(source.get_width()):
                r, g, b, _ = source.get_at((x, y))
                if r > 110 and b > 100 and g < min(r, b) * .65:
                    continue
                red.set_at((x, y), (r, g, b, 255))
                if r > 55 and r > g * 1.5 and r > b * 1.5 and g-b < (r-b)*.24:
                    blue.set_at((x, y), (b, min(255, round(g+r*.22)), r, 255))
                else:
                    blue.set_at((x, y), (r, g, b, 255))
        self.frames = {}
        for player, sheet in enumerate((red, blue)):
            for row in range(6):
                # The longest kick extends past its nominal cell boundary.
                edges = (0, 252, 520, 806, 1024) if row == 4 else (0,256,512,768,1024)
                for col in range(4):
                    left, right = edges[col]//2, edges[col+1]//2
                    cell = sheet.subsurface((left,row*128,right-left,128))
                    bounds = cell.get_bounding_rect(min_alpha=128)
                    if not bounds.width or not bounds.height:
                        raise ValueError(f'Empty fighter frame {row}:{col}')
                    frame = cell.subsurface(bounds).copy()
                    scale = SCALE * 2
                    frame = pygame.transform.scale(frame, (max(1,round(frame.get_width()*scale)),
                                                            max(1,round(frame.get_height()*scale))))
                    anchor = round((ANCHORS[row][col]/2-left-bounds.x)*scale)
                    # Scaling can discard isolated source edge pixels; trim again
                    # so every frame lands on its actual visible boot sole.
                    trim = frame.get_bounding_rect(min_alpha=128)
                    frame = frame.subsurface(trim).copy()
                    anchor -= trim.x
                    for facing in (1,-1):
                        sprite = frame if facing==1 else pygame.transform.flip(frame, True, False)
                        pivot = anchor if facing==1 else frame.get_width()-anchor
                        self.frames[player,row,col,facing] = (sprite,pivot)

    def pose(self, fighter):
        if fighter.stunned:
            return 5, min(3, int((1-min(1,fighter.hitstun/.26))*4))
        if fighter.attacking:
            # Match the existing startup / active / recovery timing exactly.
            spec = self.specs[fighter.attack]
            phase = fighter.attack_phase
            if phase < spec.startup:
                frame = 0
            elif phase < spec.startup+spec.active:
                frame = 1 if phase-spec.startup < spec.active/2 else 2
            else:
                frame = 3
            return (3 if fighter.attack=='punch' else 4), frame
        if not fighter.on_ground:
            return 2, 1 if fighter.velocity_y < -80 else 2 if fighter.velocity_y < 100 else 3
        if fighter.moving:
            return 1, int(fighter.walk_cycle / 1.5) % 4
        return 0, int(fighter.pose_time*4) % 4

    def draw(self, surface, fighter):
        row,col = self.pose(fighter)
        sprite, pivot = self.frames[0 if fighter.name=='P1' else 1,row,col,fighter.facing]
        surface.blit(sprite,(round(fighter.rect.centerx-pivot),fighter.rect.bottom-sprite.get_height()))
