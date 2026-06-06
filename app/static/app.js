const CHUNK_SIZE = 64 * 1024 * 1024;
let activeUploadKey = "";
let activeKeyInfo = null;

const $ = (selector) => document.querySelector(selector);

function show(id) {
  document.querySelectorAll(".workspace, #setupView").forEach((node) => node.classList.add("hidden"));
  $(id).classList.remove("hidden");
}

function bytes(value) {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(size >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.body instanceof Blob ? {} : { "Content-Type": "application/json" }),
      ...(options.headers || {}),
    },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

async function checkSetup() {
  const status = await api("/api/setup/status");
  if (!status.initialized) {
    show("#setupView");
  }
}

function setTab(view) {
  document.querySelectorAll(".tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  show(view === "admin" ? "#adminView" : "#uploadView");
}

async function refreshUploadRecords() {
  if (!activeUploadKey) return;
  const payload = await api("/api/upload/records", {
    headers: { "X-Upload-Key": activeUploadKey },
  });
  renderRecords($("#uploadRecords"), payload.records);
}

async function refreshAdmin() {
  const [keys, records] = await Promise.all([
    api("/api/admin/keys"),
    api("/api/admin/records"),
  ]);
  renderKeys(keys.keys);
  renderRecords($("#adminRecords"), records.records);
  $("#adminLogin").classList.add("hidden");
  $("#adminDashboard").classList.remove("hidden");
  await loadSettings();
}

async function loadSettings() {
  const payload = await api("/api/admin/settings");
  const settingsForm = $("#settingsForm");
  settingsForm.elements.publicUrl.value = payload.settings.public_url || "";
  settingsForm.elements.defaultMaxGb.value = Math.max(1, Math.round((payload.settings.default_max_bytes || 0) / 1024 / 1024 / 1024));
}

function renderKeys(keys) {
  $("#keyList").innerHTML = keys.length
    ? keys.map((key) => `
      <div class="table-row">
        <div class="name">${escapeHtml(key.label)}</div>
        <div>${escapeHtml(key.status)}</div>
        <div>${bytes(key.max_total_bytes)}</div>
        <div><button data-disable-key="${key.id}" type="button">禁用</button></div>
      </div>
    `).join("")
    : `<p class="muted">暂无上传密钥</p>`;
}

function renderRecords(target, records) {
  target.innerHTML = records.length
    ? records.map((record) => `
      <div class="table-row">
        <div class="name">${escapeHtml(record.relative_path || record.file_name)}</div>
        <div>${bytes(record.size_bytes)}</div>
        <div>${escapeHtml(record.status)}</div>
        <div>${record.completed_at ? escapeHtml(record.completed_at) : "-"}</div>
      </div>
    `).join("")
    : `<p class="muted">暂无记录</p>`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  })[char]);
}

async function uploadFiles(files) {
  for (const file of files) {
    const relativePath = file.webkitRelativePath || file.name;
    const row = document.createElement("div");
    row.className = "queue-row";
    row.innerHTML = `
      <div class="name">${escapeHtml(relativePath)}</div>
      <div>${bytes(file.size)}</div>
      <div><div class="progress"><span></span></div></div>
      <div class="muted">等待</div>
    `;
    $("#queue").prepend(row);
    const bar = row.querySelector(".progress span");
    const state = row.querySelector(".muted");

    try {
      const created = await api("/api/upload/files", {
        method: "POST",
        body: JSON.stringify({
          uploadKey: activeUploadKey,
          fileName: file.name,
          relativePath,
          sizeBytes: file.size,
          chunkSize: CHUNK_SIZE,
        }),
      });
      const uploadFile = created.file;
      const missing = created.missingChunks;
      const startedAt = Date.now();
      let uploaded = file.size - (missing.length * CHUNK_SIZE);

      for (const index of missing) {
        const start = index * CHUNK_SIZE;
        const chunk = file.slice(start, Math.min(file.size, start + CHUNK_SIZE));
        state.textContent = "上传中";
        await api(`/api/upload/files/${uploadFile.id}/chunks/${index}`, {
          method: "PUT",
          headers: { "X-Upload-Key": activeUploadKey },
          body: chunk,
        });
        uploaded += chunk.size;
        const percent = Math.min(100, Math.round((uploaded / file.size) * 100));
        bar.style.width = `${percent}%`;
        const seconds = Math.max(1, (Date.now() - startedAt) / 1000);
        state.textContent = `${percent}% · ${bytes(uploaded / seconds)}/s`;
      }
      bar.style.width = "100%";
      state.textContent = "完成";
      await refreshUploadRecords();
    } catch (error) {
      state.textContent = error.message;
      state.classList.add("failed");
    }
  }
}

async function enterUploadWithToken(token) {
  activeUploadKey = token;
  try {
    const payload = await api("/api/upload/validate-key", {
      method: "POST",
      body: JSON.stringify({ uploadKey: activeUploadKey }),
    });
    activeKeyInfo = payload.key;
    setTab("upload");
    $("#keyGate").classList.add("hidden");
    $("#uploader").classList.remove("hidden");
    $("#uploadTitle").textContent = activeKeyInfo.label || "上传素材";
    $("#uploadLimit").textContent = `上限 ${bytes(activeKeyInfo.maxTotalBytes)}`;
    $("#folderButton").classList.toggle("hidden", !activeKeyInfo.allowFolderUpload);
    await refreshUploadRecords();
  } catch (error) {
    $("#keyStatus").textContent = error.message;
  }
}

document.addEventListener("click", async (event) => {
  const tab = event.target.closest(".tab");
  if (tab) setTab(tab.dataset.view);

  const disableButton = event.target.closest("[data-disable-key]");
  if (disableButton) {
    await api(`/api/admin/keys/${disableButton.dataset.disableKey}/disable`, { method: "POST" });
    await refreshAdmin();
  }
});

$("#setupForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  await api("/api/setup", {
    method: "POST",
    body: JSON.stringify({
      username: form.get("username"),
      password: form.get("password"),
      publicUrl: form.get("publicUrl"),
      defaultMaxBytes: Number(form.get("defaultMaxGb")) * 1024 * 1024 * 1024,
    }),
  });
  show("#uploadView");
});

$("#keyForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  activeUploadKey = form.get("uploadKey");
  try {
    const payload = await api("/api/upload/validate-key", {
      method: "POST",
      body: JSON.stringify({ uploadKey: activeUploadKey }),
    });
    await enterUploadWithToken(activeUploadKey);
  } catch (error) {
    $("#keyStatus").textContent = error.message;
  }
});

$("#changeKey").addEventListener("click", () => {
  activeUploadKey = "";
  activeKeyInfo = null;
  $("#uploader").classList.add("hidden");
  $("#keyGate").classList.remove("hidden");
});

$("#fileInput").addEventListener("change", (event) => uploadFiles([...event.target.files]));
$("#folderInput").addEventListener("change", (event) => uploadFiles([...event.target.files]));

$("#loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  try {
    await api("/api/admin/login", {
      method: "POST",
      body: JSON.stringify({
        username: form.get("username"),
        password: form.get("password"),
      }),
    });
    await refreshAdmin();
  } catch (error) {
    $("#loginStatus").textContent = error.message;
  }
});

$("#keyCreateForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const formElement = event.currentTarget;
  const form = new FormData(formElement);
  const payload = await api("/api/admin/keys", {
    method: "POST",
    body: JSON.stringify({
      label: form.get("label"),
      destinationSubdir: form.get("destinationSubdir"),
      maxTotalBytes: Number(form.get("maxTotalGb")) * 1024 * 1024 * 1024,
      allowFolderUpload: form.get("allowFolderUpload") === "on",
    }),
  });
  $("#latestLinkInput").value = payload.uploadUrl;
  $("#latestLink").classList.remove("hidden");
  formElement.reset();
  await refreshAdmin();
});

$("#refreshAdmin").addEventListener("click", refreshAdmin);
$("#settingsForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  await api("/api/admin/settings", {
    method: "POST",
    body: JSON.stringify({
      publicUrl: form.get("publicUrl"),
      defaultMaxBytes: Number(form.get("defaultMaxGb")) * 1024 * 1024 * 1024,
    }),
  });
  await loadSettings();
});
$("#copyLatestLink").addEventListener("click", async () => {
  const value = $("#latestLinkInput").value;
  if (navigator.clipboard) {
    await navigator.clipboard.writeText(value);
  } else {
    $("#latestLinkInput").select();
    document.execCommand("copy");
  }
});

const shareMatch = window.location.pathname.match(/^\/u\/([^/]+)$/);
if (shareMatch) {
  enterUploadWithToken(decodeURIComponent(shareMatch[1]));
} else {
  checkSetup();
}
