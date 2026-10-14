"""A fake windowless engine for tests: a ConsoleTre client that behaves like the engine on the wire.

Run as a process in place of "Roadcraft ModEditor.exe" (engine.EngineSession(engine_argv=[python,
this file])).  It accepts the engine's argv, joins the ConsoleTre hub like the engine does
(C:\\RC_RE\\research\\engine_protocol.md section 2; decompiled Saber.ConsoleTre client code):

* TCP to 127.0.0.1:<RC_FAKE_HUB_PORT or 20563>; packets are ``u32 len | u32 id | payload``;
* ApplicationIdMessage (id 5, string guid), then ``sys RegisterApp(2, name, long hwnd, "Channel N", uint pid)``
  with N from ``--set /Config/Debug/ConsoleChannel N``;
* RegisterListener 1 ``{Channel, Module=Automation, Type=ExecSsl, Workspace=RoadBuilder}`` and a
  DbgVars listener; pings once per second;
* an ExecSsl request is ``msg`` to listener 1 with body GUID16 + string(script); the reply is sent from a
  speaker registered with ``{__PrivateId__ = native GUID text}``, body = UTF-8 + one NUL.

Canned replies: a probe script gets synthetic F/G/B/C/W/J/T lines (hull roll oscillating at
RC_FAKE_ROLL_HZ, default 1 Hz; H terrain lines when it calls GetTerrain(), unless RC_FAKE_NO_TERRAIN=1 makes
that an SSL error; L prismatic lines when it calls GetCurrentPosition), an input script gets ROAMER_INPUT_APPLIED, SaveScreenshot writes a PNG
in two steps (partial, then complete), a script containing RC_FAKE_HANG gets no reply.
RC_FAKE_MODE=silent never connects (for wall-clock tests).  RC_FAKE_LOG receives JSON lines of the
argv and every script.

IntegrationStudio's "Game editor" connector (C:/RC_RE/research/scene_play.md): the fake also registers
the engine side the SSL GameEditorController would (listener {Module=IntegrationStudio, Type=Game editor,
Workspace, GameID, Usage absent}; speakers {Module=IntegrationStudioProxy, Type=Game editor|Manager}),
answers StartFrameSharing with FrameShared, and LoadScene/LoadScenePlay with LoadingsState Scene
Loading/Loaded and Manager "Scene Changed"; after LoadScenePlay a current truck appears.  With
RC_FAKE_SCENE_GATED=1 the engine starts like smoke_003 (no level, no truck, SaveScreenshot writes nothing)
until a viewport is shared and a scene loaded; the SSL fallback scripts (SSL_FRAME_SHARING,
SSL_LOAD_REQUESTED, SSL_PLAY_REQUESTED) change the same state.  RC_FAKE_EDITOR=0 registers no editor
connector; RC_FAKE_TRUCKS=0 loads scenes without a truck.
"""

from __future__ import annotations

import json
import math
import os
import re
import socket
import struct
import sys
import threading
import time
import uuid
import zlib

START = time.monotonic()
LOG = os.environ.get("RC_FAKE_LOG")
_log_lock = threading.Lock()


def log(row: dict) -> None:
    if LOG:
        with _log_lock, open(LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")


# ---------------------------------------------------------------- codec (NativeWriter/SystemMessage)
def s_str(text: str, nul: bool = False) -> bytes:
    data = text.encode("utf-8") + (b"\0" if nul else b"")
    return struct.pack("<i", len(data)) + data


def sys_message(name: str, *params: tuple[str, object]) -> bytes:
    body = b""
    for kind, value in params:
        if kind == "int":
            body += struct.pack("<ii", 4, value)
        elif kind == "uint":
            body += struct.pack("<iI", 4, value)
        elif kind == "long":
            body += struct.pack("<iq", 8, value)
        elif kind == "str":
            body += s_str(value)
        elif kind == "buf":
            body += struct.pack("<i", len(value)) + value
        else:
            raise ValueError(kind)
    return b"sys" + s_str(name) + struct.pack("<i", len(params)) + body


def listener_passport(conditions: dict[str, str | None]) -> bytes:
    """None = an absent condition (RegisterListener: name, bool shouldAbsent, value)."""
    out = struct.pack("<i", len(conditions))
    for name in sorted(conditions):  # ordinal sort, as ListenerPassport.Sort
        value = conditions[name]
        out += s_str(name, True) + (b"\1" if value is None else b"\0") + s_str(value or "", True)
    return out


def speaker_passport(conditions: dict[str, str]) -> bytes:
    out = struct.pack("<i", len(conditions))
    for name in sorted(conditions):
        out += s_str(name, True) + s_str(conditions[name], True)
    return out


def user_message(speaker: int, body: bytes, timestamp: int = 0) -> bytes:
    return b"msg" + struct.pack("<iii", timestamp, speaker, 0) + struct.pack("<i", len(body)) + body


def native_guid(raw16: bytes) -> str:
    p = str(uuid.UUID(bytes_le=raw16)).split("-")
    return "{" + "-".join([p[0].upper(), p[1].upper(), p[2].lower(), p[3].upper(), p[4].upper()]) + "}"


def png_bytes(width: int = 4, height: int = 2) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\0" + b"\x80\x40\x20" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


# ---------------------------------------------------------------- canned engine behaviour
def probe_reply(t: float, script: str = "") -> str:
    hz = float(os.environ.get("RC_FAKE_ROLL_HZ", "1.0"))
    roll = math.radians(2.0) * math.sin(2 * math.pi * hz * t)
    up = (-math.sin(roll), math.cos(roll), 0.0)
    fwd = (0.0, 0.0, 1.0)
    frame = int(t * 60)
    lines = [f"F {frame} 0.5000 0.300 0.000",
             "G 1 1200.0 0 1 0",
             f"B BoneChassis_cdt 0.00000 {1.2 + 0.01 * math.sin(2 * math.pi * hz * t):.5f} {0.5 * t:.5f} "
             f"{up[0]:.5f} {up[1]:.5f} {up[2]:.5f} {fwd[0]:.5f} {fwd[1]:.5f} {fwd[2]:.5f}",
             "C BoneChassis_cdt 9000.000 0.00000 -0.50000 0.00000 0.00000 0.70000 0.00000"]
    for i in range(4):
        lines.append(f"W {0.10 + 0.01 * i:.4f} {(-1) ** i:.4f} 0.4000 {i:.4f} 1 3.000 0.5000 0.6000 0.0000 1")
    lines.append(f"J hinge_blade {0.1 * math.sin(t):.4f} 0.0000")
    lines.append("T 0 0.0100")
    if "GetTerrain()" in script:   # H lines: terrain under each wheel; RC_FAKE_NO_TERRAIN=1 rejects the accessor
        if os.environ.get("RC_FAKE_NO_TERRAIN") == "1":
            return "__automation__ (3:40) error 2059 : can't resolve identifier 'GetTerrain'"
        lines += [f"H {i} 0.0500" for i in range(4)]
    if "GetCurrentPosition" in script:   # L lines: prismatic positions
        lines += [f"L SuspFrontLeft {0.05 * math.sin(2 * math.pi * hz * t):.5f}", "L SuspRear -0.04000"]
    return "\n".join(lines) + "\n"


class State:
    """Scene/viewport/truck state; ungated (default) it starts loaded, as the old canned replies did."""

    def __init__(self):
        gated = os.environ.get("RC_FAKE_SCENE_GATED") == "1"
        self.sharing = not gated
        self.level = "" if gated else "fake_level"
        self.truck = not gated
        self.trucks = 0 if gated else 1
        self.scene = ""


STATE = State()
GAME_ID = "fake-game-1"


def load_scene(name: str, play: bool, delay: float = 0.3) -> None:
    STATE.scene = name
    time.sleep(delay)
    STATE.level = name.replace(".scn", "")
    if play and os.environ.get("RC_FAKE_TRUCKS", "1") != "0":
        STATE.trucks = 1
        time.sleep(delay)
        STATE.truck = True


def answer(script: str) -> str | None:
    if "RC_FAKE_HANG" in script:
        return None
    if "SaveScreenshot(" in script:
        match = re.search(r'SaveScreenshot\(ScreenshotSaveTarget\.FILE,"([^"]+)"', script)
        if match and STATE.sharing and STATE.level:  # smoke_003: nothing written without a viewport and a level; the real engine appends ".png" (scene_001)
            threading.Thread(target=write_png_slowly, args=(match.group(1) + ".png",), daemon=True).start()
        return ""
    if "RC_READY" in script:
        return (f"RC_READY\nframe {int((time.monotonic() - START) * 60)}\nlevel {STATE.level}\n"
                f"truck {1 if STATE.truck else 0}\n")
    if "RC_ADAPTER" in script:
        return ("RC_ADAPTER\napi 2 adapter 1\ncurrent NVIDIA GeForce RTX 4060 Laptop GPU\n"
                "adapter 0 Intel(R) UHD Graphics\nadapter 1 NVIDIA GeForce RTX 4060 Laptop GPU\n")
    if "RC_EDITOR" in script:
        return (f"RC_EDITOR\neditorMain 1\nlevel {STATE.level}\nscene {STATE.scene}\n"
                f"viewports {1 if STATE.sharing else 0}\ntrucks {STATE.trucks}\ntruck {1 if STATE.truck else 0}\n")
    if "SSL_FRAME_SHARING" in script:
        STATE.sharing = True
        return "SSL_FRAME_SHARING"
    for marker, play in (("SSL_LOAD_REQUESTED", False), ("SSL_PLAY_REQUESTED", True)):
        if marker in script:
            match = re.search(r'p\.name = "([^"]*)"', script)
            threading.Thread(target=load_scene, args=(match.group(1) if match else "x.scn", play),
                             daemon=True).start()
            return marker
    if "RC_FORCE_CURRENT" in script:
        if STATE.truck:
            return "ALREADY_CURRENT"
        if not STATE.trucks:
            return "NO_TRUCKS"
        STATE.truck = True
        return "SET_CURRENT fake_truck"
    if "GetBodyCount" in script or 'StringFormat("F %i' in script:
        return probe_reply(time.monotonic() - START, script)
    if "ROAMER_INPUT_APPLIED" in script:
        return "ROAMER_INPUT_APPLIED\nrequestedPedals 0.000\nrequestedSteer 0.000\n"
    if "GetFrameNmb" in script:
        return f"FRAME {int((time.monotonic() - START) * 60)}"
    return "OK"


def write_png_slowly(path: str) -> None:
    data = png_bytes()
    time.sleep(0.2)
    with open(path, "wb") as fh:  # the engine writes asynchronously: a partial file first
        fh.write(data[: len(data) // 2])
    time.sleep(0.6)
    with open(path, "wb") as fh:
        fh.write(data)


class Reader:
    def __init__(self, data: bytes):
        self.data, self.pos = data, 0

    def int(self) -> int:
        value = struct.unpack_from("<i", self.data, self.pos)[0]
        self.pos += 4
        return value

    def bool(self) -> bool:
        value = self.data[self.pos] != 0
        self.pos += 1
        return value

    def str(self) -> str:
        n = self.int()
        value = self.data[self.pos: self.pos + n].decode("utf-8")
        self.pos += n
        return value


# ---------------------------------------------------------------- client
class FakeEngine:
    def __init__(self, port: int, channel: str, name: str = "Roadcraft ModEditor"):
        self.port, self.channel, self.name = port, channel, name
        self.sock: socket.socket | None = None
        self.send_lock = threading.Lock()
        self.reply_speakers: dict[str, int] = {}
        self.next_speaker = 100
        self.editor_speaker, self.manager_speaker = 10, 11

    def packet(self, pid: int, payload: bytes) -> None:
        with self.send_lock:
            self.sock.sendall(struct.pack("<II", len(payload), pid) + payload)

    def connect(self) -> None:
        deadline = time.monotonic() + 60
        while True:
            try:
                self.sock = socket.create_connection(("127.0.0.1", self.port), timeout=2)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.2)
        self.sock.settimeout(None)
        self.packet(5, s_str(uuid.uuid4().hex))
        self.packet(1, sys_message("RegisterApp", ("int", 2), ("str", self.name), ("long", 0),
                                   ("str", self.channel), ("uint", os.getpid())))
        self.packet(1, sys_message("RegisterListener", ("int", 1), ("buf", listener_passport(
            {"Channel": self.channel, "Module": "Automation", "Type": "ExecSsl", "Workspace": "RoadBuilder"}))))
        self.packet(1, sys_message("RegisterListener", ("int", 2), ("buf", listener_passport(
            {"Channel": self.channel, "Module": "DbgVars", "Type": "Commands"}))))
        if os.environ.get("RC_FAKE_EDITOR", "1") != "0":  # the SSL GameEditorController's callback
            self.packet(1, sys_message("RegisterListener", ("int", 3), ("buf", listener_passport(
                {"Channel": self.channel, "Module": "IntegrationStudio", "Type": "Game editor",
                 "Workspace": "RoadBuilder", "GameID": GAME_ID, "Usage": None}))))
            self.packet(1, sys_message("RegisterSpeaker", ("int", self.editor_speaker), ("buf", speaker_passport(
                {"Channel": self.channel, "Module": "IntegrationStudioProxy", "Type": "Game editor",
                 "Workspace": "RoadBuilder", "GameID": GAME_ID}))))
            self.packet(1, sys_message("RegisterSpeaker", ("int", self.manager_speaker), ("buf", speaker_passport(
                {"Channel": self.channel, "Module": "IntegrationStudioProxy", "Type": "Manager",
                 "Workspace": "RoadBuilder"}))))
        log({"event": "registered", "channel": self.channel, "pid": os.getpid()})
        threading.Thread(target=self.pinger, daemon=True).start()

    def pinger(self) -> None:
        while True:
            time.sleep(1.0)
            try:
                self.packet(0, b"")
            except OSError:
                return

    def recv_exact(self, n: int) -> bytes:
        data = b""
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise ConnectionError("hub closed")
            data += chunk
        return data

    def serve(self) -> None:
        while True:
            length, pid = struct.unpack("<II", self.recv_exact(8))
            payload = self.recv_exact(length) if length else b""
            if pid != 1 or payload[:3] != b"msg":
                continue
            count = struct.unpack_from("<i", payload, 11)[0]
            listeners = struct.unpack_from(f"<{count}i", payload, 15)
            header = 15 + 4 * count
            body_len = struct.unpack_from("<i", payload, header)[0]
            body = payload[header + 4: header + 4 + body_len]
            if 1 in listeners:
                threading.Thread(target=self.exec_ssl, args=(body,), daemon=True).start()
            if 3 in listeners:
                threading.Thread(target=self.editor_message, args=(body,), daemon=True).start()

    def send_editor(self, speaker: int, name: str, *fields: tuple[str, object]) -> None:
        body = s_str(name)
        for kind, value in fields:
            if kind == "str":
                body += s_str(value)
            elif kind == "int":
                body += struct.pack("<i", value)
            else:
                body += b"\1" if value else b"\0"
        self.packet(1, user_message(speaker, body))

    def editor_message(self, body: bytes) -> None:
        reader = Reader(body)
        name = reader.str()
        row = {"event": "editor", "name": name, "bytes": len(body)}
        if name == "StartFrameSharing":
            vp, w, h, x, y, cw, ch = (reader.int() for _ in range(7))
            row.update(viewport=vp, size=[w, h], rect=[x, y, cw, ch], visible=reader.bool())
            STATE.sharing = True
            log(row)
            self.send_editor(self.editor_speaker, "FrameShared", ("str", "2147484226"), ("int", vp), ("bool", False))
            return
        if name in ("LoadScene", "LoadScenePlay"):
            scene, ps, tag, res, prefab = reader.str(), reader.str(), reader.str(), reader.str(), reader.bool()
            row.update(scene=scene, psBytes=len(ps.encode()), resTag=tag, resourceBytes=len(res.encode()),
                       prefab=prefab)
            if name == "LoadScenePlay":
                row.update(server=reader.str(), gameMode=reader.str())
            else:
                row.update(unloaded=[reader.str() for _ in range(reader.int())])
            log(row)
            self.send_editor(self.editor_speaker, "LoadingsState", ("str", "Scene"), ("int", 1), ("str", "Loading"))
            load_scene(scene, name == "LoadScenePlay")
            self.send_editor(self.editor_speaker, "LoadingsState", ("str", "Scene"), ("int", 1), ("str", "Loaded"))
            self.send_editor(self.manager_speaker, "Scene Changed", ("str", scene.replace(".scn", "")),
                             ("str", GAME_ID))
            return
        if name == "MinimizeEditorOnDeactivate":
            row["value"] = reader.bool()
        log(row)

    def exec_ssl(self, body: bytes) -> None:
        guid = native_guid(body[:16])
        size = struct.unpack_from("<i", body, 16)[0]
        script = body[20: 20 + size].decode("utf-8")
        log({"event": "exec", "guid": guid, "script": script})
        reply = answer(script)
        if reply is None:
            return
        with self.send_lock:
            speaker = self.reply_speakers.get(guid)
            if speaker is None:
                speaker = self.reply_speakers[guid] = self.next_speaker
                self.next_speaker += 1
                payload = sys_message("RegisterSpeaker", ("int", speaker), ("buf", speaker_passport(
                    {"Channel": self.channel, "__PrivateId__": guid})))
                self.sock.sendall(struct.pack("<II", len(payload), 1) + payload)
        self.packet(1, user_message(speaker, reply.encode("utf-8") + b"\0"))


def main(argv: list[str]) -> int:
    log({"event": "argv", "argv": argv})
    channel = "Channel 0"
    for i, arg in enumerate(argv):
        if arg == "--set" and i + 2 < len(argv) and argv[i + 1] == "/Config/Debug/ConsoleChannel":
            channel = f"Channel {argv[i + 2]}"
    if os.environ.get("RC_FAKE_MODE") == "silent":
        time.sleep(3600)
        return 0
    engine = FakeEngine(int(os.environ.get("RC_FAKE_HUB_PORT", "20563")), channel)
    engine.connect()
    try:
        engine.serve()
    except (ConnectionError, OSError):
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
