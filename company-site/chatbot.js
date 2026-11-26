/* Site chatbot v1: deterministic FAQ matcher, no open generation.
 *
 * Design (see docs/chatbot-options-20261101.md, option C held for P7):
 * the bot only serves canned answers from the KNOWLEDGE array below.
 * Every answer traces to site copy (source page + exact quote, enforced
 * by tests/test_company_site.py) or the P7 knowledge bank. Unknown input
 * falls back to the intake form link — the bot can never invent an
 * answer, leak data, or burn model budget. There is no backend.
 */
(function () {
  "use strict";
  var EN = document.documentElement.lang === "en";

  /* KB entry shape (fixed key order: tests regex source+quote pairs):
   * id, source PL/EN pages, exact quotes, keywords, canned answers. */
  var KNOWLEDGE = [
    {
      id: "price",
      source: "index.html", quote: "nie publikujemy cennika",
      source_en: "en/index.html", quote_en: "no price list",
      keywords: ["cena", "ceny", "cenę", "koszt", "koszty", "kosztuje", "ile", "cennik", "wycena", "wycenę", "budżet"],
      keywords_en: ["price", "pricing", "cost", "costs", "much", "budget", "quote", "charge"],
      answer: "Każde wdrożenie to indywidualna wycena stała po rozpoznaniu; nie publikujemy cennika. Orientacyjnie: rozpoznanie i lekkie poprawki — poniżej 10 tys. zł; pełne obiegi — zwykle 10–30 tys. zł; większe integracje — 30–80 tys. zł.",
      answer_en: "Every build is an individual fixed quote after discovery; we publish no price list. Roughly: discovery and light fixes — under \u20ac2k; full workflows — usually \u20ac2\u20135k; larger integrations — \u20ac5\u201315k."
    },
    {
      id: "process",
      source: "index.html", quote: "Płatne rozpoznanie",
      source_en: "en/index.html", quote_en: "Paid discovery",
      keywords: ["jak", "proces", "kroki", "działa", "współprac", "zacz", "start", "rozpoznanie", "przebieg"],
      keywords_en: ["how", "process", "steps", "work", "start", "begin", "discovery"],
      answer: "Trzy kroki, każdy z pisemnym wynikiem: płatne rozpoznanie z raportem, jedna automatyzacja w stałej cenie z testem akceptacyjnym, potem plan opieki.",
      answer_en: "Three steps, each with a written result: paid discovery with a report, one automation at a fixed price with an acceptance test, then a care plan."
    },
    {
      id: "services",
      source: "uslugi.html", quote: "Automatyzacja jednego procesu",
      source_en: "en/services.html", quote_en: "One-workflow automation",
      keywords: ["usług", "ofert", "automatyzacja", "integrac", "stron", "robicie", "robisz", "łączenie"],
      keywords_en: ["services", "offer", "automation", "integration", "website", "do you do"],
      answer: "Cztery usługi: automatyzacja jednego procesu (oferta główna), łączenie systemów, strony z opieką, prywatne AI tylko jako dodatek. Każdą poprzedza płatne rozpoznanie.",
      answer_en: "Four services: one-workflow automation (hero offer), connecting systems, websites with aftercare, private AI as an add-on only. Each starts with paid discovery."
    },
    {
      id: "notdo",
      source: "uslugi.html", quote: "Czego nie robimy",
      source_en: "en/services.html", quote_en: "What we don't do",
      keywords: ["nie rob", "czego nie", "ograniczenia", "mobiln", "sklep", "sla", "wykluczenia"],
      keywords_en: ["don't do", "not do", "limits", "mobile", "shop", "ecommerce", "sla", "exclusions"],
      answer: "Nie robimy: aplikacji mobilnych, platform sklepowych, całodobowego SLA, autonomicznych botów bez nadzoru ani systemów regulowanych. Jeśli Twoja potrzeba wpada na listę — powiemy to w pierwszej odpowiedzi.",
      answer_en: "We don't do: mobile apps, ecommerce platforms, 24/7 SLAs, unsupervised autonomous bots, or regulated cores. If your need lands on the list, we say so in the first reply."
    },
    {
      id: "area",
      source: "index.html", quote: "Bielsko-Biała, Cieszyn",
      source_en: "en/index.html", quote_en: "Bielsko-Biała, Cieszyn",
      keywords: ["gdzie", "okolica", "dojazd", "miejscu", "miejsc", "zdalnie", "miasta", "skoczów", "zasięg"],
      keywords_en: ["where", "area", "onsite", "on-site", "remote", "cities", "visit", "reach"],
      answer: "Wizyty na miejscu w ok. godzinie jazdy ze Skoczowa: Bielsko-Biała, Cieszyn, Żywiec, Tychy, obrzeża Katowic. Zdalnie: reszta Polski i UE.",
      answer_en: "On-site visits within about an hour of Skoczów: Bielsko-Biała, Cieszyn, Żywiec, Tychy, Katowice edge. Remote: the rest of Poland and the EU."
    },
    {
      id: "who",
      source: "index.html", quote: "Założyciel, senior",
      source_en: "en/index.html", quote_en: "The founder, a senior",
      keywords: ["kto", "zespół", "firma", "buduje", "właściciel", "jakub", "zespół"],
      keywords_en: ["who", "team", "company", "builds", "founder", "owner"],
      answer: "Założyciel, senior, osobiście — ta sama osoba, z którą rozmawiasz. Nie wymyślamy zespołu ani zdjęć biura.",
      answer_en: "The founder, a senior, personally — the same person you talk to. We don't invent a team or office photos."
    },
    {
      id: "contact",
      source: "kontakt.html", quote: "Zapytanie ofertowe",
      source_en: "en/contact.html", quote_en: "Project enquiry",
      keywords: ["kontakt", "email", "mail", "telefon", "napisać", "zapytanie", "odezwać"],
      keywords_en: ["contact", "email", "mail", "phone", "write", "enquiry", "reach"],
      answer: "Opisz swój proces w zapytaniu ofertowym — odpowiadam osobiście z pierwszymi pytaniami. Jeśli podasz telefon, oddzwonię.",
      answer_en: "Describe your process in a project enquiry — I reply personally with first questions. If you leave a phone number, I'll call back."
    },
    {
      id: "nogo",
      source: "index.html", quote: "nie róbcie tego",
      source_en: "en/index.html", quote_en: "don't do this",
      keywords: ["nie opłaca", "opłac", "zwrot", "nie róbcie", "warto", "ryzyko"],
      keywords_en: ["pay off", "worth", "payback", "risk", "don't do"],
      answer: "Tak — rozpoznanie może zakończyć się uczciwym „nie róbcie tego”, z wyliczeniem zwrotu policzonym wspólnie. Decyzja „nie” to dostarczony wynik, nie porażka.",
      answer_en: "Yes — discovery may conclude with an honest “don't do this”, with payback math computed together. A “no” is a delivered outcome, not a failure."
    },
    {
      id: "company",
      source: "index.html", quote: "NIP 5482782178",
      source_en: "en/index.html", quote_en: "NIP 5482782178",
      keywords: ["nip", "regon", "beskidlogic", "nazwa firmy", "dane firmy", "jaworski", "firma it"],
      keywords_en: ["nip", "regon", "beskidlogic", "company name", "company details", "jaworski", "tax id"],
      answer: "BeskidLogic — Jakub Jaworski BeskidLogic, Skoczów. NIP 5482782178, REGON 546248869.",
      answer_en: "BeskidLogic — Jakub Jaworski BeskidLogic, Skoczów. NIP 5482782178, REGON 546248869."
    }
  ];

  var FALLBACK = {
    answer: "Nie znam odpowiedzi na to pytanie — żeby niczego nie zmyślić, opisz sprawę w zapytaniu ofertowym. Odpowiadam osobiście.",
    answer_en: "I don't know the answer to that — rather than invent one, describe it in a project enquiry. I reply personally."
  };

  var FOLD = { "ą": "a", "ć": "c", "ę": "e", "ł": "l", "ń": "n", "ó": "o", "ś": "s", "ź": "z", "ż": "z" };
  function fold(text) {
    return String(text).toLowerCase().replace(/[ąćęłńóśźż]/g, function (ch) { return FOLD[ch]; });
  }
  function escapeRegExp(text) {
    return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }
  function escHtml(text) {
    return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  /* Best entry by keyword hits (folded prefix match); ties keep KB order. */
  function matchEntry(text) {
    var folded = " " + fold(text) + " ";
    var best = null, bestScore = 0;
    KNOWLEDGE.forEach(function (entry) {
      var words = EN ? entry.keywords_en : entry.keywords;
      var score = 0;
      words.forEach(function (kw) {
        var stem = escapeRegExp(fold(kw));
        /* Short words need a trailing boundary ("jak" must not fire on
         * "jaka"); longer stems keep prefix matching for inflections. */
        var tail = fold(kw).length <= 3 ? "($|[^a-z0-9])" : "";
        var pattern = new RegExp("(^|[^a-z0-9])" + stem + tail);
        if (pattern.test(folded)) score += 1;
      });
      if (score > bestScore) { bestScore = score; best = entry; }
    });
    return bestScore > 0 ? best : null;
  }

  function formLink() {
    return EN ? "contact.html" : "kontakt.html";
  }

  function reply(text) {
    var entry = matchEntry(text);
    var answer = entry ? (EN ? entry.answer_en : entry.answer) : (EN ? FALLBACK.answer_en : FALLBACK.answer);
    var link = '<a href="' + formLink() + '">' + (EN ? "Open the enquiry form" : "Otwórz formularz zapytania") + "</a>";
    return { id: entry ? entry.id : "fallback", html: "<p>" + escHtml(answer) + "</p><p>" + link + "</p>" };
  }

  /* Floating widget: injected, so pages only add the script tag. */
  function mount() {
    if (!document.body) return;
    var fab = document.createElement("button");
    fab.type = "button";
    fab.id = "chat-fab";
    fab.className = "chat-fab";
    fab.setAttribute("aria-label", EN ? "Open chat" : "Otwórz czat");
    fab.textContent = "?";
    var panel = document.createElement("div");
    panel.id = "chat-panel";
    panel.className = "chat-panel";
    panel.hidden = true;
    panel.innerHTML =
      '<div class="chat-msgs" id="chat-msgs" aria-live="polite"></div>' +
      '<form id="chat-form" class="chat-form"><input type="text" id="chat-input" autocomplete="off" placeholder="' +
      escHtml(EN ? "Ask about services, pricing, area…" : "Zapytaj o usługi, ceny, okolicę…") +
      '"><button type="submit" id="chat-send">' + (EN ? "Send" : "Wyślij") + "</button></form>";
    document.body.appendChild(fab);
    document.body.appendChild(panel);
    var msgs = document.getElementById("chat-msgs");
    function push(role, html) {
      var div = document.createElement("div");
      div.className = "chat-msg " + role;
      if (role === "user") div.textContent = html;
      else div.innerHTML = html;
      msgs.appendChild(div);
      msgs.scrollTop = msgs.scrollHeight;
    }
    fab.addEventListener("click", function () {
      panel.hidden = !panel.hidden;
      if (!panel.hidden && !msgs.hasChildNodes()) {
        push("bot", "<p>" + escHtml(EN
          ? "Hi! I answer questions about services, pricing, and area — from the site content only."
          : "Cześć! Odpowiadam na pytania o usługi, ceny i okolicę — wyłącznie na podstawie treści strony.") + "</p>");
      }
    });
    document.getElementById("chat-form").addEventListener("submit", function (ev) {
      ev.preventDefault();
      var input = document.getElementById("chat-input");
      var text = input.value.trim();
      if (!text) return;
      push("user", text);
      push("bot", reply(text).html);
      input.value = "";
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();
})();
