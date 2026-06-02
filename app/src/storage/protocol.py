




from __future__ import annotations
from typing import Protocol, runtime_checkable, List, Optional

@runtime_checkable
class WebhookStore(Protocol):





    
    def create(self, record: "WebhookRecord") -> "WebhookRecord":








        ...
    
    def get(self, webhook_id: str) -> Optional["WebhookRecord"]:








        ...
    
    def list_all(self) -> List["WebhookRecord"]:





        ...
    
    def list_active(self) -> List["WebhookRecord"]:





        ...
    
    def deactivate(self, webhook_id: str) -> bool:








        ...
