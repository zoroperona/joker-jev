import importlib.util
import unittest
from unittest.mock import Mock, patch

from joker_jev.external.jev_vision import JevScreenReader


@unittest.skipUnless(importlib.util.find_spec('PIL'), 'Pillow required')
class JevVisionTests(unittest.TestCase):
    def reader(self, backend):
        with patch('joker_jev.external.jev_vision.ScreenReader.__init__',return_value=None):
            return JevScreenReader(backend)

    def test_each_question_sees_one_card_without_ordinal_hints(self):
        from PIL import Image
        backend = Mock()
        ranks = ['3','3','4','SJ','BJ']
        def evaluate(state, questions, *, images):
            self.assertEqual(len(images),1)
            self.assertEqual(len(questions),1)
            self.assertNotIn('image_order',state)
            self.assertEqual(set(state), {'task'})
            return {'answers':{key:{'type':'choice','choice':ranks[int(key[5:])], 'confidence':1}
                               for key in questions}}
        backend.evaluate.side_effect=evaluate
        reader=self.reader(backend)
        targets=reader.hand(Image.new('RGB',(2880,3200),'white'),5)
        self.assertEqual([t['rank'] for t in targets],ranks)
        self.assertEqual(backend.evaluate.call_count,5)
        self.assertEqual(len({t['id'] for t in targets}),5)

    def test_ui_crop_keeps_coordinate_targets_inside_the_table(self):
        from PIL import Image
        from io import BytesIO
        import base64
        from joker_jev.external.ui import table_image
        image = Image.new('RGB', (2880,3200), 'white')
        # Known target at CSS (500,400), surrounded by a solid red patch.
        from PIL import ImageDraw
        ImageDraw.Draw(image).rectangle((980,780,1020,820),fill='red')
        stream=BytesIO();image.save(stream,format='PNG')
        raw=base64.b64decode(table_image(stream.getvalue()).split(',',1)[1])
        with Image.open(BytesIO(raw)) as crop:
            self.assertEqual(crop.size,(1240,570))
            self.assertEqual(crop.getpixel((500-100,400-220)),(255,0,0))

    def test_unknown_and_backend_errors_never_fall_back(self):
        from PIL import Image
        backend=Mock()
        reader=self.reader(backend)
        image=Image.new('RGB',(2880,3200),'white')
        backend.evaluate.return_value={'answers':{'card_0':{'type':'choice','choice':'unknown','confidence':1}}}
        with self.assertRaisesRegex(ValueError,'could not recognize'):
            reader.hand(image,1)
        backend.evaluate.side_effect=RuntimeError('Image endpoint rejected request')
        with self.assertRaisesRegex(RuntimeError,'rejected'):
            reader.hand(image,1)


if __name__ == '__main__':
    unittest.main()
