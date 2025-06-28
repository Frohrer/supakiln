import React, { useState, useEffect } from 'react';
import {
  Paper,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Box,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  SelectChangeEvent,
  Tabs,
  Tab,
  Alert,
  Chip,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  IconButton,
  Tooltip,
} from '@mui/material';
import { ExpandMore as ExpandMoreIcon, Refresh as RefreshIcon } from '@mui/icons-material';
import api from '../config/api';

interface Log {
  id: number;
  job_id: number | null;
  webhook_job_id: number | null;
  code: string;
  output: string | null;
  error: string | null;
  container_id: string | null;
  execution_time: number;
  started_at: string;
  status: string;
  request_data: string | null;
  response_data: string | null;
}

interface WebContainer {
  container_id: string;
  name: string;
  packages: string[];
  host_port: number;
  internal_port: number;
  url: string;
}

interface ContainerLogs {
  container_id: string;
  name: string;
  status: string;
  docker_logs: string;
  application_logs: string;
  host_port: number;
  internal_port: number;
  url: string;
}

const Logs: React.FC = () => {
  // Execution logs state
  const [logs, setLogs] = useState<Log[]>([]);
  const [selectedLog, setSelectedLog] = useState<Log | null>(null);
  const [jobFilter, setJobFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  
  // Container logs state
  const [tabValue, setTabValue] = useState(0);
  const [webContainers, setWebContainers] = useState<WebContainer[]>([]);
  const [selectedContainer, setSelectedContainer] = useState<string>('');
  const [containerLogs, setContainerLogs] = useState<ContainerLogs | null>(null);
  const [logsLoading, setLogsLoading] = useState(false);

  const fetchLogs = async () => {
    try {
      const response = await api.get(`/logs`, {
        params: {
          limit: 10,
          offset: (page - 1) * 10,
          job_id: jobFilter || undefined,
          status: statusFilter || undefined,
        },
      });
      setLogs((prevLogs: Log[]) => page === 1 ? response.data : [...prevLogs, ...response.data]);
      setHasMore(response.data.length === 10);
    } catch (error) {
      console.error('Error fetching logs:', error);
    }
  };

  const fetchWebContainers = async () => {
    try {
      const response = await api.get('/web-containers');
      setWebContainers(response.data);
    } catch (error) {
      console.error('Error fetching web containers:', error);
    }
  };

  const fetchContainerLogs = async (containerId: string) => {
    if (!containerId) return;
    
    setLogsLoading(true);
    try {
      const response = await api.get(`/web-containers/${containerId}/logs?tail=500`);
      setContainerLogs(response.data);
    } catch (error) {
      console.error('Error fetching container logs:', error);
      setContainerLogs(null);
    } finally {
      setLogsLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, [page, jobFilter, statusFilter]);

  useEffect(() => {
    if (tabValue === 1) {
      fetchWebContainers();
    }
  }, [tabValue]);

  useEffect(() => {
    if (selectedContainer) {
      fetchContainerLogs(selectedContainer);
    }
  }, [selectedContainer]);

  const handleLoadMore = () => {
    setPage(page + 1);
  };

  const handleLogClick = (log: Log) => {
    setSelectedLog(log);
  };

  const handleCloseDialog = () => {
    setSelectedLog(null);
  };

  const handleJobFilterChange = (event: SelectChangeEvent) => {
    setJobFilter(event.target.value);
    setPage(1);
  };

  const handleStatusFilterChange = (event: SelectChangeEvent) => {
    setStatusFilter(event.target.value);
    setPage(1);
  };

  return (
    <Box>
      <Paper sx={{ p: 2, mb: 3 }}>
        <Tabs value={tabValue} onChange={(_, newValue) => setTabValue(newValue)} sx={{ mb: 3 }}>
          <Tab label="Execution Logs" />
          <Tab label="Container Logs" />
        </Tabs>

        {tabValue === 0 && (
          <>
            <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
              <FormControl sx={{ minWidth: 200 }}>
                <InputLabel>Job</InputLabel>
                <Select
                  value={jobFilter}
                  label="Job"
                  onChange={handleJobFilterChange}
                >
                  <MenuItem value="">All Jobs</MenuItem>
                  {/* Add job options dynamically */}
                </Select>
              </FormControl>
              <FormControl sx={{ minWidth: 200 }}>
                <InputLabel>Status</InputLabel>
                <Select
                  value={statusFilter}
                  label="Status"
                  onChange={handleStatusFilterChange}
                >
                  <MenuItem value="">All Statuses</MenuItem>
                  <MenuItem value="success">Success</MenuItem>
                  <MenuItem value="error">Error</MenuItem>
                  <MenuItem value="timeout">Timeout</MenuItem>
                </Select>
              </FormControl>
            </Box>
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Time</TableCell>
                    <TableCell>Type</TableCell>
                    <TableCell>Job/Webhook ID</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Duration (s)</TableCell>
                    <TableCell>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {logs.map((log) => (
                    <TableRow
                      key={log.id}
                      onClick={() => handleLogClick(log)}
                      sx={{ cursor: 'pointer' }}
                    >
                      <TableCell>{new Date(log.started_at).toLocaleString()}</TableCell>
                      <TableCell>
                        {log.webhook_job_id ? 'Webhook' : log.job_id ? 'Scheduled' : 'Manual'}
                      </TableCell>
                      <TableCell>
                        {log.webhook_job_id ? `W-${log.webhook_job_id}` : log.job_id ? `S-${log.job_id}` : 'Manual'}
                      </TableCell>
                      <TableCell>{log.status}</TableCell>
                      <TableCell>{log.execution_time.toFixed(2)}</TableCell>
                      <TableCell>
                        <Button size="small" variant="outlined">
                          View Details
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            {hasMore && (
              <Box sx={{ mt: 2, display: 'flex', justifyContent: 'center' }}>
                <Button variant="outlined" onClick={handleLoadMore}>
                  Load More
                </Button>
              </Box>
            )}
          </>
        )}

        {tabValue === 1 && (
          <>
            <Box sx={{ display: 'flex', gap: 2, mb: 2, alignItems: 'center' }}>
              <FormControl sx={{ minWidth: 300 }}>
                <InputLabel>Select Container</InputLabel>
                <Select
                  value={selectedContainer}
                  label="Select Container"
                  onChange={(e) => setSelectedContainer(e.target.value)}
                >
                  <MenuItem value="">Select a container</MenuItem>
                  {webContainers.map((container) => (
                    <MenuItem key={container.container_id} value={container.container_id}>
                      {container.name} ({container.url})
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <Tooltip title="Refresh containers">
                <IconButton onClick={fetchWebContainers}>
                  <RefreshIcon />
                </IconButton>
              </Tooltip>
              {selectedContainer && (
                <Tooltip title="Refresh logs">
                  <IconButton onClick={() => fetchContainerLogs(selectedContainer)}>
                    <RefreshIcon />
                  </IconButton>
                </Tooltip>
              )}
            </Box>

            {containerLogs && (
              <Box>
                <Box sx={{ mb: 2, display: 'flex', gap: 1, alignItems: 'center' }}>
                  <Typography variant="h6">{containerLogs.name}</Typography>
                  <Chip 
                    label={containerLogs.status} 
                    color={containerLogs.status === 'running' ? 'success' : containerLogs.status === 'exited' ? 'error' : 'warning'}
                    size="small"
                  />
                  <Typography variant="body2" color="text.secondary">
                    Port: {containerLogs.host_port} → {containerLogs.internal_port}
                  </Typography>
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() => window.open(containerLogs.url, '_blank')}
                  >
                    Open App
                  </Button>
                </Box>

                {containerLogs.application_logs && (
                  <Accordion defaultExpanded sx={{ mb: 2 }}>
                    <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                      <Typography variant="subtitle1">Application Logs</Typography>
                    </AccordionSummary>
                    <AccordionDetails>
                      <Paper
                        sx={{
                          p: 2,
                          bgcolor: 'background.default',
                          borderRadius: 1,
                          maxHeight: '400px',
                          overflow: 'auto',
                          fontFamily: 'monospace',
                        }}
                      >
                        <pre style={{ margin: 0, fontSize: '12px', lineHeight: 1.4 }}>
                          {containerLogs.application_logs || 'No application logs available'}
                        </pre>
                      </Paper>
                    </AccordionDetails>
                  </Accordion>
                )}

                <Accordion sx={{ mb: 2 }}>
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Typography variant="subtitle1">Docker Container Logs</Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Paper
                      sx={{
                        p: 2,
                        bgcolor: 'background.default',
                        borderRadius: 1,
                        maxHeight: '400px',
                        overflow: 'auto',
                        fontFamily: 'monospace',
                      }}
                    >
                      <pre style={{ margin: 0, fontSize: '12px', lineHeight: 1.4 }}>
                        {containerLogs.docker_logs || 'No Docker logs available'}
                      </pre>
                    </Paper>
                  </AccordionDetails>
                </Accordion>
              </Box>
            )}

            {selectedContainer && !containerLogs && !logsLoading && (
              <Alert severity="info">
                No logs available for this container. The container may have exited or not started properly.
              </Alert>
            )}

            {!selectedContainer && (
              <Alert severity="info">
                Select a web container to view its logs.
              </Alert>
            )}

            {logsLoading && (
              <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
                <Typography>Loading logs...</Typography>
              </Box>
            )}
          </>
        )}
      </Paper>

      <Dialog
        open={!!selectedLog}
        onClose={handleCloseDialog}
        maxWidth="md"
        fullWidth
      >
        {selectedLog && (
          <>
            <DialogTitle>Log Details</DialogTitle>
            <DialogContent>
              <Box sx={{ mt: 2 }}>
                <Typography variant="h6" gutterBottom>
                  Code
                </Typography>
                <Paper
                  sx={{
                    p: 2,
                    bgcolor: 'background.paper',
                    borderRadius: 1,
                    maxHeight: '200px',
                    overflow: 'auto',
                  }}
                >
                  <pre>{selectedLog.code}</pre>
                </Paper>
              </Box>
              {selectedLog.output && (
                <Box sx={{ mt: 2 }}>
                  <Typography variant="h6" gutterBottom>
                    Output
                  </Typography>
                  <Paper
                    sx={{
                      p: 2,
                      bgcolor: 'background.paper',
                      borderRadius: 1,
                      maxHeight: '200px',
                      overflow: 'auto',
                    }}
                  >
                    <pre>{selectedLog.output}</pre>
                  </Paper>
                </Box>
              )}
              {selectedLog.error && (
                <Box sx={{ mt: 2 }}>
                  <Typography variant="h6" gutterBottom>
                    Error
                  </Typography>
                  <Paper
                    sx={{
                      p: 2,
                      bgcolor: 'error.main',
                      color: 'error.contrastText',
                      borderRadius: 1,
                      maxHeight: '200px',
                      overflow: 'auto',
                    }}
                  >
                    <pre>{selectedLog.error}</pre>
                  </Paper>
                </Box>
              )}
            </DialogContent>
            <DialogActions>
              <Button onClick={handleCloseDialog}>Close</Button>
            </DialogActions>
          </>
        )}
      </Dialog>
    </Box>
  );
};

export default Logs; 