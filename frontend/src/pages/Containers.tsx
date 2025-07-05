import React, { useState } from 'react';
import { Box, Paper, Typography, Dialog, DialogTitle, DialogContent, DialogActions, Button } from '@mui/material';
import CodeSessionList from '../components/CodeSessionList';
import Editor from '@monaco-editor/react';

interface CodeSession {
  id: string;
  name: string;
  code: string;
  packages: string[];
  created_at: string;
  updated_at: string;
}

const CodeSessions: React.FC = () => {
  const [selectedSession, setSelectedSession] = useState<CodeSession | null>(null);
  const [isViewModalOpen, setIsViewModalOpen] = useState(false);

  const handleLoadSession = (session: CodeSession) => {
    setSelectedSession(session);
    setIsViewModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsViewModalOpen(false);
    setSelectedSession(null);
  };

  const handleOpenInEditor = () => {
    // This could navigate to the editor with the session loaded
    // For now, we'll just close the modal
    handleCloseModal();
  };

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Code Sessions
      </Typography>
      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
        View and manage your saved code sessions. Click on any session to preview it or load it in the editor.
      </Typography>
      <CodeSessionList onLoadSession={handleLoadSession} />
      
      <Dialog
        open={isViewModalOpen}
        onClose={handleCloseModal}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle>
          Code Session: {selectedSession?.name}
        </DialogTitle>
        <DialogContent>
          <Box sx={{ mb: 2 }}>
            <Typography variant="subtitle2" gutterBottom>
              Packages:
            </Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
              {selectedSession?.packages.map((pkg, index) => (
                <Paper
                  key={index}
                  sx={{ px: 1, py: 0.5, bgcolor: 'grey.100', fontSize: '0.875rem' }}
                >
                  {pkg}
                </Paper>
              ))}
            </Box>
          </Box>
          <Box sx={{ height: '500px', mt: 2 }}>
            <Editor
              height="100%"
              defaultLanguage="python"
              value={selectedSession?.code || ''}
              theme="vs-dark"
              options={{
                minimap: { enabled: false },
                fontSize: 14,
                readOnly: true,
              }}
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseModal}>Close</Button>
          <Button onClick={handleOpenInEditor} variant="contained">
            Open in Editor
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default CodeSessions; 