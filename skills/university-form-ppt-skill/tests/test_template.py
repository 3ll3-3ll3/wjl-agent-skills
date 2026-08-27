from pathlib import Path
import hashlib
import zipfile
import pytest

STUDENT = Path("assets/certificate_template.pptx")
FACULTY = Path("assets/teacher_certificate_template.pptx")
EXPECTED_SHA = {
    STUDENT: "3dfa888b44be1d1219bf07d6600f3f76ef20b13488d6b24ca5c09333102ab4e2",
    FACULTY: "c0f315f563e96b4cd9696f8a6d9bd4f61efd5a9c241c34a1a07e880c3c5b47a9",
}


def require_current_binary(path: Path) -> None:
    if not path.exists():
        pytest.fail(f"current template is missing: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == EXPECTED_SHA[path], f"template SHA mismatch: {path}"


def slide_xml(path: Path) -> str:
    require_current_binary(path)
    with zipfile.ZipFile(path) as zf:
        return "\n".join(
            zf.read(name).decode("utf-8", errors="ignore")
            for name in zf.namelist()
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        )


def test_student_template_placeholders():
    xml = slide_xml(STUDENT)
    assert xml.count("{{name}}") == 1
    assert xml.count("{{student_id}}") == 1
    assert xml.count("{{facultyid}}") == 0
    assert xml.count("{{school_name}}") == 2


def test_faculty_template_placeholders():
    xml = slide_xml(FACULTY)
    assert xml.count("{{name}}") == 1
    assert xml.count("{{student_id}}") == 0
    assert xml.count("{{facultyid}}") == 1
    assert xml.count("{{school_name}}") == 2
