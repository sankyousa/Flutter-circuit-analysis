enum ComponentType {
  none,
  resistor,
  capacitor,
  inductor,
  diode,
  open,
  mosfet,
}

extension ComponentName on ComponentType {
  String get label => name;
}

enum MosfetType { nmos, pmos }

extension MosfetTypeLabel on MosfetType {
  String get label => name;
}

abstract class ComponentControl {
  const ComponentControl();
  Map<String, dynamic> toJson();
}

class AutoControl extends ComponentControl {
  const AutoControl();
  @override
  Map<String, dynamic> toJson() => {'type': 'auto'};
}

class NodeControl extends ComponentControl {
  int gateNode;
  NodeControl(this.gateNode);
  @override
  Map<String, dynamic> toJson() => {'type': 'node', 'gate': gateNode};
}

class FixedControl extends ComponentControl {
  bool isOn;
  FixedControl(this.isOn);
  @override
  Map<String, dynamic> toJson() => {'type': 'fixed', 'state': isOn ? 'on' : 'off'};
}

class TimingControl extends ComponentControl {
  List<List<double>> intervals;
  TimingControl(this.intervals);
  @override
  Map<String, dynamic> toJson() => {'type': 'timing', 'intervals': intervals};
}

class Segment {
  ComponentType type;
  double value;
  bool forward;
  ComponentControl control;
  bool direction;
  MosfetType mosfetType;
  double forwardVoltageDrop;
  double thresholdVoltage;
  double internalResistance;
  double rdsOn;


  Segment(this.type, this.value, {
    this.forward = true,
    ComponentControl? control,
    this.direction = true,
    this.mosfetType = MosfetType.nmos,
    this.forwardVoltageDrop = 0.1,
    this.thresholdVoltage = 0.1,
    this.internalResistance = 0.1,
    this.rdsOn = 0.1,
  }) : control = control ?? ((type == ComponentType.diode) ? const AutoControl() : FixedControl(true));
}

enum PathStatus { normal, short, open }
extension PathStatusLabel on PathStatus {
  String get label => name;
}

class SeriesPath {
  final int pid;
  final int from;
  final int to;
  PathStatus status;
  final List<Segment> segs;
  SeriesPath({
    required this.pid,
    required this.from,
    required this.to,
    this.status = PathStatus.normal,
    List<Segment>? segments,
  }) : segs = segments ?? [];
}

class EdgeComponent {
  int from, to;
  ComponentType type;
  double value;
  int pid;
  ComponentControl control;
  bool direction;
  MosfetType mosfetType;
  double forwardVoltageDrop;
  double thresholdVoltage;
  double internalResistance;
  double rdsOn; 


  EdgeComponent(this.from, this.to, this.type, this.value, {
    required this.pid,
    required this.control,
    this.direction = true,
    this.mosfetType = MosfetType.nmos,
    required this.forwardVoltageDrop,
    required this.thresholdVoltage,
    required this.internalResistance,
    required this.rdsOn,
  });

  Map<String, dynamic> toJson() {
    final map = <String, dynamic>{
      'from':  from,
      'to':    to,
      'type':  type.label,
      'value': value,
    };
    if (type == ComponentType.mosfet) {
      map['control'] = control.toJson();
      map['direction'] = direction;
      map['mosfetType'] = mosfetType.label;
      map['threshold_voltage'] = thresholdVoltage;
      map['rds_on'] = rdsOn;
    } else if (type == ComponentType.diode) {
      map['control'] = control.toJson();
      map['direction'] = direction;
      map['forward_voltage_drop'] = forwardVoltageDrop;
      map['internal_resistance'] = internalResistance;
    }
    return map;
  }
}

class VoltageSource {
  bool isAC;
  double dcValue;
  double acAmp;
  double acFreq;
  VoltageSource({
    required this.isAC,
    this.dcValue = 0,
    this.acAmp = 0,
    this.acFreq = 0,
  });
}