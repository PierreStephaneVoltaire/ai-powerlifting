
















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












    
    def __init__(self, table_name: str = "if-core", region: str = "ca-central-1", pk: str = "operator"):







        self.table_name = table_name
        self._table = None
        self._cache: List[Directive] = []
        self._region = region
        self._pk = pk
    
    @property
    def table(self):

        if self._table is None:
            self._table = boto3.resource(
                "dynamodb", region_name=self._region
            ).Table(self.table_name)
        return self._table
    
    def load(self) -> List[Directive]:












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
        
        directives = []
        for base_key, versions in by_alpha_beta.items():
            active_versions = [v for v in versions if v.active]
            if active_versions:
                active_versions.sort(key=lambda d: d.version, reverse=True)
                directives.append(active_versions[0])
        
        directives.sort(key=lambda d: (d.alpha, d.beta))
        self._cache = directives
        
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












        if not self._cache:
            return ""
        
        lines = []
        for d in self._cache:
            lines.append(
                f"{d.alpha}-{d.beta}  {d.label} "
                f"(Directive {self._number_to_text(d.alpha)}-{self._number_to_text(d.beta)})"
            )
            lines.append(d.content)
            lines.append("")
        
        return "\n".join(lines)
    
    @staticmethod
    def _number_to_text(n: int) -> str:








        return num2words(n).title()
    
    def next_beta(self, alpha: int) -> int:










        max_beta = 0
        for d in self._cache:
            if d.alpha == alpha and d.beta > max_beta:
                max_beta = d.beta
        return max_beta + 1
    
    def _get_latest_version(self, alpha: int, beta: int) -> Optional[Directive]:












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














        if global_directive and self._pk != "operator":
            raise ValueError("global_directive=True is only allowed when pk is 'operator'")

        beta = self.next_beta(alpha)
        now = datetime.now(timezone.utc).isoformat()

        directive = Directive(
            alpha=alpha,
            beta=beta,
            version=1,
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
        self.load()
        
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
















        existing = self._get_latest_version(alpha, beta)
        if not existing:
            return None
        
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
        self.load()
        
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
        
        self.load()
        logger.info(f"[DirectiveStore] Deactivated directive {alpha}-{beta}")
        return True
    
    def get(self, alpha: int, beta: int) -> Optional[Directive]:









        for d in self._cache:
            if d.alpha == alpha and d.beta == beta:
                return d
        return None
    
    def get_all(self, alpha: Optional[int] = None) -> List[Directive]:








        if alpha is None:
            return list(self._cache)
        return [d for d in self._cache if d.alpha == alpha]

    def get_all_global(self) -> List[Directive]:








        return [d for d in self._cache if d.global_directive and d.active]

    def get_history(self, alpha: int, beta: int) -> List[Directive]:









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

    MAIN_AGENT_ONLY_TYPES = {"tool", "memory", "metacognition"}

    def get_by_types(self, types: List[str]) -> List[Directive]:





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














        result_by_key = {}

        type_set = set(types) if types else set()

        for d in self._cache:
            if not d.active:
                continue

            d_types = set(d.types)

            if d.alpha == 0:
                result_by_key[(d.alpha, d.beta)] = d
                continue

            if d_types.issubset(self.MAIN_AGENT_ONLY_TYPES):
                continue

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


















        now = datetime.now(timezone.utc).isoformat()

        directive = Directive(
            alpha=alpha,
            beta=beta,
            version=1,
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




















        all_directives = self.load()

        by_key: Dict[tuple, Directive] = {(d.alpha, d.beta): d for d in all_directives}

        for item in items:
            key = (item["old_alpha"], item["old_beta"])
            if key not in by_key:
                raise ValueError(f"Directive {key[0]}-{key[1]} not found")

        move_map: Dict[tuple, tuple] = {}
        for item in items:
            old_key = (item["old_alpha"], item["old_beta"])
            new_key = (item["new_alpha"], item["new_beta"])
            move_map[old_key] = new_key

        moved_directives: Dict[tuple, Directive] = {}

        for old_key in move_map:
            source = by_key[old_key]
            deactivated = self.deactivate(old_key[0], old_key[1], override=True)
            if not deactivated:
                raise ValueError(f"Failed to deactivate directive {old_key[0]}-{old_key[1]}")
            moved_directives[move_map[old_key]] = source

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

        all_directives = self.load()

        by_alpha: Dict[int, List[Directive]] = defaultdict(list)
        for d in all_directives:
            by_alpha[d.alpha].append(d)

        resequence_items: List[dict] = []
        for alpha, directives in sorted(by_alpha.items()):
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

        all_directives = self.load()
        return all_directives

    def format_directives(self, directives: List[Directive]) -> str:








        if not directives:
            return ""

        lines = []
        for d in directives:
            lines.append(
                f"{d.alpha}-{d.beta}  {d.label} "
                f"(Directive {self._number_to_text(d.alpha)}-{self._number_to_text(d.beta)})"
            )
            lines.append(d.content)
            lines.append("")

        return "\n".join(lines)
