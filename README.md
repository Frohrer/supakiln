# Python Code Execution Engine

A secure and efficient Python code execution engine that runs code in isolated Docker containers. This project provides both a REST API and a web interface for executing Python code with package management capabilities.

## Features

- **Secure Code Execution**: Runs Python code in isolated Docker containers
- **Package Management**: Install and manage Python packages for each container
- **Named Containers**: Create and manage named containers with specific package configurations
- **Web Interface**: Monaco editor-based UI for code editing and execution
- **REST API**: Programmatic access to code execution and container management
- **Resource Limits**: CPU and memory limits for each container
- **Timeout Handling**: Configurable execution timeouts
- **Job Scheduling**: Schedule code execution using cron expressions
- **Execution Logs**: Track and view execution history and results

## Project Structure

```
.
├── api.py                 # FastAPI application and REST endpoints
├── code_executor.py       # Core code execution logic
├── Dockerfile            # Base Docker image configuration
├── docker-compose.yml    # Docker Compose configuration for local development
├── docker-compose.dev.yml # Docker Compose configuration for development with hot-reload
├── requirements.txt      # Python dependencies
├── frontend/             # Frontend React + Vite application
│   ├── src/              # Source files
│   ├── package.json      # Frontend dependencies and scripts
│   ├── tsconfig.json     # TypeScript configuration
│   └── Dockerfile        # Frontend Dockerfile
├── static/               # Web interface files
│   ├── index.html        # Main HTML page
│   ├── app.js            # Frontend JavaScript
│   └── styles.css        # Custom styles
└── README.md             # Project documentation
```

## API Endpoints

### Code Execution
- `POST /execute`: Execute Python code in a container
  - Request body: `{ code: string, packages?: string[], timeout?: number, container_id?: string }`
  - Response: `{ success: boolean, output?: string, error?: string, container_id?: string, container_name?: string }`

### Container Management
- `POST /containers`: Create a new container with specified packages
  - Request body: `{ name: string, packages: string[] }`
  - Response: `{ container_id: string, name: string, packages: string[] }`
- `GET /containers`: List all active containers
  - Response: `Array<{ container_id: string, name: string, packages: string[] }>`
- `DELETE /containers/{container_id}`: Delete a specific container
- `DELETE /containers`: Clean up all containers

### Job Scheduling
- `POST /jobs`: Create a new scheduled job
  - Request body: `{ name: string, cron: string, code: string }`
  - Response: `{ job_id: string }`
- `GET /jobs`: List all scheduled jobs
  - Response: `Array<{ job_id: string, name: string, cron: string, code: string }>`
- `PUT /jobs/{job_id}`: Update a scheduled job
  - Request body: `{ name?: string, cron?: string, code?: string }`
  - Response: `{ success: boolean }`
- `DELETE /jobs/{job_id}`: Delete a scheduled job

### Viewing Logs
- `GET /logs`: Get execution logs
  - Query parameters: `{ job_id?: string }`
  - Response: `Array<{ log_id: string, job_id: string, timestamp: string, output: string, error: string }>`

## Web Interface

The web interface provides:
- Monaco code editor for writing Python code
- Package management section for adding/removing packages
- Container management section for creating and deleting containers
- Container selection dropdown for choosing which container to run code in
- Real-time output display

## Setup and Installation

### Prerequisites
- Docker and Docker Compose installed
- Node.js and npm (for local frontend development)
- Python 3.7+ (for local backend development)

### Running with Docker Compose

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd <repository-directory>
   ```

2. **Build and run the application:**
   ```bash
   docker-compose up --build
   ```
   - Frontend will be available at `http://localhost:3000`
   - Backend API will be available at `http://localhost:8000`

### Local Development

1. **Backend:**
   - Install Python dependencies:
     ```bash
     pip install -r requirements.txt
     ```
   - Run the FastAPI application:
     ```bash
     uvicorn api:app --reload
     ```

2. **Frontend:**
   - Navigate to the frontend directory:
     ```bash
     cd frontend
     ```
   - Install dependencies:
     ```bash
     npm install
     ```
   - Start the development server:
     ```bash
     npm run dev
     ```

## Docker-in-Docker Setup

This project uses Docker-in-Docker to isolate code execution. The backend container mounts the host's Docker socket (`/var/run/docker.sock`) to create and manage containers.

### Windows/WSL2 Considerations

If you're running on Windows, ensure Docker Desktop is configured to use the WSL2 backend:

1. **Enable WSL2 Integration:**
   - Open Docker Desktop
   - Go to Settings → Resources → WSL Integration
   - Enable integration with your default WSL2 distro (e.g., Ubuntu)

2. **Run Docker Compose from WSL2:**
   - Open your WSL2 Ubuntu shell
   - Navigate to your project directory
   - Run:
     ```bash
     docker-compose up --build
     ```

3. **Troubleshooting Docker Socket Permissions:**
   - If you encounter permission issues with `/var/run/docker.sock`, ensure your user is part of the `docker` group:
     ```bash
     sudo usermod -aG docker $USER
     ```
   - Log out and log back in for changes to take effect.

## Security Features

- Code execution in isolated Docker containers
- Resource limits (CPU and memory) per container
- Configurable execution timeouts
- No persistent storage between executions
- Package installation in isolated environments

## Dependencies

- Python 3.7+
- Docker
- FastAPI
- Docker SDK for Python
- Monaco Editor (loaded via CDN)
- Bootstrap 5 (loaded via CDN)

## Cloudflare Access Integration

This application includes support for Cloudflare Access service authentication for secure API requests.

### Configuration

#### Backend CORS Settings
The backend automatically configures CORS headers to support Cloudflare Access, including:
- `CF-Access-Authenticated-User-Email`
- `CF-Access-Client-Id` 
- `CF-Access-Client-Secret`
- `CF-Access-Token`
- `Cf-Access-Jwt-Assertion`

#### Frontend Configuration
To configure Cloudflare service authentication in the frontend:

1. **Copy the example configuration:**
   ```bash
   cp frontend/config.example.env frontend/.env
   ```

2. **Update the environment variables:**
   ```env
   # Get these values from your Cloudflare Access dashboard
   VITE_CF_CLIENT_ID=your_cloudflare_client_id_here
   VITE_CF_CLIENT_SECRET=your_cloudflare_client_secret_here
   VITE_CF_ACCESS_TOKEN=your_cloudflare_access_token_here
   ```

3. **Obtain Cloudflare credentials:**
   - Go to your Cloudflare Zero Trust dashboard
   - Navigate to Access → Service Auth
   - Create or select your service token
   - Copy the Client ID, Client Secret, and Access Token

#### Environment Variables
- `VITE_CF_CLIENT_ID`: Your Cloudflare Access Client ID
- `VITE_CF_CLIENT_SECRET`: Your Cloudflare Access Client Secret  
- `VITE_CF_ACCESS_TOKEN`: Your Cloudflare Access Token
- `ALLOWED_ORIGINS`: Comma-separated list of allowed origins for CORS
- `ENVIRONMENT`: Set to `production` to enforce stricter CORS origins

### Production Deployment
For production deployments:
1. Set `ENVIRONMENT=production` to enforce CORS origin restrictions
2. Configure `ALLOWED_ORIGINS` with your actual frontend domains
3. Ensure all Cloudflare service auth tokens are properly configured

## License

MIT License # supakiln
