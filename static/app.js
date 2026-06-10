const $ = (sel) => document.querySelector(sel);
const fmtPct = (p) => (p * 100).toFixed(1) + "%";
const fmtInt = (n) => n.toLocaleString("es-AR");

let goalsChart = null;

async function loadTeams() {
  const res = await fetch("/api/matches");
  const data = await res.json();
  const home = $("#home");
  const away = $("#away");
  data.teams.forEach((t) => {
    home.add(new Option(`${t.team}`, t.team));
    away.add(new Option(`${t.team}`, t.team));
  });
  // Defaults distintos para arrancar.
  home.selectedIndex = 0;
  away.selectedIndex = Math.min(1, data.teams.length - 1);

  if (!data.sources.odds) {
    $("#status").textContent =
      "Sin clave de cuotas: el modelo usa Elo + ranking FIFA. Cargá ODDS_API_KEY para sumar el mercado.";
  }
}

function bar(container, label, prob, color) {
  container.innerHTML = `
    <div class="flex items-center justify-between text-sm mb-1">
      <span class="font-medium">${label}</span>
      <span class="font-semibold">${fmtPct(prob)}</span>
    </div>
    <div class="h-2.5 w-full rounded-full bg-slate-800 overflow-hidden">
      <div class="bar h-full rounded-full ${color}" style="width:0%"></div>
    </div>`;
  requestAnimationFrame(() => {
    container.querySelector(".bar").style.width = (prob * 100).toFixed(1) + "%";
  });
}

function renderCompare(components, hasMarket, home, away) {
  const note = $("#compareNote");
  const box = $("#compare");
  if (!hasMarket || !components.market) {
    note.textContent =
      "No hay cuotas disponibles para este cruce; se muestra solo el modelo Elo.";
    box.innerHTML = "";
    return;
  }
  const w = Math.round(components.market_weight * 100);
  note.textContent = `Mezcla final: ${w}% mercado · ${100 - w}% modelo.`;
  const row = (lbl, m, md) => `
    <div class="grid grid-cols-3 gap-2 py-1.5 border-t border-slate-800">
      <span class="text-slate-400">${lbl}</span>
      <span class="text-right tabular-nums">${fmtPct(m)}</span>
      <span class="text-right tabular-nums">${fmtPct(md)}</span>
    </div>`;
  box.innerHTML = `
    <div class="grid grid-cols-3 gap-2 text-xs font-semibold text-slate-500">
      <span></span><span class="text-right">Mercado</span><span class="text-right">Modelo</span>
    </div>
    ${row(`Gana ${home}`, components.market.home, components.model.home)}
    ${row("Empate", components.market.draw, components.model.draw)}
    ${row(`Gana ${away}`, components.market.away, components.model.away)}`;
}

function renderChart(dist) {
  const labels = dist.map((d) => (d.goals >= 7 ? "7+" : String(d.goals)));
  const values = dist.map((d) => +(d.prob * 100).toFixed(1));
  if (goalsChart) goalsChart.destroy();
  goalsChart = new Chart($("#goalsChart"), {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          data: values,
          backgroundColor: "rgba(52, 211, 153, 0.7)",
          borderRadius: 6,
        },
      ],
    },
    options: {
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => c.parsed.y + "%" } } },
      scales: {
        x: { grid: { display: false }, ticks: { color: "#94a3b8" } },
        y: { grid: { color: "#1e293b" }, ticks: { color: "#94a3b8", callback: (v) => v + "%" } },
      },
    },
  });
}

async function run() {
  const btn = $("#run");
  const home = $("#home").value;
  const away = $("#away").value;
  if (home === away) {
    $("#status").textContent = "Elegí dos selecciones distintas.";
    return;
  }
  btn.disabled = true;
  btn.textContent = "Simulando…";
  $("#status").textContent = "Consultando datos en vivo y corriendo simulaciones…";

  try {
    const res = await fetch("/api/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        home_team: home,
        away_team: away,
        n_simulations: +$("#sims").value,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Error en la simulación.");
    }
    const d = await res.json();

    $("#matchTitle").textContent = `${d.home_team} vs ${d.away_team}`;
    $("#simInfo").textContent =
      `${fmtInt(d.n_simulations)} sims · ${d.has_market ? "con mercado" : "solo modelo"}`;

    bar($('[data-row="home"]'), `Gana ${d.home_team}`, d.prediction.home, "bg-emerald-500");
    bar($('[data-row="draw"]'), "Empate", d.prediction.draw, "bg-slate-400");
    bar($('[data-row="away"]'), `Gana ${d.away_team}`, d.prediction.away, "bg-sky-500");

    const eh = Math.round(d.expected_goals.home);
    const ea = Math.round(d.expected_goals.away);
    $("#expScore").textContent = `${eh} - ${ea}`;
    $("#over25").textContent = fmtPct(d.markets.over_2_5);
    $("#btts").textContent = fmtPct(d.markets.btts);

    $("#scorelines").innerHTML = d.top_scorelines
      .map(
        (s) => `
        <li class="flex items-center justify-between">
          <span class="font-mono">${s.score}</span>
          <div class="flex items-center gap-2 w-2/3">
            <div class="h-1.5 flex-1 rounded-full bg-slate-800 overflow-hidden">
              <div class="h-full bg-emerald-500/70" style="width:${(s.prob * 100).toFixed(1)}%"></div>
            </div>
            <span class="text-slate-400 text-xs tabular-nums w-12 text-right">${fmtPct(s.prob)}</span>
          </div>
        </li>`
      )
      .join("");

    renderChart(d.total_goals_dist);
    renderCompare(d.components, d.has_market, d.home_team, d.away_team);

    $("#results").classList.remove("hidden");
    $("#status").textContent = "";
    $("#results").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) {
    $("#status").textContent = e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "Simular partido";
  }
}

$("#sims").addEventListener("input", (e) => {
  $("#simsLabel").textContent = (+e.target.value).toLocaleString("es-AR");
});
$("#run").addEventListener("click", run);
loadTeams();
