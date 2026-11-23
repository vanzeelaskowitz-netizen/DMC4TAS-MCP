"""DMC4 TAS tools over stdio."""
import os
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP

from client import call
from jc import jc_points as find_jc_points
from moves import rows
from record_video import record

mcp = FastMCP("DMC4 TAS", instructions="Read tas://combo-rules before searching combos. Probe preserves the paused timeline.")
HERE = Path(__file__).resolve().parent


def asset(name, suffix):
    root = Path(os.environ["DMC4TAS_ROOT"]) / "runs" if suffix == ".tas" else HERE / "outputs"
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or path.suffix.lower() != suffix:
        raise ValueError(f"Expected a {suffix} path within {root}")
    return path


@mcp.tool()
def status() -> dict:
    """Read game and timeline status with the most recent frame."""
    return call("status")


@mcp.tool()
def navigate(operation: Literal["load", "goto", "step"], amount: int = 1, script: str = "") -> dict:
    """Load a runs script. For goto, amount is the absolute frame; for step, the number of frames."""
    if operation == "load":
        return call("load", path=str(asset(script, ".tas")))
    result = call(operation, count=amount)
    return {"frames": result} if operation == "step" else result


@mcp.tool()
def probe(first: int, last: int, candidates: list[list[str]], fields: list[str]) -> list[list[dict]]:
    """Try key rows from first through last inclusive. Select frame, hits, camera.angle or dotted fields."""
    return call("probe", first=first, last=last, candidates=candidates, fields=fields)


@mcp.tool()
def jc_points(first: int, last: int, verify: bool = True) -> list[dict]:
    """Per frame of the loaded timeline (at most 60): enemies the game would let Nero step on (can),
    enemies whose step sphere holds his step point (inside), whether an enemy already took damage
    earlier in the range (afterHit), and with verify whether pressing jump there really starts an
    Enemy Step (steps). For a JC that keeps the damage, pick a frame with steps and afterHit."""
    return find_jc_points(first, last, verify)


@mcp.tool()
def practice(option: Literal["hp", "dt", "time", "kill"], enabled: bool) -> dict:
    """Set a practice switch."""
    return call("cheat", name=option, on=enabled)


@mcp.tool()
def move(name: Literal["split", "calibur", "snatch", "jc", "jumpToward", "toward", "lock"]) -> list[str]:
    """Generate input phases using the last frame's camera and game keyboard bindings."""
    last = call("status").get("last")
    if not last or not last.get("keys", {}).get("controls"):
        raise ValueError("No keyboard table for the sampled character; step a frame with a supported SE character")
    return rows(name, (last.get("camera") or {}).get("angle"), last["keys"]["controls"])


@mcp.tool()
def motions() -> dict:
    """Read the observed move IDs for the active game build."""
    return call("motions")


@mcp.tool()
def script(name: str, text: str | None = None) -> str:
    """Read a runs/*.tas file or replace its contents with text."""
    path = asset(name, ".tas")
    if text is None:
        return path.read_text(encoding="utf-8-sig")
    path.write_text(text, encoding="utf-8")
    return str(path)


@mcp.tool()
def video(script_name: str, filename: str, first: int = 0, last: int | None = None,
          show_keys: bool = False) -> str:
    """Load a script and film the visible game window; finishes on last."""
    output = asset(filename, ".mp4")
    output.parent.mkdir(parents=True, exist_ok=True)
    return record(asset(script_name, ".tas"), output, first, last, show_keys)


@mcp.resource("tas://combo-rules")
def rules() -> str:
    """Observed Bloody Palace combat timing and camera conventions."""
    return (HERE / "COMBO_RULES.md").read_text(encoding="utf-8")


if __name__ == "__main__":
    mcp.run(transport="stdio")
