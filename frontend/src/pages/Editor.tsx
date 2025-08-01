import React, { useState, useEffect } from 'react';
import { Box, Grid, Paper, Typography, Button, TextField, IconButton, Switch, FormControlLabel, MenuItem, Divider, Alert, Link, Dialog, DialogTitle, DialogContent, DialogActions } from '@mui/material';
import { Add as AddIcon, Delete as DeleteIcon, PlayArrow as PlayIcon, Launch as LaunchIcon, Save as SaveIcon, Folder as FolderIcon } from '@mui/icons-material';
import Editor from '@monaco-editor/react';
import api, { extractErrorMessage } from '../config/api';

interface CodeSession {
  id: string;
  name: string;
  code: string;
  packages: string[];
  created_at: string;
  updated_at: string;
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
    code: `# Write your Python code here
import os

# Example 1: Get environment variable with default value
database_url = os.getenv('DATABASE_URL', 'sqlite:///default.db')
print(f"Database URL: {database_url}")

# Example 2: Get required environment variable (raises error if not found)
try:
    api_key = os.environ['API_KEY']
    print(f"API Key found: {api_key[:8]}...")
except KeyError:
    print("API_KEY environment variable not set")

# Example 3: Get environment variable with type conversion
debug_mode = os.getenv('DEBUG', 'false').lower() == 'true'
print(f"Debug mode: {debug_mode}")

# Example 4: List all environment variables
print("\\nAll environment variables:")
for key, value in os.environ.items():
    print(f"{key}: {value}")

print("Hello, World!")`
  },
  gradio: {
    name: 'Gradio App',
    packages: ['gradio'],
    code: `import gradio as gr

def greet(name):
    return f"Hello, {name}!"

with gr.Blocks() as demo:
    inp = gr.Textbox(label="Your name")
    out = gr.Textbox(label="Greeting")
    btn = gr.Button("Greet")
    btn.click(fn=greet, inputs=inp, outputs=out)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
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
    packages: ['dash', 'plotly', 'pandas', 'numpy'],
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
    app.run(host='0.0.0.0', port=8050, debug=True)
`
  }
};

const CodeEditor: React.FC = () => {
  const [selectedTemplate, setSelectedTemplate] = useState('basic');
  const [code, setCode] = useState(appTemplates.basic.code);
  const [packages, setPackages] = useState<string[]>(['']);
  const [output, setOutput] = useState<string>('');
  const [isScheduled, setIsScheduled] = useState(false);
  const [scheduleName, setScheduleName] = useState('');
  const [cronExpression, setCronExpression] = useState('');
  const [isExecuting, setIsExecuting] = useState(false);
  const [executionTime, setExecutionTime] = useState<number | null>(null);
  const [webService, setWebService] = useState<WebService | null>(null);
  const [timeout, setTimeout] = useState(30); // Default timeout in seconds
  
  // Code session management
  const [codeSessions, setCodeSessions] = useState<CodeSession[]>([]);
  const [selectedSession, setSelectedSession] = useState<string>('');
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [sessionName, setSessionName] = useState('');
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);

  useEffect(() => {
    loadCodeSessions();
    // Load auto-saved editor state on mount
    loadAutoSavedState();
  }, []);

  // Auto-save current editor state to localStorage
  useEffect(() => {
    // Only auto-save if not currently loading a template or session
    if (code && code !== appTemplates.basic.code) {
      saveAutoSavedState();
    }
  }, [code, packages]);

  // Load saved code sessions from localStorage
  const loadCodeSessions = () => {
    try {
      const sessions = localStorage.getItem('codeSessions');
      if (sessions) {
        setCodeSessions(JSON.parse(sessions));
      }
    } catch (error) {
      console.error('Error loading code sessions:', error);
    }
  };

  // Load auto-saved editor state
  const loadAutoSavedState = () => {
    try {
      const autoSaved = localStorage.getItem('currentEditorState');
      if (autoSaved) {
        const { code: savedCode, packages: savedPackages, timestamp } = JSON.parse(autoSaved);
        // Only load if saved within last 24 hours and not empty
        const dayAgo = Date.now() - (24 * 60 * 60 * 1000);
        if (timestamp > dayAgo && savedCode && savedCode.trim() !== '') {
          setCode(savedCode);
          setPackages(savedPackages.length > 0 ? savedPackages : ['']);
        }
      }
    } catch (error) {
      console.error('Error loading auto-saved state:', error);
    }
  };

  // Save current editor state automatically
  const saveAutoSavedState = () => {
    try {
      const autoSaveData = {
        code,
        packages: packages.filter((p: string) => p.trim() !== ''),
        timestamp: Date.now()
      };
      localStorage.setItem('currentEditorState', JSON.stringify(autoSaveData));
    } catch (error) {
      console.error('Error auto-saving editor state:', error);
    }
  };

  // Clear auto-saved state
  const clearAutoSavedState = () => {
    try {
      localStorage.removeItem('currentEditorState');
    } catch (error) {
      console.error('Error clearing auto-saved state:', error);
    }
  };

  // Save code sessions to localStorage
  const saveCodeSessions = (sessions: CodeSession[]) => {
    try {
      localStorage.setItem('codeSessions', JSON.stringify(sessions));
      setCodeSessions(sessions);
    } catch (error) {
      console.error('Error saving code sessions:', error);
    }
  };

  const handleTemplateChange = (templateKey: string) => {
    const template = appTemplates[templateKey as keyof typeof appTemplates];
    setSelectedTemplate(templateKey);
    setCode(template.code);
    setPackages(template.packages.length > 0 ? template.packages : ['']);
    setWebService(null);
    setCurrentSessionId(null);
    setSelectedSession('');
    // Clear auto-saved state when loading a template
    clearAutoSavedState();
  };

  const handleSessionLoad = (sessionId: string) => {
    const session = codeSessions.find((s: CodeSession) => s.id === sessionId);
    if (session) {
      setCode(session.code);
      setPackages(session.packages.length > 0 ? session.packages : ['']);
      setSelectedSession(sessionId);
      setCurrentSessionId(sessionId);
      setSelectedTemplate(''); // Clear template selection
      setWebService(null);
      // Clear auto-saved state when loading a session
      clearAutoSavedState();
    }
  };

  const handleSaveSession = () => {
    if (!sessionName.trim()) return;

    const now = new Date().toISOString();
    const sessionToSave: CodeSession = {
      id: currentSessionId || Date.now().toString(),
      name: sessionName.trim(),
      code,
      packages: packages.filter((p: string) => p.trim() !== ''),
      created_at: currentSessionId ? codeSessions.find((s: CodeSession) => s.id === currentSessionId)?.created_at || now : now,
      updated_at: now
    };

    let updatedSessions: CodeSession[];
    if (currentSessionId) {
      // Update existing session
      updatedSessions = codeSessions.map((s: CodeSession) => s.id === currentSessionId ? sessionToSave : s);
    } else {
      // Create new session
      updatedSessions = [...codeSessions, sessionToSave];
    }

    saveCodeSessions(updatedSessions);
    setCurrentSessionId(sessionToSave.id);
    setSelectedSession(sessionToSave.id);
    setShowSaveDialog(false);
    setSessionName('');
  };

  const handleDeleteSession = (sessionId: string) => {
    const updatedSessions = codeSessions.filter((s: CodeSession) => s.id !== sessionId);
    saveCodeSessions(updatedSessions);
    if (selectedSession === sessionId) {
      setSelectedSession('');
      setCurrentSessionId(null);
    }
  };

  const openSaveDialog = () => {
    const currentSession = currentSessionId ? codeSessions.find((s: CodeSession) => s.id === currentSessionId) : null;
    setSessionName(currentSession?.name || '');
    setShowSaveDialog(true);
  };

  const handleAddPackage = () => {
    setPackages([...packages, '']);
  };

  const handleRemovePackage = (index: number) => {
    setPackages(packages.filter((_: string, i: number) => i !== index));
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
          timeout: timeout,
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
          timeout: timeout,
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
      setOutput('Error: ' + extractErrorMessage(error));
    } finally {
      setIsExecuting(false);
    }
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
        
        <Button
          variant="outlined"
          startIcon={<SaveIcon />}
          onClick={openSaveDialog}
          sx={{ px: 2 }}
        >
          {currentSessionId ? 'Update' : 'Save'}
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
          label="Saved Sessions"
          value={selectedSession}
          onChange={(e) => handleSessionLoad(e.target.value)}
          sx={{ minWidth: 200 }}
        >
          <MenuItem value="">
            <em>None</em>
          </MenuItem>
          {codeSessions.map((session) => (
            <MenuItem key={session.id} value={session.id}>
              <FolderIcon sx={{ mr: 1, fontSize: 16 }} />
              {session.name}
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
      <Box sx={{ 
        display: 'flex', 
        flexDirection: { xs: 'column', md: 'row' },
        flexGrow: 1, 
        gap: 1, 
        minHeight: 0 
      }}>
        {/* Left side - Code editor */}
        <Box sx={{ 
          flex: 1, 
          display: 'flex', 
          flexDirection: 'column',
          minWidth: 0, // Allow flex item to shrink below content size
          minHeight: { xs: '400px', md: 'auto' }, // Minimum height on mobile
        }}>
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
                automaticLayout: true, // Enable automatic layout on resize
              }}
            />
          </Paper>
        </Box>

        {/* Right side - Settings and Output */}
        <Box sx={{ 
          width: { xs: '100%', md: '350px', lg: '400px', xl: '450px' },
          maxWidth: { xs: 'none', md: '40%' },
          minWidth: { xs: 'auto', md: '300px' },
          display: 'flex', 
          flexDirection: 'column', 
          gap: 2, 
          pr: { xs: 0, md: 2 }
        }}>
          {/* Settings panel */}
          <Paper sx={{ p: 2 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <Typography variant="h6">
                Packages
              </Typography>
              {currentSessionId && (
                <Typography variant="caption" color="primary">
                  Session: {codeSessions.find(s => s.id === currentSessionId)?.name}
                </Typography>
              )}
            </Box>
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

            {/* Timeout Settings */}
            <Box sx={{ mt: 2 }}>
              <Divider sx={{ my: 2 }} />
              <Typography variant="h6" gutterBottom>
                Execution Timeout
              </Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <TextField
                  type="number"
                  size="small"
                  label="Timeout (seconds)"
                  value={timeout}
                  onChange={(e) => setTimeout(Math.max(1, parseInt(e.target.value) || 1))}
                  inputProps={{ min: 1, max: 300 }}
                  sx={{ width: 150 }}
                />
                <Typography variant="caption" color="text.secondary">
                  {timeout < 60 ? `${timeout}s` : `${Math.floor(timeout / 60)}m ${timeout % 60}s`}
                </Typography>
              </Box>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
                Maximum execution time (1-300 seconds)
              </Typography>
            </Box>

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

      {/* Save Session Dialog */}
      <Dialog open={showSaveDialog} onClose={() => setShowSaveDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {currentSessionId ? 'Update Code Session' : 'Save Code Session'}
        </DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Session Name"
            fullWidth
            variant="outlined"
            value={sessionName}
            onChange={(e) => setSessionName(e.target.value)}
            placeholder="Enter a name for this code session"
          />
          <Box sx={{ mt: 2 }}>
            <Typography variant="body2" color="text.secondary">
              This will save your current code and package dependencies for easy reuse.
            </Typography>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowSaveDialog(false)}>Cancel</Button>
          <Button 
            onClick={handleSaveSession} 
            variant="contained"
            disabled={!sessionName.trim()}
          >
            {currentSessionId ? 'Update' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default CodeEditor; 