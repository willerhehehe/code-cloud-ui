const cloudContainer = document.getElementById("cloudContainer");
const modeLabel = document.getElementById("modeLabel");
const termCount = document.getElementById("termCount");
const fileCount = document.getElementById("fileCount");
const updatedAt = document.getElementById("updatedAt");
const refreshButton = document.getElementById("refresh");
const errorTemplate = document.getElementById("errorTemplate");

const MODE_LABELS = {
  words: "words",
  code: "code",
  symbols: "structure (classes/functions/globals, JS skipped)",
};

function renderCloud(items) {
  cloudContainer.innerHTML = "";
  if (!items.length) {
    const empty = document.createElement("p");
    empty.textContent = "No terms found.";
    empty.className = "muted";
    cloudContainer.appendChild(empty);
    return;
  }

  const max = items[0].count || 1;
  items.forEach(({ term, count }) => {
    const el = document.createElement("span");
    el.className = "tag";
    const scale = 0.7 + (count / max) * 1.6;
    el.style.fontSize = `${Math.min(2.4, scale).toFixed(2)}rem`;
    el.textContent = term;
    const small = document.createElement("small");
    small.textContent = count;
    el.appendChild(small);
    cloudContainer.appendChild(el);
  });
}

function renderStats({ mode, items, total_terms }) {
  modeLabel.textContent = MODE_LABELS[mode] ?? mode;
  termCount.textContent = total_terms;
  fileCount.textContent = items[0]?.files ?? 0;
  const now = new Date();
  updatedAt.textContent = now.toLocaleTimeString();
}

function renderError(onRetry) {
  cloudContainer.innerHTML = "";
  const node = errorTemplate.content.cloneNode(true);
  node.querySelector(".retry").addEventListener("click", onRetry);
  cloudContainer.appendChild(node);
}

async function loadCloud(mode) {
  try {
    const res = await fetch(`/api/cloud?type=${encodeURIComponent(mode)}`, {
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderCloud(data.items);
    renderStats(data);
  } catch (err) {
    console.error("Failed to fetch cloud", err);
    renderError(() => loadCloud(mode));
  }
}

function selectedMode() {
  const checked = document.querySelector("input[name=mode]:checked");
  return checked?.value || "words";
}

function attachEvents() {
  document.querySelectorAll("input[name=mode]").forEach((input) => {
    input.addEventListener("change", () => loadCloud(selectedMode()));
  });
  refreshButton.addEventListener("click", () => loadCloud(selectedMode()));
}

attachEvents();
loadCloud(selectedMode());
