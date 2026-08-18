# Noodler patch format

Noodler patches use UTF-8 JSON and the `.noodler` extension. The format is
human-readable, diffable, and validated with Pydantic before data reaches the
audio graph. Python pickle is deliberately not used.

Every document declares both a format identity and an integer format version:

```json
{
  "format": "noodler.patch",
  "format_version": 1,
  "application_version": "0.1.0",
  "name": "Hirajoshi Garden"
}
```

Version 1 stores:

- module instance IDs, provider/type IDs, and JSON-safe parameter models;
- validated directed cables and system-output taps;
- system-output master gain;
- rack-local module positions and collapsed book-spine state;
- rack zoom and semantic control/audio rail coordinates.

It does not store audio device handles, sample buffers, oscillator phase,
random-generator progress, reverb delay memory, or whether the audio device is
currently running. Those are transient runtime details. Loading a patch should
construct fresh DSP state from the saved controls and graph.

## Shape

```json
{
  "format": "noodler.patch",
  "format_version": 1,
  "application_version": "0.1.0",
  "name": "Hirajoshi Garden",
  "modules": [
    {
      "instance_id": "vco",
      "module_type": "complex_vco",
      "provider": "builtin",
      "parameters": {
        "frequency": 220.0,
        "fine_tune_cents": 0.0,
        "amplitude": 0.22
      }
    }
  ],
  "cables": [
    {
      "source": {"module_id": "vco", "port_id": "morph"},
      "target": {"module_id": "mixer", "port_id": "input_1"}
    }
  ],
  "output_taps": [
    {
      "source": {"module_id": "reverb", "port_id": "left"},
      "gain": 1.0,
      "channel": "left"
    }
  ],
  "system_output": {"master_gain": 0.72},
  "view": {
    "zoom": 1.0,
    "rails": {"control": 20.0, "audio": 570.0},
    "nodes": [
      {
        "node_id": "wogglebug",
        "position": {"x": 430.0, "y": 20.0},
        "collapsed": true
      }
    ]
  }
}
```

Unknown fields, duplicate module or view IDs, invalid format versions, and
cables or output taps referring to unknown modules are rejected. Module
providers remain responsible for validating their parameter payload and port
compatibility when a document is instantiated as an executable patch.
