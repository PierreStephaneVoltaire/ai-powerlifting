"""DynamoDB-backed store for training programs.

Uses a pointer-based schema to track the current program version.
Pointer item: pk=HEALTH_PROGRAM_PK, sk="program#current" -> {version, ref_sk, updated_at}
Program item: pk=HEALTH_PROGRAM_PK, sk="program#v{version:03d}" -> full program JSON
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

import boto3
from boto3.dynamodb.conditions import Key, Attr

logger = logging.getLogger(__name__)

class ProgramNotFoundError(Exception):
    """Raised when pointer item does not exist in DynamoDB."""
    pass

class CurrentProgramHasFutureSessionsError(Exception):
    """Raised when trying to archive a program that still has planned future sessions."""
    pass

class ProgramStore:
    """DynamoDB-backed store for training programs with versioning support.

    Schema:
        - Pointer item: pk=HEALTH_PROGRAM_PK, sk="program#current"
          -> {version: int, ref_sk: str, updated_at: ISO8601}
        - Program item: pk=HEALTH_PROGRAM_PK, sk="program#v{version:03d}"
          -> full program JSON as DynamoDB map

    All operations are cached in memory for performance.
    """

    POINTER_SK = "program#current"
    PROGRAM_SK_PREFIX = "program#v"

    def __init__(self, table_name: str, pk: str = "operator", region: str = "ca-central-1"):
        """Initialize the program store.

        Args:
            table_name: Name of the DynamoDB table
            pk: Partition key value (default: "operator")
            region: AWS region (default: "ca-central-1")
        """
        self._table_name = table_name
        self._pk = pk
        self._region = region
        self._sessions_table_name = os.environ.get("IF_SESSIONS_TABLE_NAME", "if-sessions")
        self._table = None
        self._cache: Optional[dict] = None
        self._cache_version: Optional[int] = None

        logger.debug(f"[ProgramStore] Initialized with table={table_name}, pk={pk}, region={region}")

    @property
    def pk(self) -> str:
        """Active DynamoDB partition key."""
        return self._pk

    @pk.setter
    def pk(self, value: str) -> None:
        """Switch active partition key and clear cached program data."""
        if value != self._pk:
            self._pk = value
            self.invalidate_cache()

    @property
    def table(self):
        """Lazy-load DynamoDB table resource."""
        if self._table is None:
            self._table = boto3.resource(
                "dynamodb", region_name=self._region
            ).Table(self._table_name)
        return self._table
    
    def invalidate_cache(self) -> None:
        """Clear the in-memory cache."""
        logger.debug("[ProgramStore] Cache invalidated")
        self._cache = None
        self._cache_version = None

    def _invalidate_analysis_cache(self) -> None:
        try:
            from cache_invalidation import invalidate_analysis_caches
            invalidate_analysis_caches(self._pk, self._table_name, self._region)
        except Exception as exc:
            logger.warning("[ProgramStore] Analysis cache invalidation failed: %s", exc)

    def _get_session_store(self):
        from session_store import SessionStore
        return SessionStore(
            table_name=self._sessions_table_name,
            pk=self._pk,
            region=self._region,
            source_table_name=self._table_name,
        )

    def _current_program_sk_sync(self) -> str:
        pointer_resp = self.table.get_item(Key={"pk": self._pk, "sk": self.POINTER_SK})
        if "Item" in pointer_resp:
            ref_sk = pointer_resp["Item"].get("ref_sk")
            if ref_sk:
                return str(ref_sk)

        programs = self._list_programs_sync(include_archived=False)
        if not programs:
            raise ProgramNotFoundError(
                f"No program or pointer found for pk={self._pk}. "
                "Create a program using new_version() first."
            )
        programs.sort(key=lambda p: p["sk"], reverse=True)
        return str(programs[0]["sk"])
    
    async def get_program(self) -> dict:
        """Get the current training program.
        
        Returns cached program if available, otherwise loads from DynamoDB.
        
        Returns:
            Full program dict
            
        Raises:
            ProgramNotFoundError: If pointer item does not exist
            RuntimeError: If DynamoDB operation fails
        """
        if self._cache is not None:
            logger.debug("[ProgramStore] Cache hit, returning cached program")
            return self._cache
        
        logger.debug("[ProgramStore] Cache miss, loading from DynamoDB")
        
        try:
            program = await asyncio.get_running_loop().run_in_executor(
                None, self._load_program_sync
            )
            
            self._cache = program
            return program
            
        except ProgramNotFoundError:
            raise
        except Exception as e:
            import traceback
            logger.error(f"[ProgramStore] Failed to load program: {e}\n{traceback.format_exc()}")
            raise RuntimeError(f"Failed to load program from DynamoDB: {e}")
    
    def _load_program_sync(self) -> dict:
        """Synchronous program loading logic."""
        logger.info(f"[ProgramStore] Reading pointer from table='{self._table_name}' region='{self._region}': pk={self._pk}, sk={self.POINTER_SK}")
        pointer_resp = self.table.get_item(
            Key={"pk": self._pk, "sk": self.POINTER_SK}
        )

        if "Item" not in pointer_resp:
            logger.info(f"[ProgramStore] Pointer not found, scanning for existing program versions...")
            try:
                scan_result = self.table.scan(
                    FilterExpression=Attr("pk").eq(self._pk) & Attr("sk").begins_with(self.PROGRAM_SK_PREFIX)
                )
                items = scan_result.get("Items", [])

                if not items:
                    raise ProgramNotFoundError(
                        f"No program or pointer found for pk={self._pk}. "
                        "Create a program using new_version() first."
                    )

                latest_version = 0
                latest_sk = None
                for item in items:
                    sk = item.get("sk", "")
                    if sk.startswith(self.PROGRAM_SK_PREFIX):
                        try:
                            version_str = sk[len(self.PROGRAM_SK_PREFIX):]
                            version = int(version_str)
                            if version > latest_version:
                                latest_version = version
                                latest_sk = sk
                        except ValueError:
                            continue

                if not latest_sk:
                    raise ProgramNotFoundError(
                        f"No valid program versions found for pk={self._pk}. "
                        "Create a program using new_version() first."
                    )

                now = datetime.now(timezone.utc).isoformat()
                pointer_item = {
                    "pk": self._pk,
                    "sk": self.POINTER_SK,
                    "version": latest_version,
                    "ref_sk": latest_sk,
                    "updated_at": now,
                }
                self.table.put_item(Item=pointer_item)
                logger.info(f"[ProgramStore] Auto-created pointer to version {latest_version} ({latest_sk})")

                pointer_resp = self.table.get_item(
                    Key={"pk": self._pk, "sk": self.POINTER_SK}
                )

            except ProgramNotFoundError:
                raise
            except Exception as scan_err:
                logger.error(f"[ProgramStore] Failed to scan for programs: {scan_err}")
                raise ProgramNotFoundError(
                    f"No program pointer found for pk={self._pk}. "
                    "Create a program using new_version() first."
                )
        
        pointer = pointer_resp["Item"]
        version = int(pointer.get("version", 0))
        ref_sk = pointer.get("ref_sk", f"{self.PROGRAM_SK_PREFIX}{version:03d}")
        
        logger.debug(f"[ProgramStore] Pointer points to version={version}, ref_sk={ref_sk}")
        
        logger.debug(f"[ProgramStore] Reading program: pk={self._pk}, sk={ref_sk}")
        program_resp = self.table.get_item(
            Key={"pk": self._pk, "sk": ref_sk}
        )
        
        if "Item" not in program_resp:
            logger.error(f"[ProgramStore] Program item not found: pk={self._pk}, sk={ref_sk}")
            raise RuntimeError(
                f"Program item not found at {ref_sk}. "
                "Data inconsistency: pointer exists but program item missing."
            )
        
        program = dict(program_resp["Item"])
        program.pop("pk", None)
        program.pop("sk", None)
        program["sessions"] = self._get_session_store().list_sessions_sync(
            str(ref_sk),
            program.get("phases", []) if isinstance(program.get("phases"), list) else [],
        )
        
        self._cache_version = version
        logger.debug(f"[ProgramStore] Loaded program version {version}")
        
        return program
    
    async def update_session(self, date: str, patch: dict) -> dict:
        """Update a session by date with the given patch.
        
        Creates a new minor version of the program.
        
        Args:
            date: ISO8601 date string of the session to update
            patch: Dict with session fields to update
            
        Returns:
            Updated program dict
            
        Raises:
            ValueError: If session not found or patch invalid
            RuntimeError: If DynamoDB operation fails
        """
        program = await self.get_program()
        program_sk = await asyncio.get_running_loop().run_in_executor(
            None, self._current_program_sk_sync
        )
        await self._get_session_store().patch_session(
            program_sk,
            date,
            patch,
            program.get("phases", []) if isinstance(program.get("phases"), list) else [],
        )
        self.invalidate_cache()
        return await self.get_program()
    
    async def new_version(self, patches: list[dict], change_reason: str) -> dict:
        """Create a new major version of the program with patches.
        
        Args:
            patches: List of patches, each with "path" and "value" keys
                    Example: {"path": "sessions[0].exercises[1].kg", "value": 180}
            change_reason: Human-readable reason for the version change
            
        Returns:
            New program dict
            
        Raises:
            ValueError: If patch path is invalid
            RuntimeError: If DynamoDB operation fails
        """
        program = await self.get_program()
        
        new_program = copy.deepcopy(program)
        
        for patch in patches:
            path = patch.get("path", "")
            value = patch.get("value")
            
            if not path:
                raise ValueError("Patch must have 'path' key")
            
            self._apply_patch(new_program, path, value)
        
        if "meta" not in new_program:
            new_program["meta"] = {}
        if "change_log" not in new_program["meta"]:
            new_program["meta"]["change_log"] = []
        new_program["meta"]["change_log"].append({
            "reason": change_reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        
        updated_program = await self._write_new_version(new_program, minor=False)
        
        return updated_program
    
    def _apply_patch(self, obj: dict, path: str, value: Any) -> None:
        """Apply a JSON-path-like patch to an object.
        
        Supports paths like:
            - "sessions[0].exercises[1].kg"
            - "meta.comp_date"
            - "phases[2].end_week"
        
        Args:
            obj: Object to patch
            path: Path to the field to update
            value: New value
            
        Raises:
            ValueError: If path is invalid
        """
        import re
        
        segments = []
        for part in path.split("."):
            match = re.match(r"^(\w+)\[(\d+)\]$", part)
            if match:
                segments.append((match.group(1), int(match.group(2))))
            else:
                segments.append((part, None))
        
        current = obj
        for i, (key, idx) in enumerate(segments[:-1]):
            if idx is not None:
                if key not in current:
                    raise ValueError(f"Invalid path '{path}': '{key}' not found")
                if not isinstance(current[key], list):
                    raise ValueError(f"Invalid path '{path}': '{key}' is not a list")
                if idx >= len(current[key]):
                    raise ValueError(f"Invalid path '{path}': index {idx} out of range")
                current = current[key][idx]
            else:
                if not isinstance(current, dict):
                    raise ValueError(f"Invalid path '{path}': expected dict at '{key}'")
                if key not in current:
                    raise ValueError(f"Invalid path '{path}': '{key}' not found")
                current = current[key]
        
        final_key, final_idx = segments[-1]
        if final_idx is not None:
            if final_key not in current:
                raise ValueError(f"Invalid path '{path}': '{final_key}' not found")
            if not isinstance(current[final_key], list):
                raise ValueError(f"Invalid path '{path}': '{final_key}' is not a list")
            if final_idx >= len(current[final_key]):
                raise ValueError(f"Invalid path '{path}': index {final_idx} out of range")
            current[final_key][final_idx] = value
        else:
            if not isinstance(current, dict):
                raise ValueError(f"Invalid path '{path}': expected dict at '{final_key}'")
            current[final_key] = value
    
    async def _write_new_version(self, program: dict, minor: bool) -> dict:
        """Write a new version of the program to DynamoDB.
        
        Args:
            program: Program dict to write
            minor: If True, increment minor version (1.0 -> 1.1)
                   If False, increment major version (1.0 -> 2.0)
            
        Returns:
            The written program dict
            
        Raises:
            RuntimeError: If DynamoDB operation fails
        """
        try:
            result = await asyncio.get_running_loop().run_in_executor(
                None, lambda: self._write_new_version_sync(program, minor)
            )
            return result
        except Exception as e:
            logger.error(f"[ProgramStore] Failed to write new version: {e}")
            raise RuntimeError(f"Failed to write new version to DynamoDB: {e}")
    
    @staticmethod
    def _floats_to_decimals(obj: Any) -> Any:
        """Recursively convert float values to Decimal for DynamoDB compatibility.

        DynamoDB's boto3 client does not support Python float types.
        All floats must be converted to Decimal before writing.
        None values are left as-is (DynamoDB accepts null).
        """
        if isinstance(obj, float):
            return Decimal(str(obj))
        if isinstance(obj, dict):
            return {k: ProgramStore._floats_to_decimals(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [ProgramStore._floats_to_decimals(v) for v in obj]
        return obj

    def _write_new_version_sync(self, program: dict, minor: bool) -> dict:
        """Synchronous version writing logic."""
        now = datetime.now(timezone.utc).isoformat()
        
        logger.debug(f"[ProgramStore] Reading current pointer for version increment")
        pointer_resp = self.table.get_item(
            Key={"pk": self._pk, "sk": self.POINTER_SK}
        )
        
        if "Item" in pointer_resp:
            current_version = int(pointer_resp["Item"].get("version", 0))
        else:
            current_version = 0
        
        new_version_int = current_version + 1
        
        if "meta" not in program:
            program["meta"] = {}
        
        current_label = program["meta"].get("version_label", "0.0")
        try:
            major, minor_num = map(int, current_label.split("."))
            if minor:
                new_label = f"{major}.{minor_num + 1}"
            else:
                new_label = f"{major + 1}.0"
        except (ValueError, AttributeError):
            new_label = "1.0" if current_version == 0 else f"{new_version_int}.0"
        
        program["meta"]["version_label"] = new_label
        program["meta"]["updated_at"] = now
        
        new_sk = f"{self.PROGRAM_SK_PREFIX}{new_version_int:03d}"

        sessions = copy.deepcopy(program.get("sessions", []))
        program_without_sessions = copy.deepcopy(program)
        program_without_sessions.pop("sessions", None)

        program_item = {
            "pk": self._pk,
            "sk": new_sk,
            **program_without_sessions
        }
        
        program_item = self._floats_to_decimals(program_item)
        
        logger.debug(f"[ProgramStore] Writing new program version: sk={new_sk}, label={new_label}")
        self.table.put_item(Item=program_item)

        self._get_session_store().replace_program_sessions_sync(
            new_sk,
            sessions if isinstance(sessions, list) else [],
            program.get("phases", []) if isinstance(program.get("phases"), list) else [],
        )
        
        pointer_item = {
            "pk": self._pk,
            "sk": self.POINTER_SK,
            "version": new_version_int,
            "ref_sk": new_sk,
            "updated_at": now,
        }
        
        logger.debug(f"[ProgramStore] Updating pointer to version={new_version_int}")
        self.table.put_item(Item=pointer_item)
        logger.info(f"[ProgramStore] Created new {'minor' if minor else 'major'} version: {new_label} (v{new_version_int})")

        return program

    async def archive(self, sk: str) -> None:
        """Archive a program version.

        If the program being archived is the current active program,
        this will attempt to point 'program#current' to the most recent
        non-archived version.

        Args:
            sk: SK of the program to archive (e.g. "program#v001")

        Raises:
            CurrentProgramHasFutureSessionsError: If current program has incomplete future sessions
            ProgramNotFoundError: If program does not exist
        """
        await asyncio.get_running_loop().run_in_executor(
            None, lambda: self._archive_sync(sk)
        )
        self.invalidate_cache()

    def _archive_sync(self, sk: str) -> None:
        """Synchronous archive logic."""
        resp = self.table.get_item(Key={"pk": self._pk, "sk": sk})
        if "Item" not in resp:
            raise ProgramNotFoundError(f"Program not found: {sk}")
        
        program = resp["Item"]
        
        pointer_resp = self.table.get_item(Key={"pk": self._pk, "sk": self.POINTER_SK})
        is_current = "Item" in pointer_resp and pointer_resp["Item"].get("ref_sk") == sk
        
        if is_current:
            sessions = self._get_session_store().list_sessions_sync(
                sk,
                program.get("phases", []) if isinstance(program.get("phases"), list) else [],
            )
            has_future = any(
                not s.get("completed", False) and s.get("date", "") >= datetime.now().strftime("%Y-%m-%d")
                for s in sessions
            )
            if has_future:
                raise CurrentProgramHasFutureSessionsError(
                    "Cannot archive active program with incomplete future sessions. "
                    "Mark them as completed or skipped first, or delete them."
                )

        now = datetime.now(timezone.utc).isoformat()
        if "meta" not in program:
            program["meta"] = {}
        program["meta"]["archived"] = True
        program["meta"]["archived_at"] = now
        
        self.table.put_item(Item=program)
        logger.info(f"[ProgramStore] Archived program {sk}")
        
        if is_current:
            self._repoint_current_to_latest_non_archived_sync()

    def _repoint_current_to_latest_non_archived_sync(self) -> None:
        """Find the latest non-archived program and update the pointer to it."""
        programs = self._list_programs_sync(include_archived=False)
        if not programs:
            logger.warning("[ProgramStore] No non-archived programs found to repoint 'program#current'")
            self.table.delete_item(Key={"pk": self._pk, "sk": self.POINTER_SK})
            return

        programs.sort(key=lambda p: p["sk"], reverse=True)
        latest = programs[0]
        
        now = datetime.now(timezone.utc).isoformat()
        version_str = latest["sk"][len(self.PROGRAM_SK_PREFIX):]
        pointer_item = {
            "pk": self._pk,
            "sk": self.POINTER_SK,
            "version": int(version_str),
            "ref_sk": latest["sk"],
            "updated_at": now,
        }
        self.table.put_item(Item=pointer_item)
        logger.info(f"[ProgramStore] Repointed 'program#current' to {latest['sk']}")

    async def unarchive(self, sk: str) -> None:
        """Unarchive a program version.

        Args:
            sk: SK of the program to unarchive

        Raises:
            ProgramNotFoundError: If program does not exist
        """
        await asyncio.get_running_loop().run_in_executor(
            None, lambda: self._unarchive_sync(sk)
        )
        self.invalidate_cache()

    def _unarchive_sync(self, sk: str) -> None:
        """Synchronous unarchive logic."""
        resp = self.table.get_item(Key={"pk": self._pk, "sk": sk})
        if "Item" not in resp:
            raise ProgramNotFoundError(f"Program not found: {sk}")
        
        program = resp["Item"]
        if "meta" not in program:
            program["meta"] = {}
        
        program["meta"]["archived"] = False
        program["meta"]["archived_at"] = None
        
        self.table.put_item(Item=program)
        logger.info(f"[ProgramStore] Unarchived program {sk}")

    async def list_programs(self, include_archived: bool = False) -> list[dict]:
        """List all program versions.

        Args:
            include_archived: Whether to include archived programs in the list

        Returns:
            List of program summaries (sk, meta, etc.)
        """
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self._list_programs_sync(include_archived)
        )

    def _list_programs_sync(self, include_archived: bool = False) -> list[dict]:
        """Synchronous program listing logic."""
        scan_result = self.table.query(
            KeyConditionExpression=Key("pk").eq(self._pk) & Key("sk").begins_with(self.PROGRAM_SK_PREFIX)
        )
        items = scan_result.get("Items", [])
        
        if not include_archived:
            items = [
                item for item in items 
                if not item.get("meta", {}).get("archived", False)
            ]
        
        results = []
        for item in items:
            p = dict(item)
            results.append(p)
            
        return results
