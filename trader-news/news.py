#!/usr/bin/env python3
"""
trader-news/news.py
XAUUSD Economic Calendar Blackout Filter, Live TradingView Headline Fetcher,
& Indonesian Gold News Sentiment Analyzer (.github/skills/xauusd-news-analysis/SKILL.md).
Writes trader/news.json.
"""

from __future__ import annotations
import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


BULLISH_GOLD_KEYWORDS = {
    "rate cut": 25,
    "dovish": 20,
    "safe haven": 25,
    "geopolitical": 20,
    "central bank buying": 25,
    "yields fall": 15,
    "dollar weakens": 15,
    "recession": 15,
    "stimulus": 15,
    "gold rebounds": 15,
}

BEARISH_GOLD_KEYWORDS = {
    "rate hike": -25,
    "hawkish": -20,
    "hot cpi": -25,
    "cpi tops": -25,
    "tops forecasts": -20,
    "strong nfp": -20,
    "yields surge": -20,
    "yields, dollar rise": -25,
    "lifting dollar and yields": -25,
    "dollar surges": -15,
    "usd advances": -20,
    "gold falls": -20,
    "gold slumps": -20,
    "ceasefire": -10,
    "higher for longer": -20,
}

SAFE_HAVEN_OVERRIDE_PATTERNS = [
    r"\beskalasi geopolitik\b",
    r"\bancaman perang\b",
    r"\bperang\b",
    r"\bserangan militer\b",
    r"\brudal\b",
    r"\binvasi\b",
    r"\bkrisis perbankan\b",
    r"\bbank gagal\b",
    r"\bresesi global\b",
    r"\bgeopolitical escalation\b",
    r"\bgeopolitical tension\b",
    r"\bwar threat\b",
    r"\bmilitary strike\b",
    r"\bmissile\b",
    r"\binvasion\b",
    r"\bbanking crisis\b",
    r"\bsystemic crisis\b",
    r"\bbank collapse\b",
    r"\bglobal recession\b",
    r"\bsafe[- ]haven demand\b",
]

BEARISH_MACRO_PATTERNS = [
    r"\bdata as (?:yang )?lebih kuat\b",
    r"\bmelampaui ekspektasi\b",
    r"\bdi atas ekspektasi\b",
    r"\binflasi (?:as )?(?:meningkat|naik|memanas|melonjak)\b",
    r"\bcpi (?:as )?(?:meningkat|naik|memanas|melonjak|lebih tinggi)\b",
    r"\btenaga kerja (?:as )?menguat\b",
    r"\bnfp (?:kuat|melonjak|naik)\b",
    r"\bhawkish\b",
    r"\bsuku bunga (?:as |fed )?naik\b",
    r"\bkenaikan suku bunga\b",
    r"\byield (?:as |treasury |obligasi )?naik\b",
    r"\bdxy menguat\b",
    r"\bstronger[- ]than[- ]expected\b",
    r"\btops forecasts\b",
    r"\bbeats expectations\b",
    r"\bhot cpi\b",
    r"\byields?,? dollar rise\b",
    r"\bdollar,? yields? rise\b",
    r"\bcpi data\b",
    r"\binflation (?:rises|accelerates|surges|hotter)\b",
    r"\bstrong (?:nfp|jobs|labor|payrolls)\b",
    r"\bjob growth surges\b",
    r"\bunemployment falls\b",
    r"\brate hike\b",
    r"\bhigher for longer\b",
    r"\byields? (?:rise|surge|jump|climb)\b",
    r"\bdollar (?:rises|surges|climbs|advances)\b",
    r"\blifting dollar and yields\b",
    r"\busd advances\b",
]

BULLISH_MACRO_PATTERNS = [
    r"\bdata as (?:yang )?(?:melemah|lemah|melambat|di bawah ekspektasi)\b",
    r"\binflasi (?:as )?(?:melandai|turun|melemah)\b",
    r"\bcpi (?:as )?(?:melandai|turun|lebih rendah)\b",
    r"\btenaga kerja (?:as )?(?:melemah|melambat)\b",
    r"\bpengangguran (?:as )?naik\b",
    r"\bdovish\b",
    r"\b(?:pangkas|pemangkasan|penurunan) suku bunga\b",
    r"\bsuku bunga (?:as |fed )?turun\b",
    r"\byield (?:as |treasury |obligasi )?turun\b",
    r"\bdxy melemah\b",
    r"\bweaker[- ]than[- ]expected\b",
    r"\bmisses (?:expectations|forecasts)\b",
    r"\b(?:cooling|softer|lower) (?:inflation|cpi)\b",
    r"\bweak (?:nfp|jobs|labor|payrolls|data)\b",
    r"\bunemployment rises\b",
    r"\brate cut\b",
    r"\bfed cut\b",
    r"\byields? (?:fall|drop|decline|retreat)\b",
    r"\bdollar (?:weakens|falls|drops)\b",
]

RELEVANT_TOPIC_PATTERNS = [
    r"\bxau\b", r"\bgold\b", r"\bemas\b", r"\busd\b", r"\bdollar\b", r"\bdxy\b",
    r"\bfed\b", r"\bfomc\b", r"\bpowell\b", r"\bcpi\b", r"\bpce\b", r"\bppi\b",
    r"\bnfp\b", r"\bpayroll\b", r"\binflasi\b", r"\binflation\b", r"\bsuku bunga\b",
    r"\brate\b", r"\byield\b", r"\btreasury\b", r"\bgeopolit\b", r"\bperang\b",
    r"\bwar\b", r"\bresesi\b", r"\brecession\b", r"\bbank\b", r"\bcentral bank\b",
]

import time
_TV_HEADLINES_CACHE: List[str] = []
_TV_HEADLINES_TS: float = 0.0
_TV_HEADLINES_TTL_SEC: float = 30.0


def fetch_tradingview_headlines(symbol: str = "OANDA:XAUUSD", limit: int = 5, timeout: int = 6) -> List[str]:
    """Fetches real-time XAUUSD headlines from TradingView's public news API (with 30s cache)."""
    global _TV_HEADLINES_CACHE, _TV_HEADLINES_TS
    now_mono = time.monotonic()
    if _TV_HEADLINES_CACHE and (now_mono - _TV_HEADLINES_TS) < _TV_HEADLINES_TTL_SEC:
        return _TV_HEADLINES_CACHE[:limit]

    enc_sym = urllib.parse.quote(symbol)
    url = f"https://news-headlines.tradingview.com/v2/view/headlines/symbol?client=web&lang=en&symbol={enc_sym}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Connection": "keep-alive",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        titles: List[str] = []
        for item in data.get("items", []):
            t = str(item.get("title", "")).strip()
            if t:
                titles.append(t)
            if len(titles) >= max(limit, 5):
                break
        if titles:
            _TV_HEADLINES_CACHE = titles
            _TV_HEADLINES_TS = now_mono
        return titles[:limit]
    except Exception:
        return _TV_HEADLINES_CACHE[:limit]


def _strip_html(raw_html: str) -> str:
    no_script = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw_html, flags=re.DOTALL | re.IGNORECASE)
    no_tags = re.sub(r"<[^>]+>", " ", no_script)
    un_escaped = html.unescape(no_tags)
    return re.sub(r"\s+", " ", un_escaped).strip()


def fetch_public_news_text(url: str, timeout: int = 8) -> Optional[str]:
    """
    Fetches news text from a public Telegram link (t.me/...) or public webpage.
    For Telegram channel feeds with multiple posts, selects the latest relevant post.
    Strictly never reads or accesses telegram.json or any project credentials.
    """
    clean_url = url.strip()
    if clean_url.startswith("t.me/"):
        clean_url = "https://" + clean_url

    parsed = urllib.parse.urlparse(clean_url)
    if parsed.netloc.lower() in ("t.me", "www.t.me", "telegram.me"):
        path_parts = [p for p in parsed.path.split("/") if p]
        # Convert https://t.me/<channel>/<id> or https://t.me/<channel> to /s/ public preview
        if path_parts and path_parts[0] != "s":
            clean_url = f"https://t.me/s/{'/'.join(path_parts)}"

    req = urllib.request.Request(
        clean_url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_html = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None

    # Extract Telegram widget message blocks if present
    msg_blocks = re.findall(
        r'<div[^>]*class="[^"]*tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
        raw_html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if msg_blocks:
        cleaned_posts = [_strip_html(b) for b in msg_blocks if _strip_html(b)]
        if not cleaned_posts:
            return None
        # Prioritize the latest relevant post (iterate from newest at end to oldest)
        for post in reversed(cleaned_posts):
            low = post.lower()
            if any(re.search(pat, low) for pat in RELEVANT_TOPIC_PATTERNS):
                return post
        return cleaned_posts[-1]

    # Fallback: check meta description / title for general web articles
    og_desc = re.search(
        r'<meta[^>]+(?:property="og:description"|name="description")[^>]+content="([^"]+)"',
        raw_html,
        flags=re.IGNORECASE,
    )
    title_m = re.search(r"<title[^>]*>(.*?)</title>", raw_html, flags=re.DOTALL | re.IGNORECASE)
    parts: List[str] = []
    if title_m:
        parts.append(_strip_html(title_m.group(1)))
    if og_desc:
        parts.append(html.unescape(og_desc.group(1)).strip())
    if parts:
        combined = " — ".join(p for p in parts if p)
        if len(combined) > 15:
            return combined

    body_txt = _strip_html(raw_html)
    return body_txt[:600] if len(body_txt) > 30 else None


def _summarize_news_one_sentence(text: str, sentiment: str, category: str) -> str:
    """Produces a concise 1-sentence Indonesian summary of the input news without inventing facts."""
    cleaned = re.sub(r"\s+", " ", text).strip()
    # Protect abbreviations like U.S. from sentence splitting
    protected = cleaned.replace("U.S.", "US")
    first_sentence = re.split(r"(?<=[.!?])\s+", protected)[0].strip()
    if len(first_sentence) > 160:
        first_sentence = first_sentence[:157].rstrip() + "..."
    if not first_sentence.endswith((".", "!", "?")):
        first_sentence += "."

    low = cleaned.lower()
    # Provide natural Indonesian summary if headline is in English
    if category == "SAFE_HAVEN":
        if any(w in low for w in ("war", "missile", "attack", "geopolitical", "invasion", "strike")):
            return f"Berita melaporkan peningkatan ketegangan geopolitik dan risiko konflik militer ({first_sentence[:-1]})."
        if any(w in low for w in ("bank", "crisis", "recession")):
            return f"Berita menyoroti kekhawatiran stabilitas perbankan atau ancaman resesi global ({first_sentence[:-1]})."
    elif category == "BEARISH_MACRO":
        if "cpi" in low or "inflation" in low:
            return f"Laporan menunjukkan data inflasi AS (CPI) yang lebih kuat dari ekspektasi dan mendorong kenaikan ekspektasi suku bunga ({first_sentence[:-1]})."
        if "nfp" in low or "jobs" in low or "payroll" in low:
            return f"Data ketenagakerjaan AS dilaporkan menguat di atas ekspektasi pasar ({first_sentence[:-1]})."
        if "hawkish" in low or "rate hike" in low:
            return f"Berita mengindikasikan sikap hawkish The Fed serta meningkatnya ekspektasi kenaikan suku bunga AS ({first_sentence[:-1]})."
    elif category == "BULLISH_MACRO":
        if "cpi" in low or "inflation" in low:
            return f"Laporan menunjukkan melandainya tekanan inflasi AS sehingga memperkuat ekspektasi pelonggaran kebijakan moneter ({first_sentence[:-1]})."
        if "dovish" in low or "rate cut" in low:
            return f"Berita menyoroti sinyal dovish The Fed dan meningkatnya peluang pemangkasan suku bunga AS ({first_sentence[:-1]})."
    return first_sentence


def analyze_xauusd_news_indonesia(text_or_url: str) -> Dict[str, Any]:
    """
    Implements `.github/skills/xauusd-news-analysis/SKILL.md`:
    Assesses economic/geopolitical news or public Telegram links as BULLISH, BEARISH, or NETRAL
    for XAU/USD and returns the exact 3-part Indonesian output format.
    Strictly never reads or displays credentials from telegram.json.
    """
    raw_input = (text_or_url or "").strip()
    if not raw_input:
        msg = " Berita tidak ditemukan. Silakan tempelkan teks berita ekonomi atau geopolitik yang ingin dianalisis."
        return {
            "skill": "xauusd-news-analysis",
            "accessible": False,
            "sentimen": "NETRAL",
            "formatted_output": msg.strip(),
        }

    is_url = bool(re.match(r"^(https?://|t\.me/)", raw_input, flags=re.IGNORECASE)) and " " not in raw_input
    news_text = raw_input
    if is_url:
        fetched = fetch_public_news_text(raw_input)
        if not fetched:
            prompt_msg = (
                "Tautan berita tersebut tidak dapat diakses secara publik. "
                "Silakan tempelkan isi teks beritanya secara langsung untuk dianalisis."
            )
            return {
                "skill": "xauusd-news-analysis",
                "accessible": False,
                "source_url": raw_input,
                "sentimen": "NETRAL",
                "formatted_output": prompt_msg,
            }
        news_text = fetched

    low = news_text.lower()
    has_safe_haven = any(re.search(pat, low) for pat in SAFE_HAVEN_OVERRIDE_PATTERNS)
    bearish_hits = sum(1 for pat in BEARISH_MACRO_PATTERNS if re.search(pat, low))
    bullish_hits = sum(1 for pat in BULLISH_MACRO_PATTERNS if re.search(pat, low))
    is_relevant = any(re.search(pat, low) for pat in RELEVANT_TOPIC_PATTERNS)

    # Rule 3c: Safe-haven demand (geopolitical escalation, war, banking crisis, global recession)
    # overrides opposing economic or interest rate signals -> BULLISH
    if has_safe_haven:
        sentimen = "BULLISH"
        category = "SAFE_HAVEN"
        if bearish_hits > 0:
            logika = (
                "Meskipun terdapat sinyal tekanan suku bunga atau data ekonomi yang ketat, eskalasi risiko geopolitik/krisis "
                "memicu arus permintaan safe haven yang lebih dominan sehingga berpotensi mengangkat harga XAU/USD."
            )
        else:
            logika = (
                "Meningkatnya risiko geopolitik atau ketidakpastian sistemik berpotensi mendorong investor beralih ke aset safe haven, "
                "sehingga meningkatkan permintaan terhadap emas spot (XAU/USD)."
            )
    elif bearish_hits > bullish_hits and bearish_hits > 0:
        sentimen = "BEARISH"
        category = "BEARISH_MACRO"
        mentions_dxy_yield_move = any(
            k in low for k in ("yields, dollar rise", "lifting dollar and yields", "usd advances", "dxy menguat", "yield naik")
        )
        if mentions_dxy_yield_move:
            logika = (
                "Data AS yang lebih kuat atau tekanan inflasi yang tinggi mendorong penguatan DXY dan kenaikan yield Treasury AS "
                "sebagaimana disebutkan dalam laporan, sehingga meningkatkan opportunity cost memegang emas dan berpotensi menekan XAU/USD."
            )
        else:
            logika = (
                "Data ekonomi AS yang kuat, inflasi yang meningkat, atau sikap Fed yang hawkish berpotensi menguatkan indeks dolar (DXY) "
                "serta meningkatkan ekspektasi yield/suku bunga AS, yang menaikkan opportunity cost memegang emas (XAU/USD)."
            )
    elif bullish_hits > 0:
        sentimen = "BULLISH"
        category = "BULLISH_MACRO"
        logika = (
            "Pelemahan data ekonomi AS, sikap Fed yang dovish, atau turunnya ekspektasi suku bunga/yield AS berpotensi menekan DXY "
            "dan mengurangi opportunity cost memegang emas tanpa imbal hasil, sehingga mendukung kenaikan XAU/USD."
        )
    else:
        sentimen = "NETRAL"
        category = "IRRELEVANT" if not is_relevant else "NEUTRAL_MACRO"
        logika = (
            "Isi berita tidak memiliki katalis langsung terhadap kebijakan moneter The Fed, ekspektasi yield AS, DXY, "
            "maupun permintaan safe haven, sehingga dampaknya terhadap XAU/USD cenderung netral."
        )

    ringkasan = _summarize_news_one_sentence(news_text, sentimen, category)
    formatted = (
        f"**Ringkasan Berita:** {ringkasan}\n\n"
        f"**Sentimen XAU/USD:** {sentimen}\n\n"
        f"**Logika dan Dampak:** {logika}"
    )

    return {
        "skill": "xauusd-news-analysis",
        "accessible": True,
        "input": raw_input,
        "analyzed_text": news_text,
        "ringkasan_berita": ringkasan,
        "sentimen": sentimen,
        "logika_dan_dampak": logika,
        "formatted_output": formatted,
    }


def parse_iso_utc(ts_str: str) -> dt.datetime:
    cleaned = ts_str.replace("Z", "+00:00")
    parsed = dt.datetime.fromisoformat(cleaned)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def default_news_payload() -> Dict[str, Any]:
    return {
        "events": [
            {
                "title": "US CPI m/m & Core CPI",
                "currency": "USD",
                "impact": "HIGH",
                "time": "2026-11-11T18:30:00+00:00",
                "forecast": "0.2%",
                "previous": "0.2%",
            },
            {
                "title": "FOMC Member Speech",
                "currency": "USD",
                "impact": "MEDIUM",
                "time": "2026-11-11T20:00:00+00:00",
            },
        ],
        "headlines": [
            "Gold holds firm as central bank buying continues and Treasury yields fall",
            "Traders eye upcoming US macro data as dollar weakens modestly",
        ],
    }


def score_headlines(headlines: List[str]) -> Dict[str, Any]:
    total_score = 0
    matched_drivers: List[str] = []
    for hl in headlines:
        lower = hl.lower()
        for kw, weight in BULLISH_GOLD_KEYWORDS.items():
            if kw in lower:
                total_score += weight
                matched_drivers.append(f"+{weight} ({kw})")
        for kw, weight in BEARISH_GOLD_KEYWORDS.items():
            if kw in lower:
                total_score += weight
                matched_drivers.append(f"{weight} ({kw})")

    total_score = max(-100, min(100, total_score))
    if total_score >= 20:
        bias = "BULLISH_GOLD"
    elif total_score <= -20:
        bias = "BEARISH_GOLD"
    else:
        bias = "NEUTRAL"

    return {
        "sentiment_score": total_score,
        "sentiment_bias": bias,
        "matched_drivers": matched_drivers,
    }


def evaluate_news(
    payload: Dict[str, Any],
    now_utc: Optional[dt.datetime] = None,
    pre_blackout_min: int = 30,
    post_blackout_min: int = 30,
    caution_min: int = 90,
    symbol: str = "XAUUSD",
    live: bool = False,
) -> Dict[str, Any]:
    if now_utc is None:
        now_utc = dt.datetime.now(dt.timezone.utc)

    events = payload.get("events", [])
    headlines = list(payload.get("headlines", []))
    if live:
        tv_headlines = fetch_tradingview_headlines("OANDA:XAUUSD", limit=5)
        if tv_headlines:
            headlines = tv_headlines

    status = "SAFE"
    blackout_reason: Optional[str] = None
    upcoming_high: List[Dict[str, Any]] = []

    for ev in events:
        impact = str(ev.get("impact", "LOW")).upper()
        currency = str(ev.get("currency", "USD")).upper()
        if currency not in ("USD", "XAU", "ALL"):
            continue
        ev_time = parse_iso_utc(ev["time"])
        diff_min = (ev_time - now_utc).total_seconds() / 60.0

        ev_info = {
            "title": ev.get("title", "Economic Event"),
            "currency": currency,
            "impact": impact,
            "time": ev_time.isoformat(),
            "minutes_to_event": round(diff_min, 1),
        }

        if impact == "HIGH":
            upcoming_high.append(ev_info)
            if -post_blackout_min <= diff_min <= pre_blackout_min:
                status = "BLACKOUT"
                blackout_reason = (
                    f"High-impact {currency} event '{ev_info['title']}' at {ev_info['time']} "
                    f"({diff_min:+.1f} min from now)"
                )
            elif status != "BLACKOUT" and 0 <= diff_min <= caution_min:
                status = "CAUTION"

    sentiment = score_headlines(headlines)
    top_headline = headlines[0] if headlines else "Gold market steady ahead of US economic releases."
    id_analysis = analyze_xauusd_news_indonesia(top_headline)

    return {
        "skill": "trader-news",
        "symbol": symbol,
        "timestamp": now_utc.isoformat(),
        "status": status,
        "trade_allowed": status != "BLACKOUT",
        "blackout_reason": blackout_reason,
        "window_rules": {
            "pre_blackout_min": pre_blackout_min,
            "post_blackout_min": post_blackout_min,
            "caution_min": caution_min,
        },
        "sentiment_score": sentiment["sentiment_score"],
        "sentiment_bias": sentiment["sentiment_bias"],
        "matched_drivers": sentiment["matched_drivers"],
        "upcoming_high_impact": upcoming_high,
        "headlines_analyzed": len(headlines),
        "latest_headlines": headlines[:5],
        "xauusd_news_analysis": id_analysis,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="XAUUSD News Blackout Filter & Indonesian News Sentiment Analyzer")
    parser.add_argument("--symbol", default="XAUUSD", help="Symbol (default: XAUUSD)")
    parser.add_argument("--events-file", default=None, help="JSON file with events and headlines")
    parser.add_argument("--analyze-news", default=None, help="Analyze a news headline or public Telegram link in Indonesian")
    parser.add_argument("--live", action="store_true", help="Fetch live TradingView XAUUSD headlines")
    parser.add_argument("--now", default=None, help="Override current UTC ISO timestamp for testing")
    parser.add_argument("--pre-minutes", type=int, default=30, help="Minutes before HIGH impact event to block trading")
    parser.add_argument("--post-minutes", type=int, default=30, help="Minutes after HIGH impact event to block trading")
    parser.add_argument("--output", default="trader/news.json", help="Output JSON path")
    args = parser.parse_args(argv)

    if args.analyze_news is not None:
        analysis = analyze_xauusd_news_indonesia(args.analyze_news)
        print(analysis["formatted_output"])
        return 0

    if args.events_file and os.path.exists(args.events_file):
        with open(args.events_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
        use_live = False
    else:
        payload = default_news_payload()
        use_live = bool(args.live)

    now_utc = parse_iso_utc(args.now) if args.now else dt.datetime(2026, 11, 11, 13, 30, tzinfo=dt.timezone.utc)
    result = evaluate_news(
        payload=payload,
        now_utc=now_utc,
        pre_blackout_min=args.pre_minutes,
        post_blackout_min=args.post_minutes,
        symbol=args.symbol,
        live=use_live,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
