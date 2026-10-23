window.SHOT_DATA = {
  "motion": {
    "schema": "tidelight-cinematic-shot-motion-1",
    "status": "LOCAL_MOTION_SPEC",
    "source": {
      "frozen_scene": "../../scene.py",
      "frozen_sha256": "03484bd17d1f9c3e0a280c0d1302462181d1b1ec1e348d643232afb1faa6562c",
      "extension": "../shot_scene.py",
      "relative_to": "this metadata directory"
    },
    "timeline": {
      "fps": 24,
      "duration_seconds": 10.0,
      "frame_start": 0,
      "frame_end": 239,
      "sample_times_seconds": [
        0.0,
        5.0,
        9.958333333333334
      ],
      "preview_resolution": [
        960,
        540
      ],
      "target_resolution": [
        1920,
        1080
      ],
      "fallback_resolution": [
        1600,
        900
      ],
      "selected_resolution": [
        1600,
        900
      ]
    },
    "water": {
      "equation": "eta(x,y,t)=sum_i A_i*sin(kx_i*x+ky_i*y-sqrt(g*|k_i|)*(0.42*t)+phi_i)",
      "gravity_m_per_s2": 9.81,
      "artistic_time_scale": 0.42,
      "terms": [
        {
          "amplitude_m": 0.09,
          "kx_rad_per_m": 0.42,
          "ky_rad_per_m": 0.095,
          "phase_rad": 0.25
        },
        {
          "amplitude_m": 0.042,
          "kx_rad_per_m": 0.93,
          "ky_rad_per_m": -0.16,
          "phase_rad": 1.7
        },
        {
          "amplitude_m": 0.02,
          "kx_rad_per_m": 1.8,
          "ky_rad_per_m": 0.41,
          "phase_rad": -0.8
        },
        {
          "amplitude_m": 0.012,
          "kx_rad_per_m": -0.72,
          "ky_rad_per_m": 1.12,
          "phase_rad": 2.35
        }
      ],
      "vertex_update": "vertex.co.z=eta(vertex_base_x,vertex_base_y,t); object world Z remains -0.04 scene units",
      "shader_fine_normal_drift": "Mapping.Location=t*(0.065,-0.023,0.0)"
    },
    "mist": {
      "equation": "density=base_density*heightfalloff(z)*clamp(ramp(noise3D(Generated*(0.85,0.85,1.05)+t*(0.075,0.030,0.0))),0.18,1.28)",
      "noise_dimensions": "3D",
      "noise_scale": 2.2,
      "noise_detail": 4.0,
      "noise_roughness": 0.66,
      "noise_mapping_scale": [
        0.85,
        0.85,
        1.05
      ],
      "advection_per_second": [
        0.075,
        0.03,
        0.0
      ],
      "ramp": {
        "factor_low": 0.18,
        "value_low": 0.18,
        "factor_high": 0.78,
        "value_high": 1.28,
        "clamp": true
      },
      "height_falloff": {
        "coordinate": "Generated.Z",
        "from": [
          0.0,
          1.0
        ],
        "to": [
          0.65,
          0.03
        ],
        "clamp": true
      },
      "display_color": [
        0.68,
        0.8,
        0.96
      ],
      "claim_boundary": "procedural advected density field; not a fluid simulation"
    },
    "camera": {
      "start_location": [
        0.0,
        -18.5,
        1.42
      ],
      "start_target": [
        0.0,
        28.0,
        0.35
      ],
      "path": "smoothstep(p) with p=t/10: x=1.25*p_ease, y=-18.5+3.0*p_ease, z=1.42+0.08*sin(pi*p)",
      "target_path": "x=0.85*p_ease, y=28+3*p_ease, z=0.35+0.08*sin(pi*p)",
      "lens_mm": 32.5,
      "dof_fstop": 7.1,
      "purpose": "slow lateral/dolly move past real near wet stone geometry for parallax",
      "focus_distance": "19.0 + 2.4*smoothstep(clip(t/10,0,1))"
    },
    "foreground_wetness": {
      "material": "MAT_cinematic_wet_foreground",
      "world_z_range_m": [
        -0.3,
        1.2
      ],
      "roughness_range": [
        0.11,
        0.58
      ],
      "coat_weight_range": [
        0.42,
        0.12
      ],
      "mapping": "clamped linear world-Z map; lower stones are wetter"
    },
    "foreground_surface_detail": {
      "noise_scale": 260.0,
      "noise_detail": 2.5,
      "noise_roughness": 0.42,
      "microbump_strength": 0.16,
      "microbump_distance_m": 0.012
    },
    "render": {
      "engine": "CYCLES",
      "device": "frozen _configure_cycles Metal probe, CPU fallback",
      "preview_samples": 32,
      "movie_samples": 24,
      "seed": 13579,
      "denoising": true,
      "selected_device": "METAL"
    },
    "units_note": "Lengths are uncalibrated scene units. Historical _m field names denote an assumed scale only."
  },
  "storyboard": {
    "width": 1600,
    "height": 900,
    "fps": 24,
    "duration_seconds": 50,
    "continuous_shot_seconds": 10,
    "chapters": [
      {
        "name": "THE SHOT",
        "title": "A world in motion.",
        "subtitle": "Ten seconds. One continuous camera move.",
        "equations": [],
        "detail": "Original procedural scene \u00b7 Blender Cycles \u00b7 240 individually rendered frames",
        "start": 0,
        "end": 10
      },
      {
        "name": "01 / MOVING WATER",
        "title": "Give the waves a clock.",
        "subtitle": "Four traveling waves move the actual surface mesh.",
        "equations": [
          "\\eta(x,y,t)=\\sum_{i=1}^{4} A_i\\sin(k_{xi}x+k_{yi}y-\\omega_i\\tau+\\phi_i)",
          "\\omega_i=\\sqrt{9.81\\,\\|\\mathbf{k}_i\\|},\\qquad \\tau=0.42t"
        ],
        "detail": "Dispersion-inspired waves with an artistic time scale; fine shader normals drift separately.",
        "start": 10,
        "end": 20
      },
      {
        "name": "02 / DRIFTING MIST",
        "title": "Move a field through the light.",
        "subtitle": "The density changes in space and drifts over time.",
        "equations": [
          "\\mathbf{q}=\\operatorname{diag}(0.85,0.85,1.05)\\mathbf{g}+t(0.075,0.030,0)",
          "D(\\mathbf{g},t)=0.028(0.65-0.62g_z)\\,R\\!\\left(N(2.2\\mathbf{q})\\right)"
        ],
        "detail": "g is Generated space; N is 3D noise (detail 4, roughness 0.66). R(n) = 0.18 + 1.10 clip((n\u22120.18)/0.60, 0, 1). Procedural advection; no fluid simulation.",
        "start": 20,
        "end": 30
      },
      {
        "name": "03 / WET STONE",
        "title": "Let the waterline shape the surface.",
        "subtitle": "Lower stone is smoother and more strongly coated.",
        "equations": [
          "u=\\operatorname{clip}\\!\\left(\\frac{z+0.3}{1.5},0,1\\right)",
          "r(z)=0.11+0.47u,\\qquad w_{\\rm coat}(z)=0.42-0.30u"
        ],
        "detail": "z is world-space height. This authored wetness gradient is applied to the two added foreground stones.",
        "start": 30,
        "end": 40
      },
      {
        "name": "04 / THE CAMERA",
        "title": "A smooth path through the inlet.",
        "subtitle": "Foreground stone passes faster than the distant stacks.",
        "equations": [
          "p=\\operatorname{clip}(t/10,0,1),\\qquad s=p^2(3-2p)",
          "\\mathbf{C}(t)=\\left(1.25s,\\;-18.5+3s,\\;1.42+0.08\\sin(\\pi p)\\right)"
        ],
        "detail": "32.5 mm lens \u00b7 f/7.1. A moving look-at target keeps the inlet composed. Lengths are scene units.",
        "start": 40,
        "end": 50
      }
    ],
    "disclosure": "Same ten-second 3D-rendered shot replayed for four mathematical explanations. No optical-flow interpolation or image warping."
  }
};
