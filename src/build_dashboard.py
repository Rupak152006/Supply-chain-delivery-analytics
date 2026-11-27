"""Build a standalone, offline HTML dashboard from the CSV marts.

Output: dashboard/delhivery_dashboard.html. Open it by double-clicking; it needs
no server, no internet and no libraries (data and drawing code are embedded).
Also writes dashboard/delhivery_marts.xlsx for Power BI, Tableau or Excel.
"""
import json
import pandas as pd
from config import MARTS, ROOT

OUT = ROOT / "dashboard"
TABLES = ["overall", "daily", "route_type", "distance_band", "hour", "state", "corridor", "hub",
          "risk_drivers", "model_metrics"]

TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Delhivery Delivery Performance</title>
<style>
:root{--bg:#f6f7f9;--panel:#fff;--fg:#1d2433;--muted:#5d6676;--line:#e3e6eb;--accent:#2f6fde;--accent2:#e08a2c;--grey:#b9bfc9;--ok:#2e8b57;--warn:#c98a12;--bad:#c8463d}
@media (prefers-color-scheme:dark){:root{--bg:#14171c;--panel:#1c2027;--fg:#e8ebf0;--muted:#9aa3b2;--line:#2c323c;--accent:#6c9cf0;--accent2:#f0a75a;--grey:#4a525e;--ok:#5cc08a;--warn:#e0b04a;--bad:#ec7a70}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:24px 16px 48px;display:grid;gap:24px}
h1{font-size:28px;margin:0}h2{font-size:18px;margin:0}h3{font-size:14px;margin:0}
.eyebrow{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:0}
.muted{color:var(--muted);font-size:12px;margin:0}.lede{max-width:75ch;margin:0}
.tiles{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(160px,1fr))}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px;display:grid;gap:8px;min-width:0}
.big{font-size:26px;font-variant-numeric:tabular-nums}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr))}
svg text{fill:var(--muted);font-size:11px}svg .val{fill:var(--fg)}
table{width:100%;border-collapse:collapse;font-size:12px;font-variant-numeric:tabular-nums}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}th{color:var(--muted);font-weight:600}
th:first-child,td:first-child,.l{text-align:left}.scroll{overflow:auto;max-height:420px}
.pill{padding:1px 8px;border-radius:999px;font-weight:600}.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}
.legend{display:flex;gap:14px;font-size:12px;color:var(--muted)}.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px}
</style></head><body><div class="wrap">
<header style="display:grid;gap:8px"><p class="eyebrow">India · Delhivery public trip data</p><h1>Delhivery Delivery Performance</h1>
<p class="lede" id="lede"></p><p class="muted" id="source"></p></header>
<section class="tiles" id="tiles"></section>
<section class="card"><h2>Share of legs within SLA by day</h2><div id="daily"></div></section>
<section class="grid"><div class="card"><h2>Full truckload vs carting</h2><div id="route"></div></div>
<div class="card"><h2>Within SLA by planned distance</h2><div class="legend"><span><i class="sw" style="background:var(--accent)"></i>FTL</span><span><i class="sw" style="background:var(--accent2)"></i>Carting</span></div><div id="bands"></div></div></section>
<section class="card"><h2>Within SLA by hour the leg starts</h2><p class="muted">Dashed line: all legs.</p><div id="hours"></div></section>
<section class="grid"><div class="card"><h2>Within SLA by origin state</h2><p class="muted">States with 100+ legs. Dashed line: all legs.</p><div id="states"></div></div>
<div class="card"><h2>Busiest state-to-state corridors</h2><div class="scroll" id="corridors"></div></div></section>
<section class="card"><h2>Origin facilities (100+ legs), least reliable first</h2><div class="scroll" id="hubs"></div></section>
<section class="card"><h2>What raises the odds of missing the SLA</h2><p class="muted" id="modelnote"></p><div id="drivers"></div></section>
<p class="muted">Built by src/build_dashboard.py from data/marts. SLA = actual transit time within SLA_FACTOR × the OSRM routing estimate.</p>
</div>
<script>
const D = __DATA__;
const $ = id => document.getElementById(id);
const pct = (v, d=1) => (v*100).toFixed(d) + '%';
const num = v => Math.round(v).toLocaleString('en-IN');
const tone = v => v >= 0.6 ? 'ok' : v >= 0.45 ? 'warn' : 'bad';
const NS = 'http://www.w3.org/2000/svg';
function el(tag, attrs, parent, text){ const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (text != null) e.textContent = text; if (parent) parent.appendChild(e); return e; }
function svg(host, h){ host.innerHTML=''; const w = Math.max(320, host.clientWidth); const s = el('svg', {viewBox:`0 0 ${w} ${h}`, width:'100%', height:h, role:'img'}, host); return [s, w]; }
function tip(e, text){ el('title', {}, e, text); }
const O = D.overall[0], F = +O.sla_factor;
const st = D.state.slice().sort((a,b)=>a.sla_rate-b.sla_rate), worst = st[0], best = st[st.length-1];
const rt = t => D.route_type.find(r => r.route_type === t);
$('lede').textContent = `Only ${pct(O.sla_rate)} of ${num(O.legs)} legs finished within ${F}× their planned drive time; the typical leg took ${(+O.median_delay_ratio).toFixed(2)}× the routing estimate. Carting legs meet the target ${pct(rt('Carting').sla_rate)} of the time against ${pct(rt('FTL').sla_rate)} for full truckloads. By origin state the rate ranges from ${pct(worst.sla_rate,0)} in ${worst.state} to ${pct(best.sla_rate,0)} in ${best.state}.`;
$('source').textContent = `Data: Delhivery public trip dataset, ${O.first_date} to ${O.last_date}. No promised dates exist, so "within SLA" means actual transit time ≤ ${F}× the OSRM estimate.`;
[['Legs within SLA', pct(O.sla_rate)], ['Median actual vs plan', (+O.median_delay_ratio).toFixed(2)+'×'], ['Legs', num(O.legs)], ['Trips', num(O.trips)],
 ['Avg time at facilities', Math.round(O.avg_handling_min)+' min'], ['Full-truckload share', pct(O.ftl_share,0)]].forEach(([k,v]) => {
  const c = document.createElement('div'); c.className='card'; c.innerHTML = `<p class="muted"></p><div class="big"></div>`; c.children[0].textContent=k; c.children[1].textContent=v; $('tiles').appendChild(c); });

function drawAll(){
  // Daily line
  { const rows = D.daily, [s,w] = svg($('daily'), 240), L=44, R=24, T=12, B=28, y = v => T + (0.7 - v)/0.4*(240-T-B), x = i => L + i*(w-L-R)/(rows.length-1);
    [0.3,0.4,0.5,0.6,0.7].forEach(v => { el('line',{x1:L,x2:w-R,y1:y(v),y2:y(v),stroke:'var(--line)'},s); el('text',{x:L-6,y:y(v)+4,'text-anchor':'end'},s,pct(v,0)); });
    el('line',{x1:L,x2:w-R,y1:y(O.sla_rate),y2:y(O.sla_rate),stroke:'var(--muted)','stroke-dasharray':'4 4'},s);
    el('path',{d:rows.map((r,i)=>(i?'L':'M')+x(i)+' '+y(r.sla_rate)).join(''),fill:'none',stroke:'var(--accent)','stroke-width':2},s);
    rows.forEach((r,i)=>{ tip(el('circle',{cx:x(i),cy:y(r.sla_rate),r:3.5,fill:'var(--accent)'},s), `${r.date}: ${pct(r.sla_rate)} within SLA, ${num(r.legs)} legs`); if(i%3===0) el('text',{x:x(i),y:240-8,'text-anchor':'middle'},s,r.date.slice(5)); }); }
  // Route table
  $('route').innerHTML = '<table><tr><th>Route</th><th>Legs</th><th>Within SLA</th><th>Median actual min</th><th>Median plan min</th><th>Avg km</th></tr>' +
    D.route_type.map(r=>`<tr><td>${r.route_type}</td><td>${num(r.legs)}</td><td><span class="pill ${tone(r.sla_rate)}">${pct(r.sla_rate)}</span></td><td>${num(r.median_actual_time_min)}</td><td>${num(r.median_osrm_time_min)}</td><td>${num(r.avg_distance_km)}</td></tr>`).join('') + '</table>';
  // Distance bands grouped bars
  { const rows = D.distance_band.filter(r=>r.legs>=30), bands=[...new Set(rows.map(r=>r.distance_band))], [s,w]=svg($('bands'),240), L=40,B=28,T=10, ih=240-T-B, gw=(w-L)/bands.length;
    [0,0.2,0.4,0.6].forEach(v=>{ const yy=T+ih*(1-v/0.8); el('line',{x1:L,x2:w,y1:yy,y2:yy,stroke:'var(--line)'},s); el('text',{x:L-6,y:yy+4,'text-anchor':'end'},s,pct(v,0)); });
    bands.forEach((b,i)=>{ el('text',{x:L+gw*i+gw/2,y:240-8,'text-anchor':'middle'},s,b);
      ['FTL','Carting'].forEach((t,j)=>{ const r=rows.find(q=>q.distance_band===b&&q.route_type===t); if(!r) return; const h=ih*r.sla_rate/0.8, bw=gw*0.32;
        tip(el('rect',{x:L+gw*i+gw*0.16+j*bw,y:T+ih-h,width:bw-2,height:h,fill:j?'var(--accent2)':'var(--accent)'},s), `${b} ${t}: ${pct(r.sla_rate)} within SLA, ${num(r.legs)} legs`); }); }); }
  // Hours
  { const rows=D.hour, [s,w]=svg($('hours'),220), L=40,B=26,T=10, ih=220-T-B, bw=(w-L)/24, yy=v=>T+ih*(1-v/0.8);
    [0,0.2,0.4,0.6].forEach(v=>{ el('line',{x1:L,x2:w,y1:yy(v),y2:yy(v),stroke:'var(--line)'},s); el('text',{x:L-6,y:yy(v)+4,'text-anchor':'end'},s,pct(v,0)); });
    rows.forEach((r,i)=>{ tip(el('rect',{x:L+i*bw+2,y:yy(r.sla_rate),width:bw-4,height:ih-(yy(r.sla_rate)-T),fill:r.sla_rate<O.sla_rate?'var(--grey)':'var(--accent)'},s), `Starts ${r.hour}:00: ${pct(r.sla_rate)}, ${num(r.legs)} legs`); if(r.hour%3===0) el('text',{x:L+i*bw+bw/2,y:220-6,'text-anchor':'middle'},s,String(r.hour).padStart(2,'0')+':00'); });
    el('line',{x1:L,x2:w,y1:yy(O.sla_rate),y2:yy(O.sla_rate),stroke:'var(--muted)','stroke-dasharray':'4 4'},s); }
  // States
  { const rows=D.state.slice().sort((a,b)=>b.sla_rate-a.sla_rate), rh=22, H=rows.length*rh+10, [s,w]=svg($('states'),H), L=130, R=70, x=v=>L+(w-L-R)*v/0.8;
    rows.forEach((r,i)=>{ const yy=i*rh+4; el('text',{x:L-8,y:yy+12,'text-anchor':'end',class:'val'},s,r.state);
      tip(el('rect',{x:L,y:yy+2,width:x(r.sla_rate)-L,height:13,fill:`var(--${tone(r.sla_rate)})`,opacity:.8},s), `${r.state}: ${pct(r.sla_rate)}, ${num(r.legs)} legs`);
      el('text',{x:x(r.sla_rate)+5,y:yy+13,class:'val'},s,pct(r.sla_rate,0)); el('text',{x:w-4,y:yy+13,'text-anchor':'end'},s,num(r.legs)); });
    el('line',{x1:x(O.sla_rate),x2:x(O.sla_rate),y1:0,y2:H,stroke:'var(--muted)','stroke-dasharray':'4 4'},s); }
}
$('corridors').innerHTML = '<table><tr><th>From</th><th class="l">To</th><th>Legs</th><th>Within SLA</th><th>Avg km</th><th>Avg extra min</th></tr>' +
  D.corridor.slice().sort((a,b)=>b.legs-a.legs).map(r=>`<tr><td>${r.source_state}</td><td class="l">${r.destination_state}</td><td>${num(r.legs)}</td><td><span class="pill ${tone(r.sla_rate)}">${pct(r.sla_rate)}</span></td><td>${num(r.avg_distance_km)}</td><td>${num(r.avg_excess_min)}</td></tr>`).join('') + '</table>';
$('hubs').innerHTML = '<table><tr><th>Facility</th><th class="l">Type</th><th>Legs</th><th>Within SLA</th><th>Avg extra min</th><th>Avg at facilities min</th></tr>' +
  D.hub.slice().sort((a,b)=>a.sla_rate-b.sla_rate).map(r=>`<tr><td>${r.facility}</td><td class="l">${r.facility_type}</td><td>${num(r.legs)}</td><td><span class="pill ${tone(r.sla_rate)}">${pct(r.sla_rate)}</span></td><td>${num(r.avg_excess_min)}</td><td>${num(r.avg_handling_min)}</td></tr>`).join('') + '</table>';
const M = Object.fromEntries(D.model_metrics.map(r=>[r.metric, r.value]));
$('modelnote').textContent = `Logistic regression, trained on ${M.train_period}, tested on ${M.test_period}: ROC AUC ${(+M.roc_auc).toFixed(2)}. Riskiest 10% of test legs breached ${pct(+M.top_decile_breach_rate,0)} of the time vs ${pct(+M.test_breach_rate,0)} overall. Baseline: ${M.baseline}.`;
$('drivers').innerHTML = '<table><tr><th>Factor</th><th>Odds vs baseline</th></tr>' + D.risk_drivers.map(r=>`<tr><td>${r.feature}</td><td class="${r.odds_ratio>=1?'bad':'ok'}">${(+r.odds_ratio).toFixed(2)}×</td></tr>`).join('') + '</table>';
drawAll(); addEventListener('resize', drawAll);
</script></body></html>
"""


def main():
    data = {t: pd.read_csv(MARTS / f"{t}.csv").to_dict(orient="records") for t in TABLES}
    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    OUT.mkdir(exist_ok=True)
    (OUT / "delhivery_dashboard.html").write_text(html, encoding="utf-8")
    with pd.ExcelWriter(OUT / "delhivery_marts.xlsx") as xl:
        for t in TABLES:
            pd.DataFrame(data[t]).to_excel(xl, sheet_name=t[:31], index=False)
    print(f"wrote {OUT / 'delhivery_dashboard.html'} and {OUT / 'delhivery_marts.xlsx'}")


if __name__ == "__main__":
    main()
