import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'circuit_state.dart';
import 'package:flutter_math_fork/flutter_math.dart';

class ResultPanel extends StatefulWidget {
  const ResultPanel({Key? key}) : super(key: key);

  @override
  State<ResultPanel> createState() => _ResultPanelState();
}

class _ResultPanelState extends State<ResultPanel> {
  int startNode = 0;
  int endNode = 1;
  final ScrollController _vertCtrl = ScrollController();
  final ScrollController _horizCtrl = ScrollController();

  Map<String, dynamic> _result = {};
  bool _isLoading = false;
  String? _error;

  @override
  void dispose() {
    _vertCtrl.dispose();
    _horizCtrl.dispose();
    super.dispose();
  }

  Future<void> _calculate() async {
    setState(() {
      _isLoading = true;
      _result = {};
      _error = null;
    });

    Map<String, dynamic> payload;
    final path = CircuitState.source.isAC ? '/calculate_average' : '/calculate_circuit';

    if (CircuitState.source.isAC) {
      payload = {
        'edges': CircuitState.toEdges().map((e) => e.toJson()).toList(),
        'source': [-1, -2],
        'output': [startNode, endNode],
        'voltageValue': CircuitState.source.acAmp,
        'acFreq': CircuitState.source.acFreq,
      };
    } else {
      payload = {
        'edges': CircuitState.toEdges().map((e) => e.toJson()).toList(),
        'source': [-1, -2],
        'output': [startNode, endNode],
        'voltageValue': CircuitState.source.dcValue,
      };
    }

    final circuitJson = const JsonEncoder.withIndent('  ').convert(payload);
    
    try {
      final resp = await http.post(
        Uri.parse('http://127.0.0.1:5000$path'),
        headers: {'Content-Type': 'application/json'},
        body: circuitJson,
      );

      if (mounted) {
        if (resp.statusCode == 200) {
          setState(() {
            _result = jsonDecode(resp.body);
          });
        } else {
          setState(() {
            _error = 'Server Error (Code: ${resp.statusCode})';
          });
        }
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = 'Connection failed. Please check if the backend service is running.';
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  void _showPlotDialog(String title, String base64Image) {
    Navigator.push(context, MaterialPageRoute(builder: (context) => Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(title: Text(title)),
      body: InteractiveViewer(
        boundaryMargin: const EdgeInsets.all(double.infinity),
        minScale: 0.1, maxScale: 10,
        child: Center(child: Image.memory(base64Decode(base64Image))),
      ),
    )));
  }

  @override
  Widget build(BuildContext context) {
    final bool isUnstable = _result['unstable_circuit'] == true;
    final String warningMessage = _result['warning_message'] ?? 'Circuit is unstable.';
    
    final String tfLatex = _result['tf_latex'] ?? '';
    final num? dcGainValue = _result['dc_gain'];
    final String dcGainText = (dcGainValue != null) 
      ? r'\quad \text{(DC Gain = ' + dcGainValue.toStringAsFixed(3) + ')}' 
      : '';
    
    final h_jw = _result['H_jw'];
    
    final List zerosList = _result['zeros'] as List? ?? [];
    final List polesList = _result['poles'] as List? ?? [];
    final String formattedZeros = zerosList.join(', ');
    final String formattedPoles = polesList.join(', ');
    
    final String rootLocusImage = _result['root_locus'] ?? '';
    final String bodePlotImage = _result['bode_plot'] ?? '';
    
    final perfMs = _result['perf_ms'] ?? 0;
    final ssaUsed = _result['ssa_used'] ?? false;
    final circuitWarning = _result['mosfet_warn'] ?? '';

    final jsonPayload = const JsonEncoder.withIndent('  ').convert({
        'edges': CircuitState.toEdges().map((e) => e.toJson()).toList(),
        'source': [-1, -2], 'output': [startNode, endNode],
        'voltageValue': CircuitState.source.isAC ? CircuitState.source.acAmp : CircuitState.source.dcValue,
        if(CircuitState.source.isAC) 'acFreq': CircuitState.source.acFreq,
      });

    return Scrollbar(
      controller: _vertCtrl,
      thumbVisibility: true,
      child: SingleChildScrollView(
        controller: _vertCtrl,
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              const Text('Output:'), const SizedBox(width: 8),
              DropdownButton<int>(
                value: startNode,
                items: [-1, -2, ...List.generate(8, (i) => i)].map((n) => DropdownMenuItem(value: n, child: Text('$n'))).toList(),
                onChanged: (v) => setState(() => startNode = v!)
              ),
              const Text(' to '),
              DropdownButton<int>(
                value: endNode,
                items: [-1, -2, ...List.generate(8, (i) => i)].map((n) => DropdownMenuItem(value: n, child: Text('$n'))).toList(),
                onChanged: (v) => setState(() => endNode = v!)
              ),
            ]),
            const SizedBox(height: 12),
            ElevatedButton(onPressed: _isLoading ? null : _calculate, child: const Text('Calculate')),
            const SizedBox(height: 12),

            if (_isLoading)
              Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: const [
                  Text('H(s): ', style: TextStyle(fontSize: 16)),
                  SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2.5)),
                  SizedBox(width: 8),
                  Text('Calculating...', style: TextStyle(fontSize: 16, fontStyle: FontStyle.italic)),
                ],
              )
            else if (_error != null)
              Text('Error: $_error', style: const TextStyle(color: Colors.red, fontWeight: FontWeight.bold))
            else if (isUnstable)
              Container(
                 padding: const EdgeInsets.all(12.0),
                 decoration: BoxDecoration(color: Colors.orange.withOpacity(0.1), border: Border.all(color: Colors.orange.shade300, width: 1.5), borderRadius: BorderRadius.circular(8.0)),
                 child: Row(children: [Icon(Icons.warning_amber_rounded, color: Colors.orange.shade800), const SizedBox(width:12), Expanded(child: Text(warningMessage, style: TextStyle(color: Colors.orange.shade900, fontWeight: FontWeight.w500)))])
              )
            else if (_result.isNotEmpty) ...[
              Scrollbar(
                controller: _horizCtrl,
                thumbVisibility: true,
                child: SingleChildScrollView(
                  controller: _horizCtrl,
                  scrollDirection: Axis.horizontal,
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 10),
                    child: Math.tex(
                      'H(s)= $tfLatex$dcGainText',
                      mathStyle: MathStyle.display,
                      textStyle: const TextStyle(fontSize: 16),
                    ),
                  ),
                ),
              ),

              if (h_jw != null) ...[
                const SizedBox(height: 8),
                Scrollbar(
                  thumbVisibility: true,
                  child: SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 4),
                      child: Math.tex(
                        'H(j\\omega)|_{f=${CircuitState.source.acFreq}\\text{Hz}} = ${h_jw.toString()}',
                        mathStyle: MathStyle.display,
                        textStyle: const TextStyle(fontSize: 16),
                      ),
                    ),
                  ),
                )
              ],
              const SizedBox(height: 8),

              Text('Zeros(${zerosList.length}): $formattedZeros', style: const TextStyle(color: Colors.green)),
              Text('Poles(${polesList.length}): $formattedPoles', style: const TextStyle(color: Colors.red)),
              const SizedBox(height: 8),

              Row(
                children: [
                  if (rootLocusImage.isNotEmpty) TextButton(onPressed: () => _showPlotDialog('Root Locus', rootLocusImage), child: const Text('View Root Locus')),
                  if (bodePlotImage.isNotEmpty) TextButton(onPressed: () => _showPlotDialog('Bode Plot', bodePlotImage), child: const Text('View Bode Plot')),
                ],
              ),
              const Divider(),
            ],

            if (_result.isNotEmpty) ...[
              Row(children: [
                const Text('Solver: ', style: TextStyle(fontWeight: FontWeight.bold)), Text(ssaUsed ? 'State-Space Average' : 'DC Analysis'), const SizedBox(width: 16), Text('Time: $perfMs ms'),
              ]),
              if (circuitWarning.isNotEmpty) ...[
                const SizedBox(height: 4),
                Text('Warning: $circuitWarning', style: const TextStyle(color: Colors.orange)),
              ],
              const SizedBox(height: 24),
              Row(children: [
                const Text('Request JSON:', style: TextStyle(fontWeight: FontWeight.bold)),
                IconButton(
                  icon: const Icon(Icons.copy, size: 18),
                  onPressed: () {
                    Clipboard.setData(ClipboardData(text: jsonPayload));
                    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Copied'), duration: Duration(milliseconds: 500)));
                  },
                ),
              ]),
              Scrollbar(thumbVisibility: true, child: SingleChildScrollView(scrollDirection: Axis.horizontal, child: SelectableText(jsonPayload))),
            ]
          ],
        ),
      ),
    );
  }
}