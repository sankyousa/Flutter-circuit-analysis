import 'package:flutter/material.dart';
import 'circuit_state.dart';
import 'models_component.dart';

class VoltageEditor extends StatefulWidget {
  const VoltageEditor({super.key});
  @override
  State<VoltageEditor> createState() => _VoltageEditorState();
}

class _VoltageEditorState extends State<VoltageEditor> {
  bool isAC = CircuitState.source.isAC; 
  
  late final TextEditingController dcCtrl;
  late final TextEditingController ampCtrl;
  late final TextEditingController freqCtrl;
  String? _dcError;
  String? _ampError;
  String? _freqError;
  
  @override
  void initState() {
    super.initState();
    final source = CircuitState.source;
    dcCtrl = TextEditingController(text: (source.dcValue == 0 ? 100 : source.dcValue).toString());
    ampCtrl = TextEditingController(text: (source.acAmp == 0 ? 100 : source.acAmp).toString());
    freqCtrl = TextEditingController(text: (source.acFreq == 0 ? 100 : source.acFreq).toString());
    _validateInputs();
  }

  @override
  void dispose() {
    dcCtrl.dispose();
    ampCtrl.dispose();
    freqCtrl.dispose();
    super.dispose();
  }
  
  void _validateInputs() {
    setState(() {
      _dcError = (double.tryParse(dcCtrl.text) == null) ? 'Invalid number' : null;
      _ampError = (double.tryParse(ampCtrl.text) == null) ? 'Invalid number' : null;
      final freqVal = double.tryParse(freqCtrl.text);
      if (freqVal == null) {
        _freqError = 'Invalid number';
      } else if (freqVal <= 0) {
        _freqError = 'Must be > 0';
      } else {
        _freqError = null;
      }
    });
  }

  bool get _isFormValid {
    if (isAC) {
      return _ampError == null && _freqError == null;
    } else {
      return _dcError == null;
    }
  }

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Voltage source',
              style: TextStyle(fontWeight: FontWeight.bold)),
          Row(children: [
            const Text('DC'),
            Switch(
              value: isAC,
              onChanged: (v) => setState(() {
                isAC = v;
                CircuitState.source.isAC = v;
                _validateInputs();
              }),
            ),
            const Text('AC'),
          ]),
          if (!isAC)
            TextFormField(
              controller: dcCtrl,
              decoration: InputDecoration(
                labelText: 'DC (V)',
                errorText: _dcError,
              ),
              keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
              onChanged: (_) => _validateInputs(),
            )
          else ...[
            TextFormField(
              controller: ampCtrl,
              decoration: InputDecoration(
                labelText: 'DC operating node voltage (V)',
                errorText: _ampError,
              ),
              keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
              onChanged: (_) => _validateInputs(),
            ),
            TextFormField(
              controller: freqCtrl,
              decoration: InputDecoration(
                labelText: 'Frequency (Hz)',
                errorText: _freqError,
              ),
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              onChanged: (_) => _validateInputs(),
            ),
          ],
          const SizedBox(height: 8),
          ElevatedButton(
            onPressed: _isFormValid ? () {
              CircuitState.source = VoltageSource(
                isAC: isAC,
                dcValue: double.tryParse(dcCtrl.text) ?? 0,
                acAmp: double.tryParse(ampCtrl.text) ?? 0,
                acFreq: double.tryParse(freqCtrl.text) ?? 0,
              );
              ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                content: Text('Saved'),
                duration: Duration(milliseconds: 200),
              ));
            } : null,
            child: const Text('Save'),
          ),
        ],
      );
}