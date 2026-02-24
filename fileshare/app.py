import asyncio
import os
from aiohttp import web
from Thunder.config import Config
from Thunder.routes import routes

VERSION = "2.1.0"

def print_banner():
    banner = f"""
======================================================
      THUNDER FILE SHARE v{VERSION}
      Web UI + Telegram Storage Backend
======================================================
"""
    print(banner)

async def cleanup_expired_files(app):
    from Thunder.database import get_db
    from Thunder.telegram import telegram_storage
    
    while True:
        try:
            await asyncio.sleep(3600)
            db = get_db()
            if db:
                expired_message_ids = await db.delete_expired_files()
                for message_id in expired_message_ids:
                    await telegram_storage.delete_file(message_id)
                if expired_message_ids:
                    print(f"   [CLEANUP] Removed {len(expired_message_ids)} expired files")
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"   [ERROR] Cleanup error: {e}")

async def on_startup(app):
    from Thunder.database import init_db
    from Thunder.telegram import telegram_storage
    
    print_banner()
    
    print("[1/3] Connecting to database...")
    await init_db()
    
    print("[2/3] Connecting to Telegram...")
    if Config.validate_telegram_config():
        try:
            await telegram_storage.start()
        except Exception as e:
            print(f"   [ERROR] Failed to connect to Telegram: {e}")
            raise
    else:
        print("   [ERROR] Missing Telegram configuration!")
        print("   Required: API_ID, API_HASH, BOT_TOKEN, BIN_CHANNEL")
        raise ValueError("Missing Telegram configuration")
    
    print("[3/3] Starting background tasks...")
    app['cleanup_task'] = asyncio.create_task(cleanup_expired_files(app))
    
    print("======================================================")
    print(f"   Server running on http://{Config.BIND_ADDRESS}:{Config.PORT}")
    print(f"   Max file size: {Config.MAX_FILE_SIZE_MB}MB")
    print(f"   Link expiry: {Config.LINK_EXPIRY_DAYS} days")
    if Config.FQDN:
        print(f"   Public URL: {Config.get_base_url()}")
    print("======================================================")

async def on_cleanup(app):
    from Thunder.database import get_db
    from Thunder.telegram import telegram_storage
    
    if 'cleanup_task' in app:
        app['cleanup_task'].cancel()
        try:
            await app['cleanup_task']
        except asyncio.CancelledError:
            pass
    
    await telegram_storage.stop()
    
    db = get_db()
    if db:
        await db.close()

def create_app():
    app = web.Application(client_max_size=Config.MAX_FILE_SIZE + 1024*1024)
    app.add_routes(routes)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app

def main():
    try:
        app = create_app()
        web.run_app(
            app,
            host=Config.BIND_ADDRESS,
            port=Config.PORT,
            print=None
        )
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Server stopped by user")
    except Exception as e:
        print(f"[ERROR] Failed to start: {e}")
        raise

if __name__ == "__main__":
    main()
