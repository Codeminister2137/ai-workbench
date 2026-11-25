/* Guided intake form (chatbot v1: form-first). No backend: validates in
 * the browser, then offers the enquiry as a JSON lead download + copyable
 * text. The lead carries P7 identity keys but is NOT a valid brief: the
 * founder enriches it (target users, scope, timeline) before validation;
 * see intake/README.md. */
(function () {
  "use strict";
  var EN = document.documentElement.lang === "en";
  var T = EN ? {
    needTitle: "Give the project a short title.",
    needName: "Tell us your name.",
    needEmail: "A valid email is required so we can reply.",
    needGoal: "Describe what you want to achieve.",
    needBudget: "Pick a budget range.",
    badPhone: "Leave the phone empty or use international format (e.g. +48601234567).",
    secretWarn: "This looks like a secret — remove keys/passwords before sending.",
    ready: "Brief ready. Download the JSON and attach it to your email to us.",
    step1: "1. Contact",
    step2: "2. Project",
    step3: "3. Budget & review"
  } : {
    needTitle: "Nadaj projektowi krótki tytuł.",
    needName: "Podaj imię i nazwisko.",
    needEmail: "Prawidłowy e-mail jest wymagany, aby odpowiedzieć.",
    needGoal: "Opisz, co chcesz osiągnąć.",
    needBudget: "Wybierz przedział budżetu.",
    badPhone: "Telefon zostaw pusty albo podaj w formacie międzynarodowym (np. +48601234567).",
    secretWarn: "To wygląda na sekret — usuń klucze/hasła przed wysłaniem.",
    ready: "Zapytanie gotowe. Pobierz JSON i załącz go do e-maila do nas.",
    step1: "1. Kontakt",
    step2: "2. Projekt",
    step3: "3. Budżet i podsumowanie"
  };
  var SECRET_RE = /(api[_-]?key|password|secret|token)\s*[:=]|-----BEGIN.*PRIVATE KEY-----|(sk-|ghp_)[A-Za-z0-9]{8,}/i;
  var EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
  var PHONE_RE = /^\+[1-9]\d{7,14}$/;  /* E.164, mirrors intake schema; empty allowed */
  var BUDGETS_PL = ["<10k", "10–30k", "30–80k", "80k+", "undisclosed"];
  var BUDGETS_EN = ["<2k", "2-5k", "5-15k", "15k+", "undisclosed"];

  function el(id) { return document.getElementById(id); }
  function val(id) { var n = el(id); return n ? n.value.trim() : ""; }

  /* Lead identity in P7 vocabulary: the founder keeps project_id and
   * created_at when enriching the lead into a valid brief (see
   * intake/README.md). Timestamp drops millis to satisfy the strict
   * schema pattern (YYYY-MM-DDTHH:MM:SSZ). */
  function utcStamp(now) {
    return now.toISOString().replace(/\.\d{3}Z$/, "Z");
  }
  function projectId(title, now) {
    var slug = (title || "lead").toLowerCase().replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "").slice(0, 40) || "lead";
    var stamp = now.toISOString().slice(0, 10).replace(/-/g, "");
    var rand = ("000" + Math.floor(Math.random() * 0xffff).toString(16)).slice(-4);
    return (slug + "-" + stamp + "-" + rand).slice(0, 64);
  }

  function brief() {
    var now = new Date();
    return {
      format: "p7-project-file",
      version: "1.0.0",
      format_version: "1.0.0",
      project_id: projectId(val("f-title"), now),
      created_at: utcStamp(now),
      capture_method: "human",
      title: val("f-title"),
      client_contact: {
        name: val("f-name"),
        email: val("f-email"),
        company: val("f-company"),
        phone: val("f-phone")
      },
      goal_summary: val("f-goal"),
      problem_statement: val("f-problem"),
      budget_range: val("f-budget"),
      preferred_language: EN ? "en" : "pl",
      marketing_goals: val("f-goals") ? [val("f-goals")] : []
    };
  }

  function validate() {
    var errs = [];
    if (!val("f-title")) errs.push(T.needTitle);
    if (!val("f-name")) errs.push(T.needName);
    if (!EMAIL_RE.test(val("f-email"))) errs.push(T.needEmail);
    if (!val("f-goal")) errs.push(T.needGoal);
    if (!val("f-budget")) errs.push(T.needBudget);
    if (val("f-phone") && !PHONE_RE.test(val("f-phone"))) errs.push(T.badPhone);
    var blob = [val("f-goal"), val("f-problem"), val("f-goals")].join("\n");
    if (SECRET_RE.test(blob)) errs.push(T.secretWarn);
    return errs;
  }

  function init() {
    var form = el("intake-form");
    if (!form) return;
    var budgets = EN ? BUDGETS_EN : BUDGETS_PL;
    var sel = el("f-budget");
    budgets.forEach(function (b) {
      var o = document.createElement("option");
      o.value = b; o.textContent = b;
      sel.appendChild(o);
    });
    el("intake-steps").textContent = [T.step1, T.step2, T.step3].join(" → ");
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var errs = validate();
      var out = el("intake-errors");
      if (errs.length) {
        out.innerHTML = "<ul><li>" + errs.map(function (e) {
          return e.replace(/&/g, "&amp;").replace(/</g, "&lt;");
        }).join("</li><li>") + "</li></ul>";
        el("intake-result").hidden = true;
        return;
      }
      out.innerHTML = "";
      var text = JSON.stringify(brief(), null, 2);
      el("intake-json").textContent = text;
      el("intake-note").textContent = T.ready;
      var dl = el("intake-download");
      dl.href = "data:application/json;charset=utf-8," + encodeURIComponent(text);
      el("intake-result").hidden = false;
    });
    el("intake-copy").addEventListener("click", function () {
      navigator.clipboard.writeText(el("intake-json").textContent);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
