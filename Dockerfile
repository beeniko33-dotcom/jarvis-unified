FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY apps/ ./apps/
COPY brokers/ ./brokers/
COPY core/ ./core/
COPY packages/ ./packages/
COPY research/ ./research/
COPY scripts/ ./scripts/
COPY main.py ./

RUN useradd --system --uid 10001 --create-home jarvis
USER jarvis

CMD ["python", "main.py", "--serve"]
