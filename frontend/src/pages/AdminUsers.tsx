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
  Chip,
  Tooltip,
  Switch,
  CircularProgress,
  FormControlLabel,
} from '@mui/material';
import {
  Delete as DeleteIcon,
  PersonAdd as PersonAddIcon,
  VpnKey as ResetPwIcon,
} from '@mui/icons-material';
import { api, extractErrorMessage } from '../config/api';
import { useAuth, AuthUser } from '../auth/AuthContext';

const SYSTEM_USER_ID = 1;

interface NewUserForm {
  email: string;
  password: string;
  is_admin: boolean;
}

const AdminUsers: React.FC = () => {
  const { user: me } = useAuth();
  const [users, setUsers] = useState<AuthUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState<NewUserForm>({
    email: '',
    password: '',
    is_admin: false,
  });
  const [submitting, setSubmitting] = useState(false);
  const [resetFor, setResetFor] = useState<AuthUser | null>(null);
  const [resetPwd, setResetPwd] = useState('');

  const load = useCallback(async () => {
    setError(null);
    try {
      const r = await api.get<AuthUser[]>('/admin/users');
      setUsers(r.data);
    } catch (e) {
      setError(extractErrorMessage(e, 'Could not load users'));
      setUsers([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (!me?.is_admin) {
    return (
      <Paper sx={{ p: 3 }}>
        <Typography variant="h5" sx={{ mb: 1 }}>
          Admin: users
        </Typography>
        <Alert severity="warning">Admin access required.</Alert>
      </Paper>
    );
  }

  const handleCreate = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await api.post('/admin/users', form);
      setForm({ email: '', password: '', is_admin: false });
      setCreateOpen(false);
      await load();
    } catch (e) {
      setError(extractErrorMessage(e, 'Could not create user'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (u: AuthUser) => {
    if (!confirm(`Delete ${u.email}? This revokes their keys and can't be undone.`)) return;
    setError(null);
    try {
      await api.delete(`/admin/users/${u.id}`);
      await load();
    } catch (e) {
      setError(extractErrorMessage(e, 'Could not delete user'));
    }
  };

  const toggleDisabled = async (u: AuthUser) => {
    setError(null);
    try {
      await api.patch(`/admin/users/${u.id}`, { disabled: !u.disabled });
      await load();
    } catch (e) {
      setError(extractErrorMessage(e, 'Could not update user'));
    }
  };

  const toggleAdmin = async (u: AuthUser) => {
    setError(null);
    try {
      await api.patch(`/admin/users/${u.id}`, { is_admin: !u.is_admin });
      await load();
    } catch (e) {
      setError(extractErrorMessage(e, 'Could not update user'));
    }
  };

  const doResetPassword = async () => {
    if (!resetFor) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.patch(`/admin/users/${resetFor.id}`, { password: resetPwd });
      setResetFor(null);
      setResetPwd('');
    } catch (e) {
      setError(extractErrorMessage(e, 'Could not reset password'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2, gap: 2 }}>
        <Typography variant="h5" sx={{ flexGrow: 1 }}>
          Admin: users
        </Typography>
        <Button
          variant="contained"
          startIcon={<PersonAddIcon />}
          onClick={() => setCreateOpen(true)}
        >
          New user
        </Button>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <Paper>
        {users === null ? (
          <Box sx={{ p: 4, display: 'flex', justifyContent: 'center' }}>
            <CircularProgress size={24} />
          </Box>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>ID</TableCell>
                <TableCell>Email</TableCell>
                <TableCell>Role</TableCell>
                <TableCell>Enabled</TableCell>
                <TableCell>Created</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {users.map((u) => {
                const isSystem = u.id === SYSTEM_USER_ID;
                const isSelf = me?.id === u.id;
                return (
                  <TableRow key={u.id}>
                    <TableCell>{u.id}</TableCell>
                    <TableCell>
                      {u.email}
                      {isSelf && (
                        <Chip
                          size="small"
                          label="you"
                          sx={{ ml: 1 }}
                          color="primary"
                        />
                      )}
                      {isSystem && (
                        <Chip
                          size="small"
                          label="system"
                          sx={{ ml: 1 }}
                          variant="outlined"
                        />
                      )}
                    </TableCell>
                    <TableCell>
                      <Tooltip title={isSystem ? 'System user — role is fixed' : 'Toggle admin'}>
                        <span>
                          <Switch
                            size="small"
                            checked={u.is_admin}
                            disabled={isSystem || isSelf}
                            onChange={() => toggleAdmin(u)}
                          />
                        </span>
                      </Tooltip>
                      {u.is_admin ? 'admin' : 'user'}
                    </TableCell>
                    <TableCell>
                      <Tooltip title={isSystem ? 'System user — always enabled' : 'Toggle enabled'}>
                        <span>
                          <Switch
                            size="small"
                            checked={!u.disabled}
                            disabled={isSystem || isSelf}
                            onChange={() => toggleDisabled(u)}
                          />
                        </span>
                      </Tooltip>
                    </TableCell>
                    <TableCell>
                      {u.created_at
                        ? new Date(u.created_at).toLocaleDateString()
                        : ''}
                    </TableCell>
                    <TableCell align="right">
                      {!isSystem && (
                        <>
                          <Tooltip title="Reset password">
                            <IconButton
                              size="small"
                              onClick={() => {
                                setResetFor(u);
                                setResetPwd('');
                              }}
                            >
                              <ResetPwIcon fontSize="small" />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title={isSelf ? "Can't delete yourself" : 'Delete user'}>
                            <span>
                              <IconButton
                                size="small"
                                disabled={isSelf}
                                onClick={() => handleDelete(u)}
                              >
                                <DeleteIcon fontSize="small" />
                              </IconButton>
                            </span>
                          </Tooltip>
                        </>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </Paper>

      {/* Create dialog */}
      <Dialog open={createOpen} onClose={() => setCreateOpen(false)}>
        <DialogTitle>Create user</DialogTitle>
        <DialogContent>
          <TextField
            label="Email"
            type="email"
            fullWidth
            required
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            sx={{ mt: 1, minWidth: 380 }}
            autoFocus
          />
          <TextField
            label="Initial password"
            type="password"
            fullWidth
            required
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            sx={{ mt: 2 }}
          />
          <FormControlLabel
            control={
              <Switch
                checked={form.is_admin}
                onChange={(e) => setForm({ ...form, is_admin: e.target.checked })}
              />
            }
            label="Admin"
            sx={{ mt: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleCreate}
            disabled={submitting || !form.email || !form.password}
          >
            {submitting ? <CircularProgress size={18} /> : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Reset password dialog */}
      <Dialog open={!!resetFor} onClose={() => setResetFor(null)}>
        <DialogTitle>Reset password — {resetFor?.email}</DialogTitle>
        <DialogContent>
          <TextField
            label="New password"
            type="password"
            fullWidth
            required
            value={resetPwd}
            onChange={(e) => setResetPwd(e.target.value)}
            sx={{ mt: 1, minWidth: 380 }}
            autoFocus
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setResetFor(null)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={doResetPassword}
            disabled={submitting || !resetPwd}
          >
            {submitting ? <CircularProgress size={18} /> : 'Reset'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default AdminUsers;
