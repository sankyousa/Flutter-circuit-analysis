from flask import Flask, request, jsonify
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

def _cleanup_and_get_coeffs(expr, precision=8, zero_threshold=1e-9):
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

def build_state_matrices(edges_key, source, output):
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
    return {'H': H_expr, 'solution_vector': X_sol_vec, 'node_map': nod2idx, 'gnd_node': src_n}

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
        solution = build_state_matrices(json.dumps(final_topo), source, output)
        H_expr = solution['H']
    except RuntimeError as e:
        print(f"Warning: The final stable topology resulted in a singular matrix ({e}). The transfer function is set to 0.")
        H_expr = 0

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
        'tf': str(cleaned_H_expr), 'tf_latex': latex(factor(cleaned_H_expr)), 'zeros': zeros,
        'poles': poles, 'dc_gain': dc_gain, 'root_locus': root_locus_b64, 'bode_plot': bode_plot_b64,
        'perf_ms': perf_ms, 'mosfet_warn': warn_msg
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
                solution = build_state_matrices(json.dumps(final_topo_for_interval), source, output)
                Hi = solution['H']
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
        'tf': str(cleaned_H_expr), 'tf_latex': latex(factor(cleaned_H_expr)), 'zeros': zeros,
        'poles': poles, 'dc_gain': dc_gain, 'ssa_used': True, 'root_locus': root_locus_b64,
        'bode_plot': bode_plot_b64, 'perf_ms': perf_ms, 'mosfet_warn': " | ".join(list(set(final_warnings)))
    }
    if h_jw_str is not None:
        response_data['H_jw'] = h_jw_str
    
    return jsonify(response_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)