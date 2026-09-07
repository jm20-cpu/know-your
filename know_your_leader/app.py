from flask import Flask, render_template, request, jsonify
import sqlite3, os, re, threading, time
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('DB_PATH', os.path.join(BASE_DIR, 'data.db'))
PARLIAMENT_URL = 'https://www.parliament.go.ke/the-national-assembly/mps'


def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    c = db()
    c.executescript('''
    CREATE TABLE IF NOT EXISTS leaders (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT UNIQUE NOT NULL,
      office TEXT,
      county TEXT,
      constituency TEXT,
      party TEXT,
      status TEXT,
      performance REAL DEFAULT 0,
      activity REAL DEFAULT 0,
      promises REAL DEFAULT 0,
      budget REAL DEFAULT 0,
      evidence REAL DEFAULT 0,
      source_url TEXT,
      source_name TEXT,
      source_updated TEXT,
      last_seen TEXT
    );
    CREATE TABLE IF NOT EXISTS updates (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      source TEXT, status TEXT, message TEXT, created_at TEXT
    );
    ''')
    c.commit(); c.close()


def score(l):
    vals = [l['performance'], l['activity'], l['promises'], l['budget'], l['evidence']]
    return round(sum(float(x or 0) for x in vals) / 5, 1)


def normalize_name(s):
    return re.sub(r'\s+', ' ', re.sub(r'^(HON\.?|RT\.? HON\.?|DR\.?|AMB\.?|SEN\.?)[ .]+', '', s.strip(), flags=re.I)).strip(' ,')


def import_parliament():
    now = datetime.now(timezone.utc).isoformat()
    try:
        r = requests.get(PARLIAMENT_URL, timeout=25, headers={'User-Agent':'KnowYourLeader/1.0 civic-data-research'})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        rows = []
        for tr in soup.find_all('tr'):
            cells = [re.sub(r'\s+', ' ', x.get_text(' ', strip=True)) for x in tr.find_all(['td','th'])]
            if len(cells) >= 5 and ('HON' in cells[0].upper() or 'VACANT' in cells[0].upper()):
                rows.append(cells)
        # Deduplicate by name
        seen = set(); clean=[]
        for cells in rows:
            name=normalize_name(cells[0])
            if not name or name.upper()=='VACANT' or name in seen: continue
            seen.add(name)
            county=cells[1] if len(cells)>1 else ''
            constituency=cells[2] if len(cells)>2 else ''
            party=cells[3] if len(cells)>3 else ''
            status=cells[4] if len(cells)>4 else ''
            clean.append((name, 'Member of National Assembly', county, constituency, party, status))
        if not clean:
            raise RuntimeError('No member rows were found; the source page layout may have changed.')
        c=db()
        for name,office,county,constituency,party,status in clean:
            # Neutral score: data completeness/evidence only until activity data is collected.
            evidence=100.0
            c.execute('''INSERT INTO leaders(name,office,county,constituency,party,status,performance,activity,promises,budget,evidence,source_url,source_name,source_updated,last_seen)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                         ON CONFLICT(name) DO UPDATE SET office=excluded.office, county=excluded.county, constituency=excluded.constituency, party=excluded.party, status=excluded.status, evidence=excluded.evidence, source_url=excluded.source_url, source_name=excluded.source_name, source_updated=excluded.source_updated, last_seen=excluded.last_seen''',
                      (name,office,county,constituency,party,status,0,0,0,0,evidence,PARLIAMENT_URL,'Kenya Parliament',now,now))
        c.execute('INSERT INTO updates(source,status,message,created_at) VALUES(?,?,?,?)',('Kenya Parliament','success',f'Imported {len(clean)} National Assembly members.',now))
        c.commit(); c.close()
        return {'success':True,'count':len(clean),'message':f'Imported {len(clean)} National Assembly members.'}
    except Exception as e:
        c=db(); c.execute('INSERT INTO updates(source,status,message,created_at) VALUES(?,?,?,?)',('Kenya Parliament','error',str(e),now)); c.commit(); c.close()
        return {'success':False,'count':0,'message':str(e)}


def all_leaders(search=''):
    c=db()
    if search:
        q=f'%{search}%'
        rows=c.execute('SELECT * FROM leaders WHERE name LIKE ? OR county LIKE ? OR constituency LIKE ? OR party LIKE ? OR office LIKE ? ORDER BY name',(q,q,q,q,q)).fetchall()
    else:
        rows=c.execute('SELECT * FROM leaders ORDER BY name').fetchall()
    c.close()
    out=[]
    for r in rows:
        x=dict(r); x['overall']=score(x); out.append(x)
    return out


def bootstrap():
    init_db()
    c=db(); n=c.execute('SELECT COUNT(*) FROM leaders').fetchone()[0]; c.close()
    if n == 0:
        import_parliament()

bootstrap()

@app.route('/')
def home():
    leaders=all_leaders()
    return render_template('index.html', leaders=leaders[:12], total=len(leaders), updated=leaders[0]['last_seen'] if leaders else None)

@app.route('/leaders')
def leaders_page():
    q=request.args.get('q', request.args.get('search','')).strip()
    leaders=all_leaders(q)
    return render_template('leaders.html', leaders=leaders, q=q, total=len(leaders))

@app.route('/leader/<int:leader_id>')
def leader_page(leader_id):
    c=db(); r=c.execute('SELECT * FROM leaders WHERE id=?',(leader_id,)).fetchone(); c.close()
    if not r: return 'Leader not found',404
    leader=dict(r); leader['overall']=score(leader)
    return render_template('leader.html', leader=leader)

@app.route('/compare')
def compare():
    ids=[]
    for x in request.args.getlist('id')[:2]:
        try: ids.append(int(x))
        except: pass
    c=db(); leaders=[]
    for i in ids:
        r=c.execute('SELECT * FROM leaders WHERE id=?',(i,)).fetchone()
        if r:
            x=dict(r); x['overall']=score(x); leaders.append(x)
    c.close()
    return render_template('compare.html', leaders=leaders)

@app.route('/api/leaders')
def api_leaders():
    return jsonify({'success':True,'count':len(all_leaders()),'leaders':all_leaders()})

@app.route('/api/search')
def api_search():
    q=request.args.get('q','').strip()
    return jsonify({'success':True,'query':q,'leaders':all_leaders(q)[:50]})

@app.route('/api/refresh', methods=['GET','POST'])
def refresh():
    return jsonify(import_parliament())

@app.route('/refresh')
def refresh_page():
    return jsonify(import_parliament())

@app.route('/api/updates')
def updates():
    c=db(); rows=c.execute('SELECT * FROM updates ORDER BY id DESC LIMIT 20').fetchall(); c.close()
    return jsonify([dict(x) for x in rows])

@app.route('/health')
def health():
    c=db(); n=c.execute('SELECT COUNT(*) FROM leaders').fetchone()[0]; c.close()
    return jsonify({'status':'online','leaders':n,'database':True})

if __name__=='__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',5000)))
