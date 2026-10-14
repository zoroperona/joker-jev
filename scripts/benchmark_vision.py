"""Compare visual input layouts on fixed, manually labelled screen fixtures.

Run from repository root with the external player's Python environment.
Ground-truth labels are used only for scoring, never sent to the model.
"""
import argparse
import json
from io import BytesIO
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from joker_jev.agents.typesafe import TypeSafeBackend
from joker_jev.agents.images import png_data_url
from joker_jev.external.state import RANKS

FIXTURES = {
    'opening': '3 5 5 7 7 8 8 8 10 10 10 10 J Q A 2 2'.split(),
    'jokers': '3 3 4 5 6 6 7 7 7 8 8 9 J Q K A A 2 SJ BJ'.split(),
}


def image_url(image):
    stream = BytesIO()
    image.save(stream, format='PNG')
    return png_data_url(stream.getvalue())


def crops(image, count):
    start = (1440 - (76 + 41 * (count - 1))) / 2
    return [image.crop((round((start + 41*i + 3)*2), 1200,
                        round((start + 41*i + 39)*2), 1340)) for i in range(count)]


def layout(tiles, mode):
    from PIL import Image, ImageDraw, ImageFont
    if mode in ('multi','original','no_order'):
        return [image_url(tile) for tile in tiles]
    if mode == 'single':
        return [image_url(tiles[0])]
    if mode == 'padded':
        canvas = Image.new('RGB', (256, 256), 'white')
        tile = tiles[0].copy()
        tile.thumbnail((192, 192))
        canvas.paste(tile, ((256-tile.width)//2, (256-tile.height)//2))
        return [image_url(canvas)]
    canvas = Image.new('RGB', (256*len(tiles), 320), 'white')
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 24)
    for i, tile in enumerate(tiles):
        draw.text((i*256+72, 10), 'CARD ' + str(i+1), font=font, fill='black')
        canvas.paste(tile.resize((108, 210)), (i*256+74, 70))
    return [image_url(canvas)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', default='.env.vision')
    parser.add_argument('--modes', default='original,multi,single,padded,atlas')
    parser.add_argument('--fixtures', default='opening,jokers')
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    backend = TypeSafeBackend.from_env(args.env_file)
    from PIL import Image
    summaries = []
    with (args.output/'calls.jsonl').open('w') as log:
        for mode in args.modes.split(','):
            if mode not in ('original','no_order','multi','single','padded','atlas'):
                raise ValueError('Unknown mode')
            outcomes = []
            for name in args.fixtures.split(','):
                truth = FIXTURES[name]
                with Image.open(Path('tests/fixtures/external')/(name+'.png')) as source:
                    tiles = crops(source,len(truth))
                count = min(args.limit,len(truth)) if args.limit else len(truth)
                width = 4 if mode in ('original','no_order','multi','atlas') else 1
                for offset in range(0,count,width):
                    batch = tiles[offset:min(count,offset+width)]
                    questions = {}
                    for local in range(len(batch)):
                        scope = ('attached image %d (one-based)' % (local+1) if mode=='multi' else
                                 'the panel labeled CARD %d in the attached image' % (local+1) if mode=='atlas' else
                                 'the only card in the attached image')
                        questions['card_%d' % local] = {
                            'type':'choice', 'instructions':'Read ONLY '+scope+'. Identify the rank printed in '
                            'the upper-left corner. Ignore suit. SJ is 小王 (small joker); BJ is 大王 (big joker). '
                            'Choose unknown if unreadable.',
                            'criteria':{**{r:r for r in RANKS},'unknown':'Unreadable card'}}
                    state = {'task':'Read printed card ranks from image pixels. Do not infer a play.'}
                    if mode in ('original','no_order'):
                        questions = {'card_%d' % (offset+local): {
                            'type':'choice', 'instructions':
                            'Read ONLY attached image %d (one-based). Identify the rank printed in '
                            'the upper-left corner. Ignore suit. SJ is 小王, BJ is 大王. '
                            'Choose unknown if the glyph is unreadable.' % (local+1),
                            'criteria':{**{r:r for r in RANKS},'unknown':'Unreadable card'}}
                            for local in range(len(batch))}
                        state = {'task':'Recognize card ranks from images, not game strategy',
                                 'image_order':list(questions)}
                    if mode == 'no_order':
                        state.pop('image_order')
                    started = time.monotonic()
                    row = {'mode':mode,'fixture':name,'offset':offset,'requested_model':backend.model}
                    try:
                        response = backend.evaluate(state,
                                                    questions,images=layout(batch,mode))
                        row['response'] = response
                        for local in range(len(batch)):
                            a=response['answers'][list(questions)[local]]
                            expected=truth[offset+local]
                            outcomes.append({'fixture':name,'index':offset+local,'expected':expected,
                                             'choice':a.get('choice'),'confidence':a.get('confidence'),
                                             'correct':a.get('choice')==expected})
                    except Exception as exc:
                        row['error'] = {'type':type(exc).__name__,'message':str(exc)}
                        outcomes.extend({'fixture':name,'index':offset+i,'expected':truth[offset+i],
                                         'choice':None,'confidence':0,'correct':False} for i in range(len(batch)))
                    row['seconds']=time.monotonic()-started
                    log.write(json.dumps(row,ensure_ascii=False)+'\n');log.flush()
                    print(mode,name,offset,'error' if 'error' in row else
                          [(x['choice'],round(x['confidence'],3)) for x in outcomes[-len(batch):]],flush=True)
            summary={'mode':mode,'correct':sum(x['correct'] for x in outcomes),'total':len(outcomes),
                     'wrong_high_confidence':sum(not x['correct'] and (x['confidence'] or 0)>=0.8 for x in outcomes),
                     'below_threshold':sum((x['confidence'] or 0)<0.8 for x in outcomes),'outcomes':outcomes}
            summaries.append(summary)
            (args.output/'summary.json').write_text(json.dumps(summaries,ensure_ascii=False,indent=2)+'\n')
            print('SUMMARY', {k:v for k,v in summary.items() if k!='outcomes'},flush=True)


if __name__ == '__main__':
    main()
