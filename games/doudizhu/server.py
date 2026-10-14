"""Local shared table with frozen DouZero opponents and selectable JEV inputs."""
import argparse
from copy import deepcopy
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from joker_jev.core.models import Observation, DecisionContext
from joker_jev.games.doudizhu.full.game import FullDoudizhuGame
from joker_jev.games.doudizhu.full.agents import FullSimpleAgent
from joker_jev.games.doudizhu.full.input_modes import InputModeJEVAgent, MODES
from joker_jev.agents.typesafe import TypeSafeBackend, TypeSafeError

ROOT = Path(__file__).resolve().parent


class Table:
    def __init__(self, auto=False, delay=0.9, seed=None, opponent=None, backend=None,
                 controller="human", jev_mode="minimal", trace_path=None):
        self.game = FullDoudizhuGame()
        if controller not in ('human', 'douzero', 'jev') or jev_mode not in MODES:
            raise ValueError('无效的控制方式或信息模式')
        if controller == 'jev' and backend is None:
            raise ValueError('JEV 尚未配置，请设置 TYPESAFE_API_KEY')
        self.agent = opponent or FullSimpleAgent()
        self.opponent_name = 'DouZero ADP' if opponent is not None else '简单 AI'
        self.backend = backend
        self.jev_agents = {mode: InputModeJEVAgent(backend, mode) for mode in MODES} if backend else {}
        self.controller, self.jev_mode = controller, jev_mode
        self.trace_path = Path(trace_path) if trace_path else None
        self.error = None
        self.thinking = False
        self.generation = 0
        self.lock = threading.RLock()
        self.auto, self.delay = auto, delay
        self.revision = 0
        self.round = 0
        self.totals = dict.fromkeys(('p0', 'p1', 'p2'), 0)
        self.new(seed)

    def new(self, seed=None):
        self.seed = secrets.randbelow(1000000) if seed is None else seed
        self.state = self.game.initial_state(self.seed)
        self.generation += 1
        self.error = None
        self.history = ()
        self.rewards = dict.fromkeys(self.totals, 0)
        self.round += 1
        self.revision += 1
        self.due = time.monotonic() + self.delay

    def context(self):
        player = self.game.current_player(self.state)
        view = self.game.view(self.state, player)
        obs = Observation('doudizhu', player, len(self.history), view.private, view.public,
                          self.game.legal_actions(self.state), self.history)
        return deepcopy(DecisionContext(self.game.rules, obs,
                        self.game.create_inference().infer(obs), self.totals[player]))

    def choice(self):
        return self.agent.decide(self.context()).action_id

    def log(self, row):
        if self.trace_path:
            self.trace_path.parent.mkdir(parents=True, exist_ok=True)
            with self.trace_path.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + '\n')

    def act(self, action_id):
        action = next((a for a in self.game.legal_actions(self.state) if a.id == action_id), None)
        if action is None:
            raise ValueError('这手牌不合法，请重新选择')
        result = self.game.step(self.state, action)
        self.state = result.state
        self.history += result.events
        self.rewards = result.rewards
        for p, score in result.rewards.items():
            self.totals[p] += score
        self.revision += 1
        self.due = time.monotonic() + (4 if self.state.phase == 'finished' else self.delay)

    def tick(self):
        # Snapshot under the lock, then run inference outside it so GET, stop and
        # restart remain responsive even during a slow network call.
        with self.lock:
            if self.error or self.thinking or time.monotonic() < self.due:
                return
            if self.state.phase == 'finished':
                if self.auto:
                    self.new()
                return
            if not (self.auto or self.state.actor != 0):
                return
            ctx = self.context()
            generation = self.generation
            actor = self.state.actor
            mode = self.jev_mode
            agent = self.jev_agents[mode] if actor == 0 and self.controller == 'jev' else self.agent
            self.thinking = True
            self.revision += 1
            metadata = {'round': self.round, 'seed': self.seed, 'player': ctx.observation.player_id,
                        'turn': ctx.observation.turn, 'controller': self.controller,
                        'jev_mode': mode, 'opponent': self.opponent_name}
        started = time.monotonic()
        try:
            decision = agent.decide(ctx)
            with self.lock:
                if generation != self.generation:
                    return  # A stopped/restarted table must never apply an old result.
                self.act(decision.action_id)
                self.log({**metadata, 'status': 'applied', 'decision': asdict(decision),
                          'seconds': time.monotonic() - started, 'rewards': self.rewards})
        except Exception as exc:
            with self.lock:
                if generation == self.generation:
                    self.error = str(exc) if isinstance(exc, TypeSafeError) else 'AI 决策失败，请检查终端日志后重试'
                    self.auto = False
                    self.revision += 1
                    self.log({**metadata, 'status': 'error', 'error_type': type(exc).__name__})
                    print('AI 决策失败：' + type(exc).__name__, flush=True)
        finally:
            with self.lock:
                self.thinking = False
                self.revision += 1

    def snapshot(self):
        view = self.game.view(self.state, 'p0')
        actions = self.game.legal_actions(self.state) if self.state.actor == 0 else ()
        return dict(private=view.private, public=view.public,
                    actions=[asdict(a) for a in actions],
                    history=[asdict(e) for e in self.history],
                    auto=self.auto, delay=self.delay, revision=self.revision,
                    controller=self.controller, jev_mode=self.jev_mode,
                    jev_available=self.backend is not None, opponent=self.opponent_name,
                    thinking=self.thinking, error=self.error,
                    round=self.round, totals=self.totals, rewards=self.rewards,
                    winner=self.state.winner, spring=self.state.spring)

    def command(self, data):
        with self.lock:
            command = data.get('command')
            if command == 'mode':
                if not isinstance(data.get('auto'), bool):
                    raise ValueError('auto 必须是布尔值')
                self.auto = data['auto']
                self.error = None
                self.generation += 1
                self.due = time.monotonic() + self.delay
                self.revision += 1
            elif command == 'configure':
                controller, mode = data.get('controller'), data.get('jev_mode')
                if controller not in ('human', 'douzero', 'jev') or mode not in MODES:
                    raise ValueError('无效的控制方式或信息模式')
                if controller == 'jev' and self.backend is None:
                    raise ValueError('JEV 未配置，请在仓库 .env 中设置 TYPESAFE_API_KEY 后重启')
                self.controller, self.jev_mode = controller, mode
                self.auto = controller != 'human'
                self.totals = dict.fromkeys(self.totals, 0)
                self.new()
            elif command == 'retry':
                self.error = None
                self.auto = self.controller != 'human'
                self.due = time.monotonic()
                self.revision += 1
            elif command == 'speed':
                delay = data.get('delay')
                if isinstance(delay, bool) or not isinstance(delay, (int, float)) or not 0.1 <= delay <= 5:
                    raise ValueError('delay 必须在 0.1 到 5 秒之间')
                self.delay = delay
                self.revision += 1
            elif command == 'new':
                self.new()
            elif command in ('action', 'hint'):
                if self.thinking or self.auto or self.state.actor != 0 or self.state.phase == 'finished':
                    raise ValueError('请等待你的回合，或先关闭自动模式')
                if data.get('revision') != self.revision:
                    raise ValueError('牌局已更新，请重试')
                if command == 'hint':
                    return {'action_id': self.choice()}
                self.act(data.get('action_id'))
            else:
                raise ValueError('未知指令')
            return self.snapshot()


class RecordingBackend:
    def __init__(self, backend, path):
        self.backend, self.path = backend, path

    def evaluate(self, state, questions):
        record = {'time': time.time(), 'requested_model': self.backend.model,
                  'state': state, 'questions': questions}
        try:
            response = self.backend.evaluate(state, questions)
            record.update(status='completed', response=response)
            return response
        except Exception:
            record['status'] = 'error'
            raise
        finally:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--auto', action='store_true')
    parser.add_argument('--delay', type=float, default=0.9)
    parser.add_argument('--seed', type=int)
    parser.add_argument('--opponent', choices=('douzero', 'simple'), default='douzero')
    parser.add_argument('--controller', choices=('human', 'douzero', 'jev'), default='human')
    parser.add_argument('--jev-mode', choices=MODES, default='minimal')
    parser.add_argument('--models', type=Path, default=ROOT / 'models')
    parser.add_argument('--env-file', default=str(ROOT.parents[1] / '.env'))
    parser.add_argument('--trace-dir', type=Path, default=ROOT / 'runs')
    args = parser.parse_args()
    if not 0.1 <= args.delay <= 5:
        parser.error('--delay 必须在 0.1 到 5 秒之间')
    opponent = None
    if args.opponent == 'douzero':
        from joker_jev.games.doudizhu.full.douzero import DouZeroAgent
        opponent = DouZeroAgent(args.models)
    backend = None
    try:
        backend = TypeSafeBackend.from_env(args.env_file)
    except ValueError:
        if args.controller == 'jev':
            parser.error('JEV 配置缺失或无效，请检查 .env')
    session = time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3)
    if backend:
        backend = RecordingBackend(backend, args.trace_dir / (session + '-jev.jsonl'))
    table = Table(args.auto or args.controller != 'human', args.delay, args.seed,
                  opponent, backend, args.controller, args.jev_mode,
                  args.trace_dir / (session + '-moves.jsonl'))

    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, body, content_type='application/json; charset=utf-8'):
            raw = json.dumps(body, ensure_ascii=False).encode() if isinstance(body, dict) else body
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            path = self.path.split('?')[0]
            if path == '/api/state':
                with table.lock:
                    self.respond(200, table.snapshot())
            elif path in ('/', '/index.html', '/style.css', '/app.js'):
                name = 'index.html' if path == '/' else path[1:]
                mime = {'html': 'text/html', 'css': 'text/css', 'js': 'text/javascript'}[name.split('.')[-1]]
                self.respond(200, (ROOT / name).read_bytes(), mime + '; charset=utf-8')
            else:
                self.respond(404, {'error': 'Not found'})

        def do_POST(self):
            # Only JSON, same-origin browser requests or local scripts may control the table.
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + self.headers.get('Host', ''):
                return self.respond(403, {'error': 'Origin rejected'})
            if self.path != '/api/command':
                return self.respond(404, {'error': 'Not found'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 8192 or self.headers.get_content_type() != 'application/json':
                    raise ValueError('需要 JSON 请求')
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError('需要 JSON 对象')
                self.respond(200, table.command(data))
            except (ValueError, TypeError) as exc:
                self.respond(400, {'error': str(exc)})

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    stop = threading.Event()

    def run():
        while not stop.wait(0.05):
            table.tick()

    threading.Thread(target=run, daemon=True).start()
    print('斗地主牌桌：http://127.0.0.1:%s  |  Ctrl+C 停止' % args.port, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()


if __name__ == '__main__':
    main()
