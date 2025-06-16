# Webhook Jobs - Code Execution Triggered by HTTP Requests

## Overview

Webhook Jobs are a new type of code execution that allows you to create custom HTTP endpoints that execute Python code when triggered by web requests. This enables you to:

- Create APIs that execute custom Python code
- Respond to webhooks from external services
- Build serverless-like functions
- Process HTTP requests with custom logic

## How It Works

1. **Create a Webhook Job**: Define Python code and an endpoint path
2. **Make HTTP Requests**: Send GET, POST, PUT, DELETE, or PATCH requests to `/webhook/{your-endpoint}`
3. **Access Request Data**: Your code receives request details in the `request_data` variable
4. **Return Responses**: Set the `response_data` variable to return JSON responses

## Creating Webhook Jobs

### API Endpoint
```
POST /webhook-jobs
```

### Request Body
```json
{
  "name": "My Webhook",
  "endpoint": "/my-webhook",
  "code": "response_data = {'message': 'Hello World'}",
  "container_id": "optional-container-id",
  "packages": ["requests", "pandas"],
  "timeout": 30,
  "description": "Optional description"
}
```

### Fields
- `name`: Human-readable name for the webhook
- `endpoint`: URL path (e.g., `/my-webhook` becomes `/webhook/my-webhook`)
- `code`: Python code to execute when the webhook is triggered
- `container_id`: (Optional) Specific container to use
- `packages`: (Optional) Python packages to install
- `timeout`: (Optional) Execution timeout in seconds (default: 30)
- `description`: (Optional) Description of the webhook

## Request Data Structure

Your webhook code receives a `request_data` dictionary with:

```python
request_data = {
    "method": "GET",           # HTTP method
    "endpoint": "/my-webhook", # The endpoint path
    "headers": {...},          # Request headers
    "query_params": {...},     # URL query parameters
    "body": {...}              # Request body (parsed JSON/form data/text)
}
```

## Response Data Structure

Set the `response_data` variable to return JSON responses:

```python
response_data = {
    "status": "success",
    "message": "Operation completed",
    "data": {...}
}
```

## Examples

### 1. Simple Echo Webhook

```python
# Create webhook
POST /webhook-jobs
{
  "name": "Echo Webhook",
  "endpoint": "/echo",
  "code": "response_data = {'echo': request_data}"
}

# Trigger webhook
GET /webhook/echo?name=John
```

### 2. JSON Data Processor

```python
# Create webhook
POST /webhook-jobs
{
  "name": "Data Processor",
  "endpoint": "/process",
  "code": """
if request_data["body"] and "items" in request_data["body"]:
    items = request_data["body"]["items"]
    processed = [item.upper() for item in items if isinstance(item, str)]
    response_data = {"processed": processed, "count": len(processed)}
else:
    response_data = {"error": "Invalid data"}
  """
}

# Trigger webhook
POST /webhook/process
Content-Type: application/json
{
  "items": ["hello", "world", "test"]
}
```

### 3. External API Integration

```python
# Create webhook with requests package
POST /webhook-jobs
{
  "name": "API Fetcher",
  "endpoint": "/fetch",
  "packages": ["requests"],
  "code": """
import requests

url = request_data["query_params"].get("url")
if url:
    try:
        response = requests.get(url, timeout=10)
        response_data = {
            "status": "success",
            "data": response.json(),
            "status_code": response.status_code
        }
    except Exception as e:
        response_data = {"error": str(e)}
else:
    response_data = {"error": "Missing url parameter"}
  """
}

# Trigger webhook
GET /webhook/fetch?url=https://api.github.com/users/octocat
```

### 4. Simple Database Webhook

```python
# Create webhook
POST /webhook-jobs
{
  "name": "Simple Database",
  "endpoint": "/database",
  "code": """
import json
import os

DATA_FILE = "/tmp/webhook_data.json"

# Load existing data
try:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            storage = json.load(f)
    else:
        storage = {}
except:
    storage = {}

method = request_data["method"]

if method == "GET":
    response_data = {"data": storage, "count": len(storage)}
elif method == "POST" and request_data["body"]:
    storage.update(request_data["body"])
    with open(DATA_FILE, 'w') as f:
        json.dump(storage, f)
    response_data = {"status": "saved", "count": len(storage)}
else:
    response_data = {"error": "Invalid request"}
  """
}

# Store data
POST /webhook/database
{"name": "John", "age": 30}

# Retrieve data
GET /webhook/database
```

## Management Endpoints

### List Webhook Jobs
```
GET /webhook-jobs
```

### Get Specific Webhook Job
```
GET /webhook-jobs/{job_id}
```

### Update Webhook Job
```
PUT /webhook-jobs/{job_id}
```

### Delete Webhook Job
```
DELETE /webhook-jobs/{job_id}
```

## Execution Logs

Webhook executions are logged with request and response data:

```
GET /logs?webhook_job_id={job_id}
```

Log entries include:
- Request data (method, headers, body, etc.)
- Response data
- Execution time
- Success/error status
- Container information

## Error Handling

### Webhook Code Errors
If your webhook code raises an exception:
```json
{
  "error": "Exception message",
  "timestamp": "2024-01-01T12:00:00"
}
```

### Timeout Errors
If execution exceeds the timeout:
```json
{
  "error": "Execution timed out after 30 seconds"
}
```

### Webhook Not Found
If the endpoint doesn't exist:
```json
{
  "detail": "Webhook endpoint '/nonexistent' not found"
}
```

## Best Practices

### 1. Error Handling
Always include error handling in your webhook code:
```python
try:
    # Your main logic here
    result = some_operation()
    response_data = {"status": "success", "result": result}
except Exception as e:
    response_data = {"status": "error", "message": str(e)}
```

### 2. Input Validation
Validate incoming data:
```python
if not request_data["body"] or "required_field" not in request_data["body"]:
    response_data = {"error": "Missing required field"}
    return

data = request_data["body"]
# Process validated data...
```

### 3. Timeout Management
For potentially long operations, consider the timeout limit:
```python
import time

# For operations that might take time
start_time = time.time()
# ... do work ...
if time.time() - start_time > 25:  # Leave buffer before timeout
    response_data = {"status": "partial", "message": "Operation taking too long"}
```

### 4. Response Structure
Use consistent response structures:
```python
# Success response
response_data = {
    "status": "success",
    "data": result,
    "timestamp": datetime.now().isoformat()
}

# Error response
response_data = {
    "status": "error", 
    "message": "Error description",
    "timestamp": datetime.now().isoformat()
}
```

## Security Considerations

1. **Input Sanitization**: Always validate and sanitize incoming data
2. **Resource Limits**: Webhooks run in containers with memory and CPU limits
3. **Network Access**: Webhooks can make external HTTP requests if needed
4. **File System**: Each container has isolated temporary storage
5. **Environment Variables**: Secure environment variables are available

## Use Cases

- **API Endpoints**: Create custom REST APIs
- **Webhook Receivers**: Handle webhooks from GitHub, Stripe, etc.
- **Data Processing**: Process uploaded data or form submissions
- **Integrations**: Connect different services with custom logic
- **Automation**: Trigger automated tasks via HTTP requests
- **Microservices**: Build small, focused services

## Running the Examples

1. Start your application:
   ```bash
   docker-compose up
   ```

2. Run the example script:
   ```bash
   python webhook_examples.py
   ```

3. Test manually:
   ```bash
   # Create a webhook
   curl -X POST http://localhost:8000/webhook-jobs \
     -H "Content-Type: application/json" \
     -d '{"name": "Test", "endpoint": "/test", "code": "response_data = {\"message\": \"Hello World\"}"}'
   
   # Trigger the webhook
   curl http://localhost:8000/webhook/test
   ```

This webhook functionality transforms your code execution engine into a flexible, serverless-like platform for handling HTTP requests with custom Python logic. 