"""Tests for the centre-channel hypothesis measurement.

Synthetic mixes with the answer set by construction. On real film there is no
answer key, so the measurement has to earn trust here first.

Three earlier versions of this metric passed casual inspection and were wrong:
the first conflated music loudness with dialogue placement, the second used a
level-based speech detector that never fired under a constant score, the third
computed per-frame ratios against a median bed and so measured mostly noise.
Each was caught here rather than on real data, where nothing would have looked
amiss.
"""

from __future__ import annotations

import numpy as np
import pytest

from diegesis import hypothesis, synth

TOLERANCE = 0.10


@pytest.mark.parametrize(
    "centre_ratio",
    [1.0, 0.9, 0.7, 0.5, 0.0],
)
def test_recovers_planted_centre_ratio(centre_ratio: float) -> None:
    """The measurement recovers the ratio the mix was built with."""
    mix, expected = synth.make_5_1(duration_s=30.0, centre_ratio=centre_ratio)
    report = hypothesis.analyse(mix, synth.SR)

    assert report.centre_ratio_overall is not None
    assert abs(report.centre_ratio_overall - expected) < TOLERANCE


def test_no_centre_content_reads_as_zero() -> None:
    """Dialogue entirely in L/R must not read as centre-locked.

    The most important negative case: a metric that reports centre dominance
    when there is none would validate the hypothesis on any film at all.
    """
    mix, _ = synth.make_5_1(duration_s=30.0, centre_ratio=0.0)
    report = hypothesis.analyse(mix, synth.SR)

    assert report.centre_ratio_overall is not None
    assert report.centre_ratio_overall < 0.10
    assert report.verdict == "not centre-locked"


def test_loud_score_does_not_mask_centre_dominance() -> None:
    """A loud score must not drag a centre-locked mix below the threshold.

    This is the music-bed trap. The naive metric — centre's share of all
    speech-band energy — reported 0.39 here when the truth was 1.0, because
    music energy inside 300-3400 Hz diluted the denominator.
    """
    quiet, _ = synth.make_5_1(duration_s=30.0, centre_ratio=1.0, music_level=0.1)
    loud, _ = synth.make_5_1(duration_s=30.0, centre_ratio=1.0, music_level=0.9)

    r_quiet = hypothesis.analyse(quiet, synth.SR)
    r_loud = hypothesis.analyse(loud, synth.SR)

    assert r_quiet.centre_ratio_overall is not None
    assert r_loud.centre_ratio_overall is not None
    assert r_loud.centre_ratio_overall > 0.80
    assert abs(r_loud.centre_ratio_overall - r_quiet.centre_ratio_overall) < 0.20


def test_speech_detection_survives_constant_score() -> None:
    """Speech frames are still found under a loud, sustained score.

    A level-threshold detector fails here: with stationary music the frame
    energy barely varies, so nothing crosses the threshold and the analysis
    returns nothing at all. Modulation-based detection is what fixes it.
    """
    mix, _ = synth.make_5_1(duration_s=30.0, centre_ratio=1.0, music_level=0.9)
    report = hypothesis.analyse(mix, synth.SR)

    assert report.n_speech_frames > 50
    assert 0.02 < report.speech_fraction < 0.95


def test_lfe_is_excluded() -> None:
    """LFE must not affect the ratio — it is band-limited below speech."""
    mix, expected = synth.make_5_1(duration_s=30.0, centre_ratio=1.0)
    baseline = hypothesis.analyse(mix, synth.SR).centre_ratio_overall

    loud_lfe = mix.copy()
    loud_lfe[:, 3] *= 4.0
    with_lfe = hypothesis.analyse(loud_lfe, synth.SR).centre_ratio_overall

    assert baseline is not None and with_lfe is not None
    assert abs(with_lfe - baseline) < 0.02


def test_stereo_is_reported_untestable() -> None:
    """Stereo input cannot answer the question, and must say so."""
    rng = np.random.default_rng(0)
    stereo = rng.normal(0, 0.1, (synth.SR * 5, 2))
    report = hypothesis.analyse(stereo, synth.SR)

    assert report.centre_ratio_overall is None
    assert report.verdict == "inconclusive"
    assert any("no centre channel" in n.lower() for n in report.notes)


def test_ducking_biases_upward() -> None:
    """Ducking is a known bias, and its direction is upward.

    Real mixes pull the score down under dialogue, so off-centre contributions
    clip to zero and centre-locking is overstated. Documented rather than
    corrected, because on real film the correction is not identifiable.
    """
    plain, _ = synth.make_5_1(duration_s=30.0, centre_ratio=0.5)
    ducked, _ = synth.make_5_1(duration_s=30.0, centre_ratio=0.5, duck_db=8.0)

    r_plain = hypothesis.analyse(plain, synth.SR).centre_ratio_overall
    r_ducked = hypothesis.analyse(ducked, synth.SR).centre_ratio_overall

    assert r_plain is not None and r_ducked is not None
    assert r_ducked >= r_plain - 0.05


def test_block_distribution_reported() -> None:
    """Ratios are reported across time blocks, to localise failure scenes."""
    mix, _ = synth.make_5_1(duration_s=40.0, centre_ratio=0.9)
    report = hypothesis.analyse(mix, synth.SR)

    assert report.centre_ratio_p10 is not None
    assert report.centre_ratio_p90 is not None
    assert report.centre_ratio_p10 <= report.centre_ratio_median <= report.centre_ratio_p90


def test_rejects_non_2d_input() -> None:
    with pytest.raises(ValueError, match="2-D"):
        hypothesis.analyse(np.zeros(1000), synth.SR)


def test_layout_naming() -> None:
    assert hypothesis.layout_for(6) == hypothesis.LAYOUT_5_1
    assert hypothesis.layout_for(8) == hypothesis.LAYOUT_7_1
    assert hypothesis.layout_for(2) == ("L", "R")
