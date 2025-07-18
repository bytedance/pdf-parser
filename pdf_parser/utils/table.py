import re

_markdown_table_chars_re = re.compile(r"([\\|])")


def table_markdown(rows: list[list[str]]) -> str:
    """Create markdown table"""
    if not rows:
        return ""

    md_table = []
    md_table.append("| " + " | ".join(rows[0]) + " |")
    md_table.append("| " + " | ".join(["---"] * len(rows[0])) + " |")

    for row in rows[1:]:
        cells = [
            # escape or filter some characters for markdown table
            _markdown_table_chars_re.sub(
                r"\\\1", x.replace("\n", " ").replace("\r", "")
            )
            for x in row
        ]
        md_table.append("| " + " | ".join(cells) + " |")

    return "\n".join(md_table)
