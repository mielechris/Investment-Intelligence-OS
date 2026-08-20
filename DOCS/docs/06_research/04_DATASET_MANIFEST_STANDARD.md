# Dataset Manifest Standard

Every controlled research dataset requires a manifest.

## Required Fields

- dataset ID;
- version;
- purpose;
- creation timestamp;
- owner;
- code commit;
- schema versions;
- source IDs and versions;
- source rights;
- market-availability rules;
- universe rules;
- constituent history;
- corporate-action policy;
- revision policy;
- missing-data policy;
- feature definitions;
- label definitions;
- train/validation/holdout periods;
- content hash.

## Universe Integrity

The dataset must preserve historical membership.

Examples:

- index constituents;
- ETF constituents;
- futures contract availability;
- delisted equities;
- symbol changes.

## Revision Integrity

Revisable data must specify:

- first release;
- later revisions;
- selected vintage rule.

## Missing Data

Never silently forward-fill information that was not actually known.

## Data Freeze

A final validation dataset version is immutable.

Any change creates a new version.
