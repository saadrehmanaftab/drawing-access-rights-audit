# Drawing access rights matrix and audit tool

Personal project by Saad Ur Rehman, November 2026. **The drawings, users, roles and grants are all assumed**
(generated with a fixed seed). Nothing comes from a real company, PLM system or employer.

The tool does three things a PLM team does when it tidies up drawing access:

1. **Systematic data cleaning** of the drawing master data: normalizes drawing numbers and revision formats and
   removes duplicate records.
2. **Target rights from rules:** derives read and write rights to drawings from a rule set of role, lifecycle state
   and classification.
3. **Audit:** compares the target rights with the current grants and writes a cleanup list (revoke excessive rights,
   grant missing rights, revoke rights of inactive users).

## Run

```
pip install numpy pandas openpyxl
python access_audit.py
```

Outputs: `drawings.db` (SQLite), `access_audit.xlsx` (sheets AccessMatrix, DrawingsCleaned, CleaningLog,
CleanupList), `results.json`. The seed is fixed (2026), so a rerun reproduces the numbers on the CV.

## Result of the run (assumed data)

| Item | Value |
|---|---|
| Drawings after cleaning | 300 |
| Drawing numbers normalized | 15 |
| Revision formats normalized | 238 |
| Duplicate records removed | 12 |
| Users, roles, lifecycle states | 40 users, 5 roles, 4 states |
| User and drawing pairs checked | 12,000 |
| Excessive rights | 18 (5 of them external supplier rights above "internal") |
| Missing rights | 31 |
| Rights held by inactive users | 114 |
| Cleanup actions | 163 |

## Assumptions (all placeholders)

- Roles and head count: Design Engineer 10, Checker 4, Production 12, Sales 6, External Supplier 8.
- Lifecycle states In Work, In Review, Released, Obsolete; classes internal, confidential, export controlled.
- Rule set: engineers and checkers read everything; production reads released drawings up to confidential and
  obsolete ones up to internal; sales and suppliers read released internal drawings only. Design engineers write
  in In Work, checkers write in In Review.
- Raw data defects: four revision styles ("A", "Rev A", "rev.a", " A "), 15 lower case drawing numbers, 12
  duplicated records. Grant drift: 0.6% excessive and 0.4% missing grants. About 8% of users inactive.

## Limits

This is a model of the method, not a Teamcenter integration. Real access control in Teamcenter uses its own
access manager rules, groups and projects; this tool only mirrors the idea of rule based target rights and an audit
against current grants.
