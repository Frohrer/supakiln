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
} from '@mui/material';
import api from '../config/api';

interface Log {
  id: number;
  job_id: number | null;
  code: string;
  output: string | null;
  error: string | null;
  container_id: string | null;
  execution_time: number;
  started_at: string;
  status: string;
}

const Logs: React.FC = () => {
  const [logs, setLogs] = useState<Log[]>([]);
  const [selectedLog, setSelectedLog] = useState<Log | null>(null);
  const [jobFilter, setJobFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

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

  useEffect(() => {
    fetchLogs();
  }, [page, jobFilter, statusFilter]);

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
                <TableCell>Job ID</TableCell>
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
                  <TableCell>{log.job_id || 'Manual'}</TableCell>
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