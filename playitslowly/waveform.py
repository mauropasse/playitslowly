# playitslowly/waveform.py
"""
WaveformExtractor: detailed waveform generator for Play it Slowly.

- Uses pydub (FFmpeg) to support MP3, WAV, FLAC, OGG, AAC, etc.
- Computes min/max amplitude envelopes for Cool Edit–style waveforms.
"""

import numpy as np

try:
  from pydub import AudioSegment
except ImportError:
  raise ImportError(
      "pydub not found. Install it with:\n  pip install pydub\n"
      "and ensure ffmpeg is installed (sudo apt install ffmpeg)"
  )


class WaveformExtractor:
    def __init__(self, filename):
        # Load using FFmpeg through pydub
        audio = AudioSegment.from_file(filename)
        samples = np.array(audio.get_array_of_samples(), dtype=np.float32)

        # Stereo → mono average
        if audio.channels > 1:
            samples = samples.reshape((-1, audio.channels))
            samples = samples.mean(axis=1)

        # Normalize to [-1, 1]
        max_amp = np.max(np.abs(samples))
        self.samples = samples / max_amp if max_amp > 0 else samples
        self.sample_rate = audio.frame_rate

    def get_samples(self, num_points=20000):
        """
        Return an interleaved min/max envelope array of roughly num_points length.
        This gives DAW-style visual richness.
        """
        samples = self.samples
        total = len(samples)
        if total == 0:
            return np.zeros(num_points, dtype=np.float32)

        # Compute window size; more points => more detail
        step = max(1, total // num_points)
        trimmed = samples[: step * (total // step)]
        reshaped = trimmed.reshape(-1, step)

        # Get per-window min and max
        mins = reshaped.min(axis=1)
        maxs = reshaped.max(axis=1)

        # Interleave for drawing: [min0, max0, min1, max1, ...]
        out = np.empty(mins.size * 2, dtype=np.float32)
        out[0::2] = mins
        out[1::2] = maxs

        # Slight smoothing to make waveform more visually natural
        out = np.convolve(out, np.ones(3)/3, mode='same')

        return out
