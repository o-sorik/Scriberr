#!/usr/bin/env python3
"""
Transcription post-processing: apply dictionary corrections to raw transcripts.

Usage:
    # Apply corrections to a transcript
    python postprocess.py clean raw_transcript.txt -o cleaned.txt
    python postprocess.py clean raw_transcript.txt --dry-run

    # Diff raw vs corrected to learn new patterns
    python postprocess.py diff raw.txt corrected.txt

    # Show dictionary stats
    python postprocess.py stats
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path


DICTIONARY_PATH = os.environ.get(
    "TRANSCRIPTION_DICTIONARY",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "transcription_dictionary.md")
)


@dataclass
class DictEntry:
    raw: str
    correct: str
    context: str  # empty = always apply
    model: str
    category: str  # "direct", "name", "context", "tech"


def load_dictionary(path: str = DICTIONARY_PATH) -> list[DictEntry]:
    """Parse transcription_dictionary.md into entries."""
    entries = []
    if not os.path.exists(path):
        print(f"Warning: Dictionary not found at {path}")
        return entries

    current_category = "direct"
    in_code_block = False

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip()

            # Track category from headers
            if "## Direct Substitution" in line:
                current_category = "direct"
            elif "## Company" in line or "## Product" in line:
                current_category = "name"
            elif "## People" in line:
                current_category = "name"
            elif "## Context-Dependent" in line:
                current_category = "context"
            elif "## Tech Terms" in line:
                current_category = "tech"

            # Track code blocks
            if line.strip() == "```":
                in_code_block = not in_code_block
                continue

            if not in_code_block:
                continue

            # Parse entry: raw | correct | context | model
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 2:
                continue

            raw = parts[0]
            correct = parts[1]
            context = parts[2] if len(parts) > 2 else ""
            model = parts[3] if len(parts) > 3 else "any"

            if not raw or not correct:
                continue
            if correct.lower() == "ok":
                continue

            entries.append(DictEntry(
                raw=raw,
                correct=correct,
                context=context,
                model=model,
                category=current_category,
            ))

    return entries


def check_context(text: str, position: int, context_hint: str, window: int = 100) -> bool:
    """Check if context hint matches surrounding text."""
    if not context_hint:
        return True  # No context required = always match

    # Get surrounding text
    start = max(0, position - window)
    end = min(len(text), position + window)
    surrounding = text[start:end].lower()

    # Split context hint by / or , for multiple keywords
    keywords = [k.strip().lower() for k in re.split(r'[/,]', context_hint)]
    return any(kw in surrounding for kw in keywords)


def apply_dictionary(text: str, entries: list[DictEntry], model_filter: str = "",
                     dry_run: bool = False) -> tuple[str, list[dict]]:
    """
    Apply dictionary corrections to text.
    Returns (corrected_text, list_of_changes).
    """
    changes = []

    for entry in entries:
        # Filter by model if specified
        if model_filter and entry.model not in ("both", "any", model_filter):
            continue

        # Build regex pattern (case-insensitive, word boundary)
        pattern = re.compile(r'\b' + re.escape(entry.raw) + r'\b', re.IGNORECASE)

        for match in pattern.finditer(text):
            # Check context
            if not check_context(text, match.start(), entry.context):
                continue

            changes.append({
                "position": match.start(),
                "raw": match.group(),
                "correct": entry.correct,
                "context_hint": entry.context,
                "category": entry.category,
            })

    if dry_run:
        return text, changes

    # Apply changes in reverse order (to preserve positions)
    changes.sort(key=lambda c: c["position"], reverse=True)
    result = text
    for change in changes:
        pos = change["position"]
        raw_len = len(change["raw"])
        result = result[:pos] + change["correct"] + result[pos + raw_len:]

    # Re-sort changes by position for reporting
    changes.sort(key=lambda c: c["position"])
    return result, changes


def diff_transcripts(raw_path: str, corrected_path: str, dictionary_path: str = DICTIONARY_PATH) -> list[dict]:
    """
    Compare raw and corrected transcripts, extract new patterns.
    Returns list of new patterns found.
    """
    with open(raw_path, "r", encoding="utf-8") as f:
        raw_lines = f.readlines()
    with open(corrected_path, "r", encoding="utf-8") as f:
        corrected_lines = f.readlines()

    # Load existing dictionary to check for duplicates
    existing = load_dictionary(dictionary_path)
    existing_raws = {e.raw.lower() for e in existing}

    new_patterns = []

    # Simple word-level diff
    raw_words = []
    for line in raw_lines:
        raw_words.extend(line.split())
    corrected_words = []
    for line in corrected_lines:
        corrected_words.extend(line.split())

    # Use difflib for alignment
    import difflib
    matcher = difflib.SequenceMatcher(None, raw_words, corrected_words)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "replace":
            raw_phrase = " ".join(raw_words[i1:i2])
            correct_phrase = " ".join(corrected_words[j1:j2])

            if raw_phrase.lower() == correct_phrase.lower():
                continue  # Just capitalization

            # Check if already in dictionary
            if raw_phrase.lower() in existing_raws:
                continue

            # Get context (5 words before and after)
            ctx_before = " ".join(raw_words[max(0, i1-5):i1])
            ctx_after = " ".join(raw_words[i2:min(len(raw_words), i2+5)])

            new_patterns.append({
                "raw": raw_phrase,
                "correct": correct_phrase,
                "context_before": ctx_before,
                "context_after": ctx_after,
                "type": "replace",
            })

    return new_patterns


def append_to_dictionary(patterns: list[dict], dictionary_path: str = DICTIONARY_PATH):
    """Append new patterns to the dictionary file."""
    if not patterns:
        return

    with open(dictionary_path, "a", encoding="utf-8") as f:
        f.write("\n\n## Auto-discovered patterns\n```\n")
        for p in patterns:
            context = ""
            if p.get("context_before") or p.get("context_after"):
                # Try to extract a context keyword
                words = (p.get("context_before", "") + " " + p.get("context_after", "")).split()
                if words:
                    context = f"near: {' '.join(words[:3])}"
            f.write(f"{p['raw']} | {p['correct']} | {context} | unknown\n")
        f.write("```\n")


def cmd_clean(args):
    """Apply dictionary to clean a transcript."""
    entries = load_dictionary(args.dictionary)
    print(f"Loaded {len(entries)} dictionary entries from {args.dictionary}")

    with open(args.transcript, "r", encoding="utf-8") as f:
        text = f.read()

    corrected, changes = apply_dictionary(
        text, entries,
        model_filter=args.model or "",
        dry_run=args.dry_run,
    )

    # Report changes
    if changes:
        print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Found {len(changes)} corrections:")
        for c in changes:
            print(f"  [{c['category']}] \"{c['raw']}\" → \"{c['correct']}\""
                  f"{' (context: ' + c['context_hint'] + ')' if c['context_hint'] else ''}")
    else:
        print("No corrections found.")

    if not args.dry_run:
        output_path = args.output or args.transcript
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(corrected)
        print(f"\nSaved to: {output_path}")


def cmd_clean_json(args):
    """Apply dictionary to a JSON transcript (stdin/stdout, for Scriberr integration).

    Reads JSON from stdin with structure:
        {"text": "...", "segments": [...], "word_segments": [...], "model": "..."}
    Applies corrections to text, segment texts, and word texts.
    Writes corrected JSON to stdout.
    """
    entries = load_dictionary(args.dictionary)
    if not entries:
        # No dictionary — pass through unchanged
        sys.stdout.write(sys.stdin.read())
        return

    data = json.load(sys.stdin)
    model_filter = data.get("model", "")
    total_changes = 0

    # 1. Correct top-level text
    if data.get("text"):
        data["text"], changes = apply_dictionary(data["text"], entries, model_filter=model_filter)
        total_changes += len(changes)

    # 2. Correct segment texts
    for seg in data.get("segments", []):
        if seg.get("text"):
            seg["text"], changes = apply_dictionary(seg["text"], entries, model_filter=model_filter)
            total_changes += len(changes)

    # 3. Correct individual words
    for word in data.get("word_segments", []):
        if word.get("word"):
            corrected, changes = apply_dictionary(word["word"], entries, model_filter=model_filter)
            if changes:
                word["word"] = corrected
                total_changes += len(changes)

    # Write result + stats to stderr for logging
    print(f"Postprocess: {len(entries)} dict entries, {total_changes} corrections applied", file=sys.stderr)
    json.dump(data, sys.stdout, ensure_ascii=False)


OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")

LLM_SYSTEM_PROMPT = """Ти — коректор українських транскрипцій робочих мітингів. Тобі дано транскрипт з ASR з помилками розпізнавання.

Виправляй ТІЛЬКИ помилки розпізнавання:
- Неправильно розпізнані слова (наприклад: геймерит→гаймерит, обзвів→обдзвонив, ворогом→горлом)
- Злиті або розбиті слова
- Абракадабру яка має бути реальним словом — вгадай з контексту

НЕ змінюй:
- Таймстемпи [X:XX]
- Імена спікерів
- Розмовний стиль і слова-паразити (типу, коротше, ну)
- Правильно розпізнані слова

Поверни ТІЛЬКИ виправлений транскрипт, без коментарів і пояснень."""


def call_ollama(prompt: str, system: str = LLM_SYSTEM_PROMPT, model: str = OLLAMA_MODEL) -> str | None:
    """Call Ollama API. Returns response text or None on failure."""
    payload = json.dumps({
        "model": model,
        "system": system,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 8192},
    }).encode()

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read())
            return result.get("response", "")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        print(f"Ollama error: {e}", file=sys.stderr)
        return None


def llm_correct_segments(segments: list[dict]) -> list[dict]:
    """Send segments to Ollama for contextual correction. Returns corrected segments."""
    if not segments:
        return segments

    # Build formatted text from segments
    lines = []
    for seg in segments:
        speaker = seg.get("speaker", "")
        ts = seg.get("start", 0)
        mins = int(ts) // 60
        secs = int(ts) % 60
        prefix = f"[{mins}:{secs:02d}]"
        if speaker:
            prefix += f" {speaker}:"
        lines.append(f"{prefix} {seg.get('text', '')}")

    formatted = "\n".join(lines)

    # Call Ollama
    corrected_text = call_ollama(formatted)
    if not corrected_text:
        return segments

    # Parse corrected lines back into segments
    corrected_lines = [l.strip() for l in corrected_text.strip().split("\n") if l.strip()]

    # Match corrected lines back to segments by index
    # (LLM should preserve same number of lines)
    if len(corrected_lines) != len(segments):
        print(f"LLM returned {len(corrected_lines)} lines vs {len(segments)} segments — "
              f"falling back to original", file=sys.stderr)
        return segments

    corrected_segments = []
    for seg, line in zip(segments, corrected_lines):
        new_seg = dict(seg)
        # Strip timestamp and speaker prefix to get just the text
        text = re.sub(r'^\[\d+:\d+\]\s*(?:\S+:)?\s*', '', line)
        new_seg["text"] = text
        corrected_segments.append(new_seg)

    return corrected_segments


def cmd_llm_clean_json(args):
    """Apply LLM (Ollama) corrections to a JSON transcript (stdin/stdout).

    Reads the same JSON format as clean-json. Sends segments to Ollama for
    contextual correction, then rebuilds text and word segments.
    """
    data = json.load(sys.stdin)

    segments = data.get("segments", [])
    if not segments:
        print("LLM postprocess: no segments, skipping", file=sys.stderr)
        json.dump(data, sys.stdout, ensure_ascii=False)
        return

    # Check Ollama availability
    try:
        urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3)
    except (urllib.error.URLError, TimeoutError):
        print("LLM postprocess: Ollama not available, skipping", file=sys.stderr)
        json.dump(data, sys.stdout, ensure_ascii=False)
        return

    print(f"LLM postprocess: sending {len(segments)} segments to {OLLAMA_MODEL}...", file=sys.stderr)

    corrected = llm_correct_segments(segments)

    # Count changes
    changes = sum(1 for s, c in zip(segments, corrected) if s.get("text") != c.get("text"))

    # Update segments
    data["segments"] = corrected

    # Rebuild top-level text from corrected segments
    data["text"] = " ".join(seg.get("text", "") for seg in corrected)

    print(f"LLM postprocess: {changes} segments corrected by {OLLAMA_MODEL}", file=sys.stderr)
    json.dump(data, sys.stdout, ensure_ascii=False)


def cmd_diff(args):
    """Diff raw vs corrected to learn new patterns."""
    new_patterns = diff_transcripts(args.raw, args.corrected, args.dictionary)

    if not new_patterns:
        print("No new patterns found — dictionary already covers all corrections.")
        return

    print(f"Found {len(new_patterns)} new patterns:\n")
    for p in new_patterns:
        print(f"  \"{p['raw']}\" → \"{p['correct']}\"")
        if p.get("context_before"):
            print(f"    context: ...{p['context_before']} [{p['raw']}] {p.get('context_after', '')}...")

    if not args.dry_run:
        append_to_dictionary(new_patterns, args.dictionary)
        print(f"\nAppended {len(new_patterns)} patterns to {args.dictionary}")
    else:
        print(f"\n[DRY RUN] Would append {len(new_patterns)} patterns to {args.dictionary}")


def cmd_stats(args):
    """Show dictionary statistics."""
    entries = load_dictionary(args.dictionary)

    categories = {}
    models = {}
    for e in entries:
        categories[e.category] = categories.get(e.category, 0) + 1
        models[e.model] = models.get(e.model, 0) + 1

    print(f"Dictionary: {args.dictionary}")
    print(f"Total entries: {len(entries)}")
    print(f"\nBy category:")
    for cat, count in sorted(categories.items()):
        print(f"  {cat}: {count}")
    print(f"\nBy model:")
    for model, count in sorted(models.items()):
        print(f"  {model}: {count}")


def main():
    parser = argparse.ArgumentParser(description="Transcription post-processing")
    parser.add_argument("--dictionary", "-d", default=DICTIONARY_PATH,
                        help="Path to dictionary file")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # clean command
    clean_parser = subparsers.add_parser("clean", help="Apply dictionary to transcript")
    clean_parser.add_argument("transcript", help="Path to raw transcript")
    clean_parser.add_argument("--output", "-o", help="Output path (default: overwrite input)")
    clean_parser.add_argument("--model", "-m", help="Filter by model (parakeet_mlx, canary)")
    clean_parser.add_argument("--dry-run", action="store_true", help="Show changes without applying")

    # diff command
    diff_parser = subparsers.add_parser("diff", help="Diff raw vs corrected, learn patterns")
    diff_parser.add_argument("raw", help="Path to raw transcript")
    diff_parser.add_argument("corrected", help="Path to manually corrected transcript")
    diff_parser.add_argument("--dry-run", action="store_true", help="Show patterns without saving")

    # clean-json command (for Scriberr integration, stdin/stdout)
    subparsers.add_parser("clean-json", help="Apply dictionary to JSON transcript (stdin→stdout)")

    # llm-clean-json command (Ollama LLM correction, stdin/stdout)
    subparsers.add_parser("llm-clean-json", help="Apply LLM corrections via Ollama (stdin→stdout)")

    # stats command
    subparsers.add_parser("stats", help="Show dictionary statistics")

    args = parser.parse_args()

    if args.command == "clean":
        cmd_clean(args)
    elif args.command == "clean-json":
        cmd_clean_json(args)
    elif args.command == "llm-clean-json":
        cmd_llm_clean_json(args)
    elif args.command == "diff":
        cmd_diff(args)
    elif args.command == "stats":
        cmd_stats(args)


if __name__ == "__main__":
    main()
