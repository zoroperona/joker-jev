"""Actual rendered screenshot regressions; optional macOS vision dependencies."""
import importlib.util
from pathlib import Path
import shutil
import sys
import unittest

from joker_jev.external.screen import parse_cards


class CardTextTests(unittest.TestCase):
    def test_compact_ocr_and_jokers(self):
        self.assertEqual(parse_cards('10JQKA'), ('10','J','Q','K','A'))
        self.assertEqual(parse_cards('小王 大王'), ('SJ','BJ'))
        for text in ('100', 'Q0', '未知', '1'):
            with self.assertRaises(ValueError):
                parse_cards(text)


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swiftc') and importlib.util.find_spec('PIL'),
                     'Requires macOS Vision, Swift and Pillow')
class ScreenshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from joker_jev.external.screen import ScreenReader
        cls.reader = ScreenReader()

    def image(self, name):
        from PIL import Image
        with Image.open(Path(__file__).parent / 'fixtures' / 'external' / name) as source:
            return source.copy()

    def test_repeated_ranks_from_pixels(self):
        image = self.image('opening.png')
        visible = self.reader.read(image)
        self.assertEqual(visible['hand_count'],17)
        self.assertEqual(visible['counts'],{'left':17, 'right':17})
        self.assertTrue(visible['bidding'])
        targets = self.reader.hand(image,17)
        self.assertEqual([t['rank'] for t in targets],
                         '3 5 5 7 7 8 8 8 10 10 10 10 J Q A 2 2'.split())

    def test_vertical_jokers(self):
        image = self.image('jokers.png')
        self.assertEqual(self.reader.read(image)['landlord'],'self')
        self.assertEqual([t['rank'] for t in self.reader.hand(image,20)],
                         '3 3 4 5 6 6 7 7 7 8 8 9 J Q K A A 2 SJ BJ'.split())

    def test_row_crop_recovers_player_name(self):
        visible = self.reader.read(self.image('missing-actor.png'))
        self.assertEqual(visible['history'][-1], (11, '你•8910JQ'))

    def test_clipped_history_row_is_excluded(self):
        visible = self.reader.read(self.image('clipped-log.png'))
        self.assertEqual([n for n,_ in visible['history']],list(range(9,16)))


if __name__ == '__main__':
    unittest.main()
