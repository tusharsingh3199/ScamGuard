import { useEffect, useMemo, useState } from 'react';
import { CircleAlert, Filter, Pause, Play, RotateCcw } from 'lucide-react';
import { getTransactions } from '../api.js';

const money = (amount) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(amount || 0);
const stamp = (value) => value ? new Date(value).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : '—';

export default function LiveMonitor({ metrics }) {
  const [feed, setFeed] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [channel, setChannel] = useState('');
  const [flagged, setFlagged] = useState(false);
  const [cursor, setCursor] = useState(0);
  const [running, setRunning] = useState(false);
  const [speed, setSpeed] = useState(4);
  const [error, setError] = useState('');
  const pageSize = 500;

  useEffect(() => {
    setRunning(false);
    setCursor(0);
    getTransactions({ limit: pageSize, offset: page * pageSize, channel, flagged: flagged || undefined })
      .then((result) => { setFeed(result.items); setTotal(result.total); setError(''); })
      .catch((issue) => setError(issue.message));
  }, [page, channel, flagged]);
  useEffect(() => {
    if (!running) return undefined;
    const timer = window.setInterval(() => setCursor((current) => Math.min(current + speed, feed.length)), 850);
    return () => window.clearInterval(timer);
  }, [running, speed, feed.length]);

  const visible = useMemo(() => feed.slice(0, cursor).slice(-12).reverse(), [feed, cursor]);
  const processed = feed.slice(0, cursor);
  const alerts = processed.filter((row) => row.fraud_score >= 0.5);
  const latest = alerts.at(-1);
  const held = alerts.filter((row) => row.action === 'HOLD' && row.direction === 'debit').reduce((sum, row) => sum + row.amount, 0);

  return <section className="page-stack">
    <div className="control-strip">
      <div className="control-group"><span className="control-caption">REPLAY WINDOW</span><button className="select-control active-select" onClick={() => { setPage(0); setFlagged(false); }}>Full activity</button><button className={`select-control ${flagged ? 'active-select' : ''}`} onClick={() => { setPage(0); setFlagged((value) => !value); }}>Flagged only</button></div>
      <div className="control-group"><label className="control-caption" htmlFor="channel-filter">CHANNEL</label><select id="channel-filter" className="field-select" value={channel} onChange={(event) => { setPage(0); setChannel(event.target.value); }}><option value="">All channels</option><option>UPI</option><option>CARD</option><option>WALLET</option><option>NETBANK</option></select></div>
      <div className="control-group replay-actions"><label className="control-caption" htmlFor="speed">EVENTS / TICK</label><select id="speed" className="field-select compact-select" value={speed} onChange={(event) => setSpeed(Number(event.target.value))}><option value="1">1</option><option value="4">4</option><option value="8">8</option><option value="16">16</option></select><button className="icon-button" title="Reset replay" aria-label="Reset replay" onClick={() => { setRunning(false); setCursor(0); }}><RotateCcw size={16} /></button><button className={`primary-button ${running ? 'pause-button' : ''}`} onClick={() => setRunning((value) => !value)}>{running ? <Pause size={15} /> : <Play size={15} />}{running ? 'Pause' : 'Start replay'}</button></div>
    </div>
    {error && <div className="error-banner"><CircleAlert size={17} /> {error}</div>}
    <div className="stat-grid four-up">
      <article className="stat-panel"><span>EVENTS PROCESSED</span><strong>{processed.length.toLocaleString()}</strong><small>of {total.toLocaleString()} matching events</small></article>
      <article className="stat-panel alert-stat"><span>ALERTS RAISED</span><strong>{alerts.length.toLocaleString()}</strong><small>fraud score 0.50 or above</small></article>
      <article className="stat-panel"><span>AMOUNT HELD</span><strong>{money(held)}</strong><small>debit transactions on hold</small></article>
      <article className="stat-panel"><span>SCORING LATENCY</span><strong>{Number(metrics?.fraud?.avg_latency_ms || 0).toFixed(1)} <em>ms</em></strong><small>offline model benchmark</small></article>
    </div>
    <div className="section-title-row"><div><p className="eyebrow">TRANSACTION STREAM</p><h2>Recent events</h2></div><div className="table-meta"><Filter size={14} /> {channel || 'All channels'} · {flagged ? 'Flagged' : 'All activity'} · Page {page + 1}</div></div>
    <div className="table-shell"><div className="table-scroll"><table><thead><tr><th>TIME</th><th>CUSTOMER</th><th>CHANNEL</th><th>FLOW</th><th>AMOUNT</th><th>PAYEE</th><th>RISK</th><th>DECISION</th></tr></thead><tbody>
      {visible.map((row) => <tr key={row.txn_id} className={row.fraud_score >= 0.5 ? 'flagged-row' : ''}><td className="mono">{stamp(row.timestamp)}</td><td>{row.customer_id}</td><td><span className={`channel-chip channel-${row.channel?.toLowerCase()}`}>{row.channel}</span></td><td>{row.direction === 'debit' ? 'Out' : 'In'}</td><td className="amount-cell">{money(row.amount)}</td><td>{row.payee_id || '—'}</td><td><span className={`risk-value ${row.fraud_score >= 0.5 ? 'risk-high' : ''}`}>{Number(row.fraud_score).toFixed(2)}</span></td><td><span className={`decision-pill decision-${row.action?.toLowerCase().replace('-', '')}`}>{row.action}</span></td></tr>)}
      {!visible.length && <tr><td colSpan="8" className="empty-state">Start replay to inspect scored events in this sample.</td></tr>}
    </tbody></table></div><div className="table-footer"><span>Replay sample · {cursor} events exposed</span><div><button className="text-button" disabled={page === 0} onClick={() => setPage((value) => Math.max(0, value - 1))}>Previous</button><button className="text-button" disabled={(page + 1) * pageSize >= total} onClick={() => setPage((value) => value + 1)}>Next</button></div></div></div>
    {latest && <div className="alert-detail"><span className="alert-icon"><CircleAlert size={19} /></span><div><span className="eyebrow">LATEST FLAGGED EVENT · {latest.scam_type_pred?.replaceAll('_', ' ')}</span><h3>{latest.customer_id} · {latest.channel} · {money(latest.amount)} <span className={`decision-pill decision-${latest.action?.toLowerCase().replace('-', '')}`}>{latest.action}</span></h3><p>{latest.summary || 'No narrative available.'}</p><div className="reason-list">{safeReasons(latest.reasons).map((reason) => <span key={reason}>{reason}</span>)}</div></div></div>}
    <div className="notice-line"><span className="state-dot" /> Simulated replay of previously scored transactions. No live payment decisions are made.</div>
  </section>;
}

function safeReasons(value) {
  try { return value ? JSON.parse(value) : []; } catch { return []; }
}