import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Box, CircularProgress } from '@mui/material';
import { useAuth } from './AuthContext';

/**
 * Wraps the authenticated part of the app.
 *
 * Three states from AuthContext drive three outcomes:
 *
 *   loading === true       → splash spinner (we're probing /auth/me)
 *   authRequired === true  → redirect to /login, remember where we
 *                             came from so login can bounce back
 *   otherwise              → render children; user is either a real
 *                             logged-in user or the anonymous system
 *                             user (SUPAKILN_ALLOW_ANONYMOUS=true)
 */
const AuthGuard: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { loading, authRequired } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <Box
        sx={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <CircularProgress />
      </Box>
    );
  }

  if (authRequired) {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: location.pathname + location.search }}
      />
    );
  }

  return <>{children}</>;
};

export default AuthGuard;
