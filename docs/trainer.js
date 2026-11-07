// steno-zero trainer. All data and layout come from window.STENO_ZERO_DATA (see docs/data.js).
(function () {
  "use strict";
  var D = window.STENO_ZERO_DATA;
  var FINGERS = [
    "л. мизинец", "л. безымянный", "л. средний", "л. указательный", "л. указательный, вниз",
    "пр. указательный, вниз", "пр. указательный", "пр. средний", "пр. безымянный", "пр. мизинец"
  ];
  var $ = function (id) { return document.getElementById(id); };
  var el = {
    title: $("title"), table: $("table"), mode: $("mode"), status: $("status"),
    phrase: $("phrase"), hint: $("hint"), hintSwitch: $("hint-switch"), hintOn: $("hint-on"),
    field: $("field"), help: $("help"), layout: $("layout"), entries: $("entries"),
    left: $("left"), right: $("right"), held: $("held"),
    result: $("result"), summary: $("summary"), download: $("download"), home: $("home")
  };

  var bitOf = {};            // KeyboardEvent.code -> chord bit
  var boxes = [];
  D.keys.forEach(function (k, i) { bitOf[k.code] = 1 << i; });

  var state = {
    mode: "home",            // "home" | "exam"
    table: D.tables[0],
    labelOf: {},             // chord -> label, for the current table
    pieceOf: {},             // chord -> piece
    segs: [],                // [piece, chord] of the current phrase
    phraseIdx: -1,
    pos: 0,
    typed: "",               // text of the accepted pieces
    wrong: "",
    down: {},                // code -> true, keys held now
    chord: 0,
    chordDown: 0,
    maxHeld: 0,
    chords: 0,
    misses: 0,
    exam: null               // exam state, see startExam
  };

  function show(piece) { return piece.replace(/ /g, "␣"); }

  function fmtTime(ms) {
    var t = Math.floor(ms / 100) / 10;
    var m = Math.floor(t / 60);
    var s = (t - m * 60).toFixed(1);
    return m + ":" + (s.length < 4 ? "0" : "") + s;
  }

  function span(cls, text) {
    var s = document.createElement("span");
    if (cls) s.className = cls;
    s.textContent = text;
    return s;
  }

  // ---- tables

  function useTable(name) {
    var t = D.tables.filter(function (x) { return x.name === name; })[0] || D.tables[0];
    state.table = t;
    state.labelOf = {};
    state.pieceOf = {};
    t.entries.forEach(function (e) { state.labelOf[e[1]] = e[2]; state.pieceOf[e[1]] = e[0]; });
    el.table.value = t.name;
    el.entries.textContent = "";
    t.entries.forEach(function (e) {
      var d = document.createElement("div");
      d.textContent = show(e[0]) + " — " + e[2];
      el.entries.appendChild(d);
    });
  }

  // ---- phrases

  function nextHomePhrase() {
    var n = D.phrases.length;
    var i = Math.floor(Math.random() * n);
    if (n > 1 && i === state.phraseIdx) i = (i + 1 + Math.floor(Math.random() * (n - 1))) % n;
    setPhrase(i, state.table.segments[i]);
  }

  function setPhrase(idx, segs) {
    state.phraseIdx = idx;
    state.segs = segs;
    state.pos = 0;
    state.typed = "";
    state.wrong = "";
    render();
  }

  function render() {
    var exam = state.mode === "exam";
    var done = state.segs.slice(0, state.pos).map(function (s) { return s[0]; }).join("");
    var rest = state.segs.slice(state.pos).map(function (s) { return s[0]; });
    var next = rest.length ? rest[0] : "";
    var hinted = !exam && el.hintOn.checked && next !== "";
    el.phrase.textContent = "";
    el.phrase.appendChild(span("done", done));
    if (hinted) {
      el.phrase.appendChild(span("next", next));
      el.phrase.appendChild(span("", rest.slice(1).join("")));
    } else {
      el.phrase.appendChild(span("", rest.join("")));
    }
    el.hint.textContent = hinted ? show(next) + " — " + state.labelOf[state.segs[state.pos][1]] : "";
    el.field.textContent = "";
    el.field.appendChild(span("", state.typed));
    el.field.appendChild(span("wrong", state.wrong));
    el.status.textContent = (exam && state.exam ? fmtTime(elapsed()) + "  " : "") +
      "аккордов: " + state.chords + ", промахов: " + state.misses;
  }

  function renderHeld() {
    var n = 0;
    D.keys.forEach(function (k, i) {
      var on = !!state.down[k.code];
      boxes[i].className = on ? "key on" : "key";
      if (on) n++;
    });
    if (n > state.maxHeld) state.maxHeld = n;
    el.held.textContent = "максимум одновременно: " + state.maxHeld;
  }

  // ---- layout and help

  function buildStatic() {
    D.keys.forEach(function (k, i) {
      var b = document.createElement("div");
      b.className = "key";
      b.textContent = k.label;
      boxes.push(b);
      (i < 5 ? el.left : el.right).appendChild(b);
    });
    el.layout.textContent = "";
    D.keys.forEach(function (k, i) {
      var tr = document.createElement("tr");
      [String(i), k.label, FINGERS[i] || ""].forEach(function (text) {
        var td = document.createElement("td");
        td.textContent = text;
        tr.appendChild(td);
      });
      el.layout.appendChild(tr);
    });
    D.tables.forEach(function (t) {
      var o = document.createElement("option");
      o.value = t.name;
      o.textContent = t.name;
      el.table.appendChild(o);
    });
  }

  // ---- chords

  function onChord(typed) {
    var exam = state.mode === "exam" ? state.exam : null;
    if (exam && exam.finished) return;
    var target = state.segs[state.pos][1];
    var upMs = performance.now();
    state.chords++;
    if (exam) {
      exam.attempts.push({
        phrase: state.phraseIdx, pos: state.pos, target: target, typed: typed,
        down_ms: state.chordDown, up_ms: upMs
      });
    }
    if (typed !== target) {
      state.misses++;
      state.wrong = state.pieceOf[typed] === undefined ? "?" : show(state.pieceOf[typed]);
      render();
      return;
    }
    state.wrong = "";
    state.typed += state.segs[state.pos][0];
    state.pos++;
    if (state.pos < state.segs.length) { render(); return; }
    if (exam) { nextExamPhrase(); } else { nextHomePhrase(); }
  }

  function isChordKey(e) {
    return bitOf[e.code] !== undefined;
  }

  function hasModifier(e) {
    return e.ctrlKey || e.altKey || e.metaKey;
  }

  document.addEventListener("keydown", function (e) {
    if (e.code === D.help_key && !hasModifier(e)) {
      e.preventDefault();
      if (state.mode === "home" && !e.repeat) el.help.open = !el.help.open;
      return;
    }
    if (e.code === "Escape" && state.mode === "home") {
      nextHomePhrase();
      return;
    }
    if (!isChordKey(e) || hasModifier(e)) return;
    e.preventDefault();
    if (e.repeat) return;
    if (state.mode === "exam" && state.exam.finished) return;
    if (!Object.keys(state.down).length) state.chordDown = performance.now();
    if (state.mode === "exam" && state.exam.t0 === null) state.exam.t0 = state.chordDown;
    state.down[e.code] = true;
    state.chord |= bitOf[e.code];
    renderHeld();
  });

  document.addEventListener("keyup", function (e) {
    if (!isChordKey(e)) return;
    e.preventDefault();
    if (!state.down[e.code]) return;
    delete state.down[e.code];
    renderHeld();
    if (Object.keys(state.down).length || state.chord === 0) return;
    var typed = state.chord;
    state.chord = 0;
    onChord(typed);
  });

  window.addEventListener("blur", function () {
    state.down = {};
    state.chord = 0;
    renderHeld();
  });

  // ---- exam

  function elapsed() {
    var x = state.exam;
    if (!x || x.t0 === null) return 0;
    var end = x.finished ? x.attempts[x.attempts.length - 1].up_ms : performance.now();
    return end - x.t0;
  }

  function startExam() {
    var all = D.exam_phrases.map(function (_, i) { return i; });
    var n = Math.min(D.exam_size, all.length);
    var order = [];
    while (order.length < n) order.push(all.splice(Math.floor(Math.random() * all.length), 1)[0]);
    var started = new Date().toISOString();
    state.mode = "exam";
    state.exam = {
      order: order, k: 0, started: started, finished: false, finishedAt: "", t0: null,
      attempts: [], downloaded: false, session: state.table.name + "-" + started.replace(/:/g, "-"),
      timer: setInterval(render, 100)
    };
    state.chords = 0;
    state.misses = 0;
    state.maxHeld = 0;
    state.down = {};
    state.chord = 0;
    renderHeld();
    el.help.open = false;
    setPhrase(order[0], state.table.exam_segments[order[0]]);
    layoutMode();
  }

  function nextExamPhrase() {
    var x = state.exam;
    x.k++;
    if (x.k < x.order.length) {
      setPhrase(x.order[x.k], state.table.exam_segments[x.order[x.k]]);
      layoutMode();
      return;
    }
    x.finished = true;
    x.finishedAt = new Date().toISOString();
    clearInterval(x.timer);
    render();
    layoutMode();
    showResult();
  }

  function showResult() {
    var x = state.exam;
    var chars = x.order.reduce(function (s, i) { return s + D.exam_phrases[i].length; }, 0);
    var timeS = (x.attempts[x.attempts.length - 1].up_ms - x.attempts[0].down_ms) / 1000;
    var misses = x.attempts.filter(function (a) { return a.typed !== a.target; }).length;
    el.summary.textContent = "Время: " + timeS.toFixed(1) + " с; символов в минуту: " +
      (chars / timeS * 60).toFixed(0) + "; промахов: " + misses + " из " + x.attempts.length +
      " (" + (misses / x.attempts.length * 100).toFixed(1) + "%)";
  }

  function buildLog() {
    var x = state.exam;
    return {
      format: "steno-zero/trainer-log",
      version: 1,
      session: x.session,
      table: state.table.name,
      table_sha256: state.table.sha256,
      started: x.started,
      finished: x.finishedAt,
      user_agent: navigator.userAgent,
      max_held: state.maxHeld,
      phrases: x.order,
      chars: x.order.reduce(function (s, i) { return s + D.exam_phrases[i].length; }, 0),
      attempts: x.attempts
    };
  }

  function download() {
    var blob = new Blob([JSON.stringify(buildLog(), null, 1) + "\n"], { type: "application/json" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "steno-zero-" + state.exam.session + ".json";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
    state.exam.downloaded = true;
  }

  function goHome() {
    if (state.exam) clearInterval(state.exam.timer);
    state.exam = null;
    state.mode = "home";
    state.chords = 0;
    state.misses = 0;
    state.maxHeld = 0;
    state.down = {};
    state.chord = 0;
    renderHeld();
    el.result.hidden = true;
    nextHomePhrase();
    layoutMode();
  }

  function layoutMode() {
    var exam = state.mode === "exam";
    el.title.textContent = exam
      ? "Экзамен — фраза " + Math.min(state.exam.k + 1, state.exam.order.length) + " из " + state.exam.order.length
      : "Тренировка";
    el.table.disabled = exam;
    el.mode.textContent = exam ? "Прервать" : "Экзамен";
    el.help.hidden = exam;
    el.hintSwitch.hidden = exam;
    el.hint.hidden = exam;
    el.result.hidden = !(exam && state.exam.finished);
    el.mode.hidden = exam && state.exam.finished;
  }

  el.mode.addEventListener("click", function () {
    el.mode.blur();
    if (state.mode === "home") { startExam(); return; }
    if (confirm("Прервать экзамен? Результат будет потерян.")) goHome();
  });
  el.download.addEventListener("click", download);
  el.home.addEventListener("click", function () {
    var x = state.exam;
    if (x && x.finished && !x.downloaded && !confirm("Журнал не скачан. Всё равно вернуться домой?")) return;
    goHome();
  });
  el.table.addEventListener("change", function () {
    el.table.blur();
    useTable(el.table.value);
    nextHomePhrase();
  });
  el.hintOn.addEventListener("change", function () { el.hintOn.blur(); render(); });
  window.addEventListener("beforeunload", function (e) {
    var x = state.exam;
    if (x && x.finished && !x.downloaded) {
      e.preventDefault();
      e.returnValue = "";
    }
  });

  buildStatic();
  var wanted = new URLSearchParams(window.location.search).get("table");
  useTable(wanted);
  renderHeld();
  nextHomePhrase();
  layoutMode();
})();
