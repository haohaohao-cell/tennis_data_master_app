# Tennis Data Master App

Production-oriented tennis data platform with backend APIs, admin Web, Expo mobile app, computer-vision pipeline, shared schemas, and product/data documentation.

## Quick Start

The examples below use PowerShell 7 on Windows. Run commands from the repository root unless a step says otherwise.

### 1. Prepare Backend Environment

This project uses the Conda environment named `tennis` for Python commands:

```powershell
conda activate tennis
pip install -r backend/requirements.txt
```

Download the AreaCity boundary CSV used by the location resolver. The script writes the file to `backend/data/area_city_ok_geo.csv`, which is ignored by Git because it is about 167 MB.

```powershell
python scripts/download_area_city_data.py
```

Initialize the local SQLite database. The database file is local runtime state and is ignored by Git.

```powershell
python scripts/init_sqlite_db.py
```

Optional local admin account for the admin Web:

```powershell
python scripts/seed_test_admin.py --username li --password 0000
```

### 2. Start Backend API

```powershell
conda activate tennis
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

Useful local endpoints:

```text
http://localhost:8000/health
http://localhost:8000/docs
```

Development phone login uses verification code `000000`.

### 3. Start Admin Web

Open a new terminal:

```powershell
cd admin
npm install
npm run dev
```

Admin Web runs at:

```text
http://localhost:5175
```

It defaults to backend API base URL `http://localhost:8000/api/v1`. Local admin login can use `li / 0000` after running the seed script above.

### 4. Start Expo App

Open a new terminal:

```powershell
cd app
npm install
npm run start
```

The app automatically resolves the backend host from Expo when possible. Override it when needed:

```powershell
$env:EXPO_PUBLIC_API_BASE_URL = "http://<your-computer-ip>:8000"
npm run start
```

## Project Structure

```text
backend/                 Backend API, database, users, task management
cv/                      Video analysis, ball/player tracking, event recognition
web/                     Web dashboard and admin console
admin/                   Independent admin Web frontend
app/                     React Native / Expo app
shared/                  Shared schemas and constants
  api-schema/            API data structures
  data-schema/           CV output and tennis data formats
  constants/             Common constants
docs/                    Project documentation
scripts/                 Startup, deployment, and data processing scripts
docker-compose.yml
.gitignore
README.md
```
