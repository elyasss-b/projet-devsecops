# Etape 1 : installation des dependances
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Etape 2 : image d'execution minimale
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
# pip n'est pas utile a l'execution : on le retire pour reduire la surface d'attaque
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip uninstall -y pip \
    && groupadd -g 10001 app \
    && useradd -u 10001 -g app -M -s /usr/sbin/nologin app
WORKDIR /app
COPY --from=builder /install /usr/local
# Fichiers appartenant a root : l'utilisateur app peut les lire mais pas les modifier
COPY app.py .
COPY templates/ templates/
USER 10001:10001
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=3s CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health')"]
CMD ["gunicorn", "-b", "0.0.0.0:5000", "-w", "2", "--worker-tmp-dir", "/tmp", "app:app"]
