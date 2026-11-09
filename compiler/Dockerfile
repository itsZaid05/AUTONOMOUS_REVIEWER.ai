FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 texlive-latex-base texlive-latex-recommended texlive-publishers latexmk chktex && rm -rf /var/lib/apt/lists/*
COPY compiler/worker.py /service/worker.py
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["python3","/service/worker.py"]
