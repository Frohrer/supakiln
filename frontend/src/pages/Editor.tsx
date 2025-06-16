import React, { useState, useEffect } from 'react';
import { Box, Grid, Paper, Typography, Button, TextField, IconButton, Switch, FormControlLabel, MenuItem, Divider } from '@mui/material';
import { Add as AddIcon, Delete as DeleteIcon, PlayArrow as PlayIcon } from '@mui/icons-material';
import Editor from '@monaco-editor/react';
import api from '../config/api';

interface Container {
  id: string;
  name: string;
  created_at: string;
}

const CodeEditor: React.FC = () => {
  const [code, setCode] = useState('# Write your Python code here\nprint("Hello, World!")');
  const [packages, setPackages] = useState<string[]>(['']);
  const [output, setOutput] = useState<string>('');
  const [selectedContainer, setSelectedContainer] = useState<string>('');
  const [isScheduled, setIsScheduled] = useState(false);
  const [scheduleName, setScheduleName] = useState('');
  const [cronExpression, setCronExpression] = useState('');
  const [containers, setContainers] = useState<Container[]>([]);
  const [isExecuting, setIsExecuting] = useState(false);
  const [executionTime, setExecutionTime] = useState<number | null>(null);

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

  return (
    <Box sx={{ height: '100vh', display: 'flex', flexDirection: 'column', p: 2 }}>
      {/* Top toolbar */}
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2, gap: 2 }}>
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
      <Box sx={{ display: 'flex', flexGrow: 1, gap: 2, minHeight: 0 }}>
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
        <Box sx={{ width: '400px', display: 'flex', flexDirection: 'column', gap: 2 }}>
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