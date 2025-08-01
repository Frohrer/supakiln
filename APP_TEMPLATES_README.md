# App Templates

A simple, one-click solution for creating and running web applications directly in the code editor.

## Features

- **Template Dropdown**: Select from pre-built app templates
- **Auto Package Installation**: Required packages are automatically included
- **One-Click Execution**: No need to manually configure ports or containers
- **Ready-to-Run Code**: Complete working examples for each framework

## Available Templates

### 🐍 Basic Python
- **Purpose**: General Python code execution
- **Packages**: None (base Python)
- **Use case**: Scripts, data processing, general coding

### 🎈 Streamlit App
- **Purpose**: Interactive data science web apps
- **Packages**: `streamlit`, `pandas`, `numpy`
- **Features**: 
  - Interactive widgets (text input, buttons)
  - Data visualization (line charts)
  - Visual effects (balloons, success messages)
  - Sample data manipulation

### ⚡ FastAPI App
- **Purpose**: High-performance REST APIs
- **Packages**: `fastapi`, `uvicorn`
- **Features**:
  - Multiple endpoints (`/`, `/items/{id}`, `/health`)
  - Path parameters and query parameters
  - JSON responses
  - Auto-generated API documentation

### 🌶️ Flask App
- **Purpose**: Traditional web applications
- **Packages**: `flask`
- **Features**:
  - HTML templating with inline CSS
  - REST API endpoints
  - Static file serving
  - JSON responses

### 📊 Dash App
- **Purpose**: Interactive data visualization dashboards
- **Packages**: `dash`, `plotly`
- **Features**:
  - Interactive components (dropdowns, graphs)
  - Real-time data visualization
  - Callback functions for interactivity
  - Sample data with filtering

## How to Use

1. **Select Template**: Choose from the "App Template" dropdown
2. **Auto-Fill**: Code and packages are automatically populated
3. **Customize**: Modify the code as needed
4. **Run**: Click the "Run" button
5. **Access**: Web apps will start running in the container

## Example Workflow

### Creating a Streamlit App:
```
1. Select "Streamlit App" from dropdown
2. Template code loads automatically
3. Click "Run" 
4. Streamlit app starts running
5. Check console for startup messages
```

### Creating a FastAPI App:
```
1. Select "FastAPI App" from dropdown  
2. Template code loads with endpoints
3. Click "Run"
4. API server starts on port 8000
5. Access via container's exposed port
```

## Template Details

### Streamlit Template Features:
- Title and welcome message
- Interactive text input
- Click button with balloons effect
- Random data visualization
- Pandas/NumPy integration

### FastAPI Template Features:
- Root endpoint with welcome message
- Parameterized endpoint for items
- Health check endpoint
- Uvicorn server configuration
- Host binding for container access

### Flask Template Features:
- HTML template with styling
- Home page with navigation
- API endpoint with JSON data
- Debug mode enabled
- Host binding for external access

### Dash Template Features:
- Interactive data dashboard
- Dropdown for city selection
- Dynamic bar chart updates
- Sample dataset included
- Plotly visualization

## Benefits

- **No Configuration**: Everything works out-of-the-box
- **Educational**: Learn framework patterns from working examples
- **Rapid Prototyping**: Start building immediately
- **Best Practices**: Templates follow framework conventions
- **Container Ready**: All apps are configured for container deployment

## Customization

After selecting a template:
- **Modify Code**: Edit the auto-generated code as needed
- **Add Packages**: Include additional dependencies
- **Extend Features**: Build on the template foundation
- **Save Work**: Use containers to persist your applications

## Next Steps

1. Choose a template that matches your project needs
2. Run the template to see it working
3. Modify the code to build your specific application
4. Add additional packages if needed
5. Scale up your application as required

The template system provides a foundation for rapid development while handling all the boilerplate configuration automatically. 