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

interface EnvVarMetadata {
  name: string;
  description?: string;
  created_at: string;
  updated_at: string;
}

interface EnvVar {
  name: string;
  value: string;
  description?: string;
}

export default function EnvironmentVariables() {
  const [variables, setVariables] = useState<EnvVarMetadata[]>([]);
  const [selectedVar, setSelectedVar] = useState<EnvVar | null>(null);
  const [openDialog, setOpenDialog] = useState(false);
  const [newVar, setNewVar] = useState({ name: '', value: '', description: '' });
  const [error, setError] = useState('');

  const fetchVariables = async () => {
    try {
      const response = await api.get<EnvVarMetadata[]>('/env-metadata');
      setVariables(response.data);
    } catch (err) {
      console.error('Error fetching variables:', err);
      setError('Failed to fetch environment variables');
    }
  };

  useEffect(() => {
    fetchVariables();
  }, []);

  const handleOpenDialog = (variableName?: string) => {
    if (variableName) {
      // Get the variable value for editing
      api.get<{ name: string; value: string }>(`/env/${variableName}`).then((response: any) => {
        const metadata = variables.find((v: EnvVarMetadata) => v.name === variableName);
        setSelectedVar({
          name: response.data.name,
          value: response.data.value,
          description: metadata?.description || ''
        });
        setNewVar({ 
          name: response.data.name, 
          value: response.data.value,
          description: metadata?.description || ''
        });
      }).catch((err: any) => {
        console.error('Error fetching variable value:', err);
        setError('Failed to fetch variable details');
      });
    } else {
      setSelectedVar(null);
      setNewVar({ name: '', value: '', description: '' });
    }
    setOpenDialog(true);
  };

  const handleCloseDialog = () => {
    setOpenDialog(false);
    setSelectedVar(null);
    setNewVar({ name: '', value: '', description: '' });
    setError('');
  };

  const handleSave = async () => {
    try {
      if (!newVar.name || !newVar.value) {
        setError('Name and value are required');
        return;
      }

      await api.post('/env', newVar);
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

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString();
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
              <TableCell>Description</TableCell>
              <TableCell>Last Updated</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {variables.map((variable: EnvVarMetadata) => (
              <TableRow key={variable.name}>
                <TableCell>{variable.name}</TableCell>
                <TableCell>{variable.description || '-'}</TableCell>
                <TableCell>{formatDate(variable.updated_at)}</TableCell>
                <TableCell align="right">
                  <IconButton
                    onClick={() => handleOpenDialog(variable.name)}
                    size="small"
                  >
                    <EditIcon />
                  </IconButton>
                  <IconButton
                    onClick={() => handleDelete(variable.name)}
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
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewVar({ ...newVar, name: e.target.value })}
              margin="normal"
              disabled={!!selectedVar}
            />
            <TextField
              fullWidth
              label="Description (optional)"
              value={newVar.description}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewVar({ ...newVar, description: e.target.value })}
              margin="normal"
              multiline
              rows={2}
            />
            <TextField
              fullWidth
              label="Value"
              value={newVar.value}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewVar({ ...newVar, value: e.target.value })}
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