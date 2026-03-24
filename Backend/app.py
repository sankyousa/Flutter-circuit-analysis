from flask import Flask, request, jsonify
from flask_cors import CORS
import sympy as sp
from sympy import symbols, Eq, solve, simplify, oo, factor, latex, Matrix, zeros, eye, expand
from sympy.abc import s
import functools, time, copy
import io, base64, json, math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import itertools
from sympy.matrices.common import NonInvertibleMatrixError
from collections import defaultdict

try:
    from control import tf, bode_plot, rlocus, margin 
except ImportError:
    print("Warning: python-control library not installed")
    tf = bode_plot = rlocus = None

EPS_NUM = 1e-12
app = Flask(__name__)
CORS(app)

def _cleanup_and_get_coeffs(expr, precision=4, zero_threshold=1e-9):
    if expr.is_zero: return [0.0]
    try:
        p = sp.Poly(sp.expand(expr), s)
        coeffs = p.all_coeffs()
        cleaned_coeffs = []
        for c in coeffs:
            c_float = float(c.evalf())
            if abs(c_float) < zero_threshold: cleaned_coeffs.append(0.0)
            else: cleaned_coeffs.append(round(c_float, precision))
        first_nonzero_idx = next((i for i, c in enumerate(cleaned_coeffs) if c != 0.0), -1)
        return cleaned_coeffs[first_nonzero_idx:] if first_nonzero_idx != -1 else [0.0]
    except Exception: return []

def _coeffs_to_latex(num_coeffs, den_coeffs, precision=4):
    # ── Normalize: divide both num and den by the leading den coefficient
    #    so that the denominator becomes monic (leading coeff = 1).
    #    This removes huge coefficients caused by wire conductance (1e9).
    if den_coeffs and den_coeffs[0] != 0:
        lead = den_coeffs[0]
        num_coeffs = [c / lead for c in num_coeffs]
        den_coeffs = [c / lead for c in den_coeffs]
    # ── Re-round after normalization to clean up floating-point noise
    num_coeffs = [round(c, precision) for c in num_coeffs]
    den_coeffs = [round(c, precision) for c in den_coeffs]

    def _poly_str(coeffs):
        if not coeffs: return '0'
        def _fmt(c):
            ac = abs(c)
            if ac == 0: return '0'
            # Use engineering notation for very large or very small BEFORE rounding
            if ac >= 1000 or (ac > 0 and ac < 0.001):
                exp = int(math.floor(math.log10(ac)))
                mantissa = ac / (10 ** exp)
                mantissa = round(mantissa, precision)
                if mantissa == int(mantissa):
                    return f'{int(mantissa)} \\times 10^{{{exp}}}'
                return f'{mantissa:.{precision}g} \\times 10^{{{exp}}}'
            c = round(c, precision)
            if c == 0: return '0'
            if c == int(c): return str(int(c))
            return f'{c:.{precision}f}'.rstrip('0').rstrip('.')
        terms = []
        degree = len(coeffs) - 1
        for i, c in enumerate(coeffs):
            power = degree - i
            c_rounded = round(c, precision)
            if c_rounded == 0: continue
            c_str = _fmt(abs(c_rounded))
            sign_neg = c_rounded < 0
            if power == 0:
                terms.append(('-' + c_str) if sign_neg else c_str)
            elif power == 1:
                if c_str == '1': body = 's'
                else: body = c_str + 's'
                terms.append(('-' + body) if sign_neg else body)
            else:
                if c_str == '1': body = f's^{{{power}}}'
                else: body = c_str + f's^{{{power}}}'
                terms.append(('-' + body) if sign_neg else body)
        if not terms: return '0'
        result = terms[0]
        for t in terms[1:]:
            if t.startswith('-'):
                result += ' - ' + t[1:]
            else:
                result += ' + ' + t
        return result
    num_str = _poly_str(num_coeffs)
    den_str = _poly_str(den_coeffs)
    if den_str == '1' or den_str == '1.0':
        return num_str
    return r'\frac{' + num_str + '}{' + den_str + '}'
    
def _split_edges(edges):
    Rs, Ls, Cs, wires, mosfets, diodes = [], [], [], [], [], []
    for e in edges:
        t = e.get('type')
        if t == 'resistor': Rs.append(e)
        elif t == 'inductor': Ls.append(e)
        elif t == 'capacitor': Cs.append(e)
        elif t == 'none': wires.append(e)
        elif t == 'mosfet': mosfets.append(e)
        elif t == 'diode': diodes.append(e)
    return Rs, Ls, Cs, wires, mosfets, diodes

def _roots_from_coeffs(coeffs):
    if not coeffs or (len(coeffs) == 1 and coeffs[0] == 0): return []
    try:
        roots = np.roots(coeffs)
        out = []
        for z in roots:
            rp, ip = z.real, z.imag
            if abs(ip) < 1e-8: out.append(f"{rp:.5f}")
            else: out.append(f"{rp:.5f}{ip:+.5f}j")
        return out
    except Exception: return []
    
def fig_to_base_64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('ascii')

def judge_mosfet_on(edge: dict, node_voltages: dict, eps: float = 1e-8):
    control_info = edge.get('control', {})
    if not isinstance(control_info, dict) or control_info.get('type') != 'node': return None
    
    v_gs_th = edge.get('threshold_voltage', 0.0)
    
    gate_node = control_info.get('gate')
    try:
        v_g = node_voltages.get(f"V{gate_node}", node_voltages.get(gate_node))
        source_node = edge['to'] if edge.get('direction', True) else edge['from']
        v_s = node_voltages.get(f"V{source_node}", node_voltages.get(source_node))
        if v_g is None or v_s is None: return None
    except KeyError: return None

    diff = sp.sympify(str(v_g)) - sp.sympify(str(v_s))
    mosfet_type = edge.get('mosfetType', 'nmos')
    
    if mosfet_type == 'pmos':
        if diff.is_number: return float(diff) < v_gs_th
        try:
            diff_eps = diff.subs(s, eps).evalf()
            if diff_eps.is_real: return float(diff_eps) < v_gs_th
        except (ZeroDivisionError, ValueError): pass
        return None
    else:
        if diff.is_number: return float(diff) > v_gs_th
        try:
            diff_eps = diff.subs(s, eps).evalf()
            if diff_eps.is_real: return float(diff_eps) > v_gs_th
        except (ZeroDivisionError, ValueError): pass
        return None
    
def judge_diode_on(edge: dict, node_voltages: dict, v_th_ignored: float = 0.0, eps: float = 1e-8):
    v_th = edge.get('forward_voltage_drop', 0.0)
    
    anode_node = edge['from'] if edge.get('direction', True) else edge['to']
    cathode_node = edge['to'] if edge.get('direction', True) else edge['from']
    try:
        v_anode = node_voltages.get(f"V{anode_node}", node_voltages.get(anode_node))
        v_cathode = node_voltages.get(f"V{cathode_node}", node_voltages.get(cathode_node))
        if v_anode is None or v_cathode is None: return None
    except KeyError: return None
    diff = sp.sympify(str(v_anode)) - sp.sympify(str(v_cathode))
    
    if diff.is_number: return float(diff) > v_th
    try:
        diff_eps = diff.subs(s, eps).evalf()
        if diff_eps.is_real: return float(diff_eps) > v_th
    except (ZeroDivisionError, ValueError): pass
    return None

def _node_label_plain(n):
    """Human-readable node label for plain text."""
    if n == -1: return 'V+'
    if n == -2: return 'GND'
    return f'Node {n}'

def _node_label_latex(n):
    """Node label for LaTeX."""
    if n == -1: return 'V^+'
    if n == -2: return 'GND'
    return str(n)

def _fmt_val(v):
    """Format a numeric value with engineering notation for large/small numbers."""
    if v == 0: return '0'
    av = abs(v)
    sign = '-' if v < 0 else ''
    if av == int(av) and 0.001 <= av <= 999:
        return f'{sign}{int(av)}'
    if 0.001 <= av <= 999:
        s = f'{av:.4g}'
        return f'{sign}{s}'
    # engineering notation for large / small
    exp = int(math.floor(math.log10(av)))
    mantissa = av / (10 ** exp)
    if mantissa == int(mantissa):
        return f'{sign}{int(mantissa)}e{exp}'
    return f'{sign}{mantissa:.3g}e{exp}'

def _fmt_val_latex(v):
    """Format for LaTeX with x10^{n} notation."""
    if v == 0: return '0'
    av = abs(v)
    sign = '-' if v < 0 else ''
    if av == int(av) and 0.001 <= av <= 999:
        return f'{sign}{int(av)}'
    if 0.001 <= av <= 999:
        s = f'{av:.4g}'
        return f'{sign}{s}'
    exp = int(math.floor(math.log10(av)))
    mantissa = av / (10 ** exp)
    if mantissa == int(mantissa):
        return f'{sign}{int(mantissa)} \\times 10^{{{exp}}}'
    return f'{sign}{mantissa:.3g} \\times 10^{{{exp}}}'

def _build_derivation_steps(edges, non_gnd_nodes, nod2idx, Ls, M, F, X_sol_vec, source, output, raw_user_edges=None):
    """Build detailed derivation steps for the front-end."""
    src_p, src_n = source
    out_p, out_n = output
    n = len(non_gnd_nodes)
    m = len(Ls)
    steps = []

    # ═══════════════════════════════════════════════════════════════════
    # Step 1: Small-Signal Linearization
    # ═══════════════════════════════════════════════════════════════════
    header = (
        'In small-signal analysis, nonlinear components (Diodes and MOSFETs) are '
        'linearized around their DC operating point and replaced with linear '
        'equivalents, so that Modified Nodal Analysis (MNA) can be applied.\n\n'
    )
    scan_edges = raw_user_edges if raw_user_edges else []
    lin_lines = []
    for orig in scan_edges:
        otype = orig.get('type')
        fn, tn = orig.get('from', '?'), orig.get('to', '?')
        loc = f'{_node_label_plain(fn)} -> {_node_label_plain(tn)}'

        if otype == 'diode':
            ctrl = orig.get('control', {})
            ct = ctrl.get('type', '')
            r_on = orig.get('internal_resistance', 0.01)
            vf = orig.get('forward_voltage_drop', 0.1)

            lin_lines.append(f'  Diode ({loc}):')
            lin_lines.append(f'    Forward voltage drop Vf = {_fmt_val(vf)} V')
            lin_lines.append(f'    ON-state resistance  R_on = {_fmt_val(r_on)} Ohm')
            if ct == 'auto':
                lin_lines.append(f'    Control: Auto mode')
                lin_lines.append(f'      The system checks V_anode - V_cathode > Vf at the DC operating point.')
                lin_lines.append(f'      If ON:  replaced by R_on = {_fmt_val(r_on)} Ohm (short-circuit model)')
                lin_lines.append(f'      If OFF: removed from circuit (open-circuit model)')
            elif ct == 'fixed':
                state = 'ON' if ctrl.get('state') == 'on' else 'OFF'
                lin_lines.append(f'    Control: Fixed {state}')
                if state == 'ON':
                    lin_lines.append(f'      -> Replaced by R_on = {_fmt_val(r_on)} Ohm')
                else:
                    lin_lines.append(f'      -> Removed (open circuit)')
            lin_lines.append('')

        elif otype == 'mosfet':
            ctrl = orig.get('control', {})
            ct = ctrl.get('type', '')
            rds = orig.get('rds_on', 0.01)
            vth = orig.get('threshold_voltage', 0.1)
            mtype = orig.get('mosfetType', 'nmos').upper()

            lin_lines.append(f'  MOSFET ({loc}), {mtype}:')
            lin_lines.append(f'    Threshold voltage Vth = {_fmt_val(vth)} V')
            lin_lines.append(f'    ON-state resistance Rds(on) = {_fmt_val(rds)} Ohm')
            if ct == 'timing':
                intervals = ctrl.get('intervals', [])
                d_str = ', '.join([f'{iv[0]}~{iv[1]}' for iv in intervals])
                lin_lines.append(f'    Control: Timing (duty cycle D = [{d_str}])')
                lin_lines.append(f'      This is a switching component for State-Space Averaging (SSA).')
                lin_lines.append(f'      During ON interval:  replaced by Rds(on) = {_fmt_val(rds)} Ohm')
                lin_lines.append(f'      During OFF interval: removed (open circuit)')
                lin_lines.append(f'      The final H(s) is the time-weighted average of each interval.')
            elif ct == 'fixed':
                state = 'ON' if ctrl.get('state') == 'on' else 'OFF'
                lin_lines.append(f'    Control: Fixed {state}')
                if state == 'ON':
                    lin_lines.append(f'      -> Replaced by Rds(on) = {_fmt_val(rds)} Ohm')
                else:
                    lin_lines.append(f'      -> Removed (open circuit)')
            elif ct == 'node':
                gate = ctrl.get('gate', '?')
                lin_lines.append(f'    Control: Voltage-driven (gate = Node {gate})')
                if mtype == 'NMOS':
                    lin_lines.append(f'      ON condition: V_gate - V_source > Vth = {_fmt_val(vth)} V')
                else:
                    lin_lines.append(f'      ON condition: V_gate - V_source < Vth = {_fmt_val(vth)} V')
                lin_lines.append(f'      If ON:  replaced by Rds(on) = {_fmt_val(rds)} Ohm')
                lin_lines.append(f'      If OFF: removed (open circuit)')
                lin_lines.append(f'      The system solves for a self-consistent DC operating point.')
            lin_lines.append('')

    if lin_lines:
        steps.append({
            'title': 'Step 1: Small-Signal Linearization',
            'content': header + '\n'.join(lin_lines),
            'type': 'text',
        })
    else:
        steps.append({
            'title': 'Step 1: Small-Signal Linearization',
            'content': header + 'No nonlinear components (Diode/MOSFET) found in this circuit.\nAll elements are already linear (R, L, C, Wire). MNA can be applied directly.',
            'type': 'text',
        })

    # ═══════════════════════════════════════════════════════════════════
    # Step 2: Node Identification & Unknown Variables
    # ═══════════════════════════════════════════════════════════════════
    s2_header = (
        'Modified Nodal Analysis (MNA) extends standard Nodal Analysis by\n'
        'introducing additional unknown variables for voltage-defined elements.\n\n'
        'Why "Modified"? Standard Nodal Analysis uses only node voltages as\n'
        'unknowns and requires all components to be described by admittance (Y=I/V).\n'
        'However, voltage sources (V=const) and inductors (V=L·di/dt) are defined\n'
        'by voltage constraints, not admittance. Their admittance is either infinite\n'
        '(voltage source) or frequency-dependent in a way that couples voltage and\n'
        'current. MNA solves this by adding the currents through these elements\n'
        'as extra unknowns, and their defining equations as extra rows in the matrix.\n\n'
    )
    s2_lines = [f'Reference node (GND): {_node_label_plain(src_n)}  (voltage = 0)\n']
    s2_lines.append('Node voltages (from KCL at each non-reference node):')
    for node in non_gnd_nodes:
        idx = nod2idx[node]
        if node >= 1000:
            s2_lines.append(f'  V{idx+1}  ->  Virtual node {node} (internal node of series segment)')
        else:
            s2_lines.append(f'  V{idx+1}  ->  {_node_label_plain(node)}')
    if m > 0:
        s2_lines.append(f'\nInductor currents (because V = L·di/dt is a voltage constraint,')
        s2_lines.append(f'  the inductor current must be an extra unknown):')
        for i in range(m):
            s2_lines.append(f'  I_L{i+1}  ->  Current through inductor {i+1}')
    s2_lines.append(f'\nVoltage source current (because Vin is a voltage constraint,')
    s2_lines.append(f'  its current I_Vin must be an extra unknown):')
    s2_lines.append(f'  I_Vin  ->  Current delivered by the voltage source')
    s2_lines.append(f'\nTotal unknowns: {n + m + 1}  ({n} node voltages + {m} inductor currents + 1 source current)')
    steps.append({
        'title': 'Step 2: Node Identification & Unknown Variables',
        'content': s2_header + '\n'.join(s2_lines),
        'type': 'text',
    })

    # ═══════════════════════════════════════════════════════════════════
    # Step 3: Admittance Stamps & Stamping Rules
    # ═══════════════════════════════════════════════════════════════════
    s3_header = (
        'Each component contributes ("stamps") values into the MNA matrix.\n'
        'The stamping rules for a component between node i and node j:\n\n'
        '  Resistor (G=1/R):  Y[i,i]+=G,  Y[j,j]+=G,  Y[i,j]-=G,  Y[j,i]-=G\n'
        '  Capacitor (Y=sC):  same pattern with sC instead of G\n'
        '  Inductor (V=sL·I): adds current variable I_Lk and equations:\n'
        '      Row i: +1 at I_Lk column  |  Row j: -1 at I_Lk column\n'
        '      I_Lk row: +1 at Vi, -1 at Vj, -sL at I_Lk (diagonal)\n'
        '  Wire (short): modeled as very large conductance G ~ 1e9\n'
        '  Voltage source: adds I_Vin variable and constraint V_node = Vin\n\n'
        'Components in the linearized circuit (after Step 1 replacements):\n'
    )
    comp_lines = []
    # Build a map from (from,to,value) to origin info for traceability
    for e in edges:
        t = e.get('type')
        f_n, t_n = e['from'], e['to']
        val = e.get('value', 0)
        fi = nod2idx.get(f_n, '?')
        ti = nod2idx.get(t_n, '?')
        loc_str = f'{_node_label_plain(f_n)} -> {_node_label_plain(t_n)}'
        idx_str = f'(matrix rows/cols: {fi}, {ti})' if fi != '?' and ti != '?' else ''
        if t == 'resistor':
            g_val = 1.0/val if val > 0 else 1e9
            # Check if this R came from a linearized MOSFET/Diode
            origin = ''
            if raw_user_edges:
                for orig in raw_user_edges:
                    if orig.get('from') == f_n and orig.get('to') == t_n:
                        if orig.get('type') == 'mosfet':
                            origin = f'  [from MOSFET Rds(on)]'
                            break
                        elif orig.get('type') == 'diode':
                            origin = f'  [from Diode R_on]'
                            break
            comp_lines.append(f'  R = {_fmt_val(val)} Ohm  ({loc_str})  ->  G = {_fmt_val(g_val)}{origin}  {idx_str}')
        elif t == 'capacitor':
            comp_lines.append(f'  C = {_fmt_val(val)} F    ({loc_str})  ->  Y = {_fmt_val(val)}*s  {idx_str}')
        elif t == 'inductor':
            comp_lines.append(f'  L = {_fmt_val(val)} H    ({loc_str})  ->  Z = {_fmt_val(val)}*s  {idx_str}')
        elif t == 'none':
            comp_lines.append(f'  Wire              ({loc_str})  ->  G ~ 1e9  {idx_str}')
    steps.append({
        'title': 'Step 3: Admittance Stamps & Stamping Rules',
        'content': s3_header + '\n'.join(comp_lines),
        'type': 'text',
    })

    # ═══════════════════════════════════════════════════════════════════
    # Step 4: MNA Matrix Equation [Y]·[X] = [I]
    # ═══════════════════════════════════════════════════════════════════
    x_labels = []
    for node in non_gnd_nodes:
        idx = nod2idx[node]
        x_labels.append(f'V_{{{idx+1}}}')
    for i in range(m):
        x_labels.append(f'I_{{L_{{{i+1}}}}}')
    x_labels.append('I_{V_{in}}')

    try:
        m_latex = latex(M)
        x_latex = latex(Matrix(sp.symbols(' '.join(x_labels))))
        f_latex = latex(F)
        mna_eq = m_latex + ' \\cdot ' + x_latex + ' = ' + f_latex
    except Exception:
        mna_eq = None

    s4_text = (
        'The stamps from Step 3 are assembled into the matrix below.\n'
        f'Matrix size: {n+m+1} x {n+m+1}  '
        f'(rows 1~{n}: KCL for each node'
    )
    if m > 0:
        s4_text += f', rows {n+1}~{n+m}: inductor V-I equations'
    s4_text += f', row {n+m+1}: voltage source constraint)'
    steps.append({
        'title': 'Step 4a: Matrix Assembly Description',
        'content': s4_text,
        'type': 'text',
    })
    if mna_eq:
        steps.append({
            'title': 'Step 4b: MNA Matrix Equation  [Y]·[X] = [I]',
            'content': mna_eq,
            'type': 'latex',
        })
    else:
        steps.append({
            'title': 'Step 4b: MNA Matrix Equation  [Y]·[X] = [I]',
            'content': 'Matrix too large to render in LaTeX.',
            'type': 'text',
        })

    # ═══════════════════════════════════════════════════════════════════
    # Step 5: Solve for H(s)
    # ═══════════════════════════════════════════════════════════════════
    out_p_lbl = _node_label_latex(out_p)
    out_n_lbl = _node_label_latex(out_n)

    # Try to show the unsimplified Vout expression
    v_out_p_expr = X_sol_vec[nod2idx[out_p], 0] if out_p in nod2idx else sp.Integer(0)
    v_out_n_expr = X_sol_vec[nod2idx[out_n], 0] if out_n in nod2idx else sp.Integer(0)
    vout_raw = v_out_p_expr - v_out_n_expr

    s5_text = (
        f'Solving [Y]·[X] = [I] by matrix inversion: [X] = [Y]^(-1) · [I]\n\n'
        f'The output is defined as:\n'
        f'  V_out(s) = V({_node_label_plain(out_p)}) - V({_node_label_plain(out_n)})\n\n'
        f'Since Vin(s) = 1 (unit excitation in the MNA formulation):\n'
        f'  H(s) = V_out(s) / V_in(s) = V_out(s)\n\n'
        f'The symbolic result is simplified and expressed as a ratio of\n'
        f'polynomials in s (see the H(s) result above).'
    )
    steps.append({
        'title': 'Step 5a: Solving the Matrix Equation',
        'content': s5_text,
        'type': 'text',
    })

    # Show the LaTeX formula
    try:
        vout_simplified = simplify(vout_raw)
        num_v, den_v = sp.fraction(sp.together(vout_simplified))
        nc = _cleanup_and_get_coeffs(num_v)
        dc = _cleanup_and_get_coeffs(den_v)
        h_latex_final = _coeffs_to_latex(nc, dc)
    except Exception:
        h_latex_final = latex(vout_raw)

    steps.append({
        'title': 'Step 5b: Transfer Function H(s)',
        'content': (
            f'V_{{out}} = V({out_p_lbl}) - V({out_n_lbl})'
            r' \quad \Rightarrow \quad '
            f'H(s) = {h_latex_final}'
        ),
        'type': 'latex',
    })

    return steps

def build_state_matrices(edges_key, source, output, raw_user_edges=None):
    edges = json.loads(edges_key)
    src_p, src_n = source
    Rs, Ls, Cs, wires, _, _ = _split_edges(edges)
    all_nodes = set([src_n])
    for e in edges: all_nodes.add(e['from']); all_nodes.add(e['to'])
    non_gnd_nodes = sorted([n for n in all_nodes if n != src_n])
    nod2idx = {node: i for i, node in enumerate(non_gnd_nodes)}
    n = len(non_gnd_nodes)
    m = len(Ls)
    Y = zeros(n + m, n + m)
    def stamp_Y(r,c,v):
        if r in nod2idx and c in nod2idx: Y[nod2idx[r],nod2idx[c]]+=v
    for e in Rs:
        u,v=e['from'],e['to']; g=1./e['value'] if e.get('value',0)>0 else 1e9
        stamp_Y(u,u,g); stamp_Y(v,v,g); stamp_Y(u,v,-g); stamp_Y(v,u,-g)
    for e in wires:
        u,v=e['from'],e['to']; g=1e9
        stamp_Y(u,u,g); stamp_Y(v,v,g); stamp_Y(u,v,-g); stamp_Y(v,u,-g)
    for e in Cs:
        u,v=e['from'],e['to']; c_val=e['value'] if e.get('value',0)>0 else 1e-12
        stamp_Y(u,u,s*c_val); stamp_Y(v,v,s*c_val); stamp_Y(u,v,-s*c_val); stamp_Y(v,u,-s*c_val)
    for i, e in enumerate(Ls):
        u,v=e['from'],e['to']; idx=n+i
        if u in nod2idx: Y[nod2idx[u],idx]=1
        if v in nod2idx: Y[nod2idx[v],idx]=-1
        if u in nod2idx: Y[idx,nod2idx[u]]=1
        if v in nod2idx: Y[idx,nod2idx[v]]=-1
        Y[idx,idx]=-s*(e['value'] if e.get('value',0)>0 else 1e-12)
    M=zeros(n+m+1, n+m+1); M[:n+m,:n+m]=Y
    i_vin_idx=n+m
    if src_p in nod2idx: M[nod2idx[src_p],i_vin_idx]=1; M[i_vin_idx,nod2idx[src_p]]=1
    if src_n in nod2idx: M[nod2idx[src_n],i_vin_idx]=-1; M[i_vin_idx,nod2idx[src_n]]=-1
    F=zeros(n+m+1,1); F[i_vin_idx,0]=1
    try:
        X_sol_vec = M.inv() * F
    except NonInvertibleMatrixError:
        raise RuntimeError("MNA system matrix is singular")
    out_p, out_n = output
    v_out_p = X_sol_vec[nod2idx[out_p], 0] if out_p in nod2idx else 0
    v_out_n = X_sol_vec[nod2idx[out_n], 0] if out_n in nod2idx else 0
    H_expr = simplify(v_out_p - v_out_n)

    # Build derivation steps for front-end display
    try:
        derivation_steps = _build_derivation_steps(
            edges, non_gnd_nodes, nod2idx, Ls, M, F, X_sol_vec, source, output,
            raw_user_edges=raw_user_edges)
    except Exception as e:
        print(f"[STEPS] Failed to build derivation steps: {e}")
        derivation_steps = []

    return {'H': H_expr, 'solution_vector': X_sol_vec, 'node_map': nod2idx, 'gnd_node': src_n, 'steps': derivation_steps}

def enumerate_all_consistent(base_edges, source, output, vin, max_states=256):
    auto_components = []
    static_circuit = []
    for e in base_edges:
        control = e.get('control', {})
        control_type = control.get('type')
        is_auto = (e.get('type') == 'mosfet' and control_type == 'node') or \
                  (e.get('type') == 'diode' and control_type == 'auto')

        if is_auto:
            auto_components.append(e)
        elif control_type == 'fixed':
            if control.get('state') == 'on':
                e_copy = copy.deepcopy(e)
                comp_type = e_copy.get('type')
                if comp_type == 'diode':
                    e_copy['type'] = 'resistor'
                    e_copy['value'] = e_copy.get('internal_resistance', 0.01)
                elif comp_type == 'mosfet':
                    e_copy['type'] = 'resistor'
                    e_copy['value'] = e_copy.get('rds_on', 0.01)
                else:
                    e_copy['type'] = 'none'
                static_circuit.append(e_copy)
        else:
            static_circuit.append(e)

    auto_cnt = len(auto_components)
    if auto_cnt == 0:
        return [static_circuit], ""

    if 2 ** auto_cnt > max_states:
        warn_msg = f"Too many components for auto-detection ({auto_cnt}), state combinations ({2**auto_cnt}) exceed the limit ({max_states})."
        return [], warn_msg

    consistent_topologies = []
    
    print("\n" + "="*20 + " [DIAGNOSTIC LOG START] " + "="*20)
    print(f"[INFO] Starting self-consistency check for {auto_cnt} auto-component(s).")
    for i, comp in enumerate(auto_components):
        print(f"  - Component #{i+1}: {comp.get('type')} from {comp.get('from')} to {comp.get('to')}")

    for bits in itertools.product([0, 1], repeat=auto_cnt):
        state_desc = ", ".join([f"Comp#{i+1}={'ON' if bit else 'OFF'}" for i, bit in enumerate(bits)])
        print(f"\n--- [TESTING] Trying combination: ({state_desc}) ---")
        current_topo_for_solve = list(static_circuit)
        
        for i, component in enumerate(auto_components):
            e2 = copy.deepcopy(component)
            if bool(bits[i]):
                comp_type = component.get('type')
                if comp_type == 'diode':
                    e2['type'] = 'resistor'
                    e2['value'] = component.get('internal_resistance', 0.01)
                elif comp_type == 'mosfet':
                    e2['type'] = 'resistor'
                    e2['value'] = component.get('rds_on', 0.01)
                else:
                    e2['type'] = 'none'
            else:
                e2['type'] = 'resistor'
                e2['value'] = 1e12
            current_topo_for_solve.append(e2)

        is_consistent = True
        try:
            solution = build_state_matrices(json.dumps(current_topo_for_solve), source, output)
            
            print("  [OK] MNA matrix solved successfully for this combination.")

            node_voltages = {solution['gnd_node']: 0}
            for node, idx in solution['node_map'].items():
                volt_expr = solution['solution_vector'][idx, 0]
                node_voltages[node] = volt_expr.subs(s, 0).evalf() * vin
            
            voltage_log = {k: f'{v:.4f}V' for k, v in sorted(node_voltages.items())}
            print(f"  [INFO] Calculated DC voltages: {voltage_log}")
            print("  [CHECK] Verifying assumptions against calculated voltages...")

            for i, component in enumerate(auto_components):
                desired_on = bool(bits[i])
                real_on = None
                if component.get('type') == 'mosfet':
                    real_on = judge_mosfet_on(component, node_voltages)
                elif component.get('type') == 'diode':
                    real_on = judge_diode_on(component, node_voltages)

                if real_on is None:
                    real_on = False

                print(f"    - Comp#{i+1} ({component.get('type')}): Assumed={'ON' if desired_on else 'OFF'}, Calculated={'ON' if real_on else 'OFF'}")
                
                if desired_on != real_on:
                    is_consistent = False
                    print("      [FAIL] Assumption is INCONSISTENT. Rejecting this combination.")
                    break

        except RuntimeError as e:
            print(f"  [ERROR] MNA matrix was singular for this combination. Error: {e}")
            is_consistent = False
        
        if is_consistent:
            print("  [SUCCESS] This combination is self-consistent!")
            final_consistent_topo = list(static_circuit)
            for i, component in enumerate(auto_components):
                if bool(bits[i]):
                    e2 = copy.deepcopy(component)
                    comp_type = component.get('type')
                    if comp_type == 'diode':
                        e2['type'] = 'resistor'
                        e2['value'] = component.get('internal_resistance', 0.01)
                    elif comp_type == 'mosfet':
                        e2['type'] = 'resistor'
                        e2['value'] = component.get('rds_on', 0.01)
                    else:
                        e2['type'] = 'none'
                    final_consistent_topo.append(e2)
            consistent_topologies.append(final_consistent_topo)

    print("\n" + "="*22 + " [DIAGNOSTIC LOG END] " + "="*23)
    if not consistent_topologies:
        print("[FINAL_RESULT] No self-consistent states were found.")
        warn_msg = "Warning: No self-consistent circuit state was found under the current configuration. Please check for design issues (e.g., positive feedback oscillation), or adjust component parameters."
        return [], warn_msg
    else:
        print(f"[FINAL_RESULT] Found {len(consistent_topologies)} self-consistent state(s).")
    
    return consistent_topologies, ""

@app.route('/calculate_circuit', methods=['POST'])
def calculate_circuit():
    t0 = time.perf_counter()
    data = request.json
    source = tuple(data['source'])
    output = tuple(data['output'])
    vin = data.get('voltageValue', 1.0)

    base_edges = [e for e in data['edges'] if e.get('control', {}).get('type') != 'timing']
    
    consistent_topos, warn_msg = enumerate_all_consistent(base_edges, source, output, vin)
    
    if not consistent_topos:
        return jsonify({'unstable_circuit': True, 'warning_message': warn_msg})
    if len(consistent_topos) > 1:
        warn_msg += " | Warning: Multiple stable states were found, the first one was used for calculation."
    
    final_topo = consistent_topos[0]
    
    try:
        solution = build_state_matrices(json.dumps(final_topo), source, output, raw_user_edges=data['edges'])
        H_expr = solution['H']
        derivation_steps = solution.get('steps', [])
    except RuntimeError as e:
        print(f"Warning: The final stable topology resulted in a singular matrix ({e}). The transfer function is set to 0.")
        H_expr = 0
        derivation_steps = []

    num_sym, den_sym = sp.fraction(sp.together(H_expr))
    cleaned_num_coeffs = _cleanup_and_get_coeffs(num_sym)
    cleaned_den_coeffs = _cleanup_and_get_coeffs(den_sym)
    cleaned_num_poly = sp.Poly(cleaned_num_coeffs, s).as_expr()
    cleaned_den_poly = sp.Poly(cleaned_den_coeffs, s).as_expr()
    cleaned_H_expr = cleaned_num_poly / cleaned_den_poly if not cleaned_den_poly.is_zero else cleaned_num_poly
    zeros = _roots_from_coeffs(cleaned_num_coeffs)
    poles = _roots_from_coeffs(cleaned_den_coeffs)
    dc_gain = 0.0
    try:
        gain_at_zero = cleaned_H_expr.subs(s, 0)
        if gain_at_zero.is_number and gain_at_zero.is_finite: dc_gain = float(gain_at_zero.evalf())
    except Exception: pass
    
    root_locus_b64, bode_plot_b64 = '', ''
    if tf and cleaned_num_coeffs and cleaned_num_coeffs != [0.0]:
        try:
            if cleaned_den_coeffs:
                sys = tf(cleaned_num_coeffs, cleaned_den_coeffs)
                fig_rlocus, ax_rlocus = plt.subplots(); rlocus(sys, plot=True, ax=ax_rlocus)
                ax_rlocus.set_title('Root Locus'); ax_rlocus.set_xlabel('Real Axis'); ax_rlocus.set_ylabel('Imaginary Axis'); ax_rlocus.grid(True, which='both', linestyle='--'); fig_rlocus.tight_layout()
                root_locus_b64 = fig_to_base_64(fig_rlocus)
                
                bode_plot(sys, dB=True, Hz=True, plot=True)
                fig_bode = plt.gcf()
                axes = fig_bode.get_axes()
                if len(axes) >= 2:
                    mag_ax, phase_ax = axes[0], axes[1]
                    mag_ax.set_title('Bode Plot')
                    mag_ax.grid(True, which='both', linestyle='--')
                    phase_ax.grid(True, which='both', linestyle='--')
                fig_bode.tight_layout()
                bode_plot_b64 = fig_to_base_64(fig_bode)
        except Exception as e: print(f"[PLOT-ERROR] Plotting failed: {e}")

    perf_ms = int((time.perf_counter() - t0)*1000)
    return jsonify({
        'tf': str(cleaned_H_expr), 'tf_latex': _coeffs_to_latex(cleaned_num_coeffs, cleaned_den_coeffs), 'zeros': zeros,
        'poles': poles, 'dc_gain': dc_gain, 'root_locus': root_locus_b64, 'bode_plot': bode_plot_b64,
        'perf_ms': perf_ms, 'mosfet_warn': warn_msg,
        'derivation_steps': derivation_steps,
    })

@app.route('/calculate_average', methods=['POST'])
def calculate_average():
    t0 = time.perf_counter()
    data = request.json
    source = tuple(data['source'])
    output = tuple(data['output'])
    vin = data.get('voltageValue', 1.0)
    freq = data.get('acFreq', 0.0)
    base_edges = data['edges']
    timing_mosfets = []
    non_timing_nl_edges = [] 
    other_edges = []
    for edge in base_edges:
        edge_type = edge.get('type')
        if edge_type == 'mosfet':
            if edge.get('control', {}).get('type') == 'timing':
                timing_mosfets.append(edge)
            else: non_timing_nl_edges.append(edge)
        elif edge_type == 'diode':
            non_timing_nl_edges.append(edge)
        else: other_edges.append(edge)
    
    print("\n" + "="*50 + "\n           State Analysis Start\n" + "="*50)
    print("[Phase 1] Dividing time states based on Timing-Driven MOSFETs...")
    breakpoints = {0.0, 1.0}
    for mosfet in timing_mosfets:
        intervals = mosfet.get('control', {}).get('intervals', [])
        print(f"  - Detected timing points for Timing MOSFET (from:{mosfet['from']}, to:{mosfet['to']}): {intervals}")
        for interval in intervals:
            if 0.0 < float(interval[0]) < 1.0: breakpoints.add(float(interval[0]))
            if 0.0 < float(interval[1]) < 1.0: breakpoints.add(float(interval[1]))
    sorted_breakpoints = sorted(list(breakpoints))
    unique_breakpoints = [sorted_breakpoints[0]] if sorted_breakpoints else []
    for i in range(1, len(sorted_breakpoints)):
        if sorted_breakpoints[i] > sorted_breakpoints[i-1] + EPS_NUM:
            unique_breakpoints.append(sorted_breakpoints[i])
    if not unique_breakpoints or unique_breakpoints[-1] < 1.0: unique_breakpoints.append(1.0)
    intervals = []
    for i in range(len(unique_breakpoints) - 1):
        start, end = unique_breakpoints[i], unique_breakpoints[i+1]
        if start < end: intervals.append({'start': start, 'end': end, 'duration': end - start})
    print(f"  -> All time breakpoints: {unique_breakpoints}")
    print(f"  ==> Finally divided into {len(intervals)} states (time slices): {[f'[{i["start"]:.2f}, {i["end"]:.2f})' for i in intervals]}")
    print("-"*50 + "\n[Phase 2] Analyzing the circuit state for each time slice...")

    H_avg_expr = 0
    topo_cache = {}
    final_warnings = []
    ssa_derivation_steps = []  # capture steps from first interval
    for i, interval in enumerate(intervals):
        t_mid = (interval['start'] + interval['end']) / 2.0
        print(f"\n--- Analyzing State {i+1}: Time interval t = [{interval['start']:.2f}, {interval['end']:.2f}) ---")
        
        interval_base_edges = copy.deepcopy(other_edges)
        for mosfet in timing_mosfets:
            is_on = any(on_interval[0] <= t_mid < on_interval[1] for on_interval in mosfet.get('control', {}).get('intervals', []))
            if is_on:
                mosfet_copy = copy.deepcopy(mosfet)
                mosfet_copy['type'] = 'resistor'
                mosfet_copy['value'] = mosfet_copy.get('rds_on', 0.01)
                interval_base_edges.append(mosfet_copy)
        
        interval_base_edges.extend(copy.deepcopy(non_timing_nl_edges))

        topo_key = json.dumps(sorted(interval_base_edges, key=lambda x: (x.get('from', 0), x.get('to', 0))))
        if topo_key in topo_cache:
            Hi = topo_cache[topo_key]
            print("  -> [Cache] Using cached topology result.")
        else:
            consistent_topos, warn_msg = enumerate_all_consistent(interval_base_edges, source, output, vin)
            if warn_msg: final_warnings.append(warn_msg)
            if not consistent_topos:
                err_msg = warn_msg if "recommend" in warn_msg else f"No stable operating point found in the time interval {interval['start']:.2f}-{interval['end']:.2f}."
                return jsonify({'unstable_circuit': True, 'warning_message': err_msg})
            
            if len(consistent_topos) > 1:
                final_warnings.append(f"Warning: Multiple stable states were found in the {interval['start']:.2f}-{interval['end']:.2f} interval, the first one was used.")

            final_topo_for_interval = consistent_topos[0]
            
            try:
                solution = build_state_matrices(json.dumps(final_topo_for_interval), source, output, raw_user_edges=data['edges'])
                Hi = solution['H']
                if not ssa_derivation_steps:
                    ssa_derivation_steps = solution.get('steps', [])
            except RuntimeError as e:
                print(f"  -> [MNA Solver] Warning: Topology of state {i+1} resulted in a singular matrix ({e}). Contribution to transfer function is 0.")
                Hi = 0
            
            topo_cache[topo_key] = Hi
        print(f"  ==> H(s) for this state = {Hi}")
        H_avg_expr += Hi * interval['duration']

    print("="*50 + "\n             Analysis End\n" + f"Final averaged transfer function (before simplification): {H_avg_expr}\n" + "="*50 + "\n")
    H_avg_expr = simplify(H_avg_expr)
    num_sym, den_sym = sp.fraction(sp.together(H_avg_expr))
    cleaned_num_coeffs = _cleanup_and_get_coeffs(num_sym)
    cleaned_den_coeffs = _cleanup_and_get_coeffs(den_sym)
    print(f"NUM_COEFFS_FOR_PLOT: {cleaned_num_coeffs}")
    print(f"DEN_COEFFS_FOR_PLOT: {cleaned_den_coeffs}")
    cleaned_num_poly = sp.Poly(cleaned_num_coeffs, s).as_expr()
    cleaned_den_poly = sp.Poly(cleaned_den_coeffs, s).as_expr()
    if cleaned_den_poly.is_zero: return jsonify({'error': 'The denominator of the calculation result is zero, cannot generate transfer function.'}), 500
    cleaned_H_expr = cleaned_num_poly / cleaned_den_poly
    zeros = _roots_from_coeffs(cleaned_num_coeffs)
    poles = _roots_from_coeffs(cleaned_den_coeffs)
    
    dc_gain = 0.0
    try:
        gain_at_zero = cleaned_H_expr.subs(s, 0)
        if gain_at_zero.is_number and gain_at_zero.is_finite: dc_gain = float(gain_at_zero.evalf())
    except Exception: pass
    
    h_jw_str = None
    if freq > 0:
        try:
            omega = 2 * math.pi * freq
            h_jw_val = cleaned_H_expr.subs(s, sp.I * omega).evalf()
            real_part = sp.re(h_jw_val)
            imag_part = sp.im(h_jw_val)
            h_jw_str = f"{float(real_part):.4f} + {float(imag_part):.4f}j"
        except Exception:
            h_jw_str = "Calculation Error"

    root_locus_b64, bode_plot_b64 = '', ''
    if tf and cleaned_num_coeffs and cleaned_num_coeffs != [0.0]:
        try:
            if cleaned_den_coeffs:
                sys = tf(cleaned_num_coeffs, cleaned_den_coeffs)
                fig_rlocus, ax_rlocus = plt.subplots(); rlocus(sys, plot=True, ax=ax_rlocus)
                ax_rlocus.set_title('Root Locus'); ax_rlocus.set_xlabel('Real Axis'); ax_rlocus.set_ylabel('Imaginary Axis'); ax_rlocus.grid(True, which='both', linestyle='--'); fig_rlocus.tight_layout()
                root_locus_b64 = fig_to_base_64(fig_rlocus)

                bode_plot(sys, dB=True, Hz=True, plot=True)
                fig_bode = plt.gcf()
                axes = fig_bode.get_axes()
                if len(axes) >= 2:
                    mag_ax, phase_ax = axes[0], axes[1]
                    mag_ax.set_title('Bode Plot')
                    mag_ax.grid(True, which='both', linestyle='--')
                    phase_ax.grid(True, which='both', linestyle='--')
                fig_bode.tight_layout()
                bode_plot_b64 = fig_to_base_64(fig_bode)
        except Exception as e: print(f"[PLOT-ERROR] Plotting failed: {e}")
    
    perf_ms = int((time.perf_counter() - t0)*1000)
    
    response_data = {
        'tf': str(cleaned_H_expr), 'tf_latex': _coeffs_to_latex(cleaned_num_coeffs, cleaned_den_coeffs), 'zeros': zeros,
        'poles': poles, 'dc_gain': dc_gain, 'ssa_used': True, 'root_locus': root_locus_b64,
        'bode_plot': bode_plot_b64, 'perf_ms': perf_ms, 'mosfet_warn': " | ".join(list(set(final_warnings))),
        'derivation_steps': ssa_derivation_steps,
    }
    if h_jw_str is not None:
        response_data['H_jw'] = h_jw_str
    
    return jsonify(response_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
