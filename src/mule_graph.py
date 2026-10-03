"""Phase 3c - Mule-ring detection with networkx: fan-in (many senders) followed by fan-out (rapid
cash-out) within 24h. Returns a JSON-serialisable node/edge set for the dashboard."""
import networkx as nx
import numpy as np
import pandas as pd


def detect_mules(u: pd.DataFrame, min_senders=6, window_h=24, outflow_share=.5):
    cr = u[(u.direction == "credit") & (u.payee_type != "salary")]
    flagged = {}
    for c, g in cr.groupby("customer_id"):
        g = g.sort_values("timestamp")
        t = g.timestamp.to_numpy()
        for i in range(len(g)):
            w = g[(t >= t[i]) & (t <= t[i] + np.timedelta64(window_h, "h"))]
            if w.payee_id.nunique() >= min_senders:
                start, end, tot = w.timestamp.min(), w.timestamp.max(), w.amount.sum()
                outs = u[(u.customer_id == c) & (u.direction == "debit") & (u.timestamp > end) &
                         (u.timestamp <= end + pd.Timedelta(hours=window_h))]
                if outs.amount.sum() >= outflow_share * tot:
                    flagged[c] = dict(senders=list(w.payee_id.unique()), inflow=float(tot), outs=outs, start=start)
                    break
    G = nx.DiGraph()
    for c, info in flagged.items():
        G.add_node(c, kind="mule")
        for s in info["senders"]:
            G.add_node(s, kind="sender")
            G.add_edge(s, c, amount=float(cr[(cr.customer_id == c) & (cr.payee_id == s)].amount.sum()))
        for p, a in info["outs"].groupby("payee_id").amount.sum().items():
            G.add_node(p, kind="collector")
            G.add_edge(c, p, amount=float(a))
    if len(G) == 0:
        return dict(nodes=[], edges=[], mules=[], rings=0)
    pos = nx.spring_layout(G, seed=42, k=.35)
    rings = [sorted(cc) for cc in nx.weakly_connected_components(G)]
    nodes = [dict(id=n, kind=G.nodes[n]["kind"], x=float(pos[n][0]), y=float(pos[n][1]),
                  in_deg=int(G.in_degree(n)), out_deg=int(G.out_degree(n))) for n in G]
    edges = [dict(src=a, dst=b, amount=d["amount"]) for a, b, d in G.edges(data=True)]
    return dict(nodes=nodes, edges=edges, mules=sorted(flagged), rings=len(rings),
                ring_sizes=sorted([sum(1 for n in r if G.nodes[n]["kind"] == "mule") for r in rings], reverse=True))
