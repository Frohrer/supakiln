import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  AppBar,
  Toolbar,
  Typography,
  Container,
  Box,
  Button,
  IconButton,
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Divider,
  Tooltip,
  Chip,
} from '@mui/material';
import {
  Menu as MenuIcon,
  Logout as LogoutIcon,
} from '@mui/icons-material';
import { useAuth } from '../auth/AuthContext';

interface LayoutProps {
  children: React.ReactNode;
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const [drawerOpen, setDrawerOpen] = useState(false);

  // System user (id=1) is the anonymous-fallback identity; a real
  // logged-in user has id >= 2. Reflect that in the UI so operators can
  // tell at a glance whether they're authenticated or riding on the
  // anonymous-mode convenience.
  const isAnonymous = !user || user.id === 1;

  const handleLogout = async () => {
    await logout();
    // After logout, the guard decides whether to show login or keep
    // anonymous — we don't hardcode a destination here.
    navigate('/');
  };

  // Nav: hide auth-gated items for anonymous users, hide admin items
  // unless the caller is admin. Keeps the drawer tidy for the common
  // case.
  const navItems = [
    { path: '/', label: 'Editor' },
    { path: '/saved-code', label: 'Saved Code' },
    { path: '/containers', label: 'Running Containers' },
    { path: '/scheduler', label: 'Scheduler' },
    { path: '/webhooks', label: 'Webhooks' },
    { path: '/workers', label: 'Workers' },
    { path: '/logs', label: 'Logs' },
    { path: '/env', label: 'Environment Variables' },
    ...(!isAnonymous ? [{ path: '/keys', label: 'API Keys' }] : []),
    ...(user?.is_admin ? [{ path: '/admin/users', label: 'Admin: Users' }] : []),
  ];

  const handleDrawerToggle = () => {
    setDrawerOpen(!drawerOpen);
  };

  const handleNavigate = (path: string) => {
    navigate(path);
    setDrawerOpen(false);
  };

  const drawer = (
    <Box sx={{ width: 250 }} role="presentation">
      <Box sx={{ p: 2 }}>
        <Typography variant="h6" component="div">
          Navigation
        </Typography>
      </Box>
      <Divider />
      <List>
        {navItems.map((item) => (
          <ListItem key={item.path} disablePadding>
            <ListItemButton
              onClick={() => handleNavigate(item.path)}
              selected={location.pathname === item.path}
              sx={{
                '&.Mui-selected': {
                  backgroundColor: 'primary.main',
                  color: 'primary.contrastText',
                  '&:hover': {
                    backgroundColor: 'primary.dark',
                  },
                },
              }}
            >
              <ListItemText primary={item.label} />
            </ListItemButton>
          </ListItem>
        ))}
      </List>
    </Box>
  );

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <AppBar position="static" sx={{ height: 48 }}>
        <Toolbar sx={{ minHeight: '48px !important', px: 2 }}>
          <IconButton
            size="small"
            edge="start"
            color="inherit"
            aria-label="menu"
            onClick={handleDrawerToggle}
            sx={{ mr: 1 }}
          >
            <MenuIcon />
          </IconButton>
          <Typography variant="h6" component="div" sx={{ flexGrow: 1, fontSize: '1.1rem' }}>
            Python Code Execution Engine
          </Typography>

          {user && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Tooltip
                title={
                  isAnonymous
                    ? 'Running as the system user (anonymous mode). ' +
                      'Sign in to get your own isolated containers.'
                    : user.is_admin
                      ? 'Signed in as admin'
                      : 'Signed in'
                }
              >
                <Chip
                  size="small"
                  label={isAnonymous ? 'anonymous' : user.email}
                  color={isAnonymous ? 'default' : user.is_admin ? 'secondary' : 'primary'}
                  variant={isAnonymous ? 'outlined' : 'filled'}
                />
              </Tooltip>
              {isAnonymous ? (
                <Button
                  size="small"
                  color="inherit"
                  onClick={() => navigate('/login')}
                >
                  Sign in
                </Button>
              ) : (
                <Tooltip title="Sign out">
                  <IconButton
                    size="small"
                    color="inherit"
                    onClick={handleLogout}
                    aria-label="sign out"
                  >
                    <LogoutIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              )}
            </Box>
          )}
        </Toolbar>
      </AppBar>
      
      <Drawer
        anchor="left"
        open={drawerOpen}
        onClose={handleDrawerToggle}
        ModalProps={{
          keepMounted: true, // Better open performance on mobile.
        }}
      >
        {drawer}
      </Drawer>
      
      <Container component="main" maxWidth={false} sx={{ mt: 1, mb: 2, flex: 1 }}>
        {children}
      </Container>
    </Box>
  );
};

export default Layout; 