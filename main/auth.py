import os
import hashlib
import secrets
from typing import Optional, Dict, Any
from functools import wraps
from aiohttp import web
import aiohttp_jinja2
from supabase import create_client, Client

_supabase_client: Optional[Client] = None

def get_supabase() -> Optional[Client]:
    global _supabase_client
    return _supabase_client

def init_supabase() -> bool:
    global _supabase_client
    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_KEY", "")
    
    if not supabase_url or not supabase_key:
        print("   [WARNING] Supabase credentials not configured")
        return False
    
    try:
        _supabase_client = create_client(supabase_url, supabase_key)
        print("   [OK] Supabase client initialized")
        return True
    except Exception as e:
        print(f"   [ERROR] Failed to initialize Supabase: {e}")
        return False

async def register_user(email: str, password: str, username: str) -> Dict[str, Any]:
    client = get_supabase()
    if not client:
        return {"error": "Supabase not configured"}
    
    try:
        response = client.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {
                    "username": username,
                    "storage_limit": 100 * 1024 * 1024 * 1024,
                    "storage_used": 0
                }
            }
        })
        
        if response.user:
            return {
                "success": True,
                "user": {
                    "id": response.user.id,
                    "email": response.user.email,
                    "username": username
                }
            }
        return {"error": "Registration failed"}
    except Exception as e:
        return {"error": str(e)}

async def login_user(email: str, password: str) -> Dict[str, Any]:
    client = get_supabase()
    if not client:
        return {"error": "Supabase not configured"}
    
    try:
        response = client.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if response.user and response.session:
            return {
                "success": True,
                "user": {
                    "id": response.user.id,
                    "email": response.user.email,
                    "username": response.user.user_metadata.get("username", "User"),
                    "storage_limit": response.user.user_metadata.get("storage_limit", 100 * 1024 * 1024 * 1024),
                    "storage_used": response.user.user_metadata.get("storage_used", 0)
                },
                "session": {
                    "access_token": response.session.access_token,
                    "refresh_token": response.session.refresh_token,
                    "expires_at": response.session.expires_at
                }
            }
        return {"error": "Invalid credentials"}
    except Exception as e:
        error_msg = str(e)
        if "Invalid login credentials" in error_msg:
            return {"error": "Invalid email or password"}
        return {"error": error_msg}

async def logout_user(access_token: str) -> Dict[str, Any]:
    client = get_supabase()
    if not client:
        return {"error": "Supabase not configured"}
    
    try:
        client.auth.sign_out()
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}

async def get_user_from_token(access_token: str) -> Optional[Dict[str, Any]]:
    client = get_supabase()
    if not client or not access_token:
        return None
    
    try:
        response = client.auth.get_user(access_token)
        if response.user:
            return {
                "id": response.user.id,
                "email": response.user.email,
                "username": response.user.user_metadata.get("username", "User"),
                "storage_limit": response.user.user_metadata.get("storage_limit", 100 * 1024 * 1024 * 1024),
                "storage_used": response.user.user_metadata.get("storage_used", 0)
            }
        return None
    except Exception as e:
        return None

async def refresh_session(refresh_token: str) -> Dict[str, Any]:
    client = get_supabase()
    if not client:
        return {"error": "Supabase not configured"}
    
    try:
        response = client.auth.refresh_session(refresh_token)
        if response.session:
            return {
                "success": True,
                "session": {
                    "access_token": response.session.access_token,
                    "refresh_token": response.session.refresh_token,
                    "expires_at": response.session.expires_at
                }
            }
        return {"error": "Session refresh failed"}
    except Exception as e:
        return {"error": str(e)}

async def google_oauth_url(redirect_to: str) -> Optional[str]:
    """Get Google OAuth redirect URL via Supabase. Raises on Supabase errors."""
    client = get_supabase()
    if not client:
        return None
    # Let the exception propagate so callers can show specific error messages
    response = client.auth.sign_in_with_oauth({
        "provider": "google",
        "options": {
            "redirect_to": redirect_to,
            "query_params": {"access_type": "offline", "prompt": "consent"}
        }
    })
    return response.url

async def set_session_from_tokens(access_token: str, refresh_token: str) -> Optional[Dict[str, Any]]:
    """Set session from OAuth tokens (used after Google callback)."""
    client = get_supabase()
    if not client:
        return None
    try:
        response = client.auth.set_session(access_token, refresh_token)
        if response.user and response.session:
            meta = response.user.user_metadata or {}
            username = (
                meta.get("username")
                or meta.get("full_name")
                or meta.get("name")
                or (response.user.email or "").split("@")[0]
            )
            return {
                "user": {
                    "id": response.user.id,
                    "email": response.user.email,
                    "username": username,
                    "storage_limit": meta.get("storage_limit", 100 * 1024 * 1024 * 1024),
                    "storage_used": meta.get("storage_used", 0)
                },
                "session": {
                    "access_token": response.session.access_token,
                    "refresh_token": response.session.refresh_token,
                    "expires_at": response.session.expires_at
                }
            }
        return None
    except Exception as e:
        print(f"   [ERROR] Set session from tokens: {e}")
        return None

def get_current_user(request: web.Request) -> Optional[Dict[str, Any]]:
    return request.get('user')

def login_required(f):
    @wraps(f)
    async def decorated(request, *args, **kwargs):
        user = get_current_user(request)
        if not user:
            raise web.HTTPFound('/auth/login?next=' + str(request.path))
        return await f(request, *args, **kwargs)
    return decorated

def api_login_required(f):
    @wraps(f)
    async def decorated(request, *args, **kwargs):
        user = get_current_user(request)
        if not user:
            return web.json_response({"error": "Authentication required"}, status=401)
        return await f(request, *args, **kwargs)
    return decorated
