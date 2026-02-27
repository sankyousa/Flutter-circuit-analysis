import sympy as sp, json, sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + '/../../')
import app as backend
s = sp.symbols('s')

def test_single_L_state():
    edges = [
        {'from':-1,'to':0,'type':'inductor','value':2},
        {'from':0,'to':-2,'type':'none'}
    ]
    mats = backend.build_state_matrices(
        json.dumps(edges, sort_keys=True),
        (-1,-2), (0,-2)
    )
    A,B,C,D = mats['A'], mats['B'], mats['C'], mats['D']

    assert A == sp.zeros(1)          # A=0
    assert sp.simplify(B[0]-1/2) == 0
    assert D == sp.Matrix([[1]])
