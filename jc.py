"""Which frames of the loaded timeline allow a jump cancel (Enemy Step).

The game's own check (combat.stepCheck) is not enough on its own: on some flagged frames a jump
becomes an Air Hike instead, and a jump on the frame an attack connects cancels its damage. So with
verify, every frame is tried for real: one probe candidate per frame, jump added to that frame.
"""
from client import call

AFTER_PRESS = 8      # frames after the press in which the step has to start
HOLD = 2             # frames the jump key is held, as in the demo
MAX_FRAMES = 60
FIELDS = ["frame", "combat.player.pointer", "combat.player.action", "combat.player.motion",
          "combat.stepCheck", "hits"]


def with_jump(base, press, jump):
    return [f"{row} {jump}".strip() if press <= i < press + HOLD else row for i, row in enumerate(base)]


def step_starts(trace, table):
    """Frames on which an Enemy Step begins. Its first motion time differs by build (0 on SE, 1.2 on
    DX9), so the start is where the action becomes the step's."""
    step = table["action"]["enemyStep"]
    return {j for j, frame in enumerate(trace)
            if frame["combat.player.action"] == step and frame["combat.player.motion"] in table["motion"]["enemyStep"]
            and (j == 0 or trace[j - 1]["combat.player.action"] != step)}


def judged(frame):
    check = frame["combat.stepCheck"] or {"allowed": False, "enemies": {}}
    enemies = check["enemies"]
    return ([enemy for enemy, e in enemies.items() if check["allowed"] and e["can"]],
            [enemy for enemy, e in enemies.items() if any(e["inside"])])


def jc_points(first, last, verify):
    count = last - first + 1
    if not 1 <= first <= last or count > MAX_FRAMES:
        raise ValueError(f"Expected 1 <= first <= last and at most {MAX_FRAMES} frames")
    table = call("motions")["nero"]
    base = [" ".join(keys) for keys in call("timeline-keys", first=first, last=last + AFTER_PRESS)]
    window = dict(first=first, last=last + AFTER_PRESS, fields=FIELDS)
    observed = call("probe", candidates=[base], **window)[0]
    points, hit = [], False
    for frame in observed[:count]:
        can, inside = judged(frame)
        points.append({"frame": frame["frame"], "can": can, "inside": inside, "afterHit": hit})
        # A hit landing on this frame only counts from the next one: a jump now would cancel its damage.
        hit = hit or any(h["target"] != frame["combat.player.pointer"] for h in frame["hits"] or [])
    if verify:
        jump = call("status")["last"]["keys"]["controls"]["jump"]
        tries = call("probe", candidates=[with_jump(base, i, jump) for i in range(count)], **window)
        already = step_starts(observed, table)
        for i, (point, trace) in enumerate(zip(points, tries)):
            point["steps"] = any(j in range(i, i + AFTER_PRESS + 1) for j in step_starts(trace, table) - already)
    return points
