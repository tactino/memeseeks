# CPU image: index a mounted meme folder, then serve the web app on port 8765.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models \
    MEMESEEKS_HOME=/library

# OpenCV (used by RapidOCR) needs these shared libraries.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN pip install "torch==2.11.*" "torchvision==0.26.*" --index-url https://download.pytorch.org/whl/cpu
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install ".[ml,serve]"

RUN useradd --create-home --uid 1000 memeseeks \
 && mkdir -p /library /models /memes \
 && chown memeseeks:memeseeks /library /models
USER memeseeks

EXPOSE 8765
VOLUME ["/library", "/models"]
ENTRYPOINT ["memeseeks"]
CMD ["run", "/memes", "--host", "0.0.0.0"]
