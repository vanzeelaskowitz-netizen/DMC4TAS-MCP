"""Exercise the search loop with a deterministic single-opponent fixture."""
from unittest.mock import patch

from combo_split_calibur import CFG, Search


def simulate(rows, controls, table):
    target = {"x": .4}
    camera = dict(angle=0, target="e", player={"x": .6}, enemies={"e": target})
    motion = table["motion"]
    split, calibur, jc = (motion[name][0] for name in ("split", "calibur", "enemyStep"))
    current, age, previous = None, 0, set()
    frames = []
    for n, row in enumerate(rows, 1):
        held = set(row.partition("#")[0].split())
        pressed = held - previous
        if controls["sword"] in pressed:
            current = calibur if controls["right"] in previous else split
            age = 0
        if controls["jump"] in pressed and age >= 2 and current in (split, calibur):
            current, age = jc, 0
        hit = [dict(source="p", target="e", damage=1)] if current == split and age == 2 else []
        frames.append({"frame": n, "camera": camera, "keys": {"held": sorted(held), "controls": controls},
                       "hits": hit, "combat.player.motion": current, "combat.player.motionFrame": age,
                       "combat.player.action": table["action"]["enemyStep"] if current == jc else 1,
                       "combat.player.pointer": "p", "combat.stepCheck": {"allowed": age >= 2, "enemies": {"e": {"can": True}}}})
        previous, age = held, age + 1
    return frames


def test_demo(folder, controls):
    # Arbitrary fixture IDs catch accidental dependencies on Nero's numeric IDs.
    table = {"action": {"enemyStep": 13}, "motion": {"enemyStep": [10], "split": [11], "calibur": [12]}}
    loaded = [""] * CFG["prefix"]
    out = folder / "search.tas"

    def call(command, **args):
        nonlocal loaded
        if command == "motions":
            return {"nero": table}
        if command == "load":
            loaded = out.read_text(encoding="utf-8").splitlines()
            return {"frames": len(loaded)}
        if command == "step":
            return simulate(loaded[:args["count"]], controls, table)
        if command == "goto":
            if not args["count"]:
                return {}
            f = simulate(loaded[:args["count"]], controls, table)[-1]
            player = {key: f["combat.player."+key] for key in ("action", "motion", "motionFrame")}
            return {"last": {"combat": {"player": player}}}
        assert command == "probe"
        start = args["first"] - 1
        return [simulate(loaded[:start] + trial, controls, table)[start:] for trial in args["candidates"]]

    with patch("combo_split_calibur.call", call):
        Search(out).run(30)
    trace = simulate(loaded, controls, table)
    assert sum(bool(f["hits"]) for f in trace) == 31
    assert sum(f["combat.player.action"] == 13 and f["combat.player.motionFrame"] == 0 for f in trace) == 61
    print(f"Synthetic combat: 30 loops, 31 Split hits, 61 JC, {len(trace)} frames")
