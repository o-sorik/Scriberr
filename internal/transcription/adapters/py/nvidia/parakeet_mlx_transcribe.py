#!/usr/bin/env python3
"""
Parakeet MLX transcription script for Apple Silicon.
Uses parakeet-mlx package for ultra-fast (~51x realtime) transcription.

Audio is chunked into 60-second pieces with 3-second overlap to avoid
the hanging issue with long files. Overlap regions are deduplicated
by comparing word timestamps.
"""

import argparse
import json
import os
import sys
import tempfile
import time

import numpy as np
import soundfile as sf


def chunk_and_transcribe(audio_path, model, chunk_sec=60, overlap_sec=3):
    """
    Read audio, split into overlapping chunks, transcribe each chunk,
    and merge results with deduplication in overlap regions.
    """
    data, sr = sf.read(audio_path, dtype="float32")

    # If stereo, convert to mono
    if data.ndim > 1:
        data = data.mean(axis=1)

    total_samples = len(data)
    chunk_samples = chunk_sec * sr
    overlap_samples = overlap_sec * sr
    step_samples = chunk_samples - overlap_samples

    all_words = []
    all_segments = []
    full_text_parts = []

    chunk_idx = 0
    pos = 0

    while pos < total_samples:
        end = min(pos + chunk_samples, total_samples)
        chunk_data = data[pos:end]

        # Write chunk to temp file
        chunk_path = os.path.join(tempfile.gettempdir(), f"parakeet_mlx_chunk_{chunk_idx}.wav")
        sf.write(chunk_path, chunk_data, sr)

        try:
            result = model.transcribe(chunk_path)
        finally:
            # Clean up chunk file
            if os.path.exists(chunk_path):
                os.remove(chunk_path)

        chunk_offset = pos / sr  # Time offset for this chunk in seconds

        # Extract text
        chunk_text = result.text if hasattr(result, "text") else str(result)

        # Extract word timestamps from sentences -> tokens (subwords -> words)
        chunk_words = []
        if hasattr(result, "sentences") and result.sentences:
            for sentence in result.sentences:
                if not hasattr(sentence, "tokens") or not sentence.tokens:
                    continue
                # Merge subword tokens into words (tokens starting with space = new word)
                current_word = ""
                word_start = None
                word_end = None
                for tok in sentence.tokens:
                    tok_text = tok.text if hasattr(tok, "text") else str(tok)
                    tok_start = (tok.start if hasattr(tok, "start") else 0.0) + chunk_offset
                    tok_end = (tok.end if hasattr(tok, "end") else 0.0) + chunk_offset
                    if tok_text.startswith(" ") and current_word:
                        # Flush previous word
                        chunk_words.append({
                            "word": current_word.strip(),
                            "start": round(word_start, 3),
                            "end": round(word_end, 3),
                        })
                        current_word = tok_text
                        word_start = tok_start
                        word_end = tok_end
                    else:
                        if word_start is None:
                            word_start = tok_start
                        current_word += tok_text
                        word_end = tok_end
                # Flush last word
                if current_word.strip():
                    chunk_words.append({
                        "word": current_word.strip(),
                        "start": round(word_start, 3),
                        "end": round(word_end, 3),
                    })

        # Deduplicate words in overlap region
        if chunk_idx > 0 and all_words and chunk_words:
            overlap_boundary = pos / sr  # Start time of this chunk in global time
            # Remove words from new chunk that fall within the overlap region
            # (they were already captured by the previous chunk)
            filtered = []
            for w in chunk_words:
                if w["start"] >= overlap_boundary + overlap_sec * 0.5:
                    filtered.append(w)
            chunk_words = filtered

            # Also trim text: only add text for non-overlapping portion
            # (we rely on word timestamps for accurate text reconstruction)

        all_words.extend(chunk_words)
        full_text_parts.append(chunk_text)

        # Build segment for this chunk
        if chunk_words:
            seg_start = chunk_words[0]["start"]
            seg_end = chunk_words[-1]["end"]
            seg_text = " ".join(w["word"] for w in chunk_words)
        else:
            seg_start = chunk_offset
            seg_end = chunk_offset + len(chunk_data) / sr
            seg_text = chunk_text

        if seg_text.strip():
            all_segments.append({
                "text": seg_text.strip(),
                "start": round(seg_start, 3),
                "end": round(seg_end, 3),
            })

        chunk_idx += 1
        pos += step_samples

        if pos >= total_samples:
            break

    # Build full text from words if available, otherwise join chunk texts
    if all_words:
        full_text = " ".join(w["word"] for w in all_words)
    else:
        full_text = " ".join(full_text_parts)

    return full_text.strip(), all_words, all_segments


def transcribe_audio(audio_path, output_file=None, model_name="mlx-community/parakeet-tdt-0.6b-v3"):
    """
    Transcribe audio using parakeet-mlx.
    Chunks audio into 60-second pieces to avoid hanging on long files.
    """
    start_time = time.time()

    print(f"Loading parakeet-mlx model: {model_name}")
    from parakeet_mlx import from_pretrained
    model = from_pretrained(model_name)
    print(f"Model loaded in {time.time() - start_time:.1f}s")

    # Check audio duration to decide if chunking is needed
    info = sf.info(audio_path)
    duration = info.duration
    print(f"Audio duration: {duration:.1f}s")

    if duration <= 90:
        # Short audio: transcribe directly (no chunking needed)
        print("Short audio, transcribing directly...")
        result = model.transcribe(audio_path)

        text = result.text if hasattr(result, "text") else str(result)

        word_timestamps = []
        if hasattr(result, "sentences") and result.sentences:
            for sentence in result.sentences:
                if not hasattr(sentence, "tokens") or not sentence.tokens:
                    continue
                current_word = ""
                word_start = None
                word_end = None
                for tok in sentence.tokens:
                    tok_text = tok.text if hasattr(tok, "text") else str(tok)
                    tok_start = tok.start if hasattr(tok, "start") else 0.0
                    tok_end = tok.end if hasattr(tok, "end") else 0.0
                    if tok_text.startswith(" ") and current_word:
                        word_timestamps.append({
                            "word": current_word.strip(),
                            "start": round(word_start, 3),
                            "end": round(word_end, 3),
                        })
                        current_word = tok_text
                        word_start = tok_start
                        word_end = tok_end
                    else:
                        if word_start is None:
                            word_start = tok_start
                        current_word += tok_text
                        word_end = tok_end
                if current_word.strip():
                    word_timestamps.append({
                        "word": current_word.strip(),
                        "start": round(word_start, 3),
                        "end": round(word_end, 3),
                    })

        segment_timestamps = []
        if word_timestamps:
            segment_timestamps.append({
                "text": text.strip(),
                "start": word_timestamps[0]["start"],
                "end": word_timestamps[-1]["end"],
            })
        else:
            segment_timestamps.append({
                "text": text.strip(),
                "start": 0.0,
                "end": duration,
            })
    else:
        # Long audio: chunk and transcribe
        print(f"Long audio ({duration:.0f}s), chunking into 60s pieces with 3s overlap...")
        text, word_timestamps, segment_timestamps = chunk_and_transcribe(
            audio_path, model, chunk_sec=60, overlap_sec=3
        )

    processing_time = time.time() - start_time
    realtime_factor = duration / processing_time if processing_time > 0 else 0

    print(f"Transcription complete: {processing_time:.1f}s ({realtime_factor:.1f}x realtime)")

    output_data = {
        "transcription": text.strip() if isinstance(text, str) else str(text).strip(),
        "task": "transcribe",
        "source_language": "auto",
        "target_language": "auto",
        "word_timestamps": word_timestamps,
        "segment_timestamps": segment_timestamps,
        "processing_time": round(processing_time, 3),
        "audio_file": audio_path,
        "model": model_name,
    }

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"Results saved to: {output_file}")
    else:
        print(json.dumps(output_data, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe audio using Parakeet MLX (Apple Silicon)"
    )
    parser.add_argument("audio_file", help="Path to audio file")
    parser.add_argument(
        "--output", "-o", help="Output file path for JSON result"
    )
    parser.add_argument(
        "--model",
        default="mlx-community/parakeet-tdt-0.6b-v3",
        help="Model name (default: mlx-community/parakeet-tdt-0.6b-v3)",
    )

    args = parser.parse_args()

    if not os.path.exists(args.audio_file):
        print(f"Error: Audio file not found: {args.audio_file}")
        sys.exit(1)

    try:
        transcribe_audio(
            audio_path=args.audio_file,
            output_file=args.output,
            model_name=args.model,
        )
    except Exception as e:
        print(f"Error during transcription: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
