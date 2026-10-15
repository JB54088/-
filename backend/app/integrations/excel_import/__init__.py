"""ABC Excel import pipeline.

The importer is intentionally independent from the retired data-pool client:
an administrator uploads a workbook, previews the normalized facts, and then
confirms a transactional import into PostgreSQL.
"""

from .parser import ExcelParseError, parse_excel
from .service import confirm_import, preview_import

__all__ = ["ExcelParseError", "confirm_import", "parse_excel", "preview_import"]
