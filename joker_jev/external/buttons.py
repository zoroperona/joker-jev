"""Pixel-only button styling for the fixed green-table screenshot profile.

This is not a generic enabled-state detector. Unknown palettes fail closed.
No DOM, browser attributes, or game data are consulted.
"""
from io import BytesIO
from PIL import Image


def button_style(screenshot, target):
    with Image.open(BytesIO(screenshot)) as image:
        if image.size != (2880, 3200):
            raise ValueError('Unexpected screenshot dimensions for button styling')
        x, y = target['x'], target['y']
        box = tuple(round(v*2) for v in (x-22, y-8, x+22, y+8))
        if box[0] < 0 or box[1] < 0 or box[2] > image.width or box[3] > image.height:
            raise ValueError('Button target outside screenshot')
        pixels = list(image.convert('RGB').crop(box).getdata())
    # Enabled secondary labels are ivory on green; primary fills are gold.
    ivory = sum(r >= 205 and g >= 200 and 175 <= b <= g and abs(r-g) < 25
                for r,g,b in pixels) / len(pixels)
    gold = sum(r >= 200 and 160 <= g <= r and 90 <= b <= 170 and r-g >= 15
               for r,g,b in pixels) / len(pixels)
    green = sum(g > r and g > b and g-r >= 10 for r,g,b in pixels) / len(pixels)
    dim = sum(90 <= r <= 155 and 105 <= g <= 170 and 80 <= b <= 155 and g > r and g > b
              for r,g,b in pixels) / len(pixels)
    label = target['label']
    primary = label in ('叫3分', '出牌')
    if primary and gold >= .5:
        status = 'enabled'
    elif not primary and label in ('不出', '不叫', '叫1分', '叫2分') and .025 <= ivory <= .4 and green >= .5:
        status = 'enabled'
    elif ivory < .005 and gold < .005 and green >= .8 and dim >= .025:
        status = 'disabled'
    else:
        status = 'unknown'
    return {'status': status, 'profile': 'green-table-v1',
            'ivory_fraction': ivory, 'gold_fraction': gold,
            'green_fraction': green, 'dim_fraction': dim}
