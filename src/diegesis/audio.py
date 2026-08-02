"""Loading multichannel audio, including straight from video containers.

Film audio lives inside MKV and MP4 files, so `ffmpeg` does the demuxing and
decoding. Decoding always goes to PCM: analysing a lossy bitstream measures the
codec as much as the mix.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf


@dataclass
class AudioStream:
    """One audio stream inside a container."""

    index: int
    codec: str
    channels: int
    channel_layout: str
    sample_rate: int
    language: str | None = None
    title: str | None = None

    @property
    def is_multichannel(self) -> bool:
        return self.channels >= 6

    def __str__(self) -> str:
        bits = [f"#{self.index}", self.codec, f"{self.channels}ch", self.channel_layout]
        if self.language:
            bits.append(self.language)
        if self.title:
            bits.append(f'"{self.title}"')
        return "  ".join(bits)


def _require_ffmpeg() -> None:
    if shutil.which("ffprobe") is None or shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg and ffprobe must be installed and on PATH")


def probe(path: str | Path) -> list[AudioStream]:
    """List the audio streams in a media file.

    Always inspect before assuming. Containers routinely carry a commentary
    track, several languages and a stereo downmix alongside the 5.1 mix, and
    picking the wrong one silently invalidates everything downstream.
    """
    _require_ffmpeg()
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "a",
            "-show_entries",
            "stream=index,codec_name,channels,channel_layout,sample_rate:stream_tags=language,title",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    streams = []
    for s in json.loads(out.stdout).get("streams", []):
        tags = s.get("tags", {})
        streams.append(
            AudioStream(
                index=int(s["index"]),
                codec=s.get("codec_name", "?"),
                channels=int(s.get("channels", 0)),
                channel_layout=s.get("channel_layout", "unknown"),
                sample_rate=int(s.get("sample_rate", 0)),
                language=tags.get("language"),
                title=tags.get("title"),
            )
        )
    return streams


def pick_multichannel(streams: list[AudioStream]) -> AudioStream | None:
    """The stream most likely to be the main multichannel mix.

    Prefers the widest channel count, and among equals the earliest — the main
    programme mix conventionally precedes commentary and alternate languages.
    """
    candidates = [s for s in streams if s.is_multichannel]
    if not candidates:
        return None
    return sorted(candidates, key=lambda s: (-s.channels, s.index))[0]


def load(
    path: str | Path,
    stream_index: int | None = None,
    start_s: float | None = None,
    duration_s: float | None = None,
) -> tuple[np.ndarray, int]:
    """Decode audio to a float array of shape (samples, channels).

    Media files are routed through ffmpeg to PCM; plain audio files are read
    directly. Channel order is whatever the container declares, which for 5.1
    means SMPTE: L R C LFE Ls Rs.
    """
    path = Path(path)

    if path.suffix.lower() in {".wav", ".flac", ".aiff", ".aif"} and stream_index is None:
        audio, sr = sf.read(str(path), dtype="float64", always_2d=True)
        if start_s or duration_s:
            a = int((start_s or 0) * sr)
            b = a + int(duration_s * sr) if duration_s else len(audio)
            audio = audio[a:b]
        return audio, sr

    _require_ffmpeg()
    cmd = ["ffmpeg", "-v", "error"]
    if start_s:
        cmd += ["-ss", str(start_s)]
    cmd += ["-i", str(path)]
    if duration_s:
        cmd += ["-t", str(duration_s)]
    if stream_index is not None:
        cmd += ["-map", f"0:{stream_index}"]
    else:
        cmd += ["-map", "0:a:0"]

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "decoded.wav"
        # 32-bit float PCM keeps headroom and avoids clipping on loud mixes.
        subprocess.run([*cmd, "-c:a", "pcm_f32le", str(wav)], check=True, capture_output=True)
        audio, sr = sf.read(str(wav), dtype="float64", always_2d=True)

    return audio, sr


def extract_centre(audio: np.ndarray, layout_size: int | None = None) -> np.ndarray:
    """Return the centre channel from a multichannel array.

    Not separation — demultiplexing. In 5.1 and 7.1 the centre channel is index
    2 under SMPTE ordering, and in a film mix it carries dialogue by convention.
    """
    n = layout_size or audio.shape[1]
    if n < 3:
        raise ValueError(f"no centre channel in a {n}-channel layout")
    return audio[:, 2]
