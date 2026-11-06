"""Drawing access rights matrix and audit: clean drawing master data, derive target rights from rules,
compare them with the current grants and write a cleanup list.

PERSONAL PROJECT. THE DRAWINGS, USERS, ROLES AND GRANTS ARE ALL ASSUMED (generated with a fixed seed).
Run:  python access_audit.py      (needs numpy, pandas, openpyxl; sqlite3 ships with Python)
Outputs: drawings.db (SQLite), access_audit.xlsx, results.json
"""
import json
import os
import re
import sqlite3
import numpy as np
import pandas as pd

SEED = 2026
N_DRAWINGS, N_USERS = 300, 40
STATES = ["In Work", "In Review", "Released", "Obsolete"]
CLASSES = ["internal", "confidential", "export controlled"]
ROLES = {"Design Engineer": 10, "Checker": 4, "Production": 12, "Sales": 6, "External Supplier": 8}
# assumed rule set: role -> lifecycle state -> highest class the role may read, plus write rights
READ_MAX = {
    "Design Engineer": {s: "export controlled" for s in STATES},
    "Checker": {s: "export controlled" for s in STATES},
    "Production": {"In Work": None, "In Review": None, "Released": "confidential", "Obsolete": "internal"},
    "Sales": {"In Work": None, "In Review": None, "Released": "internal", "Obsolete": None},
    "External Supplier": {"In Work": None, "In Review": None, "Released": "internal", "Obsolete": None},
}
WRITE = {("Design Engineer", "In Work"), ("Checker", "In Review")}
LEVEL = {c: i for i, c in enumerate(CLASSES)}


def raw_master(rng):
    """Assumed raw drawing master data with typical defects: mixed revision formats, padding, duplicates."""
    rows = []
    for i in range(N_DRAWINGS):
        rev = "ABCDE"[int(rng.integers(0, 5))]
        style = int(rng.integers(0, 4))
        rev_txt = [rev, "Rev " + rev, "rev." + rev.lower(), " " + rev + " "][style]
        rows.append(dict(drawing_no="DRW%05d" % (10000 + i), revision=rev_txt,
                         state=STATES[int(rng.choice(4, p=[0.15, 0.1, 0.65, 0.1]))],
                         classification=CLASSES[int(rng.choice(3, p=[0.6, 0.3, 0.1]))]))
    df = pd.DataFrame(rows)
    dup = df.sample(12, random_state=SEED)                       # 12 duplicated records (assumed)
    lower = df.sample(15, random_state=SEED + 1).index           # 15 lower case drawing numbers (assumed)
    df.loc[lower, "drawing_no"] = df.loc[lower, "drawing_no"].str.lower()
    return pd.concat([df, dup], ignore_index=True)


def clean_master(df):
    log = {}
    out = df.copy()
    before = out["drawing_no"].copy()
    out["drawing_no"] = out["drawing_no"].str.strip().str.upper()
    log["drawing numbers normalized"] = int((before != out["drawing_no"]).sum())
    before = out["revision"].copy()
    out["revision"] = out["revision"].map(lambda r: re.sub(r"(?i)^\s*(rev\.?\s*)?", "", r).strip().upper())
    log["revision formats normalized"] = int((before != out["revision"]).sum())
    n = len(out)
    out = out.drop_duplicates(subset=["drawing_no", "revision"]).reset_index(drop=True)
    log["duplicate records removed"] = n - len(out)
    return out, log


def users(rng):
    rows, k = [], 1
    for role, n in ROLES.items():
        for _ in range(n):
            rows.append(dict(user_id="U%03d" % k, role=role, active=bool(rng.random() > 0.08)))
            k += 1
    return pd.DataFrame(rows)


def target_right(role, state, cls):
    if (role, state) in WRITE:
        return "write"
    mx = READ_MAX[role][state]
    if mx is not None and LEVEL[cls] <= LEVEL[mx]:
        return "read"
    return "none"


def current_grants(dw, us, rng):
    """Assumed current grants: the rule set plus drift (extra direct grants, missing grants)."""
    rows = []
    for d in dw.itertuples():
        for u in us.itertuples():
            r = target_right(u.role, d.state, d.classification)
            x = rng.random()
            if r == "none" and x < 0.006:
                r = "read"                                   # assumed drift: excessive direct grant
            elif r == "read" and x < 0.004:
                r = "none"                                   # assumed drift: missing grant
            if r != "none":
                rows.append((d.drawing_no, u.user_id, r))
    return pd.DataFrame(rows, columns=["drawing_no", "user_id", "right"])


def main():
    rng = np.random.default_rng(SEED)
    dw, clean_log = clean_master(raw_master(rng))
    us = users(rng)
    grants = current_grants(dw, us, rng)
    if os.path.exists("drawings.db"):
        os.remove("drawings.db")
    con = sqlite3.connect("drawings.db")
    dw.to_sql("drawings", con, index=False); us.to_sql("users", con, index=False)
    grants.to_sql("grants", con, index=False)
    full = dw.merge(us, how="cross")
    full["target"] = [target_right(r, s, c) for r, s, c in zip(full.role, full.state, full.classification)]
    full = full.merge(grants, on=["drawing_no", "user_id"], how="left").fillna({"right": "none"})
    excessive = full[(full.target == "none") & (full.right != "none")]
    missing = full[(full.target != "none") & (full.right == "none")]
    inactive = full[(~full.active) & (full.right != "none")]
    supplier_conf = excessive[(excessive.role == "External Supplier") & (excessive.classification != "internal")]
    matrix = pd.DataFrame([dict(role=r, state=s, **{c: target_right(r, s, c) for c in CLASSES})
                           for r in ROLES for s in STATES])
    cleanup = pd.concat([excessive.assign(action="revoke excessive right"),
                         missing.assign(action="grant missing right"),
                         inactive.assign(action="revoke, user inactive")], ignore_index=True)
    res = dict(drawings_after_cleaning=int(len(dw)), users=int(len(us)), inactive_users=int((~us.active).sum()),
               cleaning=clean_log, grants_checked=int(len(full)), current_grants=int(len(grants)),
               excessive_rights=int(len(excessive)), missing_rights=int(len(missing)),
               rights_held_by_inactive_users=int(len(inactive)),
               supplier_rights_above_internal=int(len(supplier_conf)), cleanup_actions=int(len(cleanup)))
    with pd.ExcelWriter("access_audit.xlsx") as xw:
        matrix.to_excel(xw, sheet_name="AccessMatrix", index=False)
        dw.to_excel(xw, sheet_name="DrawingsCleaned", index=False)
        pd.Series(clean_log, name="records").to_frame().to_excel(xw, sheet_name="CleaningLog")
        cleanup[["drawing_no", "user_id", "role", "state", "classification", "right", "target", "action"]] \
            .to_excel(xw, sheet_name="CleanupList", index=False)
    json.dump(res, open("results.json", "w"), indent=2)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
