import React, { useCallback, useEffect, useState } from 'react';
import {
  Box,
  Button,
  Typography,
  Paper,
  TextField,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Alert,
  Tooltip,
  CircularProgress,
} from '@mui/material';
import {
  ContentCopy as CopyIcon,
  Delete as DeleteIcon,
  Add as AddIcon,
} from '@mui/icons-material';
import { api, extractErrorMessage } from '../config/api';
import { useAuth } from '../auth/AuthContext';

interface ApiKey {
  id: number;
  prefix: string;
  label: string | null;
  last_used_at: string | null;
  created_at: string;
}

interface CreatedKey extends ApiKey {
  token: string; // plaintext, returned exactly once
}

const ApiKeys: React.FC = () => {
  const { user } = useAuth();
  const [keys, setKeys] = useState<ApiKey[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [label, setLabel] = useState('');
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<CreatedKey | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const r = await api.get<ApiKey[]>('/users/me/keys');
      setKeys(r.data);
    } catch (e) {
      setError(extractErrorMessage(e, 'Could not load API keys'));
      setKeys([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const isAnonymous = !user || user.id === 1;

  const handleCreate = async () => {
    setCreating(true);
    setError(null);
    try {
      const r = await api.post<CreatedKey>('/users/me/keys', { label: label || null });
      setCreated(r.data);
      setLabel('');
      setCreateOpen(false);
      await load();
    } catch (e) {
      setError(extractErrorMessage(e, 'Could not create key'));
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: number) => {
    setError(null);
    try {
      await api.delete(`/users/me/keys/${id}`);
      await load();
    } catch (e) {
      setError(extractErrorMessage(e, 'Could not revoke key'));
    }
  };

  const copyToken = async () => {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.token);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard may be blocked; user can still select manually */
    }
  };

  if (isAnonymous) {
    return (
      <Paper sx={{ p: 3 }}>
        <Typography variant="h5" sx={{ mb: 1 }}>
          API keys
        </Typography>
        <Alert severity="info">
          Sign in to manage API keys. Anonymous sessions use the shared system
          identity and can't mint keys.
        </Alert>
      </Paper>
    );
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2, gap: 2 }}>
        <Typography variant="h5" sx={{ flexGrow: 1 }}>
          API keys
        </Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setCreateOpen(true)}
        >
          New key
        </Button>
      </Box>

      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Long-lived bearer tokens for CLI / CI use. Send as{' '}
        <code>Authorization: Bearer &lt;key&gt;</code>. The token is shown
        <strong> exactly once</strong> at creation — store it immediately.
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <Paper>
        {keys === null ? (
          <Box sx={{ p: 4, display: 'flex', justifyContent: 'center' }}>
            <CircularProgress size={24} />
          </Box>
        ) : keys.length === 0 ? (
          <Box sx={{ p: 3 }}>
            <Typography color="text.secondary">
              No active keys. Click "New key" to mint one.
            </Typography>
          </Box>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Label</TableCell>
                <TableCell>Prefix</TableCell>
                <TableCell>Created</TableCell>
                <TableCell>Last used</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {keys.map((k) => (
                <TableRow key={k.id}>
                  <TableCell>{k.label || <em>—</em>}</TableCell>
                  <TableCell>
                    <code>{k.prefix}…</code>
                  </TableCell>
                  <TableCell>
                    {new Date(k.created_at).toLocaleString()}
                  </TableCell>
                  <TableCell>
                    {k.last_used_at
                      ? new Date(k.last_used_at).toLocaleString()
                      : <em style={{ color: '#888' }}>never</em>}
                  </TableCell>
                  <TableCell align="right">
                    <Tooltip title="Revoke">
                      <IconButton
                        size="small"
                        onClick={() => handleDelete(k.id)}
                      >
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Paper>

      {/* Create dialog */}
      <Dialog open={createOpen} onClose={() => setCreateOpen(false)}>
        <DialogTitle>New API key</DialogTitle>
        <DialogContent>
          <TextField
            label="Label (optional)"
            fullWidth
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            helperText="Something to remember what this key is for, e.g. ci, laptop."
            sx={{ mt: 1, minWidth: 380 }}
            autoFocus
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleCreate} disabled={creating}>
            {creating ? <CircularProgress size={18} /> : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Show-once plaintext dialog */}
      <Dialog
        open={!!created}
        onClose={() => setCreated(null)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Copy your new API key</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            This is the only time the full token is shown. Store it somewhere
            durable now — we only keep its hash on the server.
          </Alert>
          <Box
            sx={{
              p: 1.5,
              border: '1px solid',
              borderColor: 'divider',
              borderRadius: 1,
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              fontFamily: 'monospace',
              fontSize: 13,
              wordBreak: 'break-all',
            }}
          >
            <Box sx={{ flexGrow: 1 }}>{created?.token}</Box>
            <Tooltip title={copied ? 'Copied!' : 'Copy'}>
              <IconButton size="small" onClick={copyToken}>
                <CopyIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreated(null)} variant="contained">
            Done
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ApiKeys;
