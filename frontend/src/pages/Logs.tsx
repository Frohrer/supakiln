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
  Grid,
  Card,
  CardContent,
  LinearProgress,
  Divider,
  Stack,
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  Refresh as RefreshIcon,
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  Schedule as ScheduleIcon,
  Code as CodeIcon,
  Timer as TimerIcon,
  TrendingUp as TrendingUpIcon,
  WebAsset as WebAssetIcon,
} from '@mui/icons-material';
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

interface LogStats {
  total_executions: number;
  success_rate: number;
  avg_execution_time: number;
  executions_today: number;
  unique_containers: number;
  webhook_executions: number;
  scheduled_executions: number;
  manual_executions: number;
}

const Logs: React.FC = () => {
  // Execution logs state
  const [logs, setLogs] = useState<Log[]>([]);
  const [selectedLog, setSelectedLog] = useState<Log | null>(null);
  const [jobFilter, setJobFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [logStats, setLogStats] = useState<LogStats | null>(null);
  
  // Container logs state
  const [tabValue, setTabValue] = useState(0);
  const [webContainers, setWebContainers] = useState<WebContainer[]>([]);
  const [selectedContainer, setSelectedContainer] = useState<string>('');
  const [containerLogs, setContainerLogs] = useState<ContainerLogs | null>(null);
  const [logsLoading, setLogsLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const fetchLogs = async () => {
    try {
      const response = await api.get(`/logs`, {
        params: {
          limit: 20,
          offset: (page - 1) * 20,
          job_id: jobFilter || undefined,
          status: statusFilter || undefined,
        },
      });
      setLogs((prevLogs: Log[]) => page === 1 ? response.data : [...prevLogs, ...response.data]);
      setHasMore(response.data.length === 20);
    } catch (error) {
      console.error('Error fetching logs:', error);
    }
  };

  const fetchLogStats = async () => {
    try {
      // Since there's no dedicated stats endpoint, we'll calculate from recent logs
      const response = await api.get('/logs?limit=1000');
      const allLogs: Log[] = response.data;
      
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      
      const todayLogs = allLogs.filter(log => 
        new Date(log.started_at) >= today
      );
      
      const successLogs = allLogs.filter(log => log.status === 'success');
      const uniqueContainers = new Set(allLogs.filter(log => log.container_id).map(log => log.container_id)).size;
      
      const webhookLogs = allLogs.filter(log => log.webhook_job_id);
      const scheduledLogs = allLogs.filter(log => log.job_id && !log.webhook_job_id);
      const manualLogs = allLogs.filter(log => !log.job_id && !log.webhook_job_id);
      
      const avgTime = allLogs.length > 0 
        ? allLogs.reduce((sum, log) => sum + log.execution_time, 0) / allLogs.length 
        : 0;

      setLogStats({
        total_executions: allLogs.length,
        success_rate: allLogs.length > 0 ? (successLogs.length / allLogs.length) * 100 : 0,
        avg_execution_time: avgTime,
        executions_today: todayLogs.length,
        unique_containers: uniqueContainers,
        webhook_executions: webhookLogs.length,
        scheduled_executions: scheduledLogs.length,
        manual_executions: manualLogs.length,
      });
    } catch (error) {
      console.error('Error fetching log stats:', error);
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

  const handleRefreshAll = async () => {
    setRefreshing(true);
    await Promise.all([
      fetchLogs(),
      fetchLogStats(),
      tabValue === 1 ? fetchWebContainers() : Promise.resolve(),
    ]);
    setRefreshing(false);
  };

  useEffect(() => {
    fetchLogs();
    fetchLogStats();
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

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'success':
        return <CheckCircleIcon color="success" />;
      case 'error':
        return <ErrorIcon color="error" />;
      default:
        return <ScheduleIcon color="warning" />;
    }
  };

  const getStatusColor = (status: string): "success" | "error" | "warning" | "default" => {
    switch (status) {
      case 'success':
        return 'success';
      case 'error':
        return 'error';
      default:
        return 'warning';
    }
  };

  const formatDuration = (seconds: number) => {
    if (seconds < 1) return `${(seconds * 1000).toFixed(0)}ms`;
    if (seconds < 60) return `${seconds.toFixed(2)}s`;
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}m ${remainingSeconds.toFixed(0)}s`;
  };

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4">Logs & Monitoring</Typography>
        <Button
          variant="outlined"
          startIcon={<RefreshIcon />}
          onClick={handleRefreshAll}
          disabled={refreshing}
        >
          {refreshing ? 'Refreshing...' : 'Refresh All'}
        </Button>
      </Box>

      {/* Dashboard Cards */}
      {logStats && (
        <Grid container spacing={3} sx={{ mb: 3 }}>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Box display="flex" alignItems="center" gap={2}>
                  <CodeIcon color="primary" />
                  <Box>
                    <Typography variant="h4">{logStats.total_executions}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      Total Executions
                    </Typography>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Box display="flex" alignItems="center" gap={2}>
                  <TrendingUpIcon color="success" />
                  <Box>
                    <Typography variant="h4">{logStats.success_rate.toFixed(1)}%</Typography>
                    <Typography variant="body2" color="text.secondary">
                      Success Rate
                    </Typography>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Box display="flex" alignItems="center" gap={2}>
                  <TimerIcon color="info" />
                  <Box>
                    <Typography variant="h4">{formatDuration(logStats.avg_execution_time)}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      Avg. Duration
                    </Typography>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Box display="flex" alignItems="center" gap={2}>
                  <ScheduleIcon color="warning" />
                  <Box>
                    <Typography variant="h4">{logStats.executions_today}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      Today's Executions
                    </Typography>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {/* Execution Type Breakdown */}
      {logStats && (
        <Paper sx={{ p: 2, mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            Execution Breakdown
          </Typography>
          <Grid container spacing={2}>
            <Grid item xs={12} md={4}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="subtitle2" color="text.secondary">
                    Manual Executions
                  </Typography>
                  <Typography variant="h5">{logStats.manual_executions}</Typography>
                  <LinearProgress 
                    variant="determinate" 
                    value={logStats.total_executions > 0 ? (logStats.manual_executions / logStats.total_executions) * 100 : 0}
                    sx={{ mt: 1 }}
                  />
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={4}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="subtitle2" color="text.secondary">
                    Webhook Executions
                  </Typography>
                  <Typography variant="h5">{logStats.webhook_executions}</Typography>
                  <LinearProgress 
                    variant="determinate" 
                    value={logStats.total_executions > 0 ? (logStats.webhook_executions / logStats.total_executions) * 100 : 0}
                    color="secondary"
                    sx={{ mt: 1 }}
                  />
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={4}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="subtitle2" color="text.secondary">
                    Scheduled Executions
                  </Typography>
                  <Typography variant="h5">{logStats.scheduled_executions}</Typography>
                  <LinearProgress 
                    variant="determinate" 
                    value={logStats.total_executions > 0 ? (logStats.scheduled_executions / logStats.total_executions) * 100 : 0}
                    color="success"
                    sx={{ mt: 1 }}
                  />
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </Paper>
      )}

      <Paper sx={{ p: 2, mb: 3 }}>
        <Tabs value={tabValue} onChange={(_event: any, newValue: number) => setTabValue(newValue)} sx={{ mb: 3 }}>
          <Tab 
            label={
              <Box display="flex" alignItems="center" gap={1}>
                <CodeIcon />
                Execution Logs
              </Box>
            }
          />
          <Tab 
            label={
              <Box display="flex" alignItems="center" gap={1}>
                <WebAssetIcon />
                Container Logs
              </Box>
            }
          />
        </Tabs>

        {refreshing && <LinearProgress sx={{ mb: 2 }} />}

        {tabValue === 0 && (
          <>
            <Box sx={{ display: 'flex', gap: 2, mb: 2, flexWrap: 'wrap' }}>
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
                    <TableCell>Status</TableCell>
                    <TableCell>Time</TableCell>
                    <TableCell>Type</TableCell>
                    <TableCell>Job/Webhook ID</TableCell>
                    <TableCell>Duration</TableCell>
                    <TableCell>Container</TableCell>
                    <TableCell>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {logs.map((log: Log) => (
                    <TableRow
                      key={log.id}
                      onClick={() => handleLogClick(log)}
                      sx={{ 
                        cursor: 'pointer',
                        '&:hover': {
                          backgroundColor: 'action.hover',
                        }
                      }}
                    >
                      <TableCell>
                        <Box display="flex" alignItems="center" gap={1}>
                          {getStatusIcon(log.status)}
                          <Chip
                            label={log.status}
                            color={getStatusColor(log.status)}
                            size="small"
                          />
                        </Box>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">
                          {new Date(log.started_at).toLocaleString()}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={log.webhook_job_id ? 'Webhook' : log.job_id ? 'Scheduled' : 'Manual'}
                          color={log.webhook_job_id ? 'secondary' : log.job_id ? 'success' : 'default'}
                          size="small"
                          variant="outlined"
                        />
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" fontFamily="monospace">
                          {log.webhook_job_id ? `W-${log.webhook_job_id}` : log.job_id ? `S-${log.job_id}` : '-'}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" fontFamily="monospace">
                          {formatDuration(log.execution_time)}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" fontFamily="monospace">
                          {log.container_id && typeof log.container_id === 'string' ? log.container_id.slice(0, 8) : '-'}
                        </Typography>
                      </TableCell>
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
                  onChange={(e: SelectChangeEvent) => setSelectedContainer(e.target.value)}
                >
                  <MenuItem value="">Select a container</MenuItem>
                  {webContainers.map((container: WebContainer) => (
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
                <Card sx={{ mb: 2 }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap' }}>
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
                  </CardContent>
                </Card>

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
        maxWidth="lg"
        fullWidth
      >
        {selectedLog && (
          <>
            <DialogTitle>
              <Box display="flex" alignItems="center" gap={2}>
                {getStatusIcon(selectedLog.status)}
                Log Details - {selectedLog.status.toUpperCase()}
              </Box>
            </DialogTitle>
            <DialogContent>
              <Stack spacing={2}>
                {/* Metadata */}
                <Card variant="outlined">
                  <CardContent>
                    <Typography variant="subtitle1" gutterBottom>
                      Execution Metadata
                    </Typography>
                    <Grid container spacing={2}>
                      <Grid item xs={6}>
                        <Typography variant="body2" color="text.secondary">
                          Started At:
                        </Typography>
                        <Typography variant="body2">
                          {new Date(selectedLog.started_at).toLocaleString()}
                        </Typography>
                      </Grid>
                      <Grid item xs={6}>
                        <Typography variant="body2" color="text.secondary">
                          Duration:
                        </Typography>
                        <Typography variant="body2">
                          {formatDuration(selectedLog.execution_time)}
                        </Typography>
                      </Grid>
                      <Grid item xs={6}>
                        <Typography variant="body2" color="text.secondary">
                          Container ID:
                        </Typography>
                        <Typography variant="body2" fontFamily="monospace">
                          {selectedLog.container_id || 'N/A'}
                        </Typography>
                      </Grid>
                      <Grid item xs={6}>
                        <Typography variant="body2" color="text.secondary">
                          Type:
                        </Typography>
                        <Chip
                          label={selectedLog.webhook_job_id ? 'Webhook' : selectedLog.job_id ? 'Scheduled' : 'Manual'}
                          size="small"
                        />
                      </Grid>
                    </Grid>
                  </CardContent>
                </Card>

                {/* Code */}
                <Box>
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
                    <pre style={{ margin: 0, fontSize: '12px', lineHeight: 1.4 }}>
                      {selectedLog.code}
                    </pre>
                  </Paper>
                </Box>

                {/* Output */}
                {selectedLog.output && (
                  <Box>
                    <Typography variant="h6" gutterBottom>
                      Output
                    </Typography>
                    <Paper
                      sx={{
                        p: 2,
                        bgcolor: 'success.main',
                        color: 'success.contrastText',
                        borderRadius: 1,
                        maxHeight: '200px',
                        overflow: 'auto',
                      }}
                    >
                      <pre style={{ margin: 0, fontSize: '12px', lineHeight: 1.4 }}>
                        {selectedLog.output}
                      </pre>
                    </Paper>
                  </Box>
                )}

                {/* Error */}
                {selectedLog.error && (
                  <Box>
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
                      <pre style={{ margin: 0, fontSize: '12px', lineHeight: 1.4 }}>
                        {selectedLog.error}
                      </pre>
                    </Paper>
                  </Box>
                )}

                {/* Request/Response Data for Webhooks */}
                {selectedLog.request_data && (
                  <Box>
                    <Typography variant="h6" gutterBottom>
                      Request Data
                    </Typography>
                    <Paper
                      sx={{
                        p: 2,
                        bgcolor: 'background.paper',
                        borderRadius: 1,
                        maxHeight: '150px',
                        overflow: 'auto',
                      }}
                    >
                      <pre style={{ margin: 0, fontSize: '12px', lineHeight: 1.4 }}>
                        {selectedLog.request_data}
                      </pre>
                    </Paper>
                  </Box>
                )}

                {selectedLog.response_data && (
                  <Box>
                    <Typography variant="h6" gutterBottom>
                      Response Data
                    </Typography>
                    <Paper
                      sx={{
                        p: 2,
                        bgcolor: 'background.paper',
                        borderRadius: 1,
                        maxHeight: '150px',
                        overflow: 'auto',
                      }}
                    >
                      <pre style={{ margin: 0, fontSize: '12px', lineHeight: 1.4 }}>
                        {selectedLog.response_data}
                      </pre>
                    </Paper>
                  </Box>
                )}
              </Stack>
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