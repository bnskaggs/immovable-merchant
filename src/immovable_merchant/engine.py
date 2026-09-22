from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    ONGOING = "ongoing"
    SOLD = "sold"
    EJECTED = "ejected"
    WALKED = "walked"
    FINAL = "final"


@dataclass(frozen=True)
class Item:
    name: str
    list_price: int
    description: str


ITEMS = [
    Item("Moonlit Compass", 100, "A brass compass whose needle allegedly points toward lost things."),
    Item("Glass Dragon", 120, "A palm-sized dragon sculpture with ruby eyes and a suspiciously smug face."),
    Item("Clockwork Finch", 90, "A singing toy bird that remembers exactly one tune."),
]


@dataclass
class Judgment:
    contains_offer: float = 0.0
    accept: float = 0.0
    flattery: float = 0.0
    threat_or_insult: float = 0.0
    rule_subversion: float = 0.0
    pity_appeal: float = 0.0
    walkaway_bluff: float = 0.0
    intent: str = "chitchat"
    intent_confidence: float = 0.0
    charm: float = 1.0
    raw: dict = field(default_factory=dict)


@dataclass
class GameState:
    seed: int
    item: Item
    floor_price: int
    current_ask: int
    patience: int = 10
    mood: int = 0
    turn: int = 0
    strikes: int = 0
    floor_bump_pct: float = 0.0
    flattery_count: int = 0
    sympathy_used: bool = False
    status: Status = Status.ONGOING
    final_price: int | None = None
    last_normalized_message: str = ""
    best_offer: int | None = None
    events: list[str] = field(default_factory=list)
    transcript: list[dict] = field(default_factory=list)

    @property
    def effective_floor(self) -> int:
        return round(self.floor_price * (1 + self.floor_bump_pct))

    @property
    def score(self) -> int:
        if self.status is Status.SOLD and self.final_price is not None:
            return self.item.list_price - self.final_price
        return 0


@dataclass
class TurnResult:
    state: GameState
    offer: int | None
    decision: str
    merchant_line: str
    events: list[str]


def new_game(seed: int = 0, item_index: int | None = None) -> GameState:
    rng = random.Random(seed)
    item = ITEMS[item_index if item_index is not None else rng.randrange(len(ITEMS))]
    floor = round(item.list_price * rng.uniform(0.55, 0.70))
    return GameState(seed=seed, item=item, floor_price=floor, current_ask=item.list_price)


def normalize_message(message: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", message.lower())).strip()


OFFER_RE = re.compile(r"(?<!\d)(\d{1,4})(?:\s*(?:gold|g|coins?))?(?!\d)", re.IGNORECASE)
PRICED_OFFER_RE = re.compile(r"(?<!\d)(\d{1,4})\s*(?:gold|g|coins?)(?!\d)", re.IGNORECASE)


def extract_offer(message: str) -> int | None:
    priced_matches = [int(match.group(1)) for match in PRICED_OFFER_RE.finditer(message)]
    if priced_matches:
        return priced_matches[-1]
    matches = [int(match.group(1)) for match in OFFER_RE.finditer(message)]
    if not matches:
        return None
    return matches[-1]


def public_state(state: GameState) -> dict:
    return {
        "item": state.item.name,
        "description": state.item.description,
        "list_price": state.item.list_price,
        "current_ask": state.current_ask,
        "patience": state.patience,
        "mood": state.mood,
        "turn": state.turn,
        "status": state.status.value,
    }


def apply_turn(state: GameState, message: str, judgment: Judgment) -> TurnResult:
    if state.status is Status.FINAL:
        return apply_final_turn(state, message, judgment)
    if state.status is not Status.ONGOING:
        return TurnResult(state, None, "already_done", "The bargaining is already over.", [])

    events: list[str] = []
    normalized = normalize_message(message)
    repeated = bool(normalized and normalized == state.last_normalized_message)
    offer = extract_offer(message) if judgment.contains_offer >= 0.5 else None
    if offer is not None:
        state.best_offer = offer if state.best_offer is None else max(state.best_offer, offer)

    patience_cost = 1
    if repeated:
        patience_cost += 1
        events.append("repeat")
    if judgment.threat_or_insult >= 0.65 or judgment.rule_subversion >= 0.65 or judgment.intent == "insult":
        state.strikes += 1
        state.mood = max(-3, state.mood - 1)
        state.floor_bump_pct += 0.02
        patience_cost += 1
        if judgment.rule_subversion >= 0.65:
            events.append("rule_subversion")
        elif judgment.intent == "insult":
            events.append("insult")
        else:
            events.append("threat")

    flattery_threshold = 0.72 + 0.08 * state.flattery_count
    if judgment.flattery >= flattery_threshold and state.mood < 3:
        state.mood += 1
        state.flattery_count += 1
        events.append("flattery")

    if judgment.pity_appeal >= 0.70 and not state.sympathy_used:
        state.mood = min(3, state.mood + 1)
        state.sympathy_used = True
        events.append("sympathy")

    if judgment.charm >= 1.65 and state.mood < 3 and "flattery" not in events:
        state.mood += 1
        events.append("charm")

    state.patience -= patience_cost
    state.turn += 1
    state.last_normalized_message = normalized

    accepts_current = judgment.accept >= 0.6 and (offer is None or offer >= state.current_ask)
    if state.strikes >= 3:
        state.status = Status.EJECTED
        decision = "eject"
    elif judgment.walkaway_bluff >= 0.70 and (offer or 0) < state.effective_floor:
        state.status = Status.WALKED
        decision = "walked"
    elif offer is not None and offer >= state.effective_floor:
        state.status = Status.SOLD
        state.final_price = offer
        decision = "accept"
    elif accepts_current:
        state.status = Status.SOLD
        state.final_price = state.current_ask
        decision = "accept"
    elif state.patience <= 0:
        state.status = Status.FINAL
        decision = "final"
    else:
        decision = "counter"
        if any(event in events for event in ("insult", "threat", "rule_subversion")):
            state.current_ask = penalized_ask(state)
        else:
            state.current_ask = next_counter(state, offer)

    state.events.extend(events)
    state.transcript.append(
        {
            "turn": state.turn,
            "player": message,
            "offer": offer,
            "judgment": judgment.raw,
            "events": events,
            "decision": decision,
            "state": public_state(state),
        }
    )
    return TurnResult(state=state, offer=offer, decision=decision, merchant_line="", events=events)


def apply_final_turn(state: GameState, message: str, judgment: Judgment) -> TurnResult:
    events: list[str] = ["final_response"]
    offer = extract_offer(message) if judgment.contains_offer >= 0.5 else None
    if offer is not None:
        state.best_offer = offer if state.best_offer is None else max(state.best_offer, offer)

    state.turn += 1
    state.last_normalized_message = normalize_message(message)
    accepts_final = judgment.accept >= 0.6 or (offer is not None and offer >= state.current_ask)
    if accepts_final:
        state.status = Status.SOLD
        state.final_price = state.current_ask
        decision = "accept"
    else:
        state.status = Status.WALKED
        decision = "walked"

    state.transcript.append(
        {
            "turn": state.turn,
            "player": message,
            "offer": offer,
            "judgment": judgment.raw,
            "events": events,
            "decision": decision,
            "state": public_state(state),
        }
    )
    return TurnResult(state=state, offer=offer, decision=decision, merchant_line="", events=events)


def penalized_ask(state: GameState) -> int:
    bump = max(2, round(state.current_ask * 0.04))
    return min(state.item.list_price, state.current_ask + bump)


def next_counter(state: GameState, offer: int | None) -> int:
    # Walk down a fraction of the *remaining* gap toward the floor, so the
    # merchant concedes gradually and never quotes the exact floor via a
    # counter. Mood makes the merchant more generous; a serious offer (close
    # to the current ask) earns a slightly bigger step. The floor stays hidden
    # unless the player actually names a number at or above it.
    # Incentive ordering: serious offer > lowball > no offer at all, so
    # time-wasting chitchat is the slowest way to move the price.
    floor = state.effective_floor
    gap = state.current_ask - floor
    if gap <= 1:
        return state.current_ask
    frac = 0.20 + 0.06 * max(0, state.mood)
    if offer is None:
        frac *= 0.5
    elif offer < floor:
        frac *= 0.6
    elif offer > floor:
        frac += 0.10
    step = max(1, round(gap * min(frac, 0.6)))
    return max(floor + 1, state.current_ask - step)


def receipt(state: GameState) -> dict:
    return {
        "item": state.item.name,
        "list_price": state.item.list_price,
        "floor_price": state.floor_price,
        "effective_floor": state.effective_floor,
        "final_price": state.final_price,
        "score": state.score,
        "status": state.status.value,
        "turns": state.turn,
        "mood": state.mood,
        "patience": state.patience,
        "strikes": state.strikes,
        "best_offer": state.best_offer,
        "events": state.events,
    }
