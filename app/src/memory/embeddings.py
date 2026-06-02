




from __future__ import annotations
import os
import logging
from functools import lru_cache
from typing import List, Optional

from config import EMBEDDING_MODEL

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "384"))

_model_load_logged = False

@lru_cache(maxsize=1)
def get_embedding_model():








    global _model_load_logged

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ImportError(
            "sentence-transformers is required for embeddings. "
            "Install with: pip install sentence-transformers"
        )

    model = SentenceTransformer(EMBEDDING_MODEL)

    if not _model_load_logged:
        logger.info(f"Loaded embedding model: {EMBEDDING_MODEL} (dimension: {EMBEDDING_DIMENSION})")
        _model_load_logged = True

    return model

def embed(text: str) -> List[float]:








    if not text or not text.strip():
        return [0.0] * EMBEDDING_DIMENSION

    model = get_embedding_model()
    embedding = model.encode(text)
    return embedding.tolist()

def embed_batch(texts: List[str]) -> List[List[float]]:










    if not texts:
        return []

    model = get_embedding_model()

    processed = [t if t and t.strip() else " " for t in texts]

    embeddings = model.encode(processed)
    return [e.tolist() for e in embeddings]

def get_embedding_dimension() -> int:





    return EMBEDDING_DIMENSION
