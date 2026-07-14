const state = {
  workflows: [],
  crews: [],
  conversations: [],
  currentConversationId: null,
};

const els = {
  status: document.querySelector("#status"),
  workflowSelect: document.querySelector("#workflowSelect"),
  crewSelect: document.querySelector("#crewSelect"),
  userIdInput: document.querySelector("#userIdInput"),
  createCrewButton: document.querySelector("#createCrewButton"),
  newChatButton: document.querySelector("#newChatButton"),
  refreshButton: document.querySelector("#refreshButton"),
  conversationList: document.querySelector("#conversationList"),
  chatTitle: document.querySelector("#chatTitle"),
  chatMeta: document.querySelector("#chatMeta"),
  messageList: document.querySelector("#messageList"),
  chatForm: document.querySelector("#chatForm"),
  messageInput: document.querySelector("#messageInput"),
  sendButton: document.querySelector("#sendButton"),
};

function setStatus(text) {
  els.status.textContent = text;
}

function selectedCrew() {
  return state.crews.find((crew) => crew.id === els.crewSelect.value) || null;
}

function selectedWorkflowName() {
  return els.workflowSelect.value || "";
}

async function requestJson(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `${response.status} ${response.statusText}`);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function renderSelect(select, items, labelOf, valueOf) {
  select.innerHTML = "";
  if (!items.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "暂无可选项";
    select.appendChild(option);
    return;
  }
  for (const item of items) {
    const option = document.createElement("option");
    option.value = valueOf(item);
    option.textContent = labelOf(item);
    select.appendChild(option);
  }
}

function renderConversations() {
  els.conversationList.innerHTML = "";
  if (!state.conversations.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "暂无历史";
    els.conversationList.appendChild(empty);
    return;
  }

  for (const conversation of state.conversations) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "conversation-item";
    if (conversation.id === state.currentConversationId) {
      button.classList.add("active");
    }
    button.innerHTML = `
      <span class="conversation-title">${escapeHtml(conversation.title || "未命名对话")}</span>
      <span class="conversation-time">${formatTime(conversation.updated_at || conversation.created_at)}</span>
    `;
    button.addEventListener("click", () => openConversation(conversation.id));
    els.conversationList.appendChild(button);
  }
}

function renderMessages(messages) {
  els.messageList.innerHTML = "";
  if (!messages.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "开始对话";
    els.messageList.appendChild(empty);
    return;
  }

  for (const message of messages) {
    appendMessage(message.role, message.content);
  }
}

function appendMessage(role, content) {
  const item = document.createElement("div");
  item.className = `message ${String(role || "").toLowerCase()}`;
  item.innerHTML = `
    <span class="message-role">${escapeHtml(roleLabel(role))}</span>
    ${escapeHtml(content || "")}
  `;
  els.messageList.appendChild(item);
  els.messageList.scrollTop = els.messageList.scrollHeight;
}

function roleLabel(role) {
  const value = String(role || "").toLowerCase();
  if (value === "user") return "你";
  if (value === "assistant") return "助手";
  if (value === "agent") return "Agent";
  return value || "消息";
}

function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString();
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function loadWorkflows() {
  state.workflows = await requestJson("/api/workflows/");
  renderSelect(
    els.workflowSelect,
    state.workflows,
    (workflow) => workflow.is_default ? `${workflow.name} · 默认` : workflow.name,
    (workflow) => workflow.name,
  );
}

async function loadCrews() {
  state.crews = await requestJson("/api/crews/");
  renderSelect(
    els.crewSelect,
    state.crews,
    (crew) => crew.name,
    (crew) => crew.id,
  );
  syncWorkflowFromCrew();
  els.sendButton.disabled = state.crews.length === 0;
  if (!state.crews.length) {
    els.chatTitle.textContent = "先创建示例 Crew";
    els.chatMeta.textContent = "选择工作流后点击左侧按钮";
  }
}

function syncWorkflowFromCrew() {
  const crew = selectedCrew();
  if (!crew) return;
  const workflowType = crew.settings?.workflow_type;
  if (workflowType) {
    els.workflowSelect.value = workflowType;
  }
}

async function loadConversations() {
  const crew = selectedCrew();
  const userId = els.userIdInput.value.trim();
  if (!crew || !userId) {
    state.conversations = [];
    renderConversations();
    return;
  }

  const params = new URLSearchParams({ user_id: userId, crew_id: crew.id });
  state.conversations = await requestJson(`/api/conversations/?${params.toString()}`);
  renderConversations();
}

async function openConversation(conversationId) {
  state.currentConversationId = conversationId;
  const conversation = state.conversations.find((item) => item.id === conversationId);
  els.chatTitle.textContent = conversation?.title || "未命名对话";
  els.chatMeta.textContent = conversationId;
  renderConversations();
  const messages = await requestJson(`/api/conversations/${conversationId}/messages`);
  renderMessages(messages);
}

async function updateCrewWorkflow() {
  const crew = selectedCrew();
  const workflowType = selectedWorkflowName();
  if (!crew || !workflowType) return;
  const settings = { ...(crew.settings || {}), workflow_type: workflowType };
  const updated = await requestJson(`/api/crews/${crew.id}`, {
    method: "PUT",
    body: JSON.stringify({ settings }),
  });
  state.crews = state.crews.map((item) => item.id === updated.id ? updated : item);
}

async function createSampleCrew() {
  const workflowName = selectedWorkflowName();
  if (!workflowName) {
    appendMessage("assistant", "请先选择工作流。");
    return;
  }
  els.createCrewButton.disabled = true;
  setStatus("创建 Crew");
  try {
    const crew = await requestJson(`/api/workflows/${workflowName}/sample-crew`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    await loadCrews();
    els.crewSelect.value = crew.id;
    await loadConversations();
    resetChat();
    setStatus("就绪");
  } catch (error) {
    appendMessage("assistant", `创建失败：${error.message}`);
    setStatus("出错");
  } finally {
    els.createCrewButton.disabled = false;
  }
}

function resetChat() {
  state.currentConversationId = null;
  els.chatTitle.textContent = selectedWorkflowName() || "新对话";
  els.chatMeta.textContent = selectedCrew()?.name || "未选择 Crew";
  renderConversations();
  renderMessages([]);
  els.messageInput.focus();
}

async function sendMessage(message) {
  els.sendButton.disabled = true;
  try {
    const crew = selectedCrew();
    const userId = els.userIdInput.value.trim();
    if (!crew) throw new Error("请先创建或选择 Crew");
    if (!userId) throw new Error("请输入用户");

    appendMessage("user", message);
    setStatus("运行中");

    let response;
    if (state.currentConversationId) {
      response = await requestJson("/api/chat", {
        method: "POST",
        body: JSON.stringify({
          conversation_id: state.currentConversationId,
          message,
        }),
      });
    } else {
      await updateCrewWorkflow();
      response = await requestJson("/api/chat", {
        method: "POST",
        body: JSON.stringify({
          user_id: userId,
          crew_id: crew.id,
          title: message.slice(0, 40),
          message,
        }),
      });
      state.currentConversationId = response.conversation_id;
      els.chatTitle.textContent = message.slice(0, 40);
      els.chatMeta.textContent = response.conversation_id;
    }
    appendMessage("assistant", response.content);
    await loadConversations();
    setStatus("就绪");
  } catch (error) {
    appendMessage("assistant", `请求失败：${error.message}`);
    setStatus("出错");
  } finally {
    els.sendButton.disabled = false;
  }
}

async function boot() {
  try {
    await loadWorkflows();
    await loadCrews();
    await loadConversations();
    resetChat();
    setStatus("就绪");
  } catch (error) {
    setStatus("初始化失败");
    renderMessages([{ role: "assistant", content: error.message }]);
  }
}

els.crewSelect.addEventListener("change", async () => {
  syncWorkflowFromCrew();
  resetChat();
  await loadConversations();
});

els.workflowSelect.addEventListener("change", resetChat);
els.userIdInput.addEventListener("change", loadConversations);
els.createCrewButton.addEventListener("click", createSampleCrew);
els.refreshButton.addEventListener("click", loadConversations);
els.newChatButton.addEventListener("click", resetChat);

els.chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = els.messageInput.value.trim();
  if (!message) return;
  els.messageInput.value = "";
  await sendMessage(message);
});

boot();
