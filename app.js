document.getElementById("finderForm").addEventListener("submit", async function (e) {
  e.preventDefault();
  const f = e.target;
  const formData = new FormData(f);
  const payload = {};
  for (const [k, v] of formData.entries()) {
    if (v === "") continue;
    payload[k] = v;
  }

  // convert numeric fields
  if (payload.gpa) payload.gpa = parseFloat(payload.gpa);
  if (payload.sat) payload.sat = parseFloat(payload.sat);
  if (payload.act) payload.act = parseFloat(payload.act);
  if (payload.sai) payload.sai = parseFloat(payload.sai);

  const btn = document.getElementById("submitBtn");
  btn.disabled = true;
  btn.textContent = "Finding...";

  try {
    const res = await fetch("/recommend", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const j = await res.json();
    renderResults(j);
  } catch (err) {
    document.getElementById("results").innerHTML = `<div class="card">Error: ${err.message}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Find Colleges";
  }
});

function renderResults(data) {
  const root = document.getElementById("results");

  if (data.error) {
    root.innerHTML = `<div class="card">API Error: ${data.error}</div>`;
    return;
  }
  if (!data.recommendations || data.recommendations.length === 0) {
    root.innerHTML = `<div class="card">No recommendations found. Try removing filters.</div>`;
    return;
  }

  let html = `<div class="small">Showing ${data.recommendations.length} recommendations (queried ${data.query_count} schools)</div>`;
  root.innerHTML = html;

  for (const s of data.recommendations) {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <strong>${s.name}</strong> 
      <span class="small"> — ${s.city || ""} ${s.state || ""}</span>
      <div class="small">Admission rate: ${formatPct(s.admission_rate)} | Avg SAT: ${s.avg_sat || "N/A"} | Avg ACT: ${s.avg_act || "N/A"}</div>
      <div class="small">Size: ${s.student_size || "N/A"} students</div>
      <div class="small">Average net price: ${formatMoney(s.avg_net_price)} | Students receiving aid: ${formatPct(s.pell_grant_rate)}</div>
    `;

    // Add AI summary with typing animation
    if (s.ai_summary) {
      const summary = document.createElement("div");
      summary.className = "ai-summary";
      summary.innerHTML = `<strong>AI Summary:</strong> <span class="typing"></span>`;
      card.appendChild(summary);
      root.appendChild(card);

      // animate the text
      typeText(summary.querySelector(".typing"), s.ai_summary, 25);
    } else {
      root.appendChild(card);
    }
  }
}

function formatPct(v) {
  if (!v && v !== 0) return "N/A";
  try {
    return (parseFloat(v) * 100).toFixed(1) + "%";
  } catch (e) {
    return v;
  }
}
function formatMoney(v) {
  if (!v && v !== 0) return "N/A";
  try {
    return "$" + Math.round(parseFloat(v));
  } catch (e) {
    return v;
  }
}

// ✨ Typing animation for AI summaries
function typeText(element, text, speed = 30) {
  let i = 0;
  const interval = setInterval(() => {
    element.textContent += text[i];
    i++;
    if (i >= text.length) clearInterval(interval);
  }, speed);
}
