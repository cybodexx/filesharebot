import asyncio
import hashlib
import secrets
from typing import Optional, AsyncGenerator, Dict, Any, Union
from pyrogram import Client, utils
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from Thunder.config import Config

def get_peer_type_new(peer_id: int) -> str:
    peer_id_str = str(peer_id)
    if not peer_id_str.startswith("-"):
        return "user"
    elif peer_id_str.startswith("-100"):
        return "channel"
    else:
        return "chat"

utils.get_peer_type = get_peer_type_new

class TelegramStorage:
    def __init__(self):
        self.client: Optional[Client] = None
        self.bot_username: str = ""
        self._started = False
    
    async def start(self):
        if self._started:
            return
            
        if not Config.validate_telegram_config():
            raise ValueError("Missing Telegram configuration (API_ID, API_HASH, BOT_TOKEN, BIN_CHANNEL)")
        
        self.client = Client(
            name="thunder_bot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
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
            chat = await self.client.get_chat(Config.BIN_CHANNEL)
            print(f"   [OK] Storage channel verified: {chat.title if hasattr(chat, 'title') else Config.BIN_CHANNEL}")
        except Exception as e:
            print(f"   [WARNING] Could not verify storage channel: {e}")
            print(f"   [INFO] Make sure the bot is added as admin to channel {Config.BIN_CHANNEL}")
    
    async def stop(self):
        if self.client and self._started:
            await self.client.stop()
            self._started = False
    
    async def upload_file(self, file_data: bytes, filename: str, mime_type: Optional[str] = None) -> Dict[str, Any]:
        if not self._started or not self.client:
            raise RuntimeError("Telegram client not started")
        
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as tmp:
            tmp.write(file_data)
            tmp_path = tmp.name
        
        try:
            message = await self.client.send_document(
                chat_id=Config.BIN_CHANNEL,
                document=tmp_path,
                file_name=filename,
                caption=f"File: {filename}\nSize: {len(file_data)} bytes",
                force_document=True
            )
            
            if not message:
                raise RuntimeError("Failed to upload file to Telegram")
            
            file_info = {
                'message_id': message.id,
                'file_id': message.document.file_id if message.document else None,
                'file_unique_id': message.document.file_unique_id if message.document else None,
                'file_size': len(file_data),
                'file_hash': hashlib.sha256(file_data).hexdigest(),
                'mime_type': mime_type or (message.document.mime_type if message.document else 'application/octet-stream')
            }
            
            return file_info
            
        finally:
            os.unlink(tmp_path)
    
    async def get_file_info(self, message_id: int) -> Optional[Dict[str, Any]]:
        if not self._started or not self.client:
            raise RuntimeError("Telegram client not started")
        
        try:
            messages = await self.client.get_messages(Config.BIN_CHANNEL, message_id)
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
            messages = await self.client.get_messages(Config.BIN_CHANNEL, message_id)
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
    
    async def delete_file(self, message_id: int) -> bool:
        if not self._started or not self.client:
            return False
        
        try:
            await self.client.delete_messages(Config.BIN_CHANNEL, message_id)
            return True
        except Exception as e:
            print(f"Error deleting file: {e}")
            return False

telegram_storage = TelegramStorage()
