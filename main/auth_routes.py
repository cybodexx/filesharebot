import datetime
from aiohttp import web
import aiohttp_jinja2
from Thunder.config import Config
from Thunder.auth import (
    register_user, login_user, logout_user,
    get_user_from_token, get_current_user,
    google_oauth_url, set_session_from_tokens
)

auth_routes = web.RouteTableDef()

def get_template_context():
    return {
        'config': Config,
        'now': datetime.datetime.utcnow(),
        'base_url': Config.get_base_url() or ''
    }

# ── Standard email/password auth ─────────────────────────────────────────────

@auth_routes.get("/auth/login")
async def login_page(request):
    user = get_current_user(request)
    if user:
        raise web.HTTPFound('/my/dashboard')
    next_url = request.query.get('next', '/')
    return aiohttp_jinja2.render_template('auth/login.html', request, {
        **get_template_context(),
        'active_page': 'login',
        'next': next_url
    })

@auth_routes.post("/auth/login")
async def login_submit(request):
    data = await request.post()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    next_url = data.get('next', '/my/dashboard')

    if not email or not password:
        return aiohttp_jinja2.render_template('auth/login.html', request, {
            **get_template_context(),
            'active_page': 'login',
            'error': 'Please enter email and password',
            'email': email
        })

    result = await login_user(email, password)

    if result.get('error'):
        return aiohttp_jinja2.render_template('auth/login.html', request, {
            **get_template_context(),
            'active_page': 'login',
            'error': result['error'],
            'email': email
        })

    response = web.HTTPFound(next_url)
    response.set_cookie('access_token', result['session']['access_token'],
                        max_age=3600 * 24 * 7, httponly=True, secure=True, samesite='Lax')
    response.set_cookie('refresh_token', result['session']['refresh_token'],
                        max_age=3600 * 24 * 30, httponly=True, secure=True, samesite='Lax')
    return response

@auth_routes.get("/auth/register")
async def register_page(request):
    user = get_current_user(request)
    if user:
        raise web.HTTPFound('/my/dashboard')
    return aiohttp_jinja2.render_template('auth/register.html', request, {
        **get_template_context(),
        'active_page': 'register'
    })

@auth_routes.post("/auth/register")
async def register_submit(request):
    data = await request.post()
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    confirm_password = data.get('confirm_password', '')

    ctx = {**get_template_context(), 'active_page': 'register',
           'username': username, 'email': email}

    if not username or not email or not password:
        return aiohttp_jinja2.render_template('auth/register.html', request,
                                              {**ctx, 'error': 'All fields are required'})
    if len(username) < 3:
        return aiohttp_jinja2.render_template('auth/register.html', request,
                                              {**ctx, 'error': 'Username must be at least 3 characters'})
    if len(password) < 6:
        return aiohttp_jinja2.render_template('auth/register.html', request,
                                              {**ctx, 'error': 'Password must be at least 6 characters'})
    if password != confirm_password:
        return aiohttp_jinja2.render_template('auth/register.html', request,
                                              {**ctx, 'error': 'Passwords do not match'})

    result = await register_user(email, password, username)

    if result.get('error'):
        return aiohttp_jinja2.render_template('auth/register.html', request,
                                              {**ctx, 'error': result['error']})

    return aiohttp_jinja2.render_template('auth/register.html', request, {
        **get_template_context(), 'active_page': 'register',
        'success': 'Account created! Please check your email to verify, then login.'
    })

@auth_routes.get("/auth/logout")
async def logout(request):
    access_token = request.cookies.get('access_token')
    if access_token:
        await logout_user(access_token)
    response = web.HTTPFound('/')
    response.del_cookie('access_token')
    response.del_cookie('refresh_token')
    return response

# ── Google OAuth ──────────────────────────────────────────────────────────────

@auth_routes.get("/auth/google")
async def google_login(request):
    base_url = Config.get_base_url() or ''
    redirect_to = f"{base_url}/auth/callback"
    try:
        url = await google_oauth_url(redirect_to)
    except Exception as e:
        err = str(e)
        if 'not enabled' in err.lower() or 'unsupported provider' in err.lower() or 'validation_failed' in err.lower():
            msg = 'Google login is not enabled yet. Please enable the Google provider in your Supabase dashboard under Authentication → Providers → Google.'
        else:
            msg = f'Google login failed: {err}'
        return aiohttp_jinja2.render_template('auth/login.html', request, {
            **get_template_context(),
            'active_page': 'login',
            'error': msg
        })
    if not url:
        return aiohttp_jinja2.render_template('auth/login.html', request, {
            **get_template_context(),
            'active_page': 'login',
            'error': 'Google login is not configured. Enable it in Supabase → Authentication → Providers → Google.'
        })
    raise web.HTTPFound(url)

@auth_routes.get("/auth/callback")
async def oauth_callback(request):
    """OAuth callback page — JS reads the URL fragment and calls /auth/set-session."""
    return aiohttp_jinja2.render_template('auth/callback.html', request, get_template_context())

@auth_routes.post("/auth/set-session")
async def set_session(request):
    """Receives access_token + refresh_token from the callback page JS."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({'error': 'Invalid request'}, status=400)

    access_token = data.get('access_token', '')
    refresh_token = data.get('refresh_token', '')

    if not access_token:
        return web.json_response({'error': 'No access token provided'}, status=400)

    result = await set_session_from_tokens(access_token, refresh_token)
    if not result:
        return web.json_response({'error': 'Failed to validate session with Supabase'}, status=401)

    # Ensure user exists in our DB
    from Thunder.database import get_db
    db = get_db()
    if db:
        u = result['user']
        await db.create_or_update_user(u['id'], u['email'], u['username'])

    response = web.json_response({'success': True, 'redirect': '/my/dashboard'})
    response.set_cookie('access_token', result['session']['access_token'],
                        max_age=3600 * 24 * 7, httponly=True, secure=True, samesite='Lax')
    response.set_cookie('refresh_token', result['session']['refresh_token'],
                        max_age=3600 * 24 * 30, httponly=True, secure=True, samesite='Lax')
    return response

# ── User pages ────────────────────────────────────────────────────────────────

@auth_routes.get("/my/dashboard")
async def user_dashboard(request):
    user = get_current_user(request)
    if not user:
        raise web.HTTPFound('/auth/login?next=/my/dashboard')

    from Thunder.database import get_db
    db = get_db()
    user_files = await db.get_user_files(user['id']) if db else []
    user_stats = await db.get_user_stats(user['id']) if db else {}
    tg_session = await db.get_user_telegram_session(user['id']) if db else None

    return aiohttp_jinja2.render_template('user/dashboard.html', request, {
        **get_template_context(),
        'active_page': 'my_dashboard',
        'user': user,
        'files': user_files,
        'stats': user_stats,
        'has_tg_session': tg_session is not None
    })

@auth_routes.get("/my/files")
async def user_files(request):
    user = get_current_user(request)
    if not user:
        raise web.HTTPFound('/auth/login?next=/my/files')

    from Thunder.database import get_db
    db = get_db()
    user_files = await db.get_user_files(user['id'], limit=100) if db else []

    return aiohttp_jinja2.render_template('user/files.html', request, {
        **get_template_context(),
        'active_page': 'my_files',
        'user': user,
        'files': user_files
    })

@auth_routes.get("/my/earnings")
async def user_earnings(request):
    user = get_current_user(request)
    if not user:
        raise web.HTTPFound('/auth/login?next=/my/earnings')

    from Thunder.database import get_db
    db = get_db()
    earnings = await db.get_user_earnings(user['id']) if db else {}

    return aiohttp_jinja2.render_template('user/earnings.html', request, {
        **get_template_context(),
        'active_page': 'my_earnings',
        'user': user,
        'earnings': earnings
    })

@auth_routes.get("/my/wallet")
async def user_wallet(request):
    user = get_current_user(request)
    if not user:
        raise web.HTTPFound('/auth/login?next=/my/wallet')

    from Thunder.database import get_db
    db = get_db()
    wallet = await db.get_user_wallet(user['id']) if db else None

    return aiohttp_jinja2.render_template('user/wallet.html', request, {
        **get_template_context(),
        'active_page': 'my_wallet',
        'user': user,
        'wallet': wallet
    })

@auth_routes.get("/my/profile")
async def user_profile(request):
    user = get_current_user(request)
    if not user:
        raise web.HTTPFound('/auth/login?next=/my/profile')

    return aiohttp_jinja2.render_template('user/profile.html', request, {
        **get_template_context(),
        'active_page': 'my_profile',
        'user': user
    })

# ── Telegram session management ───────────────────────────────────────────────

@auth_routes.get("/my/telegram-session")
async def telegram_session_page(request):
    user = get_current_user(request)
    if not user:
        raise web.HTTPFound('/auth/login?next=/my/telegram-session')

    from Thunder.database import get_db
    db = get_db()
    session = await db.get_user_telegram_session(user['id']) if db else None

    return aiohttp_jinja2.render_template('user/telegram_session.html', request, {
        **get_template_context(),
        'active_page': 'my_telegram',
        'user': user,
        'session_active': session is not None,
        'tg_username': session.get('telegram_username') if session else None,
        'tg_phone': session.get('phone_number') if session else None,
    })

@auth_routes.post("/my/telegram-session/save")
async def telegram_session_save(request):
    user = get_current_user(request)
    if not user:
        raise web.HTTPFound('/auth/login')

    data = await request.post()
    session_string = (data.get('session_string', '') or '').strip()

    if not session_string:
        return aiohttp_jinja2.render_template('user/telegram_session.html', request, {
            **get_template_context(),
            'active_page': 'my_telegram',
            'user': user,
            'session_active': False,
            'error': 'Session string cannot be empty.'
        })

    # Validate the session by trying to start a client
    from Thunder.telegram import TelegramUserStorage, remove_user_storage_client
    try:
        storage = TelegramUserStorage(session_string)
        await storage.start()
        tg_user = storage._me
        await storage.stop()
    except Exception as e:
        return aiohttp_jinja2.render_template('user/telegram_session.html', request, {
            **get_template_context(),
            'active_page': 'my_telegram',
            'user': user,
            'session_active': False,
            'error': f'Invalid session string: {e}'
        })

    from Thunder.database import get_db
    db = get_db()
    if db:
        await db.save_user_telegram_session(
            user_id=user['id'],
            session_string=session_string,
            telegram_user_id=tg_user.id if tg_user else None,
            telegram_username=tg_user.username if tg_user else None
        )
        # Invalidate any cached client so the new session is used
        await remove_user_storage_client(user['id'])

    raise web.HTTPFound('/my/telegram-session')

@auth_routes.post("/my/telegram-session/send-otp")
async def telegram_send_otp(request):
    user = get_current_user(request)
    if not user:
        return web.json_response({'error': 'Login required'}, status=401)

    try:
        data = await request.json()
    except Exception:
        return web.json_response({'error': 'Invalid request'}, status=400)

    phone = (data.get('phone') or '').strip()
    if not phone:
        return web.json_response({'error': 'Phone number is required'})

    from Thunder.telegram import send_telegram_otp
    result = await send_telegram_otp(phone)
    return web.json_response(result)

@auth_routes.post("/my/telegram-session/verify-otp")
async def telegram_verify_otp(request):
    user = get_current_user(request)
    if not user:
        return web.json_response({'error': 'Login required'}, status=401)

    try:
        data = await request.json()
    except Exception:
        return web.json_response({'error': 'Invalid request'}, status=400)

    phone = (data.get('phone') or '').strip()
    code = (data.get('code') or '').strip()
    password = data.get('password')

    if not phone or not code:
        return web.json_response({'error': 'Phone and code are required'})

    from Thunder.telegram import verify_telegram_otp, TelegramUserStorage, remove_user_storage_client
    result = await verify_telegram_otp(phone, code, password)

    if not result.get('success'):
        return web.json_response(result)

    session_string = result['session_string']

    # Get Telegram user info
    tg_id = None
    tg_username = None
    try:
        storage = TelegramUserStorage(session_string)
        await storage.start()
        if storage._me:
            tg_id = storage._me.id
            tg_username = storage._me.username
        await storage.stop()
    except Exception:
        pass

    from Thunder.database import get_db
    db = get_db()
    if db:
        await db.save_user_telegram_session(
            user_id=user['id'],
            session_string=session_string,
            phone_number=phone,
            telegram_user_id=tg_id,
            telegram_username=tg_username
        )
        await remove_user_storage_client(user['id'])

    return web.json_response({'success': True})

@auth_routes.post("/my/telegram-session/delete")
async def telegram_session_delete(request):
    user = get_current_user(request)
    if not user:
        raise web.HTTPFound('/auth/login')

    from Thunder.database import get_db
    from Thunder.telegram import remove_user_storage_client
    db = get_db()
    if db:
        await db.delete_user_telegram_session(user['id'])
    await remove_user_storage_client(user['id'])

    raise web.HTTPFound('/my/telegram-session')

# ── API endpoints ─────────────────────────────────────────────────────────────

@auth_routes.get("/api/user/stats")
async def api_user_stats(request):
    user = get_current_user(request)
    if not user:
        return web.json_response({'error': 'Authentication required'}, status=401)

    from Thunder.database import get_db
    db = get_db()
    stats = await db.get_user_stats(user['id']) if db else {}
    return web.json_response(stats)

@auth_routes.get("/api/user/earnings")
async def api_user_earnings(request):
    user = get_current_user(request)
    if not user:
        return web.json_response({'error': 'Authentication required'}, status=401)

    from Thunder.database import get_db
    db = get_db()
    earnings = await db.get_user_earnings(user['id']) if db else {}
    return web.json_response(earnings)
