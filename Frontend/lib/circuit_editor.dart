import 'package:flutter/material.dart';
import 'circuit_state.dart';
import 'models_component.dart';

class CircuitEditor extends StatefulWidget {
  const CircuitEditor({Key? key}) : super(key: key);
  @override
  State<CircuitEditor> createState() => _CircuitEditorState();
}

class _CircuitEditorState extends State<CircuitEditor> {
  final List<List<int>> nodePairs = const [
    [-1, 0], [1, -2], [0, 1], [2, 3], [4, 5], [6, 7],
    [0, 2], [2, 4], [4, 6], [1, 3], [3, 5], [5, 7],
  ];

  int _expandedPair = -1;
  void _togglePair(int idx) => setState(() => _expandedPair = _expandedPair == idx ? -1 : idx);

  void _openPathEditor(SeriesPath p) async {
    await showDialog(context: context, builder: (_) => _PathEditor(path: p));
    if (p.segs.isEmpty) {
      CircuitState.removePath(p);
    }
    setState(() {});
  }

  Widget _buildEdgeToggle(int idx) {
    final from = nodePairs[idx][0];
    final to = nodePairs[idx][1];
    final paths = CircuitState.paths.where((p) => p.from == from && p.to == to).toList();
    final count = paths.length;

    late final String labelText;
    if (idx == 1) {
      labelText = '$to<-$from ($count)';
    } else if ({9, 10, 11}.contains(idx)) {
      labelText = '$from<-$to ($count)';
    } else {
      labelText = '$from->$to ($count)';
    }
    return ChoiceChip(
      label: Text(labelText),
      selected: _expandedPair == idx,
      onSelected: (_) => _togglePair(idx),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: Align(
            alignment: Alignment.centerLeft,
            child: Table(
              defaultColumnWidth: const FlexColumnWidth(),
              defaultVerticalAlignment: TableCellVerticalAlignment.middle,
              children: [
                TableRow(
                  children: [0, 6, 7, 8]
                      .map((idx) => Align(alignment: Alignment.centerLeft, child: _buildEdgeToggle(idx))).toList(),
                ),
                TableRow(
                  children: [2, 3, 4, 5]
                      .map((idx) => Align(alignment: Alignment.center, child: _buildEdgeToggle(idx))).toList(),
                ),
                TableRow(
                  children: [1, 9, 10, 11]
                      .map((idx) => Align(alignment: Alignment.centerLeft, child: _buildEdgeToggle(idx))).toList(),
                ),
              ],
            ),
          ),
        ),
        if (_expandedPair >= 0) ...[
          const SizedBox(height: 12),
          Builder(builder: (_) {
            final from = nodePairs[_expandedPair][0];
            final to = nodePairs[_expandedPair][1];
            final paths = CircuitState.paths.where((p) => p.from == from && p.to == to).toList();
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('$from -> $to Configuration', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                const SizedBox(height: 4),
                Wrap(
                  spacing: 8, runSpacing: 8,
                  children: [
                    ElevatedButton.icon(
                      icon: const Icon(Icons.add), label: const Text('Add Path'),
                      onPressed: () => _openPathEditor(CircuitState.addPath(from, to)),
                    ),
                    ...paths.asMap().entries.map((entry) {
                      final i = entry.key;
                      final p = entry.value;
                      final status = p.status.label;
                      return InputChip(
                        label: Text('P${i + 1} (${p.segs.length}, $status)'),
                        onPressed: () => _openPathEditor(p),
                        onDeleted: () => setState(() => CircuitState.removePath(p)),
                      );
                    }),
                  ],
                ),
                const Divider(),
              ],
            );
          }),
        ],
      ],
    );
  }
}

class _PathEditor extends StatefulWidget {
  final SeriesPath path;
  const _PathEditor({Key? key, required this.path}) : super(key: key);

  @override
  State<_PathEditor> createState() => _PathEditorState();
}

class _PathEditorState extends State<_PathEditor> {
  late List<Segment> segs;
  
  final Map<Segment, TextEditingController> _startCtrls = {};
  final Map<Segment, TextEditingController> _endCtrls = {};
  final Map<Segment, String?> _startErrors = {};
  final Map<Segment, String?> _endErrors = {};
  final Map<Segment, TextEditingController> _valueCtrls = {};
  final Map<Segment, String?> _valueErrors = {};
  final Map<Segment, String?> _vdErrors = {};
  final Map<Segment, String?> _ronErrors = {};
  final Map<Segment, String?> _vgsThErrors = {};
  final Map<Segment, String?> _rdsOnErrors = {};

  @override
  void initState() {
    super.initState();
    segs = widget.path.segs;
    for (final seg in segs) {
      if (seg.control is TimingControl) {
        final intervals = (seg.control as TimingControl).intervals;
        if (intervals.isNotEmpty) {
          _startCtrls[seg] = TextEditingController(text: intervals.first[0].toString());
          _endCtrls[seg] = TextEditingController(text: intervals.first[1].toString());
          _validateTiming(seg);
        }
      }
      else if (seg.type == ComponentType.resistor || seg.type == ComponentType.capacitor || seg.type == ComponentType.inductor) {
        _valueCtrls[seg] = TextEditingController(text: seg.value.toString());
        _validateValue(seg, seg.value.toString());
      }
    }
  }

  @override
  void dispose() {
    _startCtrls.values.forEach((c) => c.dispose());
    _endCtrls.values.forEach((c) => c.dispose());
    _valueCtrls.values.forEach((c) => c.dispose());
    super.dispose();
  }

  void _validateTiming(Segment seg) {
    final startStr = _startCtrls[seg]?.text ?? '';
    final endStr = _endCtrls[seg]?.text ?? '';
    final start = double.tryParse(startStr);
    final end = double.tryParse(endStr);

    setState(() {
      _startErrors[seg] = null;
      _endErrors[seg] = null;

      if (start == null) {
        _startErrors[seg] = 'Not a number';
      } else if (start < 0 || start > 1) {
        _startErrors[seg] = 'Out of [0,1]';
      }

      if (end == null) {
        _endErrors[seg] = 'Not a number';
      } else if (end < 0 || end > 1) {
        _endErrors[seg] = 'Out of [0,1]';
      }
      
      if (start != null && end != null && start >= end) {
        if(_startErrors[seg] == null && _endErrors[seg] == null) {
           _startErrors[seg] = 'Start >= End';
           _endErrors[seg] = 'Start >= End';
        }
      }
    });
  }
  
  void _validateValue(Segment seg, String valueStr) {
    setState(() {
      final val = double.tryParse(valueStr);
      if (val == null) {
        _valueErrors[seg] = 'Invalid number';
      } else if (val <= 0) {
        _valueErrors[seg] = 'Must be > 0';
      } else {
        _valueErrors[seg] = null;
        seg.value = val;
      }
    });
  }

  void _validateVd(Segment seg, String valStr) {
    setState(() {
      final val = double.tryParse(valStr);
      if (val == null) {
        _vdErrors[seg] = 'Invalid number';
      } else if (val < 0) {
        _vdErrors[seg] = 'Must be >= 0';
      } else {
        _vdErrors[seg] = null;
        seg.forwardVoltageDrop = val;
      }
    });
  }

  void _validateRon(Segment seg, String valStr) {
    setState(() {
      final val = double.tryParse(valStr);
      if (val == null) {
        _ronErrors[seg] = 'Invalid number';
      } else if (val < 0) {
        _ronErrors[seg] = 'Must be >= 0';
      } else {
        _ronErrors[seg] = null;
        seg.internalResistance = val;
      }
    });
  }

  void _validateVgsTh(Segment seg, String valStr) {
    setState(() {
      final val = double.tryParse(valStr);
      if (val == null) {
        _vgsThErrors[seg] = 'Invalid number';
      } else {
        _vgsThErrors[seg] = null;
        seg.thresholdVoltage = val;
      }
    });
  }

  void _validateRdsOn(Segment seg, String valStr) {
    setState(() {
      final val = double.tryParse(valStr);
      if (val == null) {
        _rdsOnErrors[seg] = 'Invalid number';
      } else if (val < 0) {
        _rdsOnErrors[seg] = 'Must be >= 0';
      } else {
        _rdsOnErrors[seg] = null;
        seg.rdsOn = val;
      }
    });
  }

  String _getUnitLabel(ComponentType type) {
    return switch (type) {
      ComponentType.resistor  => 'Value (Ω)',
      ComponentType.capacitor => 'Value (F)',
      ComponentType.inductor  => 'Value (H)',
      _                       => 'Value',
    };
  }

  Widget _buildMosfetEditor(Segment seg) {
    final control = seg.control;
    String currentControlType = 'fixed';
    if (control is NodeControl) currentControlType = 'node';
    if (control is TimingControl) currentControlType = 'timing';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.start,
          children: <Widget>[
            Text('Type: ', style: TextStyle(fontWeight: FontWeight.bold)),
            SizedBox(width: 8),
            FilterChip(
              label: Text('NMOS'),
              selected: seg.mosfetType == MosfetType.nmos,
              onSelected: (sel) => setState(() => seg.mosfetType = MosfetType.nmos),
              showCheckmark: false,
              selectedColor: Colors.blue.shade100,
            ),
            SizedBox(width: 8),
            FilterChip(
              label: Text('PMOS'),
              selected: seg.mosfetType == MosfetType.pmos,
              onSelected: (sel) => setState(() => seg.mosfetType = MosfetType.pmos),
              showCheckmark: false,
              selectedColor: Colors.pink.shade100,
            ),
          ],
        ),
        const SizedBox(height: 4),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: <Widget>[
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text('D', style: TextStyle(fontWeight: FontWeight.bold)),
                Switch(value: seg.direction, onChanged: (v) => setState(() => seg.direction = v)),
                const Text('S', style: TextStyle(fontWeight: FontWeight.bold)),
                Icon(seg.direction ? Icons.arrow_forward : Icons.arrow_back, size: 18),
              ],
            ),
            DropdownButton<String>(
              value: currentControlType,
              isDense: true,
              items: const [
                DropdownMenuItem(value: 'node', child: Text('Node-Driven')),
                DropdownMenuItem(value: 'fixed', child: Text('Fixed State')),
                DropdownMenuItem(value: 'timing', child: Text('Timing u(t)')),
              ],
              onChanged: (v) {
                setState(() {
                  if (v == 'node') seg.control = NodeControl(0);
                  if (v == 'fixed') seg.control = FixedControl(true);
                  if (v == 'timing') {
                     final newCtrl = TimingControl([[0, 0.5]]);
                     seg.control = newCtrl;
                     _startCtrls[seg] = TextEditingController(text: '0.0');
                     _endCtrls[seg] = TextEditingController(text: '0.5');
                  }
                });
              },
            ),
          ],
        ),
        const SizedBox(height: 4),
        TextFormField(
          initialValue: seg.thresholdVoltage.toString(),
          decoration: InputDecoration(
            labelText: 'Vgs (V)',
            isDense: true,
            errorText: _vgsThErrors[seg],
          ),
          keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
          onChanged: (val) => _validateVgsTh(seg, val),
        ),
        const SizedBox(height: 8),
        TextFormField(
          initialValue: seg.rdsOn.toString(),
          decoration: InputDecoration(
            labelText: 'Rds (Ω)',
            isDense: true,
            errorText: _rdsOnErrors[seg],
          ),
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          onChanged: (val) => _validateRdsOn(seg, val),
        ),
        const SizedBox(height: 8),
        if (control is NodeControl)
          Row(
            children: [
              const Text('Gate Node: '),
              DropdownButton<int>(
                value: control.gateNode,
                isDense: true,
                items: [-2, -1, ...List.generate(8, (i) => i)]
                    .map((n) => DropdownMenuItem(value: n, child: Text('$n'))).toList(),
                onChanged: (v) => setState(() => control.gateNode = v!),
              ),
            ],
          )
        else if (control is FixedControl)
          Row(
            children: [
              const Text('State: '),
              Switch(value: control.isOn, onChanged: (v) => setState(() => control.isOn = v)),
              Text(control.isOn ? 'ON' : 'OFF', style: TextStyle(color: control.isOn ? Colors.green : Colors.red)),
            ],
          )
        else if (control is TimingControl)
          Row(
            children: [
              const Text('ON Interval: '),
              const SizedBox(width: 8),
              Expanded(
                child: TextField(
                  controller: _startCtrls[seg],
                  decoration: InputDecoration(
                    isDense: true, labelText: 'Start',
                    errorText: _startErrors[seg],
                  ),
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  onChanged: (val) {
                    final start = double.tryParse(val);
                    if (start != null) {
                      if (control.intervals.isEmpty) control.intervals.add([start, 0.5]);
                      else control.intervals[0][0] = start;
                    }
                    _validateTiming(seg);
                  },
                ),
              ),
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 8.0),
                child: Text('to'),
              ),
              Expanded(
                child: TextField(
                  controller: _endCtrls[seg],
                  decoration: InputDecoration(
                    isDense: true, labelText: 'End',
                    errorText: _endErrors[seg],
                  ),
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                   onChanged: (val) {
                    final end = double.tryParse(val);
                    if (end != null) {
                      if (control.intervals.isEmpty) control.intervals.add([0.0, end]);
                      else control.intervals[0][1] = end;
                    }
                    _validateTiming(seg);
                   },
                ),
              ),
            ],
          ),
      ],
    );
  }

  Widget _buildDiodeEditor(Segment seg) {
    String currentMode = 'auto';
    if (seg.control is FixedControl) {
      currentMode = (seg.control as FixedControl).isOn ? 'on' : 'off';
    }

    return Column(
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          crossAxisAlignment: CrossAxisAlignment.center,
          children: <Widget>[
            Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                const Text('+', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                Switch(
                  value: seg.forward,
                  onChanged: (v) => setState(() => seg.forward = v),
                  materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
                const Text('-', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
                const SizedBox(width: 4),
                Icon(seg.forward ? Icons.arrow_forward : Icons.arrow_back, size: 18),
              ],
            ),
            DropdownButton<String>(
              value: currentMode,
              isDense: true,
              items: const [
                DropdownMenuItem(value: 'auto', child: Text('Auto')),
                DropdownMenuItem(value: 'on', child: Text('ON')),
                DropdownMenuItem(value: 'off', child: Text('OFF')),
              ],
              onChanged: (v) {
                setState(() {
                  if (v == 'auto') seg.control = const AutoControl();
                  if (v == 'on') seg.control = FixedControl(true);
                  if (v == 'off') seg.control = FixedControl(false);
                });
              },
            ),
          ],
        ),
        const SizedBox(height: 8),
        TextFormField(
          initialValue: seg.forwardVoltageDrop.toString(),
          decoration: InputDecoration(
            labelText: 'Vth (V)',
            isDense: true,
            errorText: _vdErrors[seg],
          ),
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          onChanged: (val) => _validateVd(seg, val),
        ),
        const SizedBox(height: 8),
        TextFormField(
          initialValue: seg.internalResistance.toString(),
          decoration: InputDecoration(
            labelText: 'Ron (Ω)',
            isDense: true,
            errorText: _ronErrors[seg],
          ),
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          onChanged: (val) => _validateRon(seg, val),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final p = widget.path;
    final allSame = CircuitState.paths.where((x) => x.from == p.from && x.to == p.to).toList();
    final displayIdx = allSame.indexOf(p) + 1;

    return AlertDialog(
      title: Text('Edit Path $displayIdx  (${p.from}->${p.to})'),
      content: SizedBox(
        width: 430,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Wrap(
              spacing: 16,
              children: PathStatus.values.map((st) {
                return Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Radio<PathStatus>(value: st, groupValue: p.status, onChanged: (v) => setState(() => p.status = v!)),
                    Text(st.label),
                  ],
                );
              }).toList(),
            ),
            const Divider(),
            SizedBox(
              height: 400,
              child: ListView.builder(
                itemCount: segs.length + 1,
                itemBuilder: (_, idx) {
                  if (idx == segs.length) {
                    return TextButton.icon(
                      icon: const Icon(Icons.add), label: const Text('Add segment'),
                      onPressed: () {
                        setState(() {
                          final newSeg = Segment(ComponentType.resistor, 1);
                          _valueCtrls[newSeg] = TextEditingController(text: '1');
                          _validateValue(newSeg, '1');
                          segs.add(newSeg);
                        });
                      },
                    );
                  }
                  final seg = segs[idx];
                  return Card(
                    margin: const EdgeInsets.symmetric(vertical: 4),
                    child: Padding(
                      padding: const EdgeInsets.all(8.0),
                      child: Column(
                        children: [
                          Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              DropdownButton<ComponentType>(
                                value: seg.type,
                                items: ComponentType.values
                                    .where((t) => t != ComponentType.none && t != ComponentType.open)
                                    .map((t) => DropdownMenuItem(value: t, child: Text(t.label))).toList(),
                                onChanged: (v) => setState(() {
                                  seg.type = v!;
                                  if (v == ComponentType.diode) {
                                    seg.value = 0;
                                    seg.control = const AutoControl();
                                  }
                                  if (v == ComponentType.mosfet) {
                                    seg.control = FixedControl(true);
                                  }
                                  if ({ComponentType.resistor, ComponentType.capacitor, ComponentType.inductor}.contains(v)) {
                                      _valueCtrls[seg] = TextEditingController(text: seg.value > 0 ? seg.value.toString() : '1');
                                      _validateValue(seg, _valueCtrls[seg]!.text);
                                  }
                                }),
                              ),
                              const SizedBox(width: 16),
                              Expanded(
                                child: switch (seg.type) {
                                  ComponentType.mosfet => _buildMosfetEditor(seg),
                                  ComponentType.diode => _buildDiodeEditor(seg),
                                  _ => SizedBox(
                                      width: 70,
                                      child: TextFormField(
                                        controller: _valueCtrls[seg],
                                        decoration: InputDecoration(
                                          isDense: true,
                                          labelText: _getUnitLabel(seg.type),
                                          errorText: _valueErrors[seg],
                                        ),
                                        keyboardType: const TextInputType.numberWithOptions(decimal: true),
                                        onChanged: (val) => _validateValue(seg, val),
                                      ),
                                    ),
                                },
                              ),
                              IconButton(
                                icon: const Icon(Icons.delete), visualDensity: VisualDensity.compact,
                                onPressed: () => setState(() => segs.removeAt(idx)),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  );
                },
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Done')),
      ],
    );
  }
}
