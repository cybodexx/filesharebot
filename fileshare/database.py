import datetime
import secrets
from typing import Optional, Dict, Any, List
import asyncpg
from Thunder.config import Config

class Database:
    def __init__(self, uri: str):
        self._uri = uri
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        if not self._uri:
            raise ValueError("DATABASE_URL is required")
        try:
            self._pool = await asyncpg.create_pool(self._uri, min_size=2, max_size=10)
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
                    delete_after_download BOOLEAN DEFAULT FALSE,
                    uploader_ip TEXT
                )
            ''')

            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_files_unique_code ON files(unique_code)
            ''')
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_files_expires_at ON files(expires_at)
            ''')
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_files_message_id ON files(message_id)
            ''')
            
            print("   [OK] Database tables ready")

    async def create_file_record(
        self,
        message_id: int,
        file_name: str,
        file_size: int,
        mime_type: Optional[str] = None,
        file_hash: Optional[str] = None,
        expires_days: Optional[int] = None,
        delete_after_download: bool = False,
        uploader_ip: Optional[str] = None
    ) -> str:
        if expires_days is None:
            expires_days = Config.LINK_EXPIRY_DAYS
            
        unique_code = secrets.token_urlsafe(16)
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=expires_days)
        
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO files (unique_code, message_id, file_name, file_size, mime_type, file_hash, expires_at, delete_after_download, uploader_ip)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ''', unique_code, message_id, file_name, file_size, mime_type, file_hash, expires_at, delete_after_download, uploader_ip)
        
        return unique_code

    async def get_file_by_code(self, unique_code: str) -> Optional[Dict[str, Any]]:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT id, unique_code, message_id, file_name, file_size, mime_type, file_hash,
                       created_at, expires_at, download_count, delete_after_download
                FROM files
                WHERE unique_code = $1
            ''', unique_code)
            return dict(row) if row else None

    async def increment_download_count(self, unique_code: str) -> bool:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            await conn.execute('''
                UPDATE files
                SET download_count = download_count + 1
                WHERE unique_code = $1
            ''', unique_code)
            return True

    async def delete_file_record(self, unique_code: str) -> bool:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            result = await conn.execute('DELETE FROM files WHERE unique_code = $1', unique_code)
            return "DELETE 1" in result

    async def delete_expired_files(self) -> List[int]:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT message_id FROM files WHERE expires_at < $1',
                datetime.datetime.utcnow()
            )
            message_ids = [row['message_id'] for row in rows]
            
            await conn.execute(
                'DELETE FROM files WHERE expires_at < $1',
                datetime.datetime.utcnow()
            )
            return message_ids

    async def get_all_files(self, limit: int = 100) -> List[Dict[str, Any]]:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT id, unique_code, message_id, file_name, file_size, mime_type,
                       created_at, expires_at, download_count
                FROM files
                ORDER BY created_at DESC
                LIMIT $1
            ''', limit)
            return [dict(row) for row in rows]

    async def get_stats(self) -> Dict[str, Any]:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            total_files = await conn.fetchval('SELECT COUNT(*) FROM files')
            total_size = await conn.fetchval('SELECT COALESCE(SUM(file_size), 0) FROM files')
            total_downloads = await conn.fetchval('SELECT COALESCE(SUM(download_count), 0) FROM files')
            
            return {
                'total_files': total_files,
                'total_size': total_size,
                'total_downloads': total_downloads
            }

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
