FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    firefox-esr \
    wget \
    && rm -rf /var/lib/apt/lists/*

RUN wget https://github.com/mozilla/geckodriver/releases/download/v0.36.0/geckodriver-v0.36.0-linux64.tar.gz \
    && tar -xvzf geckodriver-v0.36.0-linux64.tar.gz \
    && mv geckodriver /usr/local/bin/ \
    && rm geckodriver-v0.36.0-linux64.tar.gz

ADD wappalyzer /wappalyzer
ADD main.py /main.py
ADD requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT ["python", "-m", "wappalyzer"]
