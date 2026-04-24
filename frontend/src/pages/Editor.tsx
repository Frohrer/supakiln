import React, { useState, useEffect } from 'react';
import { Box, Grid, Paper, Typography, Button, TextField, IconButton, Switch, FormControlLabel, MenuItem, Divider, Alert, Link, Dialog, DialogTitle, DialogContent, DialogActions } from '@mui/material';
import { Add as AddIcon, Delete as DeleteIcon, PlayArrow as PlayIcon, Launch as LaunchIcon, Save as SaveIcon, Folder as FolderIcon } from '@mui/icons-material';
import Editor from '@monaco-editor/react';
import api, { extractErrorMessage } from '../config/api';
import { Runtime, fetchRuntimes, monacoLanguageFor } from '../config/languages';
import {
  APP_TEMPLATES,
  templatesForLanguage,
  defaultTemplateForLanguage,
  templateByKey,
} from '../config/templates';

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

// Templates now live in config/templates.ts (one flat list, per-language).
// The "Basic Python" template is the conventional blank-slate starting
// point; kept around as a named constant so the auto-save guard below
// doesn't flag it as user content.
const BASIC_PYTHON = APP_TEMPLATES.find((t) => t.key === 'python-basic')!;

const CodeEditor: React.FC = () => {
  const [selectedTemplate, setSelectedTemplate] = useState('python-basic');
  const [code, setCode] = useState(BASIC_PYTHON.code);
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

  // Language / runtime selection
  const [runtimes, setRuntimes] = useState<Runtime[]>([]);
  const [language, setLanguage] = useState<string>('python');

  useEffect(() => {
    loadCodeSessions();
    // Load auto-saved editor state on mount
    loadAutoSavedState();
    // Load available runtimes from the backend
    fetchRuntimes()
      .then((rts) => setRuntimes(rts))
      .catch((err) => console.error('Error fetching runtimes:', err));
  }, []);

  const currentRuntime = runtimes.find((r) => r.name === language);
  const supportsPackages = currentRuntime ? currentRuntime.supports_packages : true;

  // Auto-save current editor state to localStorage
  useEffect(() => {
    // Only auto-save if not currently loading a template or session
    if (code && code !== BASIC_PYTHON.code) {
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
    const template = templateByKey(templateKey);
    if (!template) return;
    setSelectedTemplate(templateKey);
    setCode(template.code);
    setPackages(template.packages.length > 0 ? [...template.packages] : ['']);
    // A template carries its own language — switching template also
    // switches the runtime so Monaco's syntax highlighting and the
    // /execute request body both stay consistent.
    if (template.language !== language) {
      setLanguage(template.language);
    }
    setWebService(null);
    setCurrentSessionId(null);
    setSelectedSession('');
    clearAutoSavedState();
  };

  // When the language changes (either directly or via a template), make
  // sure the template dropdown points at a template that belongs to the
  // new language. Otherwise the dropdown shows an out-of-list value and
  // the displayed label mismatches the selected runtime.
  useEffect(() => {
    const current = templateByKey(selectedTemplate);
    if (current && current.language === language) return;
    const fallback = defaultTemplateForLanguage(language);
    setSelectedTemplate(fallback ? fallback.key : '');
    // Intentionally don't reset `code` here — the user may be typing in
    // a language we just switched to. Templates are a scaffolding aid,
    // not a source of truth for the current buffer.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [language]);

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
          packages: supportsPackages ? packages.filter(p => p.trim() !== '') : [],
          timeout: timeout,
          language,
        });
        const endTime = Date.now();
        const execTime = endTime - startTime;
        setExecutionTime(execTime);
        setOutput('Job scheduled successfully!');
      } else {
        // Execute code immediately
        const response = await api.post('/execute', {
          code,
          packages: supportsPackages ? packages.filter(p => p.trim() !== '') : [],
          timeout: timeout,
          language,
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
          label="Language"
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          sx={{ minWidth: 140 }}
        >
          {runtimes.length === 0 ? (
            <MenuItem value="python">Python</MenuItem>
          ) : (
            runtimes.map((rt) => (
              <MenuItem key={rt.name} value={rt.name}>
                {rt.display_name}
              </MenuItem>
            ))
          )}
        </TextField>

        <TextField
          select
          size="small"
          label="Template"
          value={selectedTemplate}
          onChange={(e) => handleTemplateChange(e.target.value)}
          sx={{ minWidth: 200 }}
        >
          {templatesForLanguage(language).length === 0 ? (
            <MenuItem value="" disabled>
              <em>No templates for this runtime</em>
            </MenuItem>
          ) : (
            templatesForLanguage(language).map((template) => (
              <MenuItem key={template.key} value={template.key}>
                {template.name}
              </MenuItem>
            ))
          )}
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
              language={monacoLanguageFor(language)}
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
                {supportsPackages ? 'Packages' : 'Settings'}
              </Typography>
              {currentSessionId && (
                <Typography variant="caption" color="primary">
                  Session: {codeSessions.find(s => s.id === currentSessionId)?.name}
                </Typography>
              )}
            </Box>
            {supportsPackages ? (
              <>
                {currentRuntime?.package_manager && (
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
                    Managed with {currentRuntime.package_manager}
                  </Typography>
                )}
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
              </>
            ) : (
              <Typography variant="body2" color="text.secondary">
                {currentRuntime?.display_name || language} does not support package installation.
              </Typography>
            )}

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