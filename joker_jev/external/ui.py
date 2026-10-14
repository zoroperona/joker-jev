"""Ground fixed actions in UI targets, independently checking pixels in image mode."""
from collections import Counter
from io import BytesIO
from joker_jev.agents.images import png_data_url


def table_image(screenshot):
    """Keep the entire table at CSS resolution, excluding unrelated page chrome.

    The original frame stays in the run log; model coordinates are explicitly
    translated by the origin metadata below. No pixels are synthesized.
    """
    from PIL import Image
    with Image.open(BytesIO(screenshot)) as image:
        if image.size != (2880, 3200):
            raise ValueError('Unexpected screenshot dimensions for UI grounding')
        table = image.crop((200, 440, 2680, 1580)).resize((1240, 570), Image.Resampling.LANCZOS)
        stream = BytesIO()
        table.save(stream, format='PNG')
        return png_data_url(stream.getvalue())


class UIMapper:
    def __init__(self, backend=None, *, require_image=False):
        self.backend = backend
        self.require_image = require_image
        self.last_response = None

    def plan(self, cards, targets, buttons, button=None, *, screenshot=None):
        self.last_response = None
        if self.require_image and (not self.backend or not screenshot):
            raise ValueError('Image-based UI mapping requires a backend and a current screenshot')
        desired = button or ('出牌' if cards else '不出')
        questions = {}
        expected = []
        used = set()
        for rank in cards:
            target = next((t for t in targets if t['rank'] == rank and t['id'] not in used), None)
            if target is None:
                raise ValueError('Model card missing from screenshot')
            used.add(target['id'])
            expected.append(target)
        matching = [b for b in buttons if b['label'] == desired]
        if len(matching) != 1:
            raise ValueError('Required button not recognized: ' + desired)
        if self.backend:
            # One question per rank group. Repeated rank occurrences are grounded
            # together, so independent questions cannot select the same card twice.
            groups = {}
            for target in targets:
                groups.setdefault(target['rank'], []).append(target)
            for rank, count in Counter(cards).items():
                questions['rank_' + rank] = dict(
                    type='choice', instructions=(
                        'Locate exactly %d card(s) printed with rank %s. Select the UI group '
                        'whose printed_rank is %s. The play is fixed; do not evaluate strategy.'
                        % (count, rank, rank)),
                    criteria={r: {'printed_rank': r, 'count': count, 'elements': items[:count]}
                              for r, items in groups.items() if len(items) >= count})
            questions['button'] = dict(type='choice', instructions='Locate the button labeled exactly ' + desired,
                                       criteria={str(i): b for i, b in enumerate(buttons)})
            state = {'task': 'Ground a fixed action in screenshot OCR elements',
                     'required_cards': list(cards), 'required_button': desired,
                     'proposed_click_plan': expected + matching}
            if screenshot:
                self._verify_pixels(screenshot, expected, matching[0], bool(cards))
                return expected + matching
            response = self.backend.evaluate(state, questions)
            self.last_response = response
            for rank in Counter(cards):
                answer = response['answers']['rank_' + rank]
                self.validate(answer, questions['rank_' + rank]['criteria'])
                if answer['choice'] != rank:
                    raise ValueError('Jev UI mapping changed the prescribed card group')
            answer = response['answers']['button']
            self.validate(answer, questions['button']['criteria'])
            if buttons[int(answer['choice'])]['label'] != desired:
                raise ValueError('Jev UI mapping differs from model decision')
        return expected + matching

    def _verify_pixels(self, screenshot, targets, button, playing):
        """Classify pixels independently; expected ranks are never model inputs."""
        from PIL import Image
        from .state import RANKS
        self.last_response = {'answers': {}, 'checks': []}

        def check(key, instructions, criteria, pixels, expected):
            response = self.backend.evaluate(
                {'task': 'Read visible UI pixels only. Do not infer strategy.'},
                {key: dict(type='choice', instructions=instructions, criteria=criteria)},
                images=[pixels])
            self.last_response['checks'].append(response)
            self.last_response['answers'][key] = response['answers'][key]
            answer = response['answers'][key]
            self.validate(answer, criteria)
            if answer['choice'] != expected:
                raise ValueError('Jev rejected screenshot target: ' + key)

        check('turn', 'Read the turn indicator. Whose turn does the displayed text indicate?',
              {'self': '轮到你出牌 or 轮到你叫分', 'other': 'Another player is acting',
               'unknown': 'No readable turn indicator'}, table_image(screenshot), 'self')
        with Image.open(BytesIO(screenshot)) as image:
            def crop(box):
                stream = BytesIO()
                image.crop(tuple(round(v*2) for v in box)).save(stream, format='PNG')
                return png_data_url(stream.getvalue())

            x, y = button['x'], button['y']
            check('button', 'Read the label on the central button in this crop. '
                  'Choose unknown if it is unreadable.',
                  {label: label for label in ('出牌', '不出', '不叫', '叫1分', '叫2分', '叫3分', 'unknown')},
                  crop((x-42, y-20, x+42, y+20)), button['label'])
            if not playing:
                from .buttons import button_style
                evidence = button_style(screenshot, button)
                self.last_response['button_style'] = evidence
                if evidence['status'] != 'enabled':
                    raise ValueError('Button styling is disabled or unknown')
            for i, target in enumerate(targets):
                x = target['x']
                if target['y'] != 650:
                    raise ValueError('Unexpected card target position')
                check('card_%d' % i,
                      'Read the rank printed in the upper-left corner of the only card. Ignore suit. '
                      'SJ means 小王; BJ means 大王. Choose unknown if unreadable.',
                      {**{r: r for r in RANKS}, 'unknown': 'Unreadable'},
                      crop((x-15, 600, x+21, 670)), target['rank'])

    @staticmethod
    def validate(answer, criteria):
        confidence = answer.get('confidence')
        if (answer.get('type') != 'choice' or answer.get('choice') not in criteria
                or isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                or not 0.8 <= confidence <= 1):
            raise ValueError('Invalid or low-confidence Jev UI mapping')
