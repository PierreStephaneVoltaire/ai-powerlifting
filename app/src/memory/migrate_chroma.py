
















from __future__ import annotations
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def get_chroma_collection(db_path: str):








    try:
        import chromadb
        from chromadb.config import Settings
    except ImportError:
        logger.error("chromadb is required for migration. Install with: pip install chromadb")
        sys.exit(1)

    client = chromadb.PersistentClient(
        path=db_path,
        settings=Settings(
            anonymized_telemetry=False,
            allow_reset=True
        )
    )

    return client.get_or_create_collection(
        name="user_facts",
        metadata={"description": "User facts store"}
    )

def migrate_fact(
    fact_id: str,
    document: str,
    metadata: Dict[str, Any],
    context_id: str,
    dry_run: bool = False,
) -> Optional[str]:












    from memory.lancedb_store import get_table, clear_table_cache
    from memory.embeddings import embed

    username = metadata.get("username", "unknown")
    category = metadata.get("category", "personal")
    source = metadata.get("source", "user_stated")
    confidence = float(metadata.get("confidence", 0.8))
    cache_key = metadata.get("cache_key", "")
    created_at = metadata.get("created_at", "")
    updated_at = metadata.get("updated_at", "")
    superseded_by = metadata.get("superseded_by") or None
    active = metadata.get("active", True)

    metadata_json = metadata.get("metadata_json", "{}")
    if isinstance(metadata_json, str):
        try:
            fact_metadata = json.loads(metadata_json or "{}")
        except json.JSONDecodeError:
            fact_metadata = {}
    else:
        fact_metadata = metadata_json

    if dry_run:
        logger.info(f"[DRY RUN] Would migrate: [{category}] {document[:50]}...")
        return fact_id

    vector = embed(document)

    now = datetime.now(timezone.utc).isoformat()
    row = {
        "id": fact_id,
        "context_id": context_id,
        "user_id": username,
        "content": document,
        "vector": vector,
        "category": category,
        "source": source,
        "confidence": confidence,
        "active": active,
        "superseded_by": superseded_by,
        "created_at": created_at or now,
        "updated_at": updated_at or now,
        "session_key": cache_key,
        "metadata_json": json.dumps(fact_metadata),
    }

    table = get_table(context_id)
    table.add([row])

    return fact_id

def migrate(
    chroma_path: str,
    context_id: str = "migrated_default",
    dry_run: bool = False,
) -> Dict[str, int]:










    logger.info(f"Starting migration from ChromaDB ({chroma_path}) to LanceDB")
    logger.info(f"Context ID: {context_id}")
    logger.info(f"Dry run: {dry_run}")

    collection = get_chroma_collection(chroma_path)
    total = collection.count()
    logger.info(f"Found {total} documents in ChromaDB")

    if total == 0:
        logger.info("No documents to migrate")
        return {"total": 0, "migrated": 0, "errors": 0}

    results = collection.get(
        include=["documents", "metadatas", "embeddings"]
    )

    stats = {
        "total": total,
        "migrated": 0,
        "errors": 0,
        "skipped": 0,
    }

    for i, fact_id in enumerate(results["ids"]):
        try:
            document = results["documents"][i]
            metadata = results["metadatas"][i]

            if not document or not document.strip():
                stats["skipped"] += 1
                continue

            new_id = migrate_fact(
                fact_id=fact_id,
                document=document,
                metadata=metadata,
                context_id=context_id,
                dry_run=dry_run,
            )

            if new_id:
                stats["migrated"] += 1

            if (i + 1) % 100 == 0:
                logger.info(f"Progress: {i + 1}/{total}")

        except Exception as e:
            logger.error(f"Error migrating fact {fact_id}: {e}")
            stats["errors"] += 1

    logger.info(f"Migration complete: {stats}")
    return stats

def main():
    parser = argparse.ArgumentParser(
        description="Migrate user facts from ChromaDB to LanceDB"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without making changes",
    )
    parser.add_argument(
        "--context-id",
        default="migrated_default",
        help="Context ID for all migrated facts (default: migrated_default)",
    )
    parser.add_argument(
        "--chroma-path",
        default=None,
        help="Path to ChromaDB (default: from MEMORY_DB_PATH env var or ./data/memory_db)",
    )

    args = parser.parse_args()

    chroma_path = args.chroma_path or os.getenv("MEMORY_DB_PATH", "./data/memory_db")

    stats = migrate(
        chroma_path=chroma_path,
        context_id=args.context_id,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        logger.info("This was a dry run. No changes were made.")
        logger.info("Run without --dry-run to perform the actual migration.")

    return 0 if stats["errors"] == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
