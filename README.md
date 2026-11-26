# Marginalia
Open the reading room, select a guide, and choose a reading mode. Browse as a guest or use My account to generate a private reading key. Save it for cross-device sign-in. Guest progress is copied when creating an account. The key is a bearer credential; keep it private. No email recovery is configured.

## Replit or local
Install Python 3.11+ and pip install -r requirements.txt, then run python app.py. The .replit run command does both steps. The Flask edition stores data in reading.sqlite3; keep this file on a persistent disk. Set MARGINALIA_DB to change the path. Production and local libraries are separate.

## Administrator
Create a reading account on your own deployment. Compute SHA-256 of your reading key locally (Python: import hashlib,getpass; print(hashlib.sha256(getpass.getpass().strip().encode()).hexdigest())). In your private D1 console or local SQLite administration tool, run UPDATE readers SET admin=1 WHERE id='YOUR_HASH'; refresh My account and select Edit guides. Never paste the reading key into the SQL console. No default admin password exists.

## Hosted edition
worker.js runs the same reading UI and API on Cloudflare Workers with the DB binding to a D1 database initialized with schema.sql. All source files are available from the download. The live packaging layer adds the downloadable archive. Topic guides mark unidentified editions. Where linked, library searches are catalog aids, not evidence reviews.
