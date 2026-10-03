"""Phase 2a - Channel adapters: each channel has its own native columns; every adapter maps them
to ONE unified schema and resolves the customer through the identity map.

Unified schema:
 txn_id, customer_id, timestamp, channel, direction, amount, payee_id, payee_type, device_id,
 note, is_collect, channel_specific_json
"""
import json

import pandas as pd


def _json(df, cols):
    return [json.dumps(d, default=str) for d in df[cols].to_dict("records")]


def adapt_upi(df, idm):
    m = idm.set_index("upi_vpa").customer_id
    return pd.DataFrame(dict(
        txn_id=df.upi_ref, customer_id=df.vpa.map(m), timestamp=pd.to_datetime(df.time, format="ISO8601"), channel="UPI",
        direction=df.dr_cr, amount=df.amt, payee_id=df.payee_vpa.str.split("@").str[0].str.upper(),
        device_id=df.dev, note=df.remark.fillna(""), is_collect=df.collect_flag,
        channel_specific_json=_json(df, ["payee_vpa", "collect_flag"])))


def adapt_card(df, idm):
    m = idm.set_index("card_id").customer_id
    return pd.DataFrame(dict(
        txn_id=df.auth_id, customer_id=df.card_id.map(m), timestamp=pd.to_datetime(df.time, format="ISO8601"), channel="CARD",
        direction="debit", amount=df.amt, payee_id=df.merchant_id, device_id="CARDTERM:" + df.terminal,
        note="MCC " + df.mcc.astype(str), is_collect=0, channel_specific_json=_json(df, ["mcc", "country", "terminal"])))


def adapt_wallet(df, idm):
    m = idm.set_index("wallet_id").customer_id
    return pd.DataFrame(dict(
        txn_id=df.wallet_txn_id, customer_id=df.wallet_id.map(m), timestamp=pd.to_datetime(df.time, format="ISO8601"), channel="WALLET",
        direction=df.dr_cr, amount=df.amt, payee_id=df.counterparty, device_id=df.app_dev,
        note="wallet " + df.type, is_collect=0, channel_specific_json=_json(df, ["type"])))


def adapt_nb(df, idm):
    m = idm.set_index("account_no").customer_id
    return pd.DataFrame(dict(
        txn_id=df.ref_no, customer_id=df.account_no.map(m), timestamp=pd.to_datetime(df.time, format="ISO8601"), channel="NETBANK",
        direction=df.dr_cr, amount=df.amt, payee_id=df.beneficiary_id, device_id=df.app_dev,
        note="", is_collect=0, channel_specific_json=_json(df, ["ifsc"])))


def unify(raw_upi, raw_card, raw_wallet, raw_nb, idm, payees):
    """Normalise all feeds, attach payee type, merge into one time-ordered event stream."""
    u = pd.concat([adapt_upi(raw_upi, idm), adapt_card(raw_card, idm), adapt_wallet(raw_wallet, idm),
                   adapt_nb(raw_nb, idm)], ignore_index=True)
    u["payee_type"] = u.payee_id.map(payees.set_index("payee_id").category)
    cols = ["txn_id", "customer_id", "timestamp", "channel", "direction", "amount", "payee_id", "payee_type",
            "device_id", "note", "is_collect", "channel_specific_json"]
    return u[cols].sort_values(["timestamp", "txn_id"]).reset_index(drop=True)
