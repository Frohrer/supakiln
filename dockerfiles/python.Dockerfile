FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Non-root execution user (matches --user 1000:1000 from CodeExecutor).
RUN useradd -m -u 1000 codeuser

# Worker lives at a fixed path inside the image.
RUN mkdir -p /opt/supakiln && chown -R codeuser:codeuser /opt/supakiln

COPY --chown=codeuser:codeuser workers/python/worker.py /opt/supakiln/worker.py

USER codeuser
WORKDIR /tmp

EXPOSE 9999

CMD ["python3", "/opt/supakiln/worker.py"]
