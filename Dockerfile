FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    firefox-esr \
    wget \
    && rm -rf /var/lib/apt/lists/*

RUN wget https://github.com/mozilla/geckodriver/releases/download/v0.35.0/geckodriver-v0.35.0-linux64.tar.gz \
    && tar -xvzf geckodriver-v0.35.0-linux64.tar.gz \
    && chmod +x geckodriver \
    && mv geckodriver /usr/local/bin/ \
    && rm geckodriver-v0.35.0-linux64.tar.gz

RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir \
    beautifulsoup4 \
    selenium \
    requests \
    lxml \
    soupsieve

RUN python -m pip install --no-cache-dir wappalyzer

RUN mkdir -p /app/results

ENTRYPOINT ["wappalyzer"]
