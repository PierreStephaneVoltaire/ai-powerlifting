import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    internal_token: str
    principal_secret: str
    operations_dir: Path
    permissions_path: Path
    service_url_template: str
    profile_url: str
    public_url: str
    state_dir: Path
    model: str
    effort: str
    max_concurrent_turns: int

    @property
    def database(self) -> Path:
        return self.state_dir / "coach.sqlite3"

    @property
    def workspaces(self) -> Path:
        return self.state_dir / "workspaces"

    def service_url(self, domain: str) -> str:
        return self.service_url_template.format(domain=domain).rstrip("/")


def load() -> Settings:
    root = Path(os.getenv("PL_SERVICES_DIR", Path(__file__).resolve().parents[1]))
    return Settings(
        internal_token=os.getenv("INTERNAL_API_TOKEN", ""),
        principal_secret=os.getenv("PL_PRINCIPAL_SECRET", ""),
        operations_dir=Path(os.getenv("PL_OPERATIONS_DIR", root / "operations")),
        permissions_path=Path(os.getenv("PL_PERMISSIONS_PATH", root / "permissions.json")),
        service_url_template=os.getenv("PL_SERVICE_URL_TEMPLATE", "http://pl-{domain}:8000"),
        profile_url=os.getenv("PL_PROFILE_URL", "http://pl-profile:8000"),
        public_url=os.getenv("COACH_URL", "http://127.0.0.1:8000").rstrip("/"),
        state_dir=Path(os.getenv("COACH_STATE_DIR", "./data")),
        model=os.getenv("COACH_MODEL", "gpt-5.6-sol"),
        effort=os.getenv("COACH_REASONING_EFFORT", "medium"),
        max_concurrent_turns=int(os.getenv("COACH_MAX_CONCURRENT_TURNS", "2")),
    )
