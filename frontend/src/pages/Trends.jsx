import { useEffect, useMemo, useState } from 'react';
import Plot from '../plotly.js';
import { ChartNoAxesCombined, CircleAlert } from 'lucide-react';
import { getTrends } from '../api.js';

const chartConfig = { responsive: true, displayModeBar: false };
const chartLayout = { autosize: true, paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: { family: 'DM Sans, sans-serif', color: '#58635f', size: 11 }, margin: { l: 44, r: 16, t: 12, b: 46 }, legend: { orientation: 'h', y: -0.24 }, xaxis: { gridcolor: '#e8ece8', linecolor: '#dce2dd' }, yaxis: { gridcolor: '#e8ece8', linecolor: '#dce2dd' } };
const palette = ['#de5a43', '#139b8a', '#d19a2a', '#6574bd', '#8d6c53', '#6e9d70', '#ad6381'];

export default function Trends() {
  const [scope, setScope] = useState('flagged');
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => { getTrends(scope).then(setData).catch((issue) => setError(issue.message)); }, [scope]);

  const types = useMemo(() => [...new Set((data?.by_day || []).map((row) => row.scam_type))].filter((type) => type !== 'none'), [data]);
  const days = useMemo(() => [...new Set((data?.by_day || []).map((row) => row.day))], [data]);
  const dayTraces = types.map((type, index) => ({ type: 'bar', name: type.replaceAll('_', ' '), x: days, y: days.map((day) => data.by_day.find((row) => row.day === day && row.scam_type === type)?.alerts || 0), marker: { color: palette[index % palette.length] } }));
  const channelTypes = [...new Set((data?.by_channel || []).map((row) => row.scam_type))].filter((type) => type !== 'none');
  const channelTraces = channelTypes.map((type, index) => ({ type: 'bar', name: type.replaceAll('_', ' '), x: ['UPI', 'CARD', 'WALLET', 'NETBANK'], y: ['UPI', 'CARD', 'WALLET', 'NETBANK'].map((channel) => data.by_channel.find((row) => row.channel === channel && row.scam_type === type)?.alerts || 0), marker: { color: palette[index % palette.length] } }));
  const flow = data?.flow || [];
  const flowNodes = [...new Set([...flow.map((row) => row.channel), ...flow.map((row) => row.payee_type), ...flow.map((row) => row.outcome)])];
  const nodeIndex = Object.fromEntries(flowNodes.map((name, index) => [name, index]));
  const edges = [...aggregateEdges(flow, 'channel', 'payee_type'), ...aggregateEdges(flow, 'payee_type', 'outcome')];
  const graph = data?.graph || { nodes: [], edges: [], mules: [], rings: 0 };
  const positions = Object.fromEntries(graph.nodes.map((node) => [node.id, node]));
  const edgeX = graph.edges.flatMap((edge) => [positions[edge.src]?.x, positions[edge.dst]?.x, null]);
  const edgeY = graph.edges.flatMap((edge) => [positions[edge.src]?.y, positions[edge.dst]?.y, null]);

  return <section className="page-stack">
    <div className="control-strip"><div><p className="eyebrow">PATTERN INTELLIGENCE</p><h2>Detection signals</h2></div><div className="segmented-control" aria-label="Trend scope"><button className={scope === 'flagged' ? 'selected' : ''} onClick={() => setScope('flagged')}>Flagged events</button><button className={scope === 'all' ? 'selected' : ''} onClick={() => setScope('all')}>All transactions</button></div></div>
    {error && <div className="error-banner"><CircleAlert size={17} /> {error}</div>}
    <div className="chart-grid">
      <article className="chart-panel chart-wide"><div className="panel-heading"><div><span className="panel-index">01</span><h3>Scam classification over time</h3></div><span className="panel-unit">EVENTS / DAY</span></div><Plot data={dayTraces} layout={{ ...chartLayout, barmode: 'stack', height: 330, xaxis: { ...chartLayout.xaxis, type: 'date' }, yaxis: { ...chartLayout.yaxis, rangemode: 'tozero' } }} config={chartConfig} useResizeHandler className="plot" /></article>
      <article className="chart-panel"><div className="panel-heading"><div><span className="panel-index">02</span><h3>Risky payees</h3></div><span className="panel-unit">TOP 12</span></div><div className="payee-list">{(data?.risky_payees || []).map((payee, index) => <div className="payee-row" key={payee.payee_id}><span className="payee-rank">{String(index + 1).padStart(2, '0')}</span><div className="payee-main"><strong>{payee.payee_id}</strong><span>{payee.category || 'Unclassified'}{payee.mule_flag ? ' · mule flagged' : ''}</span></div><div className="payee-stats"><strong>{Number(payee.alerts).toLocaleString()}</strong><span>{money(payee.amount)}</span></div></div>)}{data && !data.risky_payees.length && <p className="empty-state">No risky payees in this scope.</p>}</div></article>
      <article className="chart-panel"><div className="panel-heading"><div><span className="panel-index">03</span><h3>Scam types by channel</h3></div><span className="panel-unit">CHANNEL</span></div><Plot data={channelTraces} layout={{ ...chartLayout, barmode: 'stack', height: 300, margin: { ...chartLayout.margin, b: 34 }, legend: { orientation: 'h', y: -0.35 } }} config={chartConfig} useResizeHandler className="plot" /></article>
      <article className="chart-panel"><div className="panel-heading"><div><span className="panel-index">04</span><h3>Transaction path</h3></div><span className="panel-unit">CHANNEL → PAYEE → ACTION</span></div><Plot data={[{ type: 'sankey', arrangement: 'snap', node: { pad: 18, thickness: 15, line: { color: '#fff', width: 1 }, label: flowNodes, color: flowNodes.map((_, index) => palette[index % palette.length]) }, link: { source: edges.map((edge) => nodeIndex[edge.source]), target: edges.map((edge) => nodeIndex[edge.target]), value: edges.map((edge) => edge.count), color: 'rgba(19,155,138,.22)' } }]} layout={{ ...chartLayout, height: 300, margin: { l: 8, r: 8, t: 8, b: 8 } }} config={chartConfig} useResizeHandler className="plot" /></article>
      <article className="chart-panel chart-wide"><div className="panel-heading"><div><span className="panel-index">05</span><h3>Mule-ring network</h3></div><span className="panel-unit">FAN-IN → FAN-OUT · 24H</span></div>{graph.nodes.length ? <Plot data={[{ type: 'scatter', mode: 'lines', x: edgeX, y: edgeY, line: { color: '#cbd3ce', width: 1 }, hoverinfo: 'skip', showlegend: false }, ...['sender', 'mule', 'collector'].map((kind) => { const group = graph.nodes.filter((node) => node.kind === kind); return { type: 'scatter', mode: 'markers', name: kind, x: group.map((node) => node.x), y: group.map((node) => node.y), text: group.map((node) => `${node.id}<br>In ${node.in_deg} / Out ${node.out_deg}`), hovertemplate: '%{text}<extra></extra>', marker: { size: kind === 'collector' ? 15 : kind === 'mule' ? 12 : 7, color: kind === 'mule' ? '#de5a43' : kind === 'collector' ? '#d19a2a' : '#91a29a', symbol: kind === 'collector' ? 'diamond' : 'circle', line: { color: '#fff', width: 1 } } }; })]} layout={{ ...chartLayout, height: 390, xaxis: { visible: false }, yaxis: { visible: false, scaleanchor: 'x' }, legend: { orientation: 'h', y: -0.08 }, margin: { l: 12, r: 12, t: 10, b: 28 } }} config={chartConfig} useResizeHandler className="plot" /> : <div className="empty-graph"><ChartNoAxesCombined size={23} /><span>No connected mule rings detected.</span></div>}<div className="chart-footnote">{(graph.mules || []).length} flagged mule accounts · {graph.rings || 0} connected rings. Node size reflects connection count.</div></article>
    </div>
    <div className="notice-line"><span className="state-dot" /> Synthetic scam patterns are injected; displayed metrics are not real-world performance claims.</div>
  </section>;
}

function aggregateEdges(rows, from, to) {
  const edges = new Map();
  rows.forEach((row) => { const key = `${row[from]}\u0000${row[to]}`; edges.set(key, (edges.get(key) || 0) + Number(row.count)); });
  return [...edges].map(([key, count]) => { const [source, target] = key.split('\u0000'); return { source, target, count }; });
}
function money(amount) { return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(amount || 0); }