from __future__ import annotations


def expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def update_elo(
    winner_rating: float,
    loser_rating: float,
    k_factor: float = 32.0,
) -> tuple[float, float]:
    winner_expected = expected_score(winner_rating, loser_rating)
    loser_expected = expected_score(loser_rating, winner_rating)
    return (
        winner_rating + k_factor * (1.0 - winner_expected),
        loser_rating + k_factor * (0.0 - loser_expected),
    )
