#!/usr/bin/env python3
"""
FoxNoseTech diarize — fast speaker diarization without HuggingFace token.
~8x faster than pyannote on CPU, no API keys required.
"""

import argparse
import json
import os
import sys
import time


def diarize_audio(audio_path, output_file, min_speakers=None, max_speakers=None, num_speakers=None):
    """Perform speaker diarization using FoxNoseTech/diarize."""
    from diarize import diarize

    print(f"Processing: {audio_path}")
    start_time = time.time()

    kwargs = {}
    if num_speakers is not None:
        kwargs["num_speakers"] = num_speakers
    else:
        if min_speakers is not None:
            kwargs["min_speakers"] = min_speakers
        if max_speakers is not None:
            kwargs["max_speakers"] = max_speakers

    result = diarize(audio_path, **kwargs)

    elapsed = time.time() - start_time
    print(f"Diarization completed in {elapsed:.1f}s")

    # Build JSON output
    segments = []
    speakers = set()

    for seg in result.segments:
        speakers.add(seg.speaker)
        segments.append({
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "speaker": seg.speaker,
            "confidence": 1.0,
            "duration": round(seg.end - seg.start, 3),
        })

    segments.sort(key=lambda x: x["start"])

    output = {
        "audio_file": audio_path,
        "model": "foxnose/diarize",
        "segments": segments,
        "speakers": sorted(speakers),
        "speaker_count": len(speakers),
        "total_duration": max(s["end"] for s in segments) if segments else 0,
        "processing_info": {
            "total_segments": len(segments),
            "total_speech_time": sum(s["duration"] for s in segments),
            "processing_time": round(elapsed, 2),
        },
    }

    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Speakers: {len(speakers)}, Segments: {len(segments)}")
    print(f"Saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Speaker diarization via FoxNoseTech/diarize")
    parser.add_argument("audio_file", help="Path to audio file")
    parser.add_argument("--output", "-o", required=True, help="Output JSON file path")
    parser.add_argument("--min-speakers", type=int, help="Minimum number of speakers")
    parser.add_argument("--max-speakers", type=int, help="Maximum number of speakers")
    parser.add_argument("--num-speakers", type=int, help="Exact number of speakers")

    args = parser.parse_args()

    if not os.path.exists(args.audio_file):
        print(f"Error: File not found: {args.audio_file}")
        sys.exit(1)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    diarize_audio(
        args.audio_file,
        args.output,
        min_speakers=args.min_speakers,
        max_speakers=args.max_speakers,
        num_speakers=args.num_speakers,
    )


if __name__ == "__main__":
    main()
