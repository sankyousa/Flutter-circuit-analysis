import sympy as sp, json, sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + '/../../')
import app as backend

def test_rlc_series_manual():
    edges = [
        {'from':-1,'to':1000,'type':'resistor','value':1},
        {'from':1000,'to':0,'type':'capacitor','value':1},
        {'from':0,'to':1001,'type':'resistor','value':1},
        {'from':1001,'to':1,'type':'capacitor','value':1},
        {'from':1,'to':1002,'type':'resistor','value':1},
        {'from':1002,'to':-2,'type':'inductor','value':1}
    ]
    req = {
        'edges': edges,
        'source': [-1,-2],
        'output': [0,1],
        'isAC':   True,
        'voltageValue': 1
    }
    resp = backend.calculate_circuit_internal(req)
    H = sp.simplify(sp.sympify(resp['tf']))

    s = sp.symbols('s')
    H_theory = (s+1)/(s**2 + 3*s + 2)
    assert sp.simplify(H - H_theory) == 0
