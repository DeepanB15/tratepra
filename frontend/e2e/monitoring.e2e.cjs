// Browser walkthrough against backend/scripts/e2e_dev_server.py (isolated *_e2e DB, synthetic seed). Run: node monitoring.e2e.cjs
const { chromium } = require('playwright');
const WEB = process.env.WEB || 'http://127.0.0.1:5180', API = process.env.API || 'http://127.0.0.1:8010';
const TOKEN = process.env.INTERNAL_API_TOKEN || 'e2e-internal-token-0123456789';
const ok = (c, m) => { console.log((c ? 'PASS ' : 'FAIL ') + m); if (!c) process.exitCode = 1; };
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1200, height: 1100 } });
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => m.type() === 'error' && errs.push(m.text()));
  await p.goto(WEB + '/monitor');
  await p.getByText('You are not following any trends yet').waitFor(); ok(true, 'overview empty state before following');
  await p.goto(WEB + '/trends'); await p.waitForSelector('a[href^="/trends/"]');
  await p.locator('a[href^="/trends/"]').first().click();
  await p.getByRole('button', { name: 'Follow' }).click();
  await p.getByRole('button', { name: 'Following' }).waitFor();
  ok(true, 'follow button toggles to Following');
  await p.reload(); await p.getByRole('button', { name: 'Following' }).waitFor(); ok(true, 'follow state persists after reload');
  for (const job of ['detection', 'notifications']) {
    const r = await p.request.post(API + '/api/internal/monitoring/run', { headers: { 'X-Internal-Token': TOKEN }, data: { job } });
    ok(r.status() === 202, `internal ${job} trigger accepted (${r.status()})`);
    for (let i = 0; i < 60; i++) { // triggers run in the background: wait for the persisted job row to complete
      const st = await (await p.request.get(API + '/api/monitoring/status')).json();
      if (st.last_successful[job]) break; await p.waitForTimeout(500);
    }
  }
  const bad = await p.request.post(API + '/api/internal/monitoring/run', { data: { job: 'detection' } });
  ok(bad.status() === 401, 'internal trigger rejects missing token');
  await p.goto(WEB + '/monitor');
  await p.getByTestId('stat-Followed').waitFor();
  ok((await p.getByTestId('stat-Followed').innerText()) === '1', 'overview shows 1 followed');
  const badge = p.getByTestId('unread-badge'); await badge.waitFor();
  const n = Number(await badge.innerText()); ok(n > 0, `bell shows unread count (${n})`);
  await p.goto(WEB + '/monitor/watchlist'); await p.getByTestId('watch-row').first().waitFor();
  ok((await p.getByTestId('watch-row').count()) === 1, 'watchlist lists the followed trend');
  await p.goto(WEB + '/monitor/activity'); await p.getByTestId('event-card').first().waitFor();
  const ev = await p.getByTestId('event-card').count(); ok(ev > 0, `activity feed has ${ev} event(s)`);
  await p.getByRole('button', { name: 'Why was this flagged?' }).first().click();
  ok(/Detection cd-1/.test(await p.getByTestId('event-card').first().innerText()), 'explanation panel shows detection version');
  await p.screenshot({ path: 'mon_activity.png' });
  await p.goto(WEB + '/monitor/notifications'); await p.getByTestId('notification').first().waitFor();
  await p.getByRole('button', { name: 'Mark all read' }).click();
  await p.getByText("You're all caught up").waitFor();
  await p.getByTestId('unread-badge').waitFor({ state: 'detached' }); ok(true, 'mark all read clears the badge');
  await p.getByRole('button', { name: 'All', exact: true }).click(); await p.getByTestId('notification').first().waitFor();
  ok(true, 'read notifications stay in history');
  await p.goto(WEB + '/monitor/watchlist'); 
  await p.locator('a[href^="/monitor/trends/"]').first().click();
  await p.getByText('Observation history').waitFor();
  ok((await p.locator('tbody tr').count()) >= 2, 'trend monitoring detail shows >= 2 observations');
  await p.screenshot({ path: 'mon_detail.png', fullPage: true });
  await p.goto(WEB + '/monitor/settings'); await p.getByTestId('scheduler-state').waitFor();
  ok(/disabled|MONITORING_SCHEDULER_ENABLED/.test(await p.getByTestId('scheduler-state').innerText()), 'settings shows scheduler disabled state');
  await p.getByLabel(/Minimum severity/).selectOption('important'); await p.getByRole('button', { name: 'Save preferences' }).click();
  await p.getByText('Saved.').waitFor(); await p.reload();
  ok((await p.getByLabel(/Minimum severity/).inputValue()) === 'important', 'preferences persist');
  await p.setViewportSize({ width: 390, height: 800 }); await p.goto(WEB + '/monitor');
  ok(await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'no horizontal scroll at 390px');
  await p.goto(WEB + '/monitor/watchlist'); await p.getByRole('button', { name: 'Unfollow' }).click();
  await p.getByText('Nothing on your watchlist').waitFor(); ok(true, 'unfollow empties watchlist');
  const evs = await (await p.request.get(API + '/api/monitoring/events')).json();
  ok(evs.length === ev, 'events preserved after unfollow');
  ok(errs.length === 0, 'no console/page errors ' + JSON.stringify(errs.slice(0, 3)));
  await b.close();
})().catch(e => { console.error('FAIL', e.message); process.exit(1); });
