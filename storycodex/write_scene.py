from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import llm
from .paths import scene_context_path


LENGTH_PRESETS = {
    "short": 600,
    "medium": 1000,
    "long": 1500,
}


def write_scene(
    root: Path,
    scene_id: int,
    model: str | None,
    length: str,
    target_words: int | None,
    force: bool,
    run_id: str | None,
) -> str | None:
    output_path = root / "out" / "scenes" / f"scene_{scene_id:03d}.draft.md"
    if output_path.exists() and not force:
        return None

    context_path = scene_context_path(root, scene_id)
    if not context_path.exists():
        raise FileNotFoundError(
            f"Missing context at {context_path}; run build-context first."
        )

    context_text = context_path.read_text()
    context = json.loads(context_text)

    target = target_words or LENGTH_PRESETS[length]
    chosen_model = model or llm.get_default_model()

    prompt = build_prompt(context, target, length)
    max_tokens = int(target * 2.0)
    draft = llm.chat(prompt, chosen_model, temperature=0.7, max_tokens=max_tokens)

    ok, issues = validate_draft(draft, target, context)
    if not ok:
        retry_prompt = build_retry_prompt(context, target, length, issues)
        draft = llm.chat(retry_prompt, chosen_model, temperature=0.7, max_tokens=max_tokens)
        ok, issues = validate_draft(draft, target, context)
    if not ok:
        expand_prompt = build_expand_prompt(context, target, draft)
        draft = llm.chat(expand_prompt, chosen_model, temperature=0.7, max_tokens=max_tokens)
        ok, issues = validate_draft(draft, target, context)
        if not ok:
            raise ValueError("Draft failed validation: " + "; ".join(issues))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(draft.rstrip() + "\n")

    backend_used, _ = llm.resolve_backend(llm.get_base_url(), llm.get_backend_setting())
    meta = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": chosen_model,
        "backend": backend_used,
        "target_words": target,
        "length": length,
        "input_hash": sha256_text(context_text),
        "run_id": run_id,
    }
    meta_path = root / "out" / "scenes" / f"scene_{scene_id:03d}.draft.meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")

    return draft


def build_prompt(context: dict[str, Any], target_words: int, length: str) -> list[dict[str, str]]:
    context_json = json.dumps(context, indent=2, sort_keys=True)
    rules = (
        "Hard rules:\n"
        "- Use ONLY the provided context packet.\n"
        "- Follow POV and tense from ringA exactly.\n"
        "- Follow all ringA.style_rules.\n"
        "- Obey all continuity_locks in ringB (severity 'must' is absolute).\n"
        "- Hit EVERY beat in ringB.beats in order.\n"
        "- Use one paragraph per beat, in order.\n"
        "- Do NOT invent new plot events, characters, locations, or lore.\n"
        "- Do NOT contradict ringA global constraints.\n"
        "- If cast size > 1, include dialogue.\n"
        "- If cast size == 1, interiority is allowed.\n"
        "- End naturally unless a 'hook' beat is present; then emphasize it.\n"
        "- No summaries of future scenes, no meta commentary, no exposition ungrounded in setting.\n"
        "- Output prose only (markdown text), no JSON, no headings unless in the prose.\n"
    )
    length_block = (
        f"Target length: {length} (~{target_words} words). "
        "Stay within +/-30% of the target.\n"
    )
    checklist = (
        "Checklist:\n"
        "- POV?\n"
        "- Tense?\n"
        "- Final beat reached?\n"
        "- Locks obeyed?\n"
    )
    user_content = (
        rules
        + "\n"
        + length_block
        + "\nContext packet JSON:\n"
        + context_json
        + "\n\n"
        + checklist
    )

    return [
        {"role": "system", "content": "You are a professional fiction writer executing a constrained writing task."},
        {"role": "user", "content": user_content},
    ]


def build_retry_prompt(
    context: dict[str, Any],
    target_words: int,
    length: str,
    issues: list[str],
) -> list[dict[str, str]]:
    context_json = json.dumps(context, indent=2, sort_keys=True)
    issue_text = "\n".join(f"- {issue}" for issue in issues)
    user_content = (
        "The previous draft failed validation. Fix the issues and rewrite.\n"
        f"Issues:\n{issue_text}\n\n"
        f"Target length: {length} (~{target_words} words), stay within +/-30%.\n"
        "Output prose only, no JSON, no commentary.\n\n"
        "Context packet JSON:\n"
        f"{context_json}"
    )
    return [
        {"role": "system", "content": "You are a professional fiction writer executing a constrained writing task."},
        {"role": "user", "content": user_content},
    ]


def build_expand_prompt(
    context: dict[str, Any], target_words: int, draft: str
) -> list[dict[str, str]]:
    context_json = json.dumps(context, indent=2, sort_keys=True)
    min_words = int(target_words * 0.7)
    max_words = int(target_words * 1.3)
    user_content = (
        "Expand the draft to fit the target length without changing events. "
        "Keep POV and tense, preserve beat order, add detail and dialogue where appropriate. "
        f"Target length: {min_words}-{max_words} words. "
        "Return the FULL expanded scene, no commentary.\n\n"
        "Context packet JSON:\n"
        f"{context_json}\n\n"
        "Draft to expand:\n"
        f"{draft}"
    )
    return [
        {"role": "system", "content": "You are a professional fiction writer executing a constrained writing task."},
        {"role": "user", "content": user_content},
    ]


def validate_draft(draft: str, target_words: int, context: dict[str, Any]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    text = draft.strip()
    if not text:
        return False, ["Draft is empty"]

    words = text.split()
    word_count = len(words)
    min_words = int(target_words * 0.6)
    max_words = int(target_words * 1.4)
    if word_count < min_words or word_count > max_words:
        issues.append(f"Word count {word_count} outside {min_words}-{max_words}")

    beats = context.get("ringB", {}).get("beats", []) if isinstance(context, dict) else []
    beat_count = len(beats) if isinstance(beats, list) else 0
    paragraph_count = count_paragraphs(text)
    if beat_count:
        min_paragraphs = (beat_count + 1) // 2
        if paragraph_count < min_paragraphs:
            issues.append("Paragraph count too low for beats")

    return len(issues) == 0, issues


def count_paragraphs(text: str) -> int:
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    return len(paragraphs)


def sha256_text(text: str) -> str:
    digest = hashlib.sha256()
    digest.update(text.encode("utf-8"))
    return digest.hexdigest()
