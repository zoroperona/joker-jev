"""Run a separate, screenshot-only player against the existing web table."""
import argparse
from collections import Counter
from dataclasses import asdict
from io import BytesIO
import json
from pathlib import Path
import re
import time

from .screen import NAMES, ScreenReader, parse_cards
from .state import Play, PublicState
from .ui import UIMapper


def ingest(state, history, last_row):
    """Visible log row numbers detect missed frames, including two fast opponent turns."""
    rows = [(n, text) for n, text in history if n > last_row]
    for n, text in rows:
        if n != last_row + 1:
            raise ValueError('Visible history gap: expected row %d, got %d' % (last_row+1, n))
        match = re.match(r'(你|东篱|西窗)\s*[·•・.．]\s*(.+)', text)
        if match is None:
            match = re.match(r'(你|东篱|西窗)\s+(.+)', text)
        if match:
            seat, body = NAMES[match[1]], match[2].strip()
            cards = () if body == '不出' else parse_cards(body)
            state.apply(Play(len(state.history)+1, seat, cards, state.remaining[seat]-len(cards)))
        elif not ('获得自由出牌权' in text or '获胜' in text):
            raise ValueError('Unrecognized visible event: ' + text)
        last_row = n
    return last_row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8877')
    parser.add_argument('--models', type=Path, default=Path('games/doudizhu/models'))
    parser.add_argument('--env-file', default='.env')
    parser.add_argument('--ui-policy', choices=('jev', 'jev-text', 'local'), default='jev',
                        help='jev sends the screenshot; jev-text explicitly uses OCR text only')
    parser.add_argument('--vision', choices=('local', 'jev'), default='local',
                        help='Hand rank recognition: local glyphs or Jev image Choice; layout still uses OCR')
    parser.add_argument('--execute', action='store_true', help='Click the fixed model action; default is observe/recommend')
    parser.add_argument('--bid', type=int, choices=range(4), help='Explicit fixed opening bid; DouZero has no bidding weights')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--timeout', type=float, default=300)
    parser.add_argument('--output', type=Path, required=True, help='New run directory for screenshots and structured observations')
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    args.output.mkdir(parents=True, exist_ok=False)
    from PIL import Image
    from playwright.sync_api import sync_playwright
    from .model import DouZeroPolicy
    from joker_jev.agents.typesafe import TypeSafeBackend
    backend = TypeSafeBackend.from_env(args.env_file) if args.ui_policy != 'local' or args.vision == 'jev' else None
    if args.vision == 'jev':
        from .jev_vision import JevScreenReader
        reader = JevScreenReader(backend)
    else:
        reader = ScreenReader()
    model = DouZeroPolicy(args.models)
    mapper = UIMapper(backend if args.ui_policy != 'local' else None, require_image=args.ui_policy == 'jev')
    state, last_row, pending = None, 0, None
    submitted_at = 0.0
    bid_frame = None
    deadline = time.monotonic() + args.timeout
    with (args.output / 'events.jsonl').open('w') as log, sync_playwright() as pw:
        log.write(json.dumps({'session': {'vision': args.vision, 'ui_policy': args.ui_policy,
                                         'model': backend.model if backend else None}}, ensure_ascii=False)+'\n')
        def read_hand(image, count):
            try:
                return reader.hand(image, count)
            finally:
                if args.vision == 'jev':
                    log.write(json.dumps({'hand_recognition': reader.last_recognition}, ensure_ascii=False)+'\n')
                    log.flush()

        browser = pw.chromium.launch(headless=args.headless)
        page = browser.new_page(viewport={'width': 1440, 'height': 1600}, device_scale_factor=2)
        page.goto(args.url)
        try:
            frame = 0
            while time.monotonic() < deadline:
                page.wait_for_timeout(400)
                png = page.screenshot()
                frame += 1
                (args.output / ('%05d.png' % frame)).write_bytes(png)
                image = Image.open(BytesIO(png))
                targets = None
                visible = reader.read(image)
                log.write(json.dumps({'frame': frame, 'visible': visible}, ensure_ascii=False)+'\n'); log.flush()
                if visible['bidding']:
                    if bid_frame == visible:
                        if time.monotonic() - submitted_at < 5:
                            continue
                        raise ValueError('Bid was not confirmed; stopped without retrying')
                    if not args.execute or args.bid is None:
                        print('请在牌桌完成叫分，或使用 --execute --bid 3 指定固定叫分。', flush=True)
                        continue
                    button = '不叫' if args.bid == 0 else '叫%d分' % args.bid
                    plan = mapper.plan((), [], visible['buttons'], button,
                                       screenshot=png if args.ui_policy == 'jev' else None)
                    if page.screenshot() != png:
                        raise ValueError('Table changed during bid mapping; no clicks sent')
                    for target in plan:
                        page.mouse.click(target['x'], target['y'])
                    submitted_at, bid_frame = time.monotonic(), visible
                    continue
                if state is None:
                    starts = [(n, t) for n, t in visible['history'] if '成为地主' in t]
                    if not starts or visible['landlord'] is None:
                        if visible['finished']:
                            raise ValueError('Start a new table before attaching')
                        continue
                    # Own hand is still complete: reject joining after any self play.
                    last_row = starts[-1][0]
                    if any(n > last_row and re.match(r'你\s*[·•・.．]', t) for n,t in visible['history']):
                        raise ValueError('Mid-game attachment is unsupported; start a new round')
                    targets = read_hand(image, visible['hand_count'])
                    state = PublicState([t['rank'] for t in targets], visible['landlord'])
                before = len(state.history)
                last_row = ingest(state, visible['history'], last_row)
                for event in state.history[before:]:
                    log.write(json.dumps({'play': asdict(event), 'count': event.count}, ensure_ascii=False)+'\n')
                    if event.seat == 'self' and pending is not None:
                        if Counter(event.cards) != Counter(pending):
                            raise ValueError('Screen confirmation differs from submitted action')
                        pending = None
                log.flush()
                if state.finished:
                    log.write(json.dumps({'status': 'finished', 'plays': len(state.history),
                                          'remaining': state.remaining}, ensure_ascii=False)+'\n'); log.flush()
                    print('对局结束：从截图确认 %d 手出牌/过牌。' % len(state.history), flush=True)
                    return
                if visible['finished']:
                    raise ValueError('Result screen appeared before all plays could be reconstructed')
                if visible['counts'] != {s: state.remaining[s] for s in ('left', 'right')}:
                    raise ValueError('OCR remaining counts disagree with visible history')
                if visible['hand_count'] != len(state.hand):
                    raise ValueError('OCR hand count disagrees with tracked state')
                if pending is not None:
                    if time.monotonic() - submitted_at < 5:
                        continue
                    raise ValueError('Submitted action was not confirmed; stopped without retrying clicks')
                if not visible['my_turn']:
                    continue
                if targets is None:
                    targets = read_hand(image, visible['hand_count'])
                if Counter(t['rank'] for t in targets) != Counter(state.hand):
                    raise ValueError('Hand OCR disagrees with tracked state')
                cards = model.choose(state)
                print('DouZero:', ' '.join(cards) or '不出', flush=True)
                log.write(json.dumps({'decision': list(cards), 'turn': len(state.history)}, ensure_ascii=False)+'\n'); log.flush()
                if not args.execute:
                    return
                plan = mapper.plan(cards, targets, visible['buttons'],
                                   screenshot=png if args.ui_policy == 'jev' else None)
                log.write(json.dumps({'ui_mapping': mapper.last_response, 'click_plan': plan}, ensure_ascii=False)+'\n'); log.flush()
                # Detect a restarted/changed table while OCR, model or Jev was running.
                fresh = Image.open(BytesIO(page.screenshot()))
                if fresh.crop((200, 440, 2680, 1580)).tobytes() != image.crop((200, 440, 2680, 1580)).tobytes():
                    raise ValueError('Table changed during inference; no clicks sent')
                pending, submitted_at = cards, time.monotonic()
                for target in plan:
                    page.mouse.click(target['x'], target['y'])
                page.mouse.move(50, 100)
            raise TimeoutError('External session timed out')
        except Exception as exc:
            log.write(json.dumps({'status': 'stopped', 'error_type': type(exc).__name__,
                                  'message': str(exc), 'pending': pending, 'ui_mapping': mapper.last_response}, ensure_ascii=False)+'\n')
            log.flush()
            raise
        finally:
            browser.close()


if __name__ == '__main__':
    main()
