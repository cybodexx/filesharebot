import mimetypes
import datetime
import io
import hashlib
from decimal import Decimal
from urllib.parse import quote
from aiohttp import web
import aiohttp_jinja2
import segno
from Thunder.config import Config
from Thunder.database import get_db

routes = web.RouteTableDef()

def json_safe(obj):
    """Convert an object to be JSON serializable."""
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [json_safe(item) for item in obj]
    elif isinstance(obj, Decimal):
        return int(obj) if obj == int(obj) else float(obj)
    elif isinstance(obj, datetime.datetime):
        return obj.isoformat()
    elif isinstance(obj, datetime.date):
        return obj.isoformat()
    else:
        return obj

def format_size(size_bytes) -> str:
    size = float(size_bytes)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"

def is_video_file(mime_type: str) -> bool:
    if not mime_type:
        return False
    video_mimes = ['video/mp4', 'video/webm', 'video/ogg', 'video/quicktime', 'video/x-msvideo', 'video/x-matroska']
    return mime_type.lower() in video_mimes

def is_audio_file(mime_type: str) -> bool:
    if not mime_type:
        return False
    audio_mimes = ['audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/ogg', 'audio/aac', 'audio/flac', 'audio/m4a']
    return mime_type.lower() in audio_mimes

def is_image_file(mime_type: str) -> bool:
    if not mime_type:
        return False
    image_mimes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml', 'image/bmp']
    return mime_type.lower() in image_mimes

def generate_qr_code(url: str) -> str:
    qr = segno.make(url)
    buffer = io.BytesIO()
    qr.save(buffer, kind='svg', scale=4, dark='#00f0ff', light='#ffffff')
    return buffer.getvalue().decode('utf-8')

def get_user_agent_info(user_agent: str) -> dict:
    ua_lower = user_agent.lower() if user_agent else ''
    device_type = 'desktop'
    browser = 'unknown'
    
    if 'mobile' in ua_lower or 'android' in ua_lower or 'iphone' in ua_lower:
        device_type = 'mobile'
    elif 'tablet' in ua_lower or 'ipad' in ua_lower:
        device_type = 'tablet'
    
    if 'chrome' in ua_lower:
        browser = 'Chrome'
    elif 'firefox' in ua_lower:
        browser = 'Firefox'
    elif 'safari' in ua_lower:
        browser = 'Safari'
    elif 'edge' in ua_lower:
        browser = 'Edge'
    
    return {'device_type': device_type, 'browser': browser}

def get_template_context(request=None):
    user = None
    if request:
        user = request.get('user')
    return {
        'config': Config,
        'format_size': format_size,
        'now': datetime.datetime.utcnow(),
        'base_url': Config.get_base_url() or '',
        'user': user
    }

@routes.get("/")
@aiohttp_jinja2.template('home.html')
async def home(request):
    db = get_db()
    stats = await db.get_stats() if db else {}
    
    return {
        **get_template_context(request),
        'active_page': 'home',
        'stats': stats
    }

@routes.get("/upload")
@aiohttp_jinja2.template('upload.html')
async def upload_page(request):
    user = request.get('user')
    if not user:
        raise web.HTTPFound('/auth/login?next=/upload')
    
    return {
        **get_template_context(request),
        'active_page': 'upload'
    }

@routes.get("/dashboard")
@aiohttp_jinja2.template('dashboard.html')
async def dashboard(request):
    db = get_db()
    stats = await db.get_stats() if db else {}
    files = await db.get_all_files(limit=50) if db else []
    dashboard_stats = await db.get_dashboard_stats(days=7) if db else {}
    activity = await db.get_activity_feed(limit=10) if db else []
    
    return {
        **get_template_context(request),
        'active_page': 'dashboard',
        'stats': stats,
        'files': files,
        'dashboard_stats': dashboard_stats,
        'activity': activity
    }

@routes.get("/playlists")
@aiohttp_jinja2.template('playlists.html')
async def playlists_page(request):
    db = get_db()
    playlists = await db.get_all_playlists() if db else []
    
    return {
        **get_template_context(request),
        'active_page': 'playlists',
        'playlists': playlists
    }

@routes.get("/playlist/{code}")
@aiohttp_jinja2.template('playlist_view.html')
async def playlist_view(request):
    code = request.match_info['code']
    db = get_db()
    
    playlist = await db.get_playlist_by_code(code) if db else None
    if not playlist:
        return aiohttp_jinja2.render_template('not_found.html', request, get_template_context(request))
    
    if playlist.get('password_hash'):
        session = await request.app.get('aiohttp_session', lambda r: {})(request)
        if session.get(f'playlist_auth_{code}') != True:
            return aiohttp_jinja2.render_template('password_required.html', request, {
                **get_template_context(request),
                'playlist_code': code
            })
    
    await db.increment_playlist_view_count(code)
    files = await db.get_playlist_files(code)
    
    return {
        **get_template_context(request),
        'active_page': 'playlists',
        'playlist': playlist,
        'files': files
    }

@routes.get("/f/{code}")
async def file_view(request):
    code = request.match_info['code']
    db = get_db()
    
    file_info = await db.get_file_by_code(code) if db else None
    if not file_info:
        return aiohttp_jinja2.render_template('not_found.html', request, get_template_context(request))
    
    if datetime.datetime.utcnow() > file_info['expires_at']:
        await db.delete_file_record(code)
        return aiohttp_jinja2.render_template('not_found.html', request, get_template_context(request))
    
    if file_info.get('is_protected'):
        session_key = f'file_auth_{code}'
        password_cookie = request.cookies.get(session_key)
        if password_cookie != file_info.get('password_hash'):
            return aiohttp_jinja2.render_template('password_required.html', request, {
                **get_template_context(request),
                'file_code': code
            })
    
    await db.increment_view_count(code)
    
    user_agent = request.headers.get('User-Agent', '')
    ua_info = get_user_agent_info(user_agent)
    
    await db.log_click(
        file_id=file_info['id'],
        ip_address=request.remote,
        device_type=ua_info['device_type'],
        referrer=request.headers.get('Referer')
    )
    
    await db.log_file_event(
        file_id=file_info['id'],
        event_type='view',
        ip_address=request.remote,
        user_agent=user_agent,
        referer=request.headers.get('Referer'),
        device_type=ua_info['device_type'],
        browser=ua_info['browser']
    )
    
    base_url = Config.get_base_url() or ''
    share_url = f"{base_url}/f/{code}"
    qr_code = generate_qr_code(share_url)
    
    return aiohttp_jinja2.render_template('file_view.html', request, {
        **get_template_context(request),
        'file': file_info,
        'is_video': is_video_file(file_info.get('mime_type')),
        'is_audio': is_audio_file(file_info.get('mime_type')),
        'is_image': is_image_file(file_info.get('mime_type')),
        'qr_code': qr_code,
        'share_url_encoded': quote(share_url, safe='')
    })

@routes.post("/f/{code}")
async def file_password_submit(request):
    code = request.match_info['code']
    db = get_db()
    
    file_info = await db.get_file_by_code(code) if db else None
    if not file_info:
        return aiohttp_jinja2.render_template('not_found.html', request, get_template_context())
    
    data = await request.post()
    password = data.get('password', '')
    
    if await db.verify_file_password(code, password):
        response = web.HTTPFound(f'/f/{code}')
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        response.set_cookie(f'file_auth_{code}', password_hash, max_age=86400)
        return response
    
    return aiohttp_jinja2.render_template('password_required.html', request, {
        **get_template_context(),
        'file_code': code,
        'error': 'Incorrect password. Please try again.'
    })

@routes.get("/dl/{code}")
async def download_file(request):
    code = request.match_info['code']
    db = get_db()
    
    file_info = await db.get_file_by_code(code) if db else None
    if not file_info:
        raise web.HTTPNotFound(text="File not found")
    
    if datetime.datetime.utcnow() > file_info['expires_at']:
        await db.delete_file_record(code)
        raise web.HTTPNotFound(text="File has expired")
    
    if file_info.get('is_protected'):
        session_key = f'file_auth_{code}'
        password_cookie = request.cookies.get(session_key)
        if password_cookie != file_info.get('password_hash'):
            raise web.HTTPUnauthorized(text="Password required")
    
    from Thunder.telegram import telegram_storage, get_user_storage_client

    storage_client = telegram_storage
    if file_info.get('storage_type') == 'user' and file_info.get('user_id'):
        user_session = await db.get_user_telegram_session(file_info['user_id'])
        if user_session:
            try:
                storage_client = await get_user_storage_client(file_info['user_id'], user_session['session_string'])
            except Exception as e:
                print(f"   [WARNING] Failed to get user storage client for download: {e}")

    try:
        file_data = await storage_client.download_file(file_info['message_id'])

        await db.increment_download_count(code)

        user_agent = request.headers.get('User-Agent', '')
        ua_info = get_user_agent_info(user_agent)
        await db.log_file_event(
            file_id=file_info['id'],
            event_type='download',
            ip_address=request.remote,
            user_agent=user_agent,
            referer=request.headers.get('Referer'),
            device_type=ua_info['device_type'],
            browser=ua_info['browser']
        )

        if file_info.get('delete_after_download'):
            await storage_client.delete_file(file_info['message_id'])
            await db.delete_file_record(code)
        
        headers = {
            'Content-Type': file_info.get('mime_type') or 'application/octet-stream',
            'Content-Disposition': f'attachment; filename="{quote(file_info["file_name"])}"',
            'Content-Length': str(len(file_data)),
            'Cache-Control': 'no-cache, no-store, must-revalidate'
        }
        
        return web.Response(body=file_data, headers=headers)
        
    except Exception as e:
        print(f"Download error: {e}")
        raise web.HTTPInternalServerError(text="Failed to download file")

@routes.get("/stream/{code}")
async def stream_file(request):
    code = request.match_info['code']
    db = get_db()
    
    file_info = await db.get_file_by_code(code) if db else None
    if not file_info:
        raise web.HTTPNotFound(text="File not found")
    
    if datetime.datetime.utcnow() > file_info['expires_at']:
        await db.delete_file_record(code)
        raise web.HTTPNotFound(text="File has expired")
    
    from Thunder.telegram import telegram_storage, get_user_storage_client

    storage_client = telegram_storage
    if file_info.get('storage_type') == 'user' and file_info.get('user_id'):
        user_session = await db.get_user_telegram_session(file_info['user_id'])
        if user_session:
            try:
                storage_client = await get_user_storage_client(file_info['user_id'], user_session['session_string'])
            except Exception as e:
                print(f"   [WARNING] Failed to get user storage client for stream: {e}")

    try:
        file_data = await storage_client.download_file(file_info['message_id'])

        await db.increment_play_count(code)
        
        headers = {
            'Content-Type': file_info.get('mime_type') or 'application/octet-stream',
            'Content-Length': str(len(file_data)),
            'Accept-Ranges': 'bytes',
            'Cache-Control': 'no-cache'
        }
        
        range_header = request.headers.get('Range')
        if range_header:
            try:
                range_spec = range_header.replace('bytes=', '')
                start, end = range_spec.split('-')
                start = int(start)
                end = int(end) if end else len(file_data) - 1
                
                headers['Content-Range'] = f'bytes {start}-{end}/{len(file_data)}'
                headers['Content-Length'] = str(end - start + 1)
                
                return web.Response(
                    body=file_data[start:end+1],
                    status=206,
                    headers=headers
                )
            except:
                pass
        
        return web.Response(body=file_data, headers=headers)
        
    except Exception as e:
        print(f"Stream error: {e}")
        raise web.HTTPInternalServerError(text="Failed to stream file")

@routes.post("/api/upload")
async def api_upload(request):
    db = get_db()
    if not db:
        return web.json_response({'error': 'Database not available'}, status=503)
    
    from Thunder.telegram import telegram_storage
    
    user = request.get('user')
    if not user:
        return web.json_response({'error': 'Login required to upload files'}, status=401)
    user_id = user.get('id')
    
    try:
        reader = await request.multipart()
        file_field = await reader.next()
        
        if not file_field or file_field.name != 'file':
            return web.json_response({'error': 'No file provided'}, status=400)
        
        filename = file_field.filename
        file_data = await file_field.read()
        
        if len(file_data) > Config.MAX_FILE_SIZE:
            return web.json_response({'error': f'File too large. Maximum size is {Config.MAX_FILE_SIZE_MB}MB'}, status=400)
        
        if user_id:
            can_upload = await db.check_user_storage_limit(user_id, len(file_data))
            if not can_upload:
                return web.json_response({'error': 'Storage limit exceeded. You have used all 100GB of your storage.'}, status=400)
        
        password = None
        expires_days = None
        is_private = True
        
        while True:
            field = await reader.next()
            if field is None:
                break
            if field.name == 'password':
                password = (await field.read()).decode('utf-8')
            elif field.name == 'expires_days':
                try:
                    expires_days = int((await field.read()).decode('utf-8'))
                except:
                    pass
            elif field.name == 'is_private':
                try:
                    is_private = (await field.read()).decode('utf-8').lower() == 'true'
                except:
                    pass
        
        mime_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        file_hash = hashlib.sha256(file_data).hexdigest()
        
        # Use personal Telegram storage if user has a session
        storage_client = telegram_storage
        tg_result = None
        if user_id:
            user_session = await db.get_user_telegram_session(user_id)
            if user_session:
                try:
                    from Thunder.telegram import get_user_storage_client
                    storage_client = await get_user_storage_client(user_id, user_session['session_string'])
                except Exception as e:
                    print(f"   [WARNING] Could not use user Telegram storage, falling back to bot: {e}")
                    storage_client = telegram_storage

        tg_result = await storage_client.upload_file(file_data, filename, mime_type)

        unique_code = await db.create_file_record(
            message_id=tg_result['message_id'],
            file_name=filename,
            file_size=len(file_data),
            mime_type=mime_type,
            file_hash=file_hash,
            expires_days=expires_days,
            uploader_ip=request.remote,
            password=password,
            user_id=user_id,
            is_private=is_private,
            storage_type=tg_result.get('storage_type', 'bot'),
            storage_chat_id=tg_result.get('chat_id')
        )
        
        base_url = Config.get_base_url() or ''
        share_url = f"{base_url}/f/{unique_code}"
        qr_code = generate_qr_code(share_url)
        
        return web.json_response({
            'success': True,
            'code': unique_code,
            'share_url': share_url,
            'download_url': f"{base_url}/dl/{unique_code}",
            'qr_code': qr_code,
            'file_name': filename,
            'file_size': len(file_data)
        })
        
    except Exception as e:
        print(f"Upload error: {e}")
        return web.json_response({'error': str(e)}, status=500)

@routes.delete("/api/files/{code}")
async def api_delete_file(request):
    code = request.match_info['code']
    db = get_db()
    
    if not db:
        return web.json_response({'error': 'Database not available'}, status=503)
    
    file_info = await db.get_file_by_code(code)
    if not file_info:
        return web.json_response({'error': 'File not found'}, status=404)
    
    from Thunder.telegram import telegram_storage
    
    try:
        await telegram_storage.delete_file(file_info['message_id'])
    except:
        pass
    
    await db.delete_file_record(code)
    
    return web.json_response({'success': True})

@routes.get("/api/files/{code}/analytics")
async def api_file_analytics(request):
    code = request.match_info['code']
    db = get_db()
    
    if not db:
        return web.json_response({'error': 'Database not available'}, status=503)
    
    file_info = await db.get_file_by_code(code)
    if not file_info:
        return web.json_response({'error': 'File not found'}, status=404)
    
    days = int(request.query.get('days', 30))
    analytics = await db.get_file_analytics(file_info['id'], days)
    
    return web.json_response(analytics)

@routes.post("/api/playlists")
async def api_create_playlist(request):
    db = get_db()
    if not db:
        return web.json_response({'error': 'Database not available'}, status=503)
    
    try:
        data = await request.json()
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        password = data.get('password')
        
        if not name:
            return web.json_response({'error': 'Playlist name is required'}, status=400)
        
        code = await db.create_playlist(
            name=name,
            description=description if description else None,
            password=password if password else None,
            creator_ip=request.remote
        )
        
        return web.json_response({
            'success': True,
            'code': code,
            'url': f"{Config.get_base_url()}/playlist/{code}"
        })
        
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

@routes.post("/api/playlists/{code}/files")
async def api_add_to_playlist(request):
    code = request.match_info['code']
    db = get_db()
    
    if not db:
        return web.json_response({'error': 'Database not available'}, status=503)
    
    try:
        data = await request.json()
        file_code = data.get('file_code', '').strip()
        
        if not file_code:
            return web.json_response({'error': 'File code is required'}, status=400)
        
        success = await db.add_file_to_playlist(code, file_code)
        
        if success:
            return web.json_response({'success': True})
        else:
            return web.json_response({'error': 'Playlist or file not found'}, status=404)
        
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

@routes.delete("/api/playlists/{code}/files/{file_code}")
async def api_remove_from_playlist(request):
    code = request.match_info['code']
    file_code = request.match_info['file_code']
    db = get_db()
    
    if not db:
        return web.json_response({'error': 'Database not available'}, status=503)
    
    success = await db.remove_file_from_playlist(code, file_code)
    
    if success:
        return web.json_response({'success': True})
    else:
        return web.json_response({'error': 'Not found'}, status=404)

@routes.get("/api/stats")
async def api_stats(request):
    db = get_db()
    if not db:
        return web.json_response({'error': 'Database not available'}, status=503)
    
    stats = await db.get_stats()
    return web.json_response(json_safe(stats))

@routes.get("/api/dashboard")
async def api_dashboard(request):
    db = get_db()
    if not db:
        return web.json_response({'error': 'Database not available'}, status=503)
    
    days = int(request.query.get('days', 7))
    stats = await db.get_dashboard_stats(days)
    return web.json_response(json_safe(stats))

@routes.get("/api/activity")
async def api_activity(request):
    db = get_db()
    if not db:
        return web.json_response({'error': 'Database not available'}, status=503)
    
    limit = int(request.query.get('limit', 20))
    activity = await db.get_activity_feed(limit)
    
    result = []
    for item in activity:
        result.append({
            'id': item['id'],
            'event_type': item['event_type'],
            'description': item['description'],
            'created_at': item['created_at'].isoformat() if item['created_at'] else None,
            'file_name': item.get('file_name'),
            'file_code': item.get('file_code'),
            'playlist_name': item.get('playlist_name'),
            'playlist_code': item.get('playlist_code')
        })
    
    return web.json_response(result)

@routes.post("/api/log-play")
async def api_log_play(request):
    db = get_db()
    if not db:
        return web.json_response({'error': 'Database not available'}, status=503)
    
    try:
        data = await request.json()
        code = data.get('code')
        duration = data.get('duration', 0)
        completed = data.get('completed', False)
        
        file_info = await db.get_file_by_code(code)
        if not file_info:
            return web.json_response({'error': 'File not found'}, status=404)
        
        import secrets as sec
        session_id = sec.token_urlsafe(8)
        
        await db.log_play(
            file_id=file_info['id'],
            session_id=session_id,
            watch_duration=duration,
            completed=completed
        )
        
        if file_info.get('user_id') and duration > 30:
            estimated_revenue = 0.0001 * (duration / 60)
            await db.record_earning(
                user_id=file_info['user_id'],
                file_id=file_info['id'],
                event_type='video_view',
                ad_impressions=1,
                estimated_revenue=estimated_revenue
            )
        
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

@routes.post("/api/wallet/update")
async def api_wallet_update(request):
    user = request.get('user')
    if not user:
        raise web.HTTPFound('/auth/login')
    
    db = get_db()
    if not db:
        return web.json_response({'error': 'Database not available'}, status=503)
    
    try:
        data = await request.post()
        ton_address = data.get('ton_address', '').strip()
        
        if ton_address:
            await db.update_user_wallet(user['id'], ton_address)
        
        raise web.HTTPFound('/my/wallet')
    except web.HTTPFound:
        raise
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

@routes.get("/status")
async def status(request):
    db = get_db()
    from Thunder.telegram import telegram_storage
    
    return web.json_response({
        'status': 'ok',
        'database': db is not None,
        'telegram': telegram_storage._started if telegram_storage else False,
        'version': '2.2.0'
    })

@routes.get("/static/{filepath:.*}")
async def static_files(request):
    filepath = request.match_info['filepath']
    import os
    
    static_dir = os.path.join(os.path.dirname(__file__), 'static')
    file_path = os.path.join(static_dir, filepath)
    
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        raise web.HTTPNotFound()
    
    content_type = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
    
    with open(file_path, 'rb') as f:
        content = f.read()
    
    return web.Response(body=content, content_type=content_type, headers={
        'Cache-Control': 'public, max-age=3600'
    })
