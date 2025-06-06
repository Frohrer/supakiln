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
} from '@mui/material';
import { Delete as DeleteIcon, PlayArrow as PlayIcon, Edit as EditIcon } from '@mui/icons-material';
import api from '../config/api';

interface ScheduledJob {
  id: number;
  name: string;
  cron_expression: string;
  code: string;
  last_run: string | null;
  is_active: boolean;
  container_id: string | null;
  packages: string | null;
}

const Scheduler: React.FC = () => {
  const [jobs, setJobs] = useState<ScheduledJob[]>([]);
  const [selectedJob, setSelectedJob] = useState<ScheduledJob | null>(null);
  const [isViewDialogOpen, setIsViewDialogOpen] = useState(false);

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
        code: job.code,
        packages: job.packages ? job.packages.split(',') : [],
        container_id: job.container_id,
      });
      fetchJobs(); // Refresh to get updated last_run
    } catch (error) {
      console.error('Error running job:', error);
    }
  };

  const handleViewJob = (job: ScheduledJob) => {
    setSelectedJob(job);
    setIsViewDialogOpen(true);
  };

  const handleCloseDialog = () => {
    setIsViewDialogOpen(false);
    setSelectedJob(null);
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
              <Box sx={{ mt: 2 }}>
                <Typography variant="subtitle1" gutterBottom>
                  Schedule: {selectedJob.cron_expression}
                </Typography>
                <Typography variant="subtitle1" gutterBottom>
                  Last Run: {selectedJob.last_run ? new Date(selectedJob.last_run).toLocaleString() : 'Never'}
                </Typography>
                <Typography variant="subtitle1" gutterBottom>
                  Status: {selectedJob.is_active ? 'Active' : 'Inactive'}
                </Typography>
                {selectedJob.packages && (
                  <Typography variant="subtitle1" gutterBottom>
                    Packages: {selectedJob.packages}
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
                  <pre>{selectedJob.code}</pre>
                </Paper>
              </Box>
            </DialogContent>
            <DialogActions>
              <Button onClick={handleCloseDialog}>Close</Button>
            </DialogActions>
          </>
        )}
      </Dialog>
    </Grid>
  );
};

export default Scheduler; 