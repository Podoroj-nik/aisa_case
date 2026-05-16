const state = {
  chats: [],
  activeChatId: null,
  loading: false,
};

function $(id) {
  return document.getElementById(id);
}

function formatDate(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return "";
  }
}

function setStatus(text) {
  $("status").textContent = text || "";
}

// Упрощённое приветственное окно
function showWelcomeScreen() {
  const box = $("messages");
  box.innerHTML = `
    <div class="welcome-container">
      <div class="welcome-icon">🤖</div>
      <h1 class="welcome-title">Добро пожаловать в GigaChat UI!</h1>
      <p class="welcome-description">
        Ваш интеллектуальный помощник на основе нейросети GigaChat
      </p>
    </div>
  `;
}

window.sendExample = async function(question) {
  const input = $("messageInput");
  input.value = question;
  await sendCurrent();
};

function renderChats() {
  const list = $("chatList");
  list.innerHTML = "";

  for (const chat of state.chats) {
    const el = document.createElement("div");
    el.className = "chat-item" + (chat.id === state.activeChatId ? " active" : "");
    
    const content = document.createElement("div");
    content.className = "chat-content";
    
    const headerRow = document.createElement("div");
    headerRow.className = "chat-header-row";
    
    const title = document.createElement("div");
    title.className = "title";
    title.textContent = chat.title || "Новый чат";
    
    const deleteBtn = document.createElement("button");
    deleteBtn.className = "delete-chat-btn";
    deleteBtn.innerHTML = "✕";
    deleteBtn.title = "Удалить чат";
    deleteBtn.onclick = (e) => {
      e.stopPropagation();
      deleteChat(chat.id);
    };
    
    headerRow.appendChild(title);
    headerRow.appendChild(deleteBtn);
    
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = formatDate(chat.created_at);
    
    content.appendChild(headerRow);
    content.appendChild(meta);
    el.appendChild(content);
    
    el.addEventListener("click", () => openChat(chat.id));
    list.appendChild(el);
  }
}

async function deleteChat(chatId) {
  const chat = state.chats.find(c => c.id === chatId);
  const chatTitle = chat?.title || "Новый чат";
  
  if (!confirm(`Вы уверены, что хотите удалить чат "${chatTitle}"? Все сообщения будут потеряны.`)) {
    return;
  }
  
  setStatus("Удаление...");
  
  try {
    const response = await fetch(`/api/chats/${chatId}`, { method: "DELETE" });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Ошибка удаления");
    }
    
    const index = state.chats.findIndex(c => c.id === chatId);
    if (index !== -1) {
      state.chats.splice(index, 1);
    }
    
    if (state.activeChatId === chatId) {
      if (state.chats.length > 0) {
        await openChat(state.chats[0].id);
      } else {
        state.activeChatId = null;
        await createChat();
      }
    }
    
    renderChats();
    setStatus("Чат удалён");
    setTimeout(() => setStatus(""), 2000);
  } catch (e) {
    setStatus(String(e.message || e));
    setTimeout(() => setStatus(""), 3000);
  }
}

function renderMarkdownWithMath(content) {
  let processedContent = content;
  processedContent = processedContent.replace(/C_\{([^}]+)\}\^\{([^}]+)\}/g, '\\binom{$1}{$2}');
  processedContent = processedContent.replace(/C_([a-zA-Z0-9]+)\^([a-zA-Z0-9]+)/g, '\\binom{$1}{$2}');
  processedContent = processedContent.replace(/C_\{([^}]+)\}\^([a-zA-Z0-9]+)/g, '\\binom{$1}{$2}');
  processedContent = processedContent.replace(/C_([a-zA-Z0-9]+)\^\{([^}]+)\}/g, '\\binom{$1}{$2}');
  
  const html = marked.parse(processedContent);
  const temp = document.createElement('div');
  temp.innerHTML = html;
  
  if (typeof renderMathInElement === 'function') {
    renderMathInElement(temp, {
      delimiters: [
        {left: '$$', right: '$$', display: true},
        {left: '$', right: '$', display: false},
        {left: '\\(', right: '\\)', display: false},
        {left: '\\[', right: '\\]', display: true}
      ],
      throwOnError: false,
      errorColor: '#e74c3c'
    });
  }
  
  return temp.innerHTML;
}

function showTypingIndicator() {
  const box = $("messages");
  const indicator = document.createElement("div");
  indicator.className = "msg";
  indicator.id = "typing-indicator";
  
  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = "AI";
  
  const bubble = document.createElement("div");
  bubble.className = "bubble assistant";
  
  const typingDots = document.createElement("div");
  typingDots.className = "typing-indicator";
  typingDots.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';
  
  bubble.appendChild(typingDots);
  indicator.appendChild(avatar);
  indicator.appendChild(bubble);
  
  box.appendChild(indicator);
  box.scrollTop = box.scrollHeight;
}

function hideTypingIndicator() {
  const indicator = document.getElementById("typing-indicator");
  if (indicator) {
    indicator.remove();
  }
}

async function renderMessages(messages) {
  const box = $("messages");
  
  if (!messages || messages.length === 0) {
    showWelcomeScreen();
    return;
  }
  
  box.innerHTML = "";

  for (const m of messages) {
    const row = document.createElement("div");
    row.className = "msg";

    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.textContent = m.role === "user" ? "Я" : "AI";

    const bubble = document.createElement("div");
    bubble.className = "bubble " + (m.role === "user" ? "user" : "assistant");

    if (m.role === "user") {
      bubble.textContent = m.content;
    } else {
      try {
        bubble.innerHTML = renderMarkdownWithMath(m.content);
      } catch (e) {
        console.error("Render error:", e);
        bubble.textContent = m.content;
      }
    }

    row.appendChild(avatar);
    row.appendChild(bubble);
    box.appendChild(row);
  }

  box.scrollTop = box.scrollHeight;
}

async function api(method, url, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      detail = j.detail || detail;
    } catch {}
    throw new Error(detail);
  }
  return await res.json();
}

async function loadChats() {
  try {
    state.chats = await api("GET", "/api/chats");
    renderChats();
    
    if (state.activeChatId && !state.chats.find(c => c.id === state.activeChatId)) {
      state.activeChatId = null;
      if (state.chats.length > 0) {
        await openChat(state.chats[0].id);
      } else {
        await createChat();
      }
    }
  } catch (e) {
    console.error("Error loading chats:", e);
    setStatus("Ошибка загрузки чатов");
  }
}

async function createChat() {
  const chat = await api("POST", "/api/chats", {});
  state.chats.unshift(chat);
  state.activeChatId = chat.id;
  renderChats();
  $("chatTitle").textContent = chat.title || "Новый чат";
  await renderMessages([]);
}

async function openChat(chatId) {
  const chat = state.chats.find((c) => c.id === chatId);
  if (!chat) {
    await createChat();
    return;
  }
  
  state.activeChatId = chatId;
  renderChats();
  $("chatTitle").textContent = chat.title || "Чат";

  setStatus("Загрузка…");
  try {
    const messages = await api("GET", `/api/chats/${encodeURIComponent(chatId)}/messages`);
    await renderMessages(messages);
  } catch (e) {
    console.error("Error loading messages:", e);
    if (e.message.includes("404")) {
      await createChat();
    } else {
      setStatus("Ошибка загрузки");
    }
  } finally {
    setStatus("");
  }
}

function setLoading(v) {
  state.loading = v;
  $("sendBtn").disabled = v;
  $("messageInput").disabled = v;
}

async function sendCurrent() {
  const input = $("messageInput");
  const text = input.value.trim();
  if (!text) return;

  if (!state.activeChatId) {
    await createChat();
  }

  const chatId = state.activeChatId;
  setLoading(true);
  setStatus("Думаю...");
  showTypingIndicator();

  try {
    const messages = await api("GET", `/api/chats/${encodeURIComponent(chatId)}/messages`);
    messages.push({ role: "user", content: text });
    await renderMessages(messages);
    input.value = "";
    input.style.height = "";

    await api("POST", `/api/chats/${encodeURIComponent(chatId)}/send`, { content: text });

    await loadChats();
    state.activeChatId = chatId;
    renderChats();

    const updated = await api("GET", `/api/chats/${encodeURIComponent(chatId)}/messages`);
    await renderMessages(updated);
  } catch (e) {
    setStatus(String(e.message || e));
  } finally {
    hideTypingIndicator();
    setLoading(false);
    setTimeout(() => setStatus(""), 2500);
  }
}

function autoresizeTextarea(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 180) + "px";
}

window.addEventListener("DOMContentLoaded", async () => {
  $("newChatBtn").addEventListener("click", async () => {
    await createChat();
  });

  const input = $("messageInput");
  input.addEventListener("input", () => autoresizeTextarea(input));
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendCurrent();
    }
  });

  $("composer").addEventListener("submit", (e) => {
    e.preventDefault();
    sendCurrent();
  });

  setStatus("Загрузка…");
  try {
    await loadChats();
    if (state.chats.length === 0) {
      await createChat();
    } else {
      await openChat(state.chats[0].id);
    }
  } catch (e) {
    setStatus(String(e.message || e));
  } finally {
    setTimeout(() => setStatus(""), 2500);
  }
});