import os
import sys
import types
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Mock pyodbc przed importem app.py.
# Dzięki temu testy nie wymagają zainstalowanego unixODBC ani sterowników SQL Server.
fake_pyodbc = types.ModuleType("pyodbc")

def fake_connect(*args, **kwargs):
    raise RuntimeError("pyodbc.connect nie powinien być używany w testach jednostkowych")

fake_pyodbc.connect = fake_connect
sys.modules["pyodbc"] = fake_pyodbc

import app as liga_app
