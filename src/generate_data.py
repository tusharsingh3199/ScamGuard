"""Phase 1 - Synthetic multi-channel data (UPI / Card / Wallet / NetBanking), loans, income,
injected scam patterns, hard negatives (legit look-alikes) and stressed borrowers.

Run:  python -m src.generate_data
All randomness is seeded (42) so results are reproducible.
"""
import json
import os
import sqlite3

import numpy as np
import pandas as pd
from faker import Faker

SEED = 42
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
START = pd.Timestamp("2026-07-01")
DAYS = 75
TODAY = START + pd.Timedelta(days=DAYS)          # "now" for the loan engine
N_CUST = 1000
MIN = pd.Timedelta(minutes=1)

# category: (mcc, amount factor vs customer's average, sampling weight)
CATS = {"grocery": ("5411", .6, 20), "food": ("5812", .3, 20), "utilities": ("4900", 1.2, 8),
        "fuel": ("5541", .9, 8), "shopping": ("5311", 1.4, 12), "travel": ("4722", 2.0, 5),
        "entertainment": ("7832", .4, 6), "p2p": ("6012", .8, 14), "healthcare": ("8011", 1.0, 4),
        "telecom": ("4814", .3, 5), "rent": ("6513", 3.0, 3)}
MCC = {k: v[0] for k, v in CATS.items()} | {"wallet_topup": "6540", "investment": "6211", "salary": "6012"}
REMARKS = ["dinner", "rent", "groceries", "thanks", "split bill", "movie", "gift", "", "", "fuel", "recharge", "lunch"]
HP = np.array([1, 1, .5, .3, .3, .5, 1.5, 3, 5, 6, 6, 6, 6, 6, 6, 6, 6, 7, 8, 8, 7, 5, 3, 2], float)
HP /= HP.sum()   # daytime-heavy hour-of-day distribution


def generate(n_cust=N_CUST, seed=SEED, verbose=True):
    rng = np.random.default_rng(seed)
    Faker.seed(seed)
    fake = Faker("en_IN")
    payees, pcat, devs = [], {}, {}

    # ---------------------------------------------------------------- helpers
    def add_payee(cat, age, risk, is_mule=0, prefix="P", pid=None):
        pid = pid or f"{prefix}{len(payees) + 1:05d}"
        payees.append(dict(payee_id=pid, category=cat, age_days=int(age),
                           risk_score=round(float(risk), 3), is_mule=is_mule))
        pcat[pid] = cat
        return pid

    def add_device(cid, first_seen, remote=0, emu=0, did=None):
        did = did or f"D{len(devs) + 1:05d}"
        if did in devs:
            devs[did]["first_seen"] = min(devs[did]["first_seen"], first_seen)
        else:
            devs[did] = dict(device_id=did, customer_id=cid, first_seen=first_seen,
                             is_remote_access_app=remote, is_emulator=emu)
        return did

    def scam_payee(cat):   # mostly brand-new, high-risk accounts; 15% are older compromised accounts
        if rng.random() < .15:
            return add_payee(cat, rng.integers(60, 400), rng.beta(3, 5))
        return add_payee(cat, rng.integers(1, 31), rng.beta(4, 4))

    def when(lo, hi, hours=None):
        d = int(rng.integers(lo, hi))
        h = int(rng.choice(hours)) if hours is not None else int(rng.choice(24, p=HP))
        return START + pd.Timedelta(days=d, hours=h, minutes=int(rng.integers(60)), seconds=int(rng.integers(60)))

    # ---------------------------------------------------------------- payees
    cats = list(CATS)
    w = np.array([CATS[c][2] for c in cats], float)
    w /= w.sum()
    legit = [add_payee(cats[rng.choice(len(cats), p=w)], rng.integers(200, 3000), rng.beta(2, 12)) for _ in range(400)]
    wallet_prv = add_payee("wallet_topup", 2000, .05, pid="WALLET_PRV")
    employers = [add_payee("salary", 3000, .02, prefix="E") for _ in range(40)]
    collectors = [add_payee("p2p", rng.integers(5, 40), rng.beta(5, 3), is_mule=1, prefix="M") for _ in range(5)]

    # ---------------------------------------------------------------- customers
    cids = [f"C{i + 1:04d}" for i in range(n_cust)]
    RAM = f"C{n_cust + 1:04d}"                       # demo customer "Ramesh"
    allc = cids + [RAM]
    inc0 = dict(zip(cids, np.clip(rng.lognormal(np.log(38000), .5, n_cust), 12000, 250000).round(-2)))
    inc0[RAM] = 40000.0
    avg = {c: inc0[c] * .0625 * rng.lognormal(0, .2) for c in cids}
    avg[RAM] = 2500.0
    cities = ["Delhi", "Mumbai", "Bengaluru", "Pune", "Chennai", "Hyderabad", "Kolkata", "Jaipur", "Lucknow", "Ahmedabad"]
    occs = ["Salaried", "Salaried", "Salaried", "Self-employed", "Gig worker", "Teacher", "Engineer", "Shopkeeper"]
    cust = [dict(customer_id=c, name=("Ramesh Kumar" if c == RAM else fake.name()),
                 age=int(rng.integers(21, 66)), city=str(rng.choice(cities)), occupation=str(rng.choice(occs)),
                 monthly_income=inc0[c], account_age_days=int(rng.integers(200, 4000)),
                 phone=f"9{rng.integers(10 ** 8, 10 ** 9)}") for c in allc]
    ids = {c: (f"{c.lower()}@bank", f"CARD{c[1:]}", f"W{c[1:]}", f"AC{c[1:]}{rng.integers(1000, 9999)}") for c in allc}
    idmap = pd.DataFrame([dict(customer_id=c, upi_vpa=v[0], card_id=v[1], wallet_id=v[2], account_no=v[3])
                          for c, v in ids.items()])

    cdev, regular, employer = {}, {}, {}
    for c in allc:
        cdev[c] = [add_device(c, START - pd.Timedelta(days=int(rng.integers(30, 900))))]
        if c != RAM and rng.random() < .3:
            cdev[c].append(add_device(c, START - pd.Timedelta(days=int(rng.integers(30, 900)))))
        regular[c] = list(rng.choice(legit, 10, replace=False))
        employer[c] = employers[int(rng.integers(len(employers)))]

    def primary(c):
        return cdev[c][int(rng.random() < .3 and len(cdev[c]) > 1)]

    # ---------------------------------------------------------------- loans / stress groups
    has_loan = {c: bool(rng.random() < .65) for c in cids}
    has_loan[RAM] = True
    group = {}
    for c in cids:
        if has_loan[c] and rng.random() < .12:
            group[c] = "stressed"
        elif rng.random() < .05:
            group[c] = "dip"                         # one-off income dip, NOT really stressed (noise)
        else:
            group[c] = "normal"
    group[RAM] = "stressed"
    incpath = {}
    for c in allc:
        if group[c] == "stressed":
            s = rng.uniform(.2, .4)
            p = [1, 1 - s / 2, 1 - s]
        elif group[c] == "dip":
            p = [1, 1, 1 - rng.uniform(.15, .3)]
        else:
            p = [1, 1, 1]
        incpath[c] = [round(inc0[c] * x * (1 + rng.normal(0, .015)), 0) for x in p]
    incpath[RAM] = [40000.0, 34000.0, 28000.0]       # salary falls 40k -> 28k

    loans, reps, loan_lab, outs = [], [], [], {}
    for c in allc:
        if not has_loan[c]:
            continue
        g = group[c]
        lid = f"L{len(loans) + 1:04d}"
        rate = float(rng.uniform(9, 18))
        n_rem = int(rng.integers(12, 60))
        emi = (incpath[c][2] * rng.uniform(.33, .46)) if g == "stressed" else inc0[c] * rng.uniform(.10, .25)
        r = rate / 1200
        out = emi * (1 - (1 + r) ** -n_rem) / r * rng.uniform(.95, 1.05)
        if c == RAM:
            emi, out, n_rem, rate = 9900.0, 165000.0, 24, 14.0
        outs[c] = round(out, 0)
        nxt = TODAY + pd.Timedelta(days=20 if c == RAM else int(rng.integers(1, 29)))
        loans.append(dict(loan_id=lid, customer_id=c, principal=round(out * rng.uniform(1.1, 1.6), 0) if c != RAM else 200000.0,
                          outstanding=outs[c], emi=round(emi, 0), tenure=n_rem, due_day=nxt.day,
                          interest_rate=round(rate, 1), next_due_date=str(nxt.date())))
        if g == "stressed":
            nb = int(rng.choice([1, 2, 3, 4], p=[.35, .3, .2, .15]))
            bad = [1] * nb + [0] * (4 - nb)
        else:
            bad = [0] * 4
            if rng.random() < .08:
                bad[int(rng.integers(0, 4))] = 1
        if c == RAM:
            bad = [1, 1, 0, 0]
        for k in range(4):                           # k=0 is the most recent EMI
            d = nxt - pd.Timedelta(days=30 * (k + 1))
            maxd = (TODAY - d).days
            if not bad[k]:
                st_, dpd, paid = "on_time", 0, d - pd.Timedelta(days=int(rng.integers(0, 3)))
            elif c == RAM:
                st_, dpd = "late", {0: 6, 1: 3}[k]
                paid = d + pd.Timedelta(days=dpd)
            elif g == "stressed" and k == 0 and rng.random() < .2:
                st_, dpd, paid = "missed", maxd, None
            else:
                dpd = int(min(rng.integers(2, 26) if g == "stressed" else rng.integers(1, 6), maxd))
                st_, paid = "late", d + pd.Timedelta(days=dpd)
            reps.append(dict(loan_id=lid, due_date=str(d.date()), paid_date=str(paid.date()) if paid is not None else None,
                             status=st_, days_past_due=dpd))
        y = int(rng.random() < {"stressed": .75, "dip": .05, "normal": .03}[g]) if c != RAM else 1
        loan_lab.append(dict(loan_id=lid, customer_id=c, default_within_90d=y, stress_group=g))

    ie = []
    for c in allc:
        bs, other = inc0[c] * rng.uniform(.5, .75), inc0[c] * rng.uniform(0, 3)
        for k in range(3):
            inc = incpath[c][k]
            if group[c] == "stressed":
                spend, ca, gr = bs * (1 + rng.normal(0, .02)), inc0[c] * [0, .03, .08][k] * rng.uniform(.8, 1.2), [1, 1.1, 1.25][k]
            else:
                spend = bs * inc / inc0[c] * (1 + rng.normal(0, .03))
                ca, gr = inc0[c] * rng.uniform(0, .02) * (rng.random() < .3), 1
            ie.append(dict(customer_id=c, month=str((START + pd.Timedelta(days=30 * k)).date()), income=round(inc, 0),
                           spend=round(spend, 0), cash_advance=round(ca, 0), total_debt=round(outs.get(c, 0) + other * gr, 0)))

    # ---------------------------------------------------------------- transaction writer
    rows = {k: [] for k in ("UPI", "CARD", "WALLET", "NB")}
    labels, ctr = [], [0]
    ifsc = ["HDFC0001234", "SBIN0004321", "ICIC0005678", "UTIB0000789"]

    def tx(ch, c, ts, amt, payee, dev=None, dr="debit", note="", collect=0, wtype="merchant", fraud=0, stype="none"):
        ctr[0] += 1
        n = ctr[0]
        vpa, card, wal, acc = ids[c]
        t, amt = str(pd.Timestamp(ts)), round(float(amt), 2)
        dev = dev or primary(c)
        if ch == "UPI":
            tid = f"UPI{n:07d}"
            rows["UPI"].append(dict(upi_ref=tid, vpa=vpa, payee_vpa=payee.lower() + "@upi", amt=amt, remark=note,
                                    collect_flag=collect, dr_cr=dr, time=t, dev=dev))
        elif ch == "CARD":
            tid = f"CRD{n:07d}"
            rows["CARD"].append(dict(auth_id=tid, card_id=card, merchant_id=payee, mcc=MCC.get(pcat[payee], "6012"), amt=amt,
                                     country="IN", time=t, terminal="ONLINE" if rng.random() < .5 else f"POS{rng.integers(1000, 9999)}"))
        elif ch == "WALLET":
            tid = f"WLT{n:07d}"
            rows["WALLET"].append(dict(wallet_txn_id=tid, wallet_id=wal, type=wtype, counterparty=payee, amt=amt,
                                       dr_cr=dr, time=t, app_dev=dev))
        else:
            tid = f"NB{n:08d}"
            rows["NB"].append(dict(ref_no=tid, account_no=acc, beneficiary_id=payee, ifsc=str(rng.choice(ifsc)), amt=amt,
                                   dr_cr=dr, time=t, app_dev=dev))
        labels.append((tid, fraud, stype))

    # ---------------------------------------------------------------- normal behaviour
    for c in allc:
        n = int(rng.poisson(50 * min(max(rng.lognormal(0, .3), .4), 2.2)))
        for _ in range(n):
            ts = when(0, DAYS)
            ch = str(rng.choice(["UPI", "CARD", "WALLET", "NB"], p=[.55, .25, .1, .1]))
            pay = regular[c][int(rng.integers(10))] if rng.random() < .85 else legit[int(rng.integers(len(legit)))]
            cat = pcat[pay]
            amt = rng.lognormal(np.log(avg[c] * CATS[cat][1]), .6)
            if ch == "WALLET":
                if rng.random() < .3:
                    tx("WALLET", c, ts, avg[c] * rng.uniform(.5, 2), wallet_prv, wtype="topup")
                else:
                    tx("WALLET", c, ts, amt, pay, wtype="transfer" if cat == "p2p" else "merchant")
            else:
                note = str(rng.choice(REMARKS)) if ch == "UPI" else ""
                tx(ch, c, ts, amt, pay, note=note)
        for k, off in enumerate((0, 30, 60)):   # salary credits follow the (possibly falling) income path
            ts = START + pd.Timedelta(days=off + int(rng.integers(0, 3)), hours=9, minutes=int(rng.integers(60)))
            tx("NB", c, ts, incpath[c][k], employer[c], dr="credit", note="SALARY")

    # ---------------------------------------------------------------- hard negatives (legit look-alikes)
    def pick():
        return cids[int(rng.integers(n_cust))]
    for _ in range(150):      # legit big purchase / deposit to a NEW but established payee
        c = pick()
        p = add_payee(str(rng.choice(["rent", "shopping", "travel"])), rng.integers(300, 2000), rng.beta(2, 12))
        tx(str(rng.choice(["NB", "UPI", "CARD"])), c, when(3, 74, list(range(10, 20))), avg[c] * rng.uniform(4, 10), p)
    for _ in range(60):       # legit phone change: new device, normal spending
        c = pick()
        t0 = when(3, 73)
        d = add_device(c, t0 - 5 * MIN)
        for j in range(3):
            tx("UPI", c, t0 + MIN * int(rng.integers(1, 55)), rng.lognormal(np.log(avg[c] * .5), .5),
               regular[c][int(rng.integers(10))], dev=d, note=str(rng.choice(REMARKS)))
    for _ in range(40):       # late-night food orders
        c = pick()
        tx(str(rng.choice(["CARD", "UPI"])), c, when(0, 74, [23, 0, 1, 2]), avg[c] * rng.uniform(.2, .6),
           next((p for p in regular[c] if pcat[p] in ("food", "grocery")), regular[c][0]))
    for _ in range(30):       # legit collect request from a known payee
        c = pick()
        tx("UPI", c, when(0, 74), avg[c] * rng.uniform(.5, 1.5), regular[c][int(rng.integers(10))], note="monthly split", collect=1)
    for _ in range(100):      # legit refund credits from known merchants
        c = pick()
        tx("UPI", c, when(0, 74), avg[c] * rng.uniform(.3, 1.5), regular[c][int(rng.integers(10))], dr="credit", note="refund")

    # ---------------------------------------------------------------- injected scams
    pool_dev = [f"DX{i:03d}" for i in range(8)]     # attacker devices re-used across victims
    def attacker_dev(c, ts, remote, emu):
        if rng.random() < .25:
            return add_device(c, ts - 5 * MIN, remote, emu, did=pool_dev[int(rng.integers(8))])
        return add_device(c, ts - 5 * MIN, remote, emu)

    for _ in range(120):      # 1 impersonation: new device + remote app + new payee + 8-20x amount at night
        c, ts = pick(), when(5, 75, [22, 23, 0, 1, 2, 3])
        d = attacker_dev(c, ts, int(rng.random() < .85), int(rng.random() < .1))
        tx("UPI" if rng.random() < .65 else "NB", c, ts, avg[c] * rng.uniform(8, 20), scam_payee("p2p"), dev=d,
           fraud=1, stype="impersonation")
    for _ in range(100):      # 2 phishing: new-device login then 3-5 rapid transfers
        c, ts = pick(), when(5, 74)
        d = attacker_dev(c, ts, 0, int(rng.random() < .3))
        ps = [scam_payee("p2p") for _ in range(2)]
        for j in range(int(rng.integers(3, 6))):
            ts = ts + MIN * float(rng.uniform(1, 3))
            tx("UPI" if rng.random() < .7 else "WALLET", c, ts, avg[c] * rng.uniform(1.5, 5), ps[j % 2], dev=d,
               wtype="transfer", fraud=1, stype="phishing")
    for _ in range(120):      # 3 fake refund: UPI collect, new payee, "refund" remark
        c = pick()
        tx("UPI", c, when(0, 75), avg[c] * rng.uniform(.8, 4), scam_payee("p2p"), collect=1,
           note=str(rng.choice(["refund for order", "refund processing", "your refund pending", "approve refund"])),
           fraud=1, stype="fake_refund")
    for _ in range(60):       # 4 investment scam: 4-6 escalating transfers over days to a new merchant
        c, t0, p = pick(), when(3, 62), scam_payee("investment")
        for j in range(int(rng.integers(4, 7))):
            t0 = t0 + pd.Timedelta(days=float(rng.uniform(.5, 2)))
            tx("UPI" if rng.random() < .6 else "NB", c, t0, avg[c] * (1 + .9 * j) * rng.uniform(.9, 1.2), p,
               note=str(rng.choice(["invest", "returns", "trading", ""])), fraud=1, stype="investment_scam")
    mules = list(rng.choice(cids, 25, replace=False))
    for c in mules:           # 5 mule account: many small credits from different senders, then rapid outflow
        t0, total = when(8, 70), 0.0
        d = add_device(c, t0 - MIN * 30, 0, 0, did=pool_dev[int(rng.integers(8))] if rng.random() < .6 else None)
        for j in range(int(rng.integers(8, 13))):
            a = rng.uniform(500, 5000)
            total += a
            s = add_payee("p2p", rng.integers(100, 1500), rng.beta(2, 8))
            tx("UPI", c, t0 + pd.Timedelta(minutes=float(j * rng.uniform(15, 35))), a, s, dev=d, dr="credit", note="",
               fraud=1, stype="mule_account")
        tl = t0 + pd.Timedelta(hours=6)
        cols = [collectors[int(i)] for i in rng.choice(5, 2, replace=False)]
        for j, share in enumerate((.55, .4)):
            tx("UPI", c, tl + MIN * (4 * j + 2), total * share, cols[j], dev=d, fraud=1, stype="mule_account")
    for _ in range(120):      # 6 payment request: collect request with urgency / KYC wording
        c = pick()
        tx("UPI", c, when(0, 75), avg[c] * rng.uniform(.3, 2.5), scam_payee("p2p"), collect=1,
           note=str(rng.choice(["urgent payment request", "KYC verify", "verify account urgent", "KYC update fee"])),
           fraud=1, stype="payment_request")

    def chain(c, t0, amt, new_dev):   # 7 cross-channel: card->wallet top-up -> UPI to new VPA -> NB new beneficiary
        d = add_device(c, t0 + MIN, 0, 0) if new_dev else None
        p1, p2 = scam_payee("p2p"), scam_payee("p2p")
        tx("CARD", c, t0, amt, wallet_prv, fraud=1, stype="cross_channel")
        tx("WALLET", c, t0 + 2 * MIN, amt, wallet_prv, dev=d, wtype="topup", fraud=1, stype="cross_channel")
        tx("UPI", c, t0 + 6 * MIN, amt * .97, p1, dev=d, fraud=1, stype="cross_channel")
        tx("NB", c, t0 + 12 * MIN, amt * .92, p2, dev=d, fraud=1, stype="cross_channel")
    for _ in range(70):
        c = pick()
        chain(c, when(3, 74), avg[c] * rng.uniform(5, 9), new_dev=bool(rng.random() < .4))

    # ---------------------------------------------------------------- DEMO scenario: Ramesh
    t60 = START + pd.Timedelta(days=60, hours=23, minutes=42)
    d = add_device(RAM, t60 - 4 * MIN, remote=1, emu=0, did="D_RAMESH_NEW")
    tx("UPI", RAM, t60, 48000, scam_payee("p2p"), dev=d, note="", fraud=1, stype="impersonation")
    chain(RAM, START + pd.Timedelta(days=67, hours=14, minutes=5), 20000, new_dev=False)   # only cross-channel signals

    # ---------------------------------------------------------------- save
    os.makedirs(DATA, exist_ok=True)
    dev_df = pd.DataFrame(list(devs.values()))
    dev_df["first_seen"] = dev_df.first_seen.astype(str)
    out = dict(customers=pd.DataFrame(cust), identity_map=idmap, devices=dev_df, payees=pd.DataFrame(payees),
               raw_upi=pd.DataFrame(rows["UPI"]), raw_card=pd.DataFrame(rows["CARD"]),
               raw_wallet=pd.DataFrame(rows["WALLET"]), raw_netbanking=pd.DataFrame(rows["NB"]),
               loans=pd.DataFrame(loans), repayments=pd.DataFrame(reps), income_expense=pd.DataFrame(ie),
               fraud_labels=pd.DataFrame(labels, columns=["txn_id", "is_fraud", "scam_type"]),
               loan_labels=pd.DataFrame(loan_lab))
    con = sqlite3.connect(os.path.join(DATA, "scamguard.db"))
    for name, df in out.items():
        df.to_csv(os.path.join(DATA, f"{name}.csv"), index=False)
        df.to_sql(name, con, if_exists="replace", index=False)
    con.close()
    json.dump(dict(start=str(START), today=str(TODAY), demo_customer=RAM), open(os.path.join(DATA, "meta.json"), "w"))

    if verbose:
        fl, ll = out["fraud_labels"], out["loan_labels"]
        print(f"customers={len(cust)}  transactions={len(fl):,}  fraud={fl.is_fraud.mean():.1%}")
        print(fl[fl.is_fraud == 1].scam_type.value_counts().to_string())
        print("loans:", len(ll), "| stressed: %.1f%%" % (100 * (ll.stress_group == "stressed").mean()),
              "| default rate: %.1f%%" % (100 * ll.default_within_90d.mean()))
    return out


if __name__ == "__main__":
    generate()
