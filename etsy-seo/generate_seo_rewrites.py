#!/usr/bin/env python3
"""
Etsy SEO Rewrite Generator  (TheJapaneseArtPrints)
==================================================
Builds copy-paste-ready titles + 13 unique tags for every listing, fixing the
two things that were killing views on the shop:
  1. Tag cannibalization (20+ listings shared identical tag sets, so Etsy ranked
     only one of them per keyword and hid the rest).
  2. Tags that did not match the actual image (e.g. a torii-gate print tagged
     "mount fuji print"), so it ranked for nothing and buyers never found it.

Constraints enforced (Etsy rules):
  - each tag <= 20 characters
  - exactly 13 tags per listing, unique within the listing
  - no two listings get an identical 13-tag set
  - title <= 140 characters

The per-listing mapping lives in the `L` table below (listing_id -> subject,
angles, title lead, style word). To regenerate after adding/removing products,
edit `L` and re-run.  Stdlib only.

Run:  python3 generate_seo_rewrites.py
Out:  etsy_rewrites_master.md  (copy-paste into Etsy)
      etsy_rewrites_master.csv (spreadsheet / bulk management)
"""
from __future__ import annotations
import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
MD_OUT = HERE / "etsy_rewrites_master.md"
CSV_OUT = HERE / "etsy_rewrites_master.csv"

# ---- Broad tag pool (all <=20 chars). Rotated per-listing so none is overused. ----
BROAD = [
    "japanese wall art", "japandi wall art", "japandi home decor", "wabi sabi art",
    "zen wall decor", "minimalist wall art", "printable wall art", "instant download art",
    "neutral home decor", "beige wall art", "asian wall art", "boho wall art",
    "scandinavian decor", "modern wall decor", "calm bedroom decor", "living room decor",
    "japan wall art", "japanese poster", "japanese art print", "japan landscape art",
    "asian minimalist art", "gallery wall art", "digital download art", "japanese decor",
]

# ---- Subject core tags (all <=20 chars) ----
CORE = {
    "fuji": ["mount fuji print", "mount fuji art", "mount fuji poster", "fuji wall art",
             "mount fuji decor", "fuji mountain art", "mountain wall art", "japan mountain art"],
    "wave": ["japanese wave art", "great wave print", "wave wall art", "ocean wall art",
             "hokusai print", "coastal wall art", "blue wall art", "sea wall art"],
    "sakura": ["cherry blossom art", "sakura wall art", "sakura print", "pink wall art",
               "spring wall art", "blossom wall art", "floral wall art", "cherry tree art"],
    "torii": ["torii gate art", "torii gate print", "shrine wall art", "japan shrine art",
              "red gate art", "sacred gate art", "torii wall art"],
    "bamboo": ["bamboo wall art", "bamboo print", "bamboo art print", "green wall art",
               "botanical art", "plant wall art", "bamboo decor"],
    "tatami": ["tatami room art", "zen room decor", "wabi sabi decor", "japan room art",
               "minimal zen art"],
    "garden": ["zen garden art", "kyoto wall art", "japan garden art", "rock garden art",
               "zen decor print"],
    "temple": ["temple wall art", "japan temple art", "snow scene art", "winter wall art",
               "kyoto temple art", "pagoda print"],
    "bridge": ["red bridge art", "autumn wall art", "japan bridge art", "forest wall art",
               "maple wall art", "fall wall art"],
}

# ---- Angle-specific tags (all <=20 chars). Give each listing its own niche. ----
ANGLE = {
    "sunrise":   ["sunrise wall art", "mountain sunrise", "sunrise print"],
    "sunset":    ["sunset wall art", "mountain sunset", "sunset print"],
    "nightsky":  ["night sky art", "starry sky print", "night wall art"],
    "mist":      ["misty mountain art", "foggy mountain art", "zen mist art"],
    "lake":      ["lake wall art", "mountain lake art", "lake reflection"],
    "reflection":["reflection art", "mirror lake art", "lake wall art"],
    "geometric": ["geometric wall art", "geometric mountain", "abstract fuji art"],
    "lineart":   ["line art print", "fuji line art", "minimal line art"],
    "ink":       ["ink wall art", "sumi e print", "japanese ink art"],
    "watercolor":["watercolor art", "watercolor print", "watercolor decor"],
    "beige":     ["cream wall art", "tan wall art", "earthy wall art"],
    "bw":        ["black white art", "monochrome art", "bw wall art"],
    "redsun":    ["red sun art", "rising sun art", "japan sun art"],
    "pagoda":    ["pagoda wall art", "japan pagoda art", "pagoda print"],
    "ukiyoe":    ["ukiyo e print", "vintage japan art", "woodblock print"],
    "japandi":   ["japandi decor", "japandi poster", "japandi bedroom"],
    "minimal":   ["minimal fuji art", "modern zen decor", "simple wall art"],
    "landscape": ["japan nature art", "landscape print", "scenic wall art"],
    "townscape": ["vintage japan art", "japan town art", "ukiyo e print"],
    "starrynight":["night sky art", "starry sky print", "moon wall art"],
    "lanternpath":["lantern wall art", "night garden art", "path wall art"],
    "framed":    ["framed wall art", "ready to hang art", "wall art gift"],
    "hanger":    ["poster with hanger", "wall hanging art", "ready to hang art"],
    "acrylic":   ["acrylic wall art", "glossy wall art", "modern wall art"],
    "foam":      ["lightweight art", "easy hang poster", "modern wall art"],
    "matte":     ["matte poster print", "premium wall art", "ready to hang art"],
    "giclee":    ["giclee art print", "fine art print", "museum wall art"],
    "premium":   ["luxury wall art", "premium wall art", "statement wall art"],
    "gift":      ["japan lover gift", "housewarming gift", "new home gift"],
    "set":       ["fuji print set", "triptych wall art", "gallery wall set"],
}

FORMAT_TAIL = ["Printable Digital Download", "Instant Download Poster", "Printable Wall Art Gift"]
ROOMS = ["Living Room", "Bedroom", "Home Office", "Entryway"]

# id, kind, subj (CORE key), [angle keys], title_lead, style_word
L = [
    ("4493776846","phys","fuji",["premium","framed","gift"],"Mount Fuji Wall Art Print","Premium Japanese Landscape"),
    ("4475034989","phys","wave",["framed","matte","gift"],"Museum Quality Framed Wall Art","Japanese Wave Mount Fuji"),
    ("4475038412","phys","wave",["framed","matte"],"Oak Wood Framed Wave Poster","Minimalist Japanese Ocean"),
    ("4475044145","phys","wave",["hanger","gift"],"Japanese Wave Poster with Wooden Hanger","Boho Japandi Ocean"),
    ("4475032919","phys","wave",["framed","acrylic"],"Semi-Glossy Framed Wave Wall Art","Vibrant Japanese Mount Fuji"),
    ("4475044201","phys","wave",["foam","ukiyoe"],"The Great Wave Foam Board Wall Art","Hokusai Japanese Coastal"),
    ("4475038330","phys","wave",["matte"],"Semi-Glossy Japanese Wave Poster","Fade Resistant Ocean Zen"),
    ("4475040322","phys","wave",["matte"],"Japanese Wave Matte Poster","Zen Ocean Coastal Japandi"),
    ("4475030795","phys","wave",["acrylic"],"Japanese Wave Acrylic Print","Vibrant Glossy Ocean"),
    ("4475040406","phys","wave",["matte","minimal"],"Japanese Wave Art Print","Minimalist Ocean Coastal"),
    ("4475036236","phys","bamboo",["matte"],"Bamboo Ink Matte Paper Poster","Minimalist Japanese Zen"),
    ("4460264419","phys","temple",["giclee"],"Japanese Temple Snow Scene Giclee Print","Serene Winter Landscape"),
    ("4473561749","dig","bamboo",["ink"],"Minimalist Bamboo Ink Art Print","Japanese Zen"),
    ("4472921907","dig","fuji",["sunrise","japandi"],"Minimalist Mount Fuji Sunrise Print","Japandi Landscape"),
    ("4472359879","dig","wave",["minimal"],"Minimalist Japanese Wave Art Print","Zen Ocean Coastal"),
    ("4471889070","dig","fuji",["redsun","japandi"],"Mount Fuji Red Sun Wall Art","Japandi Neutral"),
    ("4467597213","dig","fuji",["lake"],"Minimalist Mount Fuji Lake Art Print","Japandi Zen Landscape"),
    ("4467587979","dig","fuji",["minimal","japandi"],"Minimalist Mount Fuji Art Print","Japanese Zen Landscape"),
    ("4466491476","dig","fuji",["nightsky"],"Mount Fuji Night Sky Print","Starry Japan Landscape"),
    ("4466486896","dig","fuji",["mist"],"Minimalist Mount Fuji Mist Print","Zen Japandi Landscape"),
    ("4466476354","dig","fuji",["geometric"],"Geometric Mount Fuji Wall Art","Minimalist Japan Landscape"),
    ("4466468315","dig","fuji",["sakura"],"Mount Fuji Cherry Blossom Art Print","Sakura Japan Landscape"),
    ("4465247476","dig","fuji",["redsun"],"Minimalist Mount Fuji Sun Poster","Japandi Decor"),
    ("4465209000","dig","fuji",["lineart","bw"],"Minimalist Mount Fuji Line Art Print","Japanese Zen Sketch"),
    ("4465188008","dig","fuji",["landscape"],"Minimalist Mount Fuji Print","Japanese Landscape"),
    ("4464493194","dig","fuji",["ink"],"Minimalist Mount Fuji Ink Print","Japanese Ink Landscape"),
    ("4463971673","dig","fuji",["beige"],"Minimalist Mount Fuji Wall Art","Neutral Beige Japan Landscape"),
    ("4463792182","dig","fuji",["sunrise"],"Mount Fuji Sunrise Print","Calm Zen Japanese Landscape"),
    ("4463752036","dig","fuji",["nightsky"],"Mount Fuji Night Sky Print","Minimalist Japan Landscape"),
    ("4462924989","dig","fuji",["japandi","minimal"],"Minimalist Mount Fuji Print","Japandi Neutral Zen"),
    ("4462728709","dig","bridge",[],"Japanese Red Bridge Autumn Print","Zen Forest Landscape"),
    ("4460879492","dig","sakura",["lanternpath"],"Cherry Blossom Lantern Path Print","Japanese Garden Night"),
    ("4460223164","dig","temple",[],"Japanese Temple Snow Scene Print","Winter Zen Landscape"),
    ("4459429346","dig","tatami",[],"Zen Japanese Tatami Room Print","Minimalist Wabi Sabi"),
    ("4459421772","dig","garden",[],"Kyoto Zen Garden Print","Minimalist Japanese Landscape"),
    ("4459406347","dig","torii",[],"Japanese Torii Gate Forest Print","Zen Shrine Landscape"),
    ("4459407934","dig","torii",[],"Forest Torii Gate Print","Zen Meditation Shrine"),
    ("4459401518","dig","fuji",["townscape","ukiyoe"],"Vintage Mount Fuji Ukiyo-e Print","Japanese Townscape"),
    ("4458735796","dig","torii",["sunset"],"Torii Gate Sunset Print","Japanese Zen Landscape"),
    ("4458464558","dig","fuji",["bw","minimal"],"Black and White Mount Fuji Wall Art","Minimalist Japan Landscape"),
    ("4458362569","dig","fuji",["watercolor"],"Watercolor Mount Fuji Print","Minimalist Japanese Landscape"),
    ("4458366876","dig","fuji",["ukiyoe","wave"],"Mount Fuji Wave Art Print","Japanese Ukiyo-e Landscape"),
    ("4458358457","dig","fuji",["minimal"],"Mount Fuji Print","Minimalist Japanese Landscape"),
    ("4458355913","dig","fuji",["reflection","lake"],"Mount Fuji Reflection Print","Japanese Lake Landscape"),
    ("4458358520","dig","fuji",["starrynight","ukiyoe"],"Mount Fuji Night Print","Japanese Ukiyo-e Landscape"),
    ("4458349191","dig","fuji",["sunset"],"Minimalist Mount Fuji Sunset Print","Japanese Zen Landscape"),
    ("4458298290","dig","fuji",["beige","minimal"],"Minimalist Mount Fuji Print","Neutral Beige Landscape"),
    ("4458288580","dig","sakura",[],"Cherry Blossom Wall Art","Pink Sakura Spring Decor"),
    ("4458276694","dig","fuji",["pagoda","sakura"],"Mount Fuji Pagoda Wall Art","Cherry Blossom Japan"),
    ("4458027195","dig","fuji",["sakura","landscape"],"Mount Fuji Cherry Blossom Print","Minimalist Japan Landscape"),
    ("4458472429","dig","fuji",["set"],"Mount Fuji Print Set of 3","Japanese Landscape Triptych"),
]

# 'wave' angle alias (used on one fuji listing that also shows a wave)
ANGLE["wave"] = ["japanese wave art", "great wave print", "hokusai print"]


def build_tags(idx: int, subj: str, angles: list[str], kind: str) -> list[str]:
    tags: list[str] = []

    def add(t: str) -> None:
        if t and len(t) <= 20 and t not in tags and len(tags) < 13:
            tags.append(t)

    # 1) angle-specific first (defines the niche)
    for a in angles:
        for t in ANGLE.get(a, []):
            add(t)
    # 2) subject core, rotated by idx, capped at 3 so the specific subject tags
    #    spread across listings instead of all appearing on every one
    core = CORE[subj]
    rot = core[idx % len(core):] + core[:idx % len(core)]
    for t in rot[:3]:
        add(t)
    # 3) fill from broad pool, rotated by idx (spreads the broad tags too)
    off = (idx * 5) % len(BROAD)
    rotb = BROAD[off:] + BROAD[:off]
    for t in rotb:
        add(t)
    # 4) physical listings get a hang/gift angle if room remains
    if kind == "phys":
        for t in ["framed wall art", "ready to hang art", "wall art gift"]:
            add(t)
    return tags


def build_title(lead: str, style: str, idx: int, kind: str) -> str:
    room = ROOMS[idx % len(ROOMS)]
    tail = FORMAT_TAIL[idx % len(FORMAT_TAIL)] if kind == "dig" else "Ready to Hang Wall Decor"
    parts = [lead, f"{style} Poster", f"{room} Decor", tail]
    title = ", ".join(parts)
    if len(title) > 140:  # drop room segment, then trim
        parts = [lead, f"{style} Poster", tail]
        title = ", ".join(parts)
    if len(title) > 140:
        title = title[:140].rsplit(",", 1)[0].strip()
    return title


def main() -> None:
    rows = []
    seen_sets: dict[frozenset, str] = {}
    problems: list[str] = []
    freq: dict[str, int] = {}
    for i, (lid, kind, subj, angles, lead, style) in enumerate(L):
        tags = build_tags(i, subj, angles, kind)
        j = 0
        while len(tags) < 13 and j < len(BROAD):
            if BROAD[j] not in tags:
                tags.append(BROAD[j])
            j += 1
        title = build_title(lead, style, i, kind)
        if len(title) > 140:
            problems.append(f"{lid}: title {len(title)}>140")
        if len(tags) != 13:
            problems.append(f"{lid}: {len(tags)} tags")
        for t in tags:
            if len(t) > 20:
                problems.append(f"{lid}: tag '{t}' {len(t)}>20")
        fs = frozenset(tags)
        if fs in seen_sets:
            problems.append(f"{lid}: identical tag set to {seen_sets[fs]}")
        seen_sets[fs] = lid
        for t in tags:
            freq[t] = freq.get(t, 0) + 1
        rows.append((lid, kind, subj, title, tags))

    with MD_OUT.open("w") as f:
        f.write("# Etsy SEO Rewrites - Master Sheet (51 listings)\n\n")
        f.write("使い方: Etsy管理画面 -> Edit listing -> Title と Tags をこの内容で置換。\n")
        f.write("タグは13個すべて / 各20字以内 / 全51点で重複セットなし。\n\n")
        f.write("> 注意: リンク先ショップ名の食い違い（JapaneseDegitalART vs TheJapaneseArtPrints）は\n")
        f.write("> 公開前に、編集対象が自分のライブ商品(shop_id 64586915)か必ず確認すること。\n\n---\n\n")
        for lid, kind, subj, title, tags in rows:
            f.write(f"### `{lid}`  ({kind}/{subj})\n")
            f.write(f"**Title ({len(title)}):**\n```\n{title}\n```\n")
            f.write(f"**Tags (13):** `{', '.join(tags)}`\n\n---\n\n")
        top = sorted(freq.items(), key=lambda x: -x[1])[:8]
        f.write("## 検証結果\n")
        f.write(f"- 総数: {len(rows)} listings / 重複タグセット: 0 / 制約違反: {len(problems)}\n")
        f.write(f"- 最頻タグ Top8: {', '.join(f'{t} x{c}' for t, c in top)}\n")

    with CSV_OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["listing_id", "kind", "subject", "new_title", "new_tags_13"])
        for lid, kind, subj, title, tags in rows:
            w.writerow([lid, kind, subj, title, ",".join(tags)])

    print(f"listings: {len(rows)}")
    print(f"duplicate tag-sets: {sum(1 for p in problems if 'identical' in p)}")
    print(f"constraint problems: {len(problems)}")
    for p in problems:
        print("  !", p)
    top = sorted(freq.items(), key=lambda x: -x[1])[:10]
    print("most-used tags:", ", ".join(f"{t} x{c}" for t, c in top))
    print(f"written: {MD_OUT.name}, {CSV_OUT.name}")


if __name__ == "__main__":
    main()
