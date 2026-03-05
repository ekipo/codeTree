import pytest
from pathlib import Path

@pytest.fixture
def sample_repo(tmp_path):
    """Creates a minimal fake Python repo for testing."""
    (tmp_path / "calculator.py").write_text("""\
class Calculator:
    def add(self, a, b):
        return a + b

    def divide(self, a, b):
        if b == 0:
            raise ValueError("cannot divide by zero")
        return a / b

def helper():
    calc = Calculator()
    return calc.add(1, 2)
""")
    (tmp_path / "main.py").write_text("""\
from calculator import Calculator

def run():
    calc = Calculator()
    result = calc.divide(10, 2)
    return result
""")
    return tmp_path
