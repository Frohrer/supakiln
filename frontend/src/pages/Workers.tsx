import React, { useState, useEffect } from 'react';
import {
  Box,
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
  Chip,
  Alert,
  CircularProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  Tooltip,
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  Stop as StopIcon,
  DeleteSweep as DeleteSweepIcon,
} from '@mui/icons-material';
import api, { extractErrorMessage } from '../config/api';
import { formatRelativeTime } from '../config/languages';

interface Worker {
  container_id: string;
  container_short_id: string;
  language: string;
  package_hash: string;
  cache_key: string;
  host: string;
  port: number;
  created_at: string;
  last_used: string;
}

const Workers: React.FC = () => {
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');
  const [success, setSuccess] = useState<string>('');
  const [resetDialogOpen, setResetDialogOpen] = useState(false);
  const [resetting, setResetting] = useState(false);

  const fetchWorkers = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await api.get('/workers');
      setWorkers(response.data.workers || []);
    } catch (err) {
      console.error('Error fetching workers:', err);
      setError(extractErrorMessage(err, 'Failed to fetch workers'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWorkers();
  }, []);

  const handleStop = async (worker: Worker) => {
    try {
      await api.delete(`/workers/${worker.container_id}`);
      setSuccess(`Stopped worker ${worker.container_short_id}`);
      fetchWorkers();
    } catch (err) {
      console.error('Error stopping worker:', err);
      setError(extractErrorMessage(err, 'Failed to stop worker'));
    }
  };

  const handleResetAll = async () => {
    setResetting(true);
    try {
      const response = await api.post('/workers/reset');
      setSuccess(`Reset complete: ${response.data.killed ?? 0} worker(s) stopped`);
      setResetDialogOpen(false);
      fetchWorkers();
    } catch (err) {
      console.error('Error resetting workers:', err);
      setError(extractErrorMessage(err, 'Failed to reset workers'));
    } finally {
      setResetting(false);
    }
  };

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4">Workers</Typography>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={fetchWorkers}
            disabled={loading}
          >
            Refresh
          </Button>
          <Button
            variant="outlined"
            color="error"
            startIcon={<DeleteSweepIcon />}
            onClick={() => setResetDialogOpen(true)}
            disabled={workers.length === 0}
          >
            Reset All
          </Button>
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError('')}>
          {error}
        </Alert>
      )}
      {success && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccess('')}>
          {success}
        </Alert>
      )}

      <Paper sx={{ p: 2 }}>
        {loading && workers.length === 0 ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
            <CircularProgress />
          </Box>
        ) : (
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Short ID</TableCell>
                  <TableCell>Language</TableCell>
                  <TableCell>Package Hash</TableCell>
                  <TableCell>Created</TableCell>
                  <TableCell>Last Used</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {workers.map((worker) => (
                  <TableRow key={worker.container_id}>
                    <TableCell>
                      <Typography variant="body2" fontFamily="monospace">
                        {worker.container_short_id}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Chip label={worker.language} size="small" variant="outlined" />
                    </TableCell>
                    <TableCell>
                      <Tooltip title={worker.package_hash || ''}>
                        <Typography variant="body2" fontFamily="monospace">
                          {worker.package_hash ? worker.package_hash.slice(0, 12) : '-'}
                        </Typography>
                      </Tooltip>
                    </TableCell>
                    <TableCell>
                      <Tooltip title={worker.created_at}>
                        <span>{formatRelativeTime(worker.created_at)}</span>
                      </Tooltip>
                    </TableCell>
                    <TableCell>
                      <Tooltip title={worker.last_used}>
                        <span>{formatRelativeTime(worker.last_used)}</span>
                      </Tooltip>
                    </TableCell>
                    <TableCell align="right">
                      <Tooltip title="Stop worker">
                        <IconButton
                          size="small"
                          color="error"
                          onClick={() => handleStop(worker)}
                        >
                          <StopIcon />
                        </IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                ))}
                {workers.length === 0 && !loading && (
                  <TableRow>
                    <TableCell colSpan={6} align="center">
                      <Typography color="text.secondary">
                        No workers currently running.
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Paper>

      <Dialog open={resetDialogOpen} onClose={() => !resetting && setResetDialogOpen(false)}>
        <DialogTitle>Reset all workers?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            This will stop all {workers.length} cached worker container(s). New workers will be
            started on demand. This action cannot be undone.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setResetDialogOpen(false)} disabled={resetting}>
            Cancel
          </Button>
          <Button onClick={handleResetAll} color="error" variant="contained" disabled={resetting}>
            {resetting ? 'Resetting...' : 'Reset All'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default Workers;
