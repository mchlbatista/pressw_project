FROM python:3.12-slim-bookworm
WORKDIR /srv
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
EXPOSE 8080
# docker-compose mounts ./encore over /srv and runs with --reload: edit, save, retest.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--reload"]
