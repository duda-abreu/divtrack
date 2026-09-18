const state = { portfolios: [], holdings: [], dividends: [], portfolioId: "" };
const NOTIFICATION_SETTINGS_KEY = "divtrack-notifications";
const $ = (selector) => document.querySelector(selector);

const money = (value, currency = "BRL") => new Intl.NumberFormat("pt-BR", {
  style: "currency", currency, maximumFractionDigits: 2
}).format(Number(value || 0));
const number = (value) => new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 4 }).format(Number(value || 0));
const shortDate = (value) => value ? new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short" }).format(new Date(`${value}T12:00:00`)) : "A definir";

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) }
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Não foi possível concluir a operação.");
  }
  return response.status === 204 ? null : response.json();
}

function toast(message, error = false) {
  const element = $("#toast");
  element.textContent = message;
  element.className = `toast show${error ? " error" : ""}`;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.className = "toast", 3200);
}

function selectedQuery() {
  return state.portfolioId ? `?portfolio_id=${state.portfolioId}` : "";
}

async function loadData() {
  try {
    [state.portfolios, state.holdings, state.dividends] = await Promise.all([
      api("/portfolios"), api(`/holdings${selectedQuery()}`), api(`/dividends${selectedQuery()}`)
    ]);
    render();
    checkPaymentNotifications();
  } catch (error) { toast(error.message, true); }
}

function render() {
  renderPortfolioOptions();
  renderMetrics();
  renderChart();
  renderUpcoming();
  renderHoldings();
  renderNotificationState();
}

function notificationSettings() {
  try { return JSON.parse(localStorage.getItem(NOTIFICATION_SETTINGS_KEY)) || { enabled: false }; }
  catch { return { enabled: false }; }
}

function renderNotificationState() {
  const enabled = notificationSettings().enabled && "Notification" in window && Notification.permission === "granted";
  $("#notificationButton").classList.toggle("alert-on", enabled);
  $("#notificationButton").setAttribute("aria-label", enabled ? "Notificações ativadas" : "Configurar notificações");
}

function checkPaymentNotifications() {
  if (!notificationSettings().enabled || !("Notification" in window) || Notification.permission !== "granted") return;
  const today = new Date().toISOString().slice(0, 10);
  state.dividends.filter(item => item.payment_date === today).forEach(item => {
    const key = `divtrack-notified-${item.id}-${item.payment_date}`;
    if (localStorage.getItem(key)) return;
    new Notification(`${item.ticker}: pagamento hoje`, {
      body: `${money(item.total_amount, item.currency)} em ${item.event_type.toLowerCase()} agendado para hoje.`,
      icon: "/static/assets/favicon.svg",
      tag: key
    });
    localStorage.setItem(key, new Date().toISOString());
  });
}

function renderPortfolioOptions() {
  const options = state.portfolios.map(p => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join("");
  $("#portfolioFilter").innerHTML = `<option value="">Todas</option>${options}`;
  $("#portfolioFilter").value = state.portfolioId;
  $("#assetPortfolio").innerHTML = options || `<option value="">Crie uma carteira primeiro</option>`;
}

function renderMetrics() {
  const totals = state.dividends.reduce((sum, item) => item.currency === "BRL" ? sum + Number(item.total_amount) : sum, 0);
  $("#totalIncome").textContent = money(totals);
  $("#incomeRecords").textContent = `${state.dividends.length} ${state.dividends.length === 1 ? "provento registrado" : "proventos registrados"}`;
  $("#holdingCount").textContent = state.holdings.length;
  $("#portfolioCount").textContent = `${state.portfolios.length} ${state.portfolios.length === 1 ? "carteira" : "carteiras"}`;
  const upcoming = futureDividends()[0];
  $("#nextPayment").textContent = upcoming ? money(upcoming.total_amount, upcoming.currency) : "—";
  $("#nextPaymentMeta").textContent = upcoming ? `${upcoming.ticker} • ${shortDate(upcoming.payment_date)}` : "Aguardando anúncios";
}

function monthKey(date) { return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`; }
function renderChart() {
  const months = [];
  const now = new Date();
  for (let i = 5; i >= 0; i--) months.push(new Date(now.getFullYear(), now.getMonth() - i, 1));
  const sums = Object.fromEntries(months.map(d => [monthKey(d), 0]));
  state.dividends.forEach(item => {
    const key = (item.payment_date || item.ex_date || "").slice(0, 7);
    if (key in sums && item.currency === "BRL") sums[key] += Number(item.total_amount);
  });
  const max = Math.max(...Object.values(sums), 1);
  $("#incomeChart").innerHTML = months.map(date => {
    const value = sums[monthKey(date)];
    const height = value ? Math.max(8, value / max * 145) : 4;
    return `<div class="bar-wrap"><span class="bar-value">${value ? compactMoney(value) : "—"}</span><div class="bar" style="height:${height}px"></div><span class="bar-label">${date.toLocaleDateString("pt-BR", { month: "short" }).replace(".", "")}</span></div>`;
  }).join("");
}

function compactMoney(value) {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", notation: value >= 1000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(value);
}

function futureDividends() {
  const today = new Date().toISOString().slice(0, 10);
  return state.dividends.filter(d => d.payment_date && d.payment_date >= today).sort((a, b) => a.payment_date.localeCompare(b.payment_date));
}

function renderUpcoming() {
  const items = futureDividends().slice(0, 5);
  $("#upcomingCount").textContent = items.length;
  $("#upcomingList").innerHTML = items.length ? items.map(item => `
    <div class="event">
      <div class="ticker-avatar">${escapeHtml(item.ticker.slice(0, 4))}</div>
      <div><strong>${escapeHtml(item.ticker)}</strong><span>${escapeHtml(item.event_type)} • ${shortDate(item.payment_date)}</span></div>
      <div class="event-value"><b>${money(item.total_amount, item.currency)}</b><span>${money(item.amount_per_share, item.currency)}/ação</span></div>
    </div>`).join("") : `<div class="empty-state">Nenhum pagamento futuro registrado.</div>`;
}

function renderHoldings() {
  const portfolios = Object.fromEntries(state.portfolios.map(p => [p.id, p.name]));
  $("#holdingsList").innerHTML = state.holdings.length ? state.holdings.map(item => `
    <article class="holding">
      <button class="delete-holding" data-id="${item.id}" aria-label="Remover ${escapeHtml(item.ticker)}">×</button>
      <div class="holding-top"><div class="ticker-avatar">${escapeHtml(item.ticker.slice(0, 4))}</div><div><h4>${escapeHtml(item.ticker)}</h4><p>${escapeHtml(portfolios[item.portfolio_id] || "Carteira")}</p></div></div>
      <dl><div><dt>Quantidade</dt><dd>${number(item.shares)}</dd></div><div><dt>Preço médio</dt><dd>${item.average_price == null ? "—" : money(item.average_price)}</dd></div></dl>
    </article>`).join("") : `<div class="empty-state wide">Cadastre sua primeira ação para acompanhar proventos automaticamente.</div>`;
  document.querySelectorAll(".delete-holding").forEach(button => button.addEventListener("click", () => removeHolding(button.dataset.id)));
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
}

function openAssetDialog() {
  if (!state.portfolios.length) {
    toast("Crie uma carteira antes de adicionar ações.");
    $("#portfolioDialog").showModal();
    return;
  }
  $("#assetDialog").showModal();
  $("#assetDialog input[name=ticker]").focus();
}

async function removeHolding(id) {
  if (!confirm("Remover esta ação da carteira?")) return;
  try { await api(`/holdings/${id}`, { method: "DELETE" }); await loadData(); toast("Posição removida."); }
  catch (error) { toast(error.message, true); }
}

async function sync() {
  const button = $("#syncButton");
  button.classList.add("is-loading");
  $("#syncStatus").textContent = "Buscando novos anúncios…";
  try {
    const result = await api("/sync/dividends", { method: "POST" });
    await loadData();
    toast(result.imported ? `${result.imported} novos proventos importados.` : "Nenhum anúncio novo.");
    $("#syncStatus").textContent = "Sincronização concluída";
  } catch (error) { toast(error.message, true); $("#syncStatus").textContent = "Sincronização indisponível"; }
  finally { button.classList.remove("is-loading"); }
}

$("#assetForm").addEventListener("submit", async event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget));
  if (!data.average_price) delete data.average_price;
  if (!data.acquired_on) delete data.acquired_on;
  data.portfolio_id = Number(data.portfolio_id);
  try {
    await api("/holdings", { method: "POST", body: JSON.stringify(data) });
    event.currentTarget.reset(); $("#assetDialog").close(); await loadData(); toast(`${data.ticker.toUpperCase()} adicionada.`);
  } catch (error) { toast(error.message, true); }
});

$("#portfolioForm").addEventListener("submit", async event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget));
  if (!data.description) data.description = null;
  try {
    const portfolio = await api("/portfolios", { method: "POST", body: JSON.stringify(data) });
    event.currentTarget.reset(); $("#portfolioDialog").close(); await loadData();
    $("#assetPortfolio").value = portfolio.id; toast("Carteira criada.");
  } catch (error) { toast(error.message, true); }
});

$("#notificationButton").addEventListener("click", () => {
  $("#notificationEnabled").checked = notificationSettings().enabled;
  $("#notificationDialog").showModal();
});

$("#notificationForm").addEventListener("submit", async event => {
  event.preventDefault();
  let enabled = $("#notificationEnabled").checked;
  if (enabled) {
    if (!("Notification" in window)) {
      toast("Este navegador não oferece notificações.", true);
      return;
    }
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      enabled = false;
      $("#notificationEnabled").checked = false;
      toast("Permissão de notificações não concedida.", true);
    }
  }
  localStorage.setItem(NOTIFICATION_SETTINGS_KEY, JSON.stringify({ enabled }));
  $("#notificationDialog").close();
  renderNotificationState();
  if (enabled) {
    checkPaymentNotifications();
    toast("Notificações ativadas.");
  } else {
    toast("Notificações desativadas.");
  }
});

$("#portfolioFilter").addEventListener("change", async event => { state.portfolioId = event.target.value; await loadData(); });
$("#syncButton").addEventListener("click", sync);
$("#addAssetButton").addEventListener("click", openAssetDialog);
$("#inlineAddAsset").addEventListener("click", openAssetDialog);
$("#addPortfolioButton").addEventListener("click", () => $("#portfolioDialog").showModal());
$("#themeToggle").addEventListener("click", () => document.body.classList.toggle("soft-light"));
document.querySelectorAll(".close-dialog").forEach(button => button.addEventListener("click", () => button.closest("dialog").close()));

const now = new Date();
$("#todayLabel").textContent = `SEU PATRIMÔNIO • ${now.toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long" }).toUpperCase()}`;
const hour = now.getHours();
$("#welcomeTitle").textContent = `${hour < 12 ? "Bom dia" : hour < 18 ? "Boa tarde" : "Boa noite"}, Maria.`;
loadData();
