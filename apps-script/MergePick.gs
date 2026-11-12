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
const LOCK_AT = new Date('2026-11-11T20:00:00-05:00');  // 8:00 PM Toronto time, Wed Nov 11
// Castaways known to be out before the site's points data catches up.
const ALSO_OUT = ['Brady'];  // voted out in episode 7

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
// cached for a few minutes so each click doesn't refetch them, and kept for the rest of the request.
let leagueMemo = null;
function league() {
  if (leagueMemo) return leagueMemo;
  const cache = CacheService.getScriptCache();
  const hit = cache.get('league');
  if (hit) return (leagueMemo = JSON.parse(hit));
  const get = path => JSON.parse(UrlFetchApp.fetch(RAW + path).getContentText());
  const picks = get('picks.json'), data = get('docs/data.json');
  const last = String(Math.max(...Object.keys(data.episodes).map(Number)));
  const gone = (data.departures[last] || []).map(d => d.name).concat(ALSO_OUT);
  const out = {
    players: picks.players.map(pl => ({ name: pl.name, tribe: pl.picks.concat(pl.mvp) })),
    remaining: Object.keys(data.episodes[last]).filter(c => !gone.includes(c)),
  };
  cache.put('league', JSON.stringify(out), 300);
  return (leagueMemo = out);
}

function findPlayer(name) {
  const pl = league().players.find(pl => pl.name === name);
  if (!pl) throw new Error(`There's no player called ${name}.`);
  if (!EMAILS[pl.name]) throw new Error(`There's no email on file for ${pl.name}.`);
  return pl;
}

const eligible = pl => league().remaining.filter(c => !pl.tribe.includes(c));

// Once locked, everyone's confirmed pick is public; before that, only whether they have one.
// All properties are read in one call; reading them one at a time made this slow.
function status() {
  const lg = league(), all = props().getProperties();
  const read = key => JSON.parse(all[key] || 'null');
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
function send(pl, subject, html, throttled = true, extra = {}) {
  if (throttled) throttle(pl);
  MailApp.sendEmail(Object.assign({
    to: EMAILS[pl.name],
    name: 'Survivor 51 Fantasy',
    subject,
    htmlBody: `<div style="font:15px/1.5 Arial,sans-serif">${html}</div>`,
  }, extra));
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
  return { ok: true, player: pl.name, castaway, emailed: emailConfirmed(pl, castaway) };
}

// Email the confirmed pick right away so the player knows it worked and the owner's Sent
// folder keeps a record. A mail failure doesn't undo the saved pick.
function emailConfirmed(pl, castaway) {
  try {
    send(pl, `Confirmed: ${castaway} is your merge pick`,
      `<p>Hi ${pl.name},</p>
       <p>Your Survivor 51 merge pick is confirmed as <b>${castaway}</b>.</p>
       <p>Confirmed ${new Date().toUTCString()}.</p>
       <p><a href="${SITE}merge.html">View or change your merge pick</a></p>`, false);
    return true;
  } catch (err) {
    return false;
  }
}

// Set a player's pick by hand, as if they'd clicked Confirm in their email, and send them the
// usual confirmation email. Not reachable from the web app: change the defaults below, then pick
// adminSetPick in the editor's function menu and press Run.
function adminSetPick(player = 'ChelseaB', castaway = 'Sharonda') {
  const pl = findPlayer(player);
  if (!eligible(pl).includes(castaway)) throw new Error(`${castaway} isn't available as ${pl.name}'s merge pick.`);
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    write('pick:' + pl.name, { castaway, token: 'admin:' + Utilities.getUuid(), at: new Date().toISOString() });
    props().deleteProperty('pending:' + pl.name);
  } finally {
    lock.releaseLock();
  }
  const emailed = emailConfirmed(pl, castaway);
  console.log(`${pl.name}'s merge pick is now ${castaway}; confirmation email ${emailed ? 'sent' : 'FAILED'}.`);
}

// Urgent reminders to everyone without a confirmed pick at 6:00, 7:00, 7:30 and 7:55 PM Toronto,
// cc'ing REMINDER_CC. Run setupReminders once from the editor to schedule them; run
// previewReminders any time to log who would be emailed without sending anything.
const REMINDER_CC = 'dankorey4@gmail.com';
const REMINDER_TIMES = ['2026-11-11T18:00:00-05:00', '2026-11-11T19:00:00-05:00', '2026-11-11T19:30:00-05:00',
  '2026-11-11T19:55:00-05:00'];

// Safe to run again after adding a time: it only schedules times it hasn't already scheduled,
// so reminders that are still waiting to fire are left alone.
function setupReminders() {
  let done = read('remindersScheduled');
  // The first version of setupReminders scheduled 6:00, 7:00 and 7:30 without recording them.
  if (!done) done = ScriptApp.getProjectTriggers().some(t => t.getHandlerFunction() === 'sendReminders')
    ? REMINDER_TIMES.slice(0, 3) : [];
  REMINDER_TIMES.filter(t => !done.includes(t) && new Date(t) > new Date()).forEach(t => {
    ScriptApp.newTrigger('sendReminders').timeBased().at(new Date(t)).create();
    done.push(t);
    console.log('Reminder scheduled for ' + new Date(t).toString());
  });
  write('remindersScheduled', done);
  console.log(`${ScriptApp.getProjectTriggers().filter(t => t.getHandlerFunction() === 'sendReminders').length} reminder triggers in place.`);
  previewReminders();
}

const unpicked = () => {
  const all = props().getProperties();
  return league().players.filter(pl => !all['pick:' + pl.name] && EMAILS[pl.name])
    .map(pl => Object.assign({}, pl, { pending: JSON.parse(all['pending:' + pl.name] || 'null') }));
};

// Time until the lock, to the nearest 5 minutes, e.g. "2 hours", "1 hour", "30 minutes".
function timeLeft() {
  const mins = Math.max(5, Math.round((LOCK_AT - new Date()) / 300000) * 5);
  const h = Math.floor(mins / 60), m = mins % 60;
  const part = (n, unit) => n ? `${n} ${unit}${n === 1 ? '' : 's'}` : '';
  return [part(h, 'hour'), part(m, 'minute')].filter(Boolean).join(' ');
}

function previewReminders() {
  const list = unpicked();
  console.log(`Need to confirm: ${list.filter(pl => pl.pending).map(pl => pl.name).join(', ') || 'nobody'}`);
  console.log(`No pick at all: ${list.filter(pl => !pl.pending).map(pl => pl.name).join(', ') || 'nobody'}`);
  console.log(`Each round needs ${list.length * 2} of today's remaining ${MailApp.getRemainingDailyQuota()} email recipients.`);
  console.log('Time left right now: ' + timeLeft());
}

function sendReminders() {
  if (locked()) return;
  const list = unpicked(), left = timeLeft();
  if (!list.length) return console.log('Everyone has a confirmed pick; no reminders sent.');
  const wrap = html => `<div style="font:15px/1.5 Arial,sans-serif">${html}</div>`;
  const urgent = text => `<p style="color:#b00020;font-weight:bold">${text}</p>`;
  const button = label => `<p><a href="${SITE}merge.html" style="display:inline-block;background:#e9b949;color:#1c1a15;font-weight:bold;padding:10px 18px;border-radius:999px;text-decoration:none">${label}</a></p>`;
  const lockNote = `merge picks are locked at 8:00 PM Toronto time`;

  // Chose a castaway but never clicked Confirm. With a pending pick, the email carries that
  // pick's own confirm link; without one (the bcc'd group email) it points back to their earlier email.
  const confirmMail = (name, pending) => ({
    subject: `URGENT: Only ${left} left to confirm your Survivor 51 merge pick`,
    html: pending
      ? `<p>Hi ${name},</p>
        ${urgent(`This is urgent: there's only ${left} left until ${lockNote}, and your merge pick isn't confirmed yet.`)}
        <p>You chose <b>${pending.castaway}</b>, but it won't count until you confirm it. Click below to confirm <b>${pending.castaway}</b> as your merge pick:</p>
        <p><a href="${SITE}merge.html?player=${encodeURIComponent(name)}&confirm=${pending.token}" style="display:inline-block;background:#e9b949;color:#1c1a15;font-weight:bold;padding:10px 18px;border-radius:999px;text-decoration:none">Confirm ${pending.castaway}</a></p>
        <p>Want someone else instead? <a href="${SITE}merge.html">Choose a different merge pick</a></p>`
      : `<p>Hi ${name},</p>
        ${urgent(`This is urgent: there's only ${left} left until ${lockNote}, and your merge pick isn't confirmed yet.`)}
        <p>You chose a castaway, but it won't count until you click the <b>Confirm</b> button in the email we sent you about it (check spam too).</p>
        <p>Can't find it? Choose again here and we'll send a new confirmation email:</p>
        ${button('Choose and confirm my pick')}`,
  });
  // Hasn't chosen anything.
  const chooseMail = name => ({
    subject: `URGENT: Only ${left} left to make your Survivor 51 merge pick`,
    html: `<p>Hi ${name},</p>
      ${urgent(`This is urgent: there's only ${left} left until ${lockNote}, and we don't have a merge pick for you yet.`)}
      ${button('Make your merge pick now')}
      <p>After you choose, we'll email you a confirmation link. Your pick isn't saved until you click <b>Confirm</b> in that email.</p>`,
  });

  // One email per player costs two recipients each against MailApp's daily quota (player + cc).
  // If that won't fit, fall back to one email per group, bcc'd to its players.
  if (MailApp.getRemainingDailyQuota() >= list.length * 2) {
    list.forEach(pl => {
      const mail = pl.pending ? confirmMail(pl.name, pl.pending) : chooseMail(pl.name);
      try {
        send(pl, mail.subject, mail.html, false, { cc: REMINDER_CC });
      } catch (err) {
        console.error(`Reminder to ${pl.name} failed: ${err.message}`);
      }
    });
  } else {
    [[list.filter(pl => pl.pending), confirmMail('everyone')], [list.filter(pl => !pl.pending), chooseMail('everyone')]]
      .filter(([group]) => group.length)
      .forEach(([group, mail]) => MailApp.sendEmail({
        to: REMINDER_CC, bcc: group.map(pl => EMAILS[pl.name]).join(','),
        name: 'Survivor 51 Fantasy', subject: mail.subject, htmlBody: wrap(mail.html),
      }));
    console.log('Low on email quota, so sent group emails bcc\'d instead of one per player.');
  }
  console.log(`Sent ${left} reminders. Need to confirm: ${list.filter(pl => pl.pending).map(pl => pl.name).join(', ') || 'nobody'}. ` +
    `No pick: ${list.filter(pl => !pl.pending).map(pl => pl.name).join(', ') || 'nobody'}.`);
}
