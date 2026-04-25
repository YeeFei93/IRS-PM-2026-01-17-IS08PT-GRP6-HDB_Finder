import os
import re
import json
import requests
import pandas as pd
from bs4 import BeautifulSoup
from openai import OpenAI

URL = "https://en.wikipedia.org/wiki/List_of_shopping_malls_in_Singapore"


def fetch_page_text(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Get the whole page text
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n{2,}", "\n", text)
    return text


def extract_bottom_box_text(page_text: str) -> str:
    """
    Try to isolate the bottom navbox area from the page text.
    We look for the section that starts with 'Shopping malls in Singapore'
    near the bottom and stop before 'Retrieved from'.
    """
    start_markers = [
        "Shopping malls in Singapore",
    ]
    end_markers = [
        'Retrieved from "https://en.wikipedia.org/',
        "Categories:",
        "This page was last edited",
    ]

    start_idx = -1
    for marker in start_markers:
        idx = page_text.rfind(marker)
        if idx != -1:
            start_idx = idx
            break

    if start_idx == -1:
        raise RuntimeError("Could not find the bottom 'Shopping malls in Singapore' box text.")

    tail = page_text[start_idx:]

    end_idx = len(tail)
    for marker in end_markers:
        idx = tail.find(marker)
        if idx != -1:
            end_idx = min(end_idx, idx)

    navbox_text = tail[:end_idx].strip()

    if len(navbox_text) < 100:
        raise RuntimeError("Bottom box text looks too short. Wikipedia page text may have changed.")

    return navbox_text


def extract_malls_with_ai(navbox_text: str, model: str = "gpt-5.4") -> dict:
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    prompt = f"""
You are extracting shopping mall names from a Wikipedia navbox.

Task:
- Read the text below.
- Extract the mall names from the bottom "Shopping malls in Singapore" box only.
- Return strict JSON only.
- Use this exact schema:

{{
  "current": ["mall 1", "mall 2"],
  "hdb_malls": ["mall 1", "mall 2"],
  "multiplexes": ["mall 1", "mall 2"],
  "defunct": ["mall 1", "mall 2"]
}}

Rules:
- Deduplicate names.
- Keep the exact mall names as written.
- Ignore helper text like "v", "t", "e", "Image", "Singapore", "Only shopping malls with their own respective articles are listed here", and other non-mall labels.
- If a section is missing, return an empty list for that key.
- Return JSON only, no markdown.

TEXT:
{navbox_text}
""".strip()

    response = client.responses.create(
        model=model,
        input=prompt
    )

    output = response.output_text.strip()

    try:
        data = json.loads(output)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            "AI response was not valid JSON. Print response.output_text to inspect it."
        ) from e

    expected_keys = {"current", "hdb_malls", "multiplexes", "defunct"}
    missing = expected_keys - set(data.keys())
    if missing:
        raise RuntimeError(f"Missing keys in AI output: {missing}")

    return data


def save_to_csv(data: dict, filename: str = "singapore_malls_from_ai.csv") -> pd.DataFrame:
    rows = []

    for category, malls in data.items():
        for mall in malls:
            rows.append({
                "category": category,
                "mall_name": mall
            })

    df = pd.DataFrame(rows).drop_duplicates().reset_index(drop=True)
    df.to_csv(filename, index=False, encoding="utf-8-sig")
    return df


if __name__ == "__main__":
    # 1) Fetch the page
    page_text = fetch_page_text(URL)

    # 2) Isolate the bottom box text
    navbox_text = extract_bottom_box_text(page_text)

    print("=== Extracted navbox text preview ===")
    print(navbox_text[:2000])
    print("\n=== End preview ===\n")

    # 3) Use AI to identify the malls
    data = extract_malls_with_ai(navbox_text)

    # 4) Save results
    df = save_to_csv(data)

    print(df.to_string(index=False))
    print(f"\nSaved {len(df)} rows to singapore_malls_from_ai.csv")