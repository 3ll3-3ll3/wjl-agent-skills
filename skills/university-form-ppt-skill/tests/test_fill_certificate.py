from pathlib import Path
import hashlib
import zipfile
import pytest

from scripts.fill_certificate import fill

STUDENT = Path("assets/certificate_template.pptx")
FACULTY = Path("assets/teacher_certificate_template.pptx")
EXPECTED_SHA = {
    STUDENT: "3dfa888b44be1d1219bf07d6600f3f76ef20b13488d6b24ca5c09333102ab4e2",
    FACULTY: "c0f315f563e96b4cd9696f8a6d9bd4f61efd5a9c241c34a1a07e880c3c5b47a9",
}


def require_current_binary(path: Path) -> None:
    if not path.exists():
        pytest.fail(f"current template is missing: {path}")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == EXPECTED_SHA[path]


def all_slide_xml(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        return "\n".join(
            zf.read(n).decode("utf-8", errors="ignore")
            for n in zf.namelist()
            if n.startswith("ppt/slides/slide") and n.endswith(".xml")
        )


def test_student_fill(tmp_path: Path):
    require_current_binary(STUDENT)
    out = tmp_path / "student.pptx"
    fill(STUDENT, out, "student", "Li An", "1234567", "Soochow University")
    xml = all_slide_xml(out)
    assert "{{student_id}}" not in xml
    assert "1234567" in xml


def test_faculty_fill(tmp_path: Path):
    require_current_binary(FACULTY)
    out = tmp_path / "faculty.pptx"
    fill(FACULTY, out, "faculty", "Li An", "1234567", "Soochow University")
    xml = all_slide_xml(out)
    assert "{{facultyid}}" not in xml
    assert "1234567" in xml
