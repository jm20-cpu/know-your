# Know Your Leader Kenya

An evidence-first civic data website. It imports National Assembly member records from the official Parliament of Kenya members page, stores a local cache, supports search, leader profiles, comparisons, API access, and manual refresh.

## Run locally
```bash
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

## Render
If this repository is the project root:
- Build: `pip install -r requirements.txt`
- Start: `gunicorn app:app`

## Important
The current release intentionally does **not** invent performance, promise, budget, or activity scores. Those fields remain zero until verified data collectors are added. Evidence is 100 only because the leader record came from the official Parliament page. Expand collectors using official Parliament, IEBC, government/county records and published documents. Review source terms and rate limits before automated collection.
