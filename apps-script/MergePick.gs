/**
 * Merge Pick backend for merge.html, run as a Google Apps Script web app.
 *
 * Choosing a pick only emails the player a confirmation link; the pick is saved
 * when they open that link. Picks lock at LOCK_AT, after which status shows everyone's
 * pick. Player emails live in Config.gs (kept out of git).
 *
 * Deploy: Deploy > New deployment > Web app, Execute as "Me", access "Anyone".
 */
const SITE = 'https://geveffe.github.io/survivor-51-fantasy/';
const RAW = 'https://raw.githubusercontent.com/Geveffe/survivor-51-fantasy/main/';
const LOCK_AT = new Date('2026-11-04T21:40:00-05:00');  // 9:40 PM Toronto time

const locked = () => new Date() >= LOCK_AT;
function checkOpen() {
  if (locked()) throw new Error('Merge picks are locked, so picks can no longer be made or confirmed.');
}

function doGet(e) {
  let out;
  try {
    out = handle(e.parameter);
  } catch (err) {
    out = { ok: false, error: err.message };
  }
  return ContentService.createTextOutput(JSON.stringify(out)).setMimeType(ContentService.MimeType.JSON);
}

function handle(p) {
  switch (p.action) {
    case 'status': return status();
    case 'choose': return choose(p.player, p.castaway);
    case 'email': return emailCurrent(p.player);
    case 'commit': return commit(p.player, p.token);
  }
  throw new Error('Unknown action.');
}

const props = () => PropertiesService.getScriptProperties();
const read = key => JSON.parse(props().getProperty(key) || 'null');
const write = (key, value) => props().setProperty(key, JSON.stringify(value));

// Players' tribes from picks.json and who's still in the game from the site's data.json,
// cached for a few minutes so each click doesn't refetch them.
function league() {
  const cache = CacheService.getScriptCache();
  const hit = cache.get('league');
  if (hit) return JSON.parse(hit);
  const get = path => JSON.parse(UrlFetchApp.fetch(RAW + path).getContentText());
  const picks = get('picks.json'), data = get('docs/data.json');
  const last = String(Math.max(...Object.keys(data.episodes).map(Number)));
  const gone = (data.departures[last] || []).map(d => d.name);
  const out = {
    players: picks.players.map(pl => ({ name: pl.name, tribe: pl.picks.concat(pl.mvp) })),
    remaining: Object.keys(data.episodes[last]).filter(c => !gone.includes(c)),
  };
  cache.put('league', JSON.stringify(out), 300);
  return out;
}

function findPlayer(name) {
  const pl = league().players.find(pl => pl.name === name);
  if (!pl) throw new Error(`There's no player called ${name}.`);
  if (!EMAILS[pl.name]) throw new Error(`There's no email on file for ${pl.name}.`);
  return pl;
}

const eligible = pl => league().remaining.filter(c => !pl.tribe.includes(c));

// Once locked, everyone's confirmed pick is public; before that, only whether they have one.
function status() {
  const lg = league();
  if (locked()) {
    return {
      ok: true, locked: true, lockAt: LOCK_AT.toISOString(),
      players: lg.players.map(pl => ({ name: pl.name, pick: (read('pick:' + pl.name) || {}).castaway || null })),
    };
  }
  return {
    ok: true, locked: false, lockAt: LOCK_AT.toISOString(),
    players: lg.players.map(pl => ({ name: pl.name, eligible: eligible(pl),
      hasPick: !!read('pick:' + pl.name), hasPending: !!read('pending:' + pl.name) })),
  };
}

// Anyone can press the buttons for any player, so cap how often a player gets emailed.
function throttle(pl) {
  const cache = CacheService.getScriptCache(), key = 'sent:' + pl.name;
  if (cache.get(key)) throw new Error(`An email just went to ${pl.name}. Give it a minute before sending another.`);
  cache.put(key, '1', 60);
}

// Pass throttled = false for emails only a confirmation link can trigger.
function send(pl, subject, html, throttled = true) {
  if (throttled) throttle(pl);
  MailApp.sendEmail({
    to: EMAILS[pl.name],
    name: 'Survivor 51 Fantasy',
    subject,
    htmlBody: `<div style="font:15px/1.5 Arial,sans-serif">${html}</div>`,
  });
}

function choose(player, castaway) {
  checkOpen();
  const pl = findPlayer(player);
  if (!eligible(pl).includes(castaway)) throw new Error(`${castaway} isn't available as ${pl.name}'s merge pick.`);
  const token = Utilities.getUuid();
  const link = `${SITE}merge.html?player=${encodeURIComponent(pl.name)}&confirm=${token}`;
  send(pl, `Confirm ${castaway} as your merge pick`,
    `<p>Hi ${pl.name},</p>
     <p>Someone (hopefully you) chose <b>${castaway}</b> as your Survivor 51 merge pick.</p>
     <p><a href="${link}" style="display:inline-block;background:#e9b949;color:#1c1a15;font-weight:bold;padding:10px 18px;border-radius:999px;text-decoration:none">Confirm ${castaway}</a></p>
     <p>Nothing changes until you click that button. If you didn't make this choice, just ignore this email.</p>`);
  // Only the newest link works, so an older email can't overwrite a later choice.
  write('pending:' + pl.name, { token, castaway });
  return { ok: true };
}

function emailCurrent(player) {
  const pl = findPlayer(player);
  const pick = read('pick:' + pl.name), pending = read('pending:' + pl.name);
  let html = pick
    ? `<p>Your Survivor 51 merge pick is <b>${pick.castaway}</b>.</p>`
    : `<p>You haven't confirmed a Survivor 51 merge pick yet.</p>`;
  if (pending && !locked()) html += `<p>You also chose <b>${pending.castaway}</b> but haven't confirmed it. Click the link in that email to make it your pick.</p>`;
  html += locked()
    ? `<p>Merge picks are now locked. <a href="${SITE}merge.html">See everyone's merge pick</a></p>`
    : `<p><a href="${SITE}merge.html">Choose or change your merge pick</a></p>`;
  send(pl, 'Your merge pick', `<p>Hi ${pl.name},</p>${html}`);
  return { ok: true };
}

function commit(player, token) {
  const pl = findPlayer(player);
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  let castaway;
  try {
    const pick = read('pick:' + pl.name), pending = read('pending:' + pl.name);
    if (pick && pick.token === token) return { ok: true, player: pl.name, castaway: pick.castaway, already: true };
    checkOpen();
    if (!pending || pending.token !== token) {
      throw new Error('This link has expired. It may have been replaced by a newer choice; check for a more recent email.');
    }
    if (!eligible(pl).includes(pending.castaway)) throw new Error(`${pending.castaway} is no longer available as a merge pick.`);
    castaway = pending.castaway;
    write('pick:' + pl.name, { castaway: pending.castaway, token, at: new Date().toISOString() });
    props().deleteProperty('pending:' + pl.name);
  } finally {
    lock.releaseLock();
  }
  // Email the confirmed pick right away so the player knows it worked and the owner's Sent
  // folder keeps a record. A mail failure doesn't undo the saved pick.
  let emailed = true;
  try {
    send(pl, `Confirmed: ${castaway} is your merge pick`,
      `<p>Hi ${pl.name},</p>
       <p>Your Survivor 51 merge pick is confirmed as <b>${castaway}</b>.</p>
       <p>Confirmed ${new Date().toUTCString()}.</p>
       <p><a href="${SITE}merge.html">View or change your merge pick</a></p>`, false);
  } catch (err) {
    emailed = false;
  }
  return { ok: true, player: pl.name, castaway, emailed };
}
