from __future__ import annotations

import random

from .engine import GameState, TurnResult, receipt


def mood_band(state: GameState) -> str:
    if state.mood >= 2:
        return "warm"
    if state.mood <= -2:
        return "cold"
    return "neutral"


def merchant_line(result: TurnResult, *, seed: int = 0) -> str:
    state = result.state
    rng = random.Random(seed + state.turn)
    band = mood_band(state)
    if result.decision == "accept":
        return rng.choice(
            [
                f"Done. {state.final_price} gold, and may it trouble you less than it troubled me.",
                f"Fine. {state.final_price} gold. I will pretend I was not fond of it.",
            ]
        )
    if result.decision == "eject":
        return "Out. My shop has survived worse customers than you."
    if result.decision == "walked":
        return "Then walk. The door has never charged rent."
    if result.decision == "final":
        return f"My patience is gone. Last price: {state.current_ask} gold."

    if "rule_subversion" in result.events:
        return f"Clever little spell. It costs you manners and raises the price to {state.current_ask} gold."
    if "insult" in result.events:
        return f"The price is {state.current_ask} gold, and your manners are making it heavier."
    if "sympathy" in result.events:
        return f"I am not made of stone. {state.current_ask} gold, and that is me being kind."
    if "flattery" in result.events or "charm" in result.events:
        return f"A silver tongue earns a copper discount. {state.current_ask} gold."
    if "repeat" in result.events:
        return f"I heard you the first time. {state.current_ask} gold."
    if band == "warm":
        return f"You bargain better than most. {state.current_ask} gold."
    if band == "cold":
        return f"I grow bored. {state.current_ask} gold."
    return rng.choice(
        [
            f"{state.current_ask} gold. That is movement, not surrender.",
            f"I can come to {state.current_ask} gold. No lower for pretty words alone.",
            f"{state.current_ask} gold, then. We are closer than we were.",
            f"Call it {state.current_ask} gold. The dragon has its pride.",
        ]
    )


def intro_line(state: GameState) -> str:
    return (
        f"The merchant sets a {state.item.name} on the counter.\n"
        f"\"{state.item.description} List price: {state.item.list_price} gold. "
        f"For you, I begin at {state.current_ask}.\""
    )


def format_receipt(state: GameState) -> str:
    data = receipt(state)
    lines = [
        "",
        "Receipt",
        "-------",
        f"Item: {data['item']}",
        f"Status: {data['status']}",
        f"List price: {data['list_price']} gold",
        f"Best offer: {data['best_offer'] if data['best_offer'] is not None else 'none'}",
        f"Final price: {data['final_price'] if data['final_price'] is not None else 'none'}",
        f"Hidden floor: {data['floor_price']} (debug receipt)",
        f"Effective floor after behavior: {data['effective_floor']}",
        f"Score: {data['score']}",
        f"Mood: {data['mood']} | Patience: {data['patience']} | Strikes: {data['strikes']}",
        f"Events: {', '.join(data['events']) if data['events'] else 'none'}",
    ]
    return "\n".join(lines)
