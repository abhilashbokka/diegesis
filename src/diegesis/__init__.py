"""Diegesis — pull the voices out of the film.

Separating dialogue from music and effects in cinematic audio. The starting
position is that much of this is not a separation problem: film audio is mixed
to conventions, and in 5.1 the centre channel carries dialogue by convention.
Taking it is demultiplexing, not inference — free, and without artefacts.

`hypothesis` measures how far that convention actually holds, which is the
question everything else depends on.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
