import React from 'react';
import { createBrowserRouter, RouterProvider, Link, Outlet, useLocation, ScrollRestoration } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Library from './pages/Library';
import Practice from './pages/Practice';
import Results from './pages/Results';
import AuthModal from './components/AuthModal';
import './index.css';

// Global Layout Wrapper
function Layout() {
  const location = useLocation();

  const [mousePos, setMousePos] = React.useState({ x: window.innerWidth / 2, y: window.innerHeight / 2 });

  // Auth modal state (mockup — not yet backed by a real auth system).
  const [auth, setAuth] = React.useState({ open: false, mode: 'login' });
  const openAuth = (mode) => setAuth({ open: true, mode });
  const closeAuth = () => setAuth((a) => ({ ...a, open: false }));

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
          <button className="auth-signin-btn" onClick={() => openAuth('login')}>
            Log in
          </button>
          <button className="btn-primary auth-signup-btn" onClick={() => openAuth('register')}>
            Sign up
          </button>
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
        loader: async () => fetch('http://localhost:8000/practices').then(r => r.json())
      },
      { 
        path: "library", 
        element: <Library />,
        loader: async () => fetch('http://localhost:8000/practices').then(r => r.json())
      },
      { 
        path: "practice/:id", 
        element: <Practice />,
        loader: async ({ params }) => fetch(`http://localhost:8000/practices/${params.id}`).then(r => r.json())
      },
      { 
        path: "results/:jobId", 
        element: <Results />,
        loader: async ({ params }) => fetch(`http://localhost:8000/practices/${params.jobId}`).then(r => r.json())
      }
    ]
  }
]);

function App() {
  return <RouterProvider router={router} />;
}

export default App;
