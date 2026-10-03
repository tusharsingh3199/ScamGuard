import { useEffect, useMemo, useState } from 'react';
import Plot from '../plotly.js';
import { CircleAlert, Search, ShieldCheck, UserRound } from 'lucide-react';
import { getCustomer, getCustomers } from '../api.js';

const plotConfig = { responsive: true, displayModeBar: false };
const plotLayout = { autosize: true, paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: { family: 'DM Sans, sans-serif', color: '#58635f', size: 11 }, margin: { l: 54, r: 16, t: 14, b: 45 }, xaxis: { gridcolor: '#e8ece8' }, yaxis: { gridcolor: '#e8ece8' }, legend: { orientation: 'h', y: 1.14 } };

export default function Customer360({ demoCustomer }) {
  const [customers, setCustomers] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [detail, setDetail] = useState(null);
  const [search, setSearch] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    getCustomers().then((rows) => { setCustomers(rows); setSelectedId(demoCustomer || rows[0]?.customer_id || ''); }).catch((issue) => setError(issue.message));
  }, [demoCustomer]);
  useEffect(() => {
    if (selectedId) getCustomer(selectedId).then(setDetail).catch((issue) => setError(issue.message));
  }, [selectedId]);

  const customer = detail?.customer;
  const borrower = detail?.borrower;
  const transactions = detail?.transactions || [];
  const filteredCustomers = useMemo(() => customers.filter((row) => `${row.name} ${row.customer_id}`.toLowerCase().includes(search.toLowerCase())), [customers, search]);
  const riskTx = transactions.filter((row) => row.fraud_score >= 0.5);
  const topAlert = [...riskTx].sort((a, b) => b.fraud_score - a.fraud_score)[0];
  const repayments = detail?.repayments || [];
  const channelColors = { UPI: '#139b8a', CARD: '#6574bd', WALLET: '#d19a2a', NETBANK: '#de5a43' };
  const regular = transactions.filter((row) => row.fraud_score < 0.5 && row.direction === 'debit');
  const credits = transactions.filter((row) => row.fraud_score < 0.5 && row.direction === 'credit');
  const plotData = [
    ...['UPI', 'CARD', 'WALLET', 'NETBANK'].map((channel) => { const rows = regular.filter((row) => row.channel === channel); return { type: 'scatter', mode: 'markers', name: channel, x: rows.map((row) => row.timestamp), y: rows.map((row) => row.amount), text: rows.map((row) => row.payee_id), marker: { color: channelColors[channel], size: 7, opacity: 0.62 }, hovertemplate: '%{x}<br>₹%{y:,.0f} → %{text}<extra>' + channel + '</extra>' }; }),
    { type: 'scatter', mode: 'markers', name: 'Income / credits', x: credits.map((row) => row.timestamp), y: credits.map((row) => row.amount), marker: { color: '#77847e', symbol: 'triangle-up', size: 9 }, hovertemplate: '%{x}<br>Credit ₹%{y:,.0f}<extra></extra>' },
    { type: 'scatter', mode: 'markers', name: 'Scam alert', x: riskTx.map((row) => row.timestamp), y: riskTx.map((row) => row.amount), text: riskTx.map((row) => `${row.scam_type_pred} · ${Number(row.fraud_score).toFixed(2)}`), marker: { color: '#de5a43', symbol: 'x', size: 12 }, hovertemplate: '%{x}<br>₹%{y:,.0f}<br>%{text}<extra></extra>' },
    { type: 'scatter', mode: 'markers', name: 'Repayment', x: repayments.map((row) => row.due_date), y: repayments.map(() => borrower?.emi || 0), text: repayments.map((row) => `${row.status} · ${row.days_past_due} days past due`), marker: { color: repayments.map((row) => row.status === 'on_time' ? '#139b8a' : row.status === 'late' ? '#d19a2a' : '#de5a43'), symbol: 'diamond', size: 11 }, hovertemplate: '%{x}<br>EMI ₹%{y:,.0f}<br>%{text}<extra></extra>' },
  ];

  return <section className="page-stack">
    {error && <div className="error-banner"><CircleAlert size={17} /> {error}</div>}
    <div className="customer-layout">
      <aside className="customer-picker"><div className="picker-heading"><span>PROFILE DIRECTORY</span><strong>{customers.length} customers</strong></div><label className="search-field"><Search size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Name or customer ID" /></label><div className="customer-list">{filteredCustomers.map((row) => <button className={`customer-option ${selectedId === row.customer_id ? 'selected' : ''}`} key={row.customer_id} onClick={() => setSelectedId(row.customer_id)}><span className="customer-avatar">{row.name?.slice(0, 1)}</span><span className="customer-option-text"><strong>{row.name}</strong><small>{row.customer_id}</small></span><span className={`mini-risk ${row.peak_fraud_risk >= 0.5 ? 'high' : ''}`}>{Number(row.peak_fraud_risk).toFixed(2)}</span></button>)}</div></aside>
      <div className="customer-detail">
        {!customer ? <div className="loading-state">Loading customer profile…</div> : <>
          <div className="profile-banner"><div className="profile-symbol"><UserRound size={25} /></div><div className="profile-copy"><span className="eyebrow">CUSTOMER PROFILE · {customer.customer_id}</span><h2>{customer.name}</h2><p>{customer.age} years · {customer.city} · {customer.occupation}</p></div><div className="profile-income"><span>BASELINE MONTHLY INCOME</span><strong>{money(customer.monthly_income)}</strong><small>Account age {customer.account_age_days} days</small></div></div>
          <div className="stat-grid four-up compact-stats"><article className="stat-panel"><span>PEAK FRAUD RISK</span><strong className={Number(customer.peak_fraud_risk) >= 0.5 ? 'text-coral' : ''}>{Number(customer.peak_fraud_risk || 0).toFixed(2)}</strong><small>transaction history</small></article><article className="stat-panel"><span>REPAYMENT RISK</span><strong>{borrower ? Number(borrower.repayment_risk).toFixed(2) : '—'}</strong><small>{borrower?.risk_band || 'No active loan'}</small></article><article className="stat-panel"><span>OPEN ALERT EVENTS</span><strong>{riskTx.length}</strong><small>score at least 0.50</small></article><article className="stat-panel"><span>OUTSTANDING</span><strong>{borrower ? money(borrower.outstanding) : '—'}</strong><small>{borrower ? `EMI ${money(borrower.emi)}` : 'No active loan'}</small></article></div>
          <div className="explanation-grid"><article className="explanation-panel fraud-explanation"><div className="explanation-heading"><span className="explanation-icon coral"><CircleAlert size={16} /></span><div><span className="eyebrow">FRAUD ASSESSMENT</span><h3>Why activity was flagged</h3></div></div>{topAlert ? <><p className="explanation-summary">{topAlert.summary}</p><div className="reason-list">{safeReasons(topAlert.reasons).map((reason) => <span key={reason}>{reason}</span>)}</div><small className="explanation-meta">{topAlert.scam_type_pred?.replaceAll('_', ' ')} · {new Date(topAlert.timestamp).toLocaleString()} · {topAlert.channel}</small></> : <p className="muted-copy">No suspicious activity in the available transaction history.</p>}</article>
            <article className="explanation-panel loan-explanation"><div className="explanation-heading"><span className="explanation-icon teal"><ShieldCheck size={16} /></span><div><span className="eyebrow">REPAYMENT ASSESSMENT</span><h3>Borrower signals</h3></div></div>{borrower ? <><p className="explanation-summary">{borrower.summary}</p><div className="warning-tags">{(borrower.warnings || '').split(', ').filter(Boolean).map((warning) => <span key={warning}>{warning}</span>)}{!borrower.warnings && <span className="tag-positive">No active warnings</span>}</div><div className="borrower-facts"><span>EMI / income <strong>{percent(borrower.emi_to_income)}</strong></span><span>Income change 60d <strong className={borrower.income_change_60d < 0 ? 'text-coral' : ''}>{percent(borrower.income_change_60d, true)}</strong></span><span>Next payment <strong>{borrower.days_to_next_emi} days</strong></span></div><div className="reason-list">{safeReasons(borrower.reasons).map((reason) => <span key={reason}>{reason}</span>)}</div></> : <p className="muted-copy">No active loan record for this customer.</p>}</article></div>
          <article className="chart-panel customer-timeline"><div className="panel-heading"><div><span className="panel-index">01</span><h3>Combined risk timeline</h3></div><span className="panel-unit">TRANSACTIONS + EMI HISTORY</span></div><Plot data={plotData} layout={{ ...plotLayout, height: 370, yaxis: { ...plotLayout.yaxis, type: 'log', title: 'Amount (INR, log scale)' } }} config={plotConfig} useResizeHandler className="plot" /><div className="timeline-legend"><span><i className="legend-dot legend-channel" />Channel spend</span><span><i className="legend-dot legend-alert" />Flagged transaction</span><span><i className="legend-dot legend-emi" />Repayment status</span></div></article>
        </>}
      </div>
    </div>
  </section>;
}

function safeReasons(value) { try { return value ? JSON.parse(value) : []; } catch { return []; } }
function money(amount) { return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(amount || 0); }
function percent(value, signed = false) { const number = Number(value || 0) * 100; return `${signed && number > 0 ? '+' : ''}${number.toFixed(0)}%`; }