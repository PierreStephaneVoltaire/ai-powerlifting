







from __future__ import annotations
from typing import List, Optional

class DynamoDBWebhookStore:




    
    def __init__(self, table_name: str):





        self.table_name = table_name
        raise NotImplementedError("DynamoDB backend not yet implemented")

    def create(self, record) -> "WebhookRecord":








        raise NotImplementedError("DynamoDB backend not yet implemented")

    def get(self, webhook_id: str) -> Optional["WebhookRecord"]:








        raise NotImplementedError("DynamoDB backend not yet implemented")

    def list_all(self) -> List["WebhookRecord"]:





        raise NotImplementedError("DynamoDB backend not yet implemented")

    def list_active(self) -> List["WebhookRecord"]:





        raise NotImplementedError("DynamoDB backend not yet implemented")

    def deactivate(self, webhook_id: str) -> bool:








        raise NotImplementedError("DynamoDB backend not yet implemented")
