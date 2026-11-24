"""第一阶段：数据库持久化、账户会话和用户隔离的课程管理。"""
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
import json
import logging
from contextlib import contextmanager
from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from backend.materials import extract, selected_units
from backend import ai
from typing import Literal


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=10, max_length=128)


class CourseInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)


class ChapterInput(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    unit_index: int = Field(ge=0)
    end_unit_index: int | None = Field(default=None, ge=0)
    included: bool = True


class ChaptersInput(BaseModel):
    chapters: list[ChapterInput] = Field(max_length=100)


class OutlineInput(BaseModel):
    chapter_keys: list[str] | None = Field(default=None, min_length=1, max_length=2000)
    material_ids: list[str] = Field(min_length=1, max_length=20)
    goal: str = Field(default='', max_length=1000)
    detail: Literal['精简', '详细'] = '精简'


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def create_app(db_path=None):
    path = Path(db_path or os.getenv("STUDY_DB", "data/app.db"))
    path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def db():
        conn = sqlite3.connect(path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
          salt TEXT NOT NULL, password_hash TEXT NOT NULL,
          role TEXT NOT NULL DEFAULT 'user', active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS sessions(
          token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS courses(
          id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id),
          name TEXT NOT NULL, description TEXT NOT NULL, created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS materials(
          id TEXT PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id),
          course_id INTEGER NOT NULL REFERENCES courses(id), name TEXT NOT NULL,
          suffix TEXT NOT NULL, size INTEGER NOT NULL, status TEXT NOT NULL,
          message TEXT NOT NULL DEFAULT '', units TEXT NOT NULL DEFAULT '[]',
          chapters TEXT NOT NULL DEFAULT '[]', confirmed INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS outlines(
          id TEXT PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id),
          course_id INTEGER NOT NULL REFERENCES courses(id), status TEXT NOT NULL,
          goal TEXT NOT NULL, detail TEXT NOT NULL, model TEXT NOT NULL,
          sources TEXT NOT NULL, versions TEXT NOT NULL, result TEXT,
          message TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL);
        """)

    with db() as conn:
        if 'selected_chapters' not in {row['name'] for row in conn.execute('PRAGMA table_info(outlines)')}:
            conn.execute("ALTER TABLE outlines ADD COLUMN selected_chapters TEXT NOT NULL DEFAULT '[]'")

    app = FastAPI(title="过了么 API", version="0.24.0")
    frontend = Path(__file__).resolve().parent.parent / "frontend"
    app.mount("/static", StaticFiles(directory=frontend), name="static")

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(frontend / "index.html")

    @app.middleware("http")
    async def origin_check(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin and origin != str(request.base_url).rstrip("/"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "不接受跨站写入"}, status_code=403)
        return await call_next(request)

    def current_user(study_session: str | None = Cookie(default=None)):
        if not study_session:
            raise HTTPException(401, "请先登录")
        with db() as conn:
            user = conn.execute("""SELECT u.id,u.username,u.role FROM users u JOIN sessions s
                ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>? AND u.active=1""",
                (hashlib.sha256(study_session.encode()).hexdigest(), time.time())).fetchone()
        if not user:
            raise HTTPException(401, "登录已失效")
        return dict(user)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "stage": "sample-only-exams", "capabilities": ["sample-only-exams"]}

    @app.post("/api/auth/register", status_code=201)
    def register(body: Credentials):
        salt = secrets.token_hex(16)
        with db() as conn:
            try:
                conn.execute("INSERT INTO users(username,salt,password_hash) VALUES(?,?,?)",
                    (body.username, salt, password_hash(body.password, salt)))
            except sqlite3.IntegrityError:
                raise HTTPException(409, "用户名已存在")
        return {"message": "注册成功，请登录"}

    @app.post("/api/auth/login")
    def login(body: Credentials, response: Response):
        with db() as conn:
            user = conn.execute("SELECT * FROM users WHERE username=?", (body.username,)).fetchone()
            salt = user["salt"] if user else "00" * 16
            calculated = password_hash(body.password, salt)
            if not user or not hmac.compare_digest(calculated, user["password_hash"]) or not user["active"]:
                raise HTTPException(401, "账户或密码错误")
            token = secrets.token_urlsafe(32)
            conn.execute("DELETE FROM sessions WHERE expires<=?", (time.time(),))
            conn.execute("INSERT INTO sessions VALUES(?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), user["id"], time.time()+86400))
        response.set_cookie("study_session", token, httponly=True, samesite="strict", max_age=86400,
                            secure=os.getenv("STUDY_SECURE_COOKIE") == "1")
        return {"id": user["id"], "username": user["username"], "role": user["role"]}

    @app.post("/api/auth/logout")
    def logout(response: Response, study_session: str | None = Cookie(default=None)):
        if study_session:
            with db() as conn:
                conn.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(study_session.encode()).hexdigest(),))
        response.delete_cookie("study_session")
        return {"message": "已退出"}

    @app.get("/api/auth/me")
    def me(user=Depends(current_user)):
        return user

    @app.get("/api/courses")
    def courses(user=Depends(current_user)):
        with db() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM courses WHERE owner_id=? ORDER BY id DESC", (user["id"],))]

    @app.post("/api/courses", status_code=201)
    def add_course(body: CourseInput, user=Depends(current_user)):
        if not body.name.strip():
            raise HTTPException(422, "课程名称不能为空")
        with db() as conn:
            cursor = conn.execute("INSERT INTO courses(owner_id,name,description,created_at) VALUES(?,?,?,?)",
                (user["id"], body.name.strip(), body.description, time.time()))
            return {"id": cursor.lastrowid, "name": body.name.strip(), "description": body.description}

    @app.get("/api/courses/{course_id}")
    def get_course(course_id: int, user=Depends(current_user)):
        with db() as conn:
            row = conn.execute("SELECT * FROM courses WHERE id=? AND owner_id=?", (course_id,user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "课程不存在")
        return dict(row)

    @app.put("/api/courses/{course_id}")
    def update_course(course_id: int, body: CourseInput, user=Depends(current_user)):
        if not body.name.strip():
            raise HTTPException(422, "课程名称不能为空")
        with db() as conn:
            cursor = conn.execute("UPDATE courses SET name=?,description=? WHERE id=? AND owner_id=?",
                                  (body.name.strip(), body.description, course_id, user["id"]))
            if cursor.rowcount == 0:
                raise HTTPException(404, "课程不存在")
        return {"id": course_id, "name": body.name.strip(), "description": body.description}

    uploads = path.parent / 'uploads'
    uploads.mkdir(exist_ok=True)

    def owned_material(material_id, user):
        with db() as conn:
            row = conn.execute('SELECT * FROM materials WHERE id=? AND owner_id=?', (material_id, user['id'])).fetchone()
        if not row:
            raise HTTPException(404, '资料不存在')
        return dict(row)

    def parse_material(material):
        try:
            units = extract(uploads / (material['id'] + material['suffix']), material['suffix'])
            has_text = any(u['text'].strip() for u in units)
            status = 'ready' if has_text else 'needs_ocr'
            message = '文字已提取。请添加章节范围，或选择“整份资料作为一章”，再保存并确认。图片与复杂公式可能遗漏。' if has_text else '没有提取到文字，可能需要OCR；该功能尚未接入。'
            chapters = []
        except Exception as error:
            logging.getLogger(__name__).warning('Material parse failed: %s', type(error).__name__)
            units, chapters = [], []
            status = 'needs_ocr' if material['suffix'] in ('.png','.jpg','.jpeg') else 'failed'
            message = str(error) if isinstance(error, ValueError) else '文件解析失败，请确认文件未损坏且格式正确。'
        with db() as conn:
            conn.execute('UPDATE materials SET status=?,message=?,units=?,chapters=?,confirmed=0 WHERE id=? AND confirmed=0',
                         (status,message,json.dumps(units,ensure_ascii=False),json.dumps(chapters,ensure_ascii=False),material['id']))

    @app.get('/api/courses/{course_id}/materials')
    def list_materials(course_id: int, user=Depends(current_user)):
        get_course(course_id, user)
        with db() as conn:
            return [dict(r) for r in conn.execute('SELECT id,name,suffix,size,status,message,confirmed FROM materials WHERE course_id=? AND owner_id=? ORDER BY rowid DESC', (course_id,user['id']))]

    @app.post('/api/courses/{course_id}/materials', status_code=201)
    async def upload_material(course_id: int, request: Request, name: str, user=Depends(current_user)):
        get_course(course_id,user)
        name = name.replace('\\','/').split('/')[-1]
        suffix = Path(name).suffix.lower()
        if not name or len(name)>200 or suffix not in ('.pdf','.docx','.pptx','.png','.jpg','.jpeg'):
            raise HTTPException(422,'请选择PDF、DOCX、PPTX、JPG或PNG文件')
        material_id = secrets.token_hex(16)
        target = uploads / (material_id+suffix)
        size = 0
        try:
            with target.open('xb') as stream:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > 30*1024*1024:
                        raise HTTPException(413,'单个文件不能超过30MB')
                    stream.write(chunk)
            if not size:
                raise HTTPException(422,'不能上传空文件')
            with db() as conn:
                conn.execute('BEGIN IMMEDIATE')
                used = conn.execute('SELECT COALESCE(SUM(size),0) FROM materials WHERE owner_id=?',(user['id'],)).fetchone()[0]
                if used+size>500*1024*1024:
                    raise HTTPException(413,'账户资料总容量不能超过500MB')
                conn.execute('INSERT INTO materials(id,owner_id,course_id,name,suffix,size,status) VALUES(?,?,?,?,?,?,?)',
                             (material_id,user['id'],course_id,name,suffix,size,'uploaded'))
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return {'id':material_id,'status':'uploaded'}

    @app.post('/api/materials/{material_id}/parse')
    def parse(material_id: str, user=Depends(current_user)):
        material = owned_material(material_id,user)
        if material['confirmed']:
            raise HTTPException(409,'已确认的资料不重复解析，请上传新版本')
        parse_material(material)
        return {'message':'解析处理完成，请查看资料状态'}

    @app.get('/api/materials/{material_id}')
    def detail(material_id: str, user=Depends(current_user)):
        material = owned_material(material_id,user)
        material['units'] = json.loads(material['units'])
        # Unconfirmed legacy chapters were automatic suggestions, not user choices.
        material['chapters'] = json.loads(material['chapters']) if material['confirmed'] else []
        if material['status'] == 'ready' and not material['confirmed']:
            material['message'] = '文字已提取，尚未保存复习范围。请添加范围或将整份资料作为一章，再保存并确认。'
        for chapter in material['chapters']:
            # Old records only contain a start position. Do not invent a range.
            if chapter.get('end_unit_index') is None:
                chapter['end_unit_index'] = chapter['unit_index']
                chapter['range_needs_review'] = True
        return material

    @app.post('/api/materials/{material_id}/refresh-text')
    def refresh_text(material_id: str, user=Depends(current_user)):
        material = owned_material(material_id, user)
        if material['status'] != 'ready':
            raise HTTPException(409, '请先使用提取文字功能')
        try:
            units = extract(uploads / (material_id + material['suffix']), material['suffix'])
        except Exception:
            raise HTTPException(422, '重新提取失败，原有文字和章节均已保留')
        old_units = json.loads(material['units'])
        if len(units) != len(old_units):
            raise HTTPException(409, '原文位置数量发生变化，已保留旧内容；请将文件作为新资料上传')
        for old, new in zip(old_units, units):
            if old.get('vision_review'):
                new['text'] = old['text']
                new['vision_review'] = old['vision_review']
        with db() as conn:
            changed = conn.execute('UPDATE materials SET units=? WHERE id=? AND units=?', (json.dumps(units, ensure_ascii=False), material_id, material['units'])).rowcount
            if not changed:
                raise HTTPException(409, '提取期间文字已被校对，已保留新校对内容，请刷新查看')
        return {'message': '文字已更新，章节设置保留'}

    @app.get('/api/materials/{material_id}/download')
    def download(material_id: str, user=Depends(current_user)):
        material = owned_material(material_id,user)
        return FileResponse(uploads / (material_id+material['suffix']),filename=material['name'],media_type='application/octet-stream')

    @app.get('/api/materials/{material_id}/selected-content')
    def selected_content(material_id: str, user=Depends(current_user)):
        material = owned_material(material_id, user)
        if not material['confirmed']:
            raise HTTPException(409, '请先保存并确认范围')
        return {'units': selected_units(json.loads(material['units']), json.loads(material['chapters']))}

    @app.put('/api/materials/{material_id}/chapters')
    def save_chapters(material_id: str, body: ChaptersInput, user=Depends(current_user)):
        material = owned_material(material_id,user)
        if material['status'] != 'ready':
            raise HTTPException(409,'资料尚未成功提取文字')
        count = len(json.loads(material['units']))
        for chapter in body.chapters:
            if chapter.end_unit_index is None:
                chapter.end_unit_index = chapter.unit_index
            if not chapter.unit_index <= chapter.end_unit_index < count:
                raise HTTPException(422, '结束位置必须不早于起始位置，且不能超过资料末尾')
        if not body.chapters or any(not c.title.strip() or c.unit_index>=count for c in body.chapters):
            raise HTTPException(422,'至少添加一个有效章节，并选择对应原文位置')
        with db() as conn:
            conn.execute('UPDATE materials SET chapters=?,confirmed=1 WHERE id=?', (json.dumps([c.model_dump() for c in body.chapters],ensure_ascii=False),material_id))
        return {'message':'章节与纳入范围已保存'}

    def material_version(material):
        payload = json.dumps([material['name'], material['units'], material['chapters']], ensure_ascii=False)
        return hashlib.sha256(payload.encode()).hexdigest()

    def chapter_ranges(material):
        if material['status'] != 'ready' or not material['confirmed']:
            return []
        units = json.loads(material['units'])
        version = material_version(material)
        ranges = []
        for index, chapter in enumerate(json.loads(material['chapters'])):
            start, end = chapter['unit_index'], chapter.get('end_unit_index')
            if not chapter.get('included', True) or end is None or not 0 <= start <= end < len(units):
                continue
            if not any(u['text'].strip() for u in units[start:end+1]):
                continue
            key = hashlib.sha256(f"{material['id']}:{version}:{index}".encode()).hexdigest()
            ranges.append({'key': key, 'title': chapter['title'].strip(), 'material_id': material['id'],
                           'name': material['name'], 'unit_index': start, 'end_unit_index': end,
                           'start_location': units[start]['location'], 'end_location': units[end]['location']})
        return ranges

    @app.get('/api/courses/{course_id}/chapters')
    def course_chapters(course_id: int, user=Depends(current_user)):
        get_course(course_id, user)
        with db() as conn:
            materials = [dict(r) for r in conn.execute(
                'SELECT * FROM materials WHERE course_id=? AND owner_id=? ORDER BY rowid', (course_id,user['id']))]
        groups = {}
        for material in materials:
            for item in chapter_ranges(material):
                groups.setdefault(item['title'], []).append(item)
        return [{'title': title, 'ranges': ranges} for title, ranges in groups.items()]

    def expire_outlines(conn):
        conn.execute("UPDATE outlines SET status='failed',message='生成中断或等待超时，请检查后重试' WHERE status='generating' AND created_at<?", (time.time()-300,))

    @app.get('/api/ai/status')
    def ai_status(user=Depends(current_user)):
        try:
            config = ai.settings()
            return {'configured':True, 'model':config['model'], 'message':'配置已填写，尚不代表连接验证通过'}
        except ai.AIError as error:
            return {'configured':False,'message':str(error)}

    @app.get('/api/courses/{course_id}/outlines')
    def list_outlines(course_id: int, user=Depends(current_user)):
        get_course(course_id, user)
        with db() as conn:
            expire_outlines(conn)
            return [dict(row) for row in conn.execute('SELECT id,status,goal,detail,model,message,created_at FROM outlines WHERE course_id=? AND owner_id=? ORDER BY created_at DESC', (course_id,user['id']))]

    def collect_sources(course_id, body, user):
        sources, versions = [], {}
        selected_chapters, matched_keys = [], set()
        requested_keys = set(body.chapter_keys) if body.chapter_keys is not None else None
        for material_id in dict.fromkeys(body.material_ids):
            material = owned_material(material_id, user)
            if material['course_id'] != course_id:
                raise HTTPException(404,'资料不属于当前课程')
            if material['status'] != 'ready' or not material['confirmed']:
                raise HTTPException(409,'请先提取文字并保存每份所选资料的章节范围')
            chapters = json.loads(material['chapters'])
            if any(c.get('end_unit_index') is None for c in chapters):
                raise HTTPException(409,'旧版章节缺少结束位置，请重新确认范围后保存')
            available = chapter_ranges(material)
            picked = [r for r in available if requested_keys is None or r['key'] in requested_keys]
            if requested_keys is not None and not picked:
                continue
            matched_keys.update(r['key'] for r in picked)
            selected_chapters.extend(picked)
            chosen = selected_units(json.loads(material['units']), picked if requested_keys is not None else chapters)
            if not any(unit['text'].strip() for unit in chosen):
                raise HTTPException(422,'所选资料中有文件未勾选有效文字范围，请检查后重试')
            versions[material_id] = material_version(material)
            for unit in chosen:
                if unit['text'].strip():
                    sources.append({'source_id':f'S{len(sources)+1}', 'material_id':material_id,
                                    'name':material['name'], **unit})
        if requested_keys is not None and matched_keys != requested_keys:
            raise HTTPException(409,'章节或资料已变化，请刷新章节列表后重新选择')
        if not sources:
            raise HTTPException(422,'请至少选择一个包含文字的章节范围')
        return sources, versions, selected_chapters

    @app.post('/api/courses/{course_id}/outlines', status_code=201)
    def create_outline(course_id: int, body: OutlineInput, user=Depends(current_user)):
        course = get_course(course_id, user)
        sources, versions, selected_chapters = collect_sources(course_id, body, user)
        from backend.batching import split_sources, pack_sources
        if len(pack_sources(split_sources(sources))) > 1:
            raise HTTPException(409, '请刷新页面后使用新的分批大纲工作区；本次旧版请求尚未处理任何内容')
        try:
            config = ai.settings()
        except ai.AIError as error:
            raise HTTPException(503, str(error))
        outline_id = secrets.token_hex(16)
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            expire_outlines(conn)
            if conn.execute("SELECT 1 FROM outlines WHERE owner_id=? AND status='generating'", (user['id'],)).fetchone():
                raise HTTPException(409,'你已有大纲正在生成，请稍后刷新历史记录')
            conn.execute('INSERT INTO outlines(id,owner_id,course_id,status,goal,detail,model,sources,versions,created_at,selected_chapters) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                         (outline_id,user['id'],course_id,'generating',body.goal,body.detail,config['model'],json.dumps(sources,ensure_ascii=False),json.dumps(versions),time.time(),json.dumps(selected_chapters,ensure_ascii=False)))
        try:
            result = ai.generate_outline(config, course['name'], body.goal, body.detail, sources)
        except Exception as error:
            message = str(error) if isinstance(error, ai.AIError) else '生成过程发生错误，本次结果未保存，请重试'
            with db() as conn:
                conn.execute("UPDATE outlines SET status='failed',message=? WHERE id=?",(message,outline_id))
            return {'id':outline_id,'status':'failed','message':message}
        with db() as conn:
            conn.execute("UPDATE outlines SET status='ready',result=? WHERE id=?",(json.dumps(result,ensure_ascii=False),outline_id))
        return {'id':outline_id,'status':'ready'}

    @app.get('/api/outlines/{outline_id}')
    def outline_detail(outline_id: str, user=Depends(current_user)):
        with db() as conn:
            expire_outlines(conn)
            row = conn.execute('SELECT * FROM outlines WHERE id=? AND owner_id=?',(outline_id,user['id'])).fetchone()
            if not row:
                raise HTTPException(404,'大纲不存在')
            result = dict(row)
            result['stale'] = False
            for material_id, version in json.loads(result.pop('versions')).items():
                material = conn.execute('SELECT * FROM materials WHERE id=? AND owner_id=?',(material_id,user['id'])).fetchone()
                if not material or material_version(material) != version:
                    result['stale'] = True
        result['selected_chapters'] = json.loads(result['selected_chapters'])
        result['sources'] = json.loads(result['sources'])
        result['result'] = json.loads(result['result']) if result['result'] else None
        return result

    from backend.practice import register_practice_routes
    register_practice_routes(app, db, current_user, get_course, collect_sources, material_version)

    from backend.outline_sessions import register_outline_sessions
    register_outline_sessions(app, db, current_user, get_course, collect_sources, OutlineInput, material_version)

    from backend.learning_tools import register_learning_tools
    register_learning_tools(app, db, current_user, get_course, password_hash)
    from backend.paper_tools import register_paper_tools
    register_paper_tools(app, db, current_user, get_course)

    from backend.material_tools import register_material_tools
    register_material_tools(app, db, current_user)
    from backend.page_vision import register_page_vision
    register_page_vision(app, db, current_user, uploads)
    from backend.blueprints import register_blueprints
    register_blueprints(app, db, current_user, get_course, collect_sources)

    from backend.resource_search import register_resource_search
    register_resource_search(app, db, current_user, get_course)

    from backend.course_deletion import register_course_deletion
    register_course_deletion(app, db, current_user, uploads)

    return app


app = create_app()
