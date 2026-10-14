import json
import unittest
from io import BytesIO
from pathlib import Path
from PIL import Image
from joker_jev.external.buttons import button_style


class ButtonStyleTests(unittest.TestCase):
    def test_manually_labelled_button_crops(self):
        root = Path(__file__).parent/'fixtures/buttons'
        for row in json.loads((root/'manifest.json').read_text()):
            with self.subTest(sample=row['file']):
                image = Image.new('RGB', (2880, 3200))
                with Image.open(root/row['file']) as crop:
                    image.paste(crop, row['box'][:2])
                stream = BytesIO()
                image.save(stream, format='PNG')
                self.assertEqual(button_style(stream.getvalue(), row['button'])['status'], row['expected'])

    def test_unrecognized_or_obscured_palette_rejected(self):
        for color in ('black', 'white', '#204f41', 'red'):
            with self.subTest(color=color):
                stream = BytesIO()
                Image.new('RGB', (2880, 3200), color).save(stream, format='PNG')
                self.assertEqual(button_style(stream.getvalue(),
                    {'label':'不出','x':1081,'y':741})['status'], 'unknown')

    def test_mapper_uses_pixel_evidence_without_enabled_model_question(self):
        from unittest.mock import Mock
        from joker_jev.external.ui import UIMapper
        root = Path(__file__).parent/'fixtures/buttons'
        rows = json.loads((root/'manifest.json').read_text())
        for index in (0, 4):
            row = rows[index]
            with self.subTest(expected=row['expected']):
                image = Image.new('RGB', (2880, 3200))
                with Image.open(root/row['file']) as crop:
                    image.paste(crop, row['box'][:2])
                stream = BytesIO()
                image.save(stream, format='PNG')
                def evaluate(state, questions, **kwargs):
                    key = next(iter(questions))
                    choice = {'turn':'self', 'button':'不出'}[key]
                    return {'answers': {key: {'type':'choice', 'choice':choice, 'confidence':1}}}
                backend = Mock()
                backend.evaluate.side_effect = evaluate
                mapper = UIMapper(backend, require_image=True)
                if row['expected'] == 'enabled':
                    self.assertEqual(mapper.plan((), [], [row['button']], screenshot=stream.getvalue()),
                                     [row['button']])
                else:
                    with self.assertRaisesRegex(ValueError, 'styling is disabled or unknown'):
                        mapper.plan((), [], [row['button']], screenshot=stream.getvalue())
                self.assertEqual(mapper.last_response['button_style']['status'], row['expected'])
                self.assertEqual(backend.evaluate.call_count, 2)
