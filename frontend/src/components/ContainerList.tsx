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
} from '@mui/material';
import { Edit as EditIcon, Search as SearchIcon } from '@mui/icons-material';
import api from '../config/api';

interface Container {
  id: string;
  name: string;
  created_at: string;
}

interface ContainerListProps {
  onEditContainer: (container: Container) => void;
}

const ContainerList: React.FC<ContainerListProps> = ({ onEditContainer }) => {
  const [containers, setContainers] = useState<Container[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchContainers();
  }, []);

  const fetchContainers = async () => {
    try {
      const response = await api.get('/containers');
      setContainers(response.data);
      setLoading(false);
    } catch (error) {
      console.error('Error fetching containers:', error);
      setLoading(false);
    }
  };

  const filteredContainers = containers.filter(container =>
    container.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <Paper sx={{ p: 2, height: '100%' }}>
      <Typography variant="h6" gutterBottom>
        Containers
      </Typography>
      <TextField
        fullWidth
        size="small"
        placeholder="Search containers..."
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
            <ListItemText primary="Loading containers..." />
          </ListItem>
        ) : filteredContainers.length === 0 ? (
          <ListItem>
            <ListItemText primary="No containers found" />
          </ListItem>
        ) : (
          filteredContainers.map((container) => (
            <ListItem
              key={container.id}
              secondaryAction={
                <IconButton
                  edge="end"
                  aria-label="edit"
                  onClick={() => onEditContainer(container)}
                >
                  <EditIcon />
                </IconButton>
              }
            >
              <ListItemText
                primary={container.name}
                secondary={`Created: ${new Date(container.created_at).toLocaleString()}`}
              />
            </ListItem>
          ))
        )}
      </List>
    </Paper>
  );
};

export default ContainerList; 