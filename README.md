# Know Your Leader 🇰🇪

A modern evidence-first civic information platform for Kenya.

## Scope
- 47 counties
- Six elective positions: President, Governor, Senator, Woman Representative, Member of National Assembly and MCA
- Current office holders and a separate pathway for verified aspirant/candidate records
- Search, county explorer, position filters, profiles and comparison
- Source/evidence fields so claims can be traced

## Current data collector
The first live collector imports National Assembly member records from the official Parliament of Kenya members page. It intentionally does not invent scores for performance, activity, promises or finance.

The other position/candidate collectors should be added from official IEBC, county and government sources before those records are presented as verified.

## Run locally
```bash
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

## Render
Build: `pip install -r requirements.txt`
Start: `gunicorn app:app`

For production, move the database to persistent PostgreSQL and schedule official-source refresh jobs rather than relying on SQLite on an ephemeral web filesystem.
