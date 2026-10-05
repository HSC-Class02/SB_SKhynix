import io
import json
import os
import re
import time
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config/config.yml").read_text(encoding="utf-8"))
METRICS = yaml.safe_load((ROOT / "config/metrics.yml").read_text(encoding="utf-8"))["metrics"]

KEY = os.environ.get("OPENDART_API_KEY", "").strip()
if not KEY:
    raise SystemExit("OPENDART_API_KEY secret is required.")

API = "https://opendart.fss.or.kr/api"
CORP = str(CFG["company"]["corp_code"])
START = int(CFG["company"]["start_year"])
END = int(CFG["company"]["end_year"] or datetime.now().year)
LEGACY_END = int(CFG["company"].get("legacy_end_year", 2014))

DATA = ROOT / "data"
RAW = DATA / "raw"
DATA.mkdir(exist_ok=True)
RAW.mkdir(exist_ok=True)

session = requests.Session()
session.headers["User-Agent"] = "SB_SKhynix-DART-Agent/2.0"


def get_json(path, params):
    p = dict(params)
    p["crtfc_key"] = KEY
    r = session.get(f"{API}/{path}", params=p, timeout=90)
    r.raise_for_status()
    obj = r.json()
    if obj.get("status") not in (None, "000"):
        raise RuntimeError(f"{obj.get('status')}: {obj.get('message')}")
    return obj


def get_binary(path, params):
    p = dict(params)
    p["crtfc_key"] = KEY
    r = session.get(f"{API}/{path}", params=p, timeout=120)
    r.raise_for_status()
    return r.content


def norm(x):
    return re.sub(r"[\s\(\)\[\]·•,.:;／/\\_-]", "", str(x)).lower()


def num(v):
    if v is None:
        return None
    x = str(v).strip().replace(",", "")
    if x in ("", "-", "—", "nan", "None"):
        return None
    if x.startswith("(") and x.endswith(")"):
        x = "-" + x[1:-1]
    try:
        return float(x)
    except ValueError:
        return None


def find_row(rows, metric):
    aliases = [norm(a) for a in METRICS[metric]["aliases"]]
    candidates = []
    for row in rows:
        label = norm(row.get("account_nm", ""))
        if not label:
            continue
        for alias in aliases:
            if label == alias:
                return row
            if alias and (alias in label or label in alias):
                candidates.append(row)
    return candidates[0] if candidates else None


def value_from_rows(rows, metric):
    row = find_row(rows, metric)
    if not row:
        return None
    for key in ("thstrm_amount", "thstrm_add_amount"):
        value = num(row.get(key))
        if value is not None:
            return value
    return None


def report_code(report_type):
    return {
        "annual": "11011",
        "half-year": "11012",
        "quarterly_q1": "11013",
        "quarterly_q3": "11014",
    }[report_type]


def structured_report(year, report_type):
    for fs_div in (
        CFG["financial_statement"]["fs_div"],
        CFG["financial_statement"]["fallback_fs_div"],
    ):
        try:
            obj = get_json(
                "fnlttSinglAcntAll.json",
                {
                    "corp_code": CORP,
                    "bsns_year": str(year),
                    "reprt_code": report_code(report_type),
                    "fs_div": fs_div,
                },
            )
            rows = obj.get("list", [])
            if rows:
                return rows, fs_div
        except Exception as exc:
            print(f"[WARN] structured {year} {report_type} {fs_div}: {exc}")
    return [], None


def filing_candidates(year):
    # Search through the following March so the annual report filed next year
    # is still associated with the correct business year.
    try:
        return get_json(
            "list.json",
            {
                "corp_code": CORP,
                "bgn_de": f"{year}0101",
                "end_de": f"{year + 1}0331",
                "pblntf_ty": "A",
                "sort": "date",
                "sort_mth": "asc",
                "page_no": 1,
                "page_count": 100,
            },
        ).get("list", [])
    except Exception as exc:
        print(f"[WARN] filing search {year}: {exc}")
        return []


def choose_legacy_filings(year):
    selected = {}
    for filing in filing_candidates(year):
        name = str(filing.get("report_nm", ""))
        if "사업보고서" in name:
            selected["annual"] = filing
        elif "반기보고서" in name:
            selected["half-year"] = filing
        elif "3분기보고서" in name:
            selected["quarterly_q3"] = filing
        elif "1분기보고서" in name:
            selected["quarterly_q1"] = filing
    return selected


def legacy_extract(filing):
    result = {metric: None for metric in METRICS}
    rcp_no = filing.get("rcept_no")
    if not rcp_no:
        return result
    try:
        content = get_binary("document.xml", {"rcept_no": rcp_no})
        if CFG["storage"].get("save_raw_filings", True):
            (RAW / f"{rcp_no}.zip").write_bytes(content)

        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            parts = []
            for name in archive.namelist():
                if name.lower().endswith((".xml", ".html", ".htm")):
                    try:
                        parts.append(
                            BeautifulSoup(
                                archive.read(name), "lxml-xml"
                            ).get_text(" ", strip=True)
                        )
                    except Exception:
                        pass
            text = " ".join(parts)

        for metric, spec in METRICS.items():
            for alias in spec["aliases"]:
                match = re.search(re.escape(str(alias)), text, flags=re.IGNORECASE)
                if not match:
                    continue
                window = text[match.end():match.end() + 350]
                numbers = re.findall(r"(?<![A-Za-z])\(?-?\d[\d,]*\)?", window)
                for candidate in numbers:
                    value = num(candidate)
                    if value is not None:
                        result[metric] = value
                        break
                if result[metric] is not None:
                    break
    except Exception as exc:
        print(f"[WARN] legacy parser {rcp_no}: {exc}")
    return result


def make_record(year, report_type, filing=None, rows=None, fs_div=None):
    record = {
        "year": year,
        "report_type": "quarterly" if report_type.startswith("quarterly_") else report_type,
        "quarter": (
            "Q1" if report_type == "quarterly_q1"
            else "Q3" if report_type == "quarterly_q3"
            else ""
        ),
        "report_nm": (filing or {}).get("report_nm", report_type),
        "rcept_no": (filing or {}).get("rcept_no"),
        "rcept_dt": (filing or {}).get("rcept_dt"),
        "dart_url": (
            f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={filing['rcept_no']}"
            if filing and filing.get("rcept_no") else ""
        ),
    }
    if rows:
        record.update({m: value_from_rows(rows, m) for m in METRICS})
        record["fs_div"] = fs_div
        record["source"] = "OpenDART fnlttSinglAcntAll"
    else:
        record.update(legacy_extract(filing) if filing else {m: None for m in METRICS})
        record["fs_div"] = None
        record["source"] = "OpenDART document.xml legacy parser"
    return record


records = []
filing_meta = []

# 2015 onward: query by BUSINESS YEAR, not receipt year.
for year in range(max(2015, START), END + 1):
    for report_type in ("annual", "half-year", "quarterly_q1", "quarterly_q3"):
        rows, fs_div = structured_report(year, report_type)
        if not rows:
            print(f"[WARN] no structured data: {year} {report_type}")
        records.append(make_record(year, report_type, rows=rows, fs_div=fs_div))
        time.sleep(0.15)

# 2010-2014: legacy DART documents; annual reports can be filed in the next year.
for year in range(START, min(LEGACY_END, END) + 1):
    selected = choose_legacy_filings(year)
    for report_type in ("annual", "half-year", "quarterly_q1", "quarterly_q3"):
        filing = selected.get(report_type)
        if not filing:
            print(f"[WARN] no legacy filing found: {year} {report_type}")
            continue
        records.append(make_record(year, report_type, filing=filing))
        filing_meta.append(filing)
        time.sleep(0.15)

df = pd.DataFrame(records)

if not df.empty:
    df = (
        df.sort_values(["year", "report_type", "quarter", "rcept_dt"])
        .drop_duplicates(["year", "report_type", "quarter"], keep="last")
        .sort_values(["year", "report_type", "quarter"])
    )

    def div(a, b):
        return a / b if pd.notna(a) and pd.notna(b) and b not in (0, 0.0) else None

    df["operating_margin"] = [div(a, b) for a, b in zip(df.operating_income, df.revenue)]
    df["net_margin"] = [div(a, b) for a, b in zip(df.net_income, df.revenue)]
    df["roe"] = [div(a, b) for a, b in zip(df.net_income, df.total_equity)]
    df["roa"] = [div(a, b) for a, b in zip(df.net_income, df.total_assets)]
    df["debt_ratio"] = [div(a, b) for a, b in zip(df.total_liabilities, df.total_equity)]
    df["current_ratio"] = [div(a, b) for a, b in zip(df.current_assets, df.current_liabilities)]
    df["asset_turnover"] = [div(a, b) for a, b in zip(df.revenue, df.total_assets)]
else:
    df = pd.DataFrame(columns=["year", "report_type", "quarter"])

df.to_csv(DATA / "financials.csv", index=False, encoding="utf-8-sig")
df.to_json(DATA / "financials.json", orient="records", force_ascii=False, indent=2)
(DATA / "filings.json").write_text(
    json.dumps(filing_meta, ensure_ascii=False, indent=2), encoding="utf-8"
)

print(f"records: {len(df)}")
print(f"business years: {START}-{END}")
