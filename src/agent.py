"""Analyst copilot (offline, deterministic).

Stands in for the 'AI agent + web search' box of the architecture slide: it turns a case into a
narrative, next-best-actions and a scam playbook entry. It makes NO network calls. A live LLM /
web-search agent (LangChain / LangGraph) is a roadmap item - plug it in behind `analyst_brief`.
"""
import json

PLAYBOOK = {
    "impersonation": ("Fraudster poses as bank/police/support and gets the victim to install a remote-access app or share OTPs.",
                      ["Hold the transfer and call the customer on the registered number", "Block the remote-access session / revoke device",
                       "Freeze the beneficiary and file a mule-account report"]),
    "phishing": ("Credentials stolen through a fake link; attacker logs in from a new device and drains funds quickly.",
                 ["Force password/PIN reset and de-register new device", "Reverse pending transfers", "Check other customers on the same device"]),
    "fake_refund": ("Victim is asked to 'approve' a UPI collect request to receive a refund - money actually leaves the account.",
                    ["Decline the pending collect request", "Educate the customer: refunds never need a PIN", "Flag the requesting VPA"]),
    "investment_scam": ("Escalating transfers to a fake trading/investment merchant promising returns.",
                        ["Pause further transfers to the merchant", "Counsellor call to explain the pattern", "Report the merchant"]),
    "mule_account": ("Account receives money from many senders and cashes it out within hours - part of a laundering ring.",
                     ["Freeze outward transfers", "Review linked senders and collectors in the ring graph", "File an STR with compliance"]),
    "payment_request": ("Urgent KYC/verification message pushes the victim to pay a 'fee' via collect request.",
                        ["Decline the collect request", "Send an awareness SMS", "Block the requesting VPA"]),
    "cross_channel": ("Money is hopped across card, wallet, UPI and netbanking within minutes to evade single-channel limits.",
                      ["Hold the latest hop", "Trace the chain to the final beneficiary", "Step-up authenticate all channels"]),
    "unknown_anomaly": ("Behaviour is statistically unusual but matches no known pattern - possible emerging scam.",
                        ["Manual review by analyst", "If confirmed, label it to retrain the models", "Add a new rule"]),
    "High": ("Borrower shows multiple distress signals (falling income, late EMIs, rising EMI burden).",
             ["Proactive counsellor call before the next EMI", "Offer tenure extension / reduced EMI", "Pause collection calls until contacted"]),
    "Medium": ("Early signs of strain - still recoverable with a light-touch nudge.",
               ["Send EMI reminder 3 days before due date", "Offer auto-debit setup", "Re-score after next payment"]),
}


def analyst_brief(case: dict) -> str:
    reasons = json.loads(case["reasons"]) if case.get("reasons") else []
    what, steps = PLAYBOOK.get(case["category"], ("", []))
    kind = "fraud alert" if case["type"] == "fraud" else "loan early-warning"
    txt = f"**{case['customer_name']}** - {kind}, score **{case['risk_score']:.2f}**. {what}\n\n"
    if reasons:
        txt += "**Why it was flagged:** " + "; ".join(r.split(" (+")[0] for r in reasons[:3]) + ".\n\n"
    if steps:
        txt += "**Suggested next steps:**\n" + "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps))
    return txt
