"""Diegesis command line.

    diegesis probe movie.mkv                 list audio streams
    diegesis test movie.mkv                  test the centre-channel hypothesis
    diegesis validate                        verify the test against ground truth
    diegesis extract movie.mkv -o out.wav    pull the centre channel
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf
import typer
from rich.console import Console
from rich.table import Table

from diegesis import audio as au
from diegesis import hypothesis, synth

app = typer.Typer(
    name="diegesis",
    help="Pull the voices out of the film.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


def _print_report(report: hypothesis.ChannelReport, title: str) -> None:
    console.print()
    console.print(f"[bold]{title}[/]")
    console.print(f"  {report.n_channels} channels ({', '.join(report.layout)})  "
                  f"{report.duration_s:.1f} s  {report.sample_rate} Hz")

    if report.centre_ratio_median is None:
        for note in report.notes:
            console.print(f"  [yellow]{note}[/]")
        return

    console.print(f"  {report.n_speech_frames} speech-active frames of "
                  f"{report.n_frames} ({report.speech_fraction:.0%})")
    console.print()

    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("centre ratio", justify="left")
    table.add_column("value", justify="right")
    table.add_row("median", f"{report.centre_ratio_median:.3f}")
    table.add_row("mean", f"{report.centre_ratio_mean:.3f}")
    table.add_row("p10 - p90",
                  f"{report.centre_ratio_p10:.3f} - {report.centre_ratio_p90:.3f}")
    table.add_row("frames > 0.5", f"{report.centre_locked_fraction:.1%}")
    console.print(table)

    if report.channel_energy_db:
        console.print()
        console.print("  speech-band energy by channel (dB)")
        peak = max(report.channel_energy_db.values())
        for name, db in report.channel_energy_db.items():
            bar = "#" * max(int((db - peak + 40) / 2), 0)
            console.print(f"    {name:<4} {db:8.1f}  {bar}")

    colour = {
        "strongly centre-locked": "green",
        "centre-dominant": "green",
        "centre-leaning": "yellow",
        "not centre-locked": "red",
    }.get(report.verdict, "white")
    console.print()
    console.print(f"  verdict: [{colour}]{report.verdict}[/]")
    for note in report.notes:
        console.print(f"  [dim]{note}[/]")


@app.command()
def probe(path: Path) -> None:
    """List audio streams in a media file."""
    streams = au.probe(path)
    if not streams:
        console.print("[red]no audio streams found[/]")
        raise typer.Exit(1)

    console.print(f"[bold]{path.name}[/]")
    for s in streams:
        marker = "[green]<- multichannel[/]" if s.is_multichannel else ""
        console.print(f"  {s}  {marker}")

    if not au.pick_multichannel(streams):
        console.print()
        console.print("[yellow]No multichannel stream. A stereo downmix has already "
                      "folded centre into L and R at about -3 dB, unrecoverably.[/]")


@app.command()
def test(
    path: Path,
    stream: int | None = typer.Option(None, help="audio stream index (default: widest)"),
    start: float = typer.Option(0.0, help="start offset, seconds"),
    duration: float | None = typer.Option(None, help="analyse only this many seconds"),
) -> None:
    """Test the centre-channel hypothesis on a real recording."""
    if stream is None:
        streams = au.probe(path)
        chosen = au.pick_multichannel(streams)
        if chosen is None:
            console.print("[red]No multichannel stream — the hypothesis is not "
                          "testable on this file.[/]")
            raise typer.Exit(1)
        stream = chosen.index
        console.print(f"[dim]using stream #{stream} ({chosen.channels}ch)[/]")

    samples, sr = au.load(path, stream_index=stream, start_s=start, duration_s=duration)
    _print_report(hypothesis.analyse(samples, sr), path.name)


@app.command()
def validate() -> None:
    """Verify the measurement against synthetic mixes with known ground truth.

    Run this before trusting any result on real film. On real film there is no
    answer key; here there is one by construction.
    """
    console.print("[bold]Validating the centre-channel measurement[/]")
    console.print("[dim]Synthetic 5.1 mixes with dialogue placed at a known ratio.[/]")

    cases = [
        (1.0, "all dialogue in centre", {}),
        (0.9, "mostly centre, slight L/R bleed", {}),
        (0.7, "centre with real bleed", {}),
        (0.5, "half centre, half spread", {}),
        (0.0, "no centre at all - dialogue in L/R", {}),
    ]

    table = Table(show_header=True, header_style="bold")
    table.add_column("mix")
    table.add_column("expected", justify="right")
    table.add_column("measured", justify="right")
    table.add_column("error", justify="right")
    table.add_column("verdict")

    ok = True
    for centre_ratio, label, kwargs in cases:
        mix, expected = synth.make_5_1(duration_s=30.0, centre_ratio=centre_ratio, **kwargs)
        report = hypothesis.analyse(mix, synth.SR)
        measured = report.centre_ratio_overall

        if measured is None:
            table.add_row(label, f"{expected:.2f}", "-", "-", "[red]failed[/]")
            ok = False
            continue

        error = abs(measured - expected)
        passed = error < 0.10
        ok &= passed
        table.add_row(
            label, f"{expected:.2f}", f"{measured:.2f}", f"{error:.2f}",
            "[green]ok[/]" if passed else "[red]off[/]",
        )

    console.print()
    console.print(table)

    # --- known confounds, measured rather than assumed away ------------------
    console.print()
    console.print("[bold]Known confounds[/] [dim](measured on a partly spread mix, "
                  "where bias is visible rather than hidden by the 1.0 ceiling)[/]")
    confounds = Table(show_header=True, header_style="bold")
    confounds.add_column("condition")
    confounds.add_column("truth", justify="right")
    confounds.add_column("measured", justify="right")
    confounds.add_column("bias", justify="right")

    for label, kwargs in [
        ("clean reference", {}),
        ("score swells with dialogue", {"swell": True}),
        ("score ducks under dialogue (-8 dB)", {"duck_db": 8.0}),
    ]:
        mix, expected = synth.make_5_1(duration_s=30.0, centre_ratio=0.5, **kwargs)
        report = hypothesis.analyse(mix, synth.SR)
        measured = report.centre_ratio_overall
        if measured is None:
            confounds.add_row(label, f"{expected:.2f}", "-", "-")
            continue
        bias = measured - expected
        confounds.add_row(label, f"{expected:.2f}", f"{measured:.2f}", f"{bias:+.2f}")

    console.print(confounds)
    console.print("[dim]Ducking biases the measurement upward: the score drops while "
                  "dialogue plays, so its contribution clips to zero. Real mixes duck, "
                  "so real results will overstate centre-locking somewhat.[/]")

    console.print()
    if ok:
        console.print("[green]Measurement is sound[/] — it tracks the planted centre "
                      "ratio across the range, including the case with no centre "
                      "content at all.")
    else:
        console.print("[red]Measurement is unreliable.[/] Do not trust results on "
                      "real film until this passes.")
        raise typer.Exit(1)


@app.command()
def extract(
    path: Path,
    out: Path = typer.Option(..., "-o", "--out", help="output WAV"),
    stream: int | None = typer.Option(None, help="audio stream index"),
) -> None:
    """Pull the centre channel out of a multichannel mix.

    Demultiplexing, not separation: no model, no artefacts, no inference.
    """
    if stream is None:
        chosen = au.pick_multichannel(au.probe(path))
        if chosen is None:
            console.print("[red]No multichannel stream to extract from.[/]")
            raise typer.Exit(1)
        stream = chosen.index

    samples, sr = au.load(path, stream_index=stream)
    centre = au.extract_centre(samples)
    sf.write(str(out), centre.astype(np.float32), sr)
    console.print(f"wrote [cyan]{out}[/]  ({len(centre) / sr:.1f} s, {sr} Hz, mono)")


@app.command()
def version() -> None:
    """Print the Diegesis version."""
    from diegesis import __version__

    console.print(f"Diegesis [green]{__version__}[/]")


if __name__ == "__main__":
    app()
