import hashlib
import re
import sys


def image_tag(branch: str) -> str:
    if branch in {"master", "main"}:
        return "latest"
    if not branch or any(character.isspace() for character in branch):
        raise ValueError("A branch name without whitespace is required")
    name = re.sub(r"[^A-Za-z0-9_.-]", "-", branch)[:100]
    suffix = hashlib.sha256(branch.encode()).hexdigest()[:12]
    return f"branch-{name}-{suffix}"


if __name__ == "__main__":
    print(image_tag(sys.argv[1]))
