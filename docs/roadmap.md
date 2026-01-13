# Nutrisho Modernization Roadmap

This document outlines a roadmap for modernizing the Nutrisho recipe management application. The goal is to bring the project up to modern Python and Django standards, improve developer experience, and pave the way for future feature development.

## Phase 1: Foundational Improvements

This phase focuses on bringing the project up to date with current best practices and modern tooling.

1.  **Upgrade Dependencies:**

    - [✅] Resolve dependency manager conflict: Confirm uv is the chosen dependency manager and remove poetry references from Makefile.
    - [✅] Identify current Django, PyYAML, and google-genai versions from pyproject.toml.
    - [✅] Ensure .venv exists and dependencies are installed with uv by running uv venv and uv sync from the project root.
    - [✅] Identify latest LTS Django version compatible with Python 3.14 (or adjust Python version if necessary).
    - [✅] Upgrade PyYAML and google-genai to their latest versions.
    - [✅] Integrate ty for typechecking.
    - [✅] Ensure ruff is up-to-date and run it
    - [✅] Investigate and propose a modern task manager to replace Make. (Proposed: Invoke)
    - [✅] Replace make with Taskfile as a task runner, and migrate all the tasks using the structure in @../sam-audio-playground/audio-playground/Taskfile.yml

2.  **Modernize Django App Structure:**

    - [✅] Move the `recipes` app to a more standard location. Use an src/ layout if possible
    - [✅] Organize templates, static files, and management commands according to Django best practices.

3.  **Implement a Robust Settings Configuration:**

    - Use a library like `django-environ` to manage settings via environment variables. This will improve security by removing secrets from source code.
    - Create separate settings files for development and production environments.

4.  **Introduce HTMX and Tailwind CSS:**
    - Integrate HTMX to add dynamic, interactive features to the frontend without writing complex JavaScript.
    - Use Tailwind CSS for a utility-first approach to styling, allowing for rapid development of a modern user interface.
    - Set up a process to compile Tailwind's CSS, for example by using the `tailwindcss` CLI.

## Phase 2: Core Functionality and DX

This phase focuses on improving the core functionality of the application and the developer experience.

1.  **Implement Full CRUD for Recipes:**

    - Replace the raw SQL editing with proper Django forms and views for creating, reading, updating, and deleting recipes. This is the highest priority feature to implement.
    - Implement user authentication and authorization to ensure that only authorized users can edit recipes.

2.  **Improve the Data Model:**

    - Review and refactor the existing data models in the `recipes` app.
    - Use `pydantic` for data validation and to define clear data structures.

3.  **Enhance the Admin Interface:**

    - Customize the Django admin interface for better management of recipes, ingredients, and other models.

4.  **Introduce a Testing Framework:**
    - Set up `pytest` for running tests.
    - Write a comprehensive test suite, including unit and integration tests, to ensure code quality and prevent regressions.
    - Ensure tests and data quality are run on ever merge via github workflows

## Phase 3: New Features and Future Development

This phase focuses on adding new features to the application.

1.  **Add a "Meal Plan" Feature:**

    - Allow users to create meal plans for a week or a month.
    - Generate a shopping list based on the selected meal plan.

2.  **Implement a Search and Filtering System:**

    - Add a search bar to search for recipes by name, ingredients, or tags.
    - Implement filtering options to narrow down search results.

3.  **User Profiles and Social Features:**

    - Allow users to create profiles and save their favorite recipes.
    - Implement a rating and review system for recipes.

4.  **API Development:**
    - Create a RESTful API using Django Rest Framework to allow other applications to interact with the recipe data.
