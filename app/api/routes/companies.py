from fastapi import APIRouter, UploadFile, File, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import io
import csv
from typing import List, Optional
import openpyxl
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

router = APIRouter(prefix="/api/v1/companies", tags=["Companies"])

COMPANY_COLUMN_CANDIDATES = [
    "company_name",
    "companyname",
    "company",
    "company_title",
    "employer",
    "employername",
    "employer_name",
    "organization",
    "organizationname",
    "organization_name",
    "org",
]

def normalize_name(name: str) -> str:
    if not name:
        return ""
    return name.lower().replace("_", "").replace(" ", "").strip()

def find_company_column(headers: List[str]) -> int:
    normalized_headers = [normalize_name(h) for h in headers]
    # Direct candidate match
    for candidate in COMPANY_COLUMN_CANDIDATES:
        for idx, norm_header in enumerate(normalized_headers):
            if norm_header == candidate:
                return idx
    # Substring match
    for idx, norm_header in enumerate(normalized_headers):
        if "company" in norm_header or "employer" in norm_header or "org" in norm_header:
            return idx
    return -1

def resolve_column_index(headers: List[str], column_hint: Optional[str]) -> int:
    if column_hint:
        candidates = [normalize_name(c.strip()) for c in column_hint.split(",") if c.strip()]
        # First check exact normalized match of user-specified candidates in order
        for candidate in candidates:
            for idx, h in enumerate(headers):
                if normalize_name(h) == candidate:
                    return idx
        # Next check substring match of user-specified candidates in order
        for candidate in candidates:
            for idx, h in enumerate(headers):
                if candidate in normalize_name(h):
                    return idx
    # Fallback to default candidates
    return find_company_column(headers)

def clean_preference_value(value) -> List[str]:
    if value is None:
        return []
    val_str = str(value).strip()
    if not val_str:
        return []
    # If it is a JSON list
    if val_str.startswith("[") and val_str.endswith("]"):
        try:
            import json as _json
            parsed = _json.loads(val_str)
            if isinstance(parsed, list):
                return [str(s).strip() for s in parsed if s]
        except Exception:
            pass
    # Otherwise split by commas/semicolons
    return [s.strip() for s in val_str.split(",") if s.strip()]

def find_column_by_candidates(headers: List[str], candidates: List[str]) -> int:
    normalized_headers = [normalize_name(h) for h in headers]
    for candidate in candidates:
        for idx, norm_header in enumerate(normalized_headers):
            if norm_header == candidate:
                return idx
    for idx, norm_header in enumerate(normalized_headers):
        for candidate in candidates:
            if candidate in norm_header:
                return idx
    return -1

def aggregate_rows(headers: List[str], rows: List[list], col_idx: int) -> tuple[List[str], List[dict]]:
    company_candidates = ["companyname", "company", "employer", "organization", "org"]
    country_candidates = ["companycountry", "country", "location", "nation"]
    category_candidates = ["category", "jobcategory", "department", "sect", "industry"]
    title_candidates = ["title", "jobtitle", "role", "position", "occupation"]
    link_candidates = ["joblink", "link", "url", "applylink", "applyurl", "joburl"]
    pref_candidates = ["keypreferences", "skills", "requiredskills", "preferences", "keypreference", "skill", "requirement", "requirements"]

    def find_idx(candidates):
        return find_column_by_candidates(headers, candidates)

    idx_map = {
        "company_name": col_idx if col_idx != -1 else find_idx(company_candidates),
        "company_country": find_idx(country_candidates),
        "category": find_idx(category_candidates),
        "title": find_idx(title_candidates),
        "job_link": find_idx(link_candidates),
        "key_preferences": find_idx(pref_candidates)
    }

    semantic_headers = {
        "company_name": "Company Name",
        "company_country": "Company Country",
        "category": "Category",
        "title": "Job Title",
        "job_link": "Job Link",
        "key_preferences": "Key Preferences"
    }

    # If the grouping column is in the headers, preserve its exact original name as key/header in output
    for sem_key, idx in idx_map.items():
        if idx == col_idx and idx != -1:
            semantic_headers[sem_key] = headers[col_idx]

    groups = {}
    for row in rows:
        if len(row) <= col_idx or col_idx == -1:
            continue
        val = row[col_idx]
        if val is None:
            continue
        val_str = str(val).strip()
        if not val_str:
            continue
        key_lower = val_str.lower()
        if key_lower not in groups:
            groups[key_lower] = []
        groups[key_lower].append(row)

    unique_rows = []
    for key_lower, grouped_rows in groups.items():
        # 1. Company Name
        comp_val = ""
        c_idx = idx_map["company_name"]
        if c_idx != -1:
            for r in grouped_rows:
                if len(r) > c_idx and r[c_idx] is not None:
                    c_val = str(r[c_idx]).strip()
                    if c_val:
                        comp_val = c_val
                        break
        if not comp_val:
            comp_val = str(grouped_rows[0][col_idx]).strip()

        # 2. Company Country
        country_vals = []
        co_idx = idx_map["company_country"]
        if co_idx != -1:
            for r in grouped_rows:
                if len(r) > co_idx and r[co_idx] is not None:
                    co_val = str(r[co_idx]).strip()
                    if co_val and co_val not in country_vals:
                        country_vals.append(co_val)
        country_str = "\n".join(country_vals)

        # 3. Category
        category_vals = []
        ca_idx = idx_map["category"]
        if ca_idx != -1:
            for r in grouped_rows:
                if len(r) > ca_idx and r[ca_idx] is not None:
                    ca_val = str(r[ca_idx]).strip()
                    if ca_val and ca_val not in category_vals:
                        category_vals.append(ca_val)
        category_str = "\n".join(category_vals)

        # 4. Job Title
        title_vals = []
        t_idx = idx_map["title"]
        if t_idx != -1:
            for r in grouped_rows:
                if len(r) > t_idx and r[t_idx] is not None:
                    t_val = str(r[t_idx]).strip()
                    if t_val and t_val not in title_vals:
                        title_vals.append(t_val)
        title_str = "\n".join(title_vals)

        # 5. Job Link
        link_vals = []
        l_idx = idx_map["job_link"]
        if l_idx != -1:
            for r in grouped_rows:
                if len(r) > l_idx and r[l_idx] is not None:
                    l_val = str(r[l_idx]).strip()
                    if l_val and l_val not in link_vals:
                        link_vals.append(l_val)
        link_str = "\n".join(link_vals)

        # 6. Key Preferences
        pref_vals = []
        p_idx = idx_map["key_preferences"]
        if p_idx != -1:
            for r in grouped_rows:
                if len(r) > p_idx and r[p_idx] is not None:
                    cleaned = clean_preference_value(r[p_idx])
                    for skill in cleaned:
                        if skill and skill not in pref_vals:
                            pref_vals.append(skill)
        pref_str = "\n".join(pref_vals)

        row_dict = {
            semantic_headers["company_name"]: comp_val,
            semantic_headers["company_country"]: country_str,
            semantic_headers["category"]: category_str,
            semantic_headers["title"]: title_str,
            semantic_headers["job_link"]: link_str,
            semantic_headers["key_preferences"]: pref_str
        }
        unique_rows.append(row_dict)

    sort_header = semantic_headers["company_name"]
    unique_rows.sort(key=lambda r: str(r.get(sort_header, "")).lower())

    final_headers = []
    order_keys = ["company_name", "company_country", "category", "title", "job_link", "key_preferences"]
    for k in order_keys:
        if idx_map[k] != -1:
            final_headers.append(semantic_headers[k])

    return final_headers, unique_rows

class DownloadRequest(BaseModel):
    companies: List[str]
    column_name: str = "company_name"
    rows: Optional[List[dict]] = None
    headers: Optional[List[str]] = None

@router.post("/parse")
async def parse_companies_file(
    file: UploadFile = File(...),
    column: Optional[str] = Query(default=None)
):
    filename = file.filename or ""
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    
    if ext not in ["csv", "xlsx", "xls"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format. Only CSV and Excel (.xlsx, .xls) files are supported."
        )
        
    contents = await file.read()
    headers = []
    raw_rows = []
    
    if ext == "csv":
        decoded = None
        for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
            try:
                decoded = contents.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if decoded is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not decode the CSV file. Please ensure it uses UTF-8 or standard Western encoding."
            )
            
        stream = io.StringIO(decoded)
        try:
            sample = stream.read(2048)
            stream.seek(0)
            dialect = csv.Sniffer().sniff(sample)
        except Exception:
            dialect = "excel"
            
        reader = csv.reader(stream, dialect)
        headers_row = next(reader, None)
        if not headers_row:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The uploaded CSV file is empty."
            )
        headers = headers_row
        
        col_idx = resolve_column_index(headers, column)
            
        if col_idx == -1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Could not automatically detect the company name column. Available columns: {headers}. Please specify the column name."
            )
            
        for row in reader:
            raw_rows.append(row)
    else:
        # Excel
        try:
            wb = openpyxl.load_workbook(io.BytesIO(contents), read_only=True, data_only=True)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to parse Excel file: {str(e)}"
            )
            
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        headers_row = next(rows_iter, None)
        if not headers_row:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The uploaded Excel sheet is empty."
            )
            
        headers = [str(cell) if cell is not None else "" for cell in headers_row]
        
        col_idx = resolve_column_index(headers, column)
            
        if col_idx == -1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Could not automatically detect the company name column. Available columns: {headers}. Please specify the column name."
            )
            
        for row in rows_iter:
            raw_rows.append(list(row))
        wb.close()
        
    selected_col_name = headers[col_idx] if col_idx != -1 else ""
    final_headers, unique_rows = aggregate_rows(headers, raw_rows, col_idx)
    
    # Extract list of company names for preview
    sorted_companies = [str(r.get(selected_col_name, "")) for r in unique_rows]
    
    return {
        "companies": sorted_companies,
        "detected_column": selected_col_name,
        "total_unique": len(sorted_companies),
        "available_columns": final_headers,
        "unique_rows": unique_rows,
    }

@router.post("/download/csv")
def download_companies_csv(payload: DownloadRequest):
    buf = io.StringIO()
    writer = csv.writer(buf)
    
    if payload.headers and payload.rows:
        writer.writerow(payload.headers)
        for row in payload.rows:
            writer.writerow([row.get(h, "") for h in payload.headers])
    else:
        writer.writerow([payload.column_name])
        for company in payload.companies:
            writer.writerow([company])
    
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="unique_companies.csv"'}
    )

@router.post("/download/excel")
def download_companies_excel(payload: DownloadRequest):
    wb = Workbook()
    ws = wb.active
    ws.title = "Unique Data"
    
    if payload.headers and payload.rows:
        header_fill = PatternFill(start_color="1F2937", end_color="1F2937", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF")
        
        # Write headers
        for col_idx, h in enumerate(payload.headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=h)
            cell.font = header_font
            cell.fill = header_fill
            
        # Write rows
        for row_idx, row in enumerate(payload.rows, start=2):
            for col_idx, h in enumerate(payload.headers, start=1):
                val = row.get(h, "")
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                if isinstance(val, str) and "\n" in val:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
                else:
                    cell.alignment = Alignment(vertical="top")
                
        # Auto-width
        for col in ws.columns:
            max_len = 10
            for cell in col:
                val_str = str(cell.value or "")
                if "\n" in val_str:
                    lines = val_str.split("\n")
                    max_line_len = max((len(l) for l in lines), default=0)
                    if max_line_len > max_len:
                        max_len = max_line_len
                else:
                    if len(val_str) > max_len:
                        max_len = len(val_str)
            ws.column_dimensions[col[0].column_letter].width = min(max(max_len + 4, 12), 60)
    else:
        ws.cell(row=1, column=1, value=payload.column_name)
        ws.cell(row=1, column=1).font = Font(bold=True, color="FFFFFF")
        ws.cell(row=1, column=1).fill = PatternFill(start_color="1F2937", end_color="1F2937", fill_type="solid")
        
        for idx, company in enumerate(payload.companies, start=2):
            ws.cell(row=idx, column=1, value=company)
            
        max_len = max((len(c) for c in payload.companies), default=15)
        ws.column_dimensions["A"].width = max(max_len + 4, 15)
    
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="unique_companies.xlsx"'}
    )


class EnrichRequest(BaseModel):
    companies: List[str]
    api_key: Optional[str] = None
    limit: Optional[int] = None   # max companies to enrich; None = all
    # Optional dict mapping company_name -> country hint (improves match accuracy, no extra credits)
    company_countries: Optional[dict] = None


def _match_confidence(input_name: str, matched_name: str) -> str:
    """
    Compare input vs matched name and return a confidence label.
    - 'exact'   : names match (case-insensitive)
    - 'partial' : one is a substring of the other
    - 'low'     : share some words but differ
    - 'mismatch': names look unrelated — needs human review
    """
    if not matched_name:
        return "mismatch"
    a = input_name.lower().strip()
    b = matched_name.lower().strip()
    if a == b:
        return "exact"
    if a in b or b in a:
        return "partial"
    words_a = set(a.split())
    words_b = set(b.split())
    if words_a & words_b:
        return "low"
    return "mismatch"


@router.post("/enrich")
async def enrich_companies(payload: EnrichRequest):
    import httpx
    import asyncio
    import os

    api_key = payload.api_key or os.environ.get("APOLLO_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apollo API key is required. Please provide it in the input field or set APOLLO_API_KEY in the environment."
        )

    # Apply limit — clamp between 1 and total list size
    companies_to_enrich = payload.companies
    if payload.limit is not None and payload.limit > 0:
        companies_to_enrich = payload.companies[: payload.limit]

    country_map = payload.company_countries or {}

    base_url = "https://api.apollo.io/api/v1/organizations/search"
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": api_key,
    }

    enriched_results = []

    async with httpx.AsyncClient(timeout=20.0) as client:
        for idx, name in enumerate(companies_to_enrich):
            clean_name = (name or "").strip()
            if not clean_name:
                continue

            search_payload = {"q_organization_name": clean_name, "page": 1, "per_page": 1}

            try:
                resp = await client.post(base_url, headers=headers, json=search_payload)
                orgs = []
                if resp.status_code == 200:
                    orgs = resp.json().get("organizations", [])

                if resp.status_code == 200:
                    if orgs:
                        org = orgs[0]
                        matched_name = org.get("name")
                        confidence = _match_confidence(clean_name, matched_name or "")
                        enriched_results.append({
                            "input_company_name": clean_name,
                            "matched_name": matched_name,
                            "match_confidence": confidence,
                            "organization_id": org.get("id"),
                            "domain": org.get("primary_domain"),
                            "website_url": org.get("website_url"),
                            "linkedin_url": org.get("linkedin_url"),
                            "twitter_url": org.get("twitter_url"),
                            "facebook_url": org.get("facebook_url"),
                            "phone": org.get("phone"),
                            "industry": org.get("industry"),
                            "estimated_num_employees": org.get("estimated_num_employees"),
                            "founded_year": org.get("founded_year"),
                            "market_cap": org.get("market_cap"),
                            "publicly_traded_symbol": org.get("publicly_traded_symbol"),
                            "status": "success"
                        })
                    else:
                        enriched_results.append({
                            "input_company_name": clean_name,
                            "status": "not_found"
                        })
                elif resp.status_code == 401:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid Apollo API Key. Please verify your credentials."
                    )
                elif resp.status_code == 429:
                    await asyncio.sleep(2.0)
                    enriched_results.append({
                        "input_company_name": clean_name,
                        "status": "rate_limited"
                    })
                else:
                    enriched_results.append({
                        "input_company_name": clean_name,
                        "status": f"http_error_{resp.status_code}"
                    })
            except HTTPException:
                raise
            except Exception as e:
                enriched_results.append({
                    "input_company_name": clean_name,
                    "status": f"request_failed: {str(e)}"
                })

            # Polite delay between requests to avoid rate limiting
            await asyncio.sleep(0.8)

    return {"enriched": enriched_results}
