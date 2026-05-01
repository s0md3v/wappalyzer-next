FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir . \
    && python -m playwright install --with-deps chromium

ENTRYPOINT ["wappalyzer"]
