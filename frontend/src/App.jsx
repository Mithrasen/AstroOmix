import { BrowserRouter, NavLink, Navigate, Route, Routes } from 'react-router-dom'
import ABTesting from './pages/ABTesting'
import Forecasting from './pages/Forecasting'
import Integration from './pages/Integration'
import Methods from './pages/Methods'
import StudyExplorer from './pages/StudyExplorer'
import './App.css'

const PAGES = [
  { path: '/studies', label: 'Study Explorer', element: <StudyExplorer /> },
  { path: '/abtest', label: 'A/B Testing', element: <ABTesting /> },
  { path: '/forecasting', label: 'Forecasting', element: <Forecasting /> },
  { path: '/integration', label: 'Integration', element: <Integration /> },
  { path: '/methods', label: 'Methods', element: <Methods /> },
]

export default function App() {
  return (
    <BrowserRouter>
      <div className="shell">
        <header>
          <h1>
            AstroOmix <span className="subtitle">space biology, two ways</span>
          </h1>
          <nav>
            {PAGES.map((page) => (
              <NavLink key={page.path} to={page.path}>
                {page.label}
              </NavLink>
            ))}
          </nav>
        </header>
        <main>
          <Routes>
            <Route path="/" element={<Navigate to="/abtest" replace />} />
            {PAGES.map((page) => (
              <Route key={page.path} path={page.path} element={page.element} />
            ))}
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
