
import 'package:flutter/material.dart';
import 'circuit_editor.dart';
import 'voltage_editor.dart';
import 'result_panel.dart';

class CircuitApp extends StatelessWidget {
  const CircuitApp({super.key});
  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Circuit Transfer Function Calculator')),
        body: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(children: const [
            CircuitEditor(),
            SizedBox(height: 20),
            VoltageEditor(),
            SizedBox(height: 8),
            ResultPanel(),
          ]),
        ),
      );
}