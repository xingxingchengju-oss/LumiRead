"""Publish the parent-facing narrative once, before the offline demonstration."""

import argparse
import json
import os
import tempfile
from pathlib import Path

import httpx

from apps.api import storage, vision, weekly


def save_publication(path: Path, publication: weekly.WeeklyPublication):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as out:
        temporary = Path(out.name)
    try:
        temporary.write_text(
            json.dumps(publication.model_dump(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def generate(data: weekly.WeeklyInput, prompt: str, version: str, transport=None):
    user_input = data.prompt_input()
    selected = next((entry for entry in vision.config() if entry[3]), None)
    if selected is None:
        raise vision.ProviderFailure("没有已配置的文字 API。")
    provider, url, model, key = selected
    if provider == "OpenAI":
        body = {
            "model": model,
            "store": False,
            "instructions": prompt,
            "input": [{"role": "user", "content": user_input}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "parent_weekly",
                    "strict": True,
                    "schema": weekly.WeeklyNarrative.model_json_schema(),
                }
            },
        }
    else:
        body = {
            "model": model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_input},
            ],
        }
    try:
        result, receipt = vision.request_structured(
            provider, url, model, key, body, transport, weekly.WeeklyNarrative
        )
    except (httpx.HTTPError, ValueError, TypeError, IndexError, KeyError) as exc:
        reason = (
            exc.response.status_code
            if isinstance(exc, httpx.HTTPStatusError)
            else type(exc).__name__
        )
        raise vision.ProviderFailure(f"{provider} {reason}") from None
    published = weekly.WeeklyPublication(
        provider=provider,
        model=receipt["model"],
        request_sha256=storage.digest(receipt["request_id"]),
        prompt_version=version,
        prompt_sha256=storage.digest(prompt),
        input_sha256=storage.digest(user_input),
        schema_sha256=weekly.schema_digest(),
        narrative=result,
    )
    draft_dir = storage.runtime() / "weekly-report"
    draft_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    (draft_dir / (published.prompt_sha256 + ".txt")).write_text(
        prompt, encoding="utf-8"
    )
    draft = draft_dir / (published.request_sha256 + ".json")
    save_publication(draft, published)
    try:
        weekly.check_narrative(result, data.facts)
    except ValueError as exc:
        raise ValueError(f"{exc}。原始草稿已保存到 {draft}") from exc
    return published


def publish(
    path: Path = weekly.PUBLICATION, transport=None, *, draft: Path | None = None
):
    prompt = weekly.PROMPT_PATH.read_text(encoding="utf-8")
    if storage.digest(prompt) != weekly.PROMPT_SHA256:
        raise ValueError("The weekly prompt differs from the frozen version.")
    data, _ = weekly.assemble_week()
    input_hash = storage.digest(data.prompt_input())
    if draft is not None:
        reviewed = weekly.read_publication(input_hash, data.facts, draft)
        if reviewed is None:
            raise ValueError("草稿与已冻结的提示词、周统计或输出要求不匹配。")
        save_publication(path, reviewed)
        return reviewed
    existing = weekly.read_publication(input_hash, data.facts, path)
    if existing:
        return existing
    published = generate(data, prompt, weekly.PROMPT_VERSION, transport)
    save_publication(path, published)
    return published


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--preview",
        type=Path,
        metavar="PROMPT",
        help="Generate a local draft for editorial review.",
    )
    mode.add_argument(
        "--publish-draft",
        type=Path,
        metavar="DRAFT",
        help="Publish the verified draft without another API call.",
    )
    args = parser.parse_args()
    try:
        if args.preview:
            data, _ = weekly.assemble_week()
            publication = generate(
                data, args.preview.read_text(encoding="utf-8"), args.preview.stem
            )
            print(
                storage.runtime()
                / "weekly-report"
                / (publication.request_sha256 + ".json")
            )
        else:
            publication = publish(draft=args.publish_draft)
    except (ValueError, vision.ProviderFailure) as exc:
        raise SystemExit(str(exc))
    print(
        f"{publication.provider} · {publication.model} · {publication.prompt_version}"
    )
    print(publication.narrative.model_dump_json(indent=2))
