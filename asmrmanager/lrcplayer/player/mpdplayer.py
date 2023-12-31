import atexit
import os
import time
from pathlib import Path
from subprocess import run
from typing import Any, List, Literal, NamedTuple

from asmrmanager.config import config
from asmrmanager.filemanager.manager import FileManager
from asmrmanager.logger import logger

from .base import BasePlayer, Music

try:
    import mpd
except ImportError:
    raise ImportError(
        "python-mpd2 is not installed, please install asmrmanager with mpd"
        " dpendency."
    )

MPDStatus = NamedTuple(
    "MPDSatus",
    [
        ("playlistlength", int),
        ("state", Literal["play", "pause", "stop"]),
        ("song", int),
        ("total_time", int),
        ("pos", int),
    ],
)


class MPDPlayer(BasePlayer):
    bin = os.path.expanduser(config.mpd_config.bin)
    music_directory: Path = (
        Path(config.mpd_config.music_directory)
        if config.mpd_config.music_directory
        else FileManager.DATA_PATH / "mpd" / "music"
    )

    @classmethod
    def call(cls, cmd: str, check: bool = True):
        return run(
            f"{cls.bin} {FileManager.CONFIG_PATH / 'mpd.conf'} {cmd}",
            shell=True,
            capture_output=True,
            text=True,
            check=check,
        ).stdout

    @property
    def _status(self):
        status = self.client.status()
        return MPDStatus(
            playlistlength=int(status["playlistlength"]),
            state=status["state"],
            song=int(status["song"]),
            pos=int(float(status["elapsed"]) * 1000),
            total_time=int(float(status["duration"]) * 1000),
        )

    def __init__(self, music_list: List[Music]) -> None:
        super().__init__(music_list)

        # d = uuid.uuid1()

        self.call("--kill", check=False)
        self.call("")
        self.client: Any = mpd.MPDClient()
        self.client.connect(config.mpd_config.host, config.mpd_config.port)

        music_directory = self.music_directory / "default"
        music_directory.mkdir(exist_ok=True)

        for file in music_directory.iterdir():
            assert file.is_symlink()
            file.unlink()

        for music in music_list:
            (music_directory / music.path.name).symlink_to(music.path)

        self.client.update()
        while True:
            if len(self.client.listall()) != len(music_list) + 1:
                continue
            for file in self.client.listall():
                if file.get("directory"):
                    continue
                if not (self.music_directory / file["file"]).exists():
                    break
            else:
                if len(self.client.listall()) == len(music_list) + 1:
                    break
        logger.info(f"mpd update finished {self.client.listall()}")
        self.client.clear()
        while len(self.client.playlist()) != 0:
            time.sleep(0.01)
        logger.info("mpd clear finished")
        self.client.add("default")
        while len(self.client.playlist()) != len(music_list):
            time.sleep(0.01)
        logger.info(f"mpd add finished {self.client.playlist()}")
        self.client.play()

    def switch_music(self, index: int) -> None:
        self.client.stop()
        self.client.play(index)

    @property
    def is_playing(self) -> bool:
        return self._status.state == "play"

    @property
    def pos(self) -> int:
        return self._status.pos

    @pos.setter
    def pos(self, pos: int) -> None:
        self.client.seekcur(int(pos / 1000))
        self.client.pause()
        self.client.pause()

    @property
    def is_paused(self) -> bool:
        return self._status.state == "pause"

    def pause(self) -> None:
        if not self.is_paused:
            self.client.pause()

    def unpause(self) -> None:
        if self.is_paused:
            self.client.pause()

    def play(self) -> None:
        self.client.stop()
        self.client.play()

    @property
    def total_time(self) -> int:
        return self._status.total_time


def __close_mpd():
    MPDPlayer.call("--kill", check=False)


atexit.register(__close_mpd)
