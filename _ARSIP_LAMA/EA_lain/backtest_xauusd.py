import collections
import csv
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest_data")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest_results")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

PARAMS = {
    "swing": 10,
    "atr_len": 50,
    "box_width": 2.5,
    "entry_pct": 50.0,
    "rr": 2.0,
    "keep": 20,
    "overlap_mult": 2.0,
}

START_EPOCH = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())


def http_get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read().decode("utf-8")


def fetch_yahoo(symbol, interval, rng, fname):
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, fname)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + urllib.parse.quote(symbol)
        + "?interval="
        + interval
        + "&range="
        + rng
    )
    data = json.loads(http_get(url))
    with open(path, "w") as f:
        json.dump(data, f)
    return data


def parse_chart(j):
    res = j["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    out = []
    seen = set()
    for i, t in enumerate(ts):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if o is None or h is None or l is None or c is None:
            continue
        ti = int(t)
        if ti in seen:
            continue
        seen.add(ti)
        out.append((ti, float(o), float(h), float(l), float(c)))
    out.sort(key=lambda b: b[0])
    return out


def aggregate_hours(bars, hours):
    step = 3600 * hours
    groups = collections.OrderedDict()
    for t, o, h, l, c in bars:
        g = t - (t % step)
        if g not in groups:
            groups[g] = [o, h, l, c]
        else:
            gr = groups[g]
            gr[1] = max(gr[1], h)
            gr[2] = min(gr[2], l)
            gr[3] = c
    return [(g, v[0], v[1], v[2], v[3]) for g, v in groups.items()]


def aggregate_days(bars):
    groups = collections.OrderedDict()
    for t, o, h, l, c in bars:
        d = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")
        if d not in groups:
            groups[d] = [t, o, h, l, c]
        else:
            gr = groups[d]
            gr[1] = min(gr[1], t)
            gr[2] = max(gr[2], h)
            gr[3] = min(gr[3], l)
            gr[4] = c
    return [(g[0], g[1], g[2], g[3], g[4]) for g in groups.values()]


def atr_series(bars, length):
    trs = []
    prev_c = None
    for _, o, h, l, c in bars:
        tr = h - l if prev_c is None else max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
        prev_c = c
    atr = [None] * len(bars)
    s = None
    for i, tr in enumerate(trs):
        if i == length - 1:
            s = sum(trs[:length]) / length
            atr[i] = s
        elif i >= length:
            s = s + (tr - s) / length
            atr[i] = s
    return atr


def is_pivot(vals, center, span, is_high):
    v = vals[center]
    for k in range(1, span + 1):
        lv = vals[center - k]
        rv = vals[center + k]
        if is_high:
            if lv >= v or rv >= v:
                return False
        else:
            if lv <= v or rv <= v:
                return False
    return True


def fmt_t(t):
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def run_backtest(name, bars, params):
    swing = params["swing"]
    atr_len = params["atr_len"]
    buf_mult = params["box_width"] / 10.0
    ep_frac = params["entry_pct"] / 100.0
    rr = params["rr"]
    keep = params["keep"]
    ov_mult = params["overlap_mult"]
    sl_pad = params.get("mintick_sl", 0.15)

    highs = [b[2] for b in bars]
    lows = [b[3] for b in bars]
    atr = atr_series(bars, atr_len)

    supply_active = []
    demand_active = []
    supply_age = collections.deque()
    demand_age = collections.deque()
    trades = []

    def register(trade_list, z):
        pass

    n = len(bars)
    for i in range(n):
        t, o, h, l, c = bars[i]
        a = atr[i]

        if a is not None and i >= 2 * swing:
            ci = i - swing
            if is_pivot(highs, ci, swing, True):
                sh = highs[ci]
                buf = a * buf_mult
                top = sh
                bot = top - buf
                poi = bot + (top - bot) * ep_frac
                sl = top + sl_pad
                tp = poi - (sl - poi) * rr
                okay = True
                for zz in supply_active:
                    if abs(poi - zz["poi"]) <= a * ov_mult:
                        okay = False
                        break
                if okay:
                    z = {
                        "side": "SELL",
                        "top": top,
                        "bot": bot,
                        "poi": poi,
                        "sl": sl,
                        "tp": tp,
                        "filled": False,
                        "dead": False,
                        "fill_t": None,
                        "fill_px": None,
                    }
                    supply_active.append(z)
                    supply_age.append(z)
                    if len(supply_age) > keep:
                        old = supply_age.popleft()
                        if old in supply_active:
                            supply_active.remove(old)
            elif is_pivot(lows, ci, swing, False):
                slv = lows[ci]
                buf = a * buf_mult
                bot = slv
                top = bot + buf
                poi = bot + (top - bot) * ep_frac
                sl = bot - sl_pad
                tp = poi + (poi - sl) * rr
                okay = True
                for zz in demand_active:
                    if abs(poi - zz["poi"]) <= a * ov_mult:
                        okay = False
                        break
                if okay:
                    z = {
                        "side": "BUY",
                        "top": top,
                        "bot": bot,
                        "poi": poi,
                        "sl": sl,
                        "tp": tp,
                        "filled": False,
                        "dead": False,
                        "fill_t": None,
                        "fill_px": None,
                    }
                    demand_active.append(z)
                    demand_age.append(z)
                    if len(demand_age) > keep:
                        old = demand_age.popleft()
                        if old in demand_active:
                            demand_active.remove(old)

        for lst in (supply_active, demand_active):
            for z in lst:
                if z["dead"]:
                    continue
                if not z["filled"]:
                    bos = c >= z["top"] if z["side"] == "SELL" else c <= z["bot"]
                    if bos:
                        z["dead"] = True
                        continue
                    fp = None
                    if z["side"] == "SELL":
                        if o >= z["poi"]:
                            fp = o
                        elif h >= z["poi"]:
                            fp = z["poi"]
                    else:
                        if o <= z["poi"]:
                            fp = o
                        elif l <= z["poi"]:
                            fp = z["poi"]
                    if fp is not None:
                        z["filled"] = True
                        z["fill_t"] = t
                        z["fill_px"] = fp
                else:
                    ft = z["fill_t"]
                    fx = z["fill_px"]
                    res = None
                    exit_px = None
                    if z["side"] == "SELL":
                        if o >= z["sl"]:
                            res, exit_px = "L", o
                        elif o <= z["tp"]:
                            res, exit_px = "W", o
                        elif h >= z["sl"]:
                            res, exit_px = "L", z["sl"]
                        elif l <= z["tp"]:
                            res, exit_px = "W", z["tp"]
                    else:
                        if o <= z["sl"]:
                            res, exit_px = "L", o
                        elif o >= z["tp"]:
                            res, exit_px = "W", o
                        elif l <= z["sl"]:
                            res, exit_px = "L", z["sl"]
                        elif h >= z["tp"]:
                            res, exit_px = "W", z["tp"]
                    if res is not None:
                        z["dead"] = True
                        trades.append(
                            {
                                "tf": name,
                                "side": z["side"],
                                "fill_t": ft,
                                "fill_px": fx,
                                "exit_t": t,
                                "exit_px": exit_px,
                                "result": res,
                                "r": rr if res == "W" else -1.0,
                            }
                        )

        supply_active = [z for z in supply_active if not z["dead"]]
        demand_active = [z for z in demand_active if not z["dead"]]

    return trades


def summarize(trades, tf):
    rows = {}
    for side in ("BUY", "SELL"):
        sub = [x for x in trades if x["side"] == side and x["fill_t"] >= START_EPOCH]
        w = sum(1 for x in sub if x["result"] == "W")
        lo = len(sub) - w
        wr = (w / len(sub) * 100) if sub else 0.0
        net = sum(x["r"] for x in sub)
        gp = sum(x["r"] for x in sub if x["r"] > 0)
        gl = -sum(x["r"] for x in sub if x["r"] < 0)
        pf = (gp / gl) if gl > 0 else float("inf")
        rows[side] = (len(sub), w, lo, wr, net, pf)
    allsub = [x for x in trades if x["fill_t"] >= START_EPOCH]
    eq = 0.0
    peak = 0.0
    mdd = 0.0
    for x in sorted(allsub, key=lambda y: y["exit_t"]):
        eq += x["r"]
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    return rows, mdd, allsub


def export_csv(trades, tf):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "trades_" + tf.replace("/", "") + ".csv")
    with open(path, "w", newline="") as f:
        wtr = csv.writer(f)
        wtr.writerow(["tf", "side", "fill_time_utc", "fill_px", "exit_time_utc", "exit_px", "result", "R"])
        for x in trades:
            if x["fill_t"] >= START_EPOCH:
                wtr.writerow(
                    [
                        x["tf"],
                        x["side"],
                        fmt_t(x["fill_t"]),
                        round(x["fill_px"], 2),
                        fmt_t(x["exit_t"]),
                        round(x["exit_px"], 2),
                        x["result"],
                        x["r"],
                    ]
                )
    return path


def main():
    raw = parse_chart(fetch_yahoo("GC=F", "1h", "730d", "gc_h1.json"))
    print("H1 bars:", len(raw), "|", fmt_t(raw[0][0]), "->", fmt_t(raw[-1][0]))
    datasets = {
        "H1": raw,
        "H4": aggregate_hours(raw, 4),
        "D1": aggregate_days(raw),
    }
    print()
    hdr = f"{'TF':<4} {'Side':<5} {'Trades':>6} {'Win':>5} {'Loss':>5} {'WR%':>7} {'NetR':>8} {'PF':>6}"
    print(hdr)
    print("-" * len(hdr))
    for tf, bars in datasets.items():
        trades = run_backtest(tf, bars, PARAMS)
        rows, mdd, allsub = summarize(trades, tf)
        tot_n = rows["BUY"][0] + rows["SELL"][0]
        tot_w = rows["BUY"][1] + rows["SELL"][1]
        tot_net = rows["BUY"][4] + rows["SELL"][4]
        print(
            f"{tf:<4} {'BUY':<5} {rows['BUY'][0]:>6} {rows['BUY'][1]:>5} {rows['BUY'][2]:>5} {rows['BUY'][3]:>6.2f}% {rows['BUY'][4]:>8.1f} {rows['BUY'][5]:>6.2f}"
        )
        print(
            f"{tf:<4} {'SELL':<5} {rows['SELL'][0]:>6} {rows['SELL'][1]:>5} {rows['SELL'][2]:>5} {rows['SELL'][3]:>6.2f}% {rows['SELL'][4]:>8.1f} {rows['SELL'][5]:>6.2f}"
        )
        twr = (tot_w / tot_n * 100) if tot_n else 0.0
        print(f"{tf:<4} {'ALL':<5} {tot_n:>6} {tot_w:>5} {tot_n-tot_w:>5} {twr:>6.2f}% {tot_net:>8.1f}   MaxDD: {mdd:.1f}R")
        print("-" * len(hdr))
        p = export_csv(trades, tf)
        print("saved:", p)
        print()

    h1_trades = run_backtest("H1", datasets["H1"], PARAMS)
    by_year = collections.defaultdict(lambda: [0, 0, 0.0])
    for x in h1_trades:
        if x["fill_t"] < START_EPOCH:
            continue
        yr = datetime.fromtimestamp(x["fill_t"], tz=timezone.utc).year
        by_year[yr][0] += 1
        if x["result"] == "W":
            by_year[yr][1] += 1
        by_year[yr][2] += x["r"]
    print("H1 per-year:")
    for yr in sorted(by_year):
        nn, ww, net = by_year[yr]
        print(f"  {yr}: trades={nn}, wins={ww}, WR={(ww/nn*100 if nn else 0):.2f}%, NetR={net:.1f}")


if __name__ == "__main__":
    main()
