import numpy as np
import requests
from scipy.stats import poisson
import time

FOOTBALL_DATA_API_KEY = "1467319bc72f4a649dcc6417edb2d007"
TELEGRAM_BOT_TOKEN = "8824271401:AAEC1VPBbk9M0x36Hy98F-tNks2EkZkVUSo"
TELEGRAM_CHAT_ID = "6319073305"

LIGAS = {
    "NED": "Eredivisie (Holanda)",
    "AUT": "Bundesliga Austria",
    "NOR": "Eliteserien Noruega",
    "ESP2": "LaLiga2",
    "ENG1": "Premier League",
    "ESP1": "LaLiga"
}
PARTIDOS_RECIENTES = 6
MEDIA_LIGA = 2.75
enviados_ya = set()

def obtener_partidos(liga_codigo):
    url = f"https://api.football-data.org/v4/competitions/{liga_codigo}/matches"
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        return r.json().get("matches", [])
    except:
        return []

def obtener_ultimos_partidos(equipo_id, limite=PARTIDOS_RECIENTES):
    url = f"https://api.football-data.org/v4/teams/{equipo_id}/matches?status=FINISHED&limit={limite}"
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
    try:
        return requests.get(url, headers=headers, timeout=15).json().get("matches", [])
    except:
        return []

def calcular_estadisticas(partidos, equipo_nombre):
    if not partidos: return None
    gf, gc = [], []
    btts = over25 = 0
    for p in partidos:
        g_loc = p['score']['fullTime']['home'] or 0
        g_vis = p['score']['fullTime']['away'] or 0
        if p['homeTeam']['name'] == equipo_nombre:
            gf.append(g_loc); gc.append(g_vis)
        else:
            gf.append(g_vis); gc.append(g_loc)
        if g_loc > 0 and g_vis > 0: btts += 1
        if g_loc + g_vis >= 3: over25 += 1
    return {
        "gf_prom": np.mean(gf), "gc_prom": np.mean(gc),
        "pct_btts": btts / len(partidos), "pct_over25": over25 / len(partidos),
        "mu_goles": np.mean(gf) + np.mean(gc)
    }

def calcular_probabilidad(est_local, est_vis):
    lmb_loc = max(0.1, est_local['gf_prom'] * est_vis['gc_prom'] / MEDIA_LIGA)
    lmb_vis = max(0.1, est_vis['gf_prom'] * est_local['gc_prom'] / MEDIA_LIGA)
    prob = 0
    for gl in range(1, 8):
        for gv in range(1, 8):
            if gl + gv >= 3:
                prob += poisson.pmf(gl, lmb_loc) * poisson.pmf(gv, lmb_vis)
    return round(prob*100, 1), round(lmb_loc + lmb_vis, 2)

def escanear(ligas_seleccionadas, umbral_prob):
    resultados = []
    for lid, lnom in LIGAS.items():
        if lnom not in ligas_seleccionadas: continue
        partidos = obtener_partidos(lid)
        for p in partidos:
            if p['status'] != 'SCHEDULED': continue
            loc, vis = p['homeTeam'], p['awayTeam']
            est_loc = calcular_estadisticas(obtener_ultimos_partidos(loc['id']), loc['name'])
            est_vis = calcular_estadisticas(obtener_ultimos_partidos(vis['id']), vis['name'])
            if not est_loc or not est_vis: continue
            prob, goles_esp = calcular_probabilidad(est_loc, est_vis)
            if (est_loc['pct_btts'] >= 0.5 and est_vis['pct_btts'] >= 0.5 and
                est_loc['mu_goles'] + est_vis['mu_goles'] >= 2.7 and prob >= umbral_prob):
                resultados.append({
                    "fecha": p['utcDate'][:10], "liga": lnom,
                    "partido": f"{loc['name']} vs {vis['name']}",
                    "prob_%": prob, "goles_esp": goles_esp,
                    "btts_loc": round(est_loc['pct_btts']*100),
                    "btts_vis": round(est_vis['pct_btts']*100),
                    "over_loc": round(est_loc['pct_over25']*100),
                    "over_vis": round(est_vis['pct_over25']*100)
                })
            time.sleep(0.8)
    return sorted(resultados, key=lambda x: x['prob_%'], reverse=True)

def enviar_a_telegram(partidos):
    if not partidos: return False
    mensaje = "🚀 *SELECCIONES: AMBOS MARCAN + +2.5 GOLES*\n\n"
    for p in partidos:
        mensaje += (
            f"📅 {p['fecha']} | {p['liga']}\n⚽ {p['partido']}\n"
            f"✅ Prob: {p['prob_%']}%\n🎯 Goles esp: {p['goles_esp']}\n"
            f"📊 BTTS: L{p['btts_loc']}% / V{p['btts_vis']}% | Over2.5: L{p['over_loc']}% / V{p['over_vis']}%\n"
            "----------------\n"
        )
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        return requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "Markdown"}, timeout=15).ok
    except:
        return False

def filtrar_nuevos(partidos):
    nuevos = []
    for p in partidos:
        clave = f"{p['fecha']}-{p['partido']}"
        if clave not in enviados_ya:
            enviados_ya.add(clave)
            nuevos.append(p)
    return nuevos
  
