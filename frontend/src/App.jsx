import React from 'react';
import { BrowserRouter as Router, Routes, Route, Link, Outlet, useLocation } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Library from './pages/Library';
import Practice from './pages/Practice';
import Results from './pages/Results';
import './index.css';

// Global Layout Wrapper
function Layout() {
  const location = useLocation();

  const isActive = (path) => {
    if (path === '/') return location.pathname === '/';
    return location.pathname.startsWith(path);
  };

  return (
    <div className="app-container">
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

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="library" element={<Library />} />
          <Route path="practice/:id" element={<Practice />} />
          <Route path="results/:jobId" element={<Results />} />
        </Route>
      </Routes>
    </Router>
  );
}

export default App;
