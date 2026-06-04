# Python Learning App

A local Streamlit app for learning Python foundations through data-analysis-flavored exercises.

## Run With Docker

```powershell
docker compose up --build
```

Open `http://localhost:8501`.

Progress is stored in the named Docker volume `learning_progress`, mounted at `/app/data`. Rebuilding or updating the container will not remove progress unless the volume is deleted.

## Run Tests

```powershell
pytest
```

Inside Docker:

```powershell
docker compose run --rm learning-app pytest
```

## Project Structure

- `src/learning_app/`: Streamlit app and supporting code.
- `content/lessons/`: YAML lesson definitions with stable lesson IDs.
- `tests/`: Unit tests for lesson loading, storage, and exercise checks.
