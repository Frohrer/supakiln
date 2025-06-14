import { useState, useEffect } from 'react';
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import AddIcon from '@mui/icons-material/Add';
import { api } from '../config/api';

interface EnvVar {
  name: string;
  value: string;
  created_at: string;
  updated_at: string;
}

export default function EnvironmentVariables() {
  const [variables, setVariables] = useState<string[]>([]);
  const [selectedVar, setSelectedVar] = useState<EnvVar | null>(null);
  const [openDialog, setOpenDialog] = useState(false);
  const [newVar, setNewVar] = useState({ name: '', value: '' });
  const [error, setError] = useState('');

  const fetchVariables = async () => {
    try {
      const response = await api.get<string[]>('/env');
      setVariables(response.data);
    } catch (err) {
      console.error('Error fetching variables:', err);
      setError('Failed to fetch environment variables');
    }
  };

  useEffect(() => {
    fetchVariables();
  }, []);

  const handleOpenDialog = (variable?: string) => {
    if (variable) {
      api.get<EnvVar>(`/env/${variable}`).then(response => {
        setSelectedVar(response.data);
        setNewVar({ name: response.data.name, value: response.data.value });
      });
    } else {
      setSelectedVar(null);
      setNewVar({ name: '', value: '' });
    }
    setOpenDialog(true);
  };

  const handleCloseDialog = () => {
    setOpenDialog(false);
    setSelectedVar(null);
    setNewVar({ name: '', value: '' });
    setError('');
  };

  const handleSave = async () => {
    try {
      if (!newVar.name || !newVar.value) {
        setError('Name and value are required');
        return;
      }

      await api.post<EnvVar>('/env', newVar);
      handleCloseDialog();
      fetchVariables();
    } catch (err) {
      console.error('Error saving variable:', err);
      setError('Failed to save environment variable');
    }
  };

  const handleDelete = async (name: string) => {
    if (window.confirm(`Are you sure you want to delete ${name}?`)) {
      try {
        await api.delete(`/env/${name}`);
        fetchVariables();
      } catch (err) {
        console.error('Error deleting variable:', err);
        setError('Failed to delete environment variable');
      }
    }
  };

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 3 }}>
        <Typography variant="h4">Environment Variables</Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => handleOpenDialog()}
        >
          Add Variable
        </Button>
      </Box>

      {error && (
        <Typography color="error" sx={{ mb: 2 }}>
          {error}
        </Typography>
      )}

      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Last Updated</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {variables.map((name) => (
              <TableRow key={name}>
                <TableCell>{name}</TableCell>
                <TableCell>
                  {selectedVar?.name === name ? selectedVar.updated_at : ''}
                </TableCell>
                <TableCell align="right">
                  <IconButton
                    onClick={() => handleOpenDialog(name)}
                    size="small"
                  >
                    <EditIcon />
                  </IconButton>
                  <IconButton
                    onClick={() => handleDelete(name)}
                    size="small"
                    color="error"
                  >
                    <DeleteIcon />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      <Dialog open={openDialog} onClose={handleCloseDialog} maxWidth="sm" fullWidth>
        <DialogTitle>
          {selectedVar ? 'Edit Environment Variable' : 'Add Environment Variable'}
        </DialogTitle>
        <DialogContent>
          <Box sx={{ pt: 2 }}>
            <TextField
              fullWidth
              label="Name"
              value={newVar.name}
              onChange={(e) => setNewVar({ ...newVar, name: e.target.value })}
              margin="normal"
              disabled={!!selectedVar}
            />
            <TextField
              fullWidth
              label="Value"
              value={newVar.value}
              onChange={(e) => setNewVar({ ...newVar, value: e.target.value })}
              margin="normal"
              type="password"
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>Cancel</Button>
          <Button onClick={handleSave} variant="contained">
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
} 