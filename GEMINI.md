# Gemini Code Assistant Context

This document provides context for the Gemini Code Assistant to understand the Yarkie Tools project.

## Project Overview

Yarkie Tools is a Python-based command-line interface (CLI) for managing YouTube playlists and syncing them with a local SQLite database. It allows users to refresh playlist information, manage video data, and interact with the Discogs API.

The project is built using the following technologies:

- **Python 3.13**
- **Click**: For creating the CLI.
- **SQLAlchemy**: For interacting with the SQLite database.
- **Alembic**: For database migrations.
- **Pydantic**: For data validation and settings management.
- **yt-dlp**: For downloading YouTube video information.
- **Ruff**: For linting and formatting.
- **Pytest**: For testing.

The application is structured around a central `AppContext` that provides access to the database, logger, and other shared resources. The CLI commands are organized into groups (`playlist`, `discogs`, `db`) and are implemented in the `tools/commands` directory.

## Building and Running

The project uses `go-task` for task management. The following commands are available in the `Taskfile.yml`:

- **`task lint`**: Runs Ruff and MyPy to lint the codebase.
- **`task test`**: Runs the test suite using Pytest.
- **`task qa`**: Runs both linting and tests.
- **`task coverage`**: Opens the test coverage report in a browser.

To run the CLI, you can use the following command:

```bash
tools <command>
```

For example, to refresh a playlist:

```bash
tools playlist refresh <playlist_id>
```

## Development Conventions

- **Code Style**: The project uses Ruff for code formatting and linting. The configuration is in `pyproject.toml`.
- **Testing**: Tests are located in the `tests` directory and are written using Pytest. The project aims for a high test coverage.
- **Database Migrations**: Database migrations are managed with Alembic and are located in the `alembic/versions` directory.
- **Dependency Management**: Dependencies are managed with `uv` and are listed in the `pyproject.toml` file.
