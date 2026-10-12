from joker_jev.core.game import CardInference
from joker_jev.core.models import Belief, Observation


class HighCardInference(CardInference):
    def infer(self, observation: Observation) -> Belief:
        played = [event.data["card"] for event in observation.history if event.kind == "card_played"]
        known = set(played) | set(observation.private["hand"])
        unseen = sorted(set(observation.public["deck"]) - known)
        opponent = next(p for p in observation.public["hand_counts"] if p != observation.player_id)
        remaining = observation.public["hand_counts"][opponent]
        probability = remaining / len(unseen) if unseen else 0.0
        return Belief(
            facts={"played_cards": played, "unseen_cards": unseen, "opponent_card_count": remaining},
            estimates={"opponent_card_probability": {str(c): probability for c in unseen}},
            assumptions=(
                "未知牌在对手剩余手牌和未发出的牌之间均匀分布。",
                "未根据对手选牌行为更新概率；这是简化先验，不是对手真实手牌。",
                "各张牌在对手手中的事件不独立，不能将边际概率直接相乘。",
            ),
        )
