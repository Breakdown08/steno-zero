// steno-zero trainer. All data and layout come from window.STENO_ZERO_DATA (see docs/data.js).
// The random-chord plan and the calibration queue come from window.STENO_ZERO_DRILL (docs/drill.js):
// the page only plays them, everything that needs checking is built in Python.
(function () {
  "use strict";
  var D = window.STENO_ZERO_DATA;
  var P = window.STENO_ZERO_DRILL || null;
  var CALIBRATION_ATTEMPTS = 3;
  var WRONG_FLASH_MS = 600;
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
    drill: $("drill"), calibrate: $("calibrate"), keyboard: $("keyboard"), note: $("note"),
    target: $("target"), targetLeft: $("target-left"), targetRight: $("target-right"),
    targetLabel: $("target-label"), targetNote: $("target-note"),
    result: $("result"), summary: $("summary"), download: $("download"), home: $("home")
  };

  var bitOf = {};            // KeyboardEvent.code -> chord bit
  var boxes = [];
  var targetBoxes = [];
  var flashTimer = null;
  D.keys.forEach(function (k, i) { bitOf[k.code] = 1 << i; });

  var state = {
    mode: "home",            // "home" | "exam" | "drill" | "calibrate"
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
    exam: null,              // exam state, see startExam
    run: null                // random-chord or calibration state, see startDrill and startCalibration
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
      var t = document.createElement("div");
      t.className = "key";
      t.textContent = k.label;
      targetBoxes.push(t);
      (i < 5 ? el.targetLeft : el.targetRight).appendChild(t);
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
    if (state.mode === "drill") { onDrillChord(typed); return; }
    if (state.mode === "calibrate") { onCalibrationChord(typed); return; }
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
    if (state.run && state.run.finished) return;
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
    state.run = null;
    clearFlash();
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

  // ---- random chords and calibration (the plan and the queue come from drill.js)

  function labelOfChord(chord) {
    return D.keys.filter(function (_, i) { return chord >> i & 1; })
      .map(function (k) { return k.label; }).join(" ");
  }

  function showTarget(chord) {
    targetBoxes.forEach(function (b, i) { b.className = chord >> i & 1 ? "key on" : "key"; });
    el.targetLabel.textContent = labelOfChord(chord);
  }

  function clearFlash() {
    if (flashTimer !== null) clearTimeout(flashTimer);
    flashTimer = null;
    el.targetNote.textContent = "";
  }

  function flashWrong(typed) {
    clearFlash();
    el.targetNote.textContent = labelOfChord(typed);
    flashTimer = setTimeout(clearFlash, WRONG_FLASH_MS);
  }

  function resetInput() {
    state.chords = 0;
    state.misses = 0;
    state.maxHeld = 0;
    state.down = {};
    state.chord = 0;
    renderHeld();
    el.help.open = false;
  }

  function runTitle() {
    var r = state.run;
    if (state.mode === "drill") {
      return "Случайные аккорды — блок " + r.block + ", " +
        Math.min(r.k + 1, r.order.length) + " из " + r.order.length;
    }
    return "Калибровка — осталось " + r.queue.length;
  }

  function startDrill() {
    if (!P) return;
    var wanted = parseInt(new URLSearchParams(window.location.search).get("block"), 10);
    var block = wanted >= 0 && wanted < P.blocks.length ? wanted : Math.floor(Math.random() * P.blocks.length);
    var started = new Date().toISOString();
    state.mode = "drill";
    state.run = {
      kind: "drill", block: block, order: P.blocks[block], k: 0, rows: [], shownAt: 0,
      started: started, finished: false, finishedAt: "", downloaded: false,
      session: "drill-" + block + "-" + started.replace(/:/g, "-")
    };
    resetInput();
    el.keyboard.textContent = P.keyboard
      ? "клавиатура: " + P.keyboard.name
      : "план без профиля клавиатуры: заглушённые клавиатурой аккорды дадут ложные промахи";
    el.keyboard.className = P.keyboard ? "" : "warn";
    layoutMode();
    showDrillChord();
  }

  function showDrillChord() {
    var r = state.run;
    showTarget(r.order[r.k]);
    el.status.textContent = "";
    r.shownAt = performance.now();
  }

  function onDrillChord(typed) {
    var r = state.run;
    if (r.finished) return;
    var target = r.order[r.k];
    var upMs = performance.now();
    r.rows.push({
      i: r.k, target: target, typed: typed, shown_ms: r.shownAt,
      down_ms: Math.max(state.chordDown, r.shownAt), up_ms: upMs
    });
    state.chords++;
    if (typed !== target) { state.misses++; flashWrong(typed); } else { clearFlash(); }
    r.k++;
    if (r.k < r.order.length) { layoutMode(); showDrillChord(); return; }
    r.finished = true;
    r.finishedAt = new Date().toISOString();
    layoutMode();
    showDrillResult();
  }

  function showDrillResult() {
    var r = state.run;
    var times = r.rows.filter(function (x) { return x.typed === x.target; })
      .map(function (x) { return x.up_ms - x.shown_ms; }).sort(function (a, b) { return a - b; });
    var m = times.length;
    var median = m === 0 ? null : (times[(m - 1) >> 1] + times[m >> 1]) / 2;
    el.summary.textContent = "Медиана: " + (median === null ? "—" : median.toFixed(0) + " мс") +
      "; промахов: " + state.misses + " из " + r.rows.length +
      "; максимум одновременно: " + state.maxHeld;
  }

  function startCalibration() {
    if (!P) return;
    var started = new Date().toISOString();
    state.mode = "calibrate";
    state.run = {
      kind: "calibrate", queue: P.calibration.slice(), tries: {}, failed: [], attempts: [],
      started: started, finished: false, finishedAt: "", downloaded: false,
      session: "calibration-" + started.replace(/:/g, "-")
    };
    resetInput();
    el.note.textContent = "нажмите показанные клавиши вместе; если сочетание не проходит, " +
      "это может быть клавиатура";
    layoutMode();
    showTarget(state.run.queue[0]);
    renderCalibrationStatus();
  }

  function renderCalibrationStatus() {
    var r = state.run;
    el.status.textContent = "осталось: " + r.queue.length + ", не прошло: " + r.failed.length;
  }

  function onCalibrationChord(typed) {
    var r = state.run;
    if (r.finished) return;
    var target = r.queue.shift();
    r.attempts.push({ target: target, typed: typed, down_ms: state.chordDown, up_ms: performance.now() });
    r.tries[target] = (r.tries[target] || 0) + 1;
    if (typed !== target) {
      if (r.tries[target] < CALIBRATION_ATTEMPTS) r.queue.push(target); else r.failed.push(target);
    }
    if (r.queue.length) {
      layoutMode();
      showTarget(r.queue[0]);
      renderCalibrationStatus();
      return;
    }
    r.finished = true;
    r.finishedAt = new Date().toISOString();
    layoutMode();
    el.status.textContent = "";
    el.summary.textContent = "Не прошли: " +
      (r.failed.length ? r.failed.map(labelOfChord).join(", ") : "нет") +
      "; максимум одновременно: " + state.maxHeld;
  }

  function buildRunLog() {
    var r = state.run;
    var common = {
      version: 1, session: r.session, started: r.started, finished: r.finishedAt,
      user_agent: navigator.userAgent, max_held: state.maxHeld
    };
    if (r.kind === "calibrate") {
      return Object.assign({ format: "steno-zero/keyboard-calibration" }, common, { attempts: r.attempts });
    }
    return Object.assign({ format: "steno-zero/drill-log" }, common, {
      seed: P.seed, block: r.block, max_keys: P.max_keys,
      keyboard: P.keyboard ? { name: P.keyboard.name, sha256: P.keyboard.sha256 } : null,
      presentations: r.rows
    });
  }

  function downloadRun() {
    var blob = new Blob([JSON.stringify(buildRunLog(), null, 1) + "\n"], { type: "application/json" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "steno-zero-" + state.run.session + ".json";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
    state.run.downloaded = true;
  }

  function layoutMode() {
    var exam = state.mode === "exam";
    var other = state.mode === "drill" || state.mode === "calibrate";
    var home = state.mode === "home";
    var x = exam ? state.exam : (other ? state.run : null);
    el.title.textContent = exam
      ? "Экзамен — фраза " + Math.min(state.exam.k + 1, state.exam.order.length) + " из " + state.exam.order.length
      : (other ? runTitle() : "Тренировка");
    el.table.disabled = !home;
    el.mode.textContent = home ? "Экзамен" : "Прервать";
    el.help.hidden = !home;
    el.hintSwitch.hidden = !home;
    el.hint.hidden = !home;
    el.phrase.hidden = other;
    el.field.hidden = other;
    el.drill.hidden = !home || !P;
    el.calibrate.hidden = !home || !P;
    el.target.hidden = !other || state.run.finished;
    el.keyboard.hidden = state.mode !== "drill";
    el.note.hidden = state.mode !== "calibrate";
    el.result.hidden = !(x && x.finished);
    el.mode.hidden = !!(x && x.finished);
  }

  el.mode.addEventListener("click", function () {
    el.mode.blur();
    if (state.mode === "home") { startExam(); return; }
    if (confirm("Прервать? Результат будет потерян.")) goHome();
  });
  el.drill.addEventListener("click", function () { el.drill.blur(); startDrill(); });
  el.calibrate.addEventListener("click", function () { el.calibrate.blur(); startCalibration(); });
  el.download.addEventListener("click", function () {
    if (state.run) downloadRun(); else download();
  });
  el.home.addEventListener("click", function () {
    var x = state.exam || state.run;
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
    var x = state.exam || state.run;
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
