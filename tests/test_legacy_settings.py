import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.config import Settings


def test_settings_ignore_removed_bootstrap_credentials(tmp_path):
    legacy_env = tmp_path / ".env"
    legacy_env.write_text(
        "APP_HOST=127.0.0.1\n"
        "BOOTSTRAP_ADMIN_USERNAME=old-admin\n"
        "BOOTSTRAP_ADMIN_PASSWORD=old-password\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=legacy_env)

    assert settings.app_host == "127.0.0.1"
    assert not hasattr(settings, "bootstrap_admin_username")
    assert not hasattr(settings, "bootstrap_admin_password")
