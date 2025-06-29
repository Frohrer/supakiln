import React, { useState, useEffect } from 'react';
import { Box, Grid, Paper, Typography, Button, TextField, IconButton, Switch, FormControlLabel, MenuItem, Divider, Alert, Link } from '@mui/material';
import { Add as AddIcon, Delete as DeleteIcon, PlayArrow as PlayIcon, Launch as LaunchIcon } from '@mui/icons-material';
import Editor from '@monaco-editor/react';
import api from '../config/api';

interface Container {
  id: string;
  name: string;
  created_at: string;
}

interface WebService {
  type: string;
  external_port: number;
  proxy_url: string;
}

const appTemplates = {
  basic: {
    name: 'Basic Python',
    packages: [],
    code: '# Write your Python code here\nprint("Hello, World!")'
  },
  streamlit: {
    name: 'Streamlit App',
    packages: ['streamlit'],
    code: `import streamlit as st
import pandas as pd
import numpy as np

def main():
    st.title("My Streamlit App")
    st.write("Hello from Streamlit!")

    # Add some interactive elements
    name = st.text_input("Enter your name:")
    if name:
        st.write(f"Hello, {name}!")

    if st.button("Click me!"):
        st.success("Button clicked!")

    # Add some data visualization
    chart_data = pd.DataFrame(
        np.random.randn(20, 3),
        columns=['a', 'b', 'c']
    )

    st.line_chart(chart_data)

if __name__ == "__main__":
    main()
`
  },
  fastapi: {
    name: 'FastAPI App',
    packages: ['fastapi', 'uvicorn'],
    code: `from fastapi import FastAPI
import uvicorn

app = FastAPI(title="My API", description="A simple FastAPI application")

@app.get("/")
def read_root():
    return {"message": "Hello World", "status": "running"}

@app.get("/items/{item_id}")
def read_item(item_id: int, q: str = None):
    return {"item_id": item_id, "q": q}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    # This will start the server
    uvicorn.run(app, host="0.0.0.0", port=8000)
`
  },
  flask: {
    name: 'Flask App',
    packages: ['flask'],
    code: `from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

# Simple HTML template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>My Flask App</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .container { max-width: 600px; margin: 0 auto; }
        h1 { color: #333; }
        .btn { background: #007bff; color: white; padding: 10px 20px; 
               text-decoration: none; border-radius: 5px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Welcome to My Flask App!</h1>
        <p>This is a simple Flask application.</p>
        <a href="/api/data" class="btn">View API Data</a>
    </div>
</body>
</html>
'''

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/data')
def get_data():
    return jsonify({
        "message": "Hello from Flask!",
        "data": [1, 2, 3, 4, 5],
        "status": "success"
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
`
  },
  dash: {
    name: 'Dash App',
    packages: ['dash', 'plotly'],
    code: `import dash
from dash import dcc, html, Input, Output
import plotly.express as px
import pandas as pd

# Create sample data
df = pd.DataFrame({
    'Fruit': ['Apples', 'Oranges', 'Bananas', 'Grapes'],
    'Amount': [4, 1, 2, 3],
    'City': ['SF', 'SF', 'NYC', 'NYC']
})

# Initialize the Dash app
app = dash.Dash(__name__)

# Define the layout
app.layout = html.Div([
    html.H1("My Dash Application", style={'textAlign': 'center'}),
    
    html.Div([
        html.Label("Select City:"),
        dcc.Dropdown(
            id='city-dropdown',
            options=[{'label': city, 'value': city} for city in df['City'].unique()],
            value='SF'
        )
    ], style={'width': '48%', 'display': 'inline-block'}),
    
    dcc.Graph(id='fruit-graph'),
    
    html.Div([
        html.H3("Sample Text"),
        html.P("This is a sample Dash application with interactive components!")
    ])
])

# Callback for updating the graph
@app.callback(
    Output('fruit-graph', 'figure'),
    Input('city-dropdown', 'value')
)
def update_graph(selected_city):
    filtered_df = df[df['City'] == selected_city]
    fig = px.bar(filtered_df, x='Fruit', y='Amount', 
                 title=f'Fruit Amount in {selected_city}')
    return fig

if __name__ == '__main__':
    app.run_server(host='0.0.0.0', port=8050, debug=True)
`
  }
};

const CodeEditor: React.FC = () => {
  const [selectedTemplate, setSelectedTemplate] = useState('basic');
  const [code, setCode] = useState(appTemplates.basic.code);
  const [packages, setPackages] = useState<string[]>(['']);
  const [output, setOutput] = useState<string>('');
  const [selectedContainer, setSelectedContainer] = useState<string>('');
  const [isScheduled, setIsScheduled] = useState(false);
  const [scheduleName, setScheduleName] = useState('');
  const [cronExpression, setCronExpression] = useState('');
  const [containers, setContainers] = useState<Container[]>([]);
  const [isExecuting, setIsExecuting] = useState(false);
  const [executionTime, setExecutionTime] = useState<number | null>(null);
  const [webService, setWebService] = useState<WebService | null>(null);

  useEffect(() => {
    fetchContainers();
  }, []);

  const fetchContainers = async () => {
    try {
      const response = await api.get('/containers');
      setContainers(response.data);
    } catch (error) {
      console.error('Error fetching containers:', error);
    }
  };

  const handleTemplateChange = (templateKey: string) => {
    const template = appTemplates[templateKey as keyof typeof appTemplates];
    setSelectedTemplate(templateKey);
    setCode(template.code);
    setPackages(template.packages.length > 0 ? template.packages : ['']);
    setWebService(null); // Clear any previous web service info
  };

  const handleAddPackage = () => {
    setPackages([...packages, '']);
  };

  const handleRemovePackage = (index: number) => {
    setPackages(packages.filter((_, i) => i !== index));
  };

  const handlePackageChange = (index: number, value: string) => {
    const newPackages = [...packages];
    newPackages[index] = value;
    setPackages(newPackages);
  };

  const handleRunCode = async () => {
    // Clear the output and start execution timer
    setOutput('');
    setIsExecuting(true);
    setExecutionTime(null);
    setWebService(null);
    const startTime = Date.now();
    
    try {
      if (isScheduled) {
        // Create a scheduled job
        await api.post('/jobs', {
          name: scheduleName,
          code,
          cron_expression: cronExpression,
          packages: packages.filter(p => p.trim() !== ''),
          container_id: selectedContainer || undefined,
        });
        const endTime = Date.now();
        const execTime = endTime - startTime;
        setExecutionTime(execTime);
        setOutput('Job scheduled successfully!');
      } else {
        // Execute code immediately
        const response = await api.post('/execute', {
          code,
          packages: packages.filter(p => p.trim() !== ''),
          container_id: selectedContainer || undefined,
        });
        const endTime = Date.now();
        const execTime = endTime - startTime;
        setExecutionTime(execTime);
        
        setOutput(response.data.output || response.data.error || '');
        
        // Handle web service response
        if (response.data.web_service) {
          setWebService(response.data.web_service);
        }
      }
    } catch (error) {
      const endTime = Date.now();
      const execTime = endTime - startTime;
      setExecutionTime(execTime);
      setOutput('Error: ' + (error as Error).message);
    } finally {
      setIsExecuting(false);
    }
  };

  const getServiceTypeColor = (serviceType: string) => {
    const colors: { [key: string]: 'primary' | 'secondary' | 'success' | 'warning' | 'error' | 'info' } = {
      streamlit: 'error',
      fastapi: 'success',
      flask: 'info',
      dash: 'warning',
    };
    return colors[serviceType] || 'primary';
  };

  return (
    <Box sx={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Top toolbar */}
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2, gap: 2, px: 2, py: 1 }}>
        <Button
          variant="contained"
          startIcon={<PlayIcon />}
          onClick={handleRunCode}
          disabled={isExecuting}
          sx={{ 
            bgcolor: '#00d084', 
            '&:hover': { bgcolor: '#00b574' },
            px: 3,
            py: 1
          }}
        >
          {isExecuting ? 'Running...' : (isScheduled ? 'Schedule Job' : 'Run')}
        </Button>
        
        <TextField
          select
          size="small"
          label="App Template"
          value={selectedTemplate}
          onChange={(e) => handleTemplateChange(e.target.value)}
          sx={{ minWidth: 200 }}
        >
          {Object.entries(appTemplates).map(([key, template]) => (
            <MenuItem key={key} value={key}>
              {template.name}
            </MenuItem>
          ))}
        </TextField>
        
        <TextField
          select
          size="small"
          label="Container"
          value={selectedContainer}
          onChange={(e) => setSelectedContainer(e.target.value)}
          sx={{ minWidth: 200 }}
        >
          <MenuItem value="">New Container</MenuItem>
          {containers.map((container) => (
            <MenuItem key={container.id} value={container.id}>
              {container.name}
            </MenuItem>
          ))}
        </TextField>

        <FormControlLabel
          control={
            <Switch
              checked={isScheduled}
              onChange={(e) => setIsScheduled(e.target.checked)}
            />
          }
          label="Schedule"
        />
      </Box>

      {/* Main content area */}
      <Box sx={{ display: 'flex', flexGrow: 1, gap: 1, minHeight: 0 }}>
        {/* Left side - Code editor */}
        <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
          <Paper sx={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
            <Editor
              height="100%"
              defaultLanguage="python"
              value={code}
              onChange={(value) => setCode(value || '')}
              theme="vs-dark"
              options={{
                minimap: { enabled: false },
                fontSize: 14,
                wordWrap: 'on',
                scrollBeyondLastLine: false,
              }}
            />
          </Paper>
        </Box>

        {/* Right side - Settings and Output */}
        <Box sx={{ width: '400px', display: 'flex', flexDirection: 'column', gap: 2, pr: 2 }}>
          {/* Settings panel */}
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Packages
            </Typography>
            {packages.map((package_, index) => (
              <Box key={index} sx={{ display: 'flex', mb: 1 }}>
                <TextField
                  fullWidth
                  size="small"
                  value={package_}
                  onChange={(e) => handlePackageChange(index, e.target.value)}
                  placeholder="Package name"
                />
                <IconButton
                  size="small"
                  onClick={() => handleRemovePackage(index)}
                  sx={{ ml: 1 }}
                >
                  <DeleteIcon />
                </IconButton>
              </Box>
            ))}
            <Button
              startIcon={<AddIcon />}
              onClick={handleAddPackage}
              size="small"
              sx={{ mt: 1 }}
            >
              Add Package
            </Button>

            {isScheduled && (
              <Box sx={{ mt: 2 }}>
                <Divider sx={{ my: 2 }} />
                <Typography variant="h6" gutterBottom>
                  Schedule Settings
                </Typography>
                <TextField
                  fullWidth
                  size="small"
                  label="Job Name"
                  value={scheduleName}
                  onChange={(e) => setScheduleName(e.target.value)}
                  sx={{ mb: 2 }}
                  required
                />
                <TextField
                  fullWidth
                  size="small"
                  label="Cron Schedule"
                  value={cronExpression}
                  onChange={(e) => setCronExpression(e.target.value)}
                  required
                  placeholder="* * * * *"
                  helperText="Format: minute hour day month weekday"
                />
              </Box>
            )}
          </Paper>

          {/* Web Service Panel */}
          {webService && (
            <Paper sx={{ p: 2 }}>
              <Typography variant="h6" gutterBottom>
                🚀 Web Service Running
              </Typography>
              <Alert severity="success" sx={{ mb: 2 }}>
                Your {webService.type} app is now accessible!
              </Alert>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                <Typography variant="body2" fontWeight="bold">
                  Service URL:
                </Typography>
                <Link
                  href={webService.proxy_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  color="primary"
                  sx={{ textDecoration: 'none' }}
                >
                  {webService.proxy_url}
                </Link>
                <IconButton
                  size="small"
                  onClick={() => window.open(webService.proxy_url, '_blank')}
                >
                  <LaunchIcon fontSize="small" />
                </IconButton>
              </Box>
              <Typography variant="caption" color="text.secondary">
                Port: {webService.external_port} | Type: {webService.type}
              </Typography>
            </Paper>
          )}

          {/* Output panel */}
          <Paper sx={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: '300px' }}>
            <Box sx={{ 
              p: 2, 
              borderBottom: 1, 
              borderColor: 'divider',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between'
            }}>
              <Typography variant="h6">
                Console
              </Typography>
              {executionTime !== null && (
                <Typography variant="caption" color="text.secondary">
                  Executed in {executionTime}ms
                </Typography>
              )}
            </Box>
            <Box
              component="pre"
              sx={{
                flex: 1,
                p: 2,
                bgcolor: '#0d1117',
                color: '#e6edf3',
                fontFamily: 'Monaco, Menlo, "Ubuntu Mono", monospace',
                fontSize: '13px',
                overflow: 'auto',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                margin: 0,
              }}
            >
              {isExecuting ? 'Running code...' : (output || 'Ready to run your code')}
            </Box>
          </Paper>
        </Box>
      </Box>
    </Box>
  );
};

export default CodeEditor; 