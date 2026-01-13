# game.py
import random
from typing import List, Tuple

Card = Tuple[int, int]  # (rank 1-13, suit 0-3)

SUITS_SHORT = ["H", "D", "C", "S"]
SUITS_LONG  = ["Hearts", "Diamonds", "Clubs", "Spades"]

def create_deck() -> List[Card]:
    deck: List[Card] = []
    for rank in range(1, 14):
        for suit in range(4):
            deck.append((rank, suit))
    random.shuffle(deck)
    return deck

def card_value(rank: int) -> int:
    # Ace is always 11 in this assignment.
    if rank == 1:
        return 11
    if rank >= 11:
        return 10
    return rank

def hand_value(hand: List[Card]) -> int:
    return sum(card_value(r) for r, _ in hand)

def card_to_string(card: Card) -> str:
    rank, suit = card
    rank_str = {1: "A", 11: "J", 12: "Q", 13: "K"}.get(rank, str(rank))
    return f"{rank_str} of {SUITS_LONG[suit]}"
