import sympy as sp, importlib, sys, os

# 让 tests 找到 app 模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + '/../../')
import app as backend
s = sp.symbols('s')

def test_resistor():
    assert backend.component_impedance('resistor', 2, True) == 2

def test_capacitor():
    Zc = backend.component_impedance('capacitor', 5, True)
    assert sp.simplify(Zc - 1/(5*s)) == 0

def test_inductor():
    Zl = backend.component_impedance('inductor', 3, True)
    assert sp.simplify(Zl - 3*s) == 0
