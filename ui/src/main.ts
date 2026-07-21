import { invoke } from "@tauri-apps/api/core";
import { getVersion } from "@tauri-apps/api/app";
import { listen } from "@tauri-apps/api/event";
import { open } from "@tauri-apps/plugin-shell";
import "@picocss/pico/css/pico.min.css";
import "./style.css";

type Dictionary = Record<string, string>;

interface Config {
  total_screen: boolean;
  screen_index: number;
  scale_index: number;
  window_snap: boolean;
  transparency_index: number;
  auto_startup: boolean;
  click_through: boolean;
  follow_mouse: boolean;
  display_priority: number;
  wander_idle_stay_mode: number;
  instance_count: number;
  skip_updates: boolean;
  skip_version: string | null;
  voice_enabled: boolean;
  voice_volume: number;
  ui_language: string;
  voice_language: string;
}

interface PersonalizationSnapshot {
  config: Config;
  scale_options: number[];
  opacity_options: number[];
  monitor_count: number;
  voice_languages_with_clips: string[];
}

const UI_LANGUAGES = ["zh-hant", "zh-hans", "en", "ja", "ko"];

let dict: Dictionary = {};

function t(key: string, vars?: Record<string, string | number>): string {
  let s = dict[key] ?? key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, String(v));
  }
  return s;
}

async function loadDictionary(): Promise<void> {
  const raw = await invoke<string>("locale_dictionary");
  dict = JSON.parse(raw) as Dictionary;
}

type Tab = "personalization" | "update" | "about";
let activeTab: Tab = "personalization";

interface UpdateInfo {
  version: string;
  body: string | null;
}

// Whatever the startup check (updater.rs, task 14.2) already found, if
// anything -- read once at load via `pending_update` (no network
// request of its own) so the update tab can show it immediately
// instead of re-checking GitHub a second time.
let pendingUpdate: UpdateInfo | null = null;

async function main(): Promise<void> {
  await loadDictionary();
  pendingUpdate = await invoke<UpdateInfo | null>("pending_update");
  if (pendingUpdate) {
    activeTab = "update";
  }
  await render();

  // Only relevant if the startup check finds an update *after* this
  // window is already open (pendingUpdate above only covers the case
  // where it was found before the window existed).
  await listen<Tab>("switch-tab", (event) => {
    activeTab = event.payload;
    applyActiveTab();
  });
}

async function render(): Promise<void> {
  const app = document.querySelector<HTMLDivElement>("#app")!;
  app.innerHTML = `
    <main class="container-fluid settings-window">
      <nav class="tabs">
        <button class="tab-button" data-tab="personalization">${t("settings.tab.personalization")}</button>
        <button class="tab-button" data-tab="update">${t("settings.tab.update")}</button>
        <button class="tab-button" data-tab="about">${t("settings.tab.about")}</button>
      </nav>
      <section class="panel" data-panel="personalization"></section>
      <section class="panel" data-panel="update"></section>
      <section class="panel" data-panel="about"></section>
    </main>
  `;

  for (const button of app.querySelectorAll<HTMLButtonElement>(".tab-button")) {
    button.addEventListener("click", () => {
      activeTab = button.dataset.tab as Tab;
      applyActiveTab();
    });
  }

  // Select the default tab immediately, before the panels' content has
  // loaded -- each panel below fills in independently (and reports its
  // own error rather than leaving the window blank if one of them
  // fails), so tab selection must not wait on all three to succeed.
  applyActiveTab();

  await Promise.allSettled([
    renderPersonalization().catch((err) => renderError("personalization", err)),
    renderUpdate().catch((err) => renderError("update", err)),
    renderAbout().catch((err) => renderError("about", err)),
  ]);
}

function renderError(tab: Tab, err: unknown): void {
  const panel = document.querySelector<HTMLElement>(`[data-panel="${tab}"]`)!;
  console.error(`failed to render ${tab} tab:`, err);
  panel.innerHTML = `<p class="error">${String(err)}</p>`;
}

function applyActiveTab(): void {
  for (const button of document.querySelectorAll<HTMLButtonElement>(".tab-button")) {
    button.classList.toggle("active", button.dataset.tab === activeTab);
  }
  for (const panel of document.querySelectorAll<HTMLElement>(".panel")) {
    panel.classList.toggle("active", panel.dataset.panel === activeTab);
  }
}

function field(labelText: string, controlHtml: string): string {
  return `<label class="field-row"><span>${labelText}</span>${controlHtml}</label>`;
}

async function renderPersonalization(): Promise<void> {
  const panel = document.querySelector<HTMLElement>('[data-panel="personalization"]')!;
  const snapshot = await invoke<PersonalizationSnapshot>("get_personalization");
  const { config, scale_options, opacity_options, monitor_count, voice_languages_with_clips } =
    snapshot;

  const scaleOptionsHtml = scale_options
    .map(
      (v, i) =>
        `<option value="${i}" ${i === config.scale_index ? "selected" : ""}>${v.toFixed(1)}x</option>`,
    )
    .join("");
  const opacityOptionsHtml = opacity_options
    .map(
      (v, i) =>
        `<option value="${i}" ${i === config.transparency_index ? "selected" : ""}>${Math.round(v * 100)}%</option>`,
    )
    .join("");
  const displayPriorityOptionsHtml = (
    [
      [1, "personalization.display_priority.topmost"],
      [2, "personalization.display_priority.fullscreen_hide"],
      [3, "personalization.display_priority.desktop_only"],
    ] as const
  )
    .map(
      ([value, key]) =>
        `<option value="${value}" ${value === config.display_priority ? "selected" : ""}>${t(key)}</option>`,
    )
    .join("");
  const wanderOptionsHtml = (
    [
      [0, "personalization.wander_stay_mode.always_move"],
      [1, "personalization.wander_stay_mode.probabilistic"],
      [2, "personalization.wander_stay_mode.stationary"],
    ] as const
  )
    .map(
      ([value, key]) =>
        `<option value="${value}" ${value === config.wander_idle_stay_mode ? "selected" : ""}>${t(key)}</option>`,
    )
    .join("");
  const monitorOptionsHtml = Array.from({ length: monitor_count }, (_, i) => i)
    .map(
      (i) =>
        `<option value="${i}" ${i === config.screen_index ? "selected" : ""}>${t("personalization.monitor.numbered", { index: i })}</option>`,
    )
    .join("");
  const uiLanguageOptionsHtml = UI_LANGUAGES.map(
    (lang) =>
      `<option value="${lang}" ${lang === config.ui_language ? "selected" : ""}>${t(`language.${lang.replace("-", "_")}`)}</option>`,
  ).join("");
  const voiceLanguageOptionsHtml = voice_languages_with_clips
    .map(
      (lang) =>
        `<option value="${lang}" ${lang === config.voice_language ? "selected" : ""}>${t(`language.${lang}`)}</option>`,
    )
    .join("");

  panel.innerHTML = `
    ${field(t("personalization.scale_label"), `<select id="scale-select">${scaleOptionsHtml}</select>`)}
    ${field(t("personalization.opacity_label"), `<select id="opacity-select">${opacityOptionsHtml}</select>`)}
    ${field(t("personalization.display_priority_label"), `<select id="display-priority-select">${displayPriorityOptionsHtml}</select>`)}
    ${field(t("personalization.wander_stay_mode_label"), `<select id="wander-select">${wanderOptionsHtml}</select>`)}
    ${field(t("personalization.monitor.all_screens"), `<input type="checkbox" id="all-screens-checkbox" ${config.total_screen ? "checked" : ""} />`)}
    ${field(t("personalization.monitor_label"), `<select id="monitor-select" ${config.total_screen ? "disabled" : ""}>${monitorOptionsHtml}</select>`)}
    ${field(t("personalization.window_snap_label"), `<input type="checkbox" id="window-snap-checkbox" ${config.window_snap ? "checked" : ""} />`)}
    ${field(t("personalization.instance_count_label"), `<input type="number" id="instance-count-input" min="1" max="80" value="${config.instance_count}" />`)}
    ${field(t("personalization.autostart_label"), `<input type="checkbox" id="autostart-checkbox" ${config.auto_startup ? "checked" : ""} />`)}
    ${field(t("personalization.ui_language_label"), `<select id="ui-language-select">${uiLanguageOptionsHtml}</select>`)}
    ${field(t("personalization.voice_enabled_label"), `<input type="checkbox" id="voice-enabled-checkbox" ${config.voice_enabled ? "checked" : ""} />`)}
    ${field(t("personalization.voice_volume_label"), `<input type="range" id="voice-volume-input" min="0" max="150" value="${config.voice_volume}" />`)}
    ${field(t("personalization.voice_language_label"), `<select id="voice-language-select">${voiceLanguageOptionsHtml}</select>`)}
  `;

  const byId = <T extends HTMLElement>(id: string) => panel.querySelector<T>(`#${id}`)!;

  byId<HTMLSelectElement>("scale-select").addEventListener("change", (e) => {
    invoke("set_scale_index", { index: Number((e.target as HTMLSelectElement).value) });
  });
  byId<HTMLSelectElement>("opacity-select").addEventListener("change", (e) => {
    invoke("set_opacity_index", { index: Number((e.target as HTMLSelectElement).value) });
  });
  byId<HTMLSelectElement>("display-priority-select").addEventListener("change", (e) => {
    invoke("set_display_priority", { mode: Number((e.target as HTMLSelectElement).value) });
  });
  byId<HTMLSelectElement>("wander-select").addEventListener("change", (e) => {
    invoke("set_wander_stay_mode", { mode: Number((e.target as HTMLSelectElement).value) });
  });
  byId<HTMLInputElement>("all-screens-checkbox").addEventListener("change", (e) => {
    const enabled = (e.target as HTMLInputElement).checked;
    byId<HTMLSelectElement>("monitor-select").disabled = enabled;
    invoke("set_total_screen", { enabled });
  });
  byId<HTMLSelectElement>("monitor-select").addEventListener("change", (e) => {
    invoke("set_monitor_index", { index: Number((e.target as HTMLSelectElement).value) });
  });
  byId<HTMLInputElement>("window-snap-checkbox").addEventListener("change", (e) => {
    invoke("set_window_snap", { enabled: (e.target as HTMLInputElement).checked });
  });
  byId<HTMLInputElement>("instance-count-input").addEventListener("change", (e) => {
    invoke("set_instance_count", { count: Number((e.target as HTMLInputElement).value) });
  });
  byId<HTMLInputElement>("autostart-checkbox").addEventListener("change", (e) => {
    invoke("set_auto_startup", { enabled: (e.target as HTMLInputElement).checked });
  });
  byId<HTMLSelectElement>("ui-language-select").addEventListener("change", async (e) => {
    const language = (e.target as HTMLSelectElement).value;
    await invoke("set_ui_language", { language });
    // Localization spec: language changes apply with an immediate UI
    // refresh rather than requiring a restart.
    await loadDictionary();
    await render();
  });
  byId<HTMLInputElement>("voice-enabled-checkbox").addEventListener("change", (e) => {
    invoke("set_voice_enabled", { enabled: (e.target as HTMLInputElement).checked });
  });
  byId<HTMLInputElement>("voice-volume-input").addEventListener("change", (e) => {
    invoke("set_voice_volume", { percent: Number((e.target as HTMLInputElement).value) });
  });
  byId<HTMLSelectElement>("voice-language-select").addEventListener("change", (e) => {
    invoke("set_voice_language", { language: (e.target as HTMLSelectElement).value });
  });
}

async function renderUpdate(): Promise<void> {
  const panel = document.querySelector<HTMLElement>('[data-panel="update"]')!;
  const version = await getVersion();
  const snapshot = await invoke<PersonalizationSnapshot>("get_personalization");

  panel.innerHTML = `
    <p>${t("update.current_version_label", { version })}</p>
    <button id="update-check-button">${t("update.check_button")}</button>
    <div id="update-result"></div>
    ${field(t("update.skip_all_updates"), `<input type="checkbox" id="skip-updates-checkbox" ${snapshot.config.skip_updates ? "checked" : ""} />`)}
  `;

  panel
    .querySelector<HTMLInputElement>("#skip-updates-checkbox")!
    .addEventListener("change", (e) => {
      invoke("set_skip_updates", { enabled: (e.target as HTMLInputElement).checked });
    });

  const resultEl = panel.querySelector<HTMLElement>("#update-result")!;
  const checkButton = panel.querySelector<HTMLButtonElement>("#update-check-button")!;
  checkButton.addEventListener("click", () => checkForUpdate(resultEl, checkButton));

  // The startup check (14.2) may have already found this before the
  // window opened -- show it directly rather than hitting GitHub again.
  if (pendingUpdate) {
    showUpdateResult(resultEl, pendingUpdate);
  }
}

async function checkForUpdate(
  resultEl: HTMLElement,
  checkButton: HTMLButtonElement,
): Promise<void> {
  checkButton.disabled = true;
  resultEl.innerHTML = `<p>${t("update.checking")}</p>`;
  try {
    const update = await invoke<UpdateInfo | null>("check_for_update");
    showUpdateResult(resultEl, update);
  } catch (err) {
    console.error("update check failed:", err);
    resultEl.innerHTML = `<p class="error">${t("update.error")}</p>`;
  } finally {
    checkButton.disabled = false;
  }
}

function showUpdateResult(resultEl: HTMLElement, update: UpdateInfo | null): void {
  if (!update) {
    resultEl.innerHTML = `<p>${t("update.up_to_date")}</p>`;
    return;
  }
  resultEl.innerHTML = `
    <p>${t("update.latest_version_label", { version: update.version })}</p>
    ${update.body ? `<p>${update.body}</p>` : ""}
    <button id="update-install-button">${t("update.install_button")}</button>
    <button id="update-skip-version-button" class="secondary">${t("update.skip_this_version")}</button>
  `;
  resultEl
    .querySelector<HTMLButtonElement>("#update-install-button")!
    .addEventListener("click", async (e) => {
      (e.target as HTMLButtonElement).disabled = true;
      resultEl.insertAdjacentHTML("beforeend", `<p>${t("update.installing")}</p>`);
      try {
        // Restarts the app on success (Rust side calls AppHandle::
        // restart), so this only returns here on failure.
        await invoke("install_update");
      } catch (err) {
        console.error("update install failed:", err);
        resultEl.insertAdjacentHTML("beforeend", `<p class="error">${t("update.error")}</p>`);
      }
    });
  resultEl
    .querySelector<HTMLButtonElement>("#update-skip-version-button")!
    .addEventListener("click", async () => {
      await invoke("set_skip_version", { version: update.version });
      resultEl.innerHTML = "";
    });
}

const AMEATH_URL = "https://gitee.com/lzy-buaa-jdi/ameath";
const FUGU_URL = "https://space.bilibili.com/84508966";
const AUTHOR_URL = "https://github.com/kagetsuki1997";
const REPO_URL = "https://github.com/kagetsuki1997/fleet-snowfluff";

function externalLink(url: string, label: string): string {
  return `<a href="${url}" class="external-link">${label}</a>`;
}

async function renderAbout(): Promise<void> {
  const panel = document.querySelector<HTMLElement>('[data-panel="about"]')!;
  const version = await getVersion();

  panel.innerHTML = `
    <p class="version">${t("about.version", { version })}</p>
    <p>${t("about.license_notice")}</p>
    <p class="disclaimer">${t("about.asset_disclaimer")}</p>
    <h3>${t("about.credits_heading")}</h3>
    <p>${t("about.credits_original", { ameath_link: externalLink(AMEATH_URL, "Ameath"), fugu_link: externalLink(FUGU_URL, "-fugu-") })}</p>
    <p>${t("about.credits_rewrite", { author_link: externalLink(AUTHOR_URL, "kagetsuki1997"), repo_link: externalLink(REPO_URL, "github.com/kagetsuki1997/fleet-snowfluff") })}</p>
  `;

  // Links must open in the system browser, not navigate this settings
  // window itself away to an external site.
  for (const link of panel.querySelectorAll<HTMLAnchorElement>("a.external-link")) {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      open(link.href);
    });
  }
}

main();
