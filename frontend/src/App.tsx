import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { ThemeProvider, CssBaseline } from '@mui/material';
import { createTheme } from '@mui/material/styles';
import Layout from './components/Layout';
import Editor from './pages/Editor';
import Scheduler from './pages/Scheduler';
import WebhookJobs from './pages/WebhookJobs';
import Logs from './pages/Logs';
import SavedCode from './pages/Containers';
import RunningContainers from './pages/RunningContainers';
import EnvironmentVariables from './pages/EnvironmentVariables';

const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#90caf9',
    },
    secondary: {
      main: '#f48fb1',
    },
  },
});

function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Router>
        <Layout>
          <Routes>
            <Route path="/" element={<Editor />} />
            <Route path="/saved-code" element={<SavedCode />} />
            <Route path="/containers" element={<RunningContainers />} />
            <Route path="/scheduler" element={<Scheduler />} />
            <Route path="/webhooks" element={<WebhookJobs />} />
            <Route path="/logs" element={<Logs />} />
            <Route path="/env" element={<EnvironmentVariables />} />
          </Routes>
        </Layout>
      </Router>
    </ThemeProvider>
  );
}

export default App; 