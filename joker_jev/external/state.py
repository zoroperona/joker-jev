"""Reconstruct a public information set without a game instance or opponent hands."""
from collections import Counter
from dataclasses import dataclass
from types import SimpleNamespace

from joker_jev.games.doudizhu.full.cards import DECK, RANKS, legal_moves, ordered

SEATS = ('self', 'right', 'left')  # Actual turn order of the existing web table.
ROLES = ('landlord', 'landlord_down', 'landlord_up')
ENCODING = dict(zip(RANKS, (*range(3, 15), 17, 20, 30)))


def encode(cards):
    return sorted(ENCODING[c] for c in cards)


@dataclass(frozen=True)
class Play:
    sequence: int
    seat: str
    cards: tuple
    remaining: int

    @property
    def count(self):
        return len(self.cards)


class PublicState:
    def __init__(self, hand, landlord):
        if landlord not in SEATS:
            raise ValueError('Unknown landlord')
        self.hand = ordered(hand)
        if Counter(hand) - Counter(DECK) or len(hand) != (20 if landlord == 'self' else 17):
            raise ValueError('Start at the beginning of the play phase with a complete visible hand')
        self.landlord = landlord
        self.actor = landlord
        self.remaining = {s: 20 if s == landlord else 17 for s in SEATS}
        self.played = {s: () for s in SEATS}
        self.history = []
        self.target = None
        self.passes = 0
        self.bombs = 0
        self.finished = False

    def apply(self, event):
        if type(event.sequence) is not int or type(event.remaining) is not int:
            raise ValueError('Invalid event numbers')
        if event.sequence <= len(self.history):
            if event.sequence > 0 and self.history[event.sequence - 1] == event:
                return False
            raise ValueError('Conflicting duplicate event')
        if self.finished or event.sequence != len(self.history) + 1 or event.seat != self.actor:
            raise ValueError('Missed/out-of-order turn; resynchronization required')
        cards = ordered(event.cards)
        if event.remaining != self.remaining[event.seat] - len(cards) or event.remaining < 0:
            raise ValueError('Remaining count does not match the observed play')
        move = None
        if cards:
            options = [m for m in legal_moves(cards, self.target) if m.cards == cards]
            if len(options) != 1:
                raise ValueError('Illegal or ambiguous observed combination')
            move = options[0]
        elif self.target is None:
            raise ValueError('Cannot pass on a free lead')
        hand = Counter(self.hand)
        if event.seat == 'self':
            if Counter(cards) - hand:
                raise ValueError('Observed self play is not in hand')
            hand.subtract(cards)
        seen = Counter(card for pile in self.played.values() for card in pile) + Counter(cards) + hand
        if seen - Counter(DECK):
            raise ValueError('Observed cards exceed the deck')
        # Commit only after every validation succeeds.
        self.hand = ordered(hand.elements())
        self.remaining[event.seat] = event.remaining
        self.played[event.seat] += cards
        self.history.append(event)
        self.actor = SEATS[(SEATS.index(event.seat) + 1) % 3]
        if move:
            self.target, self.passes = move, 0
            self.bombs += move.kind in ('bomb', 'rocket')
        else:
            self.passes += 1
            if self.passes == 2:
                self.target, self.passes = None, 0
        self.finished = event.remaining == 0
        return True

    def actions(self):
        if self.finished or self.actor != 'self':
            raise ValueError('Not our turn')
        return tuple(m.cards for m in legal_moves(self.hand, self.target)) + (((),) if self.target else ())

    def infoset(self):
        offset = SEATS.index(self.landlord)
        roles = {SEATS[(offset + i) % 3]: role for i, role in enumerate(ROLES)}
        last = {role: [] for role in ROLES}
        for e in self.history:
            last[roles[e.seat]] = encode(e.cards)
        unseen = Counter(DECK) - Counter(self.hand) - Counter(c for pile in self.played.values() for c in pile)
        return SimpleNamespace(
            player_position=roles['self'], player_hand_cards=encode(self.hand),
            other_hand_cards=encode(unseen.elements()),
            legal_actions=[encode(a) for a in self.actions()],
            last_move=encode(self.target.cards) if self.target else [],
            last_move_dict=last, card_play_action_seq=[encode(e.cards) for e in self.history],
            played_cards={roles[s]: encode(v) for s, v in self.played.items()},
            num_cards_left_dict={roles[s]: n for s, n in self.remaining.items()}, bomb_num=self.bombs)
