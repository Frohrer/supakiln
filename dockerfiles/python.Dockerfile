FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Non-root execution user (matches --user 1000:1000 from CodeExecutor).
RUN getent passwd 1000 >/dev/null 2>&1 || useradd -m -u 1000 codeuser

# /opt/supakiln is root-owned world-readable so user code running as
# UID 1000 can read worker.py but cannot delete or overwrite it.
RUN mkdir -p /opt/supakiln && chmod 0755 /opt/supakiln

COPY workers/worker.py /opt/supakiln/worker.py
RUN chmod 0644 /opt/supakiln/worker.py

ENV SUPAKILN_RUN_CMD="python3 {file}"
ENV SUPAKILN_FILE_EXT=".py"

USER 1000
WORKDIR /tmp

EXPOSE 9999

CMD ["python3", "/opt/supakiln/worker.py"]
