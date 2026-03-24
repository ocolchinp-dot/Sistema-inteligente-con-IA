const API_URL = window.API_URL || "http://localhost:8000/api/analyze";

const fileInput = document.getElementById("fileInput");
const analyzeBtn = document.getElementById("analyzeBtn");
const statusEl = document.getElementById("status");
const jsonResultEl = document.getElementById("jsonResult");
const warningsEl = document.getElementById("warnings");
const questionsEl = document.getElementById("questions");

function setStatus(message) {
  statusEl.textContent = `Estado: ${message}`;
}

function renderList(el, items, prefix) {
  el.innerHTML = "";
  items.forEach((item) => {
    const li = document.createElement("li");
    li.textContent = `${prefix}${item}`;
    el.appendChild(li);
  });
}

analyzeBtn.addEventListener("click", async () => {
  const file = fileInput.files[0];
  if (!file) {
    alert("Selecciona un archivo primero.");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  setStatus("subiendo archivo...");
  jsonResultEl.textContent = "{}";
  warningsEl.innerHTML = "";
  questionsEl.innerHTML = "";

  try {
    setStatus("procesando con IA y tools...");
    const response = await fetch(API_URL, { method: "POST", body: formData });
    const data = await response.json();

    jsonResultEl.textContent = JSON.stringify(data, null, 2);
    renderList(warningsEl, data.warnings || [], "⚠️ ");
    renderList(questionsEl, data.clarifying_questions || [], "❓ ");

    setStatus(`${data.status} | tipo: ${data.document_type}`);
  } catch (err) {
    setStatus("error de red o backend");
    jsonResultEl.textContent = JSON.stringify({ error: String(err) }, null, 2);
  }
});
