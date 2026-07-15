FROM python:3.12-slim

WORKDIR /app

# uv is a fast pip replacement; we use it to install deps.
# (Pinning via pyproject.toml already; uv just resolves them faster.)
COPY pyproject.toml ./
RUN pip install --no-cache-dir uv==0.5.11 \
 && uv pip install --system --no-cache .

COPY app ./app

EXPOSE 8000

# --reload is useful in class so students see changes without rebuilding.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]