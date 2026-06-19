# scripts/main.py 1
import argparse
import os
import sys
import json
import logging
import subprocess
import time
from typing import List
import httpx
from dotenv import load_dotenv
from groq import Groq
import groq
from pydantic import BaseModel, Field
import concurrent.futures

# Configure basic logging architecture for system visibility
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("prospector_main")

# Reconfigure stdout/stderr to support UTF-8 natively on Windows console
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

load_dotenv()

def get_next_groq_key() -> str:
    keys = []
    for i in range(1, 10):
        key = os.getenv(f"GROQ_API_KEY_{i}")
        if key:
            keys.append(key)
    if not keys:
        standard_key = os.getenv("GROQ_API_KEY")
        if standard_key:
            keys.append(standard_key)
            
    if not keys:
        logger.error("No Groq API keys found in environment variables.")
        raise ValueError("No Groq API keys found in environment variables.")
        
    state_file = ".tmp/groq_rotator_state.json"
    os.makedirs(".tmp", exist_ok=True)
    
    current_index = 0
    import random
    # Self-healing cross-process file-access rotator logic
    for attempt in range(5):
        try:
            if os.path.exists(state_file):
                with open(state_file, "r") as f:
                    state = json.load(f)
                    current_index = state.get("current_index", 0)
            break
        except (IOError, json.JSONDecodeError, ValueError):
            time.sleep(0.02 + random.uniform(0.01, 0.03))
            
    selected_key = keys[current_index % len(keys)]
    next_index = (current_index + 1) % len(keys)
    
    for attempt in range(5):
        try:
            with open(state_file, "w") as f:
                json.dump({"current_index": next_index}, f)
            break
        except IOError:
            time.sleep(0.02 + random.uniform(0.01, 0.03))
        
    masked_key = selected_key[:7] + "..." + selected_key[-4:] if len(selected_key) > 10 else "..."
    logger.info(f"Rotating Groq API Key: selected key index {current_index % len(keys)} ({masked_key})")
    return selected_key

class CompanyDiscoveryResult(BaseModel):
    companies: list[str] = Field(description="List of exactly 15 to 20 real companies fitting the requested criteria parameters.")

def discover_companies(industry: str, size: str, advanced_keywords: str, country: str) -> list[str]:
    logger.info(f"Discovering {industry} companies in {country} of size {size} using Tavily search and Groq...")
    
    tavily_key: str = os.getenv("TAVILY_API_KEY", "")
    if not tavily_key:
        logger.error("Tavily API key not found.")
        return []
        
    query = f"list of active real {industry} companies in {country} with {size} employees involved in or matching: {advanced_keywords}"
    
    raw_context = ""
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                "https://api.tavily.com/search",
                json={"api_key": tavily_key, "query": query, "search_depth": "advanced", "max_results": 8}
            )
            if response.status_code == 200:
                results = response.json().get("results", [])
                snippets = [f"Title: {r.get('title')}\nContent: {r.get('content') or r.get('snippet')}" for r in results]
                raw_context = "\n\n".join(snippets)
            else:
                logger.error(f"Tavily search failed with status {response.status_code}")
    except Exception as e:
        logger.error(f"Error calling Tavily Search API: {e}")
        return []

    if not raw_context:
        logger.error("No raw context retrieved from Tavily.")
        return []

    # Enforce strict pacing delay of 3.0 seconds before Groq call
    logger.info("Enforcing strict 3.0s pacing delay before querying Groq...")
    time.sleep(3.0)

    prompt = f"""
    Analyze the following web search results and extract exactly 15 to 20 real active company names in {country} matching:
    - Industry: {industry}
    - Size: {size} employees
    - Target Intent/Profile: {advanced_keywords}
    
    Search Results:
    {raw_context}
    
    Extract ONLY the clean real names of these companies. Return a structured JSON array under the key 'companies'.
    Matches must match the format: {{"companies": ["Company A", "Company B"]}}
    """

    max_retries = 3
    retry_delay = 5.0
    extraction_response = None
    
    for attempt in range(max_retries):
        try:
            api_key = get_next_groq_key()
            groq_client = Groq(api_key=api_key)
            chat_completion = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional business development validator. You MUST respond with a valid JSON object matching the requested schema."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                response_format={"type": "json_object"}
            )
            extraction_response = chat_completion.choices[0].message.content
            break
        except Exception as e:
            if "429" in str(e) or "rate_limit" in str(e) or "rate limit" in str(e).lower():
                logger.warning(f"Groq Rate Limit hit. Retrying in {retry_delay}s... (Attempt {attempt+1}/{max_retries})")
                time.sleep(retry_delay)
                retry_delay *= 2.0
            else:
                logger.error(f"Non-retryable Groq generation error: {e}")
                break

    if not extraction_response:
        logger.error("Failed to extract company names due to Groq rate limits or generation failures.")
        return []

    try:
        # First attempt: strict Pydantic validation
        result = CompanyDiscoveryResult.model_validate_json(extraction_response)
        return result.companies
    except Exception as e:
        logger.warning(f"Standard Pydantic validation failed, executing tolerant dictionary parser fallback: {e}")
        try:
            raw_json = json.loads(extraction_response)
            companies_list = raw_json.get("companies", [])
            extracted_names = []
            for item in companies_list:
                if isinstance(item, dict):
                    # Seek standard company name naming keys
                    name = item.get("name") or item.get("company_name") or item.get("company")
                    if name:
                        extracted_names.append(str(name))
                elif isinstance(item, str):
                    extracted_names.append(item)
            if extracted_names:
                logger.info(f"Tolerant parser successfully recovered {len(extracted_names)} company names: {extracted_names}")
                return extracted_names
        except Exception as inner_err:
            logger.error(f"Tolerant parser failed to parse Groq response JSON: {inner_err}")
            
        logger.error(f"Error validating company name JSON: {e}. Raw response: {extraction_response}")
        return []


def update_server_status(job_id: str, phase: str, percentage: int) -> None:
    """Pipes execution progress status back into the active FastAPI instance state registry dynamically."""
    internal_url: str = os.getenv("INTERNAL_BACKEND_URL", "http://localhost:8000")
    headers = {}
    api_key = os.getenv("GLOVAR_BACKEND_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key
    try:
         httpx.patch(f"{internal_url}/api/v1/internal/update-job/{job_id}", json={
            "current_phase": phase,
            "progress_percentage": percentage
        }, headers=headers, timeout=2.0)
    except Exception as e:
        logger.debug(f"Failed to pipe status telemetry update to dashboard app: {e}")

def main() -> None:
    parser = argparse.ArgumentParser(description="Glovar Lead Prospector Engine Main Hub - Discovery First")
    parser.add_argument("--payload_path", required=True)
    parser.add_argument("--user_id", required=True)
    parser.add_argument("--job_id", required=True)
    args = parser.parse_args()

    with open(args.payload_path, "r") as f:
        form_data = json.load(f)

    industry: str = form_data["sector"]
    size: str = form_data["tamano_empresa"]
    advanced_keywords: str = form_data.get("triggers_compra") or form_data.get("keywords_industria") or "operations"

    with open(".tmp/active_runtime_context.json", "w") as f:
        json.dump(form_data, f, indent=2)

    country: str = form_data.get("pais") or "Colombia"
    discovered_companies: list[str] = discover_companies(industry, size, advanced_keywords, country)
    if not discovered_companies:
        logger.info("No companies discovered. Pipeline halting gracefully.")
        sys.exit(0)
        
    exclusion_list: list[str] = [name.strip().lower() for name in form_data.get("exclusion_list", [])]
    clean_companies: list[str] = [c for c in discovered_companies if c.strip().lower() not in exclusion_list][:20]  # Enforce strict maximum of 20 companies per execution run to prevent LLM extraction overflow
    
    if not clean_companies:
        logger.info("All targets matched blacklist exclusion array parameters. Exiting.")
        sys.exit(0)
        
    total_batch: int = len(clean_companies)
    processed_count = 0
    import threading
    lock = threading.Lock()

    def process_company(company: str):
        nonlocal processed_count
        with lock:
            start_weight = int(10 + ((processed_count / total_batch) * 85))
        update_server_status(args.job_id, f"Processing target asset: {company}", start_weight)
        
        try:
            subprocess.run([sys.executable, "-u", "scripts/news_scraper.py", "--company", company], check=True)
            subprocess.run([sys.executable, "-u", "scripts/lead_scraper.py", "--company", company], check=True)
            subprocess.run([sys.executable, "-u", "scripts/validator.py", "--company", company, "--user_id", args.user_id, "--job_id", args.job_id], check=True)
            
            # Safe automated staging file cleanup routine
            cleanup_files = [f".tmp/news_{company}.json", f".tmp/leads_{company}.json"]
            for file_path in cleanup_files:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Cleaned up staging asset: {file_path}")
        except subprocess.CalledProcessError as err:
            logger.error(f"Child module execution failure on company asset pipeline loop ({company}): {err}")
        finally:
            with lock:
                processed_count += 1
                end_weight = int(10 + ((processed_count / total_batch) * 85))
            update_server_status(args.job_id, f"Completed target asset: {company}", end_weight)

    # Parallel Execution: 3 concurrent workers to maximize throughput safely
    logger.info(f"Initiating concurrent local processing for {total_batch} companies with 3 workers.")
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        executor.map(process_company, clean_companies)

if __name__ == "__main__":
    main()