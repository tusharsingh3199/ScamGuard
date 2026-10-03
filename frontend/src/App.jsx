import { Suspense, lazy, useEffect, useState } from 'react';
import { Activity, ChartNoAxesCombined, CircleAlert, Landmark, Moon, ShieldCheck, Sun, UsersRound } from 'lucide-react';
import { getDashboard } from './api.js';
import LiveMonitor from './pages/LiveMonitor.jsx';

const Trends = lazy(() => import('./pages/Trends.jsx'));
const Customer360 = lazy(() => import('./pages/Customer360.jsx'));
const Loans = lazy(() => import('./pages/Loans.jsx'));

const navigation = [
  { id: 'monitor', label: 'Live monitor', icon: Activity },
  { id: 'trends', label: 'Scam trends', icon: ChartNoAxesCombined },
  { id: 'customer', label: 'Customer 360', icon: UsersRound },
  { id: 'loans', label: 'Loans & cases', icon: Landmark },
];
const titles = {
  monitor: ['Transaction monitor', 'Cross-channel activity and alert review'],
  trends: ['Scam trends', 'Patterns across channels, payees and connected accounts'],
  customer: ['Customer 360', 'A joined view of transaction and repayment risk'],
  loans: ['Loans & interventions', 'Borrower health and investigation follow-through'],
};

export default function App() {
  const [page, setPage] = useState('monitor');
  const [theme, setTheme] = useState(() => window.localStorage.getItem('scamguard-theme') || 'light');
  const [dashboard, setDashboard] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => { getDashboard().then(setDashboard).catch((issue) => setError(issue.message)); }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem('scamguard-theme', theme);
  }, [theme]);
  const title = titles[page];

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="#monitor" aria-label="ScamGuard home" onClick={() => setPage('monitor')}><span className="brand-mark"><ShieldCheck size={19} /></span><span><strong>ScamGuard</strong><small>FINANCIAL RISK DESK</small></span></a>
      <div className="nav-label">WORKSPACE</div>
      <nav aria-label="Main navigation">{navigation.map(({ id, label, icon: Icon }) => <button key={id} aria-label={label} title={label} className={`nav-link ${page === id ? 'active' : ''}`} onClick={() => setPage(id)}><Icon size={17} /><span>{label}</span>{page === id && <span className="nav-indicator" />}</button>)}</nav>
      <div className="sidebar-bottom"><div className="system-state"><span className="state-dot" /> Demo systems ready</div><p>Generated data · scored offline</p><div className="sidebar-foot"><span>SCAMGUARD</span><span>v1.0</span></div></div>
    </aside>
    <main className="main-area">
      <header className="topbar"><div className="breadcrumbs"><span>Risk operations</span><span className="crumb-slash">/</span><strong>{title[0]}</strong></div><div className="topbar-right"><span className="environment"><span className="state-dot" /> Synthetic demo</span><span className="topbar-divider" /><span className="operator"><span className="operator-avatar">A</span> Analyst</span><button className="theme-toggle" type="button" aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`} aria-pressed={theme === 'dark'} title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`} onClick={() => setTheme((current) => current === 'dark' ? 'light' : 'dark')}>{theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}</button></div></header>
      <div className="content-area">
        <div className="page-heading"><div><p className="eyebrow">RISK OPERATIONS / {page.toUpperCase()}</p><h1>{title[0]}</h1><p className="page-subtitle">{title[1]}</p></div>{dashboard && <div className="header-stat"><span>EVENTS SCORED</span><strong>{Number(dashboard.metrics?.data?.transactions || 0).toLocaleString()}</strong></div>}</div>
        {error && <div className="error-banner"><CircleAlert size={17} /> {error}. Start the API server and refresh.</div>}
        <Suspense fallback={<div className="loading-state">Loading workspace…</div>}>
          {page === 'monitor' && <LiveMonitor metrics={dashboard?.metrics} />}
          {page === 'trends' && <Trends />}
          {page === 'customer' && <Customer360 demoCustomer={dashboard?.meta?.demo_customer} />}
          {page === 'loans' && <Loans />}
        </Suspense>
        <footer className="content-footer"><span>SCAMGUARD RISK SYSTEM</span><span><span className="state-dot" /> SIMULATED STREAM · NOT LIVE PROCESSING</span></footer>
      </div>
    </main>
  </div>;
}