"""Directive store with DynamoDB backend and in-memory caching.

Provides CRUD operations for directives with versioning support.
All active directives are cached in memory for fast prompt assembly.

Usage:
    store = DirectiveStore(table_name="if-core")
    store.load()  # Load and cache all active directives
    
    # Get formatted block for system prompt
    directives_block = store.format_for_prompt()
    
    # Add new directive (auto-assigns beta)
    directive = store.add(alpha=2, label="NEW_RULE", content="...", created_by="agent")
    
    # Revise existing directive (creates new version)
    new_version = store.revise(alpha=2, beta=5, content="new content")
"""
from __future__ import annotations
import logging
from typing import List, Optional, Dict
from collections import defaultdict
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key
from num2words import num2words

from storage.directive_model import Directive


logger = logging.getLogger(__name__)


class DirectiveStore:
    """DynamoDB-backed directive storage with in-memory caching.
    
    Loads all active directives at startup and caches them for fast
    prompt assembly. Uses versioning - revisions create new versions
    rather than modifying existing items.
    
    Attributes:
        table_name: DynamoDB table name
        _table: Lazy-loaded DynamoDB table resource
        _cache: List of cached active directives (highest version only)
        _region: AWS region
    """
    
    def __init__(self, table_name: str = "if-core", region: str = "ca-central-1", pk: str = "operator"):
        """Initialize the directive store.
        
        Args:
            table_name: DynamoDB table name
            region: AWS region
            pk: DynamoDB partition key for directives (default "operator")
        """
        self.table_name = table_name
        self._table = None
        self._cache: List[Directive] = []
        self._region = region
        self._pk = pk
    
    @property
    def table(self):
        """Lazy-load DynamoDB table resource."""
        if self._table is None:
            self._table = boto3.resource(
                "dynamodb", region_name=self._region
            ).Table(self.table_name)
        return self._table
    
    def load(self) -> List[Directive]:
        """Query PK=<self._pk>, return only highest-versioned active directive per alpha/beta.
        
        This method loads all directives from DynamoDB, groups them by
        alpha/beta, and returns only the highest-versioned active directive
        for each group. The result is cached for fast access.
        
        Returns:
            List of active Directive objects (highest version only), sorted by alpha then beta
            
        Raises:
            Exception: If DynamoDB query fails (connection error, permission denied, etc.)
        """
        try:
            logger.info(f"[DirectiveStore] Loading directives from {self.table_name}...")
            response = self.table.query(
                KeyConditionExpression=Key("pk").eq(self._pk)
            )
            items = response.get("Items", [])
            logger.info(f"[DirectiveStore] Retrieved {len(items)} raw items from DynamoDB")
        except Exception as e:
            logger.error(f"[DirectiveStore] FAILED to query DynamoDB: {type(e).__name__}: {e}")
            raise RuntimeError(f"DirectiveStore failed to load from DynamoDB: {e}") from e
        
        # Group by alpha/beta, find highest active version for each
        by_alpha_beta: Dict[str, List[Directive]] = defaultdict(list)
        skipped_count = 0
        for item in items:
            try:
                directive = Directive.from_dynamodb_item(item)
                by_alpha_beta[directive.base_key].append(directive)
            except ValueError as e:
                logger.warning(f"Skipping invalid directive item: {e}")
                skipped_count += 1
        
        if skipped_count > 0:
            logger.warning(f"[DirectiveStore] Skipped {skipped_count} invalid directive items")
        
        # For each alpha/beta, get the highest-versioned active directive
        directives = []
        for base_key, versions in by_alpha_beta.items():
            # Filter to active, sort by version descending, take first
            active_versions = [v for v in versions if v.active]
            if active_versions:
                active_versions.sort(key=lambda d: d.version, reverse=True)
                directives.append(active_versions[0])
        
        # Sort by alpha, then beta
        directives.sort(key=lambda d: (d.alpha, d.beta))
        self._cache = directives
        
        # Build summary by alpha tier
        by_alpha = {}
        for d in directives:
            by_alpha.setdefault(d.alpha, 0)
            by_alpha[d.alpha] += 1
        
        alpha_summary = ", ".join([f"alpha {a}: {c}" for a, c in sorted(by_alpha.items())])
        logger.info(f"[DirectiveStore] Loaded {len(directives)} active directives ({alpha_summary})")
        
        if len(directives) == 0:
            logger.warning(f"[DirectiveStore] NO directives loaded from {self.table_name} - table may be empty or all directives are inactive")
        
        return directives
    
    def format_for_prompt(self) -> str:
        """Return formatted directive block matching existing style.
        
        Output format:
            0-1  MEMORY PRESERVATION (Directive Zero-One)
            Your memories, observations, and learned experiences define...
            
            0-2  NO FABRICATION
            Never invent statistics...
        
        Returns:
            Formatted directive block string, or empty string if no directives
        """
        if not self._cache:
            return ""
        
        lines = []
        for d in self._cache:
            # Convert numeric to text for directive reference
            lines.append(
                f"{d.alpha}-{d.beta}  {d.label} "
                f"(Directive {self._number_to_text(d.alpha)}-{self._number_to_text(d.beta)})"
            )
            lines.append(d.content)
            lines.append("")  # Blank line between directives
        
        return "\n".join(lines)
    
    @staticmethod
    def _number_to_text(n: int) -> str:
        """Convert number to text.
        
        Args:
            n: Number to convert
            
        Returns:
            Text representation (e.g., "Zero", "One", "Twenty-One", etc.)
        """
        return num2words(n).title()
    
    def next_beta(self, alpha: int) -> int:
        """Return max(beta) + 1 for given alpha tier from cache.
        
        If no directives exist for that alpha, return 1.
        
        Args:
            alpha: Alpha tier
            
        Returns:
            Next available beta number
        """
        max_beta = 0
        for d in self._cache:
            if d.alpha == alpha and d.beta > max_beta:
                max_beta = d.beta
        return max_beta + 1
    
    def _get_latest_version(self, alpha: int, beta: int) -> Optional[Directive]:
        """Get the latest version (active or not) of a directive from DynamoDB.
        
        This queries DynamoDB directly, not the cache, to ensure we get
        the most recent version even if it's inactive.
        
        Args:
            alpha: Alpha tier
            beta: Beta number
            
        Returns:
            Latest version Directive, or None if not found
        """
        base_key = f"{alpha:02d}#{beta:02d}"
        response = self.table.query(
            KeyConditionExpression=(
                Key("pk").eq(self._pk) & Key("sk").begins_with(base_key)
            )
        )
        
        if not response.get("Items"):
            return None
        
        versions = [
            Directive.from_dynamodb_item(item) 
            for item in response["Items"]
        ]
        versions.sort(key=lambda d: d.version, reverse=True)
        return versions[0]
    
    def add(
        self,
        alpha: int,
        label: str,
        content: str,
        types: List[str],
        created_by: str,
        global_directive: bool = False,
    ) -> Directive:
        """Create new directive with version=1. Auto-assign beta via next_beta().

        Args:
            alpha: Alpha tier (0-5)
            label: Directive label (UPPER_SNAKE_CASE)
            content: Full directive text
            types: Domain types for this directive (e.g., ["core", "code"])
            created_by: "operator", "agent", or "reflection"
            global_directive: If True, this directive applies to all users.
                Only allowed when pk is "operator".

        Returns:
            The created Directive with assigned beta
        """
        # Enforce: global directives only allowed for operator pk
        if global_directive and self._pk != "operator":
            raise ValueError("global_directive=True is only allowed when pk is 'operator'")

        beta = self.next_beta(alpha)
        now = datetime.now(timezone.utc).isoformat()

        directive = Directive(
            alpha=alpha,
            beta=beta,
            version=1,  # New directives always start at version 1
            label=label,
            content=content,
            types=types,
            created_by=created_by,
            active=True,
            created_at=now,
            superseded_at=None,
            pk=self._pk,
            global_directive=global_directive,
        )
        
        self.table.put_item(Item=directive.to_dynamodb_item())
        self.load()  # Reload cache
        
        logger.info(
            f"[DirectiveStore] Added directive {alpha}-{beta} v1: {label}"
        )
        return directive
    
    def revise(
        self,
        alpha: int,
        beta: int,
        content: str,
        types: Optional[List[str]] = None,
        label: Optional[str] = None,
        created_by: str = "agent"
    ) -> Optional[Directive]:
        """Create a new version of an existing directive.
        
        This does NOT modify the existing directive. Instead:
        1. Marks old version as inactive (sets superseded_at)
        2. Creates new version with version = old_version + 1
        
        Args:
            alpha: Alpha tier
            beta: Beta number
            content: New content for the directive
            label: New label (optional, defaults to existing label)
            created_by: Who is making this revision
            
        Returns:
            New Directive version, or None if original not found
        """
        existing = self._get_latest_version(alpha, beta)
        if not existing:
            return None
        
        now = datetime.now(timezone.utc).isoformat()
        
        # Mark old version as superseded
        self.table.update_item(
            Key={"pk": self._pk, "sk": existing.sort_key},
            UpdateExpression=(
                "SET active = :inactive, superseded_at = :superseded"
            ),
            ExpressionAttributeValues={
                ":inactive": False,
                ":superseded": now,
            },
        )
        
        # Create new version
        new_directive = Directive(
            alpha=alpha,
            beta=beta,
            version=existing.version + 1,
            label=label or existing.label,
            content=content,
            types=types if types is not None else existing.types,
            created_by=created_by,
            active=True,
            created_at=now,
            superseded_at=None,
            pk=self._pk,
            global_directive=existing.global_directive,
        )
        
        self.table.put_item(Item=new_directive.to_dynamodb_item())
        self.load()  # Reload cache
        
        logger.info(
            f"[DirectiveStore] Revised directive {alpha}-{beta} "
            f"v{new_directive.version}"
        )
        return new_directive
    
    def deactivate(
        self, 
        alpha: int, 
        beta: int, 
        override: bool = False
    ) -> bool:
        """Mark the latest version of a directive as inactive.
        
        Block alpha 0-1 deactivation unless override=True.
        
        Args:
            alpha: Alpha tier
            beta: Beta number
            override: Allow deactivating alpha 0-1 (operator-only)
            
        Returns:
            True if deactivated, False if blocked or not found
        """
        # Block alpha 0-1 deactivation
        if alpha == 0 and beta == 1 and not override:
            logger.warning(
                "[DirectiveStore] Blocked deactivation of directive 0-1"
            )
            return False
        
        existing = self._get_latest_version(alpha, beta)
        if not existing:
            return False
        
        now = datetime.now(timezone.utc).isoformat()
        self.table.update_item(
            Key={"pk": self._pk, "sk": existing.sort_key},
            UpdateExpression=(
                "SET active = :inactive, superseded_at = :superseded"
            ),
            ExpressionAttributeValues={
                ":inactive": False,
                ":superseded": now,
            },
        )
        
        self.load()  # Reload cache
        logger.info(f"[DirectiveStore] Deactivated directive {alpha}-{beta}")
        return True
    
    def get(self, alpha: int, beta: int) -> Optional[Directive]:
        """Get the active directive for alpha/beta from cache.
        
        Args:
            alpha: Alpha tier
            beta: Beta number
            
        Returns:
            Directive if found in cache, None otherwise
        """
        for d in self._cache:
            if d.alpha == alpha and d.beta == beta:
                return d
        return None
    
    def get_all(self, alpha: Optional[int] = None) -> List[Directive]:
        """Get all active directives from cache, optionally filtered by alpha.
        
        Args:
            alpha: Optional alpha tier filter
            
        Returns:
            List of matching directives
        """
        if alpha is None:
            return list(self._cache)
        return [d for d in self._cache if d.alpha == alpha]

    def get_all_global(self) -> List[Directive]:
        """Get all active global directives from cache.

        Global directives are those with global_directive=True. They apply
        to ALL users regardless of pk.

        Returns:
            List of active global Directive objects
        """
        return [d for d in self._cache if d.global_directive and d.active]

    def get_history(self, alpha: int, beta: int) -> List[Directive]:
        """Get all versions of a directive (for audit/history).
        
        Args:
            alpha: Alpha tier
            beta: Beta number
            
        Returns:
            List of all versions, sorted newest first
        """
        base_key = f"{alpha:02d}#{beta:02d}"
        response = self.table.query(
            KeyConditionExpression=(
                Key("pk").eq(self._pk) & Key("sk").begins_with(base_key)
            )
        )
        
        versions = [
            Directive.from_dynamodb_item(item) 
            for item in response.get("Items", [])
        ]
        versions.sort(key=lambda d: d.version, reverse=True)
        return versions

    # Types that should be excluded from subagent auto-injection
    MAIN_AGENT_ONLY_TYPES = {"tool", "memory", "metacognition"}

    def get_by_types(self, types: List[str]) -> List[Directive]:
        """Return all active cached directives that have ANY of the given types.

        Union logic -- types=["code", "security"] returns directives tagged
        code OR security (or both).
        """
        result = []
        type_set = set(types)
        for d in self._cache:
            if not d.active:
                continue
            d_types = set(d.types)
            if d_types & type_set:
                result.append(d)
        result.sort(key=lambda d: (d.alpha, d.beta))
        return result

    def get_for_subagent(self, types: List[str]) -> List[Directive]:
        """Build directive set for a subagent.

        1. All tier 0 directives (always included for safety)
        2. All directives matching any of the given types
        3. Exclude directives whose ONLY types are in main-agent-only set:
           (tool, memory, metacognition)
        4. Deduplicate by alpha-beta

        Args:
            types: List of directive types to include (e.g., ["code", "architecture"])

        Returns:
            List of Directive objects sorted by alpha then beta
        """
        result_by_key = {}  # Use dict for deduplication

        type_set = set(types) if types else set()

        for d in self._cache:
            if not d.active:
                continue

            d_types = set(d.types)

            # Always include tier 0 directives
            if d.alpha == 0:
                result_by_key[(d.alpha, d.beta)] = d
                continue

            # Skip main-agent-only directives (those with ONLY tool/memory/metacognition)
            if d_types.issubset(self.MAIN_AGENT_ONLY_TYPES):
                continue

            # Include if any type matches
            if d_types & type_set:
                result_by_key[(d.alpha, d.beta)] = d

        result = list(result_by_key.values())
        result.sort(key=lambda d: (d.alpha, d.beta))
        return result

    def _put_directive(
        self,
        alpha: int,
        beta: int,
        label: str,
        content: str,
        types: List[str],
        created_by: str,
        global_directive: bool = False,
    ) -> Directive:
        """Create a directive at an explicit alpha/beta position.

        Unlike ``add()``, this does NOT auto-assign beta. Used by
        ``bulk_reorder`` and the resequence step to place directives
        at exact positions.

        Args:
            alpha: Alpha tier (0-5)
            beta: Beta number (explicit, not auto-assigned)
            label: Directive label
            content: Full directive text
            types: Domain types
            created_by: Who created this directive
            global_directive: If True, applies to all users

        Returns:
            The created Directive
        """
        now = datetime.now(timezone.utc).isoformat()

        directive = Directive(
            alpha=alpha,
            beta=beta,
            version=1,  # New directives always start at version 1
            label=label,
            content=content,
            types=types,
            created_by=created_by,
            active=True,
            created_at=now,
            superseded_at=None,
            pk=self._pk,
            global_directive=global_directive,
        )

        self.table.put_item(Item=directive.to_dynamodb_item())

        logger.info(
            f"[DirectiveStore] Put directive {alpha}-{beta} v1: {label}"
        )
        return directive

    def bulk_reorder(
        self,
        items: List[dict],
    ) -> List[Directive]:
        """Bulk reorder directives with collision/swap support.

        Each item in ``items`` is a dict with keys:
            old_alpha, old_beta, new_alpha, new_beta

        When two items swap positions (A → B's slot, B → A's slot),
        both are deactivated and recreated at the target positions.

        After all moves, beta numbers within each alpha tier are
        resequenced to be contiguous (1, 2, 3, …) so there are no gaps.

        Args:
            items: List of {old_alpha, old_beta, new_alpha, new_beta} dicts

        Returns:
            List of updated Directive objects after resequence

        Raises:
            ValueError: If a source directive is not found
        """
        # 1. Load fresh directives from DynamoDB
        all_directives = self.load()

        # 2. Build lookup by (alpha, beta)
        by_key: Dict[tuple, Directive] = {(d.alpha, d.beta): d for d in all_directives}

        # 3. Validate all source directives exist
        for item in items:
            key = (item["old_alpha"], item["old_beta"])
            if key not in by_key:
                raise ValueError(f"Directive {key[0]}-{key[1]} not found")

        # 4. Build the mapping of old positions → new positions
        move_map: Dict[tuple, tuple] = {}  # (old_a, old_b) → (new_a, new_b)
        for item in items:
            old_key = (item["old_alpha"], item["old_beta"])
            new_key = (item["new_alpha"], item["new_beta"])
            move_map[old_key] = new_key

        # 5. Execute moves: deactivate all old positions first,
        #    then recreate at new positions using _put_directive
        #    (bypasses auto-beta-assign so we use exact target positions)
        moved_directives: Dict[tuple, Directive] = {}  # new_key → directive data

        # Deactivate all old positions first
        for old_key in move_map:
            source = by_key[old_key]
            deactivated = self.deactivate(old_key[0], old_key[1], override=True)
            if not deactivated:
                raise ValueError(f"Failed to deactivate directive {old_key[0]}-{old_key[1]}")
            moved_directives[move_map[old_key]] = source

        # Create all moved directives at their new positions
        for new_key, source in moved_directives.items():
            self._put_directive(
                alpha=new_key[0],
                beta=new_key[1],
                label=source.label,
                content=source.content,
                types=source.types,
                created_by=source.created_by,
                global_directive=source.global_directive,
            )

        # 6. Resequence betas within each alpha tier
        #    After moves/swaps/deletions, beta numbers may have gaps.
        #    Resequence so each tier has contiguous 1,2,3,...
        all_directives = self.load()  # Reload after all changes

        # Group by alpha
        by_alpha: Dict[int, List[Directive]] = defaultdict(list)
        for d in all_directives:
            by_alpha[d.alpha].append(d)

        resequence_items: List[dict] = []
        for alpha, directives in sorted(by_alpha.items()):
            # Sort by current beta to preserve order
            directives.sort(key=lambda d: d.beta)
            for idx, d in enumerate(directives, start=1):
                if d.beta != idx:
                    resequence_items.append({
                        "old_alpha": d.alpha,
                        "old_beta": d.beta,
                        "new_alpha": d.alpha,
                        "new_beta": idx,
                    })

        if resequence_items:
            # Deactivate mismatched and recreate at correct beta
            for item in resequence_items:
                old_key = (item["old_alpha"], item["old_beta"])
                source = None
                for d in all_directives:
                    if d.alpha == old_key[0] and d.beta == old_key[1]:
                        source = d
                        break
                if source is None:
                    continue
                self.deactivate(old_key[0], old_key[1], override=True)
                self._put_directive(
                    alpha=item["new_alpha"],
                    beta=item["new_beta"],
                    label=source.label,
                    content=source.content,
                    types=source.types,
                    created_by=source.created_by,
                    global_directive=source.global_directive,
                )

        # Final reload
        all_directives = self.load()
        return all_directives

    def format_directives(self, directives: List[Directive]) -> str:
        """Format a list of directives for injection into a subagent prompt.

        Args:
            directives: List of Directive objects to format

        Returns:
            Formatted directive block string
        """
        if not directives:
            return ""

        lines = []
        for d in directives:
            lines.append(
                f"{d.alpha}-{d.beta}  {d.label} "
                f"(Directive {self._number_to_text(d.alpha)}-{self._number_to_text(d.beta)})"
            )
            lines.append(d.content)
            lines.append("")  # Blank line between directives

        return "\n".join(lines)
