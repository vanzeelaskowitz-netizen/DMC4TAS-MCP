"""Exercise the stdio SDK and a private TCP fixture. No live service discovery."""
import asyncio
import json
import os
from pathlib import Path
import socketserver
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from demo_selftest import test_demo
from moves import rows
from record_video import subtitles

HERE = Path(__file__).resolve().parent


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        request = json.loads(self.rfile.readline())
        assert request["token"] == "offline"
        result = self.server.reply(request["command"], request["args"])
        self.wfile.write(json.dumps({"result": result}).encode() + b"\n")


async def test_stdio(root, controls):
    params = StdioServerParameters(command=sys.executable, args=[str(HERE / "server.py")],
                                  env=dict(os.environ, DMC4TAS_ROOT=str(root)))
    async with stdio_client(params) as (reader, writer), ClientSession(reader, writer) as session:
        await session.initialize()
        names = {t.name for t in (await session.list_tools()).tools}
        assert names == {"status", "navigate", "move", "probe", "motions", "practice", "script", "video", "jc_points",
                         "positions"}
        assert (await session.read_resource("tas://combo-rules")).contents
        step = await session.call_tool("move", {"name": "calibur"})
        assert not step.isError and step.structuredContent["result"] == rows("calibur", 0, controls)
        args = dict(first=8, last=9, candidates=[["J"], []], fields=["frame"])
        probe = await session.call_tool("probe", args)
        assert not probe.isError and probe.structuredContent["result"] == [[{"frame": 8}, {"frame": 9}]] * 2
        assert not (await session.call_tool("script", {"name": "demo.tas", "text": "J\n"})).isError
        assert (root / "runs/demo.tas").read_text() == "J\n"
        points = (await session.call_tool("jc_points", {"first": 9, "last": 12})).structuredContent["result"]
        assert [(p["frame"], p["can"], p["afterHit"], p["steps"]) for p in points] == [
            (9, [], False, False), (10, ["E"], False, False), (11, ["E"], True, True), (12, [], True, False)]
        where = (await session.call_tool("positions", {"first": 3, "last": 4})).structuredContent["result"]
        assert where == [{"frame": f, "player": {"position": [0, 30 + f, 0], "ground": 8.5, "landed": False},
                          "enemies": [{"pointer": "E", "type": "uEm001", "position": [5, 0, 0], "ground": 0.0,
                                       "landed": True}]} for f in (3, 4)]
        print("stdio initialize/list/call, 10 tools, combo resource, fake TCP, script write, jc_points and positions passed")


def fake_jc_probe(args):
    """Frames 10 and 11 are flagged; 10 is the hit frame and a jump there is an Air Hike; on 11 it steps."""
    def frame(n, rows, j):
        pressed = "B" in rows[j] and (j == 0 or "B" not in rows[j - 1])
        step = pressed and n == 11
        flagged = n in (10, 11)
        return {"frame": n, "combat.player.pointer": "P", "combat.player.action": 25 if step else 6,
                "combat.player.motion": 17 if step else 4, "combat.player.motionFrame": 0 if step else 1,
                "combat.stepCheck": {"allowed": flagged, "enemies": {"E": {"can": flagged, "inside": [flagged]}}},
                "hits": [{"target": "E", "source": "P", "damage": 5}] if n == 10 else []}
    return [[frame(args["first"] + j, rows, j) for j in range(len(rows))] for rows in args["candidates"]]


def test_video(folder):
    ass = subtitles(["J", "J", "", "Space + K"])
    assert "0:00:00.00,0:00:00.03" in ass and "0:00:00.05,0:00:00.06" in ass
    (folder / "keys.ass").write_text(ass, encoding="utf-8")
    pixels = subprocess.check_output(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                                      "color=black:s=320x180:r=60", "-vf", "subtitles=keys.ass",
                                      "-frames:v", "4", "-f", "rawvideo", "-pix_fmt", "gray", "-"], cwd=folder)
    size = 320*180
    assert [max(pixels[i:i+size]) > 50 for i in range(0, len(pixels), size)] == [True, True, False, True]
    print("ASS burned into 4 synthetic frames, both active spans and blank frame verified")


def main():
    controls = dict(left="H", right="L", up="U", down="N", lock="Q", sword="Z", jump="B", bringer="T")
    for angle, key in ((0, "H"), (90, "N"), (180, "L"), (-90, "U")):
        assert rows("split", angle, controls) == [f"Q {key} Z"]
    assert rows("snatch", None, controls) == ["Q T"]
    def reply(command, args):
        if command == "status":
            return {"last": {"keys": {"controls": controls}, "camera": {"angle": 0}}}
        if command == "motions":
            return {"nero": {"action": {"enemyStep": 25}, "motion": {"enemyStep": [17]}}}
        if command == "timeline-keys":
            return [[] for _ in range(args["first"], args["last"] + 1)]
        assert command == "probe"
        if args["fields"] == ["frame", "combat.player", "combat.enemies"]:
            enemy = {"pointer": "E", "type": "uEm001", "position": [5, 0, 0], "ground": 0.0, "landed": True, "hp": 1}
            return [[{"frame": f, "combat.player": {"position": [0, 30 + f, 0], "ground": 8.5, "landed": False,
                                                     "hp": 1}, "combat.enemies": [enemy]}
                     for f in range(args["first"], args["last"] + 1)]]
        if args["candidates"] != [["J"], []]:
            return fake_jc_probe(args)
        return [[{"frame": f} for f in range(args["first"], args["last"]+1)] for _ in args["candidates"]]
    with TemporaryDirectory(dir=HERE) as folder, socketserver.TCPServer(("127.0.0.1", 0), Handler) as server:
        root = Path(folder)
        (root / "runs").mkdir()
        (root / "logs").mkdir()
        (root / "logs/tas-service.json").write_text(json.dumps(dict(port=server.server_address[1], token="offline")))
        server.reply = reply
        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            asyncio.run(test_stdio(root, controls))
        finally:
            server.shutdown()
            thread.join()
        test_video(root)
        test_demo(root, controls)


if __name__ == "__main__":
    main()
