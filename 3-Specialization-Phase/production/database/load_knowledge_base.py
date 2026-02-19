"""
Customer Success Digital FTE — Knowledge Base Loader
=====================================================
Reads product-docs.md, splits into sections by Markdown headings,
generates OpenAI embeddings, and inserts into the knowledge_base table.

Replaces: KnowledgeBase class (TF-IDF, in-memory) from incubation prototype.
Target:   knowledge_base table with pgvector embedding(1536)

Usage:
    # Load all sections (first run or full refresh)
    python load_knowledge_base.py

    # Force reload (drop existing, re-embed everything)
    python load_knowledge_base.py --force

    # Custom docs path
    python load_knowledge_base.py --docs /path/to/product-docs.md

    # Dry run (parse and show sections without inserting)
    python load_knowledge_base.py --dry-run

Environment variables:
    DATABASE_URL   — PostgreSQL connection string (required)
    OPENAI_API_KEY — OpenAI API key for embeddings (required)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

import asyncpg

# ── Constants ────────────────────────────────────────────────────────────

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
BATCH_SIZE = 20  # OpenAI supports up to 2048 inputs per batch; we use small batches for reliability
DEFAULT_DOCS_PATH = Path(__file__).resolve().parent.parent.parent.parent / "1-Incubation-Phase" / "context" / "product-docs.md"


# ── Section Parser ───────────────────────────────────────────────────────


def parse_markdown_sections(text: str, source: str = "product-docs.md") -> list[dict]:
    """Parse a Markdown document into titled sections.

    Splits on ## and ### headings. Each section includes:
    - title: The heading text (e.g., "Task Management")
    - content: The body text under that heading (until the next heading)
    - category: The parent ## heading (e.g., "Core Features")
    - source: File reference (e.g., "product-docs.md#task-management")
    - metadata: word_count, heading_level, parent_section

    Skips the Table of Contents and the top-level # heading.
    """
    sections = []
    lines = text.split("\n")

    current_h2 = None  # Parent category (## level)
    current_title = None
    current_level = 0
    current_lines = []
    start_line = 0

    for i, line in enumerate(lines):
        # Match ## or ### headings
        heading_match = re.match(r"^(#{2,3})\s+(.+)$", line)

        if heading_match:
            # Save the previous section (if any)
            if current_title and current_title != "Table of Contents":
                body = "\n".join(current_lines).strip()
                if body:  # Skip empty sections
                    slug = re.sub(r"[^a-z0-9]+", "-", current_title.lower()).strip("-")
                    word_count = len(body.split())
                    sections.append({
                        "title": current_title,
                        "content": body,
                        "category": current_h2 or "General",
                        "source": f"{source}#{slug}",
                        "metadata": {
                            "word_count": word_count,
                            "heading_level": current_level,
                            "parent_section": current_h2,
                        },
                    })

            # Start new section
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()

            if level == 2:
                current_h2 = title

            current_title = title
            current_level = level
            current_lines = []
            start_line = i + 1
        else:
            current_lines.append(line)

    # Don't forget the last section
    if current_title and current_title != "Table of Contents":
        body = "\n".join(current_lines).strip()
        if body:
            slug = re.sub(r"[^a-z0-9]+", "-", current_title.lower()).strip("-")
            word_count = len(body.split())
            sections.append({
                "title": current_title,
                "content": body,
                "category": current_h2 or "General",
                "source": f"{source}#{slug}",
                "metadata": {
                    "word_count": word_count,
                    "heading_level": current_level,
                    "parent_section": current_h2,
                },
            })

    return sections


# ── Embedding Generation ─────────────────────────────────────────────────


async def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a batch of texts using OpenAI API.

    Uses text-embedding-3-small (1536 dimensions) for cost-effective
    semantic search. Costs ~$0.02 per 1M tokens.

    Args:
        texts: List of text strings to embed.

    Returns:
        List of embedding vectors (each 1536 floats).
    """
    from openai import AsyncOpenAI

    client = AsyncOpenAI()

    all_embeddings = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        response = await client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch,
        )
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)

        # Rate limit courtesy: small delay between batches
        if i + BATCH_SIZE < len(texts):
            await asyncio.sleep(0.5)

    return all_embeddings


# ── Database Operations ──────────────────────────────────────────────────


async def clear_knowledge_base(pool: asyncpg.Pool) -> int:
    """Delete all existing knowledge base entries. Returns count deleted."""
    result = await pool.fetchval("SELECT COUNT(*) FROM knowledge_base")
    await pool.execute("DELETE FROM knowledge_base")
    return result


async def insert_sections(
    pool: asyncpg.Pool,
    sections: list[dict],
    embeddings: list[list[float]],
) -> int:
    """Insert sections with embeddings into knowledge_base table.

    Returns: Number of rows inserted.
    """
    import json

    inserted = 0
    async with pool.acquire() as conn:
        for section, embedding in zip(sections, embeddings):
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
            await conn.execute(
                """
                INSERT INTO knowledge_base (title, content, category, embedding, source, metadata)
                VALUES ($1, $2, $3, $4::vector, $5, $6::jsonb)
                """,
                section["title"],
                section["content"],
                section["category"],
                embedding_str,
                section["source"],
                json.dumps(section["metadata"]),
            )
            inserted += 1

    return inserted


async def create_vector_index(pool: asyncpg.Pool) -> None:
    """Create IVFFlat index for approximate nearest neighbor search.

    Only useful when the table has data. For small datasets (< 1000 rows),
    exact search without index is fine, but we create it anyway for
    production readiness.

    Lists parameter: sqrt(row_count) is a good starting point.
    For ~40 sections: lists=10 is reasonable.
    """
    row_count = await pool.fetchval("SELECT COUNT(*) FROM knowledge_base WHERE embedding IS NOT NULL")

    if row_count == 0:
        print("  No rows with embeddings found — skipping index creation.")
        return

    # Calculate lists parameter (sqrt of row count, minimum 1)
    lists = max(1, min(100, int(row_count ** 0.5)))

    # Drop existing index if any
    await pool.execute("DROP INDEX IF EXISTS idx_kb_embedding")

    # Create IVFFlat index
    await pool.execute(
        f"""
        CREATE INDEX idx_kb_embedding ON knowledge_base
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = {lists})
        """
    )
    print(f"  Created IVFFlat index with lists={lists} for {row_count} rows.")


# ── Main ─────────────────────────────────────────────────────────────────


async def main(
    docs_path: Path,
    database_url: str,
    force: bool = False,
    dry_run: bool = False,
) -> None:
    """Load product documentation into the knowledge base.

    Steps:
        1. Read and parse product-docs.md into sections
        2. Generate OpenAI embeddings for each section
        3. Insert sections + embeddings into knowledge_base table
        4. Create IVFFlat vector index
    """
    print("=" * 60)
    print("Knowledge Base Loader")
    print("=" * 60)

    # ── Step 1: Parse document ───────────────────────────────────────
    print(f"\n[1/4] Reading {docs_path.name}...")

    if not docs_path.exists():
        print(f"  ERROR: File not found: {docs_path}")
        sys.exit(1)

    text = docs_path.read_text(encoding="utf-8")
    sections = parse_markdown_sections(text, source=docs_path.name)

    print(f"  Parsed {len(sections)} sections:")
    categories = {}
    for s in sections:
        cat = s["category"]
        categories[cat] = categories.get(cat, 0) + 1
    for cat, count in categories.items():
        print(f"    {cat}: {count} sections")

    total_words = sum(s["metadata"]["word_count"] for s in sections)
    print(f"  Total words: {total_words:,}")

    if dry_run:
        print("\n[DRY RUN] Sections that would be loaded:")
        for i, s in enumerate(sections, 1):
            print(f"  {i:2}. [{s['category']}] {s['title']} ({s['metadata']['word_count']} words)")
        print("\nDry run complete. No data was modified.")
        return

    # ── Step 2: Connect to database ──────────────────────────────────
    print(f"\n[2/4] Connecting to database...")
    pool = await asyncpg.create_pool(dsn=database_url, min_size=2, max_size=5)

    try:
        # Check if knowledge_base already has data
        existing_count = await pool.fetchval("SELECT COUNT(*) FROM knowledge_base")
        print(f"  Existing rows: {existing_count}")

        if existing_count > 0 and not force:
            print("  Knowledge base already populated. Use --force to reload.")
            print("  Exiting without changes.")
            return

        if existing_count > 0 and force:
            deleted = await clear_knowledge_base(pool)
            print(f"  Cleared {deleted} existing rows (--force).")

        # ── Step 3: Generate embeddings ──────────────────────────────
        print(f"\n[3/4] Generating embeddings with {EMBEDDING_MODEL}...")
        start_time = time.time()

        # Combine title + content for richer embeddings
        texts_to_embed = [
            f"{s['title']}\n\n{s['content']}" for s in sections
        ]

        embeddings = await generate_embeddings(texts_to_embed)

        elapsed = time.time() - start_time
        print(f"  Generated {len(embeddings)} embeddings in {elapsed:.1f}s")
        print(f"  Dimensions: {len(embeddings[0]) if embeddings else 0}")

        # ── Step 4: Insert into database ─────────────────────────────
        print(f"\n[4/4] Inserting into knowledge_base table...")
        inserted = await insert_sections(pool, sections, embeddings)
        print(f"  Inserted {inserted} rows.")

        # Create vector index
        print("  Creating vector index...")
        await create_vector_index(pool)

        # Summary
        final_count = await pool.fetchval("SELECT COUNT(*) FROM knowledge_base")
        print(f"\n{'=' * 60}")
        print(f"Knowledge base loaded successfully!")
        print(f"  Total rows: {final_count}")
        print(f"  Embedding model: {EMBEDDING_MODEL}")
        print(f"  Embedding dimensions: {EMBEDDING_DIMENSIONS}")
        print(f"{'=' * 60}")

    finally:
        await pool.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Load product documentation into the knowledge base with vector embeddings."
    )
    parser.add_argument(
        "--docs",
        type=Path,
        default=DEFAULT_DOCS_PATH,
        help=f"Path to product-docs.md (default: {DEFAULT_DOCS_PATH})",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=os.environ.get("DATABASE_URL", "postgresql://localhost/customer_success"),
        help="PostgreSQL connection string (default: $DATABASE_URL or postgresql://localhost/customer_success)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reload: clear existing data and re-embed everything",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and display sections without inserting into database",
    )

    args = parser.parse_args()

    asyncio.run(main(
        docs_path=args.docs,
        database_url=args.database_url,
        force=args.force,
        dry_run=args.dry_run,
    ))
