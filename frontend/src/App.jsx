import React from 'react';
import { createBrowserRouter, RouterProvider, Link, Outlet, useLocation } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Library from './pages/Library';
import Practice from './pages/Practice';
import Results from './pages/Results';
import './index.css';

// Global Layout Wrapper
function Layout() {
  const location = useLocation();

  React.useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);

  const [mousePos, setMousePos] = React.useState({ x: window.innerWidth / 2, y: window.innerHeight / 2 });

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
        <div className="user-profile">E</div>
      </header>

      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}

const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: "library", element: <Library /> },
      { path: "practice/:id", element: <Practice /> },
      { path: "results/:jobId", element: <Results /> }
    ]
  }
]);

function App() {
  return <RouterProvider router={router} />;
}

export default App;
