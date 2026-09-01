FROM python:3.12-slim-bookworm
WORKDIR /srv
COPY pyproject.toml app.py routes.yaml ./
RUN pip install --no-cache-dir .
ENV ROUTES_FILE=/srv/routes.yaml
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
