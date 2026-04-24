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
  Box,
  TextField,
  MenuItem,
} from '@mui/material';
import { Delete as DeleteIcon, PlayArrow as PlayIcon, Edit as EditIcon } from '@mui/icons-material';
import api, { extractErrorMessage } from '../config/api';
import { Runtime, fetchRuntimes } from '../config/languages';

interface ScheduledJob {
  id: number;
  name: string;
  cron_expression: string;
  code: string;
  last_run: string | null;
  is_active: boolean;
  container_id: string | null;
  packages: string | null;
  language?: string;
}

const Scheduler: React.FC = () => {
  const [jobs, setJobs] = useState<ScheduledJob[]>([]);
  const [selectedJob, setSelectedJob] = useState<ScheduledJob | null>(null);
  const [isViewDialogOpen, setIsViewDialogOpen] = useState(false);
  const [runtimes, setRuntimes] = useState<Runtime[]>([]);
  const [editLanguage, setEditLanguage] = useState<string>('python');
  const [editCronExpression, setEditCronExpression] = useState<string>('');
  const [editError, setEditError] = useState<string>('');

  const fetchJobs = async () => {
    try {
      const response = await api.get('/jobs');
      setJobs(response.data);
    } catch (error) {
      console.error('Error fetching jobs:', error);
    }
  };

  useEffect(() => {
    fetchJobs();
    fetchRuntimes()
      .then((rts) => setRuntimes(rts))
      .catch((err) => console.error('Error fetching runtimes:', err));
  }, []);

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/jobs/${id}`);
      fetchJobs();
    } catch (error) {
      console.error('Error deleting job:', error);
    }
  };

  const handleRunNow = async (job: ScheduledJob) => {
    try {
      await api.post('/execute', {
        job_id: job.id,
        packages: job.packages ? job.packages.split(',') : [],
        container_id: job.container_id,
        language: job.language || 'python',
      });
      fetchJobs(); // Refresh to get updated last_run
    } catch (error) {
      console.error('Error running job:', error);
    }
  };

  const handleViewJob = (job: ScheduledJob) => {
    setSelectedJob(job);
    setEditLanguage(job.language || 'python');
    setEditCronExpression(job.cron_expression);
    setEditError('');
    setIsViewDialogOpen(true);
  };

  const handleSaveJob = async () => {
    if (!selectedJob) return;
    try {
      await api.put(`/jobs/${selectedJob.id}`, {
        name: selectedJob.name,
        cron_expression: editCronExpression,
        code: selectedJob.code,
        packages: selectedJob.packages ? selectedJob.packages.split(',').filter(p => p.trim() !== '') : [],
        language: editLanguage,
      });
      setIsViewDialogOpen(false);
      setSelectedJob(null);
      fetchJobs();
    } catch (error) {
      console.error('Error updating job:', error);
      setEditError(extractErrorMessage(error));
    }
  };

  const handleCloseDialog = () => {
    setIsViewDialogOpen(false);
    setSelectedJob(null);
    setEditError('');
  };

  return (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Paper sx={{ p: 2 }}>
          <Typography variant="h6" gutterBottom>
            Scheduled Jobs
          </Typography>
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Name</TableCell>
                  <TableCell>Language</TableCell>
                  <TableCell>Schedule</TableCell>
                  <TableCell>Last Run</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {jobs.map((job) => (
                  <TableRow key={job.id}>
                    <TableCell>{job.name}</TableCell>
                    <TableCell>{job.language || 'python'}</TableCell>
                    <TableCell>{job.cron_expression}</TableCell>
                    <TableCell>
                      {job.last_run ? new Date(job.last_run).toLocaleString() : 'Never'}
                    </TableCell>
                    <TableCell>{job.is_active ? 'Active' : 'Inactive'}</TableCell>
                    <TableCell>
                      <IconButton
                        size="small"
                        color="primary"
                        onClick={() => handleViewJob(job)}
                        title="View Details"
                      >
                        <EditIcon />
                      </IconButton>
                      <IconButton
                        size="small"
                        color="primary"
                        onClick={() => handleRunNow(job)}
                        title="Run Now"
                      >
                        <PlayIcon />
                      </IconButton>
                      <IconButton
                        size="small"
                        color="error"
                        onClick={() => handleDelete(job.id)}
                        title="Delete Job"
                      >
                        <DeleteIcon />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      </Grid>

      <Dialog
        open={isViewDialogOpen}
        onClose={handleCloseDialog}
        maxWidth="md"
        fullWidth
      >
        {selectedJob && (
          <>
            <DialogTitle>Job Details: {selectedJob.name}</DialogTitle>
            <DialogContent>
              <Box sx={{ mt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
                {editError && (
                  <Typography variant="body2" color="error">
                    {editError}
                  </Typography>
                )}
                <TextField
                  label="Cron Schedule"
                  value={editCronExpression}
                  onChange={(e) => setEditCronExpression(e.target.value)}
                  size="small"
                  helperText="Format: minute hour day month weekday"
                />
                <TextField
                  select
                  label="Language"
                  value={editLanguage}
                  onChange={(e) => setEditLanguage(e.target.value)}
                  size="small"
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
                <Typography variant="subtitle1">
                  Last Run: {selectedJob.last_run ? new Date(selectedJob.last_run).toLocaleString() : 'Never'}
                </Typography>
                <Typography variant="subtitle1">
                  Status: {selectedJob.is_active ? 'Active' : 'Inactive'}
                </Typography>
                {selectedJob.packages && (
                  <Typography variant="subtitle1">
                    Packages: {selectedJob.packages}
                  </Typography>
                )}
                <Typography variant="h6" sx={{ mt: 1 }}>
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
                  <pre>{selectedJob.code}</pre>
                </Paper>
              </Box>
            </DialogContent>
            <DialogActions>
              <Button onClick={handleCloseDialog}>Close</Button>
              <Button onClick={handleSaveJob} variant="contained">Save</Button>
            </DialogActions>
          </>
        )}
      </Dialog>
    </Grid>
  );
};

export default Scheduler; 