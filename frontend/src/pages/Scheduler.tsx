import React, { useState, useEffect } from 'react';
import {
  Grid,
  Paper,
  Typography,
  TextField,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  IconButton,
} from '@mui/material';
import { Delete as DeleteIcon, PlayArrow as PlayIcon } from '@mui/icons-material';
import api from '../config/api';

interface ScheduledJob {
  id: string;
  name: string;
  cronExpression: string;
  code: string;
  lastRun: string | null;
  nextRun: string | null;
  isActive: boolean;
}

const Scheduler: React.FC = () => {
  const [jobs, setJobs] = useState<ScheduledJob[]>([]);
  const [newJob, setNewJob] = useState({
    name: '',
    cronExpression: '',
    code: '',
    packages: [''],
  });

  const handleAddPackage = () => {
    setNewJob({
      ...newJob,
      packages: [...newJob.packages, ''],
    });
  };

  const handleRemovePackage = (index: number) => {
    setNewJob({
      ...newJob,
      packages: newJob.packages.filter((_, i) => i !== index),
    });
  };

  const handlePackageChange = (index: number, value: string) => {
    const newPackages = [...newJob.packages];
    newPackages[index] = value;
    setNewJob({
      ...newJob,
      packages: newPackages,
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.post('/jobs', newJob);
      setNewJob({
        name: '',
        cronExpression: '',
        code: '',
        packages: [''],
      });
      fetchJobs();
    } catch (error) {
      console.error('Error creating job:', error);
    }
  };

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

  const handleDelete = async (id: string) => {
    try {
      await api.delete(`/jobs/${id}`);
      fetchJobs();
    } catch (error) {
      console.error('Error deleting job:', error);
    }
  };

  return (
    <Grid container spacing={3}>
      <Grid item xs={12} md={8}>
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
                    <TableCell>{job.cronExpression}</TableCell>
                    <TableCell>{job.lastRun}</TableCell>
                    <TableCell>{job.isActive ? 'Active' : 'Inactive'}</TableCell>
                    <TableCell>
                      <IconButton size="small" color="primary">
                        <PlayIcon />
                      </IconButton>
                      <IconButton size="small" color="error" onClick={() => handleDelete(job.id)}>
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
      <Grid item xs={12} md={4}>
        <Paper sx={{ p: 2 }}>
          <Typography variant="h6" gutterBottom>
            New Scheduled Job
          </Typography>
          <form onSubmit={handleSubmit}>
            <TextField
              fullWidth
              label="Job Name"
              value={newJob.name}
              onChange={(e) => setNewJob({ ...newJob, name: e.target.value })}
              margin="normal"
              required
            />
            <TextField
              fullWidth
              label="Cron Schedule"
              value={newJob.cronExpression}
              onChange={(e) => setNewJob({ ...newJob, cronExpression: e.target.value })}
              margin="normal"
              required
              placeholder="* * * * *"
              helperText="Format: minute hour day month weekday"
            />
            <TextField
              fullWidth
              label="Python Code"
              value={newJob.code}
              onChange={(e) => setNewJob({ ...newJob, code: e.target.value })}
              margin="normal"
              required
              multiline
              rows={4}
            />
            <Typography variant="subtitle1" gutterBottom sx={{ mt: 2 }}>
              Packages
            </Typography>
            {newJob.packages.map((package_, index) => (
              <div key={index} style={{ display: 'flex', marginBottom: '8px' }}>
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
              </div>
            ))}
            <Button
              variant="outlined"
              onClick={handleAddPackage}
              sx={{ mt: 1 }}
            >
              Add Package
            </Button>
            <Button
              type="submit"
              variant="contained"
              fullWidth
              sx={{ mt: 2 }}
            >
              Schedule Job
            </Button>
          </form>
        </Paper>
      </Grid>
    </Grid>
  );
};

export default Scheduler; 