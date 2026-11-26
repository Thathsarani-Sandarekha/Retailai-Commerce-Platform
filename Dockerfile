# RetailAI FastAPI + LangGraph. Supports local Docker and image publishing to ECR.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && groupadd --gid 10001 retailai \
    && useradd --uid 10001 --gid retailai --create-home retailai \
    && mkdir -p /app/data /app/media \
    && chown -R retailai:retailai /app/data /app/media
COPY --chown=retailai:retailai app /app/app
USER retailai
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=7s --start-period=45s --retries=3 \
    CMD python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5)' || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
