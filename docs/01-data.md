# 01 — Data

Where to get multichannel film audio legally, how much is needed, and how to extract it.

## The licensing position

Same as any film-audio research: **you can publish the research, not the data.**

Distribute pointers, timestamps and extracted features — never source audio. This is standard practice for speech and music benchmarks built on copyrighted material, and it keeps the work citable without a licensing problem:

```
benchmark/
  sources.yaml      # title, edition, track index, timestamps, checksums
  features/         # extracted acoustic features — redistributable
  protocol.md
  # no audio, ever
```

The exception is open-licensed content, which can be redistributed freely — and there is more of it than expected.

## Open-licensed multichannel sources

These are the ones to build on. All permit redistribution.

### Netflix Open Content — the best lead

[opencontent.netflix.com](https://opencontent.netflix.com/), CC BY 4.0.

- **Sol Levante** — a 4K HDR Dolby Atmos anime short. Critically, Netflix released **the final Pro Tools mixing and mastering sessions**, not just the finished mix. That means *individual stems*: dialogue, music and effects as separate tracks, from a real professional production.

  **This is ground truth, openly licensed.** It is the M&E route without the access problem. An Atmos master also derives 7.1, 5.1 and stereo from one mix, so you can generate matched multichannel/stereo pairs and study exactly what downmixing destroys.

- **Meridian** — a short film released as codec test material, deliberately containing hard-to-encode content.

### Blender Open Movies

CC BY, downloadable in full quality.

- **[Tears of Steel](https://mango.blender.org/download/)** — confirmed **Dolby 5.1**, 4K, CC BY. Live action plus CG, with real dialogue, score and effects.
- **Sintel**, **Big Buck Bunny**, **Elephants Dream**, **Spring**, **Coffee Run**, **Charge** — varying audio configurations, worth checking each.

Some Blender productions publish full production files, which may include audio project files and stems. Worth digging: another potential ground-truth source.

### Internet Archive

Public-domain films. Mostly older, so mostly mono or stereo — useful for the "no multichannel available" fallback case, less so for the spatial work.

## How much data do you need?

This depends entirely on what role the data plays, and getting the framing right is what makes the project feasible.

| Purpose | Realistic requirement |
| --- | --- |
| Train a separation model from scratch | 100+ hours |
| Fine-tune an existing model (Demucs, BSRNN) | 10–50 hours |
| **Evaluation set only** | **2–5 hours** |

**Use DnR for training and real multichannel film for evaluation.** DnR exists, is free, and is designed for exactly this task. Real film audio then becomes the domain-shift test — *does a model trained on artificial mono mixtures survive contact with real multichannel cinema?*

That framing changes the project's difficulty completely. You are not assembling a new training corpus; you are assembling a **few hours of carefully chosen evaluation material**, which open-licensed content alone can supply. The contribution lives in the method and the evaluation, not in data volume.

If the spatial angle needs training data, Sol Levante's stems plus Atmos-derived downmixes can generate a large amount of matched multichannel material from a small amount of source — the spatial configurations are derivable, not collectable.

## Extracting audio from video

Yes, you extract from the container. Standard `ffmpeg` work.

**Inspect what's actually there first** — never assume a file is 5.1:

```bash
ffprobe -v error -select_streams a \
  -show_entries stream=index,codec_name,channels,channel_layout,sample_rate \
  -of default=noprint_wrappers=1 movie.mkv
```

**Extract the centre channel** (5.1 order is `L R C LFE Ls Rs`, so centre is index 2):

```bash
ffmpeg -i movie.mkv -filter_complex "[0:a]pan=mono|c0=c2[out]" \
  -map "[out]" -c:a pcm_s24le center.wav
```

**Split every channel** at once:

```bash
ffmpeg -i movie.mkv -filter_complex \
  "channelsplit=channel_layout=5.1[FL][FR][FC][LFE][SL][SR]" \
  -map "[FL]" fl.wav -map "[FR]" fr.wav -map "[FC]" fc.wav \
  -map "[LFE]" lfe.wav -map "[SL]" sl.wav -map "[SR]" sr.wav
```

Notes that matter in practice:

- **Blu-ray** carries DTS-HD MA or Dolby TrueHD 5.1/7.1 — genuine multichannel. **Streaming services are DRM-protected**; extracting from them is not a legal route.
- Many MKVs carry several audio tracks (commentary, other languages, stereo downmix). Select deliberately by stream index.
- Decode to **PCM** for analysis. Never analyse the lossy bitstream.
- A stereo downmix folds centre into L and R at roughly −3 dB. Once downmixed, the separation is unrecoverable — check for a true multichannel track before doing anything else.

## Can songs be used instead?

Partly, and it's worth being precise about where the analogy holds.

**Music source separation is a mature, well-resourced neighbour.** [MUSDB18 / MUSDB18-HQ](https://sigsep.github.io/datasets/musdb.html) is the standard benchmark: 150 tracks with isolated **vocals / drums / bass / other** stems, free for research. Real ground truth, real mixes, no licensing problem. Models like Demucs and BSRNN are trained on it.

**Where it helps:**
- Pretraining, then fine-tuning on cinematic audio.
- Building and debugging the pipeline with real stems before touching film.
- The music-separation component of a dialogue/music/effects split.

**Where the analogy breaks:**
- The task differs. Music separation splits *vocals from instruments* — a singing voice over musical accompaniment. CASS splits *dialogue from music and effects*, where speech is conversational, overlapping and often quiet, and "effects" is an enormously varied class.
- **Music 5.1 mixes follow no centre-dialogue convention.** SACD, DVD-Audio, Blu-ray Audio and Atmos music exist, but vocals are not reliably centre-locked. The single most useful structural prior in film simply does not transfer.
- Music has no equivalent of the M&E stem or the screenplay.

**Verdict:** use MUSDB18 to build and validate the machinery, and for pretraining. Do not treat it as a substitute for cinematic evaluation data — the structural priors that make the film problem interesting are exactly what music lacks.

## Suggested starting set

Enough to begin, all legally clean:

1. **Sol Levante** — stems and Pro Tools sessions. Ground truth.
2. **Tears of Steel** — confirmed 5.1, real dialogue over score. The spatial test case.
3. **DnR v2/v3** — training and comparison against published baselines.
4. **MUSDB18-HQ** — pipeline development and pretraining.
5. A handful of commercially-owned Blu-rays for the private evaluation set, reported as features and pointers only.
