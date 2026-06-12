import os
import re
import json
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import quote_plus, urlparse

import pandas as pd
import feedparser
from dotenv import load_dotenv
from openai import OpenAI

from md_to_pdf import convert_markdown_to_pdf


DEFAULT_REFERENCE_SOURCES = [
    {"category": "Analytics & Data", "name": "Opta Analyst", "url": "https://theanalyst.com"},
    {"category": "Analytics & Data", "name": "StatsBomb", "url": "https://statsbomb.com/articles"},
    {"category": "Analytics & Data", "name": "Total Football Analysis", "url": "https://totalfootballanalysis.com"},
    {"category": "Analytics & Data", "name": "Coaches' Voice", "url": "https://www.coachesvoice.com"},
    {"category": "Analytics & Data", "name": "Hudl", "url": "https://www.hudl.com/blog"},
    {"category": "Analytics & Data", "name": "FIFA Project", "url": "https://fifaproject.vercel.app"},
    {"category": "Tactical & Football Analysis", "name": "Breaking The Lines", "url": "https://breakingthelines.com"},
    {"category": "Tactical & Football Analysis", "name": "Tifo Football", "url": "https://tifofootball.com"},
    {"category": "Tactical & Football Analysis", "name": "Spielverlagerung", "url": "https://spielverlagerung.com"},
    {"category": "Media & Tournament Coverage", "name": "The Athletic", "url": "https://www.nytimes.com/athletic/football"},
    {"category": "Media & Tournament Coverage", "name": "BBC Sport", "url": "https://www.bbc.com/sport/football"},
    {"category": "Media & Tournament Coverage", "name": "The Guardian", "url": "https://www.theguardian.com/football"},
    {"category": "Media & Tournament Coverage", "name": "ESPN", "url": "https://www.espn.com/soccer"},
    {"category": "Media & Tournament Coverage", "name": "FourFourTwo", "url": "https://www.fourfourtwo.com"},
    {"category": "Media & Tournament Coverage", "name": "GOAL", "url": "https://www.goal.com"},
    {"category": "Media & Tournament Coverage", "name": "Reuters", "url": "https://www.reuters.com/world-cup"},
]


def load_config(config_path: str = "match_config.json") -> dict:
    with open(config_path, "r", encoding="utf-8") as file:
        return json.load(file)


def load_reference_sources(
    csv_path: str = "reference_sources.csv",
) -> pd.DataFrame:
    if os.path.exists(csv_path):
        return pd.read_csv(csv_path).fillna("")

    return pd.DataFrame(DEFAULT_REFERENCE_SOURCES)


def source_url_to_domain(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return parsed.netloc.replace("www.", "")


def get_reference_domains(csv_path: str = "reference_sources.csv") -> list[str]:
    sources = load_reference_sources(csv_path)

    return [
        domain
        for domain in sources["url"].apply(source_url_to_domain).dropna().unique()
        if domain
    ]


def get_reference_urls(csv_path: str = "reference_sources.csv") -> list[str]:
    sources = load_reference_sources(csv_path)

    return [url for url in sources["url"].dropna().unique() if url]


def load_nvidia_client() -> OpenAI:
    load_dotenv()

    api_key = os.getenv("NVIDIA_API_KEY")

    if not api_key:
        raise ValueError("NVIDIA_API_KEY not found. Please add it to your .env file.")

    return OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=api_key,
    )


def clean_text(text: str) -> str:
    if not text:
        return ""

    text = re.sub(r"<.*?>", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def build_queries(team_a: str, team_b: str, match_date: str) -> list[str]:
    match = f"{team_a} {team_b}"

    return [
        f"{match} World Cup 2026 preview",
        f"{match} team news",
        f"{match} injuries",
        f"{match} predicted lineups",
        f"{match} tactical preview",
        f"{team_a} World Cup 2026 squad news",
        f"{team_b} World Cup 2026 squad news",
        f"{match} {match_date}",
    ]


def fetch_google_news(query: str, max_items: int = 10) -> list[dict]:
    url = (
        "https://news.google.com/rss/search?q="
        + quote_plus(query)
        + "&hl=en-US&gl=US&ceid=US:en"
    )

    feed = feedparser.parse(url)
    results = []

    for entry in feed.entries[:max_items]:
        results.append(
            {
                "query": query,
                "title": clean_text(entry.get("title", "")),
                "url": entry.get("link", ""),
                "published": entry.get("published", ""),
                "summary": clean_text(entry.get("summary", "")),
            }
        )

    return results


def parse_published_date(published: str):
    if not published:
        return None

    try:
        published_dt = parsedate_to_datetime(published)

        if published_dt.tzinfo is None:
            published_dt = published_dt.replace(tzinfo=timezone.utc)

        return published_dt.astimezone(timezone.utc)

    except Exception:
        return None


def filter_articles_by_date(
    df: pd.DataFrame,
    match_date: str,
    days_before: int = 30,
) -> pd.DataFrame:
    if df.empty:
        return df

    match_dt = datetime.strptime(match_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    start_dt = match_dt - timedelta(days=days_before)

    df = df.copy()
    df["published_dt"] = df["published"].apply(parse_published_date)

    df = df[
        (df["published_dt"].notna())
        & (df["published_dt"] >= start_dt)
        & (df["published_dt"] <= match_dt)
    ]

    return df


def is_reference_source(
    url: str,
    reference_domains: Optional[list[str]] = None,
) -> bool:
    domains = reference_domains or get_reference_domains()

    return any(domain in url for domain in domains)


def collect_news(
    team_a: str,
    team_b: str,
    match_date: str,
    max_per_query: int = 8,
    days_before_match: int = 30,
    reference_sources_path: str = "reference_sources.csv",
) -> pd.DataFrame:
    all_results = []
    reference_domains = get_reference_domains(reference_sources_path)

    for query in build_queries(team_a, team_b, match_date):
        print(f"Searching: {query}")
        all_results.extend(fetch_google_news(query, max_items=max_per_query))
        time.sleep(0.5)

    df = pd.DataFrame(all_results)

    if df.empty:
        return df

    df = df.drop_duplicates(subset=["title", "url"])

    df = filter_articles_by_date(
        df=df,
        match_date=match_date,
        days_before=days_before_match,
    )

    if df.empty:
        return df

    df["is_reference_source"] = df["url"].apply(
        lambda url: is_reference_source(url, reference_domains)
    )

    df = df.sort_values(
        by=["is_reference_source", "published_dt"],
        ascending=[False, False],
    )

    return df


def build_prompt(
    team_a: str,
    team_b: str,
    match_date: str,
    articles: pd.DataFrame,
) -> str:
    article_lines = []

    for _, row in articles.head(20).iterrows():
        article_lines.append(
            f"""
Source URL: {row["url"]}
Title: {row["title"]}
Published: {row["published"]}
Summary: {row["summary"]}
"""
        )

    articles_text = "\n---\n".join(article_lines)

    return f"""
You are helping a football analytics team prepare for a post-match World Cup analysis article.

The goal is NOT to write the article itself.

The goal is to help the analysts:
- identify possible match narratives
- anticipate tactical dynamics
- think about useful visualizations
- define what should be monitored during the game
- prepare hypotheses that can later be validated with event data

Match: {team_a} vs {team_b}
Match date: {match_date}

Use only the information from the collected article titles, summaries and URLs below.

Rules:
- Do not invent facts.
- If something is uncertain, explicitly say it is uncertain.
- Focus on football analysis usefulness.
- Do NOT use tables.
- Do NOT use HTML tags.
- Use headings and bullet points only.
- Keep the writing concise and practical.

Collected references:
{articles_text}

Generate a structured analysis preparation briefing with the following sections:

# Pre-Match Analysis Preparation — {team_a} vs {team_b}

## 1. Main Storylines
Main media and football narratives surrounding the match.

## 2. Team Context
Important squad, tactical, historical or psychological context.

## 3. Tactical Hypotheses
Possible tactical behaviors, structures, strengths, weaknesses, or expected game dynamics.

## 4. Key Matchups to Monitor
Interesting player battles, zones, or tactical interactions.

## 5. Match Dynamics to Monitor
What analysts should pay attention to during the match itself.

Examples:
- pressing intensity
- transition frequency
- wide overloads
- set-piece dependency
- possession asymmetry
- counter-attacking patterns

## 6. Data Questions to Investigate After the Match
Questions that can later be answered with event data.

Examples:
- Did Mexico dominate territory but create low xG?
- Was South Africa able to progress centrally?
- Which players generated the most value in transition?
- Which side controlled rest defense better?

## 7. Potential Visualizations
Suggest useful post-match visuals.

Examples:
- pass maps
- xG flow
- territory maps
- progressive pass networks
- shot maps
- defensive action heatmaps
- pressure maps
- transition sequence examples
- touch maps
- possession chains

For each visualization:
- explain WHY it could be useful
- explain WHAT football question it helps answer

## 8. Possible Post-Match Narratives
Possible article angles depending on how the match unfolds.

## 9. Most Relevant Sources
List only the most useful references.
"""


def generate_briefing(
    client: OpenAI,
    team_a: str,
    team_b: str,
    match_date: str,
    articles: pd.DataFrame,
) -> str:
    prompt = build_prompt(team_a, team_b, match_date, articles)

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a football analytics assistant helping a World Cup analysis team. "
                    "Focus on tactical context, storytelling, data analysis ideas, and practical insights. "
                    "Do not invent facts. Use only the provided references."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.7,
        top_p=1,
        max_tokens=3000,
        stream=False,
    )

    return response.choices[0].message.content


def safe_filename(text: str) -> str:
    return (
        text.lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("-", "_")
    )


def main() -> None:
    config = load_config()

    team_a = config["team_a"]
    team_b = config["team_b"]
    match_date = config["match_date"]
    output_dir = config.get("output_dir", "outputs")
    max_articles_per_query = config.get("max_articles_per_query", 8)
    days_before_match = config.get("days_before_match", 30)
    reference_sources_path = config.get("reference_sources_path", "reference_sources.csv")
    generate_pdf = config.get("generate_pdf", False)
    pdf_output_dir = config.get("pdf_output_dir", output_dir)

    os.makedirs(output_dir, exist_ok=True)

    client = load_nvidia_client()

    articles = collect_news(
        team_a=team_a,
        team_b=team_b,
        match_date=match_date,
        max_per_query=max_articles_per_query,
        days_before_match=days_before_match,
        reference_sources_path=reference_sources_path,
    )

    match_name = safe_filename(f"{team_a}_vs_{team_b}")

    csv_path = os.path.join(output_dir, f"{match_name}_articles.csv")
    md_path = os.path.join(output_dir, f"{match_name}_briefing.md")

    articles.to_csv(csv_path, index=False)
    print(f"Saved articles to: {csv_path}")

    if articles.empty:
        print("No articles found in the selected date range.")
        return

    briefing = generate_briefing(
        client=client,
        team_a=team_a,
        team_b=team_b,
        match_date=match_date,
        articles=articles,
    )

    with open(md_path, "w", encoding="utf-8") as file:
        file.write(briefing)

    print(f"Saved briefing to: {md_path}")

    if generate_pdf:
        pdf_path = os.path.join(pdf_output_dir, f"{match_name}_briefing.pdf")
        convert_markdown_to_pdf(md_path, pdf_path)
        print(f"Saved PDF to: {pdf_path}")


if __name__ == "__main__":
    main()
