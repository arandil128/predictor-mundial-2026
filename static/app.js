const $ = (sel) => document.querySelector(sel);
const fmtPct = (p) => (p * 100).toFixed(1) + "%";
const fmtInt = (n) => n.toLocaleString("es-AR");

let goalsChart = null;
let ES = {}; // mapa inglés -> español
const es = (t) => ES[t] || t; // traduce un nombre de selección

async function loadTeams() {
  const res = await fetch("/api/matches");
  const data = await res.json();
  ES = data.names_es || {};
  const home = $("#home");
  const away = $("#away");
  data.teams
    .slice()
    .sort((a, b) => es(a.team).localeCompare(es(b.team), "es"))
    .forEach((t) => {
      home.add(new Option(es(t.team), t.team));
      away.add(new Option(es(t.team), t.team));
    });
  // Defaults distintos para arrancar.
  home.selectedIndex = 0;
  away.selectedIndex = Math.min(1, data.teams.length - 1);

  if (!data.sources.odds) {
    $("#status").textContent =
      "Sin clave de cuotas: el modelo usa Elo + ranking FIFA. Cargá ODDS_API_KEY para sumar el mercado.";
  }
  showEloStatus(data.elo_refreshed_at);
}

function showEloStatus(iso) {
  const el = $("#eloStatus");
  if (!iso) {
    el.textContent = "Elo: dataset base";
    return;
  }
  const d = new Date(iso);
  el.textContent = "Elo actualizado " + d.toLocaleString("es-AR");
}

async function refreshElo() {
  const btn = $("#refreshElo");
  const icon = $("#refreshIcon");
  btn.disabled = true;
  icon.classList.add("inline-block", "animate-spin");
  $("#eloStatus").textContent = "Descargando ratings…";
  try {
    const res = await fetch("/api/refresh-ratings", { method: "POST" });
    if (!res.ok) throw new Error("No se pudo actualizar.");
    const d = await res.json();
    showEloStatus(d.refreshed_at);
    $("#eloStatus").textContent += ` · ${d.updated}/${d.total} equipos`;
  } catch (e) {
    $("#eloStatus").textContent = e.message;
  } finally {
    btn.disabled = false;
    icon.classList.remove("animate-spin");
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

    $("#matchTitle").textContent = `${es(d.home_team)} vs ${es(d.away_team)}`;
    $("#simInfo").textContent =
      `${fmtInt(d.n_simulations)} sims · ${d.has_market ? "con mercado" : "solo modelo"}`;

    bar($('[data-row="home"]'), `Gana ${es(d.home_team)}`, d.prediction.home, "bg-emerald-500");
    bar($('[data-row="draw"]'), "Empate", d.prediction.draw, "bg-slate-400");
    bar($('[data-row="away"]'), `Gana ${es(d.away_team)}`, d.prediction.away, "bg-sky-500");

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
    renderCompare(d.components, d.has_market, es(d.home_team), es(d.away_team));

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
// ---------------- Pestañas ----------------
function setTab(name) {
  document.querySelectorAll(".tab").forEach((b) =>
    b.classList.toggle("tab-active", b.dataset.tab === name)
  );
  document.querySelectorAll("[data-pane]").forEach((p) =>
    p.classList.toggle("hidden", p.dataset.pane !== name)
  );
  if (name === "fixture" && !fixtureLoaded) loadFixture();
}
document.querySelectorAll(".tab").forEach((b) =>
  b.addEventListener("click", () => setTab(b.dataset.tab))
);

// ---------------- Fixture ----------------
let fixtureLoaded = false;
let fixtureMatches = [];
let fxSource = "file";
// Filtros activos: fecha (ISO), grupo (A..L) y país (nombre en inglés). "all" = sin filtrar.
const fxF = { date: "all", group: "all", country: "all" };
const STAGE_LABELS = {
  group: "Grupos", r32: "Dieciseisavos", r16: "Octavos",
  qf: "Cuartos", sf: "Semis", final: "Final", third: "3er puesto",
};

// Código FIFA (3 letras) -> ISO 3166-1 alpha-2, para mostrar la bandera (flagcdn.com).
const FIFA2ISO = {
  ARG: "ar", FRA: "fr", ESP: "es", ENG: "gb-eng", BRA: "br", POR: "pt", NED: "nl",
  BEL: "be", ITA: "it", GER: "de", CRO: "hr", URU: "uy", COL: "co", MAR: "ma",
  SUI: "ch", DEN: "dk", MEX: "mx", USA: "us", SEN: "sn", JPN: "jp", ECU: "ec",
  AUT: "at", UKR: "ua", IRN: "ir", KOR: "kr", SWE: "se", SRB: "rs", POL: "pl",
  WAL: "gb-wls", AUS: "au", PER: "pe", HUN: "hu", TUR: "tr", NGA: "ng", NOR: "no",
  EGY: "eg", CZE: "cz", SCO: "gb-sct", CHI: "cl", ALG: "dz", GRE: "gr", CMR: "cm",
  TUN: "tn", CAN: "ca", CIV: "ci", ROU: "ro", CRC: "cr", PAR: "py", GHA: "gh",
  KSA: "sa", SVK: "sk", SVN: "si", MLI: "ml", QAT: "qa", VEN: "ve", IRQ: "iq",
  IRL: "ie", BIH: "ba", FIN: "fi", PAN: "pa", RSA: "za", BFA: "bf", ALB: "al",
  MKD: "mk", CPV: "cv", GEO: "ge", UAE: "ae", JAM: "jm", UZB: "uz", COD: "cd",
  JOR: "jo", HON: "hn", OMA: "om", BOL: "bo", NZL: "nz", CUW: "cw", HAI: "ht",
};

function flag(code) {
  const iso = FIFA2ISO[code];
  if (!iso) return "";
  return `<img src="https://flagcdn.com/w40/${iso}.png" alt="" loading="lazy"
    class="h-4 w-6 shrink-0 rounded-[3px] object-cover ring-1 ring-black/40"
    onerror="this.style.display='none'">`;
}

function fmtDate(iso) {
  if (!iso) return null;
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("es-AR", { weekday: "short", day: "numeric", month: "short" });
}

async function loadFixture() {
  fixtureLoaded = true;
  try {
    const res = await fetch("/api/fixture");
    const data = await res.json();
    fixtureMatches = data.matches;
    fxSource = data.source;
    renderFilterBar();
    applyFilters();
  } catch (e) {
    $("#fxInfo").textContent = "No se pudo cargar el fixture.";
  }
}

function renderFilterBar() {
  const uniq = (arr) => [...new Set(arr)];
  const dates = uniq(fixtureMatches.filter((m) => m.date).map((m) => m.date)).sort();
  const groups = uniq(fixtureMatches.filter((m) => m.group).map((m) => m.group)).sort();
  const countries = uniq(
    fixtureMatches.flatMap((m) => [m.home, m.away]).filter(Boolean)
  ).sort((a, b) => es(a).localeCompare(es(b), "es"));

  const opt = (val, label, sel) =>
    `<option value="${val}"${sel === val ? " selected" : ""}>${label}</option>`;
  const selCls =
    "w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-emerald-500";

  $("#fxFilters").innerHTML = `
    <div>
      <label class="block text-[11px] font-medium text-slate-400 mb-1">📅 Fecha</label>
      <select id="fDate" class="${selCls}">
        ${opt("all", "Todas las fechas", fxF.date)}
        ${dates.map((d) => opt(d, fmtDate(d), fxF.date)).join("")}
      </select>
    </div>
    <div>
      <label class="block text-[11px] font-medium text-slate-400 mb-1">🏟️ Grupo</label>
      <select id="fGroup" class="${selCls}">
        ${opt("all", "Todos los grupos", fxF.group)}
        ${groups.map((g) => opt(g, "Grupo " + g, fxF.group)).join("")}
      </select>
    </div>
    <div>
      <label class="block text-[11px] font-medium text-slate-400 mb-1">🌐 País</label>
      <select id="fCountry" class="${selCls}">
        ${opt("all", "Todos los países", fxF.country)}
        ${countries.map((c) => opt(c, es(c), fxF.country)).join("")}
      </select>
    </div>`;

  $("#fDate").onchange = (e) => { fxF.date = e.target.value; applyFilters(); };
  $("#fGroup").onchange = (e) => { fxF.group = e.target.value; applyFilters(); };
  $("#fCountry").onchange = (e) => { fxF.country = e.target.value; applyFilters(); };
}

function matchesFilter(m) {
  if (fxF.date !== "all" && m.date !== fxF.date) return false;
  if (fxF.group !== "all" && m.group !== fxF.group) return false;
  if (fxF.country !== "all" && m.home !== fxF.country && m.away !== fxF.country) return false;
  return true;
}

function applyFilters() {
  const shown = fixtureMatches.filter(matchesFilter);
  const playable = shown.filter((m) => m.home && m.away).length;
  const nActive = (fxF.date !== "all") + (fxF.group !== "all") + (fxF.country !== "all");
  $("#fxInfo").innerHTML =
    `${shown.length} partido${shown.length === 1 ? "" : "s"} · ${playable} simulable${playable === 1 ? "" : "s"}` +
    (fxSource === "auto" ? " · día/hora/TV a cargar" : "") +
    (nActive
      ? ` · <button id="fxClear" class="text-emerald-400 hover:underline">limpiar filtros</button>`
      : "");
  const clear = $("#fxClear");
  if (clear)
    clear.onclick = () => {
      fxF.date = fxF.group = fxF.country = "all";
      renderFilterBar();
      applyFilters();
    };
  renderFixture(shown);
}

function matchCard(m) {
  const playable = m.home && m.away;
  const when = fmtDate(m.date);
  const ABIERTA = ["TV Pública", "Telefe", "TyC Sports"];
  const tv = (m.tv || []).length
    ? m.tv
        .map((t) => {
          const free = ABIERTA.includes(t);
          const cls = free
            ? "bg-emerald-500/15 text-emerald-300 border border-emerald-600/40"
            : "bg-slate-800 text-slate-300";
          return `<span class="rounded ${cls} px-1.5 py-0.5 text-[10px]">${free ? "📡" : "📺"} ${t}</span>`;
        })
        .join(" ")
    : `<span class="text-[10px] text-slate-600">TV a confirmar</span>`;

  const badge = m.group ? `Grupo ${m.group}` : STAGE_LABELS[m.stage] || m.stage_es;
  const homeFlag = m.home_code ? flag(m.home_code) : "";
  const awayFlag = m.away_code ? flag(m.away_code) : "";

  return `
  <div class="group rounded-xl border border-slate-800 bg-slate-900/60 p-4 transition hover:border-emerald-600/50 hover:bg-slate-900" data-n="${m.n}">
    <div class="flex items-center justify-between text-[11px] text-slate-500">
      <span class="rounded bg-slate-800 px-2 py-0.5 font-medium text-slate-300">${badge}</span>
      <span class="tabular-nums">#${m.n}${when ? " · " + when : ""}${m.time ? " · " + m.time : ""}</span>
    </div>

    <div class="mt-3 flex items-center gap-2">
      <div class="flex flex-1 items-center justify-end gap-2 text-right">
        ${homeFlag}<span class="font-semibold leading-tight">${m.home_es}</span>
      </div>
      <span class="px-1 text-[11px] font-semibold text-slate-500">vs</span>
      <div class="flex flex-1 items-center gap-2">
        <span class="font-semibold leading-tight">${m.away_es}</span>${awayFlag}
      </div>
    </div>

    <div class="mt-2.5 flex flex-wrap items-center gap-1.5">${tv}</div>
    <div class="mt-3 flex items-center gap-3">
      ${
        playable
          ? `<button class="fx-sim rounded-lg border border-emerald-600/60 bg-emerald-500/10 px-3 py-1.5 text-xs font-semibold text-emerald-400 hover:bg-emerald-500/20 transition">Simular</button>`
          : `<span class="text-[11px] text-slate-600 italic">Se define con los resultados</span>`
      }
      <div class="fx-result flex-1 text-xs text-slate-400"></div>
    </div>
    ${m.venue ? `<div class="mt-2 text-[10px] text-slate-600">📍 ${m.venue}</div>` : ""}
  </div>`;
}

function renderFixture(list) {
  if (!list.length) {
    $("#fxList").innerHTML =
      `<p class="py-12 text-center text-sm text-slate-500">No hay partidos con esos filtros.</p>`;
    return;
  }
  // Agrupar por etapa para encabezados.
  const byStage = {};
  list.forEach((m) => (byStage[m.stage] = byStage[m.stage] || []).push(m));
  $("#fxList").innerHTML = Object.entries(byStage)
    .map(
      ([stage, ms]) => `
      <div>
        <h3 class="mb-2 text-sm font-bold text-slate-300">${STAGE_LABELS[stage] || stage}</h3>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">${ms.map(matchCard).join("")}</div>
      </div>`
    )
    .join("");

  document.querySelectorAll("#fxList [data-n]").forEach((card) => {
    const btn = card.querySelector(".fx-sim");
    if (btn) btn.addEventListener("click", () => simulateCard(card));
  });
}

async function simulateCard(card, nSims = 10000) {
  const n = +card.dataset.n;
  const m = fixtureMatches.find((x) => x.n === n);
  const btn = card.querySelector(".fx-sim");
  const out = card.querySelector(".fx-result");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "…";
  }
  try {
    const res = await fetch("/api/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ home_team: m.home, away_team: m.away, n_simulations: nSims }),
    });
    if (!res.ok) throw new Error("error");
    const d = await res.json();
    const p = d.prediction;
    // Favorito: mayor probabilidad entre local / empate / visitante.
    const maxp = Math.max(p.home, p.draw, p.away);
    const favLabel =
      maxp === p.draw ? "Empate" : maxp === p.home ? es(m.home) : es(m.away);
    const top = (d.top_scorelines && d.top_scorelines[0]) || null;
    out.innerHTML = `
      <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span>
          <span class="text-emerald-400 font-semibold">L ${fmtPct(p.home)}</span> ·
          <span class="text-slate-400">X ${fmtPct(p.draw)}</span> ·
          <span class="text-sky-400 font-semibold">V ${fmtPct(p.away)}</span>
        </span>
        ${top ? `<span class="text-slate-500">🎯 ${top.score} <span class="text-slate-600">(${fmtPct(top.prob)})</span></span>` : ""}
        <span class="rounded bg-amber-500/15 text-amber-300 border border-amber-600/40 px-1.5 py-0.5 text-[10px] font-semibold">⭐ ${favLabel}</span>
      </div>`;
  } catch (e) {
    out.textContent = "Error";
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Simular";
    }
  }
}

async function runAllFixture() {
  const btn = $("#runAll");
  const cards = [...document.querySelectorAll("#fxList [data-n]")].filter((c) =>
    c.querySelector(".fx-sim")
  );
  if (!cards.length) return;
  btn.disabled = true;
  let done = 0;
  for (const card of cards) {
    await simulateCard(card, 6000);
    done++;
    $("#fxProgress").textContent = `Simulados ${done}/${cards.length}…`;
  }
  $("#fxProgress").textContent = `✓ ${cards.length} partidos simulados.`;
  btn.disabled = false;
}
$("#runAll").addEventListener("click", runAllFixture);

// ---------------- Torneo completo ----------------
async function runTournament() {
  const btn = $("#runT");
  btn.disabled = true;
  btn.textContent = "Simulando torneo…";
  $("#tStatus").textContent =
    "Jugando miles de Mundiales… (cada simulación juega 103 partidos)";
  try {
    const res = await fetch("/api/simulate-tournament", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ n_simulations: +$("#tSims").value }),
    });
    if (!res.ok) throw new Error("Error en la simulación del torneo.");
    const d = await res.json();

    $("#tInfo").textContent =
      `${fmtInt(d.n_simulations)} torneos · ${d.official_groups ? "grupos oficiales" : "grupos auto"}`;
    const max = d.ranking[0].champion || 1;
    $("#tBody").innerHTML = d.ranking
      .map((r, i) => {
        const medal = i === 0 ? "🥇" : i === 1 ? "🥈" : i === 2 ? "🥉" : i + 1;
        return `
        <tr class="border-b border-slate-800/60">
          <td class="py-2 pr-2 text-slate-500">${medal}</td>
          <td class="py-2 pr-2 font-medium">${es(r.team)}<span class="text-slate-600 text-xs ml-1">${r.elo}</span></td>
          <td class="py-2 pr-2">
            <div class="flex items-center gap-2 justify-end">
              <div class="hidden sm:block h-1.5 w-20 rounded-full bg-slate-800 overflow-hidden">
                <div class="h-full bg-emerald-500" style="width:${((r.champion / max) * 100).toFixed(1)}%"></div>
              </div>
              <span class="tabular-nums font-semibold w-12 text-right">${fmtPct(r.champion)}</span>
            </div>
          </td>
          <td class="py-2 pr-2 text-right tabular-nums text-slate-400 hidden sm:table-cell">${fmtPct(r.final)}</td>
          <td class="py-2 pr-2 text-right tabular-nums text-slate-400 hidden sm:table-cell">${fmtPct(r.sf)}</td>
          <td class="py-2 text-right tabular-nums text-slate-400">${fmtPct(r.r32)}</td>
        </tr>`;
      })
      .join("");

    $("#tGroups").innerHTML = Object.entries(d.groups)
      .map(
        ([g, teams]) => `
        <div class="rounded-lg bg-slate-800/40 p-2">
          <div class="font-semibold text-slate-300 mb-1">Grupo ${g}</div>
          ${teams.map((t) => `<div class="text-slate-400">${es(t)}</div>`).join("")}
        </div>`
      )
      .join("");

    $("#tResults").classList.remove("hidden");
    $("#tStatus").textContent = "";
    $("#tResults").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) {
    $("#tStatus").textContent = e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "Simular torneo";
  }
}

$("#tSims").addEventListener("input", (e) => {
  $("#tSimsLabel").textContent = (+e.target.value).toLocaleString("es-AR");
});
$("#runT").addEventListener("click", runTournament);

$("#run").addEventListener("click", run);
$("#refreshElo").addEventListener("click", refreshElo);
setTab("match");
loadTeams();
