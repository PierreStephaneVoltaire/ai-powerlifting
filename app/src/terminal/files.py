












from __future__ import annotations
import re
import logging
from dataclasses import dataclass
from typing import List, Tuple

logger = logging.getLogger(__name__)

@dataclass
class FileRef:






    path: str
    description: str

_FILES_RE = re.compile(r"^FILES:\s*(.+)$", re.MULTILINE)

_ENTRY_RE = re.compile(r"(\S+)\s*\(([^)]+)\)")

def strip_files_line(text: str) -> Tuple[str, List[FileRef]]:













    m = _FILES_RE.search(text)
    if not m:
        return text, []
    
    files_content = m.group(1)
    refs = []
    for entry_match in _ENTRY_RE.finditer(files_content):
        path = entry_match.group(1)
        description = entry_match.group(2).strip()
        refs.append(FileRef(path=path, description=description))
    
    cleaned = text[:m.start()].rstrip("\n") + text[m.end():]
    
    return cleaned.rstrip("\n"), refs

class FilesStripBuffer:



















    
    TAIL_SIZE = 500
    
    def __init__(self):

        self._tail = ""
    
    def feed(self, chunk: str) -> str:











        combined = self._tail + chunk
        
        if len(combined) <= self.TAIL_SIZE:
            self._tail = combined
            return ""
        
        emit = combined[:-self.TAIL_SIZE]
        self._tail = combined[-self.TAIL_SIZE:]
        return emit
    
    def finalize(self) -> Tuple[str, List[FileRef]]:








        cleaned, refs = strip_files_line(self._tail)
        self._tail = ""
        return cleaned, refs
    
    def reset(self) -> None:

        self._tail = ""

def log_file_refs(conversation_id: str, refs: List[FileRef]) -> None:






    if refs:
        paths = [r.path for r in refs]
        logger.info(f"[FILES] {conversation_id}: {paths}")
        for ref in refs:
            logger.debug(f"[FILES]   - {ref.path}: {ref.description}")

import threading
_ref_lock = threading.Lock()
_pending_refs: dict[str, list[FileRef]] = {}

def accumulate_file_refs(chat_id: str, refs: List[FileRef]) -> None:

    if not refs:
        return
    with _ref_lock:
        _pending_refs.setdefault(chat_id, []).extend(refs)

def consume_file_refs(chat_id: str) -> List[FileRef]:

    with _ref_lock:
        return _pending_refs.pop(chat_id, [])
