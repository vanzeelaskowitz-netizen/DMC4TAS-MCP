"""World positions per frame of the loaded timeline, replayed through probe (Y is up).

ground is the floor height under Nero from the game's own ray (Y+100 down to Y-100, cast at the
start of his update), None when no floor lies in that range; landed is the collision land flag.
For enemies, which keep no ground result, the TAS casts the game's line query from Y+100 down to
Y-10000 at the end of each frame. All of these exist on the original (DX9) build only.
"""
from client import call

MAX_FRAMES = 600
FIELDS = ["frame", "combat.player", "combat.enemies"]


def frame(row):
    player = row["combat.player"]
    return {"frame": row["frame"],
            "player": player and {k: player.get(k) for k in ("position", "ground", "landed")},
            "enemies": [{k: e.get(k) for k in ("pointer", "type", "position", "ground", "landed")}
                        for e in row["combat.enemies"] or []]}


def positions(first, last):
    if not 1 <= first <= last or last - first + 1 > MAX_FRAMES:
        raise ValueError(f"Expected 1 <= first <= last and at most {MAX_FRAMES} frames")
    keys = [" ".join(k) for k in call("timeline-keys", first=first, last=last)]
    return [frame(row) for row in call("probe", first=first, last=last, candidates=[keys], fields=FIELDS)[0]]
