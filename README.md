# Flutter Circuit Analysis App

A cross-platform circuit analysis application built with **Flutter** (frontend) and **Python Flask** (backend). This app allows users to visually build circuit topologies, configure component parameters, and automatically compute transfer functions, Bode plots, root locus, and more.

## Project Structure

```
├── Frontend/          # Flutter app (Dart)
│   ├── lib/           # Core source code (7 files)
│   ├── assets/        # Image resources
│   ├── android/       # Android platform config
│   ├── windows/       # Windows platform config
│   └── pubspec.yaml   # Flutter dependencies
│
└── Backend/           # Python Flask server
    ├── app.py         # Main backend application
    ├── compare_plots.py   # Bode plot comparison script
    ├── tests/         # Unit and integration tests
    └── requirements.txt   # Python dependencies
```

## Features

- **Visual Circuit Editor**: Build circuit topologies with resistors, capacitors, inductors, diodes, MOSFETs, and voltage sources
- **Modified Nodal Analysis (MNA)**: Automatic construction and solving of MNA matrices
- **Small Signal Analysis**: Linearization of nonlinear circuits at the operating point
- **State Space Averaging (SSA)**: Analysis of switching circuits with MOSFET timing control
- **Transfer Function Derivation**: Symbolic computation of transfer functions using SymPy
- **Visualization**: Bode plots, root locus, pole-zero maps rendered in LaTeX format
- **Cross-Platform**: Runs on Android and Windows

## Prerequisites

- **Flutter SDK** 3.27.3 or later ([Install Flutter](https://docs.flutter.dev/get-started/install))
- **Python** 3.12+ ([Download Python](https://www.python.org/downloads/))

## Getting Started

### 1. Backend Setup

```bash
cd Backend
pip install -r requirements.txt
python app.py
```

The backend server will start on `http://127.0.0.1:5000`.

### 2. Frontend Setup

```bash
cd Frontend
flutter pub get
flutter run
```

> **Note**: When running the app, make sure the backend server is running first. If testing on a physical Android device, update the API base URL in the frontend code to point to your computer's local IP address instead of `127.0.0.1`.

### 3. Running Tests

**Backend tests:**
```bash
cd Backend
pytest tests/
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Frontend Framework | Flutter 3.27.3 (Dart 3.6.1) |
| UI Math Rendering | flutter_math_fork 0.7.2 |
| Backend Framework | Python Flask |
| Symbolic Computation | SymPy |
| Matrix Operations | NumPy |
| Control Systems | SciPy |
| Plotting | Matplotlib |
| API Communication | HTTP (REST) |

## Usage

1. Launch the backend server (`python app.py`)
2. Run the Flutter app (`flutter run`)
3. Use the visual editor to add node pairs and build circuit paths
4. Configure component parameters (resistance, capacitance, etc.)
5. Set voltage source and output node pairs
6. Tap "Calculate" to send the circuit to the backend
7. View results: transfer function expression, Bode plot, root locus, and pole-zero map

## License

This project is developed as a Master's dissertation at Nanyang Technological University, School of Electrical and Electronic Engineering.
