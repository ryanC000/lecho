import React from 'react';
import { createBrowserRouter, RouterProvider, Link, Outlet, useLocation, ScrollRestoration } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Library from './pages/Library';
import Practice from './pages/Practice';
import Results from './pages/Results';
import AuthModal from './components/AuthModal';
import { isLoggedIn, clearToken, apiGet } from './utils/auth';
import './index.css';

// Global Layout Wrapper
function Layout() {
  const location = useLocation();

  const [mousePos, setMousePos] = React.useState({ x: window.innerWidth / 2, y: window.innerHeight / 2 });

  // Auth modal state.
  const [auth, setAuth] = React.useState({ open: false, mode: 'login' });
  const openAuth = (mode) => setAuth({ open: true, mode });
  const closeAuth = () => setAuth((a) => ({ ...a, open: false }));

  // Track login state; utils/auth dispatches 'lecho-auth-changed' on login/logout.
  const [loggedIn, setLoggedIn] = React.useState(isLoggedIn());
  React.useEffect(() => {
    const sync = () => setLoggedIn(isLoggedIn());
    window.addEventListener('lecho-auth-changed', sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener('lecho-auth-changed', sync);
      window.removeEventListener('storage', sync);
    };
  }, []);

  const handleMouseMove = (e) => {
    setMousePos({ x: e.clientX, y: e.clientY });
  };

  const isActive = (path) => {
    if (path === '/') return location.pathname === '/';
    return location.pathname.startsWith(path);
  };

  return (
    <div 
      className="app-container"
      onMouseMove={handleMouseMove}
      style={{
        '--mouse-x': `${mousePos.x}px`,
        '--mouse-y': `${mousePos.y}px`
      }}
    >
      <header className="navbar">
        <Link to="/" className="logo-link">
          <h1 className="hand-text" style={{ fontSize: '1.6rem' }}>L'Écho</h1>
        </Link>
        <div className="nav-links">
          <Link to="/" className={isActive('/') && !isActive('/library') ? 'active' : ''}>
            Dashboard
          </Link>
          <Link to="/library" className={isActive('/library') ? 'active' : ''}>
            Library
          </Link>
          <Link to="#" className="">
            Settings
          </Link>
        </div>
        <div className="auth-actions">
          {loggedIn ? (
            <button className="auth-signin-btn" onClick={() => clearToken()}>
              Log out
            </button>
          ) : (
            <>
              <button className="auth-signin-btn" onClick={() => openAuth('login')}>
                Log in
              </button>
              <button className="btn-primary auth-signup-btn" onClick={() => openAuth('register')}>
                Sign up
              </button>
            </>
          )}
        </div>
      </header>

      <main className="content">
        <ScrollRestoration />
        <Outlet />
      </main>

      <AuthModal
        open={auth.open}
        mode={auth.mode}
        onClose={closeAuth}
        onSwitchMode={(mode) => setAuth({ open: true, mode })}
      />
    </div>
  );
}

const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { 
        index: true, 
        element: <Dashboard />,
        loader: async () => apiGet('/practices')
      },
      {
        path: "library",
        element: <Library />,
        loader: async () => apiGet('/practices')
      },
      {
        path: "practice/:id",
        element: <Practice />,
        loader: async ({ params }) => apiGet(`/practices/${params.id}`)
      },
      {
        // No loader: the job is genuinely async, so Results fetches GET /jobs/:jobId
        // itself and polls until the worker finishes.
        path: "results/:jobId",
        element: <Results />
      }
    ]
  }
]);

function App() {
  return <RouterProvider router={router} />;
}

export default App;
