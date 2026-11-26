import hashlib
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path

from flask import Flask, abort, g, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = 256_000
BOOKS = json.loads((ROOT / 'books.json').read_text())
SCHEMA = (ROOT / 'schema.sql').read_text()

def db():
    if 'db' not in g:
        g.db = sqlite3.connect(os.environ.get('MARGINALIA_DB', ROOT / 'reading.sqlite3'), timeout=15)
        g.db.row_factory = sqlite3.Row
        g.db.executescript(SCHEMA)
    return g.db

@app.teardown_appcontext
def close_db(error):
    if 'db' in g:
        g.db.close()

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def write(sql, args):
    db().execute(sql, args)
    db().commit()

def rows(sql, args=()):
    return [dict(r) for r in db().execute(sql, args)]

@app.get('/')
def home():
    return send_from_directory(ROOT, 'index.html')

@app.get('/<file>')
def asset(file):
    if file not in ('app.js', 'style.css', 'source.zip'):
        abort(404)
    if file == 'source.zip':
        import io, zipfile
        from flask import send_file
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in ('app.py','requirements.txt','.replit','books.json','schema.sql','index.html','app.js','style.css','README.md','worker.js'):
                path = ROOT / name
                if path.is_file():
                    archive.write(path,name)
        data.seek(0)
        return send_file(data, as_attachment=True, download_name='marginalia-source.zip')
    return send_from_directory(ROOT, file)

@app.route('/api/<path:p>', methods=['GET','POST'])
def api(p):
    post = request.method == 'POST'
    if post and (not request.is_json or request.headers.get('Origin','').split('://')[-1] != request.host):
        return jsonify(error='Invalid origin.'),403
    body = request.get_json() if post else {}
    if not isinstance(body,dict):
        return jsonify(error='Invalid body.'),400
    sid = digest(request.cookies.get('marginalia',''))
    now = int(time.time())
    users = rows('SELECT r.* FROM readers r JOIN sessions s ON s.reader=r.id WHERE s.id=? AND expires>?',(sid,now))
    u = users[0] if users else {}
    if p == 'catalog' and not post:
        catalog = [dict(b) for b in BOOKS]
        for e in rows('SELECT * FROM edits'):
            catalog[e['book']].update(json.loads(e['body']))
        return jsonify([b for b in catalog if b.get('published',True) or u.get('admin')])
    if post and p in ('create','login'):
        key = secrets.token_hex(32) if p=='create' else str(body.get('key','')).strip()
        uid = digest(key)
        if p == 'create':
            write('INSERT INTO readers(id) VALUES(?)',(uid,))
        elif not rows('SELECT id FROM readers WHERE id=?',(uid,)):
            return jsonify(error='Unknown reading key.'),401
        session = secrets.token_hex(32)
        write('INSERT INTO sessions VALUES(?,?,?)',(digest(session),uid,now+2592000))
        result = jsonify(key=key) if p=='create' else jsonify(ok=True)
        result.set_cookie('marginalia',session,max_age=2592000,httponly=True,samesite='Strict',secure=request.is_secure or request.headers.get('X-Forwarded-Proto')=='https')
        return result
    if post and p=='logout':
        write('DELETE FROM sessions WHERE id=?',(sid,))
        result=jsonify(ok=True)
        result.delete_cookie('marginalia')
        return result
    if p=='state' and not post:
        progress = rows('SELECT book,idea,minutes FROM progress WHERE reader=?',(u.get('id'),))
        return jsonify(account=bool(u),admin=bool(u.get('admin')),marks=rows('SELECT book,idea,saved,tried FROM marks WHERE reader=?',(u.get('id'),)),progress=next(iter(progress),None))
    if not u or not post:
        return jsonify(error='Sign in required.'),401
    book,idea=body.get('book'),body.get('idea')
    if type(book) is not int or not 0<=book<len(BOOKS):
        return jsonify(error='Unknown guide.'),400
    if p=='admin':
        if not u['admin']:
            return jsonify(error='Administrator required.'),403
        fields=('title','author','overview','example','limit')
        ideas=body.get('ideas')
        if any(not isinstance(body.get(k),str) or not 0<len(body[k].strip())<=4000 for k in fields) or not isinstance(ideas,list) or len(ideas)!=len(BOOKS[book]['ideas']) or any(not isinstance(x,str) or not 0<len(x.strip())<=2000 for x in ideas):
            return jsonify(error='Invalid guide fields.'),400
        content={k:body[k] for k in fields}
        content.update(ideas=ideas,published=body.get('published') is not False)
        write('INSERT OR REPLACE INTO edits VALUES(?,?)',(book,json.dumps(content)))
    elif type(idea) is not int or not 0<=idea<len(BOOKS[book]['ideas']):
        return jsonify(error='Unknown idea.'),400
    elif p=='progress' and body.get('minutes') in (2,5,15):
        write('INSERT OR REPLACE INTO progress VALUES(?,?,?,?)',(u['id'],book,idea,body['minutes']))
    elif p=='mark' and body.get('field') in ('saved','tried') and type(body.get('on')) is bool:
        field=body['field']
        write(f'INSERT INTO marks(reader,book,idea,{field}) VALUES(?,?,?,?) ON CONFLICT(reader,book,idea) DO UPDATE SET {field}=excluded.{field}',(u['id'],book,idea,int(body['on'])))
    else:
        return jsonify(error='Invalid action.'),400
    return jsonify(ok=True)

@app.after_request
def private(response):
    if request.path.startswith('/api/'):
        response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0',port=int(os.environ.get('PORT','3000')))
