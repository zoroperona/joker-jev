from dataclasses import dataclass
from typing import Tuple

from .strategy import Position, ordered


@dataclass(frozen=True)
class Scenario:
    id: str
    topic: str
    position: Position
    preferred: Tuple[str, ...]
    rationale: str
    caveat: str


def position(hands, actor, target="", owner=None, passes=0):
    return Position(tuple(ordered(h.split()) for h in hands), actor,
                    ordered(target.split()), owner, passes)


SCENARIOS = (
    Scenario("guard_before_landlord", "地主上家守门",
             position(("K", "3 4", "6 6 A"), 2, "10", 0, 1), ("play:A",),
             "地主报单且下一位就是地主；用 A 压住后保留对子出完路线。",
             "未知的 K 不一定在地主手里；标注偏向防止其立即走完的保守策略。"),
    Scenario("yield_to_teammate", "避免抢队友牌权",
             position(("Q", "4 4", "3 5 A"), 2, "K", 1), ("pass",),
             "剩余未知牌都不能压 K；让队友保持牌权，避免拆散自己的散牌后被地主反抢。",
             "队友具体是否持对子仍不公开；不能假设看见队友的 44。"),
    Scenario("override_yield_to_block", "有威胁时必须接管队友牌权",
             position(("A", "4 4", "3 3 2"), 2, "K", 1), ("play:2",),
             "地主报单且未知牌含 A，过牌有立即输局风险；用 2 接管后剩余对子。",
             "与让牌场景相反，但原因是威胁和后续出完路线，而非固定座位口诀。"),
    Scenario("pairs_against_single", "地主报单时选择对子路线",
             position(("A", "4 5", "3 3 K K"), 2), ("play:3,3", "play:K,K"),
             "对子让报单地主无法接牌，并保留另一对；领单牌会增加被地主直接走完的风险。",
             "不能推广成永远打对子：自己能直接走完时应优先赢局。"),
    Scenario("probe_pair_keep_control", "地主可能持对子时先用小单试探",
             position(("K K", "4 5", "3 Q A"), 2), ("play:3", "play:Q"),
             "先出 3 或 Q，若地主拆 K 接牌，保留 A 及时接回，再出最后一张；先耗掉 A 会失去接回能力。",
             "报双不等于对子，未知 KK45 的归属不公开；这是该参考底牌下成立的路线。"),
    Scenario("single_threat_changes_lead", "剩 QA 面对报单地主要先控牌",
             position(("K", "3 4 5", "Q A"), 2), ("play:A",),
             "地主只剩一张时，先试探 Q 可能直接输局；先出 A 后再走 Q。",
             "与试探场景比较时也要考虑自己少一张散牌；并非只凭地主报单/报双就能决定出法。"),
    Scenario("feed_next_teammate", "地主下家给下一位队友送牌",
             position(("2", "3 5 7", "A"), 1), ("play:3", "play:5", "play:7"),
             "下一位是报单队友，先领出其可能接住的小单，让其在地主行动前走完。",
             "A 和 2 的具体归属不公开；此例强调行动顺序，不声称猜中队友底牌。"),
    Scenario("landlord_stop_farmer", "地主阻止农民先走",
             position(("K K", "4 5", "3"), 0, "Q", 2), ("play:K",),
             "压住农民的 Q，留下 K；放弃牌权会让其重新领出最后一张。",
             "这里拆对子是为了夺回控制，不能机械地为保持对子而过牌。"),
    Scenario("finish_over_seat_duty", "可以直接获胜时优先走完",
             position(("A", "3 4", "8 8"), 2, "5 5", 0, 1), ("play:8,8",),
             "直接出完对子就是农民共同胜利，无须为守门保留牌。",
             "终局奖励优先于任何中间战术偏好。"),
    Scenario("single_finish_against_pair", "地主报双也不妨碍自己单牌走完",
             position(("K K", "A", "3 4"), 1), ("play:A",),
             "自己仅剩 A，直接走完即胜利；无需先推断地主是否有对子。",
             "报双只是张数事实，不等于确定持有对子。"),
)


# 单独扩展回归集，保留首次十例及其标注。
COOPERATION_SCENARIOS = (SCENARIOS[1], SCENARIOS[2],
    Scenario("yield_lower_ranks", "换点数后仍应保留队友牌权",
             position(("J", "4 4", "3 5 K"), 2, "Q", 1), ("pass",),
             "公开未知牌 J44 都压不住队友 Q；自己的 K 需要留作后续控制。",
             "这是原策略分歧场景的保序点数变体，不算独立泛化样本。"),
    Scenario("yield_with_joker_in_own_hand", "有大王也不必抢队友牌权",
             position(("A", "5 5", "3 4 BJ"), 2, "2", 1), ("pass",),
             "未知 A55 不能压 2；大王是自己的控制资源，不是必须立即使用的牌。",
             "并非有大王就永远不接队友，需要结合是否能直接走完。"),
    Scenario("yield_after_landlord_passed", "地主已过牌，下家可以还权队友",
             position(("Q", "3 5 A", "4 4"), 1, "K", 2, 1), ("pass",),
             "地主已过，自己再过就由队友自由领出；不要用 A 重开响应。",
             "明确使用地主下家的位置与一次过牌，不沿用上家场景的行动顺序。"),
    Scenario("higher_enemy_card_but_trick_closes", "未知大牌仍可能存在，但地主本轮已过",
             position(("A", "3 5 2", "4 4"), 1, "K", 2, 1), ("pass",),
             "A 可能在地主手里，但地主已经过牌，自己过牌即结束本轮；出 2 反而重开响应。",
             "过牌不证明地主没有 A；这里依赖的是轮转规则，不是错误猜牌。"),
    Scenario("finish_even_when_teammate_safe", "队友牌安全但自己能立即走完",
             position(("Q", "4 4", "A"), 2, "K", 1), ("play:A",),
             "出 A 立即终局，优先锁定共同胜利；安全牌权不意味着必须过牌。",
             "过牌在参考底牌下也能赢，标注明确偏好即时锁定胜利，而非断言过牌必错。"),
    Scenario("rocket_takeover_against_pair_threat", "地主报双可能接对子走完，王炸接管",
             position(("A A", "4 4", "3 SJ BJ"), 2, "K K", 1), ("play:SJ,BJ",),
             "地主可能用 AA 一次出完；王炸接管后只剩一张 3。",
             "AA 的具体归属未知，动作针对可能的立即输局风险。"),
)
