import asyncio
import hashlib
import secrets
import os
from typing import Optional, AsyncGenerator, Dict, Any, Union
from pyrogram import Client, utils
from pyrogram.types import Message
from pyrogram.errors import FloodWait, SessionPasswordNeeded
from Thunder.config import Config, safe_int

def get_peer_type_new(peer_id: int) -> str:
    peer_id_str = str(peer_id)
    if not peer_id_str.startswith("-"):
        return "user"
    elif peer_id_str.startswith("-100"):
        return "channel"
    else:
        return "chat"

utils.get_peer_type = get_peer_type_new

def get_telegram_config():
    return {
        'api_id': safe_int(os.getenv("API_ID"), 0),
        'api_hash': os.getenv("API_HASH", ""),
        'bot_token': os.getenv("BOT_TOKEN", ""),
        'bin_channel': safe_int(os.getenv("BIN_CHANNEL"), 0)
    }

# Cache of active user clients: {user_id: TelegramUserStorage}
_user_clients: Dict[str, 'TelegramUserStorage'] = {}

# Temporary OTP sessions: {phone_number: {client, phone_code_hash}}
_otp_sessions: Dict[str, Any] = {}


class TelegramStorage:
    """Bot-based storage using BIN_CHANNEL."""

    def __init__(self):
        self.client: Optional[Client] = None
        self.bot_username: str = ""
        self._started = False
        self._bin_channel: int = 0

    async def start(self):
        if self._started:
            return

        config = get_telegram_config()

        if not all([config['api_id'], config['api_hash'], config['bot_token'], config['bin_channel']]):
            raise ValueError("Missing Telegram configuration (API_ID, API_HASH, BOT_TOKEN, BIN_CHANNEL)")

        self._bin_channel = config['bin_channel']

        self.client = Client(
            name="thunder_bot",
            api_id=config['api_id'],
            api_hash=config['api_hash'],
            bot_token=config['bot_token'],
            in_memory=True,
            workers=8
        )

        try:
            await self.client.start()
        except FloodWait as e:
            await asyncio.sleep(int(e.value))
            await self.client.start()

        me = await self.client.get_me()
        self.bot_username = me.username or ""
        self._started = True
        print(f"   [OK] Telegram bot connected as @{self.bot_username}")

        try:
            chat = await self.client.get_chat(self._bin_channel)
            print(f"   [OK] Storage channel verified: {chat.title if hasattr(chat, 'title') else self._bin_channel}")
        except Exception as e:
            print(f"   [WARNING] Could not verify storage channel: {e}")
            print(f"   [INFO] Make sure the bot is added as admin to channel {self._bin_channel}")

    async def stop(self):
        if self.client and self._started:
            await self.client.stop()
            self._started = False

    async def upload_file(self, file_data: bytes, filename: str, mime_type: Optional[str] = None) -> Dict[str, Any]:
        if not self._started or not self.client:
            raise RuntimeError("Telegram client not started")

        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as tmp:
            tmp.write(file_data)
            tmp_path = tmp.name

        try:
            message = await self.client.send_document(
                chat_id=self._bin_channel,
                document=tmp_path,
                file_name=filename,
                caption=f"File: {filename}\nSize: {len(file_data)} bytes",
                force_document=True
            )

            if not message:
                raise RuntimeError("Failed to upload file to Telegram")

            return {
                'message_id': message.id,
                'chat_id': self._bin_channel,
                'storage_type': 'bot',
                'file_id': message.document.file_id if message.document else None,
                'file_unique_id': message.document.file_unique_id if message.document else None,
                'file_size': len(file_data),
                'file_hash': hashlib.sha256(file_data).hexdigest(),
                'mime_type': mime_type or (message.document.mime_type if message.document else 'application/octet-stream')
            }

        finally:
            os.unlink(tmp_path)

    async def get_file_info(self, message_id: int) -> Optional[Dict[str, Any]]:
        if not self._started or not self.client:
            raise RuntimeError("Telegram client not started")

        try:
            messages = await self.client.get_messages(self._bin_channel, message_id)
            message = messages[0] if isinstance(messages, list) else messages
            if not message or not message.document:
                return None

            return {
                'message_id': message.id,
                'file_id': message.document.file_id,
                'file_unique_id': message.document.file_unique_id,
                'file_size': message.document.file_size,
                'file_name': message.document.file_name,
                'mime_type': message.document.mime_type
            }
        except Exception as e:
            print(f"Error getting file info: {e}")
            return None

    async def stream_file(self, message_id: int, chunk_size: int = 1024 * 1024) -> AsyncGenerator[bytes, None]:
        if not self._started or not self.client:
            raise RuntimeError("Telegram client not started")

        try:
            messages = await self.client.get_messages(self._bin_channel, message_id)
            message = messages[0] if isinstance(messages, list) else messages
            if not message or not message.document:
                return

            async for chunk in self.client.stream_media(message, limit=chunk_size):
                if chunk:
                    yield chunk

        except FloodWait as e:
            await asyncio.sleep(int(e.value))
            async for chunk in self.stream_file(message_id, chunk_size):
                yield chunk
        except Exception as e:
            print(f"Error streaming file: {e}")
            return

    async def download_file(self, message_id: int, chat_id: Optional[int] = None) -> bytes:
        if not self._started or not self.client:
            raise RuntimeError("Telegram client not started")

        target_chat = chat_id or self._bin_channel

        try:
            messages = await self.client.get_messages(target_chat, message_id)
            message = messages[0] if isinstance(messages, list) else messages
            if not message or not message.document:
                raise RuntimeError("File not found")

            file_data = await self.client.download_media(message, in_memory=True)
            if file_data is None:
                raise RuntimeError("Failed to download file")

            if hasattr(file_data, 'getvalue'):
                return file_data.getvalue()
            elif isinstance(file_data, bytes):
                return file_data
            else:
                with open(file_data, 'rb') as f:
                    data = f.read()
                os.unlink(file_data)
                return data

        except FloodWait as e:
            await asyncio.sleep(int(e.value))
            return await self.download_file(message_id, chat_id)
        except Exception as e:
            print(f"Error downloading file: {e}")
            raise

    async def delete_file(self, message_id: int, chat_id: Optional[int] = None) -> bool:
        if not self.client or not self._started:
            return False

        target_chat = chat_id or self._bin_channel

        try:
            await self.client.delete_messages(target_chat, message_id)
            return True
        except Exception as e:
            print(f"Error deleting file: {e}")
            return False


class TelegramUserStorage:
    """Personal Telegram account storage using StringSession — unlimited storage."""

    def __init__(self, session_string: str):
        self.session_string = session_string
        self.client: Optional[Client] = None
        self._started = False
        self._me = None
        self._chat_id: Optional[int] = None

    async def start(self):
        if self._started:
            return

        config = get_telegram_config()
        self.client = Client(
            name="user_storage",
            api_id=config['api_id'],
            api_hash=config['api_hash'],
            session_string=self.session_string,
            in_memory=True,
            workers=4
        )

        try:
            await self.client.start()
        except FloodWait as e:
            await asyncio.sleep(int(e.value))
            await self.client.start()

        self._me = await self.client.get_me()
        self._chat_id = self._me.id
        self._started = True
        print(f"   [OK] User Telegram storage active for @{self._me.username or self._me.id}")

    async def stop(self):
        if self.client and self._started:
            try:
                await self.client.stop()
            except Exception:
                pass
            self._started = False

    @property
    def chat_id(self) -> Optional[int]:
        return self._chat_id

    async def upload_file(self, file_data: bytes, filename: str, mime_type: Optional[str] = None) -> Dict[str, Any]:
        if not self._started or not self.client:
            raise RuntimeError("User Telegram client not started")

        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as tmp:
            tmp.write(file_data)
            tmp_path = tmp.name

        try:
            message = await self.client.send_document(
                chat_id="me",
                document=tmp_path,
                file_name=filename,
                caption=f"📁 {filename}\n💾 {len(file_data)} bytes",
                force_document=True
            )

            if not message:
                raise RuntimeError("Failed to upload file")

            return {
                'message_id': message.id,
                'chat_id': self._chat_id,
                'storage_type': 'user',
                'file_size': len(file_data),
                'file_hash': hashlib.sha256(file_data).hexdigest(),
                'mime_type': mime_type or (message.document.mime_type if message.document else 'application/octet-stream')
            }
        finally:
            os.unlink(tmp_path)

    async def download_file(self, message_id: int) -> bytes:
        if not self._started or not self.client:
            raise RuntimeError("User Telegram client not started")

        try:
            messages = await self.client.get_messages("me", message_id)
            message = messages[0] if isinstance(messages, list) else messages
            if not message or not message.document:
                raise RuntimeError("File not found in Saved Messages")

            file_data = await self.client.download_media(message, in_memory=True)
            if file_data is None:
                raise RuntimeError("Failed to download file")

            if hasattr(file_data, 'getvalue'):
                return file_data.getvalue()
            elif isinstance(file_data, bytes):
                return file_data
            else:
                with open(file_data, 'rb') as f:
                    data = f.read()
                os.unlink(file_data)
                return data

        except FloodWait as e:
            await asyncio.sleep(int(e.value))
            return await self.download_file(message_id)
        except Exception as e:
            print(f"Error downloading from user storage: {e}")
            raise

    async def delete_file(self, message_id: int) -> bool:
        if not self.client or not self._started:
            return False
        try:
            await self.client.delete_messages("me", message_id)
            return True
        except Exception as e:
            print(f"Error deleting from user storage: {e}")
            return False


async def get_user_storage_client(user_id: str, session_string: str) -> TelegramUserStorage:
    """Get or create a cached user storage client."""
    if user_id in _user_clients:
        storage = _user_clients[user_id]
        if storage._started:
            return storage
        # Restart if stopped
        try:
            await storage.start()
            return storage
        except Exception:
            del _user_clients[user_id]

    storage = TelegramUserStorage(session_string)
    await storage.start()
    _user_clients[user_id] = storage
    return storage


async def remove_user_storage_client(user_id: str):
    """Stop and remove a cached user storage client."""
    if user_id in _user_clients:
        storage = _user_clients.pop(user_id)
        await storage.stop()


async def send_telegram_otp(phone_number: str) -> Dict[str, Any]:
    """Initiate OTP login for a phone number."""
    config = get_telegram_config()
    if not config['api_id'] or not config['api_hash']:
        return {'error': 'Telegram API not configured'}

    # Clean up any existing session for this phone
    if phone_number in _otp_sessions:
        old = _otp_sessions.pop(phone_number)
        try:
            await old['client'].disconnect()
        except Exception:
            pass

    try:
        client = Client(
            name=f"otp_{secrets.token_hex(4)}",
            api_id=config['api_id'],
            api_hash=config['api_hash'],
            in_memory=True
        )
        await client.connect()
        sent = await client.send_code(phone_number)
        _otp_sessions[phone_number] = {
            'client': client,
            'phone_code_hash': sent.phone_code_hash,
        }
        return {'success': True}
    except FloodWait as e:
        return {'error': f'Too many requests. Please wait {e.value} seconds.'}
    except Exception as e:
        return {'error': str(e)}


async def verify_telegram_otp(phone_number: str, code: str, password: Optional[str] = None) -> Dict[str, Any]:
    """Verify OTP and return session string."""
    if phone_number not in _otp_sessions:
        return {'error': 'No pending OTP for this number. Please request a new code.'}

    session_data = _otp_sessions[phone_number]
    client = session_data['client']

    try:
        await client.sign_in(phone_number, session_data['phone_code_hash'], code)
        session_string = await client.export_session_string()
        await client.disconnect()
        del _otp_sessions[phone_number]
        return {'success': True, 'session_string': session_string}

    except SessionPasswordNeeded:
        if password:
            try:
                await client.check_password(password)
                session_string = await client.export_session_string()
                await client.disconnect()
                del _otp_sessions[phone_number]
                return {'success': True, 'session_string': session_string}
            except Exception as e:
                return {'error': f'Wrong 2FA password: {e}'}
        return {'error': '2FA_REQUIRED', 'requires_2fa': True}

    except FloodWait as e:
        return {'error': f'Too many attempts. Wait {e.value} seconds.'}
    except Exception as e:
        return {'error': str(e)}


telegram_storage = TelegramStorage()
