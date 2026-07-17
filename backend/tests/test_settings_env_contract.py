from pathlib import Path

from app.config.settings import BACKEND_ENV_FILE, Settings


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _env_keys(path: Path) -> set[str]:
    keys = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key:
            keys.add(key)
    return keys


def test_env_example_matches_settings_schema():
    assert _env_keys(BACKEND_ROOT / ".env.example") == set(Settings.model_fields)


def test_local_env_matches_settings_schema_when_present():
    if BACKEND_ENV_FILE.exists():
        assert _env_keys(BACKEND_ENV_FILE) == set(Settings.model_fields)


def test_backend_env_path_does_not_depend_on_working_directory():
    assert BACKEND_ENV_FILE == BACKEND_ROOT / ".env"
