"""Unit tests for the `init` command's env-building logic (offline, no prompts)."""

from src.config import Settings
from src.installer import (
    PROVIDERS,
    InstallerAnswers,
    build_env_content,
    env_is_gitignored,
    extra_install_command,
    required_extras,
)


def test_extra_install_command_prefers_pip():
    argv, hint = extra_install_command(
        "api", python_executable="/py", has_pip=True, has_uv=True
    )
    assert argv == ["/py", "-m", "pip", "install", "-e", ".[api]"]
    assert "pip install" in hint


def test_extra_install_command_falls_back_to_uv_without_pip():
    # uv-created venvs have no pip; init must use `uv pip install` instead of failing.
    argv, hint = extra_install_command(
        "auth", python_executable="/py", has_pip=False, has_uv=True
    )
    assert argv == ["uv", "pip", "install", "--python", "/py", "-e", ".[auth]"]
    assert hint.startswith("uv pip install")


def test_extra_install_command_none_when_no_installer():
    argv, hint = extra_install_command(
        "auth", python_executable="/py", has_pip=False, has_uv=False
    )
    assert argv is None
    assert ".[auth]" in hint


def test_required_extras_per_scenario():
    # CLI + local needs the sqlite driver ([auth]) since it writes a DATABASE_URL.
    assert required_extras(InstallerAnswers("cli", "openai", "local", "open")) == [
        ("auth", "aiosqlite")
    ]
    # Web bundles the db driver in [api]; local adds nothing more.
    assert required_extras(InstallerAnswers("web", "openai", "local", "open")) == [
        ("api", "fastapi")
    ]
    # Postgres always needs asyncpg; web also needs the server.
    assert required_extras(InstallerAnswers("cli", "openai", "postgres", "open")) == [
        ("postgres", "asyncpg")
    ]
    assert required_extras(InstallerAnswers("web", "openai", "postgres", "multi")) == [
        ("api", "fastapi"),
        ("postgres", "asyncpg"),
    ]


def test_only_chosen_provider_key_slot_is_emitted():
    """The key/model pairing is unmistakable: only one provider's key slot appears."""
    env = build_env_content(InstallerAnswers("cli", "anthropic", "local", "open"))
    assert "MODEL_NAME=anthropic:claude-sonnet-4-5" in env
    assert "ANTHROPIC_API_KEY=" in env
    for other in ("OPENAI_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY", "DEEPSEEK_API_KEY"):
        assert other not in env


def test_no_secret_is_ever_written_for_the_key():
    """init never sees the key: the slot is left blank for the user to fill."""
    env = build_env_content(InstallerAnswers("cli", "openai", "local", "open"))
    assert "OPENAI_API_KEY=\n" in env


def test_agent_name_written_and_defaulted():
    named = build_env_content(
        InstallerAnswers("cli", "openai", "local", "open", agent_name="Acme Bot")
    )
    assert "AGENT_NAME=Acme Bot" in named
    # Defaults to the kit name when the user accepts the default.
    default = build_env_content(InstallerAnswers("cli", "openai", "local", "open"))
    assert "AGENT_NAME=PydanKit" in default


def test_open_vs_multi_auth_flag():
    assert "AUTH_ENABLED=false" in build_env_content(
        InstallerAnswers("cli", "openai", "local", "open")
    )
    assert "AUTH_ENABLED=true" in build_env_content(
        InstallerAnswers("web", "openai", "local", "multi")
    )


def test_persistence_local_vs_postgres():
    local = build_env_content(InstallerAnswers("cli", "openai", "local", "open"))
    assert "sqlite+aiosqlite:///./pydankit.db" in local
    pg = build_env_content(InstallerAnswers("cli", "openai", "postgres", "open"))
    assert "postgresql+asyncpg://" in pg


def test_web_writes_cors_and_cookie_note_cli_does_not():
    web = build_env_content(InstallerAnswers("web", "openai", "local", "open"))
    assert "CORS_ORIGINS=" in web
    assert "SESSION_COOKIE_SECURE=false" in web
    cli = build_env_content(InstallerAnswers("cli", "openai", "local", "open"))
    assert "CORS_ORIGINS=" not in cli


def test_admin_seeded_only_for_web_multi():
    seeded = build_env_content(
        InstallerAnswers(
            "web", "openai", "local", "multi", admin_username="alice", admin_password="pw"
        )
    )
    assert "ADMIN_USERNAME=alice" in seeded
    assert "ADMIN_PASSWORD=pw" in seeded
    # CLI + multi-user does not seed an admin (the CLI is a trusted shell).
    cli_multi = build_env_content(InstallerAnswers("cli", "openai", "local", "multi"))
    assert "ADMIN_USERNAME" not in cli_multi


def test_needs_admin_seed_property():
    assert InstallerAnswers("web", "openai", "local", "multi").needs_admin_seed is True
    assert InstallerAnswers("cli", "openai", "local", "multi").needs_admin_seed is False
    assert InstallerAnswers("web", "openai", "local", "open").needs_admin_seed is False


def test_every_provider_has_a_complete_curated_entry():
    """Sanity: each curated provider emits its model string and its key var."""
    for key, prov in PROVIDERS.items():
        env = build_env_content(InstallerAnswers("web", key, "local", "open"))
        assert prov["model"] in env
        assert prov["key_var"] in env


def test_generated_env_binds(tmp_path, monkeypatch):
    # conftest pins DATABASE_URL in the session env (it outranks the file); drop it so
    # the value the installer wrote is the one that binds.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        build_env_content(InstallerAnswers("web", "openai", "postgres", "open")),
        encoding="utf-8",
    )
    s = Settings(_env_file=str(env_file))  # type: ignore[call-arg]
    assert s.auth_enabled is False
    assert s.cors_origins == ["http://localhost:8000"]
    assert s.database_url.startswith("postgresql+asyncpg://")


def test_env_is_gitignored(tmp_path):
    assert env_is_gitignored(tmp_path) is False  # no .gitignore at all
    (tmp_path / ".gitignore").write_text("__pycache__/\n.env\n", encoding="utf-8")
    assert env_is_gitignored(tmp_path) is True
