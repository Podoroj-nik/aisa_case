# app/app.py
from __future__ import annotations

import os
import httpx
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from dotenv import load_dotenv

load_dotenv()

# ── Отключаем проверку SSL (ТОЛЬКО ДЛЯ РАЗРАБОТКИ) ──
os.environ['REQUESTS_CA_BUNDLE'] = ''
os.environ['SSL_CERT_FILE'] = ''
os.environ['CURL_CA_BUNDLE'] = ''


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"

GIGACHAT_CREDENTIALS = os.getenv("GIGACHAT_CREDENTIALS", "")
GIGACHAT_VERIFY_SSL = os.getenv("GIGACHAT_VERIFY_SSL", "0") not in ("0", "false", "False", "no", "NO")

AFISHA_API_URL = os.getenv("AFISHA_API_URL", "http://pro.sirius-ft.ru/api/afisha/event/list")
DB_PATH = os.getenv("DB_PATH", "/data/chats.db")

token_stats = {"afisha": 0, "dialog": 0}


def read_html(filename: str) -> str:
    path = TEMPLATES_DIR / filename
    if not path.exists():
        return f"<h1>Ошибка</h1><p>Файл {filename} не найден</p>"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def check_internal_ip(request: Request) -> bool:
    return True

def call_gigachat_simple(prompt: str, source: str) -> dict:
    try:
        from gigachat import GigaChat
        giga = GigaChat(
            credentials=GIGACHAT_CREDENTIALS,
            verify_ssl_certs=GIGACHAT_VERIFY_SSL
        )
        response = giga.chat(prompt)
        text = response.choices[0].message.content
        tokens_used = response.usage.total_tokens
    except ImportError:
        text = f"[ДЕМО-РЕЖИМ] Библиотека gigachat не установлена.\n\nПромпт: {prompt[:200]}..."
        tokens_used = 0
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ошибка GigaChat: {str(e)}")

    if source == "afisha":
        token_stats["afisha"] += tokens_used
    else:
        token_stats["dialog"] += tokens_used

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] source={source} | tokens={tokens_used}")

    return {"response": text, "tokens_consumed": tokens_used}


class EventAIRequest(BaseModel):
    eventId: int
    eventName: str
    eventPlace: str
    eventStartDate: str
    eventStartTime: str
    eventEndTime: str
    afishaTypeName: str

class CreateChatIn(BaseModel):
    title: str = "Новый чат"

class SendMessageIn(BaseModel):
    content: str

class ChatOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    class Config:
        from_attributes = True

class MessageOut(BaseModel):
    id: str
    chat_id: str
    role: str
    content: str
    created_at: datetime
    class Config:
        from_attributes = True


from sqlalchemy import Column, String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, relationship

class Base(DeclarativeBase):
    pass

class Chat(Base):
    __tablename__ = "chats"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    title = Column(String(255), default="Новый чат")
    created_at = Column(DateTime, default=func.now())
    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan",
                            order_by="Message.created_at")

class Message(Base):
    __tablename__ = "messages"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    chat_id = Column(String, ForeignKey("chats.id"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now())
    chat = relationship("Chat", back_populates="messages")

def create_engine(db_path: str) -> AsyncEngine:
    from sqlalchemy.ext.asyncio import create_async_engine as _create_async_engine
    return _create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)

def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)

from contextlib import asynccontextmanager as _acm

@_acm
async def session_scope(factory: async_sessionmaker[AsyncSession]):
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


class GigaChatClient:
    def __init__(self):
        self.credentials = GIGACHAT_CREDENTIALS
        self.verify_ssl = GIGACHAT_VERIFY_SSL

    async def chat(self, messages: list[dict]) -> str:
        try:
            from gigachat import GigaChat
            giga = GigaChat(
                credentials=self.credentials,
                verify_ssl_certs=self.verify_ssl
            )
            prompt_parts = []
            for msg in messages:
                prefix = "Пользователь" if msg["role"] == "user" else "Ассистент"
                prompt_parts.append(f"{prefix}: {msg['content']}")
            prompt_parts.append("Ассистент: ")
            full_prompt = "\n\n".join(prompt_parts)
            response = giga.chat(full_prompt)
            text = response.choices[0].message.content
            tokens_used = response.usage.total_tokens
            token_stats["dialog"] += tokens_used
            return text
        except ImportError:
            return "[ДЕМО-РЕЖИМ] Библиотека gigachat не установлена."
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Ошибка GigaChat: {str(e)}")

# ============================================================
#                    ПРИЛОЖЕНИЕ
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(DB_PATH)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.gigachat = GigaChatClient()
    yield
    await engine.dispose()

app = FastAPI(title="Сириус — ИИ-Агент", lifespan=lifespan)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/", response_class=HTMLResponse)
async def guest_index(request: Request):
    return HTMLResponse(content=read_html("guest.html"))

@app.post("/api/afisha/events")
async def api_afisha_events(request: Request):
    check_internal_ip(request)
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(AFISHA_API_URL, json={})
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError:
            raise HTTPException(status_code=502, detail="Сервис «Афиша» недоступен")
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Ошибка сервиса «Афиша»: {str(e)}")

@app.post("/api/afisha/event/ai-details")
async def api_afisha_ai_details(request: Request, event: EventAIRequest):
    check_internal_ip(request)
    event_description = (
        f"{event.eventStartDate}\n"
        f"{event.eventName}\n"
        f"📍 {event.eventPlace}\n"
        f"🕐 {event.eventStartTime} – {event.eventEndTime}\n"
        f"📌 {event.afishaTypeName}"
    )
    prompt = (
        "Ты агент, который рассказывает про мероприятия на ФТ Сириус. "
        "Пользователь может не понимать некоторых терминов, поэтому ему нужно "
        "рассказать чему посвящено мероприятие. Рассказывай только то, в чем уверен. "
        f"Расскажи про мероприятие:\n\n{event_description}"
    )
    result = call_gigachat_simple(prompt, source="afisha")
    return {
        "eventId": event.eventId,
        "source": "afisha",
        "response": result["response"],
        "tokens_consumed": result["tokens_consumed"]
    }


@app.get("/admin", response_class=HTMLResponse)
async def admin_chat_page(request: Request):
    return HTMLResponse(content=read_html("admin_chat.html"))

@app.get("/api/chats", response_model=list[ChatOut])
async def list_chats(request: Request):
    factory = request.app.state.session_factory
    async with session_scope(factory) as session:
        rows = await session.execute(select(Chat).order_by(Chat.created_at.desc()))
        chats = rows.scalars().all()
        return [ChatOut(id=c.id, title=c.title, created_at=c.created_at) for c in chats]

@app.post("/api/chats", response_model=ChatOut)
async def create_chat(payload: CreateChatIn, request: Request):
    factory = request.app.state.session_factory
    chat = Chat(id=str(uuid4()), title=payload.title)
    async with session_scope(factory) as session:
        session.add(chat)
        await session.flush()
        await session.refresh(chat)
        return ChatOut(id=chat.id, title=chat.title, created_at=chat.created_at)

@app.delete("/api/chats/{chat_id}")
async def delete_chat(chat_id: str, request: Request):
    factory = request.app.state.session_factory
    async with session_scope(factory) as session:
        chat = await session.get(Chat, chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Чат не найден")
        await session.delete(chat)
        return {"status": "deleted", "id": chat_id}

@app.get("/api/chats/{chat_id}/messages", response_model=list[MessageOut])
async def list_messages(chat_id: str, request: Request):
    factory = request.app.state.session_factory
    async with session_scope(factory) as session:
        chat = await session.get(Chat, chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Чат не найден")
        await session.refresh(chat, attribute_names=["messages"])
        return [
            MessageOut(id=m.id, chat_id=m.chat_id, role=m.role, content=m.content, created_at=m.created_at)
            for m in chat.messages
        ]

@app.post("/api/chats/{chat_id}/send", response_model=MessageOut)
async def send_message(chat_id: str, payload: SendMessageIn, request: Request):
    factory = request.app.state.session_factory
    gigachat: GigaChatClient = request.app.state.gigachat

    async with session_scope(factory) as session:
        chat = await session.get(Chat, chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Чат не найден")

        user_msg = Message(chat_id=chat_id, role="user", content=payload.content)
        session.add(user_msg)
        await session.flush()

        rows = await session.execute(
            select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at.asc()).limit(20)
        )
        history = rows.scalars().all()
        gc_messages = [{"role": m.role, "content": m.content} for m in history]
        assistant_text = await gigachat.chat(gc_messages)
        assistant_msg = Message(chat_id=chat_id, role="assistant", content=assistant_text)
        session.add(assistant_msg)

        if not chat.title or chat.title == "Новый чат":
            chat.title = payload.content.strip().splitlines()[0][:100]

        await session.flush()
        await session.refresh(assistant_msg)

        return MessageOut(
            id=assistant_msg.id, chat_id=assistant_msg.chat_id,
            role=assistant_msg.role, content=assistant_msg.content,
            created_at=assistant_msg.created_at
        )


@app.get("/api/admin/stats/tokens")
async def api_admin_stats(request: Request):
    return {"tokens_consumed_by_source": token_stats}

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}