import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
from openai import OpenAI

from briefing import (
    fetch_google_news,
    is_reference_source,
    load_nvidia_client,
    parse_published_date,
    safe_filename,
)

POST_MATCH_KEYWORDS = [
    "after",
    "analysis",
    "as it happened",
    "final score",
    "full time",
    "full-time",
    "highlights",
    "match report",
    "match stats",
    "player ratings",
    "post match",
    "post-match",
    "reaction",
    "recap",
    "report",
    "result",
    "takeaways",
    "talking points",
    "what we learned",
]

PRE_MATCH_KEYWORDS = [
    "bet builder",
    "betting",
    "before opening",
    "faces pressure",
    "how to watch",
    "lineups",
    "line-ups",
    "odds",
    "pick",
    "picks",
    "prediction",
    "predictions",
    "preview",
    "press conference held before",
    "ready to test",
    "seeks to",
    "sign up offer",
    "start time",
    "streaming",
    "team news",
    "tv channel",
]


def load_config(config_path: str = "post_match_config.json") -> dict:
    with open(config_path, "r", encoding="utf-8") as file:
        return json.load(file)


def build_post_match_queries(
    team_a: str,
    team_b: str,
    match_date: str,
    score: Optional[str] = None,
) -> list[str]:
    match = f"{team_a} {team_b}"
    score_text = f" {score}" if score else ""

    return [
        f"{match}{score_text} World Cup 2026 result",
        f"{match}{score_text} match report",
        f"{match}{score_text} recap",
        f"{match} highlights",
        f"{match} reaction",
        f"{match} tactical analysis",
        f"{match} player ratings",
        f"{match} stats xG",
        f"{match} post-match analysis {match_date}",
    ]


def parse_post_match_start(
    match_date: str,
    match_datetime_utc: Optional[str] = None,
) -> datetime:
    if not match_datetime_utc:
        return datetime.strptime(match_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    normalized = match_datetime_utc.replace("Z", "+00:00")
    start_dt = datetime.fromisoformat(normalized)

    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)

    return start_dt.astimezone(timezone.utc)


def score_appears_in_text(score: Optional[str], text: str) -> bool:
    if not score:
        return False

    score_lower = score.lower().strip()
    if score_lower and score_lower in text:
        return True

    score_numbers = " ".join(re.findall(r"\d+", score_lower))
    text_numbers = " ".join(re.findall(r"\d+", text))

    return bool(score_numbers and score_numbers in text_numbers)


def is_likely_post_match_article(
    row: pd.Series,
    match_year: str,
    score: Optional[str] = None,
) -> bool:
    text = f"{row.get('title', '')} {row.get('summary', '')}".lower()

    if match_year not in text and not score_appears_in_text(score, text):
        return False

    if any(keyword in text for keyword in PRE_MATCH_KEYWORDS):
        return False

    if score_appears_in_text(score, text):
        return True

    return any(keyword in text for keyword in POST_MATCH_KEYWORDS)


def filter_articles_after_match(
    df: pd.DataFrame,
    match_date: str,
    match_datetime_utc: Optional[str] = None,
    days_after: int = 3,
    score: Optional[str] = None,
) -> pd.DataFrame:
    if df.empty:
        return df

    match_dt = parse_post_match_start(match_date, match_datetime_utc)
    end_dt = match_dt + timedelta(days=days_after)

    df = df.copy()
    df["published_dt"] = df["published"].apply(parse_published_date)

    df = df[
        (df["published_dt"].notna())
        & (df["published_dt"] >= match_dt)
        & (df["published_dt"] <= end_dt)
    ]

    if df.empty:
        return df

    match_year = match_date[:4]
    df = df[df.apply(is_likely_post_match_article, axis=1, args=(match_year, score))]

    return df


def collect_post_match_news(
    team_a: str,
    team_b: str,
    match_date: str,
    score: Optional[str] = None,
    match_datetime_utc: Optional[str] = None,
    max_per_query: int = 8,
    days_after_match: int = 3,
) -> pd.DataFrame:
    all_results = []

    for query in build_post_match_queries(team_a, team_b, match_date, score):
        print(f"Searching: {query}")
        all_results.extend(fetch_google_news(query, max_items=max_per_query))
        time.sleep(0.5)

    df = pd.DataFrame(all_results)

    if df.empty:
        return df

    df = df.drop_duplicates(subset=["title", "url"])
    df = filter_articles_after_match(
        df=df,
        match_date=match_date,
        match_datetime_utc=match_datetime_utc,
        days_after=days_after_match,
        score=score,
    )

    if df.empty:
        return df

    df["is_reference_source"] = df["url"].apply(is_reference_source)

    df = df.sort_values(
        by=["is_reference_source", "published_dt"],
        ascending=[False, False],
    )

    return df


def build_post_match_prompt(
    team_a: str,
    team_b: str,
    match_date: str,
    articles: pd.DataFrame,
    score: Optional[str] = None,
) -> str:
    article_lines = []

    for _, row in articles.head(25).iterrows():
        article_lines.append(
            f"""
Source URL: {row["url"]}
Title: {row["title"]}
Published: {row["published"]}
Summary: {row["summary"]}
"""
        )

    articles_text = "\n---\n".join(article_lines)
    score_line = f"Final score: {score}" if score else "Final score: not provided"

    return f"""
You are helping a football analytics team prepare a post-match World Cup analysis article.

The goal is NOT to write the final article.

The goal is to help analysts:
- identify the strongest post-match narratives
- separate confirmed match facts from media interpretation
- frame tactical explanations that can be checked with event data
- suggest useful visualizations
- prepare concise article angles for editorial discussion

Match: {team_a} vs {team_b}
Match date: {match_date}
{score_line}

Use only the information from the collected article titles, summaries and URLs below.

Rules:
- Do not invent facts.
- If a match detail is not present in the references, say it is not confirmed by the collected sources.
- Be especially careful with goals, cards, injuries, substitutions, and tactical setups.
- Focus on football analysis usefulness.
- Do NOT use tables.
- Do NOT use HTML tags.
- Use headings and bullet points only.
- Keep the writing concise and practical.

Collected references:
{articles_text}

Generate a structured post-match briefing with the following sections:

# Post-Match Analysis Briefing — {team_a} vs {team_b}

## 1. Confirmed Match Facts
Only facts supported by the collected references.

## 2. Main Post-Match Storylines
The strongest narratives emerging from reports, reactions, and analysis.

## 3. Tactical Reading
Likely tactical explanations or patterns mentioned or implied by the sources.
Clearly mark anything that still needs validation with data.

## 4. Key Turning Points to Review
Moments, phases, decisions, goals, or substitutions analysts should inspect.

## 5. Player and Unit Focus
Players, position groups, or team units that appear important to the match story.

## 6. Data Checks Needed
Questions that should be validated with event data, tracking data, or video.

Examples:
- xG and shot quality by phase
- field tilt and territory control
- pass networks and progression routes
- pressure regains and counter-pressing
- transition shots
- set-piece shot value

## 7. Recommended Visualizations
For each visualization:
- explain WHY it is useful
- explain WHAT question it helps answer

## 8. Article Angles
Concise possible angles for a post-match analysis article.

## 9. Source Notes
List the most useful references and any important uncertainty or source gaps.
"""


def generate_post_match_briefing(
    client: OpenAI,
    team_a: str,
    team_b: str,
    match_date: str,
    articles: pd.DataFrame,
    score: Optional[str] = None,
) -> str:
    prompt = build_post_match_prompt(team_a, team_b, match_date, articles, score)

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a football analytics assistant helping a World Cup analysis team. "
                    "Focus on post-match tactical context, storytelling, data checks, and practical insights. "
                    "Do not invent facts. Use only the provided references."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.5,
        top_p=1,
        max_tokens=3000,
        stream=False,
    )

    return response.choices[0].message.content


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "post_match_config.json"
    config = load_config(config_path)

    team_a = config["team_a"]
    team_b = config["team_b"]
    match_date = config["match_date"]
    score = config.get("score")
    match_datetime_utc = config.get("match_datetime_utc")
    output_dir = config.get("output_dir", "outputs")
    max_articles_per_query = config.get("max_articles_per_query", 8)
    days_after_match = config.get("days_after_match", 3)

    os.makedirs(output_dir, exist_ok=True)

    articles = collect_post_match_news(
        team_a=team_a,
        team_b=team_b,
        match_date=match_date,
        score=score,
        match_datetime_utc=match_datetime_utc,
        max_per_query=max_articles_per_query,
        days_after_match=days_after_match,
    )

    match_name = safe_filename(f"{team_a}_vs_{team_b}")

    csv_path = os.path.join(output_dir, f"{match_name}_post_match_articles.csv")
    md_path = os.path.join(output_dir, f"{match_name}_post_match_briefing.md")

    articles.to_csv(csv_path, index=False)
    print(f"Saved articles to: {csv_path}")

    if articles.empty:
        print(
            "Nenhum artigo pós-jogo foi encontrado no período selecionado. "
            "A API não será chamada e nenhum briefing será gerado."
        )
        return

    client = load_nvidia_client()

    briefing = generate_post_match_briefing(
        client=client,
        team_a=team_a,
        team_b=team_b,
        match_date=match_date,
        articles=articles,
        score=score,
    )

    with open(md_path, "w", encoding="utf-8") as file:
        file.write(briefing)

    print(f"Saved briefing to: {md_path}")


if __name__ == "__main__":
    main()
