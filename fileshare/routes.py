import mimetypes
import datetime
from urllib.parse import quote
from aiohttp import web
from Thunder.config import Config
from Thunder.database import get_db

routes = web.RouteTableDef()

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

def get_home_page(stats = None) -> str:
    total_files = stats.get('total_files', 0) if stats else 0
    total_size = format_size(stats.get('total_size', 0)) if stats else '0 B'
    total_downloads = stats.get('total_downloads', 0) if stats else 0
    max_size = Config.MAX_FILE_SIZE_MB
    
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{Config.NAME}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 20px;
        }}
        .container {{
            max-width: 600px;
            width: 100%;
            margin-top: 40px;
        }}
        .card {{
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            padding: 40px;
            margin-bottom: 20px;
        }}
        h1 {{
            color: #333;
            font-size: 2rem;
            text-align: center;
            margin-bottom: 10px;
        }}
        .subtitle {{
            color: #666;
            text-align: center;
            margin-bottom: 30px;
            font-size: 1rem;
        }}
        .upload-area {{
            border: 3px dashed #ddd;
            border-radius: 12px;
            padding: 40px 20px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s ease;
            margin-bottom: 20px;
        }}
        .upload-area:hover, .upload-area.dragover {{
            border-color: #667eea;
            background: rgba(102, 126, 234, 0.05);
        }}
        .upload-area svg {{
            width: 60px;
            height: 60px;
            fill: #999;
            margin-bottom: 15px;
        }}
        .upload-area p {{
            color: #666;
            margin-bottom: 10px;
        }}
        .upload-area .browse {{
            color: #667eea;
            font-weight: 600;
            text-decoration: underline;
        }}
        .file-info {{
            display: none;
            background: #f8f9fa;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
        }}
        .file-info.visible {{
            display: block;
        }}
        .file-name {{
            font-weight: 600;
            color: #333;
            word-break: break-all;
        }}
        .file-size {{
            color: #666;
            font-size: 0.9rem;
        }}
        .progress-bar {{
            display: none;
            height: 8px;
            background: #eee;
            border-radius: 4px;
            margin-bottom: 20px;
            overflow: hidden;
        }}
        .progress-bar.visible {{
            display: block;
        }}
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #667eea, #764ba2);
            border-radius: 4px;
            transition: width 0.3s ease;
            width: 0%;
        }}
        .btn {{
            display: block;
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
        }}
        .btn:disabled {{
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }}
        .result {{
            display: none;
            margin-top: 20px;
        }}
        .result.visible {{
            display: block;
        }}
        .result-success {{
            background: #d4edda;
            border: 1px solid #c3e6cb;
            border-radius: 8px;
            padding: 20px;
        }}
        .result-success h3 {{
            color: #155724;
            margin-bottom: 10px;
        }}
        .link-box {{
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
        }}
        .link-input {{
            flex: 1;
            padding: 12px;
            border: 1px solid #c3e6cb;
            border-radius: 6px;
            font-size: 0.9rem;
        }}
        .copy-btn {{
            padding: 12px 20px;
            background: #28a745;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 600;
        }}
        .copy-btn:hover {{
            background: #218838;
        }}
        .result-error {{
            background: #f8d7da;
            border: 1px solid #f5c6cb;
            border-radius: 8px;
            padding: 20px;
            color: #721c24;
        }}
        .stats {{
            display: flex;
            justify-content: space-around;
            text-align: center;
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #eee;
        }}
        .stat-item h4 {{
            color: #667eea;
            font-size: 1.5rem;
        }}
        .stat-item p {{
            color: #666;
            font-size: 0.85rem;
        }}
        .info-text {{
            text-align: center;
            color: #666;
            font-size: 0.9rem;
            margin-top: 15px;
        }}
        #fileInput {{
            display: none;
        }}
        .new-upload {{
            display: none;
            width: 100%;
            padding: 12px;
            background: transparent;
            border: 2px solid #28a745;
            color: #28a745;
            border-radius: 8px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            margin-top: 10px;
        }}
        .new-upload.visible {{
            display: block;
        }}
        .upload-status {{
            text-align: center;
            color: #666;
            font-size: 0.9rem;
            margin-top: 10px;
            display: none;
        }}
        .upload-status.visible {{
            display: block;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1>{Config.NAME}</h1>
            <p class="subtitle">Share files up to {max_size}MB securely with expiring links</p>
            
            <div class="upload-area" id="uploadArea">
                <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path d="M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM14 13v4h-4v-4H7l5-5 5 5h-3z"/>
                </svg>
                <p>Drag and drop your file here</p>
                <p>or <span class="browse">browse</span> to choose</p>
            </div>
            
            <input type="file" id="fileInput">
            
            <div class="file-info" id="fileInfo">
                <div class="file-name" id="fileName"></div>
                <div class="file-size" id="fileSize"></div>
            </div>
            
            <div class="progress-bar" id="progressBar">
                <div class="progress-fill" id="progressFill"></div>
            </div>
            
            <div class="upload-status" id="uploadStatus">Uploading to cloud storage...</div>
            
            <button class="btn" id="uploadBtn" disabled>Upload File</button>
            
            <div class="result" id="result">
                <div class="result-success" id="resultSuccess">
                    <h3>File uploaded successfully!</h3>
                    <div class="link-box">
                        <input type="text" class="link-input" id="shareLink" readonly>
                        <button class="copy-btn" onclick="copyLink()">Copy</button>
                    </div>
                    <p style="color: #155724; font-size: 0.9rem;">Link expires in {Config.LINK_EXPIRY_DAYS} days</p>
                </div>
                <div class="result-error" id="resultError"></div>
            </div>
            
            <button class="new-upload" id="newUploadBtn" onclick="resetUpload()">Upload Another File</button>
            
            <div class="stats">
                <div class="stat-item">
                    <h4>{total_files}</h4>
                    <p>Files Shared</p>
                </div>
                <div class="stat-item">
                    <h4>{total_size}</h4>
                    <p>Total Size</p>
                </div>
                <div class="stat-item">
                    <h4>{total_downloads}</h4>
                    <p>Downloads</p>
                </div>
            </div>
            
            <p class="info-text">Files are automatically deleted after {Config.LINK_EXPIRY_DAYS} days</p>
        </div>
    </div>
    
    <script>
        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('fileInput');
        const fileInfo = document.getElementById('fileInfo');
        const fileName = document.getElementById('fileName');
        const fileSize = document.getElementById('fileSize');
        const progressBar = document.getElementById('progressBar');
        const progressFill = document.getElementById('progressFill');
        const uploadBtn = document.getElementById('uploadBtn');
        const uploadStatus = document.getElementById('uploadStatus');
        const result = document.getElementById('result');
        const resultSuccess = document.getElementById('resultSuccess');
        const resultError = document.getElementById('resultError');
        const shareLink = document.getElementById('shareLink');
        const newUploadBtn = document.getElementById('newUploadBtn');
        
        let selectedFile = null;
        const maxSize = {Config.MAX_FILE_SIZE};
        
        function formatBytes(bytes) {{
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }}
        
        uploadArea.addEventListener('click', () => fileInput.click());
        
        uploadArea.addEventListener('dragover', (e) => {{
            e.preventDefault();
            uploadArea.classList.add('dragover');
        }});
        
        uploadArea.addEventListener('dragleave', () => {{
            uploadArea.classList.remove('dragover');
        }});
        
        uploadArea.addEventListener('drop', (e) => {{
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            if (e.dataTransfer.files.length > 0) {{
                handleFile(e.dataTransfer.files[0]);
            }}
        }});
        
        fileInput.addEventListener('change', (e) => {{
            if (e.target.files.length > 0) {{
                handleFile(e.target.files[0]);
            }}
        }});
        
        function handleFile(file) {{
            if (file.size > maxSize) {{
                alert('File too large. Maximum size is {Config.MAX_FILE_SIZE_MB}MB');
                return;
            }}
            selectedFile = file;
            fileName.textContent = file.name;
            fileSize.textContent = formatBytes(file.size);
            fileInfo.classList.add('visible');
            uploadBtn.disabled = false;
            result.classList.remove('visible');
            newUploadBtn.classList.remove('visible');
        }}
        
        uploadBtn.addEventListener('click', async () => {{
            if (!selectedFile) return;
            
            uploadBtn.disabled = true;
            uploadBtn.textContent = 'Uploading...';
            progressBar.classList.add('visible');
            uploadStatus.classList.add('visible');
            
            const formData = new FormData();
            formData.append('file', selectedFile);
            
            const xhr = new XMLHttpRequest();
            
            xhr.upload.addEventListener('progress', (e) => {{
                if (e.lengthComputable) {{
                    const percent = (e.loaded / e.total) * 100;
                    progressFill.style.width = percent + '%';
                    if (percent >= 100) {{
                        uploadStatus.textContent = 'Processing file...';
                    }}
                }}
            }});
            
            xhr.addEventListener('load', () => {{
                progressBar.classList.remove('visible');
                uploadStatus.classList.remove('visible');
                result.classList.add('visible');
                
                if (xhr.status === 200) {{
                    const data = JSON.parse(xhr.responseText);
                    shareLink.value = data.share_url;
                    resultSuccess.style.display = 'block';
                    resultError.style.display = 'none';
                    newUploadBtn.classList.add('visible');
                    uploadBtn.style.display = 'none';
                }} else {{
                    let errorMsg = 'Upload failed. Please try again.';
                    try {{
                        const data = JSON.parse(xhr.responseText);
                        errorMsg = data.error || errorMsg;
                    }} catch (e) {{}}
                    resultError.textContent = errorMsg;
                    resultError.style.display = 'block';
                    resultSuccess.style.display = 'none';
                    uploadBtn.disabled = false;
                    uploadBtn.textContent = 'Upload File';
                }}
            }});
            
            xhr.addEventListener('error', () => {{
                progressBar.classList.remove('visible');
                uploadStatus.classList.remove('visible');
                result.classList.add('visible');
                resultError.textContent = 'Network error. Please try again.';
                resultError.style.display = 'block';
                resultSuccess.style.display = 'none';
                uploadBtn.disabled = false;
                uploadBtn.textContent = 'Upload File';
            }});
            
            xhr.open('POST', '/api/upload');
            xhr.send(formData);
        }});
        
        function copyLink() {{
            shareLink.select();
            document.execCommand('copy');
            const btn = document.querySelector('.copy-btn');
            btn.textContent = 'Copied!';
            setTimeout(() => btn.textContent = 'Copy', 2000);
        }}
        
        function resetUpload() {{
            selectedFile = null;
            fileInput.value = '';
            fileInfo.classList.remove('visible');
            result.classList.remove('visible');
            newUploadBtn.classList.remove('visible');
            progressFill.style.width = '0%';
            uploadBtn.disabled = true;
            uploadBtn.textContent = 'Upload File';
            uploadBtn.style.display = 'block';
        }}
    </script>
</body>
</html>'''

def get_download_page(file_info: dict, download_url: str) -> str:
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Download: {file_info['file_name']}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            min-height: 100vh;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }}
        .card {{
            background: white;
            padding: 40px;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            max-width: 450px;
            width: 100%;
            text-align: center;
        }}
        .file-icon {{
            width: 80px;
            height: 80px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 20px;
        }}
        .file-icon svg {{
            width: 40px;
            height: 40px;
            fill: white;
        }}
        h1 {{
            color: #333;
            font-size: 1.5rem;
            margin-bottom: 10px;
            word-break: break-all;
        }}
        .meta {{
            color: #666;
            margin-bottom: 25px;
        }}
        .meta span {{
            display: inline-block;
            margin: 0 10px;
        }}
        .btn {{
            display: inline-block;
            padding: 14px 40px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-size: 1rem;
            font-weight: 600;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
        }}
        .expires {{
            color: #999;
            font-size: 0.85rem;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="file-icon">
            <svg viewBox="0 0 24 24"><path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/></svg>
        </div>
        <h1>{file_info['file_name']}</h1>
        <div class="meta">
            <span>{format_size(file_info['file_size'])}</span>
            <span>|</span>
            <span>{file_info['download_count']} downloads</span>
        </div>
        <a href="{download_url}" class="btn" download>Download File</a>
        <p class="expires">Link expires: {file_info['expires_at'].strftime('%B %d, %Y')}</p>
    </div>
</body>
</html>'''

def get_video_page(file_info: dict, stream_url: str, download_url: str) -> str:
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Watch: {file_info['file_name']}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            min-height: 100vh;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }}
        .card {{
            background: white;
            padding: 30px;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            max-width: 800px;
            width: 100%;
            text-align: center;
        }}
        h1 {{
            color: #333;
            font-size: 1.3rem;
            margin-bottom: 20px;
            word-break: break-all;
        }}
        .video-container {{
            background: #000;
            border-radius: 12px;
            overflow: hidden;
            margin-bottom: 20px;
        }}
        video {{
            width: 100%;
            max-height: 450px;
            display: block;
        }}
        .meta {{
            color: #666;
            margin-bottom: 20px;
            font-size: 0.9rem;
        }}
        .meta span {{
            display: inline-block;
            margin: 0 10px;
        }}
        .btn {{
            display: inline-block;
            padding: 12px 30px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-size: 1rem;
            font-weight: 600;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
        }}
        .expires {{
            color: #999;
            font-size: 0.85rem;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="card">
        <h1>{file_info['file_name']}</h1>
        <div class="video-container">
            <video controls preload="metadata">
                <source src="{stream_url}" type="{file_info.get('mime_type') or 'video/mp4'}">
                Your browser does not support the video tag.
            </video>
        </div>
        <div class="meta">
            <span>{format_size(file_info['file_size'])}</span>
            <span>|</span>
            <span>{file_info['download_count']} views</span>
        </div>
        <a href="{download_url}" class="btn" download>Download Video</a>
        <p class="expires">Link expires: {file_info['expires_at'].strftime('%B %d, %Y')}</p>
    </div>
</body>
</html>'''

def get_not_found_page() -> str:
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>File Not Found</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
               display: flex; justify-content: center; align-items: center; min-height: 100vh;
               margin: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .container { text-align: center; background: white; padding: 50px; border-radius: 16px; 
                     box-shadow: 0 20px 60px rgba(0,0,0,0.3); max-width: 400px; }
        h1 { color: #e53e3e; margin-bottom: 15px; }
        p { color: #4a5568; line-height: 1.6; margin-bottom: 20px; }
        a { color: #667eea; text-decoration: none; font-weight: 600; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="container">
        <h1>File Not Found</h1>
        <p>This file doesn't exist or the link has expired.</p>
        <a href="/">Upload a new file</a>
    </div>
</body>
</html>'''

def get_expired_page() -> str:
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Link Expired</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
               display: flex; justify-content: center; align-items: center; min-height: 100vh;
               margin: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .container { text-align: center; background: white; padding: 50px; border-radius: 16px; 
                     box-shadow: 0 20px 60px rgba(0,0,0,0.3); max-width: 400px; }
        h1 { color: #dd6b20; margin-bottom: 15px; }
        p { color: #4a5568; line-height: 1.6; margin-bottom: 20px; }
        a { color: #667eea; text-decoration: none; font-weight: 600; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Link Expired</h1>
        <p>This download link has expired. Files are available for a limited time only.</p>
        <a href="/">Upload a new file</a>
    </div>
</body>
</html>'''


@routes.get("/")
async def home(request: web.Request):
    db = get_db()
    stats = await db.get_stats() if db else {}
    return web.Response(
        text=get_home_page(stats),
        content_type='text/html',
        headers={"Cache-Control": "no-cache"}
    )

@routes.post("/api/upload")
async def upload_file(request: web.Request):
    from Thunder.telegram import telegram_storage
    
    try:
        db = get_db()
        if not db:
            return web.json_response({'error': 'Database not available'}, status=500)
        
        if not telegram_storage._started:
            return web.json_response({'error': 'Storage service not available'}, status=500)
        
        reader = await request.multipart()
        field = await reader.next()
        
        if not field or field.name != 'file':
            return web.json_response({'error': 'No file provided'}, status=400)
        
        filename = field.filename or 'unnamed_file'
        
        file_data = b''
        while True:
            chunk = await field.read_chunk()
            if not chunk:
                break
            file_data += chunk
            if len(file_data) > Config.MAX_FILE_SIZE:
                return web.json_response({'error': f'File too large. Maximum size is {Config.MAX_FILE_SIZE_MB}MB'}, status=400)
        
        if not file_data:
            return web.json_response({'error': 'Empty file'}, status=400)
        
        mime_type, _ = mimetypes.guess_type(filename)
        
        file_info = await telegram_storage.upload_file(file_data, filename, mime_type)
        
        uploader_ip = request.headers.get('X-Forwarded-For', request.remote)
        
        unique_code = await db.create_file_record(
            message_id=file_info['message_id'],
            file_name=filename,
            file_size=file_info['file_size'],
            mime_type=file_info['mime_type'],
            file_hash=file_info['file_hash'],
            delete_after_download=Config.DELETE_AFTER_DOWNLOAD,
            uploader_ip=uploader_ip
        )
        
        base_url = Config.get_base_url()
        if not base_url:
            host = request.headers.get('Host', 'localhost')
            scheme = 'https' if request.headers.get('X-Forwarded-Proto') == 'https' else request.scheme
            base_url = f"{scheme}://{host}"
        
        share_url = f"{base_url}/f/{unique_code}"
        
        return web.json_response({
            'success': True,
            'share_url': share_url,
            'file_name': filename,
            'file_size': file_info['file_size'],
            'expires_days': Config.LINK_EXPIRY_DAYS
        })
        
    except Exception as e:
        print(f"Upload error: {e}")
        import traceback
        traceback.print_exc()
        return web.json_response({'error': 'Upload failed. Please try again.'}, status=500)

@routes.get("/f/{code}")
async def file_page(request: web.Request):
    code = request.match_info['code']
    db = get_db()
    
    if not db:
        return web.Response(text=get_not_found_page(), content_type='text/html', status=500)
    
    file_info = await db.get_file_by_code(code)
    
    if not file_info:
        return web.Response(text=get_not_found_page(), content_type='text/html', status=404)
    
    if file_info['expires_at'] < datetime.datetime.utcnow():
        from Thunder.telegram import telegram_storage
        await telegram_storage.delete_file(file_info['message_id'])
        await db.delete_file_record(code)
        return web.Response(text=get_expired_page(), content_type='text/html', status=410)
    
    download_url = f"/dl/{code}"
    
    if is_video_file(file_info.get('mime_type')):
        stream_url = f"/stream/{code}"
        return web.Response(
            text=get_video_page(file_info, stream_url, download_url),
            content_type='text/html',
            headers={"Cache-Control": "no-cache"}
        )
    
    return web.Response(
        text=get_download_page(file_info, download_url),
        content_type='text/html',
        headers={"Cache-Control": "no-cache"}
    )

@routes.get("/dl/{code}")
async def download_file(request: web.Request):
    from Thunder.telegram import telegram_storage
    
    code = request.match_info['code']
    db = get_db()
    
    if not db:
        raise web.HTTPInternalServerError(text="Database not available")
    
    file_info = await db.get_file_by_code(code)
    
    if not file_info:
        raise web.HTTPNotFound(text="File not found")
    
    if file_info['expires_at'] < datetime.datetime.utcnow():
        await telegram_storage.delete_file(file_info['message_id'])
        await db.delete_file_record(code)
        raise web.HTTPGone(text="Link expired")
    
    await db.increment_download_count(code)
    
    async def stream_response():
        async for chunk in telegram_storage.stream_file(file_info['message_id']):
            yield chunk
        
        if file_info.get('delete_after_download'):
            await telegram_storage.delete_file(file_info['message_id'])
            await db.delete_file_record(code)
    
    headers = {
        'Content-Type': file_info.get('mime_type') or 'application/octet-stream',
        'Content-Length': str(file_info['file_size']),
        'Content-Disposition': f"attachment; filename*=UTF-8''{quote(file_info['file_name'])}",
        'Cache-Control': 'no-cache'
    }
    
    return web.Response(
        body=stream_response(),
        headers=headers
    )

@routes.get("/stream/{code}")
async def stream_video(request: web.Request):
    from Thunder.telegram import telegram_storage
    
    code = request.match_info['code']
    db = get_db()
    
    if not db:
        raise web.HTTPInternalServerError(text="Database not available")
    
    file_info = await db.get_file_by_code(code)
    
    if not file_info:
        raise web.HTTPNotFound(text="File not found")
    
    if file_info['expires_at'] < datetime.datetime.utcnow():
        await telegram_storage.delete_file(file_info['message_id'])
        await db.delete_file_record(code)
        raise web.HTTPGone(text="Link expired")
    
    await db.increment_download_count(code)
    
    file_size = file_info['file_size']
    mime_type = file_info.get('mime_type') or 'video/mp4'
    
    range_header = request.headers.get('Range')
    
    if range_header:
        try:
            range_spec = range_header.replace('bytes=', '')
            
            if ',' in range_spec:
                raise web.HTTPRequestRangeNotSatisfiable(
                    headers={'Content-Range': f'bytes */{file_size}'}
                )
            
            range_parts = range_spec.split('-')
            
            if not range_parts[0] and range_parts[1]:
                suffix_length = int(range_parts[1])
                start = max(0, file_size - suffix_length)
                end = file_size - 1
            elif range_parts[0] and not range_parts[1]:
                start = int(range_parts[0])
                end = file_size - 1
            elif range_parts[0] and range_parts[1]:
                start = int(range_parts[0])
                end = int(range_parts[1])
            else:
                start = 0
                end = file_size - 1
            
            if start >= file_size or end >= file_size or start > end or start < 0:
                raise web.HTTPRequestRangeNotSatisfiable(
                    headers={'Content-Range': f'bytes */{file_size}'}
                )
            
            end = min(end, file_size - 1)
            content_length = end - start + 1
            
            async def stream_range():
                bytes_sent = 0
                async for chunk in telegram_storage.stream_file(file_info['message_id']):
                    chunk_start = bytes_sent
                    chunk_end = bytes_sent + len(chunk)
                    
                    if chunk_end <= start:
                        bytes_sent = chunk_end
                        continue
                    
                    if chunk_start > end:
                        break
                    
                    slice_start = max(0, start - chunk_start)
                    slice_end = min(len(chunk), end - chunk_start + 1)
                    
                    yield chunk[slice_start:slice_end]
                    bytes_sent = chunk_end
            
            headers = {
                'Content-Type': mime_type,
                'Content-Length': str(content_length),
                'Content-Range': f'bytes {start}-{end}/{file_size}',
                'Accept-Ranges': 'bytes',
                'Content-Disposition': f"inline; filename*=UTF-8''{quote(file_info['file_name'])}",
                'Cache-Control': 'no-cache'
            }
            
            return web.Response(
                status=206,
                body=stream_range(),
                headers=headers
            )
        except (ValueError, IndexError):
            pass
    
    async def stream_full():
        async for chunk in telegram_storage.stream_file(file_info['message_id']):
            yield chunk
    
    headers = {
        'Content-Type': mime_type,
        'Content-Length': str(file_size),
        'Content-Disposition': f"inline; filename*=UTF-8''{quote(file_info['file_name'])}",
        'Accept-Ranges': 'bytes',
        'Cache-Control': 'no-cache'
    }
    
    return web.Response(
        body=stream_full(),
        headers=headers
    )

@routes.get("/api/stats")
async def get_stats(request: web.Request):
    db = get_db()
    if not db:
        return web.json_response({'error': 'Database not available'}, status=500)
    
    stats = await db.get_stats()
    return web.json_response(stats)

@routes.get("/status")
async def status(request: web.Request):
    from Thunder.telegram import telegram_storage
    
    return web.json_response({
        'status': 'online',
        'name': Config.NAME,
        'telegram_connected': telegram_storage._started,
        'bot_username': telegram_storage.bot_username if telegram_storage._started else None,
        'max_file_size_mb': Config.MAX_FILE_SIZE_MB,
        'link_expiry_days': Config.LINK_EXPIRY_DAYS
    })
