#!/usr/bin/env python3
"""
Generate a simple bell sound for prayer notifications.
Works with any Linux system.
"""

import struct
import math
import os
from pathlib import Path

def generate_wav_bell(filename, duration=0.5, frequency=523.25, volume=0.3):
    """
    Generate a simple WAV file with a bell-like tone.
    frequency: 523.25 Hz = C5 (middle C)
    """
    sample_rate = 44100
    num_samples = int(sample_rate * duration)

    with open(filename, 'wb') as f:
        # WAV header
        f.write(b'RIFF')
        f.write(struct.pack('<I', 36 + num_samples * 2))
        f.write(b'WAVE')
        f.write(b'fmt ')
        f.write(struct.pack('<I', 16))
        f.write(struct.pack('<H', 1))  # PCM
        f.write(struct.pack('<H', 1))  # Mono
        f.write(struct.pack('<I', sample_rate))
        f.write(struct.pack('<I', sample_rate * 2))
        f.write(struct.pack('<H', 2))
        f.write(struct.pack('<H', 16))
        f.write(b'data')
        f.write(struct.pack('<I', num_samples * 2))

        # Generate bell tone with exponential decay
        for i in range(num_samples):
            t = i / sample_rate
            # Bell-like sound: fundamental + harmonics with decay
            decay = math.exp(-5 * t)
            sample = (
                math.sin(2 * math.pi * frequency * t) * 0.5 +
                math.sin(2 * math.pi * frequency * 2 * t) * 0.3 +
                math.sin(2 * math.pi * frequency * 3 * t) * 0.15
            ) * volume * decay

            # Convert to 16-bit signed integer
            value = int(sample * 32767)
            f.write(struct.pack('<h', value))

def generate_athan_sound(filename):
    """Generate a longer, more melodic athan-like sound."""
    sample_rate = 44100
    duration = 3.0
    num_samples = int(sample_rate * duration)

    with open(filename, 'wb') as f:
        # WAV header
        f.write(b'RIFF')
        f.write(struct.pack('<I', 36 + num_samples * 2))
        f.write(b'WAVE')
        f.write(b'fmt ')
        f.write(struct.pack('<I', 16))
        f.write(struct.pack('<H', 1))
        f.write(struct.pack('<H', 1))
        f.write(struct.pack('<I', sample_rate))
        f.write(struct.pack('<I', sample_rate * 2))
        f.write(struct.pack('<H', 2))
        f.write(struct.pack('<H', 16))
        f.write(b'data')
        f.write(struct.pack('<I', num_samples * 2))

        # Simple melodic pattern (ascending notes)
        notes = [261.63, 293.66, 329.63, 349.23, 392.00, 440.00, 523.25]  # C4 to C5
        note_duration = duration / len(notes)

        for note_idx, frequency in enumerate(notes):
            note_samples = int(sample_rate * note_duration)
            start_sample = note_idx * note_samples

            for i in range(note_samples):
                t = i / sample_rate
                sample_idx = start_sample + i

                if sample_idx >= num_samples:
                    break

                # Exponential decay for each note
                decay = math.exp(-3 * t)
                sample = math.sin(2 * math.pi * frequency * t) * 0.3 * decay

                value = int(sample * 32767)
                f.write(struct.pack('<h', value))

if __name__ == "__main__":
    config_dir = Path.home() / ".config" / "openAthan"
    config_dir.mkdir(parents=True, exist_ok=True)

    bell_file = config_dir / "bell.wav"
    athan_file = config_dir / "athan.wav"

    print(f"Generating {bell_file}...")
    generate_wav_bell(str(bell_file))

    print(f"Generating {athan_file}...")
    generate_athan_sound(str(athan_file))

    print("Done! Sound files created.")
    print(f"  - {bell_file}")
    print(f"  - {athan_file}")
