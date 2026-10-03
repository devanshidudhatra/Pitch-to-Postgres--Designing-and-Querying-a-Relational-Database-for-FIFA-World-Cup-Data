# Pitch to Postgres: Designing and Querying a Relational Database for FIFA World Cup Data

DS604 Introduction to Data Management, group project.

| Group member | Student ID |
|---|---|
| Devanshi Dudhatra | 202618027 |
| Pujita Sunapu | 202618003 |
| Rahul Saha | 202618037 |

A normalised PostgreSQL database for the 21 men's FIFA World Cups (1930-2018), loaded from the 27 CSV files of the Fjelstul World Cup Database, with 30 analytical queries, 7 views, and full documentation. The final report is in [`docs/final_report.pdf`](docs/final_report.pdf).

## Data and licence

**The Fjelstul World Cup Database** by Joshua C. Fjelstul, Ph.D., <https://github.com/jfjelstul/worldcup>, licensed under [CC-BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).

**Modifications:**
- The tables were normalised: copied, derived and row-number columns are not stored.
- The text markers "not available" / "not applicable", shirt number 0, and placeholder shoot-out scores became NULL.
- Types were converted (BOOLEAN, DATE, TIME).
- A `positions` lookup table was added.
- The group names of 18 matches were aligned with the `groups` table.

No data values were changed. Everything in this repository derived from the data is shared under the same CC-BY-SA 4.0 licence.

The files are dated July 2022 but cover 1930-2018 only. The 2022 tournament is not included.

## Folder layout

```text
data/          the 27 original CSV files (unchanged)
sql/           ddl.sql (schema), queries.sql (30 queries), views.sql (7 views), reset_local.sql (LOCAL ONLY)
notebooks/     03_load_data, 04_queries, 05_views (.ipynb + executed .pdf)
diagrams/      ER diagrams and relational schema diagrams (.png + Mermaid source .mmd)
docs/          dataset_understanding.md, milestone1-5, final_report, viva_notes, university_server_guide
src/           Python helpers (see below)
.env.example   template for database settings (copy to .env; .env is never committed)
```

| `src/` file | What it does |
|---|---|
| `db.py` | Builds the SQLAlchemy engine from `.env` and prints the target without the password |
| `check_connection.py` | Read-only connection test |
| `create_local_db.py` | Creates the local test database (refuses non-local hosts) |
| `apply_ddl.py` | Runs `sql/ddl.sql` or another SQL file; `--reset-local` drops everything first, local only |
| `clean.py` | Cleaning steps, column lists, load order, proofs that dropped columns are redundant |
| `profile_data.py` | Milestone 0 profiling, which writes `docs/dataset_understanding.md` |
| `sql_blocks.py` | Splits `queries.sql` / `views.sql` into documented blocks |
| `run_notebook.py` | Executes a notebook and exports it to PDF (headless Chrome) |
| `make_diagrams.py` | Draws the diagrams from the live database catalog |
| `md_to_pdf.py` | Converts the Markdown documents to PDF |
| `build_final_report.py` | Builds `docs/final_report.md` / `.pdf` with live query results |
| `report_content.py` | The interpretations of the 30 queries |

## Setup

1. **Python 3.10 or later**, then install the packages:

   ```bash
   python -m pip install -r requirements.txt
   ```

2. **PostgreSQL.** For local testing, any PostgreSQL 12 or later (we used 18). For the course server, see below.
3. **Database settings.** Copy `.env.example` to `.env` and fill in the values. Never commit `.env`.

   ```ini
   DB_HOST=localhost
   DB_PORT=5432
   DB_NAME=worldcup
   DB_USER=postgres
   DB_PASSWORD=your_local_password_here
   DB_SCHEMA=
   ```

4. **Local database (first time only):**

   ```bash
   python src/create_local_db.py      # creates DB_NAME on localhost if it does not exist
   python src/check_connection.py     # read-only check; must end with "Connection OK."
   ```

## Run everything

Run from the project folder, in this order:

```bash
python src/profile_data.py                               # Milestone 0: profile -> docs/dataset_understanding.md
python src/run_notebook.py notebooks/03_load_data.ipynb  # create tables + load 57,269 rows (+ PDF)
python src/run_notebook.py notebooks/04_queries.ipynb    # 30 queries + validation (+ PDF)
python src/run_notebook.py notebooks/05_views.ipynb      # 7 views (+ PDF)
```

You can also open the notebooks in Jupyter (`python -m jupyter notebook`) and use **Kernel > Restart Kernel and Run All Cells**.

**What to expect:**
- **03:** every table shows `OK`, and all 7 integrity checks report 0 problem rows.
- **04:** the validation table shows 16 `match` and 2 `explained`.
- **05:** all 8 checks are `True`.

**Regenerating the documents** (optional; needs an internet connection for the Mermaid diagram renderer):

```bash
python src/make_diagrams.py                     # diagrams/*.png from the database catalog
python src/md_to_pdf.py docs/milestone1.md docs/milestone2.md docs/milestone5.md docs/university_server_guide.md
python src/build_final_report.py                # docs/final_report.md + .pdf (reads live results)
```

**Starting again locally.** Notebook 03 resets the local database itself. To reset by hand: `python src/apply_ddl.py --reset-local`. This refuses to run unless `DB_HOST` is local.

## Switching from the local database to the course server

Only `.env` changes. No code, SQL or notebook needs editing.

1. Connect to the university network (or VPN).
2. Edit `.env` with the details from the instructor:

   ```ini
   DB_HOST=10.100.71.21
   DB_PORT=5432               # as given
   DB_NAME=...                # as given
   DB_USER=...                # as given
   DB_PASSWORD=...            # as given
   DB_SCHEMA=                 # only if told to use a schema
   ```

3. Run `python src/check_connection.py`. It must show `can create tables in that schema: True`, and `World Cup tables already present: 0` for a first load.
4. Run notebooks 03, 04 and 05 as above.

On the server:
- nothing is ever dropped;
- `ddl.sql` and `views.sql` are safe to run twice;
- the loader refuses to load into tables that already hold data, and loads everything in one transaction.

Step-by-step instructions and troubleshooting are in [`docs/university_server_guide.md`](docs/university_server_guide.md) (also available as a PDF).

## Results at a glance

- **Schema:** 28 tables (27 + `positions`), 49 foreign keys, 63 CHECK and 14 UNIQUE constraints, 21 indexes. It is in third normal form (3NF), with one deliberate, enforced redundancy.
- **Load:** 57,269 / 57,269 rows. Several source inconsistencies were found and handled (stage names, group names, shoot-out labels, text markers); all are listed in `docs/dataset_understanding.md`.
- **Queries:** 30, covering joins, GROUP BY/HAVING, subqueries, CTEs, window functions, set operations and CASE. 18 validation checks: 16 match exactly and 2 differences are explained by documented conventions.
- **Views:** 7, all agreeing with their source queries.
