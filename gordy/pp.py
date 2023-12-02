import random
import os

from PIL import Image, ImageFont, ImageDraw
from pilmoji import Pilmoji


PER_FRAME_DURATION = 75
END_FRAME_DURATION = 500


HERE = os.path.dirname(__file__)


def render(text):
    image = Image.new("RGBA", (1000, 150), (0, 0, 0, 0))
    font_path = os.path.join(HERE, "Inconsolata.ttf")
    font = ImageFont.truetype(font_path, 50)

    drawer = Pilmoji(image)
    drawer.text((50, 50), text, font=font)

    return image


def render_pp(sack, shaft, hand, drops):
    balls = "(" + ('_' * sack) + ")"

    rod = "=" * shaft
    rod = rod[:hand] + "✊" + rod[hand:]

    skeet = "💦" * drops
    pp = balls + rod + "D" + skeet
    return pp


def render_frames():
    sack = random.randint(2, 5)
    shaft = random.randint(2, 10)
    drops = random.randint(1, 5)

    #print(f"sack={sack} shaft={shaft} drops={drops}")

    frames = []
    for hand in range(shaft-1, -1, -1):
        pp = render_pp(sack, shaft, hand, 0)
        frames.append(pp)
    for hand in range(shaft+1):
        pp = render_pp(sack, shaft, hand, 0)
        frames.append(pp)


    for n in range(1, drops+1):
        pp = render_pp(max(1, sack - n), shaft, hand, n)
        frames.append(pp)

    return frames


def generate_pp(f):
    images = [render(frame) for frame in render_frames()]
    return images
