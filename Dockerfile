FROM python:3.13-slim

# Create non-root user first
RUN useradd -m -u 1000 codeuser

# Install Docker and essential packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce docker-ce-cli containerd.io \
    && rm -rf /var/lib/apt/lists/*

# Set up Python environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/home/codeuser/.local/bin:${PATH}"

# Create and set up app directory
WORKDIR /app
RUN mkdir -p /app/code && \
    chown -R codeuser:codeuser /app

# Add codeuser to docker group
RUN usermod -aG docker codeuser

# Switch to non-root user
USER codeuser

# Install pip packages as non-root user
COPY --chown=codeuser:codeuser requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Copy application code
COPY --chown=codeuser:codeuser . .

# Set up secure environment
ENV PYTHONPATH=/app
ENV DOCKER_HOST=unix:///var/run/docker.sock

# Expose port
EXPOSE 8000

# Start the application
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--reload"] 