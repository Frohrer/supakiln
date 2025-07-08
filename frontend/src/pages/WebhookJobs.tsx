import React, { useState, useEffect } from 'react';
import {
  Grid,
  Paper,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  IconButton,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Switch,
  FormControlLabel,
  Chip,
  Box,
  Alert,
  Tabs,
  Tab,
} from '@mui/material';
import {
  Delete as DeleteIcon,
  Edit as EditIcon,
  Add as AddIcon,
  Launch as LaunchIcon,
  Code as CodeIcon,
} from '@mui/icons-material';
import api, { extractErrorMessage } from '../config/api';

interface WebhookJob {
  id: number;
  name: string;
  endpoint: string;
  code: string;
  container_id: string | null;
  packages: string | null;
  timeout: number;
  description: string | null;
  last_triggered: string | null;
  is_active: boolean;
  created_at: string;
}

interface Container {
  container_id: string;
  name: string;
  packages: string[];
}

interface WebhookJobForm {
  name: string;
  endpoint: string;
  code: string;
  container_id: string;
  packages: string[];
  timeout: number;
  description: string;
  is_active: boolean;
}

const WebhookJobs: React.FC = () => {
  const [jobs, setJobs] = useState<WebhookJob[]>([]);
  const [containers, setContainers] = useState<Container[]>([]);
  const [selectedJob, setSelectedJob] = useState<WebhookJob | null>(null);
  const [isFormDialogOpen, setIsFormDialogOpen] = useState(false);
  const [isViewDialogOpen, setIsViewDialogOpen] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [error, setError] = useState<string>('');
  const [success, setSuccess] = useState<string>('');
  const [tabValue, setTabValue] = useState(0);

  const [formData, setFormData] = useState<WebhookJobForm>({
    name: '',
    endpoint: '',
    code: '',
    container_id: '',
    packages: [],
    timeout: 30,
    description: '',
    is_active: true,
  });

  const fetchJobs = async () => {
    try {
      const response = await api.get('/webhook-jobs');
      setJobs(response.data);
    } catch (error) {
      console.error('Error fetching webhook jobs:', error);
      setError('Failed to fetch webhook jobs');
    }
  };

  const fetchContainers = async () => {
    try {
      const response = await api.get('/containers');
      setContainers(response.data);
    } catch (error) {
      console.error('Error fetching containers:', error);
    }
  };

  useEffect(() => {
    fetchJobs();
    fetchContainers();
  }, []);

  const handleCreate = () => {
    setFormData({
      name: '',
      endpoint: '',
      code: '# Your webhook code here\n# Request data is available in request_data\n# Set response_data to return a response\n\nresponse_data = {\n    "message": "Hello from webhook!",\n    "request_info": request_data\n}',
      container_id: '',
      packages: [],
      timeout: 30,
      description: '',
      is_active: true,
    });
    setIsEditing(false);
    setIsFormDialogOpen(true);
  };

  const handleEdit = (job: WebhookJob) => {
    setFormData({
      name: job.name,
      endpoint: job.endpoint,
      code: job.code,
      container_id: job.container_id || '',
      packages: job.packages ? job.packages.split(',') : [],
      timeout: job.timeout,
      description: job.description || '',
      is_active: job.is_active,
    });
    setSelectedJob(job);
    setIsEditing(true);
    setIsFormDialogOpen(true);
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm('Are you sure you want to delete this webhook job?')) {
      return;
    }

    try {
      await api.delete(`/webhook-jobs/${id}`);
      setSuccess('Webhook job deleted successfully');
      fetchJobs();
    } catch (error) {
      console.error('Error deleting webhook job:', error);
      setError('Failed to delete webhook job');
    }
  };

  const handleViewJob = (job: WebhookJob) => {
    setSelectedJob(job);
    setIsViewDialogOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const payload = {
        ...formData,
        packages: formData.packages.length > 0 ? formData.packages : undefined,
        container_id: formData.container_id || undefined,
        description: formData.description || undefined,
      };

      if (isEditing && selectedJob) {
        await api.put(`/webhook-jobs/${selectedJob.id}`, payload);
        setSuccess('Webhook job updated successfully');
      } else {
        await api.post('/webhook-jobs', payload);
        setSuccess('Webhook job created successfully');
      }

      setIsFormDialogOpen(false);
      fetchJobs();
    } catch (error: any) {
      console.error('Error saving webhook job:', error);
      setError(extractErrorMessage(error));
    }
  };

  const handleFormChange = (field: string, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handlePackagesChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value;
    const packages = value.split(',').map(pkg => pkg.trim()).filter(pkg => pkg.length > 0);
    handleFormChange('packages', packages);
  };

  const testWebhook = async (job: WebhookJob) => {
    try {
      const response = await api.get(`/webhook${job.endpoint}?test=true`);
      setSuccess(`Webhook test successful: ${JSON.stringify(response.data)}`);
    } catch (error: any) {
      console.error('Error testing webhook:', error);
      setError(extractErrorMessage(error));
    }
  };

  const handleCloseDialog = () => {
    setIsFormDialogOpen(false);
    setIsViewDialogOpen(false);
    setSelectedJob(null);
    setError('');
  };

  const getWebhookUrl = (endpoint: string) => {
    const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    return `${baseUrl}/webhook${endpoint}`;
  };

  return (
    <Grid container spacing={3}>
      {error && (
        <Grid item xs={12}>
          <Alert severity="error" onClose={() => setError('')}>
            {error}
          </Alert>
        </Grid>
      )}
      
      {success && (
        <Grid item xs={12}>
          <Alert severity="success" onClose={() => setSuccess('')}>
            {success}
          </Alert>
        </Grid>
      )}

      <Grid item xs={12}>
        <Paper sx={{ p: 2 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
            <Typography variant="h6">
              Webhook Jobs
            </Typography>
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={handleCreate}
            >
              Create Webhook
            </Button>
          </Box>
          
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Name</TableCell>
                  <TableCell>Endpoint</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Last Triggered</TableCell>
                  <TableCell>Timeout</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {jobs.map((job) => (
                  <TableRow key={job.id}>
                    <TableCell>
                      <Box>
                        <Typography variant="body2" fontWeight="bold">
                          {job.name}
                        </Typography>
                        {job.description && (
                          <Typography variant="caption" color="text.secondary">
                            {job.description}
                          </Typography>
                        )}
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Box>
                        <Typography variant="body2" fontFamily="monospace">
                          {job.endpoint}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {getWebhookUrl(job.endpoint)}
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={job.is_active ? 'Active' : 'Inactive'}
                        color={job.is_active ? 'success' : 'default'}
                        size="small"
                      />
                    </TableCell>
                    <TableCell>
                      {job.last_triggered ? new Date(job.last_triggered).toLocaleString() : 'Never'}
                    </TableCell>
                    <TableCell>{job.timeout}s</TableCell>
                    <TableCell>
                      <IconButton
                        size="small"
                        color="primary"
                        onClick={() => handleViewJob(job)}
                        title="View Details"
                      >
                        <CodeIcon />
                      </IconButton>
                      <IconButton
                        size="small"
                        color="info"
                        onClick={() => testWebhook(job)}
                        title="Test Webhook"
                      >
                        <LaunchIcon />
                      </IconButton>
                      <IconButton
                        size="small"
                        color="primary"
                        onClick={() => handleEdit(job)}
                        title="Edit"
                      >
                        <EditIcon />
                      </IconButton>
                      <IconButton
                        size="small"
                        color="error"
                        onClick={() => handleDelete(job.id)}
                        title="Delete"
                      >
                        <DeleteIcon />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
                {jobs.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} align="center">
                      <Typography color="text.secondary">
                        No webhook jobs found. Create your first webhook!
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      </Grid>

      {/* Create/Edit Dialog */}
      <Dialog
        open={isFormDialogOpen}
        onClose={handleCloseDialog}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle>
          {isEditing ? 'Edit Webhook Job' : 'Create Webhook Job'}
        </DialogTitle>
        <DialogContent>
          <Box sx={{ mt: 2 }}>
            <Tabs value={tabValue} onChange={(_, newValue) => setTabValue(newValue)}>
              <Tab label="Basic Info" />
              <Tab label="Code" />
              <Tab label="Advanced" />
            </Tabs>

            {tabValue === 0 && (
              <Box sx={{ mt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
                <TextField
                  fullWidth
                  label="Name"
                  value={formData.name}
                  onChange={(e) => handleFormChange('name', e.target.value)}
                  required
                />
                <TextField
                  fullWidth
                  label="Endpoint"
                  value={formData.endpoint}
                  onChange={(e) => handleFormChange('endpoint', e.target.value)}
                  placeholder="/my-webhook"
                  helperText="URL path for the webhook (e.g., /my-webhook)"
                  required
                />
                <TextField
                  fullWidth
                  label="Description"
                  value={formData.description}
                  onChange={(e) => handleFormChange('description', e.target.value)}
                  multiline
                  rows={2}
                />
                <FormControlLabel
                  control={
                    <Switch
                      checked={formData.is_active}
                      onChange={(e) => handleFormChange('is_active', e.target.checked)}
                    />
                  }
                  label="Active"
                />
              </Box>
            )}

            {tabValue === 1 && (
              <Box sx={{ mt: 2 }}>
                <TextField
                  fullWidth
                  label="Webhook Code"
                  value={formData.code}
                  onChange={(e) => handleFormChange('code', e.target.value)}
                  multiline
                  rows={15}
                  sx={{ fontFamily: 'monospace' }}
                  helperText="Python code to execute when webhook is triggered. Use 'request_data' to access request information and set 'response_data' for the response."
                />
              </Box>
            )}

            {tabValue === 2 && (
              <Box sx={{ mt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
                <TextField
                  fullWidth
                  label="Timeout (seconds)"
                  type="number"
                  value={formData.timeout}
                  onChange={(e) => handleFormChange('timeout', parseInt(e.target.value) || 30)}
                  inputProps={{ min: 1, max: 300 }}
                />
                <TextField
                  fullWidth
                  label="Python Packages"
                  value={formData.packages.join(', ')}
                  onChange={handlePackagesChange}
                  placeholder="requests, pandas, numpy"
                  helperText="Comma-separated list of Python packages to install"
                />
                <FormControl fullWidth>
                  <InputLabel>Container</InputLabel>
                  <Select
                    value={formData.container_id}
                    label="Container"
                    onChange={(e) => handleFormChange('container_id', e.target.value)}
                  >
                    <MenuItem value="">
                      <em>Auto (create/use based on packages)</em>
                    </MenuItem>
                    {containers.map((container) => (
                      <MenuItem key={container.container_id} value={container.container_id}>
                        {container.name} ({container.packages.join(', ')})
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Box>
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>Cancel</Button>
          <Button onClick={handleSubmit} variant="contained">
            {isEditing ? 'Update' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* View Dialog */}
      <Dialog
        open={isViewDialogOpen}
        onClose={handleCloseDialog}
        maxWidth="md"
        fullWidth
      >
        {selectedJob && (
          <>
            <DialogTitle>Webhook Details: {selectedJob.name}</DialogTitle>
            <DialogContent>
              <Box sx={{ mt: 2 }}>
                <Typography variant="subtitle1" gutterBottom>
                  <strong>Endpoint:</strong> {selectedJob.endpoint}
                </Typography>
                <Typography variant="subtitle1" gutterBottom>
                  <strong>URL:</strong> {getWebhookUrl(selectedJob.endpoint)}
                </Typography>
                <Typography variant="subtitle1" gutterBottom>
                  <strong>Status:</strong> {selectedJob.is_active ? 'Active' : 'Inactive'}
                </Typography>
                <Typography variant="subtitle1" gutterBottom>
                  <strong>Timeout:</strong> {selectedJob.timeout} seconds
                </Typography>
                <Typography variant="subtitle1" gutterBottom>
                  <strong>Last Triggered:</strong> {selectedJob.last_triggered ? new Date(selectedJob.last_triggered).toLocaleString() : 'Never'}
                </Typography>
                {selectedJob.packages && (
                  <Typography variant="subtitle1" gutterBottom>
                    <strong>Packages:</strong> {selectedJob.packages}
                  </Typography>
                )}
                {selectedJob.description && (
                  <Typography variant="subtitle1" gutterBottom>
                    <strong>Description:</strong> {selectedJob.description}
                  </Typography>
                )}
                <Typography variant="h6" gutterBottom sx={{ mt: 2 }}>
                  Code
                </Typography>
                <Paper
                  sx={{
                    p: 2,
                    bgcolor: 'background.paper',
                    borderRadius: 1,
                    maxHeight: '300px',
                    overflow: 'auto',
                  }}
                >
                  <pre style={{ margin: 0, fontFamily: 'monospace' }}>{selectedJob.code}</pre>
                </Paper>
              </Box>
            </DialogContent>
            <DialogActions>
              <Button onClick={() => testWebhook(selectedJob)} color="primary">
                Test Webhook
              </Button>
              <Button onClick={() => handleEdit(selectedJob)} variant="outlined">
                Edit
              </Button>
              <Button onClick={handleCloseDialog}>Close</Button>
            </DialogActions>
          </>
        )}
      </Dialog>
    </Grid>
  );
};

export default WebhookJobs; 