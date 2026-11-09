/* Guided intake form (chatbot v1: form-first). No backend: validates in
 * the browser, then offers the brief as a JSON download + copyable text.
 * Field set mirrors the P7 intake validator; the server re-validates. */
(function () {
  "use strict";
  var EN = document.documentElement.lang === "en";
  var T = EN ? {
    needTitle: "Give the project a short title.",
    needName: "Tell us your name.",
    needEmail: "A valid email is required so we can reply.",
    needGoal: "Describe what you want to achieve.",
    needBudget: "Pick a budget range.",
    secretWarn: "This looks like a secret — remove keys/passwords before sending.",
    ready: "Brief ready. Download the JSON and attach it to your email to us.",
    step1: "1. Contact",
    step2: "2. Project",
    step3: "3. Budget & review"
  } : {
    needTitle: "Nadaj projektowi krotki tytul.",
    needName: "Podaj imie i nazwisko.",
    needEmail: "Prawidlowy e-mail jest wymagany, aby odpowiedziec.",
    needGoal: "Opisz, co chcesz osiagnac.",
    needBudget: "Wybierz przedzial budzetu.",
    secretWarn: "To wyglada na sekret — usun klucze/hasla przed wyslaniem.",
    ready: "Zapytanie gotowe. Pobierz JSON i zalacz go do e-maila do nas.",
    step1: "1. Kontakt",
    step2: "2. Projekt",
    step3: "3. Budzet i podsumowanie"
  };
  var SECRET_RE = /(api[_-]?key|password|secret|token)\s*[:=]|-----BEGIN.*PRIVATE KEY-----|(sk-|ghp_)[A-Za-z0-9]{8,}/i;
  var EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
  var BUDGETS_PL = ["<10k", "10–30k", "30–80k", "80k+", "undisclosed"];
  var BUDGETS_EN = ["<2k", "2-5k", "5-15k", "15k+", "undisclosed"];

  function el(id) { return document.getElementById(id); }
  function val(id) { var n = el(id); return n ? n.value.trim() : ""; }

  function brief() {
    return {
      format: "p7-project-file",
      version: "1.0.0",
      title: val("f-title"),
      client_contact: {
        name: val("f-name"),
        email: val("f-email"),
        company: val("f-company"),
        phone: ""
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
