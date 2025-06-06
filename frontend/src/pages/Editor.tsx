import React, { useState } from 'react';
import { Box, Grid, Paper, Typography, Button, TextField, IconButton, Switch, FormControlLabel } from '@mui/material';
import { Add as AddIcon, Delete as DeleteIcon } from '@mui/icons-material';
import Editor from '@monaco-editor/react';
import api from '../config/api';

const CodeEditor: React.FC = () => {
  const [code, setCode] = useState('# Write your Python code here\nprint("Hello, World!")');
  const [packages, setPackages] = useState<string[]>(['']);
  const [output, setOutput] = useState<string>('');
  const [selectedContainer, setSelectedContainer] = useState<string>('');
  const [isScheduled, setIsScheduled] = useState(false);
  const [scheduleName, setScheduleName] = useState('');
  const [cronExpression, setCronExpression] = useState('');

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
        setOutput('Job scheduled successfully!');
      } else {
        // Execute code immediately
        const response = await api.post('/execute', {
          code,
          packages: packages.filter(p => p.trim() !== ''),
          container_id: selectedContainer || undefined,
        });
        setOutput(response.data.output || response.data.error || '');
      }
    } catch (error) {
      setOutput('Error: ' + (error as Error).message);
    }
  };

  return (
    <Grid container spacing={3}>
      <Grid item xs={12} md={8}>
        <Paper sx={{ p: 2, height: '600px' }}>
          <Editor
            height="100%"
            defaultLanguage="python"
            value={code}
            onChange={(value) => setCode(value || '')}
            theme="vs-dark"
            options={{
              minimap: { enabled: false },
              fontSize: 14,
            }}
          />
        </Paper>
      </Grid>
      <Grid item xs={12} md={4}>
        <Paper sx={{ p: 2, mb: 2 }}>
          <Typography variant="h6" gutterBottom>
            Container & Packages
          </Typography>
          <TextField
            select
            fullWidth
            label="Select Container"
            value={selectedContainer}
            onChange={(e) => setSelectedContainer(e.target.value)}
            SelectProps={{ native: true }}
            sx={{ mb: 2 }}
          >
            <option value="">New Container</option>
          </TextField>
          <Typography variant="subtitle1" gutterBottom>
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
            sx={{ mt: 1 }}
          >
            Add Package
          </Button>

          <Box sx={{ mt: 3 }}>
            <FormControlLabel
              control={
                <Switch
                  checked={isScheduled}
                  onChange={(e) => setIsScheduled(e.target.checked)}
                />
              }
              label="Schedule Job"
            />
            {isScheduled && (
              <Box sx={{ mt: 2 }}>
                <TextField
                  fullWidth
                  label="Job Name"
                  value={scheduleName}
                  onChange={(e) => setScheduleName(e.target.value)}
                  margin="normal"
                  required
                />
                <TextField
                  fullWidth
                  label="Cron Schedule"
                  value={cronExpression}
                  onChange={(e) => setCronExpression(e.target.value)}
                  margin="normal"
                  required
                  placeholder="* * * * *"
                  helperText="Format: minute hour day month weekday"
                />
              </Box>
            )}
          </Box>

          <Button
            variant="contained"
            fullWidth
            onClick={handleRunCode}
            sx={{ mt: 2 }}
          >
            {isScheduled ? 'Schedule Job' : 'Run Code'}
          </Button>
        </Paper>
        <Paper sx={{ p: 2 }}>
          <Typography variant="h6" gutterBottom>
            Output
          </Typography>
          <Box
            component="pre"
            sx={{
              p: 2,
              bgcolor: 'background.paper',
              borderRadius: 1,
              maxHeight: '200px',
              overflow: 'auto',
            }}
          >
            {output || 'No output yet'}
          </Box>
        </Paper>
      </Grid>
    </Grid>
  );
};

export default CodeEditor; 