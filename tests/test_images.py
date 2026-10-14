import base64
import io
import json
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from joker_jev.agents.images import validate_images, png_data_url, MAX_IMAGE_BYTES
from joker_jev.agents.typesafe import TypeSafeBackend, TypeSafeError
from joker_jev.external.ui import UIMapper


class ImageProtocolTests(unittest.TestCase):
    def test_mixed_images_preserve_order_and_representation(self):
        backend = TypeSafeBackend('test-key')
        backend._opener = Mock()
        backend._opener.open.return_value = io.BytesIO(b'{"answers":{"rank":{}}}')
        images = [png_data_url(b'png bytes'), {'mediaType':'image/webp', 'base64':base64.b64encode(b'webp').decode()}]
        backend.evaluate({'task':'read pixels'}, {'rank':{}}, images=images)
        payload = json.loads(backend._opener.open.call_args.args[0].data)
        self.assertEqual(payload['images'],images)
        self.assertNotIn('images',payload['state'])

    def test_reject_invalid_encoding_formats_and_limits_before_network(self):
        backend = TypeSafeBackend('test-key')
        backend._opener = Mock()
        invalid = [['https://example.com/a.png'], ['data:image/gif;base64,YQ=='],
                   ['data:image/png;base64,YQ'], ['data:image/png;base64,YR=='],
                   ['data:image/png;base64,Y Q=='], ['data:image/png;base64,'],
                   [{'mediaType':'image/png','base64':'YQ==','extra':True}],
                   [png_data_url(b'a')]*5, [png_data_url(b'a'*(MAX_IMAGE_BYTES+1))],
                   [png_data_url(b'a'*MAX_IMAGE_BYTES)]*3]
        for images in invalid:
            with self.subTest(images_type=type(images[0]).__name__), self.assertRaises(ValueError):
                backend.evaluate({}, {'q':{}}, images=images)
        backend._opener.open.assert_not_called()
        validate_images([png_data_url(b'a'*MAX_IMAGE_BYTES)]*2)

    def test_full_request_limit_and_no_image_downgrade(self):
        backend = TypeSafeBackend('test-key')
        backend._opener = Mock()
        with self.assertRaisesRegex(ValueError,'13 MiB'):
            backend.evaluate({'large':'x'*(13*1024*1024)}, {'q':{}},images=[png_data_url(b'x')])
        backend._opener.open.assert_not_called()
        backend._opener.open.side_effect = HTTPError(backend.endpoint,400,'bad image',{},io.BytesIO())
        with self.assertRaises(TypeSafeError):
            backend.evaluate({}, {'q':{}},images=[png_data_url(b'x')])
        self.assertEqual(backend._opener.open.call_count,1)
        self.assertIsNone(backend.last_response)

    def test_image_ui_requires_visual_acceptance(self):
        backend = Mock()
        mapper = UIMapper(backend,require_image=True)
        buttons = [{'label':'不出','x':10,'y':20}]
        with self.assertRaises(ValueError):
            mapper.plan((),[],buttons)
        backend.evaluate.assert_not_called()
        backend.evaluate.return_value = {'answers':{
            'turn': {'type':'choice','choice':'other','confidence':1}}}
        with patch('joker_jev.external.ui.table_image', return_value=png_data_url(b'pixels')):
            with self.assertRaisesRegex(ValueError, 'rejected.*turn'):
                mapper.plan((), [], buttons, screenshot=b'pixels')
        self.assertEqual(backend.evaluate.call_count, 1)
        self.assertEqual(backend.evaluate.call_args.kwargs['images'], [png_data_url(b'pixels')])
        self.assertNotIn('required_cards', backend.evaluate.call_args.args[0])

    def test_image_ui_reads_card_without_expected_rank(self):
        from PIL import Image
        stream = io.BytesIO()
        Image.new('RGB', (2880, 3200)).save(stream, format='PNG')
        backend = Mock()
        def evaluate(state, questions, **kwargs):
            key = next(iter(questions))
            choice = {'turn':'self', 'button':'出牌', 'card_0':'4'}[key]
            return {'answers': {key: {'type':'choice','choice':choice,'confidence':1}}}
        backend.evaluate.side_effect = evaluate
        mapper = UIMapper(backend, require_image=True)
        with self.assertRaisesRegex(ValueError, 'rejected.*card_0'):
            mapper.plan(('3',), [{'id':'0','rank':'3','x':400,'y':650}],
                        [{'label':'出牌','x':1253,'y':741}], screenshot=stream.getvalue())
        state, questions = backend.evaluate.call_args.args
        self.assertNotIn('required_cards', state)
        self.assertEqual(set(questions['card_0']['criteria']),
                         set(('3','4','5','6','7','8','9','10','J','Q','K','A','2','SJ','BJ','unknown')))

    def test_image_ui_disabled_button_stops(self):
        from PIL import Image
        stream = io.BytesIO()
        Image.new('RGB', (2880, 3200)).save(stream, format='PNG')
        backend = Mock()
        def evaluate(state, questions, **kwargs):
            key = next(iter(questions))
            choice = {'turn':'self', 'button':'不出', 'enabled':'disabled'}[key]
            return {'answers': {key: {'type':'choice','choice':choice,'confidence':1}}}
        backend.evaluate.side_effect = evaluate
        mapper = UIMapper(backend, require_image=True)
        with self.assertRaisesRegex(ValueError, 'styling is disabled or unknown'):
            mapper.plan((), [], [{'label':'不出','x':1081,'y':741}], screenshot=stream.getvalue())
        self.assertEqual(len(mapper.last_response['checks']), 2)


if __name__ == '__main__':
    unittest.main()
