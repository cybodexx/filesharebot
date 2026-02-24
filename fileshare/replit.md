# Thunder File Share

A modern web-based file sharing application with Telegram cloud storage backend. Upload files up to 2GB and share them with expiring links.

## Overview

Thunder File Share is a hybrid web application that uses:
- **Web UI**: Modern drag-and-drop upload interface
- **Telegram Storage**: Files stored in Telegram channels (up to 2GB per file)
- **PostgreSQL Database**: Track file metadata and share links

## Project Structure

```
Thunder/
  app.py          # Main application entry point
  config.py       # Configuration settings
  database.py     # PostgreSQL database operations
  telegram.py     # Telegram storage service (pyrofork)
  routes.py       # Web routes and API endpoints
  __init__.py     # Package initialization

Procfile          # Render deployment entry point
render.yaml       # Render blueprint configuration
requirements.txt  # Python dependencies
config.env        # Configuration template
```

## Configuration

Configuration is done via environment variables:

| Variable | Description | Required |
|----------|-------------|----------|
| API_ID | Telegram API ID from my.telegram.org | Yes |
| API_HASH | Telegram API Hash from my.telegram.org | Yes |
| BOT_TOKEN | Bot token from @BotFather | Yes |
| BIN_CHANNEL | Channel ID for file storage (bot must be admin) | Yes |
| DATABASE_URL | PostgreSQL connection string | Yes |
| FQDN | Public domain (e.g., thunder.onrender.com) | For production |
| MAX_FILE_SIZE_MB | Maximum file size in MB | Default: 2000 |
| LINK_EXPIRY_DAYS | Days before links expire | Default: 10 |
| DELETE_AFTER_DOWNLOAD | Delete file after first download | Default: False |

## Running the Application

```bash
python -m Thunder.app
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Home page with upload form |
| `/api/upload` | POST | Upload a file (multipart form) |
| `/f/{code}` | GET | File download page |
| `/dl/{code}` | GET | Direct file download (streams from Telegram) |
| `/api/stats` | GET | Get statistics (JSON) |
| `/status` | GET | Server status (JSON) |

## Deployment on Render

1. Create a new Web Service on Render
2. Connect your repository
3. Set environment variables:
   - `API_ID`, `API_HASH`, `BOT_TOKEN`, `BIN_CHANNEL`
   - `DATABASE_URL` (use Render PostgreSQL or external)
   - `FQDN` (your render domain)
4. Deploy!

The `render.yaml` file provides a blueprint for one-click deployment.

## Recent Changes

- **v2.1.0** (Dec 2024): Telegram storage backend
  - Files stored in Telegram for up to 2GB support
  - Streaming downloads from Telegram
  - Render deployment configuration
  - Background cleanup task for expired files

## User Preferences

- Modern, clean UI design
- Public file sharing (no admin required)
- Simple, straightforward user experience
- Large file support via Telegram storage
