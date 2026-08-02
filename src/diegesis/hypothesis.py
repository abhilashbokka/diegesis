"""The centre-channel hypothesis, and the test for it.

    H1: In 5.1/7.1 film mixes, speech energy is concentrated in the centre
        channel, to the point that taking the centre channel alone recovers
        dialogue better than any separation model would.

Everything in Diegesis depends on the answer. If dialogue is centre-locked
almost always, neural separation of the full mix is a problem to route around
rather than solve. If it holds only sometimes, spatially-informed separation
has real room — and the failure cases are the interesting research object.

Nobody appears to have published the measurement, and it costs nothing to make.

The circularity trap
--------------------
The obvious implementation is fatally flawed: detect speech, then measure how
much of it is in the centre channel. But if speech is detected *using* the
centre channel, the test answers a question it has already assumed. Any mix
would look centre-locked.

So speech activity is detected on the **full downmix** — every channel summed,
centre included but not privileged. Only then is the energy distribution
measured. Detection and measurement never share a channel selection.

The music-bed trap
------------------
The obvious metric — centre's share of all speech-band energy — is also wrong,
and validation against synthetic mixes is what exposed it. Music and effects
have substantial energy inside 300-3400 Hz. A mix with dialogue *entirely* in
the centre but a loud score in L/R/surrounds measures as barely centre-locked,
because the score dilutes the denominator. The metric would then be reporting
how loud the music is, dressed up as a statement about dialogue placement.

So each channel's non-speech energy is estimated and subtracted. What remains
is the *speech-driven increase* per channel:

    contribution[ch] = max( sum(E[ch] over speech frames) - n * bed[ch], 0 )
    centre_ratio     = contribution[C] / sum(contribution[all full-range])

Note the aggregation. Computing this per frame and then averaging does not
work: the bed is a median, so half of all frames exceed it by construction, and
ordinary music fluctuation then manufactures off-centre contributions. Summing
energy across many frames first averages that out. Validation caught this too —
the per-frame version underestimated a fully centre-locked mix as 0.60.

The distribution is therefore reported over time blocks rather than frames,
which is the more useful output anyway: it localises *which scenes* break the
convention.

LFE is excluded: it is band-limited well below the speech range and carries no
dialogue. Reference points:

    1.00   all speech energy in centre — perfectly centre-locked
    0.33   energy spread evenly across L, R, C — no centre preference
    0.20   spread evenly across all five full-range channels
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import signal

# Speech occupies roughly 300-3400 Hz; the band that carries intelligibility and
# the band a telephone was designed around.
SPEECH_BAND_HZ = (300.0, 3400.0)

FRAME_MS = 50.0
HOP_MS = 25.0

# Syllabic modulation band. Speech amplitude fluctuates at roughly 2-8 Hz as
# syllables arrive; sustained music and room tone do not.
MODULATION_BAND_HZ = (2.0, 8.0)

# A frame counts as speech-active when its modulation strength sits this far up
# the recording's own range. Relative, so it survives level and genre
# differences between films.
MODULATION_THRESHOLD = 0.35

# Ratios are reported per time block, not per frame: a block is long enough for
# music fluctuation to average out, and short enough to localise a scene that
# breaks the convention.
BLOCK_S = 5.0
MIN_BLOCK_SPEECH_FRAMES = 20

# SMPTE channel order for 5.1: L R C LFE Ls Rs
LAYOUT_5_1 = ("L", "R", "C", "LFE", "Ls", "Rs")
LAYOUT_7_1 = ("L", "R", "C", "LFE", "Ls", "Rs", "Lb", "Rb")


@dataclass
class ChannelReport:
    """Result of testing one recording."""

    n_channels: int
    layout: tuple[str, ...]
    duration_s: float
    sample_rate: int

    n_frames: int = 0
    n_speech_frames: int = 0

    centre_ratio_overall: float | None = None
    centre_ratio_mean: float | None = None
    centre_ratio_median: float | None = None
    centre_ratio_p10: float | None = None
    centre_ratio_p90: float | None = None

    # Fraction of speech-active frames whose centre ratio exceeds 0.5 — the
    # point past which the centre channel carries more speech energy than every
    # other channel combined.
    centre_locked_fraction: float | None = None

    channel_energy_db: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def speech_fraction(self) -> float:
        return self.n_speech_frames / self.n_frames if self.n_frames else 0.0

    @property
    def verdict(self) -> str:
        if self.centre_ratio_median is None:
            return "inconclusive"
        if self.centre_ratio_median >= 0.80:
            return "strongly centre-locked"
        if self.centre_ratio_median >= 0.55:
            return "centre-dominant"
        if self.centre_ratio_median >= 0.40:
            return "centre-leaning"
        return "not centre-locked"


def layout_for(n_channels: int) -> tuple[str, ...]:
    """Channel names for a channel count, assuming SMPTE order."""
    if n_channels == 6:
        return LAYOUT_5_1
    if n_channels == 8:
        return LAYOUT_7_1
    if n_channels == 2:
        return ("L", "R")
    if n_channels == 1:
        return ("M",)
    return tuple(f"ch{i}" for i in range(n_channels))


def _speech_band_filter(sr: int) -> tuple[np.ndarray, np.ndarray]:
    nyquist = sr / 2.0
    low = SPEECH_BAND_HZ[0] / nyquist
    high = min(SPEECH_BAND_HZ[1] / nyquist, 0.99)
    return signal.butter(4, [low, high], btype="band")


def _frame_energy(x: np.ndarray, frame: int, hop: int) -> np.ndarray:
    """Mean square energy per frame."""
    n_frames = max(1 + (len(x) - frame) // hop, 0)
    if n_frames <= 0:
        return np.zeros(0)
    idx = np.arange(frame)[None, :] + hop * np.arange(n_frames)[:, None]
    return np.mean(x[idx] ** 2, axis=1)


def _modulation_strength(band: np.ndarray, sr: int, frame: int, hop: int) -> np.ndarray:
    """Per-frame strength of syllabic (2-8 Hz) amplitude modulation.

    The feature that separates speech from sustained music. Speech amplitude
    fluctuates several times a second as syllables come and go; a held chord or
    a room tone does not. Detecting on this rather than on level is what makes
    the test work under a loud score.
    """
    envelope = np.abs(signal.hilbert(band))
    # Smooth away the carrier, keep the syllabic rate.
    b_lp, a_lp = signal.butter(2, 20.0 / (sr / 2), btype="low")
    envelope = signal.lfilter(b_lp, a_lp, envelope)

    b_bp, a_bp = signal.butter(
        2, [MODULATION_BAND_HZ[0] / (sr / 2), MODULATION_BAND_HZ[1] / (sr / 2)], btype="band"
    )
    modulated = signal.lfilter(b_bp, a_bp, envelope)

    # Modulation depth relative to the local mean level, so a loud passage does
    # not read as speech merely for being loud.
    mod_energy = _frame_energy(modulated, frame, hop)
    level = _frame_energy(envelope, frame, hop)
    return mod_energy / (level + 1e-12)


def analyse(audio: np.ndarray, sr: int) -> ChannelReport:
    """Test the centre-channel hypothesis on one multichannel recording.

    ``audio`` is shape (samples, channels), assumed SMPTE order.
    """
    if audio.ndim != 2:
        raise ValueError("audio must be 2-D (samples, channels)")

    n_channels = audio.shape[1]
    layout = layout_for(n_channels)
    report = ChannelReport(
        n_channels=n_channels,
        layout=layout,
        duration_s=len(audio) / sr,
        sample_rate=sr,
    )

    if "C" not in layout:
        report.notes.append(
            f"No centre channel in a {n_channels}-channel file. The hypothesis "
            "is untestable here — a stereo downmix has already folded centre "
            "into L and R at about -3 dB, unrecoverably."
        )
        return report

    frame = int(sr * FRAME_MS / 1000)
    hop = int(sr * HOP_MS / 1000)
    if len(audio) < frame:
        report.notes.append("Recording shorter than one analysis frame.")
        return report

    b, a = _speech_band_filter(sr)

    # Full-range channels only. LFE is band-limited below speech and would
    # dilute the ratio with energy that could never carry dialogue.
    full_range = [i for i, name in enumerate(layout) if name != "LFE"]

    # --- speech detection, on the downmix ------------------------------------
    # Deliberately NOT the centre channel: detecting speech with the same
    # channel whose dominance is being measured would assume the conclusion.
    #
    # Detection is by syllabic modulation rather than raw level. Speech has a
    # strong 2-8 Hz amplitude fluctuation; sustained music and ambience do not.
    # A level threshold fails outright under a loud constant score, because the
    # frame energy barely varies and nothing ever crosses it.
    downmix = audio[:, full_range].sum(axis=1)
    downmix_band = signal.lfilter(b, a, downmix)

    if not np.any(np.abs(downmix_band) > 0):
        report.notes.append("No measurable energy in the speech band.")
        return report

    modulation = _modulation_strength(downmix_band, sr, frame, hop)
    if modulation.size == 0:
        report.notes.append("Recording too short for modulation analysis.")
        return report

    # Relative threshold: speech-active frames are those whose syllabic
    # modulation stands clearly above the recording's own baseline.
    floor = float(np.percentile(modulation, 25))
    spread = float(np.percentile(modulation, 95)) - floor
    speech_active = modulation > (floor + MODULATION_THRESHOLD * spread) if spread > 0 \
        else np.zeros(modulation.size, dtype=bool)

    report.n_frames = int(modulation.size)
    report.n_speech_frames = int(speech_active.sum())

    # --- per-channel speech-band energy --------------------------------------
    per_channel = {}
    for i in full_range:
        band = signal.lfilter(b, a, audio[:, i])
        per_channel[layout[i]] = _frame_energy(band, frame, hop)

    for name, e in per_channel.items():
        total = float(np.sum(e))
        report.channel_energy_db[name] = float(10 * np.log10(total + 1e-12))

    if report.n_speech_frames < 10:
        report.notes.append(
            f"Only {report.n_speech_frames} speech-active frames — too few to "
            "conclude anything."
        )
        return report

    # --- the metric ----------------------------------------------------------
    stacked = np.stack([per_channel[layout[i]] for i in full_range], axis=1)
    centre_col = full_range.index(layout.index("C"))

    # Estimate each channel's music/effects bed from the frames where no speech
    # is active, and subtract it. Without this the metric reports how loud the
    # score is rather than where the dialogue sits. Median resists the odd
    # loud effect landing in a "quiet" frame.
    # The bed must come from frames that are *clearly* non-speech — the least
    # modulated quartile — not merely from everything below the speech
    # threshold. When dialogue dominates a scene, sub-threshold frames still
    # contain speech, which inflates the bed and can drive the centre
    # contribution to zero. That failure looked like "no dialogue in centre" on
    # the easiest possible input.
    quiet_cut = float(np.percentile(modulation, 25))
    quiet = modulation <= quiet_cut
    if quiet.sum() >= 10:
        bed = np.median(stacked[quiet], axis=0)
    else:
        bed = np.zeros(stacked.shape[1])
        report.notes.append(
            "Fewer than 10 non-speech frames — no music bed could be estimated, "
            "so the ratio is diluted by whatever else occupies the speech band."
        )

    # Aggregate before taking the ratio. A per-frame ratio is unusable: the bed
    # is a median, so half of all frames exceed it by construction, and music
    # fluctuation alone then manufactures off-centre "contributions". Summing
    # energy over many frames averages that fluctuation out.
    #
    # The distribution comes from time blocks rather than frames, which is also
    # the more useful output — it identifies *which scenes* break the
    # convention, rather than producing noise at frame resolution.
    def block_ratio(sel: np.ndarray) -> float | None:
        if sel.sum() < MIN_BLOCK_SPEECH_FRAMES:
            return None
        summed = stacked[sel].sum(axis=0) - bed * sel.sum()
        summed = np.maximum(summed, 0.0)
        total = summed.sum()
        return float(summed[centre_col] / total) if total > 0 else None

    overall = block_ratio(speech_active)
    if overall is None:
        report.notes.append("Not enough speech-active frames to conclude anything.")
        return report

    frames_per_block = max(int(BLOCK_S * 1000 / HOP_MS), 1)
    block_ratios = []
    for start in range(0, stacked.shape[0], frames_per_block):
        sel = np.zeros(stacked.shape[0], dtype=bool)
        sel[start : start + frames_per_block] = True
        r = block_ratio(sel & speech_active)
        if r is not None:
            block_ratios.append(r)

    ratios = np.array(block_ratios) if block_ratios else np.array([overall])

    report.centre_ratio_overall = overall
    report.centre_ratio_mean = float(np.mean(ratios))
    report.centre_ratio_median = float(np.median(ratios))
    report.centre_ratio_p10 = float(np.percentile(ratios, 10))
    report.centre_ratio_p90 = float(np.percentile(ratios, 90))
    report.centre_locked_fraction = float(np.mean(ratios > 0.5))

    n_full = len(full_range)
    report.notes.append(
        f"Chance level for {n_full} full-range channels is "
        f"{1.0 / n_full:.2f}; measured median is {report.centre_ratio_median:.2f} "
        f"across {len(ratios)} blocks of {BLOCK_S:.0f} s."
    )

    return report
