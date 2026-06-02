"""DynamoDB-backed read-side store for federation and qualification standards."""
from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

import boto3

class FederationStore:
    FEDERATIONS_SK = "federations#v1"

    def __init__(self, table_name: str, pk: str = "operator", region: str = "ca-central-1"):
        self._table_name = table_name
        self._pk = pk
        self._region = region
        self._table = None

    @property
    def pk(self) -> str:
        return self._pk

    @pk.setter
    def pk(self, value: str) -> None:
        self._pk = value

    @property
    def table(self):
        if self._table is None:
            self._table = boto3.resource("dynamodb", region_name=self._region).Table(self._table_name)
        return self._table

    def _sanitize_decimals(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return float(obj) if obj % 1 > 0 else int(obj)
        if isinstance(obj, dict):
            return {key: self._sanitize_decimals(value) for key, value in obj.items()}
        if isinstance(obj, list):
            return [self._sanitize_decimals(value) for value in obj]
        return obj

    def get_library_sync(self) -> dict:
        response = self.table.get_item(Key={"pk": self._pk, "sk": self.FEDERATIONS_SK})
        item = response.get("Item")
        if not item:
            return {
                "pk": self._pk,
                "sk": self.FEDERATIONS_SK,
                "updated_at": "",
                "federations": [],
                "qualification_standards": [],
            }
        return self._sanitize_decimals(item)

    async def get_library(self) -> dict:
        return await asyncio.get_running_loop().run_in_executor(None, self.get_library_sync)
