"""Tests for the bootstrap_owner management command."""

import tomllib
from io import StringIO
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError

ENV_VARS = ("DJANGO_SUPERUSER_USERNAME", "DJANGO_SUPERUSER_EMAIL", "DJANGO_SUPERUSER_PASSWORD")
STRONG_PASSWORD = "plum-orbit-castle-91"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Start every test with none of the superuser variables set."""
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def owner_env(monkeypatch):
    """Owner credentials supplied through the environment."""
    monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "owner")
    monkeypatch.setenv("DJANGO_SUPERUSER_EMAIL", "owner@example.com")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", STRONG_PASSWORD)


@pytest.mark.django_db
def test_creates_superuser_from_env(owner_env):
    """All three variables set: a usable superuser is created."""
    out = StringIO()
    call_command("bootstrap_owner", interactive=False, stdout=out)

    owner = User.objects.get(username="owner")
    assert owner.is_superuser
    assert owner.is_staff
    assert owner.email == "owner@example.com"
    assert owner.check_password(STRONG_PASSWORD)
    assert "Created" in out.getvalue()


@pytest.mark.django_db
def test_existing_user_is_left_alone(owner_env):
    """Re-running is a no-op: the existing account and its password stay."""
    User.objects.create_user(username="owner", password="original-secret-42")

    out = StringIO()
    call_command("bootstrap_owner", interactive=False, stdout=out)

    owner = User.objects.get(username="owner")
    assert owner.check_password("original-secret-42")
    assert not owner.is_superuser
    assert "already exists" in out.getvalue()


@pytest.mark.django_db
def test_existing_user_needs_no_password(monkeypatch):
    """Only the username is needed to detect an existing account."""
    User.objects.create_user(username="owner", password="original-secret-42")
    monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "owner")

    out = StringIO()
    call_command("bootstrap_owner", interactive=False, stdout=out)

    assert "already exists" in out.getvalue()


@pytest.mark.django_db
@pytest.mark.parametrize("missing", ENV_VARS)
def test_noinput_missing_variable_fails(owner_env, monkeypatch, missing):
    """Without a prompt, every variable is required; there are no defaults."""
    monkeypatch.delenv(missing)

    with pytest.raises(CommandError, match=missing):
        call_command("bootstrap_owner", interactive=False, stdout=StringIO())

    assert not User.objects.exists()


@pytest.mark.django_db
def test_noinput_blank_variable_counts_as_missing(owner_env, monkeypatch):
    """An empty placeholder copied from .env.example is not a value."""
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "")

    with pytest.raises(CommandError, match="DJANGO_SUPERUSER_PASSWORD"):
        call_command("bootstrap_owner", interactive=False, stdout=StringIO())


@pytest.mark.django_db
@pytest.mark.parametrize("weak", ["fritz", "password", "12345678"])
def test_weak_password_is_rejected(owner_env, monkeypatch, weak):
    """The configured password validators apply, so a guessable password fails."""
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", weak)

    with pytest.raises(CommandError, match="Password rejected"):
        call_command("bootstrap_owner", interactive=False, stdout=StringIO())

    assert not User.objects.exists()


@pytest.mark.django_db
def test_invalid_email_is_rejected(owner_env, monkeypatch):
    """A malformed email fails before anything is written."""
    monkeypatch.setenv("DJANGO_SUPERUSER_EMAIL", "not-an-email")

    with pytest.raises(CommandError, match="email"):
        call_command("bootstrap_owner", interactive=False, stdout=StringIO())

    assert not User.objects.exists()


@pytest.mark.django_db
def test_interactive_prompts_for_missing_values(monkeypatch):
    """Interactive runs prompt for whatever the environment does not supply."""
    monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "owner")
    answers = iter(["owner@example.com"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr("getpass.getpass", lambda _prompt: STRONG_PASSWORD)

    call_command("bootstrap_owner", stdout=StringIO())

    owner = User.objects.get(username="owner")
    assert owner.is_superuser
    assert owner.email == "owner@example.com"
    assert owner.check_password(STRONG_PASSWORD)


@pytest.mark.django_db
def test_interactive_password_mismatch_fails(owner_env, monkeypatch):
    """The prompted password must be typed the same way twice."""
    monkeypatch.delenv("DJANGO_SUPERUSER_PASSWORD")
    answers = iter([STRONG_PASSWORD, "something-else-77"])
    monkeypatch.setattr("getpass.getpass", lambda _prompt: next(answers))

    with pytest.raises(CommandError, match="match"):
        call_command("bootstrap_owner", stdout=StringIO())

    assert not User.objects.exists()


def test_addinitialuser_is_gone():
    """The passwordless addinitialuser command no longer exists."""
    with pytest.raises(CommandError, match="Unknown command"):
        call_command("addinitialuser")


def test_poe_has_no_hard_coded_credentials():
    """No poe task carries a username, email or password."""
    poe = tomllib.loads((Path(__file__).resolve().parents[2] / ".poe.toml").read_text())
    tasks = poe["tasks"]

    assert "createsuperuser" not in tasks
    assert "bootstrap" in tasks
    text = str(tasks)
    assert "DJANGO_SUPERUSER_PASSWORD" not in text
    assert "fritz" not in text


@pytest.mark.django_db
def test_interactive_without_terminal_fails_cleanly(monkeypatch):
    """A prompt with closed stdin reports the missing variable, not EOFError."""

    def no_input(_prompt):
        raise EOFError

    monkeypatch.setattr("builtins.input", no_input)

    with pytest.raises(CommandError, match="DJANGO_SUPERUSER_USERNAME"):
        call_command("bootstrap_owner", stdout=StringIO())
