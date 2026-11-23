import json
from math import floor
from pathlib import Path

MOVES = json.loads(Path(__file__).with_name("moves.json").read_text(encoding="utf-8"))
DIRECTIONS = ("left", "down", "right", "up")


def rows(move, angle, controls):
    phases = MOVES[move]
    keys = dict(controls)
    if any(word in phase.split() for phase in phases for word in ("toward", "away")):
        if angle is None:
            raise ValueError("Move needs a camera angle to a target")
        sector = floor((angle + 45) / 90)
        keys["toward"] = keys[DIRECTIONS[sector % 4]]
        keys["away"] = keys[DIRECTIONS[(sector + 2) % 4]]
    result = []
    for phase in phases:
        names = phase.split()
        for name in names:
            if not keys.get(name):
                raise ValueError(f"No game keyboard binding for {name}")
        result.append(" ".join(keys[name] for name in names))
    return result
