# Joker + JEV

English | [中文](README_ZH.md)

An extensible Python framework for testing card games and JEV decision-making. **The main game is full three-player classic Dou Dizhu (斗地主)**: 54-card deal, bidding, revealed bottom cards, every standard play type, and final scoring. Python 3.9+, standard library only.

## Quick start

```bash
git clone https://github.com/zoroperona/joker-jev.git
cd joker-jev
# Full Dou Dizhu, three simple AIs in self-play, no API key needed
python3 -m joker_jev --game doudizhu --agent simple --seed 42
# 10 full games, saving a summary, step-by-step replays and a Markdown report
python3 -m joker_jev.games.doudizhu.full.match --episodes 10 --output reports/my-full-local.json
# Correctness tests
python3 -m unittest discover -s tests -v
```

To use JEV, copy `.env.example` to a local `.env` and set `TYPESAFE_API_KEY`. The default endpoint is `https://api.typesafe.ai/v1/systemone`; experiments pin the model to `jev-1.13.0`. `.env` is git-ignored — never put keys in reports or commits.

```bash
# 10 live full games: JEV controls one rotating seat, the other two are simple AIs
python3 -m joker_jev.games.doudizhu.full.match --live --episodes 10 --seed 20261016 --output reports/my-full-live.json
```

Output paths must not already exist, so historical results are never overwritten. JEV's role is decided by each game's bidding; when it is a farmer its teammate is also a simple AI. Remote outputs are not guaranteed to be reproducible; deals are never re-drawn based on outcome, and API errors are reported separately and not counted as losses.

## Rules

- 54 cards, 17/17/17 plus 3 bottom cards; bid 1–3 for landlord, redeal if nobody bids, landlord leads.
- Single, pair, triple, triple+single/pair, straight, pair straight, airplane with single/pair wings, four+two singles/pairs, bomb, rocket.
- Two passes return the lead; one landlord against two farmers who share the result.
- Bombs/rockets double the stakes, as do spring/anti-spring; landlord and farmers settle 2:1:1, zero-sum.
- Private hands are isolated; public card tracking, bottom-card constraints, unknown-card estimates, per-turn re-decision and logging.

Classic bidding only — no extra grab-landlord, doubling, wildcards or four-player variants. Regional differences (airplane single wings, four-with-two) are pinned explicitly. See [full rules and implementation](docs/full-doudizhu.md).

## AI and JEV

`FullSimpleAgent` is an original heuristic AI: it bids from hand strength, prioritizes finishing, yields to its teammate, blocks opponents down to one card, keeps bombs, and picks plays by an approximate remaining-group count. No models, trained weights or real opponent hands.

JEV receives the rules, rewards, its own hand, public state, inferences and legal options, and returns a Choice. The CLI defaults to **`v3`**: on top of `v2_compact`, each candidate carries a player-view sampled simulation (team win rate, mean score, sample count); candidates are sorted by simulated score and usually fit a single Choice; an immediate hand-emptying play is made by code. See [v3 sampled simulation](docs/simulation-strategy.md). `v2_compact` adds the player's own hand partition, remaining groups after each action, control-card usage and pass consequences, with at most 24 options per Choice and hierarchical grouping that keeps every legal action reachable. JEV always makes the final choice; partition counts are not win rates and returned probabilities are not real win probabilities.

**Strategies are not required to be optimal.** Legality, rules, information isolation and protocol are correctness tests; win rate, score, latency and API usage are performance metrics.

## Strategy results

**Latest (v3 sampled simulation)**: re-run paired against `v2_compact` on the same 20 deals (`jev-1.13.0`). v3 won 16/20 (80%), v2_compact 5/19. Of the 19 pairs both completed, v3 alone won 11 and v2_compact alone won 0. On the 10 new deals: v3 8/10, v2_compact 0/9. v3 never needed a second call per decision; time per game went 7.9 s → 12.8 s (local simulation). Small sample, and the opponents use the same policy as the simulation — see the [v3 write-up](docs/simulation-strategy.md) and [paired report](reports/doudizhu-strategy-ab-v3.md).

Offline, without the API (600 paired deals vs simple AIs, `full/local_eval.py`):

| Focal seat strategy | Win rate | Mean score |
|---|---:|---:|
| simple (baseline) | 51.8% | −0.05 |
| rollout_play (simulation for play only) | 73.7% | +2.04 |
| rollout (simulation for bidding + play) | 69.0% | +2.41 |

Earlier v1 vs v2_compact comparison (pairs where both completed):

| Dataset | Complete pairs | v1 | v2_compact |
|---|---:|---:|---:|
| Original 10 deals (development) | 10 | 4/10 | 5/10 |
| Another batch of new deals | 8 | 0/8 | 3/8 |

[v2 paired report](reports/doudizhu-strategy-ab-v2.md) · [behavior stats](reports/doudizhu-strategy-ab-v2-behavior.json) · [early report incl. failed requests](reports/doudizhu-strategy-ab-v1.md) · [why v2 changed](docs/strategy-adjustment.md)

```bash
# v3 sampled simulation (CLI default)
python3 -m joker_jev.games.doudizhu.full.match --live --strategy v3 --episodes 10 --output reports/my-v3.json
# v2_compact / original v1
python3 -m joker_jev.games.doudizhu.full.match --live --strategy v2_compact --episodes 10 --output reports/my-v2.json
python3 -m joker_jev.games.doudizhu.full.match --live --strategy v1 --episodes 10 --output reports/my-v1.json
# Offline paired evaluation, no API: simple / rollout_play / rollout
python3 -m joker_jev.games.doudizhu.full.local_eval --games 600 --strategies simple,rollout_play,rollout --workers 8
# Live paired comparison
python3 -m joker_jev.games.doudizhu.full.compare_strategies --baseline v2_compact --candidate v3 --fresh-seed 20270101 --output reports/my-comparison.json
```

### Remaining work

Done in v3: separate bidding vs play evaluation (offline ablation), limited hidden-card sampling and playout simulation (~0.5 s per decision), and role/position-aware blocking, yielding and taking over (handled by playouts instead of fixed rules).

Next:

- Simulations assume every seat plays like the simple AI — exactly the current opponent. Add opponents of different styles to measure the gain when the opponent model is wrong.
- Infer cards from public behavior while keeping uncertainty (a pass does not prove the absence of higher cards).
- More unseen deals, more opponent types and repeated runs, jointly tracking win rate, score, completion rate and API cost.
- Keep improving response-validation diagnostics and request-size control; never hide failed requests behind random fallback play.

## First live full games

The first **10 live full games of JEV vs simple AIs** all finished: JEV's team went **3–7 (30%)**, mean score −1.9, 0 API errors. Seeds 20261016–20261025, model `jev-1.13.0`, 69 API calls. As landlord 0/4, as farmer 3/3. [Report and replays](reports/doudizhu-full-deal-live-v1.md).

Correctness tests cover the full game and the original endgame regressions; currently **91 tests pass**.

## Architecture

```text
joker_jev/
  core/                    CardGame, agent context, shared game engine and reward protocol
  agents/                  generic random/JEV agents, TypeSafe HTTP backend
  games/
    doudizhu/
      full/                full play types, deal/bid/play state machine, AIs, simulation and evaluation
      environment.py       retained restricted endgame environment
      strategy.py          retained endgame inference and offline diagnostics
    high_card/             minimal example showing how a second game plugs in
```

Each game provides its own rules, state, legal actions, observations, rewards and inference; the shared engine checks legality, advances state and accumulates rewards. [Adding a game](docs/adding-a-game.md) · [JEV protocol](docs/jev-protocol.md) · [Evaluation principles](docs/strategy-evaluation.md). In-process view isolation is for trusted plugins, not a sandbox for malicious ones.

## Retained endgame experiments

The original restricted endgames (1–4 cards per player) are kept and reproducible, but are not full-game results: [450-game three-strategy endgame comparison](reports/doudizhu-expanded-live-v2.md) · [10 endgames JEV vs simple AI](reports/jev-vs-simple-10-v1.md) · [endgame protocol](docs/full-endgame-evaluation.md).

## Configuration and public data

Only a key-free `.env.example` is committed; the real `.env` stays local. Published replays come from synthetic deals with no real player identities. Research logs include each seat's hand on its own turn for review; it is never passed to other agents. Do not put API keys, auth headers or real user data in logs, issues or commits.
