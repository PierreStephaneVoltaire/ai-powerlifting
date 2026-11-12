import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Provider:
    auth: str
    max_concurrent: int
    base_url: str | None = None
    api_key: str = ""

    @property
    def subscription(self) -> bool:
        return self.auth == "chatgpt"


@dataclass(frozen=True)
class AISettings:
    provider: str
    model: str
    effort: str


@dataclass(frozen=True)
class Settings:
    operations_dir: Path
    permissions_path: Path
    service_url_template: str
    public_url: str
    state_dir: Path
    providers: dict[str, Provider]
    conversation_ai: AISettings
    operation_ai: dict[str, AISettings]

    @property
    def database(self) -> Path:
        return self.state_dir / "coach.sqlite3"

    @property
    def workspaces(self) -> Path:
        return self.state_dir / "workspaces"

    def service_url(self, domain: str) -> str:
        return self.service_url_template.format(domain=domain).rstrip("/")


def _providers() -> dict[str, Provider]:
    keys = json.loads(os.getenv("COACH_PROVIDER_KEYS") or "{}")
    return {name: Provider(**value, api_key=keys.get(name, "")) for name, value in json.loads(os.environ["COACH_PROVIDERS"]).items()}


def load() -> Settings:
    root = Path(os.getenv("PL_SERVICES_DIR", Path(__file__).resolve().parents[1]))
    return Settings(
        operations_dir=Path(os.getenv("PL_OPERATIONS_DIR", root / "operations")),
        permissions_path=Path(os.getenv("PL_PERMISSIONS_PATH", root / "permissions.json")),
        service_url_template=os.getenv("PL_SERVICE_URL_TEMPLATE", "http://pl-{domain}:8000"),
        public_url=os.getenv("COACH_URL", "http://127.0.0.1:8000").rstrip("/"),
        state_dir=Path(os.getenv("COACH_STATE_DIR", "./data")),
        providers=_providers(),
        conversation_ai=AISettings(**json.loads(os.environ["COACH_CONVERSATION_AI"])),
        operation_ai={name: AISettings(**value) for name, value in json.loads(os.environ["COACH_OPERATION_AI"]).items()},
    )
