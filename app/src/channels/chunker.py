
from __future__ import annotations
from typing import List

from config import CHANNEL_MAX_CHUNK_CHARS, DISCORD_MAX_CONTENT_CHARS

def chunk_response(
    text: str,
    max_chars: int | None = None,
) -> List[str]:

    if max_chars is None:
        max_chars = CHANNEL_MAX_CHUNK_CHARS

    if len(text) <= max_chars:
        return [text]

    chunks: List[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break

        cut = _find_split_point(remaining, max_chars)

        chunk = remaining[:cut].rstrip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[cut:].lstrip()

    return chunks

def _find_split_point(text: str, max_chars: int) -> int:

    code_block_split = _find_code_block_split(text, max_chars)
    if code_block_split > 0:
        return code_block_split

    delimiters = ["\n\n", ".\n", ". ", "\n", " "]
    
    for delimiter in delimiters:
        pos = text.rfind(delimiter, 0, max_chars)
        if pos > int(max_chars * 0.3):
            return pos + len(delimiter)

    return max_chars

def _find_code_block_split(text: str, max_chars: int) -> int:
    """Find a split point that respects code block boundaries.

    When an odd number of ``` markers appears in the first max_chars,
    extends the split to close the code block — but never beyond
    DISCORD_MAX_CONTENT_CHARS, which is Discord's hard API limit.
    """
    search_region = text[:max_chars]
    
    marker_count = search_region.count("```")
    
    if marker_count % 2 == 1:
        next_marker = text.find("```", max_chars)
        # Cap extension so the chunk never exceeds Discord's hard limit
        max_extension = DISCORD_MAX_CONTENT_CHARS
        if next_marker != -1 and next_marker < min(max_chars + 500, max_extension):
            end_pos = next_marker + 3
            return end_pos
    
    last_block_end = search_region.rfind("```")
    if last_block_end > int(max_chars * 0.5):
        markers_before = text[:last_block_end].count("```")
        if markers_before % 2 == 1:
            return last_block_end + 3
    
    return 0

def estimate_chunks(text: str, max_chars: int | None = None) -> int:

    return len(chunk_response(text, max_chars))
