FROM python:3.12-slim

# Install Docker CLI and required dependencies
RUN apt-get update && apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get install -y docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# Create docker group and add user to it
RUN groupadd -r docker || true && \
    useradd -m -u 1000 -g docker codeuser || true

# Set up Python environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Set proper permissions for Docker socket and app directory
RUN chown -R codeuser:docker /app && \
    chmod 660 /var/run/docker.sock || true && \
    chmod 775 /var/run/docker.sock || true

# Switch to non-root user
USER codeuser

# Expose port 8000
EXPOSE 8000

# Start the application with Docker socket configuration
ENV DOCKER_HOST=unix:///var/run/docker.sock
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--reload"] 