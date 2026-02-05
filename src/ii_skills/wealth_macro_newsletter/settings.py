from dataclasses import dataclass
from pathlib import Path


@dataclass
class WealthMacroSettings:
    """Configuration placeholder for data sources and delivery targets."""

    base_dir: Path = Path("Memory/wealth_macro_newsletter")
    fred_api_key_path: Path = Path("Config/fred-api-key.txt")
    youtube_api_key_path: Path = Path("Config/youtube-api-key.txt")
    brave_api_key_path: Path = Path("Config/brave-api-key.txt")
    newsletter_recipients_path: Path = Path("Config/wealth-macro-recipients.txt")

    def ensure_dirs(self) -> None:
        (self.base_dir / "newsletters").mkdir(parents=True, exist_ok=True)
        (self.base_dir / "sources").mkdir(parents=True, exist_ok=True)
        (self.base_dir / "charts").mkdir(parents=True, exist_ok=True)
