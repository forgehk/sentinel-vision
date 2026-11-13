/* Sentinel Vision — page behaviour.
   Demo player with three scenes, the event log and the raw model output that follow the video,
   the in-browser detector, and the page's motion. No dependencies. */
(function () {
  'use strict';
  var root = document.documentElement;
  root.classList.add('js');
  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) { var n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; }
  function fmt(t) { var m = Math.floor(t / 60), s = t - m * 60; return (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s.toFixed(1); }

  /* ------------------------------------------------------------------ headline: words pull from narrow to wide */
  (function headline() {
    var h = $('headline'); if (!h || reduceMotion || !document.fonts || !document.fonts.ready) return;
    var text = h.textContent.trim(), words = text.split(/\s+/), spans = [];
    h.setAttribute('aria-label', text); h.textContent = ''; h.style.opacity = '0';
    words.forEach(function (w, i) {
      var s = el('span', 'w', w); s.setAttribute('aria-hidden', 'true'); s.style.setProperty('--i', i); spans.push(s);
      h.appendChild(s); if (i < words.length - 1) h.appendChild(document.createTextNode(' '));
    });
    var started = false;
    function go() {
      if (started) return; started = true;
      spans.forEach(function (s) { s.style.width = Math.ceil(s.getBoundingClientRect().width) + 'px'; });   // lock final widths so lines cannot reflow mid-animation
      h.style.opacity = ''; h.classList.add('go');
      spans[spans.length - 1].addEventListener('animationend', function () { spans.forEach(function (s) { s.style.width = ''; }); });
    }
    document.fonts.ready.then(go); setTimeout(go, 1200);
  })();

  /* ------------------------------------------------------------------ demo player */
  var SCENES = {
    office: {
      video: '/media/office.mp4', poster: '/media/office-poster.jpg', data: '/data/office.json',
      label: 'Overhead view of an office. Each desk is outlined and labelled with a status that changes as one person leaves and two others pick up their phones.',
      events: [
        { t: 1.0, kind: 'info', title: 'Six desks mapped', detail: 'Seats learned from the first second of video.' },
        { t: 4.79, kind: 'alert', title: 'ID 1 away from desk', detail: 'Seat empty for three quarters of a second.' },
        { t: 7.04, kind: 'alert', title: 'ID 6 phone in hand', detail: "Phone detected inside the person's outline." },
        { t: 8.46, kind: 'alert', title: 'ID 4 phone in hand', detail: "Phone detected inside the person's outline." }
      ]
    },
    shop: {
      video: '/media/shop.mp4', poster: '/media/shop-poster.jpg', data: '/data/shop.json',
      label: 'Ceiling camera view of a small supermarket with three outlined zones: an aisle, the stockroom door and the checkout queue. Each zone changes colour as its rule fires.',
      events: [
        { t: 3.83, kind: 'alert', title: 'Stockroom door, person entered', detail: 'In the doorway zone for a third of a second.' },
        { t: 5.0, kind: 'alert', title: 'Aisle 1, dwell over 5 seconds', detail: 'The same person has been in the zone since the clip began.' },
        { t: 7.83, kind: 'info', title: 'Stockroom door cleared', detail: 'Zone empty for two and a half seconds.' },
        { t: 8.21, kind: 'alert', title: 'Checkout queue over its limit', detail: 'Four people in line against a limit of three.' }
      ]
    },
    home: {
      video: '/media/home.mp4', poster: '/media/home-poster.jpg', data: '/data/home.json',
      label: 'Camera under the eave of a house looking over the front lawn, driveway and path. A car pulls in, a dog crosses the lawn and a person walks toward the door; each is outlined and labelled.',
      events: [
        { t: 3.46, kind: 'notice', title: 'Driveway, vehicle arrived', detail: 'Logged as a notice, not an alarm.' },
        { t: 3.5, kind: 'info', title: 'Lawn, pet, no alert', detail: 'Dogs and cats are recognised and left out of alerts.' },
        { t: 6.5, kind: 'alert', title: 'Front path, person approaching the door', detail: 'In the zone for a third of a second.' }
      ]
    },
    exam: {
      video: '/media/exam.mp4', poster: '/media/exam-poster.jpg', data: '/data/exam.json',
      label: 'Camera high on the wall of an exam room where ten candidates write at separate desks. Each is outlined, with a desk zone and head keypoints. One turns toward the next desk and is flagged, and another is flagged for a phone.',
      events: [
        { t: 1.0, kind: 'info', title: 'Ten seats mapped', detail: 'Each candidate gets a desk zone and a baseline head direction.' },
        { t: 2.0, kind: 'notice', title: 'S8 under review', detail: 'Head turned 58 degrees, pointing at desk S9.' },
        { t: 2.83, kind: 'alert', title: 'S8 flagged, looking at desk S9', detail: 'The look held until the risk score passed 60.' },
        { t: 4.71, kind: 'alert', title: 'S9 flagged, phone at the desk', detail: 'A phone stayed in the desk zone for a third of a second.' }
      ]
    }
  };

  var video = $('demoVideo');
  if (video) (function player() {
    var playBtn = $('playToggle'), soundBtn = $('soundToggle'), timecode = $('timecode'), fill = $('scrubFill'), marks = $('scrubMarks');
    var log = $('eventLog'), rawRows = $('rawRows'), rawMeta = $('rawMeta'), frameBox = video.parentNode;
    var current = 'office', rows = [], cache = {}, lastFrame = -1, view = 'events', pool = [];

    function setPlayLabel() {
      playBtn.textContent = video.paused ? 'Play' : 'Pause';
      playBtn.setAttribute('aria-label', video.paused ? 'Play the demo' : 'Pause the demo');
    }
    function renderLog() {
      log.textContent = ''; rows = [];
      SCENES[current].events.forEach(function (e) {
        var li = el('li'); li.setAttribute('data-t', e.t); li.setAttribute('data-kind', e.kind);
        var time = el('time', null, fmt(e.t)), body = el('div');
        body.appendChild(el('strong', null, e.title)); body.appendChild(el('span', null, e.detail));
        li.appendChild(time); li.appendChild(body); log.appendChild(li); rows.push({ li: li, t: e.t });
      });
    }
    function placeMarks() {
      marks.textContent = ''; if (!video.duration) return;
      SCENES[current].events.forEach(function (e) {
        if (e.kind === 'info') return;
        var m = el('i', 'scrub-mark'); m.setAttribute('data-kind', e.kind); m.style.left = (e.t / video.duration * 100) + '%'; marks.appendChild(m);
      });
    }
    function loadData(name) {
      if (cache[name]) return;
      cache[name] = 'loading';
      fetch(SCENES[name].data).then(function (r) { return r.json(); }).then(function (d) { cache[name] = d; lastFrame = -1; })
        .catch(function () { cache[name] = null; if (name === current) { rawRows.textContent = ''; rawMeta.textContent = 'The detections file could not be loaded.'; } });
    }
    function rowAt(i) {
      if (!pool[i]) {
        var tr = el('tr'), c = el('td'), conf = el('td', 'conf'), bar = el('i'), num = el('span'), box = el('td');
        conf.appendChild(num); conf.appendChild(bar); tr.appendChild(c); tr.appendChild(conf); tr.appendChild(box);
        pool[i] = { tr: tr, c: c, num: num, bar: bar, box: box };
      }
      return pool[i];
    }
    function renderRaw(t) {
      var d = cache[current]; if (!d || d === 'loading') return;
      var f = Math.max(0, Math.min(d.frames.length - 1, Math.floor(t * d.fps + 0.01))); if (f === lastFrame) return; lastFrame = f;
      var dets = d.frames[f].slice().sort(function (a, b) { return b[1] - a[1]; }).slice(0, 9);
      if (rawRows.firstChild && rawRows.firstChild.nodeType === 1 && !rawRows.firstChild.__pooled) rawRows.textContent = '';
      dets.forEach(function (det, i) {
        var r = rowAt(i); r.tr.__pooled = true;
        r.c.textContent = d.classes[det[0]]; r.num.textContent = det[1].toFixed(2); r.bar.style.width = Math.round(det[1] * 100) + '%';
        r.box.textContent = det[2] + ', ' + det[3] + '  ' + (det[4] - det[2]) + '×' + (det[5] - det[3]);
        if (r.tr.parentNode !== rawRows) rawRows.appendChild(r.tr);
      });
      for (var i = dets.length; i < pool.length; i++) if (pool[i].tr.parentNode === rawRows) rawRows.removeChild(pool[i].tr);
      rawMeta.textContent = 'Frame ' + (f + 1) + ' of ' + d.frames.length + '. ' + d.model + ' at ' + d.imgsz + ' px, every detection above ' + Math.round(d.min_confidence * 100) + '% confidence.';
    }
    function frame() {
      var t = video.currentTime || 0;
      timecode.textContent = fmt(t);
      if (video.duration) fill.style.width = (t / video.duration * 100) + '%';
      for (var i = 0; i < rows.length; i++) rows[i].li.classList.toggle('on', t >= rows[i].t);
      if (view === 'raw') renderRaw(t);
      requestAnimationFrame(frame);
    }
    function hasAudio() {
      if (typeof video.mozHasAudio === 'boolean') return video.mozHasAudio;
      if (typeof video.webkitAudioDecodedByteCount === 'number') return video.webkitAudioDecodedByteCount > 0;
      if (video.audioTracks && typeof video.audioTracks.length === 'number') return video.audioTracks.length > 0;
      return false;
    }
    function checkAudio() { if (hasAudio()) soundBtn.hidden = false; }
    function selectScene(name) {
      if (!SCENES[name] || name === current) return;
      var wasPlaying = !video.paused; current = name; lastFrame = -1;
      document.querySelectorAll('.scene-tabs [role="tab"]').forEach(function (b) { b.setAttribute('aria-selected', String(b.getAttribute('data-scene') === name)); });
      frameBox.classList.add('swap');
      video.poster = SCENES[name].poster; video.src = SCENES[name].video; video.setAttribute('aria-label', SCENES[name].label); video.load();
      renderLog(); marks.textContent = ''; loadData(name);
      if (wasPlaying || !reduceMotion) video.play().catch(function () {});
    }

    playBtn.addEventListener('click', function () { if (video.paused) video.play().catch(function () {}); else video.pause(); });
    video.addEventListener('play', setPlayLabel); video.addEventListener('pause', setPlayLabel);
    video.addEventListener('loadedmetadata', placeMarks);
    video.addEventListener('loadeddata', function () { frameBox.classList.remove('swap'); checkAudio(); });
    video.addEventListener('timeupdate', checkAudio);
    soundBtn.addEventListener('click', function () {
      video.muted = !video.muted; soundBtn.textContent = video.muted ? 'Sound on' : 'Sound off'; soundBtn.setAttribute('aria-pressed', String(!video.muted));
    });
    document.querySelectorAll('.scene-tabs [role="tab"]').forEach(function (b) { b.addEventListener('click', function () { selectScene(b.getAttribute('data-scene')); }); });
    document.querySelectorAll('.side-tabs [role="tab"]').forEach(function (b) {
      b.addEventListener('click', function () {
        view = b.getAttribute('data-view'); lastFrame = -1;
        document.querySelectorAll('.side-tabs [role="tab"]').forEach(function (o) { o.setAttribute('aria-selected', String(o === b)); });
        document.querySelectorAll('.side-panel').forEach(function (p) { p.hidden = p.getAttribute('data-view') !== view; });
        if (view === 'raw') loadData(current);
      });
    });
    document.querySelectorAll('[role="tablist"]').forEach(function (list) {
      list.addEventListener('keydown', function (e) {
        if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
        var tabs = Array.prototype.slice.call(list.querySelectorAll('[role="tab"]')), i = tabs.indexOf(document.activeElement); if (i < 0) return;
        var n = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length]; n.focus(); n.click(); e.preventDefault();
      });
    });

    renderLog(); loadData('office');
    if (!reduceMotion) video.play().catch(function () {});
    setPlayLabel(); placeMarks(); requestAnimationFrame(frame);
    window.__sentinelDemo = { select: selectScene };
  })();

  /* ------------------------------------------------------------------ in-view moments and counters */
  (function inView() {
    var targets = Array.prototype.slice.call(document.querySelectorAll('.reveal, .steps, .facts'));
    function countUp(n) {
      var to = +n.getAttribute('data-to'), t0 = performance.now(), dur = 900;
      (function step(now) {
        var u = Math.min(1, (now - t0) / dur), v = Math.round(to * (1 - Math.pow(1 - u, 3)));
        n.textContent = v.toLocaleString('en-US'); if (u < 1) requestAnimationFrame(step);
      })(t0);
    }
    function seen(n) {
      if (n.classList.contains('seen')) return; n.classList.add('seen');
      if (n.classList.contains('facts') && !reduceMotion) n.querySelectorAll('.count').forEach(countUp);
    }
    if (!('IntersectionObserver' in window)) { targets.forEach(seen); return; }
    var io = new IntersectionObserver(function (es) { es.forEach(function (e) { if (e.isIntersecting) { seen(e.target); io.unobserve(e.target); } }); }, { threshold: 0.3 });
    targets.forEach(function (n) { io.observe(n); });
  })();

  /* ------------------------------------------------------------------ pointer reticle */
  (function reticle() {
    var r = $('reticle'); if (!r || !window.matchMedia || !window.matchMedia('(hover: hover) and (pointer: fine)').matches) return;
    var label = r.querySelector('b'), active = null, raf = 0;
    var SEL = 'a.button, button, .site-nav a, .site-footer nav a, .brand, .status img, video, canvas, .facts a';
    function name(n) {
      if (n.matches('video')) return 'VIDEO FEED';
      if (n.matches('canvas')) return n.closest('.stage') ? '3D MODEL' : 'FRAME';
      if (n.matches('img')) return 'IMAGE';
      if (n.matches('.brand')) return 'LOGO';
      if (n.matches('[role="tab"], .sample')) return 'TAB';
      if (n.matches('button, a.button')) return 'BUTTON';
      return 'LINK';
    }
    function place() {
      raf = 0; if (!active) return;
      var b = active.getBoundingClientRect(), pad = 5;
      if (b.bottom < 0 || b.top > window.innerHeight) { hide(); return; }
      r.style.transform = 'translate(' + (b.left - pad) + 'px,' + (b.top - pad) + 'px)';
      r.style.width = (b.width + pad * 2) + 'px'; r.style.height = (b.height + pad * 2) + 'px';
    }
    function hide() { active = null; r.classList.remove('on'); }
    document.addEventListener('pointerover', function (e) {
      var n = e.target.closest ? e.target.closest(SEL) : null;
      if (n && n.closest('.try-side, form')) n = null;     // controls that sit close together stay unmarked
      if (!n || n.closest('.hero-cam')) { hide(); return; }
      if (n === active) return;
      active = n; label.textContent = name(n); place(); r.classList.add('on');
    });
    document.addEventListener('pointerleave', hide);
    window.addEventListener('scroll', function () { if (active && !raf) raf = requestAnimationFrame(place); }, { passive: true });
    window.addEventListener('resize', function () { if (active && !raf) raf = requestAnimationFrame(place); });
  })();

  /* ------------------------------------------------------------------ run the detector in this browser */
  (function tryDetector() {
    var canvas = $('tryCanvas'); if (!canvas) return;
    var ctx = canvas.getContext('2d'), runBtn = $('tryRun'), status = $('tryStatus'), table = $('tryTable'), tbody = $('tryRows'), file = $('tryFile');
    var image = null, place = null, detector = null, busy = false, kind = 'objects';
    var camBtn = $('tryCam'), video = null, stream = null, live = false, L = null, rate = 0, lastDone = 0;
    var LEVEL = { ok: '#22c55e', alert: '#ef4444', notice: '#fbbf24', muted: '#cbd5e1' };
    /* The same thresholds as the desktop app and the pipeline (analyze.py, exam_analyze.py). */
    var RULE = { ABSENT_AFTER: 0.75, PHONE_ON: 0.35, PHONE_WINDOW: 0.8, PHONE_OFF: 1.5, SHRINK: 0.10, CALIB: 1.0, SMOOTH: 0.35, YAW_GATE: 38 };
    var LIMBS = [[5, 7], [7, 9], [6, 8], [8, 10], [5, 6], [5, 11], [6, 12], [11, 12], [11, 13], [13, 15], [12, 14], [14, 16], [0, 1], [0, 2], [1, 3], [2, 4]];
    var MODEL_TEXT = { objects: { run: 'Run the detector', idle: 'The model is 10 MB and loads when you press the button.', ready: 'Press the button to run the detector on this frame.' },
                       pose: { run: 'Run the pose model', idle: 'The pose model is 12 MB and loads when you press the button.', ready: 'Press the button to run the pose model on this frame.' } };
    var COLORS = { person: '#22c55e', car: '#fbbf24', truck: '#fbbf24', bus: '#fbbf24', dog: '#22c55e', cat: '#22c55e' };

    function draw(dets, progress, note) {
      var src = live ? video : image;
      ctx.fillStyle = '#101614'; ctx.fillRect(0, 0, canvas.width, canvas.height);
      if (!src) return;
      ctx.drawImage(src, place.x, place.y, place.w, place.h);
      if (!dets) return;
      var k = place.w / (live ? video.videoWidth : image.naturalWidth);
      ctx.font = '700 20px Archivo, Arial, sans-serif'; ctx.textBaseline = 'middle';
      dets.forEach(function (d, i) {
        var u = Math.max(0, Math.min(1, progress * dets.length * 0.6 - i * 0.45)); if (u <= 0) return;
        var main = !!note && d === note.person, phone = !!note && d === note.phone;
        var x = place.x + d.x1 * k, y = place.y + d.y1 * k, w = (d.x2 - d.x1) * k, h = (d.y2 - d.y1) * k;
        var col = main ? LEVEL[note.level] : phone ? LEVEL.notice : COLORS[d.name] || '#f8f9f6';
        var cx = x + w / 2, cy = y + h / 2, ww = w * (0.6 + 0.4 * u), hh = h * (0.6 + 0.4 * u);
        ctx.globalAlpha = u; ctx.lineWidth = main ? 5 : d.kp ? 2 : 4; ctx.strokeStyle = col; ctx.strokeRect(cx - ww / 2, cy - hh / 2, ww, hh);
        if (d.kp) {
          ctx.lineWidth = 3; ctx.strokeStyle = '#38bdf8'; ctx.lineCap = 'round';
          LIMBS.forEach(function (l, li) {
            var a = d.kp[l[0]], b = d.kp[l[1]]; if (a[2] < 0.35 || b[2] < 0.35 || u * LIMBS.length < li) return;
            ctx.beginPath(); ctx.moveTo(place.x + a[0] * k, place.y + a[1] * k); ctx.lineTo(place.x + b[0] * k, place.y + b[1] * k); ctx.stroke();
          });
          d.kp.forEach(function (p, pi) {
            if (p[2] < 0.35) return;
            ctx.beginPath(); ctx.arc(place.x + p[0] * k, place.y + p[1] * k, pi < 5 ? 3 : 4.5, 0, Math.PI * 2); ctx.fillStyle = pi < 5 ? '#ffffff' : '#38bdf8'; ctx.fill();
            ctx.lineWidth = 1.5; ctx.strokeStyle = '#0e2a21'; ctx.stroke();
          });
          ctx.strokeStyle = col;
        }
        var text = main ? note.text : phone ? 'PHONE' : d.name.toUpperCase() + ' ' + Math.round(d.score * 100) + '%', tw = ctx.measureText(text).width + 16;
        var ly = Math.max(place.y, cy - hh / 2 - 30), lx = Math.max(place.x, Math.min(place.x + place.w - tw, cx - ww / 2 - 2));
        ctx.fillStyle = col; ctx.fillRect(lx, ly, tw, 30);
        ctx.fillStyle = main && note.level === 'alert' ? '#ffffff' : '#0e2a21'; ctx.fillText(text, lx + 8, ly + 16); ctx.globalAlpha = 1;
      });
      if (note && !note.person) {                                  // nobody in view: say so in the corner of the picture
        var bw = ctx.measureText(note.text).width + 24;
        ctx.fillStyle = LEVEL[note.level]; ctx.fillRect(place.x + 16, place.y + 16, bw, 36);
        ctx.fillStyle = note.level === 'alert' ? '#ffffff' : '#0e2a21'; ctx.fillText(note.text, place.x + 28, place.y + 35);
      }
    }
    function setImage(img) {
      image = img; var s = Math.min(canvas.width / img.naturalWidth, canvas.height / img.naturalHeight);
      place = { w: img.naturalWidth * s, h: img.naturalHeight * s }; place.x = (canvas.width - place.w) / 2; place.y = (canvas.height - place.h) / 2;
      table.hidden = true; draw(null);
    }
    function loadImage(src, revoke) {
      var img = new Image(); img.onload = function () { setImage(img); if (revoke) URL.revokeObjectURL(src); };
      img.onerror = function () { say('That image could not be opened.', 'error'); }; img.src = src;
    }
    function say(text, state) { status.textContent = text; if (state) status.setAttribute('data-state', state); else status.removeAttribute('data-state'); }
    function showRows(dets) {
      tbody.textContent = '';
      dets.slice(0, 10).forEach(function (d) {
        var tr = el('tr'), conf = el('td', 'conf'), bar = el('i'); bar.style.width = Math.round(d.score * 100) + '%';
        conf.appendChild(el('span', null, d.score.toFixed(2))); conf.appendChild(bar);
        tr.appendChild(el('td', null, d.kp ? 'person, ' + d.kp.filter(function (p) { return p[2] >= 0.35; }).length + ' of 17 points' : d.name)); tr.appendChild(conf);
        tr.appendChild(el('td', null, Math.round(d.x1) + ', ' + Math.round(d.y1) + '  ' + Math.round(d.x2 - d.x1) + '×' + Math.round(d.y2 - d.y1)));
        tbody.appendChild(tr);
      });
      table.hidden = !dets.length;
    }
    function ensure(using) {                                      // the module and the chosen model, fetched on first use
      return (detector ? Promise.resolve(detector) : import('/detector.js').then(function (m) { detector = m; return m; }))
        .then(function (m) { if (m.loaded(using)) return; say('Loading the model… 0%'); return m.load(using, function (p) { say('Loading the model… ' + Math.round(p * 100) + '%'); }); });
    }
    function run() {
      if (busy || !image || live) return; busy = true; runBtn.disabled = true;
      var using = kind;
      ensure(using)
        .then(function () { say('Running…'); return detector.detect(using, image, image.naturalWidth, image.naturalHeight, 0.3); })
        .then(function (res) {
          var dets = res.dets, t0 = performance.now(), info = detector.info(using);
          var points = dets.reduce(function (n, d) { return n + (d.kp ? d.kp.filter(function (p) { return p[2] >= 0.35; }).length : 0); }, 0);
          var found = using === 'pose' ? 'Found ' + dets.length + (dets.length === 1 ? ' person' : ' people') + ' and ' + points + ' body keypoints' : 'Found ' + dets.length + (dets.length === 1 ? ' object' : ' objects');
          say(found + ' in ' + Math.round(res.ms) + ' ms on this device. ' + info.model + ', WebAssembly, ' + info.threads + (info.threads === 1 ? ' thread' : ' threads') + ', nothing uploaded.');
          showRows(dets);
          if (reduceMotion) draw(dets, 10); else (function anim(now) { var p = (now - t0) / 700; draw(dets, p); if (p < 2.2) requestAnimationFrame(anim); })(t0);
          runBtn.textContent = 'Run it again';
        })
        .catch(function (err) { say('The detector could not start in this browser (' + (err && err.message ? err.message : 'unknown error') + ').', 'error'); })
        .then(function () { busy = false; runBtn.disabled = false; });
    }
    /* ---- live camera: the same model on every frame, with the desk rule (objects) or head direction (pose) applied to the person in view */
    function wrap(d) { return ((d + 180) % 360 + 360) % 360 - 180; }
    function facing(kp) {                                        // nose relative to the midpoint of the ears, as in exam_analyze.py
      var n = kp[0]; if (n[2] < 0.35) return null;
      var le = kp[3], re = kp[4], mx = (le[0] + re[0]) / 2, my = (le[1] + re[1]) / 2;
      var size = Math.max(Math.hypot(le[0] - re[0], le[1] - re[1]), 2 * Math.hypot(kp[1][0] - kp[2][0], kp[1][1] - kp[2][1]), 8);
      return [(n[0] - mx) / size, (n[1] - my) / size];
    }
    function liveRules(using, dets, now) {
      var S = L, dt = S.last ? Math.min(0.5, now - S.last) : 0; S.last = now;
      var p = null; dets.forEach(function (d) { if (d.name === 'person' && !p) p = d; });        // detections arrive most confident first
      if (using === 'objects') {
        var phone = null;
        if (p) {
          var w = p.x2 - p.x1, h = p.y2 - p.y1, c = [p.x1 + w * RULE.SHRINK, p.y1 + h * RULE.SHRINK, p.x2 - w * RULE.SHRINK, p.y2 - h * RULE.SHRINK];
          dets.forEach(function (q) { var qx = (q.x1 + q.x2) / 2, qy = (q.y1 + q.y2) / 2; if (q.name === 'cell phone' && !phone && qx >= c[0] && qx <= c[2] && qy >= c[1] && qy <= c[3]) phone = q; });
          S.gone = 0;
        } else S.gone += dt;
        S.hist.push([now, !!phone, dt]); S.hist = S.hist.filter(function (x) { return now - x[0] <= RULE.PHONE_WINDOW; });
        if (phone) S.phoneLast = now;
        var evidence = S.hist.reduce(function (n, x) { return n + (x[1] ? x[2] : 0); }, 0), prev = S.status, status;
        if (S.gone >= RULE.ABSENT_AFTER) status = 'ABSENT';
        else if (!p) status = prev;
        else if (prev === 'PHONE USAGE') status = now - S.phoneLast < RULE.PHONE_OFF ? 'PHONE USAGE' : 'WORKING';
        else status = evidence >= RULE.PHONE_ON ? 'PHONE USAGE' : 'WORKING';
        S.status = status;
        return { person: p, phone: status === 'PHONE USAGE' ? phone : null, level: status === 'WORKING' ? 'ok' : 'alert', text: 'ID 1 · ' + status };
      }
      if (!p) return { person: null, level: 'muted', text: 'NO ONE IN VIEW' };
      var f = facing(p.kp); if (!f) { S.f = null; return { person: p, level: 'muted', text: 'S1 · HEAD NOT VISIBLE' }; }
      S.f = S.f ? [RULE.SMOOTH * f[0] + (1 - RULE.SMOOTH) * S.f[0], RULE.SMOOTH * f[1] + (1 - RULE.SMOOTH) * S.f[1]] : f;
      var dir = Math.atan2(S.f[1], S.f[0]) * 180 / Math.PI;
      if (S.base === null) {                                      // the first second sets this person's own baseline
        if (!S.t0) S.t0 = now; S.dirs.push(dir);
        if (now - S.t0 < RULE.CALIB) return { person: p, level: 'muted', text: 'S1 · MAPPING SEAT' };
        S.dirs.sort(function (a, b) { return a - b; }); S.base = S.dirs[S.dirs.length >> 1];
      }
      var yaw = Math.round(wrap(dir - S.base)), away = Math.abs(yaw) >= RULE.YAW_GATE;
      return { person: p, level: away ? 'notice' : 'ok', text: 'S1 · ' + (away ? 'LOOKING AWAY' : 'OWN PAPER') + ' · YAW ' + (yaw >= 0 ? '+' : '') + yaw + '°' };
    }
    function resetLive() { L = { last: 0, gone: 0, hist: [], phoneLast: -9, status: 'WORKING', f: null, base: null, dirs: [], t0: 0 }; rate = 0; lastDone = 0; }
    function tick() {
      if (!live) return;
      if (busy || video.readyState < 2 || !video.videoWidth) { requestAnimationFrame(tick); return; }
      busy = true; var using = kind;
      ensure(using).then(function () { return detector.detect(using, video, video.videoWidth, video.videoHeight, 0.3); })
        .then(function (res) {
          if (!live) return;
          if (using !== kind) { resetLive(); return; }            // the model was switched while this frame was running
          var now = performance.now() / 1000, note = liveRules(using, res.dets, now), info = detector.info(using);
          if (lastDone) { var inst = 1 / Math.max(0.001, now - lastDone); rate = rate ? 0.8 * rate + 0.2 * inst : inst; } lastDone = now;
          draw(res.dets, 10, note); showRows(res.dets);
          say(info.model + ', ' + Math.round(res.ms) + ' ms a frame' + (rate ? ', ' + rate.toFixed(rate < 10 ? 1 : 0) + ' frames a second' : '') + ' on this device. The picture is not uploaded or stored.');
        })
        .catch(function (err) { stopCam(); say('The model could not run on the camera in this browser (' + (err && err.message ? err.message : 'unknown error') + ').', 'error'); })
        .then(function () { busy = false; if (live) requestAnimationFrame(tick); });
    }
    function startCam() {
      if (live || busy) return;
      say('Waiting for the camera…');
      navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' }, audio: false }).then(function (st) {
        stream = st; video = document.createElement('video'); video.muted = true; video.playsInline = true; video.srcObject = st;
        return video.play();
      }).then(function () {
        var s = Math.min(canvas.width / video.videoWidth, canvas.height / video.videoHeight);
        place = { w: video.videoWidth * s, h: video.videoHeight * s }; place.x = (canvas.width - place.w) / 2; place.y = (canvas.height - place.h) / 2;
        live = true; resetLive(); camBtn.textContent = 'Stop the camera'; camBtn.setAttribute('aria-pressed', 'true'); runBtn.hidden = true;
        document.querySelectorAll('.sample').forEach(function (o) { o.setAttribute('aria-pressed', 'false'); });
        canvas.setAttribute('aria-label', 'Live picture from your camera with detections drawn on it.');
        requestAnimationFrame(tick);
      }).catch(function () {
        if (stream) stream.getTracks().forEach(function (t) { t.stop(); }); stream = null; video = null;
        say('The camera did not open. Allow it in the browser to try this, or use a sample frame.', 'error');
      });
    }
    function stopCam() {
      if (!live && !stream) return;
      live = false; if (stream) stream.getTracks().forEach(function (t) { t.stop(); }); stream = null; video = null;
      camBtn.textContent = 'Run it live on your camera'; camBtn.setAttribute('aria-pressed', 'false'); runBtn.hidden = false; table.hidden = true;
      canvas.setAttribute('aria-label', 'Sample camera frame. Detections are drawn on it after you run the detector.');
      if (image) setImage(image);
    }
    if (camBtn && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      camBtn.hidden = false;
      camBtn.addEventListener('click', function () { if (live) { stopCam(); say(MODEL_TEXT[kind].ready); } else startCam(); });
      document.addEventListener('visibilitychange', function () { if (document.hidden && live) { stopCam(); say('The camera was stopped because the page went out of view.'); } });
    }

    document.querySelectorAll('.sample').forEach(function (b) {
      b.addEventListener('click', function () {
        stopCam();
        document.querySelectorAll('.sample').forEach(function (o) { o.setAttribute('aria-pressed', String(o === b)); });
        loadImage(b.getAttribute('data-sample')); if (detector) say(MODEL_TEXT[kind].ready);
      });
    });
    file.addEventListener('change', function () {
      if (!file.files || !file.files[0]) return;
      stopCam();
      document.querySelectorAll('.sample').forEach(function (o) { o.setAttribute('aria-pressed', 'false'); });
      loadImage(URL.createObjectURL(file.files[0]), true); say('Your photo stays on this device. Press the button to run the model on it.');
    });
    document.querySelectorAll('.model-pick button').forEach(function (b) {
      b.addEventListener('click', function () {
        if ((busy && !live) || b.getAttribute('data-model') === kind) return; kind = b.getAttribute('data-model');
        document.querySelectorAll('.model-pick button').forEach(function (o) { o.setAttribute('aria-pressed', String(o === b)); });
        runBtn.textContent = MODEL_TEXT[kind].run;
        if (live) { resetLive(); return; }                          // the camera keeps running; the next frame uses the new model
        table.hidden = true; draw(null);
        say(detector && detector.loaded(kind) ? MODEL_TEXT[kind].ready : MODEL_TEXT[kind].idle);
      });
    });
    runBtn.addEventListener('click', run);
    var initial = document.querySelector('.sample[aria-pressed="true"]'); if (initial) loadImage(initial.getAttribute('data-sample'));
    window.__sentinelTry = { run: run, live: function () { return live; }, pick: function (k) { var b = document.querySelector('.model-pick [data-model="' + k + '"]'); if (b) b.click(); } };
  })();
})();
