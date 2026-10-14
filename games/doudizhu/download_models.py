"""Download the frozen DouZero ADP baseline released with PerfectDou; never trains."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent / 'models'


def main():
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    for role, info in manifest.items():
        target = ROOT / (role + '.ckpt')
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == info['sha256']:
            print(role + ': verified')
            continue
        with urlopen(info['url'], timeout=90) as response:
            data = response.read()
        if len(data) != info['size'] or hashlib.sha256(data).hexdigest() != info['sha256']:
            raise RuntimeError('模型校验失败：' + role)
        temp = target.with_suffix('.tmp')
        temp.write_bytes(data)
        temp.replace(target)
        print(role + ': downloaded and verified')


if __name__ == '__main__':
    main()
