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
import Workers from './pages/Workers';
import Login from './pages/Login';
import ApiKeys from './pages/ApiKeys';
import AdminUsers from './pages/AdminUsers';
import { AuthProvider } from './auth/AuthContext';
import AuthGuard from './auth/AuthGuard';

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
        <AuthProvider>
          <Routes>
            {/* Login lives outside the guard + Layout so an unauthed
                user can reach it without bouncing. */}
            <Route path="/login" element={<Login />} />

            {/* Everything else is gated. If the backend is in strict
                mode (SUPAKILN_ALLOW_ANONYMOUS=false) and there's no
                token, the guard redirects to /login. In anonymous mode
                /auth/me succeeds for the system user and the app
                renders as-is. */}
            <Route
              path="/*"
              element={
                <AuthGuard>
                  <Layout>
                    <Routes>
                      <Route path="/" element={<Editor />} />
                      <Route path="/saved-code" element={<SavedCode />} />
                      <Route path="/containers" element={<RunningContainers />} />
                      <Route path="/scheduler" element={<Scheduler />} />
                      <Route path="/webhooks" element={<WebhookJobs />} />
                      <Route path="/workers" element={<Workers />} />
                      <Route path="/logs" element={<Logs />} />
                      <Route path="/env" element={<EnvironmentVariables />} />
                      <Route path="/keys" element={<ApiKeys />} />
                      <Route path="/admin/users" element={<AdminUsers />} />
                    </Routes>
                  </Layout>
                </AuthGuard>
              }
            />
          </Routes>
        </AuthProvider>
      </Router>
    </ThemeProvider>
  );
}

export default App;
