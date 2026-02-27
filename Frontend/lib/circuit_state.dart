import 'models_component.dart';

class CircuitState {
  static final List<SeriesPath> paths = [];
  static Map<String, int> _nextPid = {};
  static int _nextVirtualNode = 1000;

  static SeriesPath addPath(int from, int to) {
    final key = '$from\_$to';
    final pid = _nextPid.update(key, (v) => v + 1, ifAbsent: () => 1);
    final p = SeriesPath(pid: pid, from: from, to: to, segments: [Segment(ComponentType.resistor, 1.0)]);
    paths.add(p);
    return p;
  }

  static void removePath(SeriesPath p) => paths.remove(p);
  static void insertSegment(
      {required int pid,
      required int index,
      required ComponentType type,
      required double value}) {
    final p = paths.firstWhere((it) => it.pid == pid);
    p.segs.insert(index, Segment(type, value));
  }

  static void removeSegment(int pid, int index) {
    final p = paths.firstWhere((it) => it.pid == pid);
    if (index >= 0 && index < p.segs.length) p.segs.removeAt(index);
  }

  static List<EdgeComponent> toEdges() {
    _nextVirtualNode = 1000;
    final result = <EdgeComponent>[];

    for (final p in paths) {
      if (p.status == PathStatus.open) continue;
      if (p.status == PathStatus.short) {
        result.add(EdgeComponent(
          p.from, p.to, 
          ComponentType.none, 0.0, 
          pid: p.pid, 
          control: FixedControl(true), 
          forwardVoltageDrop: 0, 
          thresholdVoltage: 0,
          internalResistance: 0.01,
          rdsOn: 0.01,
        ));
        continue;
      }

      if (p.segs.isEmpty) continue;

      int cur = p.from;
      for (int i = 0; i < p.segs.length; i++) {
        final seg = p.segs[i];
        final last = i == p.segs.length - 1;
        final next = last ? p.to : _nextVirtualNode++;

        result.add(EdgeComponent(
          cur,
          next,
          seg.type,
          seg.value,
          pid: p.pid,
          control: seg.control,
          direction: seg.type == ComponentType.diode ? seg.forward : seg.direction,
          mosfetType: seg.mosfetType,
          forwardVoltageDrop: seg.forwardVoltageDrop,
          thresholdVoltage: seg.thresholdVoltage,
          internalResistance: seg.internalResistance,
          rdsOn: seg.rdsOn,
        ));
        cur = next;
      }
    }
    return result;
  }
  static VoltageSource source = VoltageSource(isAC: false);
  static String transferFunction = '';
  static String zeros = '';
  static String poles = '';
}