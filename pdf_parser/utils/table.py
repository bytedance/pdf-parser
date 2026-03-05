# Copyright (C) 2025 ByteDance Inc
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

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
                r"\\\1", str(x).replace("\n", " ").replace("\r", "")
            )
            for x in row
        ]
        md_table.append("| " + " | ".join(cells) + " |")

    return "\n".join(md_table)
