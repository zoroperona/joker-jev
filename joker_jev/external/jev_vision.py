"""Image-based rank recognition; each Choice refers to one attached card crop."""
from io import BytesIO
from joker_jev.agents.images import png_data_url
from .screen import ScreenReader
from .state import RANKS, ordered
from .ui import UIMapper


class JevScreenReader(ScreenReader):
    """Keep the current table's OCR layout; let Jev read the actual hand pixels.

    No local rank labels are sent to Jev. Errors never fall back to local matching.
    """
    def __init__(self, backend):
        super().__init__()
        self.backend = backend
        self.last_recognition = []

    def hand(self, image, count):
        if image.size != (2880, 3200) or type(count) is not int or not 1 <= count <= 20:
            raise ValueError('Invalid screenshot profile or hand count')
        self.last_recognition = []
        start = (1440 - (76 + 41 * (count - 1))) / 2
        result = []
        # Each decision sees exactly one card. Multi-image ordinal references
        # produced confident cross-card substitutions in the recorded benchmark.
        for i in range(count):
            x = start + 41*i
            crop = image.crop((round((x+3)*2), 1200, round((x+39)*2), 1340))
            stream = BytesIO()
            crop.save(stream, format='PNG')
            key = 'card_%d' % i
            questions = {key: dict(type='choice', instructions=(
                'Read ONLY the only card in the attached image. Identify the rank printed in '
                'the upper-left corner. Ignore suit. SJ is 小王 (small joker); BJ is 大王 (big joker). '
                'Choose unknown if unreadable.'),
                criteria={**{r: r for r in RANKS}, 'unknown': 'Unreadable card'})}
            response = self.backend.evaluate(
                {'task': 'Read printed card ranks from image pixels. Do not infer a play.'},
                questions, images=[png_data_url(stream.getvalue())])
            self.last_recognition.append(response)
            answer = response['answers'][key]
            UIMapper.validate(answer, questions[key]['criteria'])
            if answer['choice'] == 'unknown':
                raise ValueError('Jev could not recognize card %d' % i)
            result.append({'rank': answer['choice'], 'id': str(i), 'x': x+18, 'y': 650})
        if tuple(t['rank'] for t in result) != ordered(t['rank'] for t in result):
            raise ValueError('Jev hand recognition violates displayed rank ordering')
        return result
