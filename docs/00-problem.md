# 00 — The Problem

Record of the framing discussion, 2026-08-01.

## The goal

Take a finished film audio mix, recover a clean dialogue track, and from it produce a highly accurate transcript or subtitle file.

Transcribing the raw mix fails in a specific and annoying way: music and effects are loudest exactly when the dialogue matters most, because dramatic scenes are mixed loud. So word error rate degrades precisely where accuracy is most needed.

## "Why can't it just be a diff?"

The question is a good one, and the answer is worth understanding in full because it shows where the exploitable structure is.

### 1. You don't have both operands

`diff` recovers B from A and A+B. A film mix gives you only the sum. If you *had* the isolated music stem, subtraction would largely work — which is the whole basis of the M&E route below.

### 2. The problem is underdetermined

At each time-frequency bin you have one observed value and two unknowns (voice energy, music energy). Voice and music occupy the same bins at the same time. No arithmetic un-sums one number into two.

Separation must therefore *infer*, using learned priors about what speech and music look like in time-frequency. That is why the field uses trained models rather than DSP.

### 3. The mix is not linear addition

This is the part that surprises people. Film audio passes through:

- per-stem EQ, compression, reverb
- **dialogue ducking** — the score's gain is automatically reduced when dialogue is present, so the music signal in the mix *depends on the dialogue signal*
- bus compression and limiting across the whole mix
- loudness normalisation
- a lossy delivery codec (AC-3, DTS, AAC) that discards perceptually masked content

So `mix ≠ music + dialogue`. It is `f(music, dialogue)`, where f is non-linear and time-varying. Even with a perfect music stem, subtraction leaves residue — and the codec has destroyed information permanently.

### 4. Phase is unforgiving

Cancellation requires sample-accurate alignment. Sub-sample offsets, resampling, or any pitch drift turn cancellation into comb filtering. Two signals that "sound identical" can fail to cancel completely.

## The structural shortcuts

Film audio is not arbitrary — it is mixed to conventions, and those conventions are exploitable.

### Centre channel — the big one

Films are mixed for 5.1/7.1. **By long-standing convention, dialogue is placed almost exclusively in the centre channel.** The other channels carry score, ambience and effects.

So with a multichannel source you do not separate anything. You demultiplex:

```
5.1 channel order (SMPTE): L  R  C  LFE  Ls  Rs
                                    ^
                                 dialogue
```

This beats any neural separator: no artefacts, no inference, no training, effectively free. **Any pipeline that downmixes to stereo before separating has discarded the answer before starting.**

Caveats worth measuring rather than assuming: loud effects and music do bleed into centre; some mixes place dialogue more widely for stylistic reasons; and musicals or heavily scored sequences break the convention. Quantifying *how often and how badly* the convention holds across real films would itself be a useful contribution — nobody seems to have published it.

### Mid/side — the stereo fallback

For stereo-only sources:

```
M = (L + R) / 2      isolates centre-panned content (dialogue-ish)
S = (L - R) / 2      removes it (the karaoke trick)
```

Literally the "diff" intuition, and it works partially. Degrades when the mix is wide or when music is also centre-panned.

### M&E stems — the diff that actually exists

Films produce **Music & Effects** tracks: the full mix minus dialogue, used for dubbing into other languages. Where both the full mix and the M&E track are available:

```
dialogue ≈ full_mix − M&E
```

subject to the non-linearity and phase caveats above. This is exactly the diff originally imagined, and it exists as a standard deliverable in film post-production.

Two consequences:

1. **Ground truth.** Mix/M&E pairs give real supervision from real mixes — which is what DnR's artificial mixtures lack.
2. **A research problem.** Learning to invert the mastering non-linearity so subtraction *does* work cleanly is concrete and well-posed.

## The reframe for subtitles

The stated goal is accurate subtitles, and separation may not be the shortest path.

If a **screenplay or existing subtitle file exists**, the task changes from *recognition* (open-vocabulary, error-prone) to *forced alignment* (known text, find the timings). Alignment is dramatically more accurate and more robust to noise, because the model is no longer guessing words.

A realistic pipeline that probably beats any separation-first approach:

```
5.1 source → centre channel → ASR → align against screenplay → subtitles
```

Separation becomes a fallback for when no script exists, or a pre-processing step to help alignment in dense scenes — not the main mechanism.

**Sluglint already parses screenplays**, which makes the alignment half substantially cheaper to build than it would otherwise be.

## Open questions

- How often does the centre-channel convention actually hold? Needs measuring across a real corpus.
- How much dialogue bleeds into L/R, and does it matter for ASR?
- Does separation help ASR *at all* once you have the centre channel, or does it only add artefacts?
- Where does forced alignment break down — overlapping dialogue, ad-libs, unscripted lines?
