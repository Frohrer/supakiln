import React, { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Typography,
  Grid,
  Card,
  CardContent,
  Chip,
  Button,
  IconButton,
  Tooltip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Alert,
  CircularProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Tabs,
  Tab,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Stack,
  Divider,
  LinearProgress,
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  Stop as StopIcon,
  Delete as DeleteIcon,
  Launch as LaunchIcon,
  ExpandMore as ExpandMoreIcon,
  PlayArrow as PlayIcon,
  Info as InfoIcon,
  Computer as ComputerIcon,
  WebAsset as WebAssetIcon,
  Storage as StorageIcon,
} from '@mui/icons-material';
import api from '../config/api';

interface Container {
  container_id: string;
  container_short_id: string;
  name: string;
  packages: string[];
  status: string;
  image: string;
  ports: any;
  created_at: string;
  is_web_service: boolean;
}

interface WebService {
  container_id: string;
  container_short_id: string;
  service_type: string;
  internal_port: number;
  external_port: number;
  start_command: string;
}

interface ActiveService {
  container_id: string;
  service_type: string;
  internal_port: number;
  external_port: number;
  proxy_url: string;
}

interface ContainerLogs {
  container_id: string;
  container_logs: string;
  service_log: string;
  is_web_service: boolean;
}

const RunningContainers: React.FC = () => {
  const [tabValue, setTabValue] = useState(0);
  const [containers, setContainers] = useState<Container[]>([]);
  const [webServices, setWebServices] = useState<WebService[]>([]);
  const [activeServices, setActiveServices] = useState<ActiveService[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');
  const [selectedContainer, setSelectedContainer] = useState<Container | null>(null);
  const [containerLogs, setContainerLogs] = useState<ContainerLogs | null>(null);
  const [logsDialogOpen, setLogsDialogOpen] = useState(false);
  const [logsLoading, setLogsLoading] = useState(false);

  const fetchContainerData = async () => {
    setLoading(true);
    setError('');
    try {
      // Fetch debug containers info
      const debugResponse = await api.get('/debug/containers');
      setContainers(debugResponse.data.containers || []);
      setWebServices(debugResponse.data.web_services || []);

      // Fetch active proxy services
      try {
        const servicesResponse = await api.get('/proxy');
        setActiveServices(servicesResponse.data.services || []);
      } catch (serviceError) {
        console.warn('Could not fetch active services:', serviceError);
        setActiveServices([]);
      }
    } catch (err: any) {
      console.error('Error fetching container data:', err);
      setError('Failed to fetch container information. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const fetchContainerLogs = async (containerId: string) => {
    setLogsLoading(true);
    try {
      const response = await api.get(`/debug/container/${containerId}/logs`);
      setContainerLogs(response.data);
    } catch (err: any) {
      console.error('Error fetching container logs:', err);
      setContainerLogs(null);
    } finally {
      setLogsLoading(false);
    }
  };

  const handleDeleteContainer = async (containerId: string) => {
    try {
      await api.delete(`/containers/${containerId}`);
      fetchContainerData(); // Refresh the data
    } catch (err: any) {
      console.error('Error deleting container:', err);
      setError('Failed to delete container');
    }
  };

  const handleViewLogs = (container: Container) => {
    setSelectedContainer(container);
    setLogsDialogOpen(true);
    fetchContainerLogs(container.container_short_id);
  };

  const handleCloseLogsDialog = () => {
    setLogsDialogOpen(false);
    setSelectedContainer(null);
    setContainerLogs(null);
  };

  useEffect(() => {
    fetchContainerData();
    // Set up auto-refresh every 10 seconds
    const interval = setInterval(fetchContainerData, 10000);
    return () => clearInterval(interval);
  }, []);

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'running':
        return 'success';
      case 'exited':
        return 'error';
      case 'created':
        return 'warning';
      default:
        return 'default';
    }
  };

  if (loading && containers.length === 0) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="200px">
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4">Running Containers</Typography>
        <Button
          variant="outlined"
          startIcon={<RefreshIcon />}
          onClick={fetchContainerData}
          disabled={loading}
        >
          Refresh
        </Button>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {/* Summary Cards */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" gap={2}>
                <ComputerIcon color="primary" />
                <Box>
                  <Typography variant="h4">{containers.length}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    Total Containers
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
                <PlayIcon color="success" />
                <Box>
                                     <Typography variant="h4">
                     {containers.filter((c: Container) => c.status === 'running').length}
                   </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Running
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
                <WebAssetIcon color="info" />
                <Box>
                  <Typography variant="h4">{webServices.length}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    Web Services
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
                <StorageIcon color="warning" />
                <Box>
                  <Typography variant="h4">{activeServices.length}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    Active Services
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Paper sx={{ p: 2 }}>
                 <Tabs value={tabValue} onChange={(_, newValue: number) => setTabValue(newValue)} sx={{ mb: 3 }}>
          <Tab label="All Containers" />
          <Tab label="Web Services" />
          <Tab label="Active Services" />
        </Tabs>

        {loading && <LinearProgress sx={{ mb: 2 }} />}

        {/* All Containers Tab */}
        {tabValue === 0 && (
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Container ID</TableCell>
                  <TableCell>Name</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Image</TableCell>
                  <TableCell>Packages</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
                             <TableBody>
                 {containers.map((container: Container) => (
                  <TableRow key={container.container_id}>
                    <TableCell>
                      <Typography variant="body2" fontFamily="monospace">
                        {container.container_short_id}
                      </Typography>
                    </TableCell>
                    <TableCell>{container.name}</TableCell>
                    <TableCell>
                      <Chip
                        label={container.status}
                        color={getStatusColor(container.status)}
                        size="small"
                      />
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" fontFamily="monospace">
                        {container.image}
                      </Typography>
                    </TableCell>
                    <TableCell>
                                             <Stack direction="row" spacing={0.5} flexWrap="wrap">
                         {container.packages.slice(0, 3).map((pkg: string, index: number) => (
                          <Chip key={index} label={pkg} size="small" variant="outlined" />
                        ))}
                        {container.packages.length > 3 && (
                          <Chip label={`+${container.packages.length - 3} more`} size="small" />
                        )}
                      </Stack>
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={container.is_web_service ? 'Web Service' : 'Regular'}
                        color={container.is_web_service ? 'primary' : 'default'}
                        size="small"
                      />
                    </TableCell>
                    <TableCell>
                      <Box display="flex" gap={1}>
                        <Tooltip title="View Logs">
                          <IconButton size="small" onClick={() => handleViewLogs(container)}>
                            <InfoIcon />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="Delete Container">
                          <IconButton
                            size="small"
                            onClick={() => handleDeleteContainer(container.container_id)}
                            color="error"
                          >
                            <DeleteIcon />
                          </IconButton>
                        </Tooltip>
                      </Box>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}

        {/* Web Services Tab */}
        {tabValue === 1 && (
                     <Grid container spacing={2}>
             {webServices.map((service: WebService) => (
              <Grid item xs={12} md={6} lg={4} key={service.container_id}>
                <Card>
                  <CardContent>
                    <Box display="flex" justifyContent="space-between" alignItems="flex-start" mb={2}>
                      <Typography variant="h6" component="div">
                        {service.service_type.toUpperCase()}
                      </Typography>
                      <Chip
                        label={service.service_type}
                        color="primary"
                        size="small"
                      />
                    </Box>
                    
                    <Typography variant="body2" color="text.secondary" gutterBottom>
                      Container: {service.container_short_id}
                    </Typography>
                    
                    <Box display="flex" alignItems="center" gap={2} mb={2}>
                      <Typography variant="body2">
                        Port: {service.internal_port} → {service.external_port}
                      </Typography>
                    </Box>
                    
                    <Typography variant="body2" color="text.secondary" mb={2}>
                      Command: {service.start_command}
                    </Typography>
                    
                    <Button
                      size="small"
                      variant="outlined"
                      startIcon={<LaunchIcon />}
                      onClick={() => window.open(`http://localhost:${service.external_port}`, '_blank')}
                    >
                      Open Service
                    </Button>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        )}

        {/* Active Services Tab */}
        {tabValue === 2 && (
                     <Grid container spacing={2}>
             {activeServices.map((service: ActiveService) => (
              <Grid item xs={12} md={6} lg={4} key={service.container_id}>
                <Card>
                  <CardContent>
                    <Box display="flex" justifyContent="space-between" alignItems="flex-start" mb={2}>
                      <Typography variant="h6" component="div">
                        {service.service_type.toUpperCase()}
                      </Typography>
                      <Chip
                        label="Active"
                        color="success"
                        size="small"
                      />
                    </Box>
                    
                    <Typography variant="body2" color="text.secondary" gutterBottom>
                      Container: {service.container_id}
                    </Typography>
                    
                    <Box display="flex" alignItems="center" gap={2} mb={2}>
                      <Typography variant="body2">
                        Port: {service.internal_port} → {service.external_port}
                      </Typography>
                    </Box>
                    
                    <Stack direction="row" spacing={1}>
                      <Button
                        size="small"
                        variant="contained"
                        startIcon={<LaunchIcon />}
                        onClick={() => window.open(service.proxy_url, '_blank')}
                      >
                        Open Service
                      </Button>
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={() => navigator.clipboard.writeText(service.proxy_url)}
                      >
                        Copy URL
                      </Button>
                    </Stack>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        )}

        {/* Empty States */}
        {!loading && containers.length === 0 && tabValue === 0 && (
          <Alert severity="info">
            No containers are currently running. Create containers from the Editor or Saved Code pages.
          </Alert>
        )}
        
        {!loading && webServices.length === 0 && tabValue === 1 && (
          <Alert severity="info">
            No web services are currently running. Execute web framework code (Streamlit, Flask, FastAPI, Dash) to create web services.
          </Alert>
        )}
        
        {!loading && activeServices.length === 0 && tabValue === 2 && (
          <Alert severity="info">
            No active services found. Web services may take a moment to appear here after starting.
          </Alert>
        )}
      </Paper>

      {/* Container Logs Dialog */}
      <Dialog
        open={logsDialogOpen}
        onClose={handleCloseLogsDialog}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle>
          Container Logs: {selectedContainer?.container_short_id}
        </DialogTitle>
        <DialogContent>
          {logsLoading ? (
            <Box display="flex" justifyContent="center" p={3}>
              <CircularProgress />
            </Box>
          ) : containerLogs ? (
            <Box>
              {containerLogs.is_web_service && containerLogs.service_log && (
                <Accordion defaultExpanded sx={{ mb: 2 }}>
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Typography variant="subtitle1">Service Logs</Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Paper
                      sx={{
                        p: 2,
                        bgcolor: 'background.default',
                        borderRadius: 1,
                        maxHeight: '300px',
                        overflow: 'auto',
                        fontFamily: 'monospace',
                      }}
                    >
                      <pre style={{ margin: 0, fontSize: '12px', lineHeight: 1.4 }}>
                        {containerLogs.service_log}
                      </pre>
                    </Paper>
                  </AccordionDetails>
                </Accordion>
              )}

              <Accordion sx={{ mb: 2 }}>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography variant="subtitle1">Container Logs</Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <Paper
                    sx={{
                      p: 2,
                      bgcolor: 'background.default',
                      borderRadius: 1,
                      maxHeight: '300px',
                      overflow: 'auto',
                      fontFamily: 'monospace',
                    }}
                  >
                    <pre style={{ margin: 0, fontSize: '12px', lineHeight: 1.4 }}>
                      {containerLogs.container_logs || 'No logs available'}
                    </pre>
                  </Paper>
                </AccordionDetails>
              </Accordion>
            </Box>
          ) : (
            <Alert severity="warning">
              Failed to load container logs.
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseLogsDialog}>Close</Button>
          {selectedContainer && (
            <Button 
              onClick={() => fetchContainerLogs(selectedContainer.container_short_id)}
              disabled={logsLoading}
            >
              Refresh Logs
            </Button>
          )}
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default RunningContainers; 