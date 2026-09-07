from flask import Flask, render_template, request, jsonify
import sqlite3, os, re
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('DB_PATH', os.path.join(BASE_DIR, 'data.db'))
PARLIAMENT_URL = 'https://www.parliament.go.ke/the-national-assembly/mps'

COUNTIES = [
'Baringo','Bomet','Bungoma','Busia','Elgeyo-Marakwet','Embu','Garissa','Homa Bay','Isiolo','Kajiado','Kakamega','Kericho','Kiambu','Kilifi','Kirinyaga','Kisii','Kisumu','Kitui','Kwale','Laikipia','Lamu','Machakos','Makueni','Mandera','Marsabit','Meru','Migori','Mombasa','Murang’a','Nairobi City','Nakuru','Nandi','Narok','Nyamira','Nyandarua','Nyeri','Samburu','Siaya','Taita-Taveta','Tana River','Tharaka-Nithi','Trans Nzoia','Turkana','Uasin Gishu','Vihiga','Wajir','West Pokot'
]
POSITIONS = {
'President': 'Republic of Kenya',
'Governor': 'County',
'Senator': 'County',
'Woman Representative': 'County',
'Member of National Assembly': 'Constituency',
'MCA': 'Ward'
}


def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def now(): return datetime.now(timezone.utc).isoformat()


def init_db():
    c = db()
    c.executescript('''
    CREATE TABLE IF NOT EXISTS leaders (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      position TEXT NOT NULL,
      county TEXT DEFAULT '',
      constituency TEXT DEFAULT '',
      ward TEXT DEFAULT '',
      party TEXT DEFAULT '',
      status TEXT DEFAULT 'Current office holder',
      bio TEXT DEFAULT '',
      photo_url TEXT DEFAULT '',
      performance REAL,
      activity REAL,
      promises REAL,
      finance REAL,
      evidence REAL DEFAULT 0,
      source_url TEXT,
      source_name TEXT,
      source_updated TEXT,
      last_seen TEXT,
      UNIQUE(name, position, county, constituency, ward)
    );
    CREATE TABLE IF NOT EXISTS updates (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      source TEXT, status TEXT, message TEXT, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS evidence (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      leader_id INTEGER, title TEXT, url TEXT, source TEXT, date TEXT, type TEXT,
      FOREIGN KEY(leader_id) REFERENCES leaders(id)
    );
    ''')
    c.commit(); c.close()


def score(l):
    vals = [l['performance'], l['activity'], l['promises'], l['finance']]
    vals = [float(v) for v in vals if v is not None]
    return round(sum(vals)/len(vals), 1) if vals else None


def clean_name(s):
    s = re.sub(r'\s+', ' ', s.strip())
    s = re.sub(r'^(RT\.?\s+HON\.?|HON\.?|DR\.?|AMB\.?|SEN\.?)\s+', '', s, flags=re.I)
    return s.strip(' ,')


def import_parliament():
    stamp = now()
    try:
        r = requests.get(PARLIAMENT_URL, timeout=30, headers={'User-Agent':'KnowYourLeader/2.0 civic information platform'})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        found = 0
        c = db()
        for tr in soup.find_all('tr'):
            cells = [re.sub(r'\s+', ' ', x.get_text(' ', strip=True)) for x in tr.find_all(['td','th'])]
            if len(cells) < 5: continue
            first = cells[0].upper()
            if 'HON' not in first and 'VACANT' not in first: continue
            if 'VACANT' in first: continue
            name = clean_name(cells[0])
            if not name: continue
            county = cells[1] if len(cells)>1 else ''
            constituency = cells[2] if len(cells)>2 else ''
            party = cells[3] if len(cells)>3 else ''
            status = cells[4] if len(cells)>4 else 'Elected'
            c.execute('''INSERT INTO leaders(name,position,county,constituency,party,status,evidence,source_url,source_name,source_updated,last_seen)
                         VALUES(?,?,?,?,?,?,100,?,?,?,?)
                         ON CONFLICT(name,position,county,constituency,ward) DO UPDATE SET
                         party=excluded.party,status=excluded.status,source_updated=excluded.source_updated,last_seen=excluded.last_seen,evidence=100''',
                      (name,'Member of National Assembly',county,constituency,party,status,PARLIAMENT_URL,'Parliament of Kenya',stamp,stamp))
            found += 1
        c.execute('INSERT INTO updates(source,status,message,created_at) VALUES(?,?,?,?)',('Parliament of Kenya','success',f'Imported {found} National Assembly records',stamp))
        c.commit(); c.close()
        return found
    except Exception as e:
        c = db(); c.execute('INSERT INTO updates(source,status,message,created_at) VALUES(?,?,?,?)',('Parliament of Kenya','error',str(e),stamp)); c.commit(); c.close()
        return 0


def rows_to_dict(rows):
    out=[]
    for r in rows:
        d=dict(r); d['score']=score(r); out.append(d)
    return out


@app.route('/')
def home():
    c=db()
    total=c.execute('SELECT COUNT(*) FROM leaders').fetchone()[0]
    current=c.execute("SELECT COUNT(*) FROM leaders WHERE status LIKE '%Current%' OR status='Elected'").fetchone()[0]
    aspirants=c.execute("SELECT COUNT(*) FROM leaders WHERE status LIKE '%Aspirant%' OR status LIKE '%Candidate%'").fetchone()[0]
    counties=c.execute('SELECT COUNT(DISTINCT county) FROM leaders WHERE county<>""').fetchone()[0]
    latest=c.execute('SELECT * FROM leaders ORDER BY last_seen DESC LIMIT 8').fetchall()
    c.close()
    return render_template('index.html', total=total,current=current,aspirants=aspirants,counties=counties,leaders=rows_to_dict(latest),positions=POSITIONS)

@app.route('/leaders')
def leaders():
    q=request.args.get('q','').strip(); pos=request.args.get('position','').strip(); county=request.args.get('county','').strip(); status=request.args.get('status','').strip()
    sql='SELECT * FROM leaders WHERE 1=1'; args=[]
    if q: sql += ' AND (name LIKE ? OR party LIKE ? OR constituency LIKE ? OR ward LIKE ?)'; args += [f'%{q}%']*4
    if pos: sql += ' AND position=?'; args.append(pos)
    if county: sql += ' AND county=?'; args.append(county)
    if status: sql += ' AND status LIKE ?'; args.append(f'%{status}%')
    sql += ' ORDER BY name LIMIT 500'
    c=db(); data=rows_to_dict(c.execute(sql,args).fetchall()); c.close()
    return render_template('leaders.html', leaders=data, q=q, position=pos, county=county, status=status, counties=COUNTIES, positions=POSITIONS)

@app.route('/leader/<int:leader_id>')
def leader(leader_id):
    c=db(); l=c.execute('SELECT * FROM leaders WHERE id=?',(leader_id,)).fetchone(); ev=c.execute('SELECT * FROM evidence WHERE leader_id=? ORDER BY date DESC',(leader_id,)).fetchall(); c.close()
    if not l: return 'Leader not found',404
    d=dict(l); d['score']=score(l)
    return render_template('leader.html', leader=d, evidence=ev)

@app.route('/counties')
def counties():
    c=db(); stats=[]
    for county in COUNTIES:
        n=c.execute('SELECT COUNT(*) FROM leaders WHERE county=?',(county,)).fetchone()[0]
        stats.append({'name':county,'count':n})
    c.close(); return render_template('counties.html', counties=stats)

@app.route('/county/<path:name>')
def county(name):
    c=db(); ls=rows_to_dict(c.execute('SELECT * FROM leaders WHERE county=? ORDER BY position,name',(name,)).fetchall()); c.close()
    return render_template('county.html',county=name,leaders=ls)

@app.route('/positions')
def positions(): return render_template('positions.html',positions=POSITIONS)

@app.route('/compare')
def compare():
    c=db(); a=request.args.get('a',''); b=request.args.get('b',''); leaders=c.execute('SELECT id,name,position,county,party FROM leaders ORDER BY name').fetchall(); selected=[]
    for x in (a,b):
        if x.isdigit():
            r=c.execute('SELECT * FROM leaders WHERE id=?',(int(x),)).fetchone();
            if r: d=dict(r); d['score']=score(r); selected.append(d)
    c.close(); return render_template('compare.html',leaders=leaders,selected=selected)

@app.route('/aspirants')
def aspirants():
    c=db(); ls=rows_to_dict(c.execute("SELECT * FROM leaders WHERE status LIKE '%Aspirant%' OR status LIKE '%Candidate%' ORDER BY name").fetchall()); c.close(); return render_template('aspirants.html',leaders=ls)

@app.route('/api/leaders')
def api_leaders():
    q=request.args.get('q',''); c=db(); rows=c.execute('SELECT * FROM leaders WHERE name LIKE ? OR county LIKE ? OR position LIKE ? LIMIT 500',(f'%{q}%',f'%{q}%',f'%{q}%')).fetchall(); c.close(); return jsonify(rows_to_dict(rows))

@app.route('/api/refresh', methods=['GET','POST'])
def refresh(): return jsonify({'imported':import_parliament(),'message':'Refresh completed'})

@app.route('/refresh')
def refresh_page():
    n=import_parliament(); return render_template('refresh.html',count=n)

@app.route('/health')
def health(): return jsonify({'status':'ok','service':'Know Your Leader','time':now()})

init_db()
if not db().execute('SELECT COUNT(*) FROM leaders').fetchone()[0]: import_parliament()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',5000)), debug=True)
