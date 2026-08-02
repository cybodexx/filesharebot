import datetime
import secrets
import hashlib
import socket
import ssl as ssl_module
from urllib.parse import urlparse
from typing import Optional, Dict, Any, List
import asyncpg
from Thunder.config import Config


def _resolve_ipv4(uri: str):
    """
    Parse a postgres URI and resolve the hostname to an IPv4 address.
    Returns (kwargs, ssl_ctx) suitable for asyncpg.create_pool(**kwargs, ssl=ssl_ctx).
    This is needed because Replit does not support IPv6, and some Supabase
    endpoints (especially the direct connection) advertise AAAA records.
    """
    parsed = urlparse(uri)
    hostname = parsed.hostname or "localhost"
    port = parsed.port or 5432

    # Force IPv4 resolution
    try:
        results = socket.getaddrinfo(hostname, port, socket.AF_INET, socket.SOCK_STREAM)
        ipv4 = results[0][4][0]
    except Exception:
        ipv4 = hostname  # fall back to hostname if resolution fails

    # Supabase always requires SSL; build a permissive context so we don't
    # need to bundle the CA cert.
    ssl_ctx = ssl_module.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl_module.CERT_NONE

    kwargs = dict(
        host=ipv4,
        port=port,
        user=parsed.username,
        password=parsed.password,
        database=(parsed.path or "/postgres").lstrip("/") or "postgres",
        server_settings={"sslmode": "require"},
    )
    return kwargs, ssl_ctx


class Database:
    def __init__(self, uri: str):
        self._uri = uri
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        if not self._uri:
            raise ValueError("DATABASE_URL is required")
        try:
            conn_kwargs, ssl_ctx = _resolve_ipv4(self._uri)
            self._pool = await asyncpg.create_pool(
                **conn_kwargs,
                ssl=ssl_ctx,
                min_size=2,
                max_size=10,
            )
            print("   [OK] Database connection established")
            await self._create_tables()
        except Exception as e:
            print(f"   [ERROR] Failed to connect to database: {e}")
            raise

    async def _create_tables(self):
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id UUID PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    username TEXT NOT NULL,
                    storage_limit BIGINT DEFAULT 107374182400,
                    storage_used BIGINT DEFAULT 0,
                    total_earnings DECIMAL(20, 8) DEFAULT 0,
                    available_earnings DECIMAL(20, 8) DEFAULT 0,
                    pending_earnings DECIMAL(20, 8) DEFAULT 0,
                    ton_wallet_address TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            ''')

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS files (
                    id SERIAL PRIMARY KEY,
                    unique_code VARCHAR(32) UNIQUE NOT NULL,
                    message_id BIGINT NOT NULL,
                    file_name TEXT NOT NULL,
                    file_size BIGINT NOT NULL,
                    mime_type TEXT,
                    file_hash VARCHAR(64),
                    created_at TIMESTAMP DEFAULT NOW(),
                    expires_at TIMESTAMP NOT NULL,
                    download_count INTEGER DEFAULT 0,
                    view_count INTEGER DEFAULT 0,
                    delete_after_download BOOLEAN DEFAULT FALSE,
                    uploader_ip TEXT,
                    password_hash TEXT,
                    is_protected BOOLEAN DEFAULT FALSE,
                    thumbnail_url TEXT,
                    last_accessed_at TIMESTAMP,
                    play_count INTEGER DEFAULT 0
                )
            ''')
            
            try:
                await conn.execute('ALTER TABLE files ADD COLUMN IF NOT EXISTS user_id UUID')
            except Exception:
                pass
            try:
                await conn.execute('ALTER TABLE files ADD COLUMN IF NOT EXISTS is_private BOOLEAN DEFAULT TRUE')
            except Exception:
                pass
            try:
                await conn.execute("ALTER TABLE files ADD COLUMN IF NOT EXISTS storage_type VARCHAR(10) DEFAULT 'bot'")
            except Exception:
                pass
            try:
                await conn.execute('ALTER TABLE files ADD COLUMN IF NOT EXISTS storage_chat_id BIGINT')
            except Exception:
                pass

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS playlists (
                    id SERIAL PRIMARY KEY,
                    unique_code VARCHAR(32) UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    expires_at TIMESTAMP,
                    is_public BOOLEAN DEFAULT TRUE,
                    password_hash TEXT,
                    view_count INTEGER DEFAULT 0,
                    creator_ip TEXT
                )
            ''')

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS playlist_items (
                    id SERIAL PRIMARY KEY,
                    playlist_id INTEGER REFERENCES playlists(id) ON DELETE CASCADE,
                    file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    added_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(playlist_id, file_id)
                )
            ''')

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS file_events (
                    id SERIAL PRIMARY KEY,
                    file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
                    event_type VARCHAR(20) NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    ip_address TEXT,
                    user_agent TEXT,
                    referer TEXT,
                    country_code VARCHAR(2),
                    city TEXT,
                    device_type VARCHAR(20),
                    browser VARCHAR(50),
                    duration_seconds INTEGER
                )
            ''')

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS activity_feed (
                    id SERIAL PRIMARY KEY,
                    event_type VARCHAR(30) NOT NULL,
                    file_id INTEGER REFERENCES files(id) ON DELETE SET NULL,
                    playlist_id INTEGER REFERENCES playlists(id) ON DELETE SET NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    metadata JSONB
                )
            ''')

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS earnings (
                    id SERIAL PRIMARY KEY,
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    file_id INTEGER REFERENCES files(id) ON DELETE SET NULL,
                    event_type VARCHAR(30) NOT NULL,
                    ad_impressions INTEGER DEFAULT 0,
                    estimated_revenue DECIMAL(20, 8) DEFAULT 0,
                    creator_share DECIMAL(20, 8) DEFAULT 0,
                    platform_share DECIMAL(20, 8) DEFAULT 0,
                    status VARCHAR(20) DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT NOW()
                )
            ''')

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_wallets (
                    id SERIAL PRIMARY KEY,
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE UNIQUE,
                    ton_address TEXT,
                    usdt_balance DECIMAL(20, 8) DEFAULT 0,
                    pending_withdrawal DECIMAL(20, 8) DEFAULT 0,
                    last_withdrawal_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            ''')

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS withdrawal_requests (
                    id SERIAL PRIMARY KEY,
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    amount DECIMAL(20, 8) NOT NULL,
                    ton_address TEXT NOT NULL,
                    status VARCHAR(20) DEFAULT 'pending',
                    tx_hash TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    processed_at TIMESTAMP
                )
            ''')

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_telegram_sessions (
                    id SERIAL PRIMARY KEY,
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE UNIQUE,
                    session_string TEXT NOT NULL,
                    phone_number TEXT,
                    telegram_user_id BIGINT,
                    telegram_username TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            ''')

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS clicks (
                    id SERIAL PRIMARY KEY,
                    file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
                    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                    ip_address TEXT,
                    device_type VARCHAR(20),
                    country_code VARCHAR(5),
                    referrer TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            ''')

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS plays (
                    id SERIAL PRIMARY KEY,
                    file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
                    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                    session_id TEXT,
                    watch_duration INTEGER DEFAULT 0,
                    completed BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            ''')

            await conn.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_files_user_id ON files(user_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_files_unique_code ON files(unique_code)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_files_expires_at ON files(expires_at)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_files_message_id ON files(message_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_files_created_at ON files(created_at)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_playlists_unique_code ON playlists(unique_code)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_playlist_items_playlist_id ON playlist_items(playlist_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_file_events_file_id ON file_events(file_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_file_events_created_at ON file_events(created_at)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_activity_feed_created_at ON activity_feed(created_at)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_earnings_user_id ON earnings(user_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_clicks_file_id ON clicks(file_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_plays_file_id ON plays(file_id)')
            
            print("   [OK] Database tables ready")

    async def create_or_update_user(self, user_id: str, email: str, username: str) -> bool:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO users (id, email, username) VALUES ($1, $2, $3)
                ON CONFLICT (id) DO UPDATE SET email = $2, username = $3, updated_at = NOW()
            ''', user_id, email, username)
            return True

    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow('SELECT * FROM users WHERE id = $1', user_id)
            return dict(row) if row else None

    async def create_file_record(
        self,
        message_id: int,
        file_name: str,
        file_size: int,
        mime_type: Optional[str] = None,
        file_hash: Optional[str] = None,
        expires_days: Optional[int] = None,
        delete_after_download: bool = False,
        uploader_ip: Optional[str] = None,
        password: Optional[str] = None,
        user_id: Optional[str] = None,
        is_private: bool = True,
        storage_type: str = 'bot',
        storage_chat_id: Optional[int] = None
    ) -> str:
        if expires_days is None:
            expires_days = Config.LINK_EXPIRY_DAYS
            
        unique_code = secrets.token_urlsafe(16)
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=expires_days)
        
        password_hash = None
        is_protected = False
        if password:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            is_protected = True
        
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO files (unique_code, user_id, message_id, file_name, file_size, mime_type, file_hash, expires_at, delete_after_download, uploader_ip, password_hash, is_protected, is_private, storage_type, storage_chat_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            ''', unique_code, user_id, message_id, file_name, file_size, mime_type, file_hash, expires_at, delete_after_download, uploader_ip, password_hash, is_protected, is_private, storage_type, storage_chat_id)
            
            if user_id:
                await conn.execute('''
                    UPDATE users SET storage_used = storage_used + $1, updated_at = NOW() WHERE id = $2
                ''', file_size, user_id)
            
            await self._log_activity(conn, 'file_uploaded', file_id=None, description=f'New file uploaded: {file_name}')
        
        return unique_code

    async def get_file_by_code(self, unique_code: str) -> Optional[Dict[str, Any]]:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT id, unique_code, user_id, message_id, file_name, file_size, mime_type, file_hash,
                       created_at, expires_at, download_count, view_count, delete_after_download,
                       is_protected, password_hash, thumbnail_url, last_accessed_at, play_count, is_private,
                       storage_type, storage_chat_id
                FROM files
                WHERE unique_code = $1
            ''', unique_code)
            return dict(row) if row else None

    async def verify_file_password(self, unique_code: str, password: str) -> bool:
        file_info = await self.get_file_by_code(unique_code)
        if not file_info or not file_info.get('is_protected'):
            return True
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        return file_info.get('password_hash') == password_hash

    async def increment_download_count(self, unique_code: str) -> bool:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            await conn.execute('''
                UPDATE files
                SET download_count = download_count + 1, last_accessed_at = NOW()
                WHERE unique_code = $1
            ''', unique_code)
            return True

    async def increment_view_count(self, unique_code: str) -> bool:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            await conn.execute('''
                UPDATE files
                SET view_count = view_count + 1, last_accessed_at = NOW()
                WHERE unique_code = $1
            ''', unique_code)
            return True

    async def increment_play_count(self, unique_code: str) -> bool:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            await conn.execute('''
                UPDATE files
                SET play_count = play_count + 1, last_accessed_at = NOW()
                WHERE unique_code = $1
            ''', unique_code)
            return True

    async def log_file_event(
        self,
        file_id: int,
        event_type: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        referer: Optional[str] = None,
        country_code: Optional[str] = None,
        city: Optional[str] = None,
        device_type: Optional[str] = None,
        browser: Optional[str] = None,
        duration_seconds: Optional[int] = None
    ):
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO file_events (file_id, event_type, ip_address, user_agent, referer, country_code, city, device_type, browser, duration_seconds)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ''', file_id, event_type, ip_address, user_agent, referer, country_code, city, device_type, browser, duration_seconds)

    async def get_file_analytics(self, file_id: int, days: int = 30) -> Dict[str, Any]:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            since = datetime.datetime.utcnow() - datetime.timedelta(days=days)
            
            total_views = await conn.fetchval(
                "SELECT COUNT(*) FROM file_events WHERE file_id = $1 AND event_type = 'view' AND created_at > $2",
                file_id, since
            )
            total_downloads = await conn.fetchval(
                "SELECT COUNT(*) FROM file_events WHERE file_id = $1 AND event_type = 'download' AND created_at > $2",
                file_id, since
            )
            total_plays = await conn.fetchval(
                "SELECT COUNT(*) FROM file_events WHERE file_id = $1 AND event_type = 'play' AND created_at > $2",
                file_id, since
            )
            
            daily_stats = await conn.fetch('''
                SELECT DATE(created_at) as date, event_type, COUNT(*) as count
                FROM file_events
                WHERE file_id = $1 AND created_at > $2
                GROUP BY DATE(created_at), event_type
                ORDER BY date
            ''', file_id, since)
            
            device_stats = await conn.fetch('''
                SELECT device_type, COUNT(*) as count
                FROM file_events
                WHERE file_id = $1 AND created_at > $2 AND device_type IS NOT NULL
                GROUP BY device_type
            ''', file_id, since)
            
            country_stats = await conn.fetch('''
                SELECT country_code, COUNT(*) as count
                FROM file_events
                WHERE file_id = $1 AND created_at > $2 AND country_code IS NOT NULL
                GROUP BY country_code
                ORDER BY count DESC
                LIMIT 10
            ''', file_id, since)
            
            return {
                'total_views': total_views or 0,
                'total_downloads': total_downloads or 0,
                'total_plays': total_plays or 0,
                'daily_stats': [dict(row) for row in daily_stats],
                'device_stats': [dict(row) for row in device_stats],
                'country_stats': [dict(row) for row in country_stats]
            }

    async def create_playlist(
        self,
        name: str,
        description: Optional[str] = None,
        expires_days: Optional[int] = None,
        is_public: bool = True,
        password: Optional[str] = None,
        creator_ip: Optional[str] = None
    ) -> str:
        unique_code = secrets.token_urlsafe(16)
        expires_at = None
        if expires_days:
            expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=expires_days)
        
        password_hash = None
        if password:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO playlists (unique_code, name, description, expires_at, is_public, password_hash, creator_ip)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            ''', unique_code, name, description, expires_at, is_public, password_hash, creator_ip)
            
            await self._log_activity(conn, 'playlist_created', description=f'New playlist created: {name}')
        
        return unique_code

    async def get_playlist_by_code(self, unique_code: str) -> Optional[Dict[str, Any]]:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT id, unique_code, name, description, created_at, updated_at, expires_at,
                       is_public, password_hash, view_count
                FROM playlists
                WHERE unique_code = $1
            ''', unique_code)
            return dict(row) if row else None

    async def add_file_to_playlist(self, playlist_code: str, file_code: str) -> bool:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            playlist = await conn.fetchrow('SELECT id FROM playlists WHERE unique_code = $1', playlist_code)
            file = await conn.fetchrow('SELECT id FROM files WHERE unique_code = $1', file_code)
            
            if not playlist or not file:
                return False
            
            max_position = await conn.fetchval(
                'SELECT COALESCE(MAX(position), 0) FROM playlist_items WHERE playlist_id = $1',
                playlist['id']
            )
            
            await conn.execute('''
                INSERT INTO playlist_items (playlist_id, file_id, position)
                VALUES ($1, $2, $3)
                ON CONFLICT (playlist_id, file_id) DO NOTHING
            ''', playlist['id'], file['id'], max_position + 1)
            
            await conn.execute(
                'UPDATE playlists SET updated_at = NOW() WHERE id = $1',
                playlist['id']
            )
            return True

    async def remove_file_from_playlist(self, playlist_code: str, file_code: str) -> bool:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            playlist = await conn.fetchrow('SELECT id FROM playlists WHERE unique_code = $1', playlist_code)
            file = await conn.fetchrow('SELECT id FROM files WHERE unique_code = $1', file_code)
            
            if not playlist or not file:
                return False
            
            await conn.execute('''
                DELETE FROM playlist_items WHERE playlist_id = $1 AND file_id = $2
            ''', playlist['id'], file['id'])
            
            await conn.execute(
                'UPDATE playlists SET updated_at = NOW() WHERE id = $1',
                playlist['id']
            )
            return True

    async def get_playlist_files(self, playlist_code: str) -> List[Dict[str, Any]]:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT f.id, f.unique_code, f.file_name, f.file_size, f.mime_type, f.created_at,
                       f.download_count, f.view_count, pi.position
                FROM playlist_items pi
                JOIN files f ON f.id = pi.file_id
                JOIN playlists p ON p.id = pi.playlist_id
                WHERE p.unique_code = $1
                ORDER BY pi.position
            ''', playlist_code)
            return [dict(row) for row in rows]

    async def get_all_playlists(self, limit: int = 50) -> List[Dict[str, Any]]:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT p.id, p.unique_code, p.name, p.description, p.created_at, p.view_count,
                       COUNT(pi.id) as file_count
                FROM playlists p
                LEFT JOIN playlist_items pi ON p.id = pi.playlist_id
                WHERE p.is_public = TRUE
                GROUP BY p.id
                ORDER BY p.created_at DESC
                LIMIT $1
            ''', limit)
            return [dict(row) for row in rows]

    async def increment_playlist_view_count(self, unique_code: str) -> bool:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            await conn.execute('''
                UPDATE playlists SET view_count = view_count + 1 WHERE unique_code = $1
            ''', unique_code)
            return True

    async def delete_file_record(self, unique_code: str) -> bool:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            file_info = await conn.fetchrow(
                'SELECT user_id, file_size FROM files WHERE unique_code = $1',
                unique_code
            )
            
            result = await conn.execute('DELETE FROM files WHERE unique_code = $1', unique_code)
            
            if file_info and file_info['user_id'] and file_info['file_size']:
                await conn.execute('''
                    UPDATE users SET storage_used = GREATEST(0, storage_used - $1), updated_at = NOW()
                    WHERE id = $2
                ''', file_info['file_size'], file_info['user_id'])
            
            return "DELETE 1" in result

    async def delete_expired_files(self) -> List[int]:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT message_id, user_id, file_size FROM files WHERE expires_at < $1',
                datetime.datetime.utcnow()
            )
            message_ids = [row['message_id'] for row in rows]
            
            for row in rows:
                if row['user_id'] and row['file_size']:
                    await conn.execute('''
                        UPDATE users SET storage_used = GREATEST(0, storage_used - $1), updated_at = NOW()
                        WHERE id = $2
                    ''', row['file_size'], row['user_id'])
            
            await conn.execute(
                'DELETE FROM files WHERE expires_at < $1',
                datetime.datetime.utcnow()
            )
            return message_ids

    async def get_all_files(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT id, unique_code, message_id, file_name, file_size, mime_type,
                       created_at, expires_at, download_count, view_count, play_count,
                       is_protected, last_accessed_at
                FROM files
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
            ''', limit, offset)
            return [dict(row) for row in rows]

    async def get_stats(self) -> Dict[str, Any]:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            total_files = await conn.fetchval('SELECT COUNT(*) FROM files')
            total_size = await conn.fetchval('SELECT COALESCE(SUM(file_size), 0) FROM files')
            total_downloads = await conn.fetchval('SELECT COALESCE(SUM(download_count), 0) FROM files')
            total_views = await conn.fetchval('SELECT COALESCE(SUM(view_count), 0) FROM files')
            total_plays = await conn.fetchval('SELECT COALESCE(SUM(play_count), 0) FROM files')
            total_playlists = await conn.fetchval('SELECT COUNT(*) FROM playlists')
            
            today = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            uploads_today = await conn.fetchval(
                'SELECT COUNT(*) FROM files WHERE created_at >= $1', today
            )
            downloads_today = await conn.fetchval(
                "SELECT COUNT(*) FROM file_events WHERE event_type = 'download' AND created_at >= $1", today
            )
            
            return {
                'total_files': total_files or 0,
                'total_size': total_size or 0,
                'total_downloads': total_downloads or 0,
                'total_views': total_views or 0,
                'total_plays': total_plays or 0,
                'total_playlists': total_playlists or 0,
                'uploads_today': uploads_today or 0,
                'downloads_today': downloads_today or 0
            }

    async def get_dashboard_stats(self, days: int = 7) -> Dict[str, Any]:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            since = datetime.datetime.utcnow() - datetime.timedelta(days=days)
            
            daily_uploads = await conn.fetch('''
                SELECT DATE(created_at) as date, COUNT(*) as count, SUM(file_size) as size
                FROM files
                WHERE created_at > $1
                GROUP BY DATE(created_at)
                ORDER BY date
            ''', since)
            
            daily_events = await conn.fetch('''
                SELECT DATE(created_at) as date, event_type, COUNT(*) as count
                FROM file_events
                WHERE created_at > $1
                GROUP BY DATE(created_at), event_type
                ORDER BY date
            ''', since)
            
            top_files = await conn.fetch('''
                SELECT unique_code, file_name, file_size, download_count, view_count, play_count
                FROM files
                ORDER BY (download_count + view_count + play_count) DESC
                LIMIT 10
            ''')
            
            recent_files = await conn.fetch('''
                SELECT unique_code, file_name, file_size, mime_type, created_at
                FROM files
                ORDER BY created_at DESC
                LIMIT 5
            ''')
            
            from decimal import Decimal
            def serialize_row(row):
                result = dict(row)
                for key, value in result.items():
                    if isinstance(value, (datetime.date, datetime.datetime)):
                        result[key] = value.isoformat()
                    elif isinstance(value, Decimal):
                        result[key] = float(value)
                return result
            
            return {
                'daily_uploads': [serialize_row(row) for row in daily_uploads],
                'daily_events': [serialize_row(row) for row in daily_events],
                'top_files': [serialize_row(row) for row in top_files],
                'recent_files': [serialize_row(row) for row in recent_files]
            }

    async def get_activity_feed(self, limit: int = 20) -> List[Dict[str, Any]]:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT af.id, af.event_type, af.description, af.created_at, af.metadata,
                       f.file_name, f.unique_code as file_code,
                       p.name as playlist_name, p.unique_code as playlist_code
                FROM activity_feed af
                LEFT JOIN files f ON f.id = af.file_id
                LEFT JOIN playlists p ON p.id = af.playlist_id
                ORDER BY af.created_at DESC
                LIMIT $1
            ''', limit)
            return [dict(row) for row in rows]

    async def _log_activity(
        self,
        conn,
        event_type: str,
        file_id: Optional[int] = None,
        playlist_id: Optional[int] = None,
        description: Optional[str] = None,
        metadata: Optional[dict] = None
    ):
        import json
        await conn.execute('''
            INSERT INTO activity_feed (event_type, file_id, playlist_id, description, metadata)
            VALUES ($1, $2, $3, $4, $5)
        ''', event_type, file_id, playlist_id, description, json.dumps(metadata) if metadata else None)

    async def get_user_files(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT id, unique_code, file_name, file_size, mime_type, created_at, 
                       expires_at, download_count, view_count, play_count, is_protected, is_private
                FROM files
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
            ''', user_id, limit)
            return [dict(row) for row in rows]

    async def get_user_storage(self, user_id: str) -> Dict[str, int]:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT storage_limit, storage_used FROM users WHERE id = $1
            ''', user_id)
            if row:
                return {'limit': row['storage_limit'], 'used': row['storage_used']}
            return {'limit': 107374182400, 'used': 0}

    async def check_user_storage_limit(self, user_id: str, file_size: int) -> bool:
        storage = await self.get_user_storage(user_id)
        return (storage['used'] + file_size) <= storage['limit']

    async def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            total_files = await conn.fetchval('SELECT COUNT(*) FROM files WHERE user_id = $1', user_id)
            total_size = await conn.fetchval('SELECT COALESCE(SUM(file_size), 0) FROM files WHERE user_id = $1', user_id)
            total_views = await conn.fetchval('SELECT COALESCE(SUM(view_count), 0) FROM files WHERE user_id = $1', user_id)
            total_plays = await conn.fetchval('SELECT COALESCE(SUM(play_count), 0) FROM files WHERE user_id = $1', user_id)
            total_downloads = await conn.fetchval('SELECT COALESCE(SUM(download_count), 0) FROM files WHERE user_id = $1', user_id)
            
            user = await conn.fetchrow('SELECT storage_limit, storage_used, total_earnings, available_earnings, pending_earnings FROM users WHERE id = $1', user_id)
            
            return {
                'total_files': total_files or 0,
                'total_size': total_size or 0,
                'total_views': total_views or 0,
                'total_plays': total_plays or 0,
                'total_downloads': total_downloads or 0,
                'storage_limit': user['storage_limit'] if user else 107374182400,
                'storage_used': user['storage_used'] if user else 0,
                'total_earnings': float(user['total_earnings']) if user else 0,
                'available_earnings': float(user['available_earnings']) if user else 0,
                'pending_earnings': float(user['pending_earnings']) if user else 0
            }

    async def get_user_earnings(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            since = datetime.datetime.utcnow() - datetime.timedelta(days=days)
            
            user = await conn.fetchrow('''
                SELECT total_earnings, available_earnings, pending_earnings FROM users WHERE id = $1
            ''', user_id)
            
            daily_earnings = await conn.fetch('''
                SELECT DATE(created_at) as date, SUM(creator_share) as earnings, SUM(ad_impressions) as impressions
                FROM earnings
                WHERE user_id = $1 AND created_at > $2
                GROUP BY DATE(created_at)
                ORDER BY date
            ''', user_id, since)
            
            top_earning_files = await conn.fetch('''
                SELECT f.unique_code, f.file_name, SUM(e.creator_share) as total_earnings, 
                       SUM(e.ad_impressions) as total_impressions
                FROM earnings e
                JOIN files f ON f.id = e.file_id
                WHERE e.user_id = $1
                GROUP BY f.id, f.unique_code, f.file_name
                ORDER BY total_earnings DESC
                LIMIT 10
            ''', user_id)
            
            return {
                'total_earnings': float(user['total_earnings']) if user else 0,
                'available_earnings': float(user['available_earnings']) if user else 0,
                'pending_earnings': float(user['pending_earnings']) if user else 0,
                'daily_earnings': [{'date': str(row['date']), 'earnings': float(row['earnings']), 'impressions': int(row['impressions'])} for row in daily_earnings],
                'top_earning_files': [{'code': row['unique_code'], 'name': row['file_name'], 'earnings': float(row['total_earnings']), 'impressions': int(row['total_impressions'])} for row in top_earning_files]
            }

    async def get_user_wallet(self, user_id: str) -> Optional[Dict[str, Any]]:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT * FROM user_wallets WHERE user_id = $1
            ''', user_id)
            if row:
                return dict(row)
            
            await conn.execute('''
                INSERT INTO user_wallets (user_id) VALUES ($1) ON CONFLICT DO NOTHING
            ''', user_id)
            row = await conn.fetchrow('SELECT * FROM user_wallets WHERE user_id = $1', user_id)
            return dict(row) if row else None

    async def update_user_wallet(self, user_id: str, ton_address: str) -> bool:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            await conn.execute('''
                UPDATE user_wallets SET ton_address = $1, updated_at = NOW() WHERE user_id = $2
            ''', ton_address, user_id)
            return True

    async def record_earning(self, user_id: str, file_id: int, event_type: str, 
                            ad_impressions: int, estimated_revenue: float, creator_share_percent: float = 0.40):
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        
        creator_share = estimated_revenue * creator_share_percent
        platform_share = estimated_revenue * (1 - creator_share_percent)
        
        async with self._pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO earnings (user_id, file_id, event_type, ad_impressions, estimated_revenue, creator_share, platform_share)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            ''', user_id, file_id, event_type, ad_impressions, estimated_revenue, creator_share, platform_share)
            
            await conn.execute('''
                UPDATE users SET pending_earnings = pending_earnings + $1, total_earnings = total_earnings + $1, updated_at = NOW()
                WHERE id = $2
            ''', creator_share, user_id)

    async def log_click(self, file_id: int, user_id: Optional[str] = None, ip_address: Optional[str] = None,
                       device_type: Optional[str] = None, country_code: Optional[str] = None, referrer: Optional[str] = None):
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO clicks (file_id, user_id, ip_address, device_type, country_code, referrer)
                VALUES ($1, $2, $3, $4, $5, $6)
            ''', file_id, user_id, ip_address, device_type, country_code, referrer)

    async def log_play(self, file_id: int, session_id: str, user_id: Optional[str] = None, 
                      watch_duration: int = 0, completed: bool = False):
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO plays (file_id, user_id, session_id, watch_duration, completed)
                VALUES ($1, $2, $3, $4, $5)
            ''', file_id, user_id, session_id, watch_duration, completed)

    async def get_file_traffic(self, file_id: int, days: int = 30) -> Dict[str, Any]:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            since = datetime.datetime.utcnow() - datetime.timedelta(days=days)
            
            total_clicks = await conn.fetchval('SELECT COUNT(*) FROM clicks WHERE file_id = $1 AND created_at > $2', file_id, since)
            total_plays = await conn.fetchval('SELECT COUNT(*) FROM plays WHERE file_id = $1 AND created_at > $2', file_id, since)
            
            device_stats = await conn.fetch('''
                SELECT device_type, COUNT(*) as count FROM clicks WHERE file_id = $1 AND created_at > $2 AND device_type IS NOT NULL
                GROUP BY device_type
            ''', file_id, since)
            
            country_stats = await conn.fetch('''
                SELECT country_code, COUNT(*) as count FROM clicks WHERE file_id = $1 AND created_at > $2 AND country_code IS NOT NULL
                GROUP BY country_code ORDER BY count DESC LIMIT 10
            ''', file_id, since)
            
            referrer_stats = await conn.fetch('''
                SELECT referrer, COUNT(*) as count FROM clicks WHERE file_id = $1 AND created_at > $2 AND referrer IS NOT NULL
                GROUP BY referrer ORDER BY count DESC LIMIT 10
            ''', file_id, since)
            
            daily_stats = await conn.fetch('''
                SELECT DATE(created_at) as date, COUNT(*) as clicks FROM clicks WHERE file_id = $1 AND created_at > $2
                GROUP BY DATE(created_at) ORDER BY date
            ''', file_id, since)
            
            return {
                'total_clicks': total_clicks or 0,
                'total_plays': total_plays or 0,
                'device_stats': [dict(row) for row in device_stats],
                'country_stats': [dict(row) for row in country_stats],
                'referrer_stats': [dict(row) for row in referrer_stats],
                'daily_stats': [{'date': str(row['date']), 'clicks': row['clicks']} for row in daily_stats]
            }

    # ── Telegram session methods ──────────────────────────────────────────

    async def save_user_telegram_session(
        self,
        user_id: str,
        session_string: str,
        phone_number: Optional[str] = None,
        telegram_user_id: Optional[int] = None,
        telegram_username: Optional[str] = None
    ) -> bool:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO user_telegram_sessions
                    (user_id, session_string, phone_number, telegram_user_id, telegram_username)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (user_id) DO UPDATE
                    SET session_string = $2,
                        phone_number = COALESCE($3, user_telegram_sessions.phone_number),
                        telegram_user_id = COALESCE($4, user_telegram_sessions.telegram_user_id),
                        telegram_username = COALESCE($5, user_telegram_sessions.telegram_username),
                        updated_at = NOW()
            ''', user_id, session_string, phone_number, telegram_user_id, telegram_username)
        return True

    async def get_user_telegram_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT * FROM user_telegram_sessions WHERE user_id = $1', user_id
            )
            return dict(row) if row else None

    async def delete_user_telegram_session(self, user_id: str) -> bool:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            await conn.execute(
                'DELETE FROM user_telegram_sessions WHERE user_id = $1', user_id
            )
        return True

    async def close(self):
        if self._pool:
            await self._pool.close()
            print("   [OK] Database connection closed")

db: Optional[Database] = None

async def init_db() -> Database:
    global db
    db = Database(Config.DATABASE_URL)
    await db.connect()
    return db

def get_db() -> Optional[Database]:
    return db
