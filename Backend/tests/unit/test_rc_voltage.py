import sympy as sp, json, sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + '/../../')
import app as backend

def test_rc_voltage_divider():
    # Vin -> R(1) -> node0 -> C(1F) -> GND
    edges = [
        {'from':-1,'to':0,'type':'resistor','value':1},
        {'from':0,'to':-2,'type':'capacitor','value':1}
    ]
    req = {
        'edges': edges,
        'source': [-1,-2],
        'output': [0,-2],
        'isAC':   True,
        'voltageValue': 1
    }
    resp = backend.calculate_circuit_internal(req)
    H = sp.simplify(sp.sympify(resp['tf']))
    s = sp.symbols('s')
    H_theory = 1/(s+1)
    assert sp.simplify(H - H_theory) == 0
