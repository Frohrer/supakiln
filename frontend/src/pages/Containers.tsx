import React, { useState } from 'react';
import { Box, Paper, Typography, Dialog, DialogTitle, DialogContent, DialogActions, Button } from '@mui/material';
import ContainerList from '../components/ContainerList';
import Editor from '@monaco-editor/react';

interface Container {
  id: string;
  name: string;
  created_at: string;
  code?: string;
  packages?: string[];
}

const Containers: React.FC = () => {
  const [selectedContainer, setSelectedContainer] = useState<Container | null>(null);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [editedCode, setEditedCode] = useState('');

  const handleEditContainer = (container: Container) => {
    setSelectedContainer(container);
    setEditedCode(container.code || '');
    setIsEditModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsEditModalOpen(false);
    setSelectedContainer(null);
  };

  const handleSaveContainer = async () => {
    if (!selectedContainer) return;
    
    try {
      // TODO: Implement save functionality
      handleCloseModal();
    } catch (error) {
      console.error('Error saving container:', error);
    }
  };

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Containers
      </Typography>
      <ContainerList onEditContainer={handleEditContainer} />
      
      <Dialog
        open={isEditModalOpen}
        onClose={handleCloseModal}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle>
          Edit Container: {selectedContainer?.name}
        </DialogTitle>
        <DialogContent>
          <Box sx={{ height: '500px', mt: 2 }}>
            <Editor
              height="100%"
              defaultLanguage="python"
              value={editedCode}
              onChange={(value) => setEditedCode(value || '')}
              theme="vs-dark"
              options={{
                minimap: { enabled: false },
                fontSize: 14,
              }}
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseModal}>Cancel</Button>
          <Button onClick={handleSaveContainer} variant="contained">
            Save Changes
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default Containers; 