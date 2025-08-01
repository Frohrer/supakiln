import React, { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Typography,
  TextField,
  List,
  ListItem,
  ListItemText,
  IconButton,
  InputAdornment,
  Chip,
  ListItemSecondaryAction,
} from '@mui/material';
import { Edit as EditIcon, Search as SearchIcon, Delete as DeleteIcon, Code as CodeIcon } from '@mui/icons-material';

interface CodeSession {
  id: string;
  name: string;
  code: string;
  packages: string[];
  created_at: string;
  updated_at: string;
}

interface CodeSessionListProps {
  onLoadSession: (session: CodeSession) => void;
}

const CodeSessionList: React.FC<CodeSessionListProps> = ({ onLoadSession }) => {
  const [codeSessions, setCodeSessions] = useState<CodeSession[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadCodeSessions();
  }, []);

  const loadCodeSessions = () => {
    try {
      const sessions = localStorage.getItem('codeSessions');
      if (sessions) {
        setCodeSessions(JSON.parse(sessions));
      }
      setLoading(false);
    } catch (error) {
      console.error('Error loading code sessions:', error);
      setLoading(false);
    }
  };

  const handleDeleteSession = (sessionId: string) => {
    const updatedSessions = codeSessions.filter((s: CodeSession) => s.id !== sessionId);
    localStorage.setItem('codeSessions', JSON.stringify(updatedSessions));
    setCodeSessions(updatedSessions);
  };

  const filteredSessions = codeSessions.filter((session: CodeSession) =>
    session.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    session.packages.some((pkg: string) => pkg.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  return (
    <Paper sx={{ p: 2, height: '100%' }}>
      <Typography variant="h6" gutterBottom>
        Saved Code Sessions
      </Typography>
      <TextField
        fullWidth
        size="small"
        placeholder="Search sessions and packages..."
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        sx={{ mb: 2 }}
        InputProps={{
          startAdornment: (
            <InputAdornment position="start">
              <SearchIcon />
            </InputAdornment>
          ),
        }}
      />
      <List sx={{ maxHeight: '400px', overflow: 'auto' }}>
        {loading ? (
          <ListItem>
            <ListItemText primary="Loading code sessions..." />
          </ListItem>
        ) : filteredSessions.length === 0 ? (
          <ListItem>
            <ListItemText 
              primary="No saved sessions found" 
              secondary={searchQuery ? "Try adjusting your search" : "Save your first code session from the editor"}
            />
          </ListItem>
        ) : (
          filteredSessions.map((session) => (
            <ListItem
              key={session.id}
              sx={{ 
                cursor: 'pointer',
                '&:hover': { bgcolor: 'action.hover' },
                borderRadius: 1,
                mb: 1
              }}
              onClick={() => onLoadSession(session)}
            >
              <CodeIcon sx={{ mr: 2, color: 'primary.main' }} />
              <ListItemText
                primary={session.name}
                secondary={
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      Updated: {new Date(session.updated_at).toLocaleDateString()}
                    </Typography>
                    {(session.packages || []).length > 0 && (
                      <Box sx={{ mt: 1, display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                        {(session.packages || []).slice(0, 3).map((pkg, index) => (
                          <Chip
                            key={index}
                            label={pkg}
                            size="small"
                            variant="outlined"
                            sx={{ fontSize: '0.7rem', height: '20px' }}
                          />
                        ))}
                        {(session.packages || []).length > 3 && (
                          <Chip
                            label={`+${(session.packages || []).length - 3} more`}
                            size="small"
                            variant="outlined"
                            sx={{ fontSize: '0.7rem', height: '20px' }}
                          />
                        )}
                      </Box>
                    )}
                  </Box>
                }
              />
              <ListItemSecondaryAction>
                <IconButton
                  edge="end"
                  aria-label="delete"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDeleteSession(session.id);
                  }}
                  size="small"
                >
                  <DeleteIcon />
                </IconButton>
              </ListItemSecondaryAction>
            </ListItem>
          ))
        )}
      </List>
    </Paper>
  );
};

export default CodeSessionList; 