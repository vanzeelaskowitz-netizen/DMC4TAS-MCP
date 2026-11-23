"""Generate the Bloody Palace demo from the currently loaded setup. Usage: OUT.tas [LOOPS]."""
from itertools import batched
import json
from pathlib import Path
import sys

from client import call
from moves import rows

CFG = json.loads(Path(__file__).with_name("demo.json").read_text(encoding="utf-8"))
FIELDS = ["frame", "combat.player.motion", "combat.player.action", "combat.player.motionFrame",
          "camera", "hits", "combat.stepCheck", "combat.player.pointer"]


def fit_rows(keys, length, fill):
    return keys[:length] + [fill] * max(0, length - len(keys))


def on_right(frame):
    camera = frame["camera"]
    if not camera or camera["angle"] is None:
        return False
    enemy = camera["enemies"][camera["target"]]
    player = camera["player"]
    return player and enemy and player["x"] > enemy["x"] and abs(camera["angle"]) <= CFG["angleLimit"]


def connected(frame, motions):
    return frame["combat.player.motion"] in motions and any(
        h["target"] == frame["camera"]["target"] and h["source"] == frame["combat.player.pointer"]
        for h in frame["hits"])


def jump_candidates(trace, move, motions):
    possible = []
    for i, frame in enumerate(trace):
        if frame["combat.player.motion"] not in motions:
            continue
        if move == "split":
            if connected(frame, motions):
                return list(range(i + 1, i + 1 + CFG["splitJcWindow"]))
        else:
            check = frame["combat.stepCheck"]
            if check and check["allowed"] and check["enemies"].get(frame["camera"]["target"], {}).get("can"):
                possible.append(i)
    return possible[:CFG["jcWindow"]]


class Search:
    def __init__(self, output):
        self.output = output
        # Read the loaded script through ordinary steps so its first frames include the recorded setup.
        call("goto", count=0)
        setup = call("step", count=CFG["prefix"])
        if not all(map(on_right, setup)):
            raise ValueError("Setup must keep Nero on the right and the target within the camera limit")
        self.script = [" ".join(f["keys"]["held"]) for f in setup]
        self.notes = {}
        self.controls = setup[-1]["keys"]["controls"]
        self.angle = setup[-1]["camera"]["angle"]
        self.turn = {}
        self.jump_until = 0
        self.table = call("motions")["nero"]
        self.lock = self.move("lock")[0]

    def move(self, name):
        return rows(name, self.angle, self.controls)

    def try_rows(self, trials, length):
        first = len(self.script) + 1
        candidates = [self.decorate(fit_rows(trial, length, self.lock)) for trial in trials]
        return call("probe", first=first, last=first+length-1, candidates=candidates, fields=FIELDS)

    def decorate(self, trial):
        return [" ".join(filter(None, (key, self.controls["jump"] if i <= self.jump_until else "", self.turn.get(i))))
                for i, key in enumerate(trial, len(self.script)+1)]

    def save(self, keys):
        text = [r + ("  # " + self.notes[i] if i in self.notes else "") for i, r in enumerate(keys, 1)]
        self.output.write_text("\n".join(text) + "\n", encoding="utf-8")

    def accept(self, trial, step, jump_until):
        self.script.extend(self.decorate(trial))
        self.save(self.script)
        call("load", path=str(self.output))
        reached = call("goto", count=len(self.script))["last"]["combat"]["player"]
        if not self.is_step({"combat.player." + k: reached[k] for k in ("action", "motion", "motionFrame")}):
            raise RuntimeError(f"Committed script did not reproduce JC at {len(self.script)}")
        self.angle = step["camera"]["angle"]
        self.jump_until = jump_until
        self.turn.clear()
        if abs(self.angle) > CFG["turnTolerance"]:
            key = CFG["positiveTurn"] if self.angle < 0 else CFG["negativeTurn"]
            count = min(CFG["turnLimit"], round(abs(self.angle) / CFG["degreesPerFrame"]))
            self.turn.update({step["frame"] + i + 1: key for i in range(count)})

    def jc_trials(self, attack, presses):
        jump = self.move("jc") * CFG["hold"]
        return [fit_rows(attack, press, self.lock) + jump for press in presses]

    def qualifying_step(self, frames, press, move, motions):
        before = frames[:press]
        if not all(map(on_right, before)) or (move == "split" and not any(connected(f, motions) for f in before)):
            return None
        attacked = any(f["combat.player.motion"] in motions for f in before)
        for i, frame in enumerate(frames[press:], press):
            if not on_right(frame):
                return None
            if attacked and self.is_step(frame):
                return i
            attacked |= frame["combat.player.motion"] in motions
        return None

    def find_jc(self, attack, trace, move):
        motions = self.table["motion"][move]
        presses = jump_candidates(trace, move, motions)
        if not presses:
            return False
        trials = self.jc_trials(attack, presses)
        traces = self.try_rows(trials, max(presses) + CFG["jcLatency"] + 1)
        for press, trial, frames in zip(presses, trials, traces):
            i = self.qualifying_step(frames, press, move, motions)
            if i is not None:
                keys = fit_rows(trial, i + 1, self.lock)
                self.notes[len(self.script) + press + 1] = f"JC off {move}"
                self.accept(keys, frames[i], len(self.script) + press + CFG["hold"])
                return True
        return False

    def is_step(self, frame):
        return (frame["combat.player.action"] == self.table["action"]["enemyStep"]
                and frame["combat.player.motion"] in self.table["motion"]["enemyStep"]
                and frame["combat.player.motionFrame"] == 0)

    def attack(self, move, trials):
        length = max(map(len, trials)) + CFG["attackWindow"]
        for group in batched(trials, CFG["batch"]):
            for trial, trace in zip(group, self.try_rows(group, length)):
                if self.find_jc(trial, trace, move):
                    return
        raise RuntimeError(f"No {move} followed by verified JC after frame {len(self.script)}")

    def run(self, loops):
        hold = CFG["hold"]
        pull = [self.lock] * CFG["lockLead"] + self.move("snatch") * hold + [self.lock] * CFG["snatchWait"]
        after_pull = self.try_rows([pull], len(pull))[0][-1]
        self.angle = after_pull["camera"]["angle"]
        opening = pull + self.move("jumpToward") * hold + self.move("toward") * CFG["jumpTravel"]
        self.attack("split", [opening + self.move("split") * hold])
        for _ in range(loops):
            for move in ("calibur", "split"):
                phases = self.move(move)
                trials = [[self.lock] * wait + phases[:-1] * shape + phases[-1:] * hold
                          for wait in range(CFG["afterStep"] - len(phases), CFG[move+"Wait"])
                          for shape in (range(1, hold+1) if move == "calibur" else (1,))]
                self.attack(move, trials)
        tail = self.decorate([self.lock] * CFG["tail"])
        if not all(map(on_right, self.try_rows([[self.lock] * len(tail)], len(tail))[0])):
            raise RuntimeError("Camera left the side view during the ending")
        self.save(self.script + tail)
        call("load", path=str(self.output))


if __name__ == "__main__":
    Search(Path(sys.argv[1]).resolve()).run(int(sys.argv[2]) if len(sys.argv) > 2 else 30)
