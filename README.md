# Bincom Election Results Application

A Flask and MySQL implementation of the three questions in the supplied Bincom assessment.

## Stack choice

The invitation permits beginner Python or intermediate Python using a framework. This project uses Flask, which is appropriate if you select the intermediate Python route and can explain Flask basics.

The supplied `bincom_test.sql` is a MySQL/phpMyAdmin dump, not PostgreSQL. Import it into MySQL or MariaDB. Do not try to import it into PostgreSQL unchanged.

## Features

1. View announced results for a selected polling unit.
2. Select an LGA and calculate party totals from `announced_pu_results` joined to `polling_unit`. The application does not use `announced_lga_results` for this calculation.
3. Create a polling unit and save a score row for every party listed in the `party` table. The polling unit and its party scores are inserted in one database transaction.

The app restricts the LGA and polling unit lists to Delta State (`state_id = 25`), as stated in the assessment.

## Database setup

1. Install MySQL Server or MariaDB.
2. Create/import the database using the supplied SQL dump. For example:

```bash
mysql -u root -p < bincom_test.sql
```

The dump creates/uses the database `bincomphptest` only if that database already exists. If necessary, run:

```sql
CREATE DATABASE bincomphptest CHARACTER SET latin1;
```

Then import the dump.

3. Copy `.env.example` to `.env` and set your database credentials. The app reads environment variables; for local testing you can export them in your terminal. If using a `.env` file, install `python-dotenv` and add it to requirements, or export variables manually.

## Run locally

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
export DB_HOST=127.0.0.1
export DB_PORT=3306
export DB_NAME=bincomphptest
export DB_USER=root
export DB_PASSWORD='your_password'
python app.py
```

Open http://127.0.0.1:5000

On Windows PowerShell, use `$env:DB_USER="root"` etc. instead of `export`.

## Important schema details

- `polling_unit.uniqueid` is the primary key for a polling unit.
- `announced_pu_results.polling_unit_uniqueid` is a VARCHAR and stores the polling unit `uniqueid` as text.
- `polling_unit.lga_id` refers to `lga.uniqueid` in the supplied records.
- `ward.lga_id` also refers to `lga.uniqueid`.
- `party.partyid` provides the party abbreviations used for new results.
- The database's `party` table contains nine parties. New polling-unit entry uses that table dynamically.

## Assessment notes / limitations to discuss

- The source dump is an old MySQL 5.1-era phpMyAdmin export. Use MySQL/MariaDB compatibility and retain the supplied schema.
- Existing data has some incomplete or unusual rows, including polling units with zero location identifiers. The UI lists only polling units joined to Delta LGAs.
- Question 3 asks for a page to store results for all parties for a new polling unit. This implementation creates the polling unit and inserts one result row per party atomically.
- This is an assessment/demo application, not a production election system. A production version would require authentication, authorization, audit controls, CSRF protection, stronger validation and review workflows.


Database relationship note: `polling_unit.ward_id` references `ward.ward_id`, and `polling_unit.lga_id` references `lga.lga_id`. The application uses these logical IDs for joins and inserts. `announced_pu_results.polling_unit_uniqueid` references `polling_unit.uniqueid`.


## Delta State Local Government Areas

The following searchable Local Government Area names and IDs are taken from the supplied `bincom_test.sql` database. Use the exact `lga_id` values when filtering or calculating polling unit results. Do not use the list position as the database ID.

| No. | Local Government Area | `lga_id` |
|---:|---|---:|
| 1 | Aniocha North | 1 |
| 2 | Aniocha - South | 2 |
| 3 | Ethiope East | 5 |
| 4 | Ethiope West | 6 |
| 5 | Ika North - East | 7 |
| 6 | Ika - South | 8 |
| 7 | Isoko North | 9 |
| 8 | Isoko South | 10 |
| 9 | Ndokwa East | 11 |
| 10 | Ndokwa West | 12 |
| 11 | Okpe | 13 |
| 12 | Oshimili - North | 14 |
| 13 | Oshimili - South | 15 |
| 14 | Patani | 16 |
| 15 | Sapele | 17 |
| 16 | Udu | 18 |
| 17 | Ughelli North | 19 |
| 18 | Ughelli South | 20 |
| 19 | Ukwuani | 21 |
| 20 | Uvwie | 22 |
| 21 | Bomadi | 31 |
| 22 | Burutu | 32 |
| 23 | Warri North | 33 |
| 24 | Warri South | 34 |
| 25 | Warri South West | 35 |

### Database query to retrieve the list

Run this query in phpMyAdmin to retrieve the current LGA names and IDs directly from the database:

```sql
SELECT lga_id, lga_name
FROM lga
WHERE state_id = 25
ORDER BY lga_name;
```

### Implementation note

For LGA analysis, match `polling_unit.lga_id` to `lga.lga_id`. Calculate party totals from `announced_pu_results` joined to `polling_unit` through `polling_unit.uniqueid`. Do not use `announced_lga_results` as the source for the required polling-unit aggregation.

