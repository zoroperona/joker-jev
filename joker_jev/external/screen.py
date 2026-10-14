"""macOS Vision OCR adapter for the existing 1440×1600 web table.

Input is a PNG only. No DOM, game HTTP API, accessibility tree or JavaScript state.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

from .state import RANKS, ordered

NAMES = {'你': 'self', '东篱': 'right', '西窗': 'left'}


def parse_cards(text):
    text = text.replace('大王', ' BJ ').replace('小王', ' SJ ')
    compact = re.sub(r'\s+', '', text)
    tokens = re.findall(r'10|SJ|BJ|[3-9JQKA2]', compact)
    if ''.join(tokens) != compact:
        raise ValueError('Unrecognized card text: ' + text)
    return ordered(tokens)


class ScreenReader:
    def __init__(self):
        source = Path(__file__).with_name('vision.swift')
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
        self.binary = Path(tempfile.gettempdir()) / ('joker-vision-' + digest)
        if not self.binary.exists():
            subprocess.run(['swiftc', str(source), '-o', str(self.binary)], check=True, capture_output=True)

    def ocr(self, image, fast=False):
        with tempfile.TemporaryDirectory(prefix='joker-ocr-') as directory:
            path = Path(directory) / 'crop.png'
            image.save(path)
            result = subprocess.run([str(self.binary), str(path)] + (['--fast'] if fast else []),
                                    check=True, capture_output=True, text=True, timeout=15)
            return json.loads(result.stdout)

    def region(self, image, box):
        scale = image.width / 1440
        crop = image.crop(tuple(round(v * scale) for v in box))
        rows = self.ocr(crop)
        for r in rows:
            x, y, w, h = r['box']
            r['box'] = [box[0] + x * (box[2]-box[0]), box[1] + y * (box[3]-box[1]),
                        w * (box[2]-box[0]), h * (box[3]-box[1])]
        return rows

    def read(self, image):
        if image.size != (2880, 3200):
            raise ValueError('This screen profile requires 1440×1600, device scale 2, browser zoom 100%')
        rows = self.region(image, (100, 220, 1340, 790))
        text = '\n'.join(r['text'] for r in rows)
        header = [r for r in rows if 540 < r['box'][1] < 585]
        hand_count = None
        for r in header:
            if r['box'][0] < 450:
                match = re.search(r'(\d+)\s*张', r['text'])
                if match:
                    hand_count = int(match[1])
        counts, landlord = {}, None
        for r in rows:
            x, y, _, _ = r['box']
            seat = 'left' if x < 600 else 'right'
            if 350 < y < 420:
                match = re.search(r'手牌\s*(\d+)\s*张', r['text'])
                if match:
                    counts[seat] = int(match[1])
                if '地主' in r['text']:
                    landlord = seat
            if 540 < y < 585 and x < 450 and '地主' in r['text']:
                landlord = 'self'
        buttons = []
        for r in rows:
            x, y, w, h = r['box']
            if 720 < y < 765 and x > 800:
                label = r['text'].replace(' ', '')
                if label in ('不出', '出牌', '不叫', '叫1分', '叫2分', '叫3分', '再来一局'):
                    buttons.append({'label': label, 'x': x+w/2, 'y': y+h/2})
        log = self.region(image, (100, 1120, 1330, 1400))
        grouped = []
        for r in sorted(log, key=lambda r: r['box'][1]):
            # The eighth row is clipped by the visible scroll container.
            if r['box'][1] >= 1360:
                continue
            y = r['box'][1]
            group = next((g for g in grouped if abs(g[0]-y) < 8), None)
            if group is None:
                group = [y, []]
                grouped.append(group)
            group[1].append(r)
        history = []
        for row_y, group in grouped:
            line = ' '.join(r['text'] for r in sorted(group, key=lambda r: r['box'][0]))
            match = re.match(r'\s*(\d+)\s+(.+)', line)
            if match:
                if not re.match(r'(你|东篱|西窗|地主|农民|三家)', match[2]):
                    # Re-read the actual row at a tighter scale; never infer the actor.
                    retry = self.region(image, (100, round(row_y)-12, 500, round(row_y)+23))
                    line = ' '.join(r['text'] for r in sorted(retry, key=lambda r: r['box'][0]))
                    revised = re.match(r'\s*(\d+)\s+(.+)', line)
                    if revised and revised[1] == match[1]:
                        match = revised
                history.append((int(match[1]), match[2]))
        return dict(hand_count=hand_count, counts=counts, landlord=landlord,
                    my_turn='轮到你出牌' in text.replace(' ', ''),
                    bidding='轮到你叫分' in text.replace(' ', ''),
                    finished='本局已结束' in text, buttons=buttons, history=sorted(history), text=text)

    def hand(self, image, count):
        from PIL import Image, ImageDraw, ImageFont, ImageChops, ImageStat
        if type(count) is not int or not 1 <= count <= 20:
            raise ValueError('Unreadable hand count')
        # Match the visible printed glyphs; no card ranks come from the game.
        font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Georgia Bold.ttf', 100)
        def normalize(im):
            mask = im.convert('L').point(lambda p: 255 if p < 180 else 0)
            box = mask.getbbox()
            if box is None:
                raise ValueError('Empty card glyph')
            return mask.crop(box).resize((32, 48))
        templates = {}
        for rank in RANKS[:-2]:
            tile = Image.new('RGB', (200, 160), 'white')
            draw = ImageDraw.Draw(tile)
            x = 10
            for char in rank:
                draw.text((x, 0), char, font=font, fill='black')
                x += font.getlength(char) - 4
            templates[rank] = normalize(tile)
        joker_font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Songti.ttc', 100, index=1)
        joker_templates = {}
        for rank, char in [('SJ', '小'), ('BJ', '大')]:
            tile = Image.new('RGB', (200, 160), 'white')
            ImageDraw.Draw(tile).text((10, 0), char, font=joker_font, fill='black')
            joker_templates[rank] = normalize(tile)
        start = (1440 - (76 + 41 * (count - 1))) / 2
        result = []
        for i in range(count):
            x = start + 41*i
            crop = image.crop((round((x+7)*2), 1212, round((x+38)*2), 1275))
            glyph = normalize(crop)
            scores = sorted((ImageStat.Stat(ImageChops.difference(glyph, tile)).mean[0]/255, rank)
                            for rank, tile in templates.items())
            if scores[0][0] < 0.15 and scores[1][0] - scores[0][0] > 0.06:
                label = scores[0][1]
            else:
                first_char = normalize(image.crop((round((x+7)*2), 1214, round((x+29)*2), 1248)))
                joker_scores = sorted((ImageStat.Stat(ImageChops.difference(first_char, tile)).mean[0]/255, rank)
                                      for rank, tile in joker_templates.items())
                if joker_scores[0][0] < 0.15 and joker_scores[1][0] - joker_scores[0][0] > 0.15:
                    result.append({'rank': joker_scores[0][1], 'x': x+18, 'y': 650, 'id': str(i)})
                    continue
                padded = Image.new('RGB', (286, 310), 'white')
                padded.paste(crop.resize((186, 210)), (50, 50))
                label = ''.join(r['text'] for r in self.ocr(padded, fast=True)).strip()
                if label not in RANKS:
                    label = ''.join(r['text'] for r in self.ocr(padded)).strip()
                if label not in RANKS:
                    crop = image.crop((round((x+2)*2), 1200, round((x+32)*2), 1338))
                    label = ''.join(r['text'] for r in self.ocr(crop)).replace(' ', '')
                    label = {'大王': 'BJ', '小王': 'SJ'}.get(label, label)
            if label not in RANKS:
                raise ValueError('Unreadable hand card %d: %r' % (i, label))
            result.append({'rank': label, 'x': x+18, 'y': 650, 'id': str(i)})
        if tuple(r['rank'] for r in result) != ordered(r['rank'] for r in result):
            raise ValueError('Hand OCR violates displayed rank ordering')
        return result
