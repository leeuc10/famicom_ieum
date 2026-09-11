# Martial artist v1

Generated with the built-in image_gen tool from the user-approved red/blue four-pose kick concept. This is the original chroma-key sheet, preserved without destructive asset edits. `fighter_sprites.py` prepares keyed, cropped, palette-swapped and mirrored surfaces at load time; no added runtime package is required.

Layout: 1024×1536, four frames per row; idle, walk, jump, punch, kick, hurt. Per-frame body anchors and the extended kick cell boundaries are recorded in `fighter_sprites.py`. 2P uses the same poses mirrored, with red uniform pixels palette-swapped to blue while preserving skin and black details.

Final built-in edit prompt:

> Technical sprite sheet edit. Change ONLY the background. Replace ALL checkerboard pixels with a perfectly flat solid pure chroma-key MAGENTA #FF00FF (RGB 255,0,255). No transparency needed. No gradients, no lighting, no shadows on background, no checkerboard. Keep all 24 red fighter sprites exactly unchanged in pose, size, position and scale, on the same 1024x1536 4-column 6-row grid. All empty space between and inside limb gaps must be perfectly solid magenta. Crisp non-antialiased boundaries. Flat magenta fills entire canvas outside character silhouettes. DO NOT use red/brown/gray backgrounds. Magenta only.

The source generation requested a compact red martial artist with black hair, headband tails, cream V collar, black belt/gloves/boots; an idle loop, walking, jumping, straight punch, raised-knee side kick and recoil, with consistent full-body proportions and no detached limbs.
