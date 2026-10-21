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

KEY = (
    os.environ.get("OPENDART_API_KEY", "").strip()
    or os.environ.get("DART_API_KEY", "").strip()
)
if not KEY:
    raise SystemExit(
        "DART API key is missing. Set repository secret OPENDART_API_KEY "
        "(recommended) or DART_API_KEY."
    )
print(f"DART API key detected (length={len(KEY)})")

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
    # Prefer exact account-name matches and rows that actually contain a value.
    aliases = [norm(a) for a in METRICS[metric]["aliases"]]
    exact = []
    partial = []
    for row in rows:
        label = norm(row.get("account_nm", ""))
        if not label:
            continue
        has_value = any(num(row.get(k)) is not None for k in ("thstrm_amount", "thstrm_add_amount"))
        if label in aliases:
            exact.append((not has_value, row))
        elif any(a and (label.startswith(a) or a in label) for a in aliases):
            partial.append((not has_value, row))
    candidates = exact or partial
    return sorted(candidates, key=lambda x: x[0])[0][1] if candidates else None


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
    """Extract legacy statements by table row, not by scanning arbitrary nearby text.

    Older DART documents often report amounts in million won. We only accept
    numeric cells from the same table row as the matched account label.
    """
    result = {metric: None for metric in METRICS}
    rcp_no = filing.get("rcept_no")
    if not rcp_no:
        return result
    try:
        content = get_binary("document.xml", {"rcept_no": rcp_no})
        if CFG["storage"].get("save_raw_filings", True):
            (RAW / f"{rcp_no}.zip").write_bytes(content)

        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            documents = []
            for name in archive.namelist():
                if name.lower().endswith((".xml", ".html", ".htm")):
                    try:
                        documents.append(archive.read(name))
                    except Exception:
                        continue
        all_text = " ".join(BeautifulSoup(part, "lxml").get_text(" ", strip=True) for part in documents)
        unit_text = norm(all_text[:20000])
        scale = 1.0
        if "백만원" in all_text[:20000]:
            scale = 1_000_000.0
        elif "천원" in all_text[:20000]:
            scale = 1_000.0

        aliases = {metric: [norm(a) for a in spec["aliases"]] for metric, spec in METRICS.items()}
        found = {metric: [] for metric in METRICS}
        for part in documents:
            soup = BeautifulSoup(part, "lxml")
            for tr in soup.find_all("tr"):
                cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"])]
                if len(cells) < 2:
                    continue
                label = norm(" ".join(cells[:2]))
                matched = []
                for metric, names in aliases.items():
                    if any(label == a or label.startswith(a) for a in names if a):
                        matched.append(metric)
                if not matched:
                    continue
                values = []
                for cell in cells[1:]:
                    value = num(cell.replace(" ", ""))
                    if value is not None:
                        values.append(value)
                if not values:
                    continue
                # The first amount column is the current-period figure in legacy statements.
                for metric in matched:
                    found[metric].append(values[0] * scale)

        for metric, candidates in found.items():
            if candidates:
                # Prefer the first table occurrence, as statement notes may repeat the same account.
                result[metric] = candidates[0]
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
    # Do not publish placeholder rows created when OpenDART has not yet published
    # a report (for example, a future Q3 report), or rows with no usable figures.
    primary_metrics = ["revenue", "operating_income", "net_income", "total_assets",
                       "total_liabilities", "total_equity"]
    existing_primary = [c for c in primary_metrics if c in df.columns]
    df = df.loc[df[existing_primary].notna().any(axis=1)].copy()
    # A financial row without any core amount is not useful and can hide API failures.
    if df.empty:
        raise RuntimeError("OpenDART returned no usable financial figures; refusing to overwrite the dashboard.")

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

# Quality gate: catch missing or implausible extraction before publishing.
annual = df[(df["report_type"] == "annual") & (df["year"] >= 2015)]
if not annual.empty:
    recent = annual[annual["year"] >= max(2015, END - 10)]
    if len(recent) and recent["revenue"].notna().mean() < 0.80:
        raise RuntimeError("Data quality check failed: too many annual revenue values are missing.")
    if len(recent) and recent["total_assets"].notna().mean() < 0.80:
        raise RuntimeError("Data quality check failed: too many annual total-asset values are missing.")
for col in ("operating_margin", "net_margin", "roe", "roa", "debt_ratio", "current_ratio", "asset_turnover"):
    if col in df and not pd.Series(df[col]).dropna().map(lambda x: abs(float(x)) < 1e6).all():
        raise RuntimeError(f"Data quality check failed: implausible values detected in {col}.")

df.to_csv(DATA / "financials.csv", index=False, encoding="utf-8-sig")
df.to_json(DATA / "financials.json", orient="records", force_ascii=False, indent=2)
(DATA / "filings.json").write_text(
    json.dumps(filing_meta, ensure_ascii=False, indent=2), encoding="utf-8"
)

print(f"records: {len(df)}")
print(f"business years: {START}-{END}")
