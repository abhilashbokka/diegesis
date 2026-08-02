"""Synthetic 5.1 mixes with known ground truth.

The centre-channel measurement has to be validated before it is trusted on real
film, because on real film there is no answer key. Here the answer is set by
construction: dialogue is placed in the centre at a chosen ratio, and the
measurement must recover that ratio.

The signals are crude — speech is a modulated formant-shaped noise burst rather
than real speech. That is adequate, because the measurement only cares about
where speech-band energy sits, not about what was said.
"""

from __future__ import annotations

import numpy as np
from scipy import signal

SR = 48000


def speech_like(duration_s: float, sr: int = SR, seed: int = 0) -> np.ndarray:
    """Noise shaped into the speech band and modulated at a syllabic rate.

    Real speech has energy concentrated at 300-3400 Hz and an amplitude
    envelope that fluctuates around 4 Hz. Both matter here: the band decides
    what the filter sees, the modulation decides which frames read as active.
    """
    rng = np.random.default_rng(seed)
    n = int(duration_s * sr)
    x = rng.normal(0, 1, n)

    b, a = signal.butter(4, [300 / (sr / 2), 3400 / (sr / 2)], btype="band")
    x = signal.lfilter(b, a, x)

    t = np.arange(n) / sr
    # ~4 Hz syllabic envelope, plus a slow pause structure so the recording is
    # not uniformly active.
    envelope = (0.5 + 0.5 * np.sin(2 * np.pi * 4.0 * t)) ** 2
    pauses = (np.sin(2 * np.pi * 0.25 * t) > -0.3).astype(float)
    x = x * envelope * pauses

    peak = np.max(np.abs(x))
    return x / peak if peak > 0 else x


def music_like(
    duration_s: float, sr: int = SR, seed: int = 1, swell: bool = False
) -> np.ndarray:
    """Sustained harmonic tones — broadband, no syllabic modulation.

    Stationary by default. A slowly swelling score partially coincides with
    speech bursts, and any frame-energy detector then reads those swells as
    speech, inflating the apparent off-centre contribution. That is a genuine
    confound rather than a synthesis artefact, so it is available via ``swell``
    and measured explicitly in the validation suite.
    """
    rng = np.random.default_rng(seed)
    n = int(duration_s * sr)
    t = np.arange(n) / sr

    x = np.zeros(n)
    for fundamental in (110.0, 165.0, 220.0):
        for harmonic in range(1, 8):
            f = fundamental * harmonic
            if f < sr / 2:
                x += (0.6**harmonic) * np.sin(2 * np.pi * f * t + rng.uniform(0, 2 * np.pi))

    if swell:
        x *= 0.6 + 0.4 * np.sin(2 * np.pi * 0.1 * t)

    peak = np.max(np.abs(x))
    return x / peak if peak > 0 else x


def make_5_1(
    duration_s: float = 20.0,
    centre_ratio: float = 1.0,
    music_level: float = 0.5,
    sr: int = SR,
    seed: int = 0,
    swell: bool = False,
    duck_db: float = 0.0,
) -> tuple[np.ndarray, float]:
    """Build a 5.1 mix with dialogue placed at a known centre ratio.

    ``centre_ratio`` is the fraction of dialogue *amplitude* sent to centre;
    the remainder is split equally between L and R. Music goes to L, R and the
    surrounds, never to centre — the convention real mixes follow.

    Returns the mix (samples, 6) in SMPTE order and the expected energy ratio.
    """
    if not 0.0 <= centre_ratio <= 1.0:
        raise ValueError("centre_ratio must be in [0, 1]")

    speech = speech_like(duration_s, sr, seed=seed)
    n = len(speech)

    mix = np.zeros((n, 6))  # L R C LFE Ls Rs

    # Dialogue: centre plus a symmetric bleed into L/R.
    side = (1.0 - centre_ratio) / 2.0
    mix[:, 2] += centre_ratio * speech
    mix[:, 0] += side * speech
    mix[:, 1] += side * speech

    # Music and ambience: everywhere except centre.
    # Optional ducking, as real mixes do — the score is pulled down while
    # dialogue is present. A smoothed speech envelope drives the gain.
    duck_gain = np.ones(n)
    if duck_db > 0:
        env = np.abs(signal.hilbert(speech))
        b_s, a_s = signal.butter(2, 3.0 / (sr / 2), btype="low")
        env = signal.lfilter(b_s, a_s, env)
        env = env / (np.max(env) + 1e-12)
        duck_gain = 10 ** (-duck_db * env / 20.0)

    for i, ch in enumerate((0, 1, 4, 5)):
        music = music_like(duration_s, sr, seed=seed + 100 + i, swell=swell)
        mix[:, ch] += music_level * duck_gain * music

    # LFE: low-frequency only, and must not affect the result — it is excluded
    # from the metric, and including it here proves that exclusion works.
    rng = np.random.default_rng(seed + 500)
    lfe = rng.normal(0, 1, n)
    b, a = signal.butter(4, 120 / (sr / 2), btype="low")
    mix[:, 3] = 0.8 * signal.lfilter(b, a, lfe)

    peak = np.max(np.abs(mix))
    if peak > 1.0:
        mix /= peak

    # Expected ratio is in energy, so amplitudes square.
    expected = centre_ratio**2 / (centre_ratio**2 + 2 * side**2) if centre_ratio > 0 else 0.0

    return mix, expected
