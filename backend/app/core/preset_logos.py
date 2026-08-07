"""Built-in preset logos every tenant can pick from instead of uploading their
own. The 16 images live in frontend/public/preset-logos/ (sliced from a 4x4
grid design asset) and are served directly by the frontend at these paths -
no backend file serving involved, so the URL is just a frontend-relative path."""

import random

PRESET_LOGO_COUNT = 16
PRESET_LOGO_URLS = [f"/preset-logos/preset-{i:02d}.png" for i in range(1, PRESET_LOGO_COUNT + 1)]


def random_preset_logo_url() -> str:
    return random.choice(PRESET_LOGO_URLS)
