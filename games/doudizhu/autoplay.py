"""Switch the running local table into autoplay (or return control to the player)."""
import argparse
import json
from urllib.request import Request, urlopen
from urllib.error import URLError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--off', action='store_true', help='关闭自动对局')
    parser.add_argument('--delay', type=float, help='每步间隔 0.1–5 秒')
    args = parser.parse_args()
    if args.delay is not None and not 0.1 <= args.delay <= 5:
        parser.error('--delay 必须在 0.1 到 5 秒之间')
    def send(data):
        request = Request('http://127.0.0.1:%d/api/command' % args.port,
                          json.dumps(data).encode(), {'Content-Type': 'application/json'})
        with urlopen(request, timeout=10) as response:
            return json.load(response)
    try:
        if args.delay is not None:
            send({'command': 'speed', 'delay': args.delay})
        state = send({'command': 'mode', 'auto': not args.off})
        print('自动对局已%s · 第 %s 局 · http://127.0.0.1:%s' %
              ('关闭' if args.off else '开启', state['round'], args.port))
    except URLError as exc:
        parser.exit(1, '无法控制牌桌，请先启动 server.py：%s\n' % exc)


if __name__ == '__main__':
    main()
