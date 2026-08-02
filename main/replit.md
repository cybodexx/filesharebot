# vidshare.in

A Netflix-style video streaming and file sharing platform with Telegram cloud storage backend. Features a dark theme UI with red accents, user authentication, and creator monetization.

## Overview

vidshare.in v3.1.0 is a hybrid web application that uses:
- **Futuristic UI**: Cyberpunk aesthetic with glassmorphism, neon gradients, dark/light theme
- **Dashboard Analytics**: Real-time stats, charts, activity feed
- **Telegram Storage**: Files stored in Telegram channels (up to 2GB per file)
- **Playlists**: Create and share file collections with sequential playback
- **PostgreSQL Database**: Track file metadata, analytics, and share links

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

- **v3.1.0** (Dec 2024): Netflix-Style Redesign
  - Redesigned home page with Netflix-inspired hero section
  - Added info-only home page for guests (no upload without login)
  - Login is now required for file uploads
  - Updated navigation to show Upload link only for logged-in users
  - Added Netflix red/dark theme throughout the site
  - Fixed config.py to properly read Telegram secrets from environment variables (using os.environ.get instead of os.getenv)
  - Added separate upload page (/upload) for authenticated users
  - Added features section and "How It Works" steps on home page
  - Added CTA section for guest users to sign up
  - Public video viewing still works for anyone with shared link

- **v3.0.0** (Dec 2024): YouTube-like Platform with User Accounts
  - Added Supabase authentication (login, register, logout)
  - Created user accounts with 100GB storage limits
  - Added user dashboard with files, earnings, wallet, and profile views
  - Implemented private link-only file access (no public discovery)
  - Added file ownership tracking (user_id on files)
  - Implemented bidirectional storage tracking (increment on upload, decrement on delete/expiry)
  - Added video quality selector and playback speed controls
  - Created earnings system with 40% creator revenue share
  - Added TON wallet integration foundation for USDT payments
  - Added Google Ads placeholder zones for monetization
  - Enhanced file analytics with view/download/play tracking

- **v2.3.0** (Dec 2024): Enhanced UI and Ad Monetization Ready
  - Added particle system background animation
  - Added confetti celebration effect on successful uploads
  - Added floating/hover animations to stat cards
  - Added staggered fade-in animations throughout
  - Added "Why Thunder?" feature showcase section
  - Added ad placeholder zones on all pages (header, footer, content areas)
  - Enhanced upload zone with animated gradient border
  - Added hover-lift effects to cards
  - Improved footer design with gradient branding
  - Fixed config loading to use Replit secrets properly (override=False)

- **v2.2.0** (Dec 2024): Debugging and enhancements
  - Fixed requirements.txt (removed duplicates)
  - Fixed config.env to properly load Telegram secrets
  - Added footer with version info
  - Added loading spinner and animation components
  - Improved mobile responsiveness for small screens
  - Added skeleton loading animation
  - Added tooltip component
  - Fixed password field autocomplete attributes
  - Created PostgreSQL database

- **v2.1.0** (Dec 2024): Telegram storage backend
  - Files stored in Telegram for up to 2GB support
  - Streaming downloads from Telegram
  - Render deployment configuration
  - Background cleanup task for expired files

## Ad Integration

Ad placeholder zones are available on all pages:
- **Header Banner**: `.ad-banner-header` - Top of each page
- **Footer Banner**: `.ad-banner-footer` - Bottom of pages
- **Content Banner**: `.ad-banner-content` - Within content areas

To enable ads, replace the `.ad-placeholder` div contents with your ad code (Google AdSense, etc).

## User Preferences

- Modern, clean UI design with cyberpunk/futuristic aesthetic
- Public file sharing (no admin required)
- Simple, straightforward user experience
- Large file support via Telegram storage
- Dynamic animations and visual feedback
