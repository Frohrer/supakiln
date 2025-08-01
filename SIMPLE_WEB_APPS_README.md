# Simple Web App Hosting

A streamlined, one-click solution for running web applications with automatic port exposure and proxy access.

## How It Works

1. **Template Selection**: Choose a web app template (Streamlit, FastAPI, Flask, Dash)
2. **Auto Detection**: System detects web service in your code
3. **Port Allocation**: Automatically allocates ports in range 9000-9999
4. **Container Creation**: Creates container with port exposure
5. **Service Start**: Starts your web service in the background
6. **Proxy Access**: Provides instant URL via proxy system

## Supported Web Frameworks

### 🎈 Streamlit
- **Detection**: `streamlit` package or `st.` in code
- **Default Port**: 8501
- **Start Command**: `streamlit run /tmp/app.py --server.address=0.0.0.0 --server.port=8501`

### ⚡ FastAPI  
- **Detection**: `fastapi` and `uvicorn` packages
- **Default Port**: 8000
- **Start Command**: `python /tmp/app.py`

### 🌶️ Flask
- **Detection**: `flask` package
- **Default Port**: 5000  
- **Start Command**: `python /tmp/app.py`

### 📊 Dash
- **Detection**: `dash` and `plotly` packages
- **Default Port**: 8050
- **Start Command**: `python /tmp/app.py`

## Usage

### Quick Start
1. Select "Streamlit App" template
2. Click "Run"
3. Get instant access URL: `http://localhost:8000/proxy/abc12345`

### Example Response
```json
{
  "success": true,
  "output": "🚀 Streamlit service started!\n\n📍 Access your app at: http://localhost:8000/proxy/abc12345\n\nService is running on port 9001",
  "web_service": {
    "type": "streamlit",
    "external_port": 9001,
    "proxy_url": "http://localhost:8000/proxy/abc12345"
  }
}
```

## Architecture

### Container Management
- **Regular Code**: Standard container, executes and exits
- **Web Services**: Persistent container with port mapping
- **Port Range**: 9000-9999 for external access
- **No Timeout**: Web service containers stay alive

### Proxy System
- **URL Format**: `/proxy/{container_short_id}`
- **Route Matching**: First 8 chars of container ID
- **Method Support**: GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS
- **Streaming**: Supports Server-Sent Events

### Detection Logic
```python
def _detect_web_service(code, packages):
    if 'streamlit' in packages:
        return {'type': 'streamlit', 'internal_port': 8501}
    elif 'fastapi' in packages and 'uvicorn' in packages:
        return {'type': 'fastapi', 'internal_port': 8000}
    # ... etc
```

## Frontend Integration

### Web Service Panel
When a web service starts, the UI displays:
- ✅ Success alert
- 🔗 Clickable proxy URL
- 🚀 Launch button
- 📊 Port and type info

### Template System
- **Auto-fill**: Code and packages populate automatically
- **One-click**: Run button handles everything
- **Visual feedback**: Clear service status

## Examples

### Streamlit App
```python
import streamlit as st
st.title("My App")
st.write("Hello World!")
```
**Result**: Instant Streamlit app at `/proxy/abc12345`

### FastAPI App  
```python
from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Hello World"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```
**Result**: REST API accessible at `/proxy/def67890`

## Benefits

- **Zero Configuration**: No manual port setup
- **Instant Access**: Immediate proxy URLs
- **Persistent Services**: Web apps stay running
- **Integrated UI**: Seamless editor experience
- **Template Driven**: Best practices built-in

## Technical Details

### Port Allocation
- Random port selection from 9000-9999
- Socket binding test for availability
- Automatic retry on conflicts

### Container Lifecycle
- Web services: Persistent containers
- Regular code: Temporary execution
- Auto-cleanup on system shutdown

### Proxy Routing
- Container ID based routing
- Full HTTP method support
- Header preservation
- Error handling with helpful messages

The system provides a complete, integrated experience for rapid web app development and deployment within the code execution environment. 