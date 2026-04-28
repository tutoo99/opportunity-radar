#!/usr/bin/env python3
"""HuggingFace trending models & spaces collector using the public API.

Collects trending models and spaces from HuggingFace and saves them
to a structured JSON file for the opportunity-radar skill.
"""

import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import List

import httpx

# Output path
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "latest.json")

# API endpoints
MODELS_URL = "https://huggingface.co/api/models?sort=likes&direction=-1&limit=30"
SPACES_URL = "https://huggingface.co/api/spaces?sort=likes&direction=-1&limit=15"

# Total trending items for scoring
TOTAL_MODELS = 30
TOTAL_SPACES = 15


def fetch_json(client: httpx.Client, url: str) -> List[dict]:
    """Fetch JSON from a HuggingFace API endpoint."""
    print(f"  GET {url}")
    response = client.get(url)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        print(f"  WARNING: Expected list from {url}, got {type(data).__name__}")
        return []
    print(f"  Got {len(data)} items")
    return data


def format_number(n: int) -> str:
    """Format a number with commas for readability."""
    if n is None:
        return "0"
    return f"{int(n):,}"


def process_model(model: dict, rank: int) -> dict:
    """Convert a HuggingFace model API object into an opportunity-radar item."""
    model_id = model.get("modelId", model.get("id", ""))
    author = model.get("author", "")
    if not author and "/" in model_id:
        author = model_id.split("/")[0]

    # Score based on reverse rank (#1 gets highest)
    score = TOTAL_MODELS - rank

    pipeline_tag = model.get("pipeline_tag", "")
    tags = model.get("tags", [])
    library_name = model.get("library_name", "")
    downloads = model.get("downloads", 0)
    likes = model.get("likes", 0)
    last_modified = model.get("lastModified", "")

    # Build title
    if pipeline_tag:
        title = f"{model_id} - {pipeline_tag}"
    else:
        title = model_id

    # Build collected_tags
    collected_tags = ["model"]
    if pipeline_tag:
        collected_tags.append(pipeline_tag)
    if library_name:
        collected_tags.append(library_name)
    # Add relevant tags from the tags list (limit to avoid noise)
    interesting_tags = [
        "safetensors",
        "gguf",
        "onnx",
        "tensorrt",
        "gptq",
        "awq",
        "bitsandbytes",
        "flash_attention",
        "rlhf",
        "dpo",
        "chat",
        "instruct",
    ]
    for tag in tags:
        if tag in interesting_tags and tag not in collected_tags:
            collected_tags.append(tag)

    # Build raw_text
    raw_parts = []
    if pipeline_tag:
        raw_parts.append(pipeline_tag)
    other_tags = [t for t in tags if t not in interesting_tags][:3]
    if other_tags:
        raw_parts.append(", ".join(other_tags))
    raw_parts.append(f"downloads: {format_number(downloads)}")
    raw_parts.append(f"likes: {format_number(likes)}")
    if last_modified:
        raw_parts.append(f"modified: {last_modified}")
    raw_text = " | ".join(raw_parts)

    return {
        "id": model_id,
        "title": title,
        "url": f"https://huggingface.co/{model_id}",
        "score": score,
        "comments_count": 0,
        "author": author,
        "type": "model",
        "raw_text": raw_text,
        "images": [],
        "collected_tags": collected_tags,
    }


def process_space(space: dict, rank: int) -> dict:
    """Convert a HuggingFace space API object into an opportunity-radar item."""
    space_id = space.get("id", "")
    author = space.get("author", "")
    if not author and "/" in space_id:
        author = space_id.split("/")[0]

    # Score based on reverse rank (#1 gets highest)
    score = TOTAL_SPACES - rank

    likes = space.get("likes", 0)
    sdk = space.get("sdk", "")
    space_tags = space.get("tags", [])
    last_modified = space.get("lastModified", "")

    # Build title
    title = space_id

    # Build collected_tags
    collected_tags = ["space"]
    if sdk:
        collected_tags.append(f"sdk:{sdk}")
    for tag in space_tags[:3]:
        if tag not in collected_tags:
            collected_tags.append(tag)

    # Build raw_text
    raw_parts = []
    if sdk:
        raw_parts.append(f"sdk: {sdk}")
    if space_tags:
        raw_parts.append(f"tags: {', '.join(space_tags[:5])}")
    raw_parts.append(f"likes: {format_number(likes)}")
    if last_modified:
        raw_parts.append(f"modified: {last_modified}")
    raw_text = " | ".join(raw_parts)

    return {
        "id": space_id,
        "title": title,
        "url": f"https://huggingface.co/spaces/{space_id}",
        "score": score,
        "comments_count": 0,
        "author": author,
        "type": "space",
        "raw_text": raw_text,
        "images": [],
        "collected_tags": collected_tags,
    }


def main():
    """Main entry point: fetch trending models & spaces and save results."""
    tz = timezone(timedelta(hours=8))
    collected_at = datetime.now(tz).strftime("%Y-%m-%dT%H:%M:%S+08:00")

    print(f"[HuggingFace] Starting collection at {collected_at}")

    items = []

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        # Fetch trending models
        try:
            models = fetch_json(client, MODELS_URL)
            for rank, model in enumerate(models):
                items.append(process_model(model, rank))
        except Exception as e:
            print(f"  Error fetching models: {e}")

        time.sleep(0.2)

        # Fetch trending spaces
        try:
            spaces = fetch_json(client, SPACES_URL)
            for rank, space in enumerate(spaces):
                items.append(process_space(space, rank))
        except Exception as e:
            print(f"  Error fetching spaces: {e}")

    # Sort by score descending
    items.sort(key=lambda x: x["score"], reverse=True)

    output = {
        "source": "huggingface",
        "collected_at": collected_at,
        "items": items,
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(
        f"[HuggingFace] Done: {len(items)} items saved to {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
