import io

from app.services.report_service import ReportService, safe_csv_cell


def test_formula_injection_is_escaped() -> None:
    assert safe_csv_cell("=CMD()") == "'=CMD()"
    assert safe_csv_cell("@SUM(A1)") == "'@SUM(A1)"
    assert safe_csv_cell("normal") == "normal"


def test_report_export() -> None:
    output = io.StringIO()
    ReportService.export_csv({"delivered": 10}, output)
    assert output.getvalue().splitlines() == ["metric,value", "delivered,10"]

